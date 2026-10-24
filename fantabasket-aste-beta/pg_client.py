"""
Client PostgreSQL per il bot aste.
Accede al DB principale per cap/slot/firme.
Se PG_URL non è configurato, tutte le funzioni restituiscono valori neutri
e loggano un warning — modalità isolata per emergenze.
"""
import logging
import os
import unicodedata
import settings as _settings

# Import lazy di psycopg2 — caricato solo se PG viene inizializzato
psycopg2 = None

logger = logging.getLogger(__name__)

_pool = None


def _normalizza(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


def _build_dsn() -> str | None:
    """Legge PG_URL e, se presente, sostituisce la password dal file secret."""
    url = os.environ.get("PG_URL")
    if not url:
        return None
    pw_file = os.environ.get("PG_PASSWORD_FILE", "/run/secrets/pg_password")
    if os.path.exists(pw_file):
        try:
            password = open(pw_file).read().strip()
            # sostituisce il placeholder o aggiunge la password
            if "password_file=" in url:
                import re
                url = re.sub(r"\?password_file=[^\s&]+", "", url)
                url = re.sub(r"&password_file=[^\s&]+", "", url)
            # psycopg2 accetta anche keyword args, usiamo PGPASSWORD
            os.environ["PGPASSWORD"] = password
        except Exception as e:
            logger.warning("Lettura pg_password_file fallita: %s", e)
    return url


def init_pg():
    global _pool, psycopg2
    dsn = _build_dsn()
    if not dsn:
        logger.warning("PG_URL non configurato — bot aste in modalità isolata (cap/slot da JSON).")
        return
    try:
        import psycopg2 as _psycopg2
        import psycopg2.pool
        import psycopg2.extras
        psycopg2 = _psycopg2
        _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=5, dsn=dsn)
        logger.info("Connessione PostgreSQL inizializzata.")
    except Exception as e:
        logger.error("Impossibile connettersi a PostgreSQL: %s — modalità isolata.", e)
        _pool = None


def pg_disponibile() -> bool:
    return _pool is not None


def _conn():
    conn = _pool.getconn()
    conn.autocommit = False
    return conn


def _putconn(conn):
    _pool.putconn(conn)


def q(sql: str, params=(), one: bool = False, many: bool = False):
    """Query generica (righe come dict) — usata dal modulo condiviso shared/ruoli_core."""
    if not pg_disponibile():
        raise RuntimeError("PostgreSQL non disponibile")
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if one:
                r = cur.fetchone()
                res = dict(r) if r else None
            elif many:
                res = [dict(x) for x in cur.fetchall()]
            else:
                res = None
        conn.commit()
        return res
    except Exception:
        conn.rollback()
        raise
    finally:
        _putconn(conn)


# ── cap e slot ────────────────────────────────────────────────────────────────
# v61 (bot principale v3.12): i conti sono in shared/cap.py, gli stessi del bot principale.
# Qui solo i controlli di disponibilità di PostgreSQL e la stagione di default.

from shared import cap as _cap   # noqa: E402


def _stagione(stagione: str | None) -> str:
    if stagione:
        return str(stagione)
    import utils
    return str(utils.get_stagione_corrente())


def _sicuro(nome: str, funzione, *args) -> int:
    if not pg_disponibile():
        return 0
    try:
        return funzione(q, *args)
    except Exception as e:
        logger.error("%s%s: %s", nome, args, e)
        return 0


def get_cap_contratti(team_id: str, stagione: str = None) -> int:
    """Contratti che pesano sul cap (in corso o RFA dichiarati), con la DPE della stagione.
    Senza `stagione` usa quella corrente."""
    return _sicuro("get_cap_contratti", _cap.cap_contratti, team_id, _stagione(stagione))


def get_impatto_taglio(team_id: str, stagione: str) -> int:
    """Spalmature dei tagli che pesano nella stagione."""
    return _sicuro("get_impatto_taglio", _cap.impatto_taglio, team_id, _stagione(stagione))


def get_roster_count(team_id: str, stagione: str = None) -> int:
    """Giocatori che occupano uno slot: contratti attivi in corso (gli x0, RFA compresi, no),
    senza chi ha una DPE approvata prima della deadline. Senza `stagione` usa quella corrente."""
    return _sicuro("get_roster_count", _cap.giocatori_in_slot, team_id, _stagione(stagione))


# ── giocatori ─────────────────────────────────────────────────────────────────

def trova_o_crea_giocatore(nome: str) -> int | None:
    """
    Cerca il giocatore per nome_norm. Se non trovato, crea un record minimale
    e logga un warning sul canale log. Restituisce il giocatore_id o None se PG non disponibile.
    """
    if not pg_disponibile():
        return None
    nome_norm = _normalizza(nome)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM giocatori WHERE nome_norm = %s", (nome_norm,))
            row = cur.fetchone()
            if row:
                return row[0]

            # Non trovato — crea record minimale
            logger.warning("Giocatore '%s' non in anagrafica PG — creo record minimale.", nome)
            cur.execute(
                "INSERT INTO giocatori (nome_bref, nome_common, nome_norm) "
                "VALUES (%s, %s, %s) RETURNING id",
                (nome, nome, nome_norm)
            )
            gid = cur.fetchone()[0]
            conn.commit()
            return gid
    except Exception as e:
        logger.error("trova_o_crea_giocatore('%s'): %s", nome, e)
        conn.rollback()
        return None
    finally:
        _putconn(conn)


# ── free agent ───────────────────────────────────────────────────────────────

def get_fa_rows_pg() -> list[dict]:
    """
    Giocatori senza contratto attivo = free agent.
    Esclude chi ha diritti 2nd pick non firmati (rookie.firmato=FALSE).
    Include fantamedia e stagione dall'ultima riga bref_stats disponibile.
    """
    if not pg_disponibile():
        return []
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT g.nome_common,
                       bs.fantamedia,
                       bs.stagione AS stagione_bref
                FROM giocatori g
                LEFT JOIN LATERAL (
                    SELECT fantamedia, stagione
                    FROM bref_stats
                    WHERE nome_bref = g.nome_bref
                    ORDER BY timestamp DESC
                    LIMIT 1
                ) bs ON TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM contratti c
                    WHERE c.giocatore_id = g.id AND c.attivo = TRUE
                )
                AND NOT EXISTS (
                    SELECT 1 FROM rookie r
                    WHERE r.giocatore_id = g.id
                      AND r.firmato = FALSE
                      AND r.diritti_scaduti = FALSE
                )
                ORDER BY bs.fantamedia DESC NULLS LAST, g.nome_norm
            """)
            return [
                {
                    "nome":          row[0],
                    "fantamedia":    float(row[1]) if row[1] is not None else None,
                    "stagione_bref": row[2],
                    "firmato":       "0",
                }
                for row in cur.fetchall()
            ]
    except Exception as e:
        logger.error("get_fa_rows_pg: %s", e)
        return []
    finally:
        conn.rollback()
        _putconn(conn)


def get_spalmato_residuo(team_id: str, giocatore_id: int, stagione_corrente: str) -> int:
    """
    Somma delle spalmate future (stagione >= stagione_corrente) per questo giocatore+team.
    Usato per calcolare il nuovo importo contratto al re-signing.
    """
    if not pg_disponibile():
        return 0
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(importo), 0)
                FROM impatto_taglio
                WHERE team_id = %s AND giocatore_id = %s AND stagione >= %s
            """, (team_id, giocatore_id, stagione_corrente))
            return cur.fetchone()[0]
    except Exception as e:
        logger.error("get_spalmato_residuo(%s, %d, %s): %s", team_id, giocatore_id, stagione_corrente, e)
        return 0
    finally:
        conn.rollback()
        _putconn(conn)


def cancella_spalmate_future(team_id: str, giocatore_id: int, stagione_corrente: str):
    """
    Rimuove le spalmate future dopo il re-signing dello stesso giocatore.
    Il nuovo contratto incorpora già lo spalmato nel suo importo.
    """
    if not pg_disponibile():
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM impatto_taglio
                WHERE team_id = %s AND giocatore_id = %s AND stagione >= %s
            """, (team_id, giocatore_id, stagione_corrente))
        conn.commit()
        logger.info("Spalmate future cancellate — giocatore_id=%d team=%s", giocatore_id, team_id)
    except Exception as e:
        conn.rollback()
        logger.error("cancella_spalmate_future(%s, %d): %s", team_id, giocatore_id, e)
    finally:
        _putconn(conn)

def registra_firma(team_id: str, nome_giocatore: str, importo: int,
                    anni: int, stagione: str, tipo: str = "normale",
                    giocatore_id: int | None = None) -> bool:
    """
    Scrive contratto + transazione 'signed' su PostgreSQL, nella stessa transazione.
    Rifirma dopo un taglio: contratto = quello firmato, le spalmature restano (v52).
    Restituisce True se ok, False se PG non disponibile o errore.
    """
    if not pg_disponibile():
        logger.warning("PG non disponibile — firma di %s non registrata su PG.", nome_giocatore)
        return False

    # v57: l'id deciso all'apertura dell'asta; il nome serve solo per le aste vecchie
    gid = giocatore_id or trova_o_crea_giocatore(nome_giocatore)
    if gid is None:
        return False

    # Rifirma dopo un taglio (v52): la spalmata resta com'è nell'impatto taglio e il
    # contratto è quello firmato. Prima veniva sommato TUTTO lo spalmato residuo
    # all'importo annuo (es. 10x2 tagliato, rifirmato 5x3 → 25x3).
    importo_finale = importo

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, "
                "stagione_firma, tipo, attivo) VALUES (%s, %s, %s, %s, %s, %s, TRUE) RETURNING id",
                (gid, team_id, importo_finale, anni, stagione, tipo)
            )
            contratto_id = cur.fetchone()[0]

            nota = f"Firma FA bot aste — {nome_giocatore} {importo_finale}M x{anni}"
            cur.execute(
                "INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, "
                "stagione, contratto_id, note) VALUES (%s, %s, NULL, %s, %s, %s, %s)",
                ("signed", gid, team_id, stagione, contratto_id, nota)
            )
        conn.commit()

        logger.info("PG: firma — %s → %s %dM x%d", nome_giocatore, team_id, importo_finale, anni)
        return True
    except Exception as e:
        conn.rollback()
        logger.error("registra_firma('%s', '%s', %d, %d): %s", nome_giocatore, team_id, importo, anni, e)
        return False
    finally:
        _putconn(conn)


def deattiva_contratto(team_id: str, importo: int, nome_giocatore: str,
                       giocatore_id: int | None = None) -> bool:
    """
    Deattiva il contratto attivo di importo specifico per questo team.
    Usato per libera_cap nelle aste RFA.
    """
    if not pg_disponibile():
        return False

    gid = giocatore_id or trova_giocatore(nome_giocatore)
    if gid is None:
        logger.warning("deattiva_contratto: '%s' non in anagrafica — gestire manualmente.", nome_giocatore)
        return False

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE contratti SET attivo = FALSE "
                "WHERE team_id = %s AND giocatore_id = %s AND attivo = TRUE "
                "RETURNING id",
                (team_id, gid)
            )
            row = cur.fetchone()
            if not row:
                logger.warning(
                    "deattiva_contratto: nessun contratto attivo trovato per %s (%s) — gestire manualmente.",
                    nome_giocatore, team_id
                )
                conn.rollback()
                return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error("deattiva_contratto('%s', '%s', %d): %s", nome_giocatore, team_id, importo, e)
        return False
    finally:
        _putconn(conn)


def trova_giocatore(nome: str) -> int | None:
    """id del giocatore per nome normalizzato, senza crearlo (None se non c'è)."""
    if not pg_disponibile():
        return None
    r = q("SELECT id FROM giocatori WHERE nome_norm = %s", (_normalizza(nome),), one=True)
    return r["id"] if r else None


def rilascia_rfa(team_id: str, nome_giocatore: str, stagione: str, giocatore_id: int | None = None) -> bool:
    """RFA lasciato andare: contratto disattivato E movimento di uscita ('expired',
    team_id_a NULL) nella stessa transazione. Senza il movimento il roster calcolato
    dalle transazioni (slot del bot aste, roster a una data, team_diff) continuava a
    contarlo nella squadra."""
    if not pg_disponibile():
        return False
    gid = giocatore_id or trova_giocatore(nome_giocatore)
    if gid is None:
        logger.warning("rilascia_rfa: '%s' non in anagrafica — gestire manualmente.", nome_giocatore)
        return False
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE contratti SET attivo = FALSE WHERE team_id = %s AND giocatore_id = %s "
                        "AND attivo = TRUE RETURNING id", (team_id, gid))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                logger.warning("rilascia_rfa: nessun contratto attivo di %s con %s.", nome_giocatore, team_id)
                return False
            cur.execute("INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, "
                        "contratto_id, note) VALUES ('expired', %s, %s, NULL, %s, %s, %s)",
                        (gid, team_id, stagione, row[0], f"RFA non rifirmato — {nome_giocatore}"))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error("rilascia_rfa('%s', '%s'): %s", team_id, nome_giocatore, e)
        return False
    finally:
        _putconn(conn)


def rfa_fuori_slot(team_id: str, nomi_rfa: list[str]) -> int:
    """Quanti RFA in corso della squadra hanno ancora un contratto attivo IN CORSO con lei
    (aste aperte a mano su contratti non finiti). Regolamento: l'RFA occupa cap ma NON slot
    finché la sua asta non è conclusa. Gli x0 sono già fuori da get_roster_count (v58)."""
    if not pg_disponibile() or not nomi_rfa:
        return 0
    r = q(f"""SELECT count(*) AS n FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
              WHERE c.team_id = %s AND c.attivo = TRUE AND g.nome_norm = ANY(%s) AND {_cap.SQL_IN_CORSO}""",
          (team_id, [_normalizza(n) for n in nomi_rfa], _stagione(None)), one=True)
    return int(r["n"]) if r else 0


def rfa_dichiarati(stagione: str) -> list[dict]:
    """RFA dichiarati nel bot principale e ancora in vigore (contratto attivo), con il
    proprietario di oggi (la dichiarazione segue il giocatore nelle trade)."""
    if not pg_disponibile():
        return []
    if not _cap.tabella_rfa(q):
        return []
    return q("""SELECT rd.giocatore_id, c.team_id, c.importo, g.nome_common
                FROM rfa_dichiarati rd
                JOIN contratti c ON c.id = rd.contratto_id AND c.attivo
                JOIN giocatori g ON g.id = rd.giocatore_id
                WHERE rd.stagione = %s AND rd.stato = 'attiva'
                ORDER BY rd.creato""", (str(stagione),), many=True) or []


def squadra_x0(giocatore_id: int | None, stagione: str) -> str | None:
    """Squadra del contratto attivo del giocatore SOLO se è finito (x0): è il contratto di
    un RFA. None se non ha un contratto attivo o se è in corso (per esempio il contratto
    nuovo appena firmato da chi ha vinto l'asta)."""
    if not pg_disponibile() or not giocatore_id:
        return None
    r = q(f"""SELECT c.team_id FROM contratti c WHERE c.giocatore_id = %s AND c.attivo = TRUE
              AND NOT {_cap.SQL_IN_CORSO}""", (giocatore_id, str(stagione)), one=True)
    return r["team_id"] if r else None


def squadre_regola_30_giorni(nome_giocatore: str, giocatore_id: int | None = None) -> set[str]:
    """Regolamento (Tagli): se un giocatore è stato tagliato, ogni franchigia che l'ha
    avuto negli ultimi 30 giorni non può firmarlo in FA né rilanciare.
    Vale se l'ultimo movimento del giocatore è un taglio: restituisce le squadre che lo
    avevano in un qualsiasi momento degli ultimi 30 giorni (chi lo aveva 30 giorni fa
    + chi l'ha ceduto o ricevuto da allora)."""
    if not pg_disponibile():
        return set()
    gid = giocatore_id or trova_giocatore(nome_giocatore)
    if gid is None:
        return set()
    ultimo = q("""SELECT tipo FROM movimenti_giocatori WHERE giocatore_id = %s
                  ORDER BY timestamp DESC, id DESC LIMIT 1""", (gid,), one=True)
    if not ultimo or ultimo["tipo"] not in ("cut", "taglio"):
        return set()
    squadre = set()
    prima = q("""SELECT team_id_a FROM movimenti_giocatori WHERE giocatore_id = %s
                 AND timestamp <= NOW() - INTERVAL '30 days'
                 ORDER BY timestamp DESC, id DESC LIMIT 1""", (gid,), one=True)
    if prima and prima["team_id_a"]:
        squadre.add(prima["team_id_a"])
    for r in q("""SELECT team_id_da, team_id_a FROM movimenti_giocatori WHERE giocatore_id = %s
                  AND timestamp > NOW() - INTERVAL '30 days'""", (gid,), many=True) or []:
        squadre.update(t for t in (r["team_id_da"], r["team_id_a"]) if t)
    return squadre


def id_giocatore_asta(asta: dict) -> int | None:
    """Id del giocatore di un'asta: quello salvato all'apertura (v57); per le aste aperte
    prima, ricerca per nome (senza mai creare giocatori)."""
    if not asta:
        return None
    chiavi = asta.keys()   # dict o sqlite3.Row
    gid = asta["giocatore_id"] if "giocatore_id" in chiavi else None
    return gid or trova_giocatore(asta["giocatore"] if "giocatore" in chiavi else "")


def id_in_roster(team_id: str, nome_common: str) -> int | None:
    """Id del giocatore con contratto attivo nella squadra e quel nome (per /nuova_rfa)."""
    if not pg_disponibile():
        return None
    r = q("""SELECT g.id FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
             WHERE c.team_id = %s AND c.attivo = TRUE AND g.nome_common = %s LIMIT 1""",
          (team_id, nome_common), one=True)
    return r["id"] if r else None


def nomi_roster(team_id: str) -> list[str]:
    """nome_common dei giocatori con contratto attivo nella squadra (per /nuova_rfa)."""
    if not pg_disponibile():
        return []
    return [r["nome_common"] for r in q(
        """SELECT g.nome_common FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
           WHERE c.team_id = %s AND c.attivo = TRUE ORDER BY g.nome_common""",
        (team_id,), many=True) or []]


def minimo_cam_thomas(nome_giocatore: str, team_id: str, giocatore_id: int | None = None) -> int | None:
    """Cam Thomas exception: se `team_id` ha fatto decadere il giocatore con questa
    regola nell'ultimo anno, il contratto di allora è il minimo per rifirmarlo."""
    if not pg_disponibile():
        return None
    gid = giocatore_id or trova_giocatore(nome_giocatore)
    if gid is None:
        return None
    r = q("""SELECT c.importo FROM movimenti_giocatori t JOIN contratti c ON c.id = t.contratto_id
             WHERE t.tipo = 'decadimento' AND t.giocatore_id = %s AND t.team_id_da = %s
               AND t.note LIKE '%%Cam Thomas%%' AND t.timestamp > NOW() - INTERVAL '1 year'
             ORDER BY t.timestamp DESC LIMIT 1""", (gid, team_id), one=True)
    return r["importo"] if r else None


# ── helper display ─────────────────────────────────────────────────────────────

def get_cap_totale(team_id: str, stagione: str, cap_pen: int = 0) -> int:
    """
    Cap lordo disponibile = cap_massimo - contratti_pg - spalmato_pg - cap_pen.
    Equivale a team["cap_disponibile"] nel vecchio sistema JSON.
    """
    return _settings.cap_limite() - get_cap_contratti(team_id, stagione) - get_impatto_taglio(team_id, stagione) - cap_pen + get_cap_anticipato(team_id)


def get_slot_totale(team_id: str, stagione: str = None) -> int:
    """
    Slot totali disponibili = max_roster - roster_count_pg + RFA in corso della squadra
    (l'RFA occupa cap ma non slot) + slot anticipato (/autoslot, 48h; fino a v54 era
    mostrato in /me ma non contava). Se stagione fornita, esclude anche i giocatori con
    DPE attiva (slot liberato).
    """
    import database as _db_aste
    nomi_rfa = [r["giocatore"] for r in _db_aste.get_rfa_proprietario(team_id)]
    return (_settings.slot_massimo() - get_roster_count(team_id, stagione=stagione)
            + rfa_fuori_slot(team_id, nomi_rfa) + get_slot_anticipato(team_id))


def get_bref_fantamedie_bulk(nomi: list[str]) -> dict[str, tuple[float | None, str | None]]:
    """
    Restituisce {nome_lower: (fantamedia, stagione)} per una lista di nomi.
    """
    if not nomi:
        return {}
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (lower(nome_bref))
                    lower(nome_bref) AS nome_key, fantamedia, stagione
                FROM bref_stats
                WHERE lower(nome_bref) = ANY(%s)
                ORDER BY lower(nome_bref), timestamp DESC
            """, ([n.lower() for n in nomi],))
            return {row[0]: (float(row[1]) if row[1] is not None else None, row[2])
                    for row in cur.fetchall()}
    finally:
        _putconn(conn)


# ── switch alla stagione in corso (Luca, 24/10) ────────────────────────────────
# /lista_fa mostra al massimo i dati dell'anno prima: chi non gioca in NBA da più di una stagione
# (ritirati, all'estero) non c'è mai. Quando almeno il 70% dei giocatori FIRMATI nella lega (contratti attivi: un numero stabile, a
# differenza dei free agent con uno storico, che crescono ogni anno) ha già giocato nella stagione in
# corso (righe di bref_stats della stagione, che si aggiungono solo quando un giocatore gioca), si
# "passa d'anno": /lista_fa non mostra più i dati della stagione prima, quindi chi non ha ancora
# giocato quest'anno sparisce dalla lista, e chi apre un'asta per lui vede un avviso. Prima dello
# switch ognuno mostra i dati più recenti che ha (quest'anno se ha giocato, se no l'anno prima).
from shared.lista_fa import QUOTA_GIOCATO  # noqa: E402  (70% dei firmati: regola in shared/lista_fa.py)


def stagione_bref_corrente() -> str:
    """La stagione di bref_stats della nostra stagione corrente ("2026" → "2027", cioè 2026-27)."""
    import utils
    return str(int(utils.load_globals().get("stagione_corrente", "2026")) + 1)


def stato_stagione(nomi: list[str]) -> dict:
    """{attivo (switch fatto), quota (firmati che hanno giocato / firmati), ultima ({nome in minuscolo:
    ultima stagione bref in cui ha giocato}, dei `nomi`), giocato (chi ha una riga della stagione in
    corso), mostrabili (chi la lista mostra: stagione in corso, o anche l'anno prima finché non c'è lo
    switch), aggiornato (ultima riga bref della stagione)}."""
    vuoto = {"attivo": False, "giocato": set(), "ultima": {}, "mostrabili": set(), "quota": 0.0, "aggiornato": None}
    if not pg_disponibile():
        return vuoto
    st = stagione_bref_corrente()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            ultima = {}
            if nomi:
                # i nomi della lista FA sono quelli comuni: si passa dall'anagrafica al nome di bref
                # (accenti e suffissi scritti diversamente: «Jokic» / «Jokić»); se non c'è, il nome così com'è
                cur.execute("""SELECT x.nome, MAX(b.stagione) FROM (
                                   SELECT lower(g.nome_common) AS nome, g.nome_bref FROM giocatori g WHERE lower(g.nome_common) = ANY(%s)
                                   UNION SELECT lower(n), n FROM unnest(%s::text[]) n) x
                               JOIN bref_stats b ON lower(b.nome_bref) = lower(x.nome_bref)
                               GROUP BY 1""", ([n.lower() for n in nomi], list(nomi)))
                ultima = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute("SELECT MAX(timestamp) FROM bref_stats WHERE stagione = %s", (st,))
            agg = cur.fetchone()[0]
    finally:
        _putconn(conn)
    # la regola è una sola, condivisa col bot principale (shared/lista_fa.py)
    from shared import lista_fa
    import utils
    quota, firmati = lista_fa.quota_firmati(q, utils.load_globals().get("stagione_corrente", "2026"))
    attivo = bool(firmati) and quota >= lista_fa.QUOTA_GIOCATO
    prima = str(int(st) - 1)
    giocato = {n for n, u in ultima.items() if u == st}
    mostrabili = giocato if attivo else {n for n, u in ultima.items() if u in (st, prima)}
    return {"attivo": attivo, "giocato": giocato, "ultima": ultima, "mostrabili": mostrabili, "quota": quota, "aggiornato": agg}


# sigle di Basketball-Reference → quelle di ESPN usate da loucabot in nba_partite
SIGLE_BREF_ESPN = {"BRK": "BKN", "PHO": "PHX", "CHO": "CHA", "NOH": "NOP"}


def dati_fa(nomi: list[str]) -> dict:
    """{nome in minuscolo: (partite giocate, squadra NBA, stagione bref, fantamedia)} dall'ultima riga di bref
    di ognuno, presa passando dall'anagrafica al nome di bref (e anche col nome così com'è): partite,
    squadra e fantamedia vengono sempre dalla stessa riga (Luca, 24/10: prima la fantamedia da una ricerca
    diversa poteva essere dell'anno prima, «FM 12.8 (2025)» per chi aveva già giocato)."""
    if not nomi or not pg_disponibile():
        return {}
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT DISTINCT ON (x.nome) x.nome, b.g, b.team, b.stagione, b.fantamedia FROM (
                               SELECT lower(g.nome_common) AS nome, g.nome_bref FROM giocatori g WHERE lower(g.nome_common) = ANY(%s)
                               UNION SELECT lower(n), n FROM unnest(%s::text[]) n) x
                           JOIN bref_stats b ON lower(b.nome_bref) = lower(x.nome_bref)
                           ORDER BY x.nome, b.stagione DESC, b.timestamp DESC""", ([n.lower() for n in nomi], list(nomi)))
            return {r[0]: (r[1], r[2], r[3], float(r[4]) if r[4] is not None else None) for r in cur.fetchall()}
    finally:
        _putconn(conn)


def partite_fa(nomi: list[str]) -> dict:
    """{nome in minuscolo: (partite, squadra, stagione bref)}: come dati_fa senza la fantamedia."""
    return {k: v[:3] for k, v in dati_fa(nomi).items()}


def posizioni_fa(nomi: list[str]) -> dict:
    """{nome comune in minuscolo: "PG/SG"} posizioni eleggibili (vista posizioni_attuali del bot principale),
    nell'ordine PG SG SF PF C; {} se la vista non c'è."""
    if not nomi or not pg_disponibile():
        return {}
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('posizioni_attuali')")
            if not cur.fetchone()[0]:
                return {}
            cur.execute("""SELECT lower(g.nome_common), p.posizioni FROM giocatori g
                           JOIN posizioni_attuali p ON p.giocatore_id = g.id WHERE lower(g.nome_common) = ANY(%s)""",
                        ([n.lower() for n in nomi],))
            ordine = ("PG", "SG", "SF", "PF", "C")
            out = {}
            for nome, pos in cur.fetchall():
                ps = {x.strip().upper() for x in (pos or "").split(",") if x.strip()}
                if ps:
                    out[nome] = "/".join(r for r in ordine if r in ps)
            return out
    finally:
        _putconn(conn)


def partite_squadre(stagione_bref: str) -> dict:
    """{squadra NBA (sigla ESPN): partite di regular season finite} nella stagione (da nba_partite di
    loucabot; la stagione di bref «2027» è per noi la 2026). {} se la tabella non c'è."""
    if not pg_disponibile():
        return {}
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('nba_partite')")
            if not cur.fetchone()[0]:
                return {}
            cur.execute("""SELECT sq, COUNT(*) FROM (
                               SELECT casa AS sq FROM nba_partite WHERE stagione = %s AND tipo = 2 AND stato = 'STATUS_FINAL'
                               UNION ALL SELECT trasferta FROM nba_partite WHERE stagione = %s AND tipo = 2 AND stato = 'STATUS_FINAL') x
                           GROUP BY sq""", (str(int(stagione_bref) - 1),) * 2)
            return {r[0]: r[1] for r in cur.fetchall()}
    finally:
        _putconn(conn)


def avviso_non_ha_giocato(nome: str) -> str:
    """La riga di avviso sotto «Quanto offri?» per un giocatore che la /lista_fa non mostrerebbe
    (Luca, 24/10: con /nuova_fa l'asta si apre per chiunque, ma si dice da quando non gioca in NBA),
    "" per gli altri."""
    try:
        st = stato_stagione([nome])
    except Exception:
        return ""
    n = nome.lower()
    if n in st["mostrabili"]:
        return ""
    u = st["ultima"].get(n)
    try:
        from zoneinfo import ZoneInfo
        quando = st["aggiornato"].astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m") if st["aggiornato"] else None
    except Exception:
        quando = None
    dati = f"; dati di Basketball-Reference aggiornati al {quando}" if quando else ""
    if not u:
        return ("\n\n⚠️ <b>Stai aprendo un'asta per un giocatore che non risulta aver mai giocato in NBA</b> "
                f"(nessuna stagione su Basketball-Reference{dati}).")
    y = int(u) - 1                       # stagione di bref «2026» = 2025-26
    return (f"\n\n⚠️ <b>Stai aprendo un'asta per un giocatore che non gioca in NBA dal {y}-{str(y + 1)[-2:]}</b> "
            f"(ultima stagione giocata{dati}).")


# ── cap/slot anticipato ───────────────────────────────────────────────────────

def get_cap_anticipato(team_id: str) -> int:
    """Cap anticipato attivo per un team (0 se non presente o scaduto)."""
    if not pg_disponibile():
        return 0
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT importo FROM cap_anticipato WHERE team_id = %s AND scade_at > NOW()",
                (team_id,)
            )
            row = cur.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.error("get_cap_anticipato(%s): %s", team_id, e)
        return 0
    finally:
        conn.rollback()
        _putconn(conn)

def set_cap_anticipato(team_id: str, importo: int, message_id: int = None) -> None:
    if not pg_disponibile():
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO cap_anticipato (team_id, importo, richiesto_at, scade_at, message_id)
                   VALUES (%s, %s, NOW(), NOW() + INTERVAL '48 hours', %s)
                   ON CONFLICT (team_id) DO UPDATE
                   SET importo=EXCLUDED.importo, richiesto_at=NOW(),
                       scade_at=NOW() + INTERVAL '48 hours', message_id=EXCLUDED.message_id""",
                (team_id, importo, message_id)
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("set_cap_anticipato(%s, %d): %s", team_id, importo, e)
    finally:
        _putconn(conn)

def reset_cap_anticipato(team_id: str) -> None:
    if not pg_disponibile():
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cap_anticipato WHERE team_id = %s", (team_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("reset_cap_anticipato(%s): %s", team_id, e)
    finally:
        _putconn(conn)

def get_anticipati_scaduti() -> list:
    if not pg_disponibile():
        return []
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT *, 'cap' as tipo FROM cap_anticipato WHERE scade_at <= NOW()")
            cap = cur.fetchall() or []
            cur.execute("SELECT *, 'slot' as tipo FROM slot_anticipato WHERE scade_at <= NOW()")
            slot = cur.fetchall() or []
            return cap + slot
    except Exception as e:
        logger.error("get_anticipati_scaduti: %s", e)
        return []
    finally:
        conn.rollback()
        _putconn(conn)

def get_slot_anticipato(team_id: str) -> int:
    if not pg_disponibile():
        return 0
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT quantita FROM slot_anticipato WHERE team_id = %s AND scade_at > NOW()",
                (team_id,)
            )
            row = cur.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.error("get_slot_anticipato(%s): %s", team_id, e)
        return 0
    finally:
        conn.rollback()
        _putconn(conn)

def set_slot_anticipato(team_id: str, quantita: int, message_id: int = None) -> None:
    if not pg_disponibile():
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO slot_anticipato (team_id, quantita, richiesto_at, scade_at, message_id)
                   VALUES (%s, %s, NOW(), NOW() + INTERVAL '48 hours', %s)
                   ON CONFLICT (team_id) DO UPDATE
                   SET quantita=EXCLUDED.quantita, richiesto_at=NOW(),
                       scade_at=NOW() + INTERVAL '48 hours', message_id=EXCLUDED.message_id""",
                (team_id, quantita, message_id)
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("set_slot_anticipato(%s, %d): %s", team_id, quantita, e)
    finally:
        _putconn(conn)

def reset_slot_anticipato(team_id: str) -> None:
    if not pg_disponibile():
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM slot_anticipato WHERE team_id = %s", (team_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("reset_slot_anticipato(%s): %s", team_id, e)
    finally:
        _putconn(conn)


# ── coda sync GAS ─────────────────────────────────────────────────────────────

def accoda_sync_gas(motivo: str = "") -> None:
    """Segnala al bot main che i fogli vanno risincronizzati.
    Il bot main processa la coda ogni 60s e aggiorna roster + scelte."""
    if not pg_disponibile():
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO gas_sync_queue (motivo) VALUES (%s)", (motivo,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.warning("accoda_sync_gas: %s", e)
    finally:
        _putconn(conn)

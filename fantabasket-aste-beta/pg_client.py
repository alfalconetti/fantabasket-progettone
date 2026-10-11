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


# ── cap ───────────────────────────────────────────────────────────────────────

def get_cap_contratti(team_id: str, stagione: str = None) -> int:
    """SUM dei contratti attivi. Se stagione fornita, usa importo_dpe quando disponibile."""
    if not pg_disponibile():
        return 0
    conn = _conn()
    try:
        with conn.cursor() as cur:
            if stagione:
                cur.execute(
                    """SELECT COALESCE(SUM(
                        COALESCE(
                            (SELECT d.importo_dpe FROM dpe d
                             WHERE d.giocatore_id = c.giocatore_id
                               AND d.team_id = c.team_id
                               AND d.stagione = %s),
                            c.importo)
                    ), 0)
                    FROM contratti c WHERE c.team_id = %s AND c.attivo = TRUE""",
                    (stagione, team_id)
                )
            else:
                cur.execute(
                    "SELECT COALESCE(SUM(importo), 0) FROM contratti "
                    "WHERE team_id = %s AND attivo = TRUE",
                    (team_id,)
                )
            return cur.fetchone()[0]
    except Exception as e:
        logger.error("get_cap_contratti(%s): %s", team_id, e)
        return 0
    finally:
        conn.rollback()
        _putconn(conn)


def get_impatto_taglio(team_id: str, stagione: str) -> int:
    """SUM delle spalmate attive per questa stagione."""
    if not pg_disponibile():
        return 0
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(importo), 0) FROM impatto_taglio "
                "WHERE team_id = %s AND stagione = %s",
                (team_id, stagione)
            )
            return cur.fetchone()[0]
    except Exception as e:
        logger.error("get_impatto_taglio(%s, %s): %s", team_id, stagione, e)
        return 0
    finally:
        conn.rollback()
        _putconn(conn)


# ── slot ──────────────────────────────────────────────────────────────────────

def get_roster_count(team_id: str, stagione: str = None) -> int:
    """Numero di giocatori nel roster. Esclude giocatori con DPE attiva (slot liberato)."""
    if not pg_disponibile():
        return 0
    conn = _conn()
    try:
        with conn.cursor() as cur:
            if stagione:
                cur.execute(
                    """SELECT COUNT(*) FROM (
                           SELECT DISTINCT ON (giocatore_id) giocatore_id, team_id_a
                           FROM transazioni
                           WHERE giocatore_id IS NOT NULL
                           ORDER BY giocatore_id, timestamp DESC
                       ) sub
                       WHERE team_id_a = %s
                         AND giocatore_id NOT IN (
                             SELECT giocatore_id FROM dpe
                             WHERE team_id = %s AND stagione = %s
                         )""",
                    (team_id, team_id, stagione)
                )
            else:
                cur.execute(
                    """SELECT COUNT(*) FROM (
                           SELECT DISTINCT ON (giocatore_id) team_id_a
                           FROM transazioni
                           WHERE giocatore_id IS NOT NULL
                           ORDER BY giocatore_id, timestamp DESC
                       ) sub
                       WHERE team_id_a = %s""",
                    (team_id,)
                )
            return cur.fetchone()[0]
    except Exception as e:
        logger.error("get_roster_count(%s): %s", team_id, e)
        return 0
    finally:
        conn.rollback()
        _putconn(conn)


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
                    anni: int, stagione: str, tipo: str = "normale") -> bool:
    """
    Scrive contratto + transazione 'signed' su PostgreSQL.
    Se il giocatore ha spalmate residue su questo team (re-signing dopo taglio):
      - somma lo spalmato all'importo del contratto
      - cancella le spalmate future (ora incorporate nel nuovo contratto)
    Restituisce True se ok, False se PG non disponibile o errore.
    """
    if not pg_disponibile():
        logger.warning("PG non disponibile — firma di %s non registrata su PG.", nome_giocatore)
        return False

    gid = trova_o_crea_giocatore(nome_giocatore)
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


def deattiva_contratto(team_id: str, importo: int, nome_giocatore: str) -> bool:
    """
    Deattiva il contratto attivo di importo specifico per questo team.
    Usato per libera_cap nelle aste RFA.
    """
    if not pg_disponibile():
        return False

    gid = trova_o_crea_giocatore(nome_giocatore)
    if gid is None:
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


def rilascia_rfa(team_id: str, nome_giocatore: str, stagione: str) -> bool:
    """RFA lasciato andare: contratto disattivato E movimento di uscita ('expired',
    team_id_a NULL) nella stessa transazione. Senza il movimento il roster calcolato
    dalle transazioni (slot del bot aste, roster a una data, team_diff) continuava a
    contarlo nella squadra."""
    if not pg_disponibile():
        return False
    gid = trova_giocatore(nome_giocatore)
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
    """Quanti RFA in corso della squadra hanno ancora il contratto attivo con lei.
    Regolamento: l'RFA continua a occupare cap ma NON slot finché la sua asta non è
    conclusa → vanno tolti dal conteggio del roster."""
    if not pg_disponibile() or not nomi_rfa:
        return 0
    r = q("""SELECT count(*) AS n FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
             WHERE c.team_id = %s AND c.attivo = TRUE AND g.nome_norm = ANY(%s)""",
          (team_id, [_normalizza(n) for n in nomi_rfa]), one=True)
    return int(r["n"]) if r else 0


def squadre_regola_30_giorni(nome_giocatore: str) -> set[str]:
    """Regolamento (Tagli): se un giocatore è stato tagliato, ogni franchigia che l'ha
    avuto negli ultimi 30 giorni non può firmarlo in FA né rilanciare.
    Vale se l'ultimo movimento del giocatore è un taglio: restituisce le squadre che lo
    avevano in un qualsiasi momento degli ultimi 30 giorni (chi lo aveva 30 giorni fa
    + chi l'ha ceduto o ricevuto da allora)."""
    if not pg_disponibile():
        return set()
    gid = trova_giocatore(nome_giocatore)
    if gid is None:
        return set()
    ultimo = q("""SELECT tipo FROM transazioni WHERE giocatore_id = %s
                  ORDER BY timestamp DESC, id DESC LIMIT 1""", (gid,), one=True)
    if not ultimo or ultimo["tipo"] not in ("cut", "taglio"):
        return set()
    squadre = set()
    prima = q("""SELECT team_id_a FROM transazioni WHERE giocatore_id = %s
                 AND timestamp <= NOW() - INTERVAL '30 days'
                 ORDER BY timestamp DESC, id DESC LIMIT 1""", (gid,), one=True)
    if prima and prima["team_id_a"]:
        squadre.add(prima["team_id_a"])
    for r in q("""SELECT team_id_da, team_id_a FROM transazioni WHERE giocatore_id = %s
                  AND timestamp > NOW() - INTERVAL '30 days'""", (gid,), many=True) or []:
        squadre.update(t for t in (r["team_id_da"], r["team_id_a"]) if t)
    return squadre


def nomi_roster(team_id: str) -> list[str]:
    """nome_common dei giocatori con contratto attivo nella squadra (per /nuova_rfa)."""
    if not pg_disponibile():
        return []
    return [r["nome_common"] for r in q(
        """SELECT g.nome_common FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
           WHERE c.team_id = %s AND c.attivo = TRUE ORDER BY g.nome_common""",
        (team_id,), many=True) or []]


def minimo_cam_thomas(nome_giocatore: str, team_id: str) -> int | None:
    """Cam Thomas exception: se `team_id` ha fatto decadere il giocatore con questa
    regola nell'ultimo anno, il contratto di allora è il minimo per rifirmarlo."""
    if not pg_disponibile():
        return None
    gid = trova_giocatore(nome_giocatore)
    if gid is None:
        return None
    r = q("""SELECT c.importo FROM transazioni t JOIN contratti c ON c.id = t.contratto_id
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


def get_cap_anticipato(team_id: str) -> int:
    """Cap anticipato attivo dal DB condiviso (tabella cap_anticipato)."""
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


def get_slot_anticipato(team_id: str) -> int:
    """Slot anticipato attivo dal DB condiviso."""
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


def get_slot_totale(team_id: str, stagione: str = None) -> int:
    """
    Slot totali disponibili = max_roster - roster_count_pg + RFA in corso della squadra
    (l'RFA occupa cap ma non slot). Se stagione fornita, esclude anche i giocatori con
    DPE attiva (slot liberato).
    """
    import database as _db_aste
    nomi_rfa = [r["giocatore"] for r in _db_aste.get_rfa_proprietario(team_id)]
    return (_settings.slot_massimo() - get_roster_count(team_id, stagione=stagione)
            + rfa_fuori_slot(team_id, nomi_rfa))


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

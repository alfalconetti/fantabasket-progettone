"""
PostgreSQL di loucabot: lo stesso database dei due bot, tabelle sue con prefisso lega_ e nba_.
Legge (mai scrive) le tabelle degli altri bot. Le righe sono dict (RealDictCursor).
"""
import logging
from datetime import datetime, timezone
import os
import re
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)
_pool = None


def init_db():
    global _pool
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL non configurato")
    pw_file = os.environ.get("PG_PASSWORD_FILE", "/run/secrets/pg_password")
    if os.path.exists(pw_file):
        os.environ["PGPASSWORD"] = open(pw_file).read().strip()
    dsn = re.sub(r"[?&]password_file=[^\s&]+", "", dsn)
    _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=5, dsn=dsn)
    migra()


@contextmanager
def get_conn():
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def q(sql, params=None, one=False, many=False):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if one:
                return cur.fetchone()
            if many:
                return cur.fetchall()
            return None


def migra():
    """Tabelle di loucabot (solo aggiunte, si può rilanciare)."""
    q("""CREATE TABLE IF NOT EXISTS lega_giornate (
            stagione       TEXT NOT NULL,
            numero         INT  NOT NULL,
            tipo           TEXT NOT NULL DEFAULT 'regular',     -- regular / playoff
            dal            DATE NOT NULL,                       -- giorni NBA (ora della costa est)
            al             DATE NOT NULL,
            media_file     TEXT[] NOT NULL DEFAULT '{}',        -- squadre NBA a media scritte nel calendario
            prima_partita  TIMESTAMPTZ,                         -- calcolate dalle partite NBA
            media          TEXT[],
            calcolato      TIMESTAMPTZ,
            PRIMARY KEY (stagione, numero))""")
    q("""CREATE TABLE IF NOT EXISTS lega_partite (
            id         SERIAL PRIMARY KEY,
            stagione   TEXT NOT NULL,
            giornata   INT  NOT NULL,
            casa       TEXT NOT NULL,                           -- team_id di teams.json
            trasferta  TEXT NOT NULL,
            UNIQUE (stagione, giornata, casa),
            UNIQUE (stagione, giornata, trasferta))""")
    q("""CREATE TABLE IF NOT EXISTS nba_partite (
            espn_id     TEXT PRIMARY KEY,
            stagione    TEXT NOT NULL,                          -- stagione della lega (2026 = 2026-27)
            tipo        INT  NOT NULL,                          -- 1 preseason, 2 regular season, 3 playoff, 5 play-in
            data_et     DATE NOT NULL,                          -- giorno della partita, ora della costa est
            inizio      TIMESTAMPTZ NOT NULL,
            casa        TEXT NOT NULL,                          -- sigla NBA (GSW, NOP, …)
            trasferta   TEXT NOT NULL,
            stato       TEXT NOT NULL,                          -- STATUS_SCHEDULED, STATUS_FINAL, STATUS_POSTPONED…
            aggiornato  TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    q("CREATE INDEX IF NOT EXISTS idx_nba_partite_data ON nba_partite (data_et)")
    q("ALTER TABLE nba_partite ADD COLUMN IF NOT EXISTS tabellino TIMESTAMPTZ")   # quando è stato scaricato
    q("""CREATE TABLE IF NOT EXISTS nba_tabellini (
            partita   TEXT NOT NULL REFERENCES nba_partite(espn_id),
            atleta    TEXT NOT NULL,                            -- id ESPN del giocatore
            nome      TEXT NOT NULL,
            squadra   TEXT NOT NULL,                            -- sigla NBA in quella partita
            titolare  BOOLEAN NOT NULL DEFAULT FALSE,
            giocato   BOOLEAN NOT NULL,                         -- entrato in campo (FALSE = a referto, DNP)
            minuti    INT NOT NULL DEFAULT 0,
            pts INT NOT NULL DEFAULT 0, fgm INT NOT NULL DEFAULT 0, fga INT NOT NULL DEFAULT 0,
            tpm INT NOT NULL DEFAULT 0, tpa INT NOT NULL DEFAULT 0, ftm INT NOT NULL DEFAULT 0,
            fta INT NOT NULL DEFAULT 0, oreb INT NOT NULL DEFAULT 0, dreb INT NOT NULL DEFAULT 0,
            ast INT NOT NULL DEFAULT 0, stl INT NOT NULL DEFAULT 0, blk INT NOT NULL DEFAULT 0,
            tov INT NOT NULL DEFAULT 0, pf INT NOT NULL DEFAULT 0,
            fp        NUMERIC(6,2) NOT NULL DEFAULT 0,          -- fantapunti (regolamento)
            PRIMARY KEY (partita, atleta))""")
    q("CREATE INDEX IF NOT EXISTS idx_nba_tabellini_atleta ON nba_tabellini (atleta)")
    q("""CREATE TABLE IF NOT EXISTS nba_infortuni (
            giorno    DATE NOT NULL,                            -- giorno della costa est dello snapshot
            atleta    TEXT NOT NULL,
            nome      TEXT NOT NULL,
            squadra   TEXT,
            stato     TEXT NOT NULL,                            -- Out, Day-To-Day, Questionable…
            dettaglio TEXT,
            preso     TIMESTAMPTZ NOT NULL DEFAULT NOW(),       -- quando: uno snapshot = tutte le righe con lo stesso preso
            PRIMARY KEY (atleta, preso))""")
    # v5.0.19: tutti gli snapshot, non più uno per giorno (prima la chiave era giorno, atleta)
    pk = q("SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint WHERE conname = 'nba_infortuni_pkey'", one=True)
    if pk and "giorno" in pk["d"]:
        q("ALTER TABLE nba_infortuni DROP CONSTRAINT nba_infortuni_pkey")
        q("ALTER TABLE nba_infortuni ADD PRIMARY KEY (atleta, preso)")
    q("CREATE INDEX IF NOT EXISTS idx_nba_infortuni_giorno ON nba_infortuni (giorno, preso)")
    q("""CREATE TABLE IF NOT EXISTS lega_calcoli (
            stagione       TEXT NOT NULL,
            giornata       INT  NOT NULL,
            stato          TEXT NOT NULL DEFAULT 'da_convalidare',   -- da_convalidare / convalidata
            versione       INT  NOT NULL DEFAULT 1,                  -- +1 a ogni ricalcolo
            calcolato      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            risultati      JSONB NOT NULL,                           -- la proposta (risultati.risultati_json)
            avvisi         JSONB,
            messaggio      BIGINT,                                   -- il messaggio da convalidare nel gruppo admin
            convalidato    TIMESTAMPTZ,
            convalidato_da BIGINT,
            PRIMARY KEY (stagione, giornata))""")
    q("""CREATE TABLE IF NOT EXISTS lega_status_validi (
            stagione   TEXT NOT NULL,
            giornata   INT  NOT NULL,
            atleta     TEXT NOT NULL,                           -- id ESPN
            stato      TEXT,                                    -- NULL = sano (disponibile)
            da         BIGINT,                                  -- l'admin che l'ha deciso
            quando     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (stagione, giornata, atleta))""")
    q("DROP TABLE IF EXISTS nba_status")                # v5.0.18, sostituita dall'ultimo snapshot di nba_infortuni
    q("""CREATE TABLE IF NOT EXISTS lega_calendario_csv (
            stagione   TEXT PRIMARY KEY,
            testo      TEXT NOT NULL,                           -- il CSV importato, tale e quale: è la mappa
            importato  TIMESTAMPTZ NOT NULL DEFAULT NOW())""")   # delle righe del foglio Calendario
    q("""CREATE TABLE IF NOT EXISTS lega_risultati (
            stagione         TEXT NOT NULL,
            giornata         INT  NOT NULL,
            casa             TEXT NOT NULL,                     -- team_id
            trasferta        TEXT NOT NULL,
            punti_casa       NUMERIC(7,2),                      -- regolamentari, bonus casa compreso
            punti_trasferta  NUMERIC(7,2),
            supp_casa        NUMERIC(7,2),                      -- i soli punti dei supplementari (se ci sono stati)
            supp_trasferta   NUMERIC(7,2),
            vince            TEXT,                              -- casa / trasferta
            convalidato      TIMESTAMPTZ,
            PRIMARY KEY (stagione, giornata, casa))""")
    q("""CREATE TABLE IF NOT EXISTS nba_atleti (
            atleta     TEXT PRIMARY KEY,                        -- id ESPN
            nome       TEXT NOT NULL,
            squadra    TEXT,
            aggiornato TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    # v33: anni di esperienza NBA dai roster ESPN (0 = esordiente), per il controllo dei dati del bot principale
    q("ALTER TABLE nba_atleti ADD COLUMN IF NOT EXISTS esperienza INT")
    # v47 (Luca, 23/10, per /carriera): ogni cambio di squadra NBA visto nei roster ESPN delle 8:30
    q("""CREATE TABLE IF NOT EXISTS nba_movimenti (
            id      SERIAL PRIMARY KEY,
            atleta  TEXT NOT NULL,                          -- id ESPN
            giorno  DATE NOT NULL,                          -- giorno NBA (costa est) in cui il bot l'ha visto
            da      TEXT,                                   -- squadra di prima (NULL: non era in nessun roster)
            a       TEXT,                                   -- squadra nuova (NULL: uscito da tutti i roster)
            preso   TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    q("CREATE INDEX IF NOT EXISTS idx_nba_movimenti_atleta ON nba_movimenti (atleta, giorno)")
    # id e nome ESPN nell'anagrafica del bot principale (giocatori.espn_id, nome_espn): è l'unica
    # cosa che loucabot scrive fuori dalle sue tabelle. Le colonne le crea anche il bot principale.
    if q("SELECT to_regclass('giocatori') AS t", one=True)["t"]:
        q("ALTER TABLE giocatori ADD COLUMN IF NOT EXISTS espn_id TEXT")
        q("ALTER TABLE giocatori ADD COLUMN IF NOT EXISTS nome_espn TEXT")
        q("CREATE UNIQUE INDEX IF NOT EXISTS idx_giocatori_espn_id ON giocatori (espn_id) WHERE espn_id IS NOT NULL")
        if q("SELECT to_regclass('lega_espn') AS t", one=True)["t"]:       # v4: tabella separata → anagrafica
            q("""UPDATE giocatori g SET espn_id = e.atleta, nome_espn = e.nome_espn FROM lega_espn e
                 WHERE g.id = e.giocatore_id AND g.espn_id IS NULL
                   AND NOT EXISTS (SELECT 1 FROM giocatori x WHERE x.espn_id = e.atleta)""")
            q("DROP TABLE lega_espn")
            logger.info("Abbinamenti ESPN spostati in giocatori.espn_id")


# ── calendario della lega ──────────────────────────────────────────────────────

def sostituisci_calendario(stagione: str, giornate: list[dict], partite: list[tuple]) -> None:
    """Sostituisce il calendario di regular season della stagione, tutto insieme o niente."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lega_partite WHERE stagione = %s AND giornata IN "
                        "(SELECT numero FROM lega_giornate WHERE stagione = %s AND tipo = 'regular')", (stagione, stagione))
            cur.execute("DELETE FROM lega_giornate WHERE stagione = %s AND tipo = 'regular'", (stagione,))
            for g in giornate:
                cur.execute("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al, media_file) "
                            "VALUES (%s, %s, 'regular', %s, %s, %s)",
                            (stagione, g["numero"], g["dal"], g["al"], g["media_file"]))
            for giornata, casa, trasferta in partite:
                cur.execute("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES (%s, %s, %s, %s)",
                            (stagione, giornata, casa, trasferta))


def giornate(stagione: str) -> list[dict]:
    return q("SELECT * FROM lega_giornate WHERE stagione = %s ORDER BY numero", (stagione,), many=True) or []


def giornata(stagione: str, numero: int) -> dict | None:
    return q("SELECT * FROM lega_giornate WHERE stagione = %s AND numero = %s", (stagione, numero), one=True)


def partite_giornata(stagione: str, numero: int) -> list[dict]:
    return q("SELECT * FROM lega_partite WHERE stagione = %s AND giornata = %s ORDER BY id",
             (stagione, numero), many=True) or []


def partita_squadra(stagione: str, numero: int, team_id: str) -> dict | None:
    return q("SELECT * FROM lega_partite WHERE stagione = %s AND giornata = %s AND %s IN (casa, trasferta)",
             (stagione, numero, team_id), one=True)


def salva_calcolo(stagione: str, numero: int, prima_partita, media: list[str]) -> None:
    q("UPDATE lega_giornate SET prima_partita = %s, media = %s, calcolato = NOW() WHERE stagione = %s AND numero = %s",
      (prima_partita, media, stagione, numero))


# ── partite NBA ────────────────────────────────────────────────────────────────

def salva_partite_nba(partite: list[dict]) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for p in partite:
                cur.execute("""INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato)
                               VALUES (%(espn_id)s, %(stagione)s, %(tipo)s, %(data_et)s, %(inizio)s, %(casa)s,
                                       %(trasferta)s, %(stato)s)
                               ON CONFLICT (espn_id) DO UPDATE SET tipo = EXCLUDED.tipo, data_et = EXCLUDED.data_et,
                                 inizio = EXCLUDED.inizio, casa = EXCLUDED.casa, trasferta = EXCLUDED.trasferta,
                                 stato = EXCLUDED.stato, aggiornato = NOW()""", p)
    return len(partite)


def partite_nba(dal, al, tipi=(2, 3, 5)) -> list[dict]:
    return q("SELECT * FROM nba_partite WHERE data_et BETWEEN %s AND %s AND tipo = ANY(%s) ORDER BY inizio",
             (dal, al, list(tipi)), many=True) or []


def squadre_nba(stagione: str) -> set[str]:
    righe = q("SELECT casa AS s FROM nba_partite WHERE stagione = %s AND tipo = 2 UNION "
              "SELECT trasferta FROM nba_partite WHERE stagione = %s AND tipo = 2", (stagione, stagione), many=True) or []
    import nba
    return {r["s"] for r in righe} & nba.NBA          # senza i segnaposto (TBD)


# ── tabellini ──────────────────────────────────────────────────────────────────

_COLONNE_TAB = ("partita", "atleta", "nome", "squadra", "titolare", "giocato", "minuti", "pts", "fgm", "fga",
                "tpm", "tpa", "ftm", "fta", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf", "fp")


def salva_tabellino(partita: str, righe: list[dict], finale: bool = True) -> None:
    """Sostituisce il tabellino di una partita (ESPN a volte corregge le statistiche) e segna la partita.
    Con finale=False (live, partita in corso) la partita resta "senza tabellino": quello definitivo
    si riscarica a partita finita (partite_senza_tabellino)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM nba_tabellini WHERE partita = %s", (partita,))
            for r in righe:
                cur.execute(f"INSERT INTO nba_tabellini ({', '.join(_COLONNE_TAB)}) VALUES "
                            f"({', '.join('%(' + c + ')s' for c in _COLONNE_TAB)})", r)
            cur.execute("UPDATE nba_partite SET tabellino = %s WHERE espn_id = %s",
                        (datetime.now(timezone.utc) if finale else None, partita))


def partite_senza_tabellino(fino=None, stagione: str | None = None, dal=None) -> list[str]:
    """Partite finite (regular season, play-in, playoff) senza tabellino, dalla più vecchia; con
    `stagione` solo quelle di quella stagione, con `dal` solo da quel giorno."""
    righe = q("SELECT espn_id FROM nba_partite WHERE stato = 'STATUS_FINAL' AND tabellino IS NULL "
              "AND tipo = ANY(%s) AND (%s::date IS NULL OR data_et <= %s) AND (%s::text IS NULL OR stagione = %s) "
              "AND (%s::date IS NULL OR data_et >= %s) ORDER BY inizio",
              ([2, 3, 5], fino, fino, stagione, stagione, dal, dal), many=True) or []
    return [r["espn_id"] for r in righe]


def tabellini_atleti(atleti: list[str], dal, al) -> list[dict]:
    """Righe di tabellino dei giocatori nei giorni indicati, con giorno e stato della partita."""
    return q("""SELECT t.*, p.data_et, p.stato AS stato_partita, p.inizio FROM nba_tabellini t
                JOIN nba_partite p ON p.espn_id = t.partita
                WHERE t.atleta = ANY(%s) AND p.data_et BETWEEN %s AND %s AND p.tipo = ANY(%s)
                ORDER BY p.inizio""", (list(atleti), dal, al, [2, 3, 5]), many=True) or []


def medie_stagione(atleti: list[str], stagione: str, prima_del) -> dict[str, dict]:
    """{atleta: {media, partite}} sulle partite giocate della stagione prima del giorno indicato."""
    righe = q("""SELECT t.atleta, AVG(t.fp)::float AS media, COUNT(*) AS partite FROM nba_tabellini t
                 JOIN nba_partite p ON p.espn_id = t.partita
                 WHERE t.atleta = ANY(%s) AND p.stagione = %s AND p.tipo = ANY(%s) AND p.data_et < %s
                   AND t.giocato AND NOT (t.fp = 0 AND t.minuti = 0) GROUP BY t.atleta""", (list(atleti), stagione, [2, 5], prima_del), many=True) or []
    from numeri import ottavi
    return {r["atleta"]: {"media": ottavi(r["media"]), "partite": r["partite"]} for r in righe}


def ultima_squadra(atleti: list[str], prima_del) -> dict[str, str]:
    """La squadra NBA dell'ultimo tabellino di ogni giocatore prima del giorno indicato."""
    righe = q("""SELECT DISTINCT ON (t.atleta) t.atleta, t.squadra FROM nba_tabellini t
                 JOIN nba_partite p ON p.espn_id = t.partita
                 WHERE t.atleta = ANY(%s) AND p.data_et < %s ORDER BY t.atleta, p.inizio DESC""",
              (list(atleti), prima_del), many=True) or []
    return {r["atleta"]: r["squadra"] for r in righe}


# ── infortunati ────────────────────────────────────────────────────────────────

# Snapshot della lista infortunati di ESPN: si tengono tutti quelli dell'ultima settimana (anche
# quelli della notte, subito prima delle partite); per i giorni più vecchi resta solo quello che
# conta per il calcolo (snapshot_del_giorno), gli altri si cancellano (pulisci_snapshot).
GIORNI_SNAPSHOT = 7


def salva_infortuni(giorno, voci: list[dict]) -> None:
    """Un nuovo snapshot (tutte le righe con lo stesso `preso`); i precedenti restano."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT NOW() AS t")
            r = cur.fetchone()
            preso = r["t"] if isinstance(r, dict) else r[0]
            for v in voci:
                cur.execute("INSERT INTO nba_infortuni (giorno, atleta, nome, squadra, stato, dettaglio, preso) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                            (giorno, v["atleta"], v["nome"], v.get("squadra"), v["stato"], v.get("dettaglio"), preso))


def snapshot_del_giorno(giorni: list) -> dict:
    """{giorno: preso} dello snapshot che conta per il calcolo: l'ultimo preso prima dell'inizio
    della prima partita NBA di quel giorno (il report subito prima delle partite); se il giorno
    non ha partite, o non ce n'è nessuno prima, l'ultimo del giorno."""
    giorni = list(giorni)
    if not giorni:
        return {}
    snap = q("SELECT DISTINCT giorno, preso FROM nba_infortuni WHERE giorno = ANY(%s) ORDER BY giorno, preso",
             (giorni,), many=True) or []
    prime = q("SELECT data_et, MIN(inizio) AS inizio FROM nba_partite WHERE data_et = ANY(%s) GROUP BY data_et",
              (giorni,), many=True) or []
    prima = {r["data_et"]: r["inizio"] for r in prime}
    per_giorno: dict = {}
    for r in snap:
        per_giorno.setdefault(r["giorno"], []).append(r["preso"])
    out = {}
    for d, tempi in per_giorno.items():
        p = prima.get(d)
        prima_delle_partite = [t for t in tempi if p is None or t < p]
        out[d] = max(prima_delle_partite) if prima_delle_partite else max(tempi)
    return out


def infortuni(atleti: list[str], giorni: list) -> dict[tuple, str]:
    """{(atleta, giorno): stato} nello snapshot che conta di ogni giorno (snapshot_del_giorno).
    I giorni senza snapshot non ci sono: chi chiama distingue "sano" da "nessuno snapshot" con
    giorni_con_snapshot."""
    scelti = snapshot_del_giorno(giorni)
    if not scelti:
        return {}
    righe = q("SELECT atleta, giorno, preso, stato FROM nba_infortuni WHERE atleta = ANY(%s) AND giorno = ANY(%s)",
              (list(atleti), list(scelti)), many=True) or []
    return {(r["atleta"], r["giorno"]): r["stato"] for r in righe if r["preso"] == scelti[r["giorno"]]}


def status_validi(stagione: str, giornata: int, atleti: list[str]) -> dict[str, str | None]:
    """{atleta: stato} deciso da un admin per la giornata (None = sano): vince sugli snapshot."""
    righe = q("SELECT atleta, stato FROM lega_status_validi WHERE stagione = %s AND giornata = %s AND atleta = ANY(%s)",
              (stagione, giornata, list(atleti)), many=True) or []
    return {r["atleta"]: r["stato"] for r in righe}


def set_status_valido(stagione: str, giornata: int, atleta: str, stato: str | None, da=None) -> None:
    q("""INSERT INTO lega_status_validi (stagione, giornata, atleta, stato, da) VALUES (%s, %s, %s, %s, %s)
         ON CONFLICT (stagione, giornata, atleta) DO UPDATE SET stato = EXCLUDED.stato, da = EXCLUDED.da, quando = NOW()""",
      (stagione, giornata, atleta, stato, da))


def togli_status_valido(stagione: str, giornata: int, atleta: str) -> None:
    q("DELETE FROM lega_status_validi WHERE stagione = %s AND giornata = %s AND atleta = %s", (stagione, giornata, atleta))


def snapshot_giocatore(atleta: str, dal, al) -> list[dict]:
    """Tutti gli snapshot dei giorni dal-al, con lo stato del giocatore in ognuno (None = non
    in lista, cioè sano): [{giorno, preso, stato}] in ordine."""
    tempi = q("SELECT DISTINCT giorno, preso FROM nba_infortuni WHERE giorno BETWEEN %s AND %s ORDER BY preso",
              (dal, al), many=True) or []
    suoi = q("SELECT preso, stato FROM nba_infortuni WHERE atleta = %s AND giorno BETWEEN %s AND %s", (atleta, dal, al),
             many=True) or []
    st = {r["preso"]: r["stato"] for r in suoi}
    return [{"giorno": t["giorno"], "preso": t["preso"], "stato": st.get(t["preso"])} for t in tempi]


def giorni_con_snapshot(giorni: list) -> set:
    return set(snapshot_del_giorno(giorni))


def pulisci_snapshot(oggi) -> int:
    """Per i giorni più vecchi di GIORNI_SNAPSHOT tiene solo lo snapshot che conta. Righe cancellate."""
    from datetime import timedelta
    vecchi = [r["giorno"] for r in (q("SELECT DISTINCT giorno FROM nba_infortuni WHERE giorno < %s",
                                      (oggi - timedelta(days=GIORNI_SNAPSHOT),), many=True) or [])]
    tolte = 0
    for d, t in snapshot_del_giorno(vecchi).items():
        r = q("WITH x AS (DELETE FROM nba_infortuni WHERE giorno = %s AND preso <> %s RETURNING 1) SELECT COUNT(*) AS n FROM x",
              (d, t), one=True)
        tolte += r["n"] if r else 0
    return tolte


# ── abbinamento con l'anagrafica del bot principale ────────────────────────────

def giocatori_anagrafica() -> list[dict]:
    return q("SELECT id, nome_common, nome_bref, nome_yahoo FROM giocatori", many=True) or []


def giocatori_a_roster(stagione: str) -> list[dict]:
    """Giocatori con contratto attivo: squadra, ruolo della stagione, id ESPN se abbinato."""
    return q("""SELECT c.team_id, g.id AS giocatore_id, g.nome_common, r.ruolo, g.espn_id AS atleta
                FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                LEFT JOIN ruolo_attuale r ON r.giocatore_id = g.id AND r.stagione = %s
                WHERE c.attivo ORDER BY c.team_id, g.nome_common""", (stagione,), many=True) or []


def abbinamenti() -> dict[int, str]:
    return {r["id"]: r["espn_id"] for r in (q("SELECT id, espn_id FROM giocatori WHERE espn_id IS NOT NULL",
                                                many=True) or [])}


def abbina(giocatore_id: int, atleta: str, nome_espn: str, metodo: str) -> None:
    """Un giocatore ↔ un id ESPN, in giocatori.espn_id e nome_espn: se l'id era di un altro
    giocatore, lì si toglie (un id ESPN è di un solo giocatore). `metodo` (auto, admin) va nel log."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE giocatori SET espn_id = NULL, nome_espn = NULL WHERE espn_id = %s AND id <> %s",
                        (atleta, giocatore_id))
            cur.execute("UPDATE giocatori SET espn_id = %s, nome_espn = %s WHERE id = %s", (atleta, nome_espn, giocatore_id))
    logger.info("ESPN %s ↔ giocatore %s (%s, %s)", atleta, giocatore_id, nome_espn, metodo)


def salva_atleti(atleti: list[dict], giorno=None) -> None:
    """I roster ESPN. Se ci sono tutte e 30 le squadre, chi non è più in nessun roster (tagliato,
    free agent NBA) resta senza squadra. Ogni cambio di squadra di un atleta già noto finisce in
    nba_movimenti (v47, per /carriera): da una squadra all'altra, o fuori da tutti i roster."""
    if giorno is None:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _Z
        giorno = _dt.now(_Z("America/New_York")).date()
    prima = {r["atleta"]: r["squadra"] for r in (q("SELECT atleta, squadra FROM nba_atleti", many=True) or [])}
    tutti = len({a["squadra"] for a in atleti}) >= 30
    with get_conn() as conn:
        with conn.cursor() as cur:
            for a in atleti:
                if a["atleta"] in prima and prima[a["atleta"]] != a["squadra"]:
                    cur.execute("INSERT INTO nba_movimenti (atleta, giorno, da, a) VALUES (%s, %s, %s, %s)",
                                (a["atleta"], giorno, prima[a["atleta"]], a["squadra"]))
                cur.execute("INSERT INTO nba_atleti (atleta, nome, squadra, esperienza) VALUES (%(atleta)s, %(nome)s, %(squadra)s, %(esperienza)s) "
                            "ON CONFLICT (atleta) DO UPDATE SET nome = EXCLUDED.nome, squadra = EXCLUDED.squadra, "
                            "esperienza = COALESCE(EXCLUDED.esperienza, nba_atleti.esperienza), aggiornato = NOW()",
                            {"esperienza": None, **a})
            if tutti:
                visti = {a["atleta"] for a in atleti}
                for atleta, sq in prima.items():
                    if sq and atleta not in visti:
                        cur.execute("INSERT INTO nba_movimenti (atleta, giorno, da, a) VALUES (%s, %s, %s, NULL)", (atleta, giorno, sq))
                cur.execute("UPDATE nba_atleti SET squadra = NULL, aggiornato = NOW() WHERE NOT (atleta = ANY(%s))",
                            ([a["atleta"] for a in atleti],))


def squadre_roster(atleti: list[str]) -> dict[str, str]:
    """La squadra NBA di adesso dai roster ESPN (aggiornati ogni mattina alle 8:30)."""
    righe = q("SELECT atleta, squadra FROM nba_atleti WHERE atleta = ANY(%s) AND squadra IS NOT NULL",
              (list(atleti),), many=True) or []
    return {r["atleta"]: r["squadra"] for r in righe}


def atleti_espn_visti() -> dict[str, str]:
    """{atleta: nome} di tutti i giocatori ESPN conosciuti (roster, tabellini, infortunati)."""
    righe = q("SELECT DISTINCT ON (atleta) atleta, nome FROM ("
              " SELECT atleta, nome, 1 AS o FROM nba_atleti UNION ALL"
              " SELECT atleta, nome, 2 FROM nba_tabellini UNION ALL"
              " SELECT atleta, nome, 3 FROM nba_infortuni) x ORDER BY atleta, o", many=True) or []
    return {r["atleta"]: r["nome"] for r in righe}


# ── calendario per il foglio Google ────────────────────────────────────────────

def salva_csv_calendario(stagione: str, testo: str) -> None:
    q("INSERT INTO lega_calendario_csv (stagione, testo) VALUES (%s, %s) "
      "ON CONFLICT (stagione) DO UPDATE SET testo = EXCLUDED.testo, importato = NOW()", (stagione, testo))


def csv_calendario(stagione: str) -> str | None:
    r = q("SELECT testo FROM lega_calendario_csv WHERE stagione = %s", (stagione,), one=True)
    return r["testo"] if r else None


def risultati(stagione: str) -> dict[tuple, dict]:
    """{(giornata, casa, trasferta): riga} dei risultati della stagione."""
    righe = q("SELECT * FROM lega_risultati WHERE stagione = %s", (stagione,), many=True) or []
    return {(r["giornata"], r["casa"], r["trasferta"]): r for r in righe}

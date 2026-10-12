"""
PostgreSQL di loucabot: lo stesso database dei due bot, tabelle sue con prefisso lega_ e nba_.
Legge (mai scrive) le tabelle degli altri bot. Le righe sono dict (RealDictCursor).
"""
import logging
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
    return {r["s"] for r in righe}

"""
Le due connessioni di klra, sempre distinte (Luca, 04/11: «la separazione deve essere assoluta»):

- **ufficiale**: il database della lega, con l'utente `klra` che ha solo SELECT su un elenco di tabelle
  (setup_db.sql) e `default_transaction_read_only` acceso. È il pool del modulo `db` di loucabot (il suo
  codice di calcolo legge da lì), creato qui SENZA `db.init_db()`, che farebbe le migrazioni di loucabot.
  In più ogni connessione apre la sessione in sola lettura: anche un bug non può scrivere, lo rifiuta PostgreSQL.
- **klra**: il database `klra`, dell'utente `klra`, con le tabelle `klra_*` (sistemi, scelte, cache).

DATABASE_URL / PG_PASSWORD_FILE → ufficiale; KLRA_DATABASE_URL (stessa password) → klra.
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


def _password() -> None:
    pw_file = os.environ.get("PG_PASSWORD_FILE", "/run/secrets/pg_password_klra")
    if os.path.exists(pw_file):
        os.environ["PGPASSWORD"] = open(pw_file).read().strip()


def apri_ufficiale() -> None:
    """Il pool di `db` (loucabot) sul database della lega, in sola lettura."""
    import db
    _password()
    dsn = re.sub(r"[?&]password_file=[^\s&]+", "", os.environ["DATABASE_URL"])
    # ogni sessione nasce in sola lettura (oltre ai permessi del ruolo, setup_db.sql)
    db._pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=5, dsn=dsn,
                                                    options="-c default_transaction_read_only=on")


def apri_klra() -> None:
    global _pool
    _password()
    _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=5, dsn=os.environ["KLRA_DATABASE_URL"])
    migra()


@contextmanager
def conn():
    c = _pool.getconn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        _pool.putconn(c)


def q(sql, params=None, one=False, many=False):
    """Solo sul database klra."""
    with conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if one:
                return cur.fetchone()
            if many:
                return cur.fetchall()
            return None


def migra() -> None:
    q("""CREATE TABLE IF NOT EXISTS klra_sistemi (
            id         SERIAL PRIMARY KEY,
            nome       TEXT NOT NULL,
            ufficiale  BOOLEAN NOT NULL DEFAULT FALSE,     -- uno solo: le regole della lega, lette ogni volta
            autore     BIGINT,
            autore_nome TEXT,
            base_id    INT REFERENCES klra_sistemi(id),     -- copiato da
            parametri  JSONB NOT NULL DEFAULT '{}'::jsonb,  -- li cambia solo chi l'ha creato (l'Ufficiale li ignora)
            creato     TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    q("CREATE UNIQUE INDEX IF NOT EXISTS klra_sistemi_nome ON klra_sistemi (lower(nome))")
    q("CREATE UNIQUE INDEX IF NOT EXISTS klra_sistemi_uff ON klra_sistemi (ufficiale) WHERE ufficiale")
    q("""CREATE TABLE IF NOT EXISTS klra_scelte (
            user_id    BIGINT PRIMARY KEY,
            sistema_id INT NOT NULL REFERENCES klra_sistemi(id),
            scelto     TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    q("""CREATE TABLE IF NOT EXISTS klra_bozze (
            user_id    BIGINT PRIMARY KEY,
            base_id    INT REFERENCES klra_sistemi(id),
            parametri  JSONB NOT NULL,
            aggiornata TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    q("""CREATE TABLE IF NOT EXISTS klra_risultati (
            sistema_id  INT NOT NULL REFERENCES klra_sistemi(id),
            firma       TEXT NOT NULL,                      -- impronta dei parametri (regole.firma)
            stagione    TEXT NOT NULL,
            giornata    INT NOT NULL,
            convalidato TIMESTAMPTZ,                        -- della convalida ufficiale: se cambia, si rifà
            dati        JSONB NOT NULL,
            calcolato   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (sistema_id, firma, stagione, giornata))""")
    # v1: chi l'ha creato può modificarlo (Luca, 04/11), gli altri lo copiano
    q("ALTER TABLE klra_sistemi ADD COLUMN IF NOT EXISTS modificato TIMESTAMPTZ")
    q("ALTER TABLE klra_bozze ADD COLUMN IF NOT EXISTS modifica_id INT REFERENCES klra_sistemi(id) ON DELETE CASCADE")
    if not q("SELECT 1 AS x FROM klra_sistemi WHERE ufficiale", one=True):
        q("INSERT INTO klra_sistemi (nome, ufficiale, autore_nome) VALUES ('Ufficiale', TRUE, 'la lega')")
    # conference alternative (v2, Luca 06/11): le squadre della prima conference e l'accoppiamento estratto col calendario vero
    q("""CREATE TABLE IF NOT EXISTS klra_conference (
            id          SERIAL PRIMARY KEY,
            nome        TEXT NOT NULL,
            autore      BIGINT,
            autore_nome TEXT,
            squadre_a   JSONB NOT NULL,                     -- le squadre della prima conference (le altre nella seconda)
            mappa       JSONB NOT NULL,                     -- {squadra: squadra di cui prende il posto nel calendario}
            creato      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            modificato  TIMESTAMPTZ)""")
    q("CREATE UNIQUE INDEX IF NOT EXISTS klra_conference_nome ON klra_conference (lower(nome))")
    q("ALTER TABLE klra_scelte ADD COLUMN IF NOT EXISTS conference_id INT REFERENCES klra_conference(id) ON DELETE SET NULL")
    # sistemi predefiniti (Luca, 04/11): seguono le regole della lega, nessuno li modifica, tutti li copiano
    q("ALTER TABLE klra_sistemi ADD COLUMN IF NOT EXISTS predefinito TEXT")
    from klra.regole import PREDEFINITI
    for chiave, d in PREDEFINITI.items():
        if not q("SELECT 1 AS x FROM klra_sistemi WHERE predefinito = %s", (chiave,), one=True):
            nome = d["nome"] if not q("SELECT 1 AS x FROM klra_sistemi WHERE lower(nome) = lower(%s)", (d["nome"],), one=True) \
                else f"{d['nome']} (klra)"
            q("INSERT INTO klra_sistemi (nome, autore_nome, predefinito) VALUES (%s, 'klra', %s)", (nome, chiave))

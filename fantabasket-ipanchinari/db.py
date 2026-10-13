"""
PostgreSQL di IPanchinari: lo stesso database degli altri bot, tabelle sue con prefisso ipa_.
Legge (mai scrive) roster, ruoli e anagrafica del bot principale e giornate e partite NBA di
loucabot. Le righe sono dict (RealDictCursor).
"""
import json
import logging
import os
import re
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)
_pool = None
RUOLI = ("PG", "SG", "SF", "PF", "C")


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
    """Tabelle di IPanchinari (solo aggiunte, si può rilanciare)."""
    q("""CREATE TABLE IF NOT EXISTS ipa_quintetto (
            team_id      TEXT NOT NULL,
            ruolo        TEXT NOT NULL,                 -- PG SG SF PF C
            giocatore_id INT  NOT NULL,
            fonte        TEXT NOT NULL,                 -- gm / admin / import
            da           BIGINT,                        -- utente Telegram
            aggiornato   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (team_id, ruolo))""")
    q("""CREATE TABLE IF NOT EXISTS ipa_alias (
            team_id      TEXT NOT NULL,
            alias        TEXT NOT NULL,                 -- la riga scritta dal GM, normalizzata
            giocatore_id INT  NOT NULL,
            creato       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (team_id, alias))""")
    q("""CREATE TABLE IF NOT EXISTS ipa_panchine (
            stagione     TEXT NOT NULL,
            giornata     INT  NOT NULL,
            team_id      TEXT NOT NULL,
            titolo       TEXT,
            righe        JSONB NOT NULL,                -- [{giocatore_id, testo}] in ordine
            inviata      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            da           BIGINT,
            fonte        TEXT NOT NULL DEFAULT 'gm',    -- gm / admin
            in_ritardo   BOOLEAN NOT NULL DEFAULT FALSE,
            messaggio_canale BIGINT,
            PRIMARY KEY (stagione, giornata, team_id))""")
    q("""CREATE TABLE IF NOT EXISTS ipa_bozze (
            id           SERIAL PRIMARY KEY,
            chat_id      BIGINT NOT NULL,
            team_id      TEXT NOT NULL,
            stagione     TEXT NOT NULL,
            giornata     INT  NOT NULL,
            dati         JSONB NOT NULL,                -- titolo e righe con candidati e scelta
            fonte        TEXT NOT NULL DEFAULT 'gm',
            creata       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            chiusa       BOOLEAN NOT NULL DEFAULT FALSE)""")
    q("""CREATE TABLE IF NOT EXISTS ipa_conferme (
            stagione     TEXT NOT NULL,
            giornata     INT  NOT NULL,
            team_id      TEXT NOT NULL,
            stato        TEXT NOT NULL,                 -- confermato / modificato
            da           BIGINT,
            quando       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (stagione, giornata, team_id))""")
    q("""CREATE TABLE IF NOT EXISTS ipa_formazioni (
            stagione     TEXT NOT NULL,
            giornata     INT  NOT NULL,
            team_id      TEXT NOT NULL,
            ruolo        TEXT NOT NULL,
            giocatore_id INT,
            PRIMARY KEY (stagione, giornata, team_id, ruolo))""")
    q("""CREATE TABLE IF NOT EXISTS ipa_stato_giornata (
            stagione     TEXT NOT NULL,
            giornata     INT  NOT NULL,
            promemoria   TIMESTAMPTZ,                   -- quando sono partiti i promemoria
            riepilogo    TIMESTAMPTZ,                   -- riepilogo agli admin prima della scadenza
            chiusa       TIMESTAMPTZ,                   -- quintetti congelati in ipa_formazioni
            PRIMARY KEY (stagione, giornata))""")
    q("ALTER TABLE ipa_alias ADD COLUMN IF NOT EXISTS id SERIAL")          # per cancellarli coi bottoni
    # il canale del messaggio (per non modificare un messaggio di un altro canale se il canale
    # cambia), il nome di chi l'ha inserita e quante volte è stata mandata (per ripubblicarla)
    q("ALTER TABLE ipa_panchine ADD COLUMN IF NOT EXISTS canale_id BIGINT")
    q("ALTER TABLE ipa_panchine ADD COLUMN IF NOT EXISTS da_nome TEXT")
    q("ALTER TABLE ipa_panchine ADD COLUMN IF NOT EXISTS versioni INT NOT NULL DEFAULT 1")
    q("""CREATE TABLE IF NOT EXISTS ipa_cessioni (
            team_id      TEXT NOT NULL,                 -- la squadra che l'ha ceduto (o tagliato)
            giocatore_id INT  NOT NULL,
            dove         TEXT NOT NULL,                 -- quintetto / panchina G<n> / formazione G<n>
            avvisato     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (team_id, giocatore_id, dove))""")


# ── letture dagli altri bot ────────────────────────────────────────────────────

def roster(team_id: str, stagione: str) -> list[dict]:
    """Giocatori con contratto attivo della squadra: id, nomi, ruolo della stagione, id ESPN."""
    return q("""SELECT g.id, g.nome_common, g.nome_bref, g.nome_yahoo, g.espn_id, g.nome_espn, r.ruolo
                FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                LEFT JOIN ruolo_attuale r ON r.giocatore_id = g.id AND r.stagione = %s
                WHERE c.attivo AND c.team_id = %s ORDER BY g.nome_common""", (stagione, team_id), many=True) or []


def giornate(stagione: str) -> list[dict]:
    return q("SELECT * FROM lega_giornate WHERE stagione = %s ORDER BY numero", (stagione,), many=True) or []


def giornata(stagione: str, numero: int) -> dict | None:
    return q("SELECT * FROM lega_giornate WHERE stagione = %s AND numero = %s", (stagione, numero), one=True)


def partite_nba(dal, al) -> list[dict]:
    return q("SELECT * FROM nba_partite WHERE data_et BETWEEN %s AND %s AND tipo = ANY(%s) ORDER BY inizio",
             (dal, al, [2, 3, 5]), many=True) or []


def squadre_nba_giocatori(ids: list[int]) -> dict[int, str]:
    """{giocatore_id: sigla NBA} dall'ultimo tabellino o dai roster ESPN (tabelle di loucabot)."""
    if not ids:
        return {}
    righe = q("""SELECT g.id,
                   COALESCE((SELECT t.squadra FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                             WHERE t.atleta = g.espn_id ORDER BY p.inizio DESC LIMIT 1),
                            (SELECT a.squadra FROM nba_atleti a WHERE a.atleta = g.espn_id)) AS squadra
                 FROM giocatori g WHERE g.id = ANY(%s)""", (list(ids),), many=True) or []
    return {r["id"]: r["squadra"] for r in righe if r["squadra"]}


# ── quintetti ──────────────────────────────────────────────────────────────────

def quintetto(team_id: str) -> dict[str, int]:
    righe = q("SELECT ruolo, giocatore_id FROM ipa_quintetto WHERE team_id = %s", (team_id,), many=True) or []
    return {r["ruolo"]: r["giocatore_id"] for r in righe}


def salva_quintetto(team_id: str, quintetto_: dict[str, int], fonte: str, da=None) -> None:
    """Sostituisce il quintetto (i ruoli assenti restano vuoti)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ipa_quintetto WHERE team_id = %s", (team_id,))
            for ruolo, gid in quintetto_.items():
                if gid:
                    cur.execute("INSERT INTO ipa_quintetto (team_id, ruolo, giocatore_id, fonte, da) VALUES (%s, %s, %s, %s, %s)",
                                (team_id, ruolo, gid, fonte, da))


def conferma(stagione: str, giornata_: int, team_id: str, stato: str, da=None) -> None:
    q("""INSERT INTO ipa_conferme (stagione, giornata, team_id, stato, da) VALUES (%s, %s, %s, %s, %s)
         ON CONFLICT (stagione, giornata, team_id) DO UPDATE SET stato = EXCLUDED.stato, da = EXCLUDED.da, quando = NOW()""",
      (stagione, giornata_, team_id, stato, da))


def conferme(stagione: str, giornata_: int) -> dict[str, dict]:
    righe = q("SELECT * FROM ipa_conferme WHERE stagione = %s AND giornata = %s", (stagione, giornata_), many=True) or []
    return {r["team_id"]: r for r in righe}


def congela_quintetti(stagione: str, giornata_: int, team_ids: list[str]) -> None:
    """Alla scadenza: il quintetto di ogni squadra diventa quello della giornata."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ipa_formazioni WHERE stagione = %s AND giornata = %s", (stagione, giornata_))
            for t in team_ids:
                cur.execute("SELECT ruolo, giocatore_id FROM ipa_quintetto WHERE team_id = %s", (t,))
                attuale = dict(cur.fetchall())
                for ruolo in RUOLI:
                    cur.execute("INSERT INTO ipa_formazioni (stagione, giornata, team_id, ruolo, giocatore_id) "
                                "VALUES (%s, %s, %s, %s, %s)", (stagione, giornata_, t, ruolo, attuale.get(ruolo)))


def salva_formazione(stagione: str, giornata_: int, team_id: str, quintetto_: dict[str, int]) -> None:
    """Il quintetto di una giornata già chiusa, corretto da un admin (giornata in corso o passata)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            for ruolo in RUOLI:
                cur.execute("""INSERT INTO ipa_formazioni (stagione, giornata, team_id, ruolo, giocatore_id) VALUES (%s, %s, %s, %s, %s)
                               ON CONFLICT (stagione, giornata, team_id, ruolo) DO UPDATE SET giocatore_id = EXCLUDED.giocatore_id""",
                            (stagione, giornata_, team_id, ruolo, quintetto_.get(ruolo)))


def formazione(stagione: str, giornata_: int, team_id: str) -> dict[str, int | None]:
    righe = q("SELECT ruolo, giocatore_id FROM ipa_formazioni WHERE stagione = %s AND giornata = %s AND team_id = %s",
              (stagione, giornata_, team_id), many=True) or []
    return {r["ruolo"]: r["giocatore_id"] for r in righe}


# ── alias ──────────────────────────────────────────────────────────────────────

def alias(team_id: str, ids: list[int] | None = None) -> dict[str, int]:
    """{riga normalizzata: giocatore}. Con `ids` (la rosa di oggi): i soprannomi di quei giocatori
    chiunque li abbia scritti, così seguono il giocatore quando cambia squadra; a parità di
    soprannome vincono quelli della squadra, poi i più recenti."""
    if ids is None:
        righe = q("SELECT alias, giocatore_id FROM ipa_alias WHERE team_id = %s", (team_id,), many=True) or []
        return {r["alias"]: r["giocatore_id"] for r in righe}
    righe = q("""SELECT alias, giocatore_id FROM ipa_alias WHERE giocatore_id = ANY(%s)
                 ORDER BY (team_id = %s), creato""", (list(ids), team_id), many=True) or []
    return {r["alias"]: r["giocatore_id"] for r in righe}


def alias_giocatori(ids: list[int]) -> list[dict]:
    """I soprannomi dei giocatori indicati (per /soprannomi), con chi li ha scritti."""
    return q("SELECT id, team_id, alias, giocatore_id FROM ipa_alias WHERE giocatore_id = ANY(%s) ORDER BY giocatore_id, alias",
             (list(ids),), many=True) or []


def elimina_alias(id_: int) -> dict | None:
    return q("DELETE FROM ipa_alias WHERE id = %s RETURNING team_id, alias, giocatore_id", (id_,), one=True)


def salva_alias(team_id: str, alias_: str, giocatore_id: int) -> None:
    if alias_:
        q("""INSERT INTO ipa_alias (team_id, alias, giocatore_id) VALUES (%s, %s, %s)
             ON CONFLICT (team_id, alias) DO UPDATE SET giocatore_id = EXCLUDED.giocatore_id, creato = NOW()""",
          (team_id, alias_, giocatore_id))


# ── cessioni (giocatori usciti dalla squadra che erano in quintetto o in panchina) ──

def squadra_attuale(giocatore_id: int) -> str | None:
    r = q("SELECT team_id FROM contratti WHERE giocatore_id = %s AND attivo LIMIT 1", (giocatore_id,), one=True)
    return r["team_id"] if r else None


def nomi_giocatori(ids: list[int]) -> dict[int, str]:
    righe = q("SELECT id, nome_common FROM giocatori WHERE id = ANY(%s)", (list(ids),), many=True) or []
    return {r["id"]: r["nome_common"] for r in righe}


def cessioni_avvisate(team_id: str) -> set[tuple[int, str]]:
    righe = q("SELECT giocatore_id, dove FROM ipa_cessioni WHERE team_id = %s", (team_id,), many=True) or []
    return {(r["giocatore_id"], r["dove"]) for r in righe}


def segna_cessione(team_id: str, giocatore_id: int, dove: str) -> None:
    q("INSERT INTO ipa_cessioni (team_id, giocatore_id, dove) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
      (team_id, giocatore_id, dove))


def dimentica_cessioni(team_id: str, rientrati: list[int]) -> None:
    """Un giocatore tornato in squadra: se riparte, va avvisato di nuovo."""
    if rientrati:
        q("DELETE FROM ipa_cessioni WHERE team_id = %s AND giocatore_id = ANY(%s)", (team_id, list(rientrati)))


# ── panchine ───────────────────────────────────────────────────────────────────

def panchina(stagione: str, giornata_: int, team_id: str) -> dict | None:
    return q("SELECT * FROM ipa_panchine WHERE stagione = %s AND giornata = %s AND team_id = %s",
             (stagione, giornata_, team_id), one=True)


def panchine(stagione: str, giornata_: int) -> dict[str, dict]:
    righe = q("SELECT * FROM ipa_panchine WHERE stagione = %s AND giornata = %s", (stagione, giornata_), many=True) or []
    return {r["team_id"]: r for r in righe}


def salva_panchina(stagione: str, giornata_: int, team_id: str, titolo: str | None, righe: list[dict],
                   da=None, fonte="gm", in_ritardo=False, messaggio_canale=None, canale_id=None, da_nome=None) -> None:
    q("""INSERT INTO ipa_panchine (stagione, giornata, team_id, titolo, righe, da, fonte, in_ritardo, messaggio_canale,
                                   canale_id, da_nome)
         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
         ON CONFLICT (stagione, giornata, team_id) DO UPDATE SET titolo = EXCLUDED.titolo, righe = EXCLUDED.righe,
           da = EXCLUDED.da, fonte = EXCLUDED.fonte, in_ritardo = EXCLUDED.in_ritardo,
           messaggio_canale = EXCLUDED.messaggio_canale, canale_id = EXCLUDED.canale_id, da_nome = EXCLUDED.da_nome,
           versioni = ipa_panchine.versioni + 1, inviata = NOW()""",
      (stagione, giornata_, team_id, titolo, json.dumps(righe), da, fonte, in_ritardo, messaggio_canale, canale_id, da_nome))


def segna_messaggio(stagione: str, giornata_: int, team_id: str, messaggio: int, canale: int) -> None:
    """Il messaggio sul canale di una panchina ripubblicata (non cambia ora né versioni)."""
    q("UPDATE ipa_panchine SET messaggio_canale = %s, canale_id = %s WHERE stagione = %s AND giornata = %s AND team_id = %s",
      (messaggio, canale, stagione, giornata_, team_id))


# ── bozze (panchine in attesa di conferma: sopravvivono ai riavvii) ────────────

def nuova_bozza(chat_id: int, team_id: str, stagione: str, giornata_: int, dati: dict, fonte="gm") -> int:
    q("UPDATE ipa_bozze SET chiusa = TRUE WHERE chat_id = %s AND team_id = %s AND NOT chiusa", (chat_id, team_id))
    return q("INSERT INTO ipa_bozze (chat_id, team_id, stagione, giornata, dati, fonte) VALUES (%s, %s, %s, %s, %s, %s) "
             "RETURNING id", (chat_id, team_id, stagione, giornata_, json.dumps(dati), fonte), one=True)["id"]


def bozza(id_: int) -> dict | None:
    return q("SELECT * FROM ipa_bozze WHERE id = %s", (id_,), one=True)


def aggiorna_bozza(id_: int, dati: dict) -> None:
    q("UPDATE ipa_bozze SET dati = %s WHERE id = %s", (json.dumps(dati), id_))


def bozza_cai(chat_id: int) -> dict | None:
    """La bozza di questa chat in CAI mode (in attesa di titolo o soprannomi), se c'è."""
    return q("SELECT * FROM ipa_bozze WHERE chat_id = %s AND NOT chiusa AND dati ? 'cai_passo' "
             "AND dati->>'cai_passo' IS NOT NULL AND creata > NOW() - INTERVAL '6 hours' ORDER BY id DESC LIMIT 1",
             (chat_id,), one=True)


def chiudi_bozza(id_: int) -> None:
    q("UPDATE ipa_bozze SET chiusa = TRUE WHERE id = %s", (id_,))


# ── stato delle giornate (promemoria, riepilogo, chiusura) ─────────────────────

def stato_giornata(stagione: str, giornata_: int) -> dict:
    q("INSERT INTO ipa_stato_giornata (stagione, giornata) VALUES (%s, %s) ON CONFLICT DO NOTHING", (stagione, giornata_))
    return q("SELECT * FROM ipa_stato_giornata WHERE stagione = %s AND giornata = %s", (stagione, giornata_), one=True)


def segna_stato(stagione: str, giornata_: int, campo: str) -> None:
    assert campo in ("promemoria", "riepilogo", "chiusa")
    q(f"UPDATE ipa_stato_giornata SET {campo} = NOW() WHERE stagione = %s AND giornata = %s", (stagione, giornata_))

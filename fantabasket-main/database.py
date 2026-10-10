"""
Layer DB PostgreSQL per il bot principale.
Usa RealDictCursor — le righe si accedono come dict (r["campo"]).
"""
import os
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.pool
import psycopg2.extras

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def ping() -> str:
    """Verifica la connessione al DB e restituisce la versione PostgreSQL."""
    return _qval("SELECT version()")


def get_ultime_trade_approvate(n: int = 10) -> list:
    return _q(
        "SELECT * FROM trade WHERE stato = 'approvata' ORDER BY aggiornato DESC LIMIT %s",
        (n,), many=True
    ) or []


def init_db():
    global _pool
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL non configurato")
    # Legge la password dal file secret se presente
    pw_file = os.environ.get("PG_PASSWORD_FILE", "/run/secrets/pg_password")
    if os.path.exists(pw_file):
        try:
            os.environ["PGPASSWORD"] = open(pw_file).read().strip()
        except Exception as e:
            logger.warning("Lettura pg_password_file fallita: %s", e)
    # Rimuove password_file= dalla DSN se presente
    if "password_file=" in dsn:
        import re
        dsn = re.sub(r'[?&]password_file=[^\s&]+', '', dsn)
    _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
    logger.info("Pool PostgreSQL inizializzato.")


def _allinea_check(tabella: str, valori: tuple) -> None:
    """Ricrea il CHECK sulla colonna `tipo` di `tabella` con l'unione di: valori del
    codice, valori ammessi dal CHECK attuale, valori già presenti nei dati.
    Quindi non toglie mai niente: aggiunge solo quello che manca."""
    import re
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT DISTINCT tipo FROM {tabella}")
                tutti = set(valori) | {r[0] for r in cur.fetchall() if r[0]}
                cur.execute("""
                    SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
                    WHERE conrelid = %s::regclass AND contype = 'c'
                      AND pg_get_constraintdef(oid) LIKE %s
                """, (tabella, "%tipo%"))
                vecchi = cur.fetchall()
                for _, definizione in vecchi:
                    tutti |= set(re.findall(r"'([^']+)'", definizione))
                tutti = sorted(tutti)
                for nome, _ in vecchi:
                    cur.execute(f'ALTER TABLE {tabella} DROP CONSTRAINT "{nome}"')
                elenco = ", ".join("'" + v.replace("'", "''") + "'" for v in tutti)
                cur.execute(f"ALTER TABLE {tabella} ADD CONSTRAINT {tabella}_tipo_check "
                            f"CHECK (tipo IN ({elenco}))")
    except Exception as e:
        logger.error("Allineamento CHECK %s.tipo fallito: %s", tabella, e)


def migrate_db():
    """Applica migrazioni incrementali al DB."""
    # CHECK sui tipi allineati al codice (v3.5.0, v3.6.0). Il DB di produzione era
    # nato da uno schema più vecchio di schema.sql. Si ricrea il CHECK con l'unione
    # dei valori del codice e di quelli già presenti nella tabella, così nessuna riga
    # esistente diventa non valida. Rilanciabile a ogni avvio; se fallisce non blocca il bot.
    _allinea_check("transazioni", (
        "signed", "traded", "cut", "renewed", "expired", "decadimento", "decaduto",
        "dpe_attivata", "10day_firma", "10day_scadenza", "rookie_firma", "rookie_diritti_scaduti",
        "firma", "taglio", "trade", "rookie", "dpe"))
    _allinea_check("cambi_ruolo", (
        "iniziale", "ordinario", "erminio", "saedro", "forzato_admin",
        "post_trade", "post_firma", "dpe_extra"))
    # v3.6.0 — richieste ai admin (DPE, Saedro, decadimento): una sola aperta per
    # giocatore e tipo; Approva/Rifiuta la chiudono in modo atomico (niente doppie
    # gestioni, niente "rifiutata" dopo un'approvazione)
    _q("""
        CREATE TABLE IF NOT EXISTS richieste_admin (
            id        SERIAL PRIMARY KEY,
            tipo      TEXT NOT NULL,              -- dpe | saedro | decadimento
            chiave    INT  NOT NULL,              -- giocatore_id
            team_id   TEXT NOT NULL,
            stato     TEXT NOT NULL DEFAULT 'aperta',  -- aperta | approvata | rifiutata | scaduta
            creato    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            chiuso    TIMESTAMPTZ,
            da        TEXT
        )
    """)
    _q("CREATE UNIQUE INDEX IF NOT EXISTS idx_richieste_admin_aperte "
       "ON richieste_admin (tipo, chiave) WHERE stato = 'aperta'")
    _q("""
        CREATE TABLE IF NOT EXISTS cap_anticipato (
            team_id      TEXT PRIMARY KEY,
            importo      INTEGER NOT NULL CHECK (importo > 0),
            richiesto_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            scade_at     TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '48 hours',
            message_id   BIGINT
        )
    """)
    _q("""
        CREATE TABLE IF NOT EXISTS slot_anticipato (
            team_id      TEXT PRIMARY KEY,
            quantita     INTEGER NOT NULL CHECK (quantita > 0),
            richiesto_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            scade_at     TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '48 hours',
            message_id   BIGINT
        )
    """)
    _q("""
        CREATE TABLE IF NOT EXISTS dpe (
            id               SERIAL PRIMARY KEY,
            giocatore_id     INTEGER NOT NULL REFERENCES giocatori(id),
            team_id          TEXT NOT NULL,
            stagione         TEXT NOT NULL,
            importo_originale INTEGER NOT NULL,
            importo_dpe      INTEGER NOT NULL,
            pre_deadline     BOOLEAN NOT NULL DEFAULT TRUE,
            approvata_da     TEXT,
            timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (giocatore_id, stagione)
        )
    """)
    _q("""
        CREATE TABLE IF NOT EXISTS gas_sync_queue (
            id         SERIAL PRIMARY KEY,
            motivo     TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # v3.1.0 — posizioni eleggibili Yahoo (event log) + yahoo_id sui giocatori
    _q("ALTER TABLE giocatori ADD COLUMN IF NOT EXISTS yahoo_id INTEGER")
    _q("CREATE UNIQUE INDEX IF NOT EXISTS idx_giocatori_yahoo_id "
       "ON giocatori (yahoo_id) WHERE yahoo_id IS NOT NULL")
    _q("""
        CREATE TABLE IF NOT EXISTS posizioni_eleggibili (
            id            SERIAL PRIMARY KEY,
            giocatore_id  INT NOT NULL REFERENCES giocatori(id),
            posizioni     TEXT NOT NULL,
            fonte         TEXT NOT NULL,
            timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _q("CREATE INDEX IF NOT EXISTS idx_posizioni_giocatore "
       "ON posizioni_eleggibili (giocatore_id, timestamp DESC)")
    _q("""
        CREATE OR REPLACE VIEW posizioni_attuali AS
        SELECT DISTINCT ON (giocatore_id) giocatore_id, posizioni, fonte, timestamp
        FROM posizioni_eleggibili
        ORDER BY giocatore_id, timestamp DESC, id DESC
    """)

    # v3.3.1 — data in cui Yahoo ha aggiunto la posizione (Erminio rule), inserita dagli admin
    _q("ALTER TABLE posizioni_eleggibili ADD COLUMN IF NOT EXISTS data_yahoo DATE")

    # v3.3.0 — dichiarazioni di ruolo in sospeso in regular season (48h, poi estrazione)
    _q("""
        CREATE TABLE IF NOT EXISTS ruoli_pendenti (
            id            SERIAL PRIMARY KEY,
            giocatore_id  INT  NOT NULL REFERENCES giocatori(id),
            team_id       TEXT NOT NULL,
            origine       TEXT NOT NULL,          -- trade | firma | rookie
            riferimento   TEXT,                   -- es. TRADE-2026-031
            creato        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            scadenza      TIMESTAMPTZ NOT NULL,
            stato         TEXT NOT NULL DEFAULT 'aperta',  -- aperta | dichiarata | estratta | annullata | senza_posizioni
            ruolo         TEXT,
            chiuso        TIMESTAMPTZ
        )
    """)
    _q("CREATE INDEX IF NOT EXISTS idx_ruoli_pendenti_aperti ON ruoli_pendenti (team_id) WHERE stato = 'aperta'")

    # v3.2.0 — dichiarazione ruoli: bozze persistenti (sopravvivono ai riavvii)
    _q("""
        CREATE TABLE IF NOT EXISTS ruoli_bozze (
            team_id       TEXT NOT NULL,
            stagione      TEXT NOT NULL,
            giocatore_id  INT  NOT NULL REFERENCES giocatori(id),
            ruolo         TEXT NOT NULL CHECK (ruolo IN ('PG','SG','SF','PF','C')),
            aggiornato    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (team_id, stagione, giocatore_id)
        )
    """)


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


def _q(sql: str, params=(), *, many=False, one=False):
    """Esegue una query e restituisce righe come dict."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if one:
                return cur.fetchone()
            if many:
                return cur.fetchall()
            return None


def _qval(sql: str, params=()):
    """Esegue una query e restituisce il valore scalare della prima colonna."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else None


# ── giocatori ─────────────────────────────────────────────────────────────────

def get_giocatore(gid: int) -> dict | None:
    return _q("SELECT * FROM giocatori WHERE id = %s", (gid,), one=True)

def cerca_giocatori(nome_norm: str) -> list:
    return _q(
        "SELECT * FROM giocatori WHERE nome_norm ILIKE %s ORDER BY nome_common",
        (f"%{nome_norm}%",), many=True
    )

def get_roster_team(team_id: str) -> list:
    """Roster attuale con data_nascita e anni_scala per il PNG roster.
    L'importo tiene conto della DPE attiva per la stagione corrente."""
    from settings import stagione_corrente
    stagione = stagione_corrente()
    return _q(
        """SELECT g.id AS giocatore_id, g.nome_common, g.nome_norm, g.data_nascita,
                  COALESCE(d.importo_dpe, c.importo) AS importo,
                  c.importo AS importo_originale,
                  c.anni_originali, c.stagione_firma, c.tipo AS tipo_contratto,
                  COALESCE(r.anni_scala, 0) AS anni_scala,
                  (d.id IS NOT NULL) AS ha_dpe
           FROM contratti c
           JOIN giocatori g ON g.id = c.giocatore_id
           LEFT JOIN rookie r ON r.giocatore_id = g.id AND r.firmato = TRUE
           LEFT JOIN dpe d ON d.giocatore_id = g.id AND d.team_id = c.team_id AND d.stagione = %s
           WHERE c.team_id = %s AND c.attivo = TRUE""",
        (stagione, team_id), many=True
    ) or []


# ── contratti ─────────────────────────────────────────────────────────────────

def get_contratto_attivo(giocatore_id: int) -> dict | None:
    return _q(
        "SELECT * FROM contratti WHERE giocatore_id = %s AND attivo = TRUE",
        (giocatore_id,), one=True
    )

def get_contratti_team(team_id: str) -> list:
    return _q(
        "SELECT c.*, g.nome_common FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id "
        "WHERE c.team_id = %s AND c.attivo = TRUE ORDER BY c.importo DESC",
        (team_id,), many=True
    )

def cap_occupato_team(team_id: str, stagione: str) -> int:
    """Cap totale occupato = contratti attivi (con DPE) + impatto taglio della stagione."""
    # Contratti attivi: se esiste DPE per questa stagione usa importo_dpe, altrimenti importo normale
    contratti = _qval(
        """SELECT COALESCE(SUM(
            COALESCE((SELECT d.importo_dpe FROM dpe d
                      WHERE d.giocatore_id = c.giocatore_id
                        AND d.team_id = c.team_id
                        AND d.stagione = %s), c.importo)
        ), 0)
        FROM contratti c WHERE c.team_id = %s AND c.attivo = TRUE""",
        (stagione, team_id)
    ) or 0
    spalmato = _qval(
        "SELECT COALESCE(SUM(importo), 0) FROM impatto_taglio WHERE team_id = %s AND stagione = %s",
        (team_id, stagione)
    ) or 0
    return contratti + spalmato


# ── trade ─────────────────────────────────────────────────────────────────────

def _next_bozza_num(team_id: str) -> int:
    """Calcola il prossimo bozza_num per questo team."""
    val = _qval(
        "SELECT COALESCE(MAX(bozza_num), 0) + 1 FROM trade "
        "WHERE proposta_da = %s",
        (team_id,)
    )
    return val or 1


def crea_trade_bozza(team_id: str, n_squadre: int, stagione: str) -> int:
    """Crea una bozza di trade con bozza_num progressivo per team."""
    num = _next_bozza_num(team_id)
    return _qval(
        "INSERT INTO trade (stagione, stato, n_squadre, proposta_da, bozza_num) "
        "VALUES (%s, 'bozza', %s, %s, %s) RETURNING id",
        (stagione, n_squadre, team_id, num)
    )


def approva_trade(trade_id: int, trade_ref: str, approvata_da: str):
    """Segna la trade come approvata con trade_ref, admin e timestamp."""
    _q(
        "UPDATE trade SET stato = 'approvata', trade_ref = %s, "
        "approvata_da = %s, approvata_at = NOW(), bozza_num = NULL, "
        "aggiornato = NOW() WHERE id = %s",
        (trade_ref, approvata_da, trade_id)
    )

def get_trade(trade_id: int) -> dict | None:
    return _q("SELECT * FROM trade WHERE id = %s", (trade_id,), one=True)

def get_bozza_by_num(team_id: str, bozza_num: int) -> dict | None:
    return _q(
        "SELECT * FROM trade WHERE proposta_da = %s AND bozza_num = %s AND stato = 'bozza'",
        (team_id, bozza_num), one=True
    )


def get_bozze_team(team_id: str) -> list:
    return _q(
        "SELECT * FROM trade WHERE proposta_da = %s AND stato = 'bozza' ORDER BY aggiornato DESC",
        (team_id,), many=True
    )

def get_trade_in_votazione(team_id: str) -> list:
    """Trade in votazione dove questo team deve ancora votare."""
    return _q(
        """SELECT t.* FROM trade t
           JOIN trade_voti v ON v.trade_id = t.id
           WHERE v.team_id = %s AND v.voto = 'pending' AND t.stato = 'proposta'
           ORDER BY t.timestamp DESC""",
        (team_id,), many=True
    )

def aggiungi_squadra_trade(trade_id: int, team_id: str, ordine: int):
    _q(
        "INSERT INTO trade_squadre (trade_id, team_id, ordine) VALUES (%s, %s, %s) "
        "ON CONFLICT DO NOTHING",
        (trade_id, team_id, ordine)
    )

def get_squadre_trade(trade_id: int) -> list:
    return _q(
        "SELECT * FROM trade_squadre WHERE trade_id = %s ORDER BY ordine",
        (trade_id,), many=True
    )

def aggiungi_item_trade(trade_id: int, tipo: str, team_id_da: str, team_id_a: str,
                         giocatore_id: int | None = None, pick_id: int | None = None) -> int:
    return _qval(
        "INSERT INTO trade_items (trade_id, tipo, giocatore_id, pick_id, team_id_da, team_id_a) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (trade_id, tipo, giocatore_id, pick_id, team_id_da, team_id_a)
    )

def rimuovi_item_trade(item_id: int):
    _q("DELETE FROM trade_items WHERE id = %s", (item_id,))

def get_items_trade(trade_id: int) -> list:
    return _q(
        """SELECT ti.*, g.nome_common, g.nome_norm,
                  c.importo AS giocatore_importo,
                  c.anni_originali AS giocatore_anni,
                  c.stagione_firma AS giocatore_stagione_firma,
                  c.tipo AS giocatore_tipo_contratto,
                  r.anni_scala AS giocatore_anni_scala,
                  p.anno AS pick_anno, p.round AS pick_round,
                  p.proprietario_orig AS pick_orig
           FROM trade_items ti
           LEFT JOIN giocatori g ON g.id = ti.giocatore_id
           LEFT JOIN contratti c ON c.giocatore_id = ti.giocatore_id AND c.attivo = TRUE
           LEFT JOIN rookie r ON r.giocatore_id = ti.giocatore_id AND r.firmato = TRUE
           LEFT JOIN pick p ON p.id = ti.pick_id
           WHERE ti.trade_id = %s
           ORDER BY ti.team_id_da, ti.tipo""",
        (trade_id,), many=True
    )

def aggiorna_stato_trade(trade_id: int, stato: str, note: str | None = None,
                          validazione_ok: bool | None = None, validazione_note: str | None = None):
    _q(
        "UPDATE trade SET stato = %s, aggiornato = NOW(), note = COALESCE(%s, note), "
        "validazione_ok = COALESCE(%s, validazione_ok), "
        "validazione_note = COALESCE(%s, validazione_note) "
        "WHERE id = %s",
        (stato, note, validazione_ok, validazione_note, trade_id)
    )

def cambia_stato_trade(trade_id: int, da: tuple, a: str, note: str | None = None) -> bool:
    """Passaggio di stato atomico: avviene solo se la trade è ancora in uno degli
    stati `da`. False se nel frattempo qualcun altro l'ha già cambiata."""
    return _qval(
        "UPDATE trade SET stato = %s, aggiornato = NOW(), note = COALESCE(%s, note) "
        "WHERE id = %s AND stato = ANY(%s) RETURNING id",
        (a, note, trade_id, list(da))
    ) is not None


def chiudi_voto_se_tutti_accettano(trade_id: int) -> bool:
    """proposta → in_approvazione solo se tutti i voti sono 'accettato' (atomico:
    con due voti quasi simultanei la trade va agli admin una volta sola)."""
    return _qval(
        "UPDATE trade SET stato = 'in_approvazione', aggiornato = NOW() "
        "WHERE id = %s AND stato = 'proposta' AND NOT EXISTS ("
        "  SELECT 1 FROM trade_voti WHERE trade_id = %s AND voto <> 'accettato') RETURNING id",
        (trade_id, trade_id)
    ) is not None


def get_trade_team(team_id: str, limite: int = 15) -> list:
    """Trade di una squadra per /my_trades: proposte da lei o in cui è coinvolta.
    Escluse le annullate e le bozze delle altre squadre (non ancora inviate)."""
    return _q(
        """SELECT t.* FROM trade t
           WHERE t.stato <> 'annullata'
             AND (t.proposta_da = %s
                  OR (t.stato <> 'bozza' AND EXISTS (
                      SELECT 1 FROM trade_squadre s WHERE s.trade_id = t.id AND s.team_id = %s)))
           ORDER BY t.aggiornato DESC
           LIMIT %s""",
        (team_id, team_id, limite), many=True
    ) or []


def clona_trade_in_bozza(trade_id: int, team_id: str, stagione: str) -> int:
    """Copia una trade (squadre e asset) in una nuova bozza di `team_id`.
    L'originale resta com'è, con il suo stato."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT n_squadre FROM trade WHERE id = %s", (trade_id,))
            n_squadre = cur.fetchone()[0]
            cur.execute("SELECT COALESCE(MAX(bozza_num), 0) + 1 FROM trade WHERE proposta_da = %s", (team_id,))
            num = cur.fetchone()[0]
            cur.execute("INSERT INTO trade (stagione, stato, n_squadre, proposta_da, bozza_num) "
                        "VALUES (%s, 'bozza', %s, %s, %s) RETURNING id", (stagione, n_squadre, team_id, num))
            nuovo = cur.fetchone()[0]
            cur.execute("INSERT INTO trade_squadre (trade_id, team_id, ordine) "
                        "SELECT %s, team_id, ordine FROM trade_squadre WHERE trade_id = %s", (nuovo, trade_id))
            cur.execute("INSERT INTO trade_items (trade_id, tipo, giocatore_id, pick_id, team_id_da, team_id_a) "
                        "SELECT %s, tipo, giocatore_id, pick_id, team_id_da, team_id_a "
                        "FROM trade_items WHERE trade_id = %s", (nuovo, trade_id))
            return nuovo


def set_trade_ref(trade_id: int, trade_ref: str):
    _q("UPDATE trade SET trade_ref = %s WHERE id = %s", (trade_ref, trade_id))

def inizializza_voti(trade_id: int, team_ids: list[str]):
    with get_conn() as conn:
        with conn.cursor() as cur:
            for tid in team_ids:
                cur.execute(
                    "INSERT INTO trade_voti (trade_id, team_id, voto) VALUES (%s, %s, 'pending') "
                    "ON CONFLICT DO NOTHING",
                    (trade_id, tid)
                )

def registra_voto(trade_id: int, team_id: str, voto: str):
    _q(
        "UPDATE trade_voti SET voto = %s, timestamp = NOW() WHERE trade_id = %s AND team_id = %s",
        (voto, trade_id, team_id)
    )

def get_voti_trade(trade_id: int) -> list:
    return _q(
        "SELECT * FROM trade_voti WHERE trade_id = %s ORDER BY team_id",
        (trade_id,), many=True
    )

def tutti_hanno_votato(trade_id: int) -> bool:
    pending = _qval(
        "SELECT COUNT(*) FROM trade_voti WHERE trade_id = %s AND voto = 'pending'",
        (trade_id,)
    )
    return pending == 0

def conferma_squadra_trade(trade_id: int, team_id: str):
    _q(
        "UPDATE trade_squadre SET confermata = TRUE WHERE trade_id = %s AND team_id = %s",
        (trade_id, team_id)
    )


# ── pick ─────────────────────────────────────────────────────────────────────

def get_pick_team(team_id: str) -> list:
    return _q(
        "SELECT * FROM pick WHERE proprietario_att = %s AND scattata = FALSE ORDER BY anno, round",
        (team_id,), many=True
    )

def get_rookie_scale_per_anno(anno_draft: int) -> dict:
    """
    Ritorna i dati per una colonna della rookie scale:
    - picks: lista di 24 slot (None se vuoto) con nome e flag # se non più in scala
    - diritti: lista di giocatori con diritti 2nd attivati (firmato=TRUE) in quell'anno
    """
    # Pick round 1 — ordinate per pick_numero, max 24
    picks_raw = _q(
        """SELECT r.pick_numero, g.nome_common,
                  (r.firmato = TRUE AND c.tipo != 'rookie') AS fuori_scala
           FROM rookie r
           JOIN giocatori g ON g.id = r.giocatore_id
           LEFT JOIN contratti c ON c.giocatore_id = r.giocatore_id AND c.attivo = TRUE
           WHERE r.round = 1 AND r.anno_draft = %s
           ORDER BY r.pick_numero""",
        (str(anno_draft),), many=True
    ) or []

    # Costruisci lista di 24 slot con gap
    picks_by_num = {p["pick_numero"]: p for p in picks_raw}
    picks = []
    for n in range(1, 25):
        p = picks_by_num.get(n)
        if p:
            nome = p["nome_common"]
            if p["fuori_scala"]:
                nome = f"#{nome}"
            picks.append(nome)
        else:
            picks.append(None)

    # Diritti 2nd attivati in quell'anno (firmato=TRUE, anno_firma=anno_draft)
    diritti_raw = _q(
        """SELECT g.nome_common
           FROM rookie r
           JOIN giocatori g ON g.id = r.giocatore_id
           WHERE r.round = 2 AND r.firmato = TRUE AND r.anno_firma = %s
           ORDER BY g.nome_common""",
        (str(anno_draft),), many=True
    ) or []

    return {
        "anno":    anno_draft,
        "picks":   picks,
        "diritti": [d["nome_common"] for d in diritti_raw],
    }

def gas_queue_max_id() -> int | None:
    """ID massimo in coda sync GAS, None se vuota."""
    return _qval("SELECT MAX(id) FROM gas_sync_queue")

def gas_queue_svuota_fino(max_id: int) -> None:
    """Cancella le richieste di sync fino a max_id (incluso)."""
    _q("DELETE FROM gas_sync_queue WHERE id <= %s", (max_id,))

def get_dpe_attive_team(team_id: str, stagione: str) -> list:
    """Ritorna tutte le DPE attive per un team in una stagione, con dati contratto."""
    return _q(
        """SELECT d.*, g.nome_common, c.anni_originali, c.stagione_firma
           FROM dpe d
           JOIN giocatori g ON g.id = d.giocatore_id
           JOIN contratti c ON c.giocatore_id = d.giocatore_id AND c.team_id = d.team_id AND c.attivo = TRUE
           WHERE d.team_id = %s AND d.stagione = %s""",
        (team_id, stagione), many=True
    ) or []

def get_stepien_anni() -> int:
    """Legge il parametro N della Stepien Rule da settings."""
    import settings
    return settings.stepien_anni()

def get_all_picks_by_orig(team_id: str) -> list:
    """Tutte le pick con proprietario_orig == team_id (ovunque siano ora), non scattate."""
    return _q(
        "SELECT * FROM pick WHERE proprietario_orig = %s AND scattata = FALSE ORDER BY anno, round",
        (team_id,), many=True
    ) or []

def get_pick_by_orig_anno_round(proprietario_orig: str, anno: str, round: int) -> dict | None:
    """Cerca una pick per proprietario originale, anno e round — usata dal trade parser."""
    return _q(
        "SELECT * FROM pick WHERE proprietario_orig = %s AND anno = %s AND round = %s AND scattata = FALSE",
        (proprietario_orig, anno, round), one=True
    )

def get_pick(pick_id: int) -> dict | None:
    return _q("SELECT * FROM pick WHERE id = %s", (pick_id,), one=True)


# ── rookie ────────────────────────────────────────────────────────────────────

def scadi_diritti_anno(anno_draft: int) -> list:
    """Marca come scaduti tutti i diritti 2nd non firmati del draft indicato.
    Restituisce le righe scadute (giocatore_id, team_id, nome_common)."""
    return _q(
        """UPDATE rookie r SET diritti_scaduti = TRUE
           FROM giocatori g
           WHERE g.id = r.giocatore_id
             AND r.round = 2 AND r.anno_draft = %s
             AND r.firmato = FALSE AND r.diritti_scaduti = FALSE
           RETURNING r.giocatore_id, r.team_id, g.nome_common""",
        (anno_draft,), many=True
    ) or []


def conta_diritti_attivi_anno(anno_draft: int) -> int:
    return _qval(
        "SELECT count(*) FROM rookie WHERE round = 2 AND anno_draft = %s "
        "AND firmato = FALSE AND diritti_scaduti = FALSE",
        (anno_draft,)
    ) or 0


def info_scadenza_diritti() -> dict | None:
    """Scadenza dei diritti 2nd al secondo anno (regolamento: 10 giorni prima
    della trade deadline). L'anno di draft che scade è stagione_corrente - 1.
    Ritorna None se manca la deadline in globals."""
    from settings import load_globals
    from datetime import date, timedelta
    g = load_globals()
    deadline_str = g.get("trade_deadline")
    if not deadline_str:
        return None
    try:
        deadline = date.fromisoformat(deadline_str)
    except ValueError:
        return None
    scadenza = deadline - timedelta(days=10)
    return {
        "anno_draft":      int(g.get("stagione_corrente", "2026")) - 1,
        "deadline":        deadline,
        "scadenza":        scadenza,
        "giorni_mancanti": (scadenza - date.today()).days,
    }


def get_diritti_scadenza_imminente(giorni: int = 3) -> dict | None:
    """Info scadenza se mancano al massimo 'giorni' giorni alla scadenza dei
    diritti (o se è già passata) e ci sono ancora diritti attivi da far scadere."""
    info = info_scadenza_diritti()
    if not info or info["giorni_mancanti"] > giorni:
        return None
    n = conta_diritti_attivi_anno(info["anno_draft"])
    if not n:
        return None
    return {**info, "n_diritti": n}


def get_diritti_2nd_team(team_id: str) -> list:
    return _q(
        "SELECT r.*, g.nome_common FROM rookie r JOIN giocatori g ON g.id = r.giocatore_id "
        "WHERE r.team_id = %s AND r.round = 2 AND r.firmato = FALSE AND r.diritti_scaduti = FALSE "
        "ORDER BY r.anno_draft",
        (team_id,), many=True
    )

def get_rookie(rookie_id: int) -> dict | None:
    return _q("SELECT * FROM rookie WHERE id = %s", (rookie_id,), one=True)


# ── impatto taglio ──────────────────────────────────────────────────────────────

def get_impatto_taglio_team(team_id: str, stagione: str) -> list:
    return _q(
        "SELECT cs.*, g.nome_common FROM impatto_taglio cs "
        "JOIN giocatori g ON g.id = cs.giocatore_id "
        "WHERE cs.team_id = %s AND cs.stagione = %s",
        (team_id, stagione), many=True
    )


def get_impatti_taglio_team_futuri(team_id: str, stagione: str) -> list:
    """Tutte le rate di impatto taglio dalla stagione corrente in poi, ordinate per stagione."""
    return _q(
        "SELECT cs.*, g.nome_common FROM impatto_taglio cs "
        "JOIN giocatori g ON g.id = cs.giocatore_id "
        "WHERE cs.team_id = %s AND cs.stagione >= %s "
        "ORDER BY cs.giocatore_id, cs.stagione",
        (team_id, stagione), many=True
    ) or []


# ── cap/slot anticipato ──────────────────────────────────────────────────────

def get_cap_anticipato(team_id: str) -> int:
    row = _q(
        "SELECT importo FROM cap_anticipato WHERE team_id = %s AND scade_at > NOW()",
        (team_id,), one=True
    )
    return row["importo"] if row else 0

def set_cap_anticipato(team_id: str, importo: int, message_id: int = None) -> None:
    _q(
        """INSERT INTO cap_anticipato (team_id, importo, richiesto_at, scade_at, message_id)
           VALUES (%s, %s, NOW(), NOW() + INTERVAL '48 hours', %s)
           ON CONFLICT (team_id) DO UPDATE
           SET importo=EXCLUDED.importo, richiesto_at=NOW(),
               scade_at=NOW() + INTERVAL '48 hours', message_id=EXCLUDED.message_id""",
        (team_id, importo, message_id)
    )

def reset_cap_anticipato(team_id: str) -> None:
    _q("DELETE FROM cap_anticipato WHERE team_id = %s", (team_id,))

def get_cap_anticipati_scaduti() -> list:
    return _q(
        "SELECT * FROM cap_anticipato WHERE scade_at <= NOW()",
        many=True
    ) or []

def get_slot_anticipato(team_id: str) -> int:
    row = _q(
        "SELECT quantita FROM slot_anticipato WHERE team_id = %s AND scade_at > NOW()",
        (team_id,), one=True
    )
    return row["quantita"] if row else 0

def set_slot_anticipato(team_id: str, quantita: int, message_id: int = None) -> None:
    _q(
        """INSERT INTO slot_anticipato (team_id, quantita, richiesto_at, scade_at, message_id)
           VALUES (%s, %s, NOW(), NOW() + INTERVAL '48 hours', %s)
           ON CONFLICT (team_id) DO UPDATE
           SET quantita=EXCLUDED.quantita, richiesto_at=NOW(),
               scade_at=NOW() + INTERVAL '48 hours', message_id=EXCLUDED.message_id""",
        (team_id, quantita, message_id)
    )

def reset_slot_anticipato(team_id: str) -> None:
    _q("DELETE FROM slot_anticipato WHERE team_id = %s", (team_id,))

def get_anticipati_scaduti() -> list:
    """Restituisce cap e slot anticipati scaduti per notifica e pulizia."""
    cap = _q("SELECT *, 'cap' as tipo FROM cap_anticipato WHERE scade_at <= NOW()", many=True) or []
    slot = _q("SELECT *, 'slot' as tipo FROM slot_anticipato WHERE scade_at <= NOW()", many=True) or []
    return cap + slot


# ── dpe ──────────────────────────────────────────────────────────────────────

def get_dpe_attiva(giocatore_id: int, stagione: str) -> dict | None:
    """Restituisce la DPE attiva per un giocatore in questa stagione, se esiste."""
    return _q(
        "SELECT * FROM dpe WHERE giocatore_id = %s AND stagione = %s",
        (giocatore_id, stagione), one=True
    )

def get_dpe_team(team_id: str, stagione: str) -> list:
    """Lista DPE attive per un team in questa stagione."""
    return _q(
        "SELECT d.*, g.nome_common FROM dpe d "
        "JOIN giocatori g ON g.id = d.giocatore_id "
        "WHERE d.team_id = %s AND d.stagione = %s",
        (team_id, stagione), many=True
    ) or []

def inserisci_dpe(giocatore_id: int, team_id: str, stagione: str,
                  importo_originale: int, importo_dpe: int,
                  pre_deadline: bool, approvata_da: str) -> int:
    """Inserisce una DPE approvata. Restituisce l'id."""
    return _qval(
        "INSERT INTO dpe (giocatore_id, team_id, stagione, importo_originale, "
        "importo_dpe, pre_deadline, approvata_da) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (giocatore_id, team_id, stagione, importo_originale, importo_dpe,
         pre_deadline, approvata_da)
    )


# ── transazioni ───────────────────────────────────────────────────────────────

def get_tagli_gratuiti_usati(team_id: str, stagione: str) -> int:
    """Conta i tagli 1x1 gratuiti usati da questo team in questa stagione."""
    return _qval(
        "SELECT COUNT(*) FROM transazioni "
        "WHERE tipo = 'cut' AND team_id_da = %s AND stagione = %s AND gratuito = TRUE",
        (team_id, stagione)
    ) or 0


def registra_transazione(tipo: str, giocatore_id: int, team_id_da: str | None,
                          team_id_a: str | None, stagione: str,
                          contratto_id: int | None = None, trade_id: int | None = None,
                          rookie_scale: bool = False, gratuito: bool = False,
                          note: str | None = None) -> int:
    return _qval(
        "INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, "
        "contratto_id, trade_id, rookie_scale, gratuito, note) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (tipo, giocatore_id, team_id_da, team_id_a, stagione,
         contratto_id, trade_id, rookie_scale, gratuito, note)
    )


def registra_decadimento(giocatore_id: int, team_id: str, stagione: str,
                          contratto_id: int | None = None, note: str | None = None) -> None:
    """
    Registra il decadimento di un contratto (ritiro, altra lega, ecc.), tutto in
    un'unica transazione DB:
    - transazione tipo 'decadimento' con team_id_a = NULL
    - contratto disattivato
    - impatti taglio futuri del giocatore per quella squadra eliminati
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, contratto_id, note) "
                "VALUES ('decadimento', %s, %s, NULL, %s, %s, %s)",
                (giocatore_id, team_id, stagione, contratto_id, note))
            cur.execute(
                "UPDATE contratti SET attivo = FALSE WHERE giocatore_id = %s AND team_id = %s AND attivo = TRUE",
                (giocatore_id, team_id))
            cur.execute(
                "DELETE FROM impatto_taglio WHERE giocatore_id = %s AND team_id = %s AND stagione >= %s",
                (giocatore_id, team_id, stagione))


def get_prima_transazione() -> str | None:
    """Timestamp della prima transazione presente nel DB (ISO format)."""
    return _qval("SELECT MIN(timestamp) FROM transazioni WHERE giocatore_id IS NOT NULL")


def get_roster_team_at(team_id: str, timestamp_iso: str) -> list:
    """Roster di una squadra a una data specifica (event sourcing).
    Prende l'ultima transazione per ogni giocatore <= timestamp_iso,
    poi filtra su team_id_a = team_id.
    """
    return _q(
        """SELECT * FROM (
               SELECT DISTINCT ON (t.giocatore_id)
                   g.id AS giocatore_id,
                   g.nome_common, g.nome_norm, g.data_nascita,
                   t.tipo AS ultimo_movimento, t.team_id_a, t.timestamp,
                   c.importo, c.anni_originali, c.stagione_firma, c.tipo AS tipo_contratto,
                   COALESCE(r.anni_scala, 0) AS anni_scala
               FROM transazioni t
               JOIN giocatori g ON g.id = t.giocatore_id
               LEFT JOIN contratti c ON c.id = t.contratto_id
               LEFT JOIN rookie r ON r.giocatore_id = g.id AND r.firmato = TRUE
               WHERE t.giocatore_id IS NOT NULL
                 AND t.timestamp <= %s
               ORDER BY t.giocatore_id, t.timestamp DESC
           ) last_tx
           WHERE team_id_a = %s""",
        (timestamp_iso, team_id), many=True
    ) or []


def get_contratti_team_at(team_id: str, timestamp_iso: str) -> list:
    """Contratti attivi di una squadra a una data specifica."""
    return _q(
        """SELECT c.*, g.nome_common FROM contratti c
           JOIN giocatori g ON g.id = c.giocatore_id
           WHERE c.team_id = %s
             AND c.attivo = TRUE
             AND EXISTS (
                 SELECT 1 FROM transazioni t
                 WHERE t.contratto_id = c.id
                   AND t.timestamp <= %s
             )
           ORDER BY c.importo DESC""",
        (team_id, timestamp_iso), many=True
    ) or []


# ── query per team_diff ───────────────────────────────────────────────────────

def get_pick_at(team_id: str, timestamp_iso: str) -> list:
    """Pick possedute da team_id a una certa data."""
    return _q(
        """SELECT * FROM pick
           WHERE proprietario_att = %s
             AND scattata = FALSE
             AND id NOT IN (
                 SELECT ti.pick_id FROM trade_items ti
                 JOIN trade t ON t.id = ti.trade_id
                 WHERE ti.team_id_da = %s
                   AND t.stato = 'approvata'
                   AND t.approvata_at <= %s
                   AND ti.pick_id IS NOT NULL
             )""",
        (team_id, team_id, timestamp_iso), many=True
    ) or []


def get_diritti_at(team_id: str, timestamp_iso: str) -> list:
    """Diritti rookie posseduti da team_id a una certa data."""
    return _q(
        """SELECT * FROM rookie
           WHERE team_id = %s
             AND firmato = FALSE
             AND diritti_scaduti = FALSE
             AND (scadenza_diritti IS NULL OR scadenza_diritti > %s)""",
        (team_id, timestamp_iso), many=True
    ) or []


def get_transazioni_giocatore_periodo(giocatore_id: int,
                                       da_iso: str, a_iso: str) -> list:
    """Transazioni di un giocatore in un periodo, ordinate per timestamp."""
    return _q(
        """SELECT * FROM transazioni
           WHERE giocatore_id = %s
             AND timestamp >= %s
             AND timestamp <= %s
           ORDER BY timestamp""",
        (giocatore_id, da_iso, a_iso), many=True
    ) or []


def get_primo_trade_pick_periodo(pick_id: int, da_iso: str, a_iso: str) -> dict | None:
    """Prima trade item che coinvolge questa pick nel periodo."""
    return _q(
        """SELECT ti.* FROM trade_items ti
           JOIN trade t ON t.id = ti.trade_id
           WHERE ti.pick_id = %s
             AND t.stato = 'approvata'
             AND t.approvata_at >= %s
             AND t.approvata_at <= %s
           ORDER BY t.approvata_at
           LIMIT 1""",
        (pick_id, da_iso, a_iso), one=True
    )


def get_proprie_1st_pick_storico(team_id: str) -> list:
    """
    Tutte le 1st pick originali di questo team, scattate e non.
    Usata solo per la verifica Stepien Rule.
    """
    return _q(
        "SELECT id, anno, scattata, proprietario_att FROM pick "
        "WHERE proprietario_orig = %s AND round = 1 "
        "ORDER BY anno",
        (team_id,), many=True
    ) or []


def get_trade_count_approvate(stagione: str) -> int:
    """Numero più alto già usato nei trade_ref della stagione (approvate o meno)."""
    val = _qval(
        """SELECT COALESCE(MAX(CAST(SPLIT_PART(trade_ref, '-', 3) AS INTEGER)), 0)
           FROM trade
           WHERE stagione = %s AND trade_ref IS NOT NULL
             AND trade_ref ~ '^TRADE-[0-9]+-[0-9]+$'""",
        (stagione,)
    )
    return int(val) if val else 0


def get_rookie_by_giocatore(giocatore_id: int) -> dict | None:
    return _q(
        "SELECT * FROM rookie WHERE giocatore_id = %s ORDER BY anno_draft DESC LIMIT 1",
        (giocatore_id,), one=True
    )


def elimina_trade(trade_id: int):
    """Elimina una bozza di trade con tutti i suoi item e squadre."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM trade_voti    WHERE trade_id = %s", (trade_id,))
            cur.execute("DELETE FROM trade_squadre WHERE trade_id = %s", (trade_id,))
            cur.execute("DELETE FROM trade_items   WHERE trade_id = %s", (trade_id,))
            cur.execute("DELETE FROM trade         WHERE id = %s",       (trade_id,))


def assegna_destinatario_item(item_id: int, team_id_a: str):
    """Assegna il destinatario a un singolo item di trade."""
    _q("UPDATE trade_items SET team_id_a = %s WHERE id = %s", (team_id_a, item_id))


def get_item_trade(item_id: int) -> dict | None:
    return _q("SELECT * FROM trade_items WHERE id = %s", (item_id,), one=True)


def get_max_pick_anno() -> int:
    """Anno massimo di pick presenti nel DB."""
    val = _qval("SELECT MAX(anno) FROM pick")
    return int(val) if val else 2032


def get_trade_by_ref(trade_ref: str) -> dict | None:
    return _q("SELECT * FROM trade WHERE trade_ref = %s", (trade_ref,), one=True)


# ── richieste agli admin (v3.6.0) ─────────────────────────────────────────────

GIORNI_RICHIESTA = 7   # una richiesta aperta da più giorni non blocca più una nuova


def apri_richiesta(tipo: str, chiave: int, team_id: str) -> bool:
    """Registra una richiesta aperta. False se ce n'è già una aperta (recente) per
    lo stesso tipo e giocatore."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE richieste_admin SET stato = 'scaduta', chiuso = NOW() "
                        "WHERE tipo = %s AND chiave = %s AND stato = 'aperta' "
                        "AND creato < NOW() - (%s || ' days')::interval",
                        (tipo, chiave, str(GIORNI_RICHIESTA)))
            cur.execute("INSERT INTO richieste_admin (tipo, chiave, team_id) VALUES (%s, %s, %s) "
                        "ON CONFLICT (tipo, chiave) WHERE stato = 'aperta' DO NOTHING RETURNING id",
                        (tipo, chiave, team_id))
            return cur.fetchone() is not None


def chiudi_richiesta(tipo: str, chiave: int, esito: str, da: str | None = None) -> str:
    """Chiude la richiesta aperta. Restituisce:
    'ok'       → chiusa adesso da questa chiamata (si procede);
    'gestita'  → era già stata approvata/rifiutata (non fare niente);
    'nessuna'  → nessuna richiesta registrata (messaggi di prima della v3.6.0: si procede)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE richieste_admin SET stato = %s, chiuso = NOW(), da = %s "
                        "WHERE tipo = %s AND chiave = %s AND stato = 'aperta' RETURNING id",
                        (esito, da, tipo, chiave))
            if cur.fetchone():
                return "ok"
            cur.execute("SELECT 1 FROM richieste_admin WHERE tipo = %s AND chiave = %s "
                        "AND stato IN ('approvata', 'rifiutata') LIMIT 1", (tipo, chiave))
            return "gestita" if cur.fetchone() else "nessuna"


def riapri_richiesta(tipo: str, chiave: int) -> None:
    """Se l'esecuzione fallisce dopo la chiusura, la richiesta torna aperta."""
    _q("UPDATE richieste_admin SET stato = 'aperta', chiuso = NULL, da = NULL "
       "WHERE id = (SELECT id FROM richieste_admin WHERE tipo = %s AND chiave = %s "
       "ORDER BY id DESC LIMIT 1)", (tipo, chiave))


# ── fantamedia per il roster (v3.6.0) ─────────────────────────────────────────

def stagione_fantamedia() -> str:
    """Stagione bref da mostrare nella colonna FM del roster (anno di fine: '2027' =
    2026-27). Si usa quella in corso solo se almeno metà dei giocatori sotto contratto
    nella lega ha già una fantamedia di quell'anno, altrimenti la precedente."""
    from settings import stagione_corrente
    corrente = str(int(stagione_corrente()) + 1)
    r = _q("""SELECT count(*) AS tot,
                     count(*) FILTER (WHERE EXISTS (
                         SELECT 1 FROM bref_stats b WHERE b.nome_bref = g.nome_bref AND b.stagione = %s
                     )) AS con_fm
              FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
              WHERE c.attivo = TRUE""", (corrente,), one=True) or {}
    tot, con_fm = r.get("tot") or 0, r.get("con_fm") or 0
    return corrente if tot and con_fm * 2 >= tot else str(int(corrente) - 1)


def fantamedie(gids: list[int], stagione_bref: str) -> dict[int, float]:
    """Ultima fantamedia della stagione per ciascun giocatore (chi non ce l'ha manca)."""
    if not gids:
        return {}
    righe = _q("""SELECT DISTINCT ON (g.id) g.id AS gid, b.fantamedia
                  FROM giocatori g JOIN bref_stats b ON b.nome_bref = g.nome_bref
                  WHERE g.id = ANY(%s) AND b.stagione = %s AND b.fantamedia IS NOT NULL
                  ORDER BY g.id, b.timestamp DESC""", (list(gids), stagione_bref), many=True) or []
    return {r["gid"]: float(r["fantamedia"]) for r in righe}

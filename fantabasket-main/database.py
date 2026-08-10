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


def migrate_db():
    """Applica migrazioni incrementali al DB."""
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
    """Roster attuale con data_nascita e anni_scala per il PNG roster."""
    return _q(
        """SELECT g.id AS giocatore_id, g.nome_common, g.nome_norm, g.data_nascita,
                  c.importo, c.anni_originali, c.stagione_firma, c.tipo AS tipo_contratto,
                  COALESCE(r.anni_scala, 0) AS anni_scala
           FROM contratti c
           JOIN giocatori g ON g.id = c.giocatore_id
           LEFT JOIN rookie r ON r.giocatore_id = g.id AND r.firmato = TRUE
           WHERE c.team_id = %s AND c.attivo = TRUE""",
        (team_id,), many=True
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

def get_pick(pick_id: int) -> dict | None:
    return _q("SELECT * FROM pick WHERE id = %s", (pick_id,), one=True)


# ── rookie ────────────────────────────────────────────────────────────────────

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
        "SELECT anno, scattata FROM pick "
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

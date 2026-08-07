"""
Gestione squadre: lettura del JSON teams.json.

NOTA v49: cap_disponibile e slot_disponibili nel JSON sono CONGELATI.
Cap e slot vengono calcolati da PostgreSQL tramite pg_client.
Le uniche scritture al JSON riguardano cap_penalizzato (set_cap_penalizzato).

Mantenuta compatibilità con modalità isolata (PG non disponibile):
in quel caso pg_client restituisce 0 e il calcolo si basa su cap_disponibile/slot_disponibili del JSON.
"""
import json
import threading
import logging
import os

TEAMS_PATH = os.environ.get("TEAMS_PATH", "/config/teams.json")

_lock  = threading.Lock()
logger = logging.getLogger(__name__)


def _load() -> dict:
    with open(TEAMS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict):
    with open(TEAMS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_teams() -> list[dict]:
    return _load()["teams"]


def get_team_by_id(team_id: str) -> dict | None:
    for t in get_all_teams():
        if t["id"] == team_id:
            return t
    return None


def get_team_by_gm(gm_telegram_id: int) -> dict | None:
    for t in get_all_teams():
        if gm_telegram_id in t["gm_ids"]:
            return t
    return None


def check_slot_virtuale(team_id: str, slot_impegnati: int) -> bool:
    """
    Controlla se ci sono slot liberi.
    Se PG disponibile: max_roster - roster_pg - slot_virtuale_sqlite > 0.
    Se PG non disponibile (modalità isolata): usa slot_disponibili dal JSON.
    """
    import pg_client
    import settings as _settings
    if pg_client.pg_disponibile():
        roster_count = pg_client.get_roster_count(team_id)
        return (_settings.slot_massimo() - roster_count - slot_impegnati) > 0
    # Modalità isolata
    team = get_team_by_id(team_id)
    if team is None:
        return False
    return (team["slot_disponibili"] - slot_impegnati) > 0


def scala_cap_slot(team_id: str, importo: int):
    """
    v49: no-op sul JSON. Il cap si riduce automaticamente dalla firma scritta su PG.
    In modalità isolata (PG non disponibile) aggiorna il JSON come fallback.
    """
    import pg_client
    if not pg_client.pg_disponibile():
        logger.warning("scala_cap_slot(%s, %d): PG non disponibile — aggiorno JSON (modalità isolata).", team_id, importo)
        with _lock:
            data = _load()
            for t in data["teams"]:
                if t["id"] == team_id:
                    t["cap_disponibile"] -= importo
                    t["slot_disponibili"] -= 1
                    break
            _save(data)


def libera_cap(team_id: str, importo: int, nome_giocatore: str = ""):
    """
    v49: deattiva il contratto in PG. Il cap si libera automaticamente.
    In modalità isolata aggiorna il JSON.
    """
    import pg_client
    if pg_client.pg_disponibile():
        if nome_giocatore:
            ok = pg_client.deattiva_contratto(team_id, importo, nome_giocatore)
            if not ok:
                logger.warning("libera_cap(%s, %d): contratto non trovato su PG — verificare manualmente.", team_id, importo)
        else:
            logger.warning("libera_cap(%s, %d): nome_giocatore non fornito — impossibile deattivare su PG.", team_id, importo)
        return
    # Modalità isolata
    with _lock:
        data = _load()
        for t in data["teams"]:
            if t["id"] == team_id:
                t["cap_disponibile"] += importo
                break
        _save(data)


# cap_penalizzato è l'unico valore che resta scrivibile nel JSON
def set_cap_penalizzato(team_id: str, valore: int):
    with _lock:
        data = _load()
        for t in data["teams"]:
            if t["id"] == team_id:
                t["cap_penalizzato"] = valore
                break
        _save(data)

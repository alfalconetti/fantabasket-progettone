import json
import os

TEAMS_PATH = os.environ.get("TEAMS_PATH", "/config/teams.json")


def _load() -> dict:
    with open(TEAMS_PATH, encoding="utf-8") as f:
        return json.load(f)

def get_all_teams() -> list:
    return _load()["teams"]

def get_team_by_id(team_id: str) -> dict | None:
    return next((t for t in get_all_teams() if t["id"] == team_id), None)

def get_team_by_gm(gm_id: int) -> dict | None:
    return next((t for t in get_all_teams() if gm_id in t.get("gm_ids", [])), None)

def is_gm(user_id: int) -> bool:
    return get_team_by_gm(user_id) is not None


def set_campo_team(team_id: str, campo: str, valore: str):
    """Aggiorna un campo editabile in teams.json."""
    import json, threading
    _lock = threading.Lock()
    with _lock:
        with open(TEAMS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for t in data["teams"]:
            if t["id"] == team_id:
                if valore == "" and campo in t:
                    del t[campo]
                else:
                    t[campo] = valore
                break
        with open(TEAMS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

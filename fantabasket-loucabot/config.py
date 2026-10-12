"""Configurazione del progettone, in sola lettura: fase, stagione, admin e canali li decide il bot
principale (globals.json), le squadre stanno in teams.json."""
import json
import os

GLOBALS_PATH = os.environ.get("GLOBALS_PATH", "/config/globals.json")
TEAMS_PATH = os.environ.get("TEAMS_PATH", "/config/teams.json")


def globali() -> dict:
    with open(GLOBALS_PATH, encoding="utf-8") as f:
        return json.load(f)


def stagione() -> str:
    return str(globali().get("stagione_corrente", "2026"))


def admin_ids() -> list[int]:
    return [int(x) for x in globali().get("admin_ids", [])]


def dev_id() -> int | None:
    d = globali().get("dev_id")
    return int(d) if d else None


def is_admin(uid: int) -> bool:
    return int(uid) in admin_ids() or int(uid) == dev_id()


def gruppo_admin():
    return globali().get("admin_group_id")


def canale_log():
    """Il canale log di loucabot; finché non c'è, quello del bot principale."""
    g = globali()
    return g.get("log_channel_id_louca") or g.get("log_channel_id_main")


def squadre() -> list[dict]:
    with open(TEAMS_PATH, encoding="utf-8") as f:
        return json.load(f)["teams"]


def squadra(team_id: str) -> dict | None:
    return next((t for t in squadre() if t["id"] == team_id), None)


def squadra_del_gm(uid: int) -> dict | None:
    return next((t for t in squadre() if int(uid) in [int(x) for x in t.get("gm_ids", [])]), None)


def nome(team_id: str) -> str:
    t = squadra(team_id)
    return t["nome"] if t else team_id


def versione() -> str:
    """L'ultima versione del CHANGELOG di loucabot."""
    import re
    try:
        t = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "CHANGELOG.md"), encoding="utf-8").read()
        v = re.findall(r"^## (v[0-9][0-9A-Za-z.\-]*)", t, re.M)
        return v[-1] if v else "sconosciuta"
    except Exception:
        return "sconosciuta"

"""
Letture comuni a loucabot e al bot principale (v7.3.0, Luca 09/11): /player, /status e /calendario stanno in
entrambi i bot, col codice qui in shared/ (giocatore.py, status_squadra.py, calendario_squadra.py).

Il database lo dà il bot: `usa(q)` all'avvio, con una funzione q(sql, params, one=, many=) (loucabot: db.q,
bot principale: database._q). Si passa una lambda che chiama quella del bot al momento, così klra, che in
loucabot sostituisce db.q (sola lettura, risultati del sistema), resta valido anche qui.
Configurazione in sola lettura: globals.json e teams.json, gli stessi file dei due bot (GLOBALS_PATH, TEAMS_PATH).
"""
import json
import os
import re
import unicodedata

_Q = None


def usa(q) -> None:
    global _Q
    _Q = q


def q(sql: str, params=None, one: bool = False, many: bool = False):
    if _Q is None:
        raise RuntimeError("shared.lettura: database non impostato (usa(q) all'avvio del bot)")
    return _Q(sql, params, one=one, many=many)


# ── configurazione (sola lettura) ──────────────────────────────────────────────

def globali() -> dict:
    with open(os.environ.get("GLOBALS_PATH", "/config/globals.json"), encoding="utf-8") as f:
        return json.load(f)


def stagione() -> str:
    return str(globali().get("stagione_corrente", "2026"))


def squadre() -> list[dict]:
    with open(os.environ.get("TEAMS_PATH", "/config/teams.json"), encoding="utf-8") as f:
        return json.load(f)["teams"]


def squadra(team_id: str) -> dict | None:
    return next((t for t in squadre() if t["id"] == team_id), None)


def squadra_del_gm(uid: int) -> dict | None:
    return next((t for t in squadre() if int(uid) in [int(x) for x in t.get("gm_ids", [])]), None)


def nome(team_id: str) -> str:
    t = squadra(team_id)
    return t["nome"] if t else team_id


def cartella_foto() -> str:
    """Le foto ESPN dei giocatori (le scarica loucabot): FOTO_DIR in loucabot, config/foto nel bot principale."""
    return os.environ.get("FOTO_DIR") or os.path.join(os.environ.get("CONFIG_DIR", "/config"), "foto")


def foto(atleta: str | None) -> str | None:
    p = os.path.join(cartella_foto(), f"{atleta}.png") if atleta else None
    return p if p and os.path.exists(p) else None


# ── nomi e tabellini ───────────────────────────────────────────────────────────

_SUFFISSI = {"jr", "sr", "ii", "iii", "iv", "v"}
_LETTERE = str.maketrans({"đ": "d", "Đ": "d", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "ß": "ss", "æ": "ae", "þ": "th"})


def norm(nome_: str) -> str:
    """Il nome senza accenti, trattini, punti e suffissi (Jr., III), tutto attaccato: per confrontare i nomi."""
    s = unicodedata.normalize("NFKD", (nome_ or "").translate(_LETTERE)).encode("ascii", "ignore").decode().lower()
    parole = [p for p in re.sub(r"[^a-z ]", "", s.replace("-", " ")).split() if p not in _SUFFISSI]
    return "".join(parole)


def conta(r: dict) -> bool:
    """Una riga di tabellino fa media? Solo se è entrato, e uno 0 con 0 minuti no (deciso con
    Luca il 13/10): uno 0 con dei minuti sì."""
    return bool(r["giocato"]) and not (float(r["fp"] or 0) == 0 and int(r.get("minuti") or 0) == 0)


def squadre_roster(atleti: list[str]) -> dict[str, str]:
    """La squadra NBA di adesso dai roster ESPN (aggiornati ogni mattina alle 8:30)."""
    righe = q("SELECT atleta, squadra FROM nba_atleti WHERE atleta = ANY(%s) AND squadra IS NOT NULL",
              (list(atleti),), many=True) or []
    return {r["atleta"]: r["squadra"] for r in righe}


def ultima_squadra(atleti: list[str], prima_del) -> dict[str, str]:
    """La squadra NBA dell'ultimo tabellino di ogni giocatore prima del giorno indicato."""
    righe = q("""SELECT DISTINCT ON (t.atleta) t.atleta, t.squadra FROM nba_tabellini t
                 JOIN nba_partite p ON p.espn_id = t.partita
                 WHERE t.atleta = ANY(%s) AND p.data_et < %s ORDER BY t.atleta, p.inizio DESC""",
              (list(atleti), prima_del), many=True) or []
    return {r["atleta"]: r["squadra"] for r in righe}


# ── squadre del fantabasket: colore e logo (v7.4.0, /rendimento) ──────────────

def colore(team: dict | None) -> str:
    """Il colore dell'intestazione scelto con /palette (colore_header), se no il blu di sempre."""
    c = (team or {}).get("colore_header") or ""
    return c if re.fullmatch(r"#[0-9A-Fa-f]{6}", c) else "#1A237E"


def logo(team_id: str) -> str:
    cartella = os.environ.get("LOGHI_DIR") or os.path.join(os.path.dirname(os.environ.get("TEAMS_PATH", "/config/teams.json")), "loghi")
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = os.path.join(cartella, f"{team_id}_logo.{ext}")
        if os.path.exists(p):
            return p
    return ""

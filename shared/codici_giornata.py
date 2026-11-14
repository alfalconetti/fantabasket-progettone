"""
Codici delle giornate (v7.9.5, Luca 14/11): G regular season, P playoff, Q Quasi NBA Cup (shared/quasi_cup.py).

P e G sono sinonimi: P1 è la giornata dopo l'ultima di regular season (quest'anno G39, perché la regular season
finisce alla G38: dipende dal massimo del calendario importato), fino a P22. Un numero senza lettera vale G in
regular season e P nella fase playoff (globals.json «fase»). In loucabot e nel bot principale (stessa lettura).
"""
import re

from shared import lettura as L

MAX_PLAYOFF = 22               # il massimo delle giornate di playoff (Luca, 14/11)
_RE = re.compile(r"([GgPp]?)(\d{1,3})")


def ultima_rs(s: str | None = None) -> int | None:
    """L'ultima giornata di regular season del calendario importato."""
    r = L.q("SELECT MAX(numero) AS n FROM lega_giornate WHERE stagione = %s AND tipo = 'regular'",
            (s or L.stagione(),), one=True)
    return r["n"] if r and r["n"] is not None else None


def in_playoff() -> bool:
    try:
        return str(L.globali().get("fase", "")) == "playoff"
    except Exception:
        return False


def e_codice(testo: str) -> bool:
    return bool(_RE.fullmatch((testo or "").strip()))


def numero(testo: str, s: str | None = None) -> int | None:
    """«G41», «P3», «41», «3» → il numero della giornata (quello di lega_giornate). None se non è un codice o se P non
    si può tradurre (calendario di regular season non importato, P oltre 22)."""
    m = _RE.fullmatch((testo or "").strip())
    if not m:
        return None
    lettera, n = m.group(1).upper(), int(m.group(2))
    if lettera == "" and in_playoff():
        lettera = "P"
    if lettera == "P":
        if not 1 <= n <= MAX_PLAYOFF:
            return None
        u = ultima_rs(s)
        return u + n if u is not None else None
    return n


def codice(n: int, s: str | None = None) -> str:
    """Il numero di lega_giornate → «G12» o, oltre la regular season, «P3 (G41)»."""
    u = ultima_rs(s)
    if u is not None and n > u:
        return f"P{n - u} (G{n})"
    return f"G{n}"

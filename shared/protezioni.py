"""
Protezioni delle pick (v7.27.0, Luca 23/11: «resterei molto semplice»).

- Solo le **1st** si proteggono, e la protezione la mette **solo chi cede la pick la prima volta** (il proprietario
  originale, che non l'ha mai scambiata prima).
- Grammatica: «protetta 1-4» (anche «protetta 3»: solo la 3ª). Nel builder delle trade e nell'import dei testi.
- Al draft si guarda la posizione **dopo le penalità**: se cade nella protezione la pick **resta al proprietario di
  partenza** (anche se nel frattempo è passata di mano più volte) e la protezione **si estingue** (niente rinvio
  all'anno dopo, Luca: «altrimenti restano bloccate troppe pick in ballo»).

Nel database: `pick.protezioni` JSONB {"da": 1, "a": 4}; nella bozza della trade `trade_items.protezione`, che
diventa `pick.protezioni` quando la trade viene eseguita.
"""
import json
import re

_RE = re.compile(r"\bprotett[ao]\s+(top\s+)?(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\b", re.IGNORECASE)
MAX = 24


class Errore(ValueError):
    pass


def leggi(testo: str) -> dict | None:
    """«protetta 1-4» → {"da": 1, "a": 4}; «protetta 3» → {"da": 3, "a": 3}; niente protezione → None."""
    m = _RE.search(testo or "")
    if not m:
        return None
    if m.group(1):                                     # «protetta top 5» = 1-5
        da, a = 1, int(m.group(2))
    else:
        da, a = int(m.group(2)), int(m.group(3) or m.group(2))
    if da > a:
        da, a = a, da
    if da < 1 or a > MAX:
        raise Errore(f"Protezione «{m.group(0)}»: le posizioni vanno da 1 a {MAX}.")
    return {"da": da, "a": a}


def togli(testo: str) -> str:
    """Il testo senza la protezione (per leggere il resto della riga)."""
    return _RE.sub("", testo or "").strip(" ,;()-–")


def _dict(p) -> dict | None:
    if not p:
        return None
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except ValueError:
            return None
    return p if isinstance(p, dict) and "da" in p and "a" in p else None


def testo(p) -> str:
    """«protetta 1-4» (o «protetta 3»); le protezioni scritte in un altro modo (import vecchi) come sono."""
    d = _dict(p)
    if d:
        return f"protetta {d['da']}" if d["da"] == d["a"] else f"protetta {d['da']}-{d['a']}"
    if not p:
        return ""
    if isinstance(p, dict):
        return ", ".join(f"{k} {v}" for k, v in p.items())
    return str(p)


def scatta(p, posizione: int) -> bool:
    """La pick, alla `posizione` finale (dopo le penalità), cade nella protezione?"""
    d = _dict(p)
    return bool(d and d["da"] <= int(posizione) <= d["a"])


def proteggibile(pick: dict, team_da: str, scambiata_prima: bool) -> bool:
    """Si può proteggere in questa trade: 1st, ceduta dal proprietario originale che non l'ha mai scambiata, ancora
    senza protezione e non ancora usata."""
    return (int(pick.get("round") or 0) == 1 and pick.get("proprietario_orig") == team_da
            and pick.get("proprietario_att") == team_da and not pick.get("protezioni")
            and not pick.get("scattata") and not scambiata_prima)

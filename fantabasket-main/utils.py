"""
Utility condivise — Fantabasket Main Bot.
Centralizza: timezone, formattazione date, normalizzazione nomi, cognome.
"""
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")


# ── date/time ─────────────────────────────────────────────────────────────────

def now_rome() -> datetime:
    return datetime.now(ROME)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def format_dt(dt: datetime | str) -> str:
    """Formatta datetime in 'DD/MM/YYYY HH:MM' ora di Roma."""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.astimezone(ROME).strftime("%d/%m/%Y %H:%M")

def format_dt_short(dt: datetime | str) -> str:
    """Formatta datetime in 'DD/MM HH:MM' ora di Roma."""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.astimezone(ROME).strftime("%d/%m %H:%M")


# ── nomi ──────────────────────────────────────────────────────────────────────

_SUFFISSI = {"jr", "sr", "ii", "iii", "iv"}

def normalizza(s: str) -> str:
    """Rimuove diacritici e porta in minuscolo."""
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower().strip()

def cognome(nome: str) -> str:
    """Ultima parola del nome ignorando suffissi (Jr., Sr., II, III, IV)."""
    tokens = nome.split()
    while len(tokens) > 1 and tokens[-1].lower().rstrip(".") in _SUFFISSI:
        tokens.pop()
    return tokens[-1] if tokens else nome

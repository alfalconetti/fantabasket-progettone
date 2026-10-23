"""
Date nei comandi, in un formato solo e tollerante (Luca, 20/10, fatto nella v6.2.1): tutti i bot.

Accettati, con separatore - / o .:
  AAAA-MM-GG   2026-10-20 · 2026/10/20
  GG-MM-AAAA   20/10/2026 · 20-10-2026 · 20.10.2026
  GG-MM-AA     20/10/26   (anno a 2 cifre: sempre giorno, mese, anno; è il 2026)
Con l'ora (ad esempio /sposta_asta): la data poi «HH:MM», separati da uno spazio o da una T
(2026-11-15T20:00, 15/11/26 20:00).
"""
import re
from datetime import date, datetime, time

_SEP = r"[-/.]"
_RE_ANNO_PRIMA = re.compile(rf"^(\d{{4}}){_SEP}(\d{{1,2}}){_SEP}(\d{{1,2}})$")
_RE_GIORNO_PRIMA = re.compile(rf"^(\d{{1,2}}){_SEP}(\d{{1,2}}){_SEP}(\d{{2}}|\d{{4}})$")
_RE_ORA = re.compile(r"^(\d{1,2})[:.](\d{2})$")

USO = "GG/MM/AAAA (anche GG/MM/AA, AAAA-MM-GG, con - / o .)"


def leggi_data(testo) -> date | None:
    """La data scritta in uno dei formati accettati, o None."""
    s = str(testo or "").strip()
    try:
        m = _RE_ANNO_PRIMA.match(s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = _RE_GIORNO_PRIMA.match(s)
        if m:
            a = int(m.group(3))
            return date(a + 2000 if a < 100 else a, int(m.group(2)), int(m.group(1)))
    except ValueError:                      # 31/02, mese 13…
        return None
    return None


def leggi_ora(testo) -> time | None:
    m = _RE_ORA.match(str(testo or "").strip())
    if not m:
        return None
    try:
        return time(int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def leggi_data_ora(testo, ora_default: time | None = None) -> datetime | None:
    """«data ora» o «dataTora» (senza fuso); senza ora vale ora_default, se c'è."""
    s = str(testo or "").strip().replace("T", " ", 1) if re.match(r"^\d{4}-\d", str(testo or "").strip()) else str(testo or "").strip()
    parti = s.split()
    if not parti or len(parti) > 2:
        return None
    d = leggi_data(parti[0])
    if not d:
        return None
    t = leggi_ora(parti[1]) if len(parti) == 2 else ora_default
    if t is None:
        return None
    return datetime.combine(d, t)

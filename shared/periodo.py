"""Il periodo in fondo a un comando di statistiche (v7.20.0, Luca 21/11): come /team_diff.

`/comando NOME`                → la stagione
`/comando NOME 01-11-26`       → da quella data a oggi
`/comando NOME 01-11-26 15-11-26` → l'intervallo (date in qualsiasi formato di shared.date_comandi)
`/comando NOME 10`             → le ultime 10 partite **giocate** (N maggiore di 5: le ultime 5 sono già in /player)

`leggi(args)` separa il nome dal periodo: (nome, periodo) o solleva Errore col testo per l'utente.
Pensato per riusarlo in /rendimento e /confronto (MIGRATION, «/rendimento con un periodo»).
"""
import re
from dataclasses import dataclass
from datetime import date

from shared.date_comandi import leggi_data

MIN_ULTIME = 6


class Errore(ValueError):
    pass


@dataclass
class Periodo:
    dal: date | None = None
    al: date | None = None
    ultime: int | None = None

    def descrizione(self, stagione_txt: str) -> str:
        if self.ultime:
            return f"ultime {self.ultime} partite giocate"
        if self.dal and self.al:
            return f"dal {self.dal:%d/%m/%Y} al {self.al:%d/%m/%Y}"
        if self.dal:
            return f"dal {self.dal:%d/%m/%Y} a oggi"
        return f"stagione {stagione_txt}"


def leggi(args: list[str]) -> tuple[str, Periodo]:
    parole = list(args or [])
    date_ = []
    while parole and len(date_) < 2:
        d = leggi_data(parole[-1]) if not parole[-1].isdigit() else None
        if d is None:
            break
        date_.insert(0, d)
        parole.pop()
    if date_:
        if len(date_) == 2 and date_[0] > date_[1]:
            date_.reverse()
        return " ".join(parole), Periodo(dal=date_[0], al=date_[1] if len(date_) == 2 else None)
    if len(parole) > 1 and _SEMBRA_DATA.fullmatch(parole[-1]):       # v7.20.2: una data scritta male non è un nome
        raise Errore(f"Non capisco la data «{parole[-1]}»: scrivila come 01-11-26 (giorno-mese-anno).")
    if len(parole) > 1 and parole[-1].isdigit():
        n = int(parole[-1])
        if n < MIN_ULTIME:
            raise Errore(f"Con un numero: le ultime N partite giocate, con N maggiore di 5 (le ultime 5 sono già in /player).")
        return " ".join(parole[:-1]), Periodo(ultime=n)
    return " ".join(parole), Periodo()


_SEMBRA_DATA = re.compile(r"\d{1,4}[-/.]\d{1,2}(?:[-/.]\d{1,4})?")


def stagione_txt(s) -> str:
    return f"{s}-{(int(s) + 1) % 100:02d}"


def stagioni_txt(stagioni: list) -> str:
    """«stagione 2026-27», «stagioni 2025-26 e 2026-27», «stagioni 2024-25 – 2026-27»."""
    ss = sorted(set(stagioni))
    if len(ss) == 1:
        return f"stagione {stagione_txt(ss[0])}"
    if len(ss) == 2:
        return f"stagioni {stagione_txt(ss[0])} e {stagione_txt(ss[1])}"
    return f"stagioni {stagione_txt(ss[0])} – {stagione_txt(ss[-1])}"


def descrizione_vera(periodo: "Periodo", giocate: int, primo: date | None, oggi: date | None = None) -> str:
    """Il periodo come è davvero nei dati (v7.20.2, Luca 21/11: «i titoli corrispondano alla verità»): una data prima
    dei primi tabellini del bot diventa quella dei primi dati; un «al» nel futuro diventa «a oggi»; le ultime N con
    meno di N partite giocate in tutto diventano «tutte le K partite giocate nei dati del bot»."""
    oggi = oggi or date.today()
    if periodo.ultime:
        if giocate < periodo.ultime:
            return f"tutte le {giocate} partite giocate nei dati del bot"
        return f"ultime {periodo.ultime} partite giocate"
    if periodo.dal and primo and periodo.dal < primo:
        dal = f"dal {primo:%d/%m/%Y} (primi dati del bot)"
    elif periodo.dal:
        dal = f"dal {periodo.dal:%d/%m/%Y}"
    else:
        dal = ""
    al = f"al {periodo.al:%d/%m/%Y}" if periodo.al and periodo.al < oggi else "a oggi"
    return f"{dal} {al}".strip()

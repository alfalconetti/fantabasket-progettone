"""Il periodo in fondo a un comando di statistiche (v7.20.0, Luca 21/11): come /team_diff.

`/comando NOME`                → la stagione
`/comando NOME 01-11-26`       → da quella data a oggi
`/comando NOME 01-11-26 15-11-26` → l'intervallo (date in qualsiasi formato di shared.date_comandi)
`/comando NOME 10`             → le ultime 10 partite **giocate** (N maggiore di 5: le ultime 5 sono già in /player)

`leggi(args)` separa il nome dal periodo: (nome, periodo) o solleva Errore col testo per l'utente.
Pensato per riusarlo in /rendimento e /confronto (MIGRATION, «/rendimento con un periodo»).
"""
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
    if len(parole) > 1 and parole[-1].isdigit():
        n = int(parole[-1])
        if n < MIN_ULTIME:
            raise Errore(f"Con un numero: le ultime N partite giocate, con N maggiore di 5 (le ultime 5 sono già in /player).")
        return " ".join(parole[:-1]), Periodo(ultime=n)
    return " ".join(parole), Periodo()

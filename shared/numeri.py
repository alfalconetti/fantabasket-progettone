"""
Arrotondamento dei fantapunti all'ottavo (deciso con Luca il 13/10): le medie e i totali
possono valere solo 0, 0,125, 0,25, 0,375, 0,5, 0,625, 0,75, 0,875 dopo la virgola, che a due
decimali si scrivono 0, 0,13, 0,25, 0,38, 0,50, 0,63, 0,75, 0,88. I fantapunti di una partita
sono già multipli di 0,25; la media di più partite e la media della stagione no.

La metà si arrotonda lontano da zero, come ROUND dei fogli Google: sul foglio di calcolo il
punteggio è ROUND(AVERAGE(notti)*8;0)/8, e deve dare lo stesso numero del bot.
"""
from decimal import ROUND_HALF_UP, Decimal


def _dec(x) -> Decimal:
    """Il float come decimale, senza il rumore della virgola mobile (2,4999999999 → 2,5)."""
    return Decimal(repr(float(x))).quantize(Decimal("1e-9"), ROUND_HALF_UP)


def ottavi(x) -> float:
    """All'ottavo più vicino (la metà lontano da zero)."""
    return float((_dec(x) * 8).quantize(Decimal(1), ROUND_HALF_UP) / 8)


def testo(x) -> str:
    """Due decimali con la virgola, la metà per eccesso: 0,125 → "0,13" (Python darebbe "0,12")."""
    return str(_dec(x).quantize(Decimal("0.01"), ROUND_HALF_UP)).replace(".", ",")

"""
Esempi nei messaggi dei bot con squadre vere della lega, a caso a ogni risposta (v7.20.4, Luca 21/11: «fare ciclare
squadre a caso tra i nomi reali»). Le guide (versionate) usano segnaposti come SQUADRA; i nomi veri stanno solo in
teams.json. Se teams.json non si legge: «Squadra A», «Squadra B».
"""
import json
import os
import random


def nomi(n: int = 1) -> list[str]:
    """`n` nomi diversi di squadre della lega, a caso."""
    try:
        with open(os.environ.get("TEAMS_PATH", "/config/teams.json"), encoding="utf-8") as f:
            tutti = [t["nome"] for t in json.load(f)["teams"] if t.get("nome")]
    except Exception:
        tutti = []
    if len(tutti) < n:
        tutti = [f"Squadra {chr(65 + i)}" for i in range(max(n, 2))]
    return random.sample(tutti, n)


def squadra() -> str:
    return nomi(1)[0]


def due() -> tuple[str, str]:
    a, b = nomi(2)
    return a, b


def filtro(nome: str) -> str:
    """Per i filtri chiave:valore (`squadra:…`): tra virgolette se il nome ha spazi."""
    return f'"{nome}"' if " " in nome else nome

"""
Vincoli di ruolo del roster — involucro del modulo condiviso shared/ruoli_core.py
(stessa logica usata dal bot aste). Mantiene l'interfaccia usata da trade e ruoli.
"""
import database as db
from shared.ruoli_core import CATEGORIA, MINIMI, deficit_minimo  # noqa: F401 (riesportati)
from shared import ruoli_core as core


def deficit_team(team_id: str, stagione: str, togli=(), aggiungi=(), imposti: dict | None = None) -> int:
    return core.deficit_team(db._q, team_id, stagione, togli=togli, aggiungi=aggiungi, imposti=imposti)

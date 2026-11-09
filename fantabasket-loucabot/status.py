"""
/status [SQUADRA] (tutti, v7.1.0): il codice sta in shared/status_squadra.py dalla v7.3.0 (anche nel bot principale).
"""
from telegram.ext import CommandHandler

from shared.status_squadra import ORDINE, ROMA, cmd_status, dati, e, testo  # noqa: F401


def get_handlers() -> list:
    return [CommandHandler("status", cmd_status)]

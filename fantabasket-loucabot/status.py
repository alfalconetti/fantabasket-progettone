"""
/status [SQUADRA] (tutti, v7.1.0): il codice sta in shared/status_squadra.py dalla v7.3.0 (anche nel bot principale).
"""
from telegram.ext import CommandHandler

from shared.prospetto_rinnovi import cmd_prospetto_rinnovi   # v7.33.0: il prospetto dei rinnovi (anche nel principale)

from shared.status_squadra import ORDINE, ROMA, cmd_status, dati, e, testo  # noqa: F401


def get_handlers() -> list:
    return [CommandHandler("status", cmd_status),
            CommandHandler("prospetto_rinnovi", cmd_prospetto_rinnovi, block=False)]

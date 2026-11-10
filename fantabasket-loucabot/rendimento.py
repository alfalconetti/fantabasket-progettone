"""
/rendimento e /rendimento_carriera (tutti, v7.4.0), /confronto e /confronto_carriera (v7.4.3): il codice sta in shared/rendimento.py, comune al bot principale
(lì solo in privato; nei gruppi risponde loucabot).
"""
from telegram.ext import CallbackQueryHandler, CommandHandler

from shared.confronto import cmd_confronto, cmd_confronto_carriera
from shared.rendimento import PATTERN, cb_rendimento, cmd_rendimento, cmd_rendimento_carriera


def get_handlers() -> list:
    return [CommandHandler("rendimento", cmd_rendimento), CommandHandler("rendimento_carriera", cmd_rendimento_carriera),
            CallbackQueryHandler(cb_rendimento, pattern=PATTERN),
            CommandHandler("confronto", cmd_confronto, block=False),                  # v7.4.3
            CommandHandler("confronto_carriera", cmd_confronto_carriera, block=False)]

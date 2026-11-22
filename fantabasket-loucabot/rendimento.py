"""
/rendimento e /rendimento_carriera (tutti, v7.4.0), /confronto e /confronto_carriera (v7.4.3): il codice sta in shared/rendimento.py, comune al bot principale
(lì solo in privato; nei gruppi risponde loucabot).
"""
from telegram.ext import CallbackQueryHandler, CommandHandler

from shared.confronto import cb_confronto, cmd_confronto, cmd_confronto_carriera
from shared.rendimento import PATTERN, cb_rendimento, cmd_rendimento, cmd_rendimento_carriera
from shared.situazione import cb_rendimento_situazione, cmd_rendimento_situazione


def get_handlers() -> list:
    return [CommandHandler("rendimento", cmd_rendimento), CommandHandler("rendimento_carriera", cmd_rendimento_carriera),
            CallbackQueryHandler(cb_rendimento, pattern=PATTERN),
            CommandHandler("confronto", cmd_confronto, block=False),                  # v7.4.3
            CommandHandler("confronto_carriera", cmd_confronto_carriera, block=False),
            CallbackQueryHandler(cb_confronto, pattern=r"^cf:[01]:\d+$"),             # v7.25.0: i «Quale?» dei due nomi
            CommandHandler("rendimento_situazione", cmd_rendimento_situazione, block=False),   # v7.20.0
            CallbackQueryHandler(cb_rendimento_situazione, pattern=r"^sit:\d+$")]

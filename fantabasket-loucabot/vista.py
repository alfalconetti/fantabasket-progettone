"""
Le viste del bot principale anche in loucabot (v7.21.0, Luca 21/11: «loucabot ha tutta la parte di visualizzazione,
il main resta il bot per agire sul team e sulla lega»): /roster, /assets, /pdf_roster, /pdf_assets, /pick, /pick_lega,
/carriera, /team_diff, /trova_trade e /penalita (solo da vedere).

Il codice è quello del bot principale, montato in sola lettura in /main (docker-compose.yml, come /louca per klra):
stesse immagini, stessi argomenti, una modifica vale per tutti e due. Nei gruppi risponde solo loucabot; il main
li tiene in privato (VISTE in fantabasket-main/comandi.py).

È il modo di gestire il codice legacy (Luca, 21/11): le viste già scritte nel principale, riusate così come sono,
senza refactor. Le viste nuove (draft, rinnovi…) vanno scritte direttamente in shared/, come /player e /rendimento.

Come si caricano: /main in fondo a sys.path (database, settings, teams, utils, typst_compila… non esistono in
loucabot); il pacchetto handlers del main si raggiunge dal modulo handlers.py di loucabot, a cui si dà come
__path__ la cartella handlers del main (così funzionano anche i loro «from handlers import carriera» interni).
"""
import logging
import os
import sys

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)
MAIN = os.environ.get("MAIN_DIR", "/main")
COMANDI = ["roster", "assets", "pick", "pick_lega", "carriera", "team_diff", "trova_trade", "penalita",
           "pdf_roster", "pdf_assets"]
_pronto = False


def prepara() -> None:
    """Rende importabile il codice del main (una volta) e apre il suo pool di connessioni."""
    global _pronto
    if _pronto:
        return
    if not os.path.isdir(os.path.join(MAIN, "handlers")):
        raise RuntimeError(f"codice del bot principale non trovato in {MAIN} (volume /main in docker-compose.yml)")
    if MAIN not in sys.path:
        sys.path.append(MAIN)
    import handlers as H                                  # il modulo di loucabot
    # handlers.roster & co. sono quelli del main: il modulo di loucabot diventa anche un pacchetto (attributo nuovo,
    # di proposito: setattr, non un nome esistente da sostituire)
    setattr(H, "__path__", [os.path.join(MAIN, "handlers")])
    import database
    if getattr(database, "_pool", None) is None:
        database.init_db()
    _pronto = True


async def cmd_penalita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/penalita [SQUADRA]: le penalità di una squadra, da vedere (assegnarle e revocarle si fa nel bot principale)."""
    import teams as tm
    from handlers import penalita as PE
    msg = update.effective_message
    team = tm.get_team_by_query(" ".join(context.args)) if context.args else tm.get_team_by_gm(update.effective_user.id)
    if not team:
        from shared import esempi as ES
        await msg.reply_text("Squadra non trovata." if context.args else f"Uso: /penalita SQUADRA (es. /penalita {ES.squadra()})")
        return
    await msg.reply_text(PE.testo_squadra(team["id"]), parse_mode="HTML")


def get_handlers() -> list:
    """Gli handler, o [] se il codice del main non c'è (loucabot parte lo stesso, senza queste viste)."""
    try:
        prepara()
        from handlers import carriera as CA, pick as PK, roster as RO, team_diff as TD, trova_trade as TT
    except Exception as e:
        logger.error("Viste del bot principale non disponibili: %s", e)
        return []
    return [CommandHandler("roster", RO.cmd_roster), CommandHandler("assets", RO.cmd_assets),
            CommandHandler("pdf_roster", RO.cmd_pdf_roster, block=False),
            CommandHandler("pdf_assets", RO.cmd_pdf_assets, block=False),
            CommandHandler("pick", PK.cmd_pick), CommandHandler("pick_lega", PK.cmd_pick_lega),
            CommandHandler("carriera", CA.cmd_carriera), CallbackQueryHandler(CA.cb_carriera, pattern=r"^car:\d+$"),
            CommandHandler("team_diff", TD.cmd_team_diff),
            CommandHandler("trova_trade", TT.cmd_trova_trade), CallbackQueryHandler(TT.cb_trova_trade, pattern=r"^ttr:\d+$"),
            CallbackQueryHandler(TT.cb_trova_giocatore, pattern=r"^ttg:\d+$"),             # v7.25.0
            CommandHandler("penalita", cmd_penalita)]

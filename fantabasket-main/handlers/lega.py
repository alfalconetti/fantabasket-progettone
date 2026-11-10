"""
/player, /status, /calendario (v7.3.0) e /rendimento, /rendimento_carriera (v7.4.0), /confronto, /confronto_carriera (v7.4.3), /giocatori (v7.5.0) anche nel bot principale (v7.3.0, Luca 09/11): stesso codice di loucabot
(shared/giocatore.py, shared/status_squadra.py, shared/calendario_squadra.py), stesse risposte.

Solo in privato: nei gruppi questi comandi sono di loucabot (risponde lui, e qui non compaiono nemmeno nel menu dei
gruppi), così nessun messaggio arriva due volte. /calendario senza squadra vale per la squadra di chi scrive; chi
non è GM deve scrivere la squadra (la giornata intera, come immagine, è /giornata di loucabot).
"""
from telegram.ext import CallbackQueryHandler, CommandHandler, filters

from shared import calendario_squadra as CS
from shared import giocatore as G
from shared import lettura as L
from shared import rendimento as R
from shared import confronto as CF
from shared import elenco_giocatori as EG
from shared.status_squadra import cmd_status

cmd_player, manda, cb_player = G.handlers(G.scheda)

PIEDE = "/calendario N [SQUADRA] per un'altra giornata o squadra · tutte le partite e la classifica su loucabot"


async def cmd_calendario(update, context):
    msg = update.effective_message
    s = L.stagione()
    n, testo = CS.argomenti(context.args)
    g = CS.giornata(s, n) if n else CS.corrente(s)
    if not g:
        await msg.reply_text("Nessuna giornata in calendario." if not CS.giornate(s) else f"La giornata {n} non c'è.")
        return
    if testo:
        from shared.squadre import cerca_squadra
        team = cerca_squadra(testo, L.squadre())
        if not team:
            await msg.reply_text(f"Nessuna squadra trovata con «{testo}».")
            return
    else:
        team = L.squadra_del_gm(update.effective_user.id)
        if not team:
            await msg.reply_text("Uso: /calendario [N] SQUADRA (senza squadra vale la tua, se sei un GM).")
            return
    await msg.reply_text(CS.testo_squadra(s, g, team, PIEDE), parse_mode="HTML")


# fuori dal menu del gruppo admin, come i comandi @solo_privato (comandi.trova_solo_privato)
for _f in (cmd_player, cmd_status, cmd_calendario, R.cmd_rendimento, R.cmd_rendimento_carriera, CF.cmd_confronto, CF.cmd_confronto_carriera,
           EG.cmd_giocatori):
    try:
        _f._solo_privato = True
    except AttributeError:
        pass


def get_handlers() -> list:
    privato = filters.ChatType.PRIVATE
    return [CommandHandler("player", cmd_player, filters=privato),
            CallbackQueryHandler(cb_player, pattern=r"^pl:\d+$"),
            CommandHandler("status", cmd_status, filters=privato),
            CommandHandler("calendario", cmd_calendario, filters=privato),
            CommandHandler("rendimento", R.cmd_rendimento, filters=privato),             # v7.4.0
            CommandHandler("rendimento_carriera", R.cmd_rendimento_carriera, filters=privato),
            CallbackQueryHandler(R.cb_rendimento, pattern=R.PATTERN),
            CommandHandler("confronto", CF.cmd_confronto, filters=privato, block=False),     # v7.4.3
            CommandHandler("confronto_carriera", CF.cmd_confronto_carriera, filters=privato, block=False),
            CommandHandler("giocatori", EG.cmd_giocatori, filters=privato)]                  # v7.5.0

"""
Trade: registrazione di comandi, bottoni e conversazioni (get_handlers) e /annulla_trade.

Il codice è diviso per fase della trade (v3.13.0; prima stava tutto in questo file):
  trade_comune.py    stati, riepilogo, tastiere, permessi sulla bozza, annuncio, notifiche
  trade_crea.py      /build_trade e /import_trade: dalle squadre al riepilogo, nota, invio
  trade_modifica.py  /edit_trade e "Modifica" dal riepilogo
  trade_voto.py      proposta ai GM, voti, rifiuto, approvazione degli admin
  trade_esegui.py    scrittura della trade approvata (_scrivi_trade), /annulla_trade_admin
  trade_liste.py     /my_trades, /mie_trade, /bozze_trade
  trade_parser.py    lettura di una trade scritta a testo
Validazione (cap, roster, ruoli, RFA…): validators/trade.py.
"""
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler

import database as db
from settings import solo_privato
from handlers.trade_comune import (
    EDIT_AGGIUNGI_ITEM, EDIT_AGGIUNGI_TIPO, EDIT_MENU, IMPORT_ATTENDI_TESTO, TRADE_ASSEGNA_DEST,
    TRADE_ASSET_DIRITTI, TRADE_ASSET_GIOCATORI, TRADE_ASSET_MENU, TRADE_ASSET_PICK, TRADE_NOTA,
    TRADE_N_SQUADRE, TRADE_RIEPILOGO, TRADE_RIFIUTO_NOTA, TRADE_SELEZIONA_SQUADRE,
)
from handlers.trade_esegui import cmd_annulla_trade_admin
from handlers.trade_voto import (
    cb_admin_trade, cb_rifiuta_conf, cb_rifiuto_nota_ricevi, cb_trade_vedi, cb_voto_gm,
)
from handlers.trade_crea import (
    cb_assegna_dest, cb_asset_menu, cb_modifica_da_riepilogo, cb_n_squadre, cb_nota_apri,
    cb_nota_ricevi, cb_salva_bozza, cb_seleziona_squadra, cb_send_trade, cb_toggle_diritti,
    cb_toggle_giocatore, cb_toggle_pick, cb_trade_del, cmd_import, cmd_trade,
    import_ricevi_testo,
)
from handlers.trade_modifica import (
    cb_edit_add, cb_edit_back, cb_edit_done, cb_edit_item, cb_edit_rm, cb_edit_tipo,
    cmd_edit_trade,
)
from handlers.trade_liste import cb_my_trades, cmd_mie_trade, cmd_my_trades


# ── /annulla_trade ─────────────────────────────────────────────────────────────

@solo_privato
async def cmd_annulla_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    trade_id = context.user_data.pop("trade_id", None)
    if trade_id:
        # Solo una bozza: una trade già inviata/approvata non va mai toccata da qui
        db.cambia_stato_trade(trade_id, ("bozza",), "annullata")
    context.user_data.pop("trade_squadre_ordine", None)
    context.user_data.pop("trade_squadre_corrente_idx", None)
    await update.effective_message.reply_text("Trade annullata.")
    return ConversationHandler.END


# ── registrazione handlers ──────────────────────────────────────────────────────

def get_handlers() -> list:
    from telegram.ext import MessageHandler, filters

    conv_build = ConversationHandler(
        entry_points=[
            CommandHandler("build_trade", cmd_trade),
            CallbackQueryHandler(cmd_trade, pattern=r"^menu_trade_build$"),
        ],
        states={
            TRADE_N_SQUADRE: [
                CallbackQueryHandler(cb_n_squadre, pattern=r"^trade_n:\d$"),
            ],
            TRADE_SELEZIONA_SQUADRE: [
                CallbackQueryHandler(cb_seleziona_squadra, pattern=r"^trade_sq:.+$"),
            ],
            TRADE_ASSET_MENU: [
                CallbackQueryHandler(cb_asset_menu, pattern=r"^trade_am:[gpod].*$|^trade_am:ok:.*$|^trade_am:back:.*$"),
            ],
            TRADE_ASSET_GIOCATORI: [
                CallbackQueryHandler(cb_toggle_giocatore, pattern=r"^trade_gi:.+$"),
                CallbackQueryHandler(cb_asset_menu,       pattern=r"^trade_am:.+$"),
            ],
            TRADE_ASSET_PICK: [
                CallbackQueryHandler(cb_toggle_pick,  pattern=r"^trade_pi:.+$"),
                CallbackQueryHandler(cb_asset_menu,   pattern=r"^trade_am:.+$"),
            ],
            TRADE_ASSET_DIRITTI: [
                CallbackQueryHandler(cb_toggle_diritti, pattern=r"^trade_di:.+$"),
                CallbackQueryHandler(cb_asset_menu,     pattern=r"^trade_am:.+$"),
            ],
            TRADE_ASSEGNA_DEST: [
                CallbackQueryHandler(cb_assegna_dest, pattern=r"^trade_dest:\d+:.+$"),
            ],
            TRADE_NOTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cb_nota_ricevi),
                CommandHandler("salta", cb_nota_ricevi),
                CommandHandler("annulla", cmd_annulla_trade),
            ],
            TRADE_RIEPILOGO: [
                CallbackQueryHandler(cb_send_trade,           pattern=r"^trade_send:.+$"),
                CallbackQueryHandler(cb_nota_apri,            pattern=r"^trade_nota:\d+$"),
                CallbackQueryHandler(cb_salva_bozza,          pattern=r"^trade_salva:\d+$"),
                CallbackQueryHandler(cb_trade_del,            pattern=r"^trade_del:\d+$"),
                CallbackQueryHandler(cb_modifica_da_riepilogo,pattern=r"^edit_back:\d+$"),
            ],
            EDIT_MENU: [
                CallbackQueryHandler(cb_edit_rm,   pattern=r"^edit_rm:\d+:\d+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
                CallbackQueryHandler(cb_edit_done, pattern=r"^edit_done:\d+$"),
                CallbackQueryHandler(cb_edit_back, pattern=r"^edit_back:\d+$"),
            ],
            EDIT_AGGIUNGI_TIPO: [
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gpd]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
            ],
            EDIT_AGGIUNGI_ITEM: [
                CallbackQueryHandler(cb_edit_item, pattern=r"^edit_item:[gpd]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gpd]:\d+:.+$"),
            ],
        },
        fallbacks=[
            CommandHandler("annulla_trade", cmd_annulla_trade),
            CommandHandler("annulla",       cmd_annulla_trade),
        ],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )

    conv_import = ConversationHandler(
        entry_points=[
            CommandHandler("import_trade", cmd_import),
            CallbackQueryHandler(cmd_import, pattern=r"^menu_trade_import$"),
        ],
        states={
            IMPORT_ATTENDI_TESTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, import_ricevi_testo),
            ],
            TRADE_RIEPILOGO: [
                CallbackQueryHandler(cb_send_trade,            pattern=r"^trade_send:.+$"),
                CallbackQueryHandler(cb_nota_apri,             pattern=r"^trade_nota:\d+$"),
                CallbackQueryHandler(cb_salva_bozza,           pattern=r"^trade_salva:\d+$"),
                CallbackQueryHandler(cb_trade_del,             pattern=r"^trade_del:\d+$"),
                CallbackQueryHandler(cb_modifica_da_riepilogo, pattern=r"^edit_back:\d+$"),
            ],
            TRADE_NOTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cb_nota_ricevi),
                CommandHandler("salta", cb_nota_ricevi),
                CommandHandler("annulla", cmd_annulla_trade),
            ],
        },
        fallbacks=[
            CommandHandler("annulla_trade", cmd_annulla_trade),
            CommandHandler("annulla",       cmd_annulla_trade),
        ],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )

    conv_edit = ConversationHandler(
        entry_points=[
            CommandHandler("edit_trade", cmd_edit_trade),
            CallbackQueryHandler(cb_edit_back, pattern=r"^edit_back:\d+$"),
        ],
        states={
            EDIT_MENU: [
                CallbackQueryHandler(cb_edit_rm,   pattern=r"^edit_rm:\d+:\d+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
                CallbackQueryHandler(cb_edit_done, pattern=r"^edit_done:\d+$"),
            ],
            EDIT_AGGIUNGI_TIPO: [
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gpd]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
            ],
            EDIT_AGGIUNGI_ITEM: [
                CallbackQueryHandler(cb_edit_item, pattern=r"^edit_item:[gpd]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gpd]:\d+:.+$"),
            ],
            # dopo "Fatto": destinatari (trade a 3-4) e riepilogo, come nel builder
            TRADE_ASSEGNA_DEST: [
                CallbackQueryHandler(cb_assegna_dest, pattern=r"^trade_dest:\d+:.+$"),
            ],
            TRADE_RIEPILOGO: [
                CallbackQueryHandler(cb_send_trade,            pattern=r"^trade_send:.+$"),
                CallbackQueryHandler(cb_nota_apri,             pattern=r"^trade_nota:\d+$"),
                CallbackQueryHandler(cb_salva_bozza,           pattern=r"^trade_salva:\d+$"),
                CallbackQueryHandler(cb_trade_del,             pattern=r"^trade_del:\d+$"),
                CallbackQueryHandler(cb_modifica_da_riepilogo, pattern=r"^edit_back:\d+$"),
            ],
            TRADE_NOTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cb_nota_ricevi),
                CommandHandler("salta", cb_nota_ricevi),
            ],
        },
        fallbacks=[
            CommandHandler("annulla_trade", cmd_annulla_trade),
            CallbackQueryHandler(cb_edit_back, pattern=r"^edit_back:\d+$"),
        ],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )

    conv_rifiuto = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_rifiuta_conf, pattern=r"^trade_rifiuta_conf:.+$"),
        ],
        states={
            TRADE_RIFIUTO_NOTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cb_rifiuto_nota_ricevi),
                CommandHandler("salta", cb_rifiuto_nota_ricevi),
                CommandHandler("annulla", cmd_annulla_trade),
            ],
        },
        fallbacks=[
            CommandHandler("annulla", cmd_annulla_trade),
        ],
        per_user=True,
        per_chat=True,
        conversation_timeout=120,
    )

    return [
        conv_build,
        conv_rifiuto,
        conv_import,
        conv_edit,
        CommandHandler("my_trades",          cmd_my_trades),
        CommandHandler("mie_trade",          cmd_my_trades),
        CallbackQueryHandler(cb_my_trades,   pattern=r"^mt:(?:l|[vrc]:\d+)$"),
        CommandHandler("bozze_trade",         cmd_mie_trade),
        CommandHandler("annulla_trade_admin", cmd_annulla_trade_admin),
        CallbackQueryHandler(cb_trade_vedi,  pattern=r"^trade_vedi:\d+$"),
        CallbackQueryHandler(cb_voto_gm,     pattern=r"^trade_voto:.+$"),
        CallbackQueryHandler(cb_admin_trade, pattern=r"^trade_admin:.+$"),
        CallbackQueryHandler(cb_edit_back,   pattern=r"^edit_back:\d+$"),
        CallbackQueryHandler(cb_trade_del,   pattern=r"^trade_del:\d+$"),  # fallback fuori conv
        CallbackQueryHandler(cb_salva_bozza,  pattern=r"^trade_salva:\d+$"),  # fallback fuori conv
        CallbackQueryHandler(cb_send_trade,   pattern=r"^trade_send:.+$"),  # fallback fuori conv
    ]

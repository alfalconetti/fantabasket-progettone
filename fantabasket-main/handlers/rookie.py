"""
Attivazione diritti 2nd pick:
  /attiva_diritti → lista diritti 2nd disponibili → seleziona → conferma importo e anni → firma
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters,
)
from datetime import datetime, timezone

import database as db
import settings
from settings import solo_privato, richiede_fase, FASI_TRADE_APERTE
import teams as tm

logger = logging.getLogger(__name__)

SCEGLI_ROOKIE, INSERISCI_IMPORTO_R, SCEGLI_ANNI_R, CONFERMA_R = range(4)
_ANNULLA_HINT = "\n<i>Per annullare: /annulla</i>"


@solo_privato
@richiede_fase(*FASI_TRADE_APERTE, msg="❌ L'attivazione dei diritti rookie non è disponibile in questa fase.")
async def cmd_attiva_diritti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END

    diritti = db.get_diritti_2nd_team(team["id"])
    if not diritti:
        await update.effective_message.reply_text("Non hai diritti di 2nd pick da attivare.")
        return ConversationHandler.END

    bottoni = [
        [InlineKeyboardButton(
            f"{r['nome_common']} (#{r['pick_numero']} {r['anno_draft']})",
            callback_data=f"att_r:{r['id']}"
        )]
        for r in diritti
    ]
    await update.effective_message.reply_text(
        "Seleziona il rookie da firmare:" + _ANNULLA_HINT,
        reply_markup=InlineKeyboardMarkup(bottoni),
    )
    return SCEGLI_ROOKIE


async def cb_scegli_rookie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rookie_id = int(query.data.split(":")[1])
    rookie    = db.get_rookie(rookie_id)
    if not rookie:
        await query.edit_message_text("❌ Rookie non trovato.")
        return ConversationHandler.END

    context.user_data["att_rookie_id"] = rookie_id
    giocatore = db.get_giocatore(rookie["giocatore_id"])

    # Contratto rookie scale da settings
    s   = settings.get()
    rs  = s["rookie_scale"]
    pic = rookie["pick_numero"]
    slot = None
    for fascia, valori in rs.items():
        limiti = fascia.split("-")
        lo = int(limiti[0])
        hi = int(limiti[-1])
        if lo <= pic <= hi:
            anno_idx = rookie["anni_scala"]  # 0=primo anno, 1=secondo...
            slot = valori[anno_idx] if anno_idx < len(valori) else None
            break

    if slot:
        imp_base = slot["imp"]
        anni_base = slot["anni"]
        context.user_data["att_imp_base"]  = imp_base
        context.user_data["att_anni_base"] = anni_base
        suggerimento = f"\n<i>Rookie scale: {imp_base}M × {anni_base} anni</i>"
    else:
        suggerimento = ""

    await query.edit_message_text(
        f"🏀 <b>{giocatore['nome_common']}</b>\n"
        f"Pick #{pic} — Draft {rookie['anno_draft']}\n{suggerimento}\n\n"
        f"Inserisci l'importo del contratto (minimo 1M):" + _ANNULLA_HINT,
        parse_mode="HTML",
    )
    return INSERISCI_IMPORTO_R


async def inserisci_importo_r(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    testo = update.effective_message.text.strip()
    if not testo.isdigit():
        await update.effective_message.reply_text(
            "❌ Inserisci un numero intero." + _ANNULLA_HINT, parse_mode="HTML"
        )
        return INSERISCI_IMPORTO_R

    importo = int(testo)
    if importo < 1:
        await update.effective_message.reply_text("❌ Minimo 1M." + _ANNULLA_HINT, parse_mode="HTML")
        return INSERISCI_IMPORTO_R

    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    cap_occ = db.cap_occupato_team(team["id"], settings.stagione_corrente())
    cap_lib = settings.cap_massimo() - cap_occ
    if cap_lib < importo:
        await update.effective_message.reply_text(
            f"❌ Cap insufficiente. Libero: {cap_lib}M." + _ANNULLA_HINT, parse_mode="HTML"
        )
        return INSERISCI_IMPORTO_R

    context.user_data["att_importo"] = importo
    anni_min = settings.anni_minimi_contratto(importo)

    # Per i rookie firmati tramite diritti: obbligatoriamente x1
    anni     = 1
    context.user_data["att_anni"] = anni

    # Conferma
    rookie   = db.get_rookie(context.user_data["att_rookie_id"])
    giocatore = db.get_giocatore(rookie["giocatore_id"])

    await update.effective_message.reply_text(
        f"🏀 Confermi firma?\n\n"
        f"Giocatore: <b>{giocatore['nome_common']}</b>\n"
        f"Contratto: <b>{importo}M × {anni} anno</b>\n"
        f"<i>(I rookie via diritti 2nd vengono firmati x1)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Conferma", callback_data="att_r_ok"),
            InlineKeyboardButton("❌ Annulla",  callback_data="att_r_no"),
        ]]),
    )
    return CONFERMA_R


async def cb_conferma_firma_rookie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user  = update.effective_user
    team  = tm.get_team_by_gm(user.id)

    rookie_id = context.user_data.pop("att_rookie_id", None)
    importo   = context.user_data.pop("att_importo", None)
    anni      = context.user_data.pop("att_anni", 1)
    context.user_data.pop("att_imp_base", None)
    context.user_data.pop("att_anni_base", None)

    rookie    = db.get_rookie(rookie_id)
    giocatore = db.get_giocatore(rookie["giocatore_id"])
    stagione  = settings.stagione_corrente()
    now       = datetime.now(timezone.utc)

    # Crea contratto
    from database import _qval, _q
    contratto_id = _qval(
        "INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) "
        "VALUES (%s, %s, %s, %s, %s, 'rookie') RETURNING id",
        (rookie["giocatore_id"], team["id"], importo, anni, stagione)
    )

    # Segna rookie come firmato e imposta anno_firma
    _q(
        "UPDATE rookie SET firmato = TRUE, anno_firma = %s WHERE id = %s",
        (stagione, rookie_id)
    )

    # Registra transazione
    db.registra_transazione(
        "rookie_firma", rookie["giocatore_id"], None, team["id"],
        stagione, contratto_id=contratto_id, rookie_scale=True,
        note=f"Attivazione diritti 2nd — pick #{rookie['pick_numero']} {rookie['anno_draft']}"
    )

    await query.edit_message_text(
        f"✅ <b>{giocatore['nome_common']}</b> firmato!\n"
        f"Contratto: <b>{importo}M × {anni} anno</b>\n\n"
        f"⚠️ Ricordati di comunicare il ruolo entro 48h.",
        parse_mode="HTML",
    )

    # Annuncio canale principale
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        testo_canale = (
            f"🏀 <b>{team.get('gm_nome', team['nome'])}</b> attiva i diritti di "
            f"<b>{giocatore['nome_common']}</b>\n"
            f"📋 {importo}M × {anni} {'anno' if anni == 1 else 'anni'} "
            f"(#{rookie['pick_numero']} {rookie['anno_draft']})"
        )
        try:
            await context.bot.send_message(
                chat_id=main_channel,
                text=testo_canale,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Annuncio canale attiva_diritti fallito: %s", e)

    logger.info("Rookie firma: team=%s giocatore=%d importo=%d",
                team["id"], rookie["giocatore_id"], importo)

    # Sync GAS Sheets
    try:
        import gas_client
        gas_client.sync_after_rookie(team["id"])
    except Exception as e:
        logger.warning("GAS sync rookie fallito: %s", e)
    return ConversationHandler.END


async def cb_annulla_firma_rookie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    for k in ("att_rookie_id", "att_importo", "att_anni", "att_imp_base", "att_anni_base"):
        context.user_data.pop(k, None)
    await query.edit_message_text("Firma annullata.")
    return ConversationHandler.END


async def cmd_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Operazione annullata.")
    return ConversationHandler.END


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("attiva_diritti", cmd_attiva_diritti)],
        states={
            SCEGLI_ROOKIE: [
                CallbackQueryHandler(cb_scegli_rookie, pattern=r"^att_r:\d+$"),
            ],
            INSERISCI_IMPORTO_R: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, inserisci_importo_r),
            ],
            CONFERMA_R: [
                CallbackQueryHandler(cb_conferma_firma_rookie, pattern=r"^att_r_ok$"),
                CallbackQueryHandler(cb_annulla_firma_rookie,  pattern=r"^att_r_no$"),
            ],
        },
        fallbacks=[CommandHandler("annulla", cmd_annulla)],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )
    return [conv]

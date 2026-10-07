"""
Attivazione diritti 2nd pick:
  /attiva_diritti → lista diritti 2nd disponibili → seleziona → conferma contratto scale → firma

Il contratto (importo e anni) è predefinito dalla rookie scale in settings.json.
Non viene chiesto importo libero — solo conferma o annulla.
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
    """Seleziona rookie → mostra direttamente il contratto da scala e chiede conferma."""
    query = update.callback_query
    await query.answer()
    rookie_id = int(query.data.split(":")[1])
    rookie    = db.get_rookie(rookie_id)
    if not rookie:
        await query.edit_message_text("❌ Rookie non trovato.")
        return ConversationHandler.END
    team = tm.get_team_by_gm(query.from_user.id)
    if (not team or rookie["team_id"] != team["id"] or rookie.get("firmato")
            or rookie.get("diritti_scaduti")):
        await query.edit_message_text("❌ Diritti non disponibili per la tua squadra.")
        return ConversationHandler.END

    context.user_data["att_rookie_id"] = rookie_id
    giocatore = db.get_giocatore(rookie["giocatore_id"])

    # Contratto predefinito dalla rookie scale
    s   = settings.get()
    rs  = s.get("rookie_scale", {})
    pic = rookie["pick_numero"]
    slot = None
    for fascia, valori in rs.items():
        limiti = fascia.split("-")
        lo = int(limiti[0])
        hi = int(limiti[-1])
        if lo <= pic <= hi:
            # Attivazione diritti: sempre anno I della scala (idx 0)
            anno_idx = 0
            slot = valori[anno_idx] if anno_idx < len(valori) else None
            break

    if not slot:
        # Fascia non trovata: fallback a input manuale (non dovrebbe succedere)
        await query.edit_message_text(
            f"🏀 <b>{giocatore['nome_common']}</b>\n"
            f"Pick #{pic} — Draft {rookie['anno_draft']}\n\n"
            f"⚠️ Contratto non trovato nella scala. Inserisci l'importo manualmente (minimo 1M):"
            + _ANNULLA_HINT,
            parse_mode="HTML",
        )
        return INSERISCI_IMPORTO_R

    importo = slot["imp"]
    anni    = slot["anni"]
    context.user_data["att_importo"]   = importo
    context.user_data["att_anni"]      = anni
    context.user_data["att_imp_base"]  = importo
    context.user_data["att_anni_base"] = anni

    anni_str = "anno" if anni == 1 else "anni"
    await query.edit_message_text(
        f"🏀 <b>{giocatore['nome_common']}</b>\n"
        f"Pick #{pic} — Draft {rookie['anno_draft']}\n\n"
        f"📋 Contratto dalla rookie scale:\n"
        f"<b>{importo}M × {anni} {anni_str}</b>\n\n"
        f"Confermi la firma?" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Conferma", callback_data="att_r_ok"),
            InlineKeyboardButton("❌ Annulla",  callback_data="att_r_no"),
        ]]),
    )
    return CONFERMA_R


async def inserisci_importo_r(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fallback: input manuale importo (solo se slot non trovato nella scala)."""
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

    context.user_data["att_importo"] = importo
    anni = 1  # diritti 2nd sempre x1 se fuori scala
    context.user_data["att_anni"] = anni

    rookie    = db.get_rookie(context.user_data["att_rookie_id"])
    giocatore = db.get_giocatore(rookie["giocatore_id"])

    await update.effective_message.reply_text(
        f"🏀 Confermi firma?\n\n"
        f"Giocatore: <b>{giocatore['nome_common']}</b>\n"
        f"Contratto: <b>{importo}M × {anni} anno</b>",
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

    if rookie_id is None or importo is None:
        await query.edit_message_text("❌ Sessione scaduta. Riprova con /attiva_diritti.")
        return ConversationHandler.END

    # Check cap (qui, non al momento dell'input)
    stagione = settings.stagione_corrente()
    cap_occ  = db.cap_occupato_team(team["id"], stagione)
    cap_lib  = settings.cap_massimo() - cap_occ
    if cap_lib < importo:
        await query.edit_message_text(
            f"❌ Cap insufficiente. Libero: {cap_lib}M — contratto scale: {importo}M.\n"
            f"Contatta un admin se ritieni ci sia un errore."
        )
        return ConversationHandler.END

    rookie    = db.get_rookie(rookie_id)
    giocatore = db.get_giocatore(rookie["giocatore_id"])
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

    anni_str = "anno" if anni == 1 else "anni"
    await query.edit_message_text(
        f"✅ <b>{giocatore['nome_common']}</b> firmato!\n"
        f"Contratto: <b>{importo}M × {anni} {anni_str}</b> (rookie scale)\n\n"
        f"⚠️ Ricordati di comunicare il ruolo entro 48h.",
        parse_mode="HTML",
    )

    # Annuncio canale principale
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        testo_canale = (
            f"🏀 <b>{team.get('gm_nome', team['nome'])}</b> attiva i diritti di "
            f"<b>{giocatore['nome_common']}</b>\n"
            f"📋 {importo}M × {anni} {anni_str} "
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


# ── Scadenza diritti 2nd (bottone dal job check_scadenza_diritti) ─────────────

async def cb_scadi_diritti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conferma admin: marca come scaduti i diritti 2nd al secondo anno,
    poi annuncia nel gruppo admin e sul canale principale."""
    query = update.callback_query
    user  = query.from_user
    if user.id not in [int(a) for a in settings.admin_ids()]:
        await query.answer("⛔ Solo gli admin possono confermare.", show_alert=True)
        return

    anno = int(query.data.split(":")[1])
    info = db.info_scadenza_diritti()
    if not info or anno != info["anno_draft"]:
        await query.answer("❌ Anno non valido per la scadenza di questa stagione.", show_alert=True)
        return
    if info["giorni_mancanti"] > 0:
        await query.answer(
            f"⏳ I diritti {anno} scadono il {info['scadenza'].strftime('%d/%m/%Y')}: "
            f"non ancora confermabile.", show_alert=True)
        return

    await query.answer()
    scaduti = db.scadi_diritti_anno(anno)
    admin_nome = user.first_name or user.username or str(user.id)

    if not scaduti:
        await query.edit_message_text(
            f"ℹ️ Nessun diritto 2nd {anno} da far scadere (già confermato?)."
        )
        return

    # Elenco per squadra
    per_team: dict[str, list[str]] = {}
    for r in scaduti:
        per_team.setdefault(r["team_id"], []).append(r["nome_common"])
    righe = []
    for team_id, nomi in sorted(per_team.items()):
        t = tm.get_team_by_id(team_id)
        righe.append(f"• <b>{t['nome'] if t else team_id}</b>: {', '.join(sorted(nomi))}")
    elenco = "\n".join(righe)

    await query.edit_message_text(
        f"✅ <b>Diritti 2nd {anno} scaduti</b> — confermato da {admin_nome}.\n"
        f"{len(scaduti)} giocatori tornano free agent:\n\n{elenco}",
        parse_mode="HTML",
    )

    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        try:
            await context.bot.send_message(
                chat_id=main_channel,
                text=(f"⌛ <b>Scadenza diritti 2nd round {anno}</b>\n\n"
                      f"I seguenti giocatori non firmati diventano free agent:\n\n{elenco}"),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Annuncio canale scadenza diritti fallito: %s", e)

    logger.info("Diritti 2nd %d scaduti (%d) da %s", anno, len(scaduti), admin_nome)

    try:
        import gas_client
        gas_client.sync_scelte()
    except Exception as e:
        logger.warning("GAS sync scelte dopo scadenza diritti fallito: %s", e)


def get_handlers() -> list:
    conv = ConversationHandler(
        # Anche la scelta del rookie è un ingresso: la lista può arrivare dal /menu,
        # che la mostra senza avviare la conversazione
        entry_points=[CommandHandler("attiva_diritti", cmd_attiva_diritti),
                      CallbackQueryHandler(cb_scegli_rookie, pattern=r"^att_r:\d+$")],
        states={
            SCEGLI_ROOKIE: [
                CallbackQueryHandler(cb_scegli_rookie, pattern=r"^att_r:\d+$"),
            ],
            INSERISCI_IMPORTO_R: [
                # Fallback manuale (solo se slot non trovato nella scala)
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
        per_message=False,
        conversation_timeout=300,
    )
    return [conv, CallbackQueryHandler(cb_scadi_diritti, pattern=r"^scadi_diritti:\d+$")]

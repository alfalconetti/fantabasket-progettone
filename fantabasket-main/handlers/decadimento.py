"""
Handler per il decadimento contratti.
Casi: ritiro, firma in altra lega, giocatore svincolato da lungo tempo.
Il contratto viene annullato senza impatto sui tagli gratuiti.
Flusso GM: richiesta → gruppo admin → approvazione → DB + canale
Flusso admin: diretto da /admin_menu
"""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler
)

import database as db
import teams as tm
import settings
from settings import solo_privato, richiede_fase, FASI_TRADE_APERTE
from utils import format_dt, ROME
from datetime import datetime

logger = logging.getLogger(__name__)

# Stati ConversationHandler
DEC_SQUADRA, DEC_GIOCATORE, DEC_MOTIVO = range(50, 53)

MOTIVI = {
    "ritiro":    "🏁 Ritiro dal basket",
    "altra_lega": "🌍 Firma in altra lega",
    "altro":     "📝 Altro",
}


# ── Flusso GM ──────────────────────────────────────────────────────────────────

@solo_privato
async def cmd_decadimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END

    roster = db.get_roster_team(team["id"])
    if not roster:
        await update.effective_message.reply_text("Il tuo roster è vuoto.")
        return ConversationHandler.END

    context.user_data["dec_team_id"] = team["id"]
    stagione = settings.stagione_corrente()
    bottoni = []
    for r in sorted(roster, key=lambda x: -x["importo"]):
        anni = _anni_residui(r, stagione)
        label = f"{r['nome_common']} {r['importo']}x{anni}"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"dec_giocat:{r['giocatore_id']}")])
    bottoni.append([InlineKeyboardButton("❌ Annulla", callback_data="dec_annulla")])

    await update.effective_message.reply_text(
        "⚠️ <b>Decadimento contratto</b>\n\n"
        "Seleziona il giocatore il cui contratto è decaduto "
        "(ritiro, firma in altra lega, ecc.).\n\n"
        "<i>Il contratto verrà annullato senza impatto sui tagli gratuiti.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )
    return DEC_GIOCATORE


async def cb_dec_giocatore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split(":")[1])
    context.user_data["dec_giocatore_id"] = gid

    giocatore = db.get_giocatore(gid)
    context.user_data["dec_giocatore_nome"] = giocatore["nome_common"]

    bottoni = [[InlineKeyboardButton(label, callback_data=f"dec_motivo:{key}")]
               for key, label in MOTIVI.items()]
    bottoni.append([InlineKeyboardButton("❌ Annulla", callback_data="dec_annulla")])

    await query.edit_message_text(
        f"<b>{giocatore['nome_common']}</b> — seleziona il motivo:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )
    return DEC_MOTIVO


async def cb_dec_motivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    motivo_key  = query.data.split(":")[1]
    motivo_label = MOTIVI.get(motivo_key, motivo_key)

    team_id  = context.user_data["dec_team_id"]
    gid      = context.user_data["dec_giocatore_id"]
    nome     = context.user_data["dec_giocatore_nome"]
    team     = tm.get_team_by_id(team_id)
    user     = update.effective_user
    gm_tag   = f"@{user.username}" if user.username else user.first_name

    await query.edit_message_text(
        f"⏳ Richiesta inviata al gruppo admin.\n\n"
        f"Giocatore: <b>{nome}</b>\n"
        f"Motivo: {motivo_label}",
        parse_mode="HTML",
    )

    # Notifica gruppo admin
    admin_group_id = settings.load_globals().get("admin_group_id")
    if admin_group_id:
        testo = (
            f"⚠️ <b>Richiesta decadimento contratto</b>\n\n"
            f"👤 {user.first_name} ({gm_tag}) — <b>{team['nome']}</b>\n"
            f"🏀 Giocatore: <b>{nome}</b>\n"
            f"📋 Motivo: {motivo_label}\n\n"
            f"<i>Il contratto verrà annullato senza impatto sui tagli gratuiti. "
            f"Lo slot roster verrà liberato.</i>"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approva", callback_data=f"dec_approva:{team_id}:{gid}:{motivo_key}"),
            InlineKeyboardButton("❌ Rifiuta", callback_data=f"dec_rifiuta:{team_id}:{gid}"),
        ]])
        try:
            await query.message.bot.send_message(
                chat_id=admin_group_id, text=testo,
                parse_mode="HTML", reply_markup=kb
            )
        except Exception as e:
            logger.warning("Notifica decadimento gruppo admin: %s", e)

    context.user_data.clear()
    return ConversationHandler.END


async def cb_dec_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Richiesta annullata.")
    context.user_data.clear()
    return ConversationHandler.END


# ── Callback approvazione admin (dal gruppo admin) ─────────────────────────────

async def cb_dec_approva(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts    = query.data.split(":")
    team_id  = parts[1]
    gid      = int(parts[2])
    motivo_key = parts[3] if len(parts) > 3 else "altro"
    motivo_label = MOTIVI.get(motivo_key, motivo_key)

    stagione  = settings.stagione_corrente()
    team      = tm.get_team_by_id(team_id)
    giocatore = db.get_giocatore(gid)
    contratto = db.get_contratto_attivo(gid)

    if not giocatore:
        await query.edit_message_text("❌ Giocatore non trovato.")
        return
    if not contratto or contratto.get("team_id") != team_id:
        await query.edit_message_text("❌ Contratto non trovato o già scaduto.")
        return

    admin_user = update.effective_user
    admin_tag  = admin_user.first_name or str(admin_user.id)
    if admin_user.username:
        admin_tag += f" (@{admin_user.username})"

    # Esegui decadimento
    db.registra_decadimento(
        giocatore_id=gid,
        team_id=team_id,
        stagione=stagione,
        contratto_id=contratto["id"],
        note=f"Decadimento: {motivo_label}",
    )

    ora = format_dt(datetime.now(ROME))

    await query.edit_message_text(
        query.message.text + f"\n\n✅ <b>Approvato</b> da {admin_tag}",
        parse_mode="HTML",
        reply_markup=None,
    )

    # Annuncio canale principale
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        testo_canale = (
            f"📋 <b>{team['nome']}</b> — Decadimento contratto\n\n"
            f"Il contratto di <b>{giocatore['nome_common']}</b> è decaduto.\n"
            f"Motivo: {motivo_label}\n"
            f"Lo slot roster è stato liberato.\n\n"
            f"<i>Approvato da {admin_tag} — {ora}</i>"
        )
        try:
            await context.bot.send_message(
                chat_id=main_channel, text=testo_canale, parse_mode="HTML"
            )
        except Exception as e:
            logger.warning("Annuncio canale decadimento: %s", e)

    # Sync GAS
    try:
        import gas_client
        gas_client.sync_after_taglio(team_id)
    except Exception as e:
        logger.warning("GAS sync decadimento: %s", e)

    logger.info("Decadimento: team=%s giocatore=%d motivo=%s admin=%s",
                team_id, gid, motivo_key, admin_tag)


async def cb_dec_rifiuta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    admin_user = update.effective_user
    admin_tag  = admin_user.first_name or str(admin_user.id)
    if admin_user.username:
        admin_tag += f" (@{admin_user.username})"

    await query.edit_message_text(
        query.message.text + f"\n\n❌ <b>Rifiutato</b> da {admin_tag}",
        parse_mode="HTML",
        reply_markup=None,
    )


# ── Helper ─────────────────────────────────────────────────────────────────────

def _anni_residui(r: dict, stagione: str) -> int:
    if r.get("tipo_contratto") == "rookie":
        return 2 if int(r.get("anni_scala") or 0) in (0, 2) else 1
    return max(1, r["anni_originali"] - (int(stagione) - int(r.get("stagione_firma") or stagione)))


# ── Registrazione handler ──────────────────────────────────────────────────────

def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("decadimento", cmd_decadimento)],
        states={
            DEC_GIOCATORE: [CallbackQueryHandler(cb_dec_giocatore, pattern=r"^dec_giocat:\d+$")],
            DEC_MOTIVO:    [CallbackQueryHandler(cb_dec_motivo,    pattern=r"^dec_motivo:\w+$")],
        },
        fallbacks=[
            CallbackQueryHandler(cb_dec_annulla, pattern=r"^dec_annulla$"),
            CommandHandler("annulla", cb_dec_annulla),
        ],
        conversation_timeout=300,
        per_message=False,
    )
    return [
        conv,
        CallbackQueryHandler(cb_dec_approva, pattern=r"^dec_approva:.+:\d+:\w+$"),
        CallbackQueryHandler(cb_dec_rifiuta, pattern=r"^dec_rifiuta:.+:\d+$"),
    ]

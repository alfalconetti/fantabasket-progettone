"""
Handler per il decadimento contratti.
Casi: ritiro, firma in altra lega, giocatore svincolato da lungo tempo.
Il contratto viene annullato senza impatto sui tagli gratuiti.
Flusso GM: richiesta → gruppo admin → approvazione → DB + canale
Flusso admin: diretto da /admin_menu → 🏁 Decadimento (decadm:)
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


async def cb_dec_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ingresso dal bottone del /menu (stesso flusso di /decadimento)."""
    await update.callback_query.answer()
    return await cmd_decadimento(update, context)


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
            await context.bot.send_message(
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


# ── Applicazione (comune a approvazione e admin diretto) ──────────────────────

def _is_admin(uid: int) -> bool:
    return uid in [int(a) for a in settings.admin_ids()]


async def _ai_gm(bot, team_id: str, testo: str) -> None:
    for gm in (tm.get_team_by_id(team_id) or {}).get("gm_ids", []):
        try:
            await bot.send_message(chat_id=int(gm), text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Avviso al GM decadimento: %s", e)


def _admin_tag(user) -> str:
    tag = user.first_name or str(user.id)
    return tag + (f" (@{user.username})" if user.username else "")


async def applica_decadimento(bot, team_id: str, gid: int, motivo_key: str, admin_tag: str) -> str | None:
    """Esegue il decadimento e lo annuncia. Restituisce un messaggio d'errore o None."""
    motivo_label = MOTIVI.get(motivo_key, motivo_key)
    stagione  = settings.stagione_corrente()
    team      = tm.get_team_by_id(team_id) or {"nome": team_id}
    giocatore = db.get_giocatore(gid)
    contratto = db.get_contratto_attivo(gid)
    if not giocatore:
        return "❌ Giocatore non trovato."
    if not contratto or contratto.get("team_id") != team_id:
        return "❌ Contratto non trovato o già scaduto."

    db.registra_decadimento(giocatore_id=gid, team_id=team_id, stagione=stagione,
                            contratto_id=contratto["id"], note=f"Decadimento: {motivo_label}")

    ora = format_dt(datetime.now(ROME))
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
            await bot.send_message(chat_id=main_channel, text=testo_canale, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio canale decadimento: %s", e)
    try:
        import gas_client
        gas_client.sync_after_taglio(team_id)
    except Exception as e:
        logger.warning("GAS sync decadimento: %s", e)
    logger.info("Decadimento: team=%s giocatore=%d motivo=%s admin=%s", team_id, gid, motivo_key, admin_tag)
    return None


# ── Callback approvazione admin (dal gruppo admin) ─────────────────────────────

async def cb_dec_approva(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo gli admin possono approvare.", show_alert=True)
        return
    await query.answer()
    parts      = query.data.split(":")
    team_id    = parts[1]
    gid        = int(parts[2])
    motivo_key = parts[3] if len(parts) > 3 else "altro"
    admin_tag  = _admin_tag(query.from_user)
    errore = await applica_decadimento(context.bot, team_id, gid, motivo_key, admin_tag)
    if errore:
        await query.edit_message_text(errore)
        return
    await query.edit_message_text(query.message.text_html + f"\n\n✅ <b>Approvato</b> da {admin_tag}",
                                  parse_mode="HTML", reply_markup=None)
    nome = (db.get_giocatore(gid) or {}).get("nome_common", str(gid))
    await _ai_gm(context.bot, team_id, f"✅ Decadimento del contratto di <b>{nome}</b> approvato.")


async def cb_dec_rifiuta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo gli admin possono rifiutare.", show_alert=True)
        return
    await query.answer()
    await query.edit_message_text(query.message.text_html + f"\n\n❌ <b>Rifiutato</b> da {_admin_tag(query.from_user)}",
                                  parse_mode="HTML", reply_markup=None)
    _, team_id, gid = query.data.split(":")
    nome = (db.get_giocatore(int(gid)) or {}).get("nome_common", gid)
    await _ai_gm(context.bot, team_id, f"❌ Richiesta di decadimento per <b>{nome}</b> rifiutata dagli admin.")


# ── Admin diretto: /admin_menu → 🏁 Decadimento ───────────────────────────────
# adm:dec → decadm:t:<team> → decadm:g:<team>:<gid> → decadm:m:<team>:<gid>:<motivo> → decadm:ok:...

async def admin_lista_team(query) -> None:
    tutti = tm.get_all_teams()
    bottoni = [InlineKeyboardButton(t["nome"], callback_data=f"decadm:t:{t['id']}") for t in tutti]
    righe = [bottoni[i:i + 2] for i in range(0, len(bottoni), 2)]
    righe.append([InlineKeyboardButton("← Menu admin", callback_data="adm:home")])
    await query.edit_message_text("🏁 <b>Decadimento (admin)</b> — scegli la squadra:",
                                  parse_mode="HTML", reply_markup=InlineKeyboardMarkup(righe))


async def cb_dec_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    await query.answer()
    parti = query.data.split(":")
    azione, team_id = parti[1], parti[2]
    team = tm.get_team_by_id(team_id) or {"nome": team_id}

    if azione == "t":
        stagione = settings.stagione_corrente()
        roster = sorted(db.get_roster_team(team_id) or [], key=lambda x: -x["importo"])
        kb = [[InlineKeyboardButton(f"{r['nome_common']} {r['importo']}x{_anni_residui(r, stagione)}",
                                    callback_data=f"decadm:g:{team_id}:{r['giocatore_id']}")] for r in roster]
        kb.append([InlineKeyboardButton("← Squadre", callback_data="adm:dec")])
        await query.edit_message_text(f"🏁 <b>{team['nome']}</b> — il contratto di chi è decaduto?",
                                      parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    gid = int(parti[3])
    nome = (db.get_giocatore(gid) or {}).get("nome_common", str(gid))
    if azione == "g":
        kb = [[InlineKeyboardButton(label, callback_data=f"decadm:m:{team_id}:{gid}:{k}")] for k, label in MOTIVI.items()]
        kb.append([InlineKeyboardButton("← Indietro", callback_data=f"decadm:t:{team_id}")])
        await query.edit_message_text(f"🏁 <b>{nome}</b> ({team['nome']}) — motivo:",
                                      parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    motivo = parti[4]
    if azione == "m":
        await query.edit_message_text(
            f"🏁 Confermi il decadimento del contratto di <b>{nome}</b> ({team['nome']})?\n"
            f"Motivo: {MOTIVI.get(motivo, motivo)}\n\n"
            f"<i>Contratto annullato senza impatto sui tagli gratuiti, slot roster liberato.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Conferma", callback_data=f"decadm:ok:{team_id}:{gid}:{motivo}"),
                InlineKeyboardButton("← Indietro", callback_data=f"decadm:g:{team_id}:{gid}"),
            ]]))
        return

    if azione == "ok":
        admin_tag = _admin_tag(query.from_user)
        errore = await applica_decadimento(context.bot, team_id, gid, motivo, admin_tag)
        if errore:
            await query.edit_message_text(errore)
            return
        await query.edit_message_text(f"✅ Contratto di <b>{nome}</b> decaduto ({team['nome']}).", parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Menu admin", callback_data="adm:home")]]))
        await _ai_gm(context.bot, team_id, f"🛠 Un admin ha registrato il decadimento del contratto di <b>{nome}</b> "
                                          f"({MOTIVI.get(motivo, motivo)}).")


# ── Helper ─────────────────────────────────────────────────────────────────────

def _anni_residui(r: dict, stagione: str) -> int:
    if r.get("tipo_contratto") == "rookie":
        return 2 if int(r.get("anni_scala") or 0) in (0, 2) else 1
    return max(1, r["anni_originali"] - (int(stagione) - int(r.get("stagione_firma") or stagione)))


# ── Registrazione handler ──────────────────────────────────────────────────────

def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("decadimento", cmd_decadimento),
                      CallbackQueryHandler(cb_dec_start, pattern=r"^dec_start$")],
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
        CallbackQueryHandler(cb_dec_admin,   pattern=r"^decadm:(?:t:[\w-]+|g:[\w-]+:\d+|(?:m|ok):[\w-]+:\d+:\w+)$"),
    ]

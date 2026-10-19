"""
/my_team — mostra e permette di modificare le info del proprio team.

Campi editabili:
  - nome squadra
  - nome GM

I colori di roster e assets si cambiano con /palette (v6.1.0: i vecchi «Colore» e «Colore 2» di
qui finivano in teams.json ma nessuno li leggeva, cioè non cambiavano niente).

Callback myt:<campo> (prima mt:, lo stesso prefisso di /my_trades: un bottone delle trade premuto
con /my_team aperto finiva qui), myt:home, myt:x. La squadra è sempre quella del GM che preme.
I dati vengono salvati in teams.json.
"""
import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

import teams as tm
from settings import solo_privato

logger = logging.getLogger(__name__)

SCEGLI_CAMPO, INSERISCI_VALORE = range(2)
CAMPI = {"nome": "nome della squadra", "gm_nome": "tuo nome GM"}


def _testo_myteam(team: dict) -> str:
    return (
        f"🏀 <b>{html.escape(team['nome'])}</b>\n"
        f"👤 GM: <b>{html.escape(team.get('gm_nome', '—'))}</b>\n"
        f"<code>ID: {team['id']}</code>\n\n"
        f"<i>I colori di roster e assets si cambiano con /palette.</i>"
    )


def _kb_myteam() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Nome squadra", callback_data="myt:nome"),
         InlineKeyboardButton("✏️ Nome GM",      callback_data="myt:gm_nome")],
        [InlineKeyboardButton("✖️ Chiudi",        callback_data="myt:x")],
    ])


@solo_privato
async def cmd_my_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    team = tm.get_team_by_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END
    await update.effective_message.reply_text(_testo_myteam(team), parse_mode="HTML", reply_markup=_kb_myteam())
    return SCEGLI_CAMPO


async def cb_scegli_campo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    team = tm.get_team_by_gm(query.from_user.id)
    if not team:
        await query.answer("⛔ Non sei registrato come GM.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    campo = query.data.split(":")[1]
    if campo == "x":
        context.user_data.pop("mt_campo", None)
        await query.edit_message_text(_testo_myteam(team), parse_mode="HTML")
        return ConversationHandler.END
    if campo == "home" or campo not in CAMPI:
        context.user_data.pop("mt_campo", None)
        await query.edit_message_text(_testo_myteam(team), parse_mode="HTML", reply_markup=_kb_myteam())
        return SCEGLI_CAMPO
    context.user_data["mt_campo"] = campo
    await query.edit_message_text(
        f"Scrivi il nuovo <b>{CAMPI[campo]}</b>:", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Indietro", callback_data="myt:home")]]))
    return INSERISCI_VALORE


async def ricevi_valore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    valore = (update.effective_message.text or "").strip()
    campo = context.user_data.pop("mt_campo", None)
    team = tm.get_team_by_gm(update.effective_user.id)
    if campo not in CAMPI or not team:
        await update.effective_message.reply_text("❌ Sessione scaduta. Riprova con /my_team.")
        return ConversationHandler.END
    if not valore or len(valore) > 40:
        context.user_data["mt_campo"] = campo
        await update.effective_message.reply_text(
            "❌ Scrivi un testo tra 1 e 40 caratteri.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Indietro", callback_data="myt:home")]]))
        return INSERISCI_VALORE

    prima = team.get(campo)
    tm.set_campo_team(team["id"], campo, valore)
    from handlers.registro import segna
    await segna(context.bot, update.effective_user, "gm", "dati della squadra", squadre=team["id"], oggetto=campo,
                prima=prima or "—", dopo=valore)
    team = tm.get_team_by_id(team["id"])
    await update.effective_message.reply_text(f"✅ Aggiornato.\n\n{_testo_myteam(team)}", parse_mode="HTML",
                                              reply_markup=_kb_myteam())
    return SCEGLI_CAMPO


async def cmd_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("mt_campo", None)
    await update.effective_message.reply_text("Operazione annullata.")
    return ConversationHandler.END


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("my_team", cmd_my_team)],
        states={
            SCEGLI_CAMPO: [
                CallbackQueryHandler(cb_scegli_campo, pattern=r"^myt:[a-z_]+$"),
            ],
            INSERISCI_VALORE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_valore),
                CallbackQueryHandler(cb_scegli_campo, pattern=r"^myt:[a-z_]+$"),
            ],
        },
        fallbacks=[CommandHandler("annulla", cmd_annulla)],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
        allow_reentry=True,
    )
    return [conv]

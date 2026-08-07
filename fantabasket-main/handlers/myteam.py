"""
/my_team — mostra e permette di modificare le info del proprio team.

Campi editabili:
  - nome squadra
  - nome GM
  - colore primario (#RRGGBB)
  - colore secondario (#RRGGBB, opzionale)

I dati vengono salvati in teams.json.
"""
import logging
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

import teams as tm
from settings import solo_privato

logger = logging.getLogger(__name__)

SCEGLI_CAMPO, INSERISCI_VALORE = range(2)
_ANNULLA_HINT = "\n<i>Per annullare: /annulla</i>"
_RE_HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _testo_myteam(team: dict) -> str:
    colore  = team.get("colore", "non impostato")
    colore2 = team.get("colore2", "non impostato")
    return (
        f"🏀 <b>{team['nome']}</b>\n"
        f"👤 GM: <b>{team.get('gm_nome', '—')}</b>\n"
        f"🎨 Colore: <b>{colore}</b>\n"
        f"🎨 Colore 2: <b>{colore2}</b>\n"
        f"<code>ID: {team['id']}</code>"
    )


def _kb_myteam(team_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Nome squadra",  callback_data=f"mt:nome:{team_id}")],
        [InlineKeyboardButton("✏️ Nome GM",       callback_data=f"mt:gm_nome:{team_id}")],
        [InlineKeyboardButton("🎨 Colore",        callback_data=f"mt:colore:{team_id}")],
        [InlineKeyboardButton("🎨 Colore 2",      callback_data=f"mt:colore2:{team_id}")],
    ])


@solo_privato
async def cmd_my_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END

    await update.effective_message.reply_text(
        _testo_myteam(team),
        parse_mode="HTML",
        reply_markup=_kb_myteam(team["id"]),
    )
    return SCEGLI_CAMPO


async def cb_scegli_campo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, campo, team_id = query.data.split(":")

    context.user_data["mt_campo"]   = campo
    context.user_data["mt_team_id"] = team_id

    label = {
        "nome":    "nome della squadra",
        "gm_nome": "tuo nome GM",
        "colore":  "colore primario (formato #RRGGBB, es. #1A237E)",
        "colore2": "colore secondario (formato #RRGGBB, oppure 'nessuno' per rimuoverlo)",
    }.get(campo, campo)

    await query.edit_message_text(
        f"Inserisci il nuovo <b>{label}</b>:" + _ANNULLA_HINT,
        parse_mode="HTML",
    )
    return INSERISCI_VALORE


async def ricevi_valore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    valore   = update.effective_message.text.strip()
    campo    = context.user_data.pop("mt_campo", None)
    team_id  = context.user_data.pop("mt_team_id", None)

    if not campo or not team_id:
        await update.effective_message.reply_text("❌ Sessione scaduta. Riprova con /my_team.")
        return ConversationHandler.END

    # Validazione colore
    if campo in ("colore", "colore2"):
        if campo == "colore2" and valore.lower() in ("nessuno", "no", "-"):
            valore = ""
        elif not _RE_HEX.match(valore):
            await update.effective_message.reply_text(
                "❌ Formato colore non valido. Usa #RRGGBB (es. #1A237E)." + _ANNULLA_HINT,
                parse_mode="HTML",
            )
            return INSERISCI_VALORE

    if not valore and campo == "colore":
        await update.effective_message.reply_text(
            "❌ Il colore primario non può essere vuoto." + _ANNULLA_HINT,
            parse_mode="HTML",
        )
        return INSERISCI_VALORE

    # Salva in teams.json
    tm.set_campo_team(team_id, campo, valore)

    team = tm.get_team_by_id(team_id)
    await update.effective_message.reply_text(
        f"✅ Aggiornato.\n\n{_testo_myteam(team)}",
        parse_mode="HTML",
        reply_markup=_kb_myteam(team_id),
    )
    return SCEGLI_CAMPO


async def cmd_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("mt_campo", None)
    context.user_data.pop("mt_team_id", None)
    await update.effective_message.reply_text("Operazione annullata.")
    return ConversationHandler.END


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("my_team", cmd_my_team)],
        states={
            SCEGLI_CAMPO: [
                CallbackQueryHandler(cb_scegli_campo, pattern=r"^mt:.+:.+$"),
            ],
            INSERISCI_VALORE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_valore),
            ],
        },
        fallbacks=[CommandHandler("annulla", cmd_annulla)],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )
    return [conv]

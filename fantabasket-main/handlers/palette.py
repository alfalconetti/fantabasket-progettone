"""
/palette — Personalizzazione colori roster/assets per il proprio team.

Flusso:
  /palette → keyboard con campi colore
  Premi campo → chiedi hex
  Mandi hex → anteprima PNG
  Conferma → salva in teams.json
  Salva tutto → scrive tutti i campi confermati
"""
import json
import logging
import os
import re
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters,
)

import database as db
import settings
import teams as tm
from settings import solo_privato
from handlers.roster import _genera_roster_png, _genera_assets_png

logger = logging.getLogger(__name__)

# Stati ConversationHandler
PAL_MENU, PAL_ATTENDI_HEX, PAL_ANTEPRIMA = range(30, 33)

CAMPI_COLORE = {
    "colore_header":   "🎨 Header / sfondo principale",
    "colore_riga1":    "▦ Riga alternata 1",
    "colore_riga2":    "▦ Riga alternata 2",
    "colore_sezione":  "📋 Sfondo sezioni (footer, leggenda)",
    "colore_pick":     "📦 Sfondo sezione pick (solo assets)",
    "colore_diritti":  "🔑 Sfondo sezione diritti (solo assets)",
}

DEFAULTS = {
    "colore_header":  "#1A237E",
    "colore_riga1":   "#C5CAE9",
    "colore_riga2":   "#FFFFFF",
    "colore_sezione": "#E8EAF6",
    "colore_pick":    "#E8EAF6",
    "colore_diritti": "#E8EAF6",
}

_HEX_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _get_palette(team: dict) -> dict:
    """Ritorna la palette corrente del team (con defaults)."""
    return {k: team.get(k) or DEFAULTS[k] for k in CAMPI_COLORE}


def _kb_palette(team: dict, pendenti: dict) -> InlineKeyboardMarkup:
    """Keyboard con tutti i campi colore. Mostra ✏️ se modificato ma non salvato."""
    palette = _get_palette(team)
    palette.update(pendenti)
    bottoni = []
    for campo, label in CAMPI_COLORE.items():
        valore = palette[campo]
        mod = " ✏️" if campo in pendenti else ""
        bottoni.append([InlineKeyboardButton(
            f"{label}: {valore}{mod}",
            callback_data=f"pal_campo:{campo}"
        )])
    bottoni.append([
        InlineKeyboardButton("👁 Anteprima", callback_data="pal_anteprima"),
        InlineKeyboardButton("💾 Salva",     callback_data="pal_salva"),
    ])
    bottoni.append([InlineKeyboardButton("❌ Annulla", callback_data="pal_annulla")])
    return InlineKeyboardMarkup(bottoni)


def _kb_conferma_campo(campo: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma", callback_data=f"pal_ok:{campo}"),
        InlineKeyboardButton("🔄 Riprova",  callback_data=f"pal_campo:{campo}"),
        InlineKeyboardButton("← Indietro", callback_data="pal_back"),
    ]])


@solo_privato
async def cmd_palette(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END

    context.user_data["pal_team_id"] = team["id"]
    context.user_data["pal_pendenti"] = {}

    await update.effective_message.reply_text(
        f"🎨 <b>Palette colori — {team['nome']}</b>\n\n"
        "Seleziona un campo per modificarlo.",
        parse_mode="HTML",
        reply_markup=_kb_palette(team, {}),
    )
    return PAL_MENU


async def cb_pal_campo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    campo = query.data.split(":")[1]
    context.user_data["pal_campo_corrente"] = campo
    label = CAMPI_COLORE.get(campo, campo)
    team_id = context.user_data["pal_team_id"]
    team = tm.get_team_by_id(team_id)
    pendenti = context.user_data.get("pal_pendenti", {})
    palette = _get_palette(team)
    palette.update(pendenti)
    attuale = palette[campo]
    await query.edit_message_text(
        f"🎨 <b>{label}</b>\n\nValore attuale: <code>{attuale}</code>\n\n"
        "Invia il nuovo colore in formato hex (es. <code>#1A237E</code>):",
        parse_mode="HTML",
    )
    return PAL_ATTENDI_HEX


async def msg_pal_hex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    testo = (update.effective_message.text or "").strip()
    if not _HEX_RE.match(testo):
        await update.effective_message.reply_text(
            "❌ Formato non valido. Usa un colore hex come <code>#1A237E</code>.",
            parse_mode="HTML",
        )
        return PAL_ATTENDI_HEX

    campo = context.user_data["pal_campo_corrente"]
    context.user_data["pal_hex_candidato"] = testo

    # Genera anteprima PNG con il nuovo colore
    team_id = context.user_data["pal_team_id"]
    team = tm.get_team_by_id(team_id)
    pendenti = {**context.user_data.get("pal_pendenti", {}), campo: testo}
    team_preview = {**team, **pendenti}

    await update.effective_message.reply_text("⏳ Generazione anteprima...")
    png_path = None
    try:
        stagione = settings.stagione_corrente()
        png_path = await _genera_roster_png(team_preview, stagione)
        with open(png_path, "rb") as f:
            await update.effective_message.reply_photo(
                photo=f,
                caption=f"👁 Anteprima con <b>{CAMPI_COLORE[campo]}</b> = <code>{testo}</code>",
                parse_mode="HTML",
                reply_markup=_kb_conferma_campo(campo),
            )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore anteprima: {e}")
        return PAL_ATTENDI_HEX
    finally:
        if png_path and os.path.exists(png_path):
            os.unlink(png_path)

    return PAL_ANTEPRIMA


async def cb_pal_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    campo = query.data.split(":")[1]
    hex_val = context.user_data["pal_hex_candidato"]
    context.user_data.setdefault("pal_pendenti", {})[campo] = hex_val

    team_id = context.user_data["pal_team_id"]
    team = tm.get_team_by_id(team_id)
    pendenti = context.user_data["pal_pendenti"]

    await query.message.reply_text(
        f"✅ <code>{campo}</code> → <code>{hex_val}</code> (non ancora salvato)\n\n"
        "Continua a modificare o premi 💾 Salva.",
        parse_mode="HTML",
        reply_markup=_kb_palette(team, pendenti),
    )
    return PAL_MENU


async def cb_pal_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    team_id = context.user_data["pal_team_id"]
    team = tm.get_team_by_id(team_id)
    pendenti = context.user_data.get("pal_pendenti", {})
    await query.message.reply_text(
        "🎨 Torna al menu palette.",
        reply_markup=_kb_palette(team, pendenti),
    )
    return PAL_MENU


async def cb_pal_anteprima(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("⏳ Generazione anteprima...")
    team_id = context.user_data["pal_team_id"]
    team = tm.get_team_by_id(team_id)
    pendenti = context.user_data.get("pal_pendenti", {})
    team_preview = {**team, **pendenti}
    stagione = settings.stagione_corrente()
    png_path = None
    try:
        png_path = await _genera_roster_png(team_preview, stagione)
        with open(png_path, "rb") as f:
            await query.message.reply_photo(
                photo=f,
                caption="👁 Anteprima palette corrente",
            )
    except Exception as e:
        await query.message.reply_text(f"❌ Errore anteprima: {e}")
    finally:
        if png_path and os.path.exists(png_path):
            os.unlink(png_path)
    return PAL_MENU


async def cb_pal_salva(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    team_id = context.user_data["pal_team_id"]
    pendenti = context.user_data.get("pal_pendenti", {})
    if not pendenti:
        await query.answer("Nessuna modifica da salvare.", show_alert=True)
        return PAL_MENU

    teams_path = os.environ.get("TEAMS_PATH", "/config/teams.json")
    teams_data = json.load(open(teams_path))
    for t in teams_data:
        if t["id"] == team_id:
            t.update(pendenti)
            break
    json.dump(teams_data, open(teams_path, "w"), indent=2, ensure_ascii=False)

    context.user_data["pal_pendenti"] = {}
    await query.edit_message_text(
        f"✅ Palette salvata per <b>{tm.get_team_by_id(team_id)['nome']}</b>.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cb_pal_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Palette annullata, nessuna modifica salvata.")
    return ConversationHandler.END


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("palette", cmd_palette)],
        states={
            PAL_MENU: [
                CallbackQueryHandler(cb_pal_campo,    pattern=r"^pal_campo:.+$"),
                CallbackQueryHandler(cb_pal_anteprima, pattern=r"^pal_anteprima$"),
                CallbackQueryHandler(cb_pal_salva,    pattern=r"^pal_salva$"),
                CallbackQueryHandler(cb_pal_annulla,  pattern=r"^pal_annulla$"),
            ],
            PAL_ATTENDI_HEX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_pal_hex),
                CallbackQueryHandler(cb_pal_campo,    pattern=r"^pal_campo:.+$"),
            ],
            PAL_ANTEPRIMA: [
                CallbackQueryHandler(cb_pal_ok,    pattern=r"^pal_ok:.+$"),
                CallbackQueryHandler(cb_pal_campo, pattern=r"^pal_campo:.+$"),
                CallbackQueryHandler(cb_pal_back,  pattern=r"^pal_back$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cb_pal_annulla, pattern=r"^pal_annulla$"),
        ],
        per_user=True,
        per_chat=True,
        per_message=False,
        conversation_timeout=300,
    )
    return [conv]

"""
/palette — Personalizzazione colori roster/assets per il proprio team.

Flusso:
  /palette → un bottone per ogni colore (col valore di adesso, o «automatico»)
  Premi un colore → scrivi l'hex (#1A237E, 1A237E, #abc) oppure ♻️ Automatico, o ← Indietro
  → anteprima (roster, o assets per pick e diritti) → ✅ Usa questo / 🔄 Un altro / ← Indietro
  💾 Salva scrive tutti i colori scelti in teams.json, 👁 Anteprima mostra roster e assets insieme

Contrasto (v6.1.0): qualsiasi colore si scelga, il testo sopra diventa chiaro o scuro da solo
(roster.input_colori), comprese intestazione, riga dei titoli e anni delle pick, che prima erano
sempre bianchi (illeggibili su un'intestazione chiara). «Automatico» = il colore che il template
ricava da quello dell'intestazione (prima il menu mostrava valori di default che non erano quelli
usati davvero).
"""
import logging
import os
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters,
)

import settings
import teams as tm
from settings import solo_privato
from handlers import roster as R
from handlers.roster import colori_effettivi, _contrasto, DEFAULT_HEADER

logger = logging.getLogger(__name__)

# Stati ConversationHandler
PAL_MENU, PAL_ATTENDI_HEX, PAL_ANTEPRIMA = range(30, 33)

CAMPI_COLORE = {
    "colore_header":   "🎨 Intestazione",
    "colore_riga1":    "▦ Righe dispari",
    "colore_riga2":    "▦ Righe pari",
    "colore_sezione":  "📋 Leggenda e riquadro del cap",
    "colore_pick":     "📦 Sezione pick (assets)",
    "colore_diritti":  "🔑 Sezione diritti (assets)",
}
_EFFETTIVO = {"colore_header": "header", "colore_riga1": "riga1", "colore_riga2": "riga2",
              "colore_sezione": "sezione", "colore_pick": "pick", "colore_diritti": "diritti"}
_SOLO_ASSETS = {"colore_pick", "colore_diritti"}
AUTO = ""          # valore pendente che vuol dire «torna automatico» (il campo si toglie da teams.json)


def normalizza_hex(testo: str) -> str | None:
    """'#1a237e', '1A237E', '#abc' → '#1A237E' / '#AABBCC'; None se non è un colore."""
    t = (testo or "").strip().lstrip("#")
    if re.fullmatch(r"[0-9A-Fa-f]{3}", t):
        t = "".join(c * 2 for c in t)
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", t):
        return None
    return "#" + t.upper()


def _team_con(team: dict, pendenti: dict) -> dict:
    """La squadra coi colori pendenti applicati («automatico» = campo tolto)."""
    t = dict(team)
    for k, v in pendenti.items():
        if v == AUTO:
            t.pop(k, None)
        else:
            t[k] = v
    return t


def _valore(team: dict, campo: str) -> str:
    """'#1A237E' se scelto, 'automatico (#C5CAE9)' se no."""
    if campo == "colore_header":
        return team.get(campo) or f"automatico ({DEFAULT_HEADER})"
    if team.get(campo):
        return team[campo]
    return f"automatico ({colori_effettivi(team)[_EFFETTIVO[campo]].upper()})"


def _note(team: dict) -> str:
    """Avvisi sulla palette (il testo è sempre leggibile: si adatta da solo)."""
    c = colori_effettivi(team)
    note = []
    if _contrasto(c["riga1"], c["riga2"]) < 1.12:
        note.append("ℹ️ Le righe pari e dispari quasi non si distinguono.")
    return ("\n" + "\n".join(note)) if note else ""


def _kb_palette(team: dict, pendenti: dict) -> InlineKeyboardMarkup:
    t = _team_con(team, pendenti)
    bottoni = []
    for campo, label in CAMPI_COLORE.items():
        mod = " ✏️" if campo in pendenti else ""
        bottoni.append([InlineKeyboardButton(f"{label}: {_valore(t, campo)}{mod}", callback_data=f"pal_campo:{campo}")])
    bottoni.append([
        InlineKeyboardButton("👁 Anteprima", callback_data="pal_anteprima"),
        InlineKeyboardButton("💾 Salva" + (f" ({len(pendenti)})" if pendenti else ""), callback_data="pal_salva"),
    ])
    bottoni.append([InlineKeyboardButton("✖️ Chiudi senza salvare", callback_data="pal_annulla")])
    return InlineKeyboardMarkup(bottoni)


def _testo_menu(team: dict, pendenti: dict) -> str:
    return (f"🎨 <b>Palette colori — {team['nome']}</b>\n\n"
            "Tocca un colore per cambiarlo. Il testo sopra ogni colore diventa chiaro o scuro da solo, "
            "così resta sempre leggibile. «Automatico» = ricavato dal colore dell'intestazione."
            + (f"\n\n✏️ {len(pendenti)} modifiche da salvare." if pendenti else "")
            + _note(_team_con(team, pendenti)))


def _kb_attendi(campo: str) -> InlineKeyboardMarkup:
    righe = [] if campo == "colore_header" else [[InlineKeyboardButton("♻️ Automatico", callback_data=f"pal_auto:{campo}")]]
    return InlineKeyboardMarkup(righe + [[InlineKeyboardButton("← Indietro", callback_data="pal_back")]])


def _kb_conferma_campo(campo: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Usa questo", callback_data=f"pal_ok:{campo}"),
        InlineKeyboardButton("🔄 Un altro",   callback_data=f"pal_campo:{campo}"),
    ], [InlineKeyboardButton("← Indietro", callback_data="pal_back")]])


def _stato(context) -> tuple[dict | None, dict]:
    team = tm.get_team_by_id(context.user_data.get("pal_team_id", ""))
    return team, context.user_data.setdefault("pal_pendenti", {})


async def _menu(query_o_msg, context, testo_extra: str = "", nuovo: bool = False) -> int:
    team, pendenti = _stato(context)
    if not team:
        return ConversationHandler.END
    testo = (testo_extra + "\n\n" if testo_extra else "") + _testo_menu(team, pendenti)
    if nuovo or not hasattr(query_o_msg, "edit_message_text"):
        msg = query_o_msg.message if hasattr(query_o_msg, "message") and query_o_msg.message else query_o_msg
        await msg.reply_text(testo, parse_mode="HTML", reply_markup=_kb_palette(team, pendenti))
    else:
        await query_o_msg.edit_message_text(testo, parse_mode="HTML", reply_markup=_kb_palette(team, pendenti))
    return PAL_MENU


async def _manda_png(msg, team_preview: dict, assets: bool, caption: str, kb=None):
    png_path = None
    try:
        stagione = settings.stagione_corrente()
        gen = R._genera_assets_png if assets else R._genera_roster_png
        png_path = await gen(team_preview, stagione)
        with open(png_path, "rb") as f:
            await msg.reply_photo(photo=f, caption=caption, parse_mode="HTML", reply_markup=kb)
    finally:
        if png_path and os.path.exists(png_path):
            os.unlink(png_path)


@solo_privato
async def cmd_palette(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    team = tm.get_team_by_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END
    context.user_data["pal_team_id"] = team["id"]
    context.user_data["pal_pendenti"] = {}
    return await _menu(update.effective_message, context)


async def cb_pal_campo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    campo = query.data.split(":")[1]
    if campo not in CAMPI_COLORE:
        return PAL_MENU
    team, pendenti = _stato(context)
    if not team:
        return ConversationHandler.END
    context.user_data["pal_campo_corrente"] = campo
    testo = (f"🎨 <b>{CAMPI_COLORE[campo]}</b>\n\nAdesso: <code>{_valore(_team_con(team, pendenti), campo)}</code>\n\n"
             "Scrivi il nuovo colore in esadecimale, per esempio <code>#1A237E</code> (va bene anche senza #)."
             + ("\nOppure ♻️ Automatico per tornare al colore ricavato dall'intestazione." if campo != "colore_header" else ""))
    if query.message and query.message.photo:          # dall'anteprima: messaggio nuovo, la foto resta
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text(testo, parse_mode="HTML", reply_markup=_kb_attendi(campo))
    else:
        await query.edit_message_text(testo, parse_mode="HTML", reply_markup=_kb_attendi(campo))
    return PAL_ATTENDI_HEX


async def msg_pal_hex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    campo = context.user_data.get("pal_campo_corrente")
    team, pendenti = _stato(context)
    if not campo or not team:
        return ConversationHandler.END
    hex_val = normalizza_hex(update.effective_message.text)
    if not hex_val:
        await update.effective_message.reply_text(
            "❌ Non è un colore. Scrivilo in esadecimale, per esempio <code>#1A237E</code>.",
            parse_mode="HTML", reply_markup=_kb_attendi(campo))
        return PAL_ATTENDI_HEX
    context.user_data["pal_hex_candidato"] = hex_val
    prova = _team_con(team, {**pendenti, campo: hex_val})
    await update.effective_message.reply_text("⏳ Preparo l'anteprima…")
    try:
        await _manda_png(update.effective_message, prova, campo in _SOLO_ASSETS,
                         f"👁 <b>{CAMPI_COLORE[campo]}</b> = <code>{hex_val}</code>{_note(prova)}",
                         _kb_conferma_campo(campo))
    except Exception as e:
        logger.warning("Anteprima palette: %s", e)
        await update.effective_message.reply_text(f"❌ Anteprima non riuscita: {e}", reply_markup=_kb_attendi(campo))
        return PAL_ATTENDI_HEX
    return PAL_ANTEPRIMA


async def cb_pal_auto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    campo = query.data.split(":")[1]
    if campo in CAMPI_COLORE and campo != "colore_header":
        _, pendenti = _stato(context)
        pendenti[campo] = AUTO
    return await _menu(query, context, f"♻️ <b>{CAMPI_COLORE.get(campo, campo)}</b>: automatico (non ancora salvato).")


async def cb_pal_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    campo = query.data.split(":")[1]
    hex_val = context.user_data.get("pal_hex_candidato")
    if campo not in CAMPI_COLORE or not hex_val:
        return await _menu(query, context, nuovo=True)
    _, pendenti = _stato(context)
    pendenti[campo] = hex_val
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    return await _menu(query, context, f"✅ <b>{CAMPI_COLORE[campo]}</b> → <code>{hex_val}</code> (non ancora salvato).",
                       nuovo=True)


async def cb_pal_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.message and query.message.photo:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await _menu(query, context, nuovo=True)
    return await _menu(query, context)


async def cb_pal_anteprima(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("⏳ Preparo l'anteprima…")
    team, pendenti = _stato(context)
    if not team:
        return ConversationHandler.END
    prova = _team_con(team, pendenti)
    try:
        await _manda_png(query.message, prova, False, "👁 Roster con questa palette")
        await _manda_png(query.message, prova, True, "👁 Assets con questa palette")
    except Exception as e:
        await query.message.reply_text(f"❌ Anteprima non riuscita: {e}")
    return await _menu(query, context, nuovo=True)


async def cb_pal_salva(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    team, pendenti = _stato(context)
    if not team:
        await query.answer()
        return ConversationHandler.END
    if not pendenti:
        await query.answer("Nessuna modifica da salvare.", show_alert=True)
        return PAL_MENU
    await query.answer()
    prima = {k: team.get(k) for k in pendenti}
    for k, v in pendenti.items():
        tm.set_campo_team(team["id"], k, v)          # "" = automatico: il campo si toglie
    from handlers.registro import segna
    await segna(context.bot, query.from_user, "gm", "palette della squadra", squadre=team["id"],
                oggetto=", ".join(CAMPI_COLORE[k] for k in pendenti),
                prima=", ".join(f"{k} {v or 'automatico'}" for k, v in prima.items()),
                dopo=", ".join(f"{k} {v or 'automatico'}" for k, v in pendenti.items()))
    context.user_data["pal_pendenti"] = {}
    await query.edit_message_text(
        f"✅ Palette salvata per <b>{team['nome']}</b>: vale da subito per /roster e /assets.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


def _pulisci(context):
    for k in ("pal_team_id", "pal_pendenti", "pal_campo_corrente", "pal_hex_candidato"):
        context.user_data.pop(k, None)


async def cmd_pal_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/annulla durante la palette: si chiude senza salvare (gli altri comandi funzionano normalmente)."""
    _pulisci(context)
    if update.effective_message:
        await update.effective_message.reply_text("✖️ Palette chiusa, nessuna modifica salvata.")
    return ConversationHandler.END


async def cb_pal_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _pulisci(context)
    try:
        if query.message and query.message.photo:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("✖️ Palette chiusa, nessuna modifica salvata.")
        else:
            await query.edit_message_text("✖️ Palette chiusa, nessuna modifica salvata.")
    except Exception:
        pass
    return ConversationHandler.END


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("palette", cmd_palette)],
        states={
            PAL_MENU: [
                CallbackQueryHandler(cb_pal_campo,     pattern=r"^pal_campo:.+$"),
                CallbackQueryHandler(cb_pal_anteprima, pattern=r"^pal_anteprima$"),
                CallbackQueryHandler(cb_pal_salva,     pattern=r"^pal_salva$"),
            ],
            PAL_ATTENDI_HEX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_pal_hex),
                CallbackQueryHandler(cb_pal_auto,  pattern=r"^pal_auto:.+$"),
                CallbackQueryHandler(cb_pal_back,  pattern=r"^pal_back$"),
                CallbackQueryHandler(cb_pal_campo, pattern=r"^pal_campo:.+$"),
            ],
            PAL_ANTEPRIMA: [
                CallbackQueryHandler(cb_pal_ok,    pattern=r"^pal_ok:.+$"),
                CallbackQueryHandler(cb_pal_campo, pattern=r"^pal_campo:.+$"),
                CallbackQueryHandler(cb_pal_back,  pattern=r"^pal_back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_pal_hex),   # un altro hex senza toccare 🔄
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cb_pal_annulla, pattern=r"^pal_annulla$"),
            CommandHandler("annulla", cmd_pal_annulla),
        ],
        allow_reentry=True,
        per_user=True,
        per_chat=True,
        per_message=False,
        conversation_timeout=600,
    )
    return [conv]

"""
/my_team — mostra e permette di modificare le info del proprio team.

Campi editabili:
  - nome squadra
  - nome GM

I colori di roster e assets si cambiano con /palette (v6.1.0: i vecchi «Colore» e «Colore 2» di
qui finivano in teams.json ma nessuno li leggeva, cioè non cambiavano niente).

Callback myt:<campo> (prima mt:, lo stesso prefisso di /my_trades: un bottone delle trade premuto
con /my_team aperto finiva qui), myt:home, myt:x. Per il GM la squadra è sempre la sua.
I dati vengono salvati in teams.json.

Admin (v6.4.6, Luca 23/10): `/edit_team [SQUADRA]` o ✏️ Nomi squadre nel pannello admin (myt:lista →
myt:t:<team_id>) aprono lo stesso pannello per qualsiasi squadra; la squadra scelta resta in
user_data["mt_team"] (solo per chi è admin), registro e canale log con veste admin.
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


def _is_admin(uid: int) -> bool:
    import settings
    return settings.is_admin(uid)


def _squadra(uid: int, context) -> tuple[dict | None, bool]:
    """(squadra su cui si lavora, da admin?): quella scelta da un admin, se no quella del GM."""
    tid = context.user_data.get("mt_team")
    if tid and _is_admin(uid):
        return tm.get_team_by_id(tid), True
    return tm.get_team_by_gm(uid), False


def _kb_lista() -> InlineKeyboardMarkup:
    sq = sorted(tm.get_all_teams(), key=lambda t: t["nome"].lower())
    b = [InlineKeyboardButton(t["nome"][:28], callback_data=f"myt:t:{t['id']}") for t in sq]
    return InlineKeyboardMarkup([b[i:i + 2] for i in range(0, len(b), 2)] + [[InlineKeyboardButton("✖️ Chiudi", callback_data="myt:x")]])


def _testo_myteam(team: dict, admin: bool = False) -> str:
    if admin:
        return (f"🛠 <b>{html.escape(team['nome'])}</b> <i>(modifica da admin)</i>\n"
                f"👤 GM: <b>{html.escape(team.get('gm_nome', '—'))}</b>\n"
                f"<code>ID: {team['id']}</code>")
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
    context.user_data.pop("mt_team", None)          # /my_team: sempre la propria squadra
    team = tm.get_team_by_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END
    await update.effective_message.reply_text(_testo_myteam(team), parse_mode="HTML", reply_markup=_kb_myteam())
    return SCEGLI_CAMPO


@solo_privato
async def cmd_edit_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/edit_team [SQUADRA] (admin): nome della squadra e nome del GM di qualsiasi squadra."""
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo per gli admin. Per la tua squadra: /my_team")
        return ConversationHandler.END
    context.user_data.pop("mt_campo", None)
    if context.args:
        team = tm.get_team_by_query(" ".join(context.args))
        if not team:
            await update.effective_message.reply_text("❌ Squadra non trovata. Scegli:", reply_markup=_kb_lista())
            return SCEGLI_CAMPO
        context.user_data["mt_team"] = team["id"]
        await update.effective_message.reply_text(_testo_myteam(team, True), parse_mode="HTML", reply_markup=_kb_myteam())
        return SCEGLI_CAMPO
    await update.effective_message.reply_text("🛠 <b>Nomi di squadre e GM</b>: scegli la squadra", parse_mode="HTML",
                                              reply_markup=_kb_lista())
    return SCEGLI_CAMPO


async def cb_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """myt:lista (dal pannello admin) e myt:t:<team_id>."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo per gli admin.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    context.user_data.pop("mt_campo", None)
    parti = query.data.split(":")
    if parti[1] == "lista":
        await query.edit_message_text("🛠 <b>Nomi di squadre e GM</b>: scegli la squadra", parse_mode="HTML",
                                      reply_markup=_kb_lista())
        return SCEGLI_CAMPO
    team = tm.get_team_by_id(parti[2])
    if not team:
        await query.edit_message_text("❌ Squadra non trovata.", reply_markup=_kb_lista())
        return SCEGLI_CAMPO
    context.user_data["mt_team"] = team["id"]
    await query.edit_message_text(_testo_myteam(team, True), parse_mode="HTML", reply_markup=_kb_myteam())
    return SCEGLI_CAMPO


async def cb_scegli_campo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    team, admin = _squadra(query.from_user.id, context)
    if not team:
        await query.answer("⛔ Non sei registrato come GM.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    campo = query.data.split(":")[1]
    if campo == "x":
        context.user_data.pop("mt_campo", None)
        context.user_data.pop("mt_team", None)
        await query.edit_message_text(_testo_myteam(team, admin), parse_mode="HTML")
        return ConversationHandler.END
    if campo == "home" or campo not in CAMPI:
        context.user_data.pop("mt_campo", None)
        await query.edit_message_text(_testo_myteam(team, admin), parse_mode="HTML", reply_markup=_kb_myteam())
        return SCEGLI_CAMPO
    context.user_data["mt_campo"] = campo
    cosa = CAMPI[campo] if not admin else ("nome della squadra" if campo == "nome" else "nome del GM")
    await query.edit_message_text(
        f"Scrivi il nuovo <b>{cosa}</b>" + (f" di {html.escape(team['nome'])}" if admin else "") + ":", parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Indietro", callback_data="myt:home")]]))
    return INSERISCI_VALORE


async def ricevi_valore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    valore = (update.effective_message.text or "").strip()
    campo = context.user_data.pop("mt_campo", None)
    team, admin = _squadra(update.effective_user.id, context)
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
    await segna(context.bot, update.effective_user, "admin" if admin else "gm", "dati della squadra", squadre=team["id"],
                oggetto=campo, prima=prima or "—", dopo=valore)
    team = tm.get_team_by_id(team["id"])
    await update.effective_message.reply_text(f"✅ Aggiornato.\n\n{_testo_myteam(team, admin)}", parse_mode="HTML",
                                              reply_markup=_kb_myteam())
    return SCEGLI_CAMPO


async def cmd_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("mt_campo", None)
    context.user_data.pop("mt_team", None)
    await update.effective_message.reply_text("Operazione annullata.")
    return ConversationHandler.END


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("my_team", cmd_my_team), CommandHandler("edit_team", cmd_edit_team),
                      CallbackQueryHandler(cb_admin, pattern=r"^myt:(lista|t:\w+)$")],
        states={
            SCEGLI_CAMPO: [
                CallbackQueryHandler(cb_admin, pattern=r"^myt:(lista|t:\w+)$"),
                CallbackQueryHandler(cb_scegli_campo, pattern=r"^myt:[a-z_]+$"),
            ],
            INSERISCI_VALORE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_valore),
                CallbackQueryHandler(cb_admin, pattern=r"^myt:(lista|t:\w+)$"),
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

"""
Navigazione dei menu a bottoni (v6.1.0, Luca 19/10: «i menu a pulsanti sempre con tasto indietro
oppure chiudi»). Ogni schermata coi bottoni ha un modo per uscire: ← verso la schermata da cui si
arriva, oppure ✖️ Chiudi (toglie il messaggio) sulle schermate di partenza.

  chiudi()          ✖️ Chiudi (callback nav:x, gestito qui, vale ovunque)
  menu()            🏠 Menu (torna al /menu dei GM)
  pannello()        ← Menu admin
  indietro(cb)      ← Indietro verso cb
  mostra(update, …) se si arriva da un bottone modifica quel messaggio, se no ne manda uno nuovo
                    (dal /menu le schermate si aprono al posto del menu, non sotto)
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

logger = logging.getLogger(__name__)
CHIUDI = "nav:x"


def chiudi(testo: str = "✖️ Chiudi") -> InlineKeyboardButton:
    return InlineKeyboardButton(testo, callback_data=CHIUDI)


def menu() -> InlineKeyboardButton:
    return InlineKeyboardButton("🏠 Menu", callback_data="menu:home")


def pannello() -> InlineKeyboardButton:
    return InlineKeyboardButton("← Menu admin", callback_data="adm:home")


def indietro(cb: str, testo: str = "← Indietro") -> InlineKeyboardButton:
    return InlineKeyboardButton(testo, callback_data=cb)


def con(kb: InlineKeyboardMarkup | list | None, *bottoni: InlineKeyboardButton) -> InlineKeyboardMarkup:
    """La tastiera con in fondo una riga di navigazione."""
    righe = [list(r) for r in (kb.inline_keyboard if isinstance(kb, InlineKeyboardMarkup) else (kb or []))]
    return InlineKeyboardMarkup(righe + [list(bottoni)])


async def mostra(update: Update, testo: str, reply_markup=None, **kw):
    """Da un bottone: al posto del messaggio di partenza (se non si può, per esempio una foto,
    sotto). Da un comando: un messaggio nuovo."""
    q = update.callback_query
    if q is not None and q.message is not None and getattr(q.message, "text", None):
        try:
            return await q.edit_message_text(testo, reply_markup=reply_markup, **kw)
        except Exception as err:
            if "not modified" in str(err).lower():
                return None
            logger.info("mostra: modifica non riuscita (%s), messaggio nuovo", err)
    return await update.effective_message.reply_text(testo, reply_markup=reply_markup, **kw)


async def cb_chiudi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        await q.message.delete()
    except Exception:                    # messaggi vecchi (più di 48 ore): si tolgono solo i bottoni
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception as err:
            logger.info("Chiudi: %s", err)


def get_handlers() -> list:
    return [CallbackQueryHandler(cb_chiudi, pattern=rf"^{CHIUDI}$")]

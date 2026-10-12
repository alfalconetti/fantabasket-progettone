"""
Controllo di coerenza (v3.10.0): stato di oggi e registro `transazioni` devono dire la
stessa cosa. Contratti attivi = ultimo movimento di ogni giocatore; pick e diritti =
ultimo movimento di ciascuno.

  job_coerenza      ogni notte all'01:00 → privato del dev, solo se trova qualcosa
  /dev_coerenza     lo stesso controllo su richiesta (dev), con l'esito anche se è tutto a posto

I problemi non si correggono da soli: di solito sono operazioni fatte a mano sul database
(un contratto chiuso senza movimento, una pick spostata con un UPDATE). Si sistemano
aggiungendo il movimento mancante, così il registro resta completo.
"""
import html
import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
import settings

logger = logging.getLogger(__name__)


def _testo(problemi: list[str]) -> str:
    righe = [f"🧭 <b>Controllo di coerenza</b> — {len(problemi)} da guardare", ""]
    righe += [f"• {html.escape(p)}" for p in problemi[:40]]
    if len(problemi) > 40:
        righe.append(f"… e altri {len(problemi) - 40}")
    return "\n".join(righe)


async def job_coerenza(context: ContextTypes.DEFAULT_TYPE):
    try:
        problemi = db.controlli_coerenza()
        logger.info("Controllo di coerenza: %d problemi.", len(problemi))
        dev = settings.dev_id()
        if problemi and dev:
            await context.bot.send_message(chat_id=dev, text=_testo(problemi), parse_mode="HTML")
    except Exception as e:
        from handlers.helpers import log_job_error
        await log_job_error(context, "job_coerenza", e)


async def cmd_dev_coerenza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != settings.dev_id():
        return
    problemi = db.controlli_coerenza()
    await update.effective_message.reply_text(
        _testo(problemi) if problemi else "🧭 Controllo di coerenza: tutto a posto ✅", parse_mode="HTML")


def get_handlers() -> list:
    return [CommandHandler("dev_coerenza", cmd_dev_coerenza)]

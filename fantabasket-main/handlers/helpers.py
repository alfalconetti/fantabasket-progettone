"""
Funzioni condivise tra handlers e job schedulati.
log_job_error: logga eccezioni nei job su canale log + dev
log_warn:      manda warning su canale log con orario
"""
import logging
import traceback
from datetime import datetime, timezone

import settings
from utils import format_dt, ROME

logger = logging.getLogger(__name__)


async def log_job_error(context, job_name: str, exc: Exception):
    """
    Logga un'eccezione avvenuta dentro un job schedulato (JobQueue).
    I job NON passano per app.add_error_handler, quindi senza questa
    funzione un errore sparirebbe nei soli log del container.
    Manda il traceback al canale log_channel_id_main e al dev in privato.
    """
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("Eccezione nel job '%s': %s", job_name, exc, exc_info=True)

    ora = format_dt(datetime.now(timezone.utc))
    testo = (
        f"❌ <b>Errore nel job '{job_name}'</b>\n"
        f"🕐 {ora}\n"
        f"<code>{str(exc)}</code>\n\n"
        f"<pre>{tb[-1500:]}</pre>"
    )

    g = settings.load_globals()
    log_channel_id = g.get("log_channel_id_main")
    if log_channel_id:
        try:
            await context.bot.send_message(
                chat_id=log_channel_id, text=testo, parse_mode="HTML"
            )
        except Exception as e:
            logger.warning("log_job_error: invio al canale log fallito: %s", e)

    dev_id = g.get("dev_id")
    if dev_id:
        try:
            await context.bot.send_message(
                chat_id=dev_id, text=testo, parse_mode="HTML"
            )
        except Exception as e:
            logger.warning("log_job_error: invio al dev fallito: %s", e)


async def log_warn(context, testo: str):
    """Manda un warning sia al logger che al canale log con orario."""
    logger.warning(testo)
    g = settings.load_globals()
    log_channel_id = g.get("log_channel_id_main")
    if not log_channel_id:
        return
    ora = format_dt(datetime.now(timezone.utc))
    try:
        await context.bot.send_message(
            chat_id=log_channel_id,
            text=f"⚠️ 🕐 {ora}\n{testo}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("log_warn fallito: %s", e)

"""
loucabot — il bot del campionato: calendario (v1), poi classifica, playoff e calcolo automatico.
Stesso PostgreSQL e stessa config del progettone; legge le tabelle degli altri bot, scrive
solo le sue (lega_*, nba_*).
"""
import logging
import os
import re
from datetime import time as dtime
from zoneinfo import ZoneInfo

from telegram import BotCommand, Update
from telegram.ext import ApplicationBuilder, ContextTypes

import config
import db
from handlers import get_handlers, job_sync

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
ROME = ZoneInfo("Europe/Rome")


def _versione() -> str:
    try:
        t = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "CHANGELOG.md"), encoding="utf-8").read()
        v = re.findall(r"^## (v[0-9][0-9A-Za-z.\-]*)", t, re.M)
        return v[-1] if v else "sconosciuta"
    except Exception:
        return "sconosciuta"


BOT_VERSION = _versione()

COMANDI = [
    BotCommand("calendario", "La tua giornata e le prossime"),
    BotCommand("giornata", "Tutte le partite di una giornata"),
    BotCommand("guida", "Cosa fa il bot"),
]


def _token() -> str:
    path = os.environ.get("BOT_TOKEN_FILE")
    if path and os.path.exists(path):
        return open(path).read().strip()
    raise RuntimeError("Token non trovato (BOT_TOKEN_FILE)")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Errore non gestito", exc_info=context.error)
    for chat in (config.canale_log(), config.dev_id()):
        if chat:
            try:
                await context.bot.send_message(chat_id=chat, text=f"⚠️ loucabot: {context.error!r}"[:3000])
            except Exception:
                pass


async def post_init(app):
    try:
        await app.bot.set_my_commands(COMANDI)
    except Exception as e:
        logger.warning("Comandi: %s", e)
    if config.canale_log():
        try:
            await app.bot.send_message(chat_id=config.canale_log(), text=f"📅 loucabot {BOT_VERSION} avviato")
        except Exception as e:
            logger.warning("Avviso di avvio: %s", e)


def main():
    db.init_db()
    app = ApplicationBuilder().token(_token()).post_init(post_init).build()
    for h in get_handlers():
        app.add_handler(h)
    app.add_error_handler(error_handler)
    app.job_queue.run_daily(job_sync, time=dtime(8, 30, tzinfo=ROME))
    logger.info("loucabot %s avviato.", BOT_VERSION)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

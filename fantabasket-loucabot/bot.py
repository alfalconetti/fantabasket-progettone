"""
loucabot — il bot del campionato: calendario, tabellini e calcolo dei fantapunti; poi formazioni, classifica e playoff.
Stesso PostgreSQL e stessa config del progettone; legge le tabelle degli altri bot, scrive
solo le sue (lega_*, nba_*).
"""
import logging
import os
from datetime import time as dtime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder

import config
import db
from handlers import get_handlers, job_sync
from handlers_calcolo import job_infortuni

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
# niente riga per ogni chiamata all'API di Telegram: contiene il token nell'URL e riempie i log
for _nome in ("httpx", "httpcore"):
    logging.getLogger(_nome).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
try:
    from shared import dev_comune
    dev_comune.installa_log()                     # per /dev_log
except ImportError:
    pass
ROME = ZoneInfo("Europe/Rome")


BOT_VERSION = config.versione()


def _token() -> str:
    path = os.environ.get("BOT_TOKEN_FILE")
    if path and os.path.exists(path):
        return open(path).read().strip()
    raise RuntimeError("Token non trovato (BOT_TOKEN_FILE)")


async def post_init(app):
    from comandi import registra_comandi
    await registra_comandi(app.bot)
    if config.canale_log():
        try:
            await app.bot.send_message(chat_id=config.canale_log(), text=f"📅 loucabot {BOT_VERSION} avviato")
        except Exception as e:
            logger.warning("Avviso di avvio: %s", e)


def main():
    db.init_db()
    app = ApplicationBuilder().token(_token()).post_init(post_init).build()
    from handlers import _is_dev
    from shared import dev_comune
    for h in get_handlers() + dev_comune.get_handlers(_is_dev, lambda: db.q("SELECT version() AS v", one=True)["v"]):
        app.add_handler(h)
    app.add_error_handler(dev_comune.error_handler("loucabot", config.canale_log, config.dev_id))
    app.job_queue.run_daily(job_sync, time=dtime(8, 30, tzinfo=ROME))        # partite, tabellini, infortunati
    for ora in (dtime(17, 30, tzinfo=ROME), dtime(23, 30, tzinfo=ROME)):       # infortunati prima delle partite
        app.job_queue.run_daily(job_infortuni, time=ora)
    logger.info("loucabot %s avviato.", BOT_VERSION)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

"""
IPanchinari — panchine e quintetti della lega. Le panchine arrivano come messaggi di testo
(soprannomi compresi) e si pubblicano sul canale Panchinari; i quintetti restano da una
giornata all'altra e si confermano dal promemoria. Stesso PostgreSQL e stessa config del
progettone; scrive solo le sue tabelle (ipa_*).
"""
import logging
import os
from datetime import timedelta

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes

import config
import db

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
# niente riga per ogni chiamata all'API di Telegram: contiene il token nell'URL e riempie i log
for _nome in ("httpx", "httpcore"):
    logging.getLogger(_nome).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BOT_VERSION = config.versione()


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
                await context.bot.send_message(chat_id=chat, text=f"⚠️ IPanchinari: {context.error!r}"[:3000])
            except Exception:
                pass


async def post_init(app):
    from comandi import registra_comandi
    await registra_comandi(app.bot)
    if config.canale_log():
        try:
            await app.bot.send_message(chat_id=config.canale_log(), text=f"🪑 IPanchinari {BOT_VERSION} avviato")
        except Exception as e:
            logger.warning("Avviso di avvio: %s", e)


def main():
    db.init_db()
    import handlers
    import panchine
    import quintetti
    app = ApplicationBuilder().token(_token()).post_init(post_init).build()
    for h in handlers.get_handlers() + quintetti.get_handlers() + panchine.get_handlers():
        app.add_handler(h)
    app.add_error_handler(error_handler)
    app.job_queue.run_repeating(quintetti.job_giornate, interval=timedelta(minutes=5), first=30)
    logger.info("IPanchinari %s avviato.", BOT_VERSION)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

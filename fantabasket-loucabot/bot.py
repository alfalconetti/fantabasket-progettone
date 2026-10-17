"""
loucabot — il bot del campionato: calendario, tabellini e calcolo dei fantapunti; poi formazioni, classifica e playoff.
Stesso PostgreSQL e stessa config del progettone; legge le tabelle degli altri bot, scrive
solo le sue (lega_*, nba_*).
"""
import logging
import os
from datetime import time as dtime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder

import config
import db
from handlers import get_handlers, job_sync
from handlers_calcolo import job_infortuni, job_prepartita

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
ORE_SNAPSHOT = [dtime(h, 30, tzinfo=ROME) for h in (0, 4, 12, 16, 20)]      # ogni 4 ore, con le 8:30 di job_sync


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
    import live
    live.migra()
    import formazioni_foglio
    formazioni_foglio.migra()
    app = ApplicationBuilder().token(_token()).post_init(post_init).build()
    from handlers import _is_dev
    from shared import dev_comune
    import handlers_risultati
    import prova_live
    import player
    import classifica
    for h in (get_handlers() + handlers_risultati.get_handlers() + prova_live.get_handlers() + player.get_handlers()
              + classifica.get_handlers()) + dev_comune.get_handlers(_is_dev, lambda: db.q("SELECT version() AS v", one=True)["v"]):
        app.add_handler(h)
    app.add_error_handler(dev_comune.error_handler("loucabot", config.canale_log, config.dev_id))
    app.job_queue.run_daily(job_sync, time=dtime(8, 30, tzinfo=ROME))        # partite, tabellini, infortunati
    app.job_queue.run_daily(handlers_risultati.job_calcolo, time=dtime(7, 45, tzinfo=ROME))     # calcolo definitivo
    app.job_queue.run_daily(handlers_risultati.job_controllo, time=dtime(10, 0, tzinfo=ROME))   # tabellini corretti da ESPN?
    # snapshot degli infortunati ogni 4 ore (anche di notte) e 30 minuti prima della prima partita
    # del giorno: per il calcolo conta quello subito prima delle partite, il più recente è lo
    # stato che IPanchinari mostra; dopo una settimana resta solo quello che conta (job_sync)
    for ora in ORE_SNAPSHOT:
        app.job_queue.run_daily(job_infortuni, time=ora)
    app.job_queue.run_repeating(job_prepartita, interval=timedelta(minutes=10), first=120)
    # punteggi live: il job guarda ogni minuto, aggiorna ogni 10 (live.cosa_fare)
    app.job_queue.run_repeating(live.job_live, interval=timedelta(minutes=1), first=60)
    # formazioni congelate sul foglio di controllo (e le correzioni degli admin), fino al calcolo
    app.job_queue.run_repeating(formazioni_foglio.job_formazioni, interval=timedelta(minutes=5), first=90)
    logger.info("loucabot %s avviato.", BOT_VERSION)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

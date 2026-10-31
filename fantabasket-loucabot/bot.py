"""
loucabot — il bot del campionato: calendario, tabellini e calcolo dei fantapunti; poi formazioni, classifica e playoff.
Stesso PostgreSQL e stessa config del progettone; legge le tabelle degli altri bot, scrive
solo le sue (lega_*, nba_*).
"""
import logging
import os
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder

import config
from shared import regole
import db
from handlers import get_handlers, job_sync
from handlers_calcolo import job_infortuni, job_injury_fitti, job_prepartita

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
    import congelamento
    congelamento.migra()
    import formazioni_foglio
    formazioni_foglio.migra()
    app = ApplicationBuilder().token(_token()).post_init(post_init).build()
    from handlers import _is_dev
    from shared import dev_comune
    import handlers_risultati
    import prova_live
    import player
    import classifica
    import partita
    for h in (get_handlers() + handlers_risultati.get_handlers() + prova_live.get_handlers() + player.get_handlers()
              + classifica.get_handlers() + partita.get_handlers() + congelamento.get_handlers()) + dev_comune.get_handlers(_is_dev, lambda: db.q("SELECT version() AS v", one=True)["v"]):
        app.add_handler(h)
    app.add_error_handler(dev_comune.error_handler("loucabot", config.canale_log, config.dev_id))
    app.job_queue.run_daily(job_sync, time=regole.orario("sync_nba").replace(tzinfo=ROME))        # partite, tabellini, infortunati
    app.job_queue.run_daily(handlers_risultati.job_calcolo, time=regole.orario("calcolo").replace(tzinfo=ROME))     # calcolo definitivo
    # v58: niente più controllo delle 10 sulle giornate; alle 20 il controllo finale della notte prima (poi congelata)
    import top
    import tanking
    app.job_queue.run_daily(tanking.job_tanking, time=regole.orario("controllo_tanking").replace(tzinfo=ROME))  # controllo tanking
    app.job_queue.run_daily(top.job_top_notte, time=regole.orario("top_notte").replace(tzinfo=ROME))        # top 20 della notte
    app.job_queue.run_daily(handlers_risultati.job_controllo_finale, time=regole.orario("controllo_notte").replace(tzinfo=ROME))
    # v60: primo controllo dell'ultima notte alle 11:05; un minuto dopo per le giornate senza live (convalidate)
    _pc = (datetime.combine(date(2000, 1, 1), regole.orario("primo_controllo")) + timedelta(minutes=1)).time()
    app.job_queue.run_daily(handlers_risultati.job_primo_controllo, time=_pc.replace(tzinfo=ROME))
    app.job_queue.run_daily(formazioni_foglio.job_parziale, time=regole.orario("foglio_parziale").replace(tzinfo=ROME))   # foglio provvisorio a metà giornata
    # snapshot degli infortunati ogni 4 ore (anche di notte) e 30 minuti prima della prima partita
    # del giorno: per il calcolo conta quello subito prima delle partite, il più recente è lo
    # stato che IPanchinari mostra; dopo una settimana resta solo quello che conta (job_sync)
    for ora in ORE_SNAPSHOT:
        app.job_queue.run_daily(job_infortuni, time=ora)
    app.job_queue.run_repeating(job_prepartita, interval=timedelta(minutes=10), first=120)
    # prima sera di una giornata: injury report ogni mezz'ora dalle 19 alla prima partita (IPanchinari avvisa i GM)
    app.job_queue.run_repeating(job_injury_fitti, interval=timedelta(minutes=5), first=150)
    # punteggi live: il job guarda ogni minuto, aggiorna ogni 10 (live.cosa_fare)
    app.job_queue.run_repeating(live.job_live, interval=timedelta(minutes=1), first=60)
    import foto                                      # foto dei giocatori: una al minuto, solo nella notte americana
    app.job_queue.run_repeating(foto.job_foto, interval=timedelta(minutes=1), first=75)
    # formazioni congelate sul foglio di controllo (e le correzioni degli admin), fino al calcolo
    app.job_queue.run_repeating(formazioni_foglio.job_formazioni, interval=timedelta(minutes=5), first=90)
    logger.info("loucabot %s avviato.", BOT_VERSION)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

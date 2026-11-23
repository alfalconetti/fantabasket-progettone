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
from telegram.ext import ApplicationBuilder, CommandHandler

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
from shared import attesa_telegram
import avvio
RECUPERABILI: dict = {}          # v7.19.0: {nome: (orario, job)} dei job a orario fisso recuperabili (avvio.py)
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
            await app.bot.send_message(chat_id=config.canale_log(), text=f"📅 loucabot {BOT_VERSION} avviato" + attesa_telegram.nota_avvio())
        except Exception as e:
            logger.warning("Avviso di avvio: %s", e)
    try:                                              # v7.19.0: i job a orario fisso saltati mentre era giù
        nomi = avvio.recupera(app, RECUPERABILI)
        if nomi and config.canale_log():
            await app.bot.send_message(chat_id=config.canale_log(), text=avvio.testo_recuperati(nomi))
    except Exception as e:
        logger.warning("Recupero dei job saltati: %s", e)


def main():
    db.init_db()
    import live
    live.migra()
    avvio.migra()
    import calendario_playoff                       # v7.9.5: le date delle giornate P
    calendario_playoff.migra()
    import playoff as _po
    _po.migra()
    import congelamento
    congelamento.migra()
    import formazioni_foglio
    formazioni_foglio.migra()
    app = ApplicationBuilder().token(_token()).post_init(post_init).build()
    # comandi admin e dev solo in privato e nel gruppo admin (Luca, 31/10): prima di tutto il resto
    # solo per la lega (Luca, 31/10): GM, admin e dev in privato, solo i gruppi e i canali della lega
    from shared import solo_lega
    solo_lega.installa(app)
    from shared import solo_gruppo_admin
    from comandi import comandi_pubblici
    solo_gruppo_admin.installa(app, comandi_pubblici(), config.gruppo_admin)
    from handlers import _is_dev
    from shared import dev_comune
    import handlers_risultati
    import prova_live
    import player
    import status
    import rendimento
    import classifica
    import partita
    import cup
    import calendario_playoff
    import playoff
    import rendimento_team
    for h in (get_handlers() + handlers_risultati.get_handlers() + prova_live.get_handlers() + player.get_handlers() + status.get_handlers() + rendimento.get_handlers()
              + classifica.get_handlers() + partita.get_handlers() + congelamento.get_handlers() + cup.get_handlers() + calendario_playoff.get_handlers() + playoff.get_handlers() + rendimento_team.get_handlers()) + dev_comune.get_handlers(_is_dev, lambda: db.q("SELECT version() AS v", one=True)["v"]):
        app.add_handler(h)
    import vista                                         # v7.21.0: roster, assets, pick… del bot principale
    for h in vista.get_handlers():
        app.add_handler(h)
    from shared import draft_vista as DV                  # v7.27.0: /draft (shared/draft_vista; il draft lo fa il principale)
    app.add_handler(CommandHandler("draft", DV.cmd_draft, block=False))
    from shared import pagine as PG                       # v7.25.0: i «Quale?» a pagine e di chi ha cercato
    for h, gr in PG.handlers():
        app.add_handler(h, group=gr)
    app.add_error_handler(dev_comune.error_handler("loucabot", config.canale_log, config.dev_id))
    # v58: niente più controllo delle 10 sulle giornate; alle 20 il controllo finale della notte prima (poi congelata)
    import top
    import tanking
    # v60: primo controllo dell'ultima notte alle 11:05; un minuto dopo per le giornate senza live (convalidate)
    _pc = (datetime.combine(date(2000, 1, 1), regole.orario("primo_controllo")) + timedelta(minutes=1)).time()
    # v7.19.0: i job a orario fisso segnano quando hanno girato (avvio.segnato); se il bot era giù alla loro ora,
    # all'avvio si rifanno (avvio.recupera, in post_init)
    RECUPERABILI.update({
        "sync_nba": (regole.orario("sync_nba"), job_sync),                                    # partite, tabellini, infortunati
        "primo_controllo": (_pc, handlers_risultati.job_primo_controllo),
        "calcolo": (regole.orario("calcolo"), handlers_risultati.job_calcolo),                 # calcolo definitivo
        "controllo_tanking": (regole.orario("controllo_tanking"), tanking.job_tanking),
        "top_notte": (regole.orario("top_notte"), top.job_top_notte),                          # top 20 della notte
        "controllo_notte": (regole.orario("controllo_notte"), handlers_risultati.job_controllo_finale)})
    for _nome, (_ora, _job) in RECUPERABILI.items():
        app.job_queue.run_daily(avvio.segnato(_nome, _job), time=_ora.replace(tzinfo=ROME), name=_nome)
    # v7.20.2: Telegram che cade col bot acceso: i job a orario fisso finiti senza Telegram si rifanno al ritorno
    _tk = _token()
    avvio.CONTROLLO = lambda: attesa_telegram.risponde(_tk)
    avvio.RECUPERABILI = RECUPERABILI
    app.job_queue.run_repeating(avvio.job_sentinella, interval=timedelta(minutes=5), first=300)
    app.job_queue.run_daily(formazioni_foglio.job_parziale, time=regole.orario("foglio_parziale").replace(tzinfo=ROME))   # foglio provvisorio a metà giornata
    # snapshot degli infortunati ogni 4 ore (anche di notte) e 30 minuti prima della prima partita
    # del giorno: per il calcolo conta quello subito prima delle partite, il più recente è lo
    # stato che IPanchinari mostra; dopo una settimana resta solo quello che conta (job_sync)
    for ora in ORE_SNAPSHOT:
        app.job_queue.run_daily(job_infortuni, time=ora)
    app.job_queue.run_repeating(job_prepartita, interval=timedelta(minutes=10), first=120)
    import playoff                                   # v7.10.0: passaggio ai playoff (fase, bozza, blocco alle 15)
    app.job_queue.run_repeating(playoff.job_passaggio, interval=timedelta(minutes=1), first=90)
    # prima sera di una giornata: injury report ogni mezz'ora dalle 19 alla prima partita (IPanchinari avvisa i GM)
    app.job_queue.run_repeating(job_injury_fitti, interval=timedelta(minutes=5), first=150)
    # punteggi live: il job guarda ogni minuto, aggiorna ogni 5 minuti, dalle 2 ogni 10 (live.cosa_fare, live.frequenza)
    app.job_queue.run_repeating(live.job_live, interval=timedelta(minutes=1), first=60)
    import foto                                      # foto dei giocatori: una al minuto, solo nella notte americana
    app.job_queue.run_repeating(foto.job_foto, interval=timedelta(minutes=1), first=75)
    # loghi delle 30 squadre NBA da ESPN (v6.13.0): all'avvio e ogni giorno, solo quelli mancanti o vecchi
    import nba as _nba
    app.job_queue.run_repeating(_nba.job_loghi, interval=timedelta(days=1), first=90)
    # formazioni congelate sul foglio di controllo (e le correzioni degli admin), fino al calcolo
    app.job_queue.run_repeating(formazioni_foglio.job_formazioni, interval=timedelta(minutes=5), first=90)
    logger.info("loucabot %s avviato.", BOT_VERSION)
    # v7.19.0: se Telegram non risponde a questo bot, si aspetta qui (niente crash in giro continuo) e intanto
    # si scaricano partite e tabellini, che non hanno bisogno di Telegram (avvio.scarica_senza_telegram)
    attesa_telegram.attendi(_token(), "loucabot", mentre=avvio.scarica_senza_telegram)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

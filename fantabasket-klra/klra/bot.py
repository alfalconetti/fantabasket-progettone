"""
klra — loucabot coi sistemi di punteggio alternativi (Luca, 04/11/2026). Solo lettura sul database della lega
(klra/basi.py, setup_db.sql), tabelle sue nel database klra. Comandi in klra/comandi.py.
"""
import logging
import os
import re
from zoneinfo import ZoneInfo

from telegram.ext import ApplicationBuilder

import config
from klra import basi, motore

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
for _nome in ("httpx", "httpcore"):
    logging.getLogger(_nome).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
ROME = ZoneInfo("Europe/Rome")


def versione() -> str:
    try:
        t = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CHANGELOG.md"), encoding="utf-8").read()
        v = re.findall(r"^## (v\d+)", t, re.M)
        return v[-1] if v else "?"
    except OSError:
        return "?"


def canale_log():
    g = config.globali()
    return g.get("log_channel_id_klra") or g.get("dev_id")


def _token() -> str:
    path = os.environ.get("BOT_TOKEN_FILE")
    if path and os.path.exists(path):
        return open(path).read().strip()
    raise RuntimeError("Token non trovato (BOT_TOKEN_FILE)")


async def job_precalcola(context) -> None:
    """Ogni ora: le giornate convalidate nuove (o riconvalidate) per tutti i sistemi, in cache."""
    import asyncio
    try:
        n = await asyncio.to_thread(precalcola)
        if n:
            logger.info("Precalcolate %d giornate", n)
    except Exception:
        logger.exception("Precalcolo")


def precalcola() -> int:
    s = config.stagione()
    fatte = 0
    conv = motore.giornate_convalidate(s)
    for sist in basi.q("SELECT * FROM klra_sistemi ORDER BY id", many=True) or []:
        for n, c in conv.items():
            f = motore.KR.firma(motore.parametri(sist))
            r = basi.q("SELECT convalidato FROM klra_risultati WHERE sistema_id = %s AND firma = %s AND stagione = %s AND giornata = %s",
                       (sist["id"], f, s, n), one=True)
            if not r or r["convalidato"] != c:
                motore.risultati_giornata(sist, s, n, c)
                fatte += 1
    return fatte


async def post_init(app):
    from klra import comandi
    await comandi.registra(app.bot)
    if canale_log():
        try:
            await app.bot.send_message(chat_id=canale_log(), text=f"🧪 klra {versione()} avviato")
        except Exception as e:
            logger.warning("Avviso di avvio: %s", e)


def main():
    basi.apri_ufficiale()
    basi.apri_klra()
    motore.installa()
    app = ApplicationBuilder().token(_token()).post_init(post_init).build()
    from shared import solo_lega
    solo_lega.installa(app)
    from shared import solo_gruppo_admin
    from klra import comandi
    solo_gruppo_admin.installa(app, comandi.comandi_pubblici(), config.gruppo_admin)
    for h in comandi.handlers():
        app.add_handler(h)
    app.job_queue.run_repeating(job_precalcola, interval=3600, first=60)
    logger.info("klra %s avviato", versione())
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

"""
Un messaggio sul canale principale mandato dal bot principale, anche da un altro bot (v7.23.0, Luca 22/11: l'annuncio
di «solo bot» lo fa IPanchinari ma deve passare dal bot principale, che è admin del canale).
Il token del principale arriva come secret (MAIN_BOT_TOKEN_FILE, docker-compose.yml); il canale è main_channel_id di
globals.json. `invia(chat_id, testo)` si può sostituire nelle prove.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)


def _canale() -> int | None:
    try:
        with open(os.environ.get("GLOBALS_PATH", "/config/globals.json"), encoding="utf-8") as f:
            c = json.load(f).get("main_channel_id")
        return int(c) if c else None
    except Exception:
        return None


def _token() -> str | None:
    p = os.environ.get("MAIN_BOT_TOKEN_FILE", "/run/secrets/bot_token_main")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


async def manda(testo: str, invia=None) -> bool:
    """True se è partito. Senza canale o token: False e una riga nel log, niente eccezioni."""
    chat = _canale()
    if not chat:
        logger.warning("Annuncio sul canale principale: main_channel_id mancante")
        return False
    try:
        if invia:
            await invia(chat, testo)
            return True
        token = _token()
        if not token:
            logger.warning("Annuncio sul canale principale: token del bot principale mancante (MAIN_BOT_TOKEN_FILE)")
            return False
        from telegram import Bot
        async with Bot(token) as b:
            await b.send_message(chat_id=chat, text=testo, parse_mode="HTML")
        return True
    except Exception as err:
        logger.warning("Annuncio sul canale principale: %s", err)
        return False

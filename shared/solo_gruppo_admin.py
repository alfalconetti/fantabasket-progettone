"""
Comandi admin e dev solo in privato e nel gruppo admin (Luca, 31/10: «È gravissimo altrimenti»).

Prima i comandi admin controllavano solo **chi** li scriveva: un admin che scriveva /tanking, /calcola, /stato…
nel gruppo della lega o in un altro gruppo li vedeva eseguiti lì, davanti a tutti. Ora ogni bot installa una
guardia che gira prima di tutti gli handler (gruppo -100):
- in chat privata: tutto come prima (i comandi controllano da sé chi è admin);
- nel gruppo admin (`admin_group_id` di globals.json): tutto come prima;
- in ogni altro gruppo, supergruppo o canale: passano solo i comandi **pubblici** del bot (quelli dei menu dei
  GM e dei gruppi, più /start, /help, /annulla); gli altri si ignorano in silenzio (nessuna risposta nel gruppo,
  una riga nel log del bot).

È una lista di quelli permessi, non di quelli vietati: un comando admin nuovo, o nascosto dai menu, nei gruppi
non passa finché non è nella lista dei pubblici. Ogni bot la ricava dai suoi menu (`comandi.comandi_pubblici()`).
"""
import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, TypeHandler

logger = logging.getLogger(__name__)

SEMPRE = {"start", "help", "annulla"}
GRUPPO_GUARDIA = -100


def comando(msg) -> str | None:
    """«/tanking@nomebot 3» → «tanking»; None se il messaggio (o la didascalia) non è un comando."""
    t = ((getattr(msg, "text", None) or getattr(msg, "caption", None)) or "") if msg else ""
    if not t.startswith("/"):
        return None
    c = t.split()[0][1:].split("@")[0].lower()
    return c or None


def bloccato(tipo_chat: str | None, chat_id, cmd: str | None, pubblici: set[str], gruppo_admin) -> bool:
    if not cmd or not tipo_chat or tipo_chat == "private":
        return False
    try:
        if gruppo_admin and int(chat_id) == int(gruppo_admin):
            return False
    except (TypeError, ValueError):
        pass
    return cmd not in pubblici and cmd not in SEMPRE


def guardia(pubblici, gruppo_admin):
    """La callback del TypeHandler. `pubblici`: insieme di nomi; `gruppo_admin`: funzione → id del gruppo admin o None."""
    pubblici = {p.lower() for p in pubblici}

    async def _guardia(update: Update, context):
        msg = update.message or update.edited_message or update.channel_post or update.edited_channel_post
        cmd = comando(msg)
        chat = update.effective_chat
        if cmd and chat and bloccato(chat.type, chat.id, cmd, pubblici, gruppo_admin()):
            u = update.effective_user
            logger.warning("Comando /%s ignorato nella chat %s (%s), da %s: fuori dal gruppo admin solo i comandi pubblici",
                           cmd, chat.id, chat.type, u.id if u else "?")
            raise ApplicationHandlerStop
    return _guardia


def installa(app, pubblici, gruppo_admin) -> None:
    app.add_handler(TypeHandler(Update, guardia(pubblici, gruppo_admin)), group=GRUPPO_GUARDIA)

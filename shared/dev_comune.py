"""
Comandi dev comuni a loucabot e IPanchinari (il bot principale e il bot aste hanno i loro):
/dev_log [N] (ultime righe di log in memoria), /dev_pg (connessione a PostgreSQL),
/reboot (riavvio: il processo esce e Docker lo fa ripartire).

Uso nel bot.py, dopo logging.basicConfig:
    from shared import dev_comune
    dev_comune.installa_log()
    ... app.add_handler(h) for h in dev_comune.get_handlers(is_dev, ping)
dove is_dev(uid) -> bool e ping() -> str (per esempio "SELECT version()").

Errori non gestiti: app.add_error_handler(dev_comune.error_handler("IPanchinari", canale_log, dev_id)).
"Message is not modified" (bottone premuto due volte) non si segnala; gli errori di rete vanno sul
canale log (non al dev), come nel bot principale: servono a capire se il bot non raggiunge Telegram.
"""
import collections
import html
import logging
import os
import signal

from telegram.ext import CommandHandler

logger = logging.getLogger(__name__)
buffer: collections.deque = collections.deque(maxlen=300)


class _Buffer(logging.Handler):
    def emit(self, record):
        try:
            buffer.append(self.format(record))
        except Exception:
            pass


def installa_log() -> None:
    h = _Buffer()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(h)


def get_handlers(is_dev, ping) -> list:
    async def cmd_dev_log(update, context):
        if not is_dev(update.effective_user.id):
            return
        try:
            n = int(context.args[0]) if context.args else 30
            assert 1 <= n <= 100
        except (ValueError, AssertionError):
            await update.effective_message.reply_text("N deve essere un intero tra 1 e 100.")
            return
        righe = list(buffer)[-n:]
        if not righe:
            await update.effective_message.reply_text("Nessuna riga di log in memoria.")
            return
        testo = "\n".join(righe)
        if len(testo) > 3800:
            testo = "…\n" + testo[-3800:]
        await update.effective_message.reply_text(f"<pre>{html.escape(testo)}</pre>", parse_mode="HTML")

    async def cmd_dev_pg(update, context):
        if not is_dev(update.effective_user.id):
            return
        try:
            await update.effective_message.reply_text(f"✅ PostgreSQL OK — {html.escape(str(ping()))}", parse_mode="HTML")
        except Exception as err:
            await update.effective_message.reply_text(f"❌ PostgreSQL KO: {err}")

    async def cmd_reboot(update, context):
        if not is_dev(update.effective_user.id):
            return
        await update.effective_message.reply_text("🔄 Riavvio in corso…")
        logger.info("Reboot richiesto dal dev %s", update.effective_user.id)
        os.kill(os.getpid(), signal.SIGTERM)

    return [CommandHandler("dev_log", cmd_dev_log), CommandHandler("dev_pg", cmd_dev_pg),
            CommandHandler("reboot", cmd_reboot)]


def descrivi_update(update) -> str:
    """Chi e cosa ha scatenato l'errore, per capire da dove viene."""
    try:
        u = getattr(update, "effective_user", None)
        chi = f"{u.full_name} ({u.id})" if u else "job"
        q = getattr(update, "callback_query", None)
        if q:
            return f"{chi} · bottone {q.data}"
        m = getattr(update, "effective_message", None)
        if m and m.text:
            return f"{chi} · " + (m.text.split()[0] if m.text.startswith("/") else "messaggio")
        return chi
    except Exception:
        return "?"


def error_handler(nome: str, canale_log, dev_id):
    """Error handler di PTB: log, poi canale log e dev. canale_log() e dev_id() sono funzioni."""
    async def gestisci(update, context):
        from telegram.error import NetworkError, TimedOut
        err = context.error
        if "message is not modified" in str(err).lower():
            logger.debug("Message is not modified (%s)", descrivi_update(update))
            q = getattr(update, "callback_query", None)
            if q:
                try:
                    await q.answer()
                except Exception:
                    pass
            return
        if isinstance(err, (TimedOut, NetworkError)):
            logger.warning("Errore di rete (%s): %s", descrivi_update(update), err)
            canale = canale_log()
            if canale:
                try:
                    await context.bot.send_message(chat_id=canale, text=f"⚠️ {nome}: errore di rete\n{err}\n{descrivi_update(update)}"[:3000])
                except Exception:
                    pass
            return
        logger.error("Errore non gestito (%s)", descrivi_update(update), exc_info=err)
        testo = f"⚠️ {nome}: {err!r}\n{descrivi_update(update)}"[:3000]
        for chat in (canale_log(), dev_id()):
            if chat:
                try:
                    await context.bot.send_message(chat_id=chat, text=testo)
                except Exception:
                    pass
    return gestisci

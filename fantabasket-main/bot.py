"""
Fantabasket Main Bot — entry point
"""
import logging
import os
import signal
import traceback

from telegram import Update
from telegram.ext import ApplicationBuilder, TypeHandler, CommandHandler, ContextTypes

import database as db
import settings
import log_buffer as _log_buffer_mod
from utils import ROME
from scheduler import backup_giornaliero, backup_settimanale, backup_shutdown
from handlers.trade       import get_handlers as trade_handlers
from handlers.tagli       import get_handlers as tagli_handlers
from handlers.rookie      import get_handlers as rookie_handlers
from handlers.menu        import get_handlers as menu_handlers
from handlers.roster      import get_handlers as roster_handlers
from handlers.myteam      import get_handlers as myteam_handlers
from handlers.team_diff   import get_handlers as team_diff_handlers
from handlers.admin_panel import get_handlers as admin_panel_handlers
from handlers.dev_player  import get_handlers as dev_player_handlers
from handlers.dev         import get_handlers as dev_handlers
from handlers.palette     import get_handlers as palette_handlers
from handlers.dpe         import get_handlers as dpe_handlers

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
_log_buffer_mod.install()
logger = logging.getLogger(__name__)

BOT_VERSION = "v1"


def _read_secret(env_var: str) -> str:
    path = os.environ.get(env_var)
    if path and os.path.exists(path):
        return open(path).read().strip()
    raise RuntimeError(f"Secret non trovato: {env_var}")


async def cmd_annulla_globale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler globale /annulla — pulisce user_data e notifica l'utente.
    Funziona anche se nessuna conversazione è attiva."""
    context.user_data.clear()
    await update.effective_message.reply_text(
        "✅ Conversazione terminata. Puoi ricominciare con un nuovo comando."
    )


async def post_stop(application):
    logger.info("Bot in arresto — esecuzione backup pre-stop.")
    await backup_shutdown(application)


async def post_init(application):
    """Registra i comandi con scope appropriato all'avvio."""
    from telegram import BotCommand, BotCommandScopeAllPrivateChats, \
        BotCommandScopeAllGroupChats, BotCommandScopeChat, BotCommandScopeDefault

    g              = settings.load_globals()
    admin_ids      = g.get("admin_ids", [])
    dev_id         = g.get("dev_id")
    admin_group_id = g.get("admin_group_id")

    cmd_group = [
        BotCommand("roster",  "Roster squadra [team_id] [DD-MM-YY]"),
        BotCommand("assets",  "Asset completi squadra [team_id]"),
    ]
    cmd_base = cmd_group + [
        BotCommand("menu",           "Menu principale"),
    ]
    cmd_gm = cmd_base + [
        BotCommand("build_trade",    "Costruisci una trade"),
        BotCommand("import_trade",   "Importa trade da testo"),
        BotCommand("bozze_trade",    "Le tue bozze di trade"),
        BotCommand("taglia",         "Taglia un giocatore"),
        BotCommand("dpe",            "Richiedi Disabled Player Exception"),
        BotCommand("attiva_diritti", "Attiva diritti 2nd pick"),
        BotCommand("my_team",        "Info e impostazioni del tuo team"),
        BotCommand("palette",        "Personalizza colori roster/assets"),
        BotCommand("team_diff",      "Variazioni roster [team_id] [da] [a]"),
        BotCommand("annulla",          "Esci da qualsiasi conversazione bloccata"),
    ]
    cmd_admin = cmd_gm + [
        BotCommand("admin_menu",          "Pannello admin"),
        BotCommand("set_fase",            "Cambia fase della stagione"),
        BotCommand("approva_trade",       "Approva una trade in attesa"),
        BotCommand("annulla_trade_admin", "Annulla una trade"),
    ]
    cmd_dev = cmd_admin + [
        BotCommand("dev",          "Lista comandi dev"),
        BotCommand("dev_version",  "Versione bot"),
        BotCommand("dev_log",      "Ultime N righe log [N]"),
        BotCommand("dev_trade",    "Ultime N trade approvate [N]"),
        BotCommand("dev_pg",       "Stato connessione PostgreSQL"),
        BotCommand("dev_roster",   "Dump roster raw [team_id]"),
        BotCommand("dev_player",   "Anagrafica giocatore [nome]"),
        BotCommand("job_status",   "Job attivi nella JobQueue"),
        BotCommand("broadcast",    "Messaggio a tutti i GM"),
        BotCommand("backup",       "Backup manuale al canale log"),
        BotCommand("reboot",       "Riavvia il bot"),
    ]

    try:
        await application.bot.set_my_commands(
            cmd_group, scope=BotCommandScopeAllGroupChats()
        )
        await application.bot.set_my_commands(
            cmd_base, scope=BotCommandScopeDefault()
        )
        await application.bot.set_my_commands(
            cmd_gm, scope=BotCommandScopeAllPrivateChats()
        )
        if admin_group_id:
            await application.bot.set_my_commands(
                cmd_admin, scope=BotCommandScopeChat(chat_id=admin_group_id)
            )
        for aid in admin_ids:
            try:
                await application.bot.set_my_commands(
                    cmd_admin, scope=BotCommandScopeChat(chat_id=aid)
                )
            except Exception:
                pass
        if dev_id:
            try:
                await application.bot.set_my_commands(
                    cmd_dev, scope=BotCommandScopeChat(chat_id=dev_id)
                )
            except Exception:
                pass
        logger.info("Scopes comandi registrati.")
    except Exception as e:
        logger.warning("Registrazione scopes fallita: %s", e)

    # Notifica avvio sul canale log
    g = settings.load_globals()
    log_channel_id = g.get("log_channel_id_main")
    if log_channel_id:
        try:
            from datetime import datetime
            ora = datetime.now(ROME).strftime("%d/%m/%Y %H:%M")
            await application.bot.send_message(
                chat_id=log_channel_id,
                text=f"🟢 <b>Fantabasket Main Bot {BOT_VERSION} avviato</b> — {ora}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Notifica avvio fallita: %s", e)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Logga gli errori non gestiti e li manda al canale log e al dev."""
    from telegram.error import TimedOut, NetworkError
    g = settings.load_globals()
    log_channel_id = g.get("log_channel_id_main")
    dev_id = g.get("dev_id")

    user_info = ""
    if update and hasattr(update, "effective_user") and update.effective_user:
        u = update.effective_user
        user_info = f"👤 {u.first_name} (@{u.username or '?'}) · ID: {u.id}\n"

    if isinstance(context.error, (TimedOut, NetworkError)):
        logger.warning("Errore di rete: %s", context.error)
        testo = f"⚠️ <b>Errore di rete</b>\n{user_info}<code>{str(context.error)}</code>"
    elif "Message is not modified" in str(context.error):
        logger.debug("Message is not modified: %s", context.error)
        return
    else:
        logger.error("Eccezione non gestita:", exc_info=context.error)
        tb = "".join(traceback.format_exception(
            type(context.error), context.error, context.error.__traceback__
        ))
        testo = (
            f"❌ <b>Errore non gestito</b>\n"
            f"{user_info}\n"
            f"<code>{str(context.error)}</code>\n\n"
            f"<pre>{tb[-2000:]}</pre>"
        )

    if log_channel_id:
        try:
            await context.bot.send_message(
                chat_id=log_channel_id, text=testo, parse_mode="HTML"
            )
        except Exception as e:
            logger.warning("Impossibile inviare al canale log: %s", e)

    if dev_id and "Errore non gestito" in testo:
        try:
            await context.bot.send_message(chat_id=dev_id, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Impossibile inviare errore al dev: %s", e)


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solo dev: invia backup manuale al canale log."""
    dev_id = settings.dev_id()
    if not dev_id or update.effective_user.id != dev_id:
        return
    from scheduler import invia_backup
    g = settings.load_globals()
    log_channel_id = g.get("log_channel_id_main")
    if not log_channel_id:
        await update.effective_message.reply_text("❌ log_channel_id non configurato.")
        return
    await update.effective_message.reply_text("⏳ Backup in corso...")
    await invia_backup(context, log_channel_id, "manuale", includi_aste_db=True)
    await update.effective_message.reply_text("✅ Backup inviato.")


async def cmd_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solo dev: riavvia il bot."""
    dev_id = settings.dev_id()
    if not dev_id or update.effective_user.id != dev_id:
        return
    await update.effective_message.reply_text("🔄 Riavvio in corso...")
    logger.info("Reboot richiesto da dev %d", update.effective_user.id)
    os.kill(os.getpid(), signal.SIGTERM)


async def _guest_handler(update: Update, context) -> None:
    """Handler per guest_message: risponde a /roster e /assets da chat esterne."""
    from handlers.roster import _genera_roster_png, _genera_assets_png
    from telegram import InlineQueryResultCachedPhoto, InlineQueryResultArticle, InputTextMessageContent
    import re, os, uuid
    msg = update.guest_message
    if not msg or not msg.text:
        return
    guest_query_id = msg.guest_query_id
    if not guest_query_id:
        return
    text = msg.text.strip()
    m = re.search(r'/(roster|assets)\s*(.*)', text, re.IGNORECASE)
    if not m:
        return
    cmd  = m.group(1).lower()
    args = m.group(2).split() if m.group(2).strip() else []

    import teams as tm
    import settings
    user = msg.from_user
    team = None
    for arg in args:
        t = tm.get_team_by_id(arg)
        if t:
            team = t
            break
    if team is None:
        team = tm.get_team_by_gm(user.id) if user else None
    if team is None:
        await context.bot.answer_guest_query(
            guest_query_id=guest_query_id,
            result=InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="Team non trovato",
                input_message_content=InputTextMessageContent("❌ Team non trovato."),
            ),
        )
        return

    stagione = settings.stagione_corrente()
    png_path = None
    try:
        if cmd == "roster":
            png_path = await _genera_roster_png(team, stagione)
        else:
            png_path = await _genera_assets_png(team, stagione)

        # Carica il PNG su log_channel per ottenere file_id
        log_channel = settings.load_globals().get("log_channel_id_main")
        with open(png_path, "rb") as f:
            sent = await context.bot.send_photo(chat_id=log_channel, photo=f)
        file_id = sent.photo[-1].file_id

        await context.bot.answer_guest_query(
            guest_query_id=guest_query_id,
            result=InlineQueryResultCachedPhoto(
                id=str(uuid.uuid4()),
                photo_file_id=file_id,
            ),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Guest handler error: %s", e)
        await context.bot.answer_guest_query(
            guest_query_id=guest_query_id,
            result=InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="Errore",
                input_message_content=InputTextMessageContent(f"❌ Errore: {e}"),
            ),
        )
    finally:
        if png_path and os.path.exists(png_path):
            os.unlink(png_path)


async def _bref_scraper_job(context) -> None:
    """Job giornaliero alle 10:00 — scraping bref e insert su DB.
    Gira solo durante regular season e playoff.
    """
    try:
        from bref_scraper import run_scraper
        g = settings.load_globals()
        fase = g.get("fase", "")
        if fase not in ("regular-season-fa", "regular-season-deadline", "playoff"):
            logger.debug("Bref scraper saltato — fase: %s", fase)
            return
        stagione_corrente = int(g.get("stagione_corrente", 2026))
        stagione_bref = str(stagione_corrente + 1)
        n = run_scraper(stagione_bref)
        logger.info("Bref scraper: %d righe inserite (stagione %s)", n, stagione_bref)
        if n > 0:
            log_ch = g.get("log_channel_id_main")
            if log_ch:
                await context.bot.send_message(
                    chat_id=log_ch,
                    text=f"📊 Bref scraper: <b>{n}</b> giocatori aggiornati — stagione {stagione_bref}",
                    parse_mode="HTML",
                )
    except Exception as e:
        logger.error("Bref scraper fallito: %s", e)


async def _ping_healthcheck(context) -> None:
    url = os.environ.get("HEALTHCHECK_URL", "")
    if not url:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            await session.get(url, timeout=aiohttp.ClientTimeout(total=5))
        logger.debug("Healthcheck ping OK")
    except Exception as e:
        logger.warning("Healthcheck ping fallito: %s", e)


def main():
    db.init_db()
    db.migrate_db()
    logger.info("DB inizializzato e migrato.")

    token = _read_secret("BOT_TOKEN_FILE")
    app   = ApplicationBuilder().token(token).post_stop(post_stop).post_init(post_init).post_shutdown(backup_shutdown).build()

    # /annulla globale — group=-1 per intercettare prima di qualsiasi ConversationHandler
    app.add_handler(CommandHandler("annulla", cmd_annulla_globale), group=-1)

    for h in menu_handlers():
        app.add_handler(h)
    for h in trade_handlers():
        app.add_handler(h)
    for h in tagli_handlers():
        app.add_handler(h)
    for h in rookie_handlers():
        app.add_handler(h)
    for h in roster_handlers():
        app.add_handler(h)
    for h in myteam_handlers():
        app.add_handler(h)
    for h in team_diff_handlers():
        app.add_handler(h)
    for h in admin_panel_handlers():
        app.add_handler(h)
    for h in dev_player_handlers():
        app.add_handler(h)
    for h in palette_handlers():
        app.add_handler(h)
    for h in dpe_handlers():
        app.add_handler(h)

    for h in dev_handlers():
        app.add_handler(h)

    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("reboot", cmd_reboot))
    app.add_error_handler(error_handler)

    # Healthcheck ogni 5 minuti
    if os.environ.get("HEALTHCHECK_URL"):
        app.job_queue.run_repeating(_ping_healthcheck, interval=300, first=30)

    # Backup giornaliero ogni 12 ore
    from datetime import time as dtime
    for ora in [0, 12]:
        app.job_queue.run_daily(
            backup_giornaliero,
            time=dtime(ora, 0, tzinfo=ROME),
        )
    # Backup settimanale domenica alle 00:30
    app.job_queue.run_daily(
        backup_settimanale,
        time=dtime(0, 30, tzinfo=ROME),
        days=(6,),
    )
    # Scraper bref ogni mattina alle 10:00
    app.job_queue.run_daily(
        _bref_scraper_job,
        time=dtime(10, 0, tzinfo=ROME),
    )

    app.add_handler(TypeHandler(Update, _guest_handler), group=99)

    logger.info("Fantabasket Main Bot %s avviato.", BOT_VERSION)
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query", "edited_message",
                         "my_chat_member", "chat_member", "guest_message"],
    )


if __name__ == "__main__":
    main()

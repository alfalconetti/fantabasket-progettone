"""Comandi generali di IPanchinari: /start, guide, comandi dev."""
import os

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import config
from comune import e, ora


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team = config.squadra_del_gm(update.effective_user.id)
    testo = ("🪑 <b>IPanchinari</b> — panchine e quintetti. Guida completa: /guida\n\n"
             "<b>Panchina</b>: mandami qui le righe dei panchinari, una per riga, in ordine, come le scrivi sempre "
             "(soprannomi compresi). Un titolo, se vuoi, sopra, separato da una riga vuota. Ti mostro chi ho capito, "
             "confermi e la pubblico sul canale Panchinari con le tue righe. Vale per la prossima giornata, fino alla scadenza.\n"
             "/build_panchina — oppure componila coi bottoni\n"
             "/panchina — la panchina che hai mandato\n"
             "/quintetto — il tuo quintetto: cambialo o confermalo")
    if team:
        testo = f"Ciao, GM di <b>{e(team['nome'])}</b>.\n\n" + testo
    if config.is_admin(update.effective_user.id):
        testo += ("\n\n<b>Admin</b>\n/quintetto_admin SQUADRA — coi bottoni, o sotto i 5 titolari\n"
                  "/quintetti_import — tutte le squadre insieme\n/panchina_admin SQUADRA — coi bottoni, o sotto le righe\n"
                  "/stato [N] — conferme e panchine della giornata\nGuida admin: /guida_admin")
    await update.effective_message.reply_text(testo, parse_mode="HTML")


async def _manda_guida(update, context, file: str, titolo: str):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", file)
    try:
        with open(path, "rb") as f:
            await context.bot.send_document(chat_id=update.effective_user.id, document=f,
                                            filename=f"ipanchinari_{file}", caption=titolo)
    except Exception as err:
        await update.effective_message.reply_text(f"❌ Guida non inviata: {err} (hai mai scritto al bot in privato?)")


async def cmd_guida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _manda_guida(update, context, "guida_gm.md", "📖 Guida GM — IPanchinari")


async def cmd_guida_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    await _manda_guida(update, context, "guida_admin.md", "📖 Guida admin — IPanchinari")


def _is_dev(uid) -> bool:
    return bool(config.dev_id()) and int(uid) == config.dev_id()


async def cmd_guida_dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_dev(update.effective_user.id):
        await _manda_guida(update, context, "guida_dev.md", "🛠 Guida dev — IPanchinari")


async def cmd_dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    await update.effective_message.reply_text(
        "<b>Comandi dev — IPanchinari</b>\n\n/guida_dev — la guida tecnica (file .md)\n"
        "/dev_version — versione del bot\n/job_status — job programmati\n"
        "/dev_promemoria [SQUADRA] — il promemoria della prossima giornata, solo a te\n"
        "/dev_log [N] — ultime N righe di log in memoria (30)\n/dev_pg — connessione a PostgreSQL\n"
        "/reboot — riavvia il bot\n\nComandi admin: /guida_admin",
        parse_mode="HTML")


async def cmd_dev_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_dev(update.effective_user.id):
        await update.effective_message.reply_text(f"🪑 IPanchinari {config.versione()}")


async def cmd_job_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    jobs = [j for j in (context.job_queue.jobs() if context.job_queue else []) if j.next_t]
    righe = [f"• {j.name}: {ora(j.next_t)}" for j in sorted(jobs, key=lambda j: j.next_t)]
    await update.effective_message.reply_text("⏱ <b>Job</b>\n" + ("\n".join(e(r) for r in righe) or "nessuno"),
                                              parse_mode="HTML")


def get_handlers() -> list:
    return [
        CommandHandler("start", cmd_start),
        CommandHandler("guida", cmd_guida),
        CommandHandler("guida_admin", cmd_guida_admin),
        CommandHandler("guida_dev", cmd_guida_dev),
        CommandHandler("dev", cmd_dev),
        CommandHandler("dev_version", cmd_dev_version),
        CommandHandler("job_status", cmd_job_status),
    ]

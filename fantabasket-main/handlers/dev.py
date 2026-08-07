"""
Comandi riservati al dev (dev_id in globals.json).

Comandi:
  /dev              — lista comandi dev
  /dev_version      — versione corrente del bot
  /dev_log [N]      — ultime N righe di log in memoria (default 30)
  /dev_trade [N]    — ultime N trade approvate (default 10)
  /dev_pg           — stato connessione PostgreSQL
  /dev_roster <id>  — dump roster raw da DB
  /job_status       — job attivi nella JobQueue
  /broadcast <msg>  — messaggio a tutti i GM in privato
"""
import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
import settings
import teams as tm
from utils import format_dt, now_rome

logger = logging.getLogger(__name__)


def _is_dev(user_id: int) -> bool:
    return user_id == settings.dev_id()


def _send_chunked(chunks: list[str]):
    """Helper per costruire messaggi chunked."""
    testo = "\n".join(chunks)
    if len(testo) <= 4096:
        return [testo]
    parts = []
    chunk = ""
    for riga in chunks:
        candidato = chunk + ("\n" if chunk else "") + riga
        if len(candidato) > 4096:
            parts.append(chunk)
            chunk = riga
        else:
            chunk = candidato
    if chunk:
        parts.append(chunk)
    return parts


# ── /dev ──────────────────────────────────────────────────────────────────────

async def cmd_dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    testo = (
        "<b>Comandi dev</b>\n\n"
        "/dev_version — versione corrente del bot\n"
        "/dev_log [N] — ultime N righe di log in memoria (default 30)\n"
        "/dev_trade [N] — ultime N trade approvate (default 10)\n"
        "/dev_pg — stato connessione PostgreSQL\n"
        "/dev_roster &lt;team_id&gt; — dump roster raw da DB\n"
        "/job_status — job attivi nella JobQueue\n"
        "/broadcast &lt;testo&gt; — manda messaggio a tutti i GM\n"
        "/backup — backup manuale al canale log\n"
        "/reboot — riavvia il bot\n"
    )
    await update.effective_message.reply_text(testo, parse_mode="HTML")


# ── /dev_version ──────────────────────────────────────────────────────────────

async def cmd_dev_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    import bot as _bot
    ver = getattr(_bot, "BOT_VERSION", "sconosciuta")
    await update.effective_message.reply_text(
        f"🤖 <b>Fantabasket Main Bot {ver}</b>", parse_mode="HTML"
    )


# ── /dev_log ──────────────────────────────────────────────────────────────────

async def cmd_dev_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    try:
        n = int(context.args[0]) if context.args else 30
        if not 1 <= n <= 100:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("❌ N deve essere un intero tra 1 e 100.")
        return
    try:
        import log_buffer
        righe = list(log_buffer.buffer)[-n:]
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore accesso log buffer: {e}")
        return
    if not righe:
        await update.effective_message.reply_text("Nessuna riga di log in memoria.")
        return
    testo = "\n".join(righe)
    if len(testo) > 3800:
        testo = "...\n" + testo[-3800:]
    await update.effective_message.reply_text(f"<pre>{testo}</pre>", parse_mode="HTML")


# ── /dev_trade ────────────────────────────────────────────────────────────────

async def cmd_dev_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    try:
        n = int(context.args[0]) if context.args else 10
        if not 1 <= n <= 50:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("❌ N deve essere un intero tra 1 e 50.")
        return

    trade_list = db.get_ultime_trade_approvate(n)
    if not trade_list:
        await update.effective_message.reply_text("Nessuna trade approvata nel DB.")
        return

    righe = [f"🔄 <b>Ultime {len(trade_list)} trade approvate</b>\n"]
    for t in trade_list:
        data = format_dt(t["aggiornato"]) if t.get("aggiornato") else "—"
        righe.append(f"<b>{t['trade_ref']}</b> — {data}\n  {t.get('descrizione', '')}")

    for parte in _send_chunked(righe):
        await update.effective_message.reply_text(parte, parse_mode="HTML")


# ── /dev_pg ───────────────────────────────────────────────────────────────────

async def cmd_dev_pg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    try:
        result = db.ping()
        await update.effective_message.reply_text(
            f"✅ PostgreSQL OK — {result}", parse_mode="HTML"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ PostgreSQL KO: {e}")


# ── /dev_roster ───────────────────────────────────────────────────────────────

async def cmd_dev_roster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    if not context.args:
        await update.effective_message.reply_text("Uso: /dev_roster &lt;team_id&gt;", parse_mode="HTML")
        return
    team_id = context.args[0]
    roster = db.get_roster_team(team_id)
    if not roster:
        await update.effective_message.reply_text(f"Nessun giocatore per {team_id}.")
        return
    stagione = settings.stagione_corrente()
    righe = [f"🏀 <b>Roster {team_id}</b> — stagione {stagione}\n"]
    for r in roster:
        anni_res = r.get("anni_originali", "?")
        flag = r.get("tipo_contratto", "N")
        righe.append(
            f"{r['nome_common']} — {r.get('importo', '?')}M × {anni_res} [{flag}]"
        )
    for parte in _send_chunked(righe):
        await update.effective_message.reply_text(parte, parse_mode="HTML")


# ── /job_status ───────────────────────────────────────────────────────────────

async def cmd_job_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    jobs = context.application.job_queue.jobs()
    if not jobs:
        await update.effective_message.reply_text("Nessun job attivo.")
        return
    now = datetime.now(timezone.utc)
    righe = [f"⚙️ <b>Job attivi: {len(jobs)}</b>\n"]
    for job in sorted(jobs, key=lambda j: j.next_t or now):
        next_t = job.next_t
        if next_t:
            diff = next_t - now
            m = int(diff.total_seconds() // 60)
            s = int(diff.total_seconds() % 60)
            prossima = f"tra {m}m {s}s ({format_dt(next_t)})"
        else:
            prossima = "—"
        righe.append(f"• <code>{job.name or 'senza nome'}</code>\n  ↳ {prossima}")
    for parte in _send_chunked(righe):
        await update.effective_message.reply_text(parte, parse_mode="HTML")


# ── /broadcast ────────────────────────────────────────────────────────────────

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "Uso: /broadcast &lt;testo&gt;", parse_mode="HTML"
        )
        return
    testo = " ".join(context.args)
    tutti_team = tm.get_all_teams()
    ok = 0
    fail = 0
    falliti = []
    già_contattati: set[int] = set()
    for team in tutti_team:
        for gm_id in team.get("gm_ids", []):
            if gm_id in già_contattati:
                continue
            già_contattati.add(gm_id)
            try:
                await context.bot.send_message(chat_id=gm_id, text=testo, parse_mode="HTML")
                ok += 1
            except Exception as e:
                fail += 1
                falliti.append(f"  • {team['nome']} (id {gm_id}): {e}")

    riepilogo = (
        f"📢 <b>Broadcast completato</b>\n"
        f"✅ Inviati: {ok}\n"
        f"❌ Falliti: {fail}"
    )
    if falliti:
        riepilogo += "\n\n<b>Falliti:</b>\n" + "\n".join(falliti)

    g = settings.load_globals()
    log_ch = g.get("log_channel_id_main")
    if log_ch:
        try:
            await context.bot.send_message(chat_id=log_ch, text=riepilogo, parse_mode="HTML")
        except Exception:
            pass
    await update.effective_message.reply_text(riepilogo, parse_mode="HTML")


# ── handlers ──────────────────────────────────────────────────────────────────

def get_handlers() -> list:
    return [
        CommandHandler("dev",          cmd_dev),
        CommandHandler("dev_version",  cmd_dev_version),
        CommandHandler("dev_log",      cmd_dev_log),
        CommandHandler("dev_trade",    cmd_dev_trade),
        CommandHandler("dev_pg",       cmd_dev_pg),
        CommandHandler("dev_roster",   cmd_dev_roster),
        CommandHandler("job_status",   cmd_job_status),
        CommandHandler("broadcast",    cmd_broadcast),
    ]

"""
Scheduler — backup periodico e shutdown per Fantabasket Main Bot.
Backup: pg_dump + zip config → inviato su canale log (giornaliero) e admin group (settimanale).
"""
import io
import logging
import os
import subprocess
import zipfile
from datetime import datetime

import settings
from utils import ROME
from handlers.helpers import log_job_error

logger = logging.getLogger(__name__)


# ── backup ────────────────────────────────────────────────────────────────────

def _pg_dump() -> bytes:
    """Esegue pg_dump e restituisce i bytes del dump SQL."""
    db_url = os.environ.get("DATABASE_URL", "")
    # Ricava credenziali dai secrets se DATABASE_URL non è impostato
    if not db_url:
        pg_pass = open(os.environ.get("PG_PASSWORD_FILE", "/run/secrets/pg_password")).read().strip()
        db_url = f"postgresql://fantabasket:{pg_pass}@postgres:5432/fantabasket"

    result = subprocess.run(
        ["pg_dump", db_url],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump fallito: {result.stderr.decode()[:500]}")
    return result.stdout


def _crea_backup_zip(includi_aste_db: bool = False) -> bytes:
    """Crea uno zip in memoria con dump SQL + config + opzionalmente SQLite aste."""
    config_dir = os.environ.get("CONFIG_DIR", "/config")
    now = datetime.now(ROME)
    sql_data = _pg_dump()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"db/fantabasket_{now.strftime('%Y%m%d_%H%M')}.sql", sql_data)
        if includi_aste_db:
            aste_db_path = os.environ.get("ASTE_DB_PATH", "/data_aste/aste.db")
            if os.path.exists(aste_db_path):
                zf.write(aste_db_path, "db/aste.db")
        for fname in ["globals.json", "teams.json", "settings_main.json",
                      "settings_aste.json"]:
            fpath = os.path.join(config_dir, fname)
            if os.path.exists(fpath):
                zf.write(fpath, f"config/{fname}")
        tabelle_dir = os.path.join(config_dir, "tabelle")
        if os.path.isdir(tabelle_dir):
            for fname in os.listdir(tabelle_dir):
                fpath = os.path.join(tabelle_dir, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, f"config/tabelle/{fname}")
        loghi_dir = os.path.join(config_dir, "loghi")
        if os.path.isdir(loghi_dir):
            for fname in os.listdir(loghi_dir):
                fpath = os.path.join(loghi_dir, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, f"config/loghi/{fname}")
    return buf.getvalue()


async def invia_backup(context, chat_id: int, label: str, includi_aste_db: bool = False):
    """Invia il backup zip a una chat specifica."""
    try:
        data = _crea_backup_zip(includi_aste_db=includi_aste_db)
        now = datetime.now(ROME)
        filename = f"backup_progettone_{now.strftime('%Y%m%d_%H%M')}.zip"
        caption = f"💾 <b>Backup {label}</b> — {now.strftime('%d/%m/%Y %H:%M')}"
        if label == "settimanale":
            caption += (
                "\n\n📖 <a href=\"https://github.com/alfalconetti/"
                "fantabasket-progettone/blob/master/fantabasket-main/docs/"
                "emergency_recovery_progettone.md\">Emergency Recovery Guide</a>"
            )
        await context.bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(data),
            filename=filename,
            caption=caption,
            parse_mode="HTML",
        )
        logger.info("Backup inviato a chat_id=%d (%s)", chat_id, label)
    except Exception as e:
        logger.warning("Invio backup fallito a %d: %s", chat_id, e)


async def backup_giornaliero(context):
    """Backup giornaliero (solo PG) al canale log."""
    try:
        g = settings.load_globals()
        log_channel_id = g.get("log_channel_id_main")
        if log_channel_id:
            await invia_backup(context, log_channel_id, "giornaliero", includi_aste_db=False)
    except Exception as e:
        await log_job_error(context, "backup_giornaliero", e)


async def backup_settimanale(context):
    """Backup settimanale completo (PG + SQLite aste) al gruppo admin."""
    try:
        g = settings.load_globals()
        admin_group_id = g.get("admin_group_id")
        if admin_group_id:
            await invia_backup(context, admin_group_id, "settimanale", includi_aste_db=True)
    except Exception as e:
        await log_job_error(context, "backup_settimanale", e)


async def backup_shutdown(application):
    """Hook post_shutdown: backup completo allo spegnimento."""
    class _Ctx:
        bot = application.bot

    try:
        g = settings.load_globals()
        log_channel_id = g.get("log_channel_id_main")
        if log_channel_id:
            await invia_backup(_Ctx(), log_channel_id, "shutdown", includi_aste_db=True)
    except Exception as e:
        logger.warning("backup_shutdown fallito: %s", e)


async def sync_sheets_periodico(context) -> None:
    """Job ogni 2 ore — sync completo roster su Google Sheets come recovery."""
    try:
        import gas_client
        gas_client.sync_all(sincrono=False)  # fire and forget
        logger.info("sync_sheets_periodico: avviato")
    except Exception as e:
        logger.warning("sync_sheets_periodico: %s", e)


async def processa_coda_gas(context) -> None:
    """Job ogni 60s — se il bot aste ha accodato richieste di sync, aggiorna tutti i fogli."""
    try:
        import asyncio
        import database as db
        import gas_client
        max_id = db.gas_queue_max_id()
        if not max_id:
            return
        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(None, gas_client.sync_all, True)
        if ok:
            db.gas_queue_svuota_fino(max_id)
            logger.info("processa_coda_gas: sync completo eseguito (coda fino a id=%d)", max_id)
        else:
            logger.warning("processa_coda_gas: sync fallito, riprovo al prossimo giro")
    except Exception as e:
        logger.warning("processa_coda_gas: %s", e)


async def check_scadenza_diritti(context):
    """
    Job giornaliero alle 9:00. I diritti 2nd al secondo anno (draft =
    stagione_corrente - 1) scadono 10 giorni prima della trade deadline.
    - fino a 3 giorni prima: avviso informativo al gruppo admin
    - dal giorno della scadenza (e ogni giorno finché non confermato):
      avviso con bottone di conferma
    """
    try:
        import database as db
        from settings import load_globals
        info = db.get_diritti_scadenza_imminente(giorni=3)
        if not info:
            return
        admin_group_id = load_globals().get("admin_group_id")
        if not admin_group_id:
            return

        import datetime
        anno = info["anno_draft"]
        cache_key = f"diritti_alert_{anno}_{datetime.date.today().isoformat()}"
        if context.bot_data.get(cache_key):
            return
        context.bot_data[cache_key] = True

        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        scad  = info["scadenza"].strftime("%d/%m/%Y")
        dead  = info["deadline"].strftime("%d/%m/%Y")
        n     = info["n_diritti"]
        giorni = info["giorni_mancanti"]

        if giorni > 0:
            testo = (
                f"⏳ <b>Scadenza diritti 2nd round {anno}</b>\n\n"
                f"I {n} diritti 2nd del draft <b>{anno}</b> non firmati scadono il "
                f"<b>{scad}</b> (10 giorni prima della deadline del {dead}): "
                f"mancano <b>{giorni} giorni</b>.\n\n"
                f"Il giorno della scadenza arriverà il bottone di conferma."
            )
            kb = None
        else:
            testo = (
                f"⚠️ <b>Scadenza diritti 2nd round {anno}</b>\n\n"
                f"I diritti 2nd del draft <b>{anno}</b> sono scaduti il <b>{scad}</b> "
                f"(10 giorni prima della deadline del {dead}).\n"
                f"Diritti ancora da far scadere: <b>{n}</b>.\n\n"
                f"Conferma per marcarli come scaduti: i giocatori tornano free agent "
                f"e viene dato l'annuncio sul canale."
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                f"✅ Conferma scadenza diritti {anno}",
                callback_data=f"scadi_diritti:{anno}",
            )]])

        await context.bot.send_message(
            chat_id=admin_group_id, text=testo, parse_mode="HTML", reply_markup=kb
        )
        logger.info("check_scadenza_diritti: anno=%d scadenza=%s giorni=%d", anno, scad, giorni)
    except Exception as e:
        from handlers.helpers import log_job_error
        await log_job_error(context, "check_scadenza_diritti", e)


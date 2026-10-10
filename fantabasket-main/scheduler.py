"""
Scheduler — backup periodico e shutdown per Fantabasket Main Bot.
Backup unico e completo (PG + aste + config + secrets cifrati): canale log alle 00 e 12,
gruppo admin la domenica alle 00:30, canale log allo spegnimento, /backup (dev).
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
# Backup UNICO del sistema (guida di ripristino: docs/RECOVERY.md nel repo).
# Ogni zip è completo, qualunque sia il motivo (giornaliero, settimanale, shutdown, manuale):
#   db/fantabasket.sql      pg_dump --clean --if-exists: ripristinabile su DB vuoto o esistente
#   db/aste.db              SQLite del bot aste: copia verificata, WAL già consolidato (un solo file)
#   config/**               tutta la cartella config (globals, teams, settings, tabelle, loghi, csv...)
#   secrets.tar.gpg         SE presente: i secrets cifrati sul server con scripts/cifra_secrets.sh.
#                           Il bot non vede mai i secrets in chiaro: include solo il file cifrato.
#   MANIFEST.txt            data, versione, contenuto

SECRETS_CIFRATI = os.environ.get("SECRETS_CIFRATI", "/secrets_cifrati/secrets.tar.gpg")
_SALTA = {"__pycache__"}
_MAX_FILE = 20 * 1024 * 1024   # file di config oltre i 20 MB: saltati (limite Telegram 50 MB)


def _pg_dump() -> bytes:
    """Esegue pg_dump e restituisce i bytes del dump SQL."""
    db_url = os.environ.get("DATABASE_URL", "")
    # Ricava credenziali dai secrets se DATABASE_URL non è impostato
    if not db_url:
        pg_pass = open(os.environ.get("PG_PASSWORD_FILE", "/run/secrets/pg_password")).read().strip()
        db_url = f"postgresql://fantabasket:{pg_pass}@postgres:5432/fantabasket"

    result = subprocess.run(
        ["pg_dump", "--clean", "--if-exists", "--no-owner", db_url],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump fallito: {result.stderr.decode()[:500]}")
    return result.stdout


def _versione() -> str:
    """Ultima '## vX' del CHANGELOG (come bot.py, senza importare bot: è il __main__)."""
    import re
    try:
        testo = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "CHANGELOG.md"), encoding="utf-8").read()
        v = re.findall(r"^## (v[\w.]+)", testo, re.M)
        return v[-1] if v else "?"
    except Exception:
        return "?"


def info_secrets_cifrati() -> str | None:
    """Data del file secrets cifrato, se presente (per caption e /backup)."""
    if os.path.isfile(SECRETS_CIFRATI):
        return datetime.fromtimestamp(os.path.getmtime(SECRETS_CIFRATI), ROME).strftime("%d/%m/%Y")
    return None


def _snapshot_aste(path: str, tentativi: int = 3) -> bytes:
    """Copia coerente del DB del bot aste, che è in WAL e montato in sola lettura qui.
    Copia -wal e poi il DB in una cartella temporanea, li apre con sqlite (che riapplica
    il WAL), controlla l'integrità e ne fa un unico file con l'API di backup di sqlite.
    Se il bot aste scrive proprio durante la copia e il controllo fallisce, riprova."""
    import shutil, sqlite3, tempfile, time
    ultimo = None
    for _ in range(tentativi):
        with tempfile.TemporaryDirectory() as tmp:
            copia = os.path.join(tmp, "aste.db")
            if os.path.isfile(path + "-wal"):
                shutil.copyfile(path + "-wal", copia + "-wal")
            shutil.copyfile(path, copia)
            src = sqlite3.connect(copia)
            try:
                esito = src.execute("PRAGMA integrity_check").fetchone()[0]
                if esito != "ok":
                    ultimo = f"integrity_check: {esito}"
                    time.sleep(1)
                    continue
                finale = os.path.join(tmp, "aste_finale.db")
                dst = sqlite3.connect(finale)
                src.backup(dst)
                dst.close()
            finally:
                src.close()
            return open(finale, "rb").read()
    raise RuntimeError(ultimo or "copia non riuscita")


def _crea_backup_zip(includi_aste_db: bool = True) -> bytes:
    """Zip in memoria con tutto il necessario al ripristino (vedi intestazione).
    includi_aste_db resta per compatibilità: il backup è sempre completo."""
    config_dir = os.environ.get("CONFIG_DIR", "/config")
    now = datetime.now(ROME)
    sql_data = _pg_dump()
    contenuto, saltati = [], []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("db/fantabasket.sql", sql_data)
        contenuto.append(f"db/fantabasket.sql ({len(sql_data) // 1024} KB)")

        aste_db_path = os.environ.get("ASTE_DB_PATH", "/data_aste/aste.db")
        if os.path.isfile(aste_db_path):
            try:
                zf.writestr("db/aste.db", _snapshot_aste(aste_db_path))
                contenuto.append("db/aste.db (copia verificata, WAL incluso)")
            except Exception as e:
                logger.warning("Snapshot aste.db fallito: %s", e)
                contenuto.append(f"⚠️ db/aste.db NON incluso: {e}")

        for root, dirs, files in os.walk(config_dir):
            dirs[:] = sorted(d for d in dirs if d not in _SALTA)
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, config_dir)
                if os.path.getsize(fpath) > _MAX_FILE:
                    saltati.append(rel)
                    continue
                zf.write(fpath, f"config/{rel}")
        contenuto.append("config/ (cartella completa)")

        data_secrets = info_secrets_cifrati()
        if data_secrets:
            zf.write(SECRETS_CIFRATI, "secrets.tar.gpg")
            contenuto.append(f"secrets.tar.gpg (cifrato, del {data_secrets})")

        BOT_VERSION = _versione()
        zf.writestr("MANIFEST.txt", "\n".join(
            [f"Backup Fantabasket Progettone — {now.strftime('%d/%m/%Y %H:%M')}",
             f"Bot main {BOT_VERSION}", "Ripristino: docs/RECOVERY.md nel repo", "", *contenuto]
            + ([f"", "Saltati (troppo grandi):", *saltati] if saltati else [])) + "\n")
    return buf.getvalue()


async def invia_backup(context, chat_id: int, label: str, includi_aste_db: bool = True):
    """Invia il backup zip (sempre completo) a una chat specifica."""
    try:
        data = _crea_backup_zip()
        now = datetime.now(ROME)
        filename = f"backup_progettone_{now.strftime('%Y%m%d_%H%M')}.zip"
        data_secrets = info_secrets_cifrati()
        caption = (f"💾 <b>Backup {label}</b> — {now.strftime('%d/%m/%Y %H:%M')}\n"
                   f"DB + aste + config" + (f" + secrets cifrati (del {data_secrets})" if data_secrets
                                             else " · ⚠️ secrets non inclusi")
                   + "\n📖 Ripristino: <code>docs/RECOVERY.md</code> nel repo")
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
    """Backup completo al canale log (00:00 e 12:00)."""
    try:
        g = settings.load_globals()
        log_channel_id = g.get("log_channel_id_main")
        if log_channel_id:
            await invia_backup(context, log_channel_id, "giornaliero", includi_aste_db=False)
    except Exception as e:
        await log_job_error(context, "backup_giornaliero", e)


async def backup_settimanale(context):
    """Backup completo settimanale al gruppo admin (domenica 00:30)."""
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


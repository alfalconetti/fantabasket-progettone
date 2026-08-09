"""
Job periodico che controlla le aste scadute e le chiude,
e invia notifiche prima della scadenza ai watcher.
Include healthcheck ping e backup periodico.
"""
import io
import logging
import os
import zipfile
from datetime import datetime, timedelta, timezone

import database as db
import utils
import settings
from handlers.firma import chiedi_anni

logger = logging.getLogger(__name__)

HEALTHCHECK_URL = os.environ.get("HEALTHCHECK_URL", "")


async def check_scadenze(context):
    try:
        from handlers.helpers import aggiorna_canale
        import teams as tm_sched
        now = datetime.now(timezone.utc)
        minuti = settings.notifica_minuti_scadenza()
        soglia = now + timedelta(minutes=minuti)
        aste = db.get_aste_aperte()

        for asta in aste:
            scade_at = datetime.fromisoformat(asta["scade_at"])

            if now >= scade_at:
                logger.info("Chiusura asta id=%d giocatore=%s", asta["id"], asta["giocatore"])
                db.chiudi_asta(asta["id"], now.isoformat())

                if asta["offerente_team_id"]:
                    await aggiorna_canale(context, asta["id"])
                    await chiedi_anni(context, asta["id"])
                else:
                    db.concludi_asta(asta["id"])
                    await aggiorna_canale(context, asta["id"])
                    logger.info("Asta id=%d chiusa senza offerte", asta["id"])
                continue

            if now < scade_at <= soglia:
                if not db.notifica_15min_inviata(asta["id"]):
                    db.segna_notifica_15min(asta["id"])
                    watchers = db.get_watchers(asta["id"])
                    if watchers:
                        teams_map = {t["id"]: t["nome"] for t in tm_sched.get_all_teams()}
                        vincitore = teams_map.get(asta["offerente_team_id"], "—") if asta["offerente_team_id"] else "nessuno"
                        testo = (
                            f"⏰ <b>{minuti} minuti alla scadenza!</b>\n"
                            f"🏀 <b>{asta['giocatore']}</b>\n"
                            f"Offerta attuale: <b>{asta['offerta_corrente']}M — {vincitore}</b>"
                        )
                        for gm_id in watchers:
                            try:
                                await context.bot.send_message(chat_id=gm_id, text=testo, parse_mode="HTML")
                            except Exception as e:
                                logger.warning("notifica scadenza a %d fallita: %s", gm_id, e)
                        logger.info("Notifica scadenza inviata per asta id=%d a %d watcher", asta["id"], len(watchers))
    except Exception as e:
        from handlers.helpers import log_job_error
        await log_job_error(context, "check_scadenze", e)


async def ping_healthcheck(context):
    """Pinga healthchecks.io ogni 5 minuti per segnalare che il bot è vivo."""
    if not HEALTHCHECK_URL:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            await session.get(HEALTHCHECK_URL, timeout=aiohttp.ClientTimeout(total=5))
        logger.debug("Healthcheck ping OK")
    except Exception as e:
        logger.warning("Healthcheck ping fallito: %s", e)


def _crea_backup_zip() -> bytes:
    """Crea uno zip in memoria con DB + config."""
    db_path = os.environ.get("DB_PATH", "/data/aste.db")
    config_dir = os.path.dirname(os.environ.get("GLOBALS_PATH", "/config/globals.json"))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(db_path):
            zf.write(db_path, "data/aste.db")
        for fname in ["globals.json", "teams.json", "settings.json", "fa_players.csv"]:
            fpath = os.path.join(config_dir, fname)
            if os.path.exists(fpath):
                zf.write(fpath, f"config/{fname}")
    return buf.getvalue()


async def invia_backup(context, chat_id: int, label: str):
    """Invia il backup zip a una chat specifica."""
    try:
        data = _crea_backup_zip()
        now = datetime.now(utils.ROME)
        filename = f"backup_aste_{now.strftime('%Y%m%d_%H%M')}.zip"
        caption = f"💾 <b>Backup {label}</b> — {now.strftime('%d/%m/%Y %H:%M')}"
        if label == "settimanale":
            caption += "\n\n📖 <a href=\"https://github.com/alfalconetti/fantabasket_aste/blob/main/docs/emergency_recovery.md\">Emergency Recovery Guide</a>"
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
    """Invia backup 2 volte al giorno al canale log."""
    try:
        log_channel_id = utils.get_log_channel_id()
        if log_channel_id:
            await invia_backup(context, log_channel_id, "giornaliero")
    except Exception as e:
        from handlers.helpers import log_job_error
        await log_job_error(context, "backup_giornaliero", e)


async def backup_settimanale(context):
    """Invia backup settimanale al gruppo admin."""
    try:
        admin_group_id = utils.get_admin_group_id()
        if admin_group_id:
            await invia_backup(context, admin_group_id, "settimanale")
    except Exception as e:
        from handlers.helpers import log_job_error
        await log_job_error(context, "backup_settimanale", e)


async def backup_shutdown(application):
    """Hook post_shutdown: backup automatico al docker compose down."""
    class _Ctx:
        bot = application.bot
    try:
        log_channel_id = utils.get_log_channel_id()
        if log_channel_id:
            await invia_backup(_Ctx(), log_channel_id, "shutdown")
    except Exception as e:
        logger.warning("backup_shutdown fallito: %s", e)


async def check_cap_stagionale(context):
    """
    Job giornaliero alle 13:00 — controlla che la somma dei cap liberi
    sia sufficiente a coprire la riduzione di cap al passaggio offseason→regular season.
    Gira solo durante le fasi offseason.
    """
    try:
        fase = utils.load_globals().get("fase", "")
        if not fase.startswith("offseason"):
            logger.debug("check_cap_stagionale saltato — fase: %s", fase)
            return
        import teams as tm
        s = settings.get()
        cap_offseason = s["cap_offseason"]
        cap_regular   = s["cap_regular"]
        n_teams       = settings.numero_teams()
        delta_per_team = cap_offseason - cap_regular

        tutti_team = tm.get_all_teams()

        cap_occupato_totale = 0
        righe_sforanti = []

        import pg_client as _pg
        stagione = utils.load_globals().get("stagione_corrente", "2025")

        for team in tutti_team:
            cap_pen = team.get("cap_penalizzato", 0)
            if _pg.pg_disponibile():
                cap_occ = _pg.get_cap_contratti(team["id"]) + _pg.get_impatto_taglio(team["id"], stagione) + cap_pen
            else:
                cap_occ = cap_offseason - team.get("cap_disponibile", 0)
            cap_occupato_totale += cap_occ
            if cap_occ > cap_regular:
                righe_sforanti.append(f"  ⚠️ {team['nome']}: {cap_occ}M (sfora di {cap_occ - cap_regular}M)")

        limite_totale = n_teams * cap_regular
        margine = limite_totale - cap_occupato_totale

        emoji = "✅" if margine >= 0 else "⚠️"
        testo = (
            f"{emoji} <b>Check cap stagionale</b>\n\n"
            f"Cap occupato totale: <b>{cap_occupato_totale}M</b>\n"
            f"Limite RS totale: <b>{limite_totale}M</b> ({n_teams} × {cap_regular}M)\n"
            f"Margine aggregato: <b>{margine:+d}M</b>\n"
        )
        if righe_sforanti:
            testo += "\n⚠️ <b>Team già oltre il limite RS:</b>\n" + "\n".join(righe_sforanti)
        if margine < 0:
            testo += (
                f"\n\n🔴 <b>Attenzione</b>: il cap occupato totale supera il limite regular season "
                f"di <b>{abs(margine)}M</b> — necessari tagli o trade prima dell'inizio RS."
            )

        log_channel_id = utils.get_log_channel_id()
        if log_channel_id:
            await context.bot.send_message(chat_id=log_channel_id, text=testo, parse_mode="HTML")
        logger.info("check_cap_stagionale: cap_libero=%d soglia=%d margine=%d",
                    cap_liberi_totale, soglia, margine)
    except Exception as e:
        from handlers.helpers import log_job_error
        await log_job_error(context, "check_cap_stagionale", e)


async def pulizia_anticipati_scaduti(context):
    """
    Job giornaliero — pulisce cap/slot anticipati scaduti e notifica gruppo admin.
    Se il cap reale del team è negativo dopo la pulizia, avvisa urgentemente.
    """
    try:
        from handlers.helpers import log_job_error as _lje
        import pg_client
        import teams as tm
        import database as db_aste
        if not pg_client.pg_disponibile():
            return
        scaduti = pg_client.get_anticipati_scaduti()
        if not scaduti:
            return
        admin_group_id = utils.load_globals().get("admin_group_id")
        stagione = utils.load_globals().get("stagione_corrente", "2025")
        for row in scaduti:
            team_id = row["team_id"]
            tipo    = row.get("tipo", "cap")
            importo = row.get("importo") or row.get("quantita", 0)
            team    = tm.get_team_by_id(team_id)
            nome    = team["nome"] if team else team_id
            cap_pen = (team.get("cap_penalizzato", 0) if team else 0)
            if tipo == "cap":
                pg_client.reset_cap_anticipato(team_id)
                cap_occ = (pg_client.get_cap_contratti(team_id)
                           + pg_client.get_impatto_taglio(team_id, stagione)
                           + cap_pen)
                cap_virt = db_aste.get_cap_virtuale(team_id)
                cap_libero_reale = settings.cap_limite() - cap_occ - cap_virt
                ha_problema = cap_libero_reale < 0
                emoji = "🚨" if ha_problema else "🔄"
                testo = f"{emoji} <b>Cap anticipato scaduto</b>\nTeam: <b>{nome}</b> (+{importo}M)"
                if ha_problema:
                    testo += f"\n⚠️ Il team è ora in negativo di <b>{abs(cap_libero_reale)}M</b> — verifica immediatamente."
            else:
                pg_client.reset_slot_anticipato(team_id)
                testo = f"🔄 <b>Slot anticipato scaduto</b>\nTeam: <b>{nome}</b> (+{importo} slot)"
            if admin_group_id:
                try:
                    await context.bot.send_message(
                        chat_id=admin_group_id, text=testo, parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning("notifica scadenza anticipato: %s", e)
        logger.info("pulizia_anticipati_scaduti: %d record rimossi", len(scaduti))
    except Exception as e:
        from handlers.helpers import log_job_error as _lje2
        await _lje2(context, "pulizia_anticipati_scaduti", e)

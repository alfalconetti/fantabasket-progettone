"""
RFA dichiarati (v58, bot principale v3.11).

La dichiarazione si fa nel bot principale durante la fase dei rinnovi (tabella
rfa_dichiarati su PostgreSQL). Qui:
  - pubblica_asta_rfa(): apertura e pubblicazione sul canale di un'asta RFA (usata da
    /nuova_rfa e dal job);
  - job_rfa() ogni 5 minuti:
      1. il proprietario di un'asta RFA in corso è la squadra che ha il contratto x0 del
         giocatore: se è stato scambiato, l'asta passa alla nuova squadra (cap, pareggio);
      2. nella fase RFA apre da solo le aste dei dichiarati che non ce l'hanno ancora.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import pg_client
import settings
import teams as tm
import utils
from handlers.helpers import aggiorna_canale, log_job_error, log_warn, teams_map

logger = logging.getLogger(__name__)

FASE_RFA = "offseason-rfa"


async def pubblica_asta_rfa(bot, team_id: str, giocatore: str, vecchio_compenso: int,
                            giocatore_id: int | None, aperta_da: str | None) -> tuple[int, datetime]:
    """Crea l'asta RFA e la pubblica sul canale. Restituisce (asta_id, scadenza)."""
    now = datetime.now(timezone.utc)
    scade = now + timedelta(hours=settings.durata_asta_ore())
    asta_id = db.crea_asta(
        tipo="RFA", giocatore=giocatore, squadra_proprietaria=team_id,
        vecchio_compenso=vecchio_compenso, creata_at=now.isoformat(), scade_at=scade.isoformat(),
        stagione=utils.get_stagione_corrente(), giocatore_id=giocatore_id,
    )
    testo = utils.build_canale_message(db.get_asta(asta_id), [], teams_map(), aperta_da=aperta_da)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏀 Offri", url=f"https://t.me/{bot.username}?start=offri_{asta_id}"),
        InlineKeyboardButton("🔔 Segui", callback_data=f"watch:{asta_id}"),
    ]])
    msg = await bot.send_message(chat_id=utils.get_channel_id(), text=testo, parse_mode="HTML",
                                 reply_markup=keyboard)
    db.set_canale_msg_id(asta_id, msg.message_id)
    return asta_id, scade


async def _allinea_proprietari(context) -> None:
    """Aste RFA in corso: proprietario = squadra del contratto finito (x0) del giocatore.
    Solo contratti x0: il contratto nuovo di chi vince (in corso) non conta mai."""
    stagione = utils.get_stagione_corrente()
    for a in db.aste_rfa_in_corso():
        gid = pg_client.id_giocatore_asta(a)
        team = pg_client.squadra_x0(gid, stagione)
        if not team or team == a["squadra_proprietaria"]:
            continue
        prima = a["squadra_proprietaria"]
        db.set_squadra_proprietaria(a["id"], team)
        await aggiorna_canale(context, a["id"])
        nomi = teams_map()
        await log_warn(context, f"RFA <b>{a['giocatore']}</b> (asta #{a['id']}): diritti passati da "
                                f"{nomi.get(prima, prima)} a {nomi.get(team, team)} con una trade")
        if a["offerente_team_id"] == team:
            await log_warn(context, f"⚠️ RFA <b>{a['giocatore']}</b> (asta #{a['id']}): la squadra che ora ha i "
                                    f"diritti è anche quella in testa all'asta — da verificare a mano.")


async def _apri_dichiarati(context) -> None:
    stagione = utils.get_stagione_corrente()
    for r in pg_client.rfa_dichiarati(stagione):
        if db.rfa_giocatore_stagione(r["giocatore_id"], r["nome_common"], stagione):
            continue
        if db.giocatore_gia_in_asta(r["nome_common"]):
            continue
        asta_id, scade = await pubblica_asta_rfa(context.bot, r["team_id"], r["nome_common"], int(r["importo"]),
                                                 r["giocatore_id"], "il bot (RFA dichiarato)")
        logger.info("RFA dichiarato all'asta: asta_id=%d giocatore=%s proprietario=%s compenso=%s",
                    asta_id, r["nome_common"], r["team_id"], r["importo"])
        team = tm.get_team_by_id(r["team_id"])
        for gm in (team or {}).get("gm_ids", []):
            try:
                db.add_watch(asta_id, int(gm))
                await context.bot.send_message(
                    chat_id=int(gm), parse_mode="HTML",
                    text=(f"🔴 L'asta RFA di <b>{r['nome_common']}</b> è aperta (scade {utils.format_dt(scade.isoformat())}).\n"
                          f"Alla fine potrai pareggiare l'offerta vincente; la segui in automatico."))
            except Exception as e:
                logger.warning("Avviso RFA al GM %s: %s", gm, e)
        await asyncio.sleep(3)     # limiti di Telegram sui messaggi nel canale


async def job_rfa(context) -> None:
    if not pg_client.pg_disponibile():
        return
    try:
        await _allinea_proprietari(context)
        if utils.load_globals().get("fase") == FASE_RFA:
            await _apri_dichiarati(context)
    except Exception as e:
        await log_job_error(context, "job_rfa", e)

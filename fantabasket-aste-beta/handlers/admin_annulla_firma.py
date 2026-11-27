"""
/annulla_firma_asta ID [ore] (admin, v7.38.0; Luca 27/11: «posso annullare una firma e contestualmente si riapre
l'asta»): la firma di un'asta FA conclusa si annulla e l'asta torna aperta, con l'offerta in testa di prima e una
nuova scadenza (18 ore se non si dice). Nel database della lega spariscono contratto e movimento della firma, le
dichiarazioni di ruolo della firma si chiudono e il ruolo dichiarato dopo si toglie (pg_client.annulla_firma_asta_pg);
nel bot aste la riga del contratto sparisce e l'asta riparte (database.annulla_firma). Prima un'anteprima con gli
effetti, poi la conferma. Non si può se dopo la firma il giocatore ha avuto altri movimenti o è stato dichiarato RFA.
Solo aste FA: una RFA si porta dietro il cap liberato al proprietario e il pareggio, e si corregge a mano.
"""
import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.ext import CallbackQueryHandler, CommandHandler

import database as db
import pg_client
import teams as tm
import utils
from handlers.admin_comune import is_admin, _admin_label

logger = logging.getLogger(__name__)
ORE = 18


def _controlla(asta_id: int) -> tuple[dict | None, dict | None, str | None]:
    """(asta, firma su PG, perché no)."""
    asta = db.get_asta(asta_id)
    if not asta:
        return None, None, "asta non trovata"
    asta = dict(asta)
    if asta["stato"] != "CONCLUSA" or not asta.get("team_firma"):
        return asta, None, f"l'asta è {asta['stato'].lower()}, non firmata"
    if asta["tipo"] != "FA":
        return asta, None, "è un'asta RFA: si porta dietro il cap liberato al proprietario e il pareggio, va corretta a mano"
    gid = pg_client.id_giocatore_asta(asta)
    f = pg_client.firma_asta_pg(gid, asta["team_firma"]) if gid else None
    if not f:
        return asta, None, "non trovo la firma nel database della lega"
    return asta, f, f["perche_no"]


async def cmd_annulla_firma_asta(update, context):
    msg = update.effective_message
    if not is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Non sei autorizzato.")
        return
    a = context.args or []
    if not a or not a[0].isdigit() or (len(a) > 1 and not a[1].isdigit()):
        await msg.reply_text("Uso: /annulla_firma_asta ID [ore] — l'ID è quello di /all_aste conclusa; l'asta si riapre "
                             f"con scadenza tra le ore dette (di solito {ORE}).")
        return
    asta_id, ore = int(a[0]), int(a[1]) if len(a) > 1 else ORE
    asta, f, no = _controlla(asta_id)
    if no:
        await msg.reply_text(f"❌ Non si può annullare: {no}.")
        return
    team = tm.get_team_by_id(asta["team_firma"]) or {"nome": asta["team_firma"]}
    await msg.reply_text(
        f"↩️ <b>Annullare la firma di {asta['giocatore']}?</b>\n{team['nome']} · {f['importo']}M × {f['anni_originali']}\n\n"
        f"• via contratto e movimento della firma (torna free agent), chiuse le dichiarazioni di ruolo della firma\n"
        f"• l'asta torna <b>aperta</b> con l'offerta in testa di prima ({asta['offerta_corrente']}M di {team['nome']}) "
        f"e scade tra <b>{ore} ore</b>\n• messaggio sul canale, avviso al GM e a chi segue l'asta, foglio aggiornato; "
        f"nel registro resta la riga",
        parse_mode="HTML", reply_markup=K([[B("✅ Annulla la firma e riapri", callback_data=f"annfa:{asta_id}:{ore}"),
                                            B("❌ No", callback_data="admin_noop")]]))


async def cb_annulla_firma_asta(update, context):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    _, asta_id, ore = q.data.split(":")
    asta_id, ore = int(asta_id), int(ore)
    asta, f, no = _controlla(asta_id)
    if no:
        await q.edit_message_text(f"❌ Non si può annullare: {no}.")
        return
    team_id = asta["team_firma"]
    try:
        pg_client.annulla_firma_asta_pg(pg_client.id_giocatore_asta(asta), team_id)
    except ValueError as e:
        await q.edit_message_text(f"❌ Non si può annullare: {e}.")
        return
    scadenza = datetime.now(timezone.utc) + timedelta(hours=ore)
    for nome in (f"firma_auto_{asta_id}", f"pareggio_auto_{asta_id}", f"notif15_{asta_id}"):
        for j in context.job_queue.get_jobs_by_name(nome) if context.job_queue else []:
            j.schedule_removal()
    db.annulla_firma(asta_id, scadenza.isoformat())
    chi = _admin_label(q.from_user)
    from registro import segna_asta
    await segna_asta(context.bot, q.from_user, "admin", "firma da asta annullata, asta riaperta", asta,
                     prima=f"{f['importo']}M × {f['anni_originali']}", dopo=f"aperta, scade {utils.format_dt(scadenza.isoformat())}")
    team = tm.get_team_by_id(team_id) or {"nome": team_id, "gm_ids": []}
    main = utils.load_globals().get("main_channel_id")
    if main:
        try:
            await context.bot.send_message(chat_id=main, parse_mode="HTML",
                                           text=f"↩️ <b>Firma annullata</b>: <b>{asta['giocatore']}</b> non è più di "
                                                f"<b>{team['nome']}</b> ({f['importo']}M × {f['anni_originali']}); l'asta si riapre.\n"
                                                f"<i>Corretto da {chi}</i>")
        except Exception as e:
            logger.warning("Annuncio firma annullata: %s", e)
    from handlers.admin_riapri import _notifica_riapertura
    await _notifica_riapertura(context, asta, scadenza, chi)
    for gm in team.get("gm_ids", []):
        try:
            await context.bot.send_message(chat_id=int(gm), parse_mode="HTML",
                                           text=f"🛠 Un admin ha annullato la firma di <b>{asta['giocatore']}</b>: l'asta è di "
                                                f"nuovo aperta, la tua offerta di {asta['offerta_corrente']}M è in testa.")
        except Exception as e:
            logger.warning("Avviso al GM: %s", e)
    pg_client.accoda_sync_gas(f"firma annullata {asta['giocatore']} ({team_id})")
    await q.edit_message_text(f"✅ Firma di <b>{asta['giocatore']}</b> annullata: asta riaperta, scade "
                              f"{utils.format_dt(scadenza.isoformat())}.", parse_mode="HTML")


def get_handlers() -> list:
    return [CommandHandler("annulla_firma_asta", cmd_annulla_firma_asta),
            CallbackQueryHandler(cb_annulla_firma_asta, pattern=r"^annfa:\d+:\d+$")]

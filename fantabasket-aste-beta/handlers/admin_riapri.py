"""
Aste, scadenze: /estendi_asta, /sposta_asta e /riapri_asta (da chiusa, pareggio o annullata
di nuovo aperta; con cap negativo chiede conferma: riapri_cap:, riapri_annullata:).
"""
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import teams as tm
import utils
from handlers.helpers import log_warn as _log_warn
from handlers.admin_comune import is_admin, _admin_label, _richiedi_conferma_cap_negativo

logger = logging.getLogger(__name__)


# ── /estendi_asta ─────────────────────────────────────────────────────────────

async def estendi_asta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sposta la scadenza di un'asta in avanti di N ore.
    Solo admin. Uso: /estendi_asta <asta_id> <ore>
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Uso: /estendi_asta &lt;asta_id&gt; &lt;ore&gt;\nEsempio: /estendi_asta 42 6",
            parse_mode="HTML",
        )
        return

    try:
        asta_id = int(context.args[0])
        ore     = int(context.args[1])
        if ore == 0:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            "❌ Parametri non validi. Le ore devono essere un intero diverso da zero "
            "(negativo per accorciare, es. -3)."
        )
        return

    asta = db.get_asta(asta_id)
    if not asta:
        await update.effective_message.reply_text("❌ Asta non trovata.")
        return
    if asta["stato"] not in ("APERTA", "CHIUSA", "PAREGGIO"):
        await update.effective_message.reply_text(
            f"❌ L'asta <b>{asta['giocatore']}</b> è in stato <b>{asta['stato']}</b>: "
            f"non è possibile estenderla.",
            parse_mode="HTML",
        )
        return

    vecchio = datetime.fromisoformat(asta["scade_at"])
    nuovo   = vecchio + timedelta(hours=ore)

    if nuovo <= datetime.now(timezone.utc):
        await update.effective_message.reply_text(
            f"❌ La nuova scadenza ({utils.format_dt(nuovo.isoformat())}) sarebbe nel passato. "
            f"Usa un valore negativo più piccolo o /sposta_asta per impostare una scadenza precisa."
        )
        return
    db.set_scade_at(asta_id, nuovo.isoformat())
    admin_label = _admin_label(update.effective_user)
    azione = f"estesa di {ore}h" if ore > 0 else f"accorciata di {abs(ore)}h"

    from handlers.helpers import aggiorna_canale, log_warn as _lw
    await aggiorna_canale(context, asta_id)
    from registro import segna_asta
    await segna_asta(context.bot, update.effective_user, "admin", f"asta {azione}", asta,
                     prima=f"scade {utils.format_dt(asta['scade_at'])}", dopo=f"scade {utils.format_dt(nuovo.isoformat())}")

    channel_id = utils.get_channel_id()
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=(
                f"⏰ Scadenza asta <b>{asta['giocatore']}</b> {azione} da <b>{admin_label}</b>.\n"
                f"Nuova scadenza: <b>{utils.format_dt(nuovo.isoformat())}</b>"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await _lw(context, f"Annuncio estensione canale fallito: {e}")

    await update.effective_message.reply_text(
        f"✅ Asta <b>{asta['giocatore']}</b> {azione}.\n"
        f"Nuova scadenza: <b>{utils.format_dt(nuovo.isoformat())}</b>",
        parse_mode="HTML",
    )
    logger.info("estendi_asta: asta_id=%d ore=%d nuova_scadenza=%s admin=%d",
                asta_id, ore, nuovo.isoformat(), update.effective_user.id)


# ── /sposta_asta ──────────────────────────────────────────────────────────────

async def sposta_asta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Imposta una scadenza precisa per un'asta.
    Solo admin. Uso: /sposta_asta <asta_id> <YYYY-MM-DDTHH:MM>
    La data/ora si intende in ora di Roma (Europe/Rome).
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Uso: /sposta_asta &lt;asta_id&gt; &lt;YYYY-MM-DDTHH:MM&gt;\n"
            "Esempio: /sposta_asta 42 2026-07-15T20:00\n"
            "L'orario si intende in ora di Roma.",
            parse_mode="HTML",
        )
        return

    try:
        asta_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso.")
        return

    try:
        from zoneinfo import ZoneInfo
        rome = ZoneInfo("Europe/Rome")
        nuovo_naive = datetime.fromisoformat(context.args[1])
        nuovo = nuovo_naive.replace(tzinfo=rome).astimezone(timezone.utc)
    except Exception:
        await update.effective_message.reply_text(
            "❌ Formato data non valido. Usa: <code>YYYY-MM-DDTHH:MM</code>",
            parse_mode="HTML",
        )
        return

    if nuovo <= datetime.now(timezone.utc):
        await update.effective_message.reply_text("❌ La nuova scadenza deve essere nel futuro.")
        return

    asta = db.get_asta(asta_id)
    if not asta:
        await update.effective_message.reply_text("❌ Asta non trovata.")
        return
    if asta["stato"] not in ("APERTA", "CHIUSA", "PAREGGIO"):
        await update.effective_message.reply_text(
            f"❌ L'asta <b>{asta['giocatore']}</b> è in stato <b>{asta['stato']}</b>: "
            f"non è possibile spostarla.",
            parse_mode="HTML",
        )
        return

    db.set_scade_at(asta_id, nuovo.isoformat())
    admin_label = _admin_label(update.effective_user)

    from handlers.helpers import aggiorna_canale, log_warn as _lw
    await aggiorna_canale(context, asta_id)
    from registro import segna_asta
    await segna_asta(context.bot, update.effective_user, "admin", "scadenza dell'asta spostata", asta,
                     prima=f"scade {utils.format_dt(asta['scade_at'])}", dopo=f"scade {utils.format_dt(nuovo.isoformat())}")

    channel_id = utils.get_channel_id()
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=(
                f"⏰ Scadenza asta <b>{asta['giocatore']}</b> spostata da <b>{admin_label}</b>.\n"
                f"Nuova scadenza: <b>{utils.format_dt(nuovo.isoformat())}</b>"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await _lw(context, f"Annuncio spostamento canale fallito: {e}")

    await update.effective_message.reply_text(
        f"✅ Scadenza asta <b>{asta['giocatore']}</b> spostata a "
        f"<b>{utils.format_dt(nuovo.isoformat())}</b>",
        parse_mode="HTML",
    )
    logger.info("sposta_asta: asta_id=%d nuova_scadenza=%s admin=%d",
                asta_id, nuovo.isoformat(), update.effective_user.id)


# ── /riapri_asta ──────────────────────────────────────────────────────────────

async def riapri_asta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Riporta un'asta in stato CHIUSA o PAREGGIO allo stato APERTA,
    con una nuova scadenza di N ore da adesso (default 18h).
    Cancella i job di firma/pareggio pendenti e notifica nel canale.
    Solo admin. Uso: /riapri_asta <asta_id> [ore]
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Uso: /riapri_asta &lt;asta_id&gt; [ore]\n"
            "Esempio: /riapri_asta 42 6 — riapre con scadenza tra 6 ore\n"
            "Default: 18 ore se non specificato.",
            parse_mode="HTML",
        )
        return

    try:
        asta_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(
            "❌ Serve l'ID numerico dell'asta. Usa /all_aste chiusa per vedere gli ID."
        )
        return

    ore = 18
    if len(context.args) > 1:
        try:
            ore = int(context.args[1])
            if ore <= 0:
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text("❌ Le ore devono essere un intero positivo.")
            return

    asta = db.get_asta(asta_id)
    if not asta:
        await update.effective_message.reply_text("❌ Asta non trovata.")
        return
    if asta["stato"] not in ("CHIUSA", "PAREGGIO", "ANNULLATA"):
        await update.effective_message.reply_text(
            f"❌ L'asta <b>{asta['giocatore']}</b> è in stato <b>{asta['stato']}</b>: "
            f"/riapri_asta funziona solo su aste CHIUSA, PAREGGIO o ANNULLATA.",
            parse_mode="HTML",
        )
        return

    # Se ANNULLATA chiede conferma prima di procedere
    if asta["stato"] == "ANNULLATA":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ Sì, riapri",
                callback_data=f"riapri_annullata:{asta_id}:{ore}"
            ),
            InlineKeyboardButton("❌ Annulla", callback_data="admin_noop"),
        ]])
        await update.effective_message.reply_text(
            f"⚠️ L'asta per <b>{asta['giocatore']}</b> è stata <b>annullata</b>.\n"
            f"Sei sicuro di volerla riaprire con scadenza tra <b>{ore}h</b>?",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    # cancella job pendenti
    for nome in [f"firma_auto_{asta_id}", f"pareggio_auto_{asta_id}", f"notif15_{asta_id}"]:
        for j in context.job_queue.get_jobs_by_name(nome):
            j.schedule_removal()

    admin_label = _admin_label(update.effective_user)

    # check cap virtuale negativo — se l'offerta vincente sforerebbe il cap, chiede conferma al gruppo admin
    if asta["offerente_team_id"]:
        cap_disp, cap_virt, cap_post = _cap_virtuale_post_riapertura(dict(asta))
        if cap_post > cap_disp:
            admin_group_id = utils.get_admin_group_id()
            if not admin_group_id:
                await update.effective_message.reply_text(
                    "❌ Riaprendo questa asta il cap virtuale di una squadra andrebbe in negativo, "
                    "ma <code>admin_group_id</code> non è configurato in globals.json. "
                    "Impossibile richiedere conferma.",
                    parse_mode="HTML",
                )
                return
            await _richiedi_conferma_cap_negativo(
                context, dict(asta), ore, admin_group_id, admin_label,
                cap_disp, cap_virt, cap_post,
                "riapri_cap"
            )
            await update.effective_message.reply_text(
                f"⚠️ Richiesta di conferma inviata al gruppo admin.\n"
                f"Riaprendo l'asta di <b>{asta['giocatore']}</b> il cap virtuale di una squadra "
                f"andrebbe in negativo. Un admin dal gruppo deve confermare per procedere.",
                parse_mode="HTML",
            )
            return

    nuova_scadenza = datetime.now(timezone.utc) + timedelta(hours=ore)
    db.riapri_asta(asta_id, nuova_scadenza.isoformat())
    from registro import segna_asta
    await segna_asta(context.bot, update.effective_user, "admin", "asta riaperta", asta, prima=asta["stato"].lower(),
                     dopo=f"aperta, scade {utils.format_dt(nuova_scadenza.isoformat())}")
    await _notifica_riapertura(context, dict(asta), nuova_scadenza, admin_label)

    await update.effective_message.reply_text(
        f"✅ Asta <b>{asta['giocatore']}</b> riaperta con scadenza tra {ore}h.\n"
        f"Nuova scadenza: <b>{utils.format_dt(nuova_scadenza.isoformat())}</b>",
        parse_mode="HTML",
    )
    logger.info("riapri_asta: asta_id=%d ore=%d nuova_scadenza=%s admin=%d",
                asta_id, ore, nuova_scadenza.isoformat(), update.effective_user.id)


async def _notifica_riapertura(context, asta: dict, nuova_scadenza, admin_label: str):
    """Invia annuncio canale e notifica watcher per riapertura asta."""
    from handlers.helpers import aggiorna_canale
    await aggiorna_canale(context, asta["id"])

    channel_id = utils.get_channel_id()
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=(
                f"🔄 Asta <b>{asta['giocatore']}</b> riaperta da <b>{admin_label}</b>.\n"
                f"Nuova scadenza: <b>{utils.format_dt(nuova_scadenza.isoformat())}</b>"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await _log_warn(context, f"Annuncio riapertura canale fallito: {e}")

    watchers = db.get_watchers(asta["id"])
    for gm_id in watchers:
        try:
            await context.bot.send_message(
                chat_id=gm_id,
                text=(
                    f"🔄 L'asta per <b>{asta['giocatore']}</b> è stata riaperta da <b>{admin_label}</b>.\n"
                    f"Nuova scadenza: <b>{utils.format_dt(nuova_scadenza.isoformat())}</b>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            await _log_warn(context, f"Notifica riapertura watcher {gm_id}: {e}")



def _cap_virtuale_post_riapertura(asta: dict) -> tuple[int, int, int]:
    """
    Calcola cap virtuale attuale + offerta vincente per il team vincitore.
    Restituisce (cap_disponibile, cap_virtuale_attuale, cap_post_riapertura).
    Utile per verificare se riaprire un'asta porterebbe il team in negativo.
    """
    team_id = asta.get("offerente_team_id") if isinstance(asta, dict) else asta["offerente_team_id"]
    if not team_id:
        return 0, 0, 0
    team_data = tm.get_team_by_id(team_id)
    if not team_data:
        return 0, 0, 0
    stagione_ri = utils.load_globals().get("stagione_corrente", "2025")
    cap_disp, _ = utils.cap_slot_display(team_data, stagione_ri)
    offerta   = asta["offerta_corrente"] or 0
    stato     = asta.get("stato") if isinstance(asta, dict) else asta["stato"]
    # l'asta stessa, se ancora in uno stato che impegna cap, è già nel cap virtuale
    cap_virt  = db.get_cap_virtuale(team_id) - (offerta if stato in db.STATI_IMPEGNO else 0)
    return cap_disp, cap_virt, cap_virt + offerta


# ── /riapri_asta con cap negativo: conferma ─────────────────────────────────────

async def riapri_annullata_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback di conferma per riapertura asta ANNULLATA o con cap negativo."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    prefix    = parts[0]
    asta_id   = int(parts[1])
    ore       = int(parts[2])

    asta = db.get_asta(asta_id)
    if not asta:
        await query.edit_message_text("❌ Asta non trovata.")
        return

    if prefix == "riapri_annullata" and asta["stato"] != "ANNULLATA":
        await query.edit_message_text("❌ Asta non più in stato ANNULLATA.")
        return
    if prefix == "riapri_cap" and asta["stato"] not in ("CHIUSA", "PAREGGIO", "ANNULLATA"):
        await query.edit_message_text("❌ Stato asta cambiato, operazione annullata.")
        return

    nuova_scadenza = datetime.now(timezone.utc) + timedelta(hours=ore)

    # Se arriva da riapri_annullata ma c'è anche cap negativo, controlla ancora
    if prefix == "riapri_annullata":
        cap_disp, cap_virt, cap_post = _cap_virtuale_post_riapertura(dict(asta))
        if cap_post > cap_disp:
            admin_group_id = utils.get_admin_group_id()
            if not admin_group_id:
                await query.edit_message_text(
                    "❌ `admin_group_id` non configurato in globals.json. "
                    "Impossibile richiedere conferma per cap negativo.",
                    parse_mode="HTML",
                )
                return
            admin_label = _admin_label(query.from_user)
            await _richiedi_conferma_cap_negativo(
                context, dict(asta), ore, admin_group_id, admin_label,
                cap_disp, cap_virt, cap_post, "riapri_cap"
            )
            await query.edit_message_text(
                f"⚠️ Richiesta di conferma inviata al gruppo admin "
                f"(cap virtuale negativo per {asta['giocatore']})."
            )
            return

    # Esegui riapertura
    for nome in [f"firma_auto_{asta_id}", f"pareggio_auto_{asta_id}", f"notif15_{asta_id}"]:
        for j in context.job_queue.get_jobs_by_name(nome):
            j.schedule_removal()

    db.riapri_asta(asta_id, nuova_scadenza.isoformat())
    admin_label = _admin_label(query.from_user)
    from registro import segna_asta
    await segna_asta(context.bot, query.from_user, "admin", "asta riaperta", asta, prima=asta["stato"].lower(),
                     dopo=f"aperta, scade {utils.format_dt(nuova_scadenza.isoformat())}",
                     nota="confermato dal gruppo admin" if prefix == "riapri_cap" else None)
    await _notifica_riapertura(context, dict(asta), nuova_scadenza, admin_label)

    await query.edit_message_text(
        f"✅ Asta <b>{asta['giocatore']}</b> riaperta con scadenza tra {ore}h.\n"
        f"Nuova scadenza: <b>{utils.format_dt(nuova_scadenza.isoformat())}</b>",
        parse_mode="HTML",
    )
    logger.info("riapri_callback: asta_id=%d ore=%d prefix=%s admin=%d",
                asta_id, ore, prefix, query.from_user.id)

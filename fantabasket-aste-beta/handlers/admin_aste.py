"""
Aste, comandi admin per guardarle e correggerle: /aste, /all_aste, /stato_asta, /chiudi_asta,
/annulla_asta (con conferma: admin_chiudi:, admin_annulla:, admin_noop), /ripubblica_asta,
/forza_aggiornamento, /force_esito.
"""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import teams as tm
import utils
from handlers.helpers import aggiorna_canale as _aggiorna_canale, log_warn as _log_warn
from handlers.admin_comune import is_admin, _admin_label

logger = logging.getLogger(__name__)


# ── /aste ────────────────────────────────────────────────────────────────────

async def aste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aste_aperte = db.get_aste_aperte()
    if not aste_aperte:
        await update.effective_message.reply_text("Nessuna asta aperta al momento.")
        return

    teams_map = {t["id"]: t["nome"] for t in tm.get_all_teams()}
    righe = ["<b>Aste in corso:</b>\n"]
    for a in aste_aperte:
        tipo = "🔴 RFA" if a["tipo"] == "RFA" else "🟢 FA"
        team_nome = teams_map.get(a["offerente_team_id"], "—") if a["offerente_team_id"] else "—"
        prop = f" <i>(diritti: {teams_map.get(a['squadra_proprietaria'], a['squadra_proprietaria'])})</i>" if a["tipo"] == "RFA" and a["squadra_proprietaria"] else ""
        righe.append(
            f"{tipo} <b>{a['giocatore']}</b>{prop}\n"
            f"  Offerta: {a['offerta_corrente']}M — {team_nome}\n"
            f"  Scade: {utils.format_dt(a['scade_at'])}\n"
            f"  ID: <code>{a['id']}</code>"
        )
    testo = "\n\n".join(righe)
    if len(testo) <= 4096:
        await update.effective_message.reply_text(testo, parse_mode="HTML")
    else:
        chunk = ""
        for riga in righe:
            candidato = chunk + ("\n\n" if chunk else "") + riga
            if len(candidato) > 4096:
                await update.effective_message.reply_text(chunk, parse_mode="HTML")
                chunk = riga
            else:
                chunk = candidato
        if chunk:
            await update.effective_message.reply_text(chunk, parse_mode="HTML")


# ── /chiudi_asta e /annulla_asta ─────────────────────────────────────────────

async def chiudi_asta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if not context.args:
        await update.effective_message.reply_text("Uso: /chiudi_asta <asta_id>")
        return

    try:
        asta_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso.")
        return

    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] != "APERTA":
        await update.effective_message.reply_text("❌ Asta non trovata o non aperta.")
        return

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma chiusura", callback_data=f"admin_chiudi:{asta_id}"),
        InlineKeyboardButton("❌ Annulla",           callback_data="admin_noop"),
    ]])
    await update.effective_message.reply_text(
        f"Chiudere forzatamente l'asta per <b>{asta['giocatore']}</b>?\n"
        f"Offerta attuale: {asta['offerta_corrente']}M\n"
        f"Il vincitore verrà contattato per la firma.",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def annulla_asta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if not context.args:
        await update.effective_message.reply_text("Uso: /annulla_asta <asta_id>")
        return

    try:
        asta_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso.")
        return

    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] not in ("APERTA", "CHIUSA", "PAREGGIO"):
        await update.effective_message.reply_text("❌ Asta non trovata o già conclusa.")
        return

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma annullamento", callback_data=f"admin_annulla:{asta_id}"),
        InlineKeyboardButton("❌ Annulla",               callback_data="admin_noop"),
    ]])
    await update.effective_message.reply_text(
        f"Annullare l'asta per <b>{asta['giocatore']}</b>? Nessun vincitore verrà assegnato.",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def admin_chiudi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Non sei autorizzato.")
        return

    asta_id = int(query.data.split(":")[1])
    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] != "APERTA":
        await query.edit_message_text("❌ Asta non più disponibile.")
        return

    admin_label = _admin_label(query.from_user)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    db.chiudi_asta(asta_id, now.isoformat())
    from registro import segna_asta
    await segna_asta(context.bot, query.from_user, "admin", "asta chiusa in anticipo", asta, prima="aperta",
                     dopo=f"chiusa, {asta['offerta_corrente']}M" if asta["offerente_team_id"] else "chiusa, senza offerte")

    await _aggiorna_canale(context, asta_id)

    # annuncio nel canale
    channel_id = utils.get_channel_id()
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=f"⏰ Asta <b>{asta['giocatore']}</b> chiusa anticipatamente da <b>{admin_label}</b>.",
            parse_mode="HTML",
        )
    except Exception as e:
        await _log_warn(context, f"Annuncio chiusura anticipata canale fallito: {e}")

    # notifica watcher
    watchers = db.get_watchers(asta_id)
    gm_ids_vincitore = set()
    if asta["offerente_team_id"]:
        team_v = tm.get_team_by_id(asta["offerente_team_id"])
        if team_v:
            gm_ids_vincitore.update(team_v["gm_ids"])
    for gm_id in watchers:
        if gm_id not in gm_ids_vincitore:
            try:
                await context.bot.send_message(
                    chat_id=gm_id,
                    text=f"⏰ L'asta per <b>{asta['giocatore']}</b> è stata chiusa anticipatamente da <b>{admin_label}</b>.",
                    parse_mode="HTML",
                )
            except Exception as e:
                await _log_warn(context, f"Notifica chiusura anticipata watcher {gm_id}: {e}")

    # notifica proprietario RFA (solo se è un'asta RFA e c'è un vincitore)
    if asta["tipo"] == "RFA" and asta["squadra_proprietaria"] and asta["offerente_team_id"]:
        team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
        if team_prop:
            for gm_id in team_prop["gm_ids"]:
                try:
                    await context.bot.send_message(
                        chat_id=gm_id,
                        text=(
                            f"⏰ L'asta RFA per <b>{asta['giocatore']}</b> è stata chiusa anticipatamente "
                            f"da <b>{admin_label}</b>. Riceverai a breve la richiesta di pareggio."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    await _log_warn(context, f"Notifica chiusura anticipata proprietario RFA {gm_id}: {e}")

    if asta["offerente_team_id"]:
        from handlers.firma import chiedi_anni
        # notifica preventiva al GM vincitore che la chiusura è stata anticipata da un admin
        team_v = tm.get_team_by_id(asta["offerente_team_id"])
        if team_v:
            for gm_id in team_v["gm_ids"]:
                try:
                    await context.bot.send_message(
                        chat_id=gm_id,
                        text=(
                            f"⏰ L'asta per <b>{asta['giocatore']}</b> è stata chiusa anticipatamente "
                            f"da <b>{admin_label}</b>. Sei il vincitore con {asta['offerta_corrente']}M — "
                            f"riceverai a breve la richiesta di firma."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    await _log_warn(context, f"Notifica chiusura anticipata GM vincitore {gm_id}: {e}")
        await chiedi_anni(context, asta_id)
        await query.edit_message_text(
            f"✅ Asta <b>{asta['giocatore']}</b> chiusa. Il vincitore è stato contattato.",
            parse_mode="HTML",
        )
    else:
        # Nessun vincitore: per FA chiudi senza assegnazione, per RFA avvia flusso proprietario
        if asta["tipo"] == "RFA":
            from handlers.firma import chiedi_anni as _chiedi
            await _chiedi(context, asta_id)
            await query.edit_message_text(
                f"✅ Asta RFA <b>{asta['giocatore']}</b> chiusa senza offerte. "
                f"Il proprietario è stato contattato per decidere.",
                parse_mode="HTML",
            )
        else:
            db.annulla_asta(asta_id)
            await _aggiorna_canale(context, asta_id)
            await query.edit_message_text(
                f"✅ Asta FA <b>{asta['giocatore']}</b> chiusa senza offerte.",
                parse_mode="HTML",
            )
    logger.info("Chiusura forzata: asta_id=%d admin=%d", asta_id, query.from_user.id)


async def admin_annulla_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Non sei autorizzato.")
        return

    asta_id = int(query.data.split(":")[1])
    asta = db.get_asta(asta_id)
    if not asta:
        await query.edit_message_text("❌ Asta non trovata.")
        return

    admin_label = _admin_label(query.from_user)

    # cancella eventuali job pendenti
    for nome in [f"firma_auto_{asta_id}", f"pareggio_auto_{asta_id}", f"notif15_{asta_id}"]:
        for j in context.job_queue.get_jobs_by_name(nome):
            j.schedule_removal()

    db.annulla_asta(asta_id)
    from registro import segna_asta
    await segna_asta(context.bot, query.from_user, "admin", "asta annullata", asta, prima=asta["stato"].lower()
                     + (f", {asta['offerta_corrente']}M" if asta["offerente_team_id"] else ""), dopo="annullata")
    await _aggiorna_canale(context, asta_id)

    # notifica GM vincitore se esiste
    import teams as tm_ann
    if asta["offerente_team_id"]:
        team_vince = tm_ann.get_team_by_id(asta["offerente_team_id"])
        if team_vince:
            for gm_id in team_vince["gm_ids"]:
                try:
                    await context.bot.send_message(
                        chat_id=gm_id,
                        text=(
                            f"⚠️ L'asta per <b>{asta['giocatore']}</b> è stata annullata da <b>{admin_label}</b>.\n"
                            f"La tua offerta di {asta['offerta_corrente']}M è stata annullata."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning("notifica annullamento GM %d: %s", gm_id, e)

    # notifica proprietario RFA se diverso dal vincitore
    if asta["tipo"] == "RFA" and asta["squadra_proprietaria"]:
        team_prop = tm_ann.get_team_by_id(asta["squadra_proprietaria"])
        if team_prop:
            for gm_id in team_prop["gm_ids"]:
                try:
                    await context.bot.send_message(
                        chat_id=gm_id,
                        text=f"⚠️ L'asta RFA per <b>{asta['giocatore']}</b> è stata annullata da <b>{admin_label}</b>.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning("notifica annullamento prop RFA %d: %s", gm_id, e)

    # notifica watcher
    from handlers.helpers import notifica_watchers as _nw
    gm_ids_gia_notificati = set()
    if asta["offerente_team_id"]:
        team_v = tm_ann.get_team_by_id(asta["offerente_team_id"])
        if team_v:
            gm_ids_gia_notificati.update(team_v["gm_ids"])
    if asta["tipo"] == "RFA" and asta["squadra_proprietaria"]:
        team_p = tm_ann.get_team_by_id(asta["squadra_proprietaria"])
        if team_p:
            gm_ids_gia_notificati.update(team_p["gm_ids"])
    watchers = db.get_watchers(asta_id)
    for gm_id in watchers:
        if gm_id not in gm_ids_gia_notificati:
            try:
                await context.bot.send_message(
                    chat_id=gm_id,
                    text=f"❌ L'asta per <b>{asta['giocatore']}</b> è stata annullata da <b>{admin_label}</b>.",
                    parse_mode="HTML",
                )
            except Exception as e:
                await _log_warn(context, f"Notifica annullamento watcher {gm_id}: {e}")

    # annuncio nel canale
    channel_id = utils.get_channel_id()
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=f"❌ Asta annullata: <b>{asta['giocatore']}</b> (da {admin_label})",
            parse_mode="HTML",
        )
    except Exception as e:
        await _log_warn(context, f"Annuncio annullamento canale fallito: {e}")

    await query.edit_message_text(
        f"✅ Asta <b>{asta['giocatore']}</b> annullata.", parse_mode="HTML"
    )
    logger.info("Annullamento: asta_id=%d admin=%d", asta_id, query.from_user.id)


async def admin_noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Operazione annullata.")


# ── /stato_asta ───────────────────────────────────────────────────────────────

async def stato_asta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dump completo di tutti i campi DB di un'asta. Utile per debug rapido
    senza dover aprire sqlite3.
    Solo admin. Uso: /stato_asta <asta_id>
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if not context.args:
        await update.effective_message.reply_text("Uso: /stato_asta &lt;asta_id&gt;", parse_mode="HTML")
        return

    try:
        asta_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso.")
        return

    asta = db.get_asta(asta_id)
    if not asta:
        await update.effective_message.reply_text("❌ Asta non trovata.")
        return

    righe = [f"🔍 <b>Dump asta #{asta_id}</b>", ""]
    for k, v in dict(asta).items():
        righe.append(f"<code>{k}</code>: {v}")

    offerte = db.get_offerte(asta_id)
    righe.append("")
    righe.append(f"<b>Offerte ({len(offerte)}):</b>")
    for o in offerte:
        righe.append(f"  {o['team_id']} — {o['importo']}M ({o['timestamp']})")

    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")


# ── /all_aste ─────────────────────────────────────────────────────────────────

async def all_aste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Lista tutte le aste con filtro opzionale per stato.
    Solo admin. Uso: /all_aste [stato]
    Stati validi: aperta, chiusa, pareggio, conclusa, annullata
    Senza argomenti mostra le ultime 30 aste di qualsiasi stato.
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    stati_validi = ("APERTA", "CHIUSA", "PAREGGIO", "CONCLUSA", "ANNULLATA")

    if context.args:
        filtro = context.args[0].upper()
        if filtro not in stati_validi:
            await update.effective_message.reply_text(
                f"❌ Stato non valido. Stati possibili: {', '.join(s.lower() for s in stati_validi)}",
            )
            return
        aste = db.get_aste_per_stato(filtro)
        titolo = f"<b>Aste {filtro} ({len(aste)})</b>"
    else:
        aste = db.get_all_aste()[:30]
        titolo = f"<b>Ultime {len(aste)} aste</b>"

    if not aste:
        await update.effective_message.reply_text("Nessuna asta trovata.")
        return

    righe = [titolo, ""]
    for a in aste:
        righe.append(
            f"#{a['id']} [{a['stato']}] {a['tipo']} — <b>{a['giocatore']}</b> "
            f"({a['offerta_corrente']}M, scade {utils.format_dt(a['scade_at'])})"
        )

    testo = "\n".join(righe)
    from shared.messaggi import manda_lungo     # se è lungo arriva come file .md
    await manda_lungo(context.bot, update.effective_chat.id, testo, "aste")


# ── /ripubblica_asta ───────────────────────────────────────────────────────────

async def ripubblica_asta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Pubblica un nuovo messaggio nel canale per un'asta esistente e aggiorna
    canale_msg_id nel DB. Utile se il messaggio originale è stato cancellato
    accidentalmente e aggiorna_canale continua a fallire.
    Solo admin.
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if not context.args:
        await update.effective_message.reply_text("Uso: /ripubblica_asta &lt;asta_id&gt;", parse_mode="HTML")
        return

    try:
        asta_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso.")
        return

    asta = db.get_asta(asta_id)
    if not asta:
        await update.effective_message.reply_text("❌ Asta non trovata.")
        return
    if asta["stato"] in ("CONCLUSA", "ANNULLATA"):
        await update.effective_message.reply_text(
            f"❌ L'asta per <b>{asta['giocatore']}</b> è già {asta['stato'].lower()}, "
            f"non ha senso ripubblicarla.",
            parse_mode="HTML",
        )
        return

    teams_map = {t["id"]: t["nome"] for t in tm.get_all_teams()}
    offerte = db.get_offerte(asta_id)
    testo = utils.build_canale_message(asta, offerte, teams_map)
    channel_id = utils.get_channel_id()

    keyboard = None
    if asta["stato"] == "APERTA":
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🏀 Offri",
                url=f"https://t.me/{context.bot.username}?start=offri_{asta_id}"
            ),
            InlineKeyboardButton("🔔 Segui", callback_data=f"watch:{asta_id}"),
        ]])

    try:
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text=testo,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Invio nel canale fallito: {e}")
        return

    db.set_canale_msg_id(asta_id, msg.message_id)

    await update.effective_message.reply_text(
        f"✅ Asta <b>{asta['giocatore']}</b> ripubblicata nel canale.\n"
        f"Nuovo canale_msg_id: <code>{msg.message_id}</code>",
        parse_mode="HTML",
    )
    logger.info("ripubblica_asta: asta_id=%d nuovo_msg_id=%d admin=%d",
                asta_id, msg.message_id, update.effective_user.id)
    from registro import segna_asta
    await segna_asta(context.bot, update.effective_user, "admin", "asta ripubblicata sul canale", asta,
                     prima=f"messaggio {asta['canale_msg_id'] or '—'}", dopo=f"messaggio {msg.message_id}")


# ── /forza_aggiornamento ──────────────────────────────────────────────────────

async def forza_aggiornamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Riedita forzatamente il messaggio canale di un'asta.
    Utile quando aggiorna_canale è andato in timeout e il messaggio è rimasto obsoleto.
    Solo admin.
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if not context.args:
        await update.effective_message.reply_text("Uso: /forza_aggiornamento &lt;asta_id&gt;", parse_mode="HTML")
        return

    try:
        asta_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Serve l'ID numerico dell'asta.")
        return

    asta = db.get_asta(asta_id)
    if not asta:
        await update.effective_message.reply_text("❌ Asta non trovata.")
        return
    if not asta["canale_msg_id"]:
        await update.effective_message.reply_text(
            f"❌ Asta <b>{asta['giocatore']}</b> non ha un canale_msg_id — usa /ripubblica_asta.",
            parse_mode="HTML",
        )
        return

    teams_map = {t["id"]: t["nome"] for t in tm.get_all_teams()}
    offerte = db.get_offerte(asta_id)
    testo = utils.build_canale_message(asta, offerte, teams_map)
    channel_id = utils.get_channel_id()

    keyboard = None
    if asta["stato"] == "APERTA":
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🏀 Offri", url=f"https://t.me/{context.bot.username}?start=offri_{asta_id}"),
            InlineKeyboardButton("🔔 Segui", callback_data=f"watch:{asta_id}"),
        ]])

    try:
        await context.bot.edit_message_text(
            chat_id=channel_id,
            message_id=asta["canale_msg_id"],
            text=testo,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Edit fallita per asta <b>{asta['giocatore']}</b>: <code>{e}</code>\n"
            f"Se il messaggio è stato cancellato usa /ripubblica_asta {asta_id}.",
            parse_mode="HTML",
        )
        logger.warning("forza_aggiornamento: asta_id=%d fallita: %s", asta_id, e)
        return

    await update.effective_message.reply_text(
        f"✅ Canale aggiornato per <b>{asta['giocatore']}</b> (asta {asta_id}).",
        parse_mode="HTML",
    )
    logger.info("forza_aggiornamento: asta_id=%d admin=%d", asta_id, update.effective_user.id)


# ── /force_esito ──────────────────────────────────────────────────────────────

async def force_esito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Rimanda manualmente il messaggio di firma/pareggio al GM o proprietario,
    in base allo stato attuale dell'asta. Utile quando il job automatico è
    saltato o il GM non ha ricevuto il messaggio (es. aveva bloccato il bot).
    Non cambia lo stato dell'asta nel DB, si limita a reinviare i messaggi.
    Solo admin.
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if not context.args:
        await update.effective_message.reply_text("Uso: /force_esito &lt;asta_id&gt;", parse_mode="HTML")
        return

    try:
        asta_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso.")
        return

    asta = db.get_asta(asta_id)
    if not asta:
        await update.effective_message.reply_text("❌ Asta non trovata.")
        return

    stato = asta["stato"]

    if stato == "CHIUSA":
        from handlers.firma import chiedi_anni, _chiedi_firma_proprietario_senza_offerte
        if asta["offerente_team_id"]:
            await chiedi_anni(context, asta_id)
            await update.effective_message.reply_text(
                f"✅ Rimandato il messaggio di scelta anni al GM vincitore di <b>{asta['giocatore']}</b>.",
                parse_mode="HTML",
            )
        else:
            if asta["tipo"] == "RFA":
                await _chiedi_firma_proprietario_senza_offerte(context, asta_id)
                await update.effective_message.reply_text(
                    f"✅ Rimandato il messaggio al proprietario RFA di <b>{asta['giocatore']}</b> "
                    f"(nessuna offerta — firma o lascia andare).",
                    parse_mode="HTML",
                )
            else:
                await update.effective_message.reply_text(
                    f"❌ Asta FA <b>{asta['giocatore']}</b> in stato CHIUSA senza offerte: "
                    f"nessun messaggio da mandare, andrebbe annullata con /annulla_asta.",
                    parse_mode="HTML",
                )
            return

    elif stato == "PAREGGIO":
        if not asta["anni_offerti"]:
            await update.effective_message.reply_text(
                f"❌ Asta <b>{asta['giocatore']}</b> in PAREGGIO ma senza anni_offerti nel DB. "
                f"Dato inconsistente, intervenire manualmente.",
                parse_mode="HTML",
            )
            return
        from handlers.firma import _chiedi_pareggio
        await _chiedi_pareggio(context, asta_id, asta["anni_offerti"])
        await update.effective_message.reply_text(
            f"✅ Rimandato il messaggio di pareggio al proprietario RFA di <b>{asta['giocatore']}</b>.",
            parse_mode="HTML",
        )

    else:
        await update.effective_message.reply_text(
            f"❌ L'asta <b>{asta['giocatore']}</b> è in stato <b>{stato}</b>: "
            f"/force_esito funziona solo su aste in stato CHIUSA o PAREGGIO.",
            parse_mode="HTML",
        )
        return

    logger.info("force_esito: asta_id=%d stato=%s admin=%d", asta_id, stato, update.effective_user.id)
    from registro import segna_asta
    await segna_asta(context.bot, update.effective_user, "admin", "esito dell'asta rimandato", asta,
                     nota=f"stato {stato.lower()}: messaggio di " + ("pareggio" if stato == "PAREGGIO" else "firma")
                     + " rimandato")

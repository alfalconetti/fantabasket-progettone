"""
Disabled Player Exception (DPE).

Flusso:
  GM lancia /dpe → seleziona giocatore dal roster → preview decurtazione →
  richiesta inviata al gruppo admin con Approva/Rifiuta →
  se approvata: scrittura DB + annuncio canale principale

Effetti per fase:
  offseason-rinnovi … regular-season-fa → libera slot roster
  regular-season-deadline               → nessuno slot liberato
                                          (cambio ruolo aggiuntivo — da implementare con i ruoli)

Decurtazione: importo - ceil(importo * 0.25), il contratto torna normale alla stagione successiva
              (la riga dpe è legata alla stagione corrente, non tocca la tabella contratti)
"""
import logging
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
import settings
from settings import solo_privato, richiede_fase
import teams as tm

logger = logging.getLogger(__name__)

FASI_DPE = (
    "offseason-rinnovi", "offseason-draft", "offseason-rfa", "offseason-fa", "offseason-ruoli",
    "regular-season-fa", "regular-season-deadline",
)


def _importo_dpe(importo: int) -> int:
    """Contratto ridotto del 25%, con la riduzione arrotondata per eccesso
    (regolamento: Klay 5 → 3, cioè 5 − ceil(1,25))."""
    return importo - math.ceil(importo * 0.25)


# ── /dpe ─────────────────────────────────────────────────────────────────────

@solo_privato
@richiede_fase(*FASI_DPE, msg="❌ La DPE non è disponibile in questa fase.")
async def cmd_dpe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return

    stagione = settings.stagione_corrente()
    roster   = db.get_roster_team(team["id"])
    if not roster:
        await update.effective_message.reply_text("Il tuo roster è vuoto.")
        return

    # Filtra giocatori che non hanno già una DPE attiva questa stagione
    eligibili = [
        r for r in roster
        if not db.get_dpe_attiva(r["giocatore_id"], stagione)
    ]
    if not eligibili:
        await update.effective_message.reply_text(
            "❌ Tutti i giocatori del tuo roster hanno già una DPE attiva questa stagione."
        )
        return

    bottoni = [
        [InlineKeyboardButton(
            f"{r['nome_common']} ({r['importo']}M)",
            callback_data=f"dpe_sel:{r['giocatore_id']}"
        )]
        for r in eligibili
    ]
    await update.effective_message.reply_text(
        "Seleziona il giocatore per cui richiedere la DPE\n"
        "<i>(giocatore dichiarato ufficialmente out for the season)</i>:",
        reply_markup=InlineKeyboardMarkup(bottoni),
        parse_mode="HTML",
    )


async def cb_seleziona_dpe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid  = int(query.data.split(":")[1])
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)

    contratto = db.get_contratto_attivo(gid)
    if not contratto or contratto["team_id"] != team["id"]:
        await query.edit_message_text("❌ Giocatore non trovato nel tuo roster.")
        return

    giocatore = db.get_giocatore(gid)
    stagione  = settings.stagione_corrente()
    fase      = settings.fase()
    pre_deadline = (fase != "regular-season-deadline")

    importo_orig = contratto["importo"]
    importo_new  = _importo_dpe(importo_orig)
    risparmio    = importo_orig - importo_new

    effetto = _effetto(pre_deadline, gid) + "\n<i>Pre o post deadline conta al momento dell'approvazione.</i>"

    testo = (
        f"🏥 <b>DPE — {giocatore['nome_common']}</b>\n\n"
        f"Contratto attuale: <b>{importo_orig}M</b>\n"
        f"Contratto DPE (stagione {stagione}): <b>{importo_new}M</b> (-{risparmio}M)\n"
        f"Il contratto torna normale dalla stagione successiva.\n\n"
        f"{effetto}\n\n"
        f"<i>La richiesta verrà inviata agli admin per approvazione.</i>"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Invia richiesta", callback_data=f"dpe_req:{gid}"),
        InlineKeyboardButton("❌ Annulla",          callback_data="dpe_no"),
    ]])
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)


def _ruolo_attuale(gid: int) -> str | None:
    r = db._q("SELECT ruolo FROM ruolo_attuale WHERE giocatore_id = %s AND stagione = %s",
              (gid, settings.stagione_corrente()), one=True)
    return r["ruolo"] if r else None


def _effetto(pre_deadline: bool, gid: int) -> str:
    if pre_deadline:
        return "✅ Libera uno slot roster"
    ruolo = _ruolo_attuale(gid)
    verso = f" verso {ruolo}" if ruolo else ""
    return f"🔁 Cambio ruolo aggiuntivo gratuito{verso} (post-deadline, nessuno slot liberato)"


async def applica_dpe(bot, gid: int, team_id: str, admin_tag: str, da_admin: bool) -> tuple[str | None, str]:
    """Applica la DPE con i dati di ADESSO: contratto della squadra, fase (pre/post
    deadline), importo. Restituisce (errore, testo_esito). Usata dall'approvazione
    della richiesta del GM e dalla DPE diretta del pannello admin."""
    giocatore = db.get_giocatore(gid) or {"nome_common": str(gid)}
    team      = tm.get_team_by_id(team_id) or {"nome": team_id, "gm_nome": team_id, "gm_ids": []}
    stagione  = settings.stagione_corrente()
    fase      = settings.fase()
    if fase not in FASI_DPE:
        return "❌ La DPE non è disponibile in questa fase.", ""
    contratto = db.get_contratto_attivo(gid)
    if not contratto or contratto["team_id"] != team_id:
        return f"❌ {giocatore['nome_common']} non è più nel roster di {team['nome']}.", ""
    if db.get_dpe_attiva(gid, stagione):
        return f"⚠️ DPE per {giocatore['nome_common']} già registrata questa stagione.", ""

    pre_deadline = (fase != "regular-season-deadline")
    importo_orig = contratto["importo"]
    importo_new  = _importo_dpe(importo_orig)
    risparmio    = importo_orig - importo_new
    effetto      = _effetto(pre_deadline, gid)
    db.inserisci_dpe(giocatore_id=gid, team_id=team_id, stagione=stagione,
                     importo_originale=importo_orig, importo_dpe=importo_new,
                     pre_deadline=pre_deadline, approvata_da=admin_tag)

    esito = (f"✅ DPE {'registrata' if da_admin else 'approvata'} — <b>{giocatore['nome_common']}</b>\n"
             f"{importo_orig}M → {importo_new}M (stagione {stagione})\n{effetto}")
    testo_gm = (f"{'🏥 <b>DPE attivata</b> per' if da_admin else '✅ La tua richiesta DPE per'} "
                f"<b>{giocatore['nome_common']}</b>{'' if da_admin else ' è stata approvata'}.\n"
                f"Contratto per questa stagione: <b>{importo_new}M</b> (-{risparmio}M)\n{effetto}"
                + (f"\n\n<i>Operazione effettuata dall'admin {admin_tag}</i>" if da_admin else ""))
    for gm_id in team.get("gm_ids", []):
        try:
            await bot.send_message(chat_id=gm_id, text=testo_gm, parse_mode="HTML")
        except Exception:
            pass
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        try:
            await bot.send_message(
                chat_id=main_channel, parse_mode="HTML",
                text=(f"🏥 <b>{team.get('gm_nome', team['nome'])}</b> attiva la DPE per <b>{giocatore['nome_common']}</b>\n"
                      f"Contratto {stagione}: {importo_orig}M → <b>{importo_new}M</b> (-{risparmio}M)\n{effetto}"))
        except Exception as e:
            logger.warning("Annuncio canale DPE fallito: %s", e)
    logger.info("DPE: team=%s giocatore=%d %dM→%dM pre_deadline=%s da=%s",
                team_id, gid, importo_orig, importo_new, pre_deadline, admin_tag)
    try:
        import gas_client
        gas_client.sync_after_dpe(team_id)
    except Exception as e:
        logger.warning("GAS sync DPE fallito: %s", e)
    return None, esito


def _admin_tag(user) -> str:
    tag = user.first_name or str(user.id)
    return tag + (f" (@{user.username})" if user.username else "")


async def cb_invia_richiesta_dpe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GM conferma → notifica al gruppo admin con bottoni Approva/Rifiuta."""
    query = update.callback_query
    await query.answer()
    gid  = int(query.data.split(":")[1])
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await query.edit_message_text("⛔ Non sei registrato come GM.")
        return
    if settings.fase() not in FASI_DPE:
        await query.edit_message_text("❌ La DPE non è disponibile in questa fase.")
        return

    contratto = db.get_contratto_attivo(gid)
    if not contratto or contratto["team_id"] != team["id"]:
        await query.edit_message_text("❌ Giocatore non trovato nel tuo roster.")
        return

    giocatore    = db.get_giocatore(gid)
    stagione     = settings.stagione_corrente()
    if db.get_dpe_attiva(gid, stagione):
        await query.edit_message_text(f"⚠️ {giocatore['nome_common']} ha già una DPE in questa stagione.")
        return
    if not db.apri_richiesta("dpe", gid, team["id"]):
        await query.edit_message_text(
            f"⏳ C'è già una richiesta DPE in attesa per <b>{giocatore['nome_common']}</b>: "
            f"aspetta la risposta degli admin.", parse_mode="HTML")
        return

    fase         = settings.fase()
    pre_deadline = (fase != "regular-season-deadline")
    importo_orig = contratto["importo"]
    importo_new  = _importo_dpe(importo_orig)

    await query.edit_message_text(
        f"✅ Richiesta DPE per <b>{giocatore['nome_common']}</b> inviata agli admin.",
        parse_mode="HTML",
    )

    admin_group_id = settings.load_globals().get("admin_group_id")
    if not admin_group_id:
        logger.warning("admin_group_id non configurato — richiesta DPE non inviata")
        return

    flag_deadline = "PRE" if pre_deadline else "POST"
    testo_admin = (
        f"🏥 <b>Richiesta DPE</b>\n\n"
        f"👤 <b>{team['gm_nome']}</b> — {team['nome']}\n"
        f"Giocatore: <b>{giocatore['nome_common']}</b>\n"
        f"Contratto: {importo_orig}M → <b>{importo_new}M</b> (stagione {stagione})\n"
        f"Fase: <b>{flag_deadline}-deadline</b> <i>(conta quella al momento dell'approvazione)</i>\n"
        f"{_effetto(pre_deadline, gid)}"
    )
    # Formato dei bottoni invariato (compatibile con i messaggi già inviati):
    # all'approvazione importi e pre/post deadline vengono ricalcolati
    kb_admin = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Approva",
            callback_data=f"dpe_ok:{gid}:{team['id']}:{importo_orig}:{importo_new}:{1 if pre_deadline else 0}"
        ),
        InlineKeyboardButton("❌ Rifiuta", callback_data=f"dpe_ko:{gid}:{team['id']}"),
    ]])
    try:
        await context.bot.send_message(chat_id=admin_group_id, text=testo_admin,
                                       parse_mode="HTML", reply_markup=kb_admin)
    except Exception as e:
        logger.error("Invio richiesta DPE al gruppo admin fallito: %s", e)
        db.chiudi_richiesta("dpe", gid, "scaduta")


async def cb_approva_dpe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approva → controlli con i dati attuali, DB, avvisi, annuncio."""
    query = update.callback_query
    if not settings.is_admin(query.from_user.id):
        await query.answer("⛔ Solo gli admin possono approvare.", show_alert=True)
        return
    await query.answer()
    parts   = query.data.split(":")
    gid     = int(parts[1])
    team_id = parts[2]
    admin_tag = _admin_tag(query.from_user)

    esito_r = db.chiudi_richiesta("dpe", gid, "approvata", admin_tag)
    if esito_r == "gestita":
        await query.edit_message_text(query.message.text_html + "\n\nℹ️ <b>Richiesta già gestita</b>",
                                      parse_mode="HTML")
        return
    try:
        errore, esito = await applica_dpe(context.bot, gid, team_id, admin_tag, da_admin=False)
    except Exception:
        db.riapri_richiesta("dpe", gid)
        raise
    if errore:
        if esito_r == "ok":   # richiesta non applicabile: chiusa come scaduta
            db._q("UPDATE richieste_admin SET stato = 'scaduta' WHERE id = (SELECT id FROM richieste_admin "
                  "WHERE tipo = 'dpe' AND chiave = %s ORDER BY id DESC LIMIT 1)", (gid,))
        await query.edit_message_text(query.message.text_html + f"\n\n{errore}", parse_mode="HTML")
        return
    await query.edit_message_text(esito + f"\n<i>Approvata da {admin_tag}</i>", parse_mode="HTML")


async def cb_rifiuta_dpe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin rifiuta → notifica al GM (solo se la richiesta non era già stata gestita)."""
    query = update.callback_query
    if not settings.is_admin(query.from_user.id):
        await query.answer("⛔ Solo gli admin possono rifiutare.", show_alert=True)
        return
    await query.answer()
    parts   = query.data.split(":")
    gid     = int(parts[1])
    team_id = parts[2]
    giocatore = db.get_giocatore(gid) or {"nome_common": str(gid)}
    team      = tm.get_team_by_id(team_id) or {"gm_ids": []}
    admin_tag = _admin_tag(query.from_user)

    esito_r = db.chiudi_richiesta("dpe", gid, "rifiutata", admin_tag)
    if esito_r == "gestita" or (esito_r == "nessuna" and db.get_dpe_attiva(gid, settings.stagione_corrente())):
        await query.edit_message_text(query.message.text_html + "\n\nℹ️ <b>Richiesta già gestita</b>",
                                      parse_mode="HTML")
        return

    await query.edit_message_text(
        f"❌ DPE rifiutata — <b>{giocatore['nome_common']}</b>\n<i>da {admin_tag}</i>",
        parse_mode="HTML",
    )
    for gm_id in team.get("gm_ids", []):
        try:
            await context.bot.send_message(
                chat_id=gm_id,
                text=f"❌ La tua richiesta DPE per <b>{giocatore['nome_common']}</b> è stata rifiutata dagli admin.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    logger.info("DPE rifiutata: team=%s giocatore=%d", team_id, gid)


async def cb_annulla_dpe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Richiesta DPE annullata.")


def get_handlers() -> list:
    return [
        CommandHandler("dpe", cmd_dpe),
        CallbackQueryHandler(cb_seleziona_dpe,        pattern=r"^dpe_sel:\d+$"),
        CallbackQueryHandler(cb_invia_richiesta_dpe,  pattern=r"^dpe_req:\d+$"),
        CallbackQueryHandler(cb_approva_dpe,          pattern=r"^dpe_ok:\d+:.+:\d+:\d+:[01]$"),
        CallbackQueryHandler(cb_rifiuta_dpe,          pattern=r"^dpe_ko:\d+:.+$"),
        CallbackQueryHandler(cb_annulla_dpe,          pattern=r"^dpe_no$"),
    ]

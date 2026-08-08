"""
Disabled Player Exception (DPE).

Flusso:
  GM lancia /dpe → seleziona giocatore dal roster → preview decurtazione →
  richiesta inviata al gruppo admin con Approva/Rifiuta →
  se approvata: scrittura DB + annuncio canale principale

Effetti per fase:
  regular-season-fa       → pre-deadline: decurtazione 25% + libera slot
  regular-season-deadline → post-deadline: decurtazione 25%, nessuno slot liberato
                            (cambio ruolo aggiuntivo — da implementare con i ruoli)

Decurtazione: ceil(importo * 0.75), il contratto torna normale alla stagione successiva
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

FASI_DPE = ("regular-season-fa", "regular-season-deadline")


def _importo_dpe(importo: int) -> int:
    """Decurtazione 25% arrotondata per eccesso: ceil(importo * 0.75)."""
    return math.ceil(importo * 0.75)


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
    pre_deadline = (fase == "regular-season-fa")

    importo_orig = contratto["importo"]
    importo_new  = _importo_dpe(importo_orig)
    risparmio    = importo_orig - importo_new

    effetto = (
        "✅ Libera uno slot roster (pre-deadline)"
        if pre_deadline else
        "ℹ️ Nessuno slot liberato — cambio ruolo aggiuntivo (post-deadline)"
    )

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


async def cb_invia_richiesta_dpe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GM conferma → notifica al gruppo admin con bottoni Approva/Rifiuta."""
    query = update.callback_query
    await query.answer()
    gid  = int(query.data.split(":")[1])
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)

    contratto = db.get_contratto_attivo(gid)
    if not contratto or contratto["team_id"] != team["id"]:
        await query.edit_message_text("❌ Giocatore non trovato nel tuo roster.")
        return

    giocatore    = db.get_giocatore(gid)
    stagione     = settings.stagione_corrente()
    fase         = settings.fase()
    pre_deadline = (fase == "regular-season-fa")
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
        f"Fase: <b>{flag_deadline}-deadline</b>\n"
        f"{'✅ Libera slot roster' if pre_deadline else 'ℹ️ Nessuno slot liberato'}"
    )
    kb_admin = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Approva",
            callback_data=f"dpe_ok:{gid}:{team['id']}:{importo_orig}:{importo_new}:{1 if pre_deadline else 0}"
        ),
        InlineKeyboardButton(
            "❌ Rifiuta",
            callback_data=f"dpe_ko:{gid}:{team['id']}"
        ),
    ]])
    try:
        await context.bot.send_message(
            chat_id=admin_group_id,
            text=testo_admin,
            parse_mode="HTML",
            reply_markup=kb_admin,
        )
    except Exception as e:
        logger.error("Invio richiesta DPE al gruppo admin fallito: %s", e)


async def cb_approva_dpe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approva → scrittura DB + annuncio canale."""
    query = update.callback_query
    await query.answer()

    parts        = query.data.split(":")
    gid          = int(parts[1])
    team_id      = parts[2]
    importo_orig = int(parts[3])
    importo_new  = int(parts[4])
    pre_deadline = parts[5] == "1"

    giocatore = db.get_giocatore(gid)
    team      = tm.get_team_by_id(team_id)
    stagione  = settings.stagione_corrente()
    admin     = update.effective_user

    # Verifica non già approvata
    if db.get_dpe_attiva(gid, stagione):
        await query.edit_message_text(
            f"⚠️ DPE per <b>{giocatore['nome_common']}</b> già registrata questa stagione.",
            parse_mode="HTML",
        )
        return

    # Scrittura DB
    _admin_tag = admin.first_name or str(admin.id)
    if admin.username:
        _admin_tag += f" (@{admin.username})"
    db.inserisci_dpe(
        giocatore_id=gid,
        team_id=team_id,
        stagione=stagione,
        importo_originale=importo_orig,
        importo_dpe=importo_new,
        pre_deadline=pre_deadline,
        approvata_da=_admin_tag,
    )

    # Se pre-deadline libera slot in teams.json
    if pre_deadline:
        tm.set_slot(team_id, team["slot_disponibili"] + 1)

    risparmio = importo_orig - importo_new
    effetto   = "✅ Slot roster liberato" if pre_deadline else "ℹ️ Nessuno slot liberato (post-deadline)"

    await query.edit_message_text(
        f"✅ DPE approvata — <b>{giocatore['nome_common']}</b>\n"
        f"{importo_orig}M → {importo_new}M (stagione {stagione})\n"
        f"{effetto}",
        parse_mode="HTML",
    )

    # Notifica al GM
    try:
        gm_ids = team.get("gm_ids", [])
        testo_gm = (
            f"✅ La tua richiesta DPE per <b>{giocatore['nome_common']}</b> è stata approvata.\n"
            f"Contratto per questa stagione: <b>{importo_new}M</b> (-{risparmio}M)\n"
            f"{effetto}"
        )
        for gm_id in gm_ids:
            try:
                await context.bot.send_message(
                    chat_id=gm_id, text=testo_gm, parse_mode="HTML"
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning("Notifica GM DPE fallita: %s", e)

    # Annuncio canale principale
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        testo_canale = (
            f"🏥 <b>{team['gm_nome']}</b> attiva la DPE per <b>{giocatore['nome_common']}</b>\n"
            f"Contratto {stagione}: {importo_orig}M → <b>{importo_new}M</b> (-{risparmio}M)\n"
            f"{effetto}"
        )
        try:
            await context.bot.send_message(
                chat_id=main_channel, text=testo_canale, parse_mode="HTML"
            )
        except Exception as e:
            logger.warning("Annuncio canale DPE fallito: %s", e)

    logger.info("DPE approvata: team=%s giocatore=%d %dM→%dM pre_deadline=%s",
                team_id, gid, importo_orig, importo_new, pre_deadline)


async def cb_rifiuta_dpe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin rifiuta → notifica al GM."""
    query = update.callback_query
    await query.answer()

    parts   = query.data.split(":")
    gid     = int(parts[1])
    team_id = parts[2]

    giocatore = db.get_giocatore(gid)
    team      = tm.get_team_by_id(team_id)

    await query.edit_message_text(
        f"❌ DPE rifiutata — <b>{giocatore['nome_common']}</b>",
        parse_mode="HTML",
    )

    gm_ids = team.get("gm_ids", [])
    for gm_id in gm_ids:
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

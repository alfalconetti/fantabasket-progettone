"""
Comandi admin del bot aste: /admin (l'elenco), /guida_admin, /backup_ora, /apri_mercato e
/chiudi_mercato, i comandi che ora rimandano al bot principale (/set_cap, /set_slot, /add_cap,
/add_slot, /set_fase, /reset_rfa, /set_cap_penalizzato) e la registrazione di tutti.

Il resto è diviso per argomento (v3.13.0 / aste v63; prima stava tutto in questo file):
  admin_comune.py    is_admin, _admin_label, conferma per cap negativo
  admin_squadre.py   /list, /listteams, /team, /firme, /autocap, /autoslot
  admin_aste.py      /aste, /all_aste, /stato_asta, /chiudi_asta, /annulla_asta,
                     /ripubblica_asta, /forza_aggiornamento, /force_esito
  admin_riapri.py    /riapri_asta, /estendi_asta, /sposta_asta
  admin_offerte.py   /apri_asta, /crea_offerta, /nuova_rfa, /annulla_offerta
"""
import logging
import json
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import teams as tm
import utils
from handlers.admin_comune import is_admin, _admin_label
from handlers.admin_squadre import (
    cb_reset_cap_anticipato, cb_reset_slot_anticipato, cmd_firme, cmd_list, listteams,
)
from handlers.admin_aste import (
    admin_annulla_callback, admin_chiudi_callback, admin_noop_callback, all_aste, annulla_asta,
    aste, chiudi_asta, force_esito, forza_aggiornamento, ripubblica_asta, stato_asta,
)
from handlers.admin_riapri import estendi_asta, riapri_annullata_callback, riapri_asta, sposta_asta
from handlers.admin_offerte import (
    annulla_off_cap_callback, annulla_offerta, apri_asta, crea_offerta, nuova_rfa,
)

logger = logging.getLogger(__name__)


GLOBALS_PATH  = os.environ.get("GLOBALS_PATH", "/config/globals.json")


def _set_mercato(aperto: bool):
    with open(GLOBALS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["mercato_aperto"] = aperto
    with open(GLOBALS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── /set_cap e /set_slot ──────────────────────────────────────────────────────

async def set_cap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return
    await update.effective_message.reply_text(
        "⚠️ In modalità beta cap e slot sono gestiti da PostgreSQL.\n"
        "Usa /set_cap_penalizzato per la penalità cap."
    )


async def set_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return
    await update.effective_message.reply_text(
        "⚠️ In modalità beta gli slot sono calcolati dal roster in PostgreSQL."
    )


# ── /apri_mercato e /chiudi_mercato ──────────────────────────────────────────

async def apri_mercato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return
    _set_mercato(True)
    await update.effective_message.reply_text("✅ Mercato FA aperto.")
    from registro import segna
    await segna(context.bot, update.effective_user, "admin", "mercato FA", oggetto="mercato", prima="chiuso",
                dopo="aperto")


async def chiudi_mercato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return
    _set_mercato(False)
    await update.effective_message.reply_text("🔒 Mercato FA chiuso.")
    from registro import segna
    await segna(context.bot, update.effective_user, "admin", "mercato FA", oggetto="mercato", prima="aperto",
                dopo="chiuso")


# ── /set_fase ────────────────────────────────────────────────────────────────

async def set_fase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    # La fase è condivisa nel globals.json e la gestisce il bot principale con i nomi
    # completi (regular-season-fa, offseason-rfa, …): scrivere qui "offseason"/"regular"
    # mandava fuori fase tutti i controlli del bot principale.
    await update.effective_message.reply_text(
        "La fase si cambia dal bot principale: /set_fase (o /admin_menu → Fase).\n"
        f"Fase attuale: <b>{utils.load_globals().get('fase', '?')}</b>", parse_mode="HTML")
    return

    fase = context.args[0]

    # leggi fase corrente
    with open(GLOBALS_PATH, "r", encoding="utf-8") as f:
        globals_data = json.load(f)

    fase_corrente = globals_data.get("fase", "offseason")
    if fase_corrente == fase:
        await update.effective_message.reply_text(f"Siamo già in fase <b>{fase}</b>.", parse_mode="HTML")
        return

    all_teams = tm.get_all_teams()
    righe = [f"Cambio fase: <b>{fase_corrente} → {fase}</b>\n"]

    # Beta: cap derivato da PG, non aggiorniamo teams.json
    righe.append("<i>Beta: cap e slot derivano da PostgreSQL — nessuna modifica al JSON.</i>")
    righe.append(f"Fase impostata a <b>{fase}</b>.")

    # aggiorna fase in globals
    globals_data["fase"] = fase
    with open(GLOBALS_PATH, "w", encoding="utf-8") as f:
        json.dump(globals_data, f, ensure_ascii=False, indent=2)

    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")
    logger.info("set_fase: %s → %s admin=%d", fase_corrente, fase, update.effective_user.id)


# ── /reset_rfa ───────────────────────────────────────────────────────────────

async def reset_rfa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chiede la nuova stagione e conferma prima di resettare."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    # La stagione è condivisa nel globals.json e la avanza il bot principale entrando in
    # offseason-rinnovi: cambiarla qui (es. "2025-26") rompeva i conti del bot principale.
    await update.effective_message.reply_text(
        "Non serve più: la stagione avanza da sola quando il bot principale entra in "
        "<b>offseason-rinnovi</b> (/set_fase), e con lei si azzera la RFA di ogni squadra.\n"
        f"Stagione attuale: <b>{utils.get_stagione_corrente()}</b>", parse_mode="HTML")
    return

    if not context.args:
        stagione_corrente = utils.get_stagione_corrente()
        await update.effective_message.reply_text(
            f"Uso: /reset_rfa &lt;nuova_stagione&gt;\n"
            f"Esempio: /reset_rfa 2025-26\n\n"
            f"Stagione corrente: <b>{stagione_corrente}</b>",
            parse_mode="HTML",
        )
        return

    nuova_stagione = context.args[0]
    stagione_corrente = utils.get_stagione_corrente()
    context.user_data["nuova_stagione"] = nuova_stagione

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma", callback_data="reset_rfa:conferma"),
        InlineKeyboardButton("❌ Annulla",  callback_data="admin_noop"),
    ]])
    await update.effective_message.reply_text(
        f"Cambio stagione: <b>{stagione_corrente} → {nuova_stagione}</b>\n"
        f"Tutti i team potranno aprire una nuova RFA.\n\nConfermi?",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def reset_rfa_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Non sei autorizzato.")
        return

    context.user_data.pop("nuova_stagione", None)
    await query.edit_message_text("La stagione la cambia il bot principale (/set_fase → offseason-rinnovi).")
    return

    nuova_stagione = None
    if not nuova_stagione:
        await query.edit_message_text("❌ Stagione non specificata.")
        return

    # aggiorna stagione_corrente in globals
    with open(GLOBALS_PATH, "r", encoding="utf-8") as f:
        import json as _json
        globals_data = _json.load(f)
    vecchia_stagione = globals_data.get("stagione_corrente", "?")
    globals_data["stagione_corrente"] = nuova_stagione
    with open(GLOBALS_PATH, "w", encoding="utf-8") as f:
        _json.dump(globals_data, f, ensure_ascii=False, indent=2)

    await query.edit_message_text(
        f"✅ Stagione aggiornata: <b>{vecchia_stagione} → {nuova_stagione}</b>\n"
        f"Tutti i team possono ora aprire una nuova RFA.",
        parse_mode="HTML",
    )
    logger.info("reset_rfa: stagione %s → %s admin=%d", vecchia_stagione, nuova_stagione, query.from_user.id)


# ── /set_cap_penalizzato ─────────────────────────────────────────────────────

async def set_cap_penalizzato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    # config/ è montata in sola lettura nel bot aste: scrivere teams.json da qui falliva.
    await update.effective_message.reply_text(
        "La penalità cap si imposta dal bot principale: /set_cap_penalizzato &lt;team_id&gt; &lt;valore&gt;",
        parse_mode="HTML")
    return

    if len(context.args) != 2:
        await update.effective_message.reply_text("Uso: /set_cap_penalizzato <team_id> <valore>")
        return

    team_id = context.args[0]
    try:
        valore = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("❌ Il valore deve essere un numero intero.")
        return

    if valore < 0:
        await update.effective_message.reply_text("❌ Il valore non può essere negativo.")
        return

    team = tm.get_team_by_id(team_id)
    if team is None:
        await update.effective_message.reply_text(f"❌ Team ID '<code>{team_id}</code>' non trovato.", parse_mode="HTML")
        return

    with open(GLOBALS_PATH.replace("globals.json", "teams.json"), "r", encoding="utf-8") as f:
        import json as _json
        data = _json.load(f)
    for t in data["teams"]:
        if t["id"] == team_id:
            t["cap_penalizzato"] = valore
            break
    teams_path = os.environ.get("TEAMS_PATH", "/config/teams.json")
    with open(teams_path, "w", encoding="utf-8") as f:
        import json as _json2
        _json2.dump(data, f, ensure_ascii=False, indent=2)

    await update.effective_message.reply_text(
        f"✅ Cap penalizzato di <b>{team['nome']}</b> impostato a <b>{valore}M</b>.", parse_mode="HTML"
    )
    logger.info("set_cap_penalizzato: team=%s valore=%d", team_id, valore)


# ── /add_cap ─────────────────────────────────────────────────────────────────

async def add_cap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return
    await update.effective_message.reply_text(
        "⚠️ In modalità beta cap e slot sono gestiti da PostgreSQL.\n"
        "Usa /set_cap_penalizzato per la penalità cap."
    )


# ── /add_slot ────────────────────────────────────────────────────────────────

async def add_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return
    await update.effective_message.reply_text(
        "⚠️ In modalità beta gli slot sono calcolati dal roster in PostgreSQL."
    )


# ── /backup_ora ───────────────────────────────────────────────────────────────

async def cmd_backup_ora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia immediatamente un backup al canale log. Solo admin."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return
    from scheduler import invia_backup
    log_channel_id = utils.get_log_channel_id()
    if not log_channel_id:
        await update.effective_message.reply_text("❌ log_channel_id non configurato in globals.json.")
        return
    try:
        await invia_backup(context, log_channel_id, "manuale")
        await update.effective_message.reply_text("✅ Backup inviato al canale log.")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Backup fallito: <code>{e}</code>", parse_mode="HTML")


async def guida_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manda la guida admin in privata come documento .md. Solo admin."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "docs", "guida_admin.md")
    path = os.path.normpath(path)
    try:
        with open(path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=f,
                filename="guida_admin.md",
                caption="📖 Guida admin",
            )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore nell'invio della guida: {e}")


# ── /admin ────────────────────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    testo = (
        "<b>Comandi admin — bot aste</b>\n"
        "<i>Fase, stagione, cap, slot e penalità arrivano dal bot principale: qui non si cambiano.</i>\n"
        "\n"
        "<b>👀 Guardare</b>\n"
        "/list — squadre con id e GM\n"
        "/listteams — cap e slot di tutte le squadre, una riga a testa\n"
        "/team &lt;team_id&gt; — la situazione di una squadra (come /me)\n"
        "/aste — aste aperte · /all_aste [stato] — tutte, anche chiuse\n"
        "/firme [N] — ultime firme (default 10)\n"
        "/stato_asta &lt;asta_id&gt; — tutti i dati di un'asta con le offerte\n"
        "\n"
        "<b>🏀 Aprire e offrire per una squadra</b>\n"
        "/apri_asta &lt;team_id&gt; &lt;importo&gt; &lt;giocatore&gt; — es. /apri_asta team07 5 LeBron James\n"
        "/crea_offerta &lt;team_id&gt; &lt;asta_id&gt; &lt;importo&gt; — es. /crea_offerta team07 42 7\n"
        "/nuova_rfa &lt;giocatore&gt; &lt;team_id&gt; &lt;vecchio_compenso&gt; — es. /nuova_rfa Doncic team12 28 "
        "(solo a mano: le RFA dichiarate nel bot principale si aprono da sole)\n"
        "\n"
        "<b>🛠 Correggere un'asta</b>\n"
        "/annulla_offerta &lt;asta_id&gt; — toglie l'ultima offerta\n"
        "/chiudi_asta &lt;asta_id&gt; — chiude subito (parte la firma)\n"
        "/annulla_asta &lt;asta_id&gt; — annulla senza vincitore\n"
        "/riapri_asta &lt;asta_id&gt; [ore] — da chiusa/pareggio/annullata ad aperta\n"
        "/estendi_asta &lt;asta_id&gt; &lt;ore&gt; — sposta la scadenza (negativo per accorciare)\n"
        "/sposta_asta &lt;asta_id&gt; &lt;AAAA-MM-GGTHH:MM&gt; — scadenza precisa, ora di Roma\n"
        "\n"
        "<b>🚑 Se qualcosa si inceppa</b>\n"
        "/force_esito &lt;asta_id&gt; — rimanda al GM il messaggio di firma o pareggio\n"
        "/firma_per_conto [asta_id] — scegli tu anni (e ruolo) al posto del GM vincitore\n"
        "/forza_aggiornamento &lt;asta_id&gt; — riscrive il messaggio dell'asta nel canale\n"
        "/ripubblica_asta &lt;asta_id&gt; — ripubblica il messaggio se è stato cancellato\n"
        "/backup_ora — backup subito sul canale log\n"
        "\n"
        "<b>🏟 Mercato</b>\n"
        "/apri_mercato · /chiudi_mercato — solo emergenza (di solito segue la fase)\n"
        "\n"
        "/guida_admin — la guida completa · /dev — comandi dev"
    )
    await update.effective_message.reply_text(testo, parse_mode="HTML")


# ── registrazione ───────────────────────────────────────────────────────────────

async def _firma_per_conto(update, context):
    from handlers.firma import cmd_firma_per_conto
    await cmd_firma_per_conto(update, context)


def get_handlers():
    return [
        CommandHandler("nuova_rfa",        nuova_rfa),
        CommandHandler("listteams",        listteams),
        CommandHandler("list",              cmd_list),
        CommandHandler("set_cap",          set_cap),
        CommandHandler("set_slot",         set_slot),
        CommandHandler("apri_mercato",     apri_mercato),
        CommandHandler("chiudi_mercato",   chiudi_mercato),
        CommandHandler("set_fase",         set_fase),
        CommandHandler("aste",             aste),
        CommandHandler("chiudi_asta",      chiudi_asta),
        CommandHandler("annulla_asta",     annulla_asta),
        CommandHandler("reset_rfa",            reset_rfa),
        CommandHandler("set_cap_penalizzato",   set_cap_penalizzato),
        CommandHandler("guida_admin",           guida_admin),
        CommandHandler("crea_offerta",          crea_offerta),
        CommandHandler("apri_asta",             apri_asta),
        CommandHandler("firme",                 cmd_firme),
        CommandHandler("all_aste",              all_aste),
        CommandHandler("riapri_asta",           riapri_asta),
        CallbackQueryHandler(riapri_annullata_callback, pattern=r"^riapri_annullata:\d+:\d+$"),
        CallbackQueryHandler(riapri_annullata_callback, pattern=r"^riapri_cap:\d+:\d+$"),
        CallbackQueryHandler(annulla_off_cap_callback,  pattern=r"^annulla_off_cap:\d+:\d+$"),
        CommandHandler("backup_ora",            cmd_backup_ora),
        CommandHandler("ripubblica_asta",       ripubblica_asta),
        CommandHandler("forza_aggiornamento",   forza_aggiornamento),
        CommandHandler("force_esito",           force_esito),
        CommandHandler("firma_per_conto",       _firma_per_conto),
        CommandHandler("estendi_asta",          estendi_asta),
        CommandHandler("sposta_asta",           sposta_asta),
        CommandHandler("stato_asta",            stato_asta),
        CallbackQueryHandler(reset_rfa_callback, pattern=r"^reset_rfa:conferma$"),
        CommandHandler("admin",            cmd_admin),
        CommandHandler("add_cap",          add_cap),
        CommandHandler("add_slot",         add_slot),
        CommandHandler("annulla_offerta",  annulla_offerta),
        CallbackQueryHandler(admin_chiudi_callback,  pattern=r"^admin_chiudi:\d+$"),
        CallbackQueryHandler(admin_annulla_callback, pattern=r"^admin_annulla:\d+$"),
        CallbackQueryHandler(admin_noop_callback,        pattern=r"^admin_noop$"),
        CallbackQueryHandler(cb_reset_cap_anticipato,    pattern=r"^reset_cap_ant:.+$"),
        CallbackQueryHandler(cb_reset_slot_anticipato,   pattern=r"^reset_slot_ant:.+$"),
    ]

"""
Pannello admin — InlineKeyboard per funzioni riservate.
Accessibile via /admin_menu (solo admin).

Funzioni:
  - Trade: Build e Import con ufficializzazione diretta
  - Altre funzioni admin (da espandere)
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

import settings
import teams as tm
from utils import ROME, format_dt

logger = logging.getLogger(__name__)

ADMIN_TRADE_BUILD_N,    \
ADMIN_TRADE_BUILD_SQ,   \
ADMIN_TRADE_BUILD_ASSET,\
ADMIN_TRADE_BUILD_PICK, \
ADMIN_TRADE_RIEPILOGO,  \
ADMIN_IMPORT_TESTO      = range(20, 26)

_ANNULLA_HINT = "\n<i>Per annullare: /annulla_admin</i>"


def is_admin(user_id: int) -> bool:
    return user_id in [int(a) for a in settings.load_globals().get("admin_ids", [])]


# ── keyboard menu admin ───────────────────────────────────────────────────────

def _kb_admin_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Trade",              callback_data="adm:trade")],
        [InlineKeyboardButton("✂️ Taglia giocatore",   callback_data="adm:taglia")],
        [InlineKeyboardButton("🏥 DPE",                callback_data="adm:dpe")],
        [InlineKeyboardButton("🏀 Attiva diritti",     callback_data="adm:rookie")],
        [InlineKeyboardButton("📊 Situazione cap",     callback_data="adm:cap")],
        [InlineKeyboardButton("🔁 Cambia fase",        callback_data="adm:set_fase")],
        [InlineKeyboardButton("↩️ Annulla trade",      callback_data="adm:annulla_trade")],
    ])


def _kb_admin_trade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔨 Build",  callback_data="adm:trade_build")],
        [InlineKeyboardButton("📥 Import", callback_data="adm:trade_import")],
        [InlineKeyboardButton("← Menu",    callback_data="adm:home")],
    ])


def _kb_ufficializza(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Ufficializza ora",  callback_data=f"adm_uff:{trade_id}")],
        [InlineKeyboardButton("📨 Manda per voto GM", callback_data=f"trade_send:gm:{trade_id}")],
        [InlineKeyboardButton("✏️ Modifica",          callback_data=f"edit_back:{trade_id}")],
        [InlineKeyboardButton("🗑️ Elimina",            callback_data=f"trade_del:{trade_id}")],
    ])


def _kb_non_valida(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Modifica",  callback_data=f"edit_back:{trade_id}")],
        [InlineKeyboardButton("🗑️ Elimina",   callback_data=f"trade_del:{trade_id}")],
    ])


# ── /admin_menu ───────────────────────────────────────────────────────────────

async def cmd_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei admin.")
        return
    await update.effective_message.reply_text(
        "🛠 <b>Pannello Admin</b>",
        parse_mode="HTML",
        reply_markup=_kb_admin_home(),
    )


async def cb_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    azione = query.data.split(":")[1]

    if azione == "home":
        await query.edit_message_text(
            "🛠 <b>Pannello Admin</b>", parse_mode="HTML",
            reply_markup=_kb_admin_home()
        )
        return ConversationHandler.END

    elif azione == "trade":
        await query.edit_message_text(
            "🔄 <b>Trade Admin</b>\nScegli modalità:",
            parse_mode="HTML", reply_markup=_kb_admin_trade()
        )
        return ConversationHandler.END

    elif azione == "trade_build":
        await query.edit_message_text(
            "🔨 <b>Build trade</b> — quante squadre?" + _ANNULLA_HINT,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("2", callback_data="adm_n:2"),
                InlineKeyboardButton("3", callback_data="adm_n:3"),
                InlineKeyboardButton("4", callback_data="adm_n:4"),
            ]])
        )
        return ADMIN_TRADE_BUILD_N

    elif azione == "trade_import":
        await query.edit_message_text(
            "📥 <b>Import trade</b>\n\nInvia il testo della trade." + _ANNULLA_HINT,
            parse_mode="HTML",
        )
        return ADMIN_IMPORT_TESTO

    elif azione == "taglia":
        # Mostra selezione team
        tutti = tm.get_all_teams()
        bottoni = [
            InlineKeyboardButton(t["nome"], callback_data=f"adm_taglia_team:{t['id']}")
            for t in tutti
        ]
        righe = [bottoni[i:i+2] for i in range(0, len(bottoni), 2)]
        righe.append([InlineKeyboardButton("← Menu", callback_data="adm:home")])
        await query.edit_message_text(
            "✂️ <b>Taglio admin</b> — seleziona squadra:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(righe),
        )
        return ConversationHandler.END

    elif azione == "dpe":
        # Rimanda al flusso DPE admin — mostra selezione team
        tutti = tm.get_all_teams()
        bottoni = [
            InlineKeyboardButton(t["nome"], callback_data=f"adm_dpe_team:{t['id']}")
            for t in tutti
        ]
        righe = [bottoni[i:i+2] for i in range(0, len(bottoni), 2)]
        righe.append([InlineKeyboardButton("← Menu", callback_data="adm:home")])
        await query.edit_message_text(
            "🏥 <b>DPE admin</b> — seleziona squadra:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(righe),
        )
        return ConversationHandler.END

    elif azione == "rookie":
        tutti = tm.get_all_teams()
        bottoni = [
            InlineKeyboardButton(t["nome"], callback_data=f"adm_rookie_team:{t['id']}")
            for t in tutti
        ]
        righe = [bottoni[i:i+2] for i in range(0, len(bottoni), 2)]
        righe.append([InlineKeyboardButton("← Menu", callback_data="adm:home")])
        await query.edit_message_text(
            "🏀 <b>Attiva diritti admin</b> — seleziona squadra:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(righe),
        )
        return ConversationHandler.END

    elif azione == "set_fase":
        # Manda un nuovo messaggio — cmd_set_fase gestisce già tutto il flusso
        # inclusi i callback set_fase:* per il cambio fase effettivo
        await query.answer()
        await cmd_set_fase(update, context)
        return ConversationHandler.END

    elif azione == "annulla_trade":
        import database as db
        trade_list = db.get_ultime_trade_approvate(15)
        if not trade_list:
            await query.edit_message_text(
                "Nessuna trade approvata da annullare.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Menu", callback_data="adm:home")]])
            )
            return ConversationHandler.END
        bottoni = [
            [InlineKeyboardButton(
                f"↩️ {t['trade_ref']}",
                callback_data=f"adm_annulla_conf:{t['id']}"
            )]
            for t in trade_list
        ]
        bottoni.append([InlineKeyboardButton("← Menu", callback_data="adm:home")])
        await query.edit_message_text(
            "↩️ <b>Annulla trade</b> — seleziona la trade da annullare:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(bottoni),
        )
        return ConversationHandler.END

    elif azione == "cap":
        import database as db
        stagione   = settings.stagione_corrente()
        cap_limite = settings.luxury_cap()
        tutti      = tm.get_all_teams()

        righe = [f"📊 <b>Riepilogo Cap — Stagione {stagione}</b>\n"]
        for team in sorted(tutti, key=lambda t: t["nome"]):
            tid        = team["id"]
            contratti  = sum(c.get("importo", 0) for c in db.get_contratti_team(tid))
            tagli      = sum(i.get("importo", 0) for i in db.get_impatto_taglio_team(tid, stagione))
            penalita   = team.get("cap_penalizzato", 0)
            dpe_rows   = db.get_dpe_team(tid, stagione)
            dpe        = sum((r.get("importo_originale", 0) - r.get("importo_dpe", 0)) for r in dpe_rows)
            totale     = contratti + tagli + penalita
            # DPE riduce il cap occupato (importo_dpe < importo_originale)
            totale_dpe = contratti - dpe + tagli + penalita
            libero     = cap_limite - totale_dpe
            stato      = "🔴" if totale_dpe > cap_limite else "✅"

            riga = f"\n{stato} <b>{team['nome']}</b>\n  \U0001f4bc Contratti: {contratti}M"
            if tagli:    riga += f"  \u2702\ufe0f Tagli: {tagli}M"
            if penalita: riga += f"  \u2696\ufe0f Penalt\xe0: {penalita}M"
            if dpe:      riga += f"  \U0001f3e5 DPE: -{dpe}M"
            riga += f"\n  \U0001f4ca Totale: <b>{totale_dpe}M</b> / {cap_limite}M  (libero: {libero}M)"
            righe.append(riga)

        testo = "\n".join(righe)
        # Telegram max 4096 chars — se troppo lungo manda in chunks
        if len(testo) <= 4096:
            await query.edit_message_text(
                testo, parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("← Menu", callback_data="adm:home")
                ]])
            )
        else:
            await query.edit_message_text("⏳ Riepilogo in arrivo...", parse_mode="HTML")
            for chunk in [testo[i:i+4096] for i in range(0, len(testo), 4096)]:
                await query.message.reply_text(chunk, parse_mode="HTML")
        return ConversationHandler.END

    return ConversationHandler.END


async def cb_adm_taglia_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin seleziona squadra → mostra roster con bottoni taglio."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    team_id = query.data.split(":")[1]
    import database as db
    from handlers.tagli import _anni_residui, _e_taglio_gratuito, calcola_spalmate, MAX_TAGLI_GRATUITI
    roster = db.get_roster_team(team_id)
    team   = tm.get_team_by_id(team_id)
    if not roster:
        await query.edit_message_text(f"Roster di {team['nome']} vuoto.")
        return
    bottoni = [
        [InlineKeyboardButton(
            f"{r['nome_common']} ({r['importo']}M)",
            callback_data=f"adm_taglia_ok:{r['giocatore_id']}:{team_id}"
        )]
        for r in roster
    ]
    bottoni.append([InlineKeyboardButton("← Indietro", callback_data="adm:taglia")])
    await query.edit_message_text(
        f"✂️ <b>Taglio admin — {team['nome']}</b>\nSeleziona giocatore:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )


async def cb_adm_taglia_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin conferma il taglio diretto."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    _, gid_s, team_id = query.data.split(":")
    gid = int(gid_s)

    import database as db
    from handlers.tagli import (
        _anni_residui, _e_taglio_gratuito, calcola_spalmate, MAX_TAGLI_GRATUITI
    )
    import settings

    contratto = db.get_contratto_attivo(gid)
    if not contratto:
        await query.edit_message_text("❌ Nessun contratto attivo trovato.")
        return

    giocatore = db.get_giocatore(gid)
    stagione  = settings.stagione_corrente()
    anni_res  = _anni_residui(contratto, stagione)
    gratuito  = _e_taglio_gratuito(contratto["importo"], anni_res)

    if gratuito:
        usati = db.get_tagli_gratuiti_usati(team_id, stagione)
        gratuito = usati < MAX_TAGLI_GRATUITI

    from database import _q
    _q("UPDATE contratti SET attivo = FALSE WHERE id = %s", (contratto["id"],))

    if gratuito:
        db.registra_transazione(
            "cut", gid, team_id, None, stagione,
            contratto_id=contratto["id"], gratuito=True,
            note=f"Taglio admin senza impatto — {giocatore['nome_common']}"
        )
        usati_now = db.get_tagli_gratuiti_usati(team_id, stagione)
        await query.edit_message_text(
            f"✅ <b>{giocatore['nome_common']}</b> tagliato senza impatto.\n"
            f"Tagli senza impatto usati: <b>{usati_now}/{MAX_TAGLI_GRATUITI}</b>",
            parse_mode="HTML",
        )
    else:
        rate = calcola_impatto_taglio(contratto["importo"], anni_res, stagione)
        trans_id = db.registra_transazione(
            "cut", gid, team_id, None, stagione,
            contratto_id=contratto["id"], gratuito=False,
            note=f"Taglio admin — {giocatore['nome_common']} {contratto['importo']}M x{anni_res}"
        )
        for r in rate:
            _q(
                "INSERT INTO impatto_taglio (team_id, giocatore_id, stagione_taglio, stagione, importo, transazione_id) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (team_id, gid, stagione, r["stagione"], r["importo"], trans_id)
            )
        righe = "\n".join(f"  • {r['stagione']}: {r['importo']}M" for r in rate)
        await query.edit_message_text(
            f"✅ <b>{giocatore['nome_common']}</b> tagliato.\n\nImpatto taglio:\n{righe}",
            parse_mode="HTML",
        )
    logger.info("Taglio admin: team=%s giocatore=%d admin=%d",
                team_id, gid, update.effective_user.id)


# ── Admin build trade ─────────────────────────────────────────────────────────
# Riusa i callback del builder GM ma con proposta_da = "admin"
# e tastiera finale con "Ufficializza ora"

async def cb_adm_n_squadre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    import database as db
    n = int(query.data.split(":")[1])
    stagione = settings.stagione_corrente()
    trade_id = db.crea_trade_bozza("admin", n, stagione)
    context.user_data["adm_trade_id"]           = trade_id
    context.user_data["adm_trade_squadre"]       = []
    context.user_data["adm_trade_squadre_left"]  = n

    tutti = tm.get_all_teams()
    bottoni = [
        InlineKeyboardButton(t["nome"], callback_data=f"adm_sq:{trade_id}:{t['id']}")
        for t in tutti
    ]
    righe = [bottoni[i:i+2] for i in range(0, len(bottoni), 2)]
    await query.edit_message_text(
        f"Seleziona le {n} squadre coinvolte:" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(righe),
    )
    return ADMIN_TRADE_BUILD_SQ


async def cb_adm_seleziona_squadra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    import database as db
    _, trade_id_s, team_id = query.data.split(":")
    trade_id = int(trade_id_s)

    ordine = context.user_data.get("adm_trade_squadre", [])
    ordine.append(team_id)
    context.user_data["adm_trade_squadre"] = ordine
    db.aggiungi_squadra_trade(trade_id, team_id, len(ordine))

    n = db.get_trade(trade_id)["n_squadre"]
    if len(ordine) < n:
        tutti = tm.get_all_teams()
        bottoni = [
            InlineKeyboardButton(t["nome"], callback_data=f"adm_sq:{trade_id}:{t['id']}")
            for t in tutti if t["id"] not in ordine
        ]
        righe = [bottoni[i:i+2] for i in range(0, len(bottoni), 2)]
        await query.edit_message_text(
            f"Seleziona ancora {n - len(ordine)} squadra/e:" + _ANNULLA_HINT,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(righe),
        )
        return ADMIN_TRADE_BUILD_SQ

    # Tutte selezionate → vai ad asset con il builder standard
    from handlers.trade import _vai_ad_asset
    context.user_data["trade_id"]               = trade_id
    context.user_data["trade_squadre_ordine"]    = ordine
    context.user_data["trade_squadra_corrente_idx"] = 0
    return await _vai_ad_asset(query, context, trade_id)


# ── Admin import ──────────────────────────────────────────────────────────────

async def admin_import_ricevi_testo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from handlers.trade_parser import parsa_trade, crea_trade_da_parse, formatta_trade
    from validators.trade import valida_trade

    testo      = update.effective_message.text
    stagione   = settings.stagione_corrente()
    tutti_team = tm.get_all_teams()

    squadre, errori_parse = parsa_trade(testo, stagione, tutti_team)

    if errori_parse or not squadre:
        righe = ["❌ <b>Errori nel parsing — bozza non salvata:</b>\n"]
        for e in errori_parse or ["Nessuna squadra riconosciuta."]:
            righe.append(f"  • {e}")
        righe.append("\nCorreggi e reinvia, oppure /annulla_admin per uscire.")
        await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")
        return ADMIN_IMPORT_TESTO

    trade_id = crea_trade_da_parse(squadre, stagione, "admin")
    ok, errori_val = valida_trade(trade_id)

    risposta = [f"📋 <b>Trade #{trade_id}</b>\n", formatta_trade(squadre)]
    if ok:
        risposta.append("\n✅ <b>Validazione OK</b>")
    else:
        risposta.append("\n⚠️ <b>Problemi:</b>")
        for e in errori_val:
            risposta.append(f"  {e}")

    await update.effective_message.reply_text(
        "\n".join(risposta),
        parse_mode="HTML",
        reply_markup=_kb_ufficializza(trade_id) if ok else _kb_non_valida(trade_id),
    )
    return ConversationHandler.END


# ── Ufficializza ora ──────────────────────────────────────────────────────────

async def cb_ufficializza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin ufficializza direttamente senza voto GM."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        await query.answer("⛔ Non sei admin.", show_alert=True)
        return

    trade_id = int(query.data.split(":")[1])
    # Delega al callback admin già esistente in trade.py
    from handlers.trade import _esegui_trade, _testo_riepilogo
    import database as db
    from datetime import datetime

    trade    = db.get_trade(trade_id)
    stagione = trade["stagione"]
    n_trade  = db.get_trade_count_approvate(stagione)
    trade_ref = f"TRADE-{stagione}-{n_trade + 1:03d}"

    admin_nome = update.effective_user.first_name or str(update.effective_user.id)
    await _esegui_trade(context, trade_id)
    db.approva_trade(trade_id, trade_ref, admin_nome)

    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        ora = format_dt(datetime.now(ROME))
        try:
            await context.bot.send_message(
                chat_id=main_channel,
                text=(
                    f"🔄 <b>Trade ufficializzata</b>\n\n"
                    f"{_testo_riepilogo(trade_id)}\n\n"
                    f"<i>Approvata da {admin_nome} alle {ora}\n"
                    f"ID: <code>{trade_ref}</code></i>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Annuncio canale fallito: %s", e)

    await query.edit_message_text(
        f"✅ <b>{trade_ref}</b> ufficializzata.",
        parse_mode="HTML",
    )


async def cmd_annulla_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for k in ["adm_trade_id", "adm_trade_squadre", "adm_trade_squadre_left"]:
        context.user_data.pop(k, None)
    await update.effective_message.reply_text("Operazione annullata.")
    return ConversationHandler.END


# ── registrazione ─────────────────────────────────────────────────────────────

FASI_ORDINE = [
    "regular-season-fa",
    "regular-season-deadline",
    "playoff",
    "offseason-break",
    "offseason-rinnovi",
    "offseason-draft",
    "offseason-rfa",
    "offseason-fa",
]

FASI_LABEL = {
    "regular-season-fa":       "🏀 Regular Season (FA aperta)",
    "regular-season-deadline": "🔒 Regular Season (dopo deadline)",
    "playoff":                 "🏆 Playoff",
    "offseason-break":         "😴 Offseason Break",
    "offseason-rinnovi":       "📝 Offseason — Rinnovi",
    "offseason-draft":         "🎯 Offseason — Draft",
    "offseason-rfa":           "⚖️ Offseason — RFA",
    "offseason-fa":            "💸 Offseason — Free Agency",
}


def _prossima_fase(fase_corrente: str) -> str:
    try:
        idx = FASI_ORDINE.index(fase_corrente)
        return FASI_ORDINE[(idx + 1) % len(FASI_ORDINE)]
    except ValueError:
        return FASI_ORDINE[0]


def _kb_set_fase(fase_corrente: str) -> InlineKeyboardMarkup:
    prossima = _prossima_fase(fase_corrente)
    bottoni = [
        [InlineKeyboardButton(
            f"✅ Avanza → {FASI_LABEL.get(prossima, prossima)}",
            callback_data=f"fase_set:{prossima}:normal"
        )],
        [InlineKeyboardButton("⚠️ Salta a...", callback_data="fase_salta_menu")],
        [InlineKeyboardButton("❌ Annulla", callback_data="fase_annulla")],
    ]
    return InlineKeyboardMarkup(bottoni)


def _kb_salta_fase(fase_corrente: str) -> InlineKeyboardMarkup:
    bottoni = []
    for f in FASI_ORDINE:
        if f != fase_corrente:
            bottoni.append([InlineKeyboardButton(
                f"⚠️ {FASI_LABEL.get(f, f)}",
                callback_data=f"fase_set:{f}:skip"
            )])
    bottoni.append([InlineKeyboardButton("← Indietro", callback_data="fase_indietro")])
    return InlineKeyboardMarkup(bottoni)


async def cmd_set_fase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solo admin: mostra la fase corrente e permette di cambiarla."""
    user = update.effective_user
    if user.id not in settings.admin_ids():
        return
    fase_corrente = settings.fase()
    testo = (
        f"⚙️ <b>Gestione Fase</b>\n\n"
        f"Fase corrente: <b>{FASI_LABEL.get(fase_corrente, fase_corrente)}</b>\n\n"
        f"Seleziona l'azione:"
    )
    await update.effective_message.reply_text(
        testo, parse_mode="HTML", reply_markup=_kb_set_fase(fase_corrente)
    )


async def cb_fase_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: imposta la nuova fase."""
    query = update.callback_query
    if query.from_user.id not in settings.admin_ids():
        await query.answer("⛔ Non autorizzato.")
        return
    await query.answer()

    _, nuova_fase, tipo = query.data.split(":")
    fase_vecchia = settings.fase()

    if tipo == "skip":
        warning = (
            f"⚠️ <b>Attenzione!</b> Stai saltando direttamente a:\n"
            f"<b>{FASI_LABEL.get(nuova_fase, nuova_fase)}</b>\n\n"
            f"Dalla fase: <b>{FASI_LABEL.get(fase_vecchia, fase_vecchia)}</b>\n\n"
            f"Sei sicuro?"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confermo", callback_data=f"fase_conferma:{nuova_fase}"),
            InlineKeyboardButton("❌ No", callback_data="fase_annulla"),
        ]])
        await query.edit_message_text(warning, parse_mode="HTML", reply_markup=kb)
        return

    # Avanzamento normale — conferma diretta
    await _esegui_cambio_fase(query, fase_vecchia, nuova_fase)


async def cb_fase_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in settings.admin_ids():
        await query.answer("⛔ Non autorizzato.")
        return
    await query.answer()
    nuova_fase = query.data.split(":")[1]
    fase_vecchia = settings.fase()
    await _esegui_cambio_fase(query, fase_vecchia, nuova_fase)


async def cb_fase_salta_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in settings.admin_ids():
        await query.answer()
        return
    await query.answer()
    fase_corrente = settings.fase()
    await query.edit_message_text(
        f"⚠️ <b>Salta a fase</b>\n\nFase corrente: <b>{FASI_LABEL.get(fase_corrente, fase_corrente)}</b>",
        parse_mode="HTML",
        reply_markup=_kb_salta_fase(fase_corrente),
    )


async def cb_fase_indietro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    fase_corrente = settings.fase()
    await query.edit_message_text(
        f"⚙️ <b>Gestione Fase</b>\n\nFase corrente: <b>{FASI_LABEL.get(fase_corrente, fase_corrente)}</b>",
        parse_mode="HTML",
        reply_markup=_kb_set_fase(fase_corrente),
    )


async def cb_fase_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Cambio fase annullato.")


async def _esegui_cambio_fase(query, fase_vecchia: str, nuova_fase: str):
    """Scrive la nuova fase in globals.json e notifica."""
    import json, os
    globals_path = os.environ.get("GLOBALS_PATH", "/config/globals.json")
    g = json.load(open(globals_path))
    g["fase"] = nuova_fase
    g["mercato_aperto"] = nuova_fase in ("regular-season-fa", "offseason-fa")

    # Incrementa stagione_corrente quando si entra in offseason-rinnovi
    nota_stagione = ""
    if nuova_fase == "offseason-rinnovi" and fase_vecchia != "offseason-rinnovi":
        stagione_nuova = int(g.get("stagione_corrente", 2026)) + 1
        g["stagione_corrente"] = str(stagione_nuova)
        nota_stagione = f"\n📅 Stagione aggiornata: <b>{stagione_nuova}</b>"

    json.dump(g, open(globals_path, "w"), indent=2, ensure_ascii=False)

    testo = (
        f"✅ Fase aggiornata:\n"
        f"<b>{FASI_LABEL.get(fase_vecchia, fase_vecchia)}</b> → "
        f"<b>{FASI_LABEL.get(nuova_fase, nuova_fase)}</b>"
        f"{nota_stagione}"
    )
    await query.edit_message_text(testo, parse_mode="HTML")

    # Notifica al canale log
    try:
        g2 = json.load(open(globals_path))
        log_ch = g2.get("log_channel_id_main")
        if log_ch:
            await query.bot.send_message(
                chat_id=log_ch,
                text=f"⚙️ {testo}",
                parse_mode="HTML",
            )
    except Exception:
        pass


async def cb_adm_dpe_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin seleziona team per DPE → mostra roster."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    import database as db
    import math
    team_id  = query.data.split(":")[1]
    team     = tm.get_team_by_id(team_id)
    roster   = db.get_roster_team(team_id)
    stagione = settings.stagione_corrente()
    if not roster:
        await query.edit_message_text(f"Roster di {team['nome']} vuoto.")
        return
    bottoni = []
    for r in roster:
        if db.get_dpe_attiva(r["giocatore_id"], stagione):
            continue
        importo_dpe = math.ceil(r["importo"] * 0.75)
        risparmio   = r["importo"] - importo_dpe
        label = f"{r['nome_common']} {r['importo']}M → {importo_dpe}M (-{risparmio}M)"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"adm_dpe_conf:{team_id}:{r['giocatore_id']}")])
    if not bottoni:
        await query.edit_message_text("Tutti i giocatori hanno già una DPE attiva questa stagione.")
        return
    bottoni.append([InlineKeyboardButton("← Menu", callback_data="adm:home")])
    await query.edit_message_text(
        f"🏥 <b>DPE admin — {team['nome']}</b>\nSeleziona giocatore:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )


async def cb_adm_dpe_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin conferma DPE — scrittura diretta DB senza approvazione."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    import database as db
    import math
    parts        = query.data.split(":")
    team_id      = parts[1]
    giocatore_id = int(parts[2])
    stagione     = settings.stagione_corrente()
    fase         = settings.fase()
    pre_deadline = (fase == "regular-season-fa")
    team      = tm.get_team_by_id(team_id)
    giocatore = db.get_giocatore(giocatore_id)
    contratto = db.get_contratto_attivo(giocatore_id)
    if not contratto:
        await query.edit_message_text("❌ Contratto non trovato.")
        return
    if db.get_dpe_attiva(giocatore_id, stagione):
        await query.edit_message_text("❌ DPE già attiva per questo giocatore.")
        return
    importo_orig = contratto["importo"]
    importo_dpe  = math.ceil(importo_orig * 0.75)
    risparmio    = importo_orig - importo_dpe
    admin_user   = update.effective_user
    admin_tag    = admin_user.first_name or str(admin_user.id)
    if admin_user.username:
        admin_tag += f" (@{admin_user.username})"
    db.inserisci_dpe(
        giocatore_id=giocatore_id, team_id=team_id, stagione=stagione,
        importo_originale=importo_orig, importo_dpe=importo_dpe,
        pre_deadline=pre_deadline, approvata_da=admin_tag,
    )
    if pre_deadline:
        tm.set_slot(team_id, team["slot_disponibili"] + 1)
    effetto = "✅ Slot roster liberato" if pre_deadline else "ℹ️ Nessuno slot liberato (post-deadline)"
    await query.edit_message_text(
        f"✅ DPE registrata — <b>{giocatore['nome_common']}</b>\n"
        f"{importo_orig}M → {importo_dpe}M (stagione {stagione})\n{effetto}",
        parse_mode="HTML",
    )
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        testo = (
            f"🏥 <b>{team['nome']}</b> — DPE <b>{giocatore['nome_common']}</b>\n"
            f"Contratto {stagione}: {importo_orig}M → <b>{importo_dpe}M</b> (-{risparmio}M)\n"
            f"{effetto}\n🔧 Ufficializzato da {admin_tag}"
        )
        try:
            await context.bot.send_message(chat_id=main_channel, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio canale DPE admin fallito: %s", e)


async def cb_adm_annulla_conf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin seleziona trade → conferma annullamento."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    trade_id = int(query.data.split(":")[1])
    import database as db
    trade = db.get_trade(trade_id)
    if not trade:
        await query.edit_message_text("❌ Trade non trovata.")
        return
    if trade["stato"] != "approvata":
        await query.edit_message_text(f"❌ Trade in stato '{trade['stato']}' — solo le approvate possono essere annullate.")
        return
    # Mostra riepilogo con bottone conferma
    from handlers.trade import _testo_riepilogo
    testo = _testo_riepilogo(trade_id)
    await query.edit_message_text(
        f"{testo}\n\n⚠️ Confermi l'annullamento?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sì, annulla", callback_data=f"adm_annulla_exec:{trade_id}")],
            [InlineKeyboardButton("❌ No, indietro", callback_data="adm:annulla_trade")],
        ])
    )


async def cb_adm_annulla_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin esegue il rollback della trade."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    trade_id = int(query.data.split(":")[1])
    import database as db
    from handlers.trade import _valida_rollback, _rollback_trade, format_dt, ROME
    from settings import load_globals
    from datetime import datetime

    trade = db.get_trade(trade_id)
    if not trade:
        await query.edit_message_text("❌ Trade non trovata.")
        return

    await query.edit_message_text("⏳ Verifica compatibilità...")
    errori = await _valida_rollback(trade_id)
    if errori:
        testo = "❌ <b>Impossibile annullare</b>\n\n" + "\n".join(f"  • {e}" for e in errori)
        await query.edit_message_text(testo, parse_mode="HTML")
        return

    await _rollback_trade(trade_id)

    admin_user = update.effective_user
    admin_tag  = admin_user.first_name or str(admin_user.id)
    if admin_user.username:
        admin_tag += f" (@{admin_user.username})"
    ora = format_dt(datetime.now(ROME))
    trade_ref = trade["trade_ref"]

    main_channel = load_globals().get("main_channel_id")
    if main_channel:
        try:
            await context.bot.send_message(
                chat_id=main_channel,
                text=(
                    f"⚠️ <b>Trade annullata</b>\n\n"
                    f"La trade <code>{trade_ref}</code> è stata annullata.\n"
                    f"Tutti i giocatori e le pick sono stati ripristinati.\n\n"
                    f"<i>Annullata da {admin_tag} alle {ora}</i>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Annuncio annullamento canale fallito: %s", e)

    await query.edit_message_text(
        f"✅ <b>{trade_ref}</b> annullata. Roster e pick ripristinati.",
        parse_mode="HTML",
    )


def get_handlers() -> list:
    from handlers.trade import (
        TRADE_ASSET_MENU, TRADE_ASSET_GIOCATORI, TRADE_ASSET_PICK, TRADE_RIEPILOGO,
        cb_asset_menu, cb_toggle_giocatore, cb_toggle_pick, cb_send_trade,
        cmd_annulla_trade,
    )

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("admin_menu", cmd_admin_menu),
            CallbackQueryHandler(cb_admin, pattern=r"^adm:[a-z_]+$"),
        ],
        states={
            ADMIN_TRADE_BUILD_N: [
                CallbackQueryHandler(cb_adm_n_squadre, pattern=r"^adm_n:\d$"),
            ],
            ADMIN_TRADE_BUILD_SQ: [
                CallbackQueryHandler(cb_adm_seleziona_squadra, pattern=r"^adm_sq:\d+:.+$"),
            ],
            # Riusa gli stati del builder GM per la selezione asset
            TRADE_ASSET_MENU: [
                CallbackQueryHandler(cb_asset_menu, pattern=r"^trade_am:.+$"),
            ],
            TRADE_ASSET_GIOCATORI: [
                CallbackQueryHandler(cb_toggle_giocatore, pattern=r"^trade_gi:.+$"),
                CallbackQueryHandler(cb_asset_menu,       pattern=r"^trade_am:.+$"),
            ],
            TRADE_ASSET_PICK: [
                CallbackQueryHandler(cb_toggle_pick,  pattern=r"^trade_pi:.+$"),
                CallbackQueryHandler(cb_asset_menu,   pattern=r"^trade_am:.+$"),
            ],
            TRADE_RIEPILOGO: [
                CallbackQueryHandler(cb_send_trade, pattern=r"^trade_send:.+$"),
            ],
            ADMIN_IMPORT_TESTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_import_ricevi_testo),
            ],
        },
        fallbacks=[
            CommandHandler("annulla_admin", cmd_annulla_admin),
            CommandHandler("annulla_trade", cmd_annulla_trade),
        ],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )

    return [
        conv,
        CommandHandler("admin_menu", cmd_admin_menu),
        CallbackQueryHandler(cb_adm_dpe_team,     pattern=r"^adm_dpe_team:.+$"),
        CallbackQueryHandler(cb_adm_annulla_conf,  pattern=r"^adm_annulla_conf:\d+$"),
        CallbackQueryHandler(cb_adm_annulla_exec,  pattern=r"^adm_annulla_exec:\d+$"),
        CallbackQueryHandler(cb_adm_dpe_conferma, pattern=r"^adm_dpe_conf:.+:\d+$"),
        CommandHandler("set_fase",   cmd_set_fase),
        CallbackQueryHandler(cb_ufficializza,        pattern=r"^adm_uff:\d+$"),
        CallbackQueryHandler(cb_adm_taglia_team,     pattern=r"^adm_taglia_team:.+$"),
        CallbackQueryHandler(cb_adm_taglia_conferma, pattern=r"^adm_taglia_ok:\d+:.+$"),
        CallbackQueryHandler(cb_fase_set,            pattern=r"^fase_set:.+:.+$"),
        CallbackQueryHandler(cb_fase_conferma,       pattern=r"^fase_conferma:.+$"),
        CallbackQueryHandler(cb_fase_salta_menu,     pattern=r"^fase_salta_menu$"),
        CallbackQueryHandler(cb_fase_indietro,       pattern=r"^fase_indietro$"),
        CallbackQueryHandler(cb_fase_annulla,        pattern=r"^fase_annulla$"),
    ]

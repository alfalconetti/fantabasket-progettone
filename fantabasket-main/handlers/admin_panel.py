"""
Pannello admin — InlineKeyboard per funzioni riservate.
Accessibile via /admin_menu (solo admin).

Menu dinamico per fase. Regola: ogni azione che può fare un GM ha qui il suo
equivalente "per conto di" una squadra (trade, tagli, diritti, decadimento, DPE,
ruoli, cambi ruolo) + situazione cap di tutte le squadre.
"""
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

import settings
import teams as tm
import database as db
from handlers.dpe import _importo_dpe
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
    """Menu admin dinamico per fase, come il /menu dei GM. Regola: ogni azione che può
    fare un GM ha qui il suo equivalente "per conto di" una squadra."""
    from handlers.dpe import FASI_DPE
    from handlers.stagione import FASI_ADMIN_RINNOVI
    fase = settings.fase()
    voci = [
        ("🔄 Trade",            "adm:trade",   True),
        ("✂️ Taglia giocatore", "adm:taglia",  True),
        ("🏀 Attiva diritti",   "adm:rookie",  True),
        ("🏁 Decadimento",      "adm:dec",     True),
        ("🏥 DPE",              "adm:dpe",     fase in FASI_DPE),
        ("🎽 Ruoli squadre",    "rladm:list",  True),   # dichiarazione per conto dei GM, anche fuori fase
        ("⏳ Ruoli in sospeso", "rpadm:list",  fase in settings.FASI_RUOLI_RS),
        ("🔁 Cambi ruolo",      "cradm:teams", fase in settings.FASI_RUOLI_RS),
        ("⏱ 10-day",           "tdadm:list",  fase in settings.FASI_RUOLI_RS),
        ("🔁 Rinnovi rookie",   "sga:scegli:rr",  fase in FASI_ADMIN_RINNOVI),
        ("🔒 RFA squadre",      "sga:scegli:rfa", fase in FASI_ADMIN_RINNOVI),
        ("⚠️ Penalità",         "pen:adm",     True),
        ("📊 Situazione cap",   "adm:cap",     True),
        ("⚙️ Impostazioni",     "set:home",    True),
        ("🩺 Controllo dati",   "rdati:md",    True),
        ("📜 Registro",         "reg:7",       True),
    ]
    bottoni = [InlineKeyboardButton(l, callback_data=cb) for l, cb, ok in voci if ok]
    from handlers import nav
    return InlineKeyboardMarkup([bottoni[i:i + 2] for i in range(0, len(bottoni), 2)] + [[nav.chiudi()]])


def _testo_admin_home() -> str:
    etichetta = FASI_LABEL.get(settings.fase(), settings.fase())
    return f"🛠 <b>Pannello Admin</b>\nFase: {etichetta}"


def _testo_cap() -> str:
    """Cap occupato / tetto attuale e giocatori a roster di tutte le squadre."""
    stagione = settings.stagione_corrente()
    offseason = settings.fase().startswith("offseason")
    righe = []
    for t in tm.get_all_teams():
        cap = db.cap_occupato_team(t["id"], stagione)
        limite = settings.cap_limite_team(t)
        cap_rs = settings.cap_massimo() - int(t.get("cap_penalizzato") or 0)
        n = db.slot_occupati(db.get_roster_team(t["id"]) or [])
        if cap > limite:
            segno = "🔴"
        elif offseason and cap > cap_rs:
            segno = "🟠"
        elif not offseason and cap < settings.salary_floor():
            segno = "🔵"
        else:
            segno = "🟢"
        righe.append((cap, f"{segno} <b>{t['nome']}</b>: {cap}/{limite}M · {n} gioc."))
    righe.sort(key=lambda x: -x[0])
    nota = ("\n\n🔴 sopra il tetto · 🟠 sopra il tetto della regular season (150M − penalità): "
            "va riportato in regola prima dell'inizio" if offseason
            else f"\n\n🔴 sopra il tetto · 🔵 sotto il salary floor ({settings.salary_floor()}M)")
    return ("📊 <b>Situazione cap</b> — stagione " + stagione + "\n\n" +
            "\n".join(r for _, r in righe) + nota)


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
        _testo_admin_home(),
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
            _testo_admin_home(), parse_mode="HTML",
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
            ], [InlineKeyboardButton("← Trade", callback_data="adm:trade")]])
        )
        return ADMIN_TRADE_BUILD_N

    elif azione == "trade_import":
        await query.edit_message_text(
            "📥 <b>Import trade</b>\n\nInvia il testo della trade." + _ANNULLA_HINT,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Trade", callback_data="adm:trade")]]),
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
        from handlers.dpe import FASI_DPE
        fase = settings.fase()
        if fase not in FASI_DPE:
            await query.answer("❌ DPE non disponibile in questa fase.", show_alert=True)
            return ConversationHandler.END
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

    elif azione == "cap":
        await query.edit_message_text(
            _testo_cap(), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Menu", callback_data="adm:home")]]))
        return ConversationHandler.END

    elif azione == "rookie":
        from handlers.rookie import admin_lista_team
        await admin_lista_team(query)
        return ConversationHandler.END

    elif azione == "dec":
        from handlers.decadimento import admin_lista_team
        await admin_lista_team(query)
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
    roster = db.get_roster_team(team_id, senza_10day=True)
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
    """Admin sceglie il giocatore → la stessa anteprima dei GM, con conferma (v3.10.0: prima il
    tap tagliava subito, senza anteprima né controlli di regular season)."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    _, gid_s, team_id = query.data.split(":")
    from handlers.tagli import _mostra_anteprima_taglio
    team = tm.get_team_by_id(team_id)
    await _mostra_anteprima_taglio(query, team, int(gid_s),
                                   cb_ok=f"adm_taglia_si:{gid_s}:{team_id}", cb_no=f"adm_taglia_team:{team_id}")


async def cb_adm_taglia_esegui(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin conferma: stesso taglio dei GM (regole, atomicità), più avviso al GM."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    _, gid_s, team_id = query.data.split(":")
    from handlers.tagli import esegui_taglio, testi_taglio, dopo_taglio, TaglioNonEseguibile
    team = tm.get_team_by_id(team_id)
    try:
        v = esegui_taglio(team, int(gid_s))
    except TaglioNonEseguibile as e:
        await query.edit_message_text(str(e))
        return
    risposta, _ = testi_taglio(team, v)
    await query.edit_message_text(risposta, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("✂️ Altro taglio", callback_data="adm:taglia"),
          InlineKeyboardButton("← Menu admin", callback_data="adm:home")]]))
    admin = update.effective_user
    await dopo_taglio(context.bot, team, v, admin_nome=admin.first_name or admin.username or str(admin.id), user=admin)
    logger.info("Taglio admin: team=%s giocatore=%s admin=%d", team_id, gid_s, admin.id)


# ── Admin DPE diretta ────────────────────────────────────────────────────────

async def cb_adm_dpe_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin seleziona squadra per DPE → mostra roster eleggibile."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    import database as db
    import math

    team_id  = query.data.split(":")[1]
    team     = tm.get_team_by_id(team_id)
    stagione = settings.stagione_corrente()
    roster   = db.get_roster_team(team_id, senza_10day=True)

    eligibili = [
        r for r in roster
        if not db.get_dpe_attiva(r["giocatore_id"], stagione)
    ]
    if not eligibili:
        await query.edit_message_text(
            f"❌ Tutti i giocatori di <b>{team['nome']}</b> hanno già una DPE attiva.",
            parse_mode="HTML",
        )
        return

    bottoni = [
        [InlineKeyboardButton(
            f"{r['nome_common']} ({r['importo']}M → {_importo_dpe(r['importo'])}M)",
            callback_data=f"adm_dpe_gi:{r['giocatore_id']}:{team_id}"
        )]
        for r in eligibili
    ]
    bottoni.append([InlineKeyboardButton("← Indietro", callback_data="adm:dpe")])
    await query.edit_message_text(
        f"🏥 <b>DPE admin — {team['nome']}</b>\nSeleziona giocatore:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )


async def cb_adm_dpe_giocatore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin seleziona giocatore → mostra preview e chiede conferma."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    import database as db
    import math

    _, gid_s, team_id = query.data.split(":")
    gid = int(gid_s)

    contratto = db.get_contratto_attivo(gid)
    if not contratto or contratto["team_id"] != team_id:
        await query.edit_message_text("❌ Giocatore non trovato nel roster.")
        return

    giocatore    = db.get_giocatore(gid)
    stagione     = settings.stagione_corrente()
    fase         = settings.fase()
    pre_deadline = (fase != "regular-season-deadline")
    importo_orig = contratto["importo"]
    importo_new  = _importo_dpe(importo_orig)
    risparmio    = importo_orig - importo_new
    from handlers.dpe import _effetto
    effetto      = _effetto(pre_deadline, gid)

    testo = (
        f"🏥 <b>DPE admin — {giocatore['nome_common']}</b>\n\n"
        f"Contratto attuale: <b>{importo_orig}M</b>\n"
        f"Contratto DPE (stagione {stagione}): <b>{importo_new}M</b> (-{risparmio}M)\n"
        f"Il contratto torna normale dalla stagione successiva.\n\n"
        f"{effetto}\n\n"
        f"<i>Operazione diretta — nessuna approvazione richiesta.</i>"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma", callback_data=f"adm_dpe_ok:{gid}:{team_id}:{importo_orig}:{importo_new}:{1 if pre_deadline else 0}"),
        InlineKeyboardButton("❌ Annulla",  callback_data=f"adm_dpe_team:{team_id}"),
    ]])
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)


async def cb_adm_dpe_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin conferma DPE diretta → scrittura DB + annuncio canale."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    import database as db

    parts   = query.data.split(":")
    gid     = int(parts[1])
    team_id = parts[2]
    # Importi e pre/post deadline ricalcolati adesso (non quelli della schermata di conferma)
    from handlers.dpe import applica_dpe, _admin_tag
    errore, esito = await applica_dpe(query.get_bot(), gid, team_id, _admin_tag(update.effective_user), da_admin=True,
                                      user=update.effective_user)
    if not errore:
        db.chiudi_richiesta("dpe", gid, "approvata", _admin_tag(update.effective_user))  # eventuale richiesta del GM
    await query.edit_message_text(errore or esito, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Menu admin", callback_data="adm:home")]]))


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
    from handlers.trade_comune import _btn_annulla
    righe.append([_btn_annulla()])
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
    if team_id in ordine:        # doppio tap sullo stesso bottone
        return ADMIN_TRADE_BUILD_SQ
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
        from handlers.trade_comune import _btn_annulla
        righe.append([_btn_annulla()])
        await query.edit_message_text(
            f"Seleziona ancora {n - len(ordine)} squadra/e:" + _ANNULLA_HINT,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(righe),
        )
        return ADMIN_TRADE_BUILD_SQ

    # Tutte selezionate → vai ad asset con il builder standard
    from handlers.trade_crea import _vai_ad_asset
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
    from handlers.trade_comune import segna_trade
    await segna_trade(context.bot, update.effective_user, "admin", "bozza trade importata", trade_id, dopo="bozza")
    ok, errori_val = valida_trade(trade_id)

    trade_obj = db.get_trade(trade_id)
    from handlers.trade_comune import _label_bozza
    risposta = [f"📋 <b>Bozza {_label_bozza(trade_obj)}</b>\n", formatta_trade(squadre)]
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
    from handlers.trade_esegui import _esegui_trade, TradeNonEseguibile
    from handlers.trade_comune import _formatta_annuncio_canale, _label_bozza
    import database as db
    from datetime import datetime

    trade    = db.get_trade(trade_id)
    stagione = trade["stagione"]
    n_trade  = db.get_trade_count_approvate(stagione)
    trade_ref = f"TRADE-{stagione}-{n_trade + 1:03d}"

    admin_nome = update.effective_user.first_name or str(update.effective_user.id)
    try:
        await _esegui_trade(context, trade_id, trade_ref, approvata_da=admin_nome, user=update.effective_user)
    except TradeNonEseguibile as e:
        await query.edit_message_text(
            f"❌ <b>Trade non ufficializzata</b>: {e}.\nNessuna modifica è stata salvata.",
            parse_mode="HTML")
        return

    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        ora = format_dt(datetime.now(ROME))
        try:
            await context.bot.send_message(
                chat_id=main_channel,
                text=(
                    f"{_formatta_annuncio_canale(trade_id)}\n\n"
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
    "offseason-ruoli",
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
    "offseason-ruoli":         "🎽 Offseason — Dichiarazione ruoli",
}


# Indicazioni specifiche per fase (le righe su trade/FA/DPE sono calcolate dalle
# stesse costanti usate dai comandi, così l'annuncio non può contraddire il bot)
FASI_INDICAZIONI = {
    "regular-season-fa": [
        "Dopo una trade, una firma o l'attivazione dei diritti il bot vi manda in privato i bottoni per dichiarare il ruolo dei nuovi giocatori: avete 48h, poi il ruolo viene estratto a caso tra quelli eleggibili",
        "Cambi ruolo con /cambio_ruolo (o 🔁 nel /menu): massimo 2 ordinari a stagione; gratuiti l'Erminio (ruolo aggiunto da Yahoo negli ultimi 14 giorni) e la Saedro (10 day, una volta a stagione, su approvazione admin)",
        "Le trade devono lasciare i roster in regola coi ruoli minimi (4 guardie, 4 ali, 2 centri)",
        "10-day contract: uno a stagione per squadra, valutato dagli admin",
        "I diritti delle 2nd al secondo anno scadono 10 giorni prima della deadline",
        "Cap massimo 150M (meno eventuali penalità)",
    ],
    "regular-season-deadline": [
        "Mercato chiuso fino alla prossima stagione: niente trade né free agency",
        "Cambi ruolo ancora disponibili con /cambio_ruolo (stesso contatore della stagione)",
        "La DPE dopo la deadline non libera slot, ma dà un cambio ruolo aggiuntivo",
    ],
    "playoff": [
        "Nelle partite di playoff il bonus casa è di 5 punti",
        "Cambi ruolo ancora disponibili con /cambio_ruolo (stesso contatore della stagione)",
    ],
    "offseason-break": [
        "Pausa di fine stagione: a breve la riunione di lega per proporre e votare modifiche al regolamento",
    ],
    "offseason-rinnovi": [
        "Nuova stagione: la durata di tutti i contratti scala di un anno. I contratti finiti (x0) restano in squadra ma non pesano su cap e slot; se non vengono rinnovati o dichiarati RFA scadono all'inizio della free agency",
        "Rookie scale aggiornata dal bot: importo del II e del IV anno dalla tabella, Doncic d'ufficio alla fine del IV anno se spetta",
        "Rinnovo dei rookie a fine II anno con /rinnovo_rookie (o 🔁 nel /menu): scala del III anno o Doncic, x2",
        "RFA: al massimo uno tra i contratti finiti, con /dichiara_rfa (o 🔒 nel /menu). Pesa sul cap ma non sugli slot. Se lo scambiate prima delle aste RFA perde la dichiarazione e ne potete dichiarare un altro",
        "Rinnovi: fino a 2 giocatori all'ultimo anno (+1/4 il primo, +1/2 il secondo, con i minimi da tabella)",
        "In offseason il cap può arrivare a 165M, ma va riportato in regola entro l'inizio della regular season",
    ],
    "offseason-draft": [
        "Le prime scelte vanno firmate obbligatoriamente",
        "I diritti delle seconde si possono tenere per due anni: per firmarle /attiva_diritti (contratto dalla rookie scale)",
        "L'RFA si può ancora dichiarare o cambiare con /dichiara_rfa, fino all'inizio delle aste RFA",
    ],
    "offseason-rfa": [
        "Aste RFA: si aprono da sole per i giocatori dichiarati; chi l'ha dichiarato ha 24h dalla fine dell'asta per pareggiare",
        "Fino alla fine della sua asta un RFA si scambia solo con un altro RFA o verso chi non ne ha dichiarati, e continua a pesare sul cap",
    ],
    "offseason-fa": [
        "Aste di free agency: si chiudono 18 ore dopo l'ultimo rilancio",
        "I contratti finiti (x0) non rinnovati e non RFA sono scaduti: quei giocatori sono free agent",
    ],
    "offseason-ruoli": [
        "Dichiarate il ruolo di tutti i vostri giocatori con /dichiarazione_ruoli (o 🎽 nel /menu), entro {deadline}",
        "Potete scegliere giocatore per giocatore o importare un messaggio con una riga per giocatore (es. «LeBron SF»)",
        "Le scelte diventano ufficiali solo quando premete Conferma; si può confermare anche una parte e completare dopo",
        "In alternativa potete mandare i ruoli a un admin, che li inserirà per voi",
    ],
}


def testo_annuncio_fase(fase: str) -> str:
    from handlers.dpe import FASI_DPE
    righe = [f"📣 <b>Nuova fase: {FASI_LABEL.get(fase, fase)}</b>", ""]
    righe.append("🔄 Trade: <b>" + ("aperte" if fase in settings.FASI_TRADE_APERTE else "chiuse") + "</b>")
    righe.append("💸 Free agency: <b>" + ("aperta" if fase in settings.FASI_FA_APERTA else "chiusa") + "</b>")
    righe.append("🏥 DPE: <b>" + ("richiedibile con /dpe" if fase in FASI_DPE else "non disponibile") + "</b>")
    indicazioni = FASI_INDICAZIONI.get(fase, [])
    if indicazioni:
        deadline = "la deadline"
        if fase == "offseason-ruoli":
            try:
                from handlers.ruoli import get_deadline
                d = get_deadline()
                deadline = d.strftime("il %d/%m alle %H:%M") if d else "la deadline che verrà comunicata"
            except Exception:
                pass
        righe.append("")
        righe += [f"• {r.format(deadline=deadline)}" for r in indicazioni]
    righe += ["", "Comandi disponibili: /menu · Guida: /guida"]
    return "\n".join(righe)


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

    # v3.11: i passaggi che cambiano i contratti (nuova stagione, scadenza degli x0)
    # mostrano prima cosa succederà e chiedono conferma, anche nell'avanzamento normale
    try:
        from handlers.stagione import anteprima_fase
        anteprima = anteprima_fase(fase_vecchia, nuova_fase)
    except Exception as e:
        logger.exception("Anteprima cambio fase")
        anteprima = f"⚠️ Anteprima non disponibile: {html.escape(str(e))}"

    if tipo == "skip" or anteprima:
        if tipo == "skip":
            warning = (
                f"⚠️ <b>Attenzione!</b> Stai saltando direttamente a:\n"
                f"<b>{FASI_LABEL.get(nuova_fase, nuova_fase)}</b>\n\n"
                f"Dalla fase: <b>{FASI_LABEL.get(fase_vecchia, fase_vecchia)}</b>\n\n"
                f"Sei sicuro?"
            )
        else:
            warning = (f"<b>{FASI_LABEL.get(fase_vecchia, fase_vecchia)}</b> → "
                       f"<b>{FASI_LABEL.get(nuova_fase, nuova_fase)}</b>")
        if anteprima:
            warning += "\n\n" + anteprima
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confermo", callback_data=f"fase_conferma:{nuova_fase}"),
            InlineKeyboardButton("❌ No", callback_data="fase_annulla"),
        ]])
        await query.edit_message_text(warning[:4000], parse_mode="HTML", reply_markup=kb)
        return

    # Avanzamento normale senza effetti sui contratti — conferma diretta
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
    g["mercato_aperto"] = nuova_fase in settings.FASI_MERCATO_APERTO

    # Incrementa stagione_corrente quando si entra in offseason-rinnovi dalla stagione prima
    # (v3.11: non tornando indietro da draft/RFA/FA/ruoli, vedi stagione.nuova_stagione)
    from handlers.stagione import nuova_stagione
    nota_stagione = ""
    if nuova_stagione(fase_vecchia, nuova_fase):
        stagione_nuova = int(g.get("stagione_corrente", 2026)) + 1
        g["stagione_corrente"] = str(stagione_nuova)
        nota_stagione = f"\n📅 Stagione aggiornata: <b>{stagione_nuova}</b>"

    json.dump(g, open(globals_path, "w"), indent=2, ensure_ascii=False)

    # v3.11: passaggi automatici sui contratti (nuova stagione → rookie scale; FA → x0
    # scaduti; RFA → pick nuove; regular season → report cap). Dopo aver scritto la fase:
    # se falliscono, la fase resta cambiata e /dev_stagione rifai li ripete.
    from handlers.stagione import dopo_cambio_fase
    from handlers.registro import segna
    await segna(query.get_bot(), query.from_user, "admin", "cambio di fase", oggetto="fase",
                prima=FASI_LABEL.get(fase_vecchia, fase_vecchia), dopo=FASI_LABEL.get(nuova_fase, nuova_fase),
                nota=nota_stagione.strip().replace("<b>", "").replace("</b>", "") or None)
    nota_passaggi = await dopo_cambio_fase(query.get_bot(), fase_vecchia, nuova_fase)

    testo = (
        f"✅ Fase aggiornata:\n"
        f"<b>{FASI_LABEL.get(fase_vecchia, fase_vecchia)}</b> → "
        f"<b>{FASI_LABEL.get(nuova_fase, nuova_fase)}</b>"
        f"{nota_stagione}"
    )
    await query.edit_message_text(testo + nota_passaggi, parse_mode="HTML")

    # Menu comandi di Telegram allineato alla nuova fase
    try:
        from comandi import registra_comandi
        await registra_comandi(query.get_bot())
    except Exception as e:
        logger.warning("Aggiornamento comandi dopo cambio fase: %s", e)

    # Notifica al canale log
    try:
        g2 = json.load(open(globals_path))
        log_ch = g2.get("log_channel_id_main")
        if log_ch:
            await query.get_bot().send_message(
                chat_id=log_ch,
                text=f"⚙️ {testo}",
                parse_mode="HTML",
            )
    except Exception:
        pass

    # Annuncio sul canale principale con le indicazioni della nuova fase
    try:
        main_ch = settings.load_globals().get("main_channel_id")
        if main_ch and nuova_fase != fase_vecchia:
            await query.get_bot().send_message(chat_id=main_ch, text=testo_annuncio_fase(nuova_fase),
                                         parse_mode="HTML")
    except Exception as e:
        logger.warning("Annuncio cambio fase sul canale: %s", e)

    # Inizio regular season: squadre fuori dai minimi dei ruoli
    if nuova_fase == "regular-season-fa" and fase_vecchia != "regular-season-fa":
        try:
            from handlers.ruoli import report_vincoli_inizio_rs
            await report_vincoli_inizio_rs(query.get_bot())
        except Exception as e:
            logger.warning("report_vincoli_inizio_rs: %s", e)

    # Fine fase dichiarazione ruoli: elenco dei giocatori senza ruolo agli admin
    if fase_vecchia == "offseason-ruoli" and nuova_fase != "offseason-ruoli":
        try:
            from handlers.ruoli import report_fine_fase
            await report_fine_fase(query.get_bot())
        except Exception as e:
            logger.warning("report_fine_fase ruoli: %s", e)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/list (admin) — squadre con id e GM, come /list del bot aste."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    righe = ["<b>📋 Squadre</b>\n"] + [
        f"<b>{t['nome']}</b> — <code>{t['id']}</code> — {t.get('gm_nome', '—')}" for t in tm.get_all_teams()]
    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")


async def cmd_set_cap_penalizzato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/set_cap_penalizzato <team_id> <valore> (admin) — penalità sul cap di regular season
    (campo `cap_penalizzato` di teams.json, letto da entrambi i bot). Era nel bot aste, che
    però ha config/ in sola lettura: lì il comando andava in errore."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    args = context.args or []
    if len(args) != 2:
        await update.effective_message.reply_text(
            "Uso: /set_cap_penalizzato <team_id> <valore>\nEs: /set_cap_penalizzato team07 5  (0 per toglierla)")
        return
    team = tm.get_team_by_id(args[0])
    if not team:
        await update.effective_message.reply_text(f"❌ Squadra '{args[0]}' non trovata. Gli id sono in /list.")
        return
    try:
        valore = int(args[1])
        if valore < 0:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("❌ Il valore deve essere un intero ≥ 0.")
        return
    prima = int(team.get("cap_penalizzato") or 0)
    tm.set_campo_team(team["id"], "cap_penalizzato", valore)
    await update.effective_message.reply_text(
        f"✅ Penalità cap di <b>{team['nome']}</b>: {prima}M → <b>{valore}M</b>\n"
        f"Tetto in regular season: {settings.get()['cap_regular'] - valore}M "
        f"(in offseason resta {settings.get()['cap_offseason']}M per tutti).",
        parse_mode="HTML")
    logger.info("set_cap_penalizzato: %s %d → %d da %d", team["id"], prima, valore, update.effective_user.id)
    from handlers.registro import segna
    await segna(context.bot, update.effective_user, "admin", "cap penalizzato", squadre=team["id"],
                oggetto="penalità sul cap", prima=f"{prima}M", dopo=f"{valore}M")
    try:
        from gas_client import sync_teams
        sync_teams([team["id"]])
    except Exception as e:
        logger.warning("sync dopo set_cap_penalizzato: %s", e)


async def cmd_registra_firma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /registra_firma <team_id> <importo> <anni> <nome giocatore>
    Es: /registra_firma team19 1 3 Al Horford
    Solo admin. Registra firma avvenuta fuori dal bot + sync GAS.
    """
    if not is_admin(update.effective_user.id):
        return
    if not context.args or len(context.args) < 4:
        await update.effective_message.reply_text(
            "Uso: /registra_firma <team_id> <importo> <anni> <nome giocatore>\n"
            "Es: /registra_firma team19 1 3 Al Horford"
        )
        return

    team_id = context.args[0]
    try:
        importo = int(context.args[1])
        anni    = int(context.args[2])
    except ValueError:
        await update.effective_message.reply_text("❌ Importo e anni devono essere numeri interi.")
        return

    nome_cerca = " ".join(context.args[3:])
    nome_norm  = nome_cerca.lower()

    team = tm.get_team_by_id(team_id)
    if not team:
        await update.effective_message.reply_text(f"❌ Team <code>{team_id}</code> non trovato.", parse_mode="HTML")
        return
    if anni not in (1, 2, 3) or anni < settings.anni_minimi_contratto(importo):
        await update.effective_message.reply_text(
            f"❌ {importo}M × {anni}: anni non validi (1-3; da {settings.soglia_anni_2()}M almeno 2, "
            f"da {settings.soglia_anni_3()}M obbligatori 3).")
        return

    risultati = db.cerca_giocatori(nome_norm)
    if not risultati:
        await update.effective_message.reply_text(f"❌ Nessun giocatore trovato per '{nome_cerca}'.")
        return

    if len(risultati) == 1:
        g = risultati[0]
        contratto = db.get_contratto_attivo(g["id"])
        if contratto:
            await update.effective_message.reply_text(
                f"❌ <b>{g['nome_common']}</b> ha già un contratto attivo con {contratto['team_id']}.",
                parse_mode="HTML"
            )
            return
        await _esegui_registra_firma(update, context, g, team_id, team, importo, anni)
    else:
        bottoni = [
            [InlineKeyboardButton(g["nome_common"], callback_data=f"rfirma:{g['id']}:{team_id}:{importo}:{anni}")]
            for g in risultati[:5]
        ]
        nomi = "\n".join(f"• {g['nome_common']}" for g in risultati[:5])
        await update.effective_message.reply_text(
            f"Trovati più giocatori:\n{nomi}\n\nSeleziona:",
            reply_markup=InlineKeyboardMarkup(bottoni)
        )


async def cb_registra_firma_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    parts   = query.data.split(":")
    gid     = int(parts[1])
    team_id = parts[2]
    importo = int(parts[3])
    anni    = int(parts[4])
    g    = db.get_giocatore(gid)
    team = tm.get_team_by_id(team_id)
    contratto = db.get_contratto_attivo(gid)
    if contratto:
        await query.edit_message_text(
            f"❌ <b>{g['nome_common']}</b> ha già un contratto attivo con {contratto['team_id']}.",
            parse_mode="HTML"
        )
        return
    await _esegui_registra_firma(query, context, g, team_id, team, importo, anni, is_callback=True)


def _avviso_cap_slot(team: dict, stagione: str) -> str:
    """Avviso (non blocca: la firma è già avvenuta fuori dal bot) se la squadra
    risulta oltre il tetto o con più di 15 giocatori."""
    righe = []
    cap = db.cap_occupato_team(team["id"], stagione)
    tetto = settings.cap_limite_team(team)
    if cap > tetto:
        righe.append(f"⚠️ Cap {cap}M oltre il tetto di {tetto}M.")
    roster = db.get_roster_team(team["id"]) or []
    occupati = db.slot_occupati(roster)
    if occupati > settings.max_roster():
        righe.append(f"⚠️ Roster a {occupati} giocatori, oltre il massimo di {settings.max_roster()}.")
    return ("\n\n" + "\n".join(righe)) if righe else ""


async def _esegui_registra_firma(update_or_query, context, giocatore, team_id, team, importo, anni, is_callback=False):
    stagione = settings.stagione_corrente()
    minimo_ct = db.minimo_cam_thomas(giocatore["id"], team_id)
    if minimo_ct and importo < minimo_ct:
        testo = (f"❌ {giocatore['nome_common']} è decaduto da {team['nome']} con la Cam Thomas exception "
                 f"meno di un anno fa: per rifirmarlo serve almeno il contratto precedente ({minimo_ct}M).")
        if is_callback:
            await update_or_query.edit_message_text(testo)
        else:
            await update_or_query.effective_message.reply_text(testo)
        return
    try:
        # contratto + transazione in un'unica transazione DB (prima: tipo 'firma' non
        # ammesso dal CHECK → contratto creato e transazione fallita)
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) "
                    "VALUES (%s, %s, %s, %s, %s, 'normale') RETURNING id",
                    (giocatore["id"], team_id, importo, anni, stagione))
                contratto_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, contratto_id) "
                    "VALUES ('signed', %s, NULL, %s, %s, %s)",
                    (giocatore["id"], team_id, stagione, contratto_id))
    except Exception as e:
        testo = f"❌ Errore DB: {e}"
        if is_callback:
            await update_or_query.edit_message_text(testo)
        else:
            await update_or_query.effective_message.reply_text(testo)
        return

    try:
        import gas_client
        gas_client.sync_after_firma(team_id)
    except Exception as e:
        logger.warning("GAS sync registra_firma: %s", e)

    try:
        from handlers.ruoli_rs import apri_pendenti
        await apri_pendenti(context.bot, team_id, [giocatore["id"]], "firma")
    except Exception as e:
        logger.warning("Dichiarazione ruolo dopo registra_firma: %s", e)

    admin_user = update_or_query.from_user if is_callback else update_or_query.effective_user
    from handlers.registro import segna
    await segna(context.bot, admin_user, "admin", "firma registrata", squadre=team_id, giocatore_id=giocatore["id"],
                oggetto=giocatore["nome_common"], prima="free agent", dopo=f"{importo}M × {anni}",
                nota="firma avvenuta fuori dal bot")

    testo = (
        f"✅ Firma registrata:\n"
        f"<b>{giocatore['nome_common']}</b> → <b>{team['nome']}</b>\n"
        f"{importo}M × {anni} anni"
        f"{_avviso_cap_slot(team, stagione)}"
    )
    if is_callback:
        await update_or_query.edit_message_text(testo, parse_mode="HTML")
    else:
        await update_or_query.effective_message.reply_text(testo, parse_mode="HTML")


def get_handlers() -> list:
    from handlers.trade_comune import cb_annulla_trade
    from handlers.trade import (
        TRADE_ASSET_MENU, TRADE_ASSET_GIOCATORI, TRADE_ASSET_PICK, TRADE_ASSET_DIRITTI,
        TRADE_ASSEGNA_DEST, TRADE_NOTA, TRADE_RIEPILOGO,
        EDIT_MENU, EDIT_AGGIUNGI_TIPO, EDIT_AGGIUNGI_ITEM,
        cb_asset_menu, cb_toggle_giocatore, cb_toggle_pick, cb_toggle_diritti, cb_assegna_dest,
        cb_nota_ricevi, cb_nota_apri, cb_salva_bozza, cb_trade_del, cb_modifica_da_riepilogo,
        cb_edit_rm, cb_edit_add, cb_edit_done, cb_edit_back, cb_edit_tipo, cb_edit_item,
        cb_send_trade, cmd_annulla_trade,
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
            # Stessi stati e handler del builder GM (trade.py): mancavano diritti,
            # destinazioni (trade a 3-4), nota, bozza, elimina e modifica
            TRADE_ASSET_DIRITTI: [
                CallbackQueryHandler(cb_toggle_diritti, pattern=r"^trade_di:.+$"),
                CallbackQueryHandler(cb_asset_menu,     pattern=r"^trade_am:.+$"),
            ],
            TRADE_ASSEGNA_DEST: [
                CallbackQueryHandler(cb_assegna_dest, pattern=r"^trade_dest:\d+:.+$"),
            ],
            TRADE_NOTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cb_nota_ricevi),
                CommandHandler("salta", cb_nota_ricevi),
            ],
            TRADE_RIEPILOGO: [
                CallbackQueryHandler(cb_send_trade,            pattern=r"^trade_send:.+$"),
                CallbackQueryHandler(cb_nota_apri,             pattern=r"^trade_nota:\d+$"),
                CallbackQueryHandler(cb_salva_bozza,           pattern=r"^trade_salva:\d+$"),
                CallbackQueryHandler(cb_trade_del,             pattern=r"^trade_del:\d+$"),
                CallbackQueryHandler(cb_modifica_da_riepilogo, pattern=r"^edit_back:\d+$"),
            ],
            EDIT_MENU: [
                CallbackQueryHandler(cb_edit_rm,   pattern=r"^edit_rm:\d+:\d+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
                CallbackQueryHandler(cb_edit_done, pattern=r"^edit_done:\d+$"),
                CallbackQueryHandler(cb_edit_back, pattern=r"^edit_back:\d+$"),
            ],
            EDIT_AGGIUNGI_TIPO: [
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gpd]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
            ],
            EDIT_AGGIUNGI_ITEM: [
                CallbackQueryHandler(cb_edit_item, pattern=r"^edit_item:[gpd]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gpd]:\d+:.+$"),
            ],
            ADMIN_IMPORT_TESTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_import_ricevi_testo),
            ],
        },
        fallbacks=[
            CommandHandler("annulla_admin", cmd_annulla_admin),
            CommandHandler("annulla_trade", cmd_annulla_trade),
            CallbackQueryHandler(cb_annulla_trade, pattern=r"^trade_x(:menu)?$"),
        ],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
        allow_reentry=True,          # ← Menu admin / ← Trade funzionano anche a metà di un'operazione
    )

    return [
        conv,
        CommandHandler("list",               cmd_list),
        CommandHandler("set_cap_penalizzato", cmd_set_cap_penalizzato),
        CommandHandler("registra_firma",     cmd_registra_firma),
        CallbackQueryHandler(cb_registra_firma_sel, pattern=r"^rfirma:\d+:.+:\d+:\d+$"),
        CommandHandler("admin_menu", cmd_admin_menu),
        CommandHandler("set_fase",   cmd_set_fase),
        CallbackQueryHandler(cb_ufficializza,        pattern=r"^adm_uff:\d+$"),
        CallbackQueryHandler(cb_adm_taglia_team,     pattern=r"^adm_taglia_team:.+$"),
        CallbackQueryHandler(cb_adm_taglia_conferma, pattern=r"^adm_taglia_ok:\d+:.+$"),
        CallbackQueryHandler(cb_adm_taglia_esegui,   pattern=r"^adm_taglia_si:\d+:.+$"),
        CallbackQueryHandler(cb_adm_dpe_team,        pattern=r"^adm_dpe_team:.+$"),
        CallbackQueryHandler(cb_adm_dpe_giocatore,   pattern=r"^adm_dpe_gi:\d+:.+$"),
        CallbackQueryHandler(cb_adm_dpe_conferma,    pattern=r"^adm_dpe_ok:\d+:.+:\d+:\d+:[01]$"),
        CallbackQueryHandler(cb_fase_set,            pattern=r"^fase_set:.+:.+$"),
        CallbackQueryHandler(cb_fase_conferma,       pattern=r"^fase_conferma:.+$"),
        CallbackQueryHandler(cb_fase_salta_menu,     pattern=r"^fase_salta_menu$"),
        CallbackQueryHandler(cb_fase_indietro,       pattern=r"^fase_indietro$"),
        CallbackQueryHandler(cb_fase_annulla,        pattern=r"^fase_annulla$"),
    ]

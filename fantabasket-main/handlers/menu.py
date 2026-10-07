"""
Menu principale del bot — entry point con InlineKeyboard.
Ogni sezione ha anche un comando testuale parallelo.

Comandi:
  /menu  → menu principale
  /trade → submenu trade (Build/Bozze/Import)
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import teams as tm
import settings
from settings import solo_privato, FASI_TRADE_APERTE

logger = logging.getLogger(__name__)


# ── keyboards ─────────────────────────────────────────────────────────────────

def _fasi_dpe() -> set:
    from handlers.dpe import FASI_DPE
    return set(FASI_DPE)


# Azioni del menu principale, ognuna con le fasi in cui è disponibile.
# Le fasi vengono dalle stesse costanti usate dai comandi, così menu e comandi
# non possono divergere. Per aggiungere un'azione di fase (rinnovi, RFA, cambi
# ruolo...) basta una riga qui + il suo callback.
#   (etichetta, callback_data, funzione che restituisce le fasi)
AZIONI_FASE = [
    ("🎽 Dichiara ruoli", "rl:home",      lambda: {"offseason-ruoli"}),
    ("🔄 Trade",          "menu:trade",   lambda: FASI_TRADE_APERTE),
    ("✂️ Tagli",          "menu:tagli",   lambda: FASI_TRADE_APERTE),
    ("🏀 Rookie",         "menu:rookie",  lambda: FASI_TRADE_APERTE),
    ("🏥 DPE",            "menu:dpe",     _fasi_dpe),
    ("🏁 Decadimento",    "dec_start",    lambda: FASI_TRADE_APERTE),
    # Prossime (da implementare):
    # ("📝 Rinnovi",       "menu:rinnovi",      lambda: {"offseason-rinnovi"}),
    # ("🔒 Dichiara RFA",  "menu:rfa",          lambda: {"offseason-rinnovi"}),
    # ("🔁 Cambio ruolo",  "menu:cambio_ruolo", lambda: {"regular-season-fa", "regular-season-deadline", "playoff"}),
]

AZIONI_SEMPRE = [
    ("📊 Roster", "menu:roster"),
    ("📋 Assets", "menu:assets"),
]


def _kb_menu_principale(fase: str, team_id: str | None = None) -> InlineKeyboardMarkup:
    """Keyboard dinamica — solo le azioni disponibili nella fase corrente (2 per riga)."""
    bottoni = []
    if team_id and fase in settings.FASI_RUOLI_RS:
        try:
            from handlers.ruoli_rs import pendenti_aperti
            n = len(pendenti_aperti(team_id))
            if n:
                bottoni.append(InlineKeyboardButton(f"🎽 Ruoli da dichiarare ({n})", callback_data="rp:list"))
        except Exception as e:
            logger.warning("Conteggio ruoli da dichiarare: %s", e)
    bottoni += [InlineKeyboardButton(label, callback_data=cb)
                for label, cb, fasi in AZIONI_FASE if fase in fasi()]
    righe = [bottoni[i:i + 2] for i in range(0, len(bottoni), 2)]
    righe.append([InlineKeyboardButton(label, callback_data=cb) for label, cb in AZIONI_SEMPRE])
    return InlineKeyboardMarkup(righe)


def _testo_home(fase: str) -> str:
    try:
        from handlers.admin_panel import FASI_LABEL
        etichetta = FASI_LABEL.get(fase, fase)
    except Exception:
        etichetta = fase
    return f"🏠 <b>Menu principale</b>\nFase: {etichetta}\n\nCosa vuoi fare?"


def _kb_menu_trade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔨 Build",   callback_data="menu_trade_build"),
            InlineKeyboardButton("📝 Bozze",   callback_data="menu:trade_bozze"),
            InlineKeyboardButton("📥 Import",  callback_data="menu_trade_import"),
        ],
        [InlineKeyboardButton("← Menu",       callback_data="menu:home")],
    ])


_TESTO_TRADE = "🔄 <b>Trade</b>\nScegli una modalità:"


# ── handlers menu ─────────────────────────────────────────────────────────────

@solo_privato
async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra il menu principale."""
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    fase = settings.fase()
    await update.effective_message.reply_text(
        _testo_home(fase), parse_mode="HTML", reply_markup=_kb_menu_principale(fase, team["id"])
    )


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Gestisci callback senza ":" (es. menu_trade_import)
    azione = query.data.split(":")[1]

    if azione == "home":
        fase = settings.fase()
        t = tm.get_team_by_gm(query.from_user.id)
        await query.edit_message_text(
            _testo_home(fase), parse_mode="HTML",
            reply_markup=_kb_menu_principale(fase, t["id"] if t else None)
        )

    elif azione == "trade":
        await query.edit_message_text(
            _TESTO_TRADE, parse_mode="HTML", reply_markup=_kb_menu_trade()
        )

    elif azione == "trade_bozze":
        # Come /bozze
        from handlers.trade import cmd_mie_trade
        await query.edit_message_text("📝 Carico bozze...", parse_mode="HTML")
        await cmd_mie_trade(update, context)

    elif azione == "tagli":
        # Mostra subito il roster con bottoni taglio
        from handlers.tagli import cmd_taglia
        await query.edit_message_text("✂️ <b>Tagli</b> — seleziona giocatore:", parse_mode="HTML")
        await cmd_taglia(update, context)

    elif azione == "rookie":
        # Mostra subito i diritti 2nd disponibili
        from handlers.rookie import cmd_attiva_diritti
        await query.edit_message_text("🏀 <b>Rookie</b> — seleziona giocatore:", parse_mode="HTML")
        await cmd_attiva_diritti(update, context)

    elif azione == "dpe":
        from handlers.dpe import cmd_dpe
        await query.edit_message_text("🏥 <b>DPE</b> — seleziona giocatore:", parse_mode="HTML")
        await cmd_dpe(update, context)

    elif azione == "roster":
        tutti = tm.get_all_teams()
        bottoni = [
            InlineKeyboardButton(t["nome"], callback_data=f"roster_sq:{t['id']}")
            for t in tutti
        ]
        righe = [bottoni[i:i+2] for i in range(0, len(bottoni), 2)]
        righe.append([InlineKeyboardButton("← Menu", callback_data="menu:home")])
        await query.edit_message_text(
            "📊 <b>Roster</b> — scegli una squadra:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(righe),
        )

    elif azione == "assets":
        tutti = tm.get_all_teams()
        bottoni = [
            InlineKeyboardButton(t["nome"], callback_data=f"assets_sq:{t['id']}")
            for t in tutti
        ]
        righe = [bottoni[i:i+2] for i in range(0, len(bottoni), 2)]
        righe.append([InlineKeyboardButton("← Menu", callback_data="menu:home")])
        await query.edit_message_text(
            "📋 <b>Assets</b> — scegli una squadra:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(righe),
        )


# ── /trade come shortcut al submenu ──────────────────────────────────────────

@solo_privato
async def cmd_trade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra il submenu trade direttamente."""
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    await update.effective_message.reply_text(
        _TESTO_TRADE, parse_mode="HTML", reply_markup=_kb_menu_trade()
    )


# ── registrazione handlers ────────────────────────────────────────────────────

async def cb_roster_squadra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback dai bottoni squadra nel menu Roster."""
    query = update.callback_query
    await query.answer()
    team_id = query.data.split(":")[1]
    team    = tm.get_team_by_id(team_id)
    if not team:
        await query.edit_message_text("❌ Squadra non trovata.")
        return
    await query.edit_message_text(f"⏳ Generazione roster <b>{team['nome']}</b>...", parse_mode="HTML")
    from handlers.roster import _genera_roster_png
    import os
    import settings as _settings_r
    png_path = None
    try:
        png_path = await _genera_roster_png(team, _settings_r.stagione_corrente())
        with open(png_path, "rb") as f:
            await update.effective_message.reply_photo(
                photo=f, caption=f"🏀 {team['nome']}"
            )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore: {e}")
    finally:
        if png_path and os.path.exists(png_path):
            os.unlink(png_path)


async def cb_assets_squadra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback dai bottoni squadra nel menu Assets."""
    query = update.callback_query
    await query.answer()
    team_id = query.data.split(":")[1]
    team    = tm.get_team_by_id(team_id)
    if not team:
        await query.edit_message_text("❌ Squadra non trovata.")
        return
    await query.edit_message_text(f"⏳ Generazione assets <b>{team['nome']}</b>...", parse_mode="HTML")
    from handlers.roster import _genera_assets_png
    import os
    import settings as _settings_r
    png_path = None
    try:
        png_path = await _genera_assets_png(team, _settings_r.stagione_corrente())
        with open(png_path, "rb") as f:
            await update.effective_message.reply_photo(
                photo=f, caption=f"📋 {team['nome']}"
            )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore: {e}")
    finally:
        if png_path and os.path.exists(png_path):
            os.unlink(png_path)


@solo_privato
async def cmd_guida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia la guida GM in privato."""
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "docs", "guida_gm.md")
    try:
        with open(path, "rb") as f:
            await update.effective_message.reply_document(
                document=f,
                filename="guida_gm.md",
                caption="📖 Guida GM — Fantabasket",
            )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore: {e}")


@solo_privato
async def cmd_guida_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia la guida admin in privato — solo admin."""
    import os
    from settings import load_globals
    if update.effective_user.id not in [int(a) for a in load_globals().get("admin_ids", [])]:
        await update.effective_message.reply_text("⛔ Non sei admin.")
        return
    path = os.path.join(os.path.dirname(__file__), "..", "docs", "guida_admin.md")
    try:
        with open(path, "rb") as f:
            await update.effective_message.reply_document(
                document=f,
                filename="guida_admin.md",
                caption="📖 Guida Admin — Fantabasket",
            )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore: {e}")


def get_handlers() -> list:
    return [
        CommandHandler("menu",        cmd_menu),
        CommandHandler("start",       cmd_menu),
        CommandHandler("guida",       cmd_guida),
        CommandHandler("guida_admin", cmd_guida_admin),
        CallbackQueryHandler(cb_menu,            pattern=r"^menu:.+$"),
        CallbackQueryHandler(cb_roster_squadra,  pattern=r"^roster_sq:.+$"),
        CallbackQueryHandler(cb_assets_squadra,  pattern=r"^assets_sq:.+$"),
    ]

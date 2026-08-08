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

def _kb_menu_principale(fase: str) -> InlineKeyboardMarkup:
    """Keyboard dinamica — mostra solo i bottoni disponibili nella fase corrente."""
    trade_aperte = fase in FASI_TRADE_APERTE
    dpe_aperta   = fase in ("regular-season-fa", "regular-season-deadline")

    righe = []

    riga1 = []
    if trade_aperte:
        riga1.append(InlineKeyboardButton("🔄 Trade",  callback_data="menu:trade"))
        riga1.append(InlineKeyboardButton("✂️ Tagli",  callback_data="menu:tagli"))
    if riga1:
        righe.append(riga1)

    riga2 = []
    if trade_aperte:
        riga2.append(InlineKeyboardButton("🏀 Rookie", callback_data="menu:rookie"))
    if dpe_aperta:
        riga2.append(InlineKeyboardButton("🏥 DPE",    callback_data="menu:dpe"))
    if riga2:
        righe.append(riga2)

    righe.append([
        InlineKeyboardButton("📊 Roster",  callback_data="menu:roster"),
        InlineKeyboardButton("📋 Assets",  callback_data="menu:assets"),
    ])

    return InlineKeyboardMarkup(righe)


def _kb_menu_trade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔨 Build",   callback_data="menu:trade_build"),
            InlineKeyboardButton("📝 Bozze",   callback_data="menu:trade_bozze"),
            InlineKeyboardButton("📥 Import",  callback_data="menu:trade_import"),
        ],
        [InlineKeyboardButton("← Menu",       callback_data="menu:home")],
    ])


_TESTO_HOME  = "🏠 <b>Menu principale</b>\nCosa vuoi fare?"
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
        _TESTO_HOME, parse_mode="HTML", reply_markup=_kb_menu_principale(fase)
    )


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    azione = query.data.split(":")[1]

    if azione == "home":
        fase = settings.fase()
        await query.edit_message_text(
            _TESTO_HOME, parse_mode="HTML", reply_markup=_kb_menu_principale(fase)
        )

    elif azione == "trade":
        await query.edit_message_text(
            _TESTO_TRADE, parse_mode="HTML", reply_markup=_kb_menu_trade()
        )

    elif azione == "trade_build":
        # Lancia il builder (come /trade)
        from handlers.trade import cmd_trade
        await query.edit_message_text("🔨 Avvio builder...", parse_mode="HTML")
        await cmd_trade(update, context)

    elif azione == "trade_bozze":
        # Come /bozze
        from handlers.trade import cmd_mie_trade
        await query.edit_message_text("📝 Carico bozze...", parse_mode="HTML")
        await cmd_mie_trade(update, context)

    elif azione == "trade_import":
        await query.edit_message_text(
            "📥 <b>Import trade</b>\n\n"
            "Invia il testo della trade nel formato standard.\n"
            "Usa /annulla_trade per uscire.",
            parse_mode="HTML",
        )
        context.user_data["import_attivo"] = True

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


def get_handlers() -> list:
    return [
        CommandHandler("menu",  cmd_menu),
        CommandHandler("start", cmd_menu),
        CallbackQueryHandler(cb_menu,            pattern=r"^menu:.+$"),
        CallbackQueryHandler(cb_roster_squadra,  pattern=r"^roster_sq:.+$"),
        CallbackQueryHandler(cb_assets_squadra,  pattern=r"^assets_sq:.+$"),
    ]

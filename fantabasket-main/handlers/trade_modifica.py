"""
Trade: /edit_trade, modifica di una bozza (togli, aggiungi giocatori, pick e diritti).
Callback edit_*. Alla fine torna al riepilogo di trade_crea.py.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from settings import solo_privato
import teams as tm
from handlers.trade_comune import (
    EDIT_AGGIUNGI_ITEM, EDIT_AGGIUNGI_TIPO, EDIT_MENU, _ANNULLA_HINT, _bozza_non_modificabile,
    _contratto_str, _kb_edit_menu, _label_bozza, _testo_riepilogo,
)
from handlers.trade_crea import _prossimo_item_da_assegnare, _vai_a_riepilogo


@solo_privato
async def cmd_edit_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /edit_trade <bozza_num> — apre l'editor di una bozza.
    """
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END

    if not context.args:
        await update.effective_message.reply_text(
            "Uso: /edit_trade &lt;numero_bozza&gt;\nEs. /edit_trade 3" + _ANNULLA_HINT,
            parse_mode="HTML",
        )
        return ConversationHandler.END

    try:
        bozza_num = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Numero bozza non valido.")
        return ConversationHandler.END

    bozza = db.get_bozza_by_num(team["id"], bozza_num)
    if not bozza:
        await update.effective_message.reply_text(f"❌ Bozza #{bozza_num} non trovata.")
        return ConversationHandler.END

    context.user_data["edit_trade_id"] = bozza["id"]
    testo = f"✏️ <b>Modifica bozza {_label_bozza(bozza)}</b>\n\n{_testo_riepilogo(bozza['id'])}\n\nPremi ❌ per rimuovere un asset, ➕ per aggiungerne uno." + _ANNULLA_HINT
    await update.effective_message.reply_text(
        testo, parse_mode="HTML", reply_markup=_kb_edit_menu(bozza["id"])
    )
    return EDIT_MENU


async def cb_edit_rm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Rimuove un item dalla bozza."""
    query = update.callback_query
    _, trade_id_s, item_id_s = query.data.split(":")
    trade_id, item_id = int(trade_id_s), int(item_id_s)
    if await _bozza_non_modificabile(query, trade_id):
        return EDIT_MENU
    await query.answer()

    db._q("DELETE FROM trade_items WHERE id = %s AND trade_id = %s", (item_id, trade_id))

    trade = db.get_trade(trade_id)
    testo = f"✏️ <b>Modifica bozza {_label_bozza(trade)}</b>\n\n{_testo_riepilogo(trade_id)}" + _ANNULLA_HINT
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=_kb_edit_menu(trade_id))
    return EDIT_MENU


async def cb_edit_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Scegli tipo di asset da aggiungere."""
    query = update.callback_query
    trade_id = int(query.data.split(":")[1])
    if await _bozza_non_modificabile(query, trade_id):
        return EDIT_MENU
    await query.answer()
    context.user_data["edit_trade_id"] = trade_id

    squadre = db.get_squadre_trade(trade_id)
    kb_rows = []
    for sq in squadre:
        team = tm.get_team_by_id(sq["team_id"])
        nome = team["nome"] if team else sq["team_id"]
        kb_rows.append([
            InlineKeyboardButton(f"🏀 {nome} — Giocatori", callback_data=f"edit_tipo:g:{trade_id}:{sq['team_id']}"),
            InlineKeyboardButton(f"🎯 Pick",               callback_data=f"edit_tipo:p:{trade_id}:{sq['team_id']}"),
            InlineKeyboardButton(f"📋 Diritti",            callback_data=f"edit_tipo:d:{trade_id}:{sq['team_id']}"),
        ])
    kb_rows.append([InlineKeyboardButton("← Indietro", callback_data=f"edit_back:{trade_id}")])

    await query.edit_message_text(
        "Scegli squadra e tipo di asset da aggiungere:" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb_rows),
    )
    return EDIT_AGGIUNGI_TIPO


async def cb_edit_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mostra gli asset disponibili per il tipo scelto."""
    query = update.callback_query
    await query.answer()
    _, tipo, trade_id_s, team_id = query.data.split(":")
    trade_id = int(trade_id_s)

    context.user_data["edit_add_tipo"]    = tipo
    context.user_data["edit_add_team_id"] = team_id
    context.user_data["edit_trade_id"]    = trade_id

    squadre = db.get_squadre_trade(trade_id)
    altri   = [s["team_id"] for s in squadre if s["team_id"] != team_id]
    team_a  = altri[0] if len(altri) == 1 else "?"

    bottoni = []
    if tipo == "g":
        roster = db.get_roster_team(team_id, senza_10day=True)
        items_gi = [i["giocatore_id"] for i in db.get_items_trade(trade_id) if i["team_id_da"] == team_id and i["tipo"] == "giocatore"]
        for r in roster:
            if r["giocatore_id"] in items_gi:
                continue
            label = f"{r['nome_common']} {_contratto_str(r)}"
            bottoni.append([InlineKeyboardButton(label, callback_data=f"edit_item:g:{trade_id}:{team_id}:{team_a}:{r['giocatore_id']}")])
    elif tipo == "p":
        picks = db.get_pick_team(team_id)
        items_pi = [i["pick_id"] for i in db.get_items_trade(trade_id) if i["team_id_da"] == team_id and i["tipo"] == "pick"]
        for p in picks:
            if p["id"] in items_pi:
                continue
            orig = p["proprietario_orig"]
            prot = f" ({p['protezioni']})" if p.get("protezioni") else ""
            t_orig = tm.get_team_by_id(orig)
            rnd = "1st" if p["round"] == 1 else "2nd"
            label = f"{t_orig['nome'] if t_orig else orig} {rnd} {p['anno']}{prot}"
            bottoni.append([InlineKeyboardButton(label, callback_data=f"edit_item:p:{trade_id}:{team_id}:{team_a}:{p['id']}")])
    elif tipo == "d":
        diritti = db.get_diritti_2nd_team(team_id)
        items_di = [i["giocatore_id"] for i in db.get_items_trade(trade_id) if i["team_id_da"] == team_id and i["tipo"] == "diritti"]
        for d in diritti:
            if d["giocatore_id"] in items_di:
                continue
            label = f"{d['nome_common']} (pick {d['pick_numero']} {d['anno_draft']})"
            bottoni.append([InlineKeyboardButton(label, callback_data=f"edit_item:d:{trade_id}:{team_id}:{team_a}:{d['giocatore_id']}")])

    if not bottoni:
        await query.answer("Nessun asset disponibile da aggiungere.", show_alert=True)
        return EDIT_AGGIUNGI_TIPO

    bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"edit_add:{trade_id}")])
    await query.edit_message_text(
        "Seleziona l'asset da aggiungere:" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )
    return EDIT_AGGIUNGI_ITEM


async def cb_edit_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Aggiunge l'asset selezionato alla bozza."""
    query = update.callback_query
    parts    = query.data.split(":")
    tipo     = parts[1]
    trade_id = int(parts[2])
    team_da  = parts[3]
    team_a   = parts[4]
    item_ref = int(parts[5])
    if await _bozza_non_modificabile(query, trade_id):
        return EDIT_MENU
    await query.answer()

    if tipo == "g":
        db.aggiungi_item_trade(trade_id, "giocatore", team_da, team_a, giocatore_id=item_ref)
    elif tipo == "p":
        db.aggiungi_item_trade(trade_id, "pick", team_da, team_a, pick_id=item_ref)
    elif tipo == "d":
        db.aggiungi_item_trade(trade_id, "diritti", team_da, team_a, giocatore_id=item_ref)

    trade = db.get_trade(trade_id)
    testo = f"✏️ <b>Modifica bozza {_label_bozza(trade)}</b>\n\n{_testo_riepilogo(trade_id)}" + _ANNULLA_HINT
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=_kb_edit_menu(trade_id))
    return EDIT_MENU


async def cb_edit_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Chiude l'editor: per le trade a 3+ squadre chiede prima il destinatario
    degli asset aggiunti (team_id_a = '?'), da qualunque punto si sia entrati
    (builder, /edit_trade, /bozze_trade, /my_trades), poi riepilogo validato."""
    query = update.callback_query
    trade_id = int(query.data.split(":")[1])
    if await _bozza_non_modificabile(query, trade_id):
        return ConversationHandler.END
    await query.answer()

    context.user_data.pop("edit_from_riepilogo", None)
    context.user_data.pop("edit_trade_id", None)

    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
    if any(i["team_id_a"] == "?" for i in db.get_items_trade(trade_id)):
        return await _prossimo_item_da_assegnare(query, context, trade_id, squadre)
    return await _vai_a_riepilogo(query, trade_id)


async def cb_edit_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    trade_id = int(query.data.split(":")[1])
    if await _bozza_non_modificabile(query, trade_id):
        return ConversationHandler.END
    await query.answer()
    trade    = db.get_trade(trade_id)
    testo    = f"✏️ <b>Modifica bozza {_label_bozza(trade)}</b>\n\n{_testo_riepilogo(trade_id)}" + _ANNULLA_HINT
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=_kb_edit_menu(trade_id))
    return EDIT_MENU

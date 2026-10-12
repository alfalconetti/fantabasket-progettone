"""
Trade: costruzione di una bozza, da /build_trade (squadre → asset → destinazioni a 3+ squadre →
riepilogo) e da /import_trade (testo). Dal riepilogo: nota, invio, salva bozza, cancella, modifica.
"""
import html

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import settings
from settings import solo_privato, richiede_fase, FASI_TRADE_APERTE
import teams as tm
from validators.trade import valida_trade
from handlers.trade_comune import (
    EDIT_MENU, IMPORT_ATTENDI_TESTO, TRADE_ASSEGNA_DEST, TRADE_ASSET_DIRITTI,
    TRADE_ASSET_GIOCATORI, TRADE_ASSET_MENU, TRADE_ASSET_PICK, TRADE_NOTA, TRADE_N_SQUADRE,
    TRADE_RIEPILOGO, TRADE_SELEZIONA_SQUADRE, _ANNULLA_HINT, _STATI, _bozza_non_modificabile,
    _contratto_str, _kb_asset_menu, _kb_edit_menu, _kb_n_squadre, _kb_riepilogo,
    _kb_riepilogo_non_valida, _kb_squadre, _label_bozza, _puo_gestire_bozza, _testo_riepilogo,
    _trade_label,
)
from handlers.trade_voto import _invia_ad_admin, _proponi_ai_gm


# ── /trade — avvio ────────────────────────────────────────────────────────────

@solo_privato
@richiede_fase(*FASI_TRADE_APERTE, msg="❌ Le trade sono chiuse in questa fase.")
async def cmd_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END

    await update.effective_message.reply_text(
        "🔄 <b>Nuova trade</b>\n\nQuante squadre sono coinvolte?" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=_kb_n_squadre(),
    )
    return TRADE_N_SQUADRE


async def cb_n_squadre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user  = update.effective_user
    team  = tm.get_team_by_gm(user.id)
    n     = int(query.data.split(":")[1])

    trade_id = db.crea_trade_bozza(team["id"], n, settings.stagione_corrente())
    context.user_data["trade_id"] = trade_id
    context.user_data["trade_squadre_rimanenti"] = n

    # La squadra del proponente è la prima automaticamente
    db.aggiungi_squadra_trade(trade_id, team["id"], 1)
    context.user_data["trade_squadre_ordine"] = [team["id"]]

    rimanenti = n - 1
    if rimanenti == 0:
        return await _vai_ad_asset(query, context, trade_id)

    await query.edit_message_text(
        f"Trade a <b>{n} squadre</b>.\n\nLa tua squadra (<b>{team['nome']}</b>) è la prima.\n"
        f"Seleziona le altre {rimanenti} squadre coinvolte:" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=_kb_squadre(escludi=context.user_data["trade_squadre_ordine"]),
    )
    return TRADE_SELEZIONA_SQUADRE


async def cb_seleziona_squadra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tid = query.data.split(":")[1]

    trade_id = context.user_data["trade_id"]
    ordine   = context.user_data["trade_squadre_ordine"]
    if tid in ordine:            # doppio tap sullo stesso bottone
        return TRADE_SELEZIONA_SQUADRE
    ordine.append(tid)
    db.aggiungi_squadra_trade(trade_id, tid, len(ordine))

    n = db.get_trade(trade_id)["n_squadre"]
    if len(ordine) == n:
        return await _vai_ad_asset(query, context, trade_id)

    team = tm.get_team_by_id(tid)
    await query.edit_message_text(
        f"✅ <b>{team['nome']}</b> aggiunta.\n\nSeleziona la prossima squadra:" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=_kb_squadre(escludi=ordine),
    )
    return TRADE_SELEZIONA_SQUADRE


async def _vai_ad_asset(query, context, trade_id: int) -> int:
    """Inizia la raccolta asset dalla prima squadra."""
    ordine = context.user_data["trade_squadre_ordine"]
    context.user_data["trade_squadra_corrente_idx"] = 0
    team_id = ordine[0]
    team    = tm.get_team_by_id(team_id)

    await query.edit_message_text(
        f"Tutte le squadre selezionate.\n\n"
        f"<b>{team['nome']}</b> — cosa cede in questa trade?" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=_kb_asset_menu(trade_id, team_id),
    )
    return TRADE_ASSET_MENU


async def cb_asset_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # NON rispondere subito — ogni ramo gestisce la risposta a modo suo
    _, tipo, trade_id_s, team_id = query.data.split(":")
    trade_id = int(trade_id_s)
    team     = tm.get_team_by_id(team_id)
    nome     = team["nome"] if team else team_id

    if tipo == "ok":
        await query.answer()
        return await cb_squadra_confermata(query, context, trade_id, team_id)

    if tipo == "g":
        roster = db.get_roster_team(team_id)
        if not roster:
            await query.answer("Nessun giocatore nel roster.", show_alert=True)
            return TRADE_ASSET_MENU
        items_gi = [
            i["giocatore_id"] for i in db.get_items_trade(trade_id)
            if i["team_id_da"] == team_id and i["tipo"] == "giocatore"
        ]
        bottoni = []
        for r in roster:
            gid   = r["giocatore_id"]
            check = "✅ " if gid in items_gi else ""
            label = f"{check}{r['nome_common']} {_contratto_str(r)}"
            bottoni.append([InlineKeyboardButton(label, callback_data=f"trade_gi:{trade_id}:{team_id}:{gid}")])
        bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"trade_am:back:{trade_id}:{team_id}")])
        await query.answer()
        await query.edit_message_text(
            f"<b>{nome}</b> — seleziona giocatori da cedere.\n"
            f"Premi di nuovo per deselezionare." + _ANNULLA_HINT,
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(bottoni),
        )
        return TRADE_ASSET_GIOCATORI

    if tipo == "p":
        picks = db.get_pick_team(team_id)
        if not picks:
            await query.answer("Nessuna pick disponibile.", show_alert=True)
            return TRADE_ASSET_MENU
        items_pi = [
            i["pick_id"] for i in db.get_items_trade(trade_id)
            if i["team_id_da"] == team_id and i["tipo"] == "pick"
        ]
        bottoni = []
        for p in picks:
            check     = "✅ " if p["id"] in items_pi else ""
            team_orig = tm.get_team_by_id(p["proprietario_orig"])
            nome_orig = team_orig["nome"] if team_orig else p["proprietario_orig"]
            rnd       = "1st" if p["round"] == 1 else "2nd"
            prot      = f" ({p['protezioni']})" if p.get("protezioni") else ""
            label     = f"{check}{nome_orig} {rnd} {p['anno']}{prot}"
            bottoni.append([InlineKeyboardButton(label, callback_data=f"trade_pi:{trade_id}:{team_id}:{p['id']}")])
        bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"trade_am:back:{trade_id}:{team_id}")])
        await query.answer()
        await query.edit_message_text(
            f"<b>{nome}</b> — seleziona pick da cedere." + _ANNULLA_HINT,
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(bottoni),
        )
        return TRADE_ASSET_PICK

    if tipo == "d":
        diritti = db.get_diritti_2nd_team(team_id)
        if not diritti:
            await query.answer("Nessun diritto 2nd disponibile.", show_alert=True)
            return TRADE_ASSET_MENU
        items_di = [
            i["giocatore_id"] for i in db.get_items_trade(trade_id)
            if i["team_id_da"] == team_id and i["tipo"] == "diritti"
        ]
        bottoni = []
        for d in diritti:
            check = "✅ " if d["giocatore_id"] in items_di else ""
            label = f"{check}{d['nome_common']} (pick {d['pick_numero']} {d['anno_draft']})"
            bottoni.append([InlineKeyboardButton(label, callback_data=f"trade_di:{trade_id}:{team_id}:{d['id']}")])
        bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"trade_am:back:{trade_id}:{team_id}")])
        await query.answer()
        await query.edit_message_text(
            f"<b>{nome}</b> — seleziona diritti da cedere." + _ANNULLA_HINT,
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(bottoni),
        )
        return TRADE_ASSET_DIRITTI

    # back → torna al menu asset
    await query.answer()
    await query.edit_message_text(
        f"<b>{nome}</b> — cosa cede in questa trade?" + _ANNULLA_HINT,
        parse_mode="HTML", reply_markup=_kb_asset_menu(trade_id, team_id),
    )
    return TRADE_ASSET_MENU


async def cb_toggle_giocatore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query   # answer() una volta sola, più sotto ("Aggiunto"/"Rimosso")
    _, trade_id_s, team_id, gid_s = query.data.split(":")
    trade_id, gid = int(trade_id_s), int(gid_s)

    items = db.get_items_trade(trade_id)
    esistente = next(
        (i for i in items if i["tipo"] == "giocatore" and i["giocatore_id"] == gid
         and i["team_id_da"] == team_id), None
    )

    if esistente:
        db.rimuovi_item_trade(esistente["id"])
        await query.answer("Rimosso.")
    else:
        # Determina dove va: alla squadra successiva (placeholder, verrà confermato nel riepilogo)
        # Per ora inseriamo team_id_a = "?" e lo risolviamo nel riepilogo
        db.aggiungi_item_trade(trade_id, "giocatore", team_id, "?", giocatore_id=gid)
        await query.answer("Aggiunto.")

    # Ricarica la lista
    return await _ricarica_lista_giocatori(query, trade_id, team_id)


async def _ricarica_lista_giocatori(query, trade_id: int, team_id: str) -> int:
    roster   = db.get_roster_team(team_id)
    items_gi = [
        i["giocatore_id"] for i in db.get_items_trade(trade_id)
        if i["team_id_da"] == team_id and i["tipo"] == "giocatore"
    ]
    bottoni = []
    for r in roster:
        gid   = r["giocatore_id"]
        check = "✅ " if gid in items_gi else ""
        label = f"{check}{r['nome_common']} {_contratto_str(r)}"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"trade_gi:{trade_id}:{team_id}:{gid}")])
    bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"trade_am:back:{trade_id}:{team_id}")])
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(bottoni))
    return TRADE_ASSET_GIOCATORI


async def cb_toggle_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query   # answer() una volta sola, più sotto ("Aggiunto"/"Rimosso")
    _, trade_id_s, team_id, pid_s = query.data.split(":")
    trade_id, pid = int(trade_id_s), int(pid_s)

    items = db.get_items_trade(trade_id)
    esistente = next((i for i in items if i["tipo"] == "pick" and i["pick_id"] == pid), None)

    if esistente:
        db.rimuovi_item_trade(esistente["id"])
        await query.answer("Rimossa.")
    else:
        db.aggiungi_item_trade(trade_id, "pick", team_id, "?", pick_id=pid)
        await query.answer("Aggiunta.")

    # Ricarica lista pick
    picks    = db.get_pick_team(team_id)
    items_pi = [
        i["pick_id"] for i in db.get_items_trade(trade_id)
        if i["team_id_da"] == team_id and i["tipo"] == "pick"
    ]
    bottoni = []
    for p in picks:
        check = "✅ " if p["id"] in items_pi else ""
        team_orig = tm.get_team_by_id(p["proprietario_orig"])
        nome_orig = team_orig["nome"] if team_orig else p["proprietario_orig"]
        rnd   = "1st" if p["round"] == 1 else "2nd"
        prot  = f" ({p['protezioni']})" if p.get("protezioni") else ""
        label = f"{check}{nome_orig} {rnd} {p['anno']}{prot}"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"trade_pi:{trade_id}:{team_id}:{p['id']}")])
    bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"trade_am:back:{trade_id}:{team_id}")])
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(bottoni))
    return TRADE_ASSET_PICK


async def cb_toggle_diritti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query   # answer() una volta sola, più sotto ("Aggiunto"/"Rimosso")
    _, trade_id_s, team_id, rookie_id_s = query.data.split(":")
    trade_id, rookie_id = int(trade_id_s), int(rookie_id_s)

    rookie = db.get_rookie(rookie_id)
    if not rookie:
        await query.answer("Diritti non trovati.", show_alert=True)
        return TRADE_ASSET_DIRITTI

    items = db.get_items_trade(trade_id)
    esistente = next(
        (i for i in items if i["tipo"] == "diritti"
         and i["giocatore_id"] == rookie["giocatore_id"]
         and i["team_id_da"] == team_id), None
    )

    if esistente:
        db.rimuovi_item_trade(esistente["id"])
        await query.answer("Rimosso.")
    else:
        db.aggiungi_item_trade(trade_id, "diritti", team_id, "?",
                               giocatore_id=rookie["giocatore_id"])
        await query.answer("Aggiunto.")

    # Ricarica lista
    diritti  = db.get_diritti_2nd_team(team_id)
    items_di = [
        i["giocatore_id"] for i in db.get_items_trade(trade_id)
        if i["team_id_da"] == team_id and i["tipo"] == "diritti"
    ]
    bottoni = []
    for d in diritti:
        check = "✅ " if d["giocatore_id"] in items_di else ""
        label = f"{check}{d['nome_common']} (pick {d['pick_numero']} {d['anno_draft']})"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"trade_di:{trade_id}:{team_id}:{d['id']}")])
    bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"trade_am:back:{trade_id}:{team_id}")])
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(bottoni))
    return TRADE_ASSET_DIRITTI   # era TRADE_ASSET_PICK: dal secondo diritto in poi il tap non faceva niente


async def cb_squadra_confermata(query, context, trade_id: int, team_id: str) -> int:
    """Una squadra ha confermato i suoi asset. Passa alla successiva o al flusso destinatari."""
    db.conferma_squadra_trade(trade_id, team_id)
    ordine = context.user_data["trade_squadre_ordine"]
    idx    = context.user_data["trade_squadra_corrente_idx"] + 1
    context.user_data["trade_squadra_corrente_idx"] = idx

    if idx < len(ordine):
        next_team_id = ordine[idx]
        next_team    = tm.get_team_by_id(next_team_id)
        await query.edit_message_text(
            f"✅ Asset di <b>{tm.get_team_by_id(team_id)['nome']}</b> confermati.\n\n"
            f"<b>{next_team['nome']}</b> — cosa cede?" + _ANNULLA_HINT,
            parse_mode="HTML",
            reply_markup=_kb_asset_menu(trade_id, next_team_id),
        )
        return TRADE_ASSET_MENU

    # Tutte le squadre confermate
    trade   = db.get_trade(trade_id)
    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]

    if len(squadre) == 2:
        # Trade a 2 squadre: assegnazione automatica
        items = db.get_items_trade(trade_id)
        for item in items:
            if item["team_id_a"] == "?":
                altro = [t for t in squadre if t != item["team_id_da"]]
                if altro:
                    db.assegna_destinatario_item(item["id"], altro[0])
        return await _vai_a_riepilogo(query, trade_id)

    # Trade a 3+ squadre: chiedi destinatari
    return await _prossimo_item_da_assegnare(query, context, trade_id, squadre)


async def _prossimo_item_da_assegnare(query, context, trade_id: int, squadre: list) -> int:
    """Mostra il prossimo item senza destinatario confermato."""
    items_pending = [
        i for i in db.get_items_trade(trade_id) if i["team_id_a"] == "?"
    ]
    if not items_pending:
        return await _vai_a_riepilogo(query, trade_id)

    item = items_pending[0]
    context.user_data["trade_item_da_assegnare"] = item["id"]

    # Label dell'asset
    if item["tipo"] == "giocatore":
        asset_label = item.get("nome_common") or f"Giocatore #{item['giocatore_id']}"
    elif item["tipo"] == "pick":
        team_orig = tm.get_team_by_id(item.get("pick_orig", ""))
        orig_nome = team_orig["nome"] if team_orig else item.get("pick_orig", "?")
        rnd = "1st" if item.get("pick_round") == 1 else "2nd"
        asset_label = f"{orig_nome} {rnd} {item.get('pick_anno','?')}"
    else:
        asset_label = f"Diritti {item.get('nome_common','?')}"

    team_da = tm.get_team_by_id(item["team_id_da"])
    nome_da = team_da["nome"] if team_da else item["team_id_da"]

    altri = [t for t in squadre if t != item["team_id_da"]]
    bottoni = [
        [InlineKeyboardButton(
            tm.get_team_by_id(t)["nome"] if tm.get_team_by_id(t) else t,
            callback_data=f"trade_dest:{item['id']}:{t}"
        )]
        for t in altri
    ]

    rimasti = len(items_pending)
    await query.edit_message_text(
        f"📦 <b>Assegna destinatario</b> ({rimasti} rimasti)\n\n"
        f"<b>{nome_da}</b> cede: <i>{asset_label}</i>\n\n"
        f"Chi lo riceve?" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )
    return TRADE_ASSEGNA_DEST


async def cb_assegna_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """L'utente ha scelto il destinatario di un item."""
    query = update.callback_query
    _, item_id_s, team_id_a = query.data.split(":")
    item_id  = int(item_id_s)
    item     = db.get_item_trade(item_id)
    if not item:
        await query.answer("Asset non più nella bozza.", show_alert=True)
        return TRADE_ASSEGNA_DEST
    trade_id = item["trade_id"]
    if await _bozza_non_modificabile(query, trade_id):
        return ConversationHandler.END
    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
    if team_id_a not in squadre or team_id_a == item["team_id_da"]:
        await query.answer("Destinatario non valido.", show_alert=True)
        return TRADE_ASSEGNA_DEST
    await query.answer()

    db.assegna_destinatario_item(item_id, team_id_a)

    return await _prossimo_item_da_assegnare(query, context, trade_id, squadre)


async def _vai_a_riepilogo(query, trade_id: int) -> int:
    """Valida e mostra il riepilogo finale."""
    ok, errori = valida_trade(trade_id)
    db.aggiorna_stato_trade(
        trade_id, "bozza",
        validazione_ok=ok,
        validazione_note="\n".join(errori) if errori else None,
    )
    testo = _testo_riepilogo(trade_id)
    if ok:
        testo += "\n\n✅ <b>Validazione OK</b>"
    else:
        testo += "\n\n⚠️ <b>Problemi rilevati:</b>\n" + "\n".join(errori)
    await query.edit_message_text(
        testo, parse_mode="HTML", reply_markup=_kb_riepilogo(trade_id) if ok else _kb_riepilogo_non_valida(trade_id)
    )
    return TRADE_RIEPILOGO


# ── dal riepilogo: cancella, modifica ───────────────────────────────────────────

async def cb_trade_del(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Elimina la bozza. Solo bozze: un vecchio bottone "Elimina" non deve poter
    cancellare una trade già inviata ai GM o agli admin."""
    query    = update.callback_query
    trade_id = int(query.data.split(":")[1])
    trade    = db.get_trade(trade_id)
    if not trade:
        await query.answer("Bozza già eliminata.", show_alert=True)
        return ConversationHandler.END
    label    = _label_bozza(trade)
    if trade["stato"] != "bozza":
        await query.answer(f"Non è più una bozza ({_STATI.get(trade['stato'], trade['stato'])}): "
                           "non si può eliminare.", show_alert=True)
        return ConversationHandler.END
    if not _puo_gestire_bozza(query.from_user.id, trade):
        await query.answer("⛔ Non è una tua bozza.", show_alert=True)
        return ConversationHandler.END
    db.elimina_trade(trade_id)
    await query.answer()
    await query.edit_message_text(f"🗑️ Bozza {label} eliminata.")
    return ConversationHandler.END


async def cb_modifica_da_riepilogo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Apre l'editor inline da TRADE_RIEPILOGO."""
    query    = update.callback_query
    trade_id = int(query.data.split(":")[1])
    if await _bozza_non_modificabile(query, trade_id):
        return ConversationHandler.END
    await query.answer()
    trade    = db.get_trade(trade_id)
    context.user_data["edit_from_riepilogo"] = True
    await query.edit_message_text(
        f"✏️ <b>Modifica bozza {_label_bozza(trade)}</b>\n\n"
        f"{_testo_riepilogo(trade_id)}\n\n"
        f"Premi ❌ per rimuovere, ➕ per aggiungere." + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=_kb_edit_menu(trade_id),
    )
    return EDIT_MENU


# ── riepilogo callbacks ───────────────────────────────────────────────────────

async def cb_send_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    _, destinatario, trade_id_s = query.data.split(":")
    trade_id = int(trade_id_s)
    trade    = db.get_trade(trade_id)

    if not trade:
        await query.answer("❌ Trade non trovata.", show_alert=True)
        return ConversationHandler.END
    if trade["stato"] != "bozza":
        await query.answer()
        await query.edit_message_text(f"⚠️ La trade non è più una bozza (stato: {_STATI.get(trade['stato'], trade['stato'])}).")
        return ConversationHandler.END
    if not _puo_gestire_bozza(update.effective_user.id, trade):
        await query.answer("⛔ Non è una tua bozza.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    # Sempre rivalidata al momento dell'invio: roster, cap e pick possono essere
    # cambiati dopo il riepilogo, e l'editor non aggiorna validazione_ok
    ok, errori = valida_trade(trade_id)
    db.aggiorna_stato_trade(trade_id, "bozza", validazione_ok=ok,
                            validazione_note="\n".join(errori) if errori else None)
    if not ok:
        testo = _testo_riepilogo(trade_id)
        testo += "\n\n⚠️ <b>Problemi rilevati:</b>\n" + "\n".join(errori)
        await query.edit_message_text(testo, parse_mode="HTML",
                                      reply_markup=_kb_riepilogo_non_valida(trade_id))
        return TRADE_RIEPILOGO

    if destinatario == "admin":
        await _invia_ad_admin(query, context, trade_id)
    else:
        await _proponi_ai_gm(query, context, trade_id)
    return ConversationHandler.END


async def cb_nota_apri(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Apre il flusso per aggiungere/modificare la nota alla trade."""
    query = update.callback_query
    await query.answer()
    _, trade_id_s = query.data.split(":")
    trade_id = int(trade_id_s)
    trade = db.get_trade(trade_id)
    nota_attuale = trade.get("nota_gm", "") if trade else ""
    context.user_data["nota_trade_id"] = trade_id

    testo = ("📝 <b>Nota alla trade</b>\n\n"
            "Scrivi il messaggio da allegare (max 300 caratteri).\n")
    if nota_attuale:
        testo += f"\nNota attuale: <i>{html.escape(nota_attuale)}</i>\n"
    testo += "\n<i>Invia /salta per rimuovere la nota.</i>"

    await query.edit_message_text(testo, parse_mode="HTML")
    return TRADE_NOTA


async def cb_nota_ricevi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Riceve il testo della nota e torna al riepilogo."""
    trade_id = context.user_data.pop("nota_trade_id", None)
    if not trade_id:
        return ConversationHandler.END

    if update.message.text.startswith("/salta"):
        nota = None
    else:
        nota = update.message.text[:300]

    db._q("UPDATE trade SET nota_gm = %s WHERE id = %s", (nota, trade_id))

    trade = db.get_trade(trade_id)
    ha_nota = bool(nota)
    testo = _testo_riepilogo(trade_id)
    ok = trade.get("validazione_ok")
    if ok:
        testo += "\n\n✅ <b>Validazione OK</b>"
        if nota:
            testo += f"\n📝 Nota: <i>{html.escape(nota)}</i>"
    else:
        note_val = trade.get("validazione_note") or ""
        testo += "\n\n⚠️ <b>Problemi rilevati:</b>\n" + note_val

    await update.message.reply_text(
        testo,
        parse_mode="HTML",
        reply_markup=_kb_riepilogo(trade_id, ha_nota=ha_nota),
    )
    return TRADE_RIEPILOGO


async def cb_salva_bozza(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Salva la bozza e termina la conversazione senza inviare."""
    query = update.callback_query
    await query.answer()
    _, trade_id_s = query.data.split(":")
    trade_id = int(trade_id_s)
    trade = db.get_trade(trade_id)
    label = _trade_label(trade) if trade else f"#{trade_id}"
    await query.edit_message_text(
        f"💾 Bozza <b>{label}</b> salvata. Puoi riprenderla con /bozze_trade.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ── /import_trade: trade scritta a testo ────────────────────────────────────────

@solo_privato
@richiede_fase(*FASI_TRADE_APERTE, msg="❌ Le trade sono chiuse in questa fase.")
async def cmd_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Avvia il flusso import: aspetta il testo della trade."""
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "📥 <b>Import trade</b>\n\n"
        "Invia il testo della trade nel formato standard.\n\n"
        "<i>Per annullare: /annulla_trade</i>",
        parse_mode="HTML",
    )
    return IMPORT_ATTENDI_TESTO


async def import_ricevi_testo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Riceve il testo della trade, parsea e crea bozza solo se senza errori."""
    from handlers.trade_parser import parsa_trade, crea_trade_da_parse, formatta_trade
    from validators.trade import valida_trade

    testo   = update.effective_message.text
    user    = update.effective_user
    team    = tm.get_team_by_gm(user.id)
    stagione = settings.stagione_corrente()
    tutti_team = tm.get_all_teams()

    squadre, errori_parse = parsa_trade(testo, stagione, tutti_team)

    # Se ci sono errori di parsing: non salvare, mostrare errori e riprovare
    if errori_parse or not squadre:
        righe = ["❌ <b>Errori nel parsing — bozza non salvata:</b>\n"]
        for e in errori_parse or ["Nessuna squadra riconosciuta."]:
            righe.append(f"  • {e}")
        righe.append("\nCorreggi il testo e reinvia, oppure /annulla_trade per uscire.")
        await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")
        return IMPORT_ATTENDI_TESTO

    # GM non può importare trade che non lo coinvolgono (gli admin sì)
    team_ids_trade = [sq.team_id for sq in squadre]
    is_admin       = user.id in [int(a) for a in settings.load_globals().get("admin_ids", [])]
    if not is_admin and team and team["id"] not in team_ids_trade:
        await update.effective_message.reply_text(
            "❌ Non puoi importare una trade che non ti coinvolge.\n"
            "Contatta un admin per proporre questa trade."
        )
        return IMPORT_ATTENDI_TESTO

    proposta_da = team["id"] if team else "admin"

    # Parsing pulito — crea bozza
    trade_id = crea_trade_da_parse(squadre, stagione, proposta_da)

    # Validazione trade (cap, roster, Stepien)
    ok, errori_val = valida_trade(trade_id)

    trade_obj = db.get_trade(trade_id)
    risposta = [f"📋 <b>Bozza {_label_bozza(trade_obj)} creata</b>\n"]
    risposta.append(formatta_trade(squadre))

    if ok:
        risposta.append("\n✅ <b>Validazione OK</b>")
    else:
        risposta.append("\n⚠️ <b>Problemi di validazione:</b>")
        for e in errori_val:
            risposta.append(f"  {e}")

    await update.effective_message.reply_text(
        "\n".join(risposta),
        parse_mode="HTML",
        reply_markup=_kb_riepilogo(trade_id) if ok else _kb_riepilogo_non_valida(trade_id),
    )
    return TRADE_RIEPILOGO

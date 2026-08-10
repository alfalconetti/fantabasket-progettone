"""
Trade builder — flusso completo:
  /trade → quante squadre → seleziona squadre → asset per squadra → riepilogo → proposta/admin
  /mie_trade → bozze e trade in votazione
  Callback: accetta/rifiuta trade proposta
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler,
)

import database as db
import settings
from settings import solo_privato, richiede_fase, FASI_TRADE_APERTE
import teams as tm
from utils import ROME, format_dt
from validators.trade import valida_trade

logger = logging.getLogger(__name__)

# ── stati ConversationHandler ─────────────────────────────────────────────────
(
    TRADE_N_SQUADRE,
    TRADE_SELEZIONA_SQUADRE,
    TRADE_ASSET_MENU,
    TRADE_ASSET_GIOCATORI,
    TRADE_ASSET_PICK,
    TRADE_ASSET_DIRITTI,
    TRADE_ASSEGNA_DEST,      # solo per trade a 3+ squadre
    TRADE_RIEPILOGO,
    EDIT_MENU,
    EDIT_AGGIUNGI_TIPO,
    EDIT_AGGIUNGI_ITEM,
) = range(11)

IMPORT_ATTENDI_TESTO = 20

_ANNULLA_HINT = "\n<i>Per annullare: /annulla_trade</i>"


# ── helpers UI ─────────────────────────────────────────────────────────────────

def _kb_n_squadre() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("2 squadre", callback_data="trade_n:2"),
        InlineKeyboardButton("3 squadre", callback_data="trade_n:3"),
        InlineKeyboardButton("4 squadre", callback_data="trade_n:4"),
    ]])


def _kb_squadre(escludi: list[str]) -> InlineKeyboardMarkup:
    tutti = tm.get_all_teams()
    bottoni = [
        InlineKeyboardButton(t["nome"], callback_data=f"trade_sq:{t['id']}")
        for t in tutti if t["id"] not in escludi
    ]
    righe = [bottoni[i:i+2] for i in range(0, len(bottoni), 2)]
    return InlineKeyboardMarkup(righe)


def _kb_asset_menu(trade_id: int, team_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏀 Giocatori", callback_data=f"trade_am:g:{trade_id}:{team_id}"),
            InlineKeyboardButton("🎯 Pick",      callback_data=f"trade_am:p:{trade_id}:{team_id}"),
            InlineKeyboardButton("📋 Diritti",   callback_data=f"trade_am:d:{trade_id}:{team_id}"),
        ],
        [InlineKeyboardButton("✅ Conferma squadra", callback_data=f"trade_am:ok:{trade_id}:{team_id}")],
    ])


def _testo_riepilogo(trade_id: int) -> str:
    trade  = db.get_trade(trade_id)
    items  = db.get_items_trade(trade_id)
    squadre = db.get_squadre_trade(trade_id)

    num = trade["bozza_num"] if trade and trade.get("bozza_num") else trade_id
    righe = [f"📋 <b>Bozza trade #{num}</b>\n"]

    for sq in squadre:
        tid = sq["team_id"]
        team = tm.get_team_by_id(tid)
        nome = team["nome"] if team else tid

        invia = [i for i in items if i["team_id_da"] == tid]
        riceve = [i for i in items if i["team_id_a"] == tid]

        righe.append(f"<b>{nome}</b>")
        if invia:
            righe.append("  <i>Cede:</i>")
            for i in invia:
                righe.append(f"    • {_label_item(i)}")
        if riceve:
            righe.append("  <i>Riceve:</i>")
            for i in riceve:
                righe.append(f"    • {_label_item(i)}")
        if not invia and not riceve:
            righe.append("  <i>Nessun asset</i>")

    return "\n".join(righe)


def _label_item(item: dict) -> str:
    if item["tipo"] == "giocatore":
        return item.get("nome_common") or f"Giocatore #{item['giocatore_id']}"
    if item["tipo"] == "pick":
        orig_id = item.get("pick_orig", "?")
        team_orig = tm.get_team_by_id(orig_id) if orig_id != "?" else None
        nome_orig = team_orig["nome"] if team_orig else orig_id
        anno = item.get("pick_anno", "?")
        rnd  = "1st" if item.get("pick_round") == 1 else "2nd" if item.get("pick_round") == 2 else "?"
        prot = f" ({item.get('protezioni')})" if item.get("protezioni") else ""
        return f"{nome_orig} {rnd} {anno}{prot}"
    if item["tipo"] == "diritti":
        return f"Diritti {item.get('nome_common','?')}"
    return "?"


def _kb_riepilogo(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Proponi ai GM",   callback_data=f"trade_send:gm:{trade_id}")],
        [InlineKeyboardButton("📨 Manda ad admin",  callback_data=f"trade_send:admin:{trade_id}")],
        [InlineKeyboardButton("✏️ Modifica",        callback_data=f"edit_back:{trade_id}")],
        [InlineKeyboardButton("🗑️ Elimina bozza",   callback_data=f"trade_del:{trade_id}")],
    ])


def _kb_riepilogo_non_valida(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Modifica",      callback_data=f"edit_back:{trade_id}")],
        [InlineKeyboardButton("🗑️ Elimina bozza", callback_data=f"trade_del:{trade_id}")],
    ])


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
            label = f"{check}{r['nome_common']} ({r['importo']}M)"
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
    query = update.callback_query
    await query.answer()
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
        label = f"{check}{r['nome_common']} ({r['importo']}M)"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"trade_gi:{trade_id}:{team_id}:{gid}")])
    bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"trade_am:back:{trade_id}:{team_id}")])
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(bottoni))
    return TRADE_ASSET_GIOCATORI


async def cb_toggle_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
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
        label = f"{check}{nome_orig} {rnd} {p['anno']}"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"trade_pi:{trade_id}:{team_id}:{p['id']}")])
    bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"trade_am:back:{trade_id}:{team_id}")])
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(bottoni))
    return TRADE_ASSET_PICK


async def cb_toggle_diritti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, trade_id_s, team_id, rookie_id_s = query.data.split(":")
    trade_id, rookie_id = int(trade_id_s), int(rookie_id_s)

    rookie = db.get_rookie(rookie_id)
    if not rookie:
        return TRADE_ASSET_PICK

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
    return TRADE_ASSET_PICK


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
    await query.answer()
    _, item_id_s, team_id_a = query.data.split(":")
    item_id  = int(item_id_s)
    trade_id = db.get_item_trade(item_id)["trade_id"]

    db.assegna_destinatario_item(item_id, team_id_a)

    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
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


async def cb_trade_del(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Elimina la bozza."""
    query    = update.callback_query
    trade_id = int(query.data.split(":")[1])
    trade    = db.get_trade(trade_id)
    num      = trade["bozza_num"] if trade else trade_id
    db.elimina_trade(trade_id)
    await query.answer()
    await query.edit_message_text(f"🗑️ Bozza #{num} eliminata.")
    return ConversationHandler.END


async def cb_modifica_da_riepilogo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Apre l'editor inline da TRADE_RIEPILOGO."""
    query    = update.callback_query
    trade_id = int(query.data.split(":")[1])
    trade    = db.get_trade(trade_id)
    context.user_data["edit_from_riepilogo"] = True
    await query.answer()
    await query.edit_message_text(
        f"✏️ <b>Modifica Bozza #{trade['bozza_num']}</b>\n\n"
        f"{_testo_riepilogo(trade_id)}\n\n"
        f"Premi ❌ per rimuovere, ➕ per aggiungere." + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=_kb_edit_menu(trade_id),
    )
    return EDIT_MENU


def _formatta_annuncio_canale(trade_id: int) -> str:
    """
    Formato annuncio canale:
    - 2 squadre: solo sezioni "cede"
    - 3+ squadre: sezioni "cede" + sezioni "riceve"
    """
    stagione_int = int(settings.stagione_corrente())
    squadre  = db.get_squadre_trade(trade_id)
    items    = db.get_items_trade(trade_id)
    righe    = ["<b>TRADE</b>"]

    def _label_item_canale(item: dict) -> str:
        if item["tipo"] == "giocatore":
            tipo_c = item.get("giocatore_tipo_contratto", "normale")
            if tipo_c == "rookie":
                scala = int(item.get("giocatore_anni_scala") or 0)
                anni  = 2 if scala in (0, 2) else 1
            else:
                anni_orig = item.get("giocatore_anni", 1) or 1
                s_firma   = int(item.get("giocatore_stagione_firma") or stagione_int)
                anni      = max(1, anni_orig - (stagione_int - s_firma))
            importo = item.get("giocatore_importo", 0) or 0
            return f"{item['nome_common']} {importo}x{anni}"
        elif item["tipo"] == "pick":
            rnd  = "1st" if item.get("pick_round") == 1 else "2nd"
            anno = item.get("pick_anno", "?")
            orig = tm.get_team_by_id(item.get("pick_orig", ""))
            by   = orig["nome"] if orig else item.get("pick_orig", "?")
            return f"{rnd} round pick {anno} by {by}"
        elif item["tipo"] == "diritti":
            return f"Diritti di {item['nome_common']}"
        return "?"

    # Sezioni "cede"
    for sq in squadre:
        team     = tm.get_team_by_id(sq["team_id"])
        nome     = team["nome"] if team else sq["team_id"]
        items_sq = [i for i in items if i["team_id_da"] == sq["team_id"]]
        if not items_sq:
            continue
        righe.append("")
        righe.append(f"<b>{nome} cede:</b>")
        for item in items_sq:
            righe.append(_label_item_canale(item))

    # Sezioni "riceve" solo per 3+ squadre
    if len(squadre) > 2:
        righe.append("")
        for sq in squadre:
            team     = tm.get_team_by_id(sq["team_id"])
            nome     = team["nome"] if team else sq["team_id"]
            items_sq = [i for i in items if i["team_id_a"] == sq["team_id"]]
            if not items_sq:
                continue
            righe.append("")
            righe.append(f"<b>{nome} riceve:</b>")
            for item in items_sq:
                righe.append(_label_item_canale(item))

    return "\n".join(righe)


# ── riepilogo callbacks ───────────────────────────────────────────────────────

async def cb_send_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, destinatario, trade_id_s = query.data.split(":")
    trade_id = int(trade_id_s)
    trade    = db.get_trade(trade_id)

    if not trade or trade["validazione_ok"] is False:
        await query.answer("⚠️ Risolvi i problemi di validazione prima.", show_alert=True)
        return TRADE_RIEPILOGO

    if destinatario == "admin":
        await _invia_ad_admin(query, context, trade_id)
    else:
        await _proponi_ai_gm(query, context, trade_id)

    return ConversationHandler.END


async def _invia_ad_admin(query, context, trade_id: int):
    admin_gid = settings.admin_group_id()
    testo = _testo_riepilogo(trade_id)
    trade = db.get_trade(trade_id)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approva", callback_data=f"trade_admin:ok:{trade_id}"),
        InlineKeyboardButton("❌ Rifiuta", callback_data=f"trade_admin:no:{trade_id}"),
    ]])

    if admin_gid:
        bozza_label = f"Bozza #{trade['bozza_num']}" if trade.get('bozza_num') else f"Trade #{trade_id}"
        await context.bot.send_message(
            chat_id=admin_gid,
            text=f"📨 <b>{bozza_label} proposta da {trade['proposta_da']}</b>\n\n{testo}",
            parse_mode="HTML",
            reply_markup=kb,
        )

    db.aggiorna_stato_trade(trade_id, "in_approvazione")
    await query.edit_message_text(
        f"✅ Trade inviata agli admin per approvazione.",
        parse_mode="HTML",
    )


async def _proponi_ai_gm(query, context, trade_id: int):
    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
    trade   = db.get_trade(trade_id)
    testo   = _testo_riepilogo(trade_id)

    # Tutti i GM tranne il proponente devono votare
    da_votare = [tid for tid in squadre if tid != trade["proposta_da"]]
    db.inizializza_voti(trade_id, da_votare)
    db.aggiorna_stato_trade(trade_id, "proposta")

    for team_id in da_votare:
        team = tm.get_team_by_id(team_id)
        if not team:
            continue
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Accetto", callback_data=f"trade_voto:si:{trade_id}:{team_id}"),
            InlineKeyboardButton("❌ Rifiuto", callback_data=f"trade_voto:no:{trade_id}:{team_id}"),
        ]])
        bozza_label = f"Bozza #{trade['bozza_num']}" if trade.get('bozza_num') else f"Trade #{trade_id}"
        for gm_id in team.get("gm_ids", []):
            try:
                await context.bot.send_message(
                    chat_id=gm_id,
                    text=f"📨 <b>Proposta di trade ({bozza_label})</b>\n\n{testo}\n\n"
                         f"<i>Accetti questa trade?</i>",
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            except Exception as e:
                logger.warning("Impossibile notificare GM %d: %s", gm_id, e)

    await query.edit_message_text(
        f"✅ Trade <b>{trade['trade_ref']}</b> proposta alle altre squadre.\nAttendo le risposte.",
        parse_mode="HTML",
    )


async def cb_voto_gm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback quando un GM accetta o rifiuta una trade proposta."""
    query = update.callback_query
    await query.answer()
    _, esito, trade_id_s, team_id = query.data.split(":")
    trade_id = int(trade_id_s)
    trade    = db.get_trade(trade_id)

    if not trade or trade["stato"] != "proposta":
        await query.edit_message_text("⚠️ Questa trade non è più in votazione.")
        return

    voto = "accettato" if esito == "si" else "rifiutato"
    db.registra_voto(trade_id, team_id, voto)
    team = tm.get_team_by_id(team_id)

    if voto == "rifiutato":
        db.aggiorna_stato_trade(trade_id, "rifiutata_gm",
                                note=f"Rifiutata da {team['nome'] if team else team_id}")
        # Notifica il proponente
        await _notifica_proponente(context, trade_id,
                                   f"❌ <b>{team['nome']}</b> ha rifiutato la trade <b>{trade['trade_ref']}</b>.")
        await query.edit_message_text(f"❌ Hai rifiutato la trade {trade['trade_ref']}.")
        return

    await query.edit_message_text(f"✅ Hai accettato la trade {trade['trade_ref']}. Attendo gli altri.")

    if db.tutti_hanno_votato(trade_id):
        db.aggiorna_stato_trade(trade_id, "in_approvazione")
        await _invia_ad_admin_dopo_voti(context, trade_id)


async def _invia_ad_admin_dopo_voti(context, trade_id: int):
    admin_gid = settings.admin_group_id()
    if not admin_gid:
        return
    trade = db.get_trade(trade_id)
    testo = _testo_riepilogo(trade_id)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approva", callback_data=f"trade_admin:ok:{trade_id}"),
        InlineKeyboardButton("❌ Rifiuta", callback_data=f"trade_admin:no:{trade_id}"),
    ]])
    await context.bot.send_message(
        chat_id=admin_gid,
        text=f"✅ <b>Tutti i GM hanno accettato — {trade['trade_ref']}</b>\n\n{testo}",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def cb_admin_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approva o rifiuta la trade."""
    query = update.callback_query
    await query.answer()
    _, esito, trade_id_s = query.data.split(":")
    trade_id = int(trade_id_s)

    if esito == "no":
        db.aggiorna_stato_trade(trade_id, "rifiutata_admin")
        await query.edit_message_text("❌ Trade rifiutata dagli admin.")
        await _notifica_proponente(context, trade_id, "❌ Gli admin hanno rifiutato la trade.")
        return

    admin_user = update.effective_user
    admin_nome = admin_user.first_name or admin_user.username or str(admin_user.id)

    # Genera trade_ref (MAX progressivo per evitare collisioni)
    trade    = db.get_trade(trade_id)
    stagione = trade["stagione"]
    n_trade  = db.get_trade_count_approvate(stagione)
    trade_ref = f"TRADE-{stagione}-{n_trade + 1:03d}"

    # Aggiorna subito il messaggio nel gruppo admin (prima di operazioni che potrebbero fallire)
    from datetime import datetime
    ora = format_dt(datetime.now(ROME))
    await query.edit_message_text(
        f"✅ <b>{trade_ref}</b> approvata da {admin_nome} alle {ora}.",
        parse_mode="HTML",
    )

    # Esegui la trade e registra
    await _esegui_trade(context, trade_id)
    db.approva_trade(trade_id, trade_ref, admin_nome)

    # Annuncio sul canale principale
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        testo_annuncio = (
            f"{_formatta_annuncio_canale(trade_id)}\n\n"
            f"<i>Approvata da {admin_nome} alle {ora}\n"
            f"ID: <code>{trade_ref}</code></i>"
        )
        try:
            await context.bot.send_message(
                chat_id=main_channel,
                text=testo_annuncio,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Annuncio trade canale fallito: %s", e)

    await query.edit_message_text(
        f"✅ Trade <b>{trade_ref}</b> approvata ed eseguita.\n"
        f"<i>Annuncio inviato al canale principale.</i>",
        parse_mode="HTML",
    )


async def _esegui_trade(context, trade_id: int):
    """Esegue materialmente la trade: aggiorna contratti e inserisce transazioni."""
    trade   = db.get_trade(trade_id)
    items   = db.get_items_trade(trade_id)
    stagione = trade["stagione"]

    for item in items:
        if item["tipo"] == "giocatore":
            gid = item["giocatore_id"]
            contratto = db.get_contratto_attivo(gid)
            # Aggiorna team_id nel contratto
            from database import _q
            _q("UPDATE contratti SET team_id = %s WHERE id = %s",
               (item["team_id_a"], contratto["id"]))
            # Registra transazione
            db.registra_transazione(
                "traded", gid, item["team_id_da"], item["team_id_a"],
                stagione, contratto_id=contratto["id"], trade_id=trade_id,
                note=trade["trade_ref"]
            )
        elif item["tipo"] == "pick":
            from database import _q
            _q("UPDATE pick SET proprietario_att = %s WHERE id = %s",
               (item["team_id_a"], item["pick_id"]))

    db.aggiorna_stato_trade(trade_id, "approvata")
    logger.info("Trade %s eseguita.", trade["trade_ref"])

    # Sync GAS Sheets
    try:
        import gas_client
        gas_client.sync_after_trade(trade_id)
    except Exception as e:
        logger.warning("GAS sync trade fallito: %s", e)

    # Notifica tutti i GM coinvolti
    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
    for team_id in squadre:
        team = tm.get_team_by_id(team_id)
        if not team:
            continue
        for gm_id in team.get("gm_ids", []):
            try:
                await context.bot.send_message(
                    chat_id=gm_id,
                    text=f"✅ <b>Trade {trade['trade_ref']} eseguita!</b>\n"
                         f"Ricordati di comunicare i ruoli entro 48h.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Notifica GM %d fallita: %s", gm_id, e)


async def _rollback_trade(trade_id: int):
    """
    Inverte una trade già eseguita:
    - giocatori: riporta team_id al mittente originale
    - pick: riporta proprietario_att al mittente originale
    - transazioni: inserisce movimento inverso
    """
    from database import _q
    trade    = db.get_trade(trade_id)
    items    = db.get_items_trade(trade_id)
    stagione = trade["stagione"]

    for item in items:
        if item["tipo"] == "giocatore":
            gid       = item["giocatore_id"]
            contratto = db.get_contratto_attivo(gid)
            if contratto:
                _q("UPDATE contratti SET team_id = %s WHERE id = %s",
                   (item["team_id_da"], contratto["id"]))
                db.registra_transazione(
                    "traded", gid, item["team_id_a"], item["team_id_da"],
                    stagione, contratto_id=contratto["id"], trade_id=trade_id,
                    note=f"ANNULLAMENTO {trade['trade_ref']}"
                )
        elif item["tipo"] == "pick":
            _q("UPDATE pick SET proprietario_att = %s WHERE id = %s",
               (item["team_id_da"], item["pick_id"]))
        elif item["tipo"] == "diritti":
            _q("UPDATE rookie SET team_id = %s WHERE id = %s",
               (item["team_id_da"], item["giocatore_id"]))

    db.aggiorna_stato_trade(trade_id, "annullata")
    logger.info("Trade %s annullata e rollback eseguito.", trade["trade_ref"])


async def _valida_rollback(trade_id: int) -> list[str]:
    """
    Verifica che il rollback sia possibile: tutti gli asset ricevuti
    devono essere ancora nei team che li avevano ricevuti.
    Restituisce lista di errori (vuota = rollback possibile).
    """
    items  = db.get_items_trade(trade_id)
    errori = []

    for item in items:
        if item["tipo"] == "giocatore":
            gid       = item["giocatore_id"]
            contratto = db.get_contratto_attivo(gid)
            nome      = item.get("nome_common", f"#{gid}")
            if not contratto:
                errori.append(f"{nome} non ha più un contratto attivo")
            elif contratto["team_id"] != item["team_id_a"]:
                team_att = tm.get_team_by_id(contratto["team_id"])
                nome_att = team_att["nome"] if team_att else contratto["team_id"]
                team_att_orig = tm.get_team_by_id(item["team_id_a"])
                nome_orig = team_att_orig["nome"] if team_att_orig else item["team_id_a"]
                errori.append(
                    f"{nome}: dovrebbe essere a {nome_orig} ma è a {nome_att}"
                )

        elif item["tipo"] == "pick":
            pick = db.get_pick(item["pick_id"])
            if not pick:
                errori.append(f"Pick #{item['pick_id']} non trovata nel DB")
            elif pick["proprietario_att"] != item["team_id_a"]:
                team_att = tm.get_team_by_id(pick["proprietario_att"])
                nome_att = team_att["nome"] if team_att else pick["proprietario_att"]
                team_att_orig = tm.get_team_by_id(item["team_id_a"])
                nome_orig = team_att_orig["nome"] if team_att_orig else item["team_id_a"]
                rnd  = "1st" if pick["round"] == 1 else "2nd"
                errori.append(
                    f"Pick {rnd} {pick['anno']}: dovrebbe essere a {nome_orig} ma è a {nome_att}"
                )

        elif item["tipo"] == "diritti":
            rookie = db.get_rookie_by_giocatore(item["giocatore_id"])
            nome   = item.get("nome_common", f"#{item['giocatore_id']}")
            if not rookie:
                errori.append(f"Diritti di {nome} non trovati nel DB")
            elif rookie["team_id"] != item["team_id_a"]:
                team_att = tm.get_team_by_id(rookie["team_id"])
                nome_att = team_att["nome"] if team_att else rookie["team_id"]
                team_att_orig = tm.get_team_by_id(item["team_id_a"])
                nome_orig = team_att_orig["nome"] if team_att_orig else item["team_id_a"]
                errori.append(
                    f"Diritti di {nome}: dovrebbe essere a {nome_orig} ma è a {nome_att}"
                )

    return errori

@solo_privato
async def cmd_annulla_trade_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /annulla_trade_admin <trade_ref>
    Es: /annulla_trade_admin TRADE-2026-003
    Riservato agli admin. Annulla una trade già eseguita e notifica il canale.
    """
    from settings import load_globals
    user = update.effective_user
    if user.id not in [int(a) for a in load_globals().get("admin_ids", [])]:
        await update.effective_message.reply_text("⛔ Non sei admin.")
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Uso: /annulla_trade_admin <trade_ref>\n"
            "Es: /annulla_trade_admin TRADE-2026-003"
        )
        return

    trade_ref = context.args[0].upper()
    trade     = db.get_trade_by_ref(trade_ref)

    if not trade:
        await update.effective_message.reply_text(f"❌ Trade '{trade_ref}' non trovata.")
        return

    if trade["stato"] != "approvata":
        await update.effective_message.reply_text(
            f"❌ La trade {trade_ref} è in stato '{trade['stato']}' — solo le trade approvate possono essere annullate."
        )
        return

    await update.effective_message.reply_text(f"⏳ Verifica compatibilità {trade_ref}...")

    errori = await _valida_rollback(trade["id"])
    if errori:
        testo = (
            f"❌ <b>Impossibile annullare {trade_ref}</b>\n\n"
            f"Alcuni asset sono stati spostati nel frattempo:\n"
        )
        for e in errori:
            testo += f"  • {e}\n"
        await update.effective_message.reply_text(testo, parse_mode="HTML")
        return

    await update.effective_message.reply_text("✅ Compatibilità OK, eseguo il rollback...")
    await _rollback_trade(trade["id"])

    # Sync GAS Sheets
    try:
        import gas_client
        gas_client.sync_after_trade(trade["id"])
    except Exception as e:
        logger.warning("GAS sync rollback trade fallito: %s", e)

    admin_nome = user.first_name or str(user.id)
    from datetime import datetime
    ora = format_dt(datetime.now(ROME))

    # Annuncio canale
    main_channel = load_globals().get("main_channel_id")
    if main_channel:
        try:
            await context.bot.send_message(
                chat_id=main_channel,
                text=(
                    f"⚠️ <b>Trade annullata</b>\n\n"
                    f"La trade <code>{trade_ref}</code> è stata annullata.\n"
                    f"Tutti i giocatori e le pick sono stati ripristinati.\n\n"
                    f"<i>Annullata da {admin_nome} alle {ora}</i>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Annuncio annullamento canale fallito: %s", e)

    await update.effective_message.reply_text(
        f"✅ <b>{trade_ref}</b> annullata. Roster e pick ripristinati.",
        parse_mode="HTML",
    )
    trade = db.get_trade(trade_id)
    team  = tm.get_team_by_id(trade["proposta_da"])
    if not team:
        return
    for gm_id in team.get("gm_ids", []):
        try:
            await context.bot.send_message(chat_id=gm_id, text=testo, parse_mode="HTML")
        except Exception:
            pass


# ── /mie_trade ─────────────────────────────────────────────────────────────────

@solo_privato
async def cmd_mie_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return

    bozze   = db.get_bozze_team(team["id"])
    pending = db.get_trade_in_votazione(team["id"])

    if not bozze and not pending:
        await update.effective_message.reply_text("Nessuna trade attiva.")
        return

    bottoni = []

    if bozze:
        for t in bozze:
            trade_id = t["id"]
            squadre  = db.get_trade_squadre(trade_id)
            gm_nomi  = [
                (tm.get_team_by_id(sq["team_id"]) or {}).get("gm_nome", sq["team_id"])
                for sq in squadre
            ]
            gm_str = " ↔ ".join(gm_nomi) if gm_nomi else f"{t['n_squadre']} squadre"
            bottoni.append([InlineKeyboardButton(
                f"📝 #{t['bozza_num']} — {gm_str}",
                callback_data=f"bozza_apri:{trade_id}"
            )])

    if pending:
        for t in pending:
            trade_id = t["id"]
            squadre  = db.get_trade_squadre(trade_id)
            gm_nomi  = [
                (tm.get_team_by_id(sq["team_id"]) or {}).get("gm_nome", sq["team_id"])
                for sq in squadre
            ]
            gm_str = " ↔ ".join(gm_nomi) if gm_nomi else "?"
            bottoni.append([InlineKeyboardButton(
                f"⏳ {t['trade_ref']} — {gm_str}",
                callback_data=f"bozza_apri:{trade_id}"
            )])

    await update.effective_message.reply_text(
        "📝 <b>Le tue trade</b> — seleziona per vedere il riepilogo:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )


async def cb_bozza_apri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra il riepilogo di una bozza/trade con bottoni azione."""
    query    = update.callback_query
    await query.answer()
    trade_id = int(query.data.split(":")[1])
    trade    = db.get_trade(trade_id)
    if not trade:
        await query.edit_message_text("❌ Trade non trovata.")
        return
    testo = _testo_riepilogo(trade_id)
    # Usa la keyboard appropriata in base allo stato
    if trade.get("stato") == "bozza":
        valida, errori = valida_trade(trade_id)
        if not valida:
            testo += "\n\n⚠️ " + "\n".join(errori)
        kb = _kb_riepilogo(trade_id) if valida else _kb_riepilogo_non_valida(trade_id)
    else:
        kb = None
    await query.edit_message_text(
        testo, parse_mode="HTML",
        reply_markup=kb,
    )


# ── /annulla_trade ─────────────────────────────────────────────────────────────

@solo_privato
async def cmd_annulla_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    trade_id = context.user_data.pop("trade_id", None)
    if trade_id:
        db.aggiorna_stato_trade(trade_id, "annullata")
    context.user_data.pop("trade_squadre_ordine", None)
    context.user_data.pop("trade_squadre_corrente_idx", None)
    await update.effective_message.reply_text("Trade annullata.")
    return ConversationHandler.END


# ── registrazione handlers ─────────────────────────────────────────────────────

# ── Edit bozza ────────────────────────────────────────────────────────────────

def _kb_edit_menu(trade_id: int) -> InlineKeyboardMarkup:
    """Keyboard per l'edit: lista asset con ❌ + bottoni aggiungi."""
    items   = db.get_items_trade(trade_id)
    trade   = db.get_trade(trade_id)
    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
    bottoni = []

    for item in items:
        label = f"❌ {_label_item(item)} ({tm.get_team_by_id(item['team_id_da'])['nome'] if tm.get_team_by_id(item['team_id_da']) else item['team_id_da']} → {item['team_id_a']})"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"edit_rm:{trade_id}:{item['id']}")])

    bottoni.append([InlineKeyboardButton("➕ Aggiungi asset", callback_data=f"edit_add:{trade_id}")])
    bottoni.append([InlineKeyboardButton("✅ Fatto",          callback_data=f"edit_done:{trade_id}")])
    return InlineKeyboardMarkup(bottoni)


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
            "Uso: /edit_trade <numero_bozza>\nEs. /edit_trade 3" + _ANNULLA_HINT,
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
    testo = f"✏️ <b>Modifica Bozza #{bozza_num}</b>\n\n{_testo_riepilogo(bozza['id'])}\n\nPremi ❌ per rimuovere un asset, ➕ per aggiungerne uno." + _ANNULLA_HINT
    await update.effective_message.reply_text(
        testo, parse_mode="HTML", reply_markup=_kb_edit_menu(bozza["id"])
    )
    return EDIT_MENU


async def cb_edit_rm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Rimuove un item dalla bozza."""
    query = update.callback_query
    await query.answer()
    _, trade_id_s, item_id_s = query.data.split(":")
    trade_id, item_id = int(trade_id_s), int(item_id_s)

    db.rimuovi_item_trade(item_id)

    trade = db.get_trade(trade_id)
    testo = f"✏️ <b>Modifica Bozza #{trade['bozza_num']}</b>\n\n{_testo_riepilogo(trade_id)}" + _ANNULLA_HINT
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=_kb_edit_menu(trade_id))
    return EDIT_MENU


async def cb_edit_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Scegli tipo di asset da aggiungere."""
    query = update.callback_query
    await query.answer()
    trade_id = int(query.data.split(":")[1])
    context.user_data["edit_trade_id"] = trade_id

    squadre = db.get_squadre_trade(trade_id)
    kb_rows = []
    for sq in squadre:
        team = tm.get_team_by_id(sq["team_id"])
        nome = team["nome"] if team else sq["team_id"]
        kb_rows.append([
            InlineKeyboardButton(f"🏀 {nome} — Giocatori", callback_data=f"edit_tipo:g:{trade_id}:{sq['team_id']}"),
            InlineKeyboardButton(f"🎯 Pick",               callback_data=f"edit_tipo:p:{trade_id}:{sq['team_id']}"),
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
        roster = db.get_roster_team(team_id)
        items_gi = [i["giocatore_id"] for i in db.get_items_trade(trade_id) if i["team_id_da"] == team_id and i["tipo"] == "giocatore"]
        for r in roster:
            if r["giocatore_id"] in items_gi:
                continue
            label = f"{r['nome_common']} ({r['importo']}M)"
            bottoni.append([InlineKeyboardButton(label, callback_data=f"edit_item:g:{trade_id}:{team_id}:{team_a}:{r['giocatore_id']}")])
    elif tipo == "p":
        picks = db.get_pick_team(team_id)
        items_pi = [i["pick_id"] for i in db.get_items_trade(trade_id) if i["team_id_da"] == team_id and i["tipo"] == "pick"]
        for p in picks:
            if p["id"] in items_pi:
                continue
            orig = p["proprietario_orig"]
            prot = f" ({p['protezioni']})" if p.get("protezioni") else ""
            label = f"{orig} {p['anno']} R{p['round']}{prot}"
            bottoni.append([InlineKeyboardButton(label, callback_data=f"edit_item:p:{trade_id}:{team_id}:{team_a}:{p['id']}")])

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
    await query.answer()
    parts    = query.data.split(":")
    tipo     = parts[1]
    trade_id = int(parts[2])
    team_da  = parts[3]
    team_a   = parts[4]
    item_ref = int(parts[5])

    if tipo == "g":
        db.aggiungi_item_trade(trade_id, "giocatore", team_da, team_a, giocatore_id=item_ref)
    elif tipo == "p":
        db.aggiungi_item_trade(trade_id, "pick", team_da, team_a, pick_id=item_ref)

    trade = db.get_trade(trade_id)
    testo = f"✏️ <b>Modifica Bozza #{trade['bozza_num']}</b>\n\n{_testo_riepilogo(trade_id)}" + _ANNULLA_HINT
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=_kb_edit_menu(trade_id))
    return EDIT_MENU


async def cb_edit_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Chiude l'editor, mostra riepilogo o lancia assegnazione destinatari per 3+ squadre."""
    query = update.callback_query
    await query.answer()
    trade_id = int(query.data.split(":")[1])

    from_riepilogo = context.user_data.pop("edit_from_riepilogo", False)
    context.user_data.pop("edit_trade_id", None)

    # Per trade 3+ squadre: se ci sono item senza destinatario, riassegna
    if from_riepilogo:
        squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
        items_pending = [i for i in db.get_items_trade(trade_id) if i["team_id_a"] == "?"]
        if len(squadre) > 2 and items_pending:
            return await _prossimo_item_da_assegnare(query, context, trade_id, squadre)

    from validators.trade import valida_trade
    ok, errori_val = valida_trade(trade_id)
    testo = _testo_riepilogo(trade_id)
    if ok:
        testo += "\n\n✅ <b>Validazione OK</b>"
    else:
        testo += "\n\n⚠️ <b>Problemi:</b>\n" + "\n".join(errori_val)

    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=_kb_riepilogo(trade_id) if ok else _kb_riepilogo_non_valida(trade_id))
    return TRADE_RIEPILOGO if from_riepilogo else ConversationHandler.END


async def cb_edit_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    trade_id = int(query.data.split(":")[1])
    trade    = db.get_trade(trade_id)
    testo    = f"✏️ <b>Modifica Bozza #{trade['bozza_num']}</b>\n\n{_testo_riepilogo(trade_id)}" + _ANNULLA_HINT
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=_kb_edit_menu(trade_id))
    return EDIT_MENU


# ── Import trade da testo — ConversationHandler ───────────────────────────────

IMPORT_ATTENDI_TESTO = 10


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

    risposta = [f"📋 <b>Trade #{trade_id} — bozza creata</b>\n"]
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
    return ConversationHandler.END


def get_handlers() -> list:
    from telegram.ext import MessageHandler, filters

    conv_build = ConversationHandler(
        entry_points=[
            CommandHandler("build_trade", cmd_trade),
            CallbackQueryHandler(cmd_trade, pattern=r"^menu_trade_build$"),
        ],
        states={
            TRADE_N_SQUADRE: [
                CallbackQueryHandler(cb_n_squadre, pattern=r"^trade_n:\d$"),
            ],
            TRADE_SELEZIONA_SQUADRE: [
                CallbackQueryHandler(cb_seleziona_squadra, pattern=r"^trade_sq:.+$"),
            ],
            TRADE_ASSET_MENU: [
                CallbackQueryHandler(cb_asset_menu, pattern=r"^trade_am:[gpod].*$|^trade_am:ok:.*$|^trade_am:back:.*$"),
            ],
            TRADE_ASSET_GIOCATORI: [
                CallbackQueryHandler(cb_toggle_giocatore, pattern=r"^trade_gi:.+$"),
                CallbackQueryHandler(cb_asset_menu,       pattern=r"^trade_am:.+$"),
            ],
            TRADE_ASSET_PICK: [
                CallbackQueryHandler(cb_toggle_pick,  pattern=r"^trade_pi:.+$"),
                CallbackQueryHandler(cb_asset_menu,   pattern=r"^trade_am:.+$"),
            ],
            TRADE_ASSET_DIRITTI: [
                CallbackQueryHandler(cb_toggle_diritti, pattern=r"^trade_di:.+$"),
                CallbackQueryHandler(cb_asset_menu,     pattern=r"^trade_am:.+$"),
            ],
            TRADE_ASSEGNA_DEST: [
                CallbackQueryHandler(cb_assegna_dest, pattern=r"^trade_dest:\d+:.+$"),
            ],
            TRADE_RIEPILOGO: [
                CallbackQueryHandler(cb_send_trade,           pattern=r"^trade_send:.+$"),
                CallbackQueryHandler(cb_trade_del,            pattern=r"^trade_del:\d+$"),
                CallbackQueryHandler(cb_modifica_da_riepilogo,pattern=r"^edit_back:\d+$"),
            ],
            EDIT_MENU: [
                CallbackQueryHandler(cb_edit_rm,   pattern=r"^edit_rm:\d+:\d+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
                CallbackQueryHandler(cb_edit_done, pattern=r"^edit_done:\d+$"),
                CallbackQueryHandler(cb_edit_back, pattern=r"^edit_back:\d+$"),
            ],
            EDIT_AGGIUNGI_TIPO: [
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gp]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
            ],
            EDIT_AGGIUNGI_ITEM: [
                CallbackQueryHandler(cb_edit_item, pattern=r"^edit_item:[gp]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gp]:\d+:.+$"),
            ],
        },
        fallbacks=[CommandHandler("annulla_trade", cmd_annulla_trade)],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )

    conv_import = ConversationHandler(
        entry_points=[
            CommandHandler("import_trade", cmd_import),
            CallbackQueryHandler(cmd_import, pattern=r"^menu_trade_import$"),
        ],
        states={
            IMPORT_ATTENDI_TESTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, import_ricevi_testo),
            ],
        },
        fallbacks=[CommandHandler("annulla_trade", cmd_annulla_trade)],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )

    conv_edit = ConversationHandler(
        entry_points=[
            CommandHandler("edit_trade", cmd_edit_trade),
            CallbackQueryHandler(cb_edit_back, pattern=r"^edit_back:\d+$"),
        ],
        states={
            EDIT_MENU: [
                CallbackQueryHandler(cb_edit_rm,   pattern=r"^edit_rm:\d+:\d+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
                CallbackQueryHandler(cb_edit_done, pattern=r"^edit_done:\d+$"),
            ],
            EDIT_AGGIUNGI_TIPO: [
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gp]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_add,  pattern=r"^edit_add:\d+$"),
            ],
            EDIT_AGGIUNGI_ITEM: [
                CallbackQueryHandler(cb_edit_item, pattern=r"^edit_item:[gp]:\d+:.+$"),
                CallbackQueryHandler(cb_edit_tipo, pattern=r"^edit_tipo:[gp]:\d+:.+$"),
            ],
        },
        fallbacks=[
            CommandHandler("annulla_trade", cmd_annulla_trade),
            CallbackQueryHandler(cb_edit_back, pattern=r"^edit_back:\d+$"),
        ],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )

    return [
        conv_build,
        conv_import,
        conv_edit,
        CommandHandler("mie_trade",          cmd_mie_trade),
        CommandHandler("bozze_trade",         cmd_mie_trade),
        CallbackQueryHandler(cb_bozza_apri,   pattern=r"^bozza_apri:\d+$"),
        CommandHandler("annulla_trade_admin", cmd_annulla_trade_admin),
        CallbackQueryHandler(cb_voto_gm,     pattern=r"^trade_voto:.+$"),
        CallbackQueryHandler(cb_admin_trade, pattern=r"^trade_admin:.+$"),
        CallbackQueryHandler(cb_edit_back,   pattern=r"^edit_back:\d+$"),
        CallbackQueryHandler(cb_trade_del,   pattern=r"^trade_del:\d+$"),  # fallback fuori conv
    ]

"""
Trade: stati, testi e tastiere del riepilogo, permessi sulla bozza, annuncio sul canale,
notifiche alle squadre. Usato da tutti i moduli trade_*.py (indice in handlers/trade.py).
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import settings
import teams as tm

logger = logging.getLogger(__name__)


_STATI = {
    "bozza":           "📝 bozza",
    "proposta":        "🗳 in voto tra i GM",
    "in_approvazione": "⏳ in attesa degli admin",
    "approvata":       "✅ approvata",
    "rifiutata_gm":    "❌ rifiutata da un GM",
    "rifiutata_admin": "🚫 rifiutata dagli admin",
    "annullata":       "🗑 annullata",
}

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
TRADE_NOTA       = 11
TRADE_RIFIUTO_NOTA = 12

IMPORT_ATTENDI_TESTO = 10   # conversazione di /import_trade (fino alla v3.12 scritto due volte, 20 e poi 10: valeva 10)

_ANNULLA_HINT = "\n<i>Per annullare: /annulla_trade</i>"


# ── helpers UI ─────────────────────────────────────────────────────────────────

ANNULLA_TRADE = "trade_x"


def _btn_annulla() -> InlineKeyboardButton:
    """✖️ Annulla nelle schermate del builder (v6.1.0): chiude la conversazione, la bozza a metà
    si annulla (come /annulla_trade). Gestito da cb_annulla_trade, nei fallback dei builder."""
    return InlineKeyboardButton("✖️ Annulla", callback_data=ANNULLA_TRADE)


async def cb_annulla_trade(update, context) -> int:
    from telegram.ext import ConversationHandler
    q = update.callback_query
    await q.answer()
    for chiave in ("trade_id", "adm_trade_id"):
        tid = context.user_data.pop(chiave, None)
        if tid:
            db.cambia_stato_trade(tid, ("bozza",), "annullata")   # solo una bozza, mai una trade inviata
    for chiave in ("trade_squadre_ordine", "trade_squadra_corrente_idx", "trade_squadre_corrente_idx",
                   "adm_trade_squadre", "adm_trade_squadre_left"):
        context.user_data.pop(chiave, None)
    try:
        if q.data.endswith(":menu"):                   # ← Trade: si esce dal builder e si torna al menu Trade
            from handlers.menu import _TESTO_TRADE, _kb_menu_trade
            await q.edit_message_text(_TESTO_TRADE, parse_mode="HTML", reply_markup=_kb_menu_trade())
        else:
            await q.edit_message_text("✖️ Trade annullata.")
    except Exception:
        pass
    return ConversationHandler.END


def _kb_n_squadre() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("2 squadre", callback_data="trade_n:2"),
        InlineKeyboardButton("3 squadre", callback_data="trade_n:3"),
        InlineKeyboardButton("4 squadre", callback_data="trade_n:4"),
    ], [InlineKeyboardButton("← Trade", callback_data=ANNULLA_TRADE + ":menu"), _btn_annulla()]])


def _kb_squadre(escludi: list[str]) -> InlineKeyboardMarkup:
    tutti = tm.get_all_teams()
    bottoni = [
        InlineKeyboardButton(t["nome"], callback_data=f"trade_sq:{t['id']}")
        for t in tutti if t["id"] not in escludi
    ]
    righe = [bottoni[i:i+2] for i in range(0, len(bottoni), 2)]
    righe.append([_btn_annulla()])
    return InlineKeyboardMarkup(righe)


def _kb_asset_menu(trade_id: int, team_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏀 Giocatori", callback_data=f"trade_am:g:{trade_id}:{team_id}"),
            InlineKeyboardButton("🎯 Pick",      callback_data=f"trade_am:p:{trade_id}:{team_id}"),
            InlineKeyboardButton("📋 Diritti",   callback_data=f"trade_am:d:{trade_id}:{team_id}"),
        ],
        [InlineKeyboardButton("✅ Conferma squadra", callback_data=f"trade_am:ok:{trade_id}:{team_id}")],
        [_btn_annulla()],
    ])


def _contratto_str(r: dict) -> str:
    """'20x2' da una riga di roster (importo del contratto × anni residui)."""
    from handlers.tagli import _anni_residui
    try:
        anni = _anni_residui(r, settings.stagione_corrente())
    except Exception:
        anni = r.get("anni_originali") or "?"
    importo = r.get("importo_originale") or r.get("importo")
    return f"{importo}x{anni}"


def _contratti_trade(items: list) -> dict:
    """{giocatore_id: '20x2'} per i giocatori della trade, dai roster di chi li cede."""
    out, roster_cache = {}, {}
    for i in items:
        if i["tipo"] != "giocatore":
            continue
        tid = i["team_id_da"]
        if tid not in roster_cache:
            roster_cache[tid] = {r["giocatore_id"]: r for r in db.get_roster_team(tid) or []}
        r = roster_cache[tid].get(i["giocatore_id"])
        if r:
            out[i["giocatore_id"]] = _contratto_str(r)
    return out


def _testo_riepilogo(trade_id: int) -> str:
    trade  = db.get_trade(trade_id)
    items  = db.get_items_trade(trade_id)
    squadre = db.get_squadre_trade(trade_id)

    label = _label_bozza(trade) if trade else f"#{trade_id}"
    righe = [f"📋 <b>Bozza {label}</b>\n"]
    contratti = _contratti_trade(items)

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
                righe.append(f"    • {_label_item(i, contratti)}")
        if riceve:
            righe.append("  <i>Riceve:</i>")
            for i in riceve:
                righe.append(f"    • {_label_item(i, contratti)}")
        if not invia and not riceve:
            righe.append("  <i>Nessun asset</i>")

    try:
        from validators.trade import avvisi_trade
        avvisi = avvisi_trade(trade_id)
        if avvisi:
            righe.append("\n" + "\n".join(avvisi))
    except Exception as e:
        logger.warning("Avvisi trade %s: %s", trade_id, e)

    return "\n".join(righe)


def _label_item(item: dict, contratti: dict | None = None) -> str:
    if item["tipo"] == "giocatore":
        nome = item.get("nome_common") or f"Giocatore #{item['giocatore_id']}"
        contratto = (contratti or {}).get(item["giocatore_id"])
        return f"{nome} {contratto}" if contratto else nome
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


def _kb_riepilogo(trade_id: int, ha_nota: bool = False) -> InlineKeyboardMarkup:
    nota_label = "📝 Modifica nota" if ha_nota else "📝 Aggiungi nota"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Proponi ai GM",   callback_data=f"trade_send:gm:{trade_id}")],
        [InlineKeyboardButton("📨 Manda ad admin",  callback_data=f"trade_send:admin:{trade_id}")],
        [InlineKeyboardButton(nota_label,           callback_data=f"trade_nota:{trade_id}")],
        [InlineKeyboardButton("💾 Salva bozza",     callback_data=f"trade_salva:{trade_id}")],
        [InlineKeyboardButton("✏️ Modifica",        callback_data=f"edit_back:{trade_id}")],
        [InlineKeyboardButton("🗑️ Elimina bozza",   callback_data=f"trade_del:{trade_id}")],
    ])


def _kb_riepilogo_non_valida(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Modifica",      callback_data=f"edit_back:{trade_id}")],
        [InlineKeyboardButton("🗑️ Elimina bozza", callback_data=f"trade_del:{trade_id}")],
    ])


# ── chi può toccare una bozza ───────────────────────────────────────────────────

def _puo_gestire_bozza(uid: int, trade: dict) -> bool:
    """Bozza del GM che la sta usando, o bozza admin ("admin") per un admin. La bozza di un GM la
    tocca solo quel GM, anche se è admin un altro (Luca, 19/10)."""
    if trade["proposta_da"] == "admin":
        return settings.is_admin(uid)
    team = tm.get_team_by_gm(uid)
    return bool(team and team["id"] == trade["proposta_da"])


async def _bozza_non_modificabile(query, trade_id: int) -> bool:
    """True (e avviso) se la trade non è più una bozza modificabile da chi preme:
    i vecchi bottoni di modifica non devono toccare trade già inviate."""
    trade = db.get_trade(trade_id)
    if not trade:
        await query.answer("Bozza non trovata (eliminata?).", show_alert=True)
        return True
    if trade["stato"] != "bozza":
        await query.answer(f"Non è più una bozza ({_STATI.get(trade['stato'], trade['stato'])}): "
                           "per cambiarla usa ♻️ Riprendi come bozza da /my_trades.", show_alert=True)
        return True
    if not _puo_gestire_bozza(query.from_user.id, trade):
        await query.answer("⛔ Non è una tua bozza.", show_alert=True)
        return True
    return False


# ── annuncio sul canale ─────────────────────────────────────────────────────────

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
            anni_orig = item.get("giocatore_anni", 1) or 1
            s_firma   = int(item.get("giocatore_stagione_firma") or stagione_int)
            anni      = anni_orig - (stagione_int - s_firma)   # 0 = x0 (v3.11.0)
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

    # Ordine dentro ogni sezione: giocatori, pick, diritti in fondo
    _ordine = {"giocatore": 0, "pick": 1, "diritti": 2}
    _ordina = lambda lst: sorted(lst, key=lambda i: _ordine.get(i["tipo"], 9))

    # Sezioni "cede"
    for sq in squadre:
        team     = tm.get_team_by_id(sq["team_id"])
        nome     = team["nome"] if team else sq["team_id"]
        items_sq = _ordina([i for i in items if i["team_id_da"] == sq["team_id"]])
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
            items_sq = _ordina([i for i in items if i["team_id_a"] == sq["team_id"]])
            if not items_sq:
                continue
            righe.append("")
            righe.append(f"<b>{nome} riceve:</b>")
            for item in items_sq:
                righe.append(_label_item_canale(item))

    return "\n".join(righe)


# ── etichette ───────────────────────────────────────────────────────────────────

def _label_bozza(trade: dict) -> str:
    """Genera la label di una bozza: 'BUF03-3' per GM, 'ADM-4' per admin."""
    num = trade.get("bozza_num", "?")
    proposta_da = trade.get("proposta_da", "")
    if proposta_da == "admin":
        return f"ADM-{num}"
    team_num = proposta_da.replace("team", "").zfill(2) if proposta_da.startswith("team") else "??"
    team = tm.get_team_by_id(proposta_da)
    team_short = team["nome"].split()[0].upper()[:3] if team else "???"
    return f"{team_short}{team_num}-{num}"

def _trade_label(trade: dict) -> str:
    """Label leggibile per una trade, anche prima che abbia un trade_ref."""
    if trade.get("trade_ref"):
        return trade["trade_ref"]
    return _label_bozza(trade)


# ── registro delle azioni (v6.0.0) ──────────────────────────────────────────────

def descrivi_trade(trade_id: int) -> str:
    """«LeBron Lakers → Celtics; Lakers 1st 2027 Celtics → Lakers» (per il registro)."""
    nome = lambda t: (tm.get_team_by_id(t) or {}).get("nome", t)
    items = db.get_items_trade(trade_id) or []
    return "; ".join(f"{_label_item(i)} {nome(i['team_id_da'])} → {nome(i['team_id_a'])}" for i in items) or "vuota"


def veste_bozza(trade: dict) -> str:
    """Bozza admin ("admin") → admin, bozza di una squadra → gm (anche se il GM è un admin)."""
    return "admin" if (trade or {}).get("proposta_da") == "admin" else "gm"


async def segna_trade(bot, user, veste: str, azione: str, trade_id: int, **campi) -> None:
    """Riga del registro per una trade: conta per tutte le squadre coinvolte. Non solleva."""
    try:
        from handlers.registro import segna
        trade = db.get_trade(trade_id) or {}
        squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id) or []]
        await segna(bot, user, veste, azione, squadre=squadre,
                    oggetto=f"{_trade_label(trade) if trade else trade_id}: {descrivi_trade(trade_id)}",
                    dettagli={"trade_id": trade_id}, **campi)
    except Exception as e:
        logger.warning("Registro trade %s: %s", trade_id, e)


# ── notifiche alle squadre ──────────────────────────────────────────────────────

async def _notifica_proponente(context, trade_id: int, testo: str) -> None:
    """Manda un messaggio privato a tutti i GM del team che ha proposto la trade."""
    trade = db.get_trade(trade_id)
    if not trade:
        return
    team = tm.get_team_by_id(trade["proposta_da"])
    if not team:
        return
    for gm_id in team.get("gm_ids", []):
        try:
            await context.bot.send_message(
                chat_id=gm_id,
                text=testo,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("_notifica_proponente GM %d: %s", gm_id, e)


async def _notifica_squadre(context, trade_id: int, testo: str, escludi: tuple = ()) -> None:
    """Messaggio privato ai GM di TUTTE le squadre della trade (tranne `escludi`).
    Nelle trade a 3-4 squadre anche chi non ha proposto deve sapere com'è finita.
    Per le trade create dagli admin (proposta_da 'admin') avvisa anche il gruppo admin."""
    trade = db.get_trade(trade_id)
    if not trade:
        return
    for sq in db.get_squadre_trade(trade_id):
        if sq["team_id"] in escludi:
            continue
        for gm_id in (tm.get_team_by_id(sq["team_id"]) or {}).get("gm_ids", []):
            try:
                await context.bot.send_message(chat_id=gm_id, text=testo, parse_mode="HTML")
            except Exception as e:
                logger.warning("_notifica_squadre GM %s: %s", gm_id, e)
    if trade["proposta_da"] == "admin" and "admin" not in escludi and settings.admin_group_id():
        try:
            await context.bot.send_message(chat_id=settings.admin_group_id(), text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("_notifica_squadre gruppo admin: %s", e)


# ── voti ────────────────────────────────────────────────────────────────────────

def _riga_voti(trade_id: int) -> str:
    icone = {"accettato": "✅", "rifiutato": "❌", "pending": "⏳"}
    parti = []
    for v in db.get_voti_trade(trade_id) or []:
        t = tm.get_team_by_id(v["team_id"])
        parti.append(f"{icone.get(v['voto'], '?')} {t['nome'] if t else v['team_id']}")
    return " · ".join(parti)


# ── tastiera della modifica di una bozza (/edit_trade) ──────────────────────────

def _kb_edit_menu(trade_id: int) -> InlineKeyboardMarkup:
    """Keyboard per l'edit: lista asset con ❌ + bottoni aggiungi."""
    items   = db.get_items_trade(trade_id)
    trade   = db.get_trade(trade_id)
    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
    bottoni = []

    def _nome(tid):
        if tid == "?":
            return "❓"
        t = tm.get_team_by_id(tid)
        return t["nome"] if t else tid

    for item in items:
        label = f"❌ {_label_item(item)} ({_nome(item['team_id_da'])} → {_nome(item['team_id_a'])})"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"edit_rm:{trade_id}:{item['id']}")])

    bottoni.append([InlineKeyboardButton("➕ Aggiungi asset", callback_data=f"edit_add:{trade_id}")])
    bottoni.append([InlineKeyboardButton("✅ Fatto",          callback_data=f"edit_done:{trade_id}")])
    return InlineKeyboardMarkup(bottoni)

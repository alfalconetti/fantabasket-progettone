"""
Trade: /my_trades (= /mie_trade) con stato, dettaglio e azioni di ogni trade della squadra, e
/bozze_trade con le bozze e le trade in voto. Callback mt:.
"""
import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import settings
from settings import solo_privato
import teams as tm
from utils import ROME
from handlers.trade_comune import _STATI, _label_bozza, _riga_voti, _testo_riepilogo, _trade_label

logger = logging.getLogger(__name__)


# ── /mie_trade ─────────────────────────────────────────────────────────────────

@solo_privato
async def cmd_mie_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers import nav
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    navig = [nav.indietro("menu:trade", "← Trade"), nav.chiudi()]

    bozze   = db.get_bozze_team(team["id"])
    pending = db.get_trade_in_votazione(team["id"])

    if not bozze and not pending:
        await nav.mostra(update, "📝 Nessuna bozza e nessuna trade da votare.\n\n"
                                 "<i>Tutte le tue trade, anche inviate o rifiutate: 📂 Le mie trade (/my_trades)</i>",
                         parse_mode="HTML", reply_markup=InlineKeyboardMarkup([navig]))
        return

    righe = []
    bottoni = []

    if bozze:
        righe.append("<b>📝 Bozze:</b>")
        for t in bozze:
            label = _label_bozza(t)
            righe.append(f"  • {label} — {t['n_squadre']} squadre")
            bottoni.append([InlineKeyboardButton(
                f"✏️ {label}", callback_data=f"edit_back:{t['id']}"
            )])

    if pending:
        righe.append("")
        righe.append("<b>⏳ In attesa del tuo voto:</b>")
        for t in pending:
            righe.append(f"  • {_trade_label(t)}")
            bottoni.append([InlineKeyboardButton(
                f"👀 {_trade_label(t)}", callback_data=f"trade_vedi:{t['id']}"
            )])
    righe.append("\n<i>Tutte le tue trade, anche inviate o rifiutate: /my_trades</i>")
    bottoni.append(navig)
    await nav.mostra(update, "\n".join(righe), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(bottoni))


# ── /my_trades ────────────────────────────────────────────────────────────────
# Tutte le trade della squadra (proposte o ricevute) con lo stato, il dettaglio e le
# azioni possibili: modifica (bozza), voto, ritiro della proposta, "riprendi come
# bozza" per quelle rifiutate. Callback mt:l (elenco), mt:v:<id>, mt:r:<id>, mt:c:<id>.

def _data_breve(ts) -> str:
    try:
        return ts.astimezone(ROME).strftime("%d/%m")
    except Exception:
        return ""


def _altre_squadre(trade_id: int, team_id: str) -> str:
    nomi = []
    for sq in db.get_squadre_trade(trade_id):
        if sq["team_id"] != team_id:
            t = tm.get_team_by_id(sq["team_id"])
            nomi.append(t["nome"] if t else sq["team_id"])
    return ", ".join(nomi) or "—"


def _testo_lista_my_trades(team_id: str):
    trades = db.get_trade_team(team_id)
    from handlers import nav
    navig = [nav.indietro("menu:trade", "← Trade"), nav.chiudi()]
    if not trades:
        return "📂 <b>Le tue trade</b>\n\nNessuna trade.", InlineKeyboardMarkup([navig])
    righe, kb = ["📂 <b>Le tue trade</b> <i>(ultime {})</i>\n".format(len(trades))], []
    for t in trades:
        stato = _STATI.get(t["stato"], t["stato"])
        chi = "proposta da te" if t["proposta_da"] == team_id else "ricevuta"
        righe.append(f"{stato.split(' ')[0]} <b>{_trade_label(t)}</b> — con {_altre_squadre(t['id'], team_id)} "
                     f"<i>({chi}, {_data_breve(t['aggiornato'])})</i>")
        kb.append([InlineKeyboardButton(f"{stato.split(' ')[0]} {_trade_label(t)}", callback_data=f"mt:v:{t['id']}")])
    righe.append("\n" + " · ".join(_STATI.values()))
    kb.append(navig)
    return "\n".join(righe), InlineKeyboardMarkup(kb)


@solo_privato
async def cmd_my_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team = tm.get_team_by_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    testo, kb = _testo_lista_my_trades(team["id"])
    await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=kb)


def _coinvolta(trade: dict, team_id: str) -> bool:
    return trade["proposta_da"] == team_id or any(
        s["team_id"] == team_id for s in db.get_squadre_trade(trade["id"]))


async def cb_my_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    team = tm.get_team_by_gm(query.from_user.id)
    if not team:
        await query.answer("⛔ Non sei registrato come GM.", show_alert=True)
        return
    parti = query.data.split(":")
    azione = parti[1]

    if azione == "l":
        await query.answer()
        testo, kb = _testo_lista_my_trades(team["id"])
        await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
        return

    trade_id = int(parti[2])
    trade = db.get_trade(trade_id)
    if not trade or not _coinvolta(trade, team["id"]):
        await query.answer("❌ Trade non trovata tra le tue.", show_alert=True)
        return
    indietro = [InlineKeyboardButton("← Elenco", callback_data="mt:l")]

    if azione == "r":                         # ritira una proposta ancora in voto
        if trade["proposta_da"] != team["id"]:
            await query.answer("⛔ Può ritirarla solo chi l'ha proposta.", show_alert=True)
            return
        if not db.cambia_stato_trade(trade_id, ("proposta",), "annullata", note="Ritirata dal proponente"):
            await query.answer("⚠️ Non è più in voto: non si può ritirare.", show_alert=True)
            return
        await query.answer("Proposta ritirata.")
        for sq in db.get_squadre_trade(trade_id):
            if sq["team_id"] == team["id"]:
                continue
            for gm in (tm.get_team_by_id(sq["team_id"]) or {}).get("gm_ids", []):
                try:
                    await context.bot.send_message(chat_id=gm, parse_mode="HTML",
                        text=f"🗑 <b>{team['nome']}</b> ha ritirato la proposta di trade <b>{_trade_label(trade)}</b>.")
                except Exception as e:
                    logger.warning("Avviso ritiro trade: %s", e)
        trade = db.get_trade(trade_id)

    elif azione == "c":                       # riprendi come bozza
        if trade["stato"] not in ("rifiutata_gm", "rifiutata_admin", "annullata"):
            await query.answer("Si possono riprendere solo trade rifiutate o ritirate.", show_alert=True)
            return
        await query.answer()
        nuovo = db.clona_trade_in_bozza(trade_id, team["id"], settings.stagione_corrente())
        bozza = db.get_trade(nuovo)
        await query.edit_message_text(
            f"♻️ Nuova bozza <b>{_label_bozza(bozza)}</b> creata da {_trade_label(trade)}.\n"
            f"Modificala e inviala di nuovo quando vuoi.", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Modifica", callback_data=f"edit_back:{nuovo}")],
                                               indietro]))
        return
    else:
        await query.answer()

    # dettaglio
    stato = trade["stato"]
    righe = [f"<b>{_trade_label(trade)}</b> — {_STATI.get(stato, stato)}",
             f"<i>Proposta da {('te' if trade['proposta_da'] == team['id'] else (tm.get_team_by_id(trade['proposta_da']) or {}).get('nome', trade['proposta_da']))}"
             f" · aggiornata il {_data_breve(trade['aggiornato'])}</i>", "",
             _testo_riepilogo(trade_id)]
    if stato in ("proposta", "rifiutata_gm", "in_approvazione"):
        voti = _riga_voti(trade_id)
        if voti:
            righe += ["", f"🗳 {voti}"]
    if trade.get("note") and stato in ("rifiutata_gm", "rifiutata_admin", "annullata"):
        righe += ["", f"📝 {html.escape(trade['note'])}"]
    kb = []
    if stato == "bozza" and trade["proposta_da"] == team["id"]:
        kb.append([InlineKeyboardButton("✏️ Modifica", callback_data=f"edit_back:{trade_id}")])
    if stato == "proposta":
        mio = next((v for v in db.get_voti_trade(trade_id) or [] if v["team_id"] == team["id"]), None)
        if mio and mio["voto"] == "pending":
            kb.append([InlineKeyboardButton("✅ Accetto", callback_data=f"trade_voto:si:{trade_id}:{team['id']}"),
                       InlineKeyboardButton("❌ Rifiuto", callback_data=f"trade_voto:no:{trade_id}:{team['id']}")])
        if trade["proposta_da"] == team["id"]:
            kb.append([InlineKeyboardButton("🗑 Ritira la proposta", callback_data=f"mt:r:{trade_id}")])
    if stato in ("rifiutata_gm", "rifiutata_admin", "annullata"):
        kb.append([InlineKeyboardButton("♻️ Riprendi come bozza", callback_data=f"mt:c:{trade_id}")])
    kb.append(indietro)
    await query.edit_message_text("\n".join(righe), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

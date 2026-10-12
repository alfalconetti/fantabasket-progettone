"""
Trade: proposta ai GM, voti, rifiuto con nota, invio e approvazione degli admin.
Callback: trade_voto:, trade_vedi:, trade_rifiuta_conf:, trade_admin:.
"""
import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import settings
import teams as tm
from utils import ROME, format_dt
from handlers.trade_comune import (
    TRADE_RIFIUTO_NOTA, _STATI, _formatta_annuncio_canale, _label_bozza, _notifica_proponente,
    _notifica_squadre, _riga_voti, _testo_riepilogo, _trade_label,
)
from handlers.trade_esegui import TradeNonEseguibile, _esegui_trade

logger = logging.getLogger(__name__)


# ── invio agli admin (trade tra due squadre di un solo GM o creata da un admin) ───

async def _invia_ad_admin(query, context, trade_id: int):
    admin_gid = settings.admin_group_id()
    testo = _testo_riepilogo(trade_id)
    trade = db.get_trade(trade_id)
    if not db.cambia_stato_trade(trade_id, ("bozza",), "in_approvazione"):
        await query.edit_message_text(f"⚠️ La trade non è più una bozza (stato: {_STATI.get(trade['stato'], trade['stato'])}).")
        return

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approva", callback_data=f"trade_admin:ok:{trade_id}"),
        InlineKeyboardButton("❌ Rifiuta", callback_data=f"trade_admin:no:{trade_id}"),
    ]])

    if admin_gid:
        bozza_label = _label_bozza(trade)
        await context.bot.send_message(
            chat_id=admin_gid,
            text=f"📨 <b>{bozza_label}</b> proposta da <b>{tm.get_team_by_id(trade['proposta_da'])['nome'] if tm.get_team_by_id(trade['proposta_da']) else trade['proposta_da']}</b>\n\n{testo}",
            parse_mode="HTML",
            reply_markup=kb,
        )

    await query.edit_message_text(
        f"✅ Trade inviata agli admin per approvazione.",
        parse_mode="HTML",
    )


# ── proposta ai GM e voti ───────────────────────────────────────────────────────

async def _proponi_ai_gm(query, context, trade_id: int):
    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
    trade   = db.get_trade(trade_id)
    testo   = _testo_riepilogo(trade_id)

    # Tutti i GM tranne il proponente devono votare
    da_votare = [tid for tid in squadre if tid != trade["proposta_da"]]
    if not db.cambia_stato_trade(trade_id, ("bozza",), "proposta"):
        await query.edit_message_text(f"⚠️ La trade non è più una bozza (stato: {_STATI.get(trade['stato'], trade['stato'])}).")
        return
    db._q("DELETE FROM trade_voti WHERE trade_id = %s", (trade_id,))   # voti di eventuali proposte precedenti
    db.inizializza_voti(trade_id, da_votare)

    for team_id in da_votare:
        team = tm.get_team_by_id(team_id)
        if not team:
            continue
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Accetto", callback_data=f"trade_voto:si:{trade_id}:{team_id}"),
            InlineKeyboardButton("❌ Rifiuto", callback_data=f"trade_voto:no:{trade_id}:{team_id}"),
        ]])
        bozza_label = _label_bozza(trade)
        nota_gm = trade.get("nota_gm", "") or ""
        proponente = tm.get_team_by_id(trade["proposta_da"])
        proponente_nome = proponente["gm_nome"] if proponente else "GM"
        testo_nota = f"\n\n💬 <b>Messaggio da {html.escape(proponente_nome)}:</b> <i>{html.escape(nota_gm)}</i>" if nota_gm else ""
        for gm_id in team.get("gm_ids", []):
            try:
                await context.bot.send_message(
                    chat_id=gm_id,
                    text=f"📨 <b>Proposta di trade ({bozza_label})</b>\n\n{testo}{testo_nota}\n\n"
                         f"<i>Accetti questa trade?</i>",
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            except Exception as e:
                logger.warning("Impossibile notificare GM %d: %s", gm_id, e)

    await query.edit_message_text(
        f"✅ Trade <b>{_trade_label(trade)}</b> proposta alle altre squadre.\nAttendo le risposte.",
        parse_mode="HTML",
    )


async def cb_trade_vedi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra il riepilogo di una trade in votazione con bottoni voto."""
    query = update.callback_query
    await query.answer()
    trade_id = int(query.data.split(":")[1])
    trade    = db.get_trade(trade_id)
    if not trade:
        await query.edit_message_text("❌ Trade non trovata.")
        return
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await query.edit_message_text("⛔ Non sei registrato come GM.")
        return
    testo = _testo_riepilogo(trade_id)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accetto", callback_data=f"trade_voto:si:{trade_id}:{team['id']}"),
        InlineKeyboardButton("❌ Rifiuto", callback_data=f"trade_voto:no:{trade_id}:{team['id']}"),
    ]])
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)


async def cb_voto_gm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback quando un GM accetta o rifiuta una trade proposta."""
    query = update.callback_query
    _, esito, trade_id_s, team_id = query.data.split(":")
    trade_id = int(trade_id_s)
    votante = tm.get_team_by_gm(query.from_user.id)
    if not votante or votante["id"] != team_id:
        await query.answer("⛔ Può votare solo il GM della squadra.", show_alert=True)
        return
    await query.answer()
    trade    = db.get_trade(trade_id)

    if not trade or trade["stato"] != "proposta":
        await query.edit_message_text("⚠️ Questa trade non è più in votazione.")
        return
    if not any(v["team_id"] == team_id for v in db.get_voti_trade(trade_id) or []):
        await query.edit_message_text("⚠️ La tua squadra non deve votare questa trade.")
        return

    voto = "accettato" if esito == "si" else "rifiutato"
    team = tm.get_team_by_id(team_id)

    if voto == "rifiutato":
        # Chiedi se vuole aggiungere una nota al rifiuto
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Rifiuto secco",   callback_data=f"trade_rifiuta_conf:{trade_id}:{team_id}:no"),
            InlineKeyboardButton("📝 Rifiuto con nota", callback_data=f"trade_rifiuta_conf:{trade_id}:{team_id}:si"),
        ]])
        await query.edit_message_text(
            f"Stai per rifiutare la trade <b>{_trade_label(trade)}</b>.\n\n"
            "Vuoi allegare una spiegazione?",
            parse_mode="HTML",
            reply_markup=kb,
        )
        # Il voto resta 'pending' finché il rifiuto non viene confermato
        # (prima la riga veniva cancellata: se il GM non confermava, la trade
        # poteva arrivare agli admin come se avesse accettato)
        return

    db.registra_voto(trade_id, team_id, voto)
    if db.chiudi_voto_se_tutti_accettano(trade_id):
        await query.edit_message_text(f"✅ Hai accettato la trade {_trade_label(trade)}. "
                                      f"Hanno accettato tutti: ora tocca agli admin.")
        await _invia_ad_admin_dopo_voti(context, trade_id)
        return
    await query.edit_message_text(f"✅ Hai accettato la trade {_trade_label(trade)}.\n🗳 {_riga_voti(trade_id)}")
    # trade a 3-4: il proponente vede l'avanzamento dei voti
    await _notifica_proponente(context, trade_id,
                               f"✅ <b>{team['nome'] if team else team_id}</b> ha accettato la trade "
                               f"<b>{_trade_label(trade)}</b>.\n🗳 {_riga_voti(trade_id)}")


# ── rifiuto con nota ────────────────────────────────────────────────────────────

async def cb_rifiuta_conf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gestisce la conferma del rifiuto — secco o con nota."""
    query = update.callback_query
    _, trade_id_s, team_id, con_nota = query.data.split(":")
    votante = tm.get_team_by_gm(query.from_user.id)
    if not votante or votante["id"] != team_id:
        await query.answer("⛔ Può votare solo il GM della squadra.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    trade_id = int(trade_id_s)
    trade    = db.get_trade(trade_id)

    if not trade or trade["stato"] != "proposta":
        await query.edit_message_text("⚠️ Questa trade non è più in votazione.")
        return ConversationHandler.END

    if con_nota == "no":
        # Rifiuto secco — esegui subito
        await _esegui_rifiuto(query, context, trade_id, team_id, nota=None)
        return ConversationHandler.END
    else:
        # Con nota — chiedi testo
        context.user_data["rifiuto_trade_id"] = trade_id
        context.user_data["rifiuto_team_id"]  = team_id
        await query.edit_message_text(
            "📝 Scrivi la motivazione del rifiuto (max 300 caratteri).\n"
            "<i>/salta per rifiutare senza nota.</i>",
            parse_mode="HTML",
        )
        return TRADE_RIFIUTO_NOTA


async def cb_rifiuto_nota_ricevi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Riceve la nota del rifiuto e completa il rifiuto."""
    trade_id = context.user_data.pop("rifiuto_trade_id", None)
    team_id  = context.user_data.pop("rifiuto_team_id", None)
    if not trade_id or not team_id:
        return ConversationHandler.END

    nota = None
    if not update.message.text.startswith("/salta"):
        nota = update.message.text[:300]

    # FakeQuery per compatibilità con _esegui_rifiuto
    class FakeQuery:
        def __init__(self, msg): self.message = msg
        async def answer(self): pass
        async def edit_message_text(self, text=None, **kw):
            kw.pop("reply_markup", None)
            await self.message.reply_text(text, **kw)

    fq = FakeQuery(update.message)
    await _esegui_rifiuto(fq, context, trade_id, team_id, nota=nota)
    return ConversationHandler.END


async def _esegui_rifiuto(query, context, trade_id: int, team_id: str, nota: str | None) -> None:
    """Esegue il rifiuto della trade con nota opzionale."""
    trade = db.get_trade(trade_id)
    team  = tm.get_team_by_id(team_id)
    db.registra_voto(trade_id, team_id, "rifiutato")
    note_db = f"Rifiutata da {team['nome'] if team else team_id}"
    if nota:
        note_db += f": {nota}"
    if not db.cambia_stato_trade(trade_id, ("proposta",), "rifiutata_gm", note=note_db):
        await query.edit_message_text("⚠️ Questa trade non è più in votazione.")
        return

    testo_altri = f"❌ <b>{team['nome'] if team else team_id}</b> ha rifiutato la trade <b>{_trade_label(trade)}</b>."
    if nota:
        testo_altri += f"\n\n📝 Motivazione: <i>{html.escape(nota)}</i>"
    testo_altri += "\n<i>La trade è chiusa. Il proponente può riprenderla come bozza da /my_trades.</i>"
    await _notifica_squadre(context, trade_id, testo_altri, escludi=(team_id,))

    testo_gm = f"❌ Hai rifiutato la trade {_trade_label(trade)}."
    if nota:
        testo_gm += f"\n📝 Nota: <i>{html.escape(nota)}</i>"
    await query.edit_message_text(testo_gm, parse_mode="HTML")


# ── approvazione degli admin ────────────────────────────────────────────────────

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
        text=f"✅ <b>Tutti i GM hanno accettato — {_trade_label(trade)}</b>\n\n{testo}",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await _notifica_squadre(context, trade_id,
                            f"🗳 Tutte le squadre hanno accettato la trade <b>{_trade_label(trade)}</b>: "
                            f"ora è in attesa degli admin.", escludi=("admin",))


async def cb_admin_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approva o rifiuta la trade."""
    query = update.callback_query
    if not settings.is_admin(query.from_user.id):
        await query.answer("⛔ Solo gli admin possono approvare o rifiutare.", show_alert=True)
        return
    await query.answer()
    _, esito, trade_id_s = query.data.split(":")
    trade_id = int(trade_id_s)
    admin_user = update.effective_user
    admin_nome = admin_user.first_name or admin_user.username or str(admin_user.id)

    if esito == "no":
        # Solo se è ancora in approvazione: mai sopra una trade già approvata ed eseguita
        if not db.cambia_stato_trade(trade_id, ("in_approvazione",), "rifiutata_admin",
                                     note=f"Rifiutata dagli admin ({admin_nome})"):
            t = db.get_trade(trade_id) or {}
            await query.edit_message_text(
                query.message.text_html + f"\n\nℹ️ <b>Già gestita</b>: stato {_STATI.get(t.get('stato'), t.get('stato'))}.",
                parse_mode="HTML")
            return
        t = db.get_trade(trade_id) or {}
        await query.edit_message_text(f"❌ Trade {_trade_label(t) if t else ''} rifiutata dagli admin ({admin_nome}).")
        await _notifica_squadre(context, trade_id,
                                f"🚫 Gli admin hanno rifiutato la trade <b>{_trade_label(t)}</b>.", escludi=("admin",))
        return

    trade    = db.get_trade(trade_id)
    if not trade or trade["stato"] != "in_approvazione":
        await query.edit_message_text(
            query.message.text_html + f"\n\nℹ️ <b>Non approvabile</b>: stato "
            f"{_STATI.get((trade or {}).get('stato'), (trade or {}).get('stato'))}.", parse_mode="HTML")
        return

    # Genera trade_ref (MAX progressivo per evitare collisioni)
    stagione = trade["stagione"]
    n_trade  = db.get_trade_count_approvate(stagione)
    trade_ref = f"TRADE-{stagione}-{n_trade + 1:03d}"

    from datetime import datetime
    ora = format_dt(datetime.now(ROME))

    # Approvazione + esecuzione atomiche: se fallisce, la trade resta com'era
    try:
        await _esegui_trade(context, trade_id, trade_ref, approvata_da=admin_nome)
    except TradeNonEseguibile as e:
        await query.edit_message_text(
            f"❌ <b>Trade non eseguita</b>: {e}.\nNessuna modifica è stata salvata; la trade resta da approvare.",
            parse_mode="HTML", reply_markup=query.message.reply_markup)   # Approva/Rifiuta restano
        return

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

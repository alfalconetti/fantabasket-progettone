"""
Gestione tagli con calcolo impatto taglio automatico.

Percentuali impatto taglio dal regolamento:
  x1 → 3 anni: 50-30-20
  x2 → 4 anni: 60-50-50-40
  x3 → 5 anni: 70-70-60-50-50

Per contratti ≤5M: tabella fissa (vedi _TABELLA_SPALMATA_BASSA).
"""
import logging
import math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
import settings
from settings import solo_privato, richiede_fase, FASI_TRADE_APERTE
import teams as tm

logger = logging.getLogger(__name__)

MAX_TAGLI_GRATUITI = 3  # dal regolamento: max 3 tagli 1x1 gratuiti a stagione


def _e_taglio_gratuito(importo: int, anni_residui: int) -> bool:
    """Contratto 1M x1 → taglio senza impatto (nessun impatto taglio, conta nel limite stagionale)."""
    return importo == 1 and anni_residui == 1

# Percentuali impatto taglio per importo > 5M
_PERC_SPALMATA = {
    1: [0.50, 0.30, 0.20],
    2: [0.60, 0.50, 0.50, 0.40],
    3: [0.70, 0.70, 0.60, 0.50, 0.50],
}

# Tabella fissa per contratti ≤5M (importo: {anni: [rate]})
_TABELLA_SPALMATA_BASSA = {
    1: {1: [1],       2: [1, 1],          3: [1, 1, 1]},
    2: {1: [1, 1],    2: [1, 1, 1, 1],    3: [2, 1, 1, 1, 1]},
    3: {1: [1, 1, 1], 2: [2, 2, 1, 1],    3: [2, 2, 2, 2, 1]},
    4: {1: [2, 1, 1], 2: [2, 2, 2, 2],    3: [3, 3, 2, 2, 2]},
    5: {1: [2, 2, 1], 2: [3, 3, 2, 2],    3: [4, 3, 3, 3, 2]},
}


def calcola_impatto_taglio(importo: int, anni_residui: int, stagione_taglio: str) -> list[dict]:
    """
    Calcola le rate di impatto taglio.
    La somma delle rate = anni_residui × importo.
    anni_residui viene cappato a 3 (massimo previsto dal regolamento).
    """
    anno_base   = int(stagione_taglio)
    anni_res    = min(anni_residui, 3)  # il regolamento va fino a x3

    if importo <= 5 and importo in _TABELLA_SPALMATA_BASSA:
        rate_raw = _TABELLA_SPALMATA_BASSA[importo].get(anni_res, [importo])
        return [
            {"stagione": str(anno_base + i), "importo": r}
            for i, r in enumerate(rate_raw)
        ]

    perc   = _PERC_SPALMATA[anni_res]
    rate   = [math.ceil(importo * p) for p in perc]
    target = anni_residui * importo   # usa anni_residui originale per il totale
    diff   = sum(rate) - target
    rate[-1] = max(0, rate[-1] - diff)

    return [
        {"stagione": str(anno_base + i), "importo": r}
        for i, r in enumerate(rate) if r > 0
    ]


def _anni_residui(contratto: dict, stagione_corrente: str) -> int:
    """
    Anni residui del contratto.
    - Rookie: derivato da anni_scala (0,2 → 2 anni; 1,3 → 1 anno)
    - Normale: anni_originali usato direttamente (stagione_firma=2026 dalla migrazione)
    """
    if contratto.get("tipo_contratto") == "rookie" or contratto.get("tipo") == "rookie":
        scala = int(contratto.get("anni_scala") or 0)
        return 2 if scala in (0, 2) else 1
    anni_orig = contratto["anni_originali"]
    s_firma   = int(contratto.get("stagione_firma") or stagione_corrente)
    s_corr    = int(stagione_corrente)
    return max(1, anni_orig - (s_corr - s_firma))


# ── /taglia <giocatore_id> ────────────────────────────────────────────────────

@solo_privato
@richiede_fase(*FASI_TRADE_APERTE, msg="❌ I tagli non sono disponibili in questa fase.")
async def cmd_taglia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return

    if not context.args:
        # Mostra roster con bottoni
        roster = db.get_roster_team(team["id"])
        if not roster:
            await update.effective_message.reply_text("Il tuo roster è vuoto.")
            return
        bottoni = [
            [InlineKeyboardButton(
                f"{r['nome_common']} ({r['importo']}M)",
                callback_data=f"taglia_sel:{r['giocatore_id']}"
            )]
            for r in roster
        ]
        await update.effective_message.reply_text(
            "Seleziona il giocatore da tagliare:",
            reply_markup=InlineKeyboardMarkup(bottoni),
        )
        return

    try:
        gid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID giocatore non valido.")
        return

    await _mostra_anteprima_taglio(update.effective_message, team, gid)


async def cb_seleziona_taglio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid  = int(query.data.split(":")[1])
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    await _mostra_anteprima_taglio(query, team, gid)


async def _mostra_anteprima_taglio(msg_or_query, team: dict, gid: int):
    contratto = db.get_contratto_attivo(gid)
    if not contratto or contratto["team_id"] != team["id"]:
        testo = "❌ Giocatore non trovato nel tuo roster."
        if hasattr(msg_or_query, "edit_message_text"):
            await msg_or_query.edit_message_text(testo)
        else:
            await msg_or_query.reply_text(testo)
        return

    giocatore  = db.get_giocatore(gid)
    stagione   = settings.stagione_corrente()
    anni_res   = _anni_residui(contratto, stagione)
    gratuito   = _e_taglio_gratuito(contratto["importo"], anni_res)

    if gratuito:
        usati = db.get_tagli_gratuiti_usati(team["id"], stagione)
        rimanenti = MAX_TAGLI_GRATUITI - usati
        if rimanenti <= 0:
            testo = (
                f"❌ <b>{giocatore['nome_common']}</b> — taglio senza impatto non disponibile.\n"
                f"Hai già usato tutti i {MAX_TAGLI_GRATUITI} tagli gratuiti 1x1 questa stagione.\n\n"
                f"Puoi comunque tagliarlo ma genererà impatto taglio sul cap."
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✂️ Taglia con impatto", callback_data=f"taglia_ok_forzato:{gid}"),
                InlineKeyboardButton("❌ Annulla",              callback_data="taglia_no"),
            ]])
        else:
            testo = (
                f"✂️ <b>Taglio senza impatto — {giocatore['nome_common']}</b>\n\n"
                f"Contratto: <b>1M × 1 anno</b>\n"
                f"✅ Nessuna impatto taglio sul cap.\n"
                f"Tagli gratuiti rimanenti: <b>{rimanenti - 1}/{MAX_TAGLI_GRATUITI}</b>"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Conferma taglio", callback_data=f"taglia_ok:{gid}"),
                InlineKeyboardButton("❌ Annulla",          callback_data="taglia_no"),
            ]])
    else:
        rate = calcola_impatto_taglio(contratto["importo"], anni_res, stagione)
        righe = [
            f"✂️ <b>Taglio — {giocatore['nome_common']}</b>\n",
            f"Contratto: {contratto['importo']}M × {anni_res} anni residui\n",
            "<b>Impatto taglio sul cap:</b>",
        ]
        for r in rate:
            righe.append(f"  • Stagione {r['stagione']}: {r['importo']}M")
        testo = "\n".join(righe)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Conferma taglio", callback_data=f"taglia_ok:{gid}"),
            InlineKeyboardButton("❌ Annulla",          callback_data="taglia_no"),
        ]])

    if hasattr(msg_or_query, "edit_message_text"):
        await msg_or_query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
    else:
        await msg_or_query.reply_text(testo, parse_mode="HTML", reply_markup=kb)


async def cb_conferma_taglio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts   = query.data.split(":")
    forzato = parts[0] == "taglia_ok_forzato"
    gid     = int(parts[1])
    user    = update.effective_user
    team    = tm.get_team_by_gm(user.id)

    contratto = db.get_contratto_attivo(gid)
    if not contratto or contratto["team_id"] != team["id"]:
        await query.edit_message_text("❌ Giocatore non trovato nel tuo roster.")
        return

    stagione  = settings.stagione_corrente()
    anni_res  = _anni_residui(contratto, stagione)
    gratuito  = _e_taglio_gratuito(contratto["importo"], anni_res) and not forzato
    giocatore = db.get_giocatore(gid)

    from database import _q
    _q("UPDATE contratti SET attivo = FALSE WHERE id = %s", (contratto["id"],))

    if gratuito:
        db.registra_transazione(
            "cut", gid, team["id"], None, stagione,
            contratto_id=contratto["id"], gratuito=True,
            note=f"Taglio senza impatto 1x1 — {giocatore['nome_common']}"
        )
        usati = db.get_tagli_gratuiti_usati(team["id"], stagione)
        await query.edit_message_text(
            f"✅ <b>{giocatore['nome_common']}</b> tagliato gratuitamente.\n"
            f"Tagli gratuiti usati questa stagione: <b>{usati}/{MAX_TAGLI_GRATUITI}</b>",
            parse_mode="HTML",
        )
    else:
        rate = calcola_impatto_taglio(contratto["importo"], anni_res, stagione)
        trans_id = db.registra_transazione(
            "cut", gid, team["id"], None, stagione,
            contratto_id=contratto["id"], gratuito=False,
            note=f"Taglio {giocatore['nome_common']} {contratto['importo']}M x{anni_res}"
        )
        for r in rate:
            _q(
                "INSERT INTO impatto_taglio "
                "(team_id, giocatore_id, stagione_taglio, stagione, importo, transazione_id) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (team["id"], gid, stagione, r["stagione"], r["importo"], trans_id)
            )
        righe_imp = "\n".join(f"  • {r['stagione']}: {r['importo']}M" for r in rate)
        await query.edit_message_text(
            f"✅ <b>{giocatore['nome_common']}</b> tagliato.\n\nImpatto taglio:\n{righe_imp}",
            parse_mode="HTML",
        )
    logger.info("Taglio: team=%s giocatore=%d gratuito=%s", team["id"], gid, gratuito)


async def cb_annulla_taglio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Taglio annullato.")


def get_handlers() -> list:
    return [
        CommandHandler("taglia", cmd_taglia),
        CallbackQueryHandler(cb_seleziona_taglio,  pattern=r"^taglia_sel:\d+$"),
        CallbackQueryHandler(cb_conferma_taglio,   pattern=r"^taglia_ok:\d+$|^taglia_ok_forzato:\d+$"),
        CallbackQueryHandler(cb_annulla_taglio,    pattern=r"^taglia_no$"),
    ]

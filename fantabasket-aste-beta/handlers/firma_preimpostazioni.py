"""
Firma, RFA: pre-impostazioni del proprietario alla chiusura dell'asta (pareggio automatico
fino a N anni, rifiuto sopra una cifra), applicate quando il vincitore sceglie gli anni.
Callback pre_par_*, pre_rifiuto*.
"""
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import database as db
import teams as tm
import utils
import settings
from handlers.helpers import log_warn as _log_warn
from handlers.firma_comune import (
    anni_minimi, importo_minimo_pareggio, soglia_pareggio, _registra_firma_finale,
)

logger = logging.getLogger(__name__)


# ── chiusura di un'asta RFA: il proprietario può decidere prima (pre-impostazioni) ───

async def _notifica_proprietario_chiusura_rfa(context, asta_id: int):
    """
    Notifica il proprietario RFA alla chiusura dell'asta.
    Mostra importo vincitore, scadenza pareggio (conclusa_at + 24h),
    avviso fascia se sotto soglia, e bottone per pre-impostare il pareggio.
    """
    from datetime import timedelta
    asta = db.get_asta(asta_id)
    if not asta:
        return
    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop:
        return
    team_vince = tm.get_team_by_id(asta["offerente_team_id"])
    team_vince_nome = team_vince["nome"] if team_vince else "altra franchigia"

    importo   = asta["offerta_corrente"]
    vec_comp  = asta["vecchio_compenso"] or 0
    conclusa_at = datetime.fromisoformat(asta["conclusa_at"])
    scadenza_pareggio = conclusa_at + timedelta(hours=settings.timeout_pareggio_ore())
    min_importo = importo_minimo_pareggio(importo, vec_comp)
    sotto_soglia = importo < soglia_pareggio(vec_comp)
    anni_obbligatori = anni_minimi(importo) == 3  # ≥35M → anni fissi

    nota_fascia = ""
    if vec_comp > 20 and sotto_soglia:
        fraz = "1/3" if vec_comp <= 34 else "1/2"
        nota_fascia = (
            f"\n\n⚠️ <b>Attenzione fascia contrattuale</b>\n"
            f"L'offerta ({importo}M) è inferiore a {fraz} del vecchio compenso ({vec_comp}M).\n"
            f"Per pareggiare dovrai offrire almeno <b>{min_importo}M</b>.\n"
            f"In questo caso gli anni sono <b>liberi</b> e non vincolati a quelli del vincitore."
        )

    if anni_obbligatori:
        # ≥35M: anni già noti (3), pareggio parte subito — niente pre-pareggio
        testo = (
            f"⚖️ <b>L'asta RFA per {asta['giocatore']} è terminata</b>\n\n"
            f"<b>{team_vince_nome}</b> ha offerto: <b>{importo}M × 3 anni</b> (obbligatori per contratti ≥{settings.get()['soglia_anni_3']}M)\n\n"
            f"⏰ Hai tempo fino a <b>{utils.format_dt(scadenza_pareggio.isoformat())}</b> per decidere se pareggiare."
            f"{nota_fascia}"
        )
        kb = None
    else:
        ore_vincitore = settings.timeout_firma_rfa_ore()
        testo = (
            f"⚖️ <b>L'asta RFA per {asta['giocatore']} è terminata</b>\n\n"
            f"<b>{team_vince_nome}</b> ha offerto: <b>{importo}M</b>\n"
            f"Gli anni verranno comunicati entro {ore_vincitore}h.\n\n"
            f"⏰ Scadenza pareggio: <b>{utils.format_dt(scadenza_pareggio.isoformat())}</b>"
            f"{nota_fascia}\n\n"
            f"<b>Pre-impostazioni opzionali</b> (ti evitano di aspettare le {ore_vincitore}h del vincitore):\n"
            f"• <b>Pre-pareggio ≤N anni</b>: pareggia automaticamente se il vincitore offre ≤N anni\n"
            f"• <b>Rifiuto assoluto</b>: il giocatore passa al vincitore qualunque siano gli anni\n"
            f"• <b>Rifiuto condizionale >N anni</b>: passa al vincitore solo se offre più di N anni\n"
            f"• Pre-pareggio e rifiuto condizionale sono compatibili se i valori non si sovrappongono\n\n"
            f"<i>Se non pre-imposti nulla, riceverai il messaggio completo appena il vincitore sceglie gli anni.</i>"
        )
        kb = _kb_preimpostazioni(asta_id, None, 0)

    for gm_id in team_prop["gm_ids"]:
        try:
            await context.bot.send_message(
                chat_id=gm_id, text=testo, parse_mode="HTML", reply_markup=kb
            )
        except Exception as e:
            await _log_warn(context, f"Notifica chiusura RFA proprietario {gm_id}: {e}")


def _testo_stato_preimpostazioni(asta: dict, pre: dict | None, rifiuto: int) -> tuple[str]:
    """Costruisce il testo di riepilogo delle pre-impostazioni correnti."""
    giocatore = asta["giocatore"]
    importo   = asta["offerta_corrente"]
    vec_comp  = asta["vecchio_compenso"] or 0
    sotto_soglia = importo < soglia_pareggio(vec_comp)
    min_importo  = importo_minimo_pareggio(importo, vec_comp)
    importo_eff  = min_importo if sotto_soglia else importo

    righe = [f"📋 <b>Pre-impostazioni per {giocatore}</b>\n"]

    if pre:
        anni_p = pre["anni"]
        righe.append(f"⚡ Pareggio: ≤{anni_p} ann{'o' if anni_p==1 else 'i'} a {importo_eff}M")
    else:
        righe.append("⚡ Pareggio: non impostato")

    if rifiuto == -1:
        righe.append("❌ Rifiuto: assoluto")
    elif rifiuto > 0:
        righe.append(f"❌ Rifiuto: condizionale se vincitore offre >{rifiuto} ann{'o' if rifiuto==1 else 'i'}")
    else:
        righe.append("❌ Rifiuto: non impostato")

    righe.append("\n<i>Puoi modificare tutto finché il vincitore non sceglie gli anni.</i>")
    return "\n".join(righe),


def _kb_preimpostazioni(asta_id: int, pre: dict | None, rifiuto: int) -> InlineKeyboardMarkup:
    """Keyboard principale con bottoni contestuali in base allo stato attuale."""
    bottoni = []
    if pre:
        bottoni.append([
            InlineKeyboardButton("✏️ Modifica pareggio", callback_data=f"pre_par_anni:{asta_id}"),
            InlineKeyboardButton("🗑 Rimuovi pareggio", callback_data=f"pre_par_annulla:{asta_id}"),
        ])
    else:
        bottoni.append([InlineKeyboardButton("⚡ Pre-imposta pareggio", callback_data=f"pre_par_anni:{asta_id}")])

    if rifiuto != 0:
        bottoni.append([
            InlineKeyboardButton("✏️ Modifica rifiuto", callback_data=f"pre_rifiuto:{asta_id}"),
            InlineKeyboardButton("🗑 Rimuovi rifiuto", callback_data=f"pre_rifiuto_annulla:{asta_id}"),
        ])
    else:
        bottoni.append([InlineKeyboardButton("❌ Pre-imposta rifiuto", callback_data=f"pre_rifiuto:{asta_id}")])

    return InlineKeyboardMarkup(bottoni)


async def pre_pareggio_anni_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Il proprietario RFA clicca 'Pre-imposta pareggio'.
    Chiede quanti anni vuole offrire (l'importo è già noto dalla DB).
    """
    query = update.callback_query
    await query.answer()

    asta_id = int(query.data.split(":")[1])
    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] not in ("CHIUSA",):
        await query.edit_message_text("❌ Asta non più disponibile per il pre-pareggio.")
        return

    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop or query.from_user.id not in team_prop["gm_ids"]:
        await query.answer("⛔ Non sei il proprietario di questo giocatore.", show_alert=True)
        return

    importo   = asta["offerta_corrente"]
    vec_comp  = asta["vecchio_compenso"] or 0
    min_importo = importo_minimo_pareggio(importo, vec_comp)
    sotto_soglia = importo < soglia_pareggio(vec_comp)

    # Anni validi per il pareggio:
    # - Sotto soglia: anni liberi, mostriamo tutti (1, 2, 3)
    # - Sopra soglia: almeno anni_minimi(importo_pareggio) — es. 25M → min 2 anni
    min_anni_validi = 1 if sotto_soglia else anni_minimi(min_importo)

    bottoni_anni = [
        [InlineKeyboardButton(f"{a} ann{'o' if a==1 else 'i'}", callback_data=f"pre_par_set:{asta_id}:{a}")]
        for a in [1, 2, 3] if a >= min_anni_validi
    ]
    bottoni_anni.append([InlineKeyboardButton("← Indietro", callback_data=f"pre_rifiuto_indietro:{asta_id}")])

    importo_label = f"{min_importo}M" if sotto_soglia else f"{importo}M"
    nota = f"⚠️ Pareggerai a <b>{importo_label}</b>" + (" (soglia minima di fascia)" if sotto_soglia else "")

    if sotto_soglia:
        istruzioni = (
            f"Pareggio automatico a prescindere dagli anni offerti dal vincitore — "
            f"gli anni che scegli sono quelli del tuo contratto (minimo {min_anni_validi})."
        )
    else:
        istruzioni = (
            f"Pareggio automatico se il vincitore offre ≤ agli anni che scegli. "
            f"Il minimo consentito per questa fascia è {min_anni_validi} ann{'o' if min_anni_validi==1 else 'i'}."
        )

    await query.edit_message_text(
        f"⚡ <b>Pre-pareggio per {asta['giocatore']}</b>\n\n"
        f"{nota}\n\n"
        f"Scegli per quanti anni vuoi pre-impostare il pareggio.\n"
        f"<i>{istruzioni}</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni_anni),
    )


async def pre_pareggio_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salva il pre-pareggio e aggiorna il messaggio con opzioni Modifica/Annulla."""
    query = update.callback_query
    await query.answer()

    _, asta_id_s, anni_s = query.data.split(":")
    asta_id = int(asta_id_s)
    anni    = int(anni_s)

    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] not in ("CHIUSA",):
        await query.edit_message_text("❌ Asta non più disponibile.")
        return

    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop or query.from_user.id not in team_prop["gm_ids"]:
        await query.answer("⛔ Non sei il proprietario.", show_alert=True)
        return

    importo   = asta["offerta_corrente"]
    vec_comp  = asta["vecchio_compenso"] or 0
    min_importo = importo_minimo_pareggio(importo, vec_comp)
    sotto_soglia = importo < soglia_pareggio(vec_comp)
    importo_eff = min_importo if sotto_soglia else importo

    db.set_pareggio_preimpostato(asta_id, importo_eff, anni)
    from registro import segna_asta
    await segna_asta(context.bot, query.from_user, "gm", "pareggio preimpostato", asta,
                     dopo=f"pareggio fino a {anni} anni, {importo_eff}M")

    # Check: se c'è rifiuto condizionale che si sovrappone, avviso
    rifiuto = db.get_rifiuto_preimpostato(asta_id)
    if rifiuto > 0 and anni >= rifiuto:
        await query.answer(
            f"⚠️ Attenzione: il rifiuto condizionale (>{rifiuto} anni) si sovrappone al pre-pareggio (≤{anni} anni). "
            f"Modifica il rifiuto per evitare contraddizioni.",
            show_alert=True
        )

    pre_aggiornato = db.get_pareggio_preimpostato(asta_id)
    testo, = _testo_stato_preimpostazioni(dict(asta), pre_aggiornato, rifiuto)
    await query.edit_message_text(
        testo,
        parse_mode="HTML",
        reply_markup=_kb_preimpostazioni(asta_id, pre_aggiornato, rifiuto),
    )


async def pre_pareggio_annulla_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulla il pre-pareggio."""
    query = update.callback_query
    await query.answer()

    asta_id = int(query.data.split(":")[1])
    asta = db.get_asta(asta_id)
    if not asta:
        await query.edit_message_text("❌ Asta non trovata.")
        return

    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop or query.from_user.id not in team_prop["gm_ids"]:
        await query.answer("⛔ Non sei il proprietario.", show_alert=True)
        return

    db.clear_pareggio_preimpostato(asta_id)
    from registro import segna_asta
    await segna_asta(context.bot, query.from_user, "gm", "pareggio preimpostato tolto", asta, dopo="tolto")
    rifiuto = db.get_rifiuto_preimpostato(asta_id)
    testo, = _testo_stato_preimpostazioni(dict(asta), None, rifiuto)
    await query.edit_message_text(
        testo,
        parse_mode="HTML",
        reply_markup=_kb_preimpostazioni(asta_id, None, rifiuto),
    )


# ── pre-rifiuto: "non pareggio sopra X" ─────────────────────────────────────────

async def pre_rifiuto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Il proprietario RFA pre-imposta il rifiuto.
    Mostra due opzioni: rifiuto assoluto o rifiuto condizionale >N anni.
    """
    query = update.callback_query
    await query.answer()

    asta_id = int(query.data.split(":")[1])
    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] not in ("CHIUSA",):
        await query.edit_message_text("❌ Asta non più disponibile.")
        return

    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop or query.from_user.id not in team_prop["gm_ids"]:
        await query.answer("⛔ Non sei il proprietario di questo giocatore.", show_alert=True)
        return

    pre = db.get_pareggio_preimpostato(asta_id)
    anni_pre = pre["anni"] if pre else None
    importo  = asta["offerta_corrente"]
    vec_comp = asta["vecchio_compenso"] or 0
    sotto_soglia = importo < soglia_pareggio(vec_comp)

    bottoni = []

    if sotto_soglia:
        # Sotto soglia: anni liberi → rifiuto condizionale non ha senso, solo assoluto
        bottoni.append([InlineKeyboardButton(
            "❌ Rifiuto assoluto — il giocatore passa al vincitore a prescindere dagli anni",
            callback_data=f"pre_rifiuto_set:{asta_id}:-1"
        )])
        nota_soglia = (
            "\n\n<i>Sei in fascia sotto soglia — gli anni del vincitore non contano per il pareggio. "
            "L'unica pre-impostazione sensata è il rifiuto assoluto.</i>"
        )
    else:
        nota_soglia = ""
        # Rifiuto assoluto — solo se non c'è pre-pareggio
        if not pre:
            bottoni.append([InlineKeyboardButton(
                "❌ Rifiuto assoluto — il giocatore passa al vincitore qualunque siano gli anni",
                callback_data=f"pre_rifiuto_set:{asta_id}:-1"
            )])

        # Rifiuto condizionale >N anni (solo 1 e 2, mai >3)
        for n in [1, 2]:
            if anni_pre is None or n > anni_pre:
                if anni_pre is None:
                    label = f"❌ Rifiuto se offre >{n} ann{'o' if n==1 else 'i'} — pareggio se ≤{n}"
                else:
                    label = f"❌ Rifiuto se offre >{n} ann{'o' if n==1 else 'i'}"
                bottoni.append([InlineKeyboardButton(label, callback_data=f"pre_rifiuto_set:{asta_id}:{n}")])

    bottoni.append([InlineKeyboardButton("← Indietro", callback_data=f"pre_rifiuto_indietro:{asta_id}")])

    nota_pre = (
        f"\n\n<i>Hai già impostato pre-pareggio a ≤{anni_pre} anni — "
        f"il rifiuto assoluto non è disponibile.</i>"
    ) if pre and not sotto_soglia else ""

    await query.edit_message_text(
        f"❌ <b>Pre-rifiuto per {asta['giocatore']}</b>\n\n"
        f"Scegli il tipo di rifiuto:\n\n"
        + ("• <b>Assoluto</b>: passa al vincitore qualunque siano gli anni\n"
           "• <b>Condizionale >N anni</b>: passa al vincitore solo se offre più di N anni "
           "(compatibile con pre-pareggio ≤N anni)\n"
           if not sotto_soglia else "")
        + f"{nota_pre}{nota_soglia}\n\n"
        f"<i>Puoi modificarla o annullarla finché il vincitore non sceglie gli anni.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )


async def pre_rifiuto_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salva il rifiuto preimpostato."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    asta_id = int(parts[1])
    valore  = int(parts[2])  # -1=assoluto, 1-2=condizionale

    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] not in ("CHIUSA",):
        await query.edit_message_text("❌ Asta non più disponibile.")
        return

    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop or query.from_user.id not in team_prop["gm_ids"]:
        await query.answer("⛔ Non sei il proprietario.", show_alert=True)
        return

    # Check compatibilità: rifiuto assoluto incompatibile con pre-pareggio
    pre = db.get_pareggio_preimpostato(asta_id)
    if valore == -1 and pre:
        await query.answer(
            "❌ Rifiuto assoluto non compatibile con un pre-pareggio già impostato. "
            "Annulla prima il pre-pareggio.",
            show_alert=True
        )
        return

    # Check: rifiuto condizionale deve essere > anni del pre-pareggio
    if valore > 0 and pre and valore <= pre["anni"]:
        await query.answer(
            f"❌ Il rifiuto condizionale (>{valore} anni) si sovrappone al pre-pareggio (≤{pre['anni']} anni). "
            f"Scegli un valore maggiore.",
            show_alert=True
        )
        return

    db.set_rifiuto_preimpostato(asta_id, valore)
    from registro import segna_asta
    await segna_asta(context.bot, query.from_user, "gm", "rifiuto preimpostato", asta,
                     dopo="rifiuto assoluto" if valore == -1 else f"rifiuto sopra {valore} anni")

    if valore == -1:
        desc_rifiuto = "Rifiuto <b>assoluto</b> — il giocatore passerà al vincitore qualunque siano gli anni."
    else:
        desc_rifiuto = f"Rifiuto <b>condizionale</b> — il giocatore passerà al vincitore se offre >{valore} ann{'o' if valore==1 else 'i'}."

    stato_pre = ""
    if pre:
        stato_pre = f"\n⚡ Pre-pareggio attivo: ≤{pre['anni']} ann{'o' if pre['anni']==1 else 'i'}"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✏️ Modifica rifiuto", callback_data=f"pre_rifiuto:{asta_id}"),
        InlineKeyboardButton("↩️ Annulla rifiuto", callback_data=f"pre_rifiuto_annulla:{asta_id}"),
    ]])

    await query.edit_message_text(
        f"❌ <b>Rifiuto pre-impostato per {asta['giocatore']}</b>\n\n"
        f"{desc_rifiuto}"
        f"{stato_pre}\n\n"
        f"<i>Puoi modificarlo o annullarlo finché il vincitore non sceglie gli anni.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def pre_rifiuto_annulla_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulla il rifiuto preimpostato."""
    query = update.callback_query
    await query.answer()

    asta_id = int(query.data.split(":")[1])
    asta = db.get_asta(asta_id)
    if not asta:
        await query.edit_message_text("❌ Asta non trovata.")
        return

    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop or query.from_user.id not in team_prop["gm_ids"]:
        await query.answer("⛔ Non sei il proprietario.", show_alert=True)
        return

    db.set_rifiuto_preimpostato(asta_id, 0)
    from registro import segna_asta
    await segna_asta(context.bot, query.from_user, "gm", "rifiuto preimpostato tolto", asta, dopo="tolto")

    pre = db.get_pareggio_preimpostato(asta_id)
    stato_pre = f"\n\n⚡ Pre-pareggio attivo: ≤{pre['anni']} ann{'o' if pre['anni']==1 else 'i'}" if pre else ""

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚡ Pre-imposta pareggio", callback_data=f"pre_par_anni:{asta_id}"),
        InlineKeyboardButton("❌ Pre-imposta rifiuto", callback_data=f"pre_rifiuto:{asta_id}"),
    ]])

    await query.edit_message_text(
        f"Rifiuto annullato per <b>{asta['giocatore']}</b>."
        f"{stato_pre}\n\n"
        f"<i>Puoi modificare le pre-impostazioni finché il vincitore non sceglie gli anni.</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def pre_rifiuto_indietro_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Torna al messaggio principale senza modificare nulla."""
    query = update.callback_query
    await query.answer()

    asta_id = int(query.data.split(":")[1])
    asta = db.get_asta(asta_id)
    if not asta:
        await query.edit_message_text("❌ Asta non trovata.")
        return

    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop or query.from_user.id not in team_prop["gm_ids"]:
        await query.answer("⛔ Non sei il proprietario.", show_alert=True)
        return

    pre     = db.get_pareggio_preimpostato(asta_id)
    rifiuto = db.get_rifiuto_preimpostato(asta_id)

    await query.edit_message_text(
        *_testo_stato_preimpostazioni(dict(asta), pre, rifiuto),
        parse_mode="HTML",
        reply_markup=_kb_preimpostazioni(asta_id, pre, rifiuto),
    )


# ── applicazione delle pre-impostazioni quando il vincitore sceglie gli anni ────

async def _esegui_pre_pareggio_se_compatibile(context, asta_id: int, anni_vincitore: int) -> bool:
    """
    Controlla se c'è un pre-pareggio impostato dal proprietario e se è compatibile
    con gli anni offerti dal vincitore. Se sì, esegue il pareggio automaticamente.
    Restituisce True se il pareggio è stato eseguito, False altrimenti.
    """
    # Controlla prima se c'è un rifiuto preimpostato
    rifiuto = db.get_rifiuto_preimpostato(asta_id)
    asta_r = db.get_asta(asta_id)
    team_vince_r = tm.get_team_by_id(asta_r["offerente_team_id"]) if asta_r else None
    team_vince_nome_r = team_vince_r["nome"] if team_vince_r else "altra franchigia"

    esegui_rifiuto = (rifiuto == -1) or (rifiuto > 0 and anni_vincitore > rifiuto)

    if esegui_rifiuto:
        logger.info("Rifiuto preimpostato (valore=%d): asta_id=%d anni_vincitore=%d — firma al vincitore",
                    rifiuto, asta_id, anni_vincitore)
        db.set_rifiuto_preimpostato(asta_id, 0)
        db.clear_pareggio_preimpostato(asta_id)
        asta = db.get_asta(asta_id)
        team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])

        if rifiuto == -1:
            motivo = "Hai pre-impostato il rifiuto assoluto."
        else:
            motivo = f"Hai pre-impostato il rifiuto per offerte >{rifiuto} ann{'o' if rifiuto==1 else 'i'} e il vincitore ha offerto {anni_vincitore}."

        if team_prop:
            for gm_id in team_prop["gm_ids"]:
                try:
                    await context.bot.send_message(
                        chat_id=gm_id,
                        text=(
                            f"❌ <b>Rifiuto eseguito automaticamente per {asta['giocatore']}</b>\n\n"
                            f"{motivo}\n"
                            f"Il giocatore passa a <b>{team_vince_nome_r}</b> con "
                            f"{asta['offerta_corrente']}M × {anni_vincitore} ann{'o' if anni_vincitore==1 else 'i'}."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    await _log_warn(context, f"Notifica rifiuto auto proprietario {gm_id}: {e}")

        await _registra_firma_finale(context, asta_id, anni_vincitore, asta["offerente_team_id"])
        return True

    pre = db.get_pareggio_preimpostato(asta_id)
    if not pre:
        return False

    importo_pre = pre["importo"]
    anni_pre    = pre["anni"]

    asta = db.get_asta(asta_id)
    vec_comp = asta["vecchio_compenso"] or 0
    sotto_soglia = asta["offerta_corrente"] < soglia_pareggio(vec_comp) and vec_comp > 20

    # Verifica che gli anni del pre-pareggio siano validi per questa fascia
    min_importo_par = importo_minimo_pareggio(asta["offerta_corrente"], vec_comp)
    min_anni_validi = 1 if sotto_soglia else anni_minimi(min_importo_par)
    if anni_pre < min_anni_validi:
        logger.warning(
            "Pre-pareggio anni %d non validi per fascia (min %d): asta_id=%d — annullato",
            anni_pre, min_anni_validi, asta_id
        )
        db.clear_pareggio_preimpostato(asta_id)
        return False

    # Se sopra soglia: anni vincitore deve essere <= anni pre-impostati
    # Se sotto soglia: gli anni sono liberi, il pre-pareggio scatta sempre
    if not sotto_soglia and anni_vincitore > anni_pre:
        logger.info("Pre-pareggio non compatibile: vincitore %d anni > pre %d anni", anni_vincitore, anni_pre)
        db.clear_pareggio_preimpostato(asta_id)
        return False
    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])

    logger.info("Pre-pareggio automatico: asta_id=%d importo=%d anni=%d", asta_id, importo_pre, anni_pre)
    db.clear_pareggio_preimpostato(asta_id)

    # Notifica il proprietario che il pareggio è scattato automaticamente
    if team_prop:
        for gm_id in team_prop["gm_ids"]:
            try:
                await context.bot.send_message(
                    chat_id=gm_id,
                    text=(
                        f"⚡ <b>Pre-pareggio eseguito automaticamente!</b>\n\n"
                        f"<b>{asta['giocatore']}</b>: hai pareggiato a <b>{importo_pre}M × {anni_pre} ann{'o' if anni_pre==1 else 'i'}</b>.\n"
                        f"Il vincitore aveva offerto {anni_vincitore} ann{'o' if anni_vincitore==1 else 'i'}."
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                await _log_warn(context, f"Notifica pre-pareggio auto proprietario {gm_id}: {e}")

    # Esegui il pareggio
    await _registra_firma_finale(context, asta_id, anni_pre, asta["squadra_proprietaria"], pareggiato=True)
    return True

"""
Firma, RFA: pareggio del proprietario (24h, sì/no, anni; allo scadere pareggio_automatico) e
RFA senza offerte (il proprietario firma o lascia andare). Callback pareggio*, firma_prop*, lascia:.
"""
import logging
from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import database as db
import teams as tm
import utils
import settings
from handlers.helpers import (
    aggiorna_canale as _aggiorna_canale, notifica_admin_group as _notifica_admin_group,
    log_warn as _log_warn,
)
from handlers.firma_comune import (
    anni_minimi, importo_minimo_pareggio, soglia_pareggio, _concludi_rfa_senza_contratto,
    _registra_firma_finale,
)

logger = logging.getLogger(__name__)


# ── fase pareggio RFA ─────────────────────────────────────────────────────────

async def _chiedi_pareggio(context, asta_id: int, anni_vincitore: int, schedula_job: bool = True):
    asta = db.get_asta(asta_id)
    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop:
        return

    importo     = asta["offerta_corrente"]
    vec_comp    = asta["vecchio_compenso"] or 0
    min_importo = importo_minimo_pareggio(importo, vec_comp)
    min_anni    = anni_vincitore

    team_vince = tm.get_team_by_id(asta["offerente_team_id"])
    team_vince_nome = team_vince["nome"] if team_vince else "altra franchigia"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Pareggio", callback_data=f"pareggio:{asta_id}:si"),
        InlineKeyboardButton("❌ Rinuncio", callback_data=f"pareggio:{asta_id}:no"),
    ]])

    nota_fascia = ""
    sotto_soglia = importo < soglia_pareggio(vec_comp)
    if vec_comp > 20 and sotto_soglia:
        fraz = "1/3" if vec_comp <= 34 else "1/2"
        nota_fascia = (
            f"\n\n⚠️ <i>L'offerta ricevuta ({importo}M) è inferiore a {fraz} del vecchio compenso "
            f"({vec_comp}M). Devi offrire almeno {min_importo}M, ma puoi scegliere gli anni liberamente.</i>"
        )

    testo = (
        f"⚖️ <b>Decisione RFA — {asta['giocatore']}</b>\n\n"
        f"<b>{team_vince_nome}</b> ha offerto: <b>{importo}M × {anni_vincitore} ann{'o' if anni_vincitore==1 else 'i'}</b>\n\n"
        f"Per pareggiare devi offrire:\n"
        f"  💰 Almeno <b>{min_importo}M</b>\n"
        + (f"  📅 Almeno <b>{min_anni} ann{'o' if min_anni==1 else 'i'}</b>" if not sotto_soglia else f"  📅 Anni a tua scelta (non vincolati)")
        + f"{nota_fascia}\n\n"
        f"Sei il proprietario dei diritti di <b>{asta['giocatore']}</b>.\n"
        f"Hai <b>24 ore</b> per decidere."
    )

    inviato = False
    for gm_id in team_prop["gm_ids"]:
        try:
            await context.bot.send_message(
                chat_id=gm_id, text=testo, parse_mode="HTML", reply_markup=kb
            )
            inviato = True
        except Exception as e:
            await _log_warn(context, f"Impossibile contattare GM pareggio {gm_id}: {e}")

    if not inviato:
        await _notifica_admin_group(
            context,
            f"⚠️ Impossibile contattare il proprietario RFA <b>{asta['giocatore']}</b> "
            f"(team: {team_prop['nome']}) per il pareggio. Intervenire manualmente."
        )

    if schedula_job:
        # Il timer parte da conclusa_at + timeout, non dall'ora corrente
        # Così rispetta le 24h dalle regole indipendentemente da quando il vincitore sceglie gli anni
        conclusa_at = datetime.fromisoformat(asta["conclusa_at"])
        scadenza = conclusa_at + timedelta(hours=settings.timeout_pareggio_ore())
        residuo = max(5, (scadenza - datetime.now(timezone.utc)).total_seconds())
        context.job_queue.run_once(
            pareggio_automatico,
            when=residuo,
            data={"asta_id": asta_id},
            name=f"pareggio_auto_{asta_id}",
        )
    logger.info("Fase pareggio avviata: asta_id=%d schedula=%s", asta_id, schedula_job)


async def pareggio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, asta_id_s, scelta = query.data.split(":")
    asta_id = int(asta_id_s)
    asta    = db.get_asta(asta_id)

    if not asta or asta["stato"] != "PAREGGIO":
        await query.edit_message_text("✅ Fase pareggio già conclusa.")
        return

    team = tm.get_team_by_gm(query.from_user.id)
    if not team or team["id"] != asta["squadra_proprietaria"]:
        await query.edit_message_text("⛔ Non sei il proprietario di questo RFA.")
        return

    for j in context.job_queue.get_jobs_by_name(f"pareggio_auto_{asta_id}"):
        j.schedule_removal()

    if scelta == "indietro":
        await _chiedi_pareggio(context, asta_id, asta["anni_offerti"], schedula_job=False)
        await query.delete_message()
        return

    if scelta == "no":
        # Chiede conferma prima di rinunciare
        team_vince = tm.get_team_by_id(asta["offerente_team_id"])
        team_vince_nome = team_vince["nome"] if team_vince else "altra franchigia"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confermo, rinuncio", callback_data=f"pareggio:{asta_id}:no_confermato"),
            InlineKeyboardButton("← Indietro", callback_data=f"pareggio:{asta_id}:indietro"),
        ]])
        await query.edit_message_text(
            f"❌ <b>Confermi di rinunciare al pareggio?</b>\n\n"
            f"<b>{asta['giocatore']}</b> passerà a <b>{team_vince_nome}</b> "
            f"con {asta['offerta_corrente']}M × {asta['anni_offerti']} ann{'o' if asta['anni_offerti']==1 else 'i'}.\n\n"
            f"<i>Questa azione è irreversibile.</i>",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    if scelta == "no_confermato":
        team_vince = tm.get_team_by_id(asta["offerente_team_id"])
        team_vince_nome = team_vince["nome"] if team_vince else "altra franchigia"
        await query.edit_message_text(
            f"❌ Hai rinunciato a pareggiare.\n"
            f"<b>{asta['giocatore']}</b> passa a <b>{team_vince_nome}</b> "
            f"a {asta['offerta_corrente']}M × {asta['anni_offerti']} ann{'o' if asta['anni_offerti']==1 else 'i'}.",
            parse_mode="HTML",
        )
        await _registra_firma_finale(
            context, asta_id, asta["anni_offerti"], asta["offerente_team_id"]
        )
    else:
        # pareggio: mostra anni disponibili
        importo     = asta["offerta_corrente"]
        vec_comp    = asta["vecchio_compenso"] or 0
        min_importo = importo_minimo_pareggio(importo, vec_comp)
        min_anni    = asta["anni_offerti"]
        sotto_soglia = importo < soglia_pareggio(vec_comp)

        if sotto_soglia:
            min_anni_btn = anni_minimi(min_importo)
            nota_anni = f"minimo {min_anni_btn} (offerta sotto soglia — anni liberi)"
        else:
            min_anni_btn = max(min_anni, anni_minimi(min_importo))
            nota_anni = f"minimo {min_anni_btn}"

        anni_btn = []
        for a in [1, 2, 3]:
            if a >= min_anni_btn:
                anni_btn.append(InlineKeyboardButton(
                    f"{a} ann{'o' if a==1 else 'i'}",
                    callback_data=f"pareggio_anni:{asta_id}:{a}"
                ))
        kb = InlineKeyboardMarkup([
            anni_btn,
            [InlineKeyboardButton("← Indietro", callback_data=f"pareggio:{asta_id}:indietro")],
        ])

        await query.edit_message_text(
            f"Stai pareggiando per <b>{asta['giocatore']}</b>.\n"
            f"Importo pareggio: <b>{min_importo}M</b>\n\n"
            f"Scegli gli anni ({nota_anni}):",
            parse_mode="HTML",
            reply_markup=kb,
        )


async def pareggio_anni_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query   # answer() una volta sola: sotto ci sono gli alert cap/slot

    _, asta_id_s, anni_s = query.data.split(":")
    asta_id = int(asta_id_s)
    anni    = int(anni_s)
    asta    = db.get_asta(asta_id)

    if not asta or asta["stato"] != "PAREGGIO":
        await query.answer()
        await query.edit_message_text("✅ Già conclusa.")
        return

    team = tm.get_team_by_gm(query.from_user.id)
    if not team or team["id"] != asta["squadra_proprietaria"]:
        await query.answer()
        await query.edit_message_text("⛔ Non sei il proprietario di questo RFA.")
        return

    vec_comp    = asta["vecchio_compenso"] or 0
    importo     = importo_minimo_pareggio(asta["offerta_corrente"], vec_comp)

    import pg_client
    from handlers.offerte import _cap_libero as _cap_lib_offerte
    cap_impegnato  = db.get_cap_virtuale(team["id"])
    slot_impegnati = db.get_slot_virtuali(team["id"])
    cap_libero     = _cap_lib_offerte(team["id"]) + vec_comp
    if pg_client.pg_disponibile():
        # slot totali senza l'RFA stesso (l'RFA non occupa slot finché l'asta è in corso):
        # rifirmarlo richiede uno slot libero
        stagione_s = utils.load_globals().get("stagione_corrente")
        slot_liberi = pg_client.get_slot_totale(team["id"], stagione=stagione_s) - slot_impegnati
    else:
        slot_liberi = tm.get_team_by_id(team["id"])["slot_disponibili"] - slot_impegnati

    if cap_libero < importo:
        await query.answer(
            f"❌ Cap insufficiente per pareggiare.\n"
            f"Importo pareggio: {importo}M\n"
            f"Cap effettivo (dopo liberazione vecchio contratto da {vec_comp}M): {cap_libero}M.\n"
            f"Riprova quando si libera cap.",
            show_alert=True,
        )
        return
    if slot_liberi <= 0:
        await query.answer(
            f"❌ Nessuno slot libero per pareggiare.\n"
            f"Slot virtuali già impegnati: {slot_impegnati}.\n"
            f"Riprova quando si libera uno slot.",
            show_alert=True,
        )
        return

    await query.answer()
    await query.edit_message_text(
        f"⚖️ <b>Confermi il pareggio?</b>\n\n"
        f"<b>{asta['giocatore']}</b> rimarrà con <b>{team['nome']}</b>\n"
        f"💰 <b>{importo}M × {anni} ann{'o' if anni==1 else 'i'}</b>\n\n"
        f"<i>Questa azione è irreversibile.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confermo il pareggio", callback_data=f"pareggio_confirm:{asta_id}:{anni}:{importo}"),
            InlineKeyboardButton("← Indietro", callback_data=f"pareggio:{asta_id}:indietro"),
        ]]),
    )


async def pareggio_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conferma definitiva del pareggio."""
    query = update.callback_query
    await query.answer()

    _, asta_id_s, anni_s, importo_s = query.data.split(":")
    asta_id = int(asta_id_s)
    anni    = int(anni_s)
    importo = int(importo_s)
    asta    = db.get_asta(asta_id)

    if not asta or asta["stato"] != "PAREGGIO":
        await query.edit_message_text("✅ Fase pareggio già conclusa.")
        return

    team = tm.get_team_by_gm(query.from_user.id)
    if not team or team["id"] != asta["squadra_proprietaria"]:
        await query.edit_message_text("⛔ Non sei il proprietario di questo RFA.")
        return

    await query.edit_message_text(
        f"✅ Pareggio confermato!\n"
        f"<b>{asta['giocatore']}</b> rimane con <b>{team['nome']}</b>\n"
        f"💰 {importo}M × {anni} ann{'o' if anni==1 else 'i'}",
        parse_mode="HTML",
    )
    await _registra_firma_finale(context, asta_id, anni, asta["squadra_proprietaria"], importo_override=importo, pareggiato=True)


async def pareggio_automatico(context: ContextTypes.DEFAULT_TYPE):
    try:
        asta_id = context.job.data["asta_id"]
        asta    = db.get_asta(asta_id)
        if not asta or asta["stato"] != "PAREGGIO":
            return
        logger.info("Pareggio automatico scaduto: asta_id=%d — passa al vincitore", asta_id)

        team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
        team_vince = tm.get_team_by_id(asta["offerente_team_id"])
        team_vince_nome = team_vince["nome"] if team_vince else "altra franchigia"

        if team_prop:
            for gm_id in team_prop["gm_ids"]:
                try:
                    await context.bot.send_message(
                        chat_id=gm_id,
                        text=(
                            f"⏰ Tempo scaduto per il pareggio.\n"
                            f"<b>{asta['giocatore']}</b> passa a <b>{team_vince_nome}</b> "
                            f"a {asta['offerta_corrente']}M × {asta['anni_offerti']} ann{'o' if asta['anni_offerti']==1 else 'i'}."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    await _log_warn(context, f"Notifica pareggio auto fallita GM {gm_id}: {e}")

        await _registra_firma_finale(
            context, asta_id, asta["anni_offerti"], asta["offerente_team_id"]
        )
    except Exception as e:
        from handlers.helpers import log_job_error
        await log_job_error(context, "pareggio_automatico", e)


# ── RFA senza offerte: proprietario può firmare ───────────────────────────────

async def _chiedi_firma_proprietario_senza_offerte(context, asta_id: int):
    asta = db.get_asta(asta_id)
    team_prop = tm.get_team_by_id(asta["squadra_proprietaria"])
    if not team_prop:
        return

    vec_comp = asta["vecchio_compenso"] or 0
    soglia   = soglia_pareggio(vec_comp)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Firmo", callback_data=f"firma_prop:{asta_id}"),
        InlineKeyboardButton("❌ Lascio andare", callback_data=f"lascia:{asta_id}"),
    ]])

    if vec_comp <= 20:
        nota = f"Puoi firmare a qualsiasi cifra (minimo 1M)."
    elif vec_comp <= 34:
        nota = f"Offerta minima: <b>{soglia}M</b> (1/3 del vecchio compenso di {vec_comp}M, approssimato per difetto)."
    else:
        nota = f"Offerta minima: <b>{soglia}M</b> (1/2 del vecchio compenso di {vec_comp}M, approssimato per difetto)."

    testo = (
        f"🏀 <b>{asta['giocatore']}</b> non ha ricevuto offerte.\n\n"
        f"Sei il proprietario dei diritti. Puoi firmarlo o lasciarlo andare in free agency.\n\n"
        f"{nota}"
    )

    inviato = False
    for gm_id in team_prop["gm_ids"]:
        try:
            await context.bot.send_message(
                chat_id=gm_id, text=testo, parse_mode="HTML", reply_markup=kb
            )
            inviato = True
        except Exception as e:
            await _log_warn(context, f"Impossibile contattare GM firma proprietario {gm_id}: {e}")

    if not inviato:
        await _notifica_admin_group(
            context,
            f"⚠️ Impossibile contattare il proprietario RFA <b>{asta['giocatore']}</b> "
            f"(team: {team_prop['nome']}) — nessuna offerta. Intervenire manualmente."
        )


async def firma_prop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    asta_id = int(query.data.split(":")[1])
    asta    = db.get_asta(asta_id)

    if not asta or asta["stato"] != "CHIUSA":
        await query.edit_message_text("✅ Già conclusa.")
        return

    team = tm.get_team_by_gm(query.from_user.id)
    if not team or team["id"] != asta["squadra_proprietaria"]:
        await query.edit_message_text("⛔ Non sei il proprietario.")
        return

    vec_comp    = asta["vecchio_compenso"] or 0
    min_importo = soglia_pareggio(vec_comp)

    anni_btn = []
    for a in [1, 2, 3]:
        if a >= anni_minimi(min_importo):
            anni_btn.append(InlineKeyboardButton(
                f"{a} ann{'o' if a==1 else 'i'}",
                callback_data=f"firma_prop_anni:{asta_id}:{a}"
            ))
    kb = InlineKeyboardMarkup([anni_btn])

    await query.edit_message_text(
        f"Firmi <b>{asta['giocatore']}</b> a <b>{min_importo}M</b>.\n"
        f"Scegli gli anni del contratto:",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def firma_prop_anni_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, asta_id_s, anni_s = query.data.split(":")
    asta_id = int(asta_id_s)
    anni    = int(anni_s)
    asta    = db.get_asta(asta_id)

    if not asta or asta["stato"] != "CHIUSA":
        await query.edit_message_text("✅ Già conclusa.")
        return

    team = tm.get_team_by_gm(query.from_user.id)
    if not team or team["id"] != asta["squadra_proprietaria"]:
        await query.edit_message_text("⛔ Non sei il proprietario.")
        return

    vec_comp = asta["vecchio_compenso"] or 0
    importo  = soglia_pareggio(vec_comp)

    import pg_client
    from handlers.offerte import _cap_libero as _cap_lib_offerte
    cap_impegnato  = db.get_cap_virtuale(team["id"])
    slot_impegnati = db.get_slot_virtuali(team["id"])
    cap_libero     = _cap_lib_offerte(team["id"]) + vec_comp
    if pg_client.pg_disponibile():
        # slot totali senza l'RFA stesso (l'RFA non occupa slot finché l'asta è in corso):
        # rifirmarlo richiede uno slot libero
        stagione_s = utils.load_globals().get("stagione_corrente")
        slot_liberi = pg_client.get_slot_totale(team["id"], stagione=stagione_s) - slot_impegnati
    else:
        slot_liberi = tm.get_team_by_id(team["id"])["slot_disponibili"] - slot_impegnati

    if cap_libero < importo:
        await query.edit_message_text(
            f"❌ Cap insufficiente per firmare.\n"
            f"Importo: <b>{importo}M</b>\n"
            f"Cap effettivo (dopo liberazione vecchio contratto da {vec_comp}M): <b>{cap_libero}M</b>.",
            parse_mode="HTML",
        )
        return
    if slot_liberi <= 0:
        await query.edit_message_text(
            f"❌ Nessuno slot libero. Slot virtuali impegnati: {slot_impegnati}.",
            parse_mode="HTML",
        )
        return

    await query.edit_message_text(
        f"✅ <b>{asta['giocatore']}</b> firmato con <b>{team['nome']}</b>\n"
        f"💰 {importo}M × {anni} ann{'o' if anni==1 else 'i'}",
        parse_mode="HTML",
    )
    await _registra_firma_finale(context, asta_id, anni, asta["squadra_proprietaria"], importo_override=importo, pareggiato=True)


async def lascia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    asta_id = int(query.data.split(":")[1])
    asta    = db.get_asta(asta_id)

    if not asta:
        await query.edit_message_text("❌ Asta non trovata.")
        return
    # Solo il proprietario, solo un RFA chiuso senza offerte ancora da decidere: prima
    # nessun controllo, e con due GM il secondo poteva "lasciar andare" un giocatore
    # appena rifirmato dal primo (contratto nuovo disattivato, asta annullata)
    team = tm.get_team_by_gm(query.from_user.id)
    if not team or team["id"] != asta["squadra_proprietaria"]:
        await query.edit_message_text("⛔ Non sei il proprietario.")
        return
    if asta["tipo"] != "RFA" or asta["stato"] != "CHIUSA" or asta["offerente_team_id"]:
        await query.edit_message_text("✅ Già conclusa.")
        return

    await _concludi_rfa_senza_contratto(context, asta_id)
    db.annulla_asta(asta_id)  # usa ANNULLATA per distinguere da CONCLUSA
    await _aggiorna_canale(context, asta_id)
    await query.edit_message_text(
        f"<b>{asta['giocatore']}</b> lasciato andare in free agency.\n"
        f"Il cap liberato ({asta['vecchio_compenso']}M) è stato restituito alla tua squadra.",
        parse_mode="HTML",
    )
    logger.info("RFA lasciato andare: asta_id=%d", asta_id)

"""
Flusso firma post-asta.

FA:
  - vincitore ha 48h per scegliere anni (dalla chiusura asta)
  - default automatico: 3 anni come penale

RFA:
  - vincitore ha 12h per scegliere anni (dalla chiusura asta)
  - default automatico: minimo per fascia (1 se <20, 2 se 20-34, 3 se >=35)
  - dopo che il vincitore sceglie gli anni → stato PAREGGIO
  - proprietario ha 24h per pareggiare (sì/no)
  - se no o timeout: giocatore passa al vincitore
  - se nessuna offerta: proprietario può firmare o lasciare andare

Principio di responsabilità singola:
  - _registra_firma_finale: gestisce SEMPRE la liberazione cap RFA + scala cap/slot + contratto
  - _concludi_rfa_senza_contratto: gestisce chiusura RFA senza firma (lascia andare, annullata senza offerte)
  - I chiamanti non devono mai chiamare libera_cap direttamente

Moduli (v3.13.0 / aste v63; prima stava tutto in questo file):
  firma.py                 scelta degli anni del vincitore (e del ruolo in regular season),
                           firma automatica allo scadere, registrazione dei bottoni
  firma_comune.py          soglie, validazione, _registra_firma_finale, _concludi_rfa_senza_contratto
  firma_preimpostazioni.py pre-impostazioni del proprietario di un RFA
  firma_pareggio.py        pareggio, RFA senza offerte, lascia andare
"""
import logging
from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import database as db
import teams as tm
import utils
import settings
from handlers.helpers import (
    aggiorna_canale as _aggiorna_canale, notifica_admin_group as _notifica_admin_group,
    log_warn as _log_warn,
)
from handlers.firma_comune import (
    anni_minimi, _info_ruolo, _registra_firma_finale, _ruoli_attivi, _valida_anni,
)
from handlers.firma_preimpostazioni import (
    pre_pareggio_anni_callback, pre_pareggio_annulla_callback, pre_pareggio_set_callback,
    pre_rifiuto_annulla_callback, pre_rifiuto_callback, pre_rifiuto_indietro_callback,
    pre_rifiuto_set_callback, _esegui_pre_pareggio_se_compatibile,
    _notifica_proprietario_chiusura_rfa,
)
from handlers.firma_pareggio import (
    firma_prop_anni_callback, firma_prop_callback, lascia_callback, pareggio_anni_callback,
    pareggio_callback, pareggio_confirm_callback, _chiedi_firma_proprietario_senza_offerte,
    _chiedi_pareggio,
)

logger = logging.getLogger(__name__)


# Per conto (v69, Luca 20/10): un admin sceglie anni (e ruolo) al posto del GM vincitore con
# /firma_per_conto. Stessi bottoni e stessi controlli, coi callback che cominciano con «pc_».
PC = "pc_"


def _p(pc: bool) -> str:
    return PC if pc else ""


def _per_conto(query) -> bool:
    return query.data.startswith(PC)


def _squadra_che_firma(query, asta) -> dict | None:
    """La squadra per cui si firma: quella del GM che preme (se è la vincitrice) o, per conto,
    la vincitrice se chi preme è admin. None = non può."""
    if _per_conto(query):
        from handlers.admin_comune import is_admin
        return tm.get_team_by_id(asta["offerente_team_id"]) if is_admin(query.from_user.id) else None
    team = tm.get_team_by_gm(query.from_user.id)
    return team if team and team["id"] == asta["offerente_team_id"] else None


_NON_PUOI = {False: "⛔ Non sei il GM vincitore di questa asta.", True: "⛔ Solo admin."}


def _kb_conferma(asta_id: int, anni: int, ruolo: str | None, pc: bool = False) -> InlineKeyboardMarkup:
    cb = f"{_p(pc)}firma_confirm:{asta_id}:{anni}" + (f":{ruolo}" if ruolo else "")
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma", callback_data=cb),
        InlineKeyboardButton("← Indietro", callback_data=f"{_p(pc)}firma_indietro:{asta_id}"),
    ]])


async def _mostra_scelta_ruolo(query, asta: dict, anni: int, team_id: str) -> bool:
    pc = _per_conto(query)
    """Dopo gli anni: scelta del ruolo. Ritorna False se il ruolo non va scelto
    (fuori RS / non FA): in quel caso il chiamante prosegue col flusso normale."""
    if not _ruoli_attivi(asta):
        return False
    info = _info_ruolo(asta, team_id)
    contratto = f"{asta['offerta_corrente']}M × {anni} ann{'o' if anni == 1 else 'i'}"
    if info["fisso"]:
        await query.edit_message_text(
            f"🏆 Confermi firma?\n\nGiocatore: <b>{asta['giocatore']}</b>\nContratto: <b>{contratto}</b>\n"
            f"Ruolo: <b>{info['fisso']}</b> <i>(regola dei 60 giorni: torna col vecchio ruolo)</i>",
            parse_mode="HTML", reply_markup=_kb_conferma(asta["id"], anni, info["fisso"], pc))
        return True
    if len(info["eleggibili"]) == 1:   # una sola posizione: niente scelta, solo conferma
        await query.edit_message_text(
            f"🏆 Confermi firma?\n\nGiocatore: <b>{asta['giocatore']}</b>\nContratto: <b>{contratto}</b>\n"
            f"Ruolo: <b>{info['eleggibili'][0]}</b> <i>(unica posizione eleggibile)</i>",
            parse_mode="HTML", reply_markup=_kb_conferma(asta["id"], anni, info["eleggibili"][0], pc))
        return True
    if not info["eleggibili"]:
        await query.edit_message_text(
            f"🏆 Confermi firma?\n\nGiocatore: <b>{asta['giocatore']}</b>\nContratto: <b>{contratto}</b>\n"
            f"Ruolo: <i>posizioni eleggibili non registrate, lo assegnerà un admin</i>",
            parse_mode="HTML", reply_markup=_kb_conferma(asta["id"], anni, None, pc))
        return True
    kb = [[InlineKeyboardButton(r, callback_data=f"{_p(pc)}firma_ruolo:{asta['id']}:{anni}:{r}") for r in info["validi"]],
          [InlineKeyboardButton("← Indietro", callback_data=f"{_p(pc)}firma_indietro:{asta['id']}")]]
    esclusi = [r for r in info["eleggibili"] if r not in info["validi"]]
    nota = (f"\n<i>{', '.join(esclusi)} non disponibile: il roster non rispetterebbe i minimi (4G/4F/2C).</i>"
            if esclusi else "")
    await query.edit_message_text(
        f"🎽 <b>{asta['giocatore']}</b> — {contratto}\n\nScegli il ruolo tra quelli eleggibili "
        f"({', '.join(info['eleggibili'])}):{nota}",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    return True


async def firma_ruolo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, asta_id_s, anni_s, ruolo = query.data.split(":")
    asta_id, anni = int(asta_id_s), int(anni_s)
    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] != "CHIUSA":
        await query.edit_message_text("✅ Firma già registrata o asta non in fase di firma.")
        return
    team = _squadra_che_firma(query, asta)
    if not team:
        await query.edit_message_text(_NON_PUOI[_per_conto(query)])
        return
    await query.edit_message_text(
        f"🏆 Confermi firma?\n\nGiocatore: <b>{asta['giocatore']}</b>\n"
        f"Contratto: <b>{asta['offerta_corrente']}M × {anni} ann{'o' if anni == 1 else 'i'}</b>\n"
        f"Ruolo: <b>{ruolo}</b>" + _riga_pc(query, team),
        parse_mode="HTML", reply_markup=_kb_conferma(asta_id, anni, ruolo, _per_conto(query)))


# ── notifica admin group ──────────────────────────────────────────────────────

# ── chiedi anni al vincitore ──────────────────────────────────────────────────

async def chiedi_anni(context: ContextTypes.DEFAULT_TYPE, asta_id: int, schedula_job: bool = True):
    asta = db.get_asta(asta_id)
    if not asta or not asta["offerente_team_id"]:
        if asta and asta["tipo"] == "RFA":
            await _chiedi_firma_proprietario_senza_offerte(context, asta_id)
        return

    team = tm.get_team_by_id(asta["offerente_team_id"])
    if not team:
        return

    importo = asta["offerta_corrente"]
    is_rfa  = asta["tipo"] == "RFA"
    ore     = settings.timeout_firma_rfa_ore() if is_rfa else settings.timeout_firma_fa_ore()

    # RFA con offerta ≥35M: anni obbligatori 3, niente scelta — pareggio parte subito
    if is_rfa and anni_minimi(importo) == 3:
        db.set_anni_offerti(asta_id, 3)
        # Notifica vincitore
        testo_vince = (
            f"🏆 <b>Hai vinto l'asta per {asta['giocatore']}!</b>\n\n"
            f"💰 Offerta: <b>{importo}M × 3 anni</b> (automatici — contratti ≥{settings.get()['soglia_anni_3']}M richiedono 3 anni obbligatori)\n\n"
            f"Il proprietario ha 24 ore dalla chiusura dell'asta per decidere se pareggiare."
        )
        for gm_id in team["gm_ids"]:
            try:
                await context.bot.send_message(chat_id=gm_id, text=testo_vince, parse_mode="HTML")
            except Exception as e:
                await _log_warn(context, f"Impossibile contattare GM vincitore {gm_id}: {e}")

        logger.info("chiedi_anni RFA ≥35M: anni automatici=3 asta_id=%d", asta_id)

        # Annuncio canale
        channel_id = utils.get_channel_id()
        team_prop_nome = tm.get_team_by_id(asta["squadra_proprietaria"])
        team_prop_nome = team_prop_nome["nome"] if team_prop_nome else "il proprietario"
        timeout_pareggio_h = settings.timeout_pareggio_ore()
        conclusa_at = datetime.fromisoformat(asta["conclusa_at"])
        scadenza_p = conclusa_at + timedelta(hours=timeout_pareggio_h)
        try:
            await context.bot.send_message(
                chat_id=channel_id,
                text=(
                    f"⚖️ <b>RFA {asta['giocatore']} — Asta conclusa</b>\n\n"
                    f"{team['nome']} ha offerto <b>{importo}M × 3 anni</b> (obbligatori).\n"
                    f"{team_prop_nome} ha tempo fino a <b>{utils.format_dt(scadenza_p.isoformat())}</b> per pareggiare."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            await _log_warn(context, f"Annuncio canale RFA ≥35M fallito: {e}")

        # Notifica proprietario e avvia pareggio — schedula_job gestito da _chiedi_pareggio
        await _notifica_proprietario_chiusura_rfa(context, asta_id)
        eseguito = await _esegui_pre_pareggio_se_compatibile(context, asta_id, 3)
        if not eseguito:
            await _chiedi_pareggio(context, asta_id, 3, schedula_job=schedula_job)
        return

    testo, kb = _anni_kb_e_testo(asta)

    inviato = False
    for gm_id in team["gm_ids"]:
        try:
            await context.bot.send_message(
                chat_id=gm_id, text=testo, parse_mode="HTML", reply_markup=kb
            )
            inviato = True
        except Exception as e:
            await _log_warn(context, f"Impossibile contattare GM {gm_id}: {e}")

    if not inviato:
        await _notifica_admin_group(
            context,
            f"⚠️ Impossibile contattare il GM vincitore di <b>{asta['giocatore']}</b> "
            f"(team: {team['nome']}) per la firma. Intervenire manualmente."
        )

    # Annuncio canale per RFA <35M
    if is_rfa and asta["squadra_proprietaria"]:
        channel_id = utils.get_channel_id()
        team_prop_c = tm.get_team_by_id(asta["squadra_proprietaria"])
        team_prop_nome_c = team_prop_c["nome"] if team_prop_c else "il proprietario"
        conclusa_at_c = datetime.fromisoformat(asta["conclusa_at"])
        scadenza_par = conclusa_at_c + timedelta(hours=settings.timeout_pareggio_ore())
        try:
            await context.bot.send_message(
                chat_id=channel_id,
                text=(
                    f"⚖️ <b>RFA {asta['giocatore']} — Asta conclusa</b>\n\n"
                    f"{team['nome']} ha offerto <b>{importo}M</b>.\n"
                    f"Il vincitore ha <b>{ore}h</b> per scegliere gli anni.\n"
                    f"{team_prop_nome_c} dovrà pareggiare entro <b>{utils.format_dt(scadenza_par.isoformat())}</b>."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            await _log_warn(context, f"Annuncio canale RFA <35M fallito: {e}")

    timeout_h = settings.timeout_firma_rfa_ore() if is_rfa else settings.timeout_firma_fa_ore()
    if schedula_job:
        context.job_queue.run_once(
            firma_automatica,
            when=timeout_h * 3600,
            data={"asta_id": asta_id},
            name=f"firma_auto_{asta_id}",
        )
    logger.info("chiedi_anni: asta_id=%d team=%s timeout=%dh schedula=%s", asta_id, team["id"], timeout_h, schedula_job)

    # Per le RFA: notifica il proprietario alla chiusura con importo e scadenza
    if is_rfa and asta["squadra_proprietaria"]:
        await _notifica_proprietario_chiusura_rfa(context, asta_id)


# ── callback scelta anni vincitore ────────────────────────────────────────────

def _riga_pc(query, team) -> str:
    return (f"\n\n🛠 <i>Per conto di <b>{team['nome']}</b>: firma da admin</i>" if _per_conto(query) and team else "")


def _anni_kb_e_testo(asta: dict, pc: bool = False) -> tuple:
    """Helper: costruisce keyboard e testo selezione anni, riutilizzato da chiedi_anni e firma_indietro_callback.
    pc: per conto (admin), stessi bottoni coi callback «pc_»."""
    importo = asta["offerta_corrente"]
    is_rfa  = asta["tipo"] == "RFA"
    ore     = settings.timeout_firma_rfa_ore() if is_rfa else settings.timeout_firma_fa_ore()
    bottoni = []
    for a in [1, 2, 3]:
        if a >= anni_minimi(importo):
            bottoni.append(InlineKeyboardButton(
                f"{a} ann{'o' if a==1 else 'i'}",
                callback_data=f"{_p(pc)}firma:{asta['id']}:{a}"
            ))
    kb = InlineKeyboardMarkup([bottoni])
    if pc:
        team = tm.get_team_by_id(asta["offerente_team_id"])
        scad = ""
        try:
            ore_s = settings.timeout_firma_rfa_ore() if asta["tipo"] == "RFA" else settings.timeout_firma_fa_ore()
            scad = utils.format_dt((datetime.fromisoformat(asta["conclusa_at"]) + timedelta(hours=ore_s)).isoformat())
        except Exception:
            pass
        s = settings.get()
        testo = (
            f"🛠 <b>Firma per conto di {team['nome'] if team else asta['offerente_team_id']}</b>\n\n"
            f"Asta {asta['tipo']} #{asta['id']}: <b>{asta['giocatore']}</b> a <b>{importo}M</b>\n"
            f"Scegli gli anni{', poi il ruolo' if _ruoli_attivi(asta) else ''} al posto del GM "
            f"<i>({s['soglia_anni_2']}–{s['fascia_media_max']}M → min 2 anni · {s['soglia_anni_3']}M+ → 3 anni obbligatori)</i>."
            + (f"\nScadenza per il GM: {scad}" if scad else "")
            + "\n\nSul canale esce l'annuncio di sempre; il GM viene avvisato."
        )
        return testo, kb
    s = settings.get()
    nota_anni = f"<i>({s['soglia_anni_2']}–{s['fascia_media_max']}M → min 2 anni · {s['soglia_anni_3']}M+ → 3 anni obbligatori)</i>"
    con_ruolo = _ruoli_attivi(asta)
    testo = (
        f"🏆 <b>Hai vinto l'asta per {asta['giocatore']}!</b>\n\n"
        f"💰 Offerta: <b>{importo}M</b>\n\n"
        f"Scegli per quanti anni firmare il contratto"
        f"{', poi il ruolo' if con_ruolo else ''}.\n{nota_anni}\n\n"
        f"⏰ Hai <b>{ore} ore</b> per rispondere.\n"
        f"Se non rispondi, {'gli anni minimi verranno assegnati automaticamente e il proprietario verrà avvisato' if is_rfa else 'il contratto sarà firmato automaticamente per 3 anni (penale)'}"
        f"{' e il ruolo verrà estratto a caso tra quelli eleggibili' if con_ruolo else ''}."
    )
    return testo, kb


async def firma_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, asta_id_s, anni_s = query.data.split(":")
    asta_id = int(asta_id_s)
    anni    = int(anni_s)

    asta = db.get_asta(asta_id)
    if not asta:
        await query.edit_message_text("❌ Asta non trovata.")
        return

    if asta["stato"] in ("PAREGGIO", "CONCLUSA", "ANNULLATA"):
        await query.edit_message_text("✅ Firma già registrata o asta annullata.")
        return

    if asta["stato"] != "CHIUSA":
        await query.edit_message_text("❌ L'asta non è in fase di firma.")
        return

    team = _squadra_che_firma(query, asta)
    if not team:
        await query.edit_message_text(_NON_PUOI[_per_conto(query)])
        return

    errore = _valida_anni(asta["offerta_corrente"], anni)
    if errore:
        await query.edit_message_text(f"❌ {errore}")
        return

    if await _mostra_scelta_ruolo(query, asta, anni, team["id"]):
        return

    # Chiedi conferma
    await query.edit_message_text(
        f"🏆 Confermi firma?\n\n"
        f"Giocatore: <b>{asta['giocatore']}</b>\n"
        f"Contratto: <b>{asta['offerta_corrente']}M × {anni} ann{'o' if anni==1 else 'i'}</b>" + _riga_pc(query, team),
        parse_mode="HTML",
        reply_markup=_kb_conferma(asta_id, anni, None, _per_conto(query)),
    )


async def firma_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parti   = query.data.split(":")
    asta_id = int(parti[1])
    anni    = int(parti[2])
    ruolo   = parti[3] if len(parti) > 3 else None

    asta = db.get_asta(asta_id)
    if not asta:
        await query.edit_message_text("❌ Asta non trovata.")
        return

    if asta["stato"] in ("PAREGGIO", "CONCLUSA", "ANNULLATA"):
        await query.edit_message_text("✅ Firma già registrata o asta annullata.")
        return

    if asta["stato"] != "CHIUSA":
        await query.edit_message_text("❌ L'asta non è in fase di firma.")
        return

    pc = _per_conto(query)
    team = _squadra_che_firma(query, asta)
    if not team:
        await query.edit_message_text(_NON_PUOI[pc])
        return

    errore = _valida_anni(asta["offerta_corrente"], anni)
    if errore:
        await query.edit_message_text(f"❌ {errore}")
        return

    for j in context.job_queue.get_jobs_by_name(f"firma_auto_{asta_id}"):
        j.schedule_removal()

    if asta["tipo"] == "FA":
        if _ruoli_attivi(asta):
            info = _info_ruolo(asta, team["id"])
            if ruolo is None and info["eleggibili"] and not info["fisso"]:
                # bottone di conferma senza ruolo (es. messaggio precedente): prima il ruolo
                await _mostra_scelta_ruolo(query, asta, anni, team["id"])
                return
            if info["fisso"]:
                ruolo = info["fisso"]
            elif ruolo is not None and ruolo not in info["validi"]:
                await query.edit_message_text("❌ Ruolo non più valido (eleggibilità o minimi del roster cambiati). Riprova.")
                await _mostra_scelta_ruolo(query, asta, anni, team["id"])
                return
        ruolo_finale = await _registra_firma_finale(context, asta_id, anni, team["id"], query=query, ruolo=ruolo,
                                                    per_conto=pc)
        await query.edit_message_text(
            f"✅ <b>{asta['giocatore']}</b> firmato: {asta['offerta_corrente']}M × {anni} ann{'o' if anni == 1 else 'i'}"
            + (f" — ruolo <b>{ruolo_finale}</b>" if ruolo_finale else "")
            + (f"\n🛠 Per conto di <b>{team['nome']}</b>: annuncio sul canale fatto, GM avvisato." if pc else ""),
            parse_mode="HTML")
        if pc:
            await _avvisa_gm_per_conto(context, team, query.from_user,
                                       f"<b>{asta['giocatore']}</b> firmato: <b>{asta['offerta_corrente']}M × {anni} "
                                       f"ann{'o' if anni == 1 else 'i'}</b>" + (f", ruolo <b>{ruolo_finale}</b>" if ruolo_finale else ""))
    else:
        db.set_anni_offerti(asta_id, anni)

        channel_id = utils.get_channel_id()
        try:
            conclusa_at_c = datetime.fromisoformat(asta["conclusa_at"])
            scadenza_par_c = conclusa_at_c + timedelta(hours=settings.timeout_pareggio_ore())
            now_c = datetime.now(timezone.utc)
            residuo_c = scadenza_par_c - now_c
            ore_r = int(residuo_c.total_seconds() // 3600)
            min_r = int((residuo_c.total_seconds() % 3600) // 60)
            await context.bot.send_message(
                chat_id=channel_id,
                text=(
                    f"📋 <b>RFA {asta['giocatore']}</b> — offerta completata\n\n"
                    f"{team['nome']} offre <b>{asta['offerta_corrente']}M × {anni} ann{'o' if anni==1 else 'i'}</b>.\n\n"
                    f"Il proprietario ha ancora <b>{ore_r}h {min_r}m</b> "
                    f"(fino a {utils.format_dt(scadenza_par_c.isoformat())}) per pareggiare."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            await _log_warn(context, f"Annuncio canale scelta anni RFA fallito: {e}")

        from registro import segna_asta
        await segna_asta(context.bot, query.from_user, "admin" if pc else "gm",
                         "anni RFA scelti" + (" per conto della squadra" if pc else ""), asta, team["id"],
                         prima=f"{asta['offerta_corrente']}M", dopo=f"{asta['offerta_corrente']}M × {anni}")
        if pc:
            await _avvisa_gm_per_conto(context, team, query.from_user,
                                       f"anni scelti per <b>{asta['giocatore']}</b>: <b>{asta['offerta_corrente']}M × {anni} "
                                       f"ann{'o' if anni == 1 else 'i'}</b>. Ora tocca al proprietario pareggiare")
        eseguito = await _esegui_pre_pareggio_se_compatibile(context, asta_id, anni)
        if not eseguito:
            await _chiedi_pareggio(context, asta_id, anni)
        await _aggiorna_canale(context, asta_id)
        msg_prop = "ricevuto il pareggio automatico." if eseguito else "24 ore per decidere se pareggiare l'offerta."
        await query.edit_message_text(
            f"✅ Anni registrati: <b>{anni}</b> per <b>{asta['giocatore']}</b> a <b>{asta['offerta_corrente']}M</b>.\n\n"
            f"Il proprietario dei diritti ha {msg_prop}",
            parse_mode="HTML",
        )


async def firma_indietro_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    asta_id = int(query.data.split(":")[1])
    asta = db.get_asta(asta_id)
    if not asta:
        await query.edit_message_text("❌ Asta non trovata.")
        return

    testo, kb = _anni_kb_e_testo(asta, _per_conto(query))
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)


# ── per conto: /firma_per_conto ─────────────────────────────────────────────────

async def _avvisa_gm_per_conto(context, team: dict, admin, cosa: str) -> None:
    from handlers.admin_comune import _admin_label
    for gm_id in team.get("gm_ids", []):
        try:
            await context.bot.send_message(chat_id=gm_id, parse_mode="HTML",
                                           text=f"🛠 L'admin {_admin_label(admin)} ha completato la firma per te: {cosa}.")
        except Exception as e:
            await _log_warn(context, f"Avviso firma per conto al GM {gm_id}: {e}")


def _in_attesa_di_anni() -> list:
    """Aste chiuse con un vincitore che deve ancora scegliere gli anni (FA, o RFA prima del pareggio)."""
    return [dict(a) for a in db.get_aste_chiuse() if a["offerente_team_id"]]


async def cmd_firma_per_conto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/firma_per_conto [asta_id] (admin): sceglie anni (e ruolo) al posto del GM vincitore. Senza
    id: le aste che aspettano la scelta degli anni, come bottoni."""
    from handlers.admin_comune import is_admin
    msg = update.effective_message
    if not is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Non sei autorizzato.")
        return
    if not context.args:
        aste = _in_attesa_di_anni()
        if not aste:
            await msg.reply_text("Nessuna asta in attesa della scelta degli anni.")
            return
        kb = [[InlineKeyboardButton(
            f"#{a['id']} {a['giocatore']} · {a['offerta_corrente']}M → "
            f"{(tm.get_team_by_id(a['offerente_team_id']) or {}).get('nome', a['offerente_team_id'])}"[:60],
            callback_data=f"{PC}firma_apri:{a['id']}")] for a in aste]
        await msg.reply_text("🛠 <b>Firma per conto</b> — aste che aspettano la scelta degli anni:",
                             parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return
    try:
        asta_id = int(context.args[0])
    except ValueError:
        await msg.reply_text("Uso: /firma_per_conto [asta_id]")
        return
    testo, kb = _testo_per_conto(asta_id)
    await msg.reply_text(testo, parse_mode="HTML", reply_markup=kb)


def _testo_per_conto(asta_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    asta = db.get_asta(asta_id)
    if not asta:
        return "❌ Asta non trovata.", None
    asta = dict(asta)
    if asta["stato"] != "CHIUSA" or not asta["offerente_team_id"]:
        return (f"❌ L'asta #{asta_id} ({asta['giocatore']}) è in stato <b>{asta['stato']}</b>: per conto si "
                "scelgono solo gli anni di un'asta chiusa con un vincitore (per il pareggio RFA c'è /force_esito)."), None
    if asta["tipo"] == "RFA" and anni_minimi(asta["offerta_corrente"]) == 3:
        return "❌ RFA da 35M in su: gli anni sono 3 d'ufficio, non c'è niente da scegliere.", None
    return _anni_kb_e_testo(asta, pc=True)


async def firma_apri_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.admin_comune import is_admin
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    await query.answer()
    testo, kb = _testo_per_conto(int(query.data.split(":")[1]))
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)


# ── firma automatica (timeout vincitore) ─────────────────────────────────────

async def firma_automatica(context: ContextTypes.DEFAULT_TYPE):
    try:
        asta_id = context.job.data["asta_id"]
        asta = db.get_asta(asta_id)
        if not asta or asta["stato"] not in ("CHIUSA",):
            return

        if asta["tipo"] == "FA":
            anni = 3
            logger.info("Firma automatica FA (penale 3 anni): asta_id=%d", asta_id)
            ruolo = await _registra_firma_finale(
                context, asta_id, anni, asta["offerente_team_id"],
                nota_tempo="il vincitore non ha scelto gli anni: 3 anni d'ufficio (penale)")
            team_auto = tm.get_team_by_id(asta["offerente_team_id"])
            for gm_id in (team_auto or {}).get("gm_ids", []):
                try:
                    await context.bot.send_message(
                        chat_id=gm_id, parse_mode="HTML",
                        text=(f"⚠️ Non hai risposto in tempo: <b>{asta['giocatore']}</b> firmato per "
                              f"<b>{asta['offerta_corrente']}M × 3 anni</b> (penale)"
                              + (f", ruolo <b>{ruolo}</b>." if ruolo else ".")))
                except Exception as e:
                    await _log_warn(context, f"Notifica firma automatica GM {gm_id}: {e}")
            return
        else:
            anni = anni_minimi(asta["offerta_corrente"])
            logger.info("Firma automatica RFA vincitore (anni minimi %d): asta_id=%d", anni, asta_id)
            db.set_anni_offerti(asta_id, anni, automatici=True)
            await _aggiorna_canale(context, asta_id)

            # Annuncio canale anni automatici
            channel_id = utils.get_channel_id()
            team_vince_auto = tm.get_team_by_id(asta["offerente_team_id"])
            team_vince_nome_auto = team_vince_auto["nome"] if team_vince_auto else "la franchigia vincitrice"
            try:
                conclusa_at_a = datetime.fromisoformat(asta["conclusa_at"])
                scadenza_par_a = conclusa_at_a + timedelta(hours=settings.timeout_pareggio_ore())
                now_a = datetime.now(timezone.utc)
                residuo_a = scadenza_par_a - now_a
                ore_a = int(residuo_a.total_seconds() // 3600)
                min_a = int((residuo_a.total_seconds() % 3600) // 60)
                await context.bot.send_message(
                    chat_id=channel_id,
                    text=(
                        f"📋 <b>RFA {asta['giocatore']}</b> — anni assegnati automaticamente\n\n"
                        f"{team_vince_nome_auto} offre <b>{asta['offerta_corrente']}M × {anni} ann{'o' if anni==1 else 'i'}</b> "
                        f"(minimi per fascia — nessuna risposta entro il termine).\n\n"
                        f"Il proprietario ha ancora <b>{ore_a}h {min_a}m</b> "
                        f"(fino a {utils.format_dt(scadenza_par_a.isoformat())}) per pareggiare."
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                await _log_warn(context, f"Annuncio canale anni auto RFA fallito: {e}")

            team = tm.get_team_by_id(asta["offerente_team_id"])
            if team:
                for gm_id in team["gm_ids"]:
                    try:
                        await context.bot.send_message(
                            chat_id=gm_id,
                            text=(
                                f"⚠️ Non hai risposto in tempo. Anni assegnati automaticamente: <b>{anni}</b> "
                                f"per <b>{asta['giocatore']}</b> a <b>{asta['offerta_corrente']}M</b>.\n\n"
                                f"Il proprietario dei diritti ha ora 24 ore per decidere se pareggiare."
                            ),
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        await _log_warn(context, f"Notifica auto vincitore RFA fallita GM {gm_id}: {e}")

        # Controlla se c'è un pre-pareggio compatibile, altrimenti chiede al proprietario
        eseguito = await _esegui_pre_pareggio_se_compatibile(context, asta_id, anni)
        if not eseguito:
            await _chiedi_pareggio(context, asta_id, anni)
    except Exception as e:
        from handlers.helpers import log_job_error
        await log_job_error(context, "firma_automatica", e)


# ── registrazione ───────────────────────────────────────────────────────────────

def get_handlers():
    return [
        CallbackQueryHandler(firma_callback,                pattern=r"^(pc_)?firma:\d+:\d+$"),
        CallbackQueryHandler(firma_confirm_callback,        pattern=r"^(pc_)?firma_confirm:\d+:\d+(:(PG|SG|SF|PF|C))?$"),
        CallbackQueryHandler(firma_ruolo_callback,          pattern=r"^(pc_)?firma_ruolo:\d+:\d+:(PG|SG|SF|PF|C)$"),
        CallbackQueryHandler(firma_indietro_callback,       pattern=r"^(pc_)?firma_indietro:\d+$"),
        CallbackQueryHandler(firma_apri_callback,           pattern=r"^pc_firma_apri:\d+$"),
        CallbackQueryHandler(pareggio_callback,             pattern=r"^pareggio:\d+:(si|no|no_confermato|indietro)$"),
        CallbackQueryHandler(pareggio_anni_callback,        pattern=r"^pareggio_anni:\d+:\d+$"),
        CallbackQueryHandler(pareggio_confirm_callback,     pattern=r"^pareggio_confirm:\d+:\d+:\d+$"),
        CallbackQueryHandler(firma_prop_callback,           pattern=r"^firma_prop:\d+$"),
        CallbackQueryHandler(firma_prop_anni_callback,      pattern=r"^firma_prop_anni:\d+:\d+$"),
        CallbackQueryHandler(lascia_callback,               pattern=r"^lascia:\d+$"),
        CallbackQueryHandler(pre_pareggio_anni_callback,    pattern=r"^pre_par_anni:\d+$"),
        CallbackQueryHandler(pre_pareggio_set_callback,     pattern=r"^pre_par_set:\d+:\d+$"),
        CallbackQueryHandler(pre_pareggio_annulla_callback, pattern=r"^pre_par_annulla:\d+$"),
        CallbackQueryHandler(pre_rifiuto_callback,          pattern=r"^pre_rifiuto:\d+$"),
        CallbackQueryHandler(pre_rifiuto_set_callback,      pattern=r"^pre_rifiuto_set:\d+:-?\d+$"),
        CallbackQueryHandler(pre_rifiuto_annulla_callback,  pattern=r"^pre_rifiuto_annulla:\d+$"),
        CallbackQueryHandler(pre_rifiuto_indietro_callback, pattern=r"^pre_rifiuto_indietro:\d+$"),
    ]

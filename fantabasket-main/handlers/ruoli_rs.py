"""
Ruoli in regular season — dichiarazioni post-trade / post-firma.

Fasi: settings.FASI_RUOLI_RS (regular-season-fa, regular-season-deadline, playoff).

- Quando una squadra riceve un giocatore (trade, attivazione diritti, /registra_firma)
  si apre una dichiarazione in sospeso (tabella ruoli_pendenti) con scadenza 48h.
- Il GM riceve in privato un messaggio per giocatore con un bottone per ogni ruolo
  eleggibile (con una sola posizione: solo conferma). Anche gli admin possono dichiarare.
- Una scelta che renderebbe impossibile rispettare i vincoli 4G/4F/2C viene rifiutata.
- Alla dichiarazione: evento cambi_ruolo (post_trade / post_firma), annuncio sul canale
  principale, sync dei roster sul foglio.
- Scaduta la 48h: estrazione casuale tra le eleggibili (preferendo quelle che lasciano
  rispettabili i vincoli), annuncio sul canale e messaggio al GM.
- Regola dei 60 giorni: se la squadra aveva il giocatore negli ultimi 60 giorni, il
  ruolo è il vecchio, assegnato subito senza scelta.
- Una sola posizione eleggibile: ruolo assegnato subito, senza dichiarazione (v3.6.0).
"""
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

import database as db
import settings
import teams as tm
from shared import ruoli_core as core

logger = logging.getLogger(__name__)

RUOLI = core.RUOLI
ORE_DICHIARAZIONE = 48
GIORNI_RIACQUISTO = core.GIORNI_RIACQUISTO
_TIPO_EVENTO = {"trade": "post_trade", "firma": "post_firma", "rookie": "post_firma"}
_ORIGINE_TXT = {"trade": "post-trade", "firma": "post-firma", "rookie": "attivazione diritti"}


# ══ dati ════════════════════════════════════════════════════════════════════

def _stagione() -> str:
    return settings.stagione_corrente()


def eleggibili(gid: int) -> list[str]:
    return core.eleggibili(db._q, gid)


def get_pendente(pid: int) -> dict | None:
    return db._q("""SELECT p.*, g.nome_common FROM ruoli_pendenti p
                    JOIN giocatori g ON g.id = p.giocatore_id WHERE p.id = %s""", (pid,), one=True)


def pendenti_aperti(team_id: str | None = None) -> list[dict]:
    filtro, params = ("AND p.team_id = %s", (team_id,)) if team_id else ("", ())
    return db._q(f"""SELECT p.*, g.nome_common FROM ruoli_pendenti p
                     JOIN giocatori g ON g.id = p.giocatore_id
                     WHERE p.stato = 'aperta' {filtro} ORDER BY p.scadenza""", params, many=True) or []


def _ruolo_riacquisto(gid: int, team_id: str) -> str | None:
    return core.ruolo_riacquisto(db._q, gid, team_id)


def _registra_ruolo(gid: int, team_id: str, ruolo: str, tipo: str) -> None:
    core.registra_ruolo(db._q, gid, team_id, ruolo, _stagione(), tipo)


def _chiudi(pid: int, stato: str, ruolo: str | None) -> None:
    db._q("UPDATE ruoli_pendenti SET stato = %s, ruolo = %s, chiuso = NOW() WHERE id = %s",
          (stato, ruolo, pid))


def _scelta_rispetta_vincoli(p: dict, ruolo: str) -> bool:
    """La scelta lascia possibile rispettare i vincoli? (o almeno non peggiora)"""
    return core.scelta_valida(db._q, p["team_id"], _stagione(), p["giocatore_id"], ruolo)


# ══ notifiche ═══════════════════════════════════════════════════════════════

def _nome_team(team_id: str) -> str:
    t = tm.get_team_by_id(team_id)
    return t["nome"] if t else team_id


async def _annuncia(bot, testo: str) -> None:
    ch = settings.load_globals().get("main_channel_id")
    if ch:
        try:
            await bot.send_message(chat_id=ch, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio ruolo sul canale: %s", e)


async def _ai_gm(bot, team_id: str, testo: str, kb=None) -> None:
    t = tm.get_team_by_id(team_id)
    for gm_id in (t or {}).get("gm_ids", []):
        try:
            await bot.send_message(chat_id=gm_id, text=testo, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning("Messaggio ruolo al GM %s: %s", gm_id, e)


def _sync_roster() -> None:
    try:
        import gas_client
        gas_client.sync_teams([t["id"] for t in tm.get_all_teams()])
    except Exception as e:
        logger.warning("GAS sync dopo ruolo RS: %s", e)


def _testo_e_tastiera(p: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    eleg = eleggibili(p["giocatore_id"])
    scad = p["scadenza"].astimezone(timezone.utc) if p["scadenza"].tzinfo else p["scadenza"]
    ore = max(0, int((scad - datetime.now(timezone.utc)).total_seconds() // 3600))
    testo = (f"🎽 <b>Ruolo da dichiarare</b> — {_nome_team(p['team_id'])}\n"
             f"<b>{p['nome_common']}</b> ({_ORIGINE_TXT.get(p['origine'], p['origine'])})\n"
             f"Tempo rimasto: ~{ore}h, poi il ruolo viene estratto a caso tra quelli eleggibili.")
    if not eleg:
        return testo + "\n\n⚠️ Posizioni eleggibili non registrate: contatta un admin.", None
    if len(eleg) == 1:
        kb = [[InlineKeyboardButton(f"✅ Conferma {eleg[0]}", callback_data=f"rp:{p['id']}:{eleg[0]}")]]
    else:
        kb = [[InlineKeyboardButton(r, callback_data=f"rp:{p['id']}:{r}") for r in eleg]]
    return testo, InlineKeyboardMarkup(kb)


# ══ apertura (chiamata da trade, firme, attivazione diritti) ═════════════════

async def apri_pendenti(bot, team_id: str, gids: list[int], origine: str, riferimento: str | None = None) -> None:
    if settings.fase() not in settings.FASI_RUOLI_RS or not gids:
        return
    tipo = _TIPO_EVENTO.get(origine, "post_trade")
    for gid in gids:
        try:
            # eventuali dichiarazioni aperte dello stesso giocatore con un'altra squadra decadono
            db._q("UPDATE ruoli_pendenti SET stato = 'annullata', chiuso = NOW() "
                  "WHERE giocatore_id = %s AND stato = 'aperta'", (gid,))
            nome = (db.get_giocatore(gid) or {}).get("nome_common", str(gid))
            vecchio = _ruolo_riacquisto(gid, team_id)
            if vecchio:
                _registra_ruolo(gid, team_id, vecchio, tipo)
                await _annuncia(bot, f"🎽 <b>{_nome_team(team_id)}</b>: {nome} → <b>{vecchio}</b>\n"
                                     f"<i>Regola dei {GIORNI_RIACQUISTO} giorni: torna col vecchio ruolo.</i>")
                await _ai_gm(bot, team_id, f"🎽 {nome} torna nel suo vecchio ruolo <b>{vecchio}</b> "
                                           f"(regola dei {GIORNI_RIACQUISTO} giorni), non serve dichiararlo.")
                continue
            eleg = eleggibili(gid)
            if len(eleg) == 1:   # una sola posizione eleggibile: niente da scegliere
                _registra_ruolo(gid, team_id, eleg[0], tipo)
                await _annuncia(bot, f"🎽 <b>{_nome_team(team_id)}</b>: {nome} → <b>{eleg[0]}</b>\n"
                                     f"<i>Unica posizione eleggibile.</i>")
                await _ai_gm(bot, team_id, f"🎽 {nome}: ruolo <b>{eleg[0]}</b> assegnato in automatico "
                                           f"(unica posizione eleggibile), non serve dichiararlo.")
                continue
            pid = db._qval("""INSERT INTO ruoli_pendenti (giocatore_id, team_id, origine, riferimento, scadenza)
                              VALUES (%s, %s, %s, %s, NOW() + (%s || ' hours')::interval) RETURNING id""",
                           (gid, team_id, origine, riferimento, str(ORE_DICHIARAZIONE)))
            testo, kb = _testo_e_tastiera(get_pendente(pid))
            await _ai_gm(bot, team_id, testo, kb)
        except Exception as e:
            logger.warning("apri_pendenti %s/%s: %s", team_id, gid, e)
    _sync_roster()


# ══ callback ════════════════════════════════════════════════════════════════

def _is_admin(user_id: int) -> bool:
    return user_id in [int(a) for a in settings.admin_ids()]


async def cb_dichiara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, pid, ruolo = query.data.split(":")
    p = get_pendente(int(pid))
    uid = query.from_user.id
    gm_team = tm.get_team_by_gm(uid)
    admin = _is_admin(uid)
    if not p or (not admin and (not gm_team or gm_team["id"] != p["team_id"])):
        await query.answer("⛔ Non puoi dichiarare questo ruolo.", show_alert=True)
        return
    if p["stato"] != "aperta":
        await query.answer("Questa dichiarazione è già chiusa.", show_alert=True)
        await query.edit_message_text(f"🎽 {p['nome_common']}: dichiarazione già chiusa"
                                      + (f" ({p['ruolo']})." if p["ruolo"] else "."))
        return
    if not db._q("SELECT 1 FROM roster_attuale WHERE giocatore_id = %s AND team_id = %s",
                 (p["giocatore_id"], p["team_id"]), one=True):
        _chiudi(p["id"], "annullata", None)
        await query.answer("Il giocatore non è più in questa squadra.", show_alert=True)
        await query.edit_message_text(f"🎽 {p['nome_common']}: non è più in squadra, dichiarazione annullata.")
        return
    if ruolo not in eleggibili(p["giocatore_id"]):
        await query.answer("Ruolo non eleggibile.", show_alert=True)
        return
    if not _scelta_rispetta_vincoli(p, ruolo):
        await query.answer("❌ Con questo ruolo il roster non può più rispettare i minimi "
                           "(4 G, 4 F, 2 C). Scegli un altro ruolo.", show_alert=True)
        return
    await query.answer()
    _registra_ruolo(p["giocatore_id"], p["team_id"], ruolo, _TIPO_EVENTO.get(p["origine"], "post_trade"))
    _chiudi(p["id"], "dichiarata", ruolo)
    chi = " (da admin)" if admin and (not gm_team or gm_team["id"] != p["team_id"]) else ""
    await query.edit_message_text(f"✅ <b>{p['nome_common']}</b>: ruolo <b>{ruolo}</b> ufficiale{chi}.",
                                  parse_mode="HTML")
    await _annuncia(context.bot, f"🎽 <b>{_nome_team(p['team_id'])}</b>: {p['nome_common']} → <b>{ruolo}</b>"
                                 f" <i>({_ORIGINE_TXT.get(p['origine'], p['origine'])}{chi})</i>")
    _sync_roster()


async def cb_lista_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dal /menu: rimanda le tastiere delle dichiarazioni aperte della propria squadra."""
    query = update.callback_query
    t = tm.get_team_by_gm(query.from_user.id)
    aperte = pendenti_aperti(t["id"]) if t else []
    await query.answer()
    if not aperte:
        await query.edit_message_text("Nessun ruolo da dichiarare. ✅")
        return
    await query.edit_message_text(f"🎽 Hai <b>{len(aperte)}</b> ruoli da dichiarare:", parse_mode="HTML")
    for p in aperte:
        testo, kb = _testo_e_tastiera(p)
        await query.message.reply_text(testo, parse_mode="HTML", reply_markup=kb)


async def cb_lista_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    aperte = pendenti_aperti()
    await query.answer()
    if not aperte:
        await query.edit_message_text("Nessuna dichiarazione di ruolo in sospeso. ✅",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Menu admin", callback_data="adm:home")]]))
        return
    await query.edit_message_text(f"⏳ <b>{len(aperte)}</b> dichiarazioni in sospeso — puoi dichiarare al posto del GM:",
                                  parse_mode="HTML")
    for p in aperte:
        testo, kb = _testo_e_tastiera(p)
        await query.message.reply_text(testo, parse_mode="HTML", reply_markup=kb)


# ══ job: scadenze ═══════════════════════════════════════════════════════════

async def job_scadenze(context: ContextTypes.DEFAULT_TYPE):
    """Ogni 15 minuti: estrazione casuale per le dichiarazioni scadute."""
    try:
        scadute = db._q("""SELECT p.*, g.nome_common FROM ruoli_pendenti p
                           JOIN giocatori g ON g.id = p.giocatore_id
                           WHERE p.stato = 'aperta' AND p.scadenza <= NOW()""", many=True) or []
        cambiato = False
        for p in scadute:
            a_roster = db._q("""SELECT 1 FROM roster_attuale WHERE giocatore_id = %s AND team_id = %s""",
                             (p["giocatore_id"], p["team_id"]), one=True)
            if not a_roster:
                _chiudi(p["id"], "annullata", None)
                continue
            eleg = eleggibili(p["giocatore_id"])
            if not eleg:
                _chiudi(p["id"], "senza_posizioni", None)
                gruppo = settings.load_globals().get("admin_group_id")
                if gruppo:
                    await context.bot.send_message(
                        chat_id=gruppo, parse_mode="HTML",
                        text=f"⚠️ Ruolo di <b>{p['nome_common']}</b> ({_nome_team(p['team_id'])}) non estraibile: "
                             f"posizioni eleggibili mancanti. Impostale con /set_posizioni_eleggibili e assegna il ruolo.")
                continue
            ruolo = core.estrai_ruolo(db._q, p["team_id"], _stagione(), p["giocatore_id"])
            _registra_ruolo(p["giocatore_id"], p["team_id"], ruolo, _TIPO_EVENTO.get(p["origine"], "post_trade"))
            _chiudi(p["id"], "estratta", ruolo)
            cambiato = True
            await _annuncia(context.bot, f"🎲 <b>{_nome_team(p['team_id'])}</b>: {p['nome_common']} → <b>{ruolo}</b>\n"
                                         f"<i>Ruolo non dichiarato entro {ORE_DICHIARAZIONE}h: estratto tra {', '.join(eleg)}.</i>")
            await _ai_gm(context.bot, p["team_id"],
                         f"🎲 Non hai dichiarato il ruolo di <b>{p['nome_common']}</b> entro {ORE_DICHIARAZIONE}h: "
                         f"estratto <b>{ruolo}</b>.")
        if cambiato:
            _sync_roster()
    except Exception as e:
        logger.warning("job_scadenze ruoli RS: %s", e)


def get_handlers() -> list:
    return [
        CallbackQueryHandler(cb_dichiara,     pattern=r"^rp:\d+:(PG|SG|SF|PF|C)$"),
        CallbackQueryHandler(cb_lista_team,   pattern=r"^rp:list$"),
        CallbackQueryHandler(cb_lista_admin,  pattern=r"^rpadm:list$"),
    ]

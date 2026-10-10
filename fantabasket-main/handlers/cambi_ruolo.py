"""
Cambi ruolo in regular season (fasi settings.FASI_RUOLI_RS).

GM:    /cambio_ruolo o "🔁 Cambio ruolo" nel /menu (callback cr:) — solo la propria squadra,
       anche per chi è admin: qui niente cambio forzato e la Saedro è sempre una richiesta
Admin: /admin_menu → "🔁 Cambi ruolo" → squadra (callback ca:) — per conto di qualsiasi
       squadra, con cambio forzato e Saedro diretta
Tutto solo nelle fasi FASI_RUOLI_RS (in offseason i ruoli si dichiarano da capo).

Tipi (eventi cambi_ruolo):
- ordinario      → max 2 a stagione per squadra (contatore su /roster e foglio)
- erminio        → gratuito, verso una posizione aggiunta da Yahoo negli ultimi 14 giorni
                   (data Yahoo se inserita con /data_erminio, altrimenti data di rilevazione)
- saedro         → temporaneo 10 giorni, una volta a stagione; il GM lo RICHIEDE
                   (approvazione nel gruppo admin con l'elenco dei giocatori in quel ruolo),
                   l'admin può applicarlo direttamente. Ritorno automatico al ruolo originale.
- forzato_admin  → solo admin, non conta nel contatore
Vincoli 4G/4F/2C: bloccanti (passano i cambi che non peggiorano); per i cambi forzati
dagli admin solo avviso. Annunci sul canale principale, sync roster di tutte le squadre.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

import database as db
import settings
import teams as tm
from settings import solo_privato
from validators.ruoli import deficit_team
from shared import ruoli_core as core

logger = logging.getLogger(__name__)

RUOLI = core.RUOLI
MAX_ORDINARI = 2
GIORNI_ERMINIO = 14
GIORNI_SAEDRO = 10
TIPI = {"o": "ordinario", "e": "erminio", "s": "saedro", "f": "forzato_admin", "d": "dpe_extra"}
ETICHETTE = {"ordinario": "cambio ordinario", "erminio": "Erminio (ruolo aggiunto)",
             "saedro": "Saedro (10 day)", "forzato_admin": "forzato dagli admin",
             "dpe_extra": "extra DPE post-deadline"}


# ══ dati ════════════════════════════════════════════════════════════════════

def _stagione() -> str:
    return settings.stagione_corrente()


def _is_admin(uid: int) -> bool:
    return uid in [int(a) for a in settings.admin_ids()]


def _nome_team(team_id: str) -> str:
    t = tm.get_team_by_id(team_id)
    return t["nome"] if t else team_id


def ordinari_usati(team_id: str, stagione: str | None = None) -> int:
    return db._qval("SELECT count(*) FROM cambi_ruolo WHERE team_id = %s AND stagione = %s AND tipo = 'ordinario'",
                    (team_id, stagione or _stagione())) or 0


def saedro_usata(team_id: str) -> bool:
    return bool(db._qval("SELECT count(*) FROM cambi_ruolo WHERE team_id = %s AND stagione = %s "
                         "AND tipo = 'saedro' AND scadenza IS NOT NULL", (team_id, _stagione())))


def dpe_extra(team_id: str) -> tuple[int, set[str]]:
    """Regolamento: una DPE attivata dopo la deadline dà un cambio ruolo aggiuntivo
    verso il ruolo del giocatore infortunato. (cambi rimasti, ruoli possibili)."""
    gids = [r["giocatore_id"] for r in db._q(
        "SELECT giocatore_id FROM dpe WHERE team_id = %s AND stagione = %s AND pre_deadline = FALSE",
        (team_id, _stagione()), many=True) or []]
    if not gids:
        return 0, set()
    usati = db._qval("SELECT count(*) FROM cambi_ruolo WHERE team_id = %s AND stagione = %s AND tipo = 'dpe_extra'",
                     (team_id, _stagione())) or 0
    ruoli = {r["ruolo"] for r in db._q(
        "SELECT ruolo FROM ruolo_attuale WHERE stagione = %s AND giocatore_id = ANY(%s)",
        (_stagione(), gids), many=True) or [] if r["ruolo"]}
    return max(0, len(gids) - usati), ruoli


def roster_ruoli(team_id: str) -> list[dict]:
    roster = db.get_roster_team(team_id) or []
    uff = {r["giocatore_id"]: r for r in db._q(
        "SELECT giocatore_id, ruolo, tipo, scadenza FROM ruolo_attuale WHERE stagione = %s AND team_id = %s",
        (_stagione(), team_id), many=True) or []}
    out = []
    for r in roster:
        u = uff.get(r["giocatore_id"]) or {}
        saedro_attiva = (u.get("tipo") == "saedro" and u.get("scadenza") is not None
                         and u["scadenza"] > datetime.now(timezone.utc))
        out.append({"gid": r["giocatore_id"], "nome": r["nome_common"], "ruolo": u.get("ruolo"),
                    "saedro_attiva": saedro_attiva, "scadenza": u.get("scadenza")})
    ordine = {p: i for i, p in enumerate(RUOLI)}
    return sorted(out, key=lambda x: (ordine.get(x["ruolo"], 9), x["nome"]))


def eleggibili(gid: int) -> list[str]:
    return core.eleggibili(db._q, gid)


def ruoli_erminio(gid: int) -> set[str]:
    """Posizioni aggiunte nell'ultimo aggiornamento, se entro 14 giorni dalla data Yahoo
    (o, se non inserita, dalla data di rilevazione)."""
    righe = db._q("""SELECT posizioni, timestamp, data_yahoo FROM posizioni_eleggibili
                     WHERE giocatore_id = %s ORDER BY timestamp DESC, id DESC LIMIT 2""",
                  (gid,), many=True) or []
    if len(righe) < 2:
        return set()
    nuove, vecchie = set(righe[0]["posizioni"].split(",")), set(righe[1]["posizioni"].split(","))
    giorno = righe[0]["data_yahoo"] or righe[0]["timestamp"].date()
    if (date.today() - giorno).days > GIORNI_ERMINIO:
        return set()
    return (nuove - vecchie) & set(RUOLI)


# ══ controlli e applicazione ════════════════════════════════════════════════

def verifica(team_id: str, gid: int, nuovo: str, tipo: str, admin: bool) -> tuple[list[str], list[str]]:
    """(errori bloccanti, avvisi)."""
    errori, avvisi = [], []
    g = next((x for x in roster_ruoli(team_id) if x["gid"] == gid), None)
    if not g:
        return ["Il giocatore non è nel roster della squadra."], []
    if not g["ruolo"]:
        return ["Il giocatore non ha ancora un ruolo ufficiale: va prima dichiarato."], []
    if g["saedro_attiva"] and tipo != "forzato_admin":
        errori.append("Il giocatore ha una Saedro in corso.")
    if nuovo == g["ruolo"]:
        errori.append(f"È già {nuovo}.")
    if nuovo not in eleggibili(gid):
        errori.append(f"{nuovo} non è tra le posizioni eleggibili.")
    if tipo == "ordinario" and nuovo in ruoli_erminio(gid):
        errori.append("Per questo ruolo è disponibile l'Erminio (gratuito): usa quello.")
    if tipo == "ordinario" and ordinari_usati(team_id) >= MAX_ORDINARI:
        errori.append(f"Cambi ordinari esauriti ({MAX_ORDINARI}/{MAX_ORDINARI}).")
    if tipo == "erminio" and nuovo not in ruoli_erminio(gid):
        errori.append(f"Erminio non applicabile: {nuovo} non è una posizione aggiunta negli ultimi {GIORNI_ERMINIO} giorni.")
    if tipo == "saedro" and saedro_usata(team_id):
        errori.append("Saedro già usata in questa stagione.")
    if tipo == "forzato_admin" and not admin:
        errori.append("Solo gli admin possono forzare un cambio.")
    if tipo == "dpe_extra":
        rimasti, ruoli_dpe = dpe_extra(team_id)
        if rimasti <= 0:
            errori.append("Nessun cambio extra DPE disponibile.")
        elif nuovo not in ruoli_dpe:
            errori.append(f"Il cambio extra DPE va verso il ruolo dell'infortunato ({', '.join(sorted(ruoli_dpe)) or '?'}).")
    prima = deficit_team(team_id, _stagione())
    dopo = deficit_team(team_id, _stagione(), imposti={gid: nuovo})
    if dopo > 0 and dopo > prima:
        msg = "Con questo cambio il roster non rispetta più i minimi (4 G, 4 F, 2 C)."
        (avvisi if tipo == "forzato_admin" else errori).append(msg)
    return errori, avvisi


def applica(team_id: str, gid: int, nuovo: str, tipo: str) -> str:
    g = next(x for x in roster_ruoli(team_id) if x["gid"] == gid)
    scadenza = datetime.now(timezone.utc) + timedelta(days=GIORNI_SAEDRO) if tipo == "saedro" else None
    db._q("""INSERT INTO cambi_ruolo (giocatore_id, team_id, ruolo_da, ruolo_a, stagione, tipo, scadenza, ruolo_ripristino)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
          (gid, team_id, g["ruolo"], nuovo, _stagione(), tipo, scadenza,
           g["ruolo"] if tipo == "saedro" else None))
    return g["ruolo"]


async def _annuncia(bot, testo: str):
    ch = settings.load_globals().get("main_channel_id")
    if ch:
        try:
            await bot.send_message(chat_id=ch, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio cambio ruolo: %s", e)


async def _ai_gm(bot, team_id: str, testo: str):
    for gm_id in (tm.get_team_by_id(team_id) or {}).get("gm_ids", []):
        try:
            await bot.send_message(chat_id=gm_id, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Messaggio cambio ruolo al GM %s: %s", gm_id, e)


def _sync():
    try:
        import gas_client
        gas_client.sync_teams([t["id"] for t in tm.get_all_teams()])
    except Exception as e:
        logger.warning("GAS sync dopo cambio ruolo: %s", e)


async def _esegui(bot, team_id: str, gid: int, nuovo: str, tipo: str, chi: str) -> str:
    vecchio = applica(team_id, gid, nuovo, tipo)
    nome = (db.get_giocatore(gid) or {}).get("nome_common", str(gid))
    extra = ""
    if tipo == "ordinario":
        extra = f" — cambi usati {ordinari_usati(team_id)}/{MAX_ORDINARI}"
    elif tipo == "saedro":
        fine = (datetime.now(timezone.utc) + timedelta(days=GIORNI_SAEDRO)).strftime("%d/%m")
        extra = f" — fino al {fine}, poi torna {vecchio}"
    await _annuncia(bot, f"🔁 <b>{_nome_team(team_id)}</b>: {nome} {vecchio} → <b>{nuovo}</b>\n"
                         f"<i>{ETICHETTE[tipo]}{extra}{chi}</i>")
    _sync()
    return f"✅ {nome}: {vecchio} → <b>{nuovo}</b> ({ETICHETTE[tipo]}{extra})"


# ══ interfaccia ═════════════════════════════════════════════════════════════
# Due modalità, distinte dal prefisso del callback:
#   cr: → GM sulla propria squadra (anche se è admin): niente "forzato", Saedro su richiesta
#   ca: → admin per conto di una squadra (da /admin_menu): forzato disponibile, Saedro diretta
# In entrambe solo nelle fasi di regular season/playoff: in offseason i ruoli si dichiarano da capo.

FUORI_FASE = "❌ I cambi ruolo sono disponibili solo in regular season e playoff."


def _accesso(uid: int, team_id: str, admin_mode: bool) -> str | None:
    if settings.fase() not in settings.FASI_RUOLI_RS:
        return FUORI_FASE
    if admin_mode:
        return None if _is_admin(uid) else "⛔ Solo admin."
    t = tm.get_team_by_gm(uid)
    if not t or t["id"] != team_id:
        return "⛔ Puoi cambiare solo i ruoli della tua squadra."
    return None


def _vista_team(team_id: str, admin: bool):
    p = "ca" if admin else "cr"
    usati = ordinari_usati(team_id)
    testo = (f"🔁 <b>Cambio ruolo — {_nome_team(team_id)}</b>" + (" <i>(admin)</i>" if admin else "") +
             f"\nCambi ordinari usati: <b>{usati}/{MAX_ORDINARI}</b> · Saedro: "
             f"{'usata' if saedro_usata(team_id) else 'disponibile'}")
    rimasti_dpe, ruoli_dpe = dpe_extra(team_id)
    if rimasti_dpe:
        testo += f"\n🏥 Extra DPE: <b>{rimasti_dpe}</b> verso {', '.join(sorted(ruoli_dpe)) or '?'}"
    testo += "\n\nScegli il giocatore:"
    kb = []
    for g in roster_ruoli(team_id):
        if not g["ruolo"]:
            label = f"❔ {g['nome']} (da dichiarare)"
        elif g["saedro_attiva"]:
            label = f"⏳ {g['ruolo']} · {g['nome']} (Saedro)"
        else:
            label = f"{g['ruolo']} · {g['nome']}"
        kb.append([InlineKeyboardButton(label, callback_data=f"{p}:g:{team_id}:{g['gid']}")])
    kb.append([InlineKeyboardButton("← Squadre", callback_data="cradm:teams") if admin
               else InlineKeyboardButton("✖️ Chiudi", callback_data="cr:close")])
    return testo, InlineKeyboardMarkup(kb)


@solo_privato
async def cmd_cambio_ruolo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    t = tm.get_team_by_gm(uid)
    if not t:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    motivo = _accesso(uid, t["id"], admin_mode=False)
    if motivo:
        await update.effective_message.reply_text(motivo)
        return
    testo, kb = _vista_team(t["id"], admin=False)
    await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=kb)


async def cb_cambio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    parti = query.data.split(":")
    if parti[1] == "close":
        await query.answer()
        await query.edit_message_text("Chiuso.")
        return
    if parti[1] == "home":
        t = tm.get_team_by_gm(uid)
        if not t:
            await query.answer("⛔ Non sei registrato come GM.", show_alert=True)
            return
        parti = ["cr", "t", t["id"]]
    p = parti[0]
    admin_mode = p == "ca"
    azione, team_id = parti[1], parti[2]
    motivo = _accesso(uid, team_id, admin_mode)
    if motivo:
        await query.answer(motivo, show_alert=True)
        return
    await query.answer()

    if azione == "t":
        testo, kb = _vista_team(team_id, admin_mode)
        await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)

    elif azione == "g":
        gid = int(parti[3])
        g = next((x for x in roster_ruoli(team_id) if x["gid"] == gid), None)
        indietro = [InlineKeyboardButton("← Indietro", callback_data=f"{p}:t:{team_id}")]
        if not g or not g["ruolo"]:
            await query.edit_message_text("Questo giocatore non ha ancora un ruolo ufficiale: va prima dichiarato.",
                                          reply_markup=InlineKeyboardMarkup([indietro]))
            return
        altri = [r for r in eleggibili(gid) if r != g["ruolo"]]
        erm = ruoli_erminio(gid)
        testo = (f"🔁 <b>{g['nome']}</b> — ruolo attuale <b>{g['ruolo']}</b>\n"
                 f"Eleggibile: {', '.join(eleggibili(gid)) or 'nessuna posizione registrata'}")
        if erm:
            testo += f"\n✨ Ruoli aggiunti (Erminio): {', '.join(sorted(erm))}"
        if not altri:
            testo += "\n\nNessun altro ruolo disponibile."
        kb = [[InlineKeyboardButton(r + (" ✨" if r in erm else ""), callback_data=f"{p}:r:{team_id}:{gid}:{r}")
               for r in altri]] if altri else []
        kb.append(indietro)
        await query.edit_message_text(testo, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    elif azione == "r":                                   # scelta del tipo di cambio
        gid, nuovo = int(parti[3]), parti[4]
        g = next((x for x in roster_ruoli(team_id) if x["gid"] == gid), None)
        erminio = nuovo in ruoli_erminio(gid)
        rimasti_dpe, ruoli_dpe = dpe_extra(team_id)
        tipi = ((["d"] if rimasti_dpe and nuovo in ruoli_dpe else [])
                + (["e", "s"] if erminio else ["o", "s"]) + (["f"] if admin_mode else []))
        righe, kb = [f"🔁 <b>{g['nome'] if g else gid}</b>: {g['ruolo'] if g else '?'} → <b>{nuovo}</b>\n"], []
        for k in tipi:
            errori, avvisi = verifica(team_id, gid, nuovo, TIPI[k], admin_mode)
            stato = "❌ " + errori[0] if errori else ("⚠️ " + avvisi[0] if avvisi else "✅ possibile")
            righe.append(f"• <b>{(ETICHETTE[TIPI[k]][:1].upper() + ETICHETTE[TIPI[k]][1:])}</b>: {stato}")
            if not errori:
                label = {"o": f"Ordinario ({ordinari_usati(team_id)}/{MAX_ORDINARI})", "e": "✨ Erminio (ruolo aggiunto)",
                         "s": "⏳ Saedro (10 day)" + ("" if admin_mode else " — richiedi"), "f": "🛠 Forzato admin",
                         "d": f"🏥 Extra DPE (gratuito, {rimasti_dpe} disponibil{'e' if rimasti_dpe == 1 else 'i'})"}[k]
                passo = "cf" if k == "o" else "do"
                kb.append([InlineKeyboardButton(label, callback_data=f"{p}:{passo}:{team_id}:{gid}:{nuovo}:{k}")])
        kb.append([InlineKeyboardButton("← Indietro", callback_data=f"{p}:g:{team_id}:{gid}")])
        await query.edit_message_text("\n".join(righe), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    elif azione == "cf":                                  # conferma del cambio ordinario
        gid, nuovo = int(parti[3]), parti[4]
        g = next((x for x in roster_ruoli(team_id) if x["gid"] == gid), None)
        n = ordinari_usati(team_id) + 1
        await query.edit_message_text(
            f"Confermi il <b>cambio ordinario</b> {g['nome'] if g else gid}: {g['ruolo'] if g else '?'} → <b>{nuovo}</b>?\n"
            f"Userai il cambio <b>{n}/{MAX_ORDINARI}</b> di questa stagione.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Confermo", callback_data=f"{p}:do:{team_id}:{gid}:{nuovo}:o"),
                InlineKeyboardButton("← Indietro", callback_data=f"{p}:r:{team_id}:{gid}:{nuovo}"),
            ]]))

    elif azione == "do":
        gid, nuovo, tipo = int(parti[3]), parti[4], TIPI[parti[5]]
        if tipo == "forzato_admin" and not admin_mode:
            return
        errori, _ = verifica(team_id, gid, nuovo, tipo, admin_mode)
        if errori:
            await query.edit_message_text("❌ " + "\n❌ ".join(errori),
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Indietro", callback_data=f"{p}:g:{team_id}:{gid}")]]))
            return
        if tipo == "saedro" and not admin_mode:
            if not db.apri_richiesta("saedro", gid, team_id):
                await query.edit_message_text("⏳ C'è già una richiesta di Saedro in attesa per questo giocatore: "
                                              "aspetta la risposta degli admin.")
                return
            await _richiedi_saedro(context.bot, team_id, gid, nuovo, query.from_user)
            await query.edit_message_text("📨 Richiesta di Saedro inviata agli admin. Ti arriva un messaggio quando decidono.")
            return
        chi = f" — {query.from_user.first_name or 'admin'}" if admin_mode else ""
        if tipo == "saedro":   # Saedro diretta dell'admin: chiude l'eventuale richiesta del GM
            db.chiudi_richiesta("saedro", gid, "approvata", query.from_user.first_name or "admin")
        esito = await _esegui(context.bot, team_id, gid, nuovo, tipo, chi)
        await query.edit_message_text(esito, parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Altri cambi", callback_data=f"{p}:t:{team_id}")]]))
        if admin_mode:
            await _ai_gm(context.bot, team_id, f"🛠 Un admin ha registrato un cambio ruolo: {esito[2:]}")


async def _richiedi_saedro(bot, team_id: str, gid: int, nuovo: str, user):
    gruppo = settings.load_globals().get("admin_group_id")
    if not gruppo:
        return
    nome = (db.get_giocatore(gid) or {}).get("nome_common", str(gid))
    attuale = next((x["ruolo"] for x in roster_ruoli(team_id) if x["gid"] == gid), "?")
    nel_ruolo = [x["nome"] for x in roster_ruoli(team_id) if x["ruolo"] == nuovo]
    testo = (f"⏳ <b>Richiesta Saedro</b> — {_nome_team(team_id)} ({user.first_name or user.id})\n"
             f"{nome}: {attuale} → <b>{nuovo}</b> per {GIORNI_SAEDRO} giorni\n\n"
             f"Giocatori della squadra in ruolo {nuovo}: <b>{', '.join(nel_ruolo) or 'nessuno'}</b>\n"
             f"<i>Da approvare se nessuno di questi è disponibile (OUT o fuori rotazione).</i>")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approva", callback_data=f"sae:ok:{team_id}:{gid}:{nuovo}"),
        InlineKeyboardButton("❌ Rifiuta", callback_data=f"sae:no:{team_id}:{gid}:{nuovo}"),
    ]])
    await bot.send_message(chat_id=gruppo, text=testo, parse_mode="HTML", reply_markup=kb)


async def cb_saedro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    _, esito, team_id, gid, nuovo = query.data.split(":")
    gid = int(gid)
    admin_nome = query.from_user.first_name or str(query.from_user.id)
    if esito == "ok" and settings.fase() not in settings.FASI_RUOLI_RS:
        await query.answer(FUORI_FASE, show_alert=True)
        return
    await query.answer()
    gia = "\n\nℹ️ <b>Richiesta già gestita</b>"
    if esito == "no":
        if db.chiudi_richiesta("saedro", gid, "rifiutata", admin_nome) == "gestita":
            await query.edit_message_text(query.message.text_html + gia, parse_mode="HTML")
            return
        await query.edit_message_text(query.message.text_html + f"\n\n❌ <b>Rifiutata</b> da {admin_nome}", parse_mode="HTML")
        await _ai_gm(context.bot, team_id, f"❌ La richiesta di Saedro per il ruolo {nuovo} è stata rifiutata.")
        return
    errori, _ = verifica(team_id, gid, nuovo, "saedro", admin=True)
    if errori:
        db.chiudi_richiesta("saedro", gid, "scaduta")
        await query.edit_message_text(query.message.text_html + "\n\n⚠️ Non applicabile: " + "; ".join(errori), parse_mode="HTML")
        return
    if db.chiudi_richiesta("saedro", gid, "approvata", admin_nome) == "gestita":
        await query.edit_message_text(query.message.text_html + gia, parse_mode="HTML")
        return
    esito_txt = await _esegui(context.bot, team_id, gid, nuovo, "saedro", f" — approvata da {admin_nome}")
    await query.edit_message_text(query.message.text_html + f"\n\n✅ <b>Approvata</b> da {admin_nome}", parse_mode="HTML")
    await _ai_gm(context.bot, team_id, f"✅ Saedro approvata. {esito_txt[2:]}")


async def cb_admin_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    if settings.fase() not in settings.FASI_RUOLI_RS:
        await query.answer(FUORI_FASE, show_alert=True)
        return
    await query.answer()
    kb = [[InlineKeyboardButton(f"{t['nome']} ({ordinari_usati(t['id'])}/{MAX_ORDINARI})",
                                callback_data=f"ca:t:{t['id']}")] for t in tm.get_all_teams()]
    kb.append([InlineKeyboardButton("← Menu admin", callback_data="adm:home")])
    await query.edit_message_text("🔁 <b>Cambi ruolo</b> — scegli la squadra\n<i>Tra parentesi i cambi ordinari usati.</i>",
                                  parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


# ══ job: fine Saedro ════════════════════════════════════════════════════════

async def job_fine_saedro(context: ContextTypes.DEFAULT_TYPE):
    """Ogni 15 minuti: Saedro scadute → ritorno al ruolo originale."""
    try:
        scadute = db._q("""SELECT DISTINCT ON (c.giocatore_id, c.stagione) c.*, g.nome_common
                           FROM cambi_ruolo c JOIN giocatori g ON g.id = c.giocatore_id
                           ORDER BY c.giocatore_id, c.stagione, c.timestamp DESC, c.id DESC""", many=True) or []
        ora = datetime.now(timezone.utc)
        fatto = False
        for c in scadute:
            if c["tipo"] != "saedro" or c["scadenza"] is None or c["scadenza"] > ora or not c["ruolo_ripristino"]:
                continue
            db._q("""INSERT INTO cambi_ruolo (giocatore_id, team_id, ruolo_da, ruolo_a, stagione, tipo)
                     VALUES (%s, %s, %s, %s, %s, 'saedro')""",
                  (c["giocatore_id"], c["team_id"], c["ruolo_a"], c["ruolo_ripristino"], c["stagione"]))
            fatto = True
            testo = (f"⏳ <b>{_nome_team(c['team_id'])}</b>: fine Saedro, {c['nome_common']} "
                     f"{c['ruolo_a']} → <b>{c['ruolo_ripristino']}</b>")
            await _annuncia(context.bot, testo)
            await _ai_gm(context.bot, c["team_id"], testo)
        if fatto:
            _sync()
    except Exception as e:
        logger.warning("job_fine_saedro: %s", e)


def get_handlers() -> list:
    return [
        CommandHandler("cambio_ruolo", cmd_cambio_ruolo),
        CallbackQueryHandler(cb_cambio, pattern=r"^(?:cr:(?:close|home)|c[ra]:(?:t:[\w-]+|g:[\w-]+:\d+|r:[\w-]+:\d+:[A-Z]{1,2}|(?:cf|do):[\w-]+:\d+:[A-Z]{1,2}:[oesfd]))$"),
        CallbackQueryHandler(cb_saedro, pattern=r"^sae:(ok|no):[\w-]+:\d+:[A-Z]{1,2}$"),
        CallbackQueryHandler(cb_admin_teams, pattern=r"^cradm:teams$"),
    ]

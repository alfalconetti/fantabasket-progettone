"""
Cambi ruolo in regular season (fasi settings.FASI_RUOLI_RS).

GM:    /cambio_ruolo o "🔁 Cambio ruolo" nel /menu
Admin: /admin_menu → "🔁 Cambi ruolo" → squadra (qualsiasi squadra)

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

logger = logging.getLogger(__name__)

RUOLI = ["PG", "SG", "SF", "PF", "C"]
MAX_ORDINARI = 2
GIORNI_ERMINIO = 14
GIORNI_SAEDRO = 10
TIPI = {"o": "ordinario", "e": "erminio", "s": "saedro", "f": "forzato_admin"}
ETICHETTE = {"ordinario": "cambio ordinario", "erminio": "Erminio rule (gratuito)",
             "saedro": f"Saedro rule ({GIORNI_SAEDRO} giorni)", "forzato_admin": "forzato dagli admin"}


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
    r = db._q("SELECT posizioni FROM posizioni_attuali WHERE giocatore_id = %s", (gid,), one=True)
    pos = set((r["posizioni"] if r else "").split(","))
    return [p for p in RUOLI if p in pos]


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

def _accesso(uid: int, team_id: str) -> str | None:
    if _is_admin(uid):
        return None
    t = tm.get_team_by_gm(uid)
    if not t or t["id"] != team_id:
        return "⛔ Puoi cambiare solo i ruoli della tua squadra."
    if settings.fase() not in settings.FASI_RUOLI_RS:
        return "❌ I cambi ruolo sono disponibili solo in regular season e playoff."
    return None


def _vista_team(team_id: str, admin: bool):
    usati = ordinari_usati(team_id)
    testo = (f"🔁 <b>Cambio ruolo — {_nome_team(team_id)}</b>" + (" <i>(admin)</i>" if admin else "") +
             f"\nCambi ordinari usati: <b>{usati}/{MAX_ORDINARI}</b> · Saedro: "
             f"{'usata' if saedro_usata(team_id) else 'disponibile'}\n\nScegli il giocatore:")
    kb = []
    for g in roster_ruoli(team_id):
        if not g["ruolo"]:
            label = f"❔ {g['nome']} (da dichiarare)"
        elif g["saedro_attiva"]:
            label = f"⏳ {g['ruolo']} · {g['nome']} (Saedro)"
        else:
            label = f"{g['ruolo']} · {g['nome']}"
        kb.append([InlineKeyboardButton(label, callback_data=f"cr:g:{team_id}:{g['gid']}")])
    kb.append([InlineKeyboardButton("✖️ Chiudi", callback_data="cr:close")])
    return testo, InlineKeyboardMarkup(kb)


@solo_privato
async def cmd_cambio_ruolo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    t = tm.get_team_by_gm(uid)
    if not t:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    motivo = _accesso(uid, t["id"])
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
    azione, team_id = parti[1], parti[2]
    motivo = _accesso(uid, team_id)
    if motivo:
        await query.answer(motivo, show_alert=True)
        return
    gm = tm.get_team_by_gm(uid)
    is_admin = _is_admin(uid)
    await query.answer()

    if azione == "t":
        testo, kb = _vista_team(team_id, is_admin and (not gm or gm["id"] != team_id))
        await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)

    elif azione == "g":
        gid = int(parti[3])
        g = next((x for x in roster_ruoli(team_id) if x["gid"] == gid), None)
        indietro = [InlineKeyboardButton("← Indietro", callback_data=f"cr:t:{team_id}")]
        if not g or not g["ruolo"]:
            await query.edit_message_text("Questo giocatore non ha ancora un ruolo ufficiale: va prima dichiarato.",
                                          reply_markup=InlineKeyboardMarkup([indietro]))
            return
        altri = [r for r in eleggibili(gid) if r != g["ruolo"]]
        erm = ruoli_erminio(gid)
        testo = (f"🔁 <b>{g['nome']}</b> — ruolo attuale <b>{g['ruolo']}</b>\n"
                 f"Eleggibile: {', '.join(eleggibili(gid)) or 'nessuna posizione registrata'}")
        if erm:
            testo += f"\n✨ Posizioni nuove (Erminio, gratuito): {', '.join(sorted(erm))}"
        if not altri:
            testo += "\n\nNessun altro ruolo disponibile."
        kb = [[InlineKeyboardButton(r + (" ✨" if r in erm else ""), callback_data=f"cr:r:{team_id}:{gid}:{r}")
               for r in altri]] if altri else []
        kb.append(indietro)
        await query.edit_message_text(testo, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    elif azione == "r":                                   # scelta del tipo di cambio
        gid, nuovo = int(parti[3]), parti[4]
        g = next((x for x in roster_ruoli(team_id) if x["gid"] == gid), None)
        erminio = nuovo in ruoli_erminio(gid)
        tipi = (["e", "s"] if erminio else ["o", "s"]) + (["f"] if is_admin else [])
        righe, kb = [f"🔁 <b>{g['nome'] if g else gid}</b>: {g['ruolo'] if g else '?'} → <b>{nuovo}</b>\n"], []
        for k in tipi:
            errori, avvisi = verifica(team_id, gid, nuovo, TIPI[k], is_admin)
            stato = "❌ " + errori[0] if errori else ("⚠️ " + avvisi[0] if avvisi else "✅ possibile")
            righe.append(f"• <b>{ETICHETTE[TIPI[k]].capitalize()}</b>: {stato}")
            if not errori:
                label = {"o": f"Ordinario ({ordinari_usati(team_id)}/{MAX_ORDINARI})", "e": "✨ Erminio (gratis)",
                         "s": "⏳ Saedro" + ("" if is_admin else " — richiedi"), "f": "🛠 Forzato admin"}[k]
                passo = "cf" if k == "o" else "do"
                kb.append([InlineKeyboardButton(label, callback_data=f"cr:{passo}:{team_id}:{gid}:{nuovo}:{k}")])
        kb.append([InlineKeyboardButton("← Indietro", callback_data=f"cr:g:{team_id}:{gid}")])
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
                InlineKeyboardButton("✅ Confermo", callback_data=f"cr:do:{team_id}:{gid}:{nuovo}:o"),
                InlineKeyboardButton("← Indietro", callback_data=f"cr:r:{team_id}:{gid}:{nuovo}"),
            ]]))

    elif azione == "do":
        gid, nuovo, tipo = int(parti[3]), parti[4], TIPI[parti[5]]
        errori, _ = verifica(team_id, gid, nuovo, tipo, is_admin)
        if errori:
            await query.edit_message_text("❌ " + "\n❌ ".join(errori),
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Indietro", callback_data=f"cr:g:{team_id}:{gid}")]]))
            return
        if tipo == "saedro" and not is_admin:
            await _richiedi_saedro(context.bot, team_id, gid, nuovo, query.from_user)
            await query.edit_message_text("📨 Richiesta di Saedro inviata agli admin. Ti arriva un messaggio quando decidono.")
            return
        chi = f" — {query.from_user.first_name or 'admin'}" if is_admin and (not gm or gm["id"] != team_id) else ""
        esito = await _esegui(context.bot, team_id, gid, nuovo, tipo, chi)
        await query.edit_message_text(esito, parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Altri cambi", callback_data=f"cr:t:{team_id}")]]))
        if chi:
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
    await query.answer()
    if esito == "no":
        await query.edit_message_text(query.message.text_html + f"\n\n❌ <b>Rifiutata</b> da {admin_nome}", parse_mode="HTML")
        await _ai_gm(context.bot, team_id, f"❌ La richiesta di Saedro per il ruolo {nuovo} è stata rifiutata.")
        return
    errori, _ = verifica(team_id, gid, nuovo, "saedro", admin=True)
    if errori:
        await query.edit_message_text(query.message.text_html + "\n\n⚠️ Non applicabile: " + "; ".join(errori), parse_mode="HTML")
        return
    esito_txt = await _esegui(context.bot, team_id, gid, nuovo, "saedro", f" — approvata da {admin_nome}")
    await query.edit_message_text(query.message.text_html + f"\n\n✅ <b>Approvata</b> da {admin_nome}", parse_mode="HTML")
    await _ai_gm(context.bot, team_id, f"✅ Saedro approvata. {esito_txt[2:]}")


async def cb_admin_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    await query.answer()
    kb = [[InlineKeyboardButton(f"{t['nome']} ({ordinari_usati(t['id'])}/{MAX_ORDINARI})",
                                callback_data=f"cr:t:{t['id']}")] for t in tm.get_all_teams()]
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
        CallbackQueryHandler(cb_cambio, pattern=r"^cr:(close|home|t:[\w-]+|g:[\w-]+:\d+|r:[\w-]+:\d+:[A-Z]{1,2}|(?:cf|do):[\w-]+:\d+:[A-Z]{1,2}:[oesf])$"),
        CallbackQueryHandler(cb_saedro, pattern=r"^sae:(ok|no):[\w-]+:\d+:[A-Z]{1,2}$"),
        CallbackQueryHandler(cb_admin_teams, pattern=r"^cradm:teams$"),
    ]

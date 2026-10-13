"""
Calcolo definitivo delle giornate, convalida e controllo dei tabellini.

Job 7:45 (Roma): per ogni giornata finita (l'ultima notte è passata), chiusa su IPanchinari e non
ancora calcolata: partite NBA e tabellini aggiornati, calcolo (risultati.calcola), tab "Calcolo GN"
sul foglio di controllo, proposta al gruppo admin coi bottoni ✅ Convalida / 🔄 Ricalcola.
Job 10:00: riscarica i tabellini delle giornate calcolate da poco o da convalidare e, se ESPN ne ha
cambiato qualcuno dei giocatori schierati, avvisa il gruppo admin col bottone 🔄 Ricalcola.
/ricalcola N (admin): riscarica i tabellini della giornata, ricalcola, riscrive il tab, nuova
proposta (anche dopo la convalida: alla nuova convalida si riscrive il Calendario).

Callback: rc:ok:<N>:<versione> convalida · rc:re:<N> ricalcola.
"""
import html
import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import config
import db
import nba
import risultati as R

logger = logging.getLogger(__name__)
e = html.escape
STATI_CHIUSI = ("STATUS_FINAL", "STATUS_POSTPONED", "STATUS_CANCELED")


def _tasti(n: int, versione: int) -> K:
    return K([[B("✅ Convalida", callback_data=f"rc:ok:{n}:{versione}"), B("🔄 Ricalcola", callback_data=f"rc:re:{n}")]])


def _giorni(g) -> list:
    return [g["dal"] + timedelta(days=i) for i in range((g["al"] - g["dal"]).days + 1)]


def pronta(stagione: str, g: dict) -> str | None:
    """None se la giornata si può calcolare, altrimenti il motivo."""
    if not R.giornata_chiusa(stagione, g["numero"]):
        return "quintetti non ancora congelati su IPanchinari"
    partite = db.partite_nba(g["dal"], g["al"])
    aperte = [p for p in partite if p["stato"] not in STATI_CHIUSI]
    if aperte:
        return f"{len(aperte)} partite NBA non ancora finite"
    senza = [p for p in partite if p["stato"] == "STATUS_FINAL" and not p.get("tabellino")]
    if senza:
        return f"{len(senza)} tabellini non ancora scaricati"
    return None


async def _riscarica(g: dict) -> dict:
    """Riscarica i tabellini di tutte le partite finite della giornata. {(partita, atleta): (prima, dopo)} dei cambi."""
    ids = [p["espn_id"] for p in db.partite_nba(g["dal"], g["al"]) if p["stato"] == "STATUS_FINAL"]
    if not ids:
        return {}
    prima = {(r["partita"], r["atleta"]): (float(r["fp"]), r["minuti"], r["nome"])
             for r in db.q("SELECT partita, atleta, fp, minuti, nome FROM nba_tabellini WHERE partita = ANY(%s)", (ids,), many=True) or []}
    await nba.scarica_tabellini(ids)
    dopo = {(r["partita"], r["atleta"]): (float(r["fp"]), r["minuti"], r["nome"])
            for r in db.q("SELECT partita, atleta, fp, minuti, nome FROM nba_tabellini WHERE partita = ANY(%s)", (ids,), many=True) or []}
    return {k: (prima.get(k), dopo.get(k)) for k in set(prima) | set(dopo) if prima.get(k) != dopo.get(k)}


async def esegui(bot, stagione: str, n: int, chi: str = "job delle 7:45") -> str:
    """Calcola (o ricalcola) la giornata n, scrive il tab, manda la proposta. Restituisce l'esito."""
    from handlers import log
    c = R.calcola(stagione, n)
    vecchio = db.q("SELECT messaggio FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (stagione, n), one=True)
    versione = R.salva_calcolo(c)
    foglio = await R.scrivi_foglio(c)
    testo = R.testo(c, versione) + f"\n\n<i>{e(foglio)}</i>"
    gruppo = config.gruppo_admin()
    if gruppo:
        if vecchio and vecchio["messaggio"]:
            try:
                await bot.edit_message_reply_markup(chat_id=gruppo, message_id=vecchio["messaggio"], reply_markup=None)
                await bot.send_message(chat_id=gruppo, reply_to_message_id=vecchio["messaggio"], allow_sending_without_reply=True,
                                       text="⏪ Superata dal ricalcolo qui sotto.")
            except Exception as err:
                logger.info("Proposta vecchia: %s", err)
        m = await bot.send_message(chat_id=gruppo, text=testo, parse_mode="HTML", reply_markup=_tasti(n, versione))
        db.q("UPDATE lega_calcoli SET messaggio = %s WHERE stagione = %s AND giornata = %s", (m.message_id, stagione, n))
    await log(bot, f"📊 Giornata {n} calcolata (versione {versione}, {chi}): "
                   + ", ".join(f"{e(config.nome(r['casa']))} {r['punti_casa']:.2f}–{r['punti_trasferta']:.2f} {e(config.nome(r['trasferta']))}"
                               for r in c["risultati"]) + f"; {e(foglio)}")
    return foglio


async def job_calcolo(context: ContextTypes.DEFAULT_TYPE):
    """7:45: le giornate finite da calcolare."""
    from handlers import log
    import handlers_calcolo as hc
    s = config.stagione()
    oggi = nba.oggi_et()
    fatte = {r["giornata"] for r in db.q("SELECT giornata FROM lega_calcoli WHERE stagione = %s", (s,), many=True) or []}
    da_fare = [g for g in db.giornate(s) if g["al"] < oggi and g["al"] >= oggi - timedelta(days=7) and g["numero"] not in fatte]
    for g in da_fare:
        try:
            await nba.sincronizza(_giorni(g))
            await hc.aggiorna_tabellini()
            motivo = pronta(s, g)
            if motivo:
                await log(context.bot, f"⏳ Giornata {g['numero']} non calcolata alle 7:45: {e(motivo)}. "
                                       f"Quando è pronta: /ricalcola {g['numero']}")
                continue
            await esegui(context.bot, s, g["numero"])
        except Exception as err:
            logger.exception("Calcolo giornata %s", g["numero"])
            await log(context.bot, f"⚠️ Calcolo della giornata {g['numero']} fallito: {e(repr(err))[:300]}")


async def job_controllo(context: ContextTypes.DEFAULT_TYPE):
    """10:00: ESPN ha corretto qualche tabellino delle giornate calcolate da poco o da convalidare?"""
    from handlers import log
    s = config.stagione()
    calc = db.q("""SELECT giornata, stato FROM lega_calcoli WHERE stagione = %s
                   AND (stato = 'da_convalidare' OR calcolato > NOW() - INTERVAL '2 days')""", (s,), many=True) or []
    for lc in calc:
        n = lc["giornata"]
        g = db.giornata(s, n)
        try:
            cambi = await _riscarica(g)
        except Exception as err:
            await log(context.bot, f"⚠️ Controllo delle 10, giornata {n}: {e(repr(err))[:200]}")
            continue
        schierati = set()
        for sq in R.schieramenti(s, n).values():
            ids = [x for x in sq["quintetto"].values() if x] + [r.get("giocatore_id") for r in (sq["panchina"] or [])]
            schierati |= {r["espn_id"] for r in db.q("SELECT espn_id FROM giocatori WHERE id = ANY(%s) AND espn_id IS NOT NULL",
                                                       (ids,), many=True) or []}
        contano = {k: v for k, v in cambi.items() if k[1] in schierati}
        if not contano:
            await log(context.bot, f"🔎 Controllo delle 10, giornata {n}: nessun tabellino cambiato"
                                   + (f" tra i giocatori schierati ({len(cambi)} cambi di altri)" if cambi else ""))
            continue
        righe = []
        for (pid, a), (prima, dopo) in sorted(contano.items(), key=lambda x: (x[1][1] or x[1][0])[2]):
            nome = (dopo or prima)[2]
            righe.append(f"• {e(nome)}: {prima[0] if prima else '—'} → {dopo[0] if dopo else '—'} fantapunti"
                         + (f" (minuti {prima[1]} → {dopo[1]})" if prima and dopo and prima[1] != dopo[1] else ""))
        testo = (f"🔎 <b>Controllo delle 10, giornata {n}</b>: ESPN ha cambiato {len(contano)} tabellini di giocatori schierati"
                 + (" (giornata già convalidata)" if lc["stato"] == "convalidata" else "") + ":\n" + "\n".join(righe)
                 + "\n\nI tabellini nel database sono già aggiornati: ricalcola per aggiornare risultati e foglio.")
        if config.gruppo_admin():
            await context.bot.send_message(chat_id=config.gruppo_admin(), text=testo, parse_mode="HTML",
                                           reply_markup=K([[B("🔄 Ricalcola", callback_data=f"rc:re:{n}")]]))
        await log(context.bot, f"🔎 Controllo delle 10, giornata {n}: {len(contano)} tabellini cambiati, avviso agli admin")


async def _ricalcola(bot, s: str, n: int, chi: str, rispondi):
    g = db.giornata(s, n)
    if not g:
        await rispondi(f"Giornata {n} non trovata.")
        return
    motivo = None
    try:
        await nba.sincronizza(_giorni(g))
        import handlers_calcolo as hc
        await hc.aggiorna_tabellini()
        await _riscarica(g)
        motivo = pronta(s, g)
        if motivo:
            await rispondi(f"❌ Giornata {n} non ancora calcolabile: {motivo}.")
            return
        esito = await esegui(bot, s, n, chi)
        await rispondi(f"✅ Giornata {n} ricalcolata: proposta nuova nel gruppo admin ({esito}).")
    except Exception as err:
        logger.exception("Ricalcolo %s", n)
        await rispondi(f"⚠️ Ricalcolo della giornata {n} fallito: {err}")


async def cmd_ricalcola(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ricalcola N (admin)."""
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Uso: /ricalcola N (riscarica i tabellini della giornata N e ricalcola)")
        return
    from handlers import _chi
    n = int(context.args[0])
    msg = update.effective_message
    await msg.reply_text(f"⏳ Ricalcolo la giornata {n}: riscarico i tabellini (un secondo a partita)…")

    async def rispondi(t):
        await msg.reply_text(t)
    await _avvia(context, _ricalcola(context.bot, config.stagione(), n, f"/ricalcola di {_chi(update)}", rispondi))


async def _avvia(context, coro):
    app = getattr(context, "application", None)
    if app:
        app.create_task(coro)          # i tabellini si riscaricano in un minuto: il bot non si blocca
    else:
        await coro


async def cb_risultati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not config.is_admin(update.effective_user.id):
        await q.answer("Solo admin.", show_alert=True)
        return
    from handlers import _chi, log
    parti = q.data.split(":")
    azione, n = parti[1], int(parti[2])
    s = config.stagione()
    lc = db.q("SELECT * FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (s, n), one=True)
    if azione == "ok":
        if not lc or lc["versione"] != int(parti[3]) or lc["stato"] != "da_convalidare":
            await q.answer("Questa proposta non è più valida (ricalcolata o già convalidata).", show_alert=True)
            return
        R.convalida(s, n, update.effective_user.id)
        await q.answer("Convalidata")
        import foglio
        esito = await foglio.aggiorna(s)
        ora = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Europe/Rome"))
        try:
            await q.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=q.message.chat_id, reply_to_message_id=q.message.message_id,
                                           text=f"✅ Giornata {n} convalidata da {_chi(update)} alle {ora:%H:%M}: risultati salvati, {e(esito)}.",
                                           parse_mode="HTML")
        except Exception as err:
            logger.info("Messaggio di convalida: %s", err)
        await log(context.bot, f"✅ Giornata {n} convalidata da {_chi(update)} (versione {lc['versione']}); {e(esito)}")
        return
    if azione == "re":
        await q.answer("Ricalcolo in corso…")

        async def rispondi(t):
            await context.bot.send_message(chat_id=q.message.chat_id, text=t)
        await _avvia(context, _ricalcola(context.bot, s, n, f"🔄 di {_chi(update)}", rispondi))


def get_handlers() -> list:
    return [CommandHandler("ricalcola", cmd_ricalcola), CallbackQueryHandler(cb_risultati, pattern=r"^rc:")]

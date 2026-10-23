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
from numeri import testo as testo_punti
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


async def esegui(bot, stagione: str, n: int, chi: str = "job delle 7:45", user=None) -> str:
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
    from registro import segna_sync
    segna_sync(user, "admin" if user else "sistema", "giornata ricalcolata" if versione > 1 else "giornata calcolata",
               oggetto=f"giornata {n}", dopo=f"versione {versione}, da convalidare",
               nota="; ".join(f"{config.nome(r['casa'])} {testo_punti(r['punti_casa'])}–{testo_punti(r['punti_trasferta'])} "
                              f"{config.nome(r['trasferta'])}" for r in c["risultati"])[:800])
    await log(bot, f"📊 Giornata {n} calcolata (versione {versione}, {chi}): "
                   + ", ".join(f"{e(config.nome(r['casa']))} {testo_punti(r['punti_casa'])}–{testo_punti(r['punti_trasferta'])} {e(config.nome(r['trasferta']))}"
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


async def _ricalcola(bot, s: str, n: int, chi: str, rispondi, user=None):
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
        esito = await esegui(bot, s, n, chi, user=user)
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
    await _avvia(context, _ricalcola(context.bot, config.stagione(), n, f"/ricalcola di {_chi(update)}", rispondi,
                                     user=update.effective_user))


async def _avvia(context, coro):
    app = getattr(context, "application", None)
    if app:
        app.create_task(coro)          # i tabellini si riscaricano in un minuto: il bot non si blocca
    else:
        await coro


def _chi_nome(update) -> str:
    u = update.effective_user
    return (u.full_name or u.first_name or str(u.id)) if u else "un admin"


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
        from registro import segna_sync
        segna_sync(update.effective_user, "admin", "giornata convalidata", oggetto=f"giornata {n}",
                   prima=f"versione {lc['versione']} da convalidare", dopo="convalidata: risultati salvati")
        await q.answer("Convalidata")
        import foglio
        esito = await foglio.aggiorna(s)
        try:                                             # canale: risultati definitivi, via il live (Luca, 23/10)
            import live
            esito += "; " + await live.pubblica_definitivo(context.bot, s, n, _chi_nome(update))
        except Exception as err:
            logger.warning("Risultati definitivi sul canale G%s: %s", n, err)
            esito += f"; ⚠️ risultati definitivi non pubblicati sul canale ({str(err)[:120]})"
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
        await _avvia(context, _ricalcola(context.bot, s, n, f"🔄 di {_chi(update)}", rispondi, user=update.effective_user))


async def cmd_dev_prova_calcolo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dev_prova_calcolo GG/MM/AAAA GG/MM/AAAA (solo dev): prova del calcolo prima che si giochi.
    Gli accoppiamenti della prossima giornata, i quintetti di adesso e le panchine già mandate,
    sulle partite NBA vere dei giorni indicati (es. di marzo della stagione scorsa): tab «Calcolo G0»
    sul foglio e la proposta solo al dev, senza bottoni. Non salva niente nei risultati."""
    if not (config.dev_id() and update.effective_user.id == config.dev_id()):
        return
    import calendario as cal
    import handlers_calcolo as hc
    msg = update.effective_message
    try:
        from shared.date_comandi import leggi_data
        dal, al = [leggi_data(x) for x in (context.args or [])[:2]]
        if not dal or not al:
            raise ValueError("data")
        assert dal <= al <= dal + timedelta(days=4)
    except Exception:
        await msg.reply_text("Uso: /dev_prova_calcolo GG/MM/AAAA GG/MM/AAAA (da 1 a 5 giorni NBA già giocati, es. 01/03/2026 03/03/2026)")
        return
    s = config.stagione()
    vera = cal.corrente(s)
    if not vera:
        await msg.reply_text("Nessuna giornata nel calendario da cui prendere gli accoppiamenti.")
        return
    await msg.reply_text(f"⏳ Prova: accoppiamenti della giornata {vera['numero']}, notti NBA {dal:%d/%m}–{al:%d/%m}. "
                         "Scarico partite e tabellini (un secondo a partita)…")

    async def lavoro():
        try:
            await nba.sincronizza([dal + timedelta(days=i) for i in range((al - dal).days + 1)])
            await hc.aggiorna_tabellini(dal, al)
            stagione_nba = next((p["stagione"] for p in db.partite_nba(dal, al)), s)
            finta = {**vera, "numero": 0, "dal": dal, "al": al, "media": None, "media_file": [], "tipo": "regular"}
            c = R.calcola(s, 0, g=finta, sch=R.schieramenti_attuali(s, vera["numero"]), stagione_nba=stagione_nba,
                          partite=db.partite_giornata(s, vera["numero"]))
            foglio = await R.scrivi_foglio(c)
            await context.bot.send_message(chat_id=update.effective_chat.id, parse_mode="HTML",
                                           text="🧪 <b>PROVA</b> (niente è stato salvato)\n\n" + R.testo(c) + f"\n\n<i>{e(foglio)}</i>")
            import live
            await live.manda_anteprima(context.bot, update.effective_chat.id, c, datetime.now(timezone.utc))
        except Exception as err:
            logger.exception("Prova del calcolo")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ Prova fallita: {err}")
    await _avvia(context, lavoro())


async def cmd_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/live (admin): il messaggio live della giornata in corso adesso, senza aspettare i 10 minuti.
    Se la giornata non è ancora iniziata, l'anteprima solo a chi lo chiede."""
    import live
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    s = config.stagione()
    ora = datetime.now(timezone.utc)
    attive = live.giornate_attive(s, ora)
    msg = update.effective_message
    if not attive:
        import calendario as cal
        g = cal.corrente(s)
        if not g:
            await msg.reply_text("Nessuna giornata.")
            return
        c = live.calcolo(s, g["numero"])
        await live.manda_anteprima(context.bot, update.effective_chat.id, c, ora)
        return

    async def lavoro():
        for g in attive:
            g = {**g, "stagione": s}
            notte = next((d for d, inizio, fine in live.notti(g) if inizio <= ora < fine), None)
            try:
                esito = await live.aggiorna(context.bot, g, notte, ora)
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🔴 Live G{g['numero']} aggiornato: {esito}")
            except Exception as err:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ Live G{g['numero']}: {err}")
    await _avvia(context, lavoro())


def get_handlers() -> list:
    return [CommandHandler("ricalcola", cmd_ricalcola), CommandHandler("dev_prova_calcolo", cmd_dev_prova_calcolo),
            CommandHandler("live", cmd_live),
            CallbackQueryHandler(cb_risultati, pattern=r"^rc:")]

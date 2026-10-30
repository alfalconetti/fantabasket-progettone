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
from zoneinfo import ZoneInfo as _ZI
ROMA = _ZI("Europe/Rome")

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
    """Riscarica i tabellini delle partite finite della giornata, tranne le notti congelate (v58: in pratica
    l'ultima notte, fino alle 20 del giorno dopo). {(partita, atleta): (riga prima, riga dopo)} dei cambi."""
    import congelamento as CG
    ids = [p["espn_id"] for p in db.partite_nba(g["dal"], g["al"]) if p["stato"] == "STATUS_FINAL"]
    if not ids:
        return {}
    prima = CG.righe(ids)
    await nba.scarica_tabellini(ids)
    return CG.cambi(prima, CG.righe(ids))


async def esegui(bot, stagione: str, n: int, chi: str = "job delle 7:45", user=None) -> str:
    """Calcola (o ricalcola) la giornata n, scrive il tab, manda la proposta. Restituisce l'esito."""
    from handlers import log
    c = R.calcola(stagione, n)
    vecchio = db.q("SELECT messaggio FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (stagione, n), one=True)
    versione = R.salva_calcolo(c)
    foglio = await R.scrivi_foglio(c)
    # giornata già convalidata (ricalcolo): cosa cambia rispetto ai risultati convalidati (Luca, 26/10)
    testo = R.testo(c, versione) + R.testo_differenze(R.differenze(stagione, n, c["risultati"])) + f"\n\n<i>{e(foglio)}</i>"
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
    """7:45: le giornate finite da calcolare, coi tabellini dell'ultima notte riscaricati (le altre sono congelate)."""
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
            # riscarica i tabellini già presi nella notte (correzioni di ESPN dopo il live, Luca 24/10); le notti
            # congelate restano come sono (v58: in pratica solo l'ultima notte)
            cambi = await _riscarica(g)
            if cambi:
                import congelamento as CG
                sch = CG.schierati(s, g["numero"])
                contano = {k: v for k, v in cambi.items() if k[1] in sch}
                await log(context.bot, f"🔁 Giornata {g['numero']}, 7:45: {len(cambi)} righe di tabellino corrette da ESPN "
                                       f"dopo la notte, il calcolo usa quelle nuove"
                                       + (":\n" + "\n".join(CG.riga_cambio(a, b) for a, b in contano.values()) if contano else
                                          " (nessuna di giocatori schierati)"))
            motivo = pronta(s, g)
            if motivo:
                await log(context.bot, f"⏳ Giornata {g['numero']} non calcolata alle 7:45: {e(motivo)}. "
                                       f"Quando è pronta: /ricalcola {g['numero']}")
                continue
            await esegui(context.bot, s, g["numero"])
        except Exception as err:
            logger.exception("Calcolo giornata %s", g["numero"])
            await log(context.bot, f"⚠️ Calcolo della giornata {g['numero']} fallito: {e(repr(err))[:300]}")


def _json_righe(d: dict) -> list:
    from db import _COLONNE_TAB
    return [{k: (float(v[k]) if k == "fp" else v[k]) for k in _COLONNE_TAB} if v else None for v in d]


async def controllo_notte(bot, d, chi: str = "controllo delle 20", user=None) -> str:
    """Controllo finale della notte d (v58, Luca 30/10, come Yahoo): riscarica i tabellini (anche se la notte è
    già congelata: è l'ultimo controllo), e se ESPN ha cambiato giocatori schierati chiede agli admin di verificare
    su Yahoo (✅ uguale · ❌ non corrisponde: tornano i valori di prima). Poi, solo per informazione e senza salvare
    niente, le altre notti della stessa giornata, sul canale log. Restituisce l'esito in breve."""
    from handlers import log
    import json
    import congelamento as CG
    s = config.stagione()
    g = CG.giornata_di(s, d)
    ids = [p["espn_id"] for p in db.partite_nba(d, d) if p["stato"] == "STATUS_FINAL"]
    if not ids:
        await log(bot, f"🔎 Controllo finale della notte del {d:%d/%m}: nessuna partita finita")
        return "nessuna partita"
    prima = CG.righe(ids)
    r = await nba.scarica_tabellini(ids, forza=True)
    cambi = CG.cambi(prima, CG.righe(ids))
    sch = CG.schierati(s, g["numero"]) if g else set()
    contano = {k: v for k, v in cambi.items() if k[1] in sch}
    errori = r.get("errori") or []
    nota_err = (f"\n⚠️ {len(errori)} partite non scaricate ({e('; '.join(errori))[:150]}): /controllo_notte {d:%d/%m} per riprovare"
                if errori else "")
    gn = f" (G{g['numero']})" if g else ""
    if contano:
        CG.migra()
        cid = db.q("""INSERT INTO lega_controlli_notte (data_et, giornata, prima, dopo, chi) VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                   (d, g["numero"] if g else None, json.dumps({f"{k[0]}|{k[1]}": v for k, v in zip(contano, _json_righe([x[0] for x in contano.values()]))}),
                    json.dumps({f"{k[0]}|{k[1]}": v for k, v in zip(contano, _json_righe([x[1] for x in contano.values()]))}), chi),
                   one=True)["id"]
        testo = (f"🔎 <b>Controllo finale, notte del {d:%d/%m}</b>{gn}: ESPN ha cambiato {len(contano)} "
                 f"{'tabellino' if len(contano) == 1 else 'tabellini'} di giocatori schierati. "
                 f"<b>Verificate che su Yahoo sia uguale:</b>\n"
                 + "\n".join(CG.riga_cambio(a, b) for a, b in sorted(contano.values(), key=lambda x: (x[1] or x[0])["nome"]))
                 + "\n\nI valori nuovi sono già nel database. Se su Yahoo non corrispondono, ❌ rimette quelli di prima."
                 + (" Poi 🔄 Ricalcola per aggiornare risultati e foglio." if g and _calcolata(s, g["numero"]) else "") + nota_err)
        tasti = [[B("✅ Uguale su Yahoo", callback_data=f"cn:ok:{cid}"), B("❌ Non corrisponde", callback_data=f"cn:no:{cid}")]]
        if g and _calcolata(s, g["numero"]):
            tasti.append([B("🔄 Ricalcola", callback_data=f"rc:re:{g['numero']}")])
        if config.gruppo_admin():
            m = await bot.send_message(chat_id=config.gruppo_admin(), text=testo, parse_mode="HTML", reply_markup=K(tasti))
            db.q("UPDATE lega_controlli_notte SET messaggio = %s WHERE id = %s", (m.message_id, cid))
        await log(bot, f"🔎 Controllo finale, notte del {d:%d/%m}{gn}: {len(contano)} tabellini cambiati tra gli schierati, "
                       f"agli admin da verificare su Yahoo")
        esito = f"{len(contano)} cambi agli admin"
    else:
        await log(bot, f"🔎 Controllo finale, notte del {d:%d/%m}{gn}: nessun tabellino cambiato tra gli schierati"
                       + (f" ({len(cambi)} cambi di altri)" if cambi else "") + "; notte congelata" + nota_err)
        esito = "nessun cambio"
    # le altre notti della giornata: solo informazione personale, sul log, SENZA salvare (Luca, 30/10)
    if g:
        for d2 in [x for x in CG.notti(g) if x < d]:
            ids2 = [p["espn_id"] for p in db.partite_nba(d2, d2) if p["stato"] == "STATUS_FINAL"]
            if not ids2:
                continue
            try:
                r2 = await nba.scarica_tabellini(ids2, forza=True, salva=False)
            except Exception as err:
                await log(bot, f"ℹ️ Notte del {d2:%d/%m} (solo informazione): non letta ({e(str(err))[:120]})")
                continue
            letti = {(pid, x["atleta"]): x for pid, tab in (r2.get("letti") or {}).items() for x in tab}
            salvati = {k: v for k, v in CG.righe(list((r2.get("letti") or {}).keys())).items()}
            diff = {k: v for k, v in CG.cambi(salvati, letti).items() if k[1] in sch}
            if not diff:
                await log(bot, f"ℹ️ Notte del {d2:%d/%m}{gn}: ESPN la dà uguale")
                continue
            # agli admin coi bottoni (Luca, 30/10): se su Yahoo è già così si aggiorna, se no resta com'era
            CG.migra()
            dopo2 = {f"{k[0]}|{k[1]}": v for k, v in zip(diff, _json_righe([x[1] for x in diff.values()]))}
            # la stessa differenza già mandata (in attesa o lasciata com'era): non si ripete ogni sera
            gia = [r for r in (db.q("SELECT id, stato, dopo, quando FROM lega_controlli_notte WHERE data_et = %s "
                                    "AND stato IN ('da applicare', 'lasciato')", (d2,), many=True) or [])
                   if (r["dopo"] if isinstance(r["dopo"], dict) else json.loads(r["dopo"])) == json.loads(json.dumps(dopo2))]
            if gia:
                await log(bot, f"ℹ️ Notte del {d2:%d/%m}{gn}: ESPN la dà ancora diversa per {len(diff)} schierati, come già "
                               f"segnalato il {gia[0]['quando'].astimezone(ROMA):%d/%m} ({'in attesa' if gia[0]['stato'] == 'da applicare' else 'lasciata com era'})")
                continue
            # una segnalazione ancora in attesa ma con valori diversi da quelli di oggi: superata da questa
            db.q("UPDATE lega_controlli_notte SET stato = 'superato' WHERE data_et = %s AND stato = 'da applicare'", (d2,))
            cid2 = db.q("""INSERT INTO lega_controlli_notte (data_et, giornata, prima, dopo, chi, stato) VALUES (%s, %s, %s, %s, %s, 'da applicare')
                           RETURNING id""",
                        (d2, g["numero"], json.dumps({f"{k[0]}|{k[1]}": v for k, v in zip(diff, _json_righe([x[0] for x in diff.values()]))}),
                         json.dumps({f"{k[0]}|{k[1]}": v for k, v in zip(diff, _json_righe([x[1] for x in diff.values()]))}), chi),
                        one=True)["id"]
            t2 = (f"ℹ️ <b>Notte del {d2:%d/%m}{gn}, {'già congelata' if CG.notte_congelata(d2, s) else 'non ancora congelata'}</b>: ESPN oggi la dà diversa per {len(diff)} "
                  f"{'schierato' if len(diff) == 1 else 'schierati'}. <b>Niente è stato salvato.</b> Guardate su Yahoo:\n"
                  + "\n".join(CG.riga_cambio(a, b) for a, b in sorted(diff.values(), key=lambda x: (x[1] or x[0])["nome"]))
                  + "\n\n✅ se su Yahoo è già così, salva i valori nuovi; ❌ lascia quelli di adesso.")
            await log(bot, f"ℹ️ Notte del {d2:%d/%m}{gn}: ESPN oggi la darebbe diversa per {len(diff)} schierati, "
                           f"agli admin da verificare su Yahoo")
            if config.gruppo_admin():
                m2 = await bot.send_message(chat_id=config.gruppo_admin(), text=t2, parse_mode="HTML",
                                            reply_markup=K([[B("✅ Su Yahoo è così: aggiorna", callback_data=f"cn:ag:{cid2}"),
                                                             B("❌ Lascia com'è", callback_data=f"cn:la:{cid2}")]]))
                db.q("UPDATE lega_controlli_notte SET messaggio = %s WHERE id = %s", (m2.message_id, cid2))
    return esito


def _calcolata(s: str, n: int) -> bool:
    return bool(db.q("SELECT 1 AS x FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (s, n), one=True))


async def primo_controllo(bot, d) -> str:
    """Primo controllo della notte d alle 11:05 quando il live non c'è più (giornata convalidata): riscarica, cambi
    degli schierati col dettaglio sul log e, se la giornata è calcolata, al gruppo admin con Ricalcola (v60, Luca
    30/10: «avevamo detto di tenerlo»). Col live ancora aperto lo fa il live stesso (live.cosa_fare → «controllo»)."""
    from handlers import log
    import congelamento as CG
    s = config.stagione()
    g = CG.giornata_di(s, d)
    ids = [p["espn_id"] for p in db.partite_nba(d, d) if p["stato"] == "STATUS_FINAL"]
    if not g or not ids:
        return "niente da controllare"
    prima = CG.righe(ids)
    await nba.scarica_tabellini(ids)
    cambi = CG.cambi(prima, CG.righe(ids))
    sch = CG.schierati(s, g["numero"])
    contano = {k: v for k, v in cambi.items() if k[1] in sch}
    from shared import regole as _r
    titolo = f"🔎 Primo controllo ({_r.orario('primo_controllo'):%H:%M}), notte del {d:%d/%m} (G{g['numero']})"
    if not contano:
        await log(bot, f"{titolo}: nessun tabellino cambiato tra gli schierati" + (f" ({len(cambi)} cambi di altri)" if cambi else ""))
        return "nessun cambio"
    righe = "\n".join(CG.riga_cambio(a, b) for a, b in sorted(contano.values(), key=lambda x: (x[1] or x[0])["nome"]))
    await log(bot, f"{titolo}: ESPN ha cambiato {len(contano)} tabellini di giocatori schierati:\n{righe}")
    if _calcolata(s, g["numero"]) and config.gruppo_admin():
        await bot.send_message(chat_id=config.gruppo_admin(), parse_mode="HTML",
                               text=f"<b>{titolo}</b>: ESPN ha cambiato {len(contano)} "
                                    f"{'tabellino' if len(contano) == 1 else 'tabellini'} di giocatori schierati:\n{righe}\n\n"
                                    f"I valori nuovi sono già nel database: ricalcola per aggiornare risultati e foglio. "
                                    f"Il controllo finale (con la verifica su Yahoo) è alle {_r.orario('controllo_notte'):%H:%M}.",
                               reply_markup=K([[B("🔄 Ricalcola", callback_data=f"rc:re:{g['numero']}")]]))
    return f"{len(contano)} cambi"


async def job_primo_controllo(context: ContextTypes.DEFAULT_TYPE):
    """11:06: il primo controllo dell'ultima notte per le giornate senza live aperto (il live lo fa alle 11:05)."""
    from handlers import log
    from zoneinfo import ZoneInfo
    import congelamento as CG
    import live
    d = datetime.now(ZoneInfo("Europe/Rome")).date() - timedelta(days=1)
    s = config.stagione()
    g = CG.giornata_di(s, d)
    if not g:
        return
    st = live.stato(s, g["numero"]) or {}
    if st.get("message_id") and not st.get("chiuso"):
        return                                          # live aperto: ci ha pensato lui alle 11:05
    try:
        await primo_controllo(context.bot, d)
    except Exception as err:
        logger.exception("Primo controllo %s", d)
        await log(context.bot, f"⚠️ Primo controllo della notte del {d:%d/%m} non riuscito ({e(str(err))[:200]})")


async def job_controllo_finale(context: ContextTypes.DEFAULT_TYPE):
    """20:00 (orari.controllo_notte): controllo finale della notte appena passata, poi è congelata (v58)."""
    from handlers import log
    from zoneinfo import ZoneInfo
    d = datetime.now(ZoneInfo("Europe/Rome")).date() - timedelta(days=1)
    try:
        await controllo_notte(context.bot, d)
    except Exception as err:
        logger.exception("Controllo finale %s", d)
        await log(context.bot, f"⚠️ Controllo finale della notte del {d:%d/%m} non riuscito ({e(str(err))[:200]}): "
                               f"/controllo_notte {d:%d/%m} per rifarlo")


async def cb_controllo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """cn:ok:<id> (uguale su Yahoo) · cn:no:<id> (non corrisponde: tornano i valori di prima).
    Notti prima della stessa giornata, già congelate (niente salvato): cn:ag:<id> (su Yahoo è così: si salvano i valori
    di ESPN) · cn:la:<id> (si lascia com'è)."""
    from handlers import _chi, log
    import json
    import congelamento as CG
    from db import _COLONNE_TAB
    q = update.callback_query
    if not config.is_admin(update.effective_user.id):
        await q.answer("Solo admin.", show_alert=True)
        return
    _, azione, cid = q.data.split(":")
    c = db.q("SELECT * FROM lega_controlli_notte WHERE id = %s", (int(cid),), one=True)
    if not c or c["stato"] != ("da applicare" if azione in ("ag", "la") else "da verificare"):
        await q.answer("Già deciso." if not c or c["stato"] != "superato" else "Superata da una segnalazione più recente.",
                       show_alert=True)
        return
    ora = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Europe/Rome"))
    prima = c["prima"] if isinstance(c["prima"], dict) else json.loads(c["prima"])
    dopo = c["dopo"] if isinstance(c["dopo"], dict) else json.loads(c["dopo"])
    from registro import segna_sync

    def scrivi(righe: dict):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for chiave, riga in righe.items():
                    pid, atleta = chiave.split("|", 1)
                    cur.execute("DELETE FROM nba_tabellini WHERE partita = %s AND atleta = %s", (pid, atleta))
                    if riga:
                        cur.execute(f"INSERT INTO nba_tabellini ({', '.join(_COLONNE_TAB)}) VALUES "
                                    f"({', '.join('%(' + k + ')s' for k in _COLONNE_TAB)})", riga)
    if azione == "ag":
        scrivi(dopo)
        db.q("UPDATE lega_controlli_notte SET stato = 'aggiornato' WHERE id = %s", (c["id"],))
        segna_sync(update.effective_user, "admin", "notte congelata aggiornata come Yahoo", oggetto=f"notte del {c['data_et']:%d/%m}",
                   dopo=f"{len(dopo)} tabellini come ESPN")
        await log(context.bot, f"✅ Notte del {c['data_et']:%d/%m} (congelata): su Yahoo è come ESPN, {_chi(update)} ha salvato "
                               f"i valori nuovi ({len(dopo)} tabellini)")
        nota = (f"\n\n✅ <i>Su Yahoo è così: valori nuovi salvati da {e(_chi_nome(update))} alle {ora:%H:%M}</i>"
                + (f"\n<i>Ricalcola per aggiornare risultati e foglio.</i>" if c["giornata"] and _calcolata(config.stagione(), c["giornata"]) else ""))
    elif azione == "la":
        db.q("UPDATE lega_controlli_notte SET stato = 'lasciato' WHERE id = %s", (c["id"],))
        segna_sync(update.effective_user, "admin", "notte congelata lasciata com'era", oggetto=f"notte del {c['data_et']:%d/%m}")
        nota = f"\n\n❌ <i>Lasciata com'era da {e(_chi_nome(update))} alle {ora:%H:%M}</i>"
    elif azione == "ok":
        db.q("UPDATE lega_controlli_notte SET stato = 'uguale' WHERE id = %s", (c["id"],))
        segna_sync(update.effective_user, "admin", "controllo notte: uguale su Yahoo", oggetto=f"notte del {c['data_et']:%d/%m}",
                   dopo=f"{len(prima)} tabellini come ESPN")
        nota = f"\n\n✅ <i>Verificato uguale su Yahoo da {e(_chi_nome(update))} alle {ora:%H:%M}</i>"
    else:
        scrivi(prima)
        db.q("UPDATE lega_controlli_notte SET stato = 'tenuti_prima' WHERE id = %s", (c["id"],))
        segna_sync(update.effective_user, "admin", "controllo notte: non corrisponde a Yahoo", oggetto=f"notte del {c['data_et']:%d/%m}",
                   dopo=f"tornati i valori di prima per {len(prima)} tabellini")
        await log(context.bot, f"❌ Notte del {c['data_et']:%d/%m}: su Yahoo i cambi di ESPN non corrispondono, "
                               f"{_chi(update)} ha rimesso i valori di prima ({len(prima)} tabellini)")
        nota = (f"\n\n❌ <i>Non corrisponde a Yahoo: rimessi i valori di prima da {e(_chi_nome(update))} alle {ora:%H:%M}</i>"
                + (f"\n<i>Ricalcola per aggiornare risultati e foglio.</i>" if c["giornata"] and _calcolata(config.stagione(), c["giornata"]) else ""))
    await q.answer("Fatto")
    tasti = None
    if azione != "la" and c["giornata"] and _calcolata(config.stagione(), c["giornata"]):
        tasti = K([[B("🔄 Ricalcola", callback_data=f"rc:re:{c['giornata']}")]])
    try:
        await q.edit_message_text(q.message.text_html + nota, parse_mode="HTML", reply_markup=tasti)
    except Exception as err:
        logger.info("Controllo notte, messaggio: %s", err)


async def cmd_controllo_notte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/controllo_notte GG/MM (admin): rifà il controllo finale di una notte (riscarica anche se congelata)."""
    import congelamento as CG
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    d = CG.leggi_data((context.args or [""])[0])
    if not d or d >= CG.oggi_et():
        await msg.reply_text("Uso: /controllo_notte GG/MM (una notte NBA già finita, es. /controllo_notte 29/10)")
        return
    await msg.reply_text(f"⏳ Controllo della notte del {d:%d/%m}…")
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "controllo notte rifatto", oggetto=f"notte del {d:%d/%m}")
    esito = await controllo_notte(context.bot, d, chi=f"/controllo_notte di {_chi_nome(update)}", user=update.effective_user)
    await msg.reply_text(f"✅ Notte del {d:%d/%m}: {esito}.")


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
        import congelamento
        fermo = congelamento.congelata(s, n)
        await _riscarica(g)                             # le notti congelate restano come sono (v58)
        motivo = pronta(s, g)
        if motivo:
            await rispondi(f"❌ Giornata {n} non ancora calcolabile: {motivo}. Quando è pronta: /ricalcola {n}")
            return
        esito = await esegui(bot, s, n, chi, user=user)
        await rispondi(f"✅ Giornata {n} ricalcolata: proposta nuova nel gruppo admin ({esito})."
                       + (" Giornata congelata: coi tabellini che c'erano, niente riscaricato da ESPN." if fermo else ""))
    except Exception as err:
        logger.exception("Ricalcolo %s", n)
        await rispondi(f"⚠️ Ricalcolo della giornata {n} fallito: {err}. Riprova con /ricalcola {n}")


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
        _rp = lc["risultati"] if isinstance(lc["risultati"], list) else __import__("json").loads(lc["risultati"])
        diff = R.differenze(s, n, _rp)                  # prima di sovrascrivere i risultati convalidati
        live_esiti_prima = None
        try:
            import live as _lv
            live_esiti_prima = _lv._esiti(s, n) or None    # chi vinceva nella convalida di prima, per l'avviso sul canale
        except Exception:
            pass
        R.convalida(s, n, update.effective_user.id)
        from registro import segna_sync
        segna_sync(update.effective_user, "admin", "giornata convalidata", oggetto=f"giornata {n}",
                   prima=f"versione {lc['versione']} da convalidare", dopo="convalidata: risultati salvati")
        await q.answer("Convalidata")
        import foglio
        esito = await foglio.aggiorna(s)
        try:                                             # canale: risultati definitivi, via il live (Luca, 23/10)
            import live
            esito += "; " + await live.pubblica_definitivo(context.bot, s, n, _chi_nome(update), prima=live_esiti_prima)
        except Exception as err:
            logger.warning("Risultati definitivi sul canale G%s: %s", n, err)
            esito += f"; ⚠️ risultati definitivi non pubblicati sul canale ({str(err)[:120]})"
        ora = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Europe/Rome"))
        try:
            await q.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=q.message.chat_id, reply_to_message_id=q.message.message_id,
                                           text=f"✅ Giornata {n} convalidata da {_chi(update)} alle {ora:%H:%M}: risultati salvati, {e(esito)}."
                                                + R.testo_differenze(diff),
                                           parse_mode="HTML")
        except Exception as err:
            logger.info("Messaggio di convalida: %s", err)
        await log(context.bot, f"✅ Giornata {n} convalidata da {_chi(update)} (versione {lc['versione']}); {e(esito)}")
        return
    if azione == "re":
        await q.answer("Ricalcolo in corso…")
        # bottoni a risposta unica (Luca, 24 e 30/10): premuto Ricalcola, su qualsiasi messaggio (proposta compresa)
        # i bottoni spariscono subito e sotto resta chi l'ha avviato; la proposta nuova arriva a ricalcolo finito
        ora = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Europe/Rome"))
        try:
            await q.edit_message_text(q.message.text_html + f"\n\n🔄 <i>Ricalcolo avviato da {e(_chi_nome(update))} alle {ora:%H:%M}</i>",
                                      parse_mode="HTML", reply_markup=None)
        except Exception as err:
            logger.info("Bottone Ricalcola: %s", err)

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


async def cmd_storico_calcolo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/storico_calcolo N (admin, v6.9.0): ogni versione calcolata della giornata e cosa cambia tra una e l'altra."""
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    if not context.args or not context.args[0].lstrip("Gg").isdigit():
        await update.effective_message.reply_text("Uso: /storico_calcolo N (le versioni calcolate della giornata N)")
        return
    import live
    t = R.testo_storico(config.stagione(), int(context.args[0].lstrip("Gg")))
    for pezzo in live._pezzi(t):
        await update.effective_message.reply_text(pezzo, parse_mode="HTML")


def get_handlers() -> list:
    return [CommandHandler("ricalcola", cmd_ricalcola), CommandHandler("storico_calcolo", cmd_storico_calcolo), CommandHandler("dev_prova_calcolo", cmd_dev_prova_calcolo),
            CommandHandler("live", cmd_live), CommandHandler("controllo_notte", cmd_controllo_notte),
            CallbackQueryHandler(cb_controllo, pattern=r"^cn:(ok|no|ag|la):\d+$"),
            CallbackQueryHandler(cb_risultati, pattern=r"^rc:")]

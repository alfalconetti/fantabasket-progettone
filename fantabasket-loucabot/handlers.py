"""Comandi di loucabot.

GM e tutti:  /start, /calendario [N], /giornata [N], /guida (file)
Admin:       /importa_calendario (con il CSV allegato), /calendario_check, /nba_sync, /guida_admin
Dev:         /dev, /guida_dev, /dev_version, /job_status
"""
import html
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import calendario as cal
import config
import db
import nba

logger = logging.getLogger(__name__)
e = html.escape


async def log(bot, testo: str):
    """Una riga sul canale log di loucabot (la parte tecnica: import, sincronizzazioni, errori)."""
    if not config.canale_log():
        return
    try:
        await bot.send_message(chat_id=config.canale_log(), text=testo, parse_mode="HTML",
                               disable_web_page_preview=True)
    except Exception as err:
        logger.warning("Canale log: %s", err)


def _chi(update) -> str:
    u = update.effective_user
    return e(u.full_name or str(u.id)) if u else "?"


def _esito_sync(r: dict) -> str:
    return (f"{r['giorni']} giorni, {r['partite']} partite"
            + (f", ⚠️ {len(r['errori'])} giorni non scaricati ({', '.join(x.split(':')[0] for x in r['errori'][:5])})"
               if r["errori"] else ""))


def _numero(args) -> int | None:
    try:
        return int(args[0]) if args else None
    except ValueError:
        return None


def _riga_giornata(g: dict) -> str:
    righe = [f"📅 <b>Giornata {g['numero']}</b> · {g['dal']:%d/%m} – {g['al']:%d/%m}"]
    if g.get("prima_partita"):
        righe.append(f"⏰ Formazione e panchina entro <b>{cal.ora(g['prima_partita'])}</b> (prima partita NBA)")
    media = g["media"] if g.get("media") is not None else g.get("media_file")
    if media:
        righe.append(f"📉 A media (senza partite NBA): <b>{', '.join(media)}</b>")
    return "\n".join(righe)


async def cmd_calendario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = config.stagione()
    n = _numero(context.args)
    g = db.giornata(s, n) if n else cal.corrente(s)
    if not g:
        await update.effective_message.reply_text(
            "Nessuna giornata in calendario." if not db.giornate(s) else f"La giornata {n} non c'è.")
        return
    team = config.squadra_del_gm(update.effective_user.id)
    if not team:
        await _mostra_giornata(update, g)
        return
    righe = [_riga_giornata(g), ""]
    p = db.partita_squadra(s, g["numero"], team["id"])
    if p:
        casa = p["casa"] == team["id"]
        avv = p["trasferta"] if casa else p["casa"]
        righe.append(f"🏀 <b>{e(team['nome'])}</b> {'in casa (+3)' if casa else 'in trasferta'} contro "
                     f"<b>{e(config.nome(avv))}</b>")
    prossime = [x for x in db.giornate(s) if x["numero"] > g["numero"]][:3]
    if prossime:
        righe += ["", "<b>Le prossime</b>"]
        for x in prossime:
            p = db.partita_squadra(s, x["numero"], team["id"])
            if p:
                casa = p["casa"] == team["id"]
                righe.append(f"• G{x['numero']} {x['dal']:%d/%m}: {'🏠' if casa else '✈️'} "
                             f"{e(config.nome(p['trasferta'] if casa else p['casa']))}")
    righe += ["", "<i>/giornata per tutte le partite · /calendario N per un'altra giornata</i>"]
    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")


async def _mostra_giornata(update, g):
    righe = [_riga_giornata(g), ""]
    for p in db.partite_giornata(config.stagione(), g["numero"]):
        righe.append(f"• {e(config.nome(p['casa']))} – {e(config.nome(p['trasferta']))}")
    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")


async def cmd_giornata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = config.stagione()
    n = _numero(context.args)
    g = db.giornata(s, n) if n else cal.corrente(s)
    if not g:
        await update.effective_message.reply_text("Nessuna giornata da mostrare.")
        return
    await _mostra_giornata(update, g)


# ── admin ──────────────────────────────────────────────────────────────────────

async def cmd_importa_calendario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/importa_calendario come didascalia del CSV, o in risposta al messaggio con il CSV."""
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    doc = msg.document or (msg.reply_to_message.document if msg.reply_to_message else None)
    if not doc:
        await msg.reply_text("Manda il CSV del calendario con didascalia /importa_calendario, oppure rispondi "
                             "con /importa_calendario al messaggio che lo contiene.")
        return
    dati = await (await doc.get_file()).download_as_bytearray()
    try:
        testo = bytes(dati).decode("utf-8-sig")
    except UnicodeDecodeError:
        testo = bytes(dati).decode("latin-1")
    try:
        r = cal.importa(testo)
    except cal.ErroreCalendario as err:
        await msg.reply_text(f"❌ <b>Calendario non importato</b>\n\n{e(str(err))[:3500]}", parse_mode="HTML")
        return
    cambi = cal.ricalcola()
    righe = [f"✅ <b>Calendario {r['stagione']} importato</b>: {r['giornate']} giornate, {r['partite']} partite, "
             f"dal {r['dal']:%d/%m/%Y} al {r['al']:%d/%m/%Y}."]
    if r["dubbi"]:
        righe += ["", "Nomi abbinati non alla lettera, controlla:"] + [f"• {e(d)}" for d in r["dubbi"]]
    if not db.squadre_nba(r["stagione"]):
        righe += ["", "Partite NBA non ancora scaricate: lancia /nba_sync, poi /calendario_check."]
    else:
        righe += ["", "Controllo con le partite NBA: /calendario_check."]
    import foglio
    esito_foglio = await foglio.aggiorna(r["stagione"])
    righe += ["", e(esito_foglio[:1].upper() + esito_foglio[1:]) + "."]
    await msg.reply_text("\n".join(righe), parse_mode="HTML")
    logger.info("Calendario importato da %s: %s (%d cambi)", update.effective_user.id, r, len(cambi))
    await log(context.bot, f"📅 Calendario {r['stagione']} importato da {_chi(update)}: {r['giornate']} giornate, "
                           f"{r['partite']} partite ({e(doc.file_name or 'csv')})"
                           + (f"\nDifferenze con le partite NBA: {len(cal.differenze_file(r['stagione']))} giornate"
                              if db.squadre_nba(r["stagione"]) and cal.differenze_file(r["stagione"]) else "")
                           + f"\n{e(esito_foglio)}")


async def cmd_calendario_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    s = config.stagione()
    gg = db.giornate(s)
    if not gg:
        await update.effective_message.reply_text("Nessun calendario: /importa_calendario.")
        return
    cal.ricalcola(s)
    gg = db.giornate(s)
    senza = [g["numero"] for g in gg if g["media"] is None]
    diff = cal.differenze_file(s)
    righe = [f"🔎 <b>Calendario {s}</b>: {len(gg)} giornate, partite NBA della stagione: "
             f"{len(db.squadre_nba(s))} squadre"]
    righe.append("✅ Squadre a media: calcolate e calendario coincidono." if not diff else
                  "⚠️ <b>Squadre a media diverse dal calendario</b>\n" + "\n".join(f"• {e(d)}" for d in diff))
    if senza:
        righe.append(f"❔ Giornate senza partite NBA scaricate: {', '.join(map(str, senza))} (/nba_sync)")
    righe += ["", "<b>Scadenze</b>"] + [f"G{g['numero']}: {cal.ora(g['prima_partita'])}"
                                        + (f" · media {', '.join(g['media'])}" if g["media"] else "")
                                        for g in gg if g["prima_partita"]]
    from shared.messaggi import manda_lungo
    await manda_lungo(context.bot, update.effective_chat.id, "\n".join(righe), "calendario-check",
                      riassunto="\n".join(righe[:3]))


async def cmd_calendario_foglio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riscrive sul foglio Google Calendario intestazioni (squadre a media) e punteggi."""
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    import foglio
    await update.effective_message.reply_text("⏳ Aggiorno il foglio Calendario…")
    esito = await foglio.aggiorna(config.stagione())
    await update.effective_message.reply_text(("✅ " if not esito.startswith("⚠️") else "") + esito[:1].upper() + esito[1:])
    await log(context.bot, f"📄 /calendario_foglio di {_chi(update)}: {e(esito)}")


async def cmd_nba_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    await update.effective_message.reply_text("⏳ Scarico le partite NBA della stagione da ESPN (qualche minuto)…")
    r = await nba.sincronizza()
    cambi = cal.ricalcola()
    await log(context.bot, f"🏀 /nba_sync di {_chi(update)}: {_esito_sync(r)}"
                           + ("\nCambi: " + "; ".join(e(c) for c in cambi) if cambi else ""))
    await update.effective_message.reply_text(
        f"✅ {r['giorni']} giorni, {r['partite']} partite salvate."
        + (f"\n⚠️ {len(r['errori'])} giorni non scaricati: {', '.join(x.split(':')[0] for x in r['errori'][:10])}"
           if r["errori"] else "")
        + ("\nCambi nelle giornate in arrivo:\n" + "\n".join(cambi) if cambi else ""))


async def job_sync(context: ContextTypes.DEFAULT_TYPE):
    """Ogni mattina: i giorni vicini da ESPN, ricalcolo; se una giornata in arrivo cambia
    (prima partita, squadre a media) avviso al gruppo admin."""
    try:
        if not db.giornate(config.stagione()):
            return
        r = await nba.sincronizza(nba.giorni_vicini())
        cambi = cal.ricalcola()
        import handlers_calcolo as hc
        try:                                          # roster ESPN: la squadra NBA di adesso di ogni giocatore
            atleti = await nba.scarica_giocatori()
            db.salva_atleti(atleti)
            roster_txt = f"roster ESPN: {len(atleti)} giocatori"
        except Exception as err:
            roster_txt = f"roster ESPN non aggiornati ({e(str(err))[:100]})"
        tab = await hc.aggiorna_tabellini()
        inf = await hc.snapshot_infortuni() if config.snapshot_attivi() else f"snapshot infortunati fermi (fase {config.fase()})"
        tolte = db.pulisci_snapshot(nba.oggi_et())
        if tolte:
            inf += f" (snapshot più vecchi di {db.GIORNI_SNAPSHOT} giorni ridotti a uno per giorno: {tolte} righe tolte)"
        if cambi:
            import foglio
            inf += "; " + await foglio.aggiorna(config.stagione())
        await log(context.bot, f"🔄 Sincronizzazione delle 8:30: {_esito_sync(r)}"
                               + (f", {len(cambi)} cambi (avviso al gruppo admin)" if cambi else ", nessun cambio")
                               + f"; {hc.testo_tabellini(tab)}; {roster_txt}; {inf}")
        if cambi and config.gruppo_admin():
            await context.bot.send_message(
                chat_id=config.gruppo_admin(), parse_mode="HTML",
                text="📅 <b>Calendario: cambi dalle partite NBA</b>\n\n" + "\n".join(f"• {e(c)}" for c in cambi))
    except Exception as err:
        logger.exception("job_sync")
        await log(context.bot, f"⚠️ Sincronizzazione delle 8:30 fallita: {e(str(err))[:500]}")
        if config.dev_id():
            try:
                await context.bot.send_message(chat_id=config.dev_id(), text=f"⚠️ loucabot job_sync: {err}")
            except Exception:
                pass


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = ("<b>loucabot</b> — calendario e punteggi della lega. Guida completa: /guida\n\n"
             "/calendario — la tua giornata: avversario, casa o trasferta, entro quando mettere la formazione, "
             "chi è a media, le prossime giornate. /calendario N per un'altra giornata\n"
             "/giornata [N] — tutte le partite di una giornata")
    if config.is_admin(update.effective_user.id):
        testo += ("\n\n<b>Admin</b>\n/importa_calendario — col CSV allegato (sostituisce quello della stagione)\n"
                  "/calendario_check — scadenze e squadre a media, confronto col calendario\n"
                  "/nba_sync — riscarica le partite NBA della stagione da ESPN\n"
                  "/calendario_foglio — riscrive squadre a media e punteggi sul foglio Calendario\n\n"
                  "<b>Calcolo</b>\n/fantapunti [N] — fantapunti della giornata dei giocatori a roster\n"
                  "/set_valid_status GIOCATORE N — lo status che vale per il calcolo, tra quelli degli snapshot\n"
                  "/ricalcola N — riscarica i tabellini, ricalcola la giornata e la ripropone da convalidare\n"
                  "/tabellini — scarica i tabellini delle partite finite che mancano\n"
                  "/espn_giocatori — roster NBA da ESPN e abbinamento con l'anagrafica\n"
                  "/espn_mancanti — giocatori a roster senza id ESPN\n"
                  "/espn_abbina ID_GIOCATORE ID_ESPN — abbinamento a mano\n\n"
                  "Guida admin completa: /guida_admin")
    await update.effective_message.reply_text(testo, parse_mode="HTML")


# ── guide e comandi dev ────────────────────────────────────────────────────────

async def _manda_guida(update, context, file: str, titolo: str):
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", file)
    try:
        with open(path, "rb") as f:
            await context.bot.send_document(chat_id=update.effective_user.id, document=f,
                                            filename=f"loucabot_{file}", caption=titolo)
    except Exception as err:
        await update.effective_message.reply_text(f"❌ Guida non inviata: {err} (hai mai scritto al bot in privato?)")


async def cmd_guida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _manda_guida(update, context, "guida_gm.md", "📖 Guida GM — loucabot")


async def cmd_guida_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    await _manda_guida(update, context, "guida_admin.md", "📖 Guida admin — loucabot")


def _is_dev(uid) -> bool:
    return bool(config.dev_id()) and int(uid) == config.dev_id()


async def cmd_guida_dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_dev(update.effective_user.id):
        await _manda_guida(update, context, "guida_dev.md", "🛠 Guida dev — loucabot")


async def cmd_dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    await update.effective_message.reply_text(
        "<b>Comandi dev — loucabot</b>\n\n"
        "/guida_dev — la guida tecnica (file .md)\n"
        "/dev_version — versione del bot\n"
        "/job_status — job programmati e prossima esecuzione\n"
        "/dev_log [N] — ultime N righe di log in memoria (30)\n"
        "/dev_pg — connessione a PostgreSQL\n"
        "/dev_prova_calcolo DAL AL — prova del calcolo su notti NBA già giocate (tab Calcolo G0, solo a te)\n"
        "/dev_prova_live [GG/MM/AAAA …] — prova del live su notti vere (anche preseason), solo a te e niente nel database; stop per fermarla\n"
        "/dev_giornata [N] — stato di una giornata: date, scadenza, squadre a media, partite NBA, "
        "tabellini, snapshot degli infortunati, risultati\n"
        "/reboot — riavvia il bot\n\n"
        "Tutti i comandi admin: /guida_admin", parse_mode="HTML")


async def cmd_dev_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_dev(update.effective_user.id):
        await update.effective_message.reply_text(f"📅 loucabot {config.versione()}")


async def cmd_job_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_dev(update.effective_user.id):
        return
    jobs = [j for j in (context.job_queue.jobs() if context.job_queue else []) if j.next_t]
    righe = [f"• {j.name}: {cal.ora(j.next_t)}" for j in sorted(jobs, key=lambda j: j.next_t)]
    await update.effective_message.reply_text("⏱ <b>Job</b>\n" + ("\n".join(e(r) for r in righe) or "nessuno"),
                                              parse_mode="HTML")


def get_handlers() -> list:
    import handlers_calcolo
    return handlers_calcolo.get_handlers() + [
        CommandHandler("start", cmd_start),
        CommandHandler("guida", cmd_guida),
        CommandHandler("guida_admin", cmd_guida_admin),
        CommandHandler("guida_dev", cmd_guida_dev),
        CommandHandler("dev", cmd_dev),
        CommandHandler("dev_version", cmd_dev_version),
        CommandHandler("job_status", cmd_job_status),
        CommandHandler("calendario", cmd_calendario),
        CommandHandler("giornata", cmd_giornata),
        CommandHandler("importa_calendario", cmd_importa_calendario),
        MessageHandler(filters.Document.ALL & filters.CaptionRegex(r"^/importa_calendario"), cmd_importa_calendario),
        CommandHandler("calendario_check", cmd_calendario_check),
        CommandHandler("nba_sync", cmd_nba_sync),
        CommandHandler("calendario_foglio", cmd_calendario_foglio),
    ]

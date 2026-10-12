"""Comandi di loucabot.

GM e tutti:  /calendario [N], /giornata [N], /guida
Admin:       /importa_calendario (con il CSV allegato), /calendario_check, /nba_sync
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
    await msg.reply_text("\n".join(righe), parse_mode="HTML")
    logger.info("Calendario importato da %s: %s (%d cambi)", update.effective_user.id, r, len(cambi))
    await log(context.bot, f"📅 Calendario {r['stagione']} importato da {_chi(update)}: {r['giornate']} giornate, "
                           f"{r['partite']} partite ({e(doc.file_name or 'csv')})"
                           + (f"\nDifferenze con le partite NBA: {len(cal.differenze_file(r['stagione']))} giornate"
                              if db.squadre_nba(r["stagione"]) and cal.differenze_file(r["stagione"]) else ""))


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
        tab = await hc.aggiorna_tabellini()
        inf = await hc.foto_infortuni()
        await log(context.bot, f"🔄 Sincronizzazione delle 8:30: {_esito_sync(r)}"
                               + (f", {len(cambi)} cambi (avviso al gruppo admin)" if cambi else ", nessun cambio")
                               + f"; {hc.testo_tabellini(tab)}; {inf}")
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


async def cmd_guida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = ("<b>loucabot</b> — calendario della lega\n\n"
             "/calendario — la tua giornata: avversario, casa o trasferta, entro quando mettere la formazione, "
             "chi è a media, le prossime giornate. /calendario N per un'altra giornata\n"
             "/giornata [N] — tutte le partite di una giornata")
    if config.is_admin(update.effective_user.id):
        testo += ("\n\n<b>Admin</b>\n/importa_calendario — col CSV allegato (sostituisce quello della stagione)\n"
                  "/calendario_check — scadenze e squadre a media, confronto col calendario\n"
                  "/nba_sync — riscarica le partite NBA della stagione da ESPN\n\n"
                  "<b>Calcolo</b>\n/fantapunti [N] — fantapunti della giornata dei giocatori a roster\n"
                  "/tabellini — scarica i tabellini delle partite finite che mancano\n"
                  "/espn_giocatori — roster NBA da ESPN e abbinamento con l'anagrafica\n"
                  "/espn_mancanti — giocatori a roster senza id ESPN\n"
                  "/espn_abbina ID_GIOCATORE ID_ESPN — abbinamento a mano")
    await update.effective_message.reply_text(testo, parse_mode="HTML")


def get_handlers() -> list:
    import handlers_calcolo
    return handlers_calcolo.get_handlers() + [
        CommandHandler(["start", "guida"], cmd_guida),
        CommandHandler("calendario", cmd_calendario),
        CommandHandler("giornata", cmd_giornata),
        CommandHandler("importa_calendario", cmd_importa_calendario),
        MessageHandler(filters.Document.ALL & filters.CaptionRegex(r"^/importa_calendario"), cmd_importa_calendario),
        CommandHandler("calendario_check", cmd_calendario_check),
        CommandHandler("nba_sync", cmd_nba_sync),
    ]

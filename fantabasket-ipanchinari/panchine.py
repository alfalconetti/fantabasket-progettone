"""
Panchine: il GM manda al bot, in privato, il messaggio di sempre (5 righe, soprannomi
compresi, titolo facoltativo sopra). Il bot abbina le righe ai giocatori della squadra, gli
mostra l'anteprima con i nomi veri e i bottoni per le righe dubbie, e alla conferma pubblica
sul canale Panchinari **solo le righe come le ha scritte il GM** (i nomi "High CAI").

Vale per la prossima giornata con la scadenza non ancora passata; fino alla scadenza si può
rimandare quante volte si vuole (vale l'ultima, sul canale esce come aggiornamento).
Le righe confermate diventano alias della squadra: la volta dopo si riconoscono da sole.

Callback: pb:r:<bozza>:<i> scegli la riga i · pb:s:<bozza>:<i>:<gid> giocatore scelto ·
pb:t:<bozza>:<i> tutta la rosa per la riga i · pb:ok:<bozza> pubblica · pb:no:<bozza> annulla ·
pb:v:<bozza> torna all'anteprima. Builder (/build_panchina): pb:b:<bozza>:<gid> aggiungi ·
pb:u:<bozza> togli l'ultimo · pb:bv:<bozza> all'anteprima. CAI mode (dall'anteprima del builder):
pb:cai:<bozza> inizia (titolo, poi i soprannomi uno alla volta, risposte come messaggi) ·
pb:cs:<bozza> salta · pb:cf:<bozza> fine.
Un panchinaro che nel quintetto del bot è titolare non blocca: fa fede Yahoo, il bot lo segnala
al GM (può aggiornare il quintetto, o ci pensa un admin) e sul canale log.
"""
import logging

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

import abbina
import config
import db
from comune import aperta, chi, e, log, ora, prossima_giornata

logger = logging.getLogger(__name__)


def _nomi(roster: list[dict]) -> dict[int, str]:
    return {g["id"]: g["nome_common"] for g in roster}


def problemi(b: dict, roster: list[dict]) -> list[str]:
    """Cosa impedisce di pubblicare la bozza (vuoto = si può)."""
    d = b["dati"]
    nomi = _nomi(roster)
    out = []
    scelti = [r.get("scelto") for r in d["righe"]]
    for i, r in enumerate(d["righe"], 1):
        if not r.get("scelto"):
            out.append(f"riga {i}: giocatore da scegliere")
        elif r["scelto"] not in nomi:
            out.append(f"riga {i}: non è più nella tua squadra")
    doppi = {g for g in scelti if g and scelti.count(g) > 1}
    for g in doppi:
        out.append(f"{nomi.get(g, g)} è in panchina due volte")
    return out


def avvisi(b: dict, roster: list[dict]) -> list[str]:
    """Cose da segnalare che non impediscono di pubblicare: un panchinaro che nel quintetto del
    bot è titolare (fa fede Yahoo: il quintetto lo può sistemare il GM o un admin)."""
    nomi = _nomi(roster)
    tit = {gid: ruolo for ruolo, gid in db.quintetto(b["team_id"]).items()}
    return [f"{nomi.get(g, g)} risulta nel tuo quintetto ({tit[g]}): se vuoi aggiornalo con /quintetto, "
            "altrimenti se ne occupa un admin"
            for g in dict.fromkeys(r.get("scelto") for r in b["dati"]["righe"]) if g in tit]


def anteprima(b: dict) -> tuple[str, K]:
    d = b["dati"]
    roster = db.roster(b["team_id"], b["stagione"])
    nomi = _nomi(roster)
    g = db.giornata(b["stagione"], b["giornata"])
    righe = [f"🪑 <b>Panchina di {e(config.nome(b['team_id']))} per la giornata {b['giornata']}</b>",
             f"Scadenza: {ora(g['prima_partita']) if g else '?'}", ""]
    if d.get("titolo"):
        righe += [f"<i>{e(d['titolo'])}</i>", ""]
    for i, r in enumerate(d["righe"], 1):
        chi_ = f"<b>{e(nomi.get(r['scelto'], '?'))}</b>" if r.get("scelto") else "❓ <b>da scegliere</b>"
        righe.append(f"{i}. {e(r['testo'])} → {chi_}")
    pb = problemi(b, roster)
    av = avvisi(b, roster)
    if pb:
        righe += ["", "⚠️ " + "\n⚠️ ".join(e(x) for x in pb)]
    if av:
        righe += ["", "ℹ️ " + "\nℹ️ ".join(e(x) for x in av)]
    if not pb:
        righe += ["", "Sul canale usciranno le righe come le hai scritte tu."]
    tasti = []
    for i, r in enumerate(d["righe"], 1):            # dubbi: i candidati direttamente come bottoni
        if r.get("scelto"):
            continue
        cand = [c for c in r.get("candidati", []) if c in nomi][:3]
        tasti.append([B(f"{i}: {nomi[c]}", callback_data=f"pb:s:{b['id']}:{i - 1}:{c}") for c in cand]
                     + [B(f"{i}: 📋 altri" if cand else f"{i}: 📋 scegli", callback_data=f"pb:t:{b['id']}:{i - 1}")])
    tasti.append([B(f"{'❓' if not r.get('scelto') else '✏️'} {i}", callback_data=f"pb:r:{b['id']}:{i - 1}")
                  for i, r in enumerate(d["righe"], 1)])
    fondo = [B("❌ Annulla", callback_data=f"pb:no:{b['id']}")]
    if not pb:
        fondo.insert(0, B("✅ Pubblica", callback_data=f"pb:ok:{b['id']}"))
    if d.get("builder") and d["righe"]:
        tasti.append([B("😎 CAI mode: titolo e soprannomi", callback_data=f"pb:cai:{b['id']}")])
    tasti.append(fondo)
    return "\n".join(righe), K(tasti)


def crea_bozza(chat_id: int, team_id: str, testo: str, fonte: str = "gm") -> tuple[dict | None, str | None]:
    """(bozza, errore)."""
    s = config.stagione()
    g = prossima_giornata(s)
    if not g:
        return None, "Non c'è una giornata aperta: il calendario non è ancora caricato o la stagione è finita."
    titolo, righe, err = abbina.leggi_messaggio(testo)
    if err:
        return None, err
    roster = db.roster(team_id, s)
    if not roster:
        return None, "Nessun giocatore a roster per questa squadra."
    abbinate = abbina.abbina_panchina(righe, roster, db.alias(team_id))
    dati = {"titolo": titolo, "righe": abbinate}
    bid = db.nuova_bozza(chat_id, team_id, s, g["numero"], dati, fonte)
    return db.bozza(bid), None


async def manda_anteprima(msg, b: dict):
    testo, tasti = anteprima(b)
    await msg.reply_text(testo, parse_mode="HTML", reply_markup=tasti)


# ── messaggio del GM ───────────────────────────────────────────────────────────

async def msg_panchina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ogni messaggio di testo in privato di un GM con almeno 2 righe è una panchina (se non è la
    risposta a una domanda della CAI mode)."""
    msg = update.effective_message
    b = db.bozza_cai(update.effective_chat.id)
    if b and len([r for r in (msg.text or "").splitlines() if r.strip()]) < 3:
        await risposta_cai(msg, b)
        return
    if b:                                   # 3 righe o più: è una panchina nuova, la CAI mode finisce
        db.chiudi_bozza(b["id"])
    team = config.squadra_del_gm(update.effective_user.id)
    if not team:
        if config.is_admin(update.effective_user.id):
            await msg.reply_text("Per la panchina di una squadra: /panchina_admin SQUADRA e sotto le righe.")
        else:
            await msg.reply_text("Non risulti GM di nessuna squadra: scrivi a un admin.")
        return
    if len([r for r in (msg.text or "").splitlines() if r.strip()]) < 2:
        await msg.reply_text("Per la panchina mandami le righe dei panchinari, una per riga, in ordine "
                             "(ed eventualmente il titolo sopra, separato da una riga vuota). Guida: /guida")
        return
    b, err = crea_bozza(update.effective_chat.id, team["id"], msg.text)
    if err:
        await msg.reply_text(f"❌ {err}")
        return
    await manda_anteprima(msg, b)


# ── bottoni ────────────────────────────────────────────────────────────────────

def _puo(update, b) -> bool:
    uid = update.effective_user.id
    return config.is_admin(uid) or uid in config.gm_ids(b["team_id"])


async def cb_panchina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parti = q.data.split(":")
    azione, bid = parti[1], int(parti[2])
    b = db.bozza(bid)
    if not b or b["chiusa"]:
        await q.answer("Questa panchina non è più modificabile: rimandala.", show_alert=True)
        return
    if not _puo(update, b):
        await q.answer("Non è la tua squadra.", show_alert=True)
        return
    roster = db.roster(b["team_id"], b["stagione"])
    nomi = _nomi(roster)
    d = b["dati"]
    if azione in ("cai", "cs", "cf"):                     # CAI mode
        if azione == "cai":
            d["cai_passo"] = 0
            db.aggiorna_bozza(bid, d)
            b = db.bozza(bid)
        elif azione == "cs" and d.get("cai_passo") is not None:
            b = avanza_cai(b)
        else:
            d["cai_passo"] = None
            db.aggiorna_bozza(bid, d)
            b = db.bozza(bid)
        await q.answer()
        testo, tasti = domanda_cai(b) if b["dati"].get("cai_passo") is not None else anteprima(b)
        await q.edit_message_text(testo, parse_mode="HTML", reply_markup=tasti)
        return
    if azione in ("b", "u", "bv"):                        # builder
        if azione == "b":
            gid = int(parti[3])
            if gid in nomi and gid not in {r["scelto"] for r in d["righe"]} and len(d["righe"]) < abbina.MAX_PANCHINA:
                d["righe"].append({"testo": nomi[gid], "candidati": [gid], "scelto": gid, "certo": True})
        elif azione == "u" and d["righe"]:
            d["righe"].pop()
        db.aggiorna_bozza(bid, d)
        b = db.bozza(bid)
        await q.answer()
        if azione == "bv" or len(d["righe"]) >= abbina.MAX_PANCHINA:
            testo, tasti = anteprima(b)
        else:
            testo, tasti = builder(b, roster)
        await q.edit_message_text(testo, parse_mode="HTML", reply_markup=tasti)
        return
    if azione in ("r", "t"):
        i = int(parti[3])
        r = d["righe"][i]
        altri = {x.get("scelto") for j, x in enumerate(d["righe"]) if j != i}
        if azione == "r" and r["candidati"]:
            ids = [c for c in r["candidati"] if c in nomi]
            extra = [[B("📋 Tutta la rosa", callback_data=f"pb:t:{bid}:{i}")]]
        else:
            ids = [g["id"] for g in roster if g["id"] not in altri]
            extra = []
        tasti = [[B(nomi[g] + (" (" + (next((x["ruolo"] for x in roster if x["id"] == g), "") or "") + ")"),
                    callback_data=f"pb:s:{bid}:{i}:{g}")] for g in ids]
        tasti += extra + [[B("↩️ Indietro", callback_data=f"pb:v:{bid}")]]
        await q.answer()
        await q.edit_message_text(f"Riga {i + 1}: «{e(r['testo'])}» — chi è?", parse_mode="HTML", reply_markup=K(tasti))
        return
    if azione == "s":
        i, gid = int(parti[3]), int(parti[4])
        if gid not in nomi:
            await q.answer("Non è più nella tua squadra.", show_alert=True)
            return
        d["righe"][i].update(scelto=gid, certo=True)
        db.aggiorna_bozza(bid, d)
        b = db.bozza(bid)
    if azione in ("s", "v"):
        await q.answer()
        testo, tasti = anteprima(b)
        await q.edit_message_text(testo, parse_mode="HTML", reply_markup=tasti)
        return
    if azione == "no":
        db.chiudi_bozza(bid)
        await q.answer()
        await q.edit_message_text("Panchina annullata: non è stato pubblicato niente.")
        return
    if azione == "ok":
        await pubblica(update, context, b)


def testo_canale(team_id: str, giornata: int, titolo: str | None, righe: list[dict], aggiornata: bool) -> str:
    out = [f"<b>{e(config.nome(team_id))}</b> · giornata {giornata}" + (" · 🔁 aggiornata" if aggiornata else "")]
    if titolo:
        out.append(f"<i>{e(titolo)}</i>")
    out += [f"{i}. {e(r['testo'])}" for i, r in enumerate(righe, 1)]
    return "\n".join(out)


async def _scrivi_canale(bot, canale, testo: str, vecchio: int | None) -> int:
    """Una panchina per squadra e giornata sul canale: se c'è già, si modifica quel messaggio.
    Un nuovo messaggio solo se il vecchio non si può più modificare (cancellato a mano)."""
    if vecchio:
        try:
            await bot.edit_message_text(chat_id=canale, message_id=vecchio, text=testo, parse_mode="HTML")
            return vecchio
        except Exception as err:
            if "not modified" in str(err).lower():
                return vecchio
            logger.warning("Canale Panchinari: non riesco a modificare il messaggio %s (%s), ne mando uno nuovo", vecchio, err)
    m = await bot.send_message(chat_id=canale, text=testo, parse_mode="HTML")
    return m.message_id


async def pubblica(update, context, b: dict):
    q = update.callback_query
    g = db.giornata(b["stagione"], b["giornata"])
    if not g or not aperta(g):
        db.chiudi_bozza(b["id"])
        await q.answer("La scadenza è passata.", show_alert=True)
        await q.edit_message_text("⏰ La scadenza di questa giornata è passata mentre confermavi: la panchina non è "
                                  "stata pubblicata. Rimandala: varrà per la giornata successiva; per questa scrivi a un admin.")
        return
    roster = db.roster(b["team_id"], b["stagione"])
    pb = problemi(b, roster)
    if pb:
        await q.answer("Ci sono ancora problemi: " + pb[0][:150], show_alert=True)
        return
    righe = [{"giocatore_id": r["scelto"], "testo": r["testo"]} for r in b["dati"]["righe"]]
    precedente = db.panchina(b["stagione"], b["giornata"], b["team_id"])
    testo = testo_canale(b["team_id"], b["giornata"], b["dati"].get("titolo"), righe, bool(precedente))
    mid = None
    canale = config.canale_panchinari()
    if canale:
        try:
            mid = await _scrivi_canale(context.bot, canale, testo, (precedente or {}).get("messaggio_canale"))
        except Exception as err:
            logger.warning("Canale Panchinari: %s", err)
            await q.answer("Non riesco a scrivere sul canale Panchinari: avvisa un admin.", show_alert=True)
            return
    db.salva_panchina(b["stagione"], b["giornata"], b["team_id"], b["dati"].get("titolo"), righe,
                      da=update.effective_user.id, fonte=b["fonte"], messaggio_canale=mid)
    for r in b["dati"]["righe"]:
        db.salva_alias(b["team_id"], abbina.chiave(r["testo"]), r["scelto"])
    db.chiudi_bozza(b["id"])
    nomi = _nomi(roster)
    av = avvisi(b, roster)
    await q.answer("Pubblicata")
    await q.edit_message_text(f"✅ Panchina della giornata {b['giornata']} pubblicata"
                              + (" (sostituisce la precedente)" if precedente else "") + ".\n\n"
                              + "\n".join(f"{i}. {e(r['testo'])} → {e(nomi.get(r['giocatore_id'], '?'))}"
                                          for i, r in enumerate(righe, 1))
                              + ("\n\nℹ️ " + "\nℹ️ ".join(e(x) for x in av) if av else ""), parse_mode="HTML")
    await log(context.bot, f"🪑 Panchina G{b['giornata']} {e(config.nome(b['team_id']))} da {chi(update)}"
                           + (" (admin)" if b["fonte"] == "admin" else "") + ": "
                           + ", ".join(e(nomi.get(r["giocatore_id"], "?")) for r in righe)
                           + "".join(f"\n⚠️ {e(x.split(':')[0])}: titolare nel quintetto del bot" for x in av))


# ── CAI mode: titolo e soprannomi per la panchina del builder ─────────────────
# dati["cai_passo"]: 0 = si aspetta il titolo, i = il soprannome della riga i; None = finita.

def domanda_cai(b: dict) -> tuple[str, K]:
    d = b["dati"]
    passo = d["cai_passo"]
    if passo == 0:
        testo = ("😎 <b>CAI mode</b>\n\nScrivimi il <b>titolo</b> della panchina"
                 + (f" (ora: <i>{e(d['titolo'])}</i>)" if d.get("titolo") else "") + ".")
    else:
        r = d["righe"][passo - 1]
        nome = _nomi(db.roster(b["team_id"], b["stagione"])).get(r["scelto"], "?")
        testo = (f"😎 Soprannome per <b>{e(nome)}</b> ({passo}/{len(d['righe'])})"
                 + (f"\nOra: <i>{e(r['testo'])}</i>" if r["testo"] != nome else "") + "\n\nScrivimelo qui.")
    return testo, K([[B("⏭️ Salta", callback_data=f"pb:cs:{b['id']}"), B("✅ Fine", callback_data=f"pb:cf:{b['id']}")]])


def avanza_cai(b: dict) -> dict:
    d = b["dati"]
    d["cai_passo"] = d["cai_passo"] + 1 if d["cai_passo"] < len(d["righe"]) else None
    db.aggiorna_bozza(b["id"], d)
    return db.bozza(b["id"])


async def risposta_cai(msg, b: dict):
    testo = (msg.text or "").strip()
    d = b["dati"]
    if testo:
        if d["cai_passo"] == 0:
            d["titolo"] = testo[:300]
        else:
            d["righe"][d["cai_passo"] - 1]["testo"] = " ".join(testo.split())[:100]
        db.aggiorna_bozza(b["id"], d)
    b = avanza_cai(db.bozza(b["id"]))
    if b["dati"].get("cai_passo") is None:
        await manda_anteprima(msg, b)
    else:
        t, k = domanda_cai(b)
        await msg.reply_text(t, parse_mode="HTML", reply_markup=k)


# ── builder coi bottoni (/build_panchina) ──────────────────────────────────────

def builder(b: dict, roster: list[dict]) -> tuple[str, K]:
    """Panchinari uno alla volta, in ordine: solo giocatori della squadra non nel quintetto e non
    ancora scelti. Sul canale escono i loro nomi."""
    d = b["dati"]
    scelti = [r["scelto"] for r in d["righe"]]
    titolari = set(db.quintetto(b["team_id"]).values())
    liberi = [g for g in roster if g["id"] not in titolari and g["id"] not in scelti]
    g = db.giornata(b["stagione"], b["giornata"])
    righe = [f"🪑 <b>Panchina di {e(config.nome(b['team_id']))} per la giornata {b['giornata']}</b>",
             f"Scadenza: {ora(g['prima_partita']) if g else '?'}", ""]
    righe += [f"{i}. {e(r['testo'])}" for i, r in enumerate(d["righe"], 1)] or ["(ancora nessuno)"]
    righe += ["", f"Scegli il panchinaro n. {len(scelti) + 1}:" if len(scelti) < abbina.MAX_PANCHINA else ""]
    tasti = [[B(f"{x['nome_common']}" + (f" ({x['ruolo']})" if x.get("ruolo") else ""),
                callback_data=f"pb:b:{b['id']}:{x['id']}")] for x in liberi]
    fondo = []
    if scelti:
        fondo += [B("↩️ Togli l'ultimo", callback_data=f"pb:u:{b['id']}"), B("➡️ Anteprima", callback_data=f"pb:bv:{b['id']}")]
    fondo.append(B("❌ Annulla", callback_data=f"pb:no:{b['id']}"))
    return "\n".join(righe), K(tasti + [fondo])


async def apri_builder(msg, chat_id: int, team_id: str, fonte: str = "gm"):
    s = config.stagione()
    g = prossima_giornata(s)
    if not g:
        await msg.reply_text("Non c'è una giornata aperta.")
        return
    bid = db.nuova_bozza(chat_id, team_id, s, g["numero"], {"titolo": None, "righe": [], "builder": True}, fonte)
    testo, tasti = builder(db.bozza(bid), db.roster(team_id, s))
    await msg.reply_text(testo, parse_mode="HTML", reply_markup=tasti)


async def cmd_build_panchina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team = config.squadra_del_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("Non risulti GM di nessuna squadra. Admin: /panchina_admin SQUADRA.")
        return
    await apri_builder(update.effective_message, update.effective_chat.id, team["id"])


# ── comandi ────────────────────────────────────────────────────────────────────

async def cmd_panchina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/panchina: la panchina della prossima giornata, con i nomi veri."""
    team = config.squadra_del_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("Non risulti GM di nessuna squadra.")
        return
    g = prossima_giornata()
    if not g:
        await update.effective_message.reply_text("Non c'è una giornata aperta.")
        return
    p = db.panchina(config.stagione(), g["numero"], team["id"])
    if not p:
        await update.effective_message.reply_text(
            f"Per la giornata {g['numero']} (scadenza {ora(g['prima_partita'])}) non hai ancora mandato la panchina: "
            "mandami le righe, una per riga.")
        return
    nomi = _nomi(db.roster(team["id"], config.stagione()))
    await update.effective_message.reply_text(
        f"🪑 Panchina della giornata {g['numero']} (scadenza {ora(g['prima_partita'])})\n"
        + (f"<i>{e(p['titolo'])}</i>\n" if p["titolo"] else "")
        + "\n".join(f"{i}. {e(r['testo'])} → {e(nomi.get(r['giocatore_id'], '?'))}" for i, r in enumerate(p["righe"], 1))
        + "\n\nPer cambiarla mandami di nuovo le righe.", parse_mode="HTML")


async def cmd_panchina_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/panchina_admin SQUADRA e sotto le righe: la panchina per conto di una squadra."""
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    righe = (msg.text or "").split("\n")
    prima = righe[0].split(maxsplit=1)
    from shared.squadre import cerca_squadra
    team = cerca_squadra(prima[1], config.squadre()) if len(prima) > 1 else None
    if not team:
        await msg.reply_text("Uso: /panchina_admin SQUADRA (nome o id) nella prima riga, sotto le righe della panchina; "
                             "senza righe si apre il builder coi bottoni.")
        return
    if not [r for r in righe[1:] if r.strip()]:
        await apri_builder(msg, update.effective_chat.id, team["id"], fonte="admin")
        return
    b, err = crea_bozza(update.effective_chat.id, team["id"], "\n".join(righe[1:]), fonte="admin")
    if err:
        await msg.reply_text(f"❌ {err}")
        return
    await manda_anteprima(msg, b)


def get_handlers() -> list:
    from telegram.ext import CommandHandler
    return [
        CommandHandler("panchina", cmd_panchina, filters=filters.ChatType.PRIVATE),
        CommandHandler("build_panchina", cmd_build_panchina, filters=filters.ChatType.PRIVATE),
        CommandHandler("panchina_admin", cmd_panchina_admin),
        CallbackQueryHandler(cb_panchina, pattern=r"^pb:"),
        MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, msg_panchina),
    ]


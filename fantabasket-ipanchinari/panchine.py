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
pb:u:<bozza> togli l'ultimo (al quinto si passa all'anteprima). CAI mode (dall'anteprima del builder):
pb:cai:<bozza> inizia (titolo, poi i soprannomi uno alla volta, risposte come messaggi) ·
pb:cs:<bozza> salta · pb:cf:<bozza> fine.
Editor (/edit, o 🛠 dall'anteprima): pb:e:<bozza> apri · pb:n:<bozza>:<i> soprannome della riga i (risposta come
messaggio, ♻️ pb:cn:<bozza> torna al nome vero) · pb:su / pb:gi:<bozza>:<i> sposta su / giù · pb:sw:<bozza>:<i>
cambia · pb:sp:<bozza>:<i>:<gid> con gid (se è già in panchina le due righe si scambiano il posto, ognuna col suo
soprannome; se no entra al posto della riga i col suo nome).
La panchina è sempre di 5 giocatori, mai meno. Un panchinaro che nel quintetto del bot è titolare
non blocca: fa fede Yahoo, il bot lo segnala al GM (può aggiornare il quintetto, non è obbligatorio:
è un favore agli admin) e sul canale log.
"""
import logging

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

import abbina
import config
import db
from shared import regole
import comune
from comune import FAVORE, ROMA, adesso, aperta, chi, e, log, ora, prossima_giornata, stati, testo_panchine_bloccate

logger = logging.getLogger(__name__)


def _nomi(roster: list[dict]) -> dict[int, str]:
    return {g["id"]: g["nome_common"] for g in roster}


def problemi(b: dict, roster: list[dict]) -> list[str]:
    """Cosa impedisce di pubblicare la bozza (vuoto = si può)."""
    d = b["dati"]
    nomi = _nomi(roster)
    out = []
    if len(d["righe"]) != regole.giocatori_panchina():
        out.append(f"la panchina è di {regole.giocatori_panchina()} giocatori, mai meno: qui ce ne sono {len(d['righe'])}")
    scelti = [r.get("scelto") for r in d["righe"]]
    for i, r in enumerate(d["righe"], 1):
        if not r.get("scelto"):
            out.append(f"riga {i}: giocatore da scegliere")
        elif r["scelto"] not in nomi:
            out.append(f"riga {i}: non è più nella tua squadra")
    if abbina.ripetute([r["testo"] for r in d["righe"]]):           # es. due soprannomi uguali in CAI mode
        out.append("righe duplicate: ogni panchinaro va scritto in modo diverso")
    doppi = {g for g in scelti if g and scelti.count(g) > 1}
    for g in doppi:
        out.append(f"{nomi.get(g, g)} è in panchina due volte")
    return out


def avvisi(b: dict, roster: list[dict]) -> list[str]:
    """Cose da segnalare che non impediscono di pubblicare: un panchinaro che nel quintetto del
    bot è titolare (fa fede Yahoo: il quintetto lo può sistemare il GM o un admin)."""
    nomi = _nomi(roster)
    tit = {gid: ruolo for ruolo, gid in db.quintetto(b["team_id"]).items()}
    return [f"{nomi.get(g, g)} risulta nel tuo quintetto ({tit[g]}): se vuoi aggiornalo con /quintetto "
            f"({FAVORE}), altrimenti se ne occupa un admin"
            for g in dict.fromkeys(r.get("scelto") for r in b["dati"]["righe"]) if g in tit]


def anteprima(b: dict) -> tuple[str, K]:
    d = b["dati"]
    roster = db.roster(b["team_id"], b["stagione"])
    nomi = _nomi(roster)
    g = db.giornata(b["stagione"], b["giornata"])
    righe = [f"🪑 <b>Panchina di {e(config.nome(b['team_id']))} per la giornata {b['giornata']}</b>"
             + (" · ✏️ correzione (giornata chiusa)" if b["dati"].get("correzione") else ""),
             f"Scadenza: {ora(g['prima_partita']) if g else '?'}", ""]
    if d.get("titolo"):
        righe += [f"<i>{e(d['titolo'])}</i>", ""]
    st, quando = stati(nomi)
    for i, r in enumerate(d["righe"], 1):
        chi_ = (f"<b>{e(nomi.get(r['scelto'], '?'))}</b>{st.get(r['scelto'], '')}" if r.get("scelto")
                else "❓ <b>da scegliere</b>")
        righe.append(f"{i}. {e(r['testo'])} → {chi_}")
    if quando and any(r.get("scelto") in st for r in d["righe"]):
        righe += ["", f"<i>{quando}</i>"]
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
    if d["righe"] and all(r.get("scelto") for r in d["righe"]):
        tasti.append([B("🛠 Ordine, cambi e soprannomi", callback_data=f"pb:e:{b['id']}")])
    tasti.append(fondo)
    return "\n".join(righe), K(tasti)


def _giornata_correzione(s: str, numero: int) -> tuple[dict | None, str | None]:
    """La giornata N già chiusa da correggere (admin, per il calcolo). (giornata, errore)"""
    g = db.giornata(s, numero)
    if not g:
        return None, f"Giornata {numero} non trovata."
    if not db.stato_giornata(s, numero)["chiusa"]:
        return None, f"La giornata {numero} non è ancora chiusa: la panchina si manda normalmente (senza G{numero})."
    return g, None


def _correzione_in_corso(s: str) -> int | None:
    """Admin a giornata in corso (Luca, 20/10): senza GN si corregge la panchina della giornata in
    corso, come con GN, invece di «non accetto panchine» (quello vale per i GM)."""
    blocco = comune.panchine_bloccate(s)
    if blocco and db.stato_giornata(s, blocco["numero"])["chiusa"]:
        return blocco["numero"]
    return None


def crea_bozza(chat_id: int, team_id: str, testo: str, fonte: str = "gm", numero: int | None = None) -> tuple[dict | None, str | None]:
    """(bozza, errore). Con `numero` (admin): correzione della panchina della giornata N, già chiusa."""
    s = config.stagione()
    if not numero and fonte == "admin":
        numero = _correzione_in_corso(s)
    if numero:
        g, err = _giornata_correzione(s, numero)
        if err:
            return None, err
    else:
        blocco = comune.panchine_bloccate(s)
        if blocco:
            return None, testo_panchine_bloccate(blocco)
        g = prossima_giornata(s)
    if not g:
        return None, "Non c'è una giornata aperta: il calendario non è ancora caricato o la stagione è finita."
    titolo, righe, err = abbina.leggi_messaggio(testo)
    if err:
        return None, err
    if len(righe) < regole.giocatori_panchina():
        return None, (f"La panchina è di {regole.giocatori_panchina()} giocatori, mai meno: ne ho letti {len(righe)}. "
                      f"Rimandamela con tutte e {regole.giocatori_panchina()} le righe (o usa /build_panchina).")
    rip = abbina.ripetute(righe)
    if rip:
        doppie = sorted({r for r in righe if abbina.chiave(r) in rip})
        return None, ("Righe duplicate: " + ", ".join(f"«{x}»" for x in doppie) + ". Ogni panchinaro va scritto in modo "
                      "diverso, sennò non si capisce chi è chi: rimandamela.")
    roster = db.roster(team_id, s)
    if not roster:
        return None, "Nessun giocatore a roster per questa squadra."
    abbinate = abbina.abbina_panchina(righe, roster, db.alias(team_id, [g["id"] for g in roster]))
    dati = {"titolo": titolo, "righe": abbinate, "correzione": bool(numero)}
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
        await msg.reply_text("Per la panchina mandami le righe dei 5 panchinari, una per riga, in ordine "
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
    if azione in ("e", "n", "su", "gi", "sw", "sp", "cn") or (azione == "cs" and d.get("cai_singolo")):
        await cb_editor(q, b, azione, parti, roster, nomi)
        return
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
            if gid in nomi and gid not in {r["scelto"] for r in d["righe"]} and len(d["righe"]) < regole.giocatori_panchina():
                d["righe"].append({"testo": nomi[gid], "candidati": [gid], "scelto": gid, "certo": True})
        elif azione == "u" and d["righe"]:
            d["righe"].pop()
        db.aggiorna_bozza(bid, d)
        b = db.bozza(bid)
        await q.answer()
        if len(d["righe"]) >= regole.giocatori_panchina():
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
        st, _ = stati(ids)
        md = comune.medie(ids)
        tasti = [[B(nomi[g] + (" (" + (next((x["ruolo"] for x in roster if x["id"] == g), "") or "") + ")") + md.get(g, "") + st.get(g, ""),
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


def testo_canale(team_id: str, giornata: int, titolo: str | None, righe: list[dict], aggiornata: bool,
                 fonte: str = "gm", admin: str | None = None, quando=None) -> str:
    """Il messaggio sul canale Panchinari: le righe del GM e, in fondo, chi l'ha inserita (GM o
    quale admin) e quando (l'ultima modifica, ora italiana)."""
    out = [f"<b>{e(config.nome(team_id))}</b> · giornata {giornata}"]
    if titolo:
        out.append(f"<i>{e(titolo)}</i>")
    out += [f"{i}. {e(r['testo'])}" for i, r in enumerate(righe, 1)]
    t = (quando or adesso()).astimezone(ROMA)
    da = f"admin {e(admin)}" if fonte == "admin" else "GM"
    out.append(f"\n<i>✍️ {da} · {'🔁 ultima modifica' if aggiornata else 'inserita'} {t:%d/%m} alle {t:%H:%M}</i>")
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
    if not b["dati"].get("correzione") and (not g or not aperta(g)):
        db.chiudi_bozza(b["id"])
        await q.answer("La scadenza è passata.", show_alert=True)
        await q.edit_message_text("⏰ La scadenza di questa giornata è passata mentre confermavi: la panchina non è "
                                  "stata pubblicata. Per questa giornata scrivi a un admin; quella della giornata "
                                  "successiva si manda dalla mattina dopo l'ultima partita (dalle 6).")
        return
    roster = db.roster(b["team_id"], b["stagione"])
    pb = problemi(b, roster)
    if pb:
        await q.answer("Ci sono ancora problemi: " + pb[0][:150], show_alert=True)
        return
    righe = [{"giocatore_id": r["scelto"], "testo": r["testo"]} for r in b["dati"]["righe"]]
    precedente = db.panchina(b["stagione"], b["giornata"], b["team_id"])
    u = update.effective_user
    testo = testo_canale(b["team_id"], b["giornata"], b["dati"].get("titolo"), righe, bool(precedente),
                         fonte=b["fonte"], admin=(u.full_name or str(u.id)) if u else "?")
    mid = None
    canale = config.canale_panchinari()
    if canale:
        try:
            vecchio = (precedente or {}).get("messaggio_canale")
            if precedente and precedente.get("canale_id") != canale:   # canale cambiato (o non noto): messaggio nuovo
                vecchio = None
            mid = await _scrivi_canale(context.bot, canale, testo, vecchio)
        except Exception as err:
            logger.warning("Canale Panchinari: %s", err)
            await q.answer("Non riesco a scrivere sul canale Panchinari: avvisa un admin.", show_alert=True)
            return
    db.salva_panchina(b["stagione"], b["giornata"], b["team_id"], b["dati"].get("titolo"), righe,
                      da=update.effective_user.id, fonte=b["fonte"], messaggio_canale=mid,
                      canale_id=canale if mid else None, da_nome=(u.full_name or str(u.id)) if u else None)
    if b["dati"].get("correzione"):                       # giornata già chiusa: i ruoli per la FADD
        db.congela_ruoli_panchine(b["stagione"], b["giornata"], b["team_id"])
    rip = abbina.ripetute([r["testo"] for r in b["dati"]["righe"]])
    for r in b["dati"]["righe"]:
        if abbina.chiave(r["testo"]) in rip:          # "prova" ×5: non è il soprannome di nessuno
            continue
        if abbina.chiave(r["testo"]) != abbina.chiave(_nomi(roster).get(r["scelto"], "")):   # il nome vero non serve
            db.salva_alias(b["team_id"], abbina.chiave(r["testo"]), r["scelto"])
    db.chiudi_bozza(b["id"])
    nomi = _nomi(roster)
    av = avvisi(b, roster)
    await q.answer("Pubblicata")
    if b["dati"].get("correzione"):
        await log(context.bot, f"✏️ Panchina G{b['giornata']} di {e(config.nome(b['team_id']))} corretta da {chi(update)} "
                               f"a giornata chiusa: per il calcolo /ricalcola {b['giornata']} su loucabot")
    await q.edit_message_text((f"✏️ Correzione: ora su loucabot /ricalcola {b['giornata']}.\n" if b["dati"].get("correzione") else "")
                              + f"✅ Panchina della giornata {b['giornata']} pubblicata"
                              + (" (sostituisce la precedente)" if precedente else "") + ".\n\n"
                              + "\n".join(f"{i}. {e(r['testo'])} → {e(nomi.get(r['giocatore_id'], '?'))}"
                                          for i, r in enumerate(righe, 1))
                              + ("\n\nℹ️ " + "\nℹ️ ".join(e(x) for x in av) if av else ""), parse_mode="HTML")
    from registro import segna_sync
    segna_sync(update.effective_user, "admin" if b["fonte"] == "admin" else "gm",
               ("panchina corretta" if b["dati"].get("correzione") else "panchina mandata")
               + (" per conto della squadra" if b["fonte"] == "admin" else ""),
               squadre=b["team_id"], oggetto=f"panchina G{b['giornata']}",
               prima="una panchina già mandata" if precedente else None,
               dopo=", ".join(nomi.get(r["giocatore_id"], "?") for r in righe),
               nota="a giornata chiusa" if b["dati"].get("correzione") else None)
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
    if d.get("cai_singolo"):                          # dall'editor: un solo soprannome, poi si torna lì
        return testo, K([[B("♻️ Nome vero", callback_data=f"pb:cn:{b['id']}"),
                          B("↩️ Indietro", callback_data=f"pb:cs:{b['id']}")]])
    return testo, K([[B("⏭️ Salta", callback_data=f"pb:cs:{b['id']}"), B("✅ Fine", callback_data=f"pb:cf:{b['id']}")]])


def avanza_cai(b: dict) -> dict:
    d = b["dati"]
    if d.pop("cai_singolo", False):
        d["cai_passo"] = None
    else:
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
    singolo = db.bozza(b["id"])["dati"].get("cai_singolo")
    b = avanza_cai(db.bozza(b["id"]))
    if b["dati"].get("cai_passo") is None:
        if singolo:
            t, k = editor(b)
            await msg.reply_text(t, parse_mode="HTML", reply_markup=k)
            return
        await manda_anteprima(msg, b)
    else:
        t, k = domanda_cai(b)
        await msg.reply_text(t, parse_mode="HTML", reply_markup=k)


# ── editor (/edit): ordine, cambi e soprannomi riga per riga ──────────────────

def editor(b: dict) -> tuple[str, K]:
    d = b["dati"]
    bid = b["id"]
    roster = db.roster(b["team_id"], b["stagione"])
    nomi = _nomi(roster)
    g = db.giornata(b["stagione"], b["giornata"])
    st, quando = stati([r.get("scelto") for r in d["righe"]])
    righe = [f"🛠 <b>Panchina di {e(config.nome(b['team_id']))} · giornata {b['giornata']}</b>"
             + (" · ✏️ correzione (giornata chiusa)" if d.get("correzione") else ""),
             f"Scadenza: {ora(g['prima_partita']) if g else '?'}", ""]
    if d.get("titolo"):
        righe += [f"<i>{e(d['titolo'])}</i>", ""]
    md = comune.medie([r.get("scelto") for r in d["righe"]])
    for i, r in enumerate(d["righe"], 1):
        nome = nomi.get(r.get("scelto"), "❓ non più in squadra")
        righe.append(f"{i}. {e(r['testo'])}" + (f" → <b>{e(nome)}</b>" if r["testo"] != nome else "")
                     + md.get(r.get("scelto"), "") + st.get(r.get("scelto"), ""))
    if quando:
        righe += ["", f"<i>{quando}</i>"]
    righe += ["", "Tocca un giocatore per il soprannome · ⬆️⬇️ sposta · 🔄 cambia (con un altro in panchina si "
                  "scambiano il posto, ognuno col suo soprannome)."]
    pb = problemi(b, roster)
    if pb:
        righe += ["", "⚠️ " + "\n⚠️ ".join(e(x) for x in pb)]
    tasti = [[B(f"✏️ {i + 1}. {r['testo']}"[:40], callback_data=f"pb:n:{bid}:{i}"),
              B("⬆️", callback_data=f"pb:su:{bid}:{i}"), B("⬇️", callback_data=f"pb:gi:{bid}:{i}"),
              B("🔄", callback_data=f"pb:sw:{bid}:{i}")] for i, r in enumerate(d["righe"])]
    fondo = [B("❌ Annulla", callback_data=f"pb:no:{bid}")]
    if not pb:
        fondo.insert(0, B("✅ Pubblica", callback_data=f"pb:ok:{bid}"))
    tasti.append([B("👁 Anteprima", callback_data=f"pb:v:{bid}")])
    tasti.append(fondo)
    return "\n".join(righe), K(tasti)


async def cb_editor(q, b: dict, azione: str, parti: list[str], roster: list[dict], nomi: dict):
    bid, d = b["id"], b["dati"]
    righe = d["righe"]
    i = int(parti[3]) if len(parti) > 3 else None
    if i is not None and not 0 <= i < len(righe):
        await q.answer("Riga non trovata: riapri con /edit.", show_alert=True)
        return
    if azione in ("su", "gi"):
        j = i - 1 if azione == "su" else i + 1
        if not 0 <= j < len(righe):
            await q.answer("È già il primo." if azione == "su" else "È già l'ultimo.")
            return
        righe[i], righe[j] = righe[j], righe[i]
    elif azione == "n":                                    # soprannome: la risposta arriva come messaggio
        d["cai_passo"], d["cai_singolo"] = i + 1, True
        db.aggiorna_bozza(bid, d)
        await q.answer()
        testo, tasti = domanda_cai(db.bozza(bid))
        await q.edit_message_text(testo, parse_mode="HTML", reply_markup=tasti)
        return
    elif azione == "cn":                                   # ♻️ torna al nome vero
        p = d.get("cai_passo")
        if p:
            r = righe[p - 1]
            r["testo"] = nomi.get(r.get("scelto"), r["testo"])
        d["cai_passo"] = None
        d.pop("cai_singolo", None)
    elif azione == "cs":                                   # ↩️ dal soprannome: niente cambia
        d["cai_passo"] = None
        d.pop("cai_singolo", None)
    elif azione == "sw":
        r = righe[i]
        in_panca = {x.get("scelto"): j for j, x in enumerate(righe)}
        titolari = set(db.quintetto(b["team_id"]).values())
        fuori = [g for g in roster if g["id"] not in in_panca]
        st, _ = stati([x.get("scelto") for j, x in enumerate(righe) if j != i] + [g["id"] for g in fuori])
        md = comune.medie([x.get("scelto") for x in righe] + [g["id"] for g in fuori])
        tasti = [[B(f"🔁 {j + 1}. {x['testo']}"[:50] + md.get(x.get("scelto"), "") + st.get(x.get("scelto"), ""),
                    callback_data=f"pb:sp:{bid}:{i}:{x['scelto']}")]
                 for j, x in enumerate(righe) if j != i and x.get("scelto")]
        tasti += [[B(f"➕ {g['nome_common']}" + (f" ({g['ruolo']})" if g.get("ruolo") else "") + md.get(g["id"], "")
                     + (" ⭐ titolare" if g["id"] in titolari else "") + st.get(g["id"], ""),
                     callback_data=f"pb:sp:{bid}:{i}:{g['id']}")] for g in fuori]
        tasti.append([B("↩️ Indietro", callback_data=f"pb:e:{bid}")])
        await q.answer()
        await q.edit_message_text(f"🔄 Riga {i + 1}: «{e(r['testo'])}» ({e(nomi.get(r.get('scelto'), '?'))})\n\n"
                                  "🔁 scambia il posto con un altro panchinaro (ognuno tiene il suo soprannome)\n"
                                  "➕ metti al suo posto un giocatore che non è in panchina",
                                  parse_mode="HTML", reply_markup=K(tasti))
        return
    elif azione == "sp":
        gid = int(parti[4])
        if gid not in nomi:
            await q.answer("Non è più nella tua squadra.", show_alert=True)
            return
        j = next((k for k, x in enumerate(righe) if x.get("scelto") == gid), None)
        if j is not None:                                  # già in panchina: si scambiano il posto
            righe[i], righe[j] = righe[j], righe[i]
        else:                                              # entra al posto della riga i, col suo nome
            righe[i] = {"testo": nomi[gid], "candidati": [gid], "scelto": gid, "certo": True}
    db.aggiorna_bozza(bid, d)
    await q.answer()
    testo, tasti = editor(db.bozza(bid))
    await q.edit_message_text(testo, parse_mode="HTML", reply_markup=tasti)


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/edit: la panchina già mandata per la prossima giornata, da modificare coi bottoni (ordine,
    cambi, soprannomi). Admin: /edit SQUADRA per conto di una squadra."""
    msg = update.effective_message
    uid = update.effective_user.id
    fonte = "gm"
    if context.args and config.is_admin(uid):
        from shared.squadre import cerca_squadra
        team = cerca_squadra(" ".join(context.args), config.squadre())
        if not team:
            await msg.reply_text("Squadra non trovata. Uso: /edit SQUADRA (nome o id).")
            return
        fonte = "admin"
    else:
        team = config.squadra_del_gm(uid)
        if not team:
            await msg.reply_text("Non risulti GM di nessuna squadra." + (" Admin: /edit SQUADRA." if config.is_admin(uid) else ""))
            return
    s = config.stagione()
    correzione = _correzione_in_corso(s) if fonte == "admin" else None
    if correzione:                                   # admin a giornata in corso: si corregge quella
        g = db.giornata(s, correzione)
    else:
        blocco = comune.panchine_bloccate(s)
        if blocco:
            await msg.reply_text(testo_panchine_bloccate(blocco)
                                 + ("\nAdmin: /edit SQUADRA o /panchina_admin SQUADRA G" + str(blocco["numero"])
                                    if config.is_admin(uid) else ""))
            return
        g = prossima_giornata(s)
    if not g:
        await msg.reply_text("Non c'è una giornata aperta.")
        return
    p = db.panchina(s, g["numero"], team["id"])
    if not p:
        await msg.reply_text(f"Per la giornata {g['numero']} non c'è ancora una panchina da modificare: "
                             + (f"/panchina_admin {team['nome']} per crearla." if fonte == "admin" else
                                "mandami le righe o usa /build_panchina."))
        return
    righe = [{"testo": r["testo"], "candidati": [r["giocatore_id"]], "scelto": r["giocatore_id"], "certo": True}
             for r in p["righe"]]
    bid = db.nuova_bozza(update.effective_chat.id, team["id"], s, g["numero"],
                         {"titolo": p["titolo"], "righe": righe, "correzione": bool(correzione), "edit": True}, fonte)
    testo, tasti = editor(db.bozza(bid))
    await msg.reply_text(testo, parse_mode="HTML", reply_markup=tasti)


# ── builder coi bottoni (/build_panchina) ──────────────────────────────────────

def builder(b: dict, roster: list[dict]) -> tuple[str, K]:
    """Panchinari uno alla volta, in ordine: solo giocatori della squadra non nel quintetto e non
    ancora scelti. Sul canale escono i loro nomi."""
    d = b["dati"]
    scelti = [r["scelto"] for r in d["righe"]]
    titolari = set(db.quintetto(b["team_id"]).values())
    liberi = [g for g in roster if g["id"] not in titolari and g["id"] not in scelti]
    if len(liberi) < regole.giocatori_panchina() - len(scelti):    # rosa corta: si possono scegliere anche i titolari
        liberi += [g for g in roster if g["id"] in titolari and g["id"] not in scelti]
    g = db.giornata(b["stagione"], b["giornata"])
    righe = [f"🪑 <b>Panchina di {e(config.nome(b['team_id']))} per la giornata {b['giornata']}</b>"
             + (" · ✏️ correzione (giornata chiusa)" if b["dati"].get("correzione") else ""),
             f"Scadenza: {ora(g['prima_partita']) if g else '?'}", ""]
    st, quando = stati([x["id"] for x in liberi] + scelti)
    righe += [f"{i}. {e(r['testo'])}{st.get(r['scelto'], '')}" for i, r in enumerate(d["righe"], 1)] or ["(ancora nessuno)"]
    righe += ["", f"Scegli il panchinaro n. {len(scelti) + 1}:" if len(scelti) < regole.giocatori_panchina() else ""]
    if quando:
        righe.append(f"<i>{quando}</i>")
    md = comune.medie([x["id"] for x in liberi])
    tasti = [[B(f"{x['nome_common']}" + (f" ({x['ruolo']})" if x.get("ruolo") else "") + md.get(x["id"], "")
                + (" ⭐ titolare" if x["id"] in titolari else "") + st.get(x["id"], ""),
                callback_data=f"pb:b:{b['id']}:{x['id']}")] for x in liberi]
    fondo = []
    if scelti:                                         # al quinto si passa da soli all'anteprima
        fondo.append(B("↩️ Togli l'ultimo", callback_data=f"pb:u:{b['id']}"))
    fondo.append(B("❌ Annulla", callback_data=f"pb:no:{b['id']}"))
    return "\n".join(righe), K(tasti + [fondo])


async def apri_builder(msg, chat_id: int, team_id: str, fonte: str = "gm", numero: int | None = None):
    s = config.stagione()
    if not numero and fonte == "admin":
        numero = _correzione_in_corso(s)
    if numero:
        g, err = _giornata_correzione(s, numero)
        if err:
            await msg.reply_text(f"❌ {err}")
            return
    else:
        blocco = comune.panchine_bloccate(s)
        if blocco:
            await msg.reply_text(testo_panchine_bloccate(blocco))
            return
        g = prossima_giornata(s)
    if not g:
        await msg.reply_text("Non c'è una giornata aperta.")
        return
    bid = db.nuova_bozza(chat_id, team_id, s, g["numero"], {"titolo": None, "righe": [], "builder": True,
                                                            "correzione": bool(numero)}, fonte)
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
    blocco = comune.panchine_bloccate()            # giornata in corso: si vede la sua panchina
    g = blocco or prossima_giornata()
    if not g:
        await update.effective_message.reply_text("Non c'è una giornata aperta.")
        return
    p = db.panchina(config.stagione(), g["numero"], team["id"])
    if not p and blocco:
        await update.effective_message.reply_text(f"Per la giornata {g['numero']}, in corso, non hai mandato la panchina.\n\n"
                                                  + testo_panchine_bloccate(blocco))
        return
    if not p:
        await update.effective_message.reply_text(
            f"Per la giornata {g['numero']} (scadenza {ora(g['prima_partita'])}) non hai ancora mandato la panchina: "
            "mandami le righe, una per riga.")
        return
    nomi = _nomi(db.roster(team["id"], config.stagione()))
    fuori = db.nomi_giocatori([r["giocatore_id"] for r in p["righe"] if r["giocatore_id"] not in nomi])
    nomi.update({g: f"{n} (non più in squadra: rimandala)" for g, n in fuori.items()})
    await update.effective_message.reply_text(
        f"🪑 Panchina della giornata {g['numero']} (scadenza {ora(g['prima_partita'])})\n"
        + (f"<i>{e(p['titolo'])}</i>\n" if p["titolo"] else "")
        + "\n".join(f"{i}. {e(r['testo'])} → {e(nomi.get(r['giocatore_id'], '?'))}" for i, r in enumerate(p["righe"], 1))
        + "\n\nPer cambiarla: /edit (ordine, cambi, soprannomi) o mandami di nuovo le righe.", parse_mode="HTML")


def testo_da_salvata(p: dict) -> str:
    """Il messaggio sul canale di una panchina salvata, com'era (chi, quando, se aggiornata)."""
    return testo_canale(p["team_id"], p["giornata"], p["titolo"], p["righe"], (p.get("versioni") or 1) > 1,
                        fonte=p["fonte"], admin=p.get("da_nome") or "?", quando=p["inviata"])


PAUSA_CANALE = 3.5          # Telegram: circa 20 messaggi al minuto nello stesso canale


async def ripubblica(bot, stagione: str, n: int, pausa: float = PAUSA_CANALE) -> tuple[int, list[str]]:
    """Manda sul canale Panchinari di oggi tutte le panchine salvate della giornata n, come
    messaggi nuovi (in ordine di squadra), e si segna i messaggi: le modifiche successive
    aggiornano questi. (mandate, errori)"""
    import asyncio
    from telegram.error import RetryAfter
    canale = config.canale_panchinari()
    panche = db.panchine(stagione, n)
    fatte, errori = 0, []
    for t in config.squadre():
        p = panche.get(t["id"])
        if not p:
            continue
        for tentativo in (1, 2):
            try:
                m = await bot.send_message(chat_id=canale, text=testo_da_salvata(p), parse_mode="HTML")
                db.segna_messaggio(stagione, n, t["id"], m.message_id, canale)
                fatte += 1
                break
            except RetryAfter as ra:                       # troppo veloce: si aspetta e si riprova
                await asyncio.sleep(ra.retry_after + 1)
            except Exception as err:
                errori.append(f"{t['nome']}: {err}")
                break
        await asyncio.sleep(pausa)
    return fatte, errori


async def cmd_ripubblica_panchine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ripubblica_panchine [N] (admin): tutte le panchine già mandate della prossima giornata
    (o della N) di nuovo sul canale Panchinari, per esempio dopo aver cambiato canale."""
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    if not config.canale_panchinari():
        await msg.reply_text("Manca canale_panchinari_id in globals.json.")
        return
    s = config.stagione()
    n = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    g = db.giornata(s, n) if n else prossima_giornata(s)
    if not g:
        await msg.reply_text("Nessuna giornata: /ripubblica_panchine N.")
        return
    quante = len(db.panchine(s, g["numero"]))
    if not quante:
        await msg.reply_text(f"Nessuna panchina salvata per la giornata {g['numero']}.")
        return
    await msg.reply_text(f"⏳ Ripubblico {quante} panchine della giornata {g['numero']} sul canale Panchinari, "
                         f"una ogni {PAUSA_CANALE:g} secondi (limite di Telegram): circa {round(quante * PAUSA_CANALE / 60) or 1} minuti.")
    chi_ = chi(update)

    async def lavoro():
        fatte, errori = await ripubblica(context.bot, s, g["numero"])
        testo = f"✅ Ripubblicate {fatte} panchine della giornata {g['numero']}." + (
            "\n❌ " + "\n❌ ".join(e(x) for x in errori) if errori else "")
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=testo, parse_mode="HTML")
        except Exception as err:
            logger.warning("Fine ripubblicazione: %s", err)
        await log(context.bot, f"📣 /ripubblica_panchine G{g['numero']} di {chi_}: {fatte} mandate, {len(errori)} errori")
        from registro import segna_sync
        segna_sync(update.effective_user, "admin", "panchine ripubblicate", oggetto=f"giornata {g['numero']}",
                   dopo=f"{fatte} mandate, {len(errori)} errori")
    app = getattr(context, "application", None)
    if app:
        app.create_task(lavoro())         # non blocca il bot per il minuto e mezzo
    else:
        await lavoro()


async def cmd_panchina_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/panchina_admin SQUADRA [GN] e sotto le righe: la panchina per conto di una squadra. Con GN
    (es. G5) corregge la panchina della giornata 5, già chiusa (poi /ricalcola 5 su loucabot)."""
    import re
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    righe = (msg.text or "").split("\n")
    prima = righe[0].split(maxsplit=1)
    numero = None
    if len(prima) > 1:
        m = re.search(r"\s+[Gg](\d{1,2})\s*$", prima[1])
        if m:
            numero, prima[1] = int(m.group(1)), prima[1][:m.start()]
    from shared.squadre import cerca_squadra
    team = cerca_squadra(prima[1], config.squadre()) if len(prima) > 1 else None
    if not team:
        await msg.reply_text("Uso: /panchina_admin SQUADRA (nome o id) nella prima riga, sotto le righe della panchina; "
                             "senza righe si apre il builder coi bottoni. Con G5 dopo la squadra corregge la panchina "
                             "della giornata 5, già chiusa.")
        return
    if not [r for r in righe[1:] if r.strip()]:
        await apri_builder(msg, update.effective_chat.id, team["id"], fonte="admin", numero=numero)
        return
    b, err = crea_bozza(update.effective_chat.id, team["id"], "\n".join(righe[1:]), fonte="admin", numero=numero)
    if err:
        await msg.reply_text(f"❌ {err}")
        return
    await manda_anteprima(msg, b)


def get_handlers() -> list:
    from telegram.ext import CommandHandler
    return [
        CommandHandler("panchina", cmd_panchina, filters=filters.ChatType.PRIVATE),
        CommandHandler("build_panchina", cmd_build_panchina, filters=filters.ChatType.PRIVATE),
        CommandHandler("edit", cmd_edit, filters=filters.ChatType.PRIVATE),
        CommandHandler("panchina_admin", cmd_panchina_admin),
        CommandHandler("ripubblica_panchine", cmd_ripubblica_panchine),
        CallbackQueryHandler(cb_panchina, pattern=r"^pb:"),
        MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, msg_panchina),
    ]


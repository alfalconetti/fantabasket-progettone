"""
Avvisi dell'injury report (Luca, 23/10): quando ESPN cambia lo stato di un giocatore di una squadra
(Probable → Out, Out → fuori dalla lista, nuovo nella lista…), il bot lo scrive in privato ai GM di
quella squadra. Tutti i cambi di stato, per tutti i giocatori della rosa (schierati o no).

- Da dove: gli snapshot degli infortunati che scarica loucabot (`nba_infortuni`): ogni 4 ore, 30
  minuti prima della prima partita del giorno e, nella prima sera di ogni giornata, ogni mezz'ora
  dalle 19 alla prima partita (`orari.injury_fitti`).
- Il job (ogni 2 minuti) confronta l'ultimo snapshot con l'ultimo già visto (`ipa_injury_visto`):
  se loucabot ne ha presi più d'uno nel frattempo, nessun cambio si perde. La prima volta segna
  solo il punto di partenza, senza avvisi.
- Se lo snapshot nuovo ha meno della metà dei giocatori del precedente (risposta di ESPN
  incompleta), niente avvisi: sarebbero tutti «tornati disponibili» per sbaglio.
- `/toggle_injures` spegne e riaccende gli avvisi per chi lo scrive (`ipa_injury_spenti`); è
  ricordato sotto ogni avviso.
"""
import html
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import config
import db
from comune import log, ora, segno_stato

logger = logging.getLogger(__name__)
SOGLIA_INCOMPLETO = 0.5
PIEDE = "🔕 /toggle_injures per spegnere (o riaccendere) questi avvisi"


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _tabella_c_e() -> bool:
    return bool(db.q("SELECT to_regclass('nba_infortuni') AS t", one=True)["t"])


def snapshot(preso) -> dict[str, dict]:
    righe = db.q("SELECT atleta, nome, squadra, stato, dettaglio FROM nba_infortuni WHERE preso = %s", (preso,), many=True) or []
    return {r["atleta"]: r for r in righe}


def cambi(prima: dict, dopo: dict) -> dict[str, tuple]:
    """{atleta: (stato prima, stato dopo, dettaglio)} per chi ha cambiato stato (None = non nella lista)."""
    out = {}
    for a in set(prima) | set(dopo):
        s1 = (prima.get(a) or {}).get("stato")
        s2 = (dopo.get(a) or {}).get("stato")
        if (s1 or "").strip().lower() != (s2 or "").strip().lower():
            out[a] = (s1, s2, (dopo.get(a) or {}).get("dettaglio") or "")
    return out


def _stato(s: str | None) -> str:
    return segno_stato(s).strip() if s else "✅ disponibile (fuori dalla lista)"


def testo_avviso(team: dict, righe: list[dict], quando) -> str:
    """righe: {nome, sigla, prima, dopo, dettaglio, ruolo_quintetto}."""
    out = [f"🩺 <b>Injury report ESPN</b> · {e(team['nome'])} · {ora(quando)}", ""]
    for r in righe:
        riga = (f"• <b>{e(r['nome'])}</b>" + (f" ({e(r['sigla'])})" if r.get("sigla") else "")
                + f": {e(_stato(r['prima']))} → <b>{e(_stato(r['dopo']))}</b>")
        if r.get("ruolo_quintetto"):
            riga += f" · nel tuo quintetto ({e(r['ruolo_quintetto'])})"
        if r.get("dopo") and r.get("dettaglio"):
            riga += f"\n   <i>{e(r['dettaglio'][:160])}</i>"
        out.append(riga)
    out += ["", PIEDE]
    return "\n".join(out)


def spenti() -> set[int]:
    return {int(r["utente"]) for r in (db.q("SELECT utente FROM ipa_injury_spenti", many=True) or [])}


async def controlla(bot) -> int:
    """Avvisi mandati (uno per GM e squadra)."""
    if not _tabella_c_e():
        return 0
    ultimo = db.q("SELECT MAX(preso) AS t FROM nba_infortuni", one=True)["t"]
    if not ultimo:
        return 0
    visto = (db.q("SELECT preso FROM ipa_injury_visto WHERE id = 1", one=True) or {}).get("preso")
    segna = lambda: db.q("INSERT INTO ipa_injury_visto (id, preso) VALUES (1, %s) ON CONFLICT (id) DO UPDATE SET preso = EXCLUDED.preso", (ultimo,))
    if not visto:
        segna()                                   # prima volta: solo il punto di partenza
        return 0
    if ultimo <= visto:
        return 0
    # il confronto: con l'ultimo già visto se c'è ancora, se no con quello subito prima
    base = visto if db.q("SELECT 1 FROM nba_infortuni WHERE preso = %s LIMIT 1", (visto,), one=True) else \
        db.q("SELECT MAX(preso) AS t FROM nba_infortuni WHERE preso < %s", (ultimo,), one=True)["t"]
    if not base:
        segna()
        return 0
    prima, dopo = snapshot(base), snapshot(ultimo)
    if prima and len(dopo) < SOGLIA_INCOMPLETO * len(prima):
        segna()
        await log(bot, f"🩺 Injury report: snapshot con {len(dopo)} giocatori contro {len(prima)} del precedente, "
                       "sembra incompleto: nessun avviso ai GM")
        return 0
    c = cambi(prima, dopo)
    segna()
    if not c:
        return 0
    s = config.stagione()
    no = spenti()
    mandati = 0
    for t in config.squadre():
        rosa = [g for g in db.roster(t["id"], s) if g.get("espn_id") in c]
        if not rosa:
            continue
        q5 = {gid: r for r, gid in db.quintetto(t["id"]).items()}
        righe = []
        for g in sorted(rosa, key=lambda x: x["nome_common"]):
            p, d, det = c[g["espn_id"]]
            x = dopo.get(g["espn_id"]) or prima.get(g["espn_id"]) or {}
            righe.append({"nome": g["nome_common"], "sigla": x.get("squadra"), "prima": p, "dopo": d,
                          "dettaglio": det, "ruolo_quintetto": q5.get(g["id"])})
        testo = testo_avviso(t, righe, ultimo)
        for uid in config.gm_ids(t["id"]):
            if uid in no:
                continue
            try:
                await bot.send_message(chat_id=uid, text=testo, parse_mode="HTML")
                mandati += 1
            except Exception as err:                  # GM che non ha mai avviato il bot in privato
                logger.info("Avviso injury a %s: %s", uid, err)
    return mandati


async def job_injury(context: ContextTypes.DEFAULT_TYPE):
    try:
        n = await controlla(context.bot)
        if n:
            logger.info("Injury report: %d avvisi", n)
    except Exception as err:
        logger.warning("Injury report: %s", err)


async def cmd_toggle_injures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if update.effective_chat and update.effective_chat.type != "private":
        await msg.reply_text("Scrivimi in privato: gli avvisi arrivano lì.")
        return
    uid = update.effective_user.id
    if not config.squadra_del_gm(uid):
        await msg.reply_text("Gli avvisi dell'injury report sono per i GM: non trovo la tua squadra.")
        return
    if db.q("DELETE FROM ipa_injury_spenti WHERE utente = %s RETURNING utente", (uid,), one=True):
        await msg.reply_text("🔔 Avvisi dell'injury report <b>accesi</b>: quando ESPN cambia lo stato di un tuo giocatore "
                             "te lo scrivo qui. /toggle_injures per spegnerli.", parse_mode="HTML")
    else:
        db.q("INSERT INTO ipa_injury_spenti (utente) VALUES (%s) ON CONFLICT DO NOTHING", (uid,))
        await msg.reply_text("🔕 Avvisi dell'injury report <b>spenti</b>. /toggle_injures per riaccenderli.", parse_mode="HTML")


def get_handlers() -> list:
    return [CommandHandler("toggle_injures", cmd_toggle_injures)]

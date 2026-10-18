"""
/report_ruoli (admin, v5.9.0): fotografia dei ruoli di tutte le squadre in quel momento, in un file
Markdown. Anche dal pannello admin: «🎽 Ruoli squadre» → «📄 Report ruoli (.md)» (callback rrep:md).

Nel file: riepilogo della lega (una riga per squadra: ruoli per posizione, guardie/ali/centri rispetto
ai minimi, giocatori senza ruolo, dichiarazioni in sospeso, stato dei minimi) e poi, squadra per
squadra, ogni giocatore a roster col ruolo ufficiale, le posizioni eleggibili e le note (10-day,
Saedro in corso, dichiarazione in sospeso con la scadenza, bozza non confermata, Erminio possibile,
ruolo fuori dalle eleggibili). Solo lettura: non cambia niente.

Stato dei minimi: ✅ rispettati coi ruoli ufficiali; 🟡 non ancora, ma i giocatori senza ruolo
possono coprirli; ❌ mancano N posti anche con la scelta migliore (shared/ruoli_core.deficit_team).
I minimi vengono da settings.json (shared/regole.py); i 10-day non contano.
"""
import asyncio
import io
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db
import settings
import teams as tm
from shared import regole, ruoli_core as core

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
RUOLI = core.RUOLI
CATEGORIA = core.CATEGORIA


def _md(x) -> str:
    """Testo sicuro dentro una tabella Markdown."""
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")


def _quando(t) -> str:
    return t.astimezone(ROMA).strftime("%d/%m %H:%M") if t else "?"


def dati_squadra(team_id: str, stagione: str, adesso: datetime) -> dict:
    from handlers import cambi_ruolo as CR
    from handlers import ruoli_rs as RS
    roster = db.get_roster_team(team_id) or []
    gids = [r["giocatore_id"] for r in roster]
    pos = {r["giocatore_id"]: (r["posizioni"] or "") for r in db._q(
        "SELECT giocatore_id, posizioni FROM posizioni_attuali WHERE giocatore_id = ANY(%s)",
        (gids,), many=True) or []} if gids else {}
    uff = {r["giocatore_id"]: r for r in db._q(
        "SELECT giocatore_id, ruolo, tipo, scadenza FROM ruolo_attuale WHERE stagione = %s AND team_id = %s",
        (stagione, team_id), many=True) or []}
    boz = {r["giocatore_id"]: r["ruolo"] for r in db._q(
        "SELECT giocatore_id, ruolo FROM ruoli_bozze WHERE stagione = %s AND team_id = %s",
        (stagione, team_id), many=True) or []}
    pend = {p["giocatore_id"]: p for p in RS.pendenti_aperti(team_id)}
    giocatori = []
    for r in roster:
        gid = r["giocatore_id"]
        u = uff.get(gid) or {}
        eleg = [p for p in RUOLI if p in pos.get(gid, "").split(",")]
        note = []
        dieci = r.get("tipo_contratto") == "10day"
        if dieci:
            note.append("10-day (non conta per i minimi)")
        if u.get("tipo") == "saedro" and u.get("scadenza") and u["scadenza"] > adesso:
            note.append(f"Saedro fino al {_quando(u['scadenza'])}")
        if gid in pend:
            note.append(f"da dichiarare entro {_quando(pend[gid].get('scadenza'))}")
        if boz.get(gid) and boz[gid] != u.get("ruolo"):
            note.append(f"bozza {boz[gid]} non confermata")
        if u.get("ruolo") and eleg and u["ruolo"] not in eleg:
            note.append(f"{u['ruolo']} non è più tra le eleggibili")
        try:
            erm = sorted(CR.ruoli_erminio(gid) - {u.get("ruolo")})
        except Exception:
            erm = []
        if erm and u.get("ruolo"):
            note.append("Erminio possibile: " + ", ".join(erm))
        giocatori.append({"gid": gid, "nome": r["nome_common"], "ruolo": u.get("ruolo"), "eleggibili": eleg,
                          "dieci": dieci, "note": note, "in_sospeso": gid in pend})
    ordine = {p: i for i, p in enumerate(RUOLI)}
    giocatori.sort(key=lambda g: (ordine.get(g["ruolo"], 9), g["nome"]))
    contano = [g for g in giocatori if g["ruolo"] and not g["dieci"]]
    per_ruolo = {p: sum(g["ruolo"] == p for g in contano) for p in RUOLI}
    cat = {k: sum(CATEGORIA[g["ruolo"]] == k for g in contano) for k in ("G", "F", "C")}
    minimi = regole.minimi_ruolo()
    deficit = core.deficit_team(db._q, team_id, stagione)
    if all(cat[k] >= minimi[k] for k in minimi):
        stato = "✅ rispettati"
    elif deficit == 0:
        stato = "🟡 da completare"
    else:
        stato = f"❌ mancano {deficit}"
    return {"giocatori": giocatori, "per_ruolo": per_ruolo, "cat": cat, "minimi": minimi, "deficit": deficit,
            "stato": stato, "senza": [g for g in giocatori if not g["ruolo"]],
            "in_sospeso": [g for g in giocatori if g["in_sospeso"]],
            "cambi": CR.ordinari_usati(team_id), "saedro": CR.saedro_usata(team_id)}


def report(adesso: datetime | None = None) -> str:
    adesso = adesso or datetime.now(timezone.utc)
    stagione = settings.stagione_corrente()
    try:
        from handlers.admin_panel import FASI_LABEL
        fase = FASI_LABEL.get(settings.fase(), settings.fase())
    except Exception:
        fase = settings.fase()
    m = regole.minimi_ruolo()
    squadre = [(t, dati_squadra(t["id"], stagione, adesso)) for t in tm.get_all_teams()]
    righe = [f"# Report ruoli — stagione {stagione}", "",
             f"Fase: {fase} · {adesso.astimezone(ROMA):%d/%m/%Y %H:%M} (ora italiana)  ",
             f"Minimi: {m['G']} guardie (PG/SG), {m['F']} ali (SF/PF), {m['C']} centri (C); i 10-day non contano.  ",
             "Stato: ✅ rispettati coi ruoli ufficiali · 🟡 non ancora, ma i giocatori senza ruolo possono coprirli · "
             "❌ mancano posti anche con la scelta migliore.", ""]
    ok = sum(d["stato"].startswith("✅") for _, d in squadre)
    righe += [f"**{ok}/{len(squadre)}** squadre rispettano i minimi · senza ruolo: "
              f"**{sum(len(d['senza']) for _, d in squadre)}** giocatori · dichiarazioni in sospeso: "
              f"**{sum(len(d['in_sospeso']) for _, d in squadre)}**", "",
              "## Riepilogo", "",
              "| Squadra | PG | SG | SF | PF | C | Guardie | Ali | Centri | Senza ruolo | In sospeso | Cambi | Minimi |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t, d in squadre:
        pr, c = d["per_ruolo"], d["cat"]
        righe.append(f"| {_md(t['nome'])} | " + " | ".join(str(pr[p]) for p in RUOLI)
                     + f" | {c['G']}/{m['G']} | {c['F']}/{m['F']} | {c['C']}/{m['C']} | {len(d['senza'])} | "
                     f"{len(d['in_sospeso'])} | {d['cambi']}/{regole.max_cambi_ordinari()} | {d['stato']} |")
    for t, d in squadre:
        c = d["cat"]
        gm = ", ".join(str(x) for x in ([t.get("gm_nome")] if t.get("gm_nome") else []))
        righe += ["", f"## {_md(t['nome'])}" + (f" — {_md(gm)}" if gm else ""), "",
                  f"Guardie {c['G']}/{m['G']} · ali {c['F']}/{m['F']} · centri {c['C']}/{m['C']} · {d['stato']}  ",
                  f"Cambi ordinari {d['cambi']}/{regole.max_cambi_ordinari()} · Saedro "
                  f"{'usata' if d['saedro'] else 'disponibile'}", ""]
        if not d["giocatori"]:
            righe.append("_Roster vuoto._")
            continue
        righe += ["| Ruolo | Giocatore | Eleggibili | Note |", "|---|---|---|---|"]
        for g in d["giocatori"]:
            righe.append(f"| {g['ruolo'] or '❔'} | {_md(g['nome'])} | {', '.join(g['eleggibili']) or '—'} | "
                         f"{_md('; '.join(g['note']))} |")
    return "\n".join(righe) + "\n"


async def _manda(bot, chat_id: int, chi: str):
    adesso = datetime.now(timezone.utc)
    testo = await asyncio.to_thread(report, adesso)     # tante query: in un thread, il bot resta libero
    nome = f"ruoli-{adesso.astimezone(ROMA):%Y%m%d-%H%M}.md"
    await bot.send_document(chat_id=chat_id, document=io.BytesIO(testo.encode("utf-8")), filename=nome,
                            caption=f"🎽 Report ruoli di tutte le squadre ({adesso.astimezone(ROMA):%d/%m %H:%M})")
    logger.info("Report ruoli chiesto da %s", chi)


async def cmd_report_ruoli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not settings.is_admin(u.id):
        return
    await _manda(context.bot, update.effective_chat.id, u.first_name or str(u.id))


async def cb_report_ruoli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not settings.is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer("Preparo il report…")
    await _manda(context.bot, q.message.chat_id, q.from_user.first_name or str(q.from_user.id))


def get_handlers() -> list:
    return [CommandHandler("report_ruoli", cmd_report_ruoli),
            CallbackQueryHandler(cb_report_ruoli, pattern=r"^rrep:md$")]

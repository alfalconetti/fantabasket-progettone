"""
/report_formazioni [N] (admin, v21): quintetti e panchine di tutte le squadre per una giornata, in un
file Markdown, coi problemi in evidenza. Senza N: la prossima giornata (quella delle panchine), o
quella in corso se non ce n'è una aperta. Prima della scadenza i quintetti sono quelli di adesso
(ipa_quintetto); a giornata chiusa le formazioni congelate (ipa_formazioni).

Per ogni giocatore: squadra NBA, partite nella giornata, stato degli infortunati (ultimo snapshot di
ESPN) e le note che contano per il calcolo: non più in squadra, ruolo cambiato, titolare anche in
panchina, senza id ESPN (0 punti), squadra NBA senza partite (a media), Out/Doubtful. In cima il
riepilogo: chi non ha mandato la panchina, chi non ha confermato il quintetto, quanti titolari
hanno problemi. Solo lettura.
"""
import asyncio
import io
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import config
import db
from comune import GIORNI, ROMA, adesso, giornata_in_corso, ora, partite_squadre_nba, prossima_giornata, segno_stato
from shared import regole

logger = logging.getLogger(__name__)
RUOLI = ("PG", "SG", "SF", "PF", "C")
GRAVI = {"out", "suspension", "doubtful"}
DUBBI = {"questionable", "day-to-day"}


def _md(x) -> str:
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")


def _accoppiamenti(s: str, n: int) -> dict[str, tuple[str, bool]]:
    """{squadra: (avversaria, in casa)} dal calendario di loucabot, se c'è."""
    if not db.q("SELECT to_regclass('lega_partite') AS t", one=True)["t"]:
        return {}
    out = {}
    for p in db.q("SELECT casa, trasferta FROM lega_partite WHERE stagione = %s AND giornata = %s", (s, n), many=True) or []:
        out[p["casa"]] = (p["trasferta"], True)
        out[p["trasferta"]] = (p["casa"], False)
    return out


def scegli_giornata(n: int | None) -> dict | None:
    s = config.stagione()
    if n:
        return db.giornata(s, n)
    import comune
    return comune.panchine_bloccate(s) or prossima_giornata(s) or giornata_in_corso(s)   # in corso fino alle 6


def report(g: dict) -> str:
    s, n = config.stagione(), g["numero"]
    chiusa = bool(db.stato_giornata(s, n)["chiusa"])
    partite = partite_squadre_nba(g)
    media = set(g.get("media") or [])
    conf, panche, acc = db.conferme(s, n), db.panchine(s, n), _accoppiamenti(s, n)
    squadre = config.squadre()
    dati, tutti = {}, set()
    for t in squadre:
        q = db.formazione(s, n, t["id"]) if chiusa else db.quintetto(t["id"])
        p = panche.get(t["id"])
        righe_p = (p["righe"] if isinstance(p["righe"], list) else []) if p else []
        rosa = {x["id"]: x for x in db.roster(t["id"], s)}
        dati[t["id"]] = (q, p, righe_p, rosa)
        tutti |= {v for v in q.values() if v} | {r.get("giocatore_id") for r in righe_p if r.get("giocatore_id")}
    nomi = db.nomi_giocatori(list(tutti))
    nba = db.squadre_nba_giocatori(list(tutti))
    st, quando = db.stati_espn(list(tutti))
    espn = {r["id"]: r["espn_id"] for r in db.q("SELECT id, espn_id FROM giocatori WHERE id = ANY(%s)", (list(tutti),), many=True) or []} if tutti else {}

    def info(gid: int, rosa: dict) -> tuple[str, str, str, list[str], bool]:
        """(squadra NBA, partite, stato, note, grave)"""
        note, grave = [], False
        sq = nba.get(gid)
        mie = partite.get(sq, []) if sq else []
        giocabili = [x for x in mie if x["stato"] not in ("STATUS_POSTPONED", "STATUS_CANCELED")]
        if mie:
            part = ", ".join(f"{GIORNI[x['data_et'].weekday()]} {x['data_et'].day} {'vs' if x['in_casa'] else '@'} {x['avversario']}"
                             + (" (rinviata)" if x not in giocabili else "") for x in mie)
        else:
            part = "—"
            if sq:
                note.append("nessuna partita: media" if sq in media or not media else "nessuna partita")
        stato = (st.get(gid) or {}).get("stato") or ""
        if stato.strip().lower() in GRAVI:
            grave = True
        elif stato.strip().lower() in DUBBI:
            note.append("da seguire")
        if not espn.get(gid):
            grave = True
            note.append("senza id ESPN: 0 punti")
        if gid not in rosa:
            grave = True
            note.append("non più in squadra")
        return sq or "?", part, (segno_stato(stato).strip() if stato else "—"), note, grave

    righe = [f"# Formazioni della giornata {n} — stagione {s}", "",
             f"Scadenza: {ora(g.get('prima_partita'))} · giorni NBA {g['dal']:%d/%m}–{g['al']:%d/%m} · "
             f"{'**chiusa**: formazioni congelate (quelle del calcolo)' if chiusa else 'aperta: quintetti di adesso, possono ancora cambiare'}  ",
             f"Infortunati: ultimo snapshot ESPN {ora(quando) if quando else '— (nessuno)'} · prendono la media: "
             f"{', '.join(sorted(media)) or 'nessuna'}  ",
             f"Report del {adesso().astimezone(ROMA):%d/%m/%Y %H:%M} (ora italiana). Su Yahoo fa fede il quintetto vero: "
             "qui quello che sa il bot.", ""]
    senza_p = [t["nome"] for t in squadre if not dati[t["id"]][1]]
    senza_c = [t["nome"] for t in squadre if t["id"] not in conf]
    riep = ["## Riepilogo", "",
            "| Squadra | Avversaria | Quintetto | Panchina | Titolari con problemi | Panchinari con problemi |",
            "|---|---|---|---|---|---|"]
    sezioni = []
    for t in squadre:
        q, p, righe_p, rosa = dati[t["id"]]
        c = conf.get(t["id"])
        stato_q = "✅ confermato" if c and c["stato"] == "confermato" else ("✏️ modificato" if c else "— da controllare")
        av = acc.get(t["id"])
        avv = (f"{'vs' if av[1] else '@'} {config.nome(av[0])}") if av else "—"
        tab = ["| Posto | Giocatore | Ruolo | Squadra NBA | Partite | Stato | Note |", "|---|---|---|---|---|---|---|"]
        prob_t = prob_p = 0
        titolari = {v for v in q.values() if v}
        for ruolo in RUOLI:
            gid = q.get(ruolo)
            if not gid:
                prob_t += 1
                tab.append(f"| Q-{ruolo} | — | {ruolo} | | | | **posto vuoto: 0 punti** |")
                continue
            sq, part, stato, note, grave = info(gid, rosa)
            r_att = (rosa.get(gid) or {}).get("ruolo")
            if r_att and r_att != ruolo:
                note.append(f"ora è {r_att}")
                grave = True
            if any(r.get("giocatore_id") == gid for r in righe_p):
                note.append("anche in panchina (lì quella posizione vale 0, gli altri non scalano)")
            prob_t += grave or bool(note)
            tab.append(f"| Q-{ruolo} | {_md(nomi.get(gid, gid))} | {ruolo} | {sq} | {_md(part)} | {_md(stato)} | "
                       f"{_md('; '.join(note))} |")
        if not p:
            tab.append("| P | — | | | | | **panchina non mandata: niente supplementari** |")
        else:
            for i, r in enumerate(righe_p, 1):
                gid = r.get("giocatore_id")
                if not gid:
                    prob_p += 1
                    tab.append(f"| P{i} | {_md(r.get('testo') or '?')} | | | | | **non abbinato** |")
                    continue
                sq, part, stato, note, grave = info(gid, rosa)
                if gid in titolari:
                    note.append("è anche titolare: tolto dalla panchina")
                prob_p += grave or bool(note)
                tab.append(f"| P{i} | {_md(nomi.get(gid, gid))} | {_md(r.get('ruolo') or (rosa.get(gid) or {}).get('ruolo') or '')} | "
                           f"{sq} | {_md(part)} | {_md(stato)} | {_md('; '.join(note))} |")
            if len(righe_p) != regole.giocatori_panchina():
                prob_p += 1
                tab.append(f"| | | | | | | **{len(righe_p)} panchinari invece di {regole.giocatori_panchina()}** |")
        panca = ("❌ non mandata" if not p else ("⏰ in ritardo" if p.get("in_ritardo") else "🪑 mandata")
                 + (f" ({ora(p.get('inviata'))})" if p and p.get("inviata") else ""))
        riep.append(f"| {_md(t['nome'])} | {_md(avv)} | {stato_q} | {panca} | {prob_t or ''} | {prob_p or ''} |")
        titolo = f"## {_md(t['nome'])}" + (f" ({_md(avv)})" if av else "")
        sezioni += ["", titolo, "", f"Quintetto {stato_q} · panchina {panca}"
                    + (f" · titolo «{_md(p['titolo'])}»" if p and p.get("titolo") else ""), ""] + tab
    righe += [f"Panchine mancanti: **{len(senza_p)}**" + (f" — {_md(', '.join(senza_p))}" if senza_p else "") + "  ",
              f"Quintetti non confermati: **{len(senza_c)}**" + (f" — {_md(', '.join(senza_c))}" if senza_c else ""), ""]
    return "\n".join(righe + riep + sezioni) + "\n"


async def cmd_report_formazioni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not config.is_admin(u.id):
        return
    msg = update.effective_message
    n = int(context.args[0].lstrip("Gg")) if context.args and context.args[0].lstrip("Gg").isdigit() else None
    g = scegli_giornata(n)
    if not g:
        await msg.reply_text("Nessuna giornata da mostrare (calendario non caricato?). Uso: /report_formazioni [N]")
        return
    testo = await asyncio.to_thread(report, g)     # tante query: in un thread, il bot resta libero
    nome = f"formazioni-G{g['numero']}-{adesso().astimezone(ROMA):%Y%m%d-%H%M}.md"
    await context.bot.send_document(chat_id=update.effective_chat.id, document=io.BytesIO(testo.encode("utf-8")),
                                    filename=nome, caption=f"🏀 Formazioni della giornata {g['numero']}: quintetti e panchine di tutte le squadre")


def get_handlers() -> list:
    return [CommandHandler("report_formazioni", cmd_report_formazioni)]

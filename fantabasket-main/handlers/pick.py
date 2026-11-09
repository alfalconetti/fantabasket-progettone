"""
/pick [SQUADRA] [1|2] [ANNO] (v7.3.0, Luca 09/11): di chi è una pick e la sua storia.

Argomenti in qualsiasi ordine: 1 o 2 (anche «1°», «r2», «2nd») è il giro, un anno (2028, «28») è l'anno del
draft, il resto è la squadra a cui apparteneva in origine (id, nome, GM o alias, la ricerca di sempre).
Default: la squadra di chi scrive, 1° giro, il prossimo draft (stagione in corso + 1: nella stagione
2026-27 il draft è quello del 2027).

Risposta: la pick (anno, giro, di chi era), il proprietario di adesso, protezioni, se è già stata usata
(numero e giocatore scelto), e la storia dal registro (transazioni con oggetto 'pick'): avvio del bot,
ogni trade col suo numero (TRADE-AAAA-NNN, da cercare con /trova_trade), e le trade annullate segnate come
tali accanto alla trade, con la data dell'annullamento.

/pick_lega (v7.3.0, Luca 09/11, mockup approvato, variante A): un'immagine con tutte le pick della lega, in privato
e nei gruppi. Una riga per squadra (a cui spetta la pick in origine), per ogni anno del draft due caselle (1° e 2°
giro) con logo e sigla di chi ce l'ha adesso (in grigio se ce l'ha ancora lei), protette con *, usate col numero; in
fondo quante pick di ogni giro ha in mano ogni squadra. Sigle: il campo `sigla` di teams.json se c'è, se no le
prime tre lettere del nome, rese diverse tra loro (`sigle`). Disegno in pick_lega.typ.
"""
import asyncio
import html
import json
import os
import re
from datetime import datetime

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import database as db
import settings
import teams as tm
from utils import ROME


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _nome(team_id: str | None) -> str:
    if not team_id:
        return "—"
    return (tm.get_team_by_id(team_id) or {}).get("nome", team_id)


def leggi_argomenti(args: list[str], stagione: str) -> tuple[str | None, int, str, str | None]:
    """(testo della squadra o None, giro, anno, errore). Il giro e l'anno si riconoscono, il resto è la squadra."""
    giro, anno, resto = None, None, []
    for a in args:
        x = a.strip().lower()
        m_giro = re.fullmatch(r"(?:r|round\s*)?([12])(?:°|st|nd|o)?", x)
        m_anno = re.fullmatch(r"(?:20)?(\d{2})", x)
        if m_giro and giro is None:
            giro = int(m_giro.group(1))
        elif m_anno and anno is None and len(x) in (2, 4):
            anno = "20" + m_anno.group(1)
        else:
            resto.append(a)
    return (" ".join(resto) or None), giro or 1, anno or str(int(stagione) + 1), None


def trova(proprietario_orig: str, giro: int, anno: str) -> dict | None:
    return db._q("SELECT * FROM pick WHERE proprietario_orig = %s AND round = %s AND anno = %s",
                 (proprietario_orig, giro, str(anno)), one=True)


def storia(pick_id: int) -> list[dict]:
    """I movimenti della pick, in ordine, col numero della trade (se c'è) e lo stato della trade."""
    return db.storia_pick(pick_id)


def _quando(ts) -> str:
    return f"{ts.astimezone(ROME):%d/%m/%Y}" if ts else "?"


def righe_storia(mov: list[dict]) -> list[str]:
    """Una riga per movimento; l'annullamento di una trade va sulla riga della trade, non a parte."""
    annullate = {}
    for r in mov:
        if (r.get("note") or "").upper().startswith("ANNULLAMENTO") and r.get("trade_id"):
            annullate[r["trade_id"]] = r
    out = []
    for r in mov:
        nota = r.get("note") or ""
        if nota.upper().startswith("ANNULLAMENTO") and r.get("trade_id") in annullate:
            continue                                        # già sulla riga della trade
        quando = _quando(r["timestamp"])
        if r["tipo"] == "iniziale":
            out.append(f"• {quando} · all'avvio del bot: di <b>{e(_nome(r['team_id_a']))}</b>")
        elif r["tipo"] in ("traded", "trade"):
            ref = r.get("trade_ref") or (f"trade #{r['trade_id']}" if r.get("trade_id") else "trade")
            riga = f"• {quando} · <b>{e(ref)}</b>: {e(_nome(r['team_id_da']))} → <b>{e(_nome(r['team_id_a']))}</b>"
            a = annullate.get(r.get("trade_id"))
            if a:
                riga += f" · <i>annullata il {_quando(a['timestamp'])}, torna a {e(_nome(r['team_id_da']))}</i>"
            out.append(riga)
        else:
            da, a = r.get("team_id_da"), r.get("team_id_a")
            out.append(f"• {quando} · {e(r['tipo'])}" + (f": {e(_nome(da))} → {e(_nome(a))}" if da or a else "")
                       + (f" <i>({e(nota)})</i>" if nota else ""))
    return out


def _protezioni(p) -> str:
    from handlers.trova_trade import _protezioni as prot
    return prot(p)


def scheda(p: dict) -> str:
    giro = "1° giro" if p["round"] == 1 else "2° giro"
    righe = [f"🎯 <b>Pick {e(p['anno'])} · {giro}</b> di <b>{e(_nome(p['proprietario_orig']))}</b>"]
    if p["scattata"]:
        scelto = db._q("""SELECT g.nome_common FROM rookie r JOIN giocatori g ON g.id = r.giocatore_id
                          WHERE r.anno_draft::text = %s AND r.round = %s AND r.pick_numero = %s LIMIT 1""",
                       (str(p["anno"]), p["round"], p.get("numero_scelta")), one=True) if p.get("numero_scelta") else None
        righe.append("✅ Già usata" + (f": scelta <b>#{p['numero_scelta']}</b>" if p.get("numero_scelta") else "")
                     + (f", {e(scelto['nome_common'])}" if scelto else "")
                     + f" · l'ha usata <b>{e(_nome(p['proprietario_att']))}</b>")
    elif p["proprietario_att"] == p["proprietario_orig"]:
        righe.append(f"📍 Proprietario: <b>{e(_nome(p['proprietario_att']))}</b> (è ancora sua)")
    else:
        righe.append(f"📍 Proprietario: <b>{e(_nome(p['proprietario_att']))}</b>")
    prot = _protezioni(p.get("protezioni"))
    if prot:
        righe.append(f"🛡️ Protezioni: {e(prot)}")
    st = righe_storia(storia(p["id"]))
    righe += ["", "<b>Storia</b>"] + (st or ["• nessun movimento nel registro: non è mai stata scambiata"])
    if any("TRADE-" in x for x in st):
        righe += ["", "<i>Il dettaglio di una trade con /trova_trade NUMERO.</i>"]
    return "\n".join(righe)


async def cmd_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    s = settings.stagione_corrente()
    testo, giro, anno, _ = leggi_argomenti(list(context.args or []), s)
    if testo:
        team = tm.get_team_by_query(testo)
        if not team:
            await msg.reply_text(f"❌ Squadra «{testo}» non trovata.\nUso: /pick [SQUADRA] [1|2] [ANNO], es. /pick Tibur 2 2028")
            return
    else:
        team = tm.get_team_by_gm(update.effective_user.id)
        if not team:
            await msg.reply_text("Uso: /pick SQUADRA [1|2] [ANNO], es. /pick Tibur 2 2028 (senza squadra vale la tua, se sei un GM).")
            return
    p = trova(team["id"], giro, anno)
    if not p:
        anni = db._q("SELECT MIN(anno) AS a, MAX(anno) AS b FROM pick", one=True) or {}
        await msg.reply_text(f"❌ Nessuna pick {anno} del {giro}° giro di {team.get('nome', team['id'])}."
                             + (f" Le pick vanno dal {anni['a']} al {anni['b']}." if anni.get("a") else ""))
        return
    await msg.reply_text(scheda(p), parse_mode="HTML")


# ── /pick_lega ──────────────────────────────────────────────────────────────────

TEMPLATE_LEGA = os.path.join(os.path.dirname(__file__), "..", "pick_lega.typ")


def sigle(squadre: list[dict]) -> dict[str, str]:
    """{team_id: sigla}: il campo «sigla» di teams.json, se no le prime tre lettere (solo lettere) della prima parola del
    nome; se due squadre si scontrano, la seconda prende la lettera dopo nel nome (Montecelio MON, Monterotondo MOO…)."""
    import unicodedata
    pulisci = lambda s: "".join(c for c in unicodedata.normalize("NFD", s or "") if c.isalpha() and unicodedata.category(c) != "Mn").upper()
    out, usate = {}, set()
    for t in squadre:
        if (t.get("sigla") or "").strip():
            out[t["id"]] = t["sigla"].strip().upper()[:4]
            usate.add(out[t["id"]])
    for t in squadre:
        if t["id"] in out:
            continue
        lettere = pulisci(t.get("nome") or t["id"]) or t["id"].upper()
        prima = pulisci((t.get("nome") or "").split()[0]) if (t.get("nome") or "").split() else lettere
        cand = (prima or lettere)[:3].ljust(3, "X")
        resto = lettere[3:] if lettere.startswith(cand) else lettere
        i = 0
        while cand in usate:                                # cambia l'ultima lettera con le successive del nome
            cand = cand[:2] + (resto[i] if i < len(resto) else str(i - len(resto) + 1))
            i += 1
        out[t["id"]] = cand
        usate.add(cand)
    return out


def dati_lega(ora: datetime | None = None) -> dict:
    from handlers.carriera import sq_fanta
    squadre = tm.get_all_teams()
    sg = sigle(squadre)
    anni = [r["anno"] for r in db._q("SELECT DISTINCT anno FROM pick ORDER BY anno", many=True) or []]
    s = settings.stagione_corrente()
    anni = [a for a in anni if int(a) > int(s)] or anni             # le pick del draft già fatto non servono più
    pick = db._q("SELECT * FROM pick WHERE anno = ANY(%s)", (anni,), many=True) or []
    per = {(p["proprietario_orig"], p["anno"], p["round"]): p for p in pick}
    info = {}
    for t in squadre:
        f = sq_fanta(t["id"]) or {}
        info[t["id"]] = {"nome": t.get("nome", t["id"]), "sigla": sg[t["id"]], "colore": f.get("colore") or "#1A237E",
                         "logo": f.get("logo") or ""}
    righe = []
    for t in sorted(squadre, key=lambda x: (x.get("nome") or x["id"]).lower()):
        celle = []
        for a in anni:
            for g in (1, 2):
                p = per.get((t["id"], a, g))
                if not p:
                    celle.append({"k": "nessuna"})
                elif p["scattata"]:
                    celle.append({"k": "usata", "num": p.get("numero_scelta") or "?"})
                elif p["proprietario_att"] == t["id"]:
                    celle.append({"k": "propria", "a": t["id"]})
                else:
                    celle.append({"k": "altra", "a": p["proprietario_att"], "prot": bool(p.get("protezioni"))})
        mano = lambda g: sum(1 for p in pick if p["proprietario_att"] == t["id"] and p["round"] == g and not p["scattata"])
        righe.append({"team": t["id"], "celle": celle, "mano1": mano(1), "mano2": mano(2)})
    for p in pick:                                     # una squadra che non c'è più in teams.json: almeno la sigla
        info.setdefault(p["proprietario_att"], {"nome": p["proprietario_att"], "sigla": p["proprietario_att"][:3].upper(),
                                                "colore": "#9AA3B5", "logo": ""})
    ora = (ora or datetime.now(ROME)).astimezone(ROME)
    return {"anni": anni, "squadre": info, "righe": righe, "aggiornato": f"{ora:%d/%m/%Y} alle {ora:%H:%M}"}


def immagine_lega(d: dict) -> bytes:
    import typst
    from typst_compila import FONT
    png = typst.compile(TEMPLATE_LEGA, root="/", format="png", ppi=180, font_paths=[f for f in FONT if os.path.isdir(f)],
                        sys_inputs={"dati": json.dumps(d, ensure_ascii=False)})
    return png[0] if isinstance(png, list) else png


async def cmd_pick_lega(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    d = await asyncio.to_thread(dati_lega)
    if not d["anni"]:
        await msg.reply_text("Nessuna pick nel database.")
        return
    png = await asyncio.to_thread(immagine_lega, d)
    await msg.reply_photo(png, caption=f"🎯 Le pick della lega, draft {d['anni'][0]}–{d['anni'][-1]} · "
                                       "la storia di una pick con /pick SQUADRA GIRO ANNO")


def get_handlers() -> list:
    return [CommandHandler("pick", cmd_pick), CommandHandler("pick_lega", cmd_pick_lega)]

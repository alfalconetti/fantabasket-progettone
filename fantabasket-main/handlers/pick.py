"""
/pick (v7.22.0, Luca 22/11, mockup approvati):
- /pick, /pick SQUADRA (o GM): immagine con le pick che la squadra ha IN MANO (sue e prese da altre), per draft e
  giro, coi colori della sua palette (/palette), più la colonna delle sue pick cedute (a chi, protezioni);
  /pick SQUADRA ANNO lo stesso per un draft, /pick SQUADRA GIRO solo quel giro, di tutti gli anni.
- /pick_lega ANNO (v7.22.2; prima /pick ANNO): immagine con tutte le pick di quel draft (stile /pick_lega: a chi
  spettava, chi ce l'ha, protezioni, in mano 1°·2°); /pick_lega ANNO GIRO solo quel giro. /pick_lega senza anno com'era.
- Senza squadra vale sempre la tua (v7.22.2): /pick ANNO, /pick GIRO, /pick GIRO ANNO.
- /pick SQUADRA GIRO ANNO (tutti e tre): il dettaglio di una pick con la storia, come prima; qui SQUADRA è la squadra a
  cui spettava la pick in origine.
Disegni in pick_squadra.typ e pick_anno.typ.

Prima (v7.3.0, Luca 09/11), /pick [SQUADRA] [1|2] [ANNO]: di chi è una pick e la sua storia.

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


def leggi(args: list[str]) -> tuple[str | None, int | None, str | None]:
    """(testo della squadra o None, giro o None, anno o None), senza default (v7.22.0)."""
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
    return (" ".join(resto) or None), giro, anno


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


def _scelto(p: dict) -> dict | None:
    """Il giocatore scelto con una pick già usata (dal registro dei rookie), o None."""
    legato = db._q("""SELECT g.nome_common FROM rookie r JOIN giocatori g ON g.id = r.giocatore_id
                      WHERE r.pick_id = %s LIMIT 1""", (p["id"],), one=True) if p.get("id") else None
    if legato or not p.get("numero_scelta"):            # v7.36.0: dal legame; per i rookie vecchi senza, dal numero
        return legato
    return db._q("""SELECT g.nome_common FROM rookie r JOIN giocatori g ON g.id = r.giocatore_id
                    WHERE r.pick_id IS NULL AND r.anno_draft::text = %s AND r.round = %s AND r.pick_numero = %s LIMIT 1""",
                 (str(p["anno"]), p["round"], p.get("numero_scelta")), one=True)


def scheda(p: dict) -> str:
    giro = "1° giro" if p["round"] == 1 else "2° giro"
    righe = [f"🎯 <b>Pick {e(p['anno'])} · {giro}</b> di <b>{e(_nome(p['proprietario_orig']))}</b>"]
    if p["scattata"]:
        scelto = _scelto(p)
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


USO = ("Uso: /pick [SQUADRA] [ANNO] [GIRO] [DATA] — le pick che la squadra ha in mano (senza squadra la tua, se sei un GM); "
       "con giro e anno la storia di una pick (SQUADRA: a chi spettava). Tutta la lega: /pick_lega [ANNO] [GIRO]. "
       "Tutti i modi: /pick aiuto")


def aiuto() -> str:
    """/pick aiuto (v7.22.2, Luca 22/11): tutti i modi di usare /pick e /pick_lega, con squadre vere negli esempi."""
    from shared import esempi as ES
    a = ES.squadra()
    return ("🎯 <b>/pick</b> — le pick, squadra per squadra\n"
            "• <code>/pick</code> — le pick che hai in mano (tue e prese da altri), di tutti gli anni, e quelle che hai ceduto\n"
            "• <code>/pick 2028</code> — solo quel draft · <code>/pick 1</code> — solo il 1° giro\n"
            f"• <code>/pick {e(a)}</code> — le stesse di un'altra squadra (nome, GM o alias), anche con anno o giro\n"
            "• <code>/pick 1 2028</code> — la storia della tua 1ª 2028: chi ce l'ha, protezioni, ogni trade\n"
            f"• <code>/pick {e(a)} 1 2028</code> — la storia di quella pick: qui la squadra è quella <b>a cui spettava</b>\n"
            "Anno anche «28», giro anche «2°» o «r2», in qualsiasi ordine.\n"
            "📅 Con una data com'erano allora, dal registro: <code>/pick 15/01/2027</code>, "
            f"<code>/pick {e(a)} 2028 15/01/2027</code>\n\n"
            "🏀 <b>/pick_lega</b> — tutta la lega\n"
            "• <code>/pick_lega</code> — tutte le pick di tutti i draft\n"
            "• <code>/pick_lega 2028</code> — tutto quel draft: di chi erano e chi ce l'ha · <code>/pick_lega 2028 1</code> solo il 1° giro\n"
            "• <code>/pick_lega 15/01/2027</code>, <code>/pick_lega 2028 15/01/2027</code> — com'erano a quella data")


async def cmd_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v7.22.0 (Luca, 22/11): vedi la docstring del modulo."""
    msg = update.effective_message
    if [x.lower() for x in context.args or []] in (["aiuto"], ["help"], ["?"]):
        await msg.reply_text(aiuto(), parse_mode="HTML")
        return
    args, al = estrai_data(list(context.args or []))       # v7.36.0: /pick … DATA com'era a quella data
    if al and al > datetime.now(ROME):
        await msg.reply_text("❌ La data non può essere nel futuro.")
        return
    testo, giro, anno = leggi(args)
    if testo:
        team = tm.get_team_by_query(testo)
        if not team:
            await msg.reply_text(f"❌ Squadra «{testo}» non trovata.\n{USO}")
            return
    else:                                                 # v7.22.2 (Luca, 22/11): senza squadra vale sempre la tua
        team = tm.get_team_by_gm(update.effective_user.id)
        if not team:
            await msg.reply_text(USO)
            return
    if giro and anno:                                     # tutto: il dettaglio con la storia
        p = trova(team["id"], giro, anno)
        if not p:
            anni = db._q("SELECT MIN(anno) AS a, MAX(anno) AS b FROM pick", one=True) or {}
            await msg.reply_text(f"❌ Nessuna pick {anno} del {giro}° giro di {team.get('nome', team['id'])}."
                                 + (f" Le pick vanno dal {anni['a']} al {anni['b']}." if anni.get("a") else ""))
            return
        await msg.reply_text(scheda(p), parse_mode="HTML")
        return
    d = await asyncio.to_thread(dati_squadra, team, anno, giro, None, al)
    if not d["righe"]:
        await msg.reply_text(f"❌ Nessuna pick" + (f" del draft {anno}" if anno else "") + (f" al {al:%d/%m/%Y}" if al else "")
                             + " nel database.")
        return
    png = await asyncio.to_thread(immagine, TEMPLATE_SQUADRA, d)
    await msg.reply_photo(png, caption=f"🎯 Le pick di {team.get('nome', team['id'])}" + (f"\n📅 com'erano al {al:%d/%m/%Y}" if al else "")
                                       + " · la storia di una pick con /pick SQUADRA GIRO ANNO (la squadra a cui spettava)")


# ── /pick SQUADRA, /pick ANNO: le immagini (v7.22.0) ───────────────────────────

TEMPLATE_SQUADRA = os.path.join(os.path.dirname(__file__), "..", "pick_squadra.typ")
TEMPLATE_ANNO = os.path.join(os.path.dirname(__file__), "..", "pick_anno.typ")


def estrai_data(args: list[str]) -> tuple[list[str], datetime | None]:
    """v7.36.0: (argomenti senza la data, fine di quel giorno o None). La data come in /roster (GG/MM/AAAA, AAAA-MM-GG…)."""
    from datetime import timezone
    from shared.date_comandi import leggi_data
    resto, al = [], None
    for a in args:
        g = leggi_data(a) if a[:1].isdigit() and not re.fullmatch(r"(?:20)?\d{2}", a.strip()) else None
        if g and al is None:
            al = datetime(g.year, g.month, g.day, 23, 59, tzinfo=timezone.utc)
        else:
            resto.append(a)
    return resto, al


def _pick(anni: list[str] | None = None, giri: list[int] | None = None, al: datetime | None = None) -> list[dict]:
    """Le pick (di quei draft e giri), di adesso o com'erano a una data (v7.36.0, dal registro)."""
    if al:
        tutte = db.pick_al(al.isoformat())
    else:
        tutte = db._q("SELECT * FROM pick", many=True) or []
    return sorted((p for p in tutte if (anni is None or str(p["anno"]) in anni) and (giri is None or p["round"] in giri)),
                  key=lambda p: (str(p["anno"]), p["round"], p["proprietario_orig"]))


def _stagione(al: datetime | None = None) -> int:
    return db.stagione_al(al) if al else int(settings.stagione_corrente())


def _anni(anno: str | None, al: datetime | None = None) -> list[str]:
    """[anno], o i draft ancora da fare (quelli già fatti non servono più; se non ce ne sono, tutti), a quella data."""
    if anno:
        return [str(anno)]
    anni = sorted({str(p["anno"]) for p in _pick(al=al)})
    s = _stagione(al)
    return [a for a in anni if int(a) > int(s)] or anni


def _usata(p: dict) -> str:
    if not p["scattata"]:
        return ""
    sc = _scelto(p)
    return f"#{p.get('numero_scelta') or '?'}" + (f" · {sc['nome_common']}" if sc else "")


def _ora(ora: datetime | None = None) -> str:
    ora = (ora or datetime.now(ROME)).astimezone(ROME)
    return f"{ora:%d/%m/%Y} alle {ora:%H:%M}"


def _com_era(al: datetime | None) -> str:
    """v7.36.0: a una data passata l'immagine dice «com'era al …» (come /roster con la data)."""
    return f"com'era al {al:%d/%m/%Y}" if al else ""


def info_squadre(pick: list[dict]) -> dict:
    """{team_id: nome, sigla, colore, logo}, anche per una squadra che non c'è più in teams.json (dalle pick)."""
    from handlers.carriera import sq_fanta
    squadre = tm.get_all_teams()
    sg = sigle(squadre)
    info = {}
    for t in squadre:
        f = sq_fanta(t["id"]) or {}
        info[t["id"]] = {"nome": t.get("nome", t["id"]), "sigla": sg[t["id"]], "colore": f.get("colore") or "#1A237E",
                         "logo": f.get("logo") or ""}
    for p in pick:
        for k in ("proprietario_att", "proprietario_orig"):
            info.setdefault(p[k], {"nome": p[k], "sigla": p[k][:3].upper(), "colore": "#9AA3B5", "logo": ""})
    return info


def palette(team: dict) -> dict:
    """I colori della squadra (/palette), come nel roster, e i testi leggibili sopra."""
    from handlers.roster import _text_on, _text_on_muted, colori_effettivi
    c = colori_effettivi(team)
    return {**c, "t_header": _text_on(c["header"]), "t_header_m": _text_on_muted(c["header"]), "t_dark": _text_on(c["dark"]),
            "t_riga1": _text_on(c["riga1"]), "t_riga2": _text_on(c["riga2"]), "t_sezione": _text_on(c["sezione"]),
            "t_pick": _text_on(c["pick"])}


def dati_squadra(team: dict, anno: str | None = None, giro: int | None = None, ora: datetime | None = None,
                 al: datetime | None = None) -> dict:
    """Per pick_squadra.typ: le pick che `team` ha in mano, draft per draft (e giro), e le sue cedute (a una data, `al`)."""
    T = team["id"]
    anni = _anni(anno, al)
    giri = [giro] if giro else [1, 2]
    pick = _pick(anni, giri, al)
    chip = lambda p: {"orig": p["proprietario_orig"], "propria": p["proprietario_orig"] == T,
                      "prot": _protezioni(p.get("protezioni")) or "", "usata": _usata(p)}
    righe = []
    for a in anni:
        mie = [p for p in pick if p["anno"] == a and p["proprietario_att"] == T]
        mie.sort(key=lambda p: (p["proprietario_orig"] != T, _nome(p["proprietario_orig"]).lower()))
        cedute = [p for p in pick if p["anno"] == a and p["proprietario_orig"] == T and p["proprietario_att"] != T]
        righe.append({"anno": a, "giri": [[chip(p) for p in mie if p["round"] == g] for g in giri],
                      "cedute": [{"giro": p["round"], "a": p["proprietario_att"], "prot": _protezioni(p.get("protezioni")) or "",
                                  "usata": _usata(p)} for p in cedute]})
    if not pick:
        righe = []
    in_mano = lambda g: sum(1 for p in pick if p["proprietario_att"] == T and p["round"] == g and not p["scattata"])
    titolo = (f"draft {anni[0]}" if len(anni) == 1 else f"draft {anni[0]}–{anni[-1]}") + (f" · {giro}° giro" if giro else "")
    mano = " · in mano: " + ", ".join(f"{in_mano(g)} di {g}° giro" for g in giri)
    info = info_squadre(pick + [{"proprietario_att": T, "proprietario_orig": T}])
    if info[T]["nome"] == T and team.get("nome"):
        info[T]["nome"] = team["nome"]
    return {"team": T, "squadre": info, "quando": _com_era(al),
            "colori": palette(team), "giri": giri, "righe": righe, "titolo": titolo + mano, "aggiornato": _ora(ora)}


def dati_anno(anno: str, giro: int | None = None, ora: datetime | None = None, al: datetime | None = None) -> dict:
    """Per pick_anno.typ: tutte le pick di un draft, una riga per squadra a cui spettavano (a una data, `al`)."""
    giri = [giro] if giro else [1, 2]
    pick = _pick([str(anno)], giri, al)
    per = {(p["proprietario_orig"], p["round"]): p for p in pick}
    origini = {p["proprietario_orig"] for p in pick}
    info = info_squadre(pick)
    righe = []
    for t in sorted(origini, key=lambda x: info[x]["nome"].lower()):
        celle = []
        for g in giri:
            p = per.get((t, g))
            celle.append({"k": "nessuna"} if not p else
                         {"k": "usata" if p["scattata"] else "propria" if p["proprietario_att"] == t else "altra",
                          "a": p["proprietario_att"], "prot": _protezioni(p.get("protezioni")) or "", "usata": _usata(p)})
        mano = {g: sum(1 for p in pick if p["proprietario_att"] == t and p["round"] == g and not p["scattata"]) for g in giri}
        righe.append({"team": t, "celle": celle, "mano": [mano[g] for g in giri]})
    return {"anno": str(anno), "giri": giri, "squadre": info, "righe": righe, "aggiornato": _ora(ora), "quando": _com_era(al)}


def immagine(template: str, d: dict) -> bytes:
    import typst
    from typst_compila import FONT
    png = typst.compile(template, root="/", format="png", ppi=180, font_paths=[f for f in FONT if os.path.isdir(f)],
                        sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})
    return png[0] if isinstance(png, list) else png


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


def dati_lega(ora: datetime | None = None, al: datetime | None = None) -> dict:
    from handlers.carriera import sq_fanta
    squadre = tm.get_all_teams()
    sg = sigle(squadre)
    anni = _anni(None, al)                                          # le pick del draft già fatto non servono più
    pick = _pick(anni, None, al)
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
    return {"anni": anni, "squadre": info, "righe": righe, "aggiornato": f"{ora:%d/%m/%Y} alle {ora:%H:%M}", "quando": _com_era(al)}


def immagine_lega(d: dict) -> bytes:
    import typst
    from typst_compila import FONT
    png = typst.compile(TEMPLATE_LEGA, root="/", format="png", ppi=180, font_paths=[f for f in FONT if os.path.isdir(f)],
                        sys_inputs={"dati": json.dumps(d, ensure_ascii=False)})
    return png[0] if isinstance(png, list) else png


async def cmd_pick_lega(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if [x.lower() for x in context.args or []] in (["aiuto"], ["help"], ["?"]):
        await msg.reply_text(aiuto(), parse_mode="HTML")
        return
    args, al = estrai_data(list(context.args or []))       # v7.36.0: /pick_lega [ANNO] DATA com'era a quella data
    if al and al > datetime.now(ROME):
        await msg.reply_text("❌ La data non può essere nel futuro.")
        return
    _, giro, anno = leggi(args)
    data_cap = f"\n📅 com'erano al {al:%d/%m/%Y}" if al else ""
    if anno:                                              # v7.22.2 (Luca, 22/11): /pick_lega ANNO [GIRO] = tutto un draft
        d = await asyncio.to_thread(dati_anno, anno, giro, None, al)
        if not d["righe"]:
            await msg.reply_text(f"❌ Nessuna pick del draft {anno}" + (f" al {al:%d/%m/%Y}" if al else "") + ".")
            return
        png = await asyncio.to_thread(immagine, TEMPLATE_ANNO, d)
        await msg.reply_photo(png, caption=f"🎯 Le pick del draft {anno}" + (f", {giro}° giro" if giro else "") + data_cap
                                           + " · la storia di una pick con /pick SQUADRA GIRO ANNO")
        return
    d = await asyncio.to_thread(dati_lega, None, al)
    if not d["anni"]:
        await msg.reply_text("Nessuna pick nel database.")
        return
    png = await asyncio.to_thread(immagine_lega, d)
    await msg.reply_photo(png, caption=f"🎯 Le pick della lega, draft {d['anni'][0]}–{d['anni'][-1]}{data_cap} · "
                                       "la storia di una pick con /pick SQUADRA GIRO ANNO")


def get_handlers() -> list:
    return [CommandHandler("pick", cmd_pick), CommandHandler("pick_lega", cmd_pick_lega)]

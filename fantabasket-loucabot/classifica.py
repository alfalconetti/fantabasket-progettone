"""
Classifica (v27, decisa con Luca il 13 e il 16/10). Solo i risultati convalidati (lega_risultati).

Punti fatti e subiti: i regolamentari col bonus casa (i supplementari decidono solo chi vince).
Ordine: vittorie; a parità gli scontri diretti tra le squadre a pari (classifica avulsa, solo
vittorie e sconfitte, mai lo scarto; si riapplica ai sottogruppi ancora a pari; se tra loro non si
sono mai incontrate non conta), poi la media dei punti fatti, poi la differenza punti.

/classifica: immagine verticale (vittorie, sconfitte, punti fatti e subiti, media, striscia).
/classifica_full: immagine orizzontale con in più media delle ultime 10, migliori di giornata,
massimo e minimo, età media, record subiti, coefficiente di variazione, fantapunti, percentuali
di partite giocate, età del quintetto, scarti medi, supplementari.

«Migliore di giornata» = punteggio più alto della giornata (anche a pari merito). «Record positivi
subiti» = volte in cui l'avversario ha fatto il punteggio più alto della giornata; «negativi
subiti» = il più basso. Roster e quintetto sono quelli di adesso (contratti attivi senza 10-day,
quintetto di IPanchinari); fantapunti = media della stagione di ognuno (come nel calcolo),
partite giocate = sue partite che contano / partite della sua squadra NBA in stagione.
"""
import json
import logging
import os
import statistics
from datetime import date

import config
import db
from numeri import ottavi, testo as tp

logger = logging.getLogger(__name__)
LOGHI = os.path.join(os.path.dirname(os.environ.get("TEAMS_PATH", "/config/teams.json")), "loghi")
ULTIME = 10


def risultati(stagione: str) -> list[dict]:
    return db.q("""SELECT * FROM lega_risultati WHERE stagione = %s AND convalidato IS NOT NULL
                   ORDER BY giornata, casa""", (stagione,), many=True) or []


def partite_squadra(ris: list[dict]) -> dict[str, list[dict]]:
    """{team: [{giornata, avv, fatti, subiti, vinta, supp}]} in ordine di giornata."""
    out: dict[str, list[dict]] = {}
    for r in ris:
        pc, pt = float(r["punti_casa"]), float(r["punti_trasferta"])
        supp = r["supp_casa"] is not None
        out.setdefault(r["casa"], []).append({"giornata": r["giornata"], "avv": r["trasferta"], "fatti": pc, "subiti": pt,
                                              "vinta": r["vince"] == "casa", "supp": supp})
        out.setdefault(r["trasferta"], []).append({"giornata": r["giornata"], "avv": r["casa"], "fatti": pt, "subiti": pc,
                                                   "vinta": r["vince"] == "trasferta", "supp": supp})
    return out


def _striscia(p: list[dict]) -> str:
    if not p:
        return "—"
    ultima = p[-1]["vinta"]
    n = 0
    for x in reversed(p):
        if x["vinta"] != ultima:
            break
        n += 1
    return f"{n}{'W' if ultima else 'L'}"


def base(ris: list[dict], squadre: list[str]) -> dict[str, dict]:
    """Le voci della classifica per squadra."""
    per = partite_squadra(ris)
    out = {}
    for t in squadre:
        p = per.get(t, [])
        n = len(p)
        fatti = sum(x["fatti"] for x in p)
        subiti = sum(x["subiti"] for x in p)
        out[t] = {"team": t, "g": n, "w": sum(x["vinta"] for x in p), "l": sum(not x["vinta"] for x in p),
                  "pf": fatti, "ps": subiti, "media": ottavi(fatti / n) if n else 0.0, "diff": fatti - subiti,
                  "striscia": _striscia(p), "partite": p}
    return out


def _h2h(gruppo: list[str], per: dict[str, list[dict]]) -> dict[str, tuple[int, int]]:
    """(vinte, giocate) di ciascuna contro le altre del gruppo."""
    g = set(gruppo)
    return {t: (sum(x["vinta"] for x in per.get(t, []) if x["avv"] in g),
                sum(1 for x in per.get(t, []) if x["avv"] in g)) for t in gruppo}


def _ordina_pari(gruppo: list[str], st: dict[str, dict], per: dict[str, list[dict]]) -> list[str]:
    """Squadre con le stesse vittorie: avulsa (ricorsiva), poi media punti fatti, poi differenza."""
    if len(gruppo) <= 1:
        return list(gruppo)
    resto = lambda ts: sorted(ts, key=lambda t: (-st[t]["media"], -st[t]["diff"], config.nome(t)))
    h = _h2h(gruppo, per)
    if not any(gioc for _, gioc in h.values()):
        return resto(gruppo)
    perc = {t: (v / gioc if gioc else 0.5) for t, (v, gioc) in h.items()}
    livelli = sorted(set(perc.values()), reverse=True)
    if len(livelli) == 1:
        return resto(gruppo)
    out = []
    for lv in livelli:
        sotto = [t for t in gruppo if perc[t] == lv]
        out += _ordina_pari(sotto, st, per) if len(sotto) < len(gruppo) else resto(sotto)
    return out


def ordina(st: dict[str, dict]) -> list[str]:
    per = {t: s["partite"] for t, s in st.items()}
    out = []
    for w in sorted({s["w"] for s in st.values()}, reverse=True):
        gruppo = [t for t, s in st.items() if s["w"] == w]
        # a parità di vittorie, prima chi ha giocato meno (meno sconfitte)
        for l in sorted({st[t]["l"] for t in gruppo}):
            out += _ordina_pari([t for t in gruppo if st[t]["l"] == l], st, per)
    return out


def extra(ris: list[dict], st: dict[str, dict]) -> None:
    """Le voci di /classifica_full che vengono dai soli risultati."""
    per_g: dict[int, list[float]] = {}
    for t, s in st.items():
        for x in s["partite"]:
            per_g.setdefault(x["giornata"], []).append(x["fatti"])
    massimi = {g: max(v) for g, v in per_g.items()}
    minimi = {g: min(v) for g, v in per_g.items()}
    for t, s in st.items():
        p = s["partite"]
        punti = [x["fatti"] for x in p]
        ult = punti[-ULTIME:]
        s["media_ult"] = ottavi(sum(ult) / len(ult)) if ult else 0.0
        s["n_ult"] = len(ult)
        s["migliore"] = sum(x["fatti"] == massimi[x["giornata"]] for x in p)
        s["max"] = max(punti) if punti else 0.0
        s["min"] = min(punti) if punti else 0.0
        s["rec_pos_subiti"] = sum(x["subiti"] == massimi[x["giornata"]] for x in p)
        s["rec_neg_subiti"] = sum(x["subiti"] == minimi[x["giornata"]] for x in p)
        s["cv"] = (statistics.pstdev(punti) / statistics.mean(punti) * 100) if len(punti) > 1 and statistics.mean(punti) else 0.0
        vin = [x["fatti"] - x["subiti"] for x in p if x["vinta"] and not x["supp"]]
        per_ = [x["subiti"] - x["fatti"] for x in p if not x["vinta"] and not x["supp"]]
        s["vantaggio"] = sum(vin) / len(vin) if vin else None
        s["svantaggio"] = sum(per_) / len(per_) if per_ else None
        sup = [x for x in p if x["supp"]]
        s["supp"] = len(sup)
        s["supp_w"] = sum(x["vinta"] for x in sup)


def _eta(dn) -> float | None:
    if not dn:
        return None
    oggi = date.today()
    dn = dn if isinstance(dn, date) else date.fromisoformat(str(dn))
    return oggi.year - dn.year - ((oggi.month, oggi.day) < (dn.month, dn.day))


def roster_stats(stagione: str, st: dict[str, dict]) -> None:
    """Età, fantapunti e partite giocate di roster e quintetto di adesso."""
    roster = db.q("""SELECT c.team_id, g.id, g.espn_id, g.data_nascita FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                     WHERE c.attivo AND c.tipo <> '10day'""", many=True) or []
    quint: dict[str, set] = {}
    try:
        for r in db.q("SELECT team_id, giocatore_id FROM ipa_quintetto", many=True) or []:
            quint.setdefault(r["team_id"], set()).add(r["giocatore_id"])
    except Exception:
        pass
    atleti = [r["espn_id"] for r in roster if r["espn_id"]]
    medie = db.medie_stagione(atleti, stagione, date(2999, 1, 1)) if atleti else {}
    squadra_nba = {**db.ultima_squadra(atleti, date(2999, 1, 1)), **db.squadre_roster(atleti)} if atleti else {}
    gare_sq: dict[str, int] = {}
    for r in db.q("""SELECT casa, trasferta FROM nba_partite WHERE stagione = %s AND tipo = ANY(%s) AND stato = 'STATUS_FINAL'""",
                  (stagione, [2, 5]), many=True) or []:
        for sq in (r["casa"], r["trasferta"]):
            gare_sq[sq] = gare_sq.get(sq, 0) + 1

    def perc(a):
        sq = squadra_nba.get(a)
        tot = gare_sq.get(sq, 0)
        if not a or not tot:
            return None
        return min(100.0, 100 * (medie.get(a, {}).get("partite", 0)) / tot)

    def media(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    per_t: dict[str, list[dict]] = {}
    for r in roster:
        per_t.setdefault(r["team_id"], []).append(r)
    for t, s in st.items():
        rs = per_t.get(t, [])
        qs = [r for r in rs if r["id"] in quint.get(t, set())]
        s["eta"] = media(_eta(r["data_nascita"]) for r in rs)
        s["eta_q"] = media(_eta(r["data_nascita"]) for r in qs)
        s["fp_roster"] = media((medie.get(r["espn_id"]) or {}).get("media") for r in rs)
        s["fp_q"] = media((medie.get(r["espn_id"]) or {}).get("media") for r in qs)
        s["gioc_roster"] = media(perc(r["espn_id"]) for r in rs)
        s["gioc_q"] = media(perc(r["espn_id"]) for r in qs)


def calcola(stagione: str | None = None, full: bool = False) -> tuple[list[dict], int]:
    """(righe in ordine, giornate convalidate)."""
    s = stagione or config.stagione()
    ris = risultati(s)
    st = base(ris, [t["id"] for t in config.squadre()])
    if full:
        extra(ris, st)
        roster_stats(s, st)
    ordine = ordina(st)
    return [{**st[t], "pos": i + 1} for i, t in enumerate(ordine)], len({r["giornata"] for r in ris})


# ── immagine ───────────────────────────────────────────────────────────────────

def _n(x, dec: int = 2, pct: bool = False) -> str:
    if x is None:
        return "—"
    if dec == 2:
        return tp(x)
    t = f"{x:.{dec}f}".replace(".", ",")
    return t + ("%" if pct else "")


def _logo(team_id: str) -> str:
    for ext in ("png", "jpg", "jpeg"):
        p = os.path.join(LOGHI, f"{team_id}_logo.{ext}")
        if os.path.exists(p):
            return p
    return ""


def dati_typst(righe: list[dict], giornate: int, full: bool) -> dict:
    out = []
    for r in righe:
        x = {"pos": r["pos"], "nome": config.nome(r["team"]), "logo": _logo(r["team"]), "w": r["w"], "l": r["l"],
             "pf": _n(r["pf"]), "ps": _n(r["ps"]), "media": _n(r["media"]), "striscia": r["striscia"],
             "diff": ("+" if r["diff"] > 0 else "") + _n(r["diff"])}
        if full:
            x.update({"media_ult": _n(r["media_ult"]), "migliore": r["migliore"], "max": _n(r["max"]), "min": _n(r["min"]),
                      "eta": _n(r["eta"], 1), "rec_pos": r["rec_pos_subiti"], "rec_neg": r["rec_neg_subiti"],
                      "cv": _n(r["cv"], 1, True), "fp_roster": _n(r["fp_roster"], 1), "fp_q": _n(r["fp_q"], 1),
                      "gioc_roster": _n(r["gioc_roster"], 0, True), "gioc_q": _n(r["gioc_q"], 0, True),
                      "eta_q": _n(r["eta_q"], 1), "vantaggio": _n(r["vantaggio"], 1), "svantaggio": _n(r["svantaggio"], 1),
                      "supp": f"{r['supp']} ({r['supp_w']}-{r['supp'] - r['supp_w']})" if r["supp"] else "0"})
        out.append(x)
    n_ult = min(ULTIME, giornate)
    return {"titolo": f"Classifica {config.stagione()}-{str(int(config.stagione()) + 1)[-2:]}",
            "sotto": f"dopo {giornate} {'giornata' if giornate == 1 else 'giornate'} convalidate",
            "ult": f"Media ult. {n_ult}", "righe": out}


TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "classifica.typ")


def immagine(full: bool = False, stagione: str | None = None) -> tuple[bytes | None, int]:
    righe, giornate = calcola(stagione, full)
    if not giornate:
        return None, 0
    import typst
    dati = dati_typst(righe, giornate, full)
    png = typst.compile(TEMPLATE, root="/", format="png", ppi=180,
                        sys_inputs={"dati": json.dumps(dati, ensure_ascii=False), "full": "1" if full else ""})
    return png, giornate


# ── comandi ────────────────────────────────────────────────────────────────────

async def cmd_classifica(update, context, full: bool = False):
    import asyncio
    import io
    msg = update.effective_message
    try:
        png, giornate = await asyncio.to_thread(immagine, full)
    except Exception as err:
        logger.exception("Classifica")
        await msg.reply_text(f"⚠️ Classifica non disponibile: {err}")
        return
    if not png:
        await msg.reply_text("Nessuna giornata convalidata: la classifica parte dalla prima convalida.")
        return
    nome = f"classifica{'_full' if full else ''}_G{giornate}.png"
    if full:      # larga: come file, così Telegram non la comprime
        await msg.reply_document(document=io.BytesIO(png), filename=nome,
                                 caption=f"📊 Classifica completa dopo {giornate} giornate convalidate")
    else:
        await msg.reply_photo(photo=io.BytesIO(png), caption=f"🏆 Classifica dopo {giornate} giornate · /classifica_full per tutte le statistiche")


async def cmd_classifica_full(update, context):
    await cmd_classifica(update, context, full=True)


def get_handlers() -> list:
    from telegram.ext import CommandHandler
    return [CommandHandler("classifica", cmd_classifica), CommandHandler("classifica_full", cmd_classifica_full)]

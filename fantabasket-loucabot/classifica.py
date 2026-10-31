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
subiti» = volte in cui l'avversario ha fatto contro di te il suo massimo della stagione; «negativi
subiti» = il suo minimo (Luca, 16/10). Roster di adesso (contratti attivi senza 10-day); quintetto
= il migliore possibile per fantapunti dal roster di adesso, uno per ruolo (PG SG SF PF C, ruoli
della stagione), non quello schierato (Luca, 16/10); fantapunti = media della stagione di ognuno
(come nel calcolo), partite giocate = sue partite che contano / partite della sua squadra NBA.

/classifica_conference: la generale filtrata per conference (gli ex aequo si risolvono sulla
generale, non tra le squadre della conference); conference da config/divisions.json, chiave
"conference": {"Nome": ["A", "B", "C"], ...} (division di team_div).
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
    max_sq = {t: max((x["fatti"] for x in s["partite"]), default=None) for t, s in st.items()}
    min_sq = {t: min((x["fatti"] for x in s["partite"]), default=None) for t, s in st.items()}
    for t, s in st.items():
        p = s["partite"]
        punti = [x["fatti"] for x in p]
        ult = punti[-ULTIME:]
        s["media_ult"] = ottavi(sum(ult) / len(ult)) if ult else 0.0
        s["n_ult"] = len(ult)
        s["migliore"] = sum(x["fatti"] == massimi[x["giornata"]] for x in p)
        s["max"] = max(punti) if punti else 0.0
        s["min"] = min(punti) if punti else 0.0
        # record subiti: l'avversario ha fatto contro di te il suo massimo (minimo) della stagione
        s["rec_pos_subiti"] = sum(x["subiti"] == max_sq[x["avv"]] for x in p)
        s["rec_neg_subiti"] = sum(x["subiti"] == min_sq[x["avv"]] for x in p)
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
    roster = db.q("""SELECT c.team_id, g.id, g.espn_id, g.data_nascita,
                            (SELECT r.ruolo FROM ruolo_attuale r WHERE r.giocatore_id = g.id AND r.stagione = %s LIMIT 1) AS ruolo
                     FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                     WHERE c.attivo AND c.tipo <> '10day'""", (stagione,), many=True) or []
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
        qs = miglior_quintetto(rs, medie)
        s["eta"] = media(_eta(r["data_nascita"]) for r in rs)
        s["eta_q"] = media(_eta(r["data_nascita"]) for r in qs)
        s["fp_roster"] = media((medie.get(r["espn_id"]) or {}).get("media") for r in rs)
        s["fp_q"] = media((medie.get(r["espn_id"]) or {}).get("media") for r in qs)
        s["gioc_roster"] = media(perc(r["espn_id"]) for r in rs)
        s["gioc_q"] = media(perc(r["espn_id"]) for r in qs)


RUOLI = ("PG", "SG", "SF", "PF", "C")


def miglior_quintetto(roster: list[dict], medie: dict) -> list[dict]:
    """Per ogni ruolo il giocatore del roster con la media fantapunti più alta (chi non ha
    partite vale 0): il quintetto migliore possibile adesso."""
    out = []
    for ruolo in RUOLI:
        cand = [r for r in roster if r.get("ruolo") == ruolo]
        if cand:
            out.append(max(cand, key=lambda r: ((medie.get(r["espn_id"]) or {}).get("media") or 0.0)))
    return out


def conference() -> dict[str, str]:
    """{team_id: nome della conference} da config/divisions.json ("conference" + "team_div")."""
    path = os.path.join(os.path.dirname(os.environ.get("TEAMS_PATH", "/config/teams.json")), "divisions.json")
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
    div_conf = {div: nome for nome, divs in (d.get("conference") or {}).items() for div in divs}
    return {t: div_conf[dv] for t, dv in (d.get("team_div") or {}).items() if dv in div_conf}


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


# migliore (verde) e peggiore (rosso) di ogni colonna, tranne V/S, striscia e posizione (Luca, 28/10):
# chiave nel JSON → (chiave del valore, 1 se più alto è meglio, −1 se più basso è meglio). Supplementari esclusi
# (giocarne tanti non è né bene né male). Età: più giovane è meglio.
DIREZIONI = {"pf": ("pf", 1), "ps": ("ps", -1), "diff": ("diff", 1), "media": ("media", 1)}
DIREZIONI_FULL = {"media_ult": ("media_ult", 1), "migliore": ("migliore", 1), "max": ("max", 1), "min": ("min", 1),
                  "eta": ("eta", -1), "rec_pos": ("rec_pos_subiti", -1), "rec_neg": ("rec_neg_subiti", 1), "cv": ("cv", -1),
                  "fp_roster": ("fp_roster", 1), "fp_q": ("fp_q", 1), "gioc_roster": ("gioc_roster", 1), "gioc_q": ("gioc_q", 1),
                  "eta_q": ("eta_q", -1), "vantaggio": ("vantaggio", 1), "svantaggio": ("svantaggio", -1)}


def colori(righe: list[dict], full: bool) -> dict[str, dict[str, str]]:
    """{team: {colonna: "best" | "worst"}}: a pari valore colorate tutte; niente se la colonna è tutta uguale."""
    out = {r["team"]: {} for r in righe}
    for k, (campo, verso) in {**DIREZIONI, **(DIREZIONI_FULL if full else {})}.items():
        val = {r["team"]: float(r[campo]) for r in righe if r.get(campo) is not None}
        if len(set(val.values())) < 2:
            continue
        hi, lo = max(val.values()), min(val.values())
        best, worst = (hi, lo) if verso > 0 else (lo, hi)
        for t, v in val.items():
            if abs(v - best) < 1e-9:
                out[t][k] = "best"
            elif abs(v - worst) < 1e-9:
                out[t][k] = "worst"
    return out


def dati_typst(righe: list[dict], giornate: int, full: bool) -> dict:
    out = []
    col = colori(righe, full)
    for r in righe:
        x = {"pos": r["pos"], "nome": config.nome(r["team"]), "logo": _logo(r["team"]), "w": r["w"], "l": r["l"],
             "pf": _n(r["pf"]), "ps": _n(r["ps"]), "media": _n(r["media"]), "striscia": r["striscia"],
             "diff": ("+" if r["diff"] > 0 else "") + _n(r["diff"]), "col": col.get(r["team"], {})}
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


def dati_conference(righe: list[dict], giornate: int, conf: dict[str, str]) -> dict:
    """La generale filtrata per conference: stesso ordine (ex aequo risolti sulla generale)."""
    base_ = dati_typst(righe, giornate, False)
    per_nome = {r["team"]: x for r, x in zip(righe, base_["righe"])}
    sezioni = []
    for nome in sorted(set(conf.values()), key=lambda n: min(r["pos"] for r in righe if conf.get(r["team"]) == n)):
        rs = [r for r in righe if conf.get(r["team"]) == nome]
        medie = [float(r["media"]) for r in rs if r.get("media") is not None]
        sezioni.append({"nome": nome, "righe": [{**per_nome[r["team"]], "pos": i + 1, "gen": r["pos"]} for i, r in enumerate(rs)],
                        # in fondo alla colonna Media, la media punti della conference (Luca, 31/10)
                        "media": _n(sum(medie) / len(medie)) if medie else "—"})
    return {**base_, "sezioni": sezioni}


TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "classifica.typ")


def immagine(full: bool = False, stagione: str | None = None, per_conference: bool = False) -> tuple[bytes | None, int]:
    righe, giornate = calcola(stagione, full)
    if not giornate:
        return None, 0
    import typst
    if per_conference:
        conf = conference()
        if len(set(conf.values())) < 2:
            raise RuntimeError("conference non configurate: in config/divisions.json manca \"conference\" "
                               "(es. {\"Conference A\": [\"A\", \"B\", \"C\"], \"Conference B\": [\"D\", \"E\", \"F\"]})")
        dati = dati_conference(righe, giornate, conf)
    else:
        dati = dati_typst(righe, giornate, full)
    png = typst.compile(TEMPLATE, root="/", format="png", ppi=180,
                        sys_inputs={"dati": json.dumps(dati, ensure_ascii=False), "full": "1" if full else ""})
    return png, giornate


# ── comandi ────────────────────────────────────────────────────────────────────

async def cmd_classifica(update, context, full: bool = False, per_conference: bool = False):
    import asyncio
    import io
    msg = update.effective_message
    try:
        png, giornate = await asyncio.to_thread(immagine, full, None, per_conference)
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
        await msg.reply_photo(photo=io.BytesIO(png), caption=f"🏆 Classifica{' per conference' if per_conference else ''} dopo "
                                                            f"{giornate} giornate · /classifica_full per tutte le statistiche")


async def cmd_classifica_conference(update, context):
    await cmd_classifica(update, context, per_conference=True)


async def cmd_classifica_full(update, context):
    await cmd_classifica(update, context, full=True)


def get_handlers() -> list:
    from telegram.ext import CommandHandler
    return [CommandHandler("classifica", cmd_classifica), CommandHandler("classifica_full", cmd_classifica_full),
            CommandHandler("classifica_conference", cmd_classifica_conference)]

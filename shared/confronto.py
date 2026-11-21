"""
/confronto A vs B e /confronto_carriera A vs B (v7.4.3, Luca 10/11; idea del 25/10: «lo stesso grafico di /rendimento
con due giocatori sovrapposti»). In loucabot e nel bot principale (in privato), come /rendimento. Disegno in
confronto.typ, stile di /rendimento; il giocatore A in blu, B in arancione.

/confronto: la stagione in corso dei due giocatori partita per partita, sulle date (le partite dello stesso giorno
una sopra l'altra), coi dati di /rendimento (`rendimento.dati_stagione`): punti (rombo per play-in e playoff), per
ognuno la media delle ultime 5 (piena) e quella dall'inizio della stagione (tratteggiata). Sotto, una tabella:
fantamedia (regular season e play-in, come /player), partite, ultime 5, playoff, migliore, minuti; il migliore dei
due in grassetto. Solo giocatori del bot (tabellini ESPN).

/confronto_carriera: le fantamedie stagione per stagione dei due, allineate per **stagione di carriera** (1ª, 2ª…:
così si confrontano anche giocatori di epoche diverse), coi dati di /rendimento_carriera (Basketball-Reference dal
1979-80, la stagione in corso dai tabellini); barre affiancate, sotto le stagioni vere. Tabella: fantamedia in
carriera, stagioni, partite, stagione migliore. I nomi si cercano come in /rendimento_carriera (anche gli storici).

I due nomi: «A vs B», «A contro B», «A, B» o «A - B». Un nome che corrisponde a più giocatori: la risposta li elenca e
chiede il nome completo (niente bottoni: sono due nomi).
"""
import json
import os
import re
from datetime import date

from shared import giocatore as G
from shared import lettura as L
from shared import rendimento as R
from shared.numeri import ottavi, testo as tp

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "confronto.typ")
SEPARATORE = re.compile(r"\s+(?:vs\.?|v\.?|contro)\s+|\s*,\s*|\s+-\s+", re.IGNORECASE)


def dividi(testo: str) -> tuple[str, str] | None:
    parti = [x.strip() for x in SEPARATORE.split(testo or "", maxsplit=1)]
    return (parti[0], parti[1]) if len(parti) == 2 and all(parti) else None


# ── chi sono ──────────────────────────────────────────────────────────────────

def trova_lega(testo: str) -> tuple[int | None, list[str]]:
    """(id del giocatore del bot, nomi tra cui scegliere se è ambiguo)."""
    from shared import parole_nome as PN
    trovati = G.cerca(testo)
    if not trovati:
        return None, []
    esatti = [x for x in trovati if L.norm(x["nome_common"]) == L.norm(testo) or PN.stesse_parole(testo, x["nome_common"])]
    if len(esatti) == 1:
        return esatti[0]["id"], []
    if len(trovati) == 1:
        return trovati[0]["id"], []
    return None, [x["nome_common"] for x in trovati]


def trova_carriera(testo: str) -> tuple[tuple[int | None, str] | None, list[str]]:
    """((id o None, nome di Basketball-Reference), ambigui): come /rendimento_carriera."""
    from shared import parole_nome as PN
    trovati = G.cerca(testo)
    esatti = [x for x in trovati if L.norm(x["nome_common"]) == L.norm(testo) or PN.stesse_parole(testo, x["nome_common"])]
    if len(esatti) == 1:
        g = L.q("SELECT nome_bref, nome_common FROM giocatori WHERE id = %s", (esatti[0]["id"],), one=True) or {}
        return (esatti[0]["id"], g.get("nome_bref") or g.get("nome_common") or testo), []
    nomi = R.nomi_bref(testo)
    if len(nomi) == 1 or (nomi and (L.norm(nomi[0]) == L.norm(testo) or PN.stesse_parole(testo, nomi[0]))
                          and sum(1 for x in nomi if L.norm(x) == L.norm(nomi[0])) == 1):
        return (R._gid_da_bref(nomi[0]), nomi[0]), []
    if nomi:
        return None, nomi
    if len(trovati) == 1:
        g = L.q("SELECT nome_bref, nome_common FROM giocatori WHERE id = %s", (trovati[0]["id"],), one=True) or {}
        return (trovati[0]["id"], g.get("nome_bref") or g.get("nome_common") or testo), []
    return None, [x["nome_common"] for x in trovati]


# ── dati per il disegno ───────────────────────────────────────────────────────

def _media(v: list[float]) -> float | None:
    return sum(v) / len(v) if v else None


def _cifra(x: float | None) -> str:
    return R._t(x) if x is not None else "—"


def _num(v: str):
    """«29,63» → 29.63; «—» → None (per scegliere il migliore nei riquadri)."""
    try:
        return float(str(v).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _meglio(a, b, piu_alto: bool = True) -> str:
    if a is None or b is None or a == b:
        return "a" if b is None and a is not None else ("b" if a is None and b is not None else "")
    return "a" if (a > b) == piu_alto else "b"


def _partite(n: int) -> str:
    return f"{n} partita" if n == 1 else f"{n} partite"


def _quando(d: dict, i: int | None) -> str:
    if i is None:
        return "—"
    p = d["partite"][i]
    return f"vs {p['avv']} {date.fromisoformat(p['giorno']):%d/%m}"


def _lato_stagione(d: dict, npo: dict | None) -> dict:
    p = d["partite"]
    giocate = [i for i, x in enumerate(p) if x["fp"] is not None]
    reg = [p[i]["fp"] for i in giocate if p[i]["media_player"]]          # regular season e play-in, come /player
    post = [p[i]["fp"] for i in giocate if not p[i]["media_player"]]
    nostri = [p[i]["fp"] for i in giocate
              if npo and npo["dal"].isoformat() <= p[i]["giorno"] <= npo["al"].isoformat()]
    ult = [p[i]["fp"] for i in giocate[-5:]]
    media = _media(reg) if reg else _media([p[i]["fp"] for i in giocate])
    bi = max(giocate, key=lambda i: p[i]["fp"], default=None)
    wi = min(giocate, key=lambda i: p[i]["fp"], default=None)
    return {"reg": reg, "post": post, "nostri": nostri, "media": media, "u5": _media(ult),
            "best": p[bi]["fp"] if bi is not None else None, "bi": bi, "worst": p[wi]["fp"] if wi is not None else None, "wi": wi}


def dati_stagione(gid_a: int, gid_b: int, stagione: str | None = None) -> dict | None:
    """Il JSON per confronto.typ, modo «stagione» (v7.9.7, Luca 15/11: solo linee, come /rendimento sul viola). None
    se uno dei due non ha partite."""
    da, db_ = R.dati_stagione(gid_a, stagione), R.dati_stagione(gid_b, stagione)
    if not da or not db_:
        return None
    giorni = sorted({x["giorno"] for x in da["partite"] + db_["partite"]})
    g0, g1 = date.fromisoformat(giorni[0]), date.fromisoformat(giorni[-1])
    tot = max((g1 - g0).days, 1)
    xf = lambda g: round(((g if isinstance(g, date) else date.fromisoformat(g)) - g0).days / tot, 4)

    def punti(d):
        return [{"x": xf(x["giorno"]), "fp": x["fp"], "post": x["tipo"] == "post", "mobile": x["mobile"]} for x in d["partite"]]
    mesi, prima = [], None
    for g in giorni:
        if g[5:7] != prima:
            mesi.append({"x": xf(date.fromisoformat(g).replace(day=1)) if g != giorni[0] else 0.0, "lbl": R.MESI[int(g[5:7])]})
            prima = g[5:7]
    # v7.16.0 (Luca, 16/11): oltre ai mesi, il 10 e il 20 di ogni mese
    date_x, m0 = [], g0.replace(day=1)
    while m0 <= g1:
        for gg in (10, 20):
            dd = m0.replace(day=gg)
            if g0 < dd <= g1:
                date_x.append({"x": xf(dd), "lbl": f"{gg}/{dd.month}"})
        m0 = (m0.replace(day=28) + __import__("datetime").timedelta(days=4)).replace(day=1)
    vals = [x["fp"] for x in da["partite"] + db_["partite"] if x["fp"] is not None]
    lo, hi, passo_y = R._asse(vals)
    npo = R.nostri_playoff(stagione)
    a, b = _lato_stagione(da, npo), _lato_stagione(db_, npo)
    fanta = None
    if npo and npo["al"] >= g0 and npo["dal"] <= g1:
        fanta = {"x0": max(xf(npo["dal"]), 0.0), "x1": min(xf(npo["al"]), 1.0), "lbl": f"P1–P{npo['n']}"}
    minuti = lambda gid: L.q("""SELECT AVG(t.minuti)::float AS m FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                                JOIN giocatori g ON g.espn_id = t.atleta
                                WHERE g.id = %s AND p.stagione = %s AND p.tipo = ANY(%s) AND t.giocato
                                  AND NOT (t.fp = 0 AND t.minuti = 0)""", (gid, stagione or L.stagione(), list(G.TIPI)), one=True)
    mia, mib = (minuti(gid_a) or {}).get("m"), (minuti(gid_b) or {}).get("m")
    freccia = lambda x: ("▲" if x["u5"] >= x["media"] else "▼") if x["u5"] is not None and x["media"] is not None else "–"
    riq = [{"t": "Fantamedia", "a": _cifra(a["media"]), "b": _cifra(b["media"]), "m": _meglio(a["media"], b["media"]),
            "s": f"{_partite(len(a['reg']))} · {_partite(len(b['reg']))}"},
           {"t": "Ultime 5", "a": _cifra(a["u5"]), "b": _cifra(b["u5"]), "m": _meglio(a["u5"], b["u5"]),
            "s": f"{freccia(a)} · {freccia(b)} rispetto alla sua media"}]
    tab = [{"t": "Partite", "a": str(len(a["reg"])), "b": str(len(b["reg"])), "m": _meglio(len(a["reg"]), len(b["reg"]))}]
    peggiore = {"t": "Peggiore", "a": _cifra(a["worst"]), "b": _cifra(b["worst"]), "m": _meglio(a["worst"], b["worst"]),
                "s": f"{_quando(da, a['wi'])} · {_quando(db_, b['wi'])}"}
    if npo and (a["nostri"] or b["nostri"]):
        na, nb = _media(a["nostri"]), _media(b["nostri"])
        riq.append({"t": "Nei nostri playoff", "a": _cifra(na), "b": _cifra(nb), "m": _meglio(na, nb),
                    "s": f"P1–P{npo['n']} · {_partite(len(a['nostri']))} · {_partite(len(b['nostri']))}"})
        tab.append({k: peggiore[k] for k in ("t", "a", "b", "m")})
    else:
        riq.append(peggiore)
    riq.insert(2, {"t": "Migliore", "a": _cifra(a["best"]), "b": _cifra(b["best"]), "m": _meglio(a["best"], b["best"]),
                   "s": f"{_quando(da, a['bi'])} · {_quando(db_, b['bi'])}"})
    if a["post"] or b["post"]:
        pa, pb = _media(a["post"]), _media(b["post"])
        tab.append({"t": "Play-in e playoff NBA", "a": f"{_cifra(pa)} ({len(a['post'])})", "b": f"{_cifra(pb)} ({len(b['post'])})",
                    "m": _meglio(pa, pb)})
    tab.append({"t": "Minuti a partita", "a": f"{mia:.1f}".replace(".", ",") if mia else "—",
                "b": f"{mib:.1f}".replace(".", ",") if mib else "—", "m": _meglio(mia, mib)})
    i_post = [x["x"] for x in punti(da) + punti(db_) if x["post"]]
    tieni = ("nome", "iniziali", "foto", "sotto", "contratto")
    return {"modo": "stagione", "titolo": da["titolo"],
            "a": {k: da[k] for k in tieni}, "b": {k: db_[k] for k in tieni}, "punti_a": punti(da), "punti_b": punti(db_),
            "riquadri": riq, "tabella": tab, "mesi": mesi, "date": date_x, "y_min": lo, "y_max": hi, "y_passo": passo_y,
            "media_a": a["media"] or 0, "media_b": b["media"] or 0, "media_a_t": _cifra(a["media"]), "media_b_t": _cifra(b["media"]),
            "fanta": fanta, "post_x": min(i_post, default=None)}


def dati_carriera(a: tuple[int | None, str], b: tuple[int | None, str]) -> dict | None:
    """Il JSON per confronto.typ, modo «carriera» (v7.9.7: come /rendimento_carriera, sul blu)."""
    da, db_ = R.dati_carriera(a[0], a[1]), R.dati_carriera(b[0], b[1])
    if not da or not db_:
        return None
    sa, sb = da["stagioni"], db_["stagioni"]
    ia = max(range(len(sa)), key=lambda i: sa[i]["fm"])
    ib = max(range(len(sb)), key=lambda i: sb[i]["fm"])
    stag = []
    for i in range(max(len(sa), len(sb))):
        xa = sa[i] if i < len(sa) else None
        xb = sb[i] if i < len(sb) else None
        stag.append({"n": f"{i + 1}ª", "a": xa["fm"] if xa else None, "b": xb["fm"] if xb else None,
                     "pa": i == ia, "pb": i == ib, "ca": bool(xa and xa["in_corso"]), "cb": bool(xb and xb["in_corso"]),
                     "sa": xa["lbl"] if xa else "", "sb": xb["lbl"] if xb else ""})
    riq = []
    for ra, rb in zip(da["riquadri"], db_["riquadri"]):
        t = "Fantamedia in carriera" if ra["t"] == "Fantamedia" else ra["t"]
        riq.append({"t": t, "a": ra["v"], "b": rb["v"], "m": _meglio(_num(ra["v"]), _num(rb["v"])),
                    "s": f"{ra['s']} · {rb['s']}" if ra["t"] != "Fantamedia" else "pesata sulle partite"})
    ga, gb = sum(x["g"] for x in sa), sum(x["g"] for x in sb)
    mp = lambda st: (sum(_num(x["min"]) * x["g"] for x in st) / max(sum(x["g"] for x in st), 1)) if st else None
    ma_, mb_ = mp(sa), mp(sb)
    tab = [{"t": "Partite", "a": f"{ga:,}".replace(",", "."), "b": f"{gb:,}".replace(",", "."), "m": _meglio(ga, gb)},
           {"t": "Minuti a partita", "a": f"{ma_:.1f}".replace(".", ","), "b": f"{mb_:.1f}".replace(".", ","), "m": _meglio(ma_, mb_)}]
    _, hi, passo = R._asse([x["fm"] for x in sa + sb])
    tieni = ("nome", "iniziali", "foto", "sotto")
    return {"modo": "carriera", "titolo": "Carriere a confronto", "a": {k: da[k] for k in tieni}, "b": {k: db_[k] for k in tieni},
            "riquadri": riq, "tabella": tab, "stagioni": stag, "y_max": hi, "y_passo": passo,
            "media_a": da["media_val"], "media_b": db_["media_val"], "media_a_t": da["media_big"], "media_b_t": db_["media_big"]}


def immagine(d: dict) -> bytes:
    import typst
    from shared import non_ufficiale as NU
    fonts = [f for f in ("/usr/share/fonts",) if os.path.isdir(f)]
    png = typst.compile(TEMPLATE, root="/", format="png", ppi=170, font_paths=fonts,
                        sys_inputs={"dati": json.dumps(NU.marca(d), ensure_ascii=False, default=str)})
    return png[0] if isinstance(png, list) else png


# ── comandi ───────────────────────────────────────────────────────────────────

USO = ("Uso: /confronto A vs B (es. /confronto Wembanyama vs Holmgren): la stagione dei due partita per partita.\n"
       "Per tutta la carriera, anche dei giocatori storici: /confronto_carriera A vs B")
USO_C = ("Uso: /confronto_carriera A vs B (es. /confronto_carriera LeBron James vs Kevin Durant): le fantamedie stagione per "
         "stagione, allineate per stagione di carriera (dati dal 1979-80).")


def _ambiguo(testo: str, nomi: list[str]) -> str:
    return f"«{testo}» può essere: " + ", ".join(nomi[:8]) + ". Scrivi il nome completo."


async def cmd_confronto(update, context):
    import asyncio
    msg = update.effective_message
    due = dividi(" ".join(context.args or []))
    if not due:
        await msg.reply_text(USO)
        return
    ids = []
    for testo in due:
        gid, nomi = trova_lega(testo)
        if gid is None:
            await msg.reply_text(_ambiguo(testo, nomi) if nomi else
                                 f"Nessun giocatore si chiama «{testo}». Per i giocatori di altre epoche: /confronto_carriera A vs B")
            return
        ids.append(gid)
    if ids[0] == ids[1]:
        await msg.reply_text("È lo stesso giocatore due volte.")
        return
    d = await asyncio.to_thread(dati_stagione, ids[0], ids[1])
    if not d:
        await msg.reply_text("Uno dei due non ha partite in questa stagione nei tabellini ESPN.")
        return
    await msg.reply_photo(await asyncio.to_thread(immagine, d))


async def cmd_confronto_carriera(update, context):
    import asyncio
    msg = update.effective_message
    due = dividi(" ".join(context.args or []))
    if not due:
        await msg.reply_text(USO_C)
        return
    chi = []
    for testo in due:
        x, nomi = trova_carriera(testo)
        if x is None:
            await msg.reply_text(_ambiguo(testo, nomi) if nomi else
                                 f"Nessun giocatore si chiama «{testo}», nemmeno tra quelli di Basketball-Reference (dal 1979-80).")
            return
        chi.append(x)
    if chi[0][1] == chi[1][1] and chi[0][0] == chi[1][0]:
        await msg.reply_text("È lo stesso giocatore due volte.")
        return
    d = await asyncio.to_thread(dati_carriera, chi[0], chi[1])
    if not d:
        await msg.reply_text("Per uno dei due non ci sono stagioni nei dati di Basketball-Reference.")
        return
    await msg.reply_photo(await asyncio.to_thread(immagine, d))

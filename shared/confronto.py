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
COLORE_A = "#1D4ED8"
COLORE_B = "#E07A10"
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


def _riga(nome: str, a, b, testo_a: str, testo_b: str, piu_alto: bool = True) -> dict:
    """Una riga della tabella: chi è meglio in grassetto (a pari merito nessuno)."""
    meglio = ""
    if a is not None and b is not None and a != b:
        meglio = "a" if (a > b) == piu_alto else "b"
    return {"voce": nome, "a": testo_a, "b": testo_b, "meglio": meglio}


def _lato_stagione(d: dict) -> dict:
    p = d["partite"]
    contano = [x for x in p if x["fp"] is not None]
    reg = [x["fp"] for x in contano if x["media_player"]]                # regular season e play-in, come /player
    return {"reg": reg, "post": [x["fp"] for x in contano if not x["media_player"]], "ult5": [x["fp"] for x in contano][-5:],
            "best": max(contano, key=lambda x: x["fp"]) if contano else None}


def dati_stagione(gid_a: int, gid_b: int, stagione: str | None = None) -> dict | None:
    """Il JSON per confronto.typ, modo «stagione». None se uno dei due non ha partite."""
    da, db_ = R.dati_stagione(gid_a, stagione), R.dati_stagione(gid_b, stagione)
    if not da or not db_:
        return None
    giorni = sorted({x["giorno"] for x in da["partite"] + db_["partite"]})
    g0, g1 = date.fromisoformat(giorni[0]), date.fromisoformat(giorni[-1])
    tot = max((g1 - g0).days, 1)

    def punti(d):
        out = []
        for x in d["partite"]:
            out.append({"x": round((date.fromisoformat(x["giorno"]) - g0).days / tot, 4), "fp": x["fp"], "tipo": x["tipo"],
                        "prog": x["prog"], "mobile": x["mobile"]})
        return out
    # etichette delle date: 8 circa, sulle date vere
    passo = max(1, round(len(giorni) / 8))
    date_lbl = [{"x": round((date.fromisoformat(g) - g0).days / tot, 4), "t": f"{date.fromisoformat(g):%d/%m}"}
                for i, g in enumerate(giorni) if i % passo == 0]
    vals = [x["fp"] for x in da["partite"] + db_["partite"] if x["fp"] is not None]
    lo, hi, passo_y = R._asse(vals)
    a, b = _lato_stagione(da), _lato_stagione(db_)
    ma, mb = _media(a["reg"]), _media(b["reg"])
    pa, pb = _media(a["post"]), _media(b["post"])
    u5a, u5b = _media(a["ult5"]), _media(b["ult5"])
    minuti = lambda gid: L.q("""SELECT AVG(t.minuti)::float AS m FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                                JOIN giocatori g ON g.espn_id = t.atleta
                                WHERE g.id = %s AND p.stagione = %s AND p.tipo = ANY(%s) AND t.giocato
                                  AND NOT (t.fp = 0 AND t.minuti = 0)""", (gid, stagione or L.stagione(), list(G.TIPI)), one=True)
    mia, mib = (minuti(gid_a) or {}).get("m"), (minuti(gid_b) or {}).get("m")
    best = lambda x: f"{R._t(x['fp'])}" if x else "—"
    righe = [
        _riga("Fantamedia", ma, mb, _cifra(ma), _cifra(mb)),
        _riga("Partite", len(a["reg"]), len(b["reg"]), str(len(a["reg"])), str(len(b["reg"]))),
        _riga("Ultime 5", u5a, u5b, _cifra(u5a), _cifra(u5b)),
        _riga("Minuti a partita", mia, mib, f"{mia:.1f}".replace(".", ",") if mia else "—", f"{mib:.1f}".replace(".", ",") if mib else "—"),
        _riga("Migliore partita", a["best"]["fp"] if a["best"] else None, b["best"]["fp"] if b["best"] else None, best(a["best"]), best(b["best"])),
    ]
    if a["post"] or b["post"]:
        righe.insert(3, _riga("Playoff", pa, pb, f"{_cifra(pa)} ({len(a['post'])})", f"{_cifra(pb)} ({len(b['post'])})"))
    i_post = [x for x in punti(da) + punti(db_) if x["tipo"] == "post"]
    return {"modo": "stagione", "titolo": da["titolo"], "colore_a": COLORE_A, "colore_b": COLORE_B,
            "a": {k: da[k] for k in ("nome", "iniziali", "foto", "sotto")} | {"media": _cifra(ma), "punti": punti(da)},
            "b": {k: db_[k] for k in ("nome", "iniziali", "foto", "sotto")} | {"media": _cifra(mb), "punti": punti(db_)},
            "date": date_lbl, "y_min": lo, "y_max": hi, "y_passo": passo_y,
            "post_x": min((x["x"] for x in i_post), default=None), "righe": righe,
            "nota": "Fantapunti di ogni partita (◆ play-in e playoff), sulle date · linea piena: media delle ultime 5 · tratteggiata: "
                    "media dall'inizio della stagione · fantamedia e partite: regular season e play-in, come /player"}


def _lato_carriera(d: dict) -> dict:
    st = d["stagioni"]
    g = sum(x["g"] for x in st)
    media = sum(x["fm"] * x["g"] for x in st) / g if g else None
    best = max(st, key=lambda x: x["fm"]) if st else None
    return {"media": media, "g": g, "n": len(st), "best": best}


def dati_carriera(a: tuple[int | None, str], b: tuple[int | None, str]) -> dict | None:
    da, db_ = R.dati_carriera(a[0], a[1]), R.dati_carriera(b[0], b[1])
    if not da or not db_:
        return None
    n = max(len(da["stagioni"]), len(db_["stagioni"]))
    anni = []
    for i in range(n):
        xa = da["stagioni"][i] if i < len(da["stagioni"]) else None
        xb = db_["stagioni"][i] if i < len(db_["stagioni"]) else None
        anni.append({"k": f"{i + 1}ª",
                     "a": {"fm": xa["fm"], "t": xa["fm_t"], "lbl": xa["lbl"], "g": xa["g"], "in_corso": xa["in_corso"]} if xa else None,
                     "b": {"fm": xb["fm"], "t": xb["fm_t"], "lbl": xb["lbl"], "g": xb["g"], "in_corso": xb["in_corso"]} if xb else None})
    la, lb = _lato_carriera(da), _lato_carriera(db_)
    _, hi, passo = R._asse([x["fm"] for x in da["stagioni"] + db_["stagioni"]])
    best = lambda x: f"{x['best']['fm_t']} ({x['best']['lbl']})" if x["best"] else "—"
    righe = [
        _riga("Fantamedia in carriera", la["media"], lb["media"], _cifra(la["media"]), _cifra(lb["media"])),
        _riga("Stagioni", la["n"], lb["n"], str(la["n"]), str(lb["n"])),
        _riga("Partite", la["g"], lb["g"], f"{la['g']:,}".replace(",", "."), f"{lb['g']:,}".replace(",", ".")),
        _riga("Stagione migliore", la["best"]["fm"] if la["best"] else None, lb["best"]["fm"] if lb["best"] else None, best(la), best(lb)),
    ]
    tieni = ("nome", "iniziali", "foto", "sotto")
    return {"modo": "carriera", "titolo": "Carriere a confronto", "colore_a": COLORE_A, "colore_b": COLORE_B,
            "a": {k: da[k] for k in tieni} | {"media": _cifra(la["media"])},
            "b": {k: db_[k] for k in tieni} | {"media": _cifra(lb["media"])},
            "anni": anni, "y_max": hi, "y_passo": passo, "righe": righe,
            "nota": "Fantamedia di ogni stagione, allineate per stagione di carriera (1ª, 2ª…), sotto le stagioni vere · "
                    "Basketball-Reference (regular season, dal 1979-80), la stagione in corso dai tabellini ESPN, come /player"}


def immagine(d: dict) -> bytes:
    import typst
    fonts = [f for f in ("/usr/share/fonts",) if os.path.isdir(f)]
    png = typst.compile(TEMPLATE, root="/", format="png", ppi=170, font_paths=fonts,
                        sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})
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

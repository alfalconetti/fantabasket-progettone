"""
Prospetto dei rinnovi (v7.33.0, mockup approvato da Luca il 26/11): un'immagine con i giocatori di una squadra
rinnovabili alla prossima offseason e quanto verrebbero col rinnovo da ¼ e con quello da ½. Bot principale (in
privato, /prospetto_rinnovi e 🔮 nel /menu) e loucabot (anche nei gruppi), stesso codice.

Tre modi, secondo la fase (Luca, 26/11):
  - stima       regular season, playoff, break: la prossima offseason con le fantamedie della stagione in corso
                (Luca: sempre quelle, con un avviso nelle prime 10 giornate); nel break sono quelle finali;
  - reale       fase dei rinnovi: i numeri veri (fantamedia della stagione appena finita) e i rinnovi già usati;
  - senza dati  draft, RFA, FA, ruoli: la stagione nuova non ha ancora fantamedie, solo l'elenco dei rinnovabili.
Rinnovabili: i contratti che alla prossima offseason saranno appena diventati x1, e i rookie che lì escono dal IV
anno (prima la Doncic d'ufficio, poi da quell'importo il rinnovo). In fondo i rookie a fine II anno (il rinnovo
rookie, illimitato, a parte: /rinnovo_rookie). Le regole sono quelle di fantabasket-main/handlers/stagione.py e
handlers/rinnovi.py (la prova tests/main/prospetto_rinnovi.py controlla che i numeri siano gli stessi).
"""
import json
import math
import os

from shared import lettura as L
from shared import regole as RG

FASI_STIMA = {"regular-season-fa", "regular-season-deadline", "playoff", "offseason-break"}
FASE_RINNOVI = "offseason-rinnovi"
GIORNATE_AFFIDABILI = 10
TIPI = {"quarto": ("¼", 5, 4), "mezzo": ("½", 3, 2)}


# ── regole (le stesse del bot principale) ──────────────────────────────────────

def _s() -> dict:
    return RG._settings()


def minimo(fm) -> int:
    """Minimo da tabella per la fantamedia: la fascia più alta con «da» ≤ fm (come settings del main)."""
    if fm is None:
        return 1
    m = 1
    for f in sorted(_s().get("tabella_minimo_contratto", []), key=lambda f: f["da"]):
        if f["da"] <= fm:
            m = f["minimo"]
    return m


def doncic(fm) -> int | None:
    if fm is None:
        return None
    x = math.floor(float(fm))
    s1, s2 = int(_s().get("doncic_soglia_1", 20)), int(_s().get("doncic_soglia_2", 25))
    if x < s1:
        return None
    if x < s2:
        return 12 + (6 * (x - s1) + 9) // 10
    return 15 + (4 * (x - s2) + 9) // 10


def formula_doncic(fm) -> str:
    """«24,3 → 24 → 12 + 0,6·4 = 14,4 → 15»."""
    x = math.floor(float(fm))
    s1, s2 = int(_s().get("doncic_soglia_1", 20)), int(_s().get("doncic_soglia_2", 25))
    base, k, soglia = (12, 0.6, s1) if x < s2 else (15, 0.4, s2)
    esatto = base + k * (x - soglia)
    return (f"{_num(fm)} → {x} → {base} + {_num(k)}·{x - soglia} = {_num(round(esatto, 2))}"
            + (f" → {doncic(fm)}" if round(esatto, 2) != doncic(fm) else ""))


def importo_scala(pick: int, indice: int) -> int | None:
    for fascia, valori in _s().get("rookie_scale", {}).items():
        lim = fascia.split("-")
        if int(lim[0]) <= int(pick) <= int(lim[-1]):
            return int(valori[indice]["imp"]) if len(valori) > indice else None
    return None


def aumento(importo: int, tipo: str) -> int:
    _, num, den = TIPI[tipo]
    return -(-int(importo) * num // den)


def solo_x3(importo: int) -> bool:
    return importo >= int(_s().get("soglia_anni_3", 35))


def fantamedie(gids: list[int], stagione_lega: int) -> dict[int, float]:
    """Fantamedia (ultima) della stagione di lega (2026 = 2026-27 = bref 2027)."""
    if not gids:
        return {}
    rr = L.q("""SELECT DISTINCT ON (g.id) g.id AS gid, b.fantamedia FROM giocatori g
                JOIN bref_stats b ON b.nome_bref = g.nome_bref
                WHERE g.id = ANY(%s) AND b.stagione = %s AND b.fantamedia IS NOT NULL
                ORDER BY g.id, b.timestamp DESC""", (list(gids), str(stagione_lega + 1)), many=True) or []
    return {r["gid"]: float(r["fantamedia"]) for r in rr}


def etichetta(s: int) -> str:
    return f"{s}-{str(s + 1)[2:]}"


def _num(x) -> str:
    return f"{float(x):.2f}".rstrip("0").rstrip(".").replace(".", ",")


# ── il prospetto ───────────────────────────────────────────────────────────────

def modo(fase: str) -> str:
    return "reale" if fase == FASE_RINNOVI else "stima" if fase in FASI_STIMA else "senza"


def _contratti(team_id: str) -> list[dict]:
    return L.q("""SELECT c.*, g.nome_common, r.anno_firma, r.pick_numero FROM contratti c
                  JOIN giocatori g ON g.id = c.giocatore_id
                  LEFT JOIN rookie r ON r.giocatore_id = c.giocatore_id AND r.firmato AND c.tipo = 'rookie'
                  WHERE c.team_id = %s AND c.attivo AND c.tipo <> '10day'
                  ORDER BY c.importo DESC, g.nome_common""", (team_id,), many=True) or []


def _rfa(stagione: int) -> set:
    try:
        return {r["contratto_id"] for r in L.q("SELECT contratto_id FROM rfa_dichiarati WHERE stagione = %s "
                                                "AND stato = 'attiva'", (str(stagione),), many=True) or []}
    except Exception:
        return set()


def _usati(team_id: str, stagione: int) -> dict:
    try:
        rr = L.q("""SELECT r.tipo, g.nome_common FROM rinnovi_normali r JOIN giocatori g ON g.id = r.giocatore_id
                    WHERE r.stagione = %s AND r.team_id = %s AND r.annullato IS NULL""",
                 (str(stagione), team_id), many=True) or []
    except Exception:
        rr = []
    return {r["tipo"]: r["nome_common"] for r in rr}


def _nota_fine_scala(contratto_id: int) -> str | None:
    r = L.q("SELECT note FROM movimenti_giocatori WHERE contratto_id = %s AND tipo = 'rookie_fine_scala' "
            "ORDER BY id DESC LIMIT 1", (contratto_id,), one=True)
    return r["note"] if r else None


def calcola(team_id: str, fase: str, stagione: int) -> dict:
    """Il prospetto della squadra: `off` = la stagione dell'offseason dei rinnovi (quella dopo, se non siamo ai
    rinnovi), i rinnovabili con base e opzioni, i rookie a fine II anno, il cap di quella stagione."""
    m = modo(fase)
    off = stagione if m == "reale" else stagione + 1
    cc = _contratti(team_id)
    rfa = _rfa(off) if m == "reale" else set()
    gids = [c["giocatore_id"] for c in cc]
    fm_off = fantamedie(gids, off - 1) if m != "senza" else {}       # la stagione che finisce
    fm_prima = fantamedie(gids, off - 2) if m != "senza" else {}
    righe, rookie, cap = [], [], 0
    for c in cc:
        sf, anni, imp = int(c["stagione_firma"]), int(c["anni_originali"]), int(c["importo"])
        residui = anni - (off - sf)
        gid = c["giocatore_id"]
        fm = fm_off.get(gid)
        k = off - int(c["anno_firma"]) if c.get("anno_firma") else None        # anno di scala all'offseason (0 = I)
        base, doncic_txt, motivo = None, None, None
        if c["tipo"] == "normale" and c["id"] not in rfa:
            if residui == 1 and sf < off:
                base, motivo = imp, (f"{imp}x{anni - (stagione - sf)} oggi → x1" if m != "reale" else "appena diventato x1")
            elif m == "reale" and residui == 0 and anni == 0 and sf == off:
                base, motivo = imp, "ex rookie, uscito dal IV anno"
                nota = _nota_fine_scala(c["id"])
                doncic_txt = nota.replace("Fine rookie scale: ", "") + " (già applicata)" if nota else None
        elif c["tipo"] == "rookie" and k == 4 and residui <= 0 and m != "reale":
            motivo = f"rookie al IV anno ({imp}x1) → x0 a fine scala"
            if m == "senza":
                base = None
                doncic_txt = "Doncic d'ufficio sulla fantamedia del III e IV anno: si saprà a fine stagione"
            else:
                fmx = max([v for v in (fm_prima.get(gid), fm) if v is not None], default=None)
                d = doncic(fmx)
                base = max(imp, d or 0)
                if d and d > imp:
                    doncic_txt = (f"fantamedia migliore di III e IV anno {formula_doncic(fmx)}. Doncic d'ufficio: da "
                                  f"{imp}x1 a {base}x0, e da {base} si calcola il rinnovo")
                else:
                    doncic_txt = ((f"fantamedia migliore di III e IV anno {_num(fmx)}: niente Doncic"
                                   if fmx is not None else "nessuna fantamedia: niente Doncic") + f". Resta {imp}x0")
            righe.append(_riga(c, base, 0, fm, motivo, doncic_txt, m, True))
            continue
        elif c["tipo"] == "rookie" and k == 2 and residui <= 0 and c["id"] not in rfa:
            if m == "senza":
                rookie.append({"nome": c["nome_common"], "come": "scala III o Doncic: si saprà a fine stagione", "nuovo": "—"})
            else:
                s3 = importo_scala(c["pick_numero"], 2) or 0
                fmx = max([v for v in (fm_prima.get(gid), fm) if v is not None], default=None)
                d = doncic(fmx)
                nuovo = d if d and d > s3 else s3
                come = (f"{imp}x{'1' if m != 'reale' else '0'} → scala III {s3}"
                        + (f" o Doncic (fm {formula_doncic(fmx)})" if d else
                           (f" (fm {_num(fmx)}: niente Doncic)" if fmx is not None else "")))
                rookie.append({"nome": c["nome_common"], "come": come, "nuovo": f"{nuovo}x2"})
        if base is not None:
            righe.append(_riga(c, base, 1 if motivo != "ex rookie, uscito dal IV anno" else 0, fm, motivo, doncic_txt,
                               m, motivo == "ex rookie, uscito dal IV anno"))
        # cap della stagione dell'offseason, senza rinnovi: i contratti ancora in corso lì (la rookie scale del
        # II e del IV anno con l'importo della tabella)
        if residui >= 1:
            peso = imp
            if c["tipo"] == "rookie" and c.get("pick_numero") and m != "reale":
                if k == 1:
                    peso = importo_scala(c["pick_numero"], 1) or imp
                elif k == 3:
                    peso = max(imp, importo_scala(c["pick_numero"], 3) or 0)
            cap += peso
    from shared import cap as CAP
    try:
        cap = CAP.cap_occupato(L.q, team_id, off) if m == "reale" else cap + CAP.impatto_taglio(L.q, team_id, off)
    except Exception:
        pass
    return {"modo": m, "off": off, "righe": righe, "rookie": rookie, "cap": cap,
            "usati": _usati(team_id, off) if m == "reale" else {}}


def _riga(c: dict, base, anni_ora: int, fm, motivo: str, doncic_txt, m: str, ex_rookie: bool) -> dict:
    r = {"nome": c["nome_common"], "motivo": motivo, "doncic": doncic_txt, "ex_rookie": ex_rookie,
         "base": f"{base}x{anni_ora}" if base is not None else "—", "fm": None, "min": None, "q": None, "m": None}
    if m == "senza" or base is None:
        return r
    mn = minimo(fm)
    r.update({"fm": _num(fm) if fm is not None else None, "min": mn})
    for tipo, (simbolo, num, den) in TIPI.items():
        esatto = base * num / den
        alz = aumento(base, tipo)
        imp = max(alz, mn)
        conto = f"{base} + {simbolo} = " + (f"{alz}" if alz == esatto else f"{_num(esatto)} → {alz}")
        r["q" if tipo == "quarto" else "m"] = {"imp": imp, "conto": conto, "tab": imp > alz, "x3": solo_x3(imp)}
    return r


def dati(team: dict, fase: str | None = None, stagione: int | None = None, giornate: int | None = None) -> dict:
    """I dati per prospetto_rinnovi.typ. `giornate`: le giornate convalidate (per l'avviso delle prime 10)."""
    g = L.globali()
    fase = fase or str(g.get("fase", ""))
    stagione = int(stagione or g.get("stagione_corrente", 2026))
    p = calcola(team["id"], fase, stagione)
    m, off = p["modo"], p["off"]
    tetto, lusso = int(_s().get("cap_regular", 150)), int(_s().get("cap_offseason", 165))
    n_ex = sum(1 for r in p["righe"] if r["ex_rookie"])
    n_x1 = len(p["righe"]) - n_ex
    if m == "stima":
        if fase == "offseason-break":
            striscia = f"Fantamedie finali del {etichetta(off - 1)}: gli importi saranno questi, salvo trade"
        elif giornate is not None and giornate < GIORNATE_AFFIDABILI and fase.startswith("regular"):
            striscia = (f"STIMA — solo {giornate} giornate giocate: fantamedie ancora poco affidabili")
        else:
            striscia = "STIMA — con le fantamedie di oggi: gli importi veri si calcolano a fine stagione"
        periodo = f"offseason {off} · fantamedie {etichetta(off - 1)}"
    elif m == "reale":
        striscia = ""
        periodo = f"fase dei rinnovi {off} · fantamedie {etichetta(off - 1)}"
    else:
        striscia = f"Mancano le fantamedie del {etichetta(off - 1)}: importi e Doncic si stimano dalla regular season"
        periodo = f"offseason {off} · solo i rinnovabili"
    if m == "reale":
        u = p["usati"]
        rinnovi = {"t": "Rinnovi", "v": " · ".join(f"{s} {'✓' if t in u else 'libero'}" for t, (s, _, _) in TIPI.items()),
                   "s": ", ".join(f"{TIPI[t][0]} a {n}" for t, n in u.items()) or "ancora nessuno"}
    else:
        rinnovi = {"t": "Rinnovi", "v": "¼ + ½", "s": "uno per tipo, a scelta"}
    note = ("Base = contratto alla prossima offseason (per gli ex rookie dopo la Doncic d'ufficio). Da ¼ e da ½: "
            "vecchio + ¼ o + ½ per eccesso, mai sotto il minimo da tabella per la fantamedia della stagione che finisce. "
            "In oro quando vale il minimo. Da 35M solo x3. Un rinnovo da ¼ e uno da ½ a stagione, non obbligatori; "
            "i rinnovi rookie a fine II anno sono a parte (/rinnovo_rookie) e non contano nei due.")
    if m == "reale":
        note += " Si rinnova con /rinnovo nel bot principale."
    return {"nome": team["nome"], "periodo": periodo, "striscia": striscia, "modo": m,
            "riquadri": [{"t": "Rinnovabili", "v": str(len(p["righe"])), "s": f"{n_x1} x1 · {n_ex} ex rookie"},
                         rinnovi,
                         {"t": f"Cap {etichetta(off)}", "v": f"{p['cap']}M", "s": "già impegnato, senza rinnovi"},
                         {"t": "Spazio", "v": f"{tetto - p['cap']}M / {lusso - p['cap']}M", "s": f"sotto {tetto} / sotto {lusso}"}],
            "giocatori": p["righe"], "rookie": p["rookie"], "note": note}


def immagine(d: dict) -> bytes:
    import typst
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prospetto_rinnovi.typ")
    fonts = [x for x in ("/usr/share/fonts",) if os.path.isdir(x)]
    return typst.compile(tpl, root="/", format="png", ppi=150, font_paths=fonts,
                         sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})


def _giornate(stagione: int) -> int | None:
    try:
        from shared import lottery_vista as LV
        return LV.classifica_oggi(str(stagione))[1]
    except Exception:
        return None


def foto_squadra(team: dict) -> bytes:
    g = L.globali()
    s = int(g.get("stagione_corrente", 2026))
    return immagine(dati(team, giornate=_giornate(s)))


async def cmd_prospetto_rinnovi(update, context):
    """/prospetto_rinnovi [SQUADRA]: senza squadra la propria (GM)."""
    import asyncio
    from shared.squadre import cerca_squadra
    msg = update.effective_message
    q = " ".join(context.args or []).strip()
    sq = cerca_squadra(q, L.squadre()) if q else L.squadra_del_gm(update.effective_user.id)
    if not sq:
        await msg.reply_text(f"Squadra non trovata: «{q}»." if q else "Uso: /prospetto_rinnovi SQUADRA (senza, la tua squadra).")
        return
    await msg.reply_photo(await asyncio.to_thread(foto_squadra, sq))


async def cb_prospetto_rinnovi(update, context):
    """prr:mio (🔮 nel /menu del bot principale)."""
    import asyncio
    query = update.callback_query
    sq = L.squadra_del_gm(query.from_user.id)
    if not sq:
        await query.answer("⛔ Non sei registrato come GM.", show_alert=True)
        return
    await query.answer()
    await query.message.reply_photo(await asyncio.to_thread(foto_squadra, sq))

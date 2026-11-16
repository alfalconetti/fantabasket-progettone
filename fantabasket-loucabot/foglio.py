"""
Il calendario sul foglio Google "Calendario" (stesso file del Roster), tramite gas-router e la
stessa web app del Roster (azione "calendario").

A ogni aggiornamento si ricarica tutta la pagina, colonne A:E: lo script svuota i valori di A:E
(la formattazione resta) e scrive la griglia. La griglia è il CSV importato tale e quale (per
ogni giornata l'intestazione "Week N gg/mm - gg/mm (media …)" su A:E unite, poi per ogni partita
la riga "Casa | punti | V | punti | Trasferta", sotto quella dei supplementari e due vuote), con
le squadre a media calcolate dalle partite NBA nelle intestazioni e i punteggi da lega_risultati
in B e D. Si aggiorna all'import, quando cambiano le squadre a media, con /calendario_foglio e
dopo ogni giornata convalidata.
"""
import csv
import io
import logging
import os
import re

import calendario as cal
import db

logger = logging.getLogger(__name__)

RE_MEDIA = re.compile(r"\s*\(\s*media[^)]*\)", re.I)


def intestazione(originale: str, media: list[str] | None) -> str:
    """L'intestazione del CSV con le squadre a media aggiornate (None = lascia com'è)."""
    if media is None:
        return originale
    base = RE_MEDIA.sub("", originale).rstrip()
    return f"{base} (media {','.join(media)})" if media else base


def _num(x):
    return None if x is None else float(x)


def griglia(stagione: str) -> list[list]:
    """Tutta la pagina Calendario, colonne A:E, dal CSV importato: intestazioni con le squadre a
    media calcolate (testo tutto in A, il resto vuoto: A:E sono unite), squadre e V come nel CSV,
    punteggi in B e D da lega_risultati (regolamentari nella riga delle squadre, supplementari
    subito sotto). Le celle senza valore sono stringhe vuote."""
    testo = db.csv_calendario(stagione)
    if not testo:
        return []
    righe = [list(r) for r in csv.reader(io.StringIO(testo))]
    nomi = {c.strip() for r in righe for c in (r[:1] + r[4:5]) if c.strip()}
    mappa, _, _ = cal.abbina_squadre({n for n in nomi if not cal.RE_GIORNATA.match(n)})
    ris = db.risultati(stagione)
    gg = {g["numero"]: g for g in db.giornate(stagione)}
    out, numero, sotto = [], None, None
    for r in righe:
        celle = ([c.strip() for c in r] + [""] * 5)[:5]
        m = cal.RE_GIORNATA.match(",".join(r))
        if m:
            numero = int(m.group(1))
            g = gg.get(numero)
            testo_int = ",".join(r).strip().rstrip(",").strip()
            out.append([intestazione(testo_int, g["media"] if g else None), "", "", "", ""])
            sotto = None
            continue
        riga = list(celle)
        if celle[0] and celle[2].upper() == "V" and celle[4]:
            x = ris.get((numero, mappa.get(celle[0]), mappa.get(celle[4])))
            if x and x["punti_casa"] is not None:
                riga[1], riga[3] = _num(x["punti_casa"]), _num(x["punti_trasferta"])
            sotto = x
        elif sotto is not None:
            if sotto["supp_casa"] is not None:
                riga[1], riga[3] = _num(sotto["supp_casa"]), _num(sotto["supp_trasferta"])
            sotto = None
        out.append(riga)
    while out and all(v == "" for v in out[-1]):
        out.pop()
    return out


# ── v7.15.0 (Luca, 15/11): i playoff in un foglio a parte, come il vecchio foglio dei playoff ──────────
# Il foglio si chiama «Playoff 26-27» (uno per stagione). In cima il titolo, le conference, le teste di serie e il
# tabellone (primo turno, semifinali, finali di conference, finals; la prima conference a sinistra, l'altra a destra
# a specchio, con le vittorie accanto ai nomi); sotto, per ogni turno, le giornate: «DATA» e i giorni in A (sotto, se
# ci sono, le squadre a media), le partite in C–F (casa, punti, punti, trasferta) col punteggio della serie in G
# dal lato di chi gioca in casa, i supplementari nella riga sotto. Colonne A–W.
LARGHEZZA = 23
TITOLO_LEGA = "QUASI FRIENDS"
NOMI_TURNI = {1: "PRIMO TURNO", 2: "SEMIFINALI DI CONFERENCE", 3: "FINALI DI CONFERENCE", 4: "FINALS"}


def nome_foglio_playoff(stagione: str) -> str:
    a = int(stagione)
    return f"Playoff {a % 100:02d}-{(a + 1) % 100:02d}"


def _riga() -> list:
    return [""] * LARGHEZZA


SCURO, MARRONE, GIALLO, ARANCIO, CREMA, BORDO, GRIGIO = "#2A1A00", "#6B4A00", "#FFD23F", "#FF9F1C", "#FFF8E1", "#F0D48A", "#8A7A5A"
LARGHEZZE = {1: 95, 2: 28, 3: 170, 4: 62, 5: 62, 6: 170, 7: 52, 8: 150, 9: 28, 10: 150, 11: 28, 12: 150, 13: 28,
             14: 150, 15: 28, 16: 28, 17: 150, 18: 28, 19: 150, 20: 28, 21: 150, 22: 28, 23: 150}


def _a1(r: int, c: int, r2: int | None = None, c2: int | None = None) -> str:
    """Da indici (da 0) a «B2» o «B2:F2»."""
    col = lambda j: (col((j // 26) - 1) if j >= 26 else "") + chr(65 + j % 26)
    x = f"{col(c)}{r + 1}"
    return x if r2 is None else f"{x}:{col(c2)}{r2 + 1}"


def griglia_playoff(stagione: str) -> list[list]:
    return dati_playoff(stagione)[0]


def dati_playoff(stagione: str) -> tuple[list[list], list[dict]]:
    """(righe, stili) del foglio dei playoff. Gli stili (Luca, 15/11: «ci vorrebbe pure la formattazione») sono per
    intervalli: {range, sfondo, colore, grassetto, corsivo, dimensione, allinea, formato, unisci}; sui colori del
    tabellone dei playoff (giallo e marrone)."""
    gg = [g for g in db.giornate(stagione) if g.get("tipo") == "playoff"]
    if not gg:
        return [], []
    import config
    import playoff as PO
    nome = config.nome
    a = int(stagione)
    out = [_riga() for _ in range(19)]
    st: list[dict] = []
    out[1][1] = f"PLAYOFF {TITOLO_LEGA} {a}/{a + 1}"
    st.append({"range": _a1(1, 1, 1, 22), "unisci": True, "sfondo": SCURO, "colore": GIALLO, "grassetto": True,
               "dimensione": 18, "allinea": "center"})
    confs = PO.conferenze()[:2]
    sd = PO.seed(stagione)
    serie = PO.serie(stagione)
    per = {(x["turno"], x["conference"], x["slot"]): x for x in serie}
    if confs:
        out[3][7] = confs[0].upper()
        st.append({"range": _a1(3, 7, 3, 12), "unisci": True, "sfondo": MARRONE, "colore": "#FFFFFF", "grassetto": True,
                   "dimensione": 12, "allinea": "center"})
    if len(confs) > 1:
        out[3][16] = confs[1].upper()
        st.append({"range": _a1(3, 16, 3, 22), "unisci": True, "sfondo": MARRONE, "colore": "#FFFFFF", "grassetto": True,
                   "dimensione": 12, "allinea": "center"})
    out[4][2] = "Teste di Serie"
    st.append({"range": _a1(4, 1, 4, 5), "unisci": True, "grassetto": True, "colore": MARRONE, "allinea": "center"})
    for c, txt in zip((7, 9, 11, 13, 17, 19, 21), ("Primo Turno", "Semifinali", "Finali Conference", "FINALS",
                                                     "Finali Conference", "Semifinali", "Primo Turno")):
        out[6][c] = txt
    for c1, c2 in ((7, 8), (9, 10), (11, 12), (17, 18), (19, 20), (21, 22)):
        st.append({"range": _a1(6, c1, 6, c2), "unisci": True, "sfondo": ARANCIO, "colore": SCURO, "grassetto": True, "allinea": "center"})
    st.append({"range": _a1(6, 13, 6, 16), "unisci": True, "sfondo": GIALLO, "colore": SCURO, "grassetto": True, "allinea": "center"})
    for k, (cn, cs) in enumerate(((1, 2), (4, 5))):        # teste di serie: # e squadra
        if k < len(confs):
            out[8][cn], out[8][cs] = "#", confs[k].upper()
            st.append({"range": _a1(8, cn, 8, cs), "sfondo": MARRONE, "colore": "#FFFFFF", "grassetto": True})
            for i, t in enumerate(sd.get(confs[k], [])[:6]):
                out[10 + i][cn], out[10 + i][cs] = i + 1, nome(t)
            st.append({"range": _a1(10, cn, 15, cs), "sfondo": CREMA})
            st.append({"range": _a1(10, cn, 11, cs), "sfondo": GIALLO, "grassetto": True})      # 1 e 2: aspettano in semifinale
            st.append({"range": _a1(10, cn, 15, cn), "allinea": "center", "colore": GRIGIO, "grassetto": True})

    def metti(r: int, x: dict | None, c_sq: int, c_v: int) -> None:
        cc = (min(c_sq, c_v), max(c_sq, c_v))
        st.append({"range": _a1(r, cc[0], r + 1, cc[1]), "sfondo": CREMA, "bordo": BORDO})
        if not x:
            return
        out[r][c_sq], out[r][c_v] = nome(x["alta"]), x["vinte_alta"]
        out[r + 1][c_sq], out[r + 1][c_v] = nome(x["bassa"]), x["vinte_bassa"]
        st.append({"range": _a1(r, c_v, r + 1, c_v), "allinea": "center", "grassetto": True})
        if x["vincente"]:
            rv = r if x["vincente"] == x["alta"] else r + 1
            st.append({"range": _a1(rv, cc[0], rv, cc[1]), "sfondo": GIALLO, "grassetto": True})
            st.append({"range": _a1(r + 1 if rv == r else r, cc[0], r + 1 if rv == r else r, cc[1]), "colore": GRIGIO})

    for k, (sq_pt, v_pt, sq_sf, v_sf, sq_cf, v_cf) in enumerate(((7, 8, 9, 10, 11, 12), (22, 21, 20, 19, 18, 17))):
        if k >= len(confs):
            break
        c = confs[k]
        metti(8, per.get((1, c, "3-6")), sq_pt, v_pt)
        metti(16, per.get((1, c, "4-5")), sq_pt, v_pt)
        metti(10, per.get((2, c, "2")), sq_sf, v_sf)
        metti(14, per.get((2, c, "1")), sq_sf, v_sf)
        metti(12, per.get((3, c, "cf")), sq_cf, v_cf)
    st.append({"range": _a1(12, 13, 12, 16), "sfondo": GIALLO, "grassetto": True, "bordo": ARANCIO})
    st.append({"range": _a1(12, 14, 12, 15), "allinea": "center", "dimensione": 12})
    f = per.get((4, "", "f"))
    if f and confs:
        sinistra = f["alta"] if f["alta"] in sd.get(confs[0], []) else f["bassa"]
        destra = f["bassa"] if sinistra == f["alta"] else f["alta"]
        vs, vd = ((f["vinte_alta"], f["vinte_bassa"]) if sinistra == f["alta"] else (f["vinte_bassa"], f["vinte_alta"]))
        out[12][13], out[12][14], out[12][15], out[12][16] = nome(sinistra), vs, vd, nome(destra)
        if f["vincente"]:
            out[13][13] = f"🏆 {nome(f['vincente'])}"
            st.append({"range": _a1(13, 13, 13, 16), "unisci": True, "sfondo": SCURO, "colore": GIALLO, "grassetto": True,
                       "dimensione": 12, "allinea": "center"})
    # le giornate, turno per turno
    ris = db.risultati(stagione)
    turno = None
    vinte: dict[tuple, int] = {}
    for g in gg:
        n = g["numero"]
        t = max((x["turno"] for x in serie if (x["inizio"] or 0) <= n), default=None)
        if t != turno and t:
            out += [_riga()]
            r = _riga()
            r[2], r[6] = NOMI_TURNI.get(t, f"TURNO {t}"), "SERIE"
            i0 = len(out)
            out += [r, _riga(), _riga()]
            st.append({"range": _a1(i0, 0, i0, 6), "sfondo": SCURO, "colore": GIALLO, "grassetto": True, "dimensione": 12})
            st.append({"range": _a1(i0, 6, i0, 6), "allinea": "center"})
            turno = t
        partite = db.q("SELECT casa, trasferta FROM lega_partite WHERE stagione = %s AND giornata = %s ORDER BY id",
                       (stagione, n), many=True) or []
        blocco, st_b = [], []
        for p in partite:
            x = ris.get((n, p["casa"], p["trasferta"]))
            r1, r2 = _riga(), _riga()
            r1[2], r1[5] = nome(p["casa"]), nome(p["trasferta"])
            j = len(blocco)
            st_b.append(({"sfondo": CREMA, "bordo": BORDO}, j, 2, j, 6))
            if x and x["punti_casa"] is not None:
                r1[3], r1[4] = _num(x["punti_casa"]), _num(x["punti_trasferta"])
                chi = p["casa"] if x["vince"] == "casa" else p["trasferta"]
                coppia = tuple(sorted((p["casa"], p["trasferta"])))
                vinte[(coppia, chi)] = vinte.get((coppia, chi), 0) + 1
                r1[6] = f"{vinte.get((coppia, p['casa']), 0)}-{vinte.get((coppia, p['trasferta']), 0)}"
                cv = (2, 3) if chi == p["casa"] else (4, 5)
                st_b.append(({"grassetto": True}, j, cv[0], j, cv[0]))
                st_b.append(({"grassetto": True}, j, cv[1], j, cv[1]))
                if x["supp_casa"] is not None:
                    r2[3], r2[4] = _num(x["supp_casa"]), _num(x["supp_trasferta"])
                    st_b.append(({"corsivo": True, "colore": GRIGIO, "formato": "0.00"}, j + 1, 3, j + 1, 4))
            blocco += [r1, r2]
        if not blocco:
            blocco = [_riga(), _riga()]
        while len(blocco) < 3:
            blocco.append(_riga())
        blocco[0][0] = "DATA"
        blocco[1][0] = f"{g['dal'].day}/{g['dal'].month}-{g['al'].day}/{g['al'].month}"
        media = g.get("media") if g.get("media") is not None else (g.get("media_file") or [])
        if media:
            blocco[2][0] = "MEDIA " + ",".join(media)
        i0 = len(out)
        st.append({"range": _a1(i0, 0, i0, 0), "grassetto": True, "colore": MARRONE})
        st.append({"range": _a1(i0 + 1, 0, i0 + 1, 0), "colore": SCURO})
        if media:
            st.append({"range": _a1(i0 + 2, 0, i0 + 2, 0), "colore": ARANCIO, "grassetto": True, "dimensione": 8})
        st.append({"range": _a1(i0, 3, i0 + len(blocco) - 1, 4), "formato": "0.00", "allinea": "right"})
        st.append({"range": _a1(i0, 6, i0 + len(blocco) - 1, 6), "allinea": "center", "grassetto": True, "colore": MARRONE})
        for sty, r1_, c1, r2_, c2 in st_b:
            st.append({"range": _a1(i0 + r1_, c1, i0 + r2_, c2), **sty})
        out += blocco + [_riga()]
    while out and all(v == "" for v in out[-1]):
        out.pop()
    return out, st


async def aggiorna_playoff(stagione: str, manda=None) -> str:
    """Ricarica il foglio dei playoff della stagione («Playoff 26-27»); una riga di esito."""
    if not manda and not configurato():
        return "foglio non configurato (GAS_ROUTER_URL)"
    g, stili = dati_playoff(stagione)
    if not g:
        return ""
    try:
        r = await manda_gas("calendario", {"action": "calendario", "righe": g, "foglio": nome_foglio_playoff(stagione),
                                           "stili": stili, "larghezze": LARGHEZZE}, manda)
    except Exception as err:
        logger.warning("Foglio dei playoff: %s", err)
        return f"⚠️ foglio dei playoff non aggiornato ({type(err).__name__}: {str(err)[:150]})"
    if r.get("error"):
        return f"⚠️ foglio dei playoff non aggiornato: {str(r['error'])[:200]}"
    return f"foglio {nome_foglio_playoff(stagione)} ricaricato ({r.get('righe', len(g))} righe)"


def configurato() -> bool:
    return bool(os.environ.get("GAS_ROUTER_URL"))


async def invia(righe: list[list], manda=None) -> dict:
    """POST al gas-router (/gas/calendario). `manda(payload)` si può sostituire nelle prove."""
    payload = {"action": "calendario", "righe": righe}
    if manda:
        return await manda(payload)
    import httpx
    tok_file = os.environ.get("GAS_ROUTER_TOKEN_FILE", "")
    token = open(tok_file).read().strip() if tok_file and os.path.exists(tok_file) else ""
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(os.environ["GAS_ROUTER_URL"].rstrip("/") + "/gas/calendario", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


async def manda_gas(endpoint: str, payload: dict, manda=None) -> dict:
    """POST al gas-router (/gas/<endpoint>). `manda(payload)` si può sostituire nelle prove."""
    if manda:
        return await manda(payload)
    import httpx
    tok_file = os.environ.get("GAS_ROUTER_TOKEN_FILE", "")
    token = open(tok_file).read().strip() if tok_file and os.path.exists(tok_file) else ""
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(os.environ["GAS_ROUTER_URL"].rstrip("/") + f"/gas/{endpoint}", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


async def aggiorna(stagione: str, manda=None) -> str:
    """Aggiorna il foglio e restituisce una riga di esito per il canale log."""
    if not manda and not configurato():
        return "foglio non configurato (GAS_ROUTER_URL)"
    g = griglia(stagione)
    if not g:
        return "nessun calendario importato"
    try:
        r = await invia(g, manda)
    except Exception as err:
        logger.warning("Foglio Calendario: %s", err)
        return f"⚠️ foglio non aggiornato ({type(err).__name__}: {str(err)[:150]})"
    if r.get("error"):
        return f"⚠️ foglio non aggiornato: {str(r['error'])[:200]}"
    return f"foglio Calendario ricaricato ({r.get('righe', len(g))} righe)"

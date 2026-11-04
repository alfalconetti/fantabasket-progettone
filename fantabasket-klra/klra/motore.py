"""
Il calcolo di klra: lo stesso codice di loucabot (risultati.calcola, calcolo.punteggio_giocatori e
punteggio_squadra: quintetti congelati, panchine, medie, snapshot, decisioni degli admin, ceduti, FADD),
con i parametri del sistema scelto al posto di quelli della lega.

Come: `installa()` sostituisce, una volta sola, quattro funzioni di loucabot con versioni che guardano il
sistema del calcolo in corso (una ContextVar, quindi ogni thread il suo; senza sistema = comportamento di
loucabot identico):
- db.tabellini_atleti → i fantapunti di ogni partita rifatti coi pesi e i bonus del giocatore del sistema;
- db.medie_stagione   → le medie della stagione coi fantapunti del sistema (stessa regola: lo 0 con 0 minuti non conta);
- calcolo.punteggio_giocatori → chi non gioca e la sua squadra non ha partite: media, % della media o 0;
- calcolo._fadd_possibile     → FADD sì o no.
Poi qui: bonus di squadra (quintetto completo, MVP, titolari sotto zero), esito (bonus casa, scarto,
supplementari / pareggio / chi fa di più, pari finale) e classifica (a vittorie come loucabot, o a punti).

Si calcolano solo le giornate convalidate dalla lega (lega_risultati): i risultati di un sistema sono in cache
(klra_risultati) per firma dei parametri e si rifanno se la giornata viene riconvalidata.
Nessuna scrittura sul database ufficiale: legge col pool di sola lettura (basi.apri_ufficiale).
"""
import contextvars
import json
import logging

import calcolo
import classifica as CL
import config
import db
import risultati as RIS
from numeri import ottavi

from klra import basi
from klra import regole as KR

logger = logging.getLogger(__name__)
_ATTIVO: contextvars.ContextVar = contextvars.ContextVar("klra_sistema", default=None)
_orig: dict = {}


# ── fantapunti di una partita ──────────────────────────────────────────────────

def bonus_riga(r: dict, P: dict, esito_nba: dict | None = None) -> list[tuple[str, float]]:
    """I bonus del giocatore in una partita (solo quelli accesi): [(etichetta, valore)]."""
    if not r.get("giocato"):
        return []
    g = P["giocatore"]
    v = lambda k: float(r.get(k) or 0)
    reb = v("oreb") + v("dreb")
    cat = [v("pts"), reb, v("ast"), v("stl"), v("blk")]
    n10 = sum(x >= 10 for x in cat)
    out = []
    if n10 >= 4 and g["quadrupla_doppia"]:
        out.append(("QD", g["quadrupla_doppia"]))
    elif n10 >= 3 and g["tripla_doppia"]:
        out.append(("TD", g["tripla_doppia"]))
    elif n10 >= 2 and g["doppia_doppia"]:
        out.append(("DD", g["doppia_doppia"]))
    if g["cinque_x_cinque"] and all(x >= 5 for x in cat):
        out.append(("5x5", g["cinque_x_cinque"]))
    for k, lab, soglia, x in (("punti_40", "40", 40, v("pts")), ("rimbalzi_20", "20R", 20, reb),
                              ("assist_15", "15A", 15, v("ast")), ("stoppate_5", "5S", 5, v("blk"))):
        if g[k] and x >= soglia:
            out.append((lab, g[k]))
    fga, fgm = v("fga"), v("fgm")
    if g["mano_calda"] and fga >= 8 and fgm / fga >= 0.70:
        out.append(("🔥", g["mano_calda"]))
    if g["mattone"] and fga >= 10 and fgm / fga < 0.30:
        out.append(("🧱", g["mattone"]))
    if g["custode"] and v("minuti") >= 30 and v("tov") == 0:
        out.append(("🔒", g["custode"]))
    if g["sei_falli"] and v("pf") >= 6:
        out.append(("6F", g["sei_falli"]))
    if g["vittoria_nba"] and esito_nba:
        e = esito_nba.get(r.get("partita"))
        if e and e.get("vince") and e["vince"] == r.get("squadra"):
            out.append(("W", g["vittoria_nba"]))
    return out


def fp_riga(r: dict, P: dict, esito_nba: dict | None = None) -> float:
    """I fantapunti di una partita col sistema: pesi (come nba.fantapunti, a due decimali), bonus, tetto."""
    pesi = P["pesi"]
    fp = round(sum(float(p) * float(r.get(k) or 0) for k, p in pesi.items() if p), 2)
    fp += sum(x for _, x in bonus_riga(r, P, esito_nba))
    tetto = P["giocatore"]["tetto"]
    if tetto is not None and fp > float(tetto):
        fp = float(tetto)
    return round(fp, 2)


def _esiti_nba(partite: set) -> dict:
    """{partita: {vince: sigla}} delle partite NBA finite coi punti."""
    if not partite:
        return {}
    righe = db.q("SELECT espn_id, casa, trasferta, punti_casa, punti_trasferta FROM nba_partite WHERE espn_id = ANY(%s)",
                 (list(partite),), many=True) or []
    out = {}
    for p in righe:
        if p["punti_casa"] is not None and p["punti_trasferta"] is not None and p["punti_casa"] != p["punti_trasferta"]:
            out[p["espn_id"]] = {"vince": p["casa"] if p["punti_casa"] > p["punti_trasferta"] else p["trasferta"]}
    return out


# ── le funzioni di loucabot, col sistema del calcolo in corso ─────────────────

def _tabellini(atleti, dal, al):
    righe = _orig["tab"](atleti, dal, al)
    P = _ATTIVO.get()
    if P:
        es = _esiti_nba({r["partita"] for r in righe}) if P["giocatore"]["vittoria_nba"] else {}
        for r in righe:
            r["fp_lega"] = r["fp"]
            r["fp"] = fp_riga(r, P, es)
            r["klra_bonus"] = bonus_riga(r, P, es)
    return righe


def _medie(atleti, stagione, prima_del):
    P = _ATTIVO.get()
    if not P:
        return _orig["medie"](atleti, stagione, prima_del)
    righe = db.q("""SELECT t.* FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                    WHERE t.atleta = ANY(%s) AND p.stagione = %s AND p.tipo = ANY(%s) AND p.data_et < %s AND t.giocato""",
                 (list(atleti), stagione, [2, 5], prima_del), many=True) or []
    es = _esiti_nba({r["partita"] for r in righe}) if P["giocatore"]["vittoria_nba"] else {}
    per: dict[str, list[float]] = {}
    for r in righe:
        fp = fp_riga(r, P, es)
        if fp == 0 and int(r.get("minuti") or 0) == 0:         # lo 0 con 0 minuti non fa media (calcolo.conta)
            continue
        per.setdefault(r["atleta"], []).append(fp)
    return {a: {"media": ottavi(sum(v) / len(v)), "partite": len(v)} for a, v in per.items()}


def _punteggio_giocatori(stagione, g, atleti):
    out = _orig["pg"](stagione, g, atleti)
    P = _ATTIVO.get()
    if P and P["partita"]["fantapunti"] == "media":
        # fantamedie: chi ha giocato prende la media della stagione fino al giorno prima della giornata (coi pesi
        # del sistema); chi non ha giocato segue le regole di sempre (media se la squadra non ha partite, se no 0)
        giocato = [a for a, x in out.items() if x["come"] == "partite"]
        medie = db.medie_stagione(giocato, stagione, g["dal"]) if giocato else {}
        # chi non ha ancora giocato nella stagione: la fantamedia dell'anno prima, se c'è, se no 0 (Luca, 04/11)
        prima = precedente([a for a in giocato if a not in medie], stagione, g["dal"])
        for a in giocato:
            m = medie.get(a)
            out[a]["fp_partite"] = out[a]["fp"]
            if m:
                out[a]["fp"], nota = m["media"], f"fantamedie: media su {m['partite']} partite prima della giornata"
            elif a in prima:
                out[a]["fp"], nota = prima[a]
            else:
                out[a]["fp"], nota = 0.0, "fantamedie: nessuna partita prima della giornata né l'anno prima, 0"
            out[a]["nota"] = ((out[a].get("nota") or "") + " · " if out[a].get("nota") else "") + nota
    if P and P["partita"]["assenti"] != "media":
        pct = 0 if P["partita"]["assenti"] == "zero" else float(P["partita"]["assenti_pct"])
        for x in out.values():
            if x["come"] == "media":
                x["fp"] = ottavi(x["fp"] * pct / 100)
                x["nota"] = (x.get("nota") or "") + (f" · il {pct:g}% della media" if pct else " · senza media: 0")
    return out


def precedente(atleti: list[str], stagione: str, prima_del) -> dict[str, tuple[float, str]]:
    """La fantamedia dell'anno prima: dai tabellini ESPN della stagione precedente (coi pesi del sistema), se ci sono;
    se no da basketball-reference (bref_stats, coi pesi della lega). {atleta: (media, nota)}."""
    if not atleti:
        return {}
    prec = str(int(stagione) - 1)
    out = {a: (m["media"], f"fantamedie: nessuna partita quest'anno, media del {prec}-{stagione[-2:]} su {m['partite']} partite")
           for a, m in db.medie_stagione(atleti, prec, prima_del).items()}
    resto = [a for a in atleti if a not in out]
    if resto:
        try:
            # bref: la stagione col suo anno di fine (2025-26 → «2026»), l'ultima rilevazione
            righe = db.q("""SELECT DISTINCT ON (g.espn_id) g.espn_id, b.fantamedia FROM giocatori g
                            JOIN bref_stats b ON b.nome_bref = g.nome_bref
                            WHERE g.espn_id = ANY(%s) AND b.stagione = %s AND b.fantamedia IS NOT NULL
                            ORDER BY g.espn_id, b.timestamp DESC""", (resto, stagione), many=True) or []
            for r in righe:
                out[r["espn_id"]] = (ottavi(float(r["fantamedia"])),
                                     f"fantamedie: nessuna partita quest'anno, fantamedia del {prec}-{stagione[-2:]} (basketball-reference)")
        except Exception as err:
            logger.warning("Fantamedia dell'anno prima da bref: %s", err)
    return out


def _fadd(a, p, g):
    P = _ATTIVO.get()
    if P and not P["partita"]["fadd"]:
        return False, ""
    return _orig["fadd"](a, p, g)


def _live_calcolo(s, n):
    """live.calcolo per /partita (partita.dati): col sistema, il calcolo di klra."""
    P = _ATTIVO.get()
    return calcolo_completo(P, s, n) if P else _orig["live"](s, n)


def _stato_calcolo(s, n):
    """partita._stato_calcolo: col sistema la giornata è «calcolata» (niente risultato salvato della lega in testa)."""
    return "calcolata" if _ATTIVO.get() else _orig["stato"](s, n)


def installa() -> None:
    if _orig:
        return
    import live
    import partita
    _orig.update(tab=db.tabellini_atleti, medie=db.medie_stagione, pg=calcolo.punteggio_giocatori,
                 fadd=calcolo._fadd_possibile, calcola=RIS.calcola, live=live.calcolo, stato=partita._stato_calcolo)
    db.tabellini_atleti = _tabellini
    db.medie_stagione = _medie
    calcolo.punteggio_giocatori = _punteggio_giocatori
    calcolo._fadd_possibile = _fadd
    live.calcolo = _live_calcolo
    partita._stato_calcolo = _stato_calcolo


# ── partita ─────────────────────────────────────────────────────────────────────

def esito(c_tot: float, t_tot: float, pan_c: list, pan_t: list, P: dict, bonus: float) -> dict:
    """Come calcolo.esito, coi parametri del sistema. vince ∈ casa / trasferta / pari."""
    pa = P["partita"]
    SC, N = float(pa["scarto"]), int(pa["panchina"])
    c, t = c_tot + bonus, t_tot
    reg = (ottavi(c), ottavi(t))
    pari = "trasferta" if pa["pari_finale"] == "trasferta" else "pari"
    supp = 0
    if pa["supplementari"] == "nessuno":
        vince = "casa" if c > t else "trasferta" if t > c else pari
    elif pa["supplementari"] == "pareggio":
        vince = ("casa" if c > t else "trasferta") if abs(c - t) >= SC else "pari"
    else:
        pc = [float(x["fp"]) for x in pan_c] + [0.0] * N
        pt = [float(x["fp"]) for x in pan_t] + [0.0] * N
        while abs(c - t) < SC and supp < N:
            c, t = c + pc[supp], t + pt[supp]
            supp += 1
        vince = ("casa" if c > t else "trasferta") if abs(c - t) >= SC else pari
    return {"vince": vince, "casa": ottavi(c), "trasferta": ottavi(t), "supplementari": supp, "regolamentari": reg,
            "punti_supplementari": (ottavi(c - reg[0]), ottavi(t - reg[1])) if supp else None}


def _giocatore(x: dict, bonus: dict) -> dict:
    return {"nome": x.get("nome"), "ruolo": x.get("ruolo"), "atleta": x.get("atleta"), "fp": float(x.get("fp") or 0),
            "come": x.get("come"), "nota": x.get("nota") or "", "fadd": bool(x.get("fadd")),
            "bonus": bonus.get(x.get("atleta"), [])}


def calcolo_completo(P: dict, stagione: str, n: int, sch: dict | None = None) -> dict:
    """Il calcolo di risultati.calcola col sistema P, con bonus di squadra ed esito del sistema: stessa forma
    (c["risultati"][i]["sc"/"st"/"esito"/"vince"/"punti_casa"…], c["bonus"]) più c["klra_bonus"] {atleta: [[etichetta, valore]]}
    e sc/st["bonus_squadra"]. Serve a calcola_giornata e a /partita (partita.dati di loucabot). Non scrive niente."""
    P = KR.completa(P)
    installa()
    tok = _ATTIVO.set(P)
    try:
        c = _orig["calcola"](stagione, n, sch=sch) if sch is not None else _orig["calcola"](stagione, n)
        g = c["giornata"]
        bonus: dict[str, list] = {}
        righe_b = [] if P["partita"]["fantapunti"] == "media" else db.tabellini_atleti(list(c["punti"]), g["dal"], g["al"])
        for r in righe_b:                                 # con le fantamedie i bonus stanno già nella media
            for lab, v in r.get("klra_bonus") or []:
                bonus.setdefault(r["atleta"], []).append([lab, v])
    finally:
        _ATTIVO.reset(tok)
    playoff = g.get("tipo") == "playoff"
    bc = float(P["partita"]["bonus_casa_playoff" if playoff else "bonus_casa"])
    sq = {}
    for r in c["risultati"]:
        sq[r["casa"]], sq[r["trasferta"]] = r["sc"], r["st"]
    S = P["squadra"]
    mvp = set()
    if S["mvp_bonus"]:
        tit = [(t, x["fp"]) for t, s in sq.items() for x in s["titolari"] if x.get("atleta")]
        if tit:
            top = max(fp for _, fp in tit)
            mvp = {t for t, fp in tit if fp == top}
    for t, s in sq.items():
        e = []
        tit = s["titolari"]
        if S["quintetto_bonus"] and len(tit) == 5 and all(float(x["fp"]) >= float(S["quintetto_soglia"]) for x in tit):
            e.append(["Quintetto completo", S["quintetto_bonus"]])
        neg = sum(float(x["fp"]) < 0 for x in tit)
        if S["negativo_malus"] and neg:
            e.append([f"{neg} titolar{'e' if neg == 1 else 'i'} sotto zero", S["negativo_malus"] * neg])
        if t in mvp:
            e.append(["MVP di giornata", S["mvp_bonus"]])
        s["bonus_squadra"] = e
        s["totale"] = ottavi(s["totale"] + sum(v for _, v in e))
    for r in c["risultati"]:
        es = esito(r["sc"]["totale"], r["st"]["totale"], r["sc"]["panchina"], r["st"]["panchina"], P, bc)
        r.update(esito=es, vince=es["vince"], supplementari=es["supplementari"],
                 punti_casa=es["regolamentari"][0], punti_trasferta=es["regolamentari"][1],
                 supp_casa=es["punti_supplementari"][0] if es["punti_supplementari"] else None,
                 supp_trasferta=es["punti_supplementari"][1] if es["punti_supplementari"] else None)
    c["bonus"] = bc
    c["klra_bonus"] = bonus
    c["klra_parametri"] = P
    return c


def calcola_giornata(P: dict, stagione: str, n: int) -> dict:
    """La giornata n col sistema P, in forma da salvare in cache."""
    c = calcolo_completo(P, stagione, n)
    bonus = c["klra_bonus"]
    out = []
    for r in c["risultati"]:
        lato = lambda s: {"totale": s["totale"], "bonus_squadra": s["bonus_squadra"],
                          "titolari": [_giocatore(x, bonus) for x in s["titolari"]],
                          "panchina": [_giocatore(x, bonus) for x in s["panchina"]],
                          "fadd": ({"esce": s["fadd"]["esce"].get("nome"), "entra": s["fadd"]["entra"].get("nome")}
                                   if s.get("fadd") else None)}
        out.append({"casa": r["casa"], "trasferta": r["trasferta"], "punti_casa": r["punti_casa"], "punti_trasferta": r["punti_trasferta"],
                    "supp_casa": r["supp_casa"], "supp_trasferta": r["supp_trasferta"], "supplementari": r["supplementari"],
                    "vince": r["vince"], "finale": [r["esito"]["casa"], r["esito"]["trasferta"]], "sc": lato(r["sc"]), "st": lato(r["st"])})
    return {"giornata": n, "bonus_casa": c["bonus"], "risultati": out}


# ── cache e stagione ───────────────────────────────────────────────────────────

def sistema(sid: int) -> dict | None:
    return basi.q("SELECT * FROM klra_sistemi WHERE id = %s", (sid,), one=True)


def parametri(sist: dict) -> dict:
    """I parametri di un sistema: l'Ufficiale e i predefiniti seguono le regole della lega di adesso."""
    if sist["ufficiale"]:
        return KR.ufficiale()
    if sist.get("predefinito") == "fantamedie":
        P = KR.ufficiale()
        P["partita"]["fantapunti"] = "media"
        return P
    p = sist["parametri"] if isinstance(sist["parametri"], dict) else json.loads(sist["parametri"])
    return KR.completa(p)


def giornate_convalidate(stagione: str) -> dict[int, object]:
    """{giornata: ultima convalida} della lega."""
    righe = db.q("""SELECT giornata, MAX(convalidato) AS c FROM lega_risultati WHERE stagione = %s AND convalidato IS NOT NULL
                    GROUP BY giornata ORDER BY giornata""", (stagione,), many=True) or []
    return {r["giornata"]: r["c"] for r in righe}


def risultati_giornata(sist: dict, stagione: str, n: int, convalidato=None) -> dict:
    P = parametri(sist)
    f = KR.firma(P)
    if convalidato is None:
        convalidato = giornate_convalidate(stagione).get(n)
    r = basi.q("SELECT dati, convalidato FROM klra_risultati WHERE sistema_id = %s AND firma = %s AND stagione = %s AND giornata = %s",
               (sist["id"], f, stagione, n), one=True)
    if r and r["convalidato"] == convalidato:
        return r["dati"] if isinstance(r["dati"], dict) else json.loads(r["dati"])
    dati = calcola_giornata(P, stagione, n)
    basi.q("""INSERT INTO klra_risultati (sistema_id, firma, stagione, giornata, convalidato, dati) VALUES (%s, %s, %s, %s, %s, %s)
              ON CONFLICT (sistema_id, firma, stagione, giornata) DO UPDATE SET convalidato = EXCLUDED.convalidato,
                dati = EXCLUDED.dati, calcolato = NOW()""",
           (sist["id"], f, stagione, n, convalidato, json.dumps(dati, default=str)))
    return dati


def risultati_stagione(sist: dict, stagione: str) -> list[dict]:
    """Le partite delle giornate convalidate col sistema, come le righe di lega_risultati (+ giornata)."""
    out = []
    for n, conv in giornate_convalidate(stagione).items():
        for r in risultati_giornata(sist, stagione, n, conv)["risultati"]:
            out.append({**r, "giornata": n})
    return out


# ── classifica ──────────────────────────────────────────────────────────────────

def _punti_partita(vinta: bool, pari: bool, supp: bool, C: dict) -> float:
    if pari:
        return float(C["pareggio"])
    if vinta:
        return float(C["vittoria_supp"] if supp else C["vittoria"])
    return float(C["sconfitta_supp"] if supp else C["sconfitta"])


def tabella(ris: list[dict], P: dict) -> list[dict]:
    """Classifica di un sistema: righe ordinate con pos, w, l, p (pareggi), pt (a punti), pf, ps, media, diff."""
    C = P["classifica"]
    per: dict[str, list[dict]] = {}
    for r in ris:
        pc, pt = float(r["punti_casa"]), float(r["punti_trasferta"])
        supp = bool(r.get("supplementari"))
        for t, avv, f, s, lato in ((r["casa"], r["trasferta"], pc, pt, "casa"), (r["trasferta"], r["casa"], pt, pc, "trasferta")):
            pari, vinta = r["vince"] == "pari", r["vince"] == lato
            per.setdefault(t, []).append({"giornata": r["giornata"], "avv": avv, "fatti": f, "subiti": s, "vinta": vinta,
                                          "pari": pari, "supp": supp, "punti": _punti_partita(vinta, pari, supp, C)})
    st = {}
    for t in [x["id"] for x in config.squadre()]:
        p = per.get(t, [])
        n, fatti, subiti = len(p), sum(x["fatti"] for x in p), sum(x["subiti"] for x in p)
        st[t] = {"team": t, "g": n, "w": sum(x["vinta"] for x in p), "p": sum(x["pari"] for x in p),
                 "l": sum(not x["vinta"] and not x["pari"] for x in p), "pt": sum(x["punti"] for x in p),
                 "pf": fatti, "ps": subiti, "media": ottavi(fatti / n) if n else 0.0, "diff": fatti - subiti,
                 "striscia": CL._striscia(p), "partite": p}
    if C["modo"] == "punti":
        per_p = {t: s["partite"] for t, s in st.items()}
        ordine = []
        for v in sorted({s["pt"] for s in st.values()}, reverse=True):
            ordine += CL._ordina_pari([t for t, s in st.items() if s["pt"] == v], st, per_p)
    else:
        ordine = CL.ordina(st)
    return [{**st[t], "pos": i + 1} for i, t in enumerate(ordine)]


def classifica(sist: dict, stagione: str) -> list[dict]:
    return tabella(risultati_stagione(sist, stagione), parametri(sist))


def confronta(sist: dict, stagione: str) -> dict:
    """Ufficiale (lega_risultati, la classifica di loucabot) contro il sistema: posizioni e partite che cambiano esito."""
    uff, _ = CL.calcola(stagione)
    pos_u = {r["team"]: r for r in uff}
    alt = classifica(sist, stagione)
    righe = [{**r, "uff": pos_u.get(r["team"])} for r in alt]
    vere = {(r["giornata"], r["casa"]): r for r in CL.risultati(stagione)}
    cambiano = []
    for r in risultati_stagione(sist, stagione):
        v = vere.get((r["giornata"], r["casa"]))
        if v and v["vince"] != r["vince"]:
            cambiano.append({"giornata": r["giornata"], "casa": r["casa"], "trasferta": r["trasferta"],
                             "prima": v["vince"], "dopo": r["vince"], "supplementari": r["supplementari"]})
    return {"righe": righe, "cambiano": cambiano, "giornate": len(giornate_convalidate(stagione))}


def centesimi(x):
    """Come lo salva lega_risultati (NUMERIC a due decimali, la metà lontano da zero)."""
    from decimal import ROUND_HALF_UP, Decimal
    return None if x is None else float(Decimal(repr(float(x))).quantize(Decimal("0.01"), ROUND_HALF_UP))


def verifica(stagione: str) -> list[str]:
    """L'Ufficiale di klra contro i risultati convalidati della lega: deve dare gli stessi numeri."""
    uff = basi.q("SELECT * FROM klra_sistemi WHERE ufficiale", one=True)
    vere = {(r["giornata"], r["casa"]): r for r in CL.risultati(stagione)}
    diff = []
    for r in risultati_stagione(uff, stagione):
        v = vere.get((r["giornata"], r["casa"]))
        if not v:
            continue
        a = (float(v["punti_casa"]), float(v["punti_trasferta"]), v["vince"],
             None if v["supp_casa"] is None else float(v["supp_casa"]), None if v["supp_trasferta"] is None else float(v["supp_trasferta"]))
        b = (centesimi(r["punti_casa"]), centesimi(r["punti_trasferta"]), r["vince"], centesimi(r["supp_casa"]), centesimi(r["supp_trasferta"]))
        if a != b:
            diff.append(f"G{r['giornata']} {config.nome(r['casa'])}–{config.nome(r['trasferta'])}: lega {a}, klra {b}")
    return diff

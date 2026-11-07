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
# v7.1.0: i risultati della stagione col sistema, al posto di lega_risultati nelle letture del codice di loucabot
# (calendario, calendario_full, classifiche): vedi contesto() e _q
_RIS: contextvars.ContextVar = contextvars.ContextVar("klra_risultati", default=None)
_NOME: contextvars.ContextVar = contextvars.ContextVar("klra_nome", default=None)
# v2: conference alternative attive (riga di klra_conference) e le loro partite al posto di lega_partite
_CONF: contextvars.ContextVar = contextvars.ContextVar("klra_conference", default=None)
_PARTITE: contextvars.ContextVar = contextvars.ContextVar("klra_partite", default=None)
_TABELLA_PARTITE = """(SELECT * FROM json_to_recordset(%s::json) AS x(id int, stagione text, giornata int, casa text, trasferta text))"""
STRISCIA = "🧪 KLRA · NON UFFICIALE · sistema {} · i risultati veri sono quelli di loucabot"
_TABELLA = """(SELECT * FROM json_to_recordset(%s::json) AS x(stagione text, giornata int, casa text, trasferta text,
  punti_casa numeric, punti_trasferta numeric, supp_casa numeric, supp_trasferta numeric, vince text, convalidato timestamptz))"""
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


def _sostituisci(sql: str, params, righe_json: str, tabella: str = "lega_risultati", con: str | None = None):
    """Ogni «lega_risultati» (o la tabella indicata) della query diventa una tabella fatta coi dati di klra
    (json_to_recordset), col suo parametro al posto giusto. Solo letture: klra non scrive mai nel database della lega."""
    import re
    params = list(params) if params is not None else []
    out, i = "", 0
    for m in re.finditer(r"\b" + tabella + r"\b", sql):
        out += sql[i:m.start()]
        params.insert(out.count("%s"), righe_json)
        out += con or _TABELLA
        i = m.end()
    out += sql[i:]
    return out, tuple(params)


def _q(sql, params=None, one=False, many=False):
    righe = _RIS.get()
    if righe is not None and "lega_risultati" in sql:
        sql, params = _sostituisci(sql, params, righe)
    partite = _PARTITE.get()
    if partite is not None and "lega_partite" in sql:
        sql, params = _sostituisci(sql, params, partite, "lega_partite", _TABELLA_PARTITE)
    return _orig["q"](sql, params, one=one, many=many)


class in_conference:
    """with motore.in_conference(conf): calcoli e codice di loucabot col calendario delle conference alternative
    (None = le ufficiali, anche dentro un altro in_conference)."""
    def __init__(self, conf: dict | None, stagione: str | None = None):
        self.conf, self.stagione = conf, stagione or config.stagione()

    def __enter__(self):
        installa()
        if self.conf:
            from klra import conference as CO
            prima = _PARTITE.set(None)                       # le partite vere, per costruire quelle permutate
            try:
                pj = CO.partite_json(self.conf, self.stagione)
            finally:
                _PARTITE.reset(prima)
        else:
            pj = None
        self._t = (_CONF.set(self.conf), _PARTITE.set(pj))
        return self

    def __exit__(self, *a):
        _PARTITE.reset(self._t[1])
        _CONF.reset(self._t[0])
        return False


def _conference_lega():
    """classifica.conference di loucabot: con le conference alternative, le loro."""
    c = _CONF.get()
    if c:
        from klra import conference as CO
        return CO.appartenenza(c)
    return _orig["conference"]()


def _scheda_player(gid: int) -> str:
    """/player di loucabot: dentro contesto(), in testa NON UFFICIALE e in fondo la stagione col sistema (v2)."""
    t = _orig["scheda"](gid)
    P, nome = _ATTIVO.get(), _NOME.get()
    if not P or not nome:
        return t
    return t + "\n\n" + sezione_player(gid, P, nome)


def sezione_player(gid: int, P: dict, nome: str) -> str:
    """Fantamedia della stagione e ultime 5 partite coi fantapunti del sistema, accanto quelli della lega."""
    import html
    from numeri import testo as tp
    g = db.q("SELECT espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    a = (g or {}).get("espn_id")
    righe = [f"🧪 <b>Col sistema {html.escape(nome)}</b> (NON UFFICIALE)"]
    if not a:
        return righe[0] + "\n<i>non abbinato a ESPN: niente statistiche</i>"
    tab = db.q("""SELECT t.*, p.inizio, p.casa, p.trasferta FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                  WHERE t.atleta = %s AND p.stagione = %s AND p.tipo = ANY(%s) AND t.giocato ORDER BY p.inizio""",
               (a, config.stagione(), [2, 5]), many=True) or []
    es = _esiti_nba({r["partita"] for r in tab}) if P["giocatore"]["vittoria_nba"] else {}
    conta = [r for r in tab if not (float(r["fp"] or 0) == 0 and int(r["minuti"] or 0) == 0)]
    if not conta:
        return righe[0] + "\n<i>nessuna partita in stagione</i>"
    mia = [fp_riga(r, P, es) for r in conta]
    lega = [float(r["fp"] or 0) for r in conta]
    righe.append(f"Fantamedia <b>{tp(ottavi(sum(mia) / len(mia)))}</b> (lega {tp(ottavi(sum(lega) / len(lega)))}) su {len(mia)} partite")
    from zoneinfo import ZoneInfo
    for r, x in list(zip(conta, mia))[-5:]:
        avv = r["trasferta"] if r["squadra"] == r["casa"] else r["casa"]
        b = bonus_riga(r, P, es)
        righe.append(f"• {r['inizio'].astimezone(ZoneInfo('Europe/Rome')):%d/%m} {'vs' if r['squadra'] == r['casa'] else '@'} {avv}: "
                     f"<b>{tp(x)}</b> (lega {tp(float(r['fp'] or 0))})" + (" " + " ".join(f"{'+' if v > 0 else ''}{v:g} {l}" for l, v in b) if b else ""))
    return "\n".join(righe)


def nome_contesto(sist: dict) -> str:
    c = _CONF.get()
    return sist["nome"] + (f" · conference {c['nome']}" if c else "")


def _ordina(st):
    """classifica.ordina di loucabot: col sistema, l'ordine della classifica del sistema (a punti, pareggi)."""
    P, righe = _ATTIVO.get(), _RIS.get()
    if P is None or righe is None:
        return _orig["ordina"](st)
    ordine = [r["team"] for r in tabella(json.loads(righe), P)]
    return [t for t in ordine if t in st] + [t for t in st if t not in ordine]


def righe_lega(sist: dict, stagione: str) -> str:
    """I risultati del sistema nella forma di lega_risultati (JSON per _sostituisci)."""
    conv = giornate_convalidate(stagione)
    out = []
    for r in risultati_stagione(sist, stagione):
        out.append({"stagione": stagione, "giornata": r["giornata"], "casa": r["casa"], "trasferta": r["trasferta"],
                    "punti_casa": centesimi(r["punti_casa"]), "punti_trasferta": centesimi(r["punti_trasferta"]),
                    "supp_casa": centesimi(r["supp_casa"]), "supp_trasferta": centesimi(r["supp_trasferta"]),
                    "vince": r["vince"], "supplementari": r["supplementari"], "convalidato": str(conv.get(r["giornata"])),
                    "tot_casa": r["sc"]["totale"], "tot_trasferta": r["st"]["totale"]})
    return json.dumps(out)


class contesto:
    """with motore.contesto(sistema): il codice di loucabot chiamato dentro vede risultati e regole del sistema."""
    def __init__(self, sist: dict, stagione: str | None = None, righe: str | None = None):
        self.sist, self.stagione, self.righe = sist, stagione or config.stagione(), righe

    def __enter__(self):
        installa()
        # prima di sostituire: legge la lega vera (in un comando, calcolata prima in un thread e passata qui)
        righe = self.righe if self.righe is not None else righe_lega(self.sist, self.stagione)
        self._t = (_ATTIVO.set(KR.completa(parametri(self.sist))), _RIS.set(righe), _NOME.set(nome_contesto(self.sist)))
        return self

    def __exit__(self, *a):
        _NOME.reset(self._t[2])
        _RIS.reset(self._t[1])
        _ATTIVO.reset(self._t[0])
        return False


def _non_ufficiale(f):
    """Le immagini di loucabot fatte dentro contesto(): con striscia e filigrana NON UFFICIALE."""
    def g(*a, **k):
        d = f(*a, **k)
        if _NOME.get() and isinstance(d, dict):
            d = {**d, "filigrana": "NON UFFICIALE", "striscia": STRISCIA.format(_NOME.get())}
        return d
    return g


def installa() -> None:
    if _orig:
        return
    import live
    import partita
    _orig.update(tab=db.tabellini_atleti, medie=db.medie_stagione, pg=calcolo.punteggio_giocatori,
                 fadd=calcolo._fadd_possibile, calcola=RIS.calcola, live=live.calcolo, stato=partita._stato_calcolo,
                 q=db.q, ordina=CL.ordina, conference=CL.conference)
    CL.conference = _conference_lega
    import player
    _orig["scheda"] = player.scheda
    player.scheda = _scheda_player
    db.q = _q
    CL.ordina = _ordina
    CL.dati_typst = _non_ufficiale(CL.dati_typst)
    CL.dati_conference = _non_ufficiale(CL.dati_conference)
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


_MEMO: contextvars.ContextVar = contextvars.ContextVar("klra_memo", default=None)


class memo:
    """with motore.memo(): dentro, calcolo_completo della stessa giornata col sistema si fa una volta (PDF: v7.1.0)."""
    def __enter__(self):
        self._t = _MEMO.set({})
        return self

    def __exit__(self, *a):
        _MEMO.reset(self._t)
        return False


def calcolo_completo(P: dict, stagione: str, n: int, sch: dict | None = None) -> dict:
    m = _MEMO.get()
    if m is not None and sch is None:
        import copy
        k = (KR.firma(P), stagione, n)
        if k not in m:
            m[k] = _calcolo_completo(P, stagione, n)
        return copy.deepcopy(m[k])
    return _calcolo_completo(P, stagione, n, sch)


def _calcolo_completo(P: dict, stagione: str, n: int, sch: dict | None = None) -> dict:
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
    cc = P["partita"]["chi_conta"]
    if cc != "titolari":                                   # Fantapanchine (v2): i panchinari nel totale
        for s in sq.values():
            pan = ottavi(sum(float(x["fp"]) for x in s["panchina"]))
            s["totale_titolari"] = s["totale"]
            s["totale"] = pan if cc == "panchina" else ottavi(s["totale"] + pan)
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
        senza = cc != "titolari"                           # panchinari già nel totale: nessuno per i supplementari
        es = esito(r["sc"]["totale"], r["st"]["totale"], [] if senza else r["sc"]["panchina"], [] if senza else r["st"]["panchina"], P, bc)
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
    if sist.get("predefinito") in KR.PREDEFINITI:
        return KR.predefinito(sist["predefinito"])
    p = sist["parametri"] if isinstance(sist["parametri"], dict) else json.loads(sist["parametri"])
    return KR.completa(p)


def giornate_convalidate(stagione: str) -> dict[int, object]:
    """{giornata: ultima convalida} della lega."""
    righe = db.q("""SELECT giornata, MAX(convalidato) AS c FROM lega_risultati WHERE stagione = %s AND convalidato IS NOT NULL
                    GROUP BY giornata ORDER BY giornata""", (stagione,), many=True) or []
    return {r["giornata"]: r["c"] for r in righe}


# cambia quando cambia il modo di calcolare (motore o loucabot): la cache vecchia non vale più
# v2 (v7.1.0): FADD di chi non ha tabellini nei ricalcoli di giornate vecchie
VERSIONE_MOTORE = "2"


def firma_cache(P: dict) -> str:
    """Parametri + versione del motore + (se attive) le conference alternative con il loro accoppiamento."""
    c = _CONF.get()
    extra = ""
    if c:
        import hashlib
        m = c["mappa"] if isinstance(c["mappa"], dict) else json.loads(c["mappa"])
        extra = ":c" + hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest()[:12]
    return KR.firma(P) + ":" + VERSIONE_MOTORE + extra


def risultati_giornata(sist: dict, stagione: str, n: int, convalidato=None) -> dict:
    P = parametri(sist)
    f = firma_cache(P)
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
        # totali della squadra senza bonus casa né supplementari (classifica cumulativa, v2)
        tc = float(r["sc"]["totale"] if "sc" in r else r.get("tot_casa", pc))
        tt = float(r["st"]["totale"] if "st" in r else r.get("tot_trasferta", pt))
        for t, avv, f, s, lato, tot in ((r["casa"], r["trasferta"], pc, pt, "casa", tc), (r["trasferta"], r["casa"], pt, pc, "trasferta", tt)):
            pari, vinta = r["vince"] == "pari", r["vince"] == lato
            per.setdefault(t, []).append({"giornata": r["giornata"], "avv": avv, "fatti": f, "subiti": s, "vinta": vinta,
                                          "pari": pari, "supp": supp, "punti": _punti_partita(vinta, pari, supp, C), "tot": tot})
    st = {}
    for t in [x["id"] for x in config.squadre()]:
        p = per.get(t, [])
        n, fatti, subiti = len(p), sum(x["fatti"] for x in p), sum(x["subiti"] for x in p)
        st[t] = {"team": t, "g": n, "w": sum(x["vinta"] for x in p), "p": sum(x["pari"] for x in p),
                 "l": sum(not x["vinta"] and not x["pari"] for x in p), "pt": sum(x["punti"] for x in p),
                 "pf": fatti, "ps": subiti, "media": ottavi(fatti / n) if n else 0.0, "diff": fatti - subiti,
                 "striscia": CL._striscia(p), "partite": p, "cumulati": ottavi(sum(x["tot"] for x in p)),
                 "media_cumulati": ottavi(sum(x["tot"] for x in p) / n) if n else 0.0}
    if C["modo"] == "cumulativa":                         # punti fatti in totale, niente partite (Luca, 05-06/11)
        st_ = sorted(st, key=lambda t: (-st[t]["cumulati"], -st[t]["media_cumulati"], t))
        return [{**st[t], "pos": i + 1, "pt": st[t]["cumulati"]} for i, t in enumerate(st_)]
    if C["modo"] == "punti":
        per_p = {t: s["partite"] for t, s in st.items()}
        ordine = []
        for v in sorted({s["pt"] for s in st.values()}, reverse=True):
            ordine += CL._ordina_pari([t for t, s in st.items() if s["pt"] == v], st, per_p)
    else:
        ordine = _orig.get("ordina", CL.ordina)(st)          # quella di loucabot, non la sostituta (_ordina)
    return [{**st[t], "pos": i + 1} for i, t in enumerate(ordine)]


def classifica(sist: dict, stagione: str) -> list[dict]:
    return tabella(risultati_stagione(sist, stagione), parametri(sist))


def ufficiale_sistema() -> dict:
    return basi.q("SELECT * FROM klra_sistemi WHERE ufficiale", one=True)


def confronta(sist: dict, stagione: str) -> dict:
    """L'Ufficiale ricalcolato coi dati di oggi contro il sistema: posizioni e partite che cambiano esito. Si parte dal
    ricalcolo e non dai risultati convalidati, così le differenze vengono solo dalle regole (v7.1.0: le correzioni di
    ESPN arrivate dopo la convalida non si mescolano)."""
    uff = ufficiale_sistema()
    with in_conference(None):                              # l'Ufficiale col calendario vero, anche con conference alternative
        pos_u = {r["team"]: r for r in classifica(uff, stagione)}
        vere = {(r["giornata"], r["casa"]): r for r in risultati_stagione(uff, stagione)}
    alt = classifica(sist, stagione)
    righe = [{**r, "uff": pos_u.get(r["team"])} for r in alt]
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


def verifica(stagione: str) -> dict:
    """{"motore": differenze tra l'Ufficiale di klra e il ricalcolo di oggi di loucabot (devono essere zero),
        "dati": partite in cui il ricalcolo di oggi è diverso dalla convalida (dati cambiati dopo: correzioni di ESPN,
        decisioni degli admin; i risultati ufficiali restano quelli convalidati)}."""
    installa()
    uff = ufficiale_sistema()
    motore, dati = [], []
    for n, conv in giornate_convalidate(stagione).items():
        oggi = _orig["calcola"](stagione, n)
        kl = {r["casa"]: r for r in calcola_giornata(parametri(uff), stagione, n)["risultati"]}   # niente cache: i dati di oggi
        for r in oggi["risultati"]:
            k = kl.get(r["casa"])
            a = (centesimi(r["punti_casa"]), centesimi(r["punti_trasferta"]), r["vince"], centesimi(r.get("supp_casa")),
                 centesimi(r.get("supp_trasferta")))
            b = (centesimi(k["punti_casa"]), centesimi(k["punti_trasferta"]), k["vince"], centesimi(k["supp_casa"]),
                 centesimi(k["supp_trasferta"])) if k else None
            if a != b:
                motore.append(f"G{n} {config.nome(r['casa'])}–{config.nome(r['trasferta'])}: loucabot {a}, klra {b}")
        dati += [f"G{n} " + x.lstrip("• ") for x in (RIS.differenze(stagione, n, oggi["risultati"]) or [])]
    return {"motore": motore, "dati": dati}

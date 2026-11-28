"""
/prestazione GIOCATORE [DATA] (v7.31.0, Luca 26/11; mockup approvato): la singola notte di un giocatore, in immagine
(shared/prestazione.typ, viola come /player). Senza data l'ultima partita giocata; con la data quella notte.

- Se quella notte la sua squadra NBA ha giocato e lui no (DNP, infortunato, non a referto): l'immagine con 0 e il
  motivo (lo status dell'injury report di quella sera, o «DNP, scelta tecnica»), più l'ultima partita giocata prima e
  la prima dopo, coi bottoni.
- Se quella notte la sua squadra non ha giocato: si sceglie tra la partita prima e quella dopo (bottoni).
- In offseason NBA (tra l'ultima partita di una stagione e la prima della successiva) lo dice.
- Lo storico è quello dei tabellini ESPN, dal 22/10/2026 (`INIZIO`): prima ci sono solo le medie di bref.

Dati: nba_tabellini e nba_partite (loucabot), nba_infortuni (lo status di quella sera), movimenti_giocatori (di che
squadra del fanta era), lega_giornate (la giornata), ipa_formazioni e ipa_panchine (titolare, panchinaro o fuori).
Callback `pre:<giocatore>:<partita>` per le frecce e le scelte.
"""
import html
import json
import os
from datetime import date, datetime, timedelta

from shared import lettura as L
from shared import non_ufficiale as NU          # v7.41.0: in klra i fantapunti e i pesi del sistema
from shared import regole

INIZIO = date(2026, 10, 22)
TIPI = (2, 3, 5)
TIPO = {2: "regular season", 3: "playoff", 5: "play-in"}
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
GIORNI_BREVI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
VOCI = [("ast", "Assist"), ("pts", "Punti"), ("fgm", "Tiri segnati"), ("dreb", "Rimb. difensivi"), ("tpm", "Triple"),
        ("ftm", "Liberi segnati"), ("oreb", "Rimb. offensivi"), ("stl", "Recuperi"), ("blk", "Stoppate"),
        ("fta", "Liberi tentati"), ("tov", "Perse"), ("fga", "Tiri tentati")]
# v7.35.0 (Luca, 26/11): la composizione dei fantapunti per voce, la notte contro la media della stagione intera.
# Punti = punti + tiri, triple e liberi (segnati e tentati); le perse a parte, fuori dalla barra
GRUPPI = [("Punti", ("pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta")), ("Assist", ("ast",)), ("Rimbalzi", ("dreb", "oreb")),
          ("Recuperi", ("stl",)), ("Stoppate", ("blk",))]
COLONNE = [("MIN", "minuti"), ("PTS", "pts"), ("REB", "reb"), ("OREB", "oreb"), ("DREB", "dreb"), ("AST", "ast"),
           ("STL", "stl"), ("BLK", "blk"), ("TO", "tov"), ("PF", "pf")]
MENO_E_MEGLIO = {"tov", "pf"}
e = lambda x: html.escape(str(x), quote=False)


def _n(x, dec: int = 2) -> str:
    s = f"{float(x):.{dec}f}".replace(".", ",")
    return s.rstrip("0").rstrip(",") if dec and "," in s else s


def _segno(x: float, dec: int = 1) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "±") + _n(abs(x), dec) if dec else ""


def _breve(d: date) -> str:
    return f"{GIORNI_BREVI[d.weekday()]} {d:%d/%m}"


# ── le partite ────────────────────────────────────────────────────────────────

def righe(atleta: str) -> list[dict]:
    """Tutte le righe di tabellino del giocatore (anche DNP), con la partita, dalla più vecchia."""
    return L.q("""SELECT t.*, p.data_et, p.inizio, p.tipo, p.stagione, p.casa, p.trasferta, p.punti_casa, p.punti_trasferta
                  FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                  WHERE t.atleta = %s AND p.tipo = ANY(%s) ORDER BY p.inizio""", (atleta, list(TIPI)), many=True) or []


def giocate(rr: list[dict]) -> list[dict]:
    return [r for r in rr if r["giocato"]]


def vicine(rr: list[dict], giorno: date) -> tuple[dict | None, dict | None]:
    """L'ultima partita giocata prima del giorno e la prima dopo."""
    g = giocate(rr)
    prima = [r for r in g if r["data_et"] < giorno]
    dopo = [r for r in g if r["data_et"] > giorno]
    return (prima[-1] if prima else None), (dopo[0] if dopo else None)


def squadra_al(atleta: str, rr: list[dict], giorno: date) -> str | None:
    """La squadra NBA del giocatore quel giorno: l'ultimo tabellino fino a quel giorno, se no il cambio di squadra
    registrato, se no il roster di adesso."""
    prima = [r for r in rr if r["data_et"] <= giorno]
    if prima:
        return prima[-1]["squadra"]
    m = L.q("SELECT a FROM nba_movimenti WHERE atleta = %s AND giorno <= %s ORDER BY giorno DESC, id DESC LIMIT 1",
            (atleta, giorno), one=True)
    if m:
        return m["a"]
    return L.squadre_roster([atleta]).get(atleta)


def partita_squadra(sq: str, giorno: date) -> dict | None:
    return L.q("""SELECT * FROM nba_partite WHERE data_et = %s AND tipo = ANY(%s) AND (casa = %s OR trasferta = %s)
                  AND stato NOT IN ('STATUS_POSTPONED', 'STATUS_CANCELED') ORDER BY inizio LIMIT 1""",
               (giorno, list(TIPI), sq, sq), one=True)


def offseason(giorno: date) -> bool:
    """Nessuna partita NBA (regular season, play-in, playoff) entro 10 giorni prima e dopo: offseason."""
    r = L.q("SELECT 1 AS x FROM nba_partite WHERE tipo = ANY(%s) AND data_et BETWEEN %s AND %s LIMIT 1",
            (list(TIPI), giorno - timedelta(days=10), giorno + timedelta(days=10)), one=True)
    return not r


def motivo_assenza(atleta: str, sq: str | None, giorno: date, riga: dict | None) -> str:
    """Perché non ha giocato: lo status dell'injury report di quella sera (l'ultimo prima della partita), se no DNP."""
    p = partita_squadra(sq, giorno) if sq else None
    inf = L.q("""SELECT stato, dettaglio FROM nba_infortuni WHERE atleta = %s AND giorno = %s
                 AND (%s::timestamptz IS NULL OR preso <= %s) ORDER BY preso DESC LIMIT 1""",
              (atleta, giorno, p["inizio"] if p else None, p["inizio"] if p else None), one=True)
    if inf:
        return f"{inf['stato']}" + (f" ({inf['dettaglio'][:70]})" if inf.get("dettaglio") else "")
    return "DNP, scelta tecnica" if riga else "non a referto"


# ── il fantabasket ─────────────────────────────────────────────────────────────

def fanta(gid: int, giorno: date, inizio) -> dict:
    """Di che squadra era quella notte, la giornata della lega e se era titolare, in panchina o fuori."""
    from shared import rosa, codici_giornata as CG
    team = rosa.squadre_al(L.q, [gid], inizio or datetime.combine(giorno, datetime.max.time())).get(gid)
    s = str(giorno.year if giorno.month >= 7 else giorno.year - 1)
    g = L.q("SELECT numero FROM lega_giornate WHERE stagione = %s AND dal <= %s AND al >= %s", (s, giorno, giorno), one=True)
    out = {"team": team, "squadra": L.nome(team) if team else "", "giornata": CG.codice(g["numero"], s) if g else "", "ruolo": ""}
    if team and g:
        try:
            f = L.q("SELECT ruolo FROM ipa_formazioni WHERE stagione = %s AND giornata = %s AND team_id = %s AND giocatore_id = %s",
                    (s, g["numero"], team, gid), one=True)
            if f:
                out["ruolo"] = f"titolare ({f['ruolo']})"
            else:
                pa = L.q("SELECT righe FROM ipa_panchine WHERE stagione = %s AND giornata = %s AND team_id = %s",
                         (s, g["numero"], team), one=True)
                rr = pa["righe"] if pa else []
                rr = json.loads(rr) if isinstance(rr, str) else rr
                pos = [i for i, x in enumerate(rr or [], 1) if x.get("giocatore_id") == gid]
                out["ruolo"] = f"panchinaro n. {pos[0]}" if pos else ("fuori formazione" if pa else "")
        except Exception:
            pass                                       # IPanchinari non c'è (prove, klra)
    return out


# ── i dati dell'immagine ───────────────────────────────────────────────────────

def _reb(r: dict) -> int:
    return int(r["oreb"] or 0) + int(r["dreb"] or 0)


def _val(r: dict, k: str) -> float:
    return _reb(r) if k == "reb" else float(r[k] or 0)


def _pct(m: float, a: float) -> str:
    return f"{_n(100 * m / a, 1)}%" if a else "—"


def badge(r: dict, stagione: list[dict], tutte: list[dict]) -> list[str]:
    out = []
    doppie = sum(1 for k in ("pts", "ast", "stl", "blk") if float(r[k] or 0) >= 10) + (1 if _reb(r) >= 10 else 0)
    if doppie >= 3:
        out.append("🏀 TRIPLA DOPPIA")
    elif doppie == 2:
        out.append("🏀 DOPPIA DOPPIA")
    if len(tutte) > 1 and NU.fp(r) >= max(NU.fp(x) for x in tutte):
        out.append("⭐ RECORD DI FANTAPUNTI DAL 22/10/2026")
    elif len(stagione) > 1 and NU.fp(r) >= max(NU.fp(x) for x in stagione):
        out.append("⭐ RECORD STAGIONALE DI FANTAPUNTI")
    for k, nome in (("pts", "PUNTI"), ("reb", "RIMBALZI"), ("ast", "ASSIST")):
        if len(stagione) > 1 and _val(r, k) > 0 and _val(r, k) >= max(_val(x, k) for x in stagione) \
                and sum(1 for x in stagione if _val(x, k) >= _val(r, k)) == 1:
            out.append(f"⭐ RECORD STAGIONALE DI {nome}")
    return out[:3]                                       # non più di una riga


def dati(gid: int, r: dict | None, giorno: date, rr: list[dict], foto_di=None, motivo: str = "") -> dict:
    """I dati di prestazione.typ per la notte `giorno`: `r` la riga di tabellino (None se non a referto)."""
    g = L.q("SELECT id, nome_common, espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    atleta = g["espn_id"]
    sq = r["squadra"] if r else squadra_al(atleta, rr, giorno)
    p = (L.q("SELECT * FROM nba_partite WHERE espn_id = %s", (r["partita"],), one=True) if r else partita_squadra(sq, giorno)) or {}
    casa = p.get("casa") == sq
    avv = p.get("trasferta") if casa else p.get("casa")
    pn, pa = (p.get("punti_casa"), p.get("punti_trasferta")) if casa else (p.get("punti_trasferta"), p.get("punti_casa"))
    esito = ""
    if pn is not None and pa is not None:
        esito = f"{'V' if pn > pa else 'S'} {pn}–{pa}"
    giocato = bool(r and r["giocato"])
    stag = p.get("stagione")
    st = [x for x in giocate(rr) if x["stagione"] == stag]
    f = foto_di(gid) if foto_di else None
    nomi = [x for x in (g["nome_common"] or "").split() if x]
    d = {"nome": g["nome_common"], "iniziali": "".join(x[0] for x in nomi[:2]).upper(),
         "foto": os.path.abspath(f) if f and os.path.exists(f) else "",
         "sq": sq or "", "contro": ("vs " if casa else "@ ") + (avv or "?"),
         "data": f"{GIORNI[giorno.weekday()]} {giorno:%d/%m/%Y}",
         "sotto": " · ".join(x for x in ((("Titolare" if r["titolare"] else "Dalla panchina") + f" · {r['minuti']} minuti") if giocato else "",
                                         TIPO.get(p.get("tipo"), "")) if x),
         "esito": esito, "vinta": bool(pn is not None and pa is not None and pn > pa),
         "punteggio": f"{p.get('casa')} {p.get('punti_casa')} · {p.get('trasferta')} {p.get('punti_trasferta')}" if esito else "",
         "giocato": giocato, "motivo": motivo, "badge": [], "riquadri": [], "tabella": [], "tiri": [], "voci": [], "totale": "",
         "correzione": "", "prima": "", "dopo": ""}
    fa = fanta(gid, giorno, p.get("inizio"))
    # v7.31.2 (Luca, 26/11): la squadra del fantabasket in evidenza, in una fascia sua sotto i riquadri
    d["fanta"] = {"squadra": fa["squadra"] or "svincolato", "giornata": fa["giornata"], "ruolo": fa["ruolo"]}
    prima, dopo = vicine(rr, giorno)
    if prima:
        d["prima"] = f"Prima: {_breve(prima['data_et'])} {_contro(prima)} · {_n(NU.fp(prima))} fp"
    if dopo:
        d["dopo"] = f"Dopo: {_breve(dopo['data_et'])} {_contro(dopo)} · {_n(NU.fp(dopo))} fp"
    if not giocato:
        d["riquadri"] = [{"t": "Fantapunti", "v": "0", "s": motivo}]
        return d
    fp = NU.fp(r)
    pos = 1 + sum(1 for x in st if NU.fp(x) > fp)
    if NU.attivo():                                  # v7.41.0, klra: la notte coi fantapunti del sistema
        tutti_n = L.q("""SELECT t.* FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                         WHERE p.data_et = %s AND p.tipo = ANY(%s) AND t.giocato""", (giorno, list(TIPI)), many=True) or []
        notte = {"sopra": sum(1 for x in tutti_n if NU.fp(x) > fp), "tutti": len(tutti_n)}
    else:
        notte = L.q("""SELECT COUNT(*) FILTER (WHERE t.fp > %s) AS sopra, COUNT(*) AS tutti FROM nba_tabellini t
                       JOIN nba_partite p ON p.espn_id = t.partita WHERE p.data_et = %s AND p.tipo = ANY(%s) AND t.giocato""",
                    (fp, giorno, list(TIPI)), one=True)
    media = sum(NU.fp(x) for x in st) / len(st) if st else fp
    # v7.31.1 (Luca, 26/11): il confronto sia con la media di tutta la stagione sia con quella fino a quella notte
    pr = [x for x in st if x["inizio"] < r["inizio"]]
    media_p = sum(NU.fp(x) for x in pr) / len(pr) if pr else None
    # v7.31.2: due riquadri, la media fino a quella notte e quella di tutta la stagione
    pt = lambda k: f"{k} partit{'a' if k == 1 else 'e'}"
    rq_prima = ({"t": "Sulla media fino a lì", "v": _segno(fp - media_p, 1), "s": f"media {_n(media_p)} in {pt(len(pr))}"}
                if pr else {"t": "Sulla media fino a lì", "v": "—", "s": "la prima partita della stagione"})
    rq_stag = {"t": "Sulla media stagione", "v": _segno(fp - media, 1), "s": f"media {_n(media)} in {pt(len(st))}"}
    d["riquadri"] = [
        {"t": "Fantapunti", "v": _n(fp), "s": f"{pos}ª migliore della stagione" if len(st) > 1 else "la prima della stagione"},
        {"t": "Della notte", "v": f"{notte['sopra'] + 1}°", "s": f"su {notte['tutti']} in campo"},
        rq_prima, rq_stag]
    d["badge"] = badge(r, st, giocate(rr))
    def colonna(gg):
        return {k: (sum(_val(x, k) for x in gg) / len(gg) if gg else None) for _, k in COLONNE}
    def cella(k, m):
        if m is None:
            return {"m": "—", "d": "", "buono": True}
        return {"m": _n(m, 1), "d": _segno(_val(r, k) - m, 1), "buono": (_val(r, k) - m) * (-1 if k in MENO_E_MEGLIO else 1) >= 0}
    mp, ms = colonna(pr), colonna(st)
    d["medie"] = [f"Fino a lì ({len(pr)})", f"Stagione ({len(st)})"]
    d["tabella"] = [{"t": t, "v": str(int(_val(r, k))), "righe": [cella(k, mp[k]), cella(k, ms[k])]} for t, k in COLONNE]
    def pc(gg, m, a):
        return _pct(sum(float(x[m] or 0) for x in gg), sum(float(x[a] or 0) for x in gg)) if gg else "—"
    d["tiri"] = [{"t": t, "v": f"{r[m]}/{r[a]}", "s": f"{_pct(r[m], r[a])} · fino a lì {pc(pr, m, a)} · stagione {pc(st, m, a)}"}
                 for t, m, a in (("Tiri dal campo", "fgm", "fga"), ("Da tre", "tpm", "tpa"), ("Liberi", "ftm", "fta"))]
    pesi = NU.pesi()                                  # v7.41.0: in klra i pesi del sistema
    d["composizione"] = composizione(r, st, pesi)
    voci = [{"n": n, "q": int(r[k] or 0), "p": round(float(pesi.get(k, 0)) * float(r[k] or 0), 2)} for k, n in VOCI if pesi.get(k)]
    voci = [v for v in voci if v["p"]]
    voci.sort(key=lambda v: (v["p"] < 0, -abs(v["p"])))
    m = max([abs(v["p"]) for v in voci] or [1])
    d["voci"] = [{**v, "w": abs(v["p"]) / m, "pt": ("+" if v["p"] > 0 else "−") + _n(abs(v["p"]))} for v in voci]
    somma = round(sum(v["p"] for v in voci), 2)
    d["totale"] = _n(fp)
    if abs(somma - fp) > 0.001:
        d["correzione"] = (f"col sistema: {_n(somma)} dalle statistiche, {_n(fp)} con bonus e regole del sistema" if NU.attivo()
                           else f"corretto a mano dagli admin: dal tabellino {_n(somma)}")
    return d


def composizione(r: dict, st: list[dict], pesi: dict) -> dict:
    """I fantapunti della notte per gruppo di voci, con la media della stagione intera (le partite giocate) e la
    quota di ognuno sul prodotto (la barra: solo i gruppi in positivo)."""
    def fp(x, chiavi):
        return sum(float(pesi.get(k, 0)) * float(x.get(k) or 0) for k in chiavi)
    def medio(chiavi):
        return sum(fp(x, chiavi) for x in st) / len(st) if st else None
    i = lambda k: int(r.get(k) or 0)
    det = {"Punti": f"{i('pts')} pt, {i('fgm')}/{i('fga')}, {i('tpm')}/{i('tpa')} da 3, {i('ftm')}/{i('fta')} TL",
           "Assist": f"{i('ast')} assist", "Rimbalzi": f"{i('dreb')} dif + {i('oreb')} off",
           "Recuperi": f"{i('stl')} recuper{'o' if i('stl') == 1 else 'i'}",
           "Stoppate": f"{i('blk')} stoppat{'a' if i('blk') == 1 else 'e'}"}
    voci = [{"n": n, "v": round(fp(r, k), 2), "m": medio(k)} for n, k in GRUPPI]
    prod = sum(max(v["v"], 0) for v in voci)
    prod_m = sum(max(v["m"] or 0, 0) for v in voci)
    out = []
    for v in voci:
        m = v["m"]
        out.append({"n": v["n"], "v": ("+" if v["v"] >= 0 else "−") + _n(abs(v["v"])), "pos": v["v"] >= 0,
                    "q": max(v["v"], 0) / prod if prod else 0, "qm": max(m or 0, 0) / prod_m if prod_m else 0,
                    "m": _n(m, 1) if m is not None else "—", "d": _segno(v["v"] - m, 1) if m is not None else "",
                    "meglio": m is None or v["v"] >= m, "det": det[v["n"]]})
    perse, perse_m = fp(r, ("tov",)), medio(("tov",))
    conto = f"Notte: {_n(prod)} prodotti − {_n(abs(perse))} perse = {_n(prod + perse)}"
    if perse_m is not None and st:
        conto += f" · media stagione: {_n(prod_m, 1)} − {_n(abs(perse_m), 1)} = {_n(prod_m + perse_m, 1)}"
    return {"voci": out, "perse": {"v": "−" + _n(abs(perse)), "m": ("−" if perse_m < 0 else "") + _n(abs(perse_m), 1) if perse_m is not None else "—",
                                   "d": _segno(perse - perse_m, 1) if perse_m is not None else "",
                                   "meglio": perse_m is None or perse >= perse_m,
                                   "det": f"{i('tov')} pers{'a' if i('tov') == 1 else 'e'}, fuori dalla barra"},
            "conto": conto, "barra_media": bool(st and prod_m)}


def _contro(r: dict) -> str:
    return ("vs " if r["casa"] == r["squadra"] else "@ ") + (r["trasferta"] if r["casa"] == r["squadra"] else r["casa"])


def immagine(d: dict) -> bytes:
    import typst
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prestazione.typ")
    return typst.compile(tpl, root="/", format="png", ppi=144, sys_inputs={"dati": json.dumps(NU.marca(d), ensure_ascii=False)})


# ── la scelta della notte ──────────────────────────────────────────────────────

def notte(gid: int, giorno: date | None) -> dict:
    """Cosa mostrare: {"tipo": "scheda", "riga", "giorno", "motivo"} | {"tipo": "scegli", "prima", "dopo", "testo"} |
    {"tipo": "testo", "testo"}."""
    g = L.q("SELECT nome_common, espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    if not g or not g.get("espn_id"):
        return {"tipo": "testo", "testo": "Il giocatore non è abbinato a ESPN: niente tabellini."}
    rr = righe(g["espn_id"])
    nome = e(g["nome_common"])
    if giorno is None:
        gg = giocate(rr)
        if not gg:
            return {"tipo": "testo", "testo": f"Nessuna partita giocata di <b>{nome}</b> dal {INIZIO:%d/%m/%Y}."}
        return {"tipo": "scheda", "rr": rr, "riga": gg[-1], "giorno": gg[-1]["data_et"], "motivo": ""}
    if giorno < INIZIO:
        return {"tipo": "testo", "testo": f"I tabellini partono dal {INIZIO:%d/%m/%Y}: per prima ci sono solo le medie "
                                         "di Basketball-Reference (/rendimento, /carriera)."}
    if giorno > date.today():
        return {"tipo": "testo", "testo": f"Il {giorno:%d/%m/%Y} non è ancora arrivato."}
    stessa = [r for r in rr if r["data_et"] == giorno]
    if stessa and stessa[0]["giocato"]:
        return {"tipo": "scheda", "rr": rr, "riga": stessa[0], "giorno": giorno, "motivo": ""}
    sq = stessa[0]["squadra"] if stessa else squadra_al(g["espn_id"], rr, giorno)
    if stessa or (sq and partita_squadra(sq, giorno)):
        return {"tipo": "scheda", "rr": rr, "riga": stessa[0] if stessa else None, "giorno": giorno,
                "motivo": motivo_assenza(g["espn_id"], sq, giorno, stessa[0] if stessa else None)}
    if offseason(giorno):
        return {"tipo": "testo", "testo": f"Il {giorno:%d/%m/%Y} è offseason NBA: niente partite."}
    prima, dopo = vicine(rr, giorno)
    return {"tipo": "scegli", "prima": prima, "dopo": dopo,
            "testo": f"🏀 Il {giorno:%d/%m/%Y} {('i ' + e(sq)) if sq else 'la sua squadra'} non giocavano. "
                     + ("Quale partita di <b>" + nome + "</b>?" if (prima or dopo) else "Nessuna partita vicina.")}


def bottoni(gid: int, d_prima: dict | None, d_dopo: dict | None):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
    riga = []
    if d_prima:
        riga.append(B(f"◀ {_breve(d_prima['data_et'])} {_contro(d_prima)}", callback_data=f"pre:{gid}:{d_prima['data_et']:%Y%m%d}"))
    if d_dopo:
        riga.append(B(f"{_breve(d_dopo['data_et'])} {_contro(d_dopo)} ▶", callback_data=f"pre:{gid}:{d_dopo['data_et']:%Y%m%d}"))
    return K([riga]) if riga else None


def leggi(args: list[str]) -> tuple[str, date | None]:
    """«NOME [DATA]»: la data in fondo, se c'è (GG/MM, GG/MM/AA, GG/MM/AAAA, AAAA-MM-GG)."""
    from shared.date_comandi import leggi_data
    if len(args) > 1:
        ultimo = args[-1]
        d = leggi_data(ultimo)
        if not d and "/" in ultimo and ultimo.count("/") == 1:
            oggi = date.today()
            d = leggi_data(f"{ultimo}/{oggi.year}")
            if d and d > oggi:
                d = leggi_data(f"{ultimo}/{oggi.year - 1}")
        if d:
            return " ".join(args[:-1]), d
    return " ".join(args), None


def handlers(foto_di=None):
    """(cmd_prestazione, cb_prestazione) per un bot."""
    from shared import giocatore as G

    async def manda(msg, gid: int, giorno: date | None, modifica=None) -> None:
        import asyncio
        n = await asyncio.to_thread(notte, gid, giorno)
        if n["tipo"] == "testo":
            await msg.reply_text(n["testo"], parse_mode="HTML")
            return
        if n["tipo"] == "scegli":
            await msg.reply_text(n["testo"], parse_mode="HTML", reply_markup=bottoni(gid, n["prima"], n["dopo"]))
            return
        d = await asyncio.to_thread(dati, gid, n["riga"], n["giorno"], n["rr"], foto_di, n["motivo"])
        img = await asyncio.to_thread(immagine, d)
        prima, dopo = vicine(n["rr"], n["giorno"])
        await msg.reply_photo(img, caption=f"{d['nome']} · {n['giorno']:%d/%m/%Y}", reply_markup=bottoni(gid, prima, dopo))

    async def cmd_prestazione(update, context):
        msg = update.effective_message
        testo, giorno = leggi(context.args or [])
        if not testo:
            await msg.reply_text("Uso: /prestazione GIOCATORE [DATA] (es. /prestazione Jokic 25/11): senza data l'ultima partita.")
            return
        trovati = G.cerca(testo)
        if not trovati:
            await msg.reply_text(f"Nessun giocatore si chiama «{testo}».")
            return
        if len(trovati) > 1 and L.norm(trovati[0]["nome_common"]) != L.norm(G.PN_senza(testo)):
            from shared import pagine as PG
            g = f"{giorno:%Y%m%d}" if giorno else "0"
            await PG.manda(msg, context, [(x["nome_common"] + (" ✅" if x["a_roster"] else ""), f"pre:{x['id']}:{g}") for x in trovati])
            return
        await manda(msg, trovati[0]["id"], giorno)

    async def cb_prestazione(update, context):
        q = update.callback_query
        await q.answer()
        _, gid, g = q.data.split(":")
        giorno = None if g == "0" else datetime.strptime(g, "%Y%m%d").date()
        await manda(q.message, int(gid), giorno)

    return cmd_prestazione, cb_prestazione

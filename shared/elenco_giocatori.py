"""
/giocatori [filtri] (v7.5.0, Luca 10/11): la ricerca libera tra i giocatori, coi filtri che si combinano. Per ognuno
nome, squadra NBA, fantamedia (con le partite e le ultime 5) e la situazione nel fantabasket (contratto, diritti o FA).
In loucabot (gruppi e privato) e nel bot principale (solo in privato), come /player. /lista_fa del bot aste resta a sé.

Filtri, in qualsiasi ordine (`/giocatori aiuto` li elenca):
- PG SG SF PF C (anche G = PG o SG, F = SF o PF) scritti da soli, o `ruolo:G,C`: le posizioni eleggibili
  (l'ultima rilevazione: in off-season quelle della stagione prima);
- `fa` / `firmati` / `diritti` / `tutti` da soli, o `stato:`; `rookie` i firmati col contratto rookie (v7.9.2, `-rookie` gli altri);
- `nba:LAL,BOS` la squadra NBA di adesso (roster ESPN), `nba:no` senza squadra;
- `squadra:` squadra del fantabasket (contratto o diritti), come negli altri comandi; `ruolo_squadra:C` il ruolo
  ufficiale della stagione dei firmati;
- `nome:REGEX` (espressione regolare, maiuscole e accenti indifferenti); le parole scritte da sole cercano nel nome;
- `anno:2024` (2024-25) la media di una stagione passata, da Basketball-Reference; senza, la stagione in corso dai
  tabellini ESPN (Basketball-Reference per chi non è abbinato a ESPN);
- `media:30+` (almeno 30), `media:20-` (al massimo 20), anche insieme: `media:20+ and media:30-` (tra 20 e 30); vale
  anche `media:>=30` o `media:20-30` (v7.27.0, Luca 23/11). «and» tra i filtri si può scrivere, ma non serve:
  dentro un gruppo i filtri sono già tutti insieme.
- `top:N`, `min_g:N`, `costo:<10` / `costo:5-10`, `anni:1` / `anni:>=2`, `infortunati:no|si`,
  `ordina:media|costo|partite|ultime5|minuti|nome`, con `+` in fondo crescente e `-` decrescente (il default; v7.42.0).
Senza `anno:` ci sono i firmati e i diritti sempre e i FA con la regola della lista FA (v7.9.6: chi ha giocato
nella stagione in corso o, fino allo switch del 70% dei firmati, in quella prima; shared/lista_fa.py); con `anno:` solo chi ha giocato quella
stagione (il contratto è sempre quello di oggi). La risposta (v7.5.0, Luca 10/11): un'immagine sul viola di Yahoo
come /partita (elenco_giocatori.typ, 25 giocatori con la foto ESPN), un album se sono di più (fino a 10 immagini),
e sotto sempre il file .md con tutti.
"""
import html
import io
import re
import shlex

from shared import lettura as L
from shared.numeri import ottavi, testo as tp
from shared import non_ufficiale as NU          # v7.41.0: in klra i fantapunti del sistema

RUOLI = ("PG", "SG", "SF", "PF", "C")
GRUPPI = {"G": ("PG", "SG"), "F": ("SF", "PF")}
STATI = ("fa", "firmati", "diritti", "tutti")
ORDINI = ("media", "costo", "partite", "ultime5", "minuti", "nome")
TIPI = (2, 5)                    # regular season e play-in, come /player
ULTIME = 5
PER_IMMAGINE = 25                # giocatori in un'immagine
MAX_IMMAGINI = 10                # un album di Telegram: oltre, i giocatori sono solo nel file
MAX_REGEX = 100

AIUTO = ("<b>/giocatori</b> [filtri] — cerca tra i giocatori; i filtri si combinano, in qualsiasi ordine:\n"
         "• <code>PG SG SF PF C</code> (o <code>G</code>, <code>F</code>) — posizioni eleggibili, anche <code>ruolo:G,C</code>\n"
         "• <code>fa</code> · <code>firmati</code> · <code>diritti</code> · <code>tutti</code> — situazione nel fantabasket\n"
         "• <code>rookie</code> — i firmati col contratto rookie (<code>-rookie</code> gli altri)\n"
         "Più valori dello stesso filtro valgono in «o» (<code>fa firmati</code>, <code>nba:LAL,BOS</code>, <code>squadra:§A§,§B§</code>), "
         "filtri diversi in «e».\n"
         "• <code>nba:LAL</code> (anche <code>nba:LAL,BOS</code>, <code>nba:no</code>) — squadra NBA\n"
         "• <code>squadra:NOME</code> — squadra del fantabasket · <code>ruolo_squadra:C</code> — ruolo ufficiale dei firmati\n"
         "• <code>nome:REGEX</code> — nome con un'espressione regolare (<code>nome:^jal</code>); le parole da sole cercano nel nome\n"
         "• <code>anno:2024</code> — la media del 2024-25 (Basketball-Reference); senza, la stagione in corso\n"
         "• <code>media:30+</code> (almeno 30) · <code>media:20-</code> (al massimo 20) · <code>media:20+ and media:30-</code> (tra 20 e 30)\n"
         "• <code>minuti:25+</code> (almeno 25 minuti a partita) · <code>minuti:15-</code> · <code>minuti:20-30</code>\n"
         "• <code>top:20</code> · <code>min_g:10</code> · <code>costo:&lt;10</code> · <code>costo:5-10</code> · <code>anni:1</code> · <code>infortunati:no</code>\n"
         "• <code>ordina:media</code> (o costo, partite, ultime5, minuti, nome), dal più alto; <code>ordina:costo+</code> dal più basso\n"
         "• <code>watch</code> — i giocatori della tua watchlist (solo in privato)\n"
         "• <code>-</code> davanti nega un filtro: <code>-C</code>, <code>-nba:LAL</code>, <code>-firmati</code>\n"
         "• <code>|</code> (o <code>oppure</code>) separa gruppi alternativi: <code>C fa | PF diritti</code>\n"
         "Con spazi nel valore, tra virgolette: <code>squadra:\"Los Tizi\"</code>. Es. <code>/giocatori fa C top:10 min_g:5</code>")


class Errore(ValueError):
    """Un filtro scritto male: il messaggio va a chi ha scritto il comando."""


def e(x) -> str:
    return html.escape(str(x), quote=False)


def lbl(anno: int) -> str:
    return f"{anno}-{str(anno + 1)[-2:]}"


# ── i filtri ──────────────────────────────────────────────────────────────────

def _numero(chiave: str, v: str) -> int:
    if not v.isdigit():
        raise Errore(f"«{chiave}:{v}»: serve un numero.")
    return int(v)


def _confronto(chiave: str, v: str):
    """«10» · «<10» · «<=10» · «>5» · «>=5» · «5-10» → funzione sul numero."""
    v = v.replace(",", ".")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", v)
    if m:
        a, b = float(m[1]), float(m[2])
        return lambda x: a <= x <= b
    m = re.fullmatch(r"(<=|>=|<|>|=)?(\d+(?:\.\d+)?)", v)
    if not m:
        raise Errore(f"«{chiave}:{v}»: scrivi un numero, <N, >N, <=N, >=N o DA-A.")
    op, n = m[1] or "=", float(m[2])
    return {"<": lambda x: x < n, "<=": lambda x: x <= n, ">": lambda x: x > n, ">=": lambda x: x >= n,
            "=": lambda x: x == n}[op]


def _media(chiave: str, v: str, nome: str = "media"):
    """v7.27.0 (Luca, 23/11): «30+» almeno 30, «20-» al massimo 20; se no come costo (>=30, 20-30…).
    (funzione, testo per l'intestazione). v7.41.0: anche per i minuti (nome «min»)."""
    w = v.replace(",", ".").strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([+-])", w)
    if m:
        n = float(m[1])
        return (lambda x: x >= n, f"{nome} ≥ {m[1]}") if m[2] == "+" else (lambda x: x <= n, f"{nome} ≤ {m[1]}")
    return _confronto(chiave, w), f"{nome} {v}"


def _ruoli(chiave: str, v: str) -> set:
    out = set()
    for r in filter(None, re.split(r"[,/+]", v.upper())):
        if r in RUOLI:
            out.add(r)
        elif r in GRUPPI:
            out |= set(GRUPPI[r])
        else:
            raise Errore(f"«{chiave}:{v}»: i ruoli sono PG, SG, SF, PF, C (e G, F).")
    return out


def _stati(v: str, scritto: str | None = None) -> set:
    """«fa» · «fa,firmati» · «tutti» (= nessun filtro: tutti e tre)."""
    out = set()
    for x in filter(None, v.lower().split(",")):
        if x not in STATI:
            raise Errore(f"«{scritto or v}»: lo stato è fa, firmati, diritti o tutti.")
        out |= {"fa", "firmati", "diritti"} if x == "tutti" else {x}
    return out


def leggi(testo: str, oggi: int) -> dict:
    """I filtri dal testo dopo il comando. `oggi` = la stagione della lega (anno di inizio).
    v7.8.0 (Luca, 14/11): `|` (o «oppure») separa gruppi alternativi, in «o»; dentro un gruppo i filtri in «e»;
    un `-` davanti nega un filtro (`-C`, `-nba:LAL`, `-firmati`). Le opzioni (anno, top, ordina) valgono per tutti.
    Il risultato: i filtri del primo gruppo (come prima) più "gruppi" (tutti, ognuno con le sue negazioni "neg")."""
    try:
        parti = shlex.split(testo or "")
    except ValueError:                                  # virgolette non chiuse
        parti = (testo or "").split()
    glob = {"anno": oggi, "top": None, "ordina": "media", "verso": "", "aiuto": False}
    blocchi, cur = [], []
    for p in parti:
        if p in ("|", "||") or p.lower() == "oppure":
            blocchi.append(cur)
            cur = []
        else:
            cur.append(p)
    blocchi.append(cur)
    if len(blocchi) > 1 and not all(blocchi):
        raise Errore("Un «|» (oppure) va tra due gruppi di filtri, es. /giocatori C fa | PF diritti.")
    gruppi = []
    for b in blocchi:
        g = _gruppo([p for p in b if not (p.startswith("-") and len(p) > 1)], oggi, glob)
        for p in b:
            if p.startswith("-") and len(p) > 1:
                n = _gruppo([p[1:]], oggi, glob)
                if not _ha_condizioni(n):
                    raise Errore(f"«{p}»: si nega un filtro (es. -C, -fa, -nba:LAL, -nome:^jal).")
                g["neg"].append(n)
        gruppi.append(g)
    return {**gruppi[0], **glob, "gruppi": gruppi}


def _vuoto() -> dict:
    # dentro lo stesso filtro le condizioni sono in «o» (fa firmati, nba:LAL,BOS, squadra:A,B), tra filtri
    # diversi in «e» (v7.5.2, Luca 10/11); un insieme vuoto = nessun filtro
    return {"ruoli": set(), "stato": set(), "nba": set(), "squadra": [], "ruolo_squadra": set(), "regex": None,
            "parole": [], "min_g": None, "costo": None, "anni": None, "infortunati": None, "watch": False, "rookie": False, "neg": [],
            "media": [], "minuti": []}


def _ha_condizioni(g: dict) -> bool:
    return any(g[k] for k in ("ruoli", "stato", "nba", "squadra", "ruolo_squadra", "regex", "parole", "min_g", "costo",
                              "anni", "watch", "rookie", "media", "minuti")) or g["infortunati"] is not None


def _gruppo(parti: list[str], oggi: int, glob: dict) -> dict:
    """Un gruppo di filtri in «e». Le opzioni che valgono per tutti (anno, top, ordina, aiuto) vanno in glob."""
    f = _vuoto()
    for p in parti:
        k, sep, v = p.partition(":")
        k = k.lower()
        if not sep:
            up = p.upper()
            if p.lower() in ("and", "&", "&&"):            # v7.27.0: «and» tra due filtri (sono già in «e»)
                continue
            if p.lower() in ("aiuto", "help", "?"):
                glob["aiuto"] = True
            elif p.lower() in ("watch", "watchlist", "seguiti"):
                f["watch"] = True                        # la watchlist di chi scrive (v7.8.0), solo in privato
            elif p.lower() in ("rookie", "rookies"):
                f["rookie"] = True                       # contratto rookie (v7.9.2, Luca 14/11: solo i firmati)
            elif up in RUOLI or up in GRUPPI:
                f["ruoli"] |= _ruoli("ruolo", up)
            elif p.lower() in STATI:
                f["stato"] |= _stati(p)
            else:
                f["parole"].append(p)
            continue
        if not v:
            raise Errore(f"«{p}»: manca il valore dopo i due punti.")
        if k in ("ruolo", "ruoli", "pos"):
            f["ruoli"] |= _ruoli(k, v)
        elif k == "stato":
            f["stato"] |= _stati(v, p)
        elif k == "nba":
            f["nba"] |= {x.upper() for x in v.split(",") if x}
        elif k in ("squadra", "team"):
            from shared.squadre import cerca_squadra
            for nome_sq in filter(None, (x.strip() for x in v.split(","))):
                t = cerca_squadra(nome_sq, L.squadre())
                if not t:
                    raise Errore(f"Nessuna squadra trovata con «{nome_sq}».")
                if t["id"] not in [x["id"] for x in f["squadra"]]:
                    f["squadra"].append(t)
        elif k == "ruolo_squadra":
            f["ruolo_squadra"] |= _ruoli(k, v)
        elif k == "nome":
            if len(v) > MAX_REGEX:
                raise Errore(f"«nome:»: al massimo {MAX_REGEX} caratteri.")
            try:
                f["regex"] = re.compile(v, re.IGNORECASE)
            except re.error as err:
                raise Errore(f"«nome:{v}»: espressione regolare non valida ({err}).")
        elif k == "anno":
            m = re.fullmatch(r"(\d{4})(?:-\d{2,4})?", v)
            if not m or not 1979 <= int(m[1]) <= oggi:
                raise Errore(f"«{p}»: l'anno è quello di inizio della stagione, dal 1979 al {oggi} (2024 = 2024-25).")
            glob["anno"] = int(m[1])
        elif k == "top":
            glob["top"] = _numero(k, v) or None
        elif k in ("min_g", "ming", "partite"):
            f["min_g"] = _numero(k, v)
        elif k in ("costo", "importo"):
            f["costo"] = _confronto(k, v)
        elif k in ("media", "fantamedia", "fm"):
            f["media"].append(_media(k, v))
        elif k in ("minuti", "min", "minutaggio"):          # v7.41.0 (Luca, 28/11): i minuti a partita
            f["minuti"].append(_media(k, v, "min"))
        elif k == "anni":
            f["anni"] = _confronto(k, v)
        elif k in ("infortunati", "infortunato"):
            if v.lower() not in ("no", "si", "sì"):
                raise Errore(f"«{p}»: infortunati:no o infortunati:si.")
            f["infortunati"] = v.lower() != "no"
        elif k == "ordina":                              # v7.42.0 (Luca, 28/11): + crescente, - decrescente (il default)
            w = v.lower().strip()
            verso = w[-1] if w[-1:] in ("+", "-") else ""
            w = w.rstrip("+-")
            if w not in ORDINI:
                raise Errore(f"«{p}»: si ordina per {', '.join(ORDINI)}, con + (crescente) o - (decrescente) in fondo.")
            glob["ordina"], glob["verso"] = w, verso
        else:
            raise Errore(f"Filtro sconosciuto: «{k}:». /giocatori aiuto per l'elenco.")
    return f


def descrizione(f: dict, oggi: int) -> str:
    """I filtri in breve, per l'intestazione: i gruppi separati da « | », le negazioni con «non»."""
    pezzi = []
    for g in f.get("gruppi") or [f]:
        t = " · ".join(x for x in [_descr_gruppo(g)] + [f"non {_descr_gruppo(n)}" for n in g.get("neg", [])] if x)
        if t:
            pezzi.append(t)
    d = [" | ".join(pezzi)] if pezzi else []
    o = f["ordina"] + (" crescente" if crescente(f) and f["ordina"] != "nome" else " Z-A" if not crescente(f) and f["ordina"] == "nome" else "")
    if f["top"]:
        d.append(f"top {f['top']} per {o}")
    elif o != "media":
        d.append(f"per {o}")
    return " · ".join(d)


def crescente(f: dict) -> bool:
    """v7.42.0: l'ordine. Senza segno decrescente (il nome dalla A alla Z), «+» crescente, «-» decrescente."""
    v = f.get("verso") or ""
    return v == "+" or (not v and f["ordina"] == "nome")


def _descr_gruppo(f: dict) -> str:
    d = []
    if f.get("watch"):
        d.append("watchlist")
    if f.get("rookie"):
        d.append("rookie")
    if f["ruoli"]:
        d.append("/".join(r for r in RUOLI if r in f["ruoli"]))
    if f["stato"] and len(f["stato"]) < 3:
        d.append(" o ".join({"fa": "FA", "firmati": "firmati", "diritti": "diritti"}[s] for s in ("firmati", "diritti", "fa") if s in f["stato"]))
    if f["nba"]:
        d.append(" o ".join(("senza squadra NBA" if x == "NO" else "NBA " + x) for x in sorted(f["nba"])))
    if f["squadra"]:
        d.append(" o ".join(L.nome(t["id"]) for t in f["squadra"]))
    if f["ruolo_squadra"]:
        d.append("ruolo " + "/".join(r for r in RUOLI if r in f["ruolo_squadra"]))
    if f["regex"]:
        d.append(f"nome ~ {f['regex'].pattern}")
    if f["parole"]:
        d.append("nome «" + " ".join(f["parole"]) + "»")
    if f["min_g"]:
        d.append(f"almeno {f['min_g']} G")
    if f.get("media"):
        d.append(" e ".join(t for _, t in f["media"]))
    if f.get("minuti"):
        d.append(" e ".join(t for _, t in f["minuti"]))
    if f["costo"]:
        d.append("costo filtrato")
    if f["anni"]:
        d.append("anni filtrati")
    if f["infortunati"] is not None:
        d.append("solo infortunati" if f["infortunati"] else "senza infortunati")
    return " · ".join(d)


# ── i dati ────────────────────────────────────────────────────────────────────

def _q(sql, params=None):
    try:
        return L.q(sql, params, many=True) or []
    except Exception:                       # tabella che manca (prove, database vuoto)
        return []


def dati(anno: int, oggi: int) -> list[dict]:
    """Tutti i giocatori dell'anagrafica con la situazione di oggi e la media della stagione `anno`."""
    s = str(oggi)
    gioc = L.q("SELECT id, nome_common, nome_bref, espn_id FROM giocatori", many=True) or []
    contr = {r["giocatore_id"]: r for r in _q(
        """SELECT c.giocatore_id, c.team_id, c.importo, c.anni_originali, c.stagione_firma, c.tipo,
                  (SELECT r.ruolo FROM ruolo_attuale r WHERE r.giocatore_id = c.giocatore_id AND r.stagione = %s LIMIT 1) AS ruolo
           FROM contratti c WHERE c.attivo""", (s,))}
    dir_ = {r["giocatore_id"]: r["team_id"] for r in _q(
        "SELECT DISTINCT ON (giocatore_id) giocatore_id, team_id FROM rookie WHERE NOT firmato AND NOT diritti_scaduti "
        "ORDER BY giocatore_id, id DESC")}
    pos = {r["giocatore_id"]: [x for x in RUOLI if x in set((r["posizioni"] or "").split(","))]
           for r in _q("SELECT giocatore_id, posizioni FROM posizioni_attuali")}
    nba = {r["atleta"]: r["squadra"] for r in _q("SELECT atleta, squadra FROM nba_atleti WHERE squadra IS NOT NULL")}
    inf = {r["atleta"]: r["stato"] for r in _q(
        "SELECT atleta, stato FROM nba_infortuni WHERE preso = (SELECT MAX(preso) FROM nba_infortuni)")}

    # la stagione di Basketball-Reference (2024 → «2025»): la riga più recente di quella stagione
    bref = {r["n"]: r for r in _q(
        """SELECT DISTINCT ON (lower(nome_bref)) lower(nome_bref) AS n, * FROM bref_stats
           WHERE stagione = %s AND fantamedia IS NOT NULL ORDER BY lower(nome_bref), timestamp DESC, id DESC""",
        (str(anno + 1),))}
    # v7.9.6 (Luca, 15/11): i FA come nella lista FA (shared/lista_fa.py): chi ha giocato nella stagione in corso o,
    # prima dello switch del 70%, in quella prima; gli altri FA non ci sono
    recenti = set()
    if anno == oggi:
        from shared import lista_fa as LF
        recenti = {r["n"] for r in _q("SELECT DISTINCT lower(nome_bref) AS n FROM bref_stats WHERE stagione = ANY(%s)",
                                      (list(LF.stagioni_valide(L.q, s)),))}
    espn, minuti = {}, {}
    if anno == oggi:                        # la stagione in corso: i tabellini ESPN, come /player
        for r in _q("""SELECT t.* FROM nba_tabellini t
                       JOIN nba_partite p ON p.espn_id = t.partita
                       WHERE p.stagione = %s AND p.tipo = ANY(%s) ORDER BY p.inizio""", (s, list(TIPI))):
            if L.conta(r):
                espn.setdefault(r["atleta"], []).append(NU.fp(r))      # v7.41.0: in klra col sistema
                minuti.setdefault(r["atleta"], []).append(float(r["minuti"] or 0))

    out = []
    for g in gioc:
        a, c = g["espn_id"], contr.get(g["id"])
        x = {"id": g["id"], "nome": g["nome_common"], "atleta": a, "nba": nba.get(a) if a else None, "pos": pos.get(g["id"], []),
             "inf": inf.get(a) if a else None, "contratto": c, "diritti": None if c else dir_.get(g["id"]),
             "media": None, "g": 0, "ult5": None, "fonte": None, "minuti": None,
             "recente": bool(g.get("nome_bref") and g["nome_bref"].lower() in recenti)}
        if c:
            x["anni"] = int(c["anni_originali"]) - (oggi - int(c["stagione_firma"]))
        fp = espn.get(a) if a else None
        if fp:
            x.update(media=ottavi(sum(fp) / len(fp)), g=len(fp), fonte="espn",
                     ult5=ottavi(sum(fp[-ULTIME:]) / ULTIME) if len(fp) > ULTIME else None,
                     minuti=round(sum(minuti[a]) / len(minuti[a]), 1))
        elif (anno != oggi or not a) and g.get("nome_bref") and (g["nome_bref"].lower() in bref):
            b = bref[g["nome_bref"].lower()]
            x.update(media=NU.fm_bref(b), g=int(b["g"] or 0), fonte="bref",
                     minuti=float(b["mp"]) if b.get("mp") is not None else None)
        out.append(x)
    return out


def stato(x: dict) -> str:
    return "firmati" if x["contratto"] else "diritti" if x["diritti"] else "fa"


def filtra(righe: list[dict], f: dict, oggi: int, seguiti: set | None = None) -> list[dict]:
    """Chi passa almeno un gruppo (e nessuna delle sue negazioni). `seguiti`: gli id della watchlist di chi scrive."""
    out = []
    tutti_seguiti = usa_watch(f)
    for x in righe:
        if f["anno"] != oggi or stato(x) == "fa":
            # chi non ha giocato: solo i firmati e i diritti, nella stagione in corso; e tutti quelli della watchlist.
            # v7.9.6: i FA della stagione in corso come nella lista FA, cioè anche chi ha giocato la stagione prima
            # (fino allo switch del 70%), ma nessuno che non gioca da più di una stagione
            seguito = tutti_seguiti and x["id"] in (seguiti or set())
            if f["anno"] == oggi and stato(x) == "fa":
                if not (x.get("recente") or x["media"] is not None and x["fonte"] == "espn" or seguito):
                    continue
            elif x["media"] is None and not seguito:
                continue
        if any(_passa(x, g, seguiti or set()) and not any(_passa(x, n, seguiti or set()) for n in g["neg"])
               for g in f.get("gruppi") or [f]):
            out.append(x)
    return _ordina(out, f)


def _passa(x: dict, f: dict, seguiti: set) -> bool:
    """x rispetta tutti i filtri del gruppo f."""
    parole = [L.norm(p) for p in f["parole"]]
    st = stato(x)
    for _ in (0,):
        if f.get("watch") and x["id"] not in seguiti:
            continue
        if f["stato"] and st not in f["stato"]:
            continue
        if f.get("rookie") and not (x["contratto"] and x["contratto"].get("tipo") == "rookie"):
            continue
        if f["ruoli"] and not f["ruoli"] & set(x["pos"]):
            continue
        if f["nba"] and (x["nba"] or "NO").upper() not in f["nba"]:      # «no» = senza squadra NBA
            continue
        if f["squadra"]:
            tid = x["contratto"]["team_id"] if x["contratto"] else x["diritti"]
            if tid not in [t["id"] for t in f["squadra"]]:
                continue
        if f["ruolo_squadra"] and not (x["contratto"] and x["contratto"].get("ruolo") in f["ruolo_squadra"]):
            continue
        if f["regex"] and not (f["regex"].search(x["nome"]) or f["regex"].search(_senza_accenti(x["nome"]))):
            continue
        if parole and not all(p in L.norm(x["nome"]) for p in parole):
            continue
        if f["min_g"] and x["g"] < f["min_g"]:
            continue
        if f.get("media") and not (x["media"] is not None and all(fn(float(x["media"])) for fn, _ in f["media"])):
            continue
        if f.get("minuti") and not (x.get("minuti") is not None and all(fn(float(x["minuti"])) for fn, _ in f["minuti"])):
            continue
        if f["costo"] and not (x["contratto"] and f["costo"](float(x["contratto"]["importo"]))):
            continue
        if f["anni"] and not (x["contratto"] and f["anni"](float(x["anni"]))):
            continue
        if f["infortunati"] is not None and bool(x["inf"]) != f["infortunati"]:
            continue
        return True
    return False


def _ordina(out: list[dict], f: dict) -> list[dict]:
    """v7.42.0: crescente o decrescente (crescente()); chi non ha il valore resta comunque in fondo, a pari il nome."""
    valore = {"media": lambda x: x["media"],
              "costo": lambda x: float((x["contratto"] or {}).get("importo") or 0) if x["contratto"] else None,
              "partite": lambda x: x["g"],
              "ultime5": lambda x: x["ult5"] if x["ult5"] is not None else x["media"],
              "minuti": lambda x: x.get("minuti")}
    if f["ordina"] == "nome":
        out.sort(key=lambda x: x["nome"], reverse=not crescente(f))
    else:
        su = 1 if crescente(f) else -1
        v = valore[f["ordina"]]
        sec = (lambda x: su * (x["media"] or 0)) if f["ordina"] == "partite" else (lambda x: 0)
        out.sort(key=lambda x: (v(x) is None, su * (v(x) or 0), sec(x), x["nome"]))
    return out[:f["top"]] if f["top"] else out


def _senza_accenti(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


# ── l'immagine e il file ──────────────────────────────────────────────────────

def contratto_breve(x: dict) -> str:
    """Il contratto senza la squadra: «30M × 3 anni (rookie) · ruolo C»."""
    c = x["contratto"]
    if not c:
        return ""
    if c["tipo"] == "10day":
        t = f"{c['importo']}M · 10-day"
    elif x["anni"] <= 0:
        t = f"{c['importo']}M · x0"
    else:
        t = f"{c['importo']}M × {x['anni']} {'anno' if x['anni'] == 1 else 'anni'}"
    if c["tipo"] == "rookie":
        t += " (rookie)"
    if c.get("ruolo"):
        t += f" · ruolo {c['ruolo']}"
    return t


def situazione(x: dict) -> str:
    """La situazione nel fantabasket in una riga, per il file: «Squadra · 30M × 3 anni», «diritti di Squadra», «FA»."""
    if x["contratto"]:
        return f"{L.nome(x['contratto']['team_id'])} · {contratto_breve(x)}"
    if x["diritti"]:
        return f"diritti di {L.nome(x['diritti'])}"
    return "FA"


def media_txt(x: dict) -> str:
    return tp(x["media"]) if x["media"] is not None else "—"


def _colore(team_id: str) -> str:
    from shared.rendimento import colore_squadra                 # come i tondi di /rendimento
    return colore_squadra(L.squadra(team_id) or {"id": team_id})


def riga_immagine(n: int, x: dict) -> dict:
    sotto = []
    if x["media"] is not None:
        sotto.append(f"{x['g']} G")
    if x["ult5"] is not None:
        sotto.append(f"ult. 5: {tp(x['ult5'])}")
    tid = (x["contratto"] or {}).get("team_id") or x["diritti"]
    f = L.foto(x["atleta"]) if x["atleta"] else None
    return {"n": n, "nome": x["nome"], "foto": f and __import__("os").path.abspath(f),
            "iniziali": "".join(p[0] for p in x["nome"].split()[:2]).upper(), "inf": x["inf"],
            "pos": ",".join(x["pos"]) or "posizioni non registrate", "dettagli": "", "nba": x["nba"] or "—",
            "media": media_txt(x), "sotto_media": " · ".join(sotto) or "non ha giocato",
            "stato": stato(x), "colore": _colore(tid) if tid else "#1B8A4B",
            "squadra": L.nome(tid) if x["contratto"] else f"diritti · {L.nome(tid)}" if tid else "FA",
            "contratto": contratto_breve(x) if x["contratto"] else "rookie non firmato" if tid else "libero"}


def fonte(f: dict, oggi: int) -> str:
    return ("Media: tabellini ESPN della stagione (regular season e play-in), all'ottavo; Basketball-Reference per chi non è su ESPN"
            if f["anno"] == oggi else f"Media: Basketball-Reference, stagione {lbl(f['anno'])}; squadra NBA e contratto di oggi") + \
           " · status: ultimo report infortuni · tutti i giocatori nel file .md"


def pagine_immagini(righe: list[dict], f: dict, oggi: int) -> list[dict]:
    """I dati delle immagini: PER_IMMAGINE giocatori l'una, al massimo MAX_IMMAGINI (un album)."""
    tot = len(righe)
    usate = righe[:PER_IMMAGINE * MAX_IMMAGINI]
    pagine = -(-len(usate) // PER_IMMAGINE)
    out = []
    for p in range(pagine):
        da = p * PER_IMMAGINE
        pezzo = usate[da:da + PER_IMMAGINE]
        out.append({"stagione": lbl(f["anno"]), "filtri": descrizione(f, oggi) or "tutti i giocatori", "tot": tot,
                    "da": da + 1, "a": da + len(pezzo), "pagina": p + 1, "pagine": pagine,
                    "righe": [riga_immagine(da + i + 1, x) for i, x in enumerate(pezzo)], "fonte": fonte(f, oggi)})
    return out


def immagine(d: dict) -> bytes:
    import json
    import os
    import typst
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "elenco_giocatori.typ")
    fonts = [x for x in ("/usr/share/fonts",) if os.path.isdir(x)]
    return typst.compile(tpl, root="/", format="png", ppi=170, font_paths=fonts,
                         sys_inputs={"dati": json.dumps(NU.marca(d), ensure_ascii=False)})


def markdown(righe: list[dict], f: dict, oggi: int) -> str:
    cella = lambda s: str(s).replace("|", "\\|")
    d = descrizione(f, oggi)
    out = [f"# Giocatori · {lbl(f['anno'])}", "", f"Filtri: {d or 'nessuno'} · {len(righe)} giocatori", "",
           "| # | Giocatore | NBA | Pos. | Media | G | Ult. 5 | Fantabasket | Status |",
           "|---|-----------|-----|------|-------|---|--------|-------------|--------|"]
    for i, x in enumerate(righe, 1):
        out.append("| " + " | ".join(cella(v) for v in (
            i, x["nome"], x["nba"] or "—", ",".join(x["pos"]) or "—", media_txt(x), x["g"] if x["media"] is not None else "—",
            tp(x["ult5"]) if x["ult5"] is not None else "—", situazione(x), x["inf"] or "")) + " |")
    out += ["", fonte(f, oggi).replace(" · tutti i giocatori nel file .md", "") + "."]
    return "\n".join(out) + "\n"


def nome_file(f: dict, oggi: int) -> str:
    return ("giocatori_" + re.sub(r"[^a-z0-9]+", "_", (descrizione(f, oggi) or "tutti").lower()).strip("_")[:50]
            + f"_{lbl(f['anno'])}.md")


def usa_watch(f: dict) -> bool:
    return any(g.get("watch") or any(n.get("watch") for n in g["neg"]) for g in f.get("gruppi") or [f])


def _quota(t: str) -> str:
    if t and re.fullmatch(r"[^\s\"'\\]+", t):
        return t
    k, sep, v = t.partition(":")
    q = lambda x: '"' + x.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"{k}:{q(v)}" if sep and k and re.fullmatch(r"[\w-]+", k) else q(t)


def query(testo: str, comando: str = "giocatori") -> str:
    """v7.42.0 (Luca, 28/11): la ricerca riscritta pulita, da ricopiare per rifarla uguale (anche quella del builder)."""
    try:
        parti = shlex.split(testo or "")
    except ValueError:
        parti = (testo or "").split()
    return " ".join([f"/{comando}"] + [_quota(p) for p in parti])


def riga_query(testo: str) -> str:
    return f"🔁 <code>{e(query(testo))}</code>"


def risposta(testo: str, uid: int | None = None, privato: bool = True) -> dict:
    """{"testo": messaggio HTML (aiuto, errori, nessuno)} oppure
    {"pagine": [dati delle immagini], "didascalia", "md", "nome"}. uid e privato servono per `watch`."""
    oggi = int(L.stagione())
    try:
        f = leggi(testo, oggi)
    except Errore as err:
        return {"testo": f"⚠️ {e(err)}\n\n/giocatori aiuto per i filtri."}
    if f["aiuto"]:
        from shared import esempi as ES
        a, b = ES.due()
        return {"testo": AIUTO.replace("§A§", ES.filtro(a)).replace("§B§", ES.filtro(b))}
    seguiti = set()
    if usa_watch(f):
        if not privato or not uid:                      # la watchlist è privata: nessuno sa chi segue chi
            return {"testo": "👁 Il filtro <code>watch</code> funziona solo in privato: la watchlist è solo tua."}
        from shared import watchlist as W
        seguiti = W.seguiti(uid)
    righe = filtra(dati(f["anno"], oggi), f, oggi, seguiti)
    d = descrizione(f, oggi)
    if not righe:
        return {"testo": f"🏀 <b>Giocatori</b> · {lbl(f['anno'])}" + (f" · {e(d)}" if d else "") + "\n\nNessun giocatore con questi filtri."
                + "\n" + riga_query(testo)}
    pagine = pagine_immagini(righe, f, oggi)
    didascalia = f"🏀 Giocatori · {lbl(f['anno'])}" + (f" · {d}" if d else "") + f" · {len(righe)}"
    if len(righe) > PER_IMMAGINE * MAX_IMMAGINI:
        didascalia += f" (nelle immagini i primi {PER_IMMAGINE * MAX_IMMAGINI})"
    return {"pagine": pagine, "didascalia": didascalia[:1000], "md": markdown(righe, f, oggi), "nome": nome_file(f, oggi),
            "query": riga_query(testo)}


async def cmd_giocatori(update, context):
    import asyncio
    from telegram import InputMediaPhoto
    msg = update.effective_message
    testo = (msg.text or "").split(maxsplit=1)
    privato = getattr(getattr(update, "effective_chat", None), "type", "private") == "private"
    uid = getattr(getattr(update, "effective_user", None), "id", None)
    r = await asyncio.to_thread(risposta, testo[1] if len(testo) > 1 else "", uid, privato)
    await manda(msg, r)


async def manda(msg, r: dict) -> None:
    """La risposta di `risposta`: testo, o immagine (album oltre le 25) e sotto il file .md."""
    import asyncio
    from telegram import InputMediaPhoto
    if "testo" in r:
        await msg.reply_text(r["testo"], parse_mode="HTML", disable_notification=True)
        return
    png = [await asyncio.to_thread(immagine, p) for p in r["pagine"]]
    if len(png) == 1:
        await msg.reply_photo(photo=png[0], caption=r["didascalia"])
    else:
        await msg.reply_media_group([InputMediaPhoto(media=x, caption=r["didascalia"] if i == 0 else None)
                                     for i, x in enumerate(png)])
    # v7.42.0: sotto il file la ricerca da ricopiare (in un album la didascalia si perde, quella del file no)
    await msg.reply_document(document=io.BytesIO(r["md"].encode("utf-8")), filename=r["nome"],
                             caption=r.get("query"), parse_mode="HTML" if r.get("query") else None)

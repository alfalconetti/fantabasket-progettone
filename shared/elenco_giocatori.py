"""
/giocatori [filtri] (v7.5.0, Luca 10/11): la ricerca libera tra i giocatori, coi filtri che si combinano. Per ognuno
nome, squadra NBA, fantamedia (con le partite e le ultime 5) e la situazione nel fantabasket (contratto, diritti o FA).
In loucabot (gruppi e privato) e nel bot principale (solo in privato), come /player. /lista_fa del bot aste resta a sé.

Filtri, in qualsiasi ordine (`/giocatori aiuto` li elenca):
- PG SG SF PF C (anche G = PG o SG, F = SF o PF) scritti da soli, o `ruolo:G,C`: le posizioni eleggibili
  (l'ultima rilevazione: in off-season quelle della stagione prima);
- `fa` / `firmati` / `diritti` / `tutti` da soli, o `stato:`;
- `nba:LAL,BOS` la squadra NBA di adesso (roster ESPN), `nba:no` senza squadra;
- `squadra:` squadra del fantabasket (contratto o diritti), come negli altri comandi; `ruolo_squadra:C` il ruolo
  ufficiale della stagione dei firmati;
- `nome:REGEX` (espressione regolare, maiuscole e accenti indifferenti); le parole scritte da sole cercano nel nome;
- `anno:2024` (2024-25) la media di una stagione passata, da Basketball-Reference; senza, la stagione in corso dai
  tabellini ESPN (Basketball-Reference per chi non è abbinato a ESPN);
- `top:N`, `min_g:N`, `costo:<10` / `costo:5-10`, `anni:1` / `anni:>=2`, `infortunati:no|si`,
  `ordina:media|costo|partite|ultime5|nome`.
Senza `anno:` ci sono i firmati e i diritti sempre e i FA che hanno giocato; con `anno:` solo chi ha giocato quella
stagione (il contratto è sempre quello di oggi). Se non entra in un messaggio, i primi 10 e il file .md con tutti.
"""
import html
import io
import re
import shlex

from shared import lettura as L
from shared.numeri import ottavi, testo as tp

RUOLI = ("PG", "SG", "SF", "PF", "C")
GRUPPI = {"G": ("PG", "SG"), "F": ("SF", "PF")}
STATI = ("fa", "firmati", "diritti", "tutti")
ORDINI = ("media", "costo", "partite", "ultime5", "nome")
TIPI = (2, 5)                    # regular season e play-in, come /player
ULTIME = 5
MAX_MESSAGGIO = 3800             # Telegram ne accetta 4096: un po' di margine per l'intestazione
NEL_MESSAGGIO = 10               # quanti nel messaggio quando c'è il file
MAX_REGEX = 100

AIUTO = ("<b>/giocatori</b> [filtri] — cerca tra i giocatori; i filtri si combinano, in qualsiasi ordine:\n"
         "• <code>PG SG SF PF C</code> (o <code>G</code>, <code>F</code>) — posizioni eleggibili, anche <code>ruolo:G,C</code>\n"
         "• <code>fa</code> · <code>firmati</code> · <code>diritti</code> · <code>tutti</code> — situazione nel fantabasket\n"
         "• <code>nba:LAL</code> (anche <code>nba:LAL,BOS</code>, <code>nba:no</code>) — squadra NBA\n"
         "• <code>squadra:NOME</code> — squadra del fantabasket · <code>ruolo_squadra:C</code> — ruolo ufficiale dei firmati\n"
         "• <code>nome:REGEX</code> — nome con un'espressione regolare (<code>nome:^jal</code>); le parole da sole cercano nel nome\n"
         "• <code>anno:2024</code> — la media del 2024-25 (Basketball-Reference); senza, la stagione in corso\n"
         "• <code>top:20</code> · <code>min_g:10</code> · <code>costo:&lt;10</code> · <code>costo:5-10</code> · <code>anni:1</code> · <code>infortunati:no</code>\n"
         "• <code>ordina:media</code> (o costo, partite, ultime5, nome)\n"
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


def leggi(testo: str, oggi: int) -> dict:
    """I filtri dal testo dopo il comando. `oggi` = la stagione della lega (anno di inizio)."""
    try:
        parti = shlex.split(testo or "")
    except ValueError:                                  # virgolette non chiuse
        parti = (testo or "").split()
    f = {"ruoli": set(), "stato": "tutti", "nba": None, "squadra": None, "ruolo_squadra": set(), "regex": None,
         "parole": [], "anno": oggi, "top": None, "min_g": None, "costo": None, "anni": None, "infortunati": None,
         "ordina": "media", "aiuto": False, "descr": []}
    for p in parti:
        k, sep, v = p.partition(":")
        k = k.lower()
        if not sep:
            up = p.upper()
            if p.lower() in ("aiuto", "help", "?"):
                f["aiuto"] = True
            elif up in RUOLI or up in GRUPPI:
                f["ruoli"] |= _ruoli("ruolo", up)
            elif p.lower() in STATI:
                f["stato"] = p.lower()
            else:
                f["parole"].append(p)
            continue
        if not v:
            raise Errore(f"«{p}»: manca il valore dopo i due punti.")
        if k in ("ruolo", "ruoli", "pos"):
            f["ruoli"] |= _ruoli(k, v)
        elif k == "stato":
            if v.lower() not in STATI:
                raise Errore(f"«{p}»: lo stato è fa, firmati, diritti o tutti.")
            f["stato"] = v.lower()
        elif k == "nba":
            f["nba"] = {"no"} if v.lower() == "no" else {x.upper() for x in v.split(",") if x}
        elif k in ("squadra", "team"):
            from shared.squadre import cerca_squadra
            t = cerca_squadra(v, L.squadre())
            if not t:
                raise Errore(f"Nessuna squadra trovata con «{v}».")
            f["squadra"] = t
        elif k == "ruolo_squadra":
            f["ruolo_squadra"] = _ruoli(k, v)
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
            f["anno"] = int(m[1])
        elif k == "top":
            f["top"] = _numero(k, v) or None
        elif k in ("min_g", "ming", "partite"):
            f["min_g"] = _numero(k, v)
        elif k in ("costo", "importo"):
            f["costo"] = _confronto(k, v)
        elif k == "anni":
            f["anni"] = _confronto(k, v)
        elif k in ("infortunati", "infortunato"):
            if v.lower() not in ("no", "si", "sì"):
                raise Errore(f"«{p}»: infortunati:no o infortunati:si.")
            f["infortunati"] = v.lower() != "no"
        elif k == "ordina":
            if v.lower() not in ORDINI:
                raise Errore(f"«{p}»: si ordina per {', '.join(ORDINI)}.")
            f["ordina"] = v.lower()
        else:
            raise Errore(f"Filtro sconosciuto: «{k}:». /giocatori aiuto per l'elenco.")
    return f


def descrizione(f: dict, oggi: int) -> str:
    """I filtri in breve, per l'intestazione."""
    d = []
    if f["ruoli"]:
        d.append("/".join(r for r in RUOLI if r in f["ruoli"]))
    if f["stato"] != "tutti":
        d.append({"fa": "FA", "firmati": "firmati", "diritti": "diritti"}[f["stato"]])
    if f["nba"]:
        d.append("senza squadra NBA" if f["nba"] == {"no"} else "NBA " + ",".join(sorted(f["nba"])))
    if f["squadra"]:
        d.append(L.nome(f["squadra"]["id"]))
    if f["ruolo_squadra"]:
        d.append("ruolo " + "/".join(r for r in RUOLI if r in f["ruolo_squadra"]))
    if f["regex"]:
        d.append(f"nome ~ {f['regex'].pattern}")
    if f["parole"]:
        d.append("nome «" + " ".join(f["parole"]) + "»")
    if f["min_g"]:
        d.append(f"almeno {f['min_g']} G")
    if f["costo"]:
        d.append("costo filtrato")
    if f["anni"]:
        d.append("anni filtrati")
    if f["infortunati"] is not None:
        d.append("solo infortunati" if f["infortunati"] else "senza infortunati")
    if f["top"]:
        d.append(f"top {f['top']} per {f['ordina']}")
    elif f["ordina"] != "media":
        d.append(f"per {f['ordina']}")
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
        """SELECT DISTINCT ON (lower(nome_bref)) lower(nome_bref) AS n, fantamedia, g FROM bref_stats
           WHERE stagione = %s AND fantamedia IS NOT NULL ORDER BY lower(nome_bref), timestamp DESC, id DESC""",
        (str(anno + 1),))}
    espn = {}
    if anno == oggi:                        # la stagione in corso: i tabellini ESPN, come /player
        for r in _q("""SELECT t.atleta, t.fp, t.giocato, t.minuti FROM nba_tabellini t
                       JOIN nba_partite p ON p.espn_id = t.partita
                       WHERE p.stagione = %s AND p.tipo = ANY(%s) ORDER BY p.inizio""", (s, list(TIPI))):
            if L.conta(r):
                espn.setdefault(r["atleta"], []).append(float(r["fp"]))

    out = []
    for g in gioc:
        a, c = g["espn_id"], contr.get(g["id"])
        x = {"id": g["id"], "nome": g["nome_common"], "nba": nba.get(a) if a else None, "pos": pos.get(g["id"], []),
             "inf": inf.get(a) if a else None, "contratto": c, "diritti": None if c else dir_.get(g["id"]),
             "media": None, "g": 0, "ult5": None, "fonte": None}
        if c:
            x["anni"] = int(c["anni_originali"]) - (oggi - int(c["stagione_firma"]))
        fp = espn.get(a) if a else None
        if fp:
            x.update(media=ottavi(sum(fp) / len(fp)), g=len(fp), fonte="espn",
                     ult5=ottavi(sum(fp[-ULTIME:]) / ULTIME) if len(fp) > ULTIME else None)
        elif (anno != oggi or not a) and g.get("nome_bref") and (g["nome_bref"].lower() in bref):
            b = bref[g["nome_bref"].lower()]
            x.update(media=float(b["fantamedia"]), g=int(b["g"] or 0), fonte="bref")
        out.append(x)
    return out


def stato(x: dict) -> str:
    return "firmati" if x["contratto"] else "diritti" if x["diritti"] else "fa"


def filtra(righe: list[dict], f: dict, oggi: int) -> list[dict]:
    parole = [L.norm(p) for p in f["parole"]]
    out = []
    for x in righe:
        st = stato(x)
        if f["anno"] != oggi or st == "fa":
            if x["media"] is None:          # chi non ha giocato: solo i firmati e i diritti, nella stagione in corso
                continue
        if f["stato"] != "tutti" and st != f["stato"]:
            continue
        if f["ruoli"] and not f["ruoli"] & set(x["pos"]):
            continue
        if f["nba"] is not None:
            if f["nba"] == {"no"}:
                if x["nba"]:
                    continue
            elif (x["nba"] or "").upper() not in f["nba"]:
                continue
        if f["squadra"]:
            tid = x["contratto"]["team_id"] if x["contratto"] else x["diritti"]
            if tid != f["squadra"]["id"]:
                continue
        if f["ruolo_squadra"] and not (x["contratto"] and x["contratto"].get("ruolo") in f["ruolo_squadra"]):
            continue
        if f["regex"] and not (f["regex"].search(x["nome"]) or f["regex"].search(_senza_accenti(x["nome"]))):
            continue
        if parole and not all(p in L.norm(x["nome"]) for p in parole):
            continue
        if f["min_g"] and x["g"] < f["min_g"]:
            continue
        if f["costo"] and not (x["contratto"] and f["costo"](float(x["contratto"]["importo"]))):
            continue
        if f["anni"] and not (x["contratto"] and f["anni"](float(x["anni"]))):
            continue
        if f["infortunati"] is not None and bool(x["inf"]) != f["infortunati"]:
            continue
        out.append(x)
    chiave = {"media": lambda x: (x["media"] is None, -(x["media"] or 0), x["nome"]),
              "costo": lambda x: (not x["contratto"], -float((x["contratto"] or {}).get("importo") or 0), x["nome"]),
              "partite": lambda x: (-x["g"], -(x["media"] or 0), x["nome"]),
              "ultime5": lambda x: (x["ult5"] is None and x["media"] is None, -(x["ult5"] if x["ult5"] is not None else (x["media"] or 0)), x["nome"]),
              "nome": lambda x: x["nome"]}[f["ordina"]]
    out.sort(key=chiave)
    return out[:f["top"]] if f["top"] else out


def _senza_accenti(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


# ── il testo ──────────────────────────────────────────────────────────────────

def contratto_breve(x: dict) -> str:
    c = x["contratto"]
    if c:
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
        return f"{L.nome(c['team_id'])} · {t}"
    if x["diritti"]:
        return f"diritti di {L.nome(x['diritti'])}"
    return "FA"


def media_txt(x: dict) -> str:
    return tp(x["media"]) if x["media"] is not None else "—"


def riga(n: int, x: dict) -> str:
    icona = "📝" if x["contratto"] else "🔒" if x["diritti"] else "🆓"
    dettagli = [f"{x['g']} G"] if x["media"] is not None else []
    if x["ult5"] is not None:
        dettagli.append(f"ult. 5: {tp(x['ult5'])}")
    testa = (f"{n}. <b>{e(x['nome'])}</b> · {e(x['nba'] or '—')} · <b>{media_txt(x)}</b>"
             + (f" ({', '.join(dettagli)})" if dettagli else "") + (f" · 🩹 {e(x['inf'])}" if x["inf"] else ""))
    return f"{testa}\n   {icona} {e(contratto_breve(x))}"


def intestazione(f: dict, oggi: int, quanti: int) -> str:
    d = descrizione(f, oggi)
    return f"🏀 <b>Giocatori</b> · {lbl(f['anno'])}" + (f" · {e(d)}" if d else "") + f" · {quanti}"


def markdown(righe: list[dict], f: dict, oggi: int) -> str:
    cella = lambda s: str(s).replace("|", "\\|")
    d = descrizione(f, oggi)
    out = [f"# Giocatori · {lbl(f['anno'])}", "", f"Filtri: {d or 'nessuno'} · {len(righe)} giocatori", "",
           "| # | Giocatore | NBA | Pos. | Media | G | Ult. 5 | Contratto | Status |",
           "|---|-----------|-----|------|-------|---|--------|-----------|--------|"]
    for i, x in enumerate(righe, 1):
        out.append("| " + " | ".join(cella(v) for v in (
            i, x["nome"], x["nba"] or "—", ",".join(x["pos"]) or "—", media_txt(x), x["g"] if x["media"] is not None else "—",
            tp(x["ult5"]) if x["ult5"] is not None else "—", contratto_breve(x), x["inf"] or "")) + " |")
    out += ["", "Media: tabellini ESPN della stagione in corso (regular season e play-in); stagioni passate e "
                "giocatori senza ESPN: Basketball-Reference."]
    return "\n".join(out) + "\n"


def risposta(testo: str) -> tuple[str, str | None, str | None]:
    """(messaggio HTML, contenuto del file .md o None, nome del file)."""
    oggi = int(L.stagione())
    try:
        f = leggi(testo, oggi)
    except Errore as err:
        return f"⚠️ {e(err)}\n\n/giocatori aiuto per i filtri.", None, None
    if f["aiuto"]:
        return AIUTO, None, None
    righe = filtra(dati(f["anno"], oggi), f, oggi)
    if not righe:
        return intestazione(f, oggi, 0) + "\n\nNessun giocatore con questi filtri.", None, None
    testa = intestazione(f, oggi, len(righe))
    corpo = [riga(i, x) for i, x in enumerate(righe, 1)]
    msg = testa + "\n\n" + "\n".join(corpo)
    if len(msg) <= MAX_MESSAGGIO:
        return msg, None, None
    nome = "giocatori_" + re.sub(r"[^a-z0-9]+", "_", (descrizione(f, oggi) or "tutti").lower()).strip("_")[:50] + f"_{lbl(f['anno'])}.md"
    return (testa + f"\n<i>i primi {NEL_MESSAGGIO} qui, tutti nel file</i>\n\n" + "\n".join(corpo[:NEL_MESSAGGIO]),
            markdown(righe, f, oggi), nome)


async def cmd_giocatori(update, context):
    msg = update.effective_message
    testo = (msg.text or "").split(maxsplit=1)
    testo = testo[1] if len(testo) > 1 else ""
    m, md, nome = risposta(testo)
    await msg.reply_text(m, parse_mode="HTML", disable_notification=True)
    if md:
        await msg.reply_document(document=io.BytesIO(md.encode("utf-8")), filename=nome)

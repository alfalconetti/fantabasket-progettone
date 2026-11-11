"""
/rendimento GIOCATORE e /rendimento_carriera GIOCATORE (v7.4.0, Luca 09/11, mockup approvato): in loucabot e nel
bot principale (lì solo in privato, come /player). Disegno in rendimento.typ, stile di /carriera.

/rendimento: la stagione in corso partita per partita dai tabellini ESPN, tutte le partite (regular season, play-in
e playoff; play-in e playoff accorpati, in fondo dorato, col rombo). Punti col colore della squadra del fantabasket in
cui era quel giorno (dal registro dei movimenti: l'ultimo movimento prima della palla a due; grigio se libero), × se
non ha giocato (o 0 con 0 minuti: non fa media, come in /player). Due linee: media delle ultime 5 e media dall'inizio
della stagione. Sotto, una fascia per ogni periodo in una squadra, con la sua media. In alto la media della stagione
come in /player (regular season e play-in), e quella dei playoff se ci sono.

/rendimento_carriera: una barra per stagione con la fantamedia di Basketball-Reference (regular season, l'ultima
istantanea di ogni stagione; chi ha cambiato squadra: la riga del totale e sotto tutte le squadre in ordine), la
stagione in corso dai tabellini ESPN (lo stesso numero di /player); il tondo della squadra del fantabasket (a fine
stagione, o adesso). Se il nome non è nell'anagrafica del bot cerca tra tutti i nomi di Basketball-Reference: anche
i giocatori storici (i dati partono dal 1979-80).
"""
import html
import json
import os
from datetime import date, datetime, timezone

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K

from shared import giocatore as G
from shared import lettura as L
from shared.numeri import ottavi, testo as tp

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rendimento.typ")
# /rendimento_carriera resta col disegno di prima (Luca, 11/11): il suo template a parte
TEMPLATE_CARRIERA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rendimento_carriera.typ")
TIPI_TUTTE = (2, 3, 5)           # regular season, playoff, play-in (la preseason no)
LIBERO = "#A7B0C0"


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _t(x: float) -> str:
    return tp(ottavi(x))


def _iniziali(nome: str) -> str:
    p = [x for x in (nome or "").split() if x[:1].isalpha()]
    return "".join(x[0] for x in p[:2]).upper() or "?"


def etichetta_stagione(s: int | str) -> str:
    """Basketball-Reference: «2025» è la 2024-25 → «24-25»."""
    s = int(s)
    return f"{(s - 1) % 100:02d}-{s % 100:02d}"


# ── squadre del fantabasket nel tempo ─────────────────────────────────────────

def movimenti(gid: int) -> list[dict]:
    """I movimenti del giocatore (vista movimenti_giocatori del registro), in ordine."""
    return L.q("""SELECT team_id_a, timestamp FROM movimenti_giocatori WHERE giocatore_id = %s
                  ORDER BY timestamp, id""", (gid,), many=True) or []


def squadra_al(mov: list[dict], quando) -> str | None:
    """La squadra del fantabasket a un istante: quella dell'ultimo movimento fino ad allora (None = libero)."""
    team = None
    for m in mov:
        if m["timestamp"] <= quando:
            team = m["team_id_a"]
        else:
            break
    return team


# senza un colore scelto con /palette (colore_header) ogni squadra ne prende uno di questi, sempre lo stesso (ordine di
# teams.json): così due squadre non hanno lo stesso blu di default
TAVOLOZZA = ["#7A1F2B", "#1F6E43", "#1F4E79", "#8E5A00", "#5B2C83", "#00695C", "#B23A48", "#2E7D32", "#283593", "#6D4C41",
             "#AD1457", "#00838F", "#9E6B00", "#455A64", "#4E342E", "#1565C0", "#827717", "#6A1B9A", "#C62828", "#2E4057",
             "#00796B", "#5D4037", "#3949AB", "#7B1FA2"]


def colore_squadra(t: dict) -> str:
    if t.get("colore_header") and L.colore(t) == t.get("colore_header"):
        return L.colore(t)
    ids = [x["id"] for x in L.squadre()]
    i = ids.index(t["id"]) if t.get("id") in ids else sum(map(ord, t.get("id", ""))) 
    return TAVOLOZZA[i % len(TAVOLOZZA)]


def _info_squadra(team_id: str | None) -> dict:
    if not team_id:
        return {"nome": "Libero", "colore": LIBERO, "logo": ""}
    t = L.squadra(team_id) or {"id": team_id, "nome": team_id}
    return {"nome": t.get("nome", team_id), "colore": colore_squadra(t), "logo": L.logo(team_id)}


def _testata(gid: int | None, nome: str) -> dict:
    """Foto, iniziali e la riga sotto il nome (squadra NBA, età, squadra del fantabasket e contratto)."""
    if gid is None:
        return {"nome": nome, "iniziali": _iniziali(nome), "foto": "", "sotto": "dati storici di Basketball-Reference · non è nel bot"}
    g = L.q("SELECT nome_common, espn_id, data_nascita FROM giocatori WHERE id = %s", (gid,), one=True) or {}
    pezzi = []
    if g.get("espn_id"):
        nba = L.squadre_roster([g["espn_id"]]).get(g["espn_id"])
        if nba:
            pezzi.append(nba)
    if g.get("data_nascita"):
        pezzi.append(f"{G.eta(g['data_nascita'])} anni")
    c = L.q("SELECT team_id, importo, anni_originali, stagione_firma FROM contratti WHERE giocatore_id = %s AND attivo LIMIT 1",
            (gid,), one=True)
    pezzi.append(f"{L.nome(c['team_id'])}, {tp(c['importo'])} × {c['anni_originali']}" if c else "free agent")
    return {"nome": g.get("nome_common") or nome, "iniziali": _iniziali(g.get("nome_common") or nome),
            "foto": L.foto(g.get("espn_id")) or "", "sotto": " · ".join(pezzi)}


# ── /rendimento: la stagione ──────────────────────────────────────────────────

MESI = ("", "gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")
MIN_PARTITE = 5          # sotto, /rendimento non disegna niente: troppo pochi dati (Luca, 11/11)

def partite(atleta: str, stagione: str) -> list[dict]:
    return L.q("""SELECT t.*, p.tipo, p.inizio, p.data_et, p.casa, p.trasferta FROM nba_tabellini t
                  JOIN nba_partite p ON p.espn_id = t.partita
                  WHERE t.atleta = %s AND p.stagione = %s AND p.tipo = ANY(%s) ORDER BY p.inizio""",
               (atleta, stagione, list(TIPI_TUTTE)), many=True) or []


def _asse(valori: list[float]) -> tuple[int, int, int]:
    alto = max([40.0] + [v + 4 for v in valori])          # spazio sopra per le etichette
    basso = min([0.0] + valori)
    hi = int(-(-alto // 10) * 10)
    lo = int((basso // 10) * 10)
    passo = 10 if hi - lo <= 70 else 20
    return lo, hi, passo


def dati_stagione(gid: int, stagione: str | None = None) -> dict | None:
    stagione = stagione or L.stagione()
    g = L.q("SELECT nome_common, espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    if not g or not g.get("espn_id"):
        return None
    tab = partite(g["espn_id"], stagione)
    if not tab:
        return None
    mov = movimenti(gid)
    out, contano, reg, post = [], [], [], []
    for r in tab:
        conta = L.conta(r)
        fp = float(r["fp"]) if conta else None
        sq = squadra_al(mov, r["inizio"])
        if fp is not None:
            contano.append(fp)
            (reg if r["tipo"] in G.TIPI else post).append(fp)
        avv = r["trasferta"] if r["squadra"] == r["casa"] else r["casa"]
        out.append({"fp": fp, "sq": sq or "_libero", "tipo": "rs" if r["tipo"] == 2 else "post", "media_player": r["tipo"] in G.TIPI,
                    "prog": round(sum(contano) / len(contano), 3) if fp is not None else None,
                    "mobile": round(sum(contano[-5:]) / 5, 3) if fp is not None and len(contano) >= 5 else None,
                    "data": r["data_et"], "avv": avv})
    n = len(out)
    passo = max(1, round(n / 8))
    for i, p in enumerate(out):
        giorno = p.pop("data")
        p["giorno"] = giorno.isoformat()                 # per /confronto: le partite dei due giocatori allineate per data
        p["data_lbl"] = f"{giorno:%d/%m}" if i % passo == 0 else ""
    # fasce: periodi consecutivi nella stessa squadra del fantabasket
    fasce = []
    for i, p in enumerate(out):
        if fasce and fasce[-1]["sq"] == p["sq"]:
            fasce[-1]["a"] = i
        else:
            fasce.append({"sq": p["sq"], "da": i, "a": i})
    for f in fasce:
        v = [p["fp"] for p in out[f["da"]:f["a"] + 1] if p["fp"] is not None]
        f["media"] = _t(sum(v) / len(v)) if v else "—"
        f["g"] = len(v)
    squadre = {s: _info_squadra(None if s == "_libero" else s) for s in {p["sq"] for p in out}}
    vals = [p["fp"] for p in out if p["fp"] is not None]
    lo, hi, passo_y = _asse(vals)
    bi = max((i for i, p in enumerate(out) if p["fp"] is not None), key=lambda i: out[i]["fp"], default=None)
    i_post = next((i for i, p in enumerate(out) if p["tipo"] == "post"), None)
    media = sum(reg) / len(reg) if reg else (sum(vals) / len(vals) if vals else 0.0)
    sotto = [f"{len(reg)} partite su {sum(1 for r in tab if r['tipo'] in G.TIPI)}"]
    if post or any(r["tipo"] == 3 for r in tab):
        sotto.append(f"playoff {_t(sum(post) / len(post)) if post else '—'} ({len(post)})")
    if bi is not None:
        sotto.append(f"migliore {_t(out[bi]['fp'])}")
    a = int(stagione)
    # v7.6.2 (Luca, 11/11): i riquadri della testata, i mesi sull'asse, la media della stagione tratteggiata
    giocate = [i for i, p in enumerate(out) if p["fp"] is not None]
    ult = [out[i]["fp"] for i in giocate[-5:]]
    u5 = sum(ult) / len(ult) if ult else 0.0
    wi = min(giocate, key=lambda i: out[i]["fp"], default=None)
    quando = lambda i: f"vs {out[i]['avv']} · {date.fromisoformat(out[i]['giorno']):%d/%m}"
    sotto_fm = sotto[0] + (f" · {sotto[1]}" if len(sotto) > 2 else "")
    riquadri = [{"t": "Fantamedia", "v": _t(media) if reg or vals else "—", "s": sotto_fm},
                {"t": "Ultime 5", "v": _t(u5) if ult else "—",
                 "s": ("▲ sopra la media" if u5 >= media else "▼ sotto la media") if ult else ""},
                {"t": "Migliore", "v": _t(out[bi]["fp"]) if bi is not None else "—", "s": quando(bi) if bi is not None else ""},
                {"t": "Peggiore", "v": _t(out[wi]["fp"]) if wi is not None else "—", "s": quando(wi) if wi is not None else ""}]
    mesi, prima = [], None
    for i, p in enumerate(out):
        m = p["giorno"][5:7]
        if m != prima:
            mesi.append({"i": i, "lbl": MESI[int(m)]})
            prima = m
    return {"modo": "stagione", **_testata(gid, g["nome_common"]),
            "riquadri": riquadri, "mesi": mesi, "media_val": ottavi(media), "giocate": len(giocate),
            "y_barre": max(40, int(-(-(max(vals, default=0) + 6) // 10) * 10)),
            "titolo": f"Stagione {a}-{(a + 1) % 100:02d}", "media_big": _t(media) if reg or vals else "—",
            "media_sotto": " · ".join(sotto), "partite": out, "squadre": squadre, "fasce": fasce,
            "y_min": lo, "y_max": hi, "y_passo": passo_y, "post": i_post,
            "migliore": ({"i": bi, "fp": out[bi]["fp"], "t": f"{_t(out[bi]['fp'])} vs {out[bi]['avv']}"} if bi is not None
                         else {"i": 0, "fp": 0, "t": ""})}


# ── /rendimento_carriera ───────────────────────────────────────────────────────

def stagioni_bref(nome_bref: str) -> list[dict]:
    """Per ogni stagione di Basketball-Reference: l'ultima istantanea di ogni riga (squadra o totale)."""
    righe = L.q("""SELECT DISTINCT ON (stagione, team) stagione, team, g, mp, fantamedia, id,
                          MIN(id) OVER (PARTITION BY stagione, team) AS primo
                   FROM bref_stats WHERE nome_bref = %s AND fantamedia IS NOT NULL ORDER BY stagione, team, timestamp DESC, id DESC""",
                (nome_bref,), many=True) or []
    per = {}
    for r in righe:
        per.setdefault(r["stagione"], []).append(r)
    out = []
    for s, rr in sorted(per.items(), key=lambda x: int(x[0])):
        tot = [r for r in rr if (r["team"] or "").upper() in ("TOT",) or (r["team"] or "").upper().endswith("TM")]
        squadre = sorted([r for r in rr if r not in tot], key=lambda r: r["primo"])
        base = tot[0] if tot else max(rr, key=lambda r: r["g"] or 0)
        out.append({"stagione": int(s), "g": int(base["g"] or 0), "mp": float(base["mp"] or 0),
                    "fm": float(base["fantamedia"] or 0), "teams": [r["team"] for r in squadre if r["team"]] or [base["team"] or ""]})
    return out


def _righe_squadre(teams: list[str]) -> list[str]:
    if len(teams) <= 2:
        return ["·".join(teams)]
    meta = (len(teams) + 1) // 2
    return ["·".join(teams[:meta]), "·".join(teams[meta:])]


def stagione_in_corso(atleta: str, stagione: str) -> dict | None:
    """La stagione in corso dai tabellini ESPN, come la media di /player (regular season e play-in)."""
    tab = [r for r in partite(atleta, stagione) if r["tipo"] in G.TIPI]
    contano = [r for r in tab if L.conta(r)]
    if not contano:
        return None
    teams = []
    for r in tab:
        if r["squadra"] and r["squadra"] not in teams:
            teams.append(r["squadra"])
    return {"stagione": int(stagione) + 1, "g": len(contano), "mp": sum(int(r["minuti"] or 0) for r in contano) / len(contano),
            "fm": sum(float(r["fp"]) for r in contano) / len(contano), "teams": teams, "in_corso": True}


def dati_carriera(gid: int | None, nome_bref: str, nome: str | None = None) -> dict | None:
    s_ora = L.stagione()
    stagioni = [x for x in stagioni_bref(nome_bref) if x["stagione"] <= int(s_ora)]   # quella in corso: dai tabellini
    atleta = None
    if gid is not None:
        g = L.q("SELECT espn_id FROM giocatori WHERE id = %s", (gid,), one=True) or {}
        atleta = g.get("espn_id")
    corso = stagione_in_corso(atleta, s_ora) if atleta else None
    if corso:
        stagioni.append(corso)
    elif gid is None:
        stagioni += [x for x in stagioni_bref(nome_bref) if x["stagione"] > int(s_ora)]
    if not stagioni:
        return None
    mov = movimenti(gid) if gid is not None else []
    ora = datetime.now(timezone.utc)
    out = []
    for x in stagioni:
        fanta = []
        if gid is not None and x["stagione"] >= 2027:            # il fantabasket nel bot: dal 2026-27
            # tutte le squadre del fantabasket della stagione, in ordine (Luca, 10/11): quella all'inizio (1° agosto)
            # e quelle dei movimenti fino al 1° luglio dopo (o adesso)
            inizio = datetime(x["stagione"] - 1, 8, 1, tzinfo=timezone.utc)
            fine = min(datetime(x["stagione"], 7, 1, tzinfo=timezone.utc), ora)
            ids = [squadra_al(mov, inizio)] + [m["team_id_a"] for m in mov if inizio < m["timestamp"] <= fine]
            for t_id in ids:
                if t_id and t_id not in [f["id"] for f in fanta]:
                    info = _info_squadra(t_id)
                    fanta.append({"id": t_id, "nome": info["nome"], "colore": info["colore"], "logo": info["logo"],
                                  "sigla": "".join(p[0] for p in info["nome"].split()[:3]).upper()})
        out.append({"lbl": etichetta_stagione(x["stagione"]), "fm": round(x["fm"], 3), "fm_t": _t(x["fm"]), "g": x["g"],
                    "min": f"{x['mp']:.1f}".replace(".", ","), "team": _righe_squadre(x["teams"]),
                    "in_corso": bool(x.get("in_corso")), "fanta": fanta})
    tot_g = sum(x["g"] for x in stagioni)
    media = sum(x["fm"] * x["g"] for x in stagioni) / tot_g if tot_g else 0.0
    _, hi, passo = _asse([x["fm"] for x in stagioni])
    nota = ("Fantamedia di ogni stagione dalle medie di Basketball-Reference (regular season), con le partite giocate"
            + (", i minuti a partita" if len(out) <= 14 else "") + " e le squadre NBA in ordine")
    if gid is not None:
        nota += " · i tondi e i nomi colorati: le squadre del fantabasket in cui è stato nella stagione (dal 2026-27)"
    if corso:
        nota += " · la stagione in corso dai tabellini ESPN, come /player"
    nota += " · dati dal 1979-80"
    test = _testata(gid, nome or nome_bref)
    # i quattro riquadri (Luca, 11/11); senza la stagione in corso lo dice
    mi = max(range(len(out)), key=lambda i: out[i]["fm"])
    a_ora = int(s_ora)
    ora_lbl = f"{a_ora}-{(a_ora + 1) % 100:02d}"
    ul = out[-1]
    riquadri = [{"t": "Fantamedia", "v": _t(media), "s": "in carriera, pesata sulle partite"},
                {"t": "Stagioni", "v": str(len(out)), "s": f"{tot_g:,} partite".replace(",", ".")},
                {"t": "Migliore", "v": out[mi]["fm_t"], "s": out[mi]["lbl"]},
                {"t": "In corso", "v": ul["fm_t"], "s": f"{ora_lbl} · {ul['g']} G"} if ul["in_corso"] else
                {"t": "In corso", "v": "—", "s": f"non gioca nel {ora_lbl} · ultima {ul['lbl']}"}]
    return {"modo": "carriera", **test, "titolo": "Rendimento in carriera", "media_big": _t(media), "riquadri": riquadri,
            "media_val": ottavi(media),
            "media_sotto": f"fantamedia in carriera · {tot_g:,} partite in {len(out)} {'stagione' if len(out) == 1 else 'stagioni'}".replace(",", "."),
            "stagioni": out, "y_max": hi, "y_passo": passo, "nota": nota}


SOMIGLIANZA = 0.88      # un nome scritto male vale per quello giusto se gli somiglia almeno così…
STACCO = 0.06           # …e più degli altri di almeno tanto


def nomi_bref(testo: str) -> list[str]:
    """I nomi di Basketball-Reference (tutti, anche i giocatori storici) che corrispondono al testo."""
    import difflib
    from shared import parole_nome as PN
    n = L.norm(testo)
    if not n:
        return []
    tutti = [r["nome_bref"] for r in (L.q("SELECT DISTINCT nome_bref FROM bref_stats", many=True) or [])]
    esatti = [x for x in tutti if L.norm(x) == n or PN.stesse_parole(testo, x)]
    trovati = esatti or [x for x in tutti if n in L.norm(x) or PN.contiene_parole(testo, x)]
    if not trovati:
        # nome scritto male (Luca, 10/11: «Micheal Jordan» dava anche Jordan Mickey): i simili in ordine di somiglianza,
        # e se il primo è nettamente il più vicino solo lui
        nomi = {PN.ordinata(x): x for x in tutti}
        simili = difflib.get_close_matches(PN.ordinata(testo), list(nomi), n=5, cutoff=0.8)
        voto = lambda x: difflib.SequenceMatcher(None, PN.ordinata(testo), x).ratio()
        simili.sort(key=voto, reverse=True)
        if simili and voto(simili[0]) >= SOMIGLIANZA and (len(simili) == 1 or voto(simili[0]) - voto(simili[1]) >= STACCO):
            simili = simili[:1]
        return [nomi[x] for x in simili]
    return sorted(trovati)[:8]


def immagine(d: dict) -> bytes:
    import typst
    fonts = [f for f in ("/usr/share/fonts",) if os.path.isdir(f)]
    png = typst.compile(TEMPLATE_CARRIERA if d.get("modo") == "carriera" else TEMPLATE, root="/", format="png", ppi=170, font_paths=fonts,
                        sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})
    return png[0] if isinstance(png, list) else png


# ── comandi ───────────────────────────────────────────────────────────────────

async def _manda(msg, d: dict | None, vuoto: str) -> None:
    import asyncio
    if not d:
        await msg.reply_text(vuoto)
        return
    png = await asyncio.to_thread(immagine, d)
    await msg.reply_photo(png)


async def _rendimento(msg, gid: int) -> None:
    import asyncio
    d = await asyncio.to_thread(dati_stagione, gid)
    if d and d["giocate"] < MIN_PARTITE:
        n = d["giocate"]
        await msg.reply_text(f"Troppo pochi dati: {d['nome']} ha giocato {n} {'partita' if n == 1 else 'partite'} in questa "
                             f"stagione, per il grafico ne servono almeno {MIN_PARTITE}. Intanto c'è /player.")
        return
    await _manda(msg, d, "Nessuna partita in questa stagione nei tabellini ESPN.")


async def _carriera(msg, gid: int | None, nome_bref: str | None) -> None:
    import asyncio
    if gid is not None and not nome_bref:
        g = L.q("SELECT nome_bref, nome_common FROM giocatori WHERE id = %s", (gid,), one=True) or {}
        nome_bref = g.get("nome_bref") or g.get("nome_common") or ""
    d = await asyncio.to_thread(dati_carriera, gid, nome_bref)
    await _manda(msg, d, "Nessuna stagione di questo giocatore nei dati di Basketball-Reference.")


async def cmd_rendimento(update, context):
    msg = update.effective_message
    testo = " ".join(context.args or [])
    if not testo:
        await msg.reply_text("Uso: /rendimento NOME (es. /rendimento Wembanyama): la stagione partita per partita.\n"
                             "Per tutta la carriera: /rendimento_carriera NOME")
        return
    trovati = G.cerca(testo)
    if not trovati:
        await msg.reply_text(f"Nessun giocatore si chiama «{testo}». Per i giocatori di altre epoche: /rendimento_carriera NOME")
        return
    if len(trovati) > 1 and L.norm(trovati[0]["nome_common"]) != L.norm(testo):
        await msg.reply_text("Quale?", reply_markup=K([[B(x["nome_common"] + (" ✅" if x["a_roster"] else ""), callback_data=f"rs:{x['id']}")]
                                                       for x in trovati]))
        return
    await _rendimento(msg, trovati[0]["id"])


def _gid_da_bref(nome_bref: str) -> int | None:
    r = L.q("SELECT id FROM giocatori WHERE nome_bref = %s ORDER BY id LIMIT 1", (nome_bref,), one=True)
    return r["id"] if r else None


async def cmd_rendimento_carriera(update, context):
    """Il nome si cerca così (Luca, 09/11: «Deron Williams» dava i Williams della lega): prima i giocatori del bot con
    quel nome esatto; se no tutti i nomi di Basketball-Reference (anche gli storici: un nome che è nel bot si ricollega
    al giocatore, per il fantabasket e la stagione in corso); solo se lì non c'è niente, i nomi simili del bot."""
    from shared import parole_nome as PN
    msg = update.effective_message
    testo = " ".join(context.args or [])
    if not testo:
        await msg.reply_text("Uso: /rendimento_carriera NOME (es. /rendimento_carriera LeBron James): la fantamedia stagione per "
                             "stagione, anche dei giocatori che non sono nel fantabasket (dati dal 1979-80).")
        return
    trovati = G.cerca(testo)
    esatti = [x for x in trovati if L.norm(x["nome_common"]) == L.norm(testo) or PN.stesse_parole(testo, x["nome_common"])]
    if len(esatti) == 1:
        await _carriera(msg, esatti[0]["id"], None)
        return
    nomi = nomi_bref(testo)
    if len(nomi) == 1 or (nomi and (L.norm(nomi[0]) == L.norm(testo) or PN.stesse_parole(testo, nomi[0]))
                          and sum(1 for x in nomi if L.norm(x) == L.norm(nomi[0])) == 1):
        await _carriera(msg, _gid_da_bref(nomi[0]), nomi[0])
        return
    if nomi:
        await msg.reply_text("Quale?", reply_markup=K([[B(x, callback_data=f"rcb:{x}"[:64])] for x in nomi]))
        return
    if trovati:                                   # niente in Basketball-Reference: i nomi simili del bot
        await msg.reply_text("Quale?", reply_markup=K([[B(x["nome_common"] + (" ✅" if x["a_roster"] else ""), callback_data=f"rc:{x['id']}")]
                                                       for x in trovati]))
        return
    await msg.reply_text(f"Nessun giocatore si chiama «{testo}», nemmeno tra quelli di Basketball-Reference (dal 1979-80).")


async def cb_rendimento(update, context):
    q = update.callback_query
    await q.answer()
    tipo, _, val = q.data.partition(":")
    await q.edit_message_text("📈 ⬇️")
    if tipo == "rs":
        await _rendimento(q.message, int(val))
    elif tipo == "rc":
        await _carriera(q.message, int(val), None)
    else:
        await _carriera(q.message, _gid_da_bref(val), val)


PATTERN = r"^(rs|rc):\d+$|^rcb:.+$"

"""
Il draft visto da fuori (v7.27.0, Luca 23/11): chi sceglie, l'ordine in testo, il tabellone per giro.

Codice di lettura, usato dal bot principale (che fa il draft, handlers/draft.py) e da loucabot (/draft per vederlo).
Le righe sono in `draft_scelte` (anno, giro, numero 1–48, pick, penalità, stato, squadra, via, protetta, giocatore).

- Chi sceglie: chi ha la pick in quel momento (si scambia fino alla scelta); se la 1st cade nella protezione (alla
  posizione dopo le penalità) resta al proprietario di partenza (shared/protezioni).
- Ordine in testo (Luca, 23/11): «ORDINE SCELTE AL DRAFT 2026», PRIMO GIRO / SECONDO GIRO, righe «1 | Andrea -
  Cam Boozer», «5 | Geva (via Henry) - …», «13 | Calamo (-1) - …», «19 | Enzo (via Alan, -1)», «2 | Leo (protetta
  1-4) - …».
- Tabellone: un'immagine per giro (draft.typ, stile «tracker» chiaro a righe, due colonne da 12; in prova finché la
  lega non sceglie lo stile nel sondaggio del 23/11).
"""
import json
import os

from shared import lettura as L
from shared import protezioni as P

ORDINALI = {1: "prima", 2: "seconda", 3: "terza", 4: "quarta", 5: "quinta", 6: "sesta", 7: "settima", 8: "ottava",
            9: "nona", 10: "decima", 11: "undicesima", 12: "dodicesima", 13: "tredicesima", 14: "quattordicesima",
            15: "quindicesima", 16: "sedicesima", 17: "diciassettesima", 18: "diciottesima", 19: "diciannovesima",
            20: "ventesima", 21: "ventunesima", 22: "ventiduesima", 23: "ventitreesima", 24: "ventiquattresima"}


def scelta_testo(numero: int) -> str:
    """«la prima scelta» nel primo giro; dal secondo «la 25ª scelta» (Luca, 23/11)."""
    return f"la {ORDINALI[numero]} scelta" if numero in ORDINALI else f"la {numero}ª scelta"


def gm(team_id: str | None) -> str:
    t = L.squadra(team_id) if team_id else None
    return (t or {}).get("gm_nome") or (t or {}).get("nome") or (team_id or "?")


def righe(anno: str) -> list[dict]:
    return L.q("""SELECT s.*, p.proprietario_orig, p.proprietario_att, p.protezioni, p.round,
                         g.nome_common AS giocatore
                  FROM draft_scelte s JOIN pick p ON p.id = s.pick_id
                  LEFT JOIN giocatori g ON g.id = s.giocatore_id
                  WHERE s.anno = %s ORDER BY s.numero""", (str(anno),), many=True) or []


def chi_sceglie(r: dict) -> tuple[str, str | None, str | None]:
    """(squadra che sceglie, «via» la squadra di chi era la pick o None, «protetta 1-4» se è scattata o None)."""
    if r.get("stato") == "fatta" and r.get("squadra"):
        return r["squadra"], r.get("via"), r.get("protetta")
    if int(r.get("round") or r.get("giro") or 0) == 1 and P.scatta(r.get("protezioni"), r["numero"]):
        return r["proprietario_orig"], None, P.testo(r.get("protezioni"))
    chi = r["proprietario_att"]
    return chi, (r["proprietario_orig"] if r["proprietario_orig"] != chi else None), None


def etichetta(r: dict) -> str:
    """«Geva (via Henry, -1)», «Leo (protetta 1-4)»."""
    chi, via, prot = chi_sceglie(r)
    tra = [f"via {gm(via)}"] if via else []
    if r.get("penalita"):
        tra.append(f"-{r['penalita']}")
    if prot:
        tra.append(prot)
    return gm(chi) + (f" ({', '.join(tra)})" if tra else "")


def corrente(anno: str) -> dict | None:
    return next((r for r in righe(anno) if r["stato"] != "fatta"), None)


def testo_ordine(anno: str) -> str:
    """Il messaggio dell'ordine sul canale, che si aggiorna a ogni scelta."""
    rr = righe(anno)
    cor = next((r for r in rr if r["stato"] != "fatta"), None)
    out = [f"<b>ORDINE SCELTE AL DRAFT {anno}</b>"]
    for giro, titolo in ((1, "PRIMO GIRO"), (2, "SECONDO GIRO")):
        gg = [r for r in rr if r["giro"] == giro]
        if not gg:
            continue
        out += ["", f"<b>{titolo}</b>"]
        for r in gg:
            riga = f"{r['numero']} | {etichetta(r)}"
            if r["stato"] == "fatta":
                riga += f" - {r['giocatore'] or r.get('nome_proposto') or '?'}"
            elif cor and r["id"] == cor["id"]:
                riga += " - ⏳ on the clock"
            out.append(riga)
    return "\n".join(out)


def scala(numero: int, giro: int) -> str:
    """Il contratto della rookie scale (colonna del I anno) per la posizione: «12M ×2»."""
    try:
        path = os.environ.get("SETTINGS_PATH", "/config/settings.json")
        tab = json.load(open(path, encoding="utf-8")).get("rookie_scale", {})
    except Exception:
        tab = {}
    for fascia, valori in tab.items():
        lim = fascia.split("-")
        if int(lim[0]) <= numero <= int(lim[-1]) and valori:
            return f"{valori[0]['imp']}M ×{valori[0]['anni']}"
    return ""


def dati(anno: str, giro: int) -> dict | None:
    """I dati del tabellone di un giro (draft.typ)."""
    rr = [r for r in righe(anno) if r["giro"] == giro]
    if not rr:
        return None
    cor = corrente(anno)
    fatte = sum(1 for r in rr if r["stato"] == "fatta")
    pick = []
    for r in rr:
        chi, via, prot = chi_sceglie(r)
        t = L.squadra(chi) or {"nome": chi}
        stato = "fatta" if r["stato"] == "fatta" else ("ora" if cor and cor["id"] == r["id"] else "dopo")
        sc = scala(r["numero"], giro)
        pick.append({"n": r["numero"], "squadra": t.get("nome", chi), "gm": gm(chi), "colore": L.colore(t), "logo": L.logo(chi),
                     "sigla": "".join(w[0] for w in t.get("nome", chi).split()[:2]).upper(),
                     "via": (L.squadra(via) or {}).get("nome", via) if via else "", "prot": prot or "",
                     "sanz": f"−{r['penalita']} penalità" if r.get("penalita") else "", "stato": stato,
                     "gioc": r.get("giocatore") or "",
                     "scala": ("diritti" if giro == 2 else f"firmato {sc}") if stato == "fatta" else ("diritti" if giro == 2 else f"scala {sc}")})
    ora = None
    if cor and cor["giro"] == giro:
        chi, _, _ = chi_sceglie(cor)
        ora = {"pick": f"Pick {cor['numero']}", "squadra": L.nome(chi),
               "stato": f"GM {gm(chi)} · " + ("nome da approvare dagli admin" if cor["stato"] in ("proposta", "approvata") else "in attesa del nome")}
    return {"anno": str(anno), "giro": "Primo giro" if giro == 1 else "Secondo giro",
            "sotto": f"{fatte} scelte fatte su {len(rr)}", "ora": ora, "pick": pick,
            "note": "«via»: la pick era di quella squadra · 🛡 protezione scattata, la pick resta a chi l'aveva ceduta · "
                    "in rosso le discese per le penalità · le 1st si firmano alla rookie scale della posizione, le 2nd "
                    "diventano diritti"}


def immagine(d: dict) -> bytes:
    import typst
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "draft.typ")
    fonts = [x for x in ("/usr/share/fonts",) if os.path.isdir(x)]
    return typst.compile(tpl, root="/", format="png", ppi=150, font_paths=fonts,
                         sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})


def anni() -> list[str]:
    return [r["anno"] for r in (L.q("SELECT DISTINCT anno FROM draft_scelte ORDER BY anno DESC", many=True) or [])]


async def cmd_draft(update, context):
    """/draft [ANNO]: i tabelloni dei due giri (senza anno l'ultimo, quello in corso)."""
    import asyncio
    msg = update.effective_message
    try:
        tutti = anni()
    except Exception:
        tutti = []
    anno = (context.args or [None])[0] or (tutti[0] if tutti else None)
    if not anno or anno not in tutti:
        await msg.reply_text("Nessun draft " + (f"{anno} " if anno else "") + "nel bot." +
                             (f" Draft che ci sono: {', '.join(tutti)}." if tutti else ""))
        return
    for giro in (1, 2):
        d = await asyncio.to_thread(dati, anno, giro)
        if d:
            await msg.reply_photo(await asyncio.to_thread(immagine, d))

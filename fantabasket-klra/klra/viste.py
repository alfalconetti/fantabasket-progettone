"""
Quello che klra mostra: scheda di un sistema, classifica, /giornata, /partita, /risultati, /confronta.
Le immagini usano i template di loucabot dove ci sono già (partita.typ e live.typ, con l'etichetta del sistema)
e i due di klra (classifica.typ con P e PT, confronta.typ). Tutto in sola lettura sulla lega.
"""
import json
import os
from datetime import datetime, timezone

import classifica as CL
import config
import db
from numeri import testo as tp

from klra import motore as M
from klra import regole as KR
from klra import sistemi as SI

QUI = os.path.dirname(os.path.abspath(__file__))
VIOLA = "#7B3FE4"
ROSSO = "#C0392B"
NON_UFFICIALE = "🧪 NON UFFICIALE"
FILIGRANA = "NON UFFICIALE"


def striscia(s: dict) -> str:
    return f"🧪 KLRA · NON UFFICIALE · sistema {s['nome']} · i risultati veri sono quelli di loucabot"


def _anno(s: str) -> str:
    return f"{s}-{str(int(s) + 1)[-2:]}"


def _png(template: str, d: dict, ppi: int = 180) -> bytes:
    import typst
    return typst.compile(template, root="/", format="png", ppi=ppi, sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})


def riassunto(s: dict, max_righe: int = 3) -> str:
    """Le differenze dall'Ufficiale in una riga (per le liste e le bande)."""
    if s["ufficiale"]:
        return "le regole della lega"
    if s.get("predefinito") == "fantamedie":
        return "chi gioca prende la sua media prima della giornata, il resto come la lega"
    d = KR.differenze(SI.parametri(s), breve=True)
    if not d:
        return "uguale all'Ufficiale"
    return " · ".join(d[:max_righe]) + (f" · e altre {len(d) - max_righe}" if len(d) > max_righe else "")


# ── classifica ──

def dati_classifica(s: dict, stagione: str) -> dict | None:
    P = SI.parametri(s)
    righe = M.classifica(s, stagione)
    giornate = len(M.giornate_convalidate(stagione))
    if not giornate:
        return None
    col = CL.colori(righe, False)
    out = [{"pos": r["pos"], "nome": config.nome(r["team"]), "logo": CL._logo(r["team"]), "w": r["w"], "l": r["l"], "p": r["p"],
            "pt": f"{r['pt']:g}", "pf": tp(r["pf"]), "ps": tp(r["ps"]), "media": tp(r["media"]), "striscia": r["striscia"],
            "col": col.get(r["team"], {})} for r in righe]
    punti = P["classifica"]["modo"] == "punti"
    return {"filigrana": FILIGRANA, "striscia": striscia(s), "titolo": f"Classifica {_anno(stagione)}", "sotto": f"dopo {giornate} {'giornata' if giornate == 1 else 'giornate'} convalidate",
            "sistema": s["nome"], "regole": riassunto(s, 2), "righe": out, "punti": punti,
            "pareggi": any(r["p"] for r in righe),
            "ordine": ("ordine per punti in classifica, a parità scontri diretti, media punti, differenza" if punti else
                       "ordine per vittorie, a parità scontri diretti, media punti, differenza")}


def img_classifica(s: dict, stagione: str) -> bytes | None:
    d = dati_classifica(s, stagione)
    return _png(os.path.join(QUI, "classifica.typ"), d) if d else None


# ── confronta ──

def dati_confronta(s: dict, stagione: str) -> dict | None:
    cf = M.confronta(s, stagione)
    if not cf["giornate"]:
        return None
    P = SI.parametri(s)
    rec = lambda r: f"{r['w']}-{r['l']}" + (f"-{r['p']}" if r.get("p") else "")
    righe = []
    for r in cf["righe"]:
        u = r["uff"] or {}
        righe.append({"pos": r["pos"], "diff": (u.get("pos", r["pos"]) - r["pos"]), "nome": config.nome(r["team"]),
                      "logo": CL._logo(r["team"]), "pos_uff": u.get("pos", "—"), "rec_uff": f"{u.get('w', 0)}-{u.get('l', 0)}",
                      "rec": rec(r), "supp": sum(1 for x in r["partite"] if x["supp"]), "pt": f"{r['pt']:g}"})
    ris = {(x["giornata"], x["casa"]): x for x in M.risultati_stagione(s, stagione)}
    nome_esito = lambda v, casa, tr, supp: ("pareggio" if v == "pari" else config.nome(casa if v == "casa" else tr)) + (" (supp.)" if supp and v != "pari" else "")
    vere = {(x["giornata"], x["casa"]): x for x in CL.risultati(stagione)}
    cambi = []
    for c in cf["cambiano"]:
        r = ris[(c["giornata"], c["casa"])]
        v = vere[(c["giornata"], c["casa"])]
        cambi.append({"giornata": c["giornata"], "casa": config.nome(c["casa"]), "trasferta": config.nome(c["trasferta"]),
                      "punti": f"{tp(r['punti_casa'])} – {tp(r['punti_trasferta'])}",
                      "prima": nome_esito(v["vince"], c["casa"], c["trasferta"], v["supp_casa"] is not None),
                      "dopo": nome_esito(r["vince"], c["casa"], c["trasferta"], r["supplementari"])})
    return {"filigrana": FILIGRANA, "striscia": striscia(s), "sistema": s["nome"], "sotto": f"stagione {_anno(stagione)} · {cf['giornate']} giornate convalidate",
            "regole": "" if s["ufficiale"] else f"{s['nome']}" + (f" (di {s['autore_nome']})" if s.get("autore_nome") else "") + ": " + riassunto(s, 3),
            "punti": P["classifica"]["modo"] == "punti", "righe": righe, "cambiano": cambi, "partite": len(ris)}


def img_confronta(s: dict, stagione: str) -> bytes | None:
    d = dati_confronta(s, stagione)
    return _png(os.path.join(QUI, "confronta.typ"), d) if d else None


# ── giornata (tabellone di live.typ in «modo finale») ──

def dati_giornata(s: dict, stagione: str, n: int) -> dict:
    import live
    g = db.giornata(stagione, n)
    d = M.risultati_giornata(s, stagione, n)
    out = []
    for k, x in enumerate(d["risultati"], 1):
        nota = f"SUPPLEMENTARI · {tp(x['supp_casa'])} – {tp(x['supp_trasferta'])}" if x["supp_casa"] is not None else ""
        if x["vince"] == "pari":
            nota = "PAREGGIO" + (f" · {nota}" if nota else "")
        lati = [{**live._squadra_img(t), "punti": tp(p), "finito": True, "campo": 0, "giocare": 0, "rigiocare": 0, "finora": "",
                 "media": 0} for t, p in ((x["casa"], x["punti_casa"]), (x["trasferta"], x["punti_trasferta"]))]
        out.append({"k": k, "casa": lati[0], "tras": lati[1], "avanti": x["vince"] if x["vince"] != "pari" else "", "nota": nota})
    return {"n": n, "date": f"{g['dal']:%d/%m} – {g['al']:%d/%m}", "nba": [], "nba_colonne": 5, "nba_notte": "", "notte": "",
            "modo": "finale", "etichetta": f"NON UFFICIALE · {s['nome'].upper()}", "colore_stato": ROSSO,
            "filigrana": FILIGRANA, "striscia": striscia(s),
            "ora_label": "", "ora": "", "partite": out, "soglia": 0, "bonus": f"{d['bonus_casa']:g}",
            "nota_finale": f"Ricalcolata col sistema {s['nome']} ({riassunto(s, 2)}) · bonus casa +{d['bonus_casa']:g} · "
                           "in grassetto chi vince · il dettaglio di ogni sfida con /partita"}


def img_giornata(s: dict, stagione: str, n: int) -> bytes:
    import live
    return live.immagine(dati_giornata(s, stagione, n))


# ── partita (partita.dati di loucabot, col sistema) ──

def _bonus_testo(lista) -> str:
    if not lista:
        return ""
    tot = {}
    for lab, v in lista:
        tot[lab] = tot.get(lab, 0) + v
    return " ".join(f"{'+' if v > 0 else ''}{v:g} {lab}" for lab, v in tot.items())


def dati_partita(s: dict, stagione: str, n: int, casa: str, trasferta: str) -> dict:
    import partita
    P = SI.parametri(s)
    M.installa()
    c = M.calcolo_completo(P, stagione, n)
    tok = M._ATTIVO.set(KR.completa(P))
    try:
        d = partita.dati(stagione, n, casa, trasferta, datetime.now(timezone.utc))
    finally:
        M._ATTIVO.reset(tok)
    r = next(x for x in c["risultati"] if x["casa"] == casa and x["trasferta"] == trasferta)
    nomi = {}
    for t in (casa, trasferta):
        for x in c["squadre"][t]["quintetto"] + c["squadre"][t]["panchina"]:
            if x.get("atleta"):
                nomi[x.get("nome")] = x["atleta"]
    for sq, calc in zip(d["squadre"], (r["sc"], r["st"])):
        for riga in sq["righe"]:
            a = nomi.get(riga["nome"])
            riga["bonus"] = _bonus_testo(c["klra_bonus"].get(a)) if a and riga.get("conta") else ""
        sq["totale"] = tp(calc["totale"])
        for lab, v in calc.get("bonus_squadra") or []:
            d["note"].insert(0, f"{sq['nome']}: {lab} {'+' if v > 0 else ''}{v:g}")
        if r["vince"] == "pari":
            sq["vince"] = False
    d["note"] = [x for x in d["note"] if not x.startswith("Supplementari:")]
    if r["supplementari"]:
        d["note"].append(f"Supplementari: scarto sotto {P['partita']['scarto']:g} punti, {r['supplementari']} "
                         f"{'giro' if r['supplementari'] == 1 else 'giri'} di panchinari in ordine (S1, S2…)")
    if r["vince"] == "pari":
        d["note"].insert(0, "Pareggio col sistema " + s["nome"])
    d["note"].insert(0, f"Sistema {s['nome']}: {riassunto(s, 4)}")
    d["sistema"] = s["nome"]
    d["filigrana"], d["striscia"] = FILIGRANA, striscia(s)
    d["bonus"] = tp(c["bonus"])
    return d


def img_partita(s: dict, stagione: str, n: int, casa: str, trasferta: str) -> tuple[bytes, dict]:
    import partita
    d = dati_partita(s, stagione, n, casa, trasferta)
    return partita.immagine(d), d


# ── risultati in testo ──

def testo_risultati(s: dict, stagione: str, n: int) -> str:
    import html
    e = lambda x: html.escape(str(x), quote=False)
    d = M.risultati_giornata(s, stagione, n)
    vere = {x["casa"]: x for x in CL.risultati(stagione) if x["giornata"] == n}
    righe = [f"🧪 <b>NON UFFICIALE</b> · sistema <b>{e(s['nome'])}</b>", f"📅 <b>Giornata {n}</b>", f"<i>{e(riassunto(s, 3))}</i>", ""]
    for x in d["risultati"]:
        c, t = config.nome(x["casa"]), config.nome(x["trasferta"])
        b = lambda nome, lato: f"<b>{e(nome)}</b>" if x["vince"] == lato else e(nome)
        riga = f"{b(c, 'casa')} {tp(x['punti_casa'])} – {tp(x['punti_trasferta'])} {b(t, 'trasferta')}"
        if x["supp_casa"] is not None:
            riga += f" <i>(supp. {tp(x['supp_casa'])} – {tp(x['supp_trasferta'])})</i>"
        if x["vince"] == "pari":
            riga += " · pareggio"
        extra = [f"{e(nome)} {lab} {'+' if v > 0 else ''}{v:g}" for nome, lato in ((c, "sc"), (t, "st"))
                 for lab, v in x[lato]["bonus_squadra"]]
        if extra:
            riga += "\n   <i>" + " · ".join(extra) + "</i>"
        v = vere.get(x["casa"])
        if v and v["vince"] != x["vince"]:
            riga += "  🔄 <i>nella realtà " + ("pareggio" if v["vince"] == "pari" else e(config.nome(x["casa"] if v["vince"] == "casa" else x["trasferta"]))) + "</i>"
        righe.append(riga)
    righe += ["", "🔄 = finisce diversamente dalla realtà · i risultati veri sono quelli di loucabot"]
    return "\n".join(righe)


# ── /top: fantamedia col sistema (come /top di loucabot) ──

def classifica_top(s: dict, stagione: str, solo_firmati: bool = False) -> list[dict]:
    """Come top_giocatori.classifica di loucabot (stesso minimo di partite, stesse colonne), con la fantamedia
    rifatta coi pesi e i bonus del giocatore del sistema; accanto quella della lega."""
    import math
    import top_giocatori as TG
    P = SI.parametri(s)
    righe = db.q("""SELECT t.*, p.inizio FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                    WHERE p.stagione = %s AND p.tipo = ANY(%s) AND t.giocato ORDER BY p.inizio""", (stagione, [2, 5]), many=True) or []
    es = M._esiti_nba({r["partita"] for r in righe}) if P["giocatore"]["vittoria_nba"] else {}
    per: dict[str, dict] = {}
    for r in righe:
        x = per.setdefault(r["atleta"], {"nome": r["nome"], "fp": [], "lega": [], "ultima": r["squadra"]})
        x["ultima"] = r["squadra"]
        if not (float(r["fp"] or 0) == 0 and int(r["minuti"] or 0) == 0):        # come /top: lo 0 con 0 minuti non conta
            x["fp"].append(M.fp_riga(r, P, es))
            x["lega"].append(float(r["fp"] or 0))
    if not per:
        return []
    info = {r["atleta"]: r for r in db.q("""SELECT a.atleta, a.squadra, gi.id AS gid, c.team_id FROM nba_atleti a
                                             LEFT JOIN giocatori gi ON gi.espn_id = a.atleta
                                             LEFT JOIN contratti c ON c.giocatore_id = gi.id AND c.attivo
                                             WHERE a.atleta = ANY(%s)""", (list(per),), many=True) or []}
    extra = {r["atleta"]: r for r in db.q("""SELECT gi.espn_id AS atleta, gi.id AS gid, c.team_id FROM giocatori gi
                                              LEFT JOIN contratti c ON c.giocatore_id = gi.id AND c.attivo
                                              WHERE gi.espn_id = ANY(%s)""", (list(per),), many=True) or []}
    squadre = {r["sq"]: r["n"] for r in db.q(
        """SELECT sq, COUNT(*) AS n FROM (SELECT casa AS sq FROM nba_partite WHERE stagione = %s AND tipo = ANY(%s) AND stato = 'STATUS_FINAL'
               UNION ALL SELECT trasferta FROM nba_partite WHERE stagione = %s AND tipo = ANY(%s) AND stato = 'STATUS_FINAL') x
           GROUP BY sq""", (stagione, [2, 5], stagione, [2, 5]), many=True) or []}
    try:
        pos = {r["giocatore_id"]: r["posizioni"] for r in db.q("SELECT giocatore_id, posizioni FROM posizioni_attuali", many=True) or []}
    except Exception:
        pos = {}
    out = []
    for a, x in per.items():
        if not x["fp"]:
            continue
        i = {**extra.get(a, {}), **{k: v for k, v in (info.get(a) or {}).items() if v is not None}}
        if solo_firmati and not i.get("team_id"):
            continue
        sq = i.get("squadra") or x["ultima"]
        tot = squadre.get(sq, 0)
        if tot and len(x["fp"]) < math.ceil(TG.MINIMO * tot):
            continue
        from numeri import ottavi
        out.append({"nome": x["nome"], "media": ottavi(sum(x["fp"]) / len(x["fp"])), "lega": ottavi(sum(x["lega"]) / len(x["lega"])),
                    "partite": len(x["fp"]), "squadra": sq or "—",
                    "fanta": config.nome(i["team_id"]) if i.get("team_id") else "libero",
                    "pos": (pos.get(i.get("gid")) or "").replace(",", "/")})
    out.sort(key=lambda x: (-x["media"], x["nome"]))
    return out


def testo_top(s: dict, stagione: str, da: int, a: int, solo_firmati: bool) -> str:
    import top_giocatori as TG
    tutti = classifica_top(s, stagione, solo_firmati)
    uff = {x["nome"]: i for i, x in enumerate(sorted(tutti, key=lambda x: (-x["lega"], x["nome"])), 1)}
    scelti = tutti[da - 1:a]
    righe = [f"{NON_UFFICIALE} · sistema {s['nome']}",
             f"🏆 Top {da}–{min(a, da - 1 + len(scelti))} per fantamedia col sistema · stagione {_anno(stagione)}"
             + (" · solo firmati" if solo_firmati else ""),
             f"{riassunto(s, 3)}",
             f"Con almeno il {int(TG.MINIMO * 100)}% delle partite della propria squadra NBA ({len(tutti)} giocatori) · "
             f"tra parentesi la fantamedia della lega e la posizione nella top vera", ""]
    for i, x in enumerate(scelti, da):
        righe.append(f"{i}. {x['nome']} {tp(x['media'])} (lega {tp(x['lega'])}, {uff[x['nome']]}º) · {x['partite']} G · "
                     f"{x['squadra']} · {x['fanta']}" + (f" · {x['pos']}" if x["pos"] else ""))
    if not scelti:
        righe.append("Nessun giocatore in questo intervallo.")
    return "\n".join(righe)

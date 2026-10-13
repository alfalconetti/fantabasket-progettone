"""
Calcolo dei punteggi secondo il regolamento (capitolo PARTITA), dai tabellini di ESPN.

Giocatore in una giornata (punteggio_giocatori):
- ha giocato una o più partite della giornata → media matematica dei fantapunti delle partite giocate;
- non ha giocato e la sua squadra NBA nella giornata non ha partite (squadre a media), oppure ha
  solo partite rinviate → la sua media della stagione, ma 0 se è indisponibile (infortunato,
  squalificato: per tutti i giorni della giornata con uno snapshot degli infortunati);
- non ha giocato e la sua squadra ha giocato → 0.

Squadra (punteggio_squadra): somma dei 5 titolari; FADD: un panchinaro dello stesso ruolo prende il
posto di un titolare che non ha giocato nessuna partita e ha avuto il tag (O, INJ, GTD: per ESPN
qualunque stato diverso da Probable) in tutti i giorni in cui la sua squadra ha giocato. Una sola
sostituzione per giornata, il primo panchinaro in ordine che può entrare; la panchina scala.

Partita (esito): vince chi ha 5 o più punti di scarto, bonus casa compreso (3, nei playoff 5);
altrimenti si aggiungono i panchinari uno alla volta, in ordine (supplementari); pari anche dopo
l'ultimo → vince la squadra in trasferta.

Restano agli admin: i 72 ore di attesa per le partite rinviate, le penalità.
"""
from datetime import timedelta

import db

STATI_DISPONIBILE = {"probable", "active", "available"}
SCARTO = 5


def indisponibile(stato: str | None) -> bool:
    return bool(stato) and stato.strip().lower() not in STATI_DISPONIBILE


def _giorni(dal, al) -> list:
    return [dal + timedelta(days=i) for i in range((al - dal).days + 1)]


def _media(valori: list[float]) -> float:
    return round(sum(valori) / len(valori), 2) if valori else 0.0


def punteggio_giocatori(stagione: str, g: dict, atleti: list[str]) -> dict[str, dict]:
    """{atleta: {fp, come, partite, squadra, nota}}; come ∈ partite / media / zero."""
    atleti = [a for a in dict.fromkeys(atleti) if a]
    if not atleti:
        return {}
    dal, al = g["dal"], g["al"]
    giorni = _giorni(dal, al)
    tab = db.tabellini_atleti(atleti, dal, al)
    partite_nba = db.partite_nba(dal, al)
    giocano = {}                    # squadra NBA → partite della giornata (giocate, rinviate)
    for p in partite_nba:
        for sq in (p["casa"], p["trasferta"]):
            x = giocano.setdefault(sq, {"giocate": [], "rinviate": []})
            (x["rinviate"] if p["stato"] in ("STATUS_POSTPONED", "STATUS_CANCELED") else x["giocate"]).append(p)
    media_giornata = set(g.get("media") if g.get("media") is not None else (g.get("media_file") or []))
    squadre_prima = db.ultima_squadra(atleti, al + timedelta(days=1))
    medie = db.medie_stagione(atleti, stagione, dal)
    stati = db.infortuni(atleti, giorni)
    decisi = db.status_validi(stagione, g["numero"], atleti) if g.get("numero") else {}
    con_snap = db.giorni_con_snapshot(giorni)
    out = {}
    for a in atleti:
        righe = [r for r in tab if r["atleta"] == a]
        giocate = [float(r["fp"]) for r in righe if r["giocato"]]
        squadra = righe[-1]["squadra"] if righe else squadre_prima.get(a)
        if giocate:
            out[a] = {"fp": _media(giocate), "come": "partite", "partite": giocate, "squadra": squadra,
                      "nota": f"{len(giocate)} partite" if len(giocate) > 1 else ""}
            continue
        sq = giocano.get(squadra, {"giocate": [], "rinviate": []})
        senza_partite = squadra in media_giornata or (squadra and not sq["giocate"] and not sq["rinviate"])
        solo_rinviate = bool(sq["rinviate"]) and not sq["giocate"]
        if squadra and (senza_partite or solo_rinviate) and a in decisi:      # deciso da un admin
            if indisponibile(decisi[a]):
                out[a] = {"fp": 0.0, "come": "zero", "partite": [], "squadra": squadra,
                          "nota": f"indisponibile ({decisi[a]}, deciso da un admin): niente media"}
            else:
                m = medie.get(a)
                out[a] = {"fp": m["media"] if m else 0.0, "come": "media", "partite": [], "squadra": squadra,
                          "nota": (f"media su {m['partite']} partite" if m else "nessuna partita giocata, media 0")
                                  + " (disponibile, deciso da un admin)"}
            continue
        if squadra and (senza_partite or solo_rinviate):
            snap = sorted(d for d in giorni if d in con_snap)
            ko = [stati.get((a, d)) for d in snap]
            if snap and all(indisponibile(s) for s in ko):
                out[a] = {"fp": 0.0, "come": "zero", "partite": [], "squadra": squadra,
                          "nota": f"indisponibile ({ko[-1]}): niente media"}
                continue
            m = medie.get(a)
            perche = "partita rinviata" if solo_rinviate else "squadra senza partite"
            out[a] = {"fp": m["media"] if m else 0.0, "come": "media", "partite": [], "squadra": squadra,
                      "nota": f"{perche}: media su {m['partite']} partite" if m else f"{perche}: nessuna partita giocata, media 0"}
            if not snap:
                out[a]["nota"] += " (nessuno snapshot infortunati: disponibilità non verificata)"
            continue
        out[a] = {"fp": 0.0, "come": "zero", "partite": [], "squadra": squadra,
                  "nota": "non ha giocato" if squadra else "nessun tabellino: squadra NBA sconosciuta"}
    return out


def _fadd_possibile(a: str, p: dict, g: dict) -> tuple[bool, str]:
    """Il titolare `a` (con punteggio p) può essere sostituito? (sì/no, motivo)"""
    if p["come"] != "zero" or not p.get("squadra"):
        return False, ""
    giorni = sorted({x["data_et"] for x in db.partite_nba(g["dal"], g["al"])
                     if p["squadra"] in (x["casa"], x["trasferta"]) and x["stato"] == "STATUS_FINAL"})
    if not giorni:
        return False, ""
    if g.get("numero") and g.get("stagione"):
        deciso = db.status_validi(g["stagione"], g["numero"], [a])
        if a in deciso:                                       # deciso da un admin: vince sugli snapshot
            return (True, f"{deciso[a]}, deciso da un admin") if indisponibile(deciso[a]) else (False, "")
    con_snap = db.giorni_con_snapshot(giorni)
    if set(giorni) - con_snap:
        return False, "manca lo snapshot degli infortunati di qualche giorno: decide un admin"
    stati = db.infortuni([a], giorni)
    if all(indisponibile(stati.get((a, d))) for d in giorni):
        return True, "/".join(sorted({stati[(a, d)] for d in giorni}))
    return False, ""


def punteggio_squadra(g: dict, quintetto: list[dict], panchina: list[dict], punteggi: dict[str, dict]) -> dict:
    """quintetto, panchina: [{atleta, ruolo, nome}] (panchina in ordine). punteggi: punteggio_giocatori.
    → {totale, titolari: [...], panchina: [...], fadd, avvisi}"""
    zero = {"fp": 0.0, "come": "zero", "nota": "senza id ESPN"}
    tit = [{**x, **punteggi.get(x.get("atleta"), zero)} for x in quintetto]
    pan = [{**x, **punteggi.get(x.get("atleta"), zero)} for x in panchina]
    fadd, avvisi = None, []
    candidati = []
    for i, t in enumerate(tit):
        si, motivo = _fadd_possibile(t.get("atleta"), t, g) if t.get("atleta") else (False, "")
        if si:
            candidati.append((i, motivo))
        elif motivo:
            avvisi.append(f"{t.get('nome', t.get('atleta'))}: {motivo}")
    for j, b in enumerate(pan):
        i = next((i for i, _ in candidati if tit[i].get("ruolo") and tit[i].get("ruolo") == b.get("ruolo")), None)
        if i is not None:
            motivo = dict(candidati)[i]
            fadd = {"esce": tit[i], "entra": b, "motivo": motivo}
            tit[i] = {**b, "fadd": True}
            pan = pan[:j] + pan[j + 1:]
            break
    if candidati and not fadd:
        avvisi.append("titolare sostituibile (FADD) ma nessun panchinaro del suo ruolo")
    return {"totale": round(sum(t["fp"] for t in tit), 2), "titolari": tit, "panchina": pan,
            "fadd": fadd, "avvisi": avvisi}


def esito(casa: dict, trasferta: dict, bonus: float = 3) -> dict:
    """casa, trasferta: risultati di punteggio_squadra. → {vince: casa/trasferta, casa, trasferta, supplementari}"""
    c, t = casa["totale"] + bonus, trasferta["totale"]
    pc = [x["fp"] for x in casa["panchina"]] + [0.0] * 5
    pt = [x["fp"] for x in trasferta["panchina"]] + [0.0] * 5
    supp = 0
    while abs(c - t) < SCARTO and supp < 5:
        c, t = c + pc[supp], t + pt[supp]
        supp += 1
    if abs(c - t) >= SCARTO:
        vince = "casa" if c > t else "trasferta"
    else:
        vince = "trasferta"
    return {"vince": vince, "casa": round(c, 2), "trasferta": round(t, 2), "supplementari": supp,
            "regolamentari": (round(casa["totale"] + bonus, 2), round(trasferta["totale"], 2))}


# ── abbinamento giocatori ↔ ESPN ───────────────────────────────────────────────

_SUFFISSI = {"jr", "sr", "ii", "iii", "iv", "v"}
_LETTERE = str.maketrans({"đ": "d", "Đ": "d", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "ß": "ss", "æ": "ae", "þ": "th"})


def norm(nome: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", (nome or "").translate(_LETTERE)).encode("ascii", "ignore").decode().lower()
    parole = [p for p in re.sub(r"[^a-z ]", "", s.replace("-", " ")).split() if p not in _SUFFISSI]
    return "".join(parole)


def abbina_auto(atleti: dict[str, str]) -> dict:
    """Abbina all'anagrafica i giocatori ESPN {atleta: nome} non ancora abbinati, solo se il nome
    (senza accenti, punteggiatura e Jr./III) corrisponde a uno e un solo giocatore e viceversa."""
    indice = {}
    for g in db.giocatori_anagrafica():
        for n in {norm(g["nome_common"]), norm(g["nome_bref"]), norm(g.get("nome_yahoo") or "")} - {""}:
            indice.setdefault(n, set()).add(g["id"])
    gia = db.abbinamenti()
    gia_atleti = set(gia.values())
    per_nome = {}
    for a, nome in atleti.items():
        per_nome.setdefault(norm(nome), []).append(a)
    nuovi, ambigui = 0, []
    for a, nome in atleti.items():
        if a in gia_atleti:
            continue
        ids = indice.get(norm(nome), set())
        if len(ids) == 1 and len(per_nome[norm(nome)]) == 1:
            gid = next(iter(ids))
            if gid not in gia:
                db.abbina(gid, a, nome, "auto")
                gia[gid] = a
                nuovi += 1
        elif len(ids) > 1 or len(per_nome[norm(nome)]) > 1:
            ambigui.append(nome)
    return {"nuovi": nuovi, "ambigui": sorted(set(ambigui))}

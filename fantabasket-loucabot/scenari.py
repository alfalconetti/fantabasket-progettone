"""
Scenari di fine regular season (v7.37.0, mockup approvato da Luca il 26/11): per conference la corsa ai playoff e al
bye, e la corsa alla lottery (tanking) per tutta la lega.

Due cose diverse, tenute separate anche nelle immagini:
- **Certezze** (stato, seed possibili, «cosa serve»): valgono qualunque cosa succeda. Si ragiona sulle sole vittorie
  (a fine stagione tutte hanno giocato le stesse partite) e un pari vittorie si considera incerto, perché lo possono
  decidere scontri diretti ancora da giocare o la media punti; l'unico spareggio già noto è la vincitrice della Quasi
  Cup, che a pari record passa davanti a tutte. Gli scontri tra le inseguitrici non si sottraggono: le frasi
  possono arrivare una giornata dopo il momento esatto, mai sbagliare.
- **Probabilità**: SIMULAZIONI giri Monte Carlo delle partite rimaste. In ogni giro ogni squadra fa un punteggio
  estratto da una normale con la media e la deviazione dei suoi punteggi della stagione, pesate (v7.37.0, Luca 27/11:
  le ultime 5 partite contano 3, dalla 6ª alla 10ª dall'ultima 2, le altre 1; senza bonus casa, che si riaggiunge a
  chi gioca in casa); sotto lo scarto minimo vince una delle due a caso (i supplementari). Poi la
  classifica con gli spareggi veri (classifica.ordina: vittorie, Quasi Cup, avulsa, media, differenza), seed per
  conference (6, le prime 2 col bye) e posto in lottery (le 12 fuori, dall'ultima). Il seme dipende da stagione e
  giornate convalidate: /scenari e il canale danno gli stessi numeri.

Lottery: la 1ª scelta e le prime 4 dalla matrice delle odds del regolamento (shared/lottery.ODDS), media sui giri.
Partite chiave: della prossima giornata, quanto cambia la probabilità (playoff per le conference, 1ª scelta per la
lottery) della squadra più toccata a seconda di chi vince.

Sul canale principale dopo ogni convalida di regular season quando mancano da DA_MANCANTI giornate in giù (una volta
per giornata); /scenari in qualsiasi momento della regular season.
"""
import asyncio
import io
import json
import logging
import math
import os
import random
import statistics

import classifica as C
import config
import db
from numeri import ottavi
from shared import lottery as LT
from shared import regole

logger = logging.getLogger(__name__)
SIMULAZIONI = 20000
DA_MANCANTI = 5
QUANTE, BYE, POSTI_LOTTERY = 6, 2, 6
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenari.typ")


# ── dati ───────────────────────────────────────────────────────────────────────

def rimaste(s: str, convalidate: set[int]) -> list[tuple[int, str, str]]:
    """(giornata, casa, trasferta) delle partite di regular season non ancora convalidate."""
    rr = db.q("""SELECT p.giornata, p.casa, p.trasferta FROM lega_partite p
                 JOIN lega_giornate g ON g.stagione = p.stagione AND g.numero = p.giornata AND g.tipo = 'regular'
                 WHERE p.stagione = %s ORDER BY p.giornata, p.id""", (s,), many=True) or []
    return [(r["giornata"], r["casa"], r["trasferta"]) for r in rr if r["giornata"] not in convalidate]


def situazione(s: str | None = None) -> dict:
    """Tutto quello che serve, letto una volta: classifica di adesso, partite rimaste, conference, Cup."""
    s = s or config.stagione()
    ris = C.risultati(s)
    squadre = [t["id"] for t in config.squadre()]
    st = C.base(ris, squadre)
    fatte = {r["giornata"] for r in ris}
    return {"s": s, "st": st, "squadre": squadre, "rimaste": rimaste(s, fatte), "campione": C.campione_cup(s),
            "conf": C.conference(), "ultima": max(fatte) if fatte else 0, "bonus": float(regole.bonus_casa()),
            "scarto": float(regole.scarto_minimo())}


PESI_RECENTI = ((5, 3.0), (10, 2.0))           # le ultime 5 partite pesano 3, dalla 6ª alla 10ª dall'ultima 2, le altre 1


def peso(dalla_fine: int) -> float:
    """Peso di una partita: dalla_fine 0 = l'ultima giocata (Luca, 27/11: più le ultime 10, ancora di più le ultime 5)."""
    for quante, p in PESI_RECENTI:
        if dalla_fine < quante:
            return p
    return 1.0


def _media_dev(v: list[float]) -> tuple[float, float]:
    """Media e deviazione pesate; v in ordine di giornata."""
    w = [peso(len(v) - 1 - i) for i in range(len(v))]
    tot = sum(w)
    mu = sum(x * p for x, p in zip(v, w)) / tot
    return mu, math.sqrt(sum(p * (x - mu) ** 2 for x, p in zip(v, w)) / tot)


def parametri(st: dict, bonus: float) -> dict[str, tuple[float, float]]:
    """(media, deviazione) pesate dei punteggi di ogni squadra senza bonus casa: le ultime giornate contano di più."""
    grezzi = {t: [x["fatti"] - (bonus if x["casa"] else 0) for x in sorted(s["partite"], key=lambda x: x["giornata"])]
              for t, s in st.items()}
    tutti = [p for v in grezzi.values() for p in v]
    dev_lega = statistics.pstdev(tutti) if len(tutti) > 1 else 10.0
    media_lega = statistics.mean(tutti) if tutti else 100.0
    out = {}
    for t, v in grezzi.items():
        if len(v) >= 5:
            mu, sd = _media_dev(v)
        else:
            mu, sd = (statistics.mean(v) if v else media_lega), dev_lega
        out[t] = (mu, sd or dev_lega)
    return out


# ── certezze ───────────────────────────────────────────────────────────────────

def _minmax(sit: dict) -> dict[str, tuple[int, int]]:
    resto = {t: 0 for t in sit["squadre"]}
    for _, c, tr in sit["rimaste"]:
        resto[c] = resto.get(c, 0) + 1
        resto[tr] = resto.get(tr, 0) + 1
    return {t: (sit["st"][t]["w"], sit["st"][t]["w"] + resto.get(t, 0)) for t in sit["squadre"]}


def _puo_davanti(o: str, vo_max: int, t: str, vt: int, camp: str | None) -> bool:
    """o può finire davanti a t se t chiude con vt vittorie."""
    return vo_max > vt or (vo_max == vt and t != camp)


def _sicura_davanti(o: str, vo_min: int, t: str, vt: int, camp: str | None) -> bool:
    return vo_min > vt or (vo_min == vt and o == camp)


def _parola(n: int, uno: str, tanti: str) -> str:
    return f"{n} {uno if n == 1 else tanti}"


def _pari(kp: int | None, k: int) -> str:
    """Quando con meno vittorie basta vincere gli spareggi (che a pari vittorie non si sanno prima)."""
    if kp is None or kp >= k:
        return ""
    return f" ({'già adesso' if kp == 0 else 'con ' + str(kp)} se vince gli eventuali spareggi)"


def certezze(sit: dict) -> dict[str, dict]:
    """{team: {stato, seed: (migliore, peggiore), serve, lotto: (min, max) o None, frase_lottery}}."""
    mm, camp, conf = _minmax(sit), sit["campione"], sit["conf"]
    out = {}
    for t in sit["squadre"]:
        altre = [o for o in sit["squadre"] if o != t and conf.get(o) == conf.get(t)]
        w, wmax = mm[t]
        resto = wmax - w
        davanti_possibili = lambda vt: sum(_puo_davanti(o, mm[o][1], t, vt, camp) for o in altre)
        davanti_sicure = lambda vt: sum(_sicura_davanti(o, mm[o][0], t, vt, camp) for o in altre)
        senza_pari = lambda vt: sum(mm[o][1] > vt or (mm[o][1] == vt and o == camp) for o in altre)
        migliore, peggiore = 1 + davanti_sicure(wmax), min(len(altre) + 1, 1 + davanti_possibili(w))
        if peggiore <= BYE:
            stato = "bye"
        elif peggiore <= QUANTE:
            stato = "dentro"
        elif migliore > QUANTE:
            stato = "fuori"
        else:
            stato = "corsa"
        frasi = []
        if stato in ("corsa", "dentro") and migliore <= BYE:
            k = next((k for k in range(resto + 1) if davanti_possibili(w + k) < BYE), None)
            kp = next((k for k in range(resto + 1) if senza_pari(w + k) < BYE), None)
            if k is not None:
                frasi.append(f"bye sicuro con {_parola(k, 'vittoria', 'vittorie')}" + _pari(kp, k))
            else:
                frasi.append("il bye non dipende solo da lei")
        if stato == "dentro":
            frasi.insert(0, "Playoff già sicuri")
        elif stato == "corsa":
            k = next((k for k in range(resto + 1) if davanti_possibili(w + k) < QUANTE), None)
            kp = next((k for k in range(resto + 1) if senza_pari(w + k) < QUANTE), None)
            if k is not None:
                p = (f"Playoff sicuri vincendole tutte" if k == resto and resto > 1
                     else f"Playoff sicuri con {_parola(k, 'vittoria', 'vittorie')}")
                p += _pari(kp, k)
            elif kp is not None:
                p = f"Non dipende solo da lei: anche con {_parola(kp, 'vittoria', 'vittorie')} a pari decidono gli spareggi"
            else:
                p = "Non dipende solo da lei: anche vincendole tutte servono altri risultati"
            frasi.insert(0, p)
            fuori_sotto = max((j + 1 for j in range(resto + 1) if davanti_sicure(w + j) >= QUANTE), default=0)
            if fuori_sotto == resto:
                frasi.append("fuori alla prima sconfitta")
            elif fuori_sotto == 1:
                frasi.append("fuori se le perde tutte")
            elif fuori_sotto > 0:
                frasi.append(f"fuori se ne vince meno di {fuori_sotto}")
        f = " · ".join(frasi)
        out[t] = {"stato": stato, "seed": (migliore, peggiore), "serve": f[:1].upper() + f[1:]}
    # lottery: posto tra le fuori dai playoff, 1 = la peggiore della lega
    for t in sit["squadre"]:
        if out[t]["stato"] in ("bye", "dentro"):
            out[t]["lotto"] = None
            continue
        w, wmax = mm[t]
        sotto_sicure = sum(1 for o in sit["squadre"] if o != t and out[o]["stato"] == "fuori"
                           and (mm[o][1] < w or (mm[o][1] == w and t == camp)))
        sotto_possibili = sum(1 for o in sit["squadre"] if o != t and out[o]["stato"] not in ("bye", "dentro")
                              and (mm[o][0] < wmax or (mm[o][0] == wmax and o != camp)))
        a, b = 1 + sotto_sicure, min(12, 1 + sotto_possibili)
        frasi = []
        if out[t]["stato"] == "corsa":
            frasi.append("ancora in corsa per i playoff")
        if a == b:
            frasi.append("record peggiore sicuro" if a == 1 else f"{a}ª in lottery sicura")
        else:
            if a > 1:
                frasi.append("non può più avere il record peggiore")
            if b < 12:
                frasi.append(f"non può finire oltre la {b}ª")
        f = " · ".join(frasi)
        out[t]["lotto"] = (a, b)
        out[t]["frase_lottery"] = f[:1].upper() + f[1:]
    return out


# ── simulazioni ────────────────────────────────────────────────────────────────

def simula(sit: dict, n: int = SIMULAZIONI, seme: str | None = None) -> dict:
    """Conteggi su n giri. → {po, bye, lotto (team → [conteggi posto 1..12]), pick1, top4, chiave}."""
    rng = random.Random(seme or f"{sit['s']}-G{sit['ultima']}")
    par = parametri(sit["st"], sit["bonus"])
    conf, camp, bonus, scarto = sit["conf"], sit["campione"], sit["bonus"], sit["scarto"]
    squadre = sit["squadre"]
    prossima = min((g for g, _, _ in sit["rimaste"]), default=None)
    partite_pross = [(c, tr) for g, c, tr in sit["rimaste"] if g == prossima]
    nomi_conf = sorted(set(conf.values()))
    po = {t: 0 for t in squadre}
    bye = {t: 0 for t in squadre}
    lotto = {t: [0] * 12 for t in squadre}
    pick1 = {t: 0.0 for t in squadre}
    top4 = {t: 0.0 for t in squadre}
    # partite chiave: per partita e per esito (0 casa, 1 trasferta) → giri, playoff per squadra, 1ª scelta per squadra
    chiave = {(c, tr): [[0, {t: 0 for t in squadre}, {t: 0.0 for t in squadre}] for _ in range(2)] for c, tr in partite_pross}
    base_st = sit["st"]
    nomi = {t: config.nome(t) for t in squadre}
    for _ in range(n):
        nuove = {t: list(base_st[t]["partite"]) for t in squadre}
        esiti = {}
        for g, c, tr in sit["rimaste"]:
            mc, sc = par[c]
            mt, stt = par[tr]
            pc, pt = rng.gauss(mc, sc) + bonus, rng.gauss(mt, stt)
            vince_casa = pc > pt if abs(pc - pt) >= scarto else rng.random() < 0.5
            nuove[c].append({"giornata": g, "avv": tr, "fatti": pc, "subiti": pt, "vinta": vince_casa, "supp": False, "casa": True})
            nuove[tr].append({"giornata": g, "avv": c, "fatti": pt, "subiti": pc, "vinta": not vince_casa, "supp": False, "casa": False})
            if g == prossima:
                esiti[(c, tr)] = 0 if vince_casa else 1
        st = {}
        for t in squadre:
            p = nuove[t]
            k = len(p)
            fatti, subiti = sum(x["fatti"] for x in p), sum(x["subiti"] for x in p)
            vinte = sum(x["vinta"] for x in p)
            st[t] = {"team": t, "w": vinte, "l": k - vinte, "media": ottavi(fatti / k) if k else 0.0,
                     "diff": fatti - subiti, "partite": p}
        ordine = C.ordina(st, camp, nomi)
        dentro = set()
        for nc in nomi_conf:
            cc = [t for t in ordine if conf.get(t) == nc]
            for i, t in enumerate(cc[:QUANTE]):
                dentro.add(t)
                po[t] += 1
                if i < BYE:
                    bye[t] += 1
        fuori = [t for t in reversed(ordine) if t not in dentro]
        p1 = {}
        for i, t in enumerate(fuori[:12]):
            lotto[t][i] += 1
            riga = LT.ODDS[i]
            p1[t] = riga[0]
            pick1[t] += riga[0]
            top4[t] += sum(riga[:4])
        for partita, e in esiti.items():
            cella = chiave[partita][e]
            cella[0] += 1
            for t in dentro:
                cella[1][t] += 1
            for t, v in p1.items():
                cella[2][t] += v
    return {"n": n, "po": po, "bye": bye, "lotto": lotto, "pick1": pick1, "top4": top4, "chiave": chiave, "prossima": prossima}


# ── immagini ───────────────────────────────────────────────────────────────────

def _pct(x: float) -> int:
    """Percentuale intera, senza far sembrare certo quello che non lo è: 0 e 100 solo se esatti."""
    v = round(x * 100)
    if v == 100 and x < 1:
        return 99
    if v == 0 and x > 0:
        return 1
    return v


def _pct1(x: float) -> str:
    return f"{x * 100:.1f}".replace(".", ",")


def _nome_seed(a: int, b: int) -> str:
    return str(a) if a == b else f"{a}-{b}"


def _chiave_conf(sit: dict, sim: dict, nc: str) -> list[dict]:
    out = []
    for (c, tr), esiti in sim["chiave"].items():
        if nc not in (sit["conf"].get(c), sit["conf"].get(tr)) or not esiti[0][0] or not esiti[1][0]:
            continue
        migliore = None
        for t in sit["squadre"]:
            if sit["conf"].get(t) != nc:
                continue
            pa, pb = esiti[0][1][t] / esiti[0][0], esiti[1][1][t] / esiti[1][0]
            if migliore is None or abs(pa - pb) > migliore[0]:
                migliore = (abs(pa - pb), t, pa, pb)
        if migliore and migliore[0] >= 0.03:
            d, t, pa, pb = migliore
            out.append({"peso": d, "partita": f"{config.nome(c)} – {config.nome(tr)}",
                        "dice": f"{config.nome(t)} ai playoff: {_pct(pa)}% se vince {config.nome(c)}, {_pct(pb)}% se vince {config.nome(tr)}",
                        "testo_peso": f"±{round(d * 50)}%"})
    return [{k: v for k, v in x.items() if k != "peso"} for x in sorted(out, key=lambda x: -x["peso"])[:3]]


def _chiave_lottery(sit: dict, sim: dict, mostrate: set[str]) -> list[dict]:
    out = []
    for (c, tr), esiti in sim["chiave"].items():
        if not esiti[0][0] or not esiti[1][0]:
            continue
        migliore = None
        for t in mostrate:
            pa, pb = esiti[0][2][t] / esiti[0][0], esiti[1][2][t] / esiti[1][0]
            if migliore is None or abs(pa - pb) > migliore[0]:
                migliore = (abs(pa - pb), t, pa, pb)
        if migliore and migliore[0] >= 0.005:
            d, t, pa, pb = migliore
            out.append({"peso": d, "partita": f"{config.nome(c)} – {config.nome(tr)}",
                        "dice": f"{config.nome(t)} 1ª scelta: {_pct1(pa)}% se vince {config.nome(c)}, {_pct1(pb)}% se vince {config.nome(tr)}",
                        "testo_peso": f"±{_pct1(d / 2)}%"})
    return [{k: v for k, v in x.items() if k != "peso"} for x in sorted(out, key=lambda x: -x["peso"])[:3]]


NOTE_CONF = ("Stato, seed possibili e «cosa serve» sono certi: valgono qualunque cosa facciano le altre. «Sicuri con N "
             "vittorie» vuol dire con N vittorie in qualunque caso; dove a pari vittorie potrebbero decidere gli scontri diretti "
             "o la media punti lo dice, perché quelli non si sanno prima. Le percentuali sono stime. Spareggi: vincitrice della "
             "Quasi Cup, scontri diretti (classifica avulsa), media punti fatti, differenza.")
NOTE_LOTTERY = ("Come per i playoff, le frasi sono certe (valgono qualunque cosa succeda) e le percentuali sono stime. A pari "
                "record il posto in lottery lo decidono gli stessi spareggi della classifica, rovesciati: chi sta peggio prende il "
                "posto più alto. Le partite sospette restano al controllo anti-tanking degli admin.")


def dati(sit: dict, sim: dict, cert: dict) -> dict:
    """{conference: [dati per conference.typ], lottery: dati}. Ordine: la classifica di adesso."""
    n = sim["n"]
    ordine = C.ordina({t: dict(v) for t, v in sit["st"].items()}, sit["campione"])
    giornate = sorted({g for g, _, _ in sit["rimaste"]})
    mancano = len(giornate)
    sotto = (f"Dopo la G{sit['ultima']} convalidata · probabilità da {n:,} simulazioni delle ultime giornate con le medie di "
             "ogni squadra").replace(",", ".")
    import playoff as PO
    conferenze = []
    presenti = set(sit["conf"].values())
    for nc in [c for c in PO.conferenze() if c in presenti] or sorted(presenti):
        righe = []
        for t in [t for t in ordine if sit["conf"].get(t) == nc]:
            s, c = sit["st"][t], cert[t]
            righe.append({"nome": config.nome(t), "wl": f"{s['w']}-{s['l']}", "seed": _nome_seed(*c["seed"]),
                          "po": _pct(sim["po"][t] / n), "bye": _pct(sim["bye"][t] / n), "stato": c["stato"], "serve": c["serve"]})
        conferenze.append({"tipo": "conference", "conf": nc, "mancano": mancano, "sotto": sotto, "righe": righe,
                           "prossima": sim["prossima"], "chiave": _chiave_conf(sit, sim, nc), "note": NOTE_CONF})
    # chi può ancora finire nei primi posti (certezza) e ci finisce in almeno un giro (le altre allungherebbero e basta)
    mostrate = [t for t in reversed(ordine) if cert[t]["lotto"] and cert[t]["lotto"][0] <= POSTI_LOTTERY
                and sum(sim["lotto"][t][:POSTI_LOTTERY])]
    righe = []
    for t in mostrate:
        s = sit["st"][t]
        fuori = 1 - sim["po"][t] / n
        righe.append({"nome": config.nome(t), "conf": sit["conf"].get(t, ""), "wl": f"{s['w']}-{s['l']}", "fuori": _pct(fuori),
                      "posti": [_pct(x / n) for x in sim["lotto"][t][:POSTI_LOTTERY]],
                      "prima": _pct1(sim["pick1"][t] / n), "top4": _pct(sim["top4"][t] / n), "serve": cert[t]["frase_lottery"]})
    lottery = {"tipo": "lottery", "mancano": mancano, "prossima": sim["prossima"], "righe": righe,
               "sotto": (f"Dopo la G{sit['ultima']} convalidata · le squadre che possono ancora finire nelle prime "
                         f"{POSTI_LOTTERY} posizioni della lottery · {n:,} simulazioni con le medie").replace(",", "."),
               "chiave": _chiave_lottery(sit, sim, set(mostrate)), "note": NOTE_LOTTERY}
    return {"conferenze": conferenze, "lottery": lottery}


def immagine(d: dict) -> bytes:
    import typst
    return typst.compile(TEMPLATE, root="/", format="png", ppi=160, sys_inputs={"dati": json.dumps(d, ensure_ascii=False)})


def calcola(s: str | None = None, n: int = SIMULAZIONI) -> tuple[list[tuple[str, bytes]], dict]:
    """[(nome, png)] (le conference, poi la lottery) e i dati. ValueError se non si può."""
    sit = situazione(s)
    if not sit["ultima"]:
        raise ValueError("nessuna giornata convalidata: gli scenari partono dalla prima convalida")
    if not sit["rimaste"]:
        raise ValueError("la regular season è finita: niente più scenari, la classifica è quella finale (/classifica)")
    if len(set(sit["conf"].values())) < 2:
        raise ValueError("conference non configurate (config/divisions.json)")
    sim = simula(sit, n)
    d = dati(sit, sim, certezze(sit))
    out = [(c["conf"], immagine(c)) for c in d["conferenze"]]
    if d["lottery"]["righe"]:
        out.append(("Lottery", immagine(d["lottery"])))
    return out, {**d, "ultima": sit["ultima"], "mancano": d["lottery"]["mancano"]}


def didascalia(d: dict) -> str:
    m = d["mancano"]
    return (f"🔮 <b>Scenari di fine regular season</b> dopo la G{d['ultima']} · {'manca 1 giornata' if m == 1 else f'mancano {m} giornate'}\n"
            "<i>Stato e «cosa serve» sono certi; le percentuali sono stime da simulazioni con le medie.</i>")


# ── canale e comando ───────────────────────────────────────────────────────────

async def _manda(bot, chat_id, imm: list[tuple[str, bytes]], d: dict, **kw) -> None:
    from telegram import InputMediaPhoto
    media = [InputMediaPhoto(io.BytesIO(png), caption=didascalia(d) if i == 0 else None, parse_mode="HTML")
             for i, (_, png) in enumerate(imm)]
    await bot.send_media_group(chat_id=chat_id, media=media, read_timeout=60, write_timeout=60, connect_timeout=30, **kw)


def mancano_dopo(s: str, n: int) -> int | None:
    """Giornate di regular season dopo la n (None se la n non è di regular season)."""
    g = db.giornata(s, n)
    if not g or g.get("tipo", "regular") != "regular":
        return None
    return sum(1 for x in db.giornate(s) if x.get("tipo", "regular") == "regular" and x["numero"] > n)


async def dopo_convalida(bot, s: str, n: int) -> str:
    """Dalla convalida (handlers_risultati): sul canale principale quando mancano da DA_MANCANTI giornate in giù,
    una volta per giornata (una convalida rifatta non li rimanda)."""
    m = mancano_dopo(s, n)
    if not m or m > DA_MANCANTI:
        return ""
    canale = config.globali().get("main_channel_id")
    if not canale:
        return "scenari: canale principale non configurato"
    import playoff as PO
    if not PO._una_volta(s, f"scenari_G{n}"):
        return ""
    imm, d = await asyncio.to_thread(calcola, s)
    await _manda(bot, canale, imm, d)
    return "scenari di fine regular season sul canale"


async def cmd_scenari(update, context):
    msg = update.effective_message
    if config.fase() not in ("regular-season-fa", "regular-season-deadline"):
        await msg.reply_text("Gli scenari ci sono solo in regular season.")
        return
    attesa = await msg.reply_text("🔮 Simulo le ultime giornate…")
    try:
        imm, d = await asyncio.to_thread(calcola, None)
    except ValueError as err:
        await attesa.edit_text(f"Scenari non disponibili: {err}.")
        return
    except Exception as err:
        logger.warning("Scenari: %s", err)
        await attesa.edit_text(f"⚠️ Scenari non disponibili: {err}")
        return
    try:
        await attesa.delete()
    except Exception:
        pass
    await _manda(context.bot, msg.chat_id, imm, d, reply_to_message_id=msg.message_id)


def get_handlers() -> list:
    from telegram.ext import CommandHandler
    return [CommandHandler("scenari", cmd_scenari)]

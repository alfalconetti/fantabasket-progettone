#!/usr/bin/env python3
"""Verifica del modello delle simulazioni di /scenari (v7.37.0b, Luca 27/11: «ha senso usare una normale?»).
Solo lettura: legge i risultati convalidati della regular season, non scrive niente. Si lancia nel container di
loucabot (dove ci sono il DB e il codice), dalla cartella del repo:

    docker compose exec -T loucabot python - [STAGIONE] < strumenti/verifica_scenari.py

1. Forma dei punteggi: i residui (punteggio senza bonus casa − media della squadra) / deviazione della squadra, di
   tutta la lega, confrontati con una normale: asimmetria, code, quantili, quanti oltre 2 e 3 deviazioni.
2. Prova all'indietro: ogni giornata convalidata dalla 6ª prevista con le sole giornate prima, come farebbe /scenari
   quel giorno, e confrontata con chi ha vinto davvero. Quattro modelli: 50/50, normale con la media semplice,
   normale con la media pesata (il motore di adesso), residui veri della lega con la media pesata.
   Brier (errore quadratico medio, più basso meglio; 50/50 = 0,250) e log loss (più basso meglio; 50/50 = 0,693).
   Guarda una giornata avanti: la deriva della forza (DERIVA), che conta quando mancano tante giornate, qui non entra.
3. Calibrazione del motore di adesso: le partite raggruppate per probabilità prevista; se il modello è giusto, quelle
   date al 70% le vince la favorita circa 7 volte su 10.
"""
import math
import random
import statistics
import sys

import classifica as C
import config
import db
import scenari as SC
from shared import regole


def connetti():
    """Il pool di loucabot, ma in sola lettura e senza migra() (db.init_db migra lo schema): v7.37.0c, prima nel
    container il pool non c'era proprio."""
    import os
    import re
    import psycopg2.pool
    pw = os.environ.get("PG_PASSWORD_FILE", "/run/secrets/pg_password")
    if os.path.exists(pw):
        os.environ["PGPASSWORD"] = open(pw).read().strip()
    dsn = re.sub(r"[?&]password_file=[^\s&]+", "", os.environ["DATABASE_URL"])
    db._pool = psycopg2.pool.ThreadedConnectionPool(1, 2, dsn=dsn, options="-c default_transaction_read_only=on")


connetti()

S = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "-" else config.stagione()
BONUS, SCARTO = float(regole.bonus_casa()), float(regole.scarto_minimo())
PRIMA = 6                                         # dalla 6ª giornata: prima le medie sono troppo poche
Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))


def residui(st: dict, par: dict) -> list[float]:
    return [(x["fatti"] - (BONUS if x["casa"] else 0) - par[t][0]) / par[t][1] for t, s in st.items() for x in s["partite"]]


def p_normale(mc, sc, ec, mt, sdt, et) -> float:
    """P(vince la squadra di casa): differenza normale, sotto lo scarto metà e metà (i supplementari)."""
    mu = mc + BONUS - mt
    sd = math.sqrt(sc ** 2 + sdt ** 2 + ec ** 2 + et ** 2)
    sopra, sotto = 1 - Phi((SCARTO - mu) / sd), Phi((-SCARTO - mu) / sd)
    return sopra + 0.5 * (1 - sopra - sotto)


def p_empirica(mc, sc, ec, mt, sdt, et, pool: list[float], rng: random.Random, k: int = 3000) -> float:
    vinte = 0.0
    for _ in range(k):
        d = (mc + rng.gauss(0, ec) + sc * rng.choice(pool) + BONUS) - (mt + rng.gauss(0, et) + sdt * rng.choice(pool))
        vinte += 1 if d >= SCARTO else 0.5 if d > -SCARTO else 0
    return vinte / k


def semplici(st: dict) -> dict:
    """La normale con la media semplice (senza pesi e senza incertezza della media)."""
    out = {}
    for t, s in st.items():
        v = [x["fatti"] - (BONUS if x["casa"] else 0) for x in s["partite"]]
        out[t] = (statistics.mean(v), statistics.pstdev(v) or 10.0, 0.0)
    return out


def main():
    ris = C.risultati(S)
    squadre = [t["id"] for t in config.squadre()]
    giornate = sorted({r["giornata"] for r in ris})
    print(f"Stagione {S}: {len(ris)} partite convalidate in {len(giornate)} giornate (bonus casa {BONUS:g}, scarto {SCARTO:g})\n")
    if len(giornate) < PRIMA + 1:
        print(f"Servono almeno {PRIMA + 1} giornate convalidate.")
        return

    # 1. forma dei punteggi
    st = C.base(ris, squadre)
    z = residui(st, semplici(st))
    n = len(z)
    m = statistics.mean(z)
    sd = statistics.pstdev(z)
    asim = sum((x - m) ** 3 for x in z) / n / sd ** 3
    curt = sum((x - m) ** 4 for x in z) / n / sd ** 4 - 3
    zs = sorted(z)
    q = lambda p: zs[min(n - 1, int(p * n))]
    print("1. FORMA DEI PUNTEGGI (residui standardizzati, tutta la lega)")
    print(f"   {n} punteggi · asimmetria {asim:+.2f} (normale 0; >0 = più exploit che crolli) · "
          f"curtosi in eccesso {curt:+.2f} (normale 0; >0 = code più pesanti)")
    print("   quantile        5%     25%     50%     75%     95%")
    print("   reali       " + "  ".join(f"{q(p):+6.2f}" for p in (0.05, 0.25, 0.5, 0.75, 0.95)))
    print("   normale      -1.64   -0.67   +0.00   +0.67   +1.64")
    for k, atteso in ((2, 4.55), (3, 0.27)):
        sopra, sotto = sum(x > k for x in z) / n * 100, sum(x < -k for x in z) / n * 100
        print(f"   oltre {k} deviazioni: {sopra + sotto:.2f}% (normale {atteso}%) · sopra {sopra:.2f}% · sotto {sotto:.2f}%")

    # 2. prova all'indietro
    rng = random.Random(1)
    modelli = {"50/50": [], "normale, media semplice": [], "normale, media pesata (adesso)": [], "residui veri, media pesata": []}
    esiti = []
    for g in giornate:
        if g < giornate[0] + PRIMA:
            continue
        prima = [r for r in ris if r["giornata"] < g]
        stg = C.base(prima, squadre)
        if any(not stg[t]["partite"] for t in squadre):
            continue
        pes, sem = SC.parametri(stg, BONUS), semplici(stg)
        pool = residui(stg, pes)
        for r in (x for x in ris if x["giornata"] == g):
            c, t = r["casa"], r["trasferta"]
            esiti.append(1 if r["vince"] == "casa" else 0)
            modelli["50/50"].append(0.5)
            modelli["normale, media semplice"].append(p_normale(*sem[c], *sem[t]))
            modelli["normale, media pesata (adesso)"].append(p_normale(*pes[c], *pes[t]))
            modelli["residui veri, media pesata"].append(p_empirica(*pes[c], *pes[t], pool, rng))
    print(f"\n2. PROVA ALL'INDIETRO ({len(esiti)} partite, ognuna prevista con le sole giornate prima)")
    print("   modello                              Brier   log loss")
    for nome, p in modelli.items():
        brier = statistics.mean((a - b) ** 2 for a, b in zip(p, esiti))
        ll = -statistics.mean(math.log(min(max(a if b else 1 - a, 1e-6), 1)) for a, b in zip(p, esiti))
        print(f"   {nome:<36} {brier:.4f}   {ll:.4f}")
    casa = sum(esiti) / len(esiti) * 100
    print(f"   (vinte in casa: {casa:.1f}%; previste dal motore: {statistics.mean(modelli['normale, media pesata (adesso)']) * 100:.1f}%)")

    # 3. calibrazione
    print("\n3. CALIBRAZIONE DEL MOTORE DI ADESSO (dalla parte della favorita)")
    print("   fascia     prevista   partite   vinte dalla favorita")
    fasce = {}
    for p, e in zip(modelli["normale, media pesata (adesso)"], esiti):
        fav, vinta = (p, e) if p >= 0.5 else (1 - p, 1 - e)
        b = min(int(fav * 10), 9)
        fasce.setdefault(b, []).append((fav, vinta))
    for b in sorted(fasce):
        v = fasce[b]
        print(f"   {b * 10:>2}-{b * 10 + 10:<3}%    {statistics.mean(x for x, _ in v) * 100:5.1f}%   {len(v):>7}   "
              f"{statistics.mean(y for _, y in v) * 100:5.1f}%")
    print("\nSe «vinte dalla favorita» segue «prevista» (scarti di qualche punto con poche partite sono normali) e il "
          "motore ha Brier e log loss vicini o migliori dei residui veri, la normale va bene.")


main()

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.37.0b: strumenti/verifica_scenari.py (sola lettura) su una stagione finta: 24 squadre, 20 giornate con punteggi
asimmetrici (exploit più frequenti dei crolli). Escono le tre parti, il 50/50 ha Brier 0,25 e log loss 0,693, il
motore fa meglio del 50/50, l'asimmetria si vede, la tabella di calibrazione c'è."""
import contextlib
import io
import json
import random
import runpy
import sys
from datetime import date, timedelta

import db, config
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
_teams = open(config.TEAMS_PATH, encoding="utf-8").read()
T = [f"vs{i:02d}" for i in range(1, 25)]
json.dump({"teams": [{"id": t, "nome": f"Squadra {t[-2:]}", "gm_ids": [], "gm_nome": t} for t in T]}, open(config.TEAMS_PATH, "w"))
try:
    db.init_db()
    S = config.stagione()
    for t in ("lega_giornate", "lega_risultati", "lega_partite"):
        db.q(f"TRUNCATE {t}")
    rng = random.Random(7)
    forza = {t: 115 - i for i, t in enumerate(T)}
    punti = lambda t: forza[t] + rng.gammavariate(4, 3) - 12           # asimmetrica a destra, media ~forza
    Y = int(S) + 1
    for n in range(1, 21):
        dal = date(Y, 1, 1) + timedelta(days=7 * n)
        db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES (%s, %s, 'regular', %s, %s)", (S, n, dal, dal + timedelta(days=6)))
        giro = T[:1] + T[1:][n % 23:] + T[1:][:n % 23]
        for i in range(12):
            a, b = giro[i], giro[23 - i]
            pa, pb = punti(a) + 3, punti(b)
            db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince, convalidato)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())""", (S, n, a, b, round(pa, 1), round(pb, 1), "casa" if pa > pb else "trasferta"))
    righe_prima = db.q("SELECT COUNT(*) AS n FROM lega_risultati", one=True)["n"]
    out = io.StringIO()
    sys.argv = ["verifica_scenari.py", S]
    with contextlib.redirect_stdout(out):
        runpy.run_path(_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "strumenti", "verifica_scenari.py"), run_name="__main__")
    o = out.getvalue()
    print(o)
    ok("1. FORMA" in o and "2. PROVA" in o and "3. CALIBRAZIONE" in o, "le tre parti")
    riga = lambda k: next(l for l in o.splitlines() if l.strip().startswith(k)).split()
    ok(riga("50/50")[-2:] == ["0.2500", "0.6931"], "50/50: Brier 0,25 e log loss 0,693")
    ok(float(riga("normale, media pesata")[-2]) < 0.25, "il motore fa meglio del 50/50")
    asim = float(o.split("asimmetria ")[1].split()[0])
    ok(asim > 0.3, f"punteggi con più exploit che crolli: asimmetria positiva ({asim})")
    ok(db.q("SELECT COUNT(*) AS n FROM lega_risultati", one=True)["n"] == righe_prima, "sola lettura: non scrive niente")
finally:
    open(config.TEAMS_PATH, "w").write(_teams)
    for t in ("lega_giornate", "lega_risultati", "lega_partite"):
        db.q(f"TRUNCATE {t}")

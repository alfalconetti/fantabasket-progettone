import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.14.0 (Luca, 15/11): /rendimento_team. Giornate convalidate della squadra (regular season e playoff), vinte e
perse, casa e trasferta, media e posizione nella lega, ultime 5, migliore e peggiore, panchina (linea, riga, posizione,
supplementari, giornate senza), fascia dei nostri playoff, cache delle panchine, immagine, comando."""
import asyncio
import types
from datetime import date

import db, config
import rendimento_team as RT
import risultati as R
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()
S = config.stagione()
Y = int(S) + 1
for t in ("lega_giornate", "lega_risultati", "lega_partite", "lega_calcoli"):
    db.q(f"TRUNCATE {t}")
T = [t["id"] for t in config.squadre()][:4]
a, b, c, d = T
# 6 giornate di regular season e 2 di playoff (a contro b)
cal = {1: [(a, b, 500, 480), (c, d, 450, 470)], 2: [(b, a, 520, 470), (d, c, 460, 400)], 3: [(a, c, 560, 440), (b, d, 430, 431)],
       4: [(d, a, 480, 410), (c, b, 470, 500)], 5: [(a, d, 505, 499), (b, c, 450, 440)], 6: [(c, a, 300, 470), (d, b, 480, 400)],
       7: [(a, b, 530, 500)], 8: [(b, a, 490, 510)]}
for n in cal:
    tipo = "playoff" if n > 6 else "regular"
    db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES (%s, %s, %s, %s, %s)",
         (S, n, tipo, date(Y, 1, n), date(Y, 1, n)))
    for casa, tr, pc, pt in cal[n]:
        vince = "casa" if pc - pt >= 5 else "trasferta"
        db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, supp_casa, supp_trasferta,
                  vince, convalidato) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
             (S, n, casa, tr, pc, pt, 4 if n == 2 else None, 6 if n == 2 else None, vince))
    db.q("INSERT INTO lega_calcoli (stagione, giornata, stato, risultati) VALUES (%s, %s, 'convalidata', '[]')", (S, n))
chiamate = []
def finto_calcola(s, n, *k, **kw):
    chiamate.append(n)
    out = []
    for casa, tr, _pc, _pt in cal[n]:
        pan = lambda t: None if (t == a and n == 4) else [{"fp": 100.0 + n}, {"fp": 50.0, "doppio": t == b}, {"fp": 20.5}]
        out.append({"casa": casa, "trasferta": tr, "sc": {"panchina": pan(casa)}, "st": {"panchina": pan(tr)}})
    return {"risultati": out}
_vero = R.calcola
R.calcola = finto_calcola
try:
    RT._cache.clear()
    x = RT.dati(a, S)
    gg = x["giornate"]
    ok([g["cod"] for g in gg] == ["G1", "G2", "G3", "G4", "G5", "G6", "P1", "P2"], f"giornate della squadra, P dopo la regular season {[g['cod'] for g in gg]}")
    ok([g["v"] for g in gg] == [True, False, True, False, True, True, True, True], f"vinte e perse {[g['v'] for g in gg]}")
    ok([g["casa"] for g in gg][:4] == [True, False, True, False] and gg[3]["fatti"] == 410 and gg[3]["subiti"] == 480,
       "casa e trasferta, punti fatti e subiti dal lato giusto")
    ok(x["sotto"].startswith(f"Stagione {S}-") and " · 4-2 · " in x["sotto"] and "in casa 3-0, in trasferta 1-2" in x["sotto"] and "playoff 2-0" in x["sotto"],
       f"testata: record, casa e trasferta, playoff ({x['sotto']})")
    m_rs = (500 + 470 + 560 + 410 + 505 + 470) / 6
    ok(x["media"] == round(m_rs, 2) and "regular season" in x["riquadri"][0]["s"], "media della regular season (coi playoff lo dice)")
    ok(x["riquadri"][2]["v"].startswith("560") and "G3 vs" in x["riquadri"][2]["s"] and "G4" in x["riquadri"][3]["s"], "migliore e peggiore con l'avversario")
    ok(gg[4]["mobile"] is not None and gg[3]["mobile"] is None, "media delle ultime 5 dalla quinta")
    ok(gg[0]["panchina"] == 171.5 and gg[3]["panchina"] is None, "panchina: somma dei fantapunti; non mandata → niente")
    ok("1 supplementare (vinto 0)" in x["panchina"] and "1 giornata senza panchina" in x["panchina"] and "della lega" in x["panchina"],
       f"riga della panchina: {x['panchina']}")
    ok(x["fanta"] == {"da": 6, "a": 7}, "fascia gialla sulle giornate dei nostri playoff")
    n_prima = len(chiamate)
    RT.dati(b, S)
    ok(len(chiamate) == n_prima, "panchine in memoria: un'altra squadra non ricalcola")
    db.q("UPDATE lega_calcoli SET versione = 2 WHERE stagione = %s AND giornata = 1", (S,))
    RT.dati(b, S)
    ok(chiamate[n_prima:] == [1], "giornata ricalcolata (versione nuova): solo quella si ricalcola")
    db.q("DELETE FROM lega_risultati WHERE stagione = %s AND giornata > 2", (S,))
    ok(RT.dati(a, S) is None, "meno di 3 giornate: niente grafico")
    db.q("TRUNCATE lega_risultati")
    for n in cal:
        for casa, tr, pc, pt in cal[n]:
            db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince, convalidato)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())""", (S, n, casa, tr, pc, pt, "casa" if pc - pt >= 5 else "trasferta"))
    try:
        import typst  # noqa: F401
        png = RT.immagine(RT.dati(a, S))
        ok(png[:4] == b"\x89PNG", "immagine")
        if _os.environ.get("RT_PNG"):
            open(_os.environ["RT_PNG"], "wb").write(png)
        foto = []
        class Msg:
            async def reply_photo(self, photo, caption=None, **k): foto.append(caption)
            async def reply_text(self, t, **k): foto.append(t)
        upd = types.SimpleNamespace(effective_message=Msg(), effective_user=types.SimpleNamespace(id=999))
        asyncio.run(RT.cmd_rendimento_team(upd, types.SimpleNamespace(args=[config.nome(a)])))
        ok(foto and foto[-1].startswith("📈 Rendimento di"), "/rendimento_team SQUADRA: l'immagine")
        asyncio.run(RT.cmd_rendimento_team(upd, types.SimpleNamespace(args=[])))
        ok(foto[-1].startswith("Uso: /rendimento_team"), "senza squadra e senza essere GM: l'uso")
    except ImportError:
        pass
finally:
    R.calcola = _vero
    for t in ("lega_giornate", "lega_risultati", "lega_partite", "lega_calcoli"):
        db.q(f"TRUNCATE {t}")

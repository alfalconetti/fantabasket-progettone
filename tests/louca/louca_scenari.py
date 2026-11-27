import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.37.0: scenari di fine regular season. Le certezze (stato, seed possibili, cosa serve, posto in lottery) su una
classifica costruita a mano; poi dal DB: partite rimaste, simulazioni (probabilità coerenti, stesso seme stessi
numeri), immagini, /scenari e l'album sul canale alla convalida delle ultime 5 giornate, una volta per giornata."""
import asyncio
import json
import types
from datetime import date, timedelta

import db, config
import scenari as SC
import playoff as PO
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)

# ── certezze, senza DB ──
O = [f"O{i}" for i in range(1, 13)]
E = [f"E{i}" for i in range(1, 13)]
vinte = dict(zip(O, [20, 19, 15, 14, 14, 13, 13, 12, 10, 8, 5, 4])) | dict(zip(E, [18, 17, 16, 15, 14, 13, 3, 4, 0, 6, 7, 9]))
sq = O + E
rim = [(1, sq[i], sq[i + 1]) for i in range(0, 24, 2)] + [(2, sq[i], sq[23 - i]) for i in range(12)]
sit = {"squadre": sq, "st": {t: {"w": vinte[t]} for t in sq}, "rimaste": rim, "campione": "O6",
       "conf": {t: ("Ovest" if t[0] == "O" else "Est") for t in sq}}
c = SC.certezze(sit)
ok(c["O1"]["stato"] == "bye" and c["O1"]["seed"] == (1, 2), f"20 vittorie, la seconda ne può fare 21: bye sicuro {c['O1']}")
ok(c["O3"]["stato"] == "corsa" and c["O3"]["serve"].startswith("Playoff sicuri con 1 vittoria (già adesso se vince"),
   f"15 vittorie: sicura con una, già adesso se vince gli spareggi {c['O3']['serve']}")
ok(c["O8"]["stato"] == "corsa" and c["O8"]["serve"] == "Non dipende solo da lei: anche vincendole tutte servono altri risultati · fuori alla prima sconfitta",
   f"12 vittorie: con 13 la campione della Cup (13) le passa davanti, fuori alla prima sconfitta {c['O8']['serve']}")
ok(c["O11"]["stato"] == "fuori" and c["O11"]["serve"] == "", "5 vittorie e 2 da giocare: eliminata")
ok(c["E9"]["lotto"] == (1, 1) and c["E9"]["frase_lottery"] == "Record peggiore sicuro", f"0 vittorie, tutte le altre almeno 3: ultima sicura {c['E9']}")
ok(c["O1"]["lotto"] is None, "chi è già ai playoff non è nella lottery")
ok(c["E7"]["lotto"][0] == 2 and "non può più avere il record peggiore" in c["E7"]["frase_lottery"].lower(), f"E7: dalla 2ª in giù {c['E7']}")
# la campione della Cup vince i pari: O6 con 13 (max 15) contro O3 con 15
sit2 = {**sit, "campione": "O3"}
c2 = SC.certezze(sit2)
ok(c2["O3"]["seed"][1] < c["O3"]["seed"][1], "la vincitrice della Quasi Cup vince i pari: seed peggiore possibile più alto")
ok("fuori se le perde tutte" in c2["O8"]["serve"], f"senza la campione a 13: fuori solo se le perde tutte {c2['O8']['serve']}")
# medie pesate: le ultime 5 contano il triplo, dalla 6ª alla 10ª il doppio
ok([SC.peso(i) for i in (0, 4, 5, 9, 10, 30)] == [3, 3, 2, 2, 1, 1], "pesi: ultime 5 ×3, 6ª-10ª ×2, le altre ×1")
_p = lambda punti: {"x": {"partite": [{"giornata": g, "fatti": f, "casa": False} for g, f in enumerate(punti, 1)]}}
mu, _, _ = SC.parametri(_p([90] * 10 + [110] * 5), 3)["x"]
ok(abs(mu - (90 * 5 + 90 * 2 * 5 + 110 * 3 * 5) / 30) < 1e-9, f"10 partite da 90 e le ultime 5 da 110: media pesata {mu:.2f} (semplice 96,67)")
mu_casa, _, _ = SC.parametri({"x": {"partite": [{"giornata": g, "fatti": 103, "casa": True} for g in range(1, 8)]}}, 3)["x"]
ok(mu_casa == 100, "il bonus casa tolto prima della media")
# ── dal DB ──
CFG = _os.path.dirname(config.TEAMS_PATH)
_teams = open(config.TEAMS_PATH, encoding="utf-8").read()
_glob = open(config.GLOBALS_PATH, encoding="utf-8").read()
_div_path = _os.path.join(CFG, "divisions.json")
_div = open(_div_path, encoding="utf-8").read() if _os.path.exists(_div_path) else None
T = [f"sc{i:02d}" for i in range(1, 25)]
json.dump({"teams": [{"id": t, "nome": f"Squadra {t[-2:]}", "gm_ids": [], "gm_nome": t} for t in T]}, open(config.TEAMS_PATH, "w"))
json.dump({"conference": {"Ovest": ["O"], "Est": ["E"]}, "team_div": {t: ("O" if i % 2 else "E") for i, t in enumerate(T)}},
          open(_div_path, "w"))
try:
    db.init_db(); PO.migra()
    S = config.stagione()
    for t in ("lega_giornate", "lega_risultati", "lega_partite", "lega_avvisi_playoff"):
        db.q(f"TRUNCATE {t}")
    Y = int(S) + 1
    forza = {t: 120 - i * 1.5 for i, t in enumerate(T)}            # sc01 la più forte
    for n in range(1, 11):
        dal = date(Y, 1, 1) + timedelta(days=7 * n)
        db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES (%s, %s, 'regular', %s, %s)", (S, n, dal, dal + timedelta(days=6)))
        giro = T[:1] + T[1:][n % 23:] + T[1:][:n % 23]               # metodo del cerchio
        for i in range(12):
            a, b = giro[i], giro[23 - i]
            db.q("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES (%s, %s, %s, %s)", (S, n, a, b))
            if n <= 7:
                pa, pb = forza[a] + 3 + (n * 7 + i) % 9, forza[b] + (n * 5 + i) % 11
                db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince, convalidato)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())""", (S, n, a, b, pa, pb, "casa" if pa > pb else "trasferta"))
    sit = SC.situazione(S)
    ok(sit["ultima"] == 7 and len(sit["rimaste"]) == 36 and {g for g, _, _ in sit["rimaste"]} == {8, 9, 10},
       "partite rimaste: le 3 giornate non convalidate, 12 partite ciascuna")
    sim = SC.simula(sit, 2000)
    ok(all(sum(sim["po"][t] for t in T if sit["conf"][t] == c) == 6 * 2000 for c in ("Ovest", "Est")), "6 per conference ai playoff in ogni giro")
    ok(all(sum(sim["lotto"][t][k] for t in T) == 2000 for k in range(12)), "ogni posto della lottery assegnato una volta per giro")
    ok(abs(sum(sim["pick1"].values()) - 2000) < 1e-6, "la 1ª scelta: le probabilità sommano a 1")
    ok(sim["po"]["sc01"] > sim["po"]["sc23"], "la più forte va ai playoff più spesso della più debole")
    cert = SC.certezze(sit)
    smentite = [t for t in T if (cert[t]["stato"] in ("bye", "dentro") and sim["po"][t] < 2000)
                or (cert[t]["stato"] == "fuori" and sim["po"][t] > 0) or (cert[t]["stato"] == "bye" and sim["bye"][t] < 2000)]
    ok(not smentite, f"nessuna certezza smentita dalle simulazioni {smentite}")
    ok(SC.simula(sit, 300)["po"] == SC.simula(sit, 300)["po"], "stesso seme (stagione e giornata): stessi numeri")
    _d = SC.DERIVA
    SC.DERIVA = 0.0
    fermo = SC.simula(sit, 2000)
    SC.DERIVA = 4.0
    mosso = SC.simula(sit, 2000)
    SC.DERIVA = _d
    estremi = lambda x: sum(1 for t in T if x["po"][t] in (0, 2000))
    ok(estremi(mosso) <= estremi(fermo), f"con la forza che si muove meno squadre sempre dentro o sempre fuori ({estremi(mosso)} contro {estremi(fermo)})")
    ok(sim["prossima"] == 8 and len(sim["chiave"]) == 12, "partite chiave: le 12 della G8")
    imm, d = SC.calcola(S, 500)
    ok([n for n, _ in imm][:2] == ["Ovest", "Est"] and all(p[:4] == b"\x89PNG" for _, p in imm), f"immagini: le conference, poi la lottery {[n for n, _ in imm]}")
    ok(d["mancano"] == 3 and "G7" in SC.didascalia(d) and "mancano 3 giornate" in SC.didascalia(d), "didascalia")
    ok(all(r["po"] <= 100 and r["bye"] <= r["po"] for c in d["conferenze"] for r in c["righe"]), "percentuali sensate (bye ≤ playoff)")

    # canale alla convalida: solo quando mancano 5 o meno, una volta per giornata
    mandati = []
    class Bot:
        async def send_media_group(self, chat_id, media, **k): mandati.append((chat_id, len(media), media[0].caption))
    g = json.loads(_glob); g["main_channel_id"] = -100123; g["fase"] = "regular-season-fa"
    json.dump(g, open(config.GLOBALS_PATH, "w"))
    SC.SIMULAZIONI = 300
    _calcola = SC.calcola
    SC.calcola = lambda s, n=300: _calcola(s, 300)
    ok(SC.mancano_dopo(S, 4) == 6 and asyncio.run(SC.dopo_convalida(Bot(), S, 4)) == "" and not mandati, "mancano 6: niente")
    r = asyncio.run(SC.dopo_convalida(Bot(), S, 7))
    ok("canale" in r and mandati and mandati[0][0] == -100123 and mandati[0][1] == len(imm) and "Scenari" in mandati[0][2],
       f"dopo la G7 (mancano 3): l'album sul canale {mandati}")
    ok(asyncio.run(SC.dopo_convalida(Bot(), S, 7)) == "" and len(mandati) == 1, "convalida rifatta: non li rimanda")
    ok(asyncio.run(SC.dopo_convalida(Bot(), S, 10)) == "", "dopo l'ultima: niente (la classifica è finale)")

    # /scenari
    risposte = []
    class Msg:
        chat_id, message_id = 5, 9
        async def reply_text(self, t, **k):
            risposte.append(t)
            class A:
                async def edit_text(s, t, **k): risposte.append(t)
                async def delete(s): pass
            return A()
    up = types.SimpleNamespace(effective_message=Msg())
    asyncio.run(SC.cmd_scenari(up, types.SimpleNamespace(bot=Bot())))
    ok(len(mandati) == 2 and mandati[1][0] == 5, f"/scenari in regular season: l'album in risposta {risposte}")
    g["fase"] = "playoff"; json.dump(g, open(config.GLOBALS_PATH, "w"))
    asyncio.run(SC.cmd_scenari(up, types.SimpleNamespace(bot=Bot())))
    ok("solo in regular season" in risposte[-1], "fuori dalla regular season: lo dice")
finally:
    SC.calcola = _calcola if "_calcola" in dir() else SC.calcola
    open(config.TEAMS_PATH, "w").write(_teams)
    open(config.GLOBALS_PATH, "w").write(_glob)
    if _div is None:
        _os.remove(_div_path)
    else:
        open(_div_path, "w").write(_div)
    for t in ("lega_giornate", "lega_risultati", "lega_partite", "lega_avvisi_playoff"):
        db.q(f"TRUNCATE {t}")

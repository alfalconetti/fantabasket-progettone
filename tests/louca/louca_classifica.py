import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""loucabot v27: classifica (ordine con la classifica avulsa, voci di /classifica e /classifica_full,
immagini Typst) dai risultati convalidati."""
import json
import db, config, classifica as C
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()

def r(g, casa, tr, pc, pt, vince=None, supp=False):
    return {"giornata": g, "casa": casa, "trasferta": tr, "punti_casa": pc, "punti_trasferta": pt,
            "supp_casa": 5.0 if supp else None, "supp_trasferta": 3.0 if supp else None,
            "vince": vince or ("casa" if pc - pt >= 5 else "trasferta")}

T = ["A", "B", "C", "D"]
# A, B, C a 2 vittorie: A batte B, B batte C, C batte A (avulsa pari: 1-1 ciascuna) → media punti
# D a 0. Poi A–D e B–D vinte, C–D vinta: tutte e tre 2-1? No: costruiamo direttamente
ris = [r(1, "A", "B", 110, 100), r(1, "C", "D", 120, 90),
       r(2, "B", "C", 105, 95), r(2, "D", "A", 80, 130),
       r(3, "C", "A", 115, 100), r(3, "B", "D", 99, 98, vince="casa", supp=True)]
st = C.base(ris, T)
ok([st[t]["w"] for t in T] == [2, 2, 2, 0], "vittorie e sconfitte")
ok(C.ordina(st) == ["A", "C", "B", "D"], f"tre a pari con avulsa 1-1 tra loro: poi media punti fatti {C.ordina(st)}")
# due a pari: vince lo scontro diretto anche con la media più bassa
ris2 = ris + [r(4, "A", "D", 100, 200), r(4, "C", "B", 90, 120)]          # A e C 2-2 ... B 3-1
st2 = C.base(ris2, T)
ok(st2["B"]["w"] == 3 and C.ordina(st2)[:3] == ["B", "C", "A"] and st2["A"]["media"] > st2["C"]["media"],
   f"due a pari (A, C): conta lo scontro diretto (C ha battuto A), non la media {C.ordina(st2)}")
ok(st2["C"]["striscia"] == "1L" and st2["B"]["striscia"] == "3W" and st2["A"]["striscia"] == "2L", "striscia: 3W, 1L, 2L")
C.extra(ris2, st2)
ok(st2["D"]["migliore"] == 1 and st2["A"]["max"] == 130 and st2["A"]["min"] == 100, "migliore di giornata, massimo e minimo")
ok((st2["A"]["rec_pos_subiti"], st2["A"]["rec_neg_subiti"], st2["D"]["rec_pos_subiti"], st2["D"]["rec_neg_subiti"]) == (1, 1, 2, 2),
   "record subiti: l'avversario ha fatto contro di te il suo massimo / minimo della stagione")
ok(st2["B"]["supp"] == 1 and st2["B"]["supp_w"] == 1 and st2["B"]["vantaggio"] == 20.0,
   f"supplementari contati a parte, vantaggio medio senza supplementari {st2['B']['vantaggio']}")
ok(st2["A"]["n_ult"] == 4, "media sulle ultime n (meno di 10)")
# quintetto migliore possibile: per ruolo il più alto per fantapunti, non lo schierato
ros = [{"espn_id": "1", "ruolo": "PG"}, {"espn_id": "2", "ruolo": "PG"}, {"espn_id": "3", "ruolo": "C"}, {"espn_id": "4", "ruolo": "SF"}]
q = C.miglior_quintetto(ros, {"1": {"media": 20.0}, "2": {"media": 31.5}, "3": {"media": 12.0}})
ok([x["espn_id"] for x in q] == ["2", "4", "3"], "quintetto migliore: il PG da 31,5 e non quello da 20, un giocatore per ruolo")
# per conference: filtro della generale, ex aequo risolti sulla generale
righe_g = [{**st2[t], "pos": i + 1} for i, t in enumerate(C.ordina(st2))]
config.nome = lambda t: t
dc = C.dati_conference(righe_g, 4, {"A": "Est", "D": "Est", "B": "Ovest", "C": "Ovest"})
ok([(x["nome"], [(y["nome"], y["pos"], y["gen"]) for y in x["righe"]]) for x in dc["sezioni"]]
   == [("Ovest", [("B", 1, 1), ("C", 2, 2)]), ("Est", [("A", 1, 3), ("D", 2, 4)])],
   "per conference: stesso ordine della generale, posizione nella conference e nella generale")

# ── dal database: risultati convalidati, immagini ──
S = config.stagione()
db.q("TRUNCATE lega_risultati")
squadre = [t["id"] for t in config.squadre()]
a, b, c, d = squadre[:4]
for x in [r(1, a, b, 110, 100), r(1, c, d, 120, 90), r(2, b, c, 105, 95)]:
    db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, supp_casa, supp_trasferta, vince, convalidato)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
         (S, x["giornata"], x["casa"], x["trasferta"], x["punti_casa"], x["punti_trasferta"], x["supp_casa"], x["supp_trasferta"], x["vince"]))
db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince)
        VALUES (%s, 3, %s, %s, 200, 10, 'casa')""", (S, a, b))                # non convalidata: non conta
righe, gg = C.calcola(S, full=True)
ok(gg == 2 and righe[0]["team"] in (a, c) and next(x for x in righe if x["team"] == a)["w"] == 1,
   "solo le giornate convalidate")
try:
    import typst  # noqa: F401
    png, _ = C.immagine(False, S)
    png2, _ = C.immagine(True, S)
    _conf = C.conference
    C.conference = lambda: {a: "Est", b: "Est", c: "Ovest", d: "Ovest"}
    png3, _ = C.immagine(False, S, per_conference=True)
    C.conference = lambda: {}
    try:
        C.immagine(False, S, per_conference=True); senza = False
    except RuntimeError as err:
        senza = "divisions.json" in str(err)
    C.conference = _conf
    ok(png3[:4] == b"\x89PNG" and senza, "immagine per conference; senza conference configurate lo dice")
    ok(png[:8] == b"\x89PNG\r\n\x1a\n" and png2[:8] == b"\x89PNG\r\n\x1a\n", "immagini di /classifica e /classifica_full")
except ImportError:
    print("(typst non installato: immagini non provate)")
# migliore in verde e peggiore in rosso per colonna, tranne V/S (Luca, 28/10)
_rr = [{"team": "a", "pf": 100, "ps": 90, "diff": 10, "media": 100}, {"team": "b", "pf": 80, "ps": 70, "diff": 10, "media": 80},
       {"team": "c", "pf": 100, "ps": 95, "diff": 5, "media": 90}]
_col = C.colori(_rr, False)
ok(_col["a"]["pf"] == "best" and _col["c"]["pf"] == "best" and _col["b"]["pf"] == "worst"
   and _col["b"]["ps"] == "best" and _col["c"]["ps"] == "worst" and _col["c"]["diff"] == "worst" and "diff" in _col["a"]
   and all("w" not in x and "l" not in x for x in _col.values()),
   "classifica: migliore e peggiore di ogni colonna (punti subiti: il più basso è il migliore; a pari merito tutti)")
_rr2 = [dict(r, pf=50) for r in _rr]
ok(all("pf" not in x for x in C.colori(_rr2, False).values()), "colonna tutta uguale: niente colori")
_righe, _g = C.calcola(S, True)
if _g:
    _d = C.dati_typst(_righe, _g, True)
    ok(all("col" in x for x in _d["righe"]) and any(x["col"] for x in _d["righe"]), "nei dati dell'immagine i colori per riga")
db.q("TRUNCATE lega_risultati")
ok(C.immagine(False, S) == (None, 0), "nessuna giornata convalidata: niente immagine")

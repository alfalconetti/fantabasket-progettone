import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.9.5 (Luca, 14/11): calendario dei playoff da CSV (giornata, giorno1[, giorno2][, giorno3][, squadre a media]),
P1 = la giornata dopo l'ultima di regular season, codici G/P sinonimi (senza lettera: G in regular season, P nei
playoff), controllo delle squadre a media."""
import json
from datetime import date, datetime, timezone

import db, config
import calendario_playoff as CP
from shared import codici_giornata as CG
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()
CP.migra()
S = config.stagione()
Y = int(S) + 1
for t in ("lega_giornate", "lega_giornate_playoff"):
    db.q(f"TRUNCATE {t}")
db.q("DELETE FROM nba_partite WHERE espn_id LIKE 'pc%%'")
ok(CG.ultima_rs(S) is None and CG.numero("P1") is None and CG.numero("G5") == 5 and CG.numero("7") == 7,
   "senza calendario: P non si traduce, G e i numeri sì")
try:
    CP.importa("P1,18/04/2027", S); _e = ""
except CP.Errore as err:
    _e = str(err)
ok("regular season" in _e, "senza calendario di regular season non si importa")
for n, dal, al in ((1, date(Y, 3, 29), date(Y, 4, 4)), (2, date(Y, 4, 5), date(Y, 4, 11)), (3, date(Y, 4, 12), date(Y, 4, 17))):
    db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES (%s, %s, 'regular', %s, %s)", (S, n, dal, al))
ok(CG.ultima_rs(S) == 3 and CG.numero("P1") == 4 and CG.numero("p22") == 25 and CG.numero("P23") is None
   and CG.numero("g41") == 41 and CG.numero("2") == 2 and CG.codice(5) == "P2 (G5)" and CG.codice(3) == "G3",
   "P1 = la giornata dopo l'ultima di regular season; G resta G; codice")
_g = json.load(open(config.GLOBALS_PATH))
json.dump({**_g, "fase": "playoff"}, open(config.GLOBALS_PATH, "w"))
ok(CG.numero("2") == 5 and CG.numero("G2") == 2, "nella fase playoff un numero senza lettera è P")
json.dump(_g, open(config.GLOBALS_PATH, "w"))

csv = ("giornata;giorno1;giorno2;giorno3\nP1;18/04/2027;19/04/2027;20/04/2027\nG5;21/04;22/04\n"
       "3,2027-04-23,2027-04-24,2027-04-25,mia bos\n")
gg = CP.importa(csv, S)
ok([g["numero_p"] for g in gg] == [1, 2, 3] and gg[0]["dal"] == date(2027, 4, 18) and gg[0]["al"] == date(2027, 4, 20)
   and gg[1]["giorni"] == [date(2027, 4, 21), date(2027, 4, 22)] and gg[2]["media_file"] == ["BOS", "MIA"],
   "import: intestazione, «;» e «,», P1, G5 = P2, numero solo, date in tre formati, squadre a media in fondo")
ok(len(CP.giornate(S)) == 3, "salvate in lega_giornate_playoff")
ok(db.q("SELECT count(*) AS n FROM lega_giornate WHERE stagione = %s AND tipo <> 'regular'", (S,), one=True)["n"] == 0,
   "le giornate P non entrano ancora nel calendario (si fa col passaggio ai playoff)")


def errore(t):
    try:
        CP.importa(t, S)
        return ""
    except CP.Errore as err:
        return str(err)


ok("non sono consecutivi" in errore("P1,18/04/2027,20/04/2027"), "giorni non consecutivi")
ok("da 1 a 3" in errore("P1,18/04/2027,19/04/2027,20/04/2027,21/04/2027"), "più di tre giorni")
ok("di seguito da P1" in errore("P1,18/04/2027\nP3,20/04/2027"), "numerazione con un buco")
ok("prima della fine di P1" in errore("P1,18/04/2027,19/04/2027\nP2,19/04/2027"), "giornate sovrapposte")
ok("fuori dai playoff" in errore("P23,18/04/2027"), "oltre P22")
ok("prima della fine dell'ultima giornata di regular season" in errore("P1,16/04/2027"), "P1 dentro la regular season")
ok("non è una data" in errore("P1,18/04/2027,boh!"), "una cella storta")
ok(len(CP.giornate(S)) == 3, "un import sbagliato non tocca quello di prima")

# controllo: prima partita e squadre a media dalle partite NBA
for i, (casa, tr) in enumerate((("MIA", "NYK"), ("LAL", "DEN"))):
    db.q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES (%s, %s, 2, %s, %s, %s, %s, 'STATUS_SCHEDULED')",
         (f"pc{i}", S, date(2027, 4, 23), datetime(2027, 4, 23, 23, 30, tzinfo=timezone.utc), casa, tr))
for i, (casa, tr) in enumerate((("MIA", "NYK"), ("LAL", "DEN"), ("BOS", "PHI"))):
    db.q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES (%s, %s, 2, %s, %s, %s, %s, 'STATUS_FINAL')",
         (f"pcr{i}", S, date(Y, 3, 30), datetime(Y, 3, 30, 23, 30, tzinfo=timezone.utc), casa, tr))
t = CP.controllo(S)
ok("P1 = G4" in t and "<b>P3</b> (G6)" in t and "nessuna partita NBA" in t and "a media: BOS, PHI ⚠️ nel file: BOS, MIA" in t,
   "controllo: G corrispondente, giornate senza partite NBA, squadre a media calcolate diverse dal file\n" + t)
db.q("DELETE FROM nba_partite WHERE espn_id LIKE 'pc%%'")
for t_ in ("lega_giornate", "lega_giornate_playoff"):
    db.q(f"TRUNCATE {t_}")

# il tabellone approvato (mockup del 14/11) col suo esempio: deve restare compilabile
try:
    import typst
    _d = open(_os.path.join(_os.getcwd(), "docs", "playoff_esempio.json"), encoding="utf-8").read()
    ok(typst.compile(_os.path.join(_os.getcwd(), "playoff.typ"), root="/", format="png", ppi=60,
                     sys_inputs={"dati": _d})[:4] == b"\x89PNG", "playoff.typ (mockup approvato) si compila con l'esempio")
except ImportError:
    print("(typst non installato: tabellone non provato)")

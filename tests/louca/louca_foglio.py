import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""loucabot: il calendario sul foglio Google. Dal CSV importato (mappa delle righe del foglio)
si costruiscono i blocchi da mandare allo script: intestazione con le squadre a media
calcolate, punteggi regolamentari e supplementari in B e D, None per le celle da non toccare."""
import asyncio
import db, calendario as cal, foglio
db.init_db()
db.q("TRUNCATE lega_giornate, lega_partite, lega_risultati, lega_calendario_csv, nba_partite, nba_tabellini")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)

# come il CSV vero: per ogni partita la riga delle squadre e tre righe vuote (la prima è dei supplementari)
CSV = ("Week 1 20/10 - 22/10,,,,\r\nAlfa,,V,,Beta\r\n,,,,\r\n,,,,\r\n,,,,\r\nGamma,,V,,Delta\r\n,,,,\r\n,,,,\r\n,,,,\r\n"
       "\"Week 2 23/10 - 24/10 (media DAL,LAL)\",,,,\r\nDelta,,V,,Alfa\r\n,,,,\r\n,,,,\r\n,,,,\r\nBeta,,V,,Gamma\r\n,,,,\r\n")
cal.importa(CSV, "2026")
ok(db.csv_calendario("2026") == CSV, "all'import il CSV si conserva tale e quale (è la mappa del foglio)")
db.q("UPDATE lega_giornate SET media = %s WHERE stagione = '2026' AND numero = 1", (["OKC"],))
db.q("UPDATE lega_giornate SET media = %s WHERE stagione = '2026' AND numero = 2", ([],))
db.q("INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince) "
     "VALUES ('2026', 1, 'team01', 'team02', 110.5, 98.25, 'casa')")
db.q("INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, supp_casa, supp_trasferta, vince) "
     "VALUES ('2026', 2, 'team04', 'team01', 100, 103, 120.75, 131, 'trasferta')")
B = foglio.blocchi("2026")
ok([b["numero"] for b in B] == [1, 2], "un blocco per giornata")
r1, r2 = B[0]["righe"], B[1]["righe"]
ok(r1[0] == ["Week 1 20/10 - 22/10 (media OKC)", None, None, None, None], f"intestazione con le squadre a media calcolate {r1[0]}")
ok(r1[1] == [None, 110.5, None, 98.25, None] and len(r1) == 2,
   "punteggi regolamentari in B e D; senza supplementari la riga sotto non si tocca; righe vuote finali tolte")
ok(r2[0][0] == "Week 2 23/10 - 24/10", "media calcolata vuota: la nota sparisce dall'intestazione")
ok(r2[1] == [None, 100.0, None, 103.0, None] and r2[2] == [None, 120.75, None, 131.0, None],
   "supplementari subito sotto la riga delle squadre")
ok(all(r[0] is None and r[2] is None and r[4] is None for b in B for r in b["righe"][1:]),
   "nomi delle squadre e V mai riscritti")
ok(foglio.intestazione("Week 3 1/1 - 2/1 (media cle, den)", None) == "Week 3 1/1 - 2/1 (media cle, den)",
   "giornata non ancora calcolata: intestazione com'è")

inviati = []
async def manda(p):
    inviati.append(p)
    return {"ok": True, "celle": 7, "non_trovate": [2]}
esito = asyncio.run(foglio.aggiorna("2026", manda=manda))
ok(inviati and inviati[0]["action"] == "calendario" and inviati[0]["blocchi"] == B and "7 celle" in esito and "2" in esito,
   f"invio allo script tramite gas-router, esito con le giornate non trovate: {esito}")
async def rotto(p):
    raise RuntimeError("router giù")
ok(asyncio.run(foglio.aggiorna("2026", manda=rotto)).startswith("⚠️"), "router irraggiungibile: avviso, niente eccezione")
db.q("TRUNCATE lega_giornate, lega_partite, lega_risultati, lega_calendario_csv")
ok(asyncio.run(foglio.aggiorna("2026", manda=manda)) == "nessun calendario importato", "senza calendario non manda niente")

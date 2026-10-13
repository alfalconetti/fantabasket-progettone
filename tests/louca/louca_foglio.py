import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""loucabot: il calendario sul foglio Google. Dal CSV importato si costruisce tutta la pagina\n(colonne A:E): intestazioni con le squadre a media calcolate, punteggi regolamentari e\nsupplementari in B e D."""
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
G = foglio.griglia("2026")
ok(len(G) == 15 and all(len(r) == 5 for r in G), f"tutta la pagina, 5 colonne, righe come il CSV (vuote finali tolte) {len(G)}")
ok(G[0] == ["Week 1 20/10 - 22/10 (media OKC)", "", "", "", ""], f"intestazione con le squadre a media calcolate, testo in A {G[0]}")
ok(G[1] == ["Alfa", 110.5, "V", 98.25, "Beta"] and G[2] == ["", "", "", "", ""],
   "squadre e V dal CSV, punteggi regolamentari in B e D; senza supplementari la riga sotto resta vuota")
ok(G[5] == ["Gamma", "", "V", "", "Delta"], "partita senza risultato: B e D vuote")
ok(G[9] == ["Week 2 23/10 - 24/10", "", "", "", ""], "media calcolata vuota: la nota sparisce dall'intestazione (anche se era tra virgolette)")
ok(G[10] == ["Delta", 100.0, "V", 103.0, "Alfa"] and G[11] == ["", 120.75, "", 131.0, ""],
   "supplementari subito sotto la riga delle squadre")
ok(foglio.intestazione("Week 3 1/1 - 2/1 (media cle, den)", None) == "Week 3 1/1 - 2/1 (media cle, den)",
   "giornata non ancora calcolata: intestazione com'è")
db.q("INSERT INTO lega_calendario_csv (stagione, testo) VALUES ('2027', 'Week 3 1/1 - 2/1 (media cle, den),,,,\nAlfa,,V,,Beta\n')")
ok(foglio.griglia("2027")[0] == ["Week 3 1/1 - 2/1 (media cle, den)", "", "", "", ""],
   "intestazione con virgole non tra virgolette: tutta in A")

inviati = []
async def manda(p):
    inviati.append(p)
    return {"ok": True, "righe": len(p["righe"])}
esito = asyncio.run(foglio.aggiorna("2026", manda=manda))
ok(inviati and inviati[0]["action"] == "calendario" and inviati[0]["righe"] == G and "15 righe" in esito,
   f"invio di tutta la pagina allo script tramite gas-router: {esito}")
async def rotto(p):
    raise RuntimeError("router giù")
ok(asyncio.run(foglio.aggiorna("2026", manda=rotto)).startswith("⚠️"), "router irraggiungibile: avviso, niente eccezione")
db.q("TRUNCATE lega_giornate, lega_partite, lega_risultati, lega_calendario_csv")
ok(asyncio.run(foglio.aggiorna("2026", manda=manda)) == "nessun calendario importato", "senza calendario non manda niente")

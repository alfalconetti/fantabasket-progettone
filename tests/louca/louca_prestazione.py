import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""/prestazione (v7.31.0, Luca 26/11): la singola notte di un giocatore. Senza data l'ultima giocata; una notte giocata
in immagine; DNP, non a referto o infortunato: 0 col motivo, la partita prima e dopo; la squadra non giocava: scegli
prima o dopo; prima dei tabellini, nel futuro, offseason: lo dice."""
import asyncio, os, types
from datetime import date, datetime, timedelta, timezone
import db, config
from shared import prestazione as PR
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()
S = config.stagione()


def pulisci():
    db.q("DELETE FROM nba_tabellini WHERE atleta LIKE 'pr%%' OR partita LIKE 'pr%%'"); db.q("DELETE FROM nba_partite WHERE espn_id LIKE 'pr%%'")
    db.q("DELETE FROM nba_infortuni WHERE atleta LIKE 'pr%%'")
    for r in db.q("SELECT id FROM giocatori WHERE nome_bref LIKE 'Prest %%'", many=True) or []:
        db.q("DELETE FROM transazioni WHERE giocatore_id = %s", (r["id"],)); db.q("DELETE FROM contratti WHERE giocatore_id = %s", (r["id"],))
        db.q("DELETE FROM giocatori WHERE id = %s", (r["id"],))
    db.q("DELETE FROM lega_giornate WHERE stagione = %s AND numero = 977", (S,))


pulisci()
gid = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES ('Prest Uno', 'Prest Uno', 'prest uno', 'pr1') RETURNING id", one=True)["id"]
db.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) VALUES (%s, 'team03', 9, 2, %s, 'normale', TRUE)", (gid, S))
db.q("INSERT INTO transazioni (oggetto, tipo, giocatore_id, team_id_a, stagione, timestamp) VALUES ('giocatore', 'signed', %s, 'team03', %s, '2026-08-01')", (gid, S))
db.q("INSERT INTO lega_giornate (stagione, numero, dal, al) VALUES (%s, 977, '2026-10-25', '2026-10-26')", (S,))
D = lambda m, g: date(2026, m, g)
partite = [("pr0", D(10, 25), "PRA", "PRB", 118, 112), ("pr1", D(10, 27), "PRC", "PRA", 100, 95),
           ("pr2", D(10, 29), "PRA", "PRD", 101, 99), ("pr3", D(10, 31), "PRE", "PRA", 90, 99)]
for pid, d, c, t, pc, pt in partite:
    db.q("""INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato, punti_casa, punti_trasferta)
            VALUES (%s, %s, 2, %s, %s, %s, %s, 'STATUS_FINAL', %s, %s)""", (pid, S, d, datetime(d.year, d.month, d.day, 23, 30, tzinfo=timezone.utc), c, t, pc, pt))
def tab(pid, **k):
    r = {"partita": pid, "atleta": "pr1", "nome": "Prest Uno", "squadra": "PRA", "titolare": True, "giocato": True, "minuti": 0,
         **{x: 0 for x in ("pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf")}, "fp": 0, **k}
    db.q(f"INSERT INTO nba_tabellini ({', '.join(r)}) VALUES ({', '.join(['%s'] * len(r))})", tuple(r.values()))
tab("pr0", minuti=37, pts=31, fgm=11, fga=19, tpm=4, tpa=8, ftm=5, fta=7, oreb=2, dreb=8, ast=11, stl=2, blk=1, tov=4, pf=2, fp=56.75)
tab("pr1", giocato=False, titolare=False)                                   # DNP
tab("pr3", minuti=30, pts=20, fgm=8, fga=15, tpm=2, tpa=5, ftm=2, fta=2, dreb=5, ast=4, stl=1, tov=2, pf=3, fp=28.5)
tab("pr0", atleta="pr9", nome="Altro", squadra="PRB", minuti=30, pts=40, fp=60)  # uno che fa di più quella notte
db.q("INSERT INTO nba_infortuni (giorno, atleta, nome, squadra, stato, dettaglio, preso) VALUES (%s, 'pr1', 'Prest Uno', 'PRA', 'Out', 'Ankle', %s)",
     (D(10, 29), datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)))

n = PR.notte(gid, None)
ok(n["tipo"] == "scheda" and n["giorno"] == D(10, 31), "senza data: l'ultima partita giocata")
n = PR.notte(gid, D(10, 25))
d = PR.dati(gid, n["riga"], n["giorno"], n["rr"])
rq = {r["t"]: r for r in d["riquadri"]}
ok(d["giocato"] and d["contro"] == "vs PRB" and d["esito"] == "V 118–112" and d["vinta"] and rq["Fantapunti"]["v"] == "56,75"
   and "1ª migliore" in rq["Fantapunti"]["s"] and rq["Della notte"]["v"] == "2°", f"la notte del 25/10: avversario, risultato, fantapunti, posto ({rq})")
ok(d["fanta"]["giornata"] == "G977" and d["fanta"]["squadra"] == config.nome("team03") and len(d["riquadri"]) == 4
   and rq["Sulla media fino a lì"]["v"] == "—" and rq["Sulla media stagione"]["v"] == "+14,1", f"la squadra del fantabasket a parte, le due medie {d['fanta']}")
ok("TRIPLA DOPPIA" in d["badge"][0], f"badge {d['badge']}")
tb = {c["t"]: c for c in d["tabella"]}
ok(tb["PTS"]["v"] == "31" and tb["REB"]["v"] == "10" and tb["PTS"]["righe"][1]["m"] == "25,5" and tb["PTS"]["righe"][1]["d"] == "+5,5"
   and tb["TO"]["righe"][1]["buono"] is False and tb["PTS"]["righe"][0]["m"] == "—", "tabellino con la media della stagione e la differenza; prima partita: niente media fino a lì")
n31 = PR.notte(gid, D(10, 31))
d31 = PR.dati(gid, n31["riga"], n31["giorno"], n31["rr"])
t31 = {c["t"]: c for c in d31["tabella"]}
r31 = {r["t"]: r for r in d31["riquadri"]}
ok(t31["PTS"]["righe"][0]["m"] == "31" and t31["PTS"]["righe"][0]["d"] == "−11" and t31["PTS"]["righe"][1]["m"] == "25,5"
   and r31["Sulla media fino a lì"]["v"] == "−28,2" and "media 56,75 in 1 partita" in r31["Sulla media fino a lì"]["s"]
   and r31["Sulla media stagione"]["v"] == "−14,1", f"v7.31.1: la media fino a quella notte e quella della stagione ({r31})")
ok(d["tiri"][0]["v"] == "11/19" and "57,9%" in d["tiri"][0]["s"] and "stagione 55,9%" in d["tiri"][0]["s"], "i tiri")
ok(d["voci"][0]["n"] == "Assist" and d["voci"][0]["pt"] == "+22" and d["voci"][-1]["pt"].startswith("−") and d["totale"] == "56,75"
   and not d["correzione"], "come nascono i fantapunti, la somma torna")
ok(d["dopo"].startswith("Dopo: sab 31/10 @ PRE") and d["prima"] == "", "prima e dopo (giocate)")
n = PR.notte(gid, D(10, 27))
d = PR.dati(gid, n["riga"], n["giorno"], n["rr"], motivo=n["motivo"])
ok(n["tipo"] == "scheda" and not d["giocato"] and d["riquadri"][0]["v"] == "0" and "DNP" in d["motivo"] and "25/10" in d["prima"] and "31/10" in d["dopo"],
   "DNP: 0 col motivo, la giocata prima e quella dopo")
n = PR.notte(gid, D(10, 29))
ok(n["tipo"] == "scheda" and n["riga"] is None and n["motivo"].startswith("Out"), f"non a referto e infortunato: 0 con lo status ({n['motivo']})")
n = PR.notte(gid, D(10, 26))
ok(n["tipo"] == "scegli" and n["prima"]["partita"] == "pr0" and n["dopo"]["partita"] == "pr3", "la squadra non giocava: scegli prima o dopo")
ok(PR.notte(gid, D(9, 1))["tipo"] == "testo" and "22/10/2026" in PR.notte(gid, D(9, 1))["testo"], "prima dei tabellini: lo dice")
ok("non è ancora arrivato" in PR.notte(gid, date.today() + timedelta(days=3))["testo"], "nel futuro: lo dice")
ok(PR.offseason(date(2031, 8, 1)) and not PR.offseason(D(10, 26)), "offseason: niente partite NBA intorno")
ok(PR.leggi(["Prest", "Uno", "25/10/2026"]) == ("Prest Uno", D(10, 25)) and PR.leggi(["Prest", "Uno"]) == ("Prest Uno", None), "nome e data")
# l'immagine
n = PR.notte(gid, D(10, 25))
img = PR.immagine(PR.dati(gid, n["riga"], n["giorno"], n["rr"]))
n2 = PR.notte(gid, D(10, 27))
img2 = PR.immagine(PR.dati(gid, n2["riga"], n2["giorno"], n2["rr"], motivo=n2["motivo"]))
ok(img[:4] == b"\x89PNG" and img2[:4] == b"\x89PNG", "l'immagine, giocata e non giocata")
if os.environ.get("REND_PNG"):
    open(os.environ["REND_PNG"] + "_prestazione_31.png", "wb").write(PR.immagine(d31))
    open(os.environ["REND_PNG"] + "_prestazione.png", "wb").write(img); open(os.environ["REND_PNG"] + "_prestazione_dnp.png", "wb").write(img2)
# il comando
inviati = []
class M:
    chat = types.SimpleNamespace(id=1, type="private")
    async def reply_text(s, t, **k): inviati.append(("t", t, k.get("reply_markup")))
    async def reply_photo(s, p, **k): inviati.append(("f", k.get("caption"), k.get("reply_markup")))
cmd, cb = PR.handlers()
asyncio.run(cmd(types.SimpleNamespace(effective_message=M()), types.SimpleNamespace(args=["Prest", "Uno", "26/10/2026"])))
ok(inviati[-1][0] == "t" and [b.callback_data for b in inviati[-1][2].inline_keyboard[0]] == [f"pre:{gid}:20261025", f"pre:{gid}:20261031"],
   "/prestazione in un giorno senza partita: i bottoni prima e dopo")
q = types.SimpleNamespace(data=f"pre:{gid}:20261025", message=M())
async def _ans(*a, **k): pass
q.answer = _ans
asyncio.run(cb(types.SimpleNamespace(callback_query=q), None))
ok(inviati[-1][0] == "f" and inviati[-1][1] == "Prest Uno · 25/10/2026" and inviati[-1][2].inline_keyboard[0][-1].callback_data == f"pre:{gid}:20261031",
   "il bottone porta alla notte, con la freccia alla successiva")
pulisci()

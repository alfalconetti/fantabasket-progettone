import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.30.0 (Luca, 26/11): la Cam Thomas exception riconosciuta dal bot. 30 giorni senza squadra NBA tra l'inizio della
regular season e la trade deadline NBA; chi non ci arriva, è tagliato dopo la deadline o resta senza squadra fino alla
stagione dopo, 10 giorni dopo l'inizio della regular season successiva. Avvisi solo agli admin, decisione loro."""
import asyncio, importlib.util, os, types
from datetime import date
import database as db, settings
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
db.init_db(); db.migrate_db()
spec = importlib.util.spec_from_file_location("louca_db", os.path.join(ROOT, "fantabasket-loucabot", "db.py"))
ldb = importlib.util.module_from_spec(spec); spec.loader.exec_module(ldb); ldb.init_db()
from shared import cam_thomas as CT, lettura as L
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'ct%%'"); db._q("DELETE FROM nba_atleti WHERE atleta LIKE 'ct%%'")
db._q("DELETE FROM nba_movimenti WHERE atleta LIKE 'ct%%'")
for eid, st, tipo, d in (("ct1", "2090", 1, "2090-10-05"), ("ct2", "2090", 2, "2090-10-20"), ("ct3", "2090", 2, "2091-04-10"),
                         ("ct4", "2091", 2, "2091-10-19")):
    db._q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES (%s,%s,%s,%s,%s,'AAA','BBB','STATUS_FINAL')",
          (eid, st, tipo, d, d + " 20:00"))
_g = L.globali
L.globali = lambda: {**_g(), "trade_deadline": "2091-01-10", "nba_trade_deadline": {"2090": "2091-02-01", "2091": "2092-02-06"}}
ok(CT.inizio_rs(2090) == date(2090, 10, 20) and CT.deadline(2090) == date(2091, 2, 1) and CT.deadline(2092) is None,
   "inizio della regular season dal calendario NBA (non la preseason), deadline NBA per stagione (non quella della lega)")
def taglio(atleta, giorno, da="LAL"):
    db._q("INSERT INTO nba_atleti (atleta, nome, squadra) VALUES (%s, %s, NULL) ON CONFLICT (atleta) DO UPDATE SET squadra = NULL", (atleta, atleta))
    if giorno:
        db._q("INSERT INTO nba_movimenti (atleta, giorno, da, a) VALUES (%s, %s, %s, NULL)", (atleta, giorno, da))
taglio("cta", "2090-11-01")
v = CT.valuta("cta", date(2090, 11, 20))
ok(v["dal"] == date(2090, 11, 1) and v["idoneo_dal"] == date(2090, 12, 1) and not v["idoneo"] and "30 giorni" in v["perche"],
   "tagliato in stagione: dopo 30 giorni")
ok(CT.valuta("cta", date(2090, 12, 1))["idoneo"] and "può decadere dal 01/12/2090" in CT.testo(CT.valuta("cta", date(2090, 12, 1)), date(2090, 12, 1)),
   "al 30° giorno può decadere, e il testo lo dice")
taglio("ctb", "2091-01-15")
v = CT.valuta("ctb", date(2091, 2, 20))
ok(v["d30"] == date(2091, 7, 13) and v["idoneo_dal"] == date(2091, 10, 29) and not v["idoneo"],
   "a metà gennaio: 17 giorni fino alla deadline, gli altri 13 dal 1° luglio, poi 10 giorni di regular season")
taglio("ctc", "2091-03-10")
v = CT.valuta("ctc", date(2091, 11, 1))
ok(v["d30"] == date(2091, 7, 30) and v["idoneo_dal"] == date(2091, 10, 29) and v["idoneo"] and "non prima di 10 giorni" in v["perche"],
   "tagliato a marzo (mercato chiuso): conta dal 1° luglio, poi 10 giorni di regular season")
taglio("ctd", "2090-08-01")
ok(CT.valuta("ctd", date(2090, 10, 25))["idoneo_dal"] == date(2090, 10, 30), "tagliato d'estate: 10 giorni dopo l'inizio della regular season")
taglio("ctg", "2090-10-05")
v = CT.valuta("ctg", date(2090, 11, 1))
ok(v["idoneo_dal"] == date(2090, 11, 4) and not v["idoneo"] and "30 giorni" in v["perche"], "tagliato a ottobre (preseason, mercato aperto): i 30 giorni")
taglio("cth", "2090-09-25")
ok(CT.valuta("cth", date(2090, 11, 1))["idoneo_dal"] == date(2090, 10, 30), "a fine settembre: 30 giorni il 25/10, ma non prima di 10 giorni di regular season")
taglio("cte", None)
v = CT.valuta("cte", date(2090, 11, 5))
ok(v["almeno"] and v["dal"] == date(2026, 10, 23) and v["d30"] == date(2026, 11, 22) and "almeno dal 23/10/2026" in CT.testo(v, date(2090, 11, 5)),
   "senza data: conta dal 23/10/2026, quando il bot ha cominciato a registrare")
db._q("INSERT INTO nba_atleti (atleta, nome, squadra) VALUES ('ctf', 'ctf', 'BOS')")
ok(CT.valuta("ctf", date(2090, 12, 5)) is None and "ha una squadra" in CT.testo(None), "con una squadra NBA: niente")
db._q("UPDATE nba_atleti SET squadra = 'MIA' WHERE atleta = 'cta'")
db._q("INSERT INTO nba_movimenti (atleta, giorno, da, a) VALUES ('cta', '2090-11-20', NULL, 'MIA')")
ok(CT.valuta("cta", date(2090, 12, 5)) is None, "rifirmato in NBA: niente")
db._q("UPDATE nba_atleti SET squadra = NULL WHERE atleta = 'cta'")
db._q("INSERT INTO nba_movimenti (atleta, giorno, da, a) VALUES ('cta', '2090-12-01', 'MIA', NULL)")
ok(CT.valuta("cta", date(2090, 12, 10))["idoneo_dal"] == date(2090, 12, 31), "ritagliato: si riconta dall'ultimo taglio")

# gli avvisi agli admin
import handlers.decadimento as D
db._q("TRUNCATE giocatori, contratti RESTART IDENTITY CASCADE")
gid = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES ('Kevin Porter Jr.','Kevin Porter Jr.','kevin porter jr.','ctd') RETURNING id")
db._q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s,'team01',4,1,'2090','normale')", (gid,))
gid2 = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES ('Uno','Uno','uno','ctf') RETURNING id")
db._q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s,'team02',4,1,'2090','normale')", (gid2,))
cc = D.candidati_cam_thomas(date(2090, 11, 2))
ok([c["giocatore_id"] for c in cc] == [gid], "candidati: chi è senza squadra e può decadere, non chi ha una squadra")
inviati = []
class Bot:
    async def send_message(self, chat_id, text, **k): inviati.append((chat_id, text, k.get("reply_markup")))
D.candidati_cam_thomas = lambda oggi=None: cc
settings.admin_group_id = lambda: -2
D.migra_cam_thomas(); db._q("TRUNCATE cam_thomas_avvisi")
asyncio.run(D.job_cam_thomas(types.SimpleNamespace(bot=Bot())))
asyncio.run(D.job_cam_thomas(types.SimpleNamespace(bot=Bot())))
ok(len(inviati) == 1 and inviati[0][0] == -2 and "Cam Thomas exception possibile" in inviati[0][1] and "Kevin Porter Jr." in inviati[0][1]
   and inviati[0][2].inline_keyboard[0][0].callback_data == f"decadm:m:team01:{gid}:cam_thomas", "un avviso solo, agli admin, col bottone del decadimento")
ok("ha una squadra" in D.riga_cam_thomas(gid2) and "decadere dal 30/10/2090" in D.riga_cam_thomas(gid), "nella conferma del decadimento la riga della Cam Thomas")
L.globali = lambda: {**_g(), "nba_trade_deadline": {"2090": "2091-02-01"}}
ok(D.avviso_deadline_nba(date(2091, 11, 1)) and "deadline_nba" in D.avviso_deadline_nba(date(2091, 11, 1))
   and D.avviso_deadline_nba(date(2090, 11, 1)) is None and D.avviso_deadline_nba(date(2091, 9, 1)) is None,
   "deadline NBA mancante a stagione iniziata: la si chiede agli admin")
L.globali = _g
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'ct%%'"); db._q("DELETE FROM nba_atleti WHERE atleta LIKE 'ct%%'")
db._q("DELETE FROM nba_movimenti WHERE atleta LIKE 'ct%%'"); db._q("TRUNCATE cam_thomas_avvisi")
db._q("TRUNCATE giocatori, contratti RESTART IDENTITY CASCADE")

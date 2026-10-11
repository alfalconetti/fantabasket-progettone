import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""/autoslot e /autocap contano davvero (fino a v54 lo slot anticipato si vedeva in /me ma non contava)."""
import database as db, teams as tm, pg_client as pg
from datetime import datetime, timezone
pg.init_pg(); db.init_db()
pg.q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
pg.q("DELETE FROM slot_anticipato"); pg.q("DELETE FROM cap_anticipato")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
for i in range(15):
    gid=pg.q("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(f"p{i}",f"p{i}",f"p{i}"),one=True)["id"]
    c=pg.q("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,'team01',10,1,'2026','normale') RETURNING id",(gid,),one=True)["id"]
    pg.q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id,timestamp) VALUES ('signed',%s,'team01','2026',%s,%s)",(gid,c,datetime.now(timezone.utc)))
ok(pg.get_slot_totale("team01","2026")==0 and not tm.check_slot_virtuale("team01",0), "roster pieno: 0 slot, niente offerte")
pg.set_slot_anticipato("team01",1)
ok(pg.get_slot_totale("team01","2026")==1 and tm.check_slot_virtuale("team01",0), "dopo /autoslot 1: uno slot libero, può offrire")
cap_prima=pg.get_cap_totale("team01","2026"); pg.set_cap_anticipato("team01",10)
ok(pg.get_cap_totale("team01","2026")==cap_prima+10, "dopo /autocap 10: +10 di cap")
pg.reset_slot_anticipato("team01")
ok(pg.get_slot_totale("team01","2026")==0, "reset dello slot anticipato: di nuovo 0")

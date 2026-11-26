import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types
import database as db
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe RESTART IDENTITY CASCADE")
def g(n): return db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(n,n,n))
def c(gid,t,imp,anni,att=True): return db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo,attivo) VALUES (%s,%s,%s,%s,'2026','normale',%s) RETURNING id",(gid,t,imp,anni,att))
def tx(tipo,gid,da,a,cid,ts): db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,team_id_a,stagione,contratto_id,timestamp) VALUES (%s,%s,%s,%s,'2026',%s,%s)",(tipo,gid,da,a,cid,ts))
p1,p2,p3,p4,p5=[g(x) for x in ["Uno","Due","Tre","Quattro","Cinque"]]
c1=c(p1,"team01",10,2); tx("signed",p1,None,"team01",c1,"2026-08-01")
c2=c(p2,"team02",12,3); tx("signed",p2,None,"team01",c2,"2026-08-01"); tx("traded",p2,"team01","team02",c2,"2026-09-10")
c3=c(p3,"team01",15,3); tx("signed",p3,None,"team02",c3,"2026-08-01"); tx("traded",p3,"team02","team01",c3,"2026-09-10")
c4a=c(p4,"team01",5,1,False); tx("signed",p4,None,"team01",c4a,"2026-08-01")
c4b=c(p4,"team01",7,2); tx("cut",p4,"team01",None,c4a,"2026-09-12"); tx("signed",p4,None,"team01",c4b,"2026-09-13")
c5=c(p5,"team01",20,3); tx("signed",p5,None,"team01",c5,"2026-08-01")
db._q("INSERT INTO dpe (giocatore_id,team_id,stagione,importo_originale,importo_dpe,timestamp) VALUES (%s,'team01','2026',10,8,'2026-09-15')",(p1,))
db._q("DELETE FROM cambi_ruolo")
db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_a,stagione,tipo,timestamp) VALUES (%s,'team01','PG','2026','iniziale','2026-08-02'),"
      "(%s,'team01','C','2026','post_trade','2026-09-11')", (p1, p3))
import handlers.team_diff as TD
out=[]
class M:
    async def reply_text(s,t,**k): out.append(t)
async def main():
    m=M(); upd=types.SimpleNamespace(effective_user=types.SimpleNamespace(id=101),effective_message=m)
    await TD.cmd_team_diff(upd, types.SimpleNamespace(args=["team01","01-09-26","01-10-26"]))
    await TD.cmd_team_diff(upd, types.SimpleNamespace(args=["team01","01-08-27","02-08-27"]))
    await TD.cmd_team_diff(upd, types.SimpleNamespace(args=["team01","15-09-26","01-08-27"]))
asyncio.run(main()); print("\n=====\n".join(out))
_ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
# v7.29.1 (Luca, 25/11): il computo complessivo prima → dopo
_o = out[1] if out[0].startswith("⏳") else out[0]
_o = next(x for x in out if "01/09/2026 → 01/10/2026" in x)
_ok("COMPLESSIVO" in _o and "Cap: 47M → 50M (+3M)" in _o and "Slot: 4/15 → 3/15 (−1)" in _o and "(4 → 4 a roster)" in _o
    and "Pick: 1st 0 → 0 · 2nd 0 → 0" in _o and "Diritti: 0 → 0" in _o and "Ruoli" not in _o, "/team_diff: computo di cap, slot (la DPE prima della deadline lo libera), pick e diritti")
_o2 = next(x for x in out if "15/09/2026 → 01/08/2027" in x)
_ok("Slot: 3/15 → 4/15 (+1)" in _o2, "la DPE prima della deadline libera lo slot solo nella sua stagione")

# v7.1.0 (Luca, 05/11): trade di prova annullata e poi decadimento → «Decaduto», non «Trade»
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
p6 = g("Konchar")
c6 = c(p6, "team01", 1, 1, False)
db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,team_id_a,stagione,contratto_id,timestamp,note) VALUES "
      "('signed',%s,NULL,'team01','2026',%s,'2026-07-25','migrazione iniziale'),"
      "('traded',%s,'team01','team03','2026',%s,'2026-10-03 18:54','TRADE-2026-026'),"
      "('traded',%s,'team03','team01','2026',%s,'2026-10-03 18:56','ANNULLAMENTO TRADE-2026-026'),"
      "('decadimento',%s,'team01',NULL,'2026',%s,'2026-10-25 22:59','Decadimento: firma in altra lega')", (p6, c6) * 4)
from datetime import datetime as _dt
ok(TD._motivo_giocatore("team01", p6, _dt(2026, 9, 30), _dt(2026, 11, 5), "out") == "Decaduto", "trade annullata saltata: esce per decadimento")
p7 = g("Sette")
c7 = c(p7, "team02", 1, 1)
db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,team_id_a,stagione,contratto_id,timestamp,note) VALUES "
      "('cut',%s,'team01',NULL,'2026',%s,'2026-10-01',NULL), ('signed',%s,NULL,'team01','2026',%s,'2026-10-02',NULL),"
      "('traded',%s,'team01','team02','2026',%s,'2026-10-10','TRADE-2026-030')", (p7, c7) * 3)
ok(TD._motivo_giocatore("team01", p7, _dt(2026, 9, 30), _dt(2026, 11, 5), "out") == "Trade", "più uscite nel periodo: conta l'ultima (trade, non il taglio)")

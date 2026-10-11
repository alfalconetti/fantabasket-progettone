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

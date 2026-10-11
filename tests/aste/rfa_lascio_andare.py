import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types
import database as db, teams as tm, pg_client as pg
from datetime import datetime, timezone, timedelta
pg.init_pg(); db.init_db()
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
gid=pg.q("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES ('Ron Rfa','Ron Rfa','ron rfa') RETURNING id",one=True)["id"]
cid=pg.q("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,'team01',8,1,'2026','normale') RETURNING id",(gid,),one=True)["id"]
pg.q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,'team01','2026',%s)",(gid,cid))
now=datetime.now(timezone.utc)
aid=db.crea_asta(tipo="RFA",giocatore="Ron Rfa",squadra_proprietaria="team01",vecchio_compenso=8,creata_at=now.isoformat(),scade_at=now.isoformat(),stagione="2026")
db.chiudi_asta(aid, now.isoformat())
import handlers.firma as F
class Q:
    def __init__(s,uid): s.data=f"lascia:{aid}"; s.from_user=types.SimpleNamespace(id=uid); s.t=None
    async def answer(s,*a,**k): pass
    async def edit_message_text(s,t,**k): s.t=t
class Bot:
    async def send_message(self,**k): pass
    async def edit_message_text(self,*a,**k): pass
async def go(uid):
    q=Q(uid); await F.lascia_callback(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=Bot())); return q.t
async def main():
    t=await go(102); ok("Non sei il proprietario" in t and db.get_asta(aid)["stato"]=="CHIUSA", "altra squadra non può lasciarlo andare")
    t=await go(101); ok(db.get_asta(aid)["stato"]=="ANNULLATA" and not pg.q("SELECT attivo FROM contratti WHERE id=%s",(cid,),one=True)["attivo"], "proprietario: lasciato andare, contratto chiuso")
    t=await go(101); ok("Già conclusa" in t, "secondo tap (o secondo GM): nessun effetto")
asyncio.run(main())

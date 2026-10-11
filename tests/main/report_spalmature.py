import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types
from datetime import datetime, timezone, timedelta
import database as db
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
db._q("DELETE FROM bref_stats")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
def g(n): return db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(n,n,n.lower()))
vecchio=g("Vecchio Ritirato"); attivo=g("Sotto Contratto"); ct=g("Cam Free")
for gid,t,imp in [(vecchio,"team01",3),(vecchio,"team02",2),(attivo,"team03",4),(ct,"team01",1)]:
    db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES (%s,%s,'2025','2026',%s),(%s,%s,'2025','2025',9)",(t,gid,imp,t,gid))
c=db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,'team04',1,1,'2026','normale') RETURNING id",(attivo,))
c2=db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo,attivo) VALUES (%s,'team02',8,1,'2026','normale',FALSE) RETURNING id",(ct,))
db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,stagione,contratto_id,note) VALUES ('decadimento',%s,'team02','2026',%s,'Decadimento: ✂️ Cam Thomas exception')",(ct,c2))
db._q("INSERT INTO bref_stats (timestamp,stagione,nome_bref,team,g) VALUES (%s,'2025','Vecchio Ritirato','LAL',30)",(datetime.now(timezone.utc)-timedelta(days=400),))
from handlers.spalmature import testi_report, job_report_spalmature
t="".join(testi_report())
ok("Vecchio Ritirato" in t and "Alfa 3M" in t and "Beta 2M" in t, "free agent con spalmature su due squadre (solo stagione corrente e future)")
ok("Sotto Contratto" not in t, "chi ha un contratto non compare")
ok("Cam Free" in t and "Cam Thomas il" in t and "mai rilevato" in t, "Cam Thomas segnalato, giocatore mai visto su bref")
ok("9M" not in t, "le rate delle stagioni passate non contano")
sent=[]
class Bot:
    async def send_message(self, **k): sent.append(k["chat_id"])
asyncio.run(job_report_spalmature(types.SimpleNamespace(bot=Bot())))
ok(sent==[-2], "job: inviato al gruppo admin")

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types
import database as db, teams as tm, pg_client as pg, utils
from datetime import datetime, timezone, timedelta
pg.init_pg(); db.init_db()
pg.q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
def g(n): return pg.q("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(n,n,pg._normalizza(n)),one=True)["id"]
def firma(gid,t,imp,anni=2,ts=None):
    cid=pg.q("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,%s,%s,'2026','normale') RETURNING id",(gid,t,imp,anni),one=True)["id"]
    pg.q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id,timestamp) VALUES ('signed',%s,%s,'2026',%s,%s)",(gid,t,cid,ts or datetime.now(timezone.utc)))
    return cid
for i in range(14): firma(g(f"Bull {i}"),"team01",5)
rfa=g("Jalen Williams"); firma(rfa,"team01",10)
now=datetime.now(timezone.utc)
aid=db.crea_asta(tipo="RFA",giocatore="Jalen Williams",squadra_proprietaria="team01",vecchio_compenso=10,creata_at=now.isoformat(),scade_at=(now+timedelta(hours=18)).isoformat(),stagione="2026")
ok(pg.get_roster_count("team01","2026")==15, "Bulls: 15 contratti (14 + RFA)")
ok(pg.get_slot_totale("team01","2026")==1 and tm.check_slot_virtuale("team01",0), "RFA non occupa slot: 1 libero, può offrire in FA")
cap_prima=pg.get_cap_contratti("team01","2026"); ok(cap_prima==80, f"RFA occupa cap: {cap_prima}M")
# lascia: rilascia_rfa
ok(pg.rilascia_rfa("team01","Jalen Williams","2026"), "lascia andare: contratto chiuso + movimento")
ok(pg.get_roster_count("team01","2026")==14 and pg.get_cap_contratti("team01","2026")==70, "dopo: 14 nel roster, cap 70")
r=pg.q("SELECT tipo, team_id_a FROM transazioni WHERE giocatore_id=%s ORDER BY id DESC LIMIT 1",(rfa,),one=True)
ok(r["tipo"]=="expired" and r["team_id_a"] is None, "movimento di uscita registrato")
# 30 giorni
x=g("Kevin Durant"); c=firma(x,"team02",20,ts=now-timedelta(days=60))
pg.q("UPDATE contratti SET attivo=FALSE WHERE id=%s",(c,))
pg.q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,stagione,contratto_id,timestamp) VALUES ('cut',%s,'team02','2026',%s,%s)",(x,c,now-timedelta(days=5)))
ok(pg.squadre_regola_30_giorni("Kevin Durant")=={"team02"}, "30 giorni: tagliato 5 giorni fa dai Lakers → solo Lakers bloccati")
y=g("Old Cut"); c=firma(y,"team02",3,ts=now-timedelta(days=90)); pg.q("UPDATE contratti SET attivo=FALSE WHERE id=%s",(c,))
pg.q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,stagione,contratto_id,timestamp) VALUES ('cut',%s,'team02','2026',%s,%s)",(y,c,now-timedelta(days=40)))
ok(pg.squadre_regola_30_giorni("Old Cut")==set(), "30 giorni: tagliato 40 giorni fa → nessun blocco")
from handlers.offerte import _esegui_offerta, apri_asta_fa
class Bot:
    username="b"
    async def send_message(self, chat_id, text, **k): return types.SimpleNamespace(message_id=1)
async def t():
    a,err=await apri_asta_fa(types.SimpleNamespace(bot=Bot()), tm.get_team_by_id("team02"), "Kevin Durant", 2, [102])
    ok(a is None and "30 giorni" in err, "Lakers non possono aprire l'asta per Durant")
asyncio.run(t())
# DPE nel cap per offrire
from handlers.offerte import _cap_libero
pre=_cap_libero("team01")
pg.q("INSERT INTO dpe (giocatore_id,team_id,stagione,importo_originale,importo_dpe) VALUES (%s,'team01','2026',5,3)",(pg.trova_giocatore("Bull 0"),))
ok(_cap_libero("team01")==pre+2, f"DPE conta nel cap per offrire ({pre} → {_cap_libero('team01')})")
# rifirma dopo taglio: niente fusione
z=g("Re Sign"); c=firma(z,"team01",10)
pg.q("UPDATE contratti SET attivo=FALSE WHERE id=%s",(c,))
for st,imp in [("2026",6),("2027",5),("2028",5),("2029",4)]:
    pg.q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team01',%s,'2026',%s,%s)",(z,st,imp))
pg.registra_firma("team01","Re Sign",5,3,"2026")
r=pg.q("SELECT importo, anni_originali FROM contratti WHERE giocatore_id=%s AND attivo",(z,),one=True)
n=pg.q("SELECT count(*) n FROM impatto_taglio WHERE giocatore_id=%s",(z,),one=True)["n"]
ok(r["importo"]==5 and n==4, f"rifirma: contratto {r['importo']}x{r['anni_originali']}, spalmate intatte ({n})")

# Cam Thomas: la squadra che l'ha fatto decadere deve offrire almeno il vecchio contratto
ct=g("Cam Thomas"); c=firma(ct,"team02",12)
pg.q("UPDATE contratti SET attivo=FALSE WHERE id=%s",(c,))
pg.q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,stagione,contratto_id,note) VALUES ('decadimento',%s,'team02','2026',%s,'Decadimento: ✂️ Cam Thomas exception')",(ct,c))
async def t2():
    a,err=await apri_asta_fa(types.SimpleNamespace(bot=Bot()), tm.get_team_by_id("team02"), "Cam Thomas", 5, [102])
    ok(a is None and "Cam Thomas" in err, "Cam Thomas: Beta non può riaprirlo a 5M (minimo 12)")
    a,err=await apri_asta_fa(types.SimpleNamespace(bot=Bot()), tm.get_team_by_id("team01"), "Cam Thomas", 5, [101])
    ok(a is not None, "Cam Thomas: un'altra squadra può aprire a 5M")
asyncio.run(t2())

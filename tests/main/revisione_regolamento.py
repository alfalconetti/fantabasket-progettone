import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types, json, os
import database as db, settings
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
def setfase(f):
    g=json.load(open(os.environ["GLOBALS_PATH"])); g["fase"]=f; json.dump(g,open(os.environ["GLOBALS_PATH"],"w"))
def g(n): return db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(n,n,n.lower()))
def firma(gid,t,imp,anni):
    c=db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,%s,%s,'2026','normale') RETURNING id",(gid,t,imp,anni))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,'2026',%s)",(gid,t,c))
G={}
for i in range(12): G[i]=g(f"p{i}"); firma(G[i],"team01",1 if i<5 else 4,1)
sent=[]
class Bot:
    async def send_message(self,**k): sent.append(k.get("text",""))
class Q:
    def __init__(s,d,uid=101): s.data=d; s.from_user=types.SimpleNamespace(id=uid); s.t=None
    async def answer(s,*a,**k): pass
    async def edit_message_text(s,t,**k): s.t=t
import handlers.tagli as T
async def taglia(gid):
    q=Q(f"taglia_ok:{gid}"); u=types.SimpleNamespace(callback_query=q,effective_user=q.from_user)
    await T.cb_conferma_taglio(u, types.SimpleNamespace(bot=Bot())); return q.t
async def main():
    setfase("offseason-fa")
    for i in range(3): await taglia(G[i])
    ok(db.get_tagli_gratuiti_usati("team01","2026")==3, "3 tagli 1x1 gratuiti")
    t=await taglia(G[3])
    imp=db._q("SELECT stagione,importo FROM impatto_taglio WHERE giocatore_id=%s",(G[3],),many=True)
    ok("tagliato" in t and [ (r["stagione"],r["importo"]) for r in imp]==[("2026",1)], f"4° 1x1: consentito con spalmatura 1x1 {[(r['stagione'],r['importo']) for r in imp]}")
    ok(db.get_tagli_gratuiti_usati("team01","2026")==3, "il 4° non conta come gratuito")
    setfase("regular-season-fa")   # roster ora 8? 12-4 = 8 → sotto 10
    t=await taglia(G[6]); ok("sotto il minimo" in t and db.get_contratto_attivo(G[6]), "RS: taglio bloccato sotto i 10")
    setfase("offseason-fa")
    # decadimento ritiro: spalmate di altre squadre tolte
    x=g("Ret"); firma(x,"team02",10,2)
    db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team01',%s,'2025','2026',3),('team01',%s,'2025','2027',2)",(x,x))
    from handlers.decadimento import applica_decadimento, cmd_ritiro_fa
    await applica_decadimento(Bot(),"team02",x,"ritiro","adm")
    ok(db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s",(x,))==0 and any("spalmature" in s for s in sent), "ritiro: tolte anche le spalmature di team01")
    y=g("Cam"); firma(y,"team02",5,1)
    db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team01',%s,'2025','2026',3)",(y,))
    await applica_decadimento(Bot(),"team02",y,"altro","adm")
    ok(db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s",(y,))==1, "motivo 'altro' (Cam Thomas): spalmate di altri restano")
    # ritiro_fa
    z=g("Free Ret"); db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team03',%s,'2025','2026',4),('team03',%s,'2025','2025',4)",(z,z))
    out=[]
    class M:
        async def reply_text(s,t,**k): out.append(t)
    upd=types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900),effective_message=M())
    await cmd_ritiro_fa(upd, types.SimpleNamespace(args=["Free","Ret"],bot=Bot()))
    ok(db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s",(z,))==1 and "−4M" in out[-1], "/ritiro_fa: tolta la stagione corrente e future, storico 2025 resta")
    # rookie slot
    for i in range(7): firma(g(f"fill{i}"),"team01",1,2)   # team01: 8 + 7 = 15
    rk=g("Rook"); rid=db._qval("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft) VALUES (%s,'team01',2,40,'2026') RETURNING id",(rk,))
    from handlers.rookie import esegui_attivazione, AttivazioneNonEseguibile
    try: esegui_attivazione(rid,"team01",1,2); ok(False,"rookie con roster pieno")
    except AttivazioneNonEseguibile as e: ok("Roster pieno" in str(e), "attivazione diritti bloccata a roster pieno")
    # registra_firma anni
    import handlers.admin_panel as A
    out.clear()
    upd=types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900),effective_message=M(),effective_chat=types.SimpleNamespace(type="private"))
    await A.cmd_registra_firma(upd, types.SimpleNamespace(args=["team02","25","1","Nobody"],bot=Bot()))
    ok("anni non validi" in out[-1], "/registra_firma 25M x1 rifiutato")
asyncio.run(main())

# ── Cam Thomas exception
async def cam_thomas():
    from handlers.decadimento import applica_decadimento
    import handlers.admin_panel as A
    ct=g("Cam Thomas"); firma(ct,"team03",12,2)
    db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team02',%s,'2025','2026',3)",(ct,))
    await applica_decadimento(Bot(),"team03",ct,"cam_thomas","adm")
    ok(db.get_contratto_attivo(ct) is None and db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s",(ct,))==1,
       "Cam Thomas: contratto chiuso gratis, spalmature degli altri restano")
    ok(db.minimo_cam_thomas(ct,"team03")==12 and db.minimo_cam_thomas(ct,"team02") is None, "minimo 12M solo per la squadra che l'ha fatto decadere")
    out=[]
    class M:
        async def reply_text(s,t,**k): out.append(t)
    u=types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900,first_name="Adm",username=None),effective_message=M(),effective_chat=types.SimpleNamespace(type="private"))
    await A.cmd_registra_firma(u, types.SimpleNamespace(args=["team03","8","1","Cam","Thomas"],bot=Bot()))
    ok("almeno il contratto precedente" in out[-1] and db.get_contratto_attivo(ct) is None, "/registra_firma a 8M rifiutato (minimo 12)")
    await A.cmd_registra_firma(u, types.SimpleNamespace(args=["team03","12","1","Cam","Thomas"],bot=Bot()))
    ok(db.get_contratto_attivo(ct) is not None, "/registra_firma a 12M accettato")
asyncio.run(cam_thomas())

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v3.10.0: il taglio dal pannello admin passa dallo stesso codice dei GM (anteprima, regole
di regular season, scrittura atomica, avviso al GM)."""
import asyncio, types, json, os
import database as db
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
def fase(f):
    g=json.load(open(os.environ["GLOBALS_PATH"])); g["fase"]=f; json.dump(g,open(os.environ["GLOBALS_PATH"],"w"))
def gioc(n,t,imp,anni=1):
    gid=db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",(n,n,n.lower()))
    c=db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,%s,%s,'2026','normale') RETURNING id",(gid,t,imp,anni))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,'2026',%s)",(gid,t,c)); return gid
grosso=gioc("Grosso","team01",20,2)
piccoli=[gioc(f"p{i}","team01",1) for i in range(9)]
import handlers.admin_panel as A
msgs=[]
class Q:
    def __init__(s,data): s.data=data; s.t=None; s.kb=None
    async def answer(s,*a,**k): pass
    async def edit_message_text(s,t,**k): s.t=t; s.kb=k.get("reply_markup")
class Bot:
    async def send_message(self,**k): msgs.append(k)
def tap(cb, data):
    q=Q(data); asyncio.run(cb(types.SimpleNamespace(callback_query=q, effective_user=types.SimpleNamespace(id=900,first_name="Adm",username="adm")),
                             types.SimpleNamespace(bot=Bot()))); return q
fase("regular-season-fa")
q=tap(A.cb_adm_taglia_conferma, f"adm_taglia_ok:{grosso}:team01")
ok("sotto il minimo" in (q.t or "") and db._qval("SELECT attivo FROM contratti WHERE giocatore_id=%s",(grosso,)),
   "RS: anche l'admin non può scendere sotto i 10 (prima tagliava subito)")
fase("offseason-fa")
q=tap(A.cb_adm_taglia_conferma, f"adm_taglia_ok:{grosso}:team01")
ok("Impatto taglio" in q.t and q.kb.inline_keyboard[0][0].callback_data==f"adm_taglia_si:{grosso}:team01", "anteprima con l'impatto e il bottone di conferma")
msgs.clear(); q=tap(A.cb_adm_taglia_esegui, f"adm_taglia_si:{grosso}:team01")
ok(not db._qval("SELECT attivo FROM contratti WHERE giocatore_id=%s",(grosso,))
   and db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s",(grosso,))>0
   and db._qval("SELECT count(*) FROM transazioni WHERE giocatore_id=%s AND tipo='cut'",(grosso,))==1, "taglio eseguito: contratto chiuso, movimento e spalmature")
ok(any("Un admin ha tagliato" in m["text"] for m in msgs) and any("Registrato da un admin" in m["text"] for m in msgs), "avviso al GM e annuncio con il nome dell'admin")
q=tap(A.cb_adm_taglia_esegui, f"adm_taglia_si:{grosso}:team01")
ok("non" in q.t.lower() and db._qval("SELECT count(*) FROM transazioni WHERE giocatore_id=%s AND tipo='cut'",(grosso,))==1, "secondo tap: niente doppio taglio")
ok(db.controlli_coerenza()==[] or all("storico" in p for p in db.controlli_coerenza()), "coerenza dopo il taglio")

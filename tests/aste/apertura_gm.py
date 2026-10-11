import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types, json, os
import database as db, teams as tm
db.init_db()
g=json.load(open(os.environ["GLOBALS_PATH"])); g["mercato_aperto"]=True; json.dump(g,open(os.environ["GLOBALS_PATH"],"w"))
sent=[]
class Bot:
    username="astebot"
    async def send_message(self, chat_id, text, **k): sent.append((chat_id,text[:60])); return types.SimpleNamespace(message_id=9)
class Q:
    def __init__(s,d): s.data=d; s.from_user=types.SimpleNamespace(id=102)
    async def answer(s,*a,**k): pass
    async def edit_message_text(s,t,**k): sent.append(("edit",t.replace("\n"," | ")))
import handlers.offerte as O
async def go(gioc):
    sent.clear(); ud={"pending_importo":2,"pending_tipo":"apertura","nuova_fa_team":tm.get_team_by_id("team02"),"nuova_fa_giocatore":gioc}
    q=Q("conferma_offerta:si"); upd=types.SimpleNamespace(callback_query=q,effective_user=q.from_user)
    r=await O.conferma_offerta_callback(upd, types.SimpleNamespace(bot=Bot(),user_data=ud)); print(r, sent)
asyncio.run(go("Kevin Durant")); asyncio.run(go("Kevin Durant"))
print("watch", db.get_watchers(db.get_aste_aperte()[-1]["id"]))

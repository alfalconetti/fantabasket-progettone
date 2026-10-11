import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types, os
import database as db
db.init_db()
sent=[]
class Bot:
    username="astebot"
    async def send_message(self, chat_id, text, **k):
        sent.append((chat_id,text.replace("\n"," | "))); return types.SimpleNamespace(message_id=len(sent))
class M:
    async def reply_text(s,t,**k): sent.append(("reply",t.replace("\n"," | ")))
import handlers.admin as A
async def run(uid,*args):
    sent.clear(); m=M()
    upd=types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid,first_name="Adm",username="adm"),effective_message=m,effective_chat=types.SimpleNamespace(id=uid,type="private"))
    await A.apri_asta(upd, types.SimpleNamespace(bot=Bot(),args=list(args),bot_data={},application=None))
    for x in sent: print("   ",x[0],"→",x[1][:160])
async def main():
    print("1 non admin");      await run(101,"team01","5","LeBron","James")
    print("2 ok esatto");      await run(900,"team01","5","LeBron","James")
    print("   watchers:", db.get_watchers(1))
    print("3 già in asta");    await run(900,"team01","5","lebron","james")
    print("4 omonimi");        await run(900,"team01","5","Williams")
    print("5 fuzzy");          await run(900,"team01","5","Durnat")
    print("6 cap lakers");     await run(900,"team02","5","Kevin","Durant")
    print("7 team errato");    await run(900,"team99","5","Kevin","Durant")
    print("8 importo");        await run(900,"team01","x","Kevin","Durant")
    import json; g=json.load(open(os.environ["GLOBALS_PATH"])); g["mercato_aperto"]=False; json.dump(g,open(os.environ["GLOBALS_PATH"],"w"))
    print("9 mercato chiuso"); await run(900,"team01","5","Kevin","Durant")
asyncio.run(main())

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""/set_cap_penalizzato nel bot principale (v3.9.4): scrive teams.json, tetto RS ridotto, offseason invariato."""
import asyncio, types, json, os
import database as db, settings, teams as tm
db.init_db(); db.migrate_db()
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
import gas_client; gas_client.sync_teams = lambda ids: True     # niente rete
from handlers.admin_panel import cmd_set_cap_penalizzato
out=[]
class M:
    async def reply_text(s,t,**k): out.append(t)
def chiama(uid,args):
    out.clear()
    asyncio.run(cmd_set_cap_penalizzato(types.SimpleNamespace(effective_message=M(),effective_user=types.SimpleNamespace(id=uid)), types.SimpleNamespace(args=args)))
    return out[-1] if out else ""
def setfase(f):
    g=json.load(open(os.environ["GLOBALS_PATH"])); g["fase"]=f; json.dump(g,open(os.environ["GLOBALS_PATH"],"w"))
ok("Solo admin" in chiama(101,["team02","5"]) and not tm.get_team_by_id("team02").get("cap_penalizzato"), "un GM non può")
r=chiama(900,["team02","5"])
ok(tm.get_team_by_id("team02")["cap_penalizzato"]==5 and "145M" in r, "admin: penalità 5 → tetto RS 145")
setfase("regular-season-fa"); ok(settings.cap_limite_team(tm.get_team_by_id("team02"))==145, "in regular season il tetto è 145")
setfase("offseason-fa");      ok(settings.cap_limite_team(tm.get_team_by_id("team02"))==165, "in offseason resta 165")
ok("non trovata" in chiama(900,["team99","5"]) and "≥ 0" in chiama(900,["team02","-1"]), "squadra sbagliata e valore negativo rifiutati")
chiama(900,["team02","0"]); ok(tm.get_team_by_id("team02")["cap_penalizzato"]==0, "0 la toglie")

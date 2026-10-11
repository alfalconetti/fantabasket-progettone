import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""Il foglio Roster si aggiorna sempre per tutte le squadre (v3.9.4), qualunque cosa chieda il chiamante."""
import database as db, gas_client, teams as tm
db.init_db(); db.migrate_db()
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
inviati=[]
gas_client._get_config=lambda: ("http://finto", "token")
gas_client._build_team_payload=lambda tid: {"team_id": tid}
gas_client._do_sync=lambda url, tok, payload, attempt=1: inviati.append([t["team_id"] for t in payload["teams"]])
import threading
class T:
    def __init__(s, target, args, daemon): s.f, s.a = target, args
    def start(s): s.f(*s.a)
threading.Thread=T
tutte=sorted(t["id"] for t in tm.get_all_teams())
gas_client.sync_teams(["team02"]); ok(sorted(inviati[-1])==tutte, f"sync_teams(['team02']) → tutte le {len(tutte)} squadre")
gas_client.sync_after_taglio("team03"); ok(any(sorted(x)==tutte for x in inviati[1:]), "sync_after_taglio → tutte")
gas_client.sync_teams_sync(["team01"]); ok(sorted(inviati[-1])==tutte, "sync manuale → tutte")

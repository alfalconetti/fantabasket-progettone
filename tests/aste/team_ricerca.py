import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v62: /team cerca la squadra come /roster nel bot principale (shared/squadre.py)."""
import asyncio, types
import database as db, teams as tm
db.init_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
casi = {"team02": "team02", "Beta": "team02", "beta": "team02", "GA": "team01", "gam": "team03", "Deltta": "team04", "zzzz": None}
trovati = {q: (tm.get_team_by_query(q) or {}).get("id") for q in casi}
ok(trovati == casi, f"id, nome, GM, inizio, errore di battitura, niente {trovati}")
import sys; sys.path.insert(0, "..")
from shared.squadre import cerca_squadra
ok(cerca_squadra("", tm.get_all_teams()) is None and cerca_squadra("  ", tm.get_all_teams()) is None, "testo vuoto: nessuna squadra")


class Msg:
    def __init__(s): s.t = []
    async def reply_text(s, t, **k): s.t.append(t)


def team(args, uid=101):
    m = Msg()
    asyncio.run(__import__("handlers.admin", fromlist=["cmd_team"]).cmd_team(
        types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=m),
        types.SimpleNamespace(args=args)))
    return m.t[-1]


ok("Gamma" in team(["gam"]), "/team gam → Gamma")
ok("Alfa" in team([]), "/team senza argomento: la propria squadra")
ok("Uso" in team([], uid=999), "/team senza argomento e senza squadra: istruzioni")
ok("Nessuna squadra" in team(["zzzz"]), "/team con un nome che non esiste")

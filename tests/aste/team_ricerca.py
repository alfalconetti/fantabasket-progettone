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
# v6.4.3 (Luca, 23/10): una parola sola di un nome di due parole, squadra o GM
_S = [{"id": "t1", "nome": "Montecelio Redskins", "gm_nome": "Cristian Paris"},
      {"id": "t2", "nome": "No Trade Knicks", "gm_nome": "Marco Rossi"},
      {"id": "t3", "nome": "Red Devils", "gm_nome": "Mario Rossini"}]
_c = {q: (cerca_squadra(q, _S) or {}).get("id") for q in
      ("Paris", "redskins", "Redskin", "redsk", "paris redskins", "Rossi", "rossin", "knicks", "Devils", "zzzz")}
ok(_c == {"Paris": "t1", "redskins": "t1", "Redskin": "t1", "redsk": "t1", "paris redskins": "t1", "Rossi": "t2",
          "rossin": "t3", "knicks": "t2", "Devils": "t3", "zzzz": None},
   f"parola per parola: cognome del GM, seconda parola della squadra, inizio, errore, mescolate; Rossi ≠ Rossini {_c}")
from shared.squadre import per_parole
ok(per_parole("ross", _S) is None, "parola che va bene per due squadre (Rossi, Rossini): nessuna, non una a caso")


class Msg:
    def __init__(s): s.t = []
    async def reply_text(s, t, **k): s.t.append(t)


def team(args, uid=101):
    m = Msg()
    asyncio.run(__import__("handlers.admin_squadre", fromlist=["cmd_team"]).cmd_team(
        types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=m),
        types.SimpleNamespace(args=args)))
    return m.t[-1]


ok("Gamma" in team(["gam"]), "/team gam → Gamma")
ok("Alfa" in team([]), "/team senza argomento: la propria squadra")
ok("Uso" in team([], uid=999), "/team senza argomento e senza squadra: istruzioni")
ok("Nessuna squadra" in team(["zzzz"]), "/team con un nome che non esiste")
# giocatori scritti con le parole in un altro ordine (Luca, 31/10: «Clowney Noah»)
import utils as _U
from shared import parole_nome as PN
ok(PN.stesse_parole("Clowney Noah", "Noah Clowney") and PN.stesse_parole("jackson jaren jr", "Jaren Jackson Jr.")
   and PN.contiene_parole("clown noah", "Noah Clowney") and not PN.stesse_parole("Noah", "Noah Clowney"),
   "parole del nome: stesso nome in un altro ordine, suffissi e pezzi di parola")
ok(_U.trova_giocatore_generico("Clowney Noah", ["Noah Clowney", "Noah Penda"]) == ("Noah Clowney", None)
   and _U.trova_giocatore_generico("Clowny Noah", ["Noah Clowney", "Noah Penda"]) == (None, "Noah Clowney"),
   "bot aste: cognome e nome invertiti trovano il giocatore (anche con un errore, come proposta)")
_vfa = _U.get_fa_players
_U.get_fa_players = lambda: ["Noah Clowney", "Noah Penda", "Jalen Johnson"]
ok(_U.trova_giocatore_fa("Clowney Noah")[0] == "Noah Clowney" and _U.trova_giocatore_fa("johnson jalen")[0] == "Jalen Johnson",
   "bot aste: lista FA con cognome e nome invertiti")
_U.get_fa_players = _vfa

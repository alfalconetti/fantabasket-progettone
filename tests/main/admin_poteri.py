import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v5.12.0 (Luca, 19/10): dal menu normale un admin che è anche GM ha le stesse regole degli altri GM
(sua squadra, fase, deadline); i poteri da admin solo dal pannello admin e dai comandi admin."""
import asyncio, json, os, types
from datetime import datetime, timedelta
import database as db, settings, teams as tm
from handlers import ruoli as RU, ruoli_rs as RS, trade_comune as TC
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
T = tm.get_all_teams()
MIO, ALTRO = T[0]["id"], T[1]["id"]
ADMIN_GM, SOLO_GM = 4242, 4343
settings.admin_ids = lambda: [ADMIN_GM]
tm.get_team_by_gm = lambda uid: {ADMIN_GM: T[0], SOLO_GM: T[1]}.get(uid)
P = os.environ["GLOBALS_PATH"]
g = json.load(open(P)); g["fase"] = "offseason-ruoli"
g["deadline_ruoli"] = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
json.dump(g, open(P, "w"))

# dichiarazione ruoli
ok("deadline" in (RU._accesso(ADMIN_GM, MIO) or ""), "admin e GM, dal menu normale: dopo la deadline bloccato come gli altri")
ok("tua squadra" in (RU._accesso(ADMIN_GM, ALTRO) or ""), "admin e GM, dal menu normale: non tocca le altre squadre")
ok(RU._accesso(ADMIN_GM, MIO, admin_mode=True) is None and RU._accesso(ADMIN_GM, ALTRO, admin_mode=True) is None,
   "dal pannello admin (modalità admin): qualsiasi squadra, anche dopo la deadline")
ok(RU._accesso(SOLO_GM, ALTRO, admin_mode=True) == "⛔ Solo admin.", "la modalità admin è solo per gli admin")
kb = RU._kb_vista(MIO, [{"gid": 1, "nome": "X", "eleggibili": ["PG"], "ufficiale": None, "bozza": None, "auto": "PG", "scelta": "PG"}], admin=False)
kba = RU._kb_vista(MIO, [{"gid": 1, "nome": "X", "eleggibili": ["PG"], "ufficiale": None, "bozza": None, "auto": "PG", "scelta": "PG"}], admin=True)
cb = lambda k: [b.callback_data for r in k.inline_keyboard for b in r]
ok(all(c.startswith("rl:") for c in cb(kb)) and all(c.startswith("rla:") for c in cb(kba)), "bottoni distinti: rl: (GM) e rla: (admin)")
risposte = []
class Q:
    def __init__(s, data, uid): s.data, s.from_user = data, types.SimpleNamespace(id=uid, first_name="X")
    async def answer(s, t=None, **k): risposte.append(t)
    async def edit_message_text(s, *a, **k): risposte.append("edit")
CTX = types.SimpleNamespace(bot=None, user_data={})
asyncio.run(RU.cb_ruoli(types.SimpleNamespace(callback_query=Q(f"rl:v:{MIO}", ADMIN_GM)), CTX))
ok(risposte and "deadline" in str(risposte[-1]), "bottone GM dopo la deadline: rifiutato anche all'admin")

# ruoli in sospeso
RS.get_pendente = lambda pid: {"id": pid, "team_id": ALTRO, "stato": "chiusa", "nome_common": "Y", "ruolo": "PG"}
risposte.clear()
asyncio.run(RS.cb_dichiara(types.SimpleNamespace(callback_query=Q("rp:7:PG", ADMIN_GM)), CTX))
ok("Non puoi dichiarare" in str(risposte[0]), "ruolo in sospeso di un'altra squadra coi bottoni del GM: rifiutato all'admin")
risposte.clear()
asyncio.run(RS.cb_dichiara(types.SimpleNamespace(callback_query=Q("rpa:7:PG", ADMIN_GM)), CTX))
ok("già chiusa" in str(risposte[0]), "coi bottoni del pannello admin (rpa:): l'admin passa")
risposte.clear()
asyncio.run(RS.cb_dichiara(types.SimpleNamespace(callback_query=Q("rpa:7:PG", SOLO_GM)), CTX))
ok("Solo admin" in str(risposte[0]), "bottoni rpa: solo per gli admin")

# bozze trade
ok(not TC._puo_gestire_bozza(ADMIN_GM, {"proposta_da": ALTRO}) and TC._puo_gestire_bozza(ADMIN_GM, {"proposta_da": MIO})
   and TC._puo_gestire_bozza(ADMIN_GM, {"proposta_da": "admin"}) and not TC._puo_gestire_bozza(SOLO_GM, {"proposta_da": "admin"}),
   "bozze trade: solo il GM che l'ha fatta (le bozze «admin» agli admin)")

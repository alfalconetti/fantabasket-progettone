import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""/riassegna nel bot principale (v6.25.0) e richieste di accesso col menu (v6.26.0): la franchigia passa a un nuovo GM (gm_ids e gm_nome di teams.json),
con conferma, registro, avvisi al vecchio e al nuovo GM."""
import asyncio, types, json
import database as db, teams as tm
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
import gas_client; gas_client.sync_teams = lambda ids: True     # niente rete
from handlers.admin_panel import cmd_riassegna, cb_riassegna
orig = open(tm.TEAMS_PATH, encoding="utf-8").read()
out, mandati = [], []
class M:
    async def reply_text(s, t, **k): out.append((t, k.get("reply_markup")))
class Bot:
    async def send_message(s, *a, **k): mandati.append((a[0] if a else k.get("chat_id"), a[1] if len(a) > 1 else k.get("text")))
class Q:
    def __init__(s, uid, data): s.from_user, s.data, s.testo = types.SimpleNamespace(id=uid, full_name="Admin", username=None), data, None
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.testo = t
ud = {}
ctx = lambda args=None: types.SimpleNamespace(args=args or [], bot=Bot(), user_data=ud)
def cmd(uid, args):
    out.clear()
    asyncio.run(cmd_riassegna(types.SimpleNamespace(effective_message=M(), effective_user=types.SimpleNamespace(id=uid)), ctx(args)))
    return out[-1] if out else ("", None)
def cb(uid, data):
    q = Q(uid, data)
    asyncio.run(cb_riassegna(types.SimpleNamespace(callback_query=q), ctx()))
    return q.testo or ""
vecchi = tm.get_team_by_id("team02")["gm_ids"]
ok("Solo admin" in cmd(101, ["team02", "555", "Nuovo GM"])[0], "un GM non può")
ok("Uso" in cmd(900, ["team02"])[0] and "non trovata" in cmd(900, ["team99", "555", "X"])[0], "uso e squadra sbagliata")
ok("già GM" in cmd(900, ["team02", str(tm.get_team_by_id("team01")["gm_ids"][0]), "X"])[0], "un GM, una squadra")
t, kb = cmd(900, ["team02", "555", "Nuovo", "GM"])
ok("Riassegnare" in t and kb is not None and tm.get_team_by_id("team02")["gm_ids"] == vecchi, "prima la conferma, niente cambia")
ok("annullata" in cb(900, "riass:no") and tm.get_team_by_id("team02")["gm_ids"] == vecchi, "annulla: niente cambia")
cmd(900, ["team02", "555", "Nuovo", "GM"])
ok("Solo admin" not in cb(101, "riass:ok:team02:555") and tm.get_team_by_id("team02")["gm_ids"] == vecchi, "bottone premuto da un GM: niente")
mandati.clear()
r = cb(900, "riass:ok:team02:555")
t2 = tm.get_team_by_id("team02")
ok("riassegnata" in r and t2["gm_ids"] == [555] and t2["gm_nome"] == "Nuovo GM" and t2.get("nome"), f"conferma: gm_ids e gm_nome cambiati, il resto no {t2}")
ok(any(c == 555 for c, _ in mandati) and all(any(c == int(v) for c, _ in mandati) for v in vecchi), "avvisati il nuovo e il vecchio GM")
ok(tm.is_gm(555) and not any(tm.is_gm(int(v)) for v in vecchi), "il nuovo è GM, il vecchio no")
ok(db._q("SELECT COUNT(*) AS n FROM registro_azioni WHERE azione = 'riassegnazione franchigia'", one=True)["n"] >= 1, "nel registro")
ok("scaduta" in cb(900, "riass:ok:team02:555"), "rilanciare il bottone dopo: scaduta")

# ── richiesta di accesso (v6.26.0): dal bottone dello sconosciuto al dev, poi squadra e conferma ──
open(tm.TEAMS_PATH, "w", encoding="utf-8").write(orig)
from handlers import accesso as AC
AC.migra(); db._q("TRUNCATE richieste_accesso")
class Q2(Q):
    def __init__(s, uid, data, nome="Nuovo Tizio", username="tizio"):
        super().__init__(uid, data); s.alert = None
        s.from_user = types.SimpleNamespace(id=uid, full_name=nome, username=username)
    async def answer(s, *a, **k): s.alert = a[0] if a else None
mandati.clear()
q = Q2(777, "accesso:chiedi")
asyncio.run(AC.richiedi(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), ctx()))
ok("Richiesta inviata" in (q.testo or "") and mandati and mandati[-1][0] == 900 and "777" in mandati[-1][1] and "@tizio" in mandati[-1][1],
   "richiesta: salvata, al dev con nome, username e user_id; allo sconosciuto «inviata»")
q = Q2(777, "accesso:chiedi")
asyncio.run(AC.richiedi(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), ctx()))
ok(len(mandati) == 1 and "già arrivata" in (q.alert or ""), "seconda richiesta entro 24 ore: non arriva di nuovo al dev")
def cb2(uid, data):
    q = Q2(uid, data)
    asyncio.run(AC.cb(types.SimpleNamespace(callback_query=q), ctx()))
    return q
ok(cb2(101, "riass:menu").testo is None, "menu: solo admin")
qm = Q2(900, "riass:menu"); asyncio.run(AC.cb(types.SimpleNamespace(callback_query=qm), ctx()))
ok("in attesa" in qm.testo, "menu admin: le richieste in attesa")
qs = cb2(900, "riass:utente:777")
ok("A quale squadra" in qs.testo, "assegna: scelta della squadra")
qc = Q2(900, "riass:sq:777:team03")
qc_testo = []
async def _e(t, **k): qc_testo.append((t, k.get("reply_markup")))
qc.edit_message_text = _e
asyncio.run(AC.cb(types.SimpleNamespace(callback_query=qc), ctx()))
ok(qc_testo and "Riassegnare" in qc_testo[0][0] and "Nuovo Tizio" in qc_testo[0][0] and tm.get_team_by_id("team03")["gm_ids"] != [777],
   "squadra scelta: il riepilogo da confermare, col nome Telegram; niente cambia ancora")
r = cb(900, "riass:ok:team03:777")
ok("riassegnata" in r and tm.get_team_by_id("team03")["gm_ids"] == [777] and AC.richiesta(777)["stato"] == "assegnata",
   "conferma: squadra assegnata, richiesta segnata come assegnata")
qm = Q2(900, "riass:menu"); asyncio.run(AC.cb(types.SimpleNamespace(callback_query=qm), ctx()))
ok("Nessuna richiesta" in qm.testo, "menu: la richiesta assegnata non c'è più")
mandati.clear()
q = Q2(778, "accesso:chiedi"); asyncio.run(AC.richiedi(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), ctx()))
ok("ignorata" in cb2(900, "riass:ignora:778").testo and AC.richiesta(778)["stato"] == "ignorata", "ignora")
from handlers.admin_panel import _kb_admin_home
ok(any(b.callback_data == "riass:menu" for r in _kb_admin_home().inline_keyboard for b in r), "voce nel menu admin")
db._q("TRUNCATE richieste_accesso")
open(tm.TEAMS_PATH, "w", encoding="utf-8").write(orig)

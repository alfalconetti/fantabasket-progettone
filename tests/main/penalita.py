import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v5.6.0: penalità date dagli admin (motivazione, canale, GM, log, foglio Scelte), revoca,
conteggio per stagione con lo storico."""
import asyncio, json, types
import database as db, settings, teams as tm
from handlers import penalita as P
db.init_db(); db.migrate_db(); P.migra()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db._q("TRUNCATE penalita")
G = json.load(open(settings.GLOBALS_PATH)) if hasattr(settings, "GLOBALS_PATH") else None
glob = settings.load_globals()
CANALE, LOG = -100, -300
settings.load_globals = lambda: {**glob, "main_channel_id": CANALE, "log_channel_id_main": LOG}
ADMIN = int(settings.admin_ids()[0])
T = tm.get_all_teams()[0]
GM = int(T["gm_ids"][0])
sincr = []
import gas_client
gas_client.sync_scelte = lambda *a, **k: sincr.append(1)

class Bot:
    def __init__(s): s.mandati, s.modifiche, s.n = [], [], 500
    async def send_message(s, chat_id, text, **k):
        s.n += 1; s.mandati.append({"chat_id": chat_id, "text": text, "id": s.n}); return types.SimpleNamespace(message_id=s.n)
    async def edit_message_text(s, chat_id=None, message_id=None, text=None, **k):
        s.modifiche.append({"chat_id": chat_id, "id": message_id, "text": text})
BOT = Bot()
class Q:
    def __init__(s, data, uid): s.data, s.from_user, s.testi, s.risposte = data, types.SimpleNamespace(id=uid, first_name="Luca"), [], []
    async def answer(s, t=None, **k): s.risposte.append(t)
    async def edit_message_text(s, t, **k): s.testi.append((t, k))
class Msg:
    def __init__(s, t=""): s.text, s.risposte = t, []
    async def reply_text(s, t, **k): s.risposte.append((t, k))
CTX = types.SimpleNamespace(bot=BOT, user_data={}, args=[])
def upd(uid, q=None, msg=None, chat="private"):
    return types.SimpleNamespace(callback_query=q, effective_message=msg, effective_user=types.SimpleNamespace(id=uid, first_name="Luca"),
                                 effective_chat=types.SimpleNamespace(type=chat))
def premi(data, uid=ADMIN):
    q = Q(data, uid); asyncio.run(P.cb_penalita(upd(uid, q), CTX)); return q

ok(premi("pen:new", GM).risposte == ["⛔ Solo admin."], "solo gli admin danno penalità")
q = Q(f"pen:s:{T['id']}", ADMIN)
st = asyncio.run(P.cb_squadra(upd(ADMIN, q), CTX))
ok(st == P.MOTIVO and "motivazione" in q.testi[-1][0], "squadra scelta: chiede la motivazione")
m = Msg("Panchina mandata dopo la scadenza per la terza volta")
asyncio.run(P.msg_motivo(upd(ADMIN, msg=m), CTX))
ok("Anteprima" in m.risposte[-1][0] and "la 1ª della stagione" in m.risposte[-1][0], "anteprima prima di confermare")
ok(not db._q("SELECT 1 FROM penalita", one=True), "niente salvato prima della conferma")
q = premi("pen:ok")
can = [x for x in BOT.mandati if x["chat_id"] == CANALE]
gm = [x for x in BOT.mandati if x["chat_id"] == GM]
ok(len(can) == 1 and "Penalità a" in can[0]["text"] and "terza volta" in can[0]["text"] and gm and "la 1ª" in gm[0]["text"]
   and any(x["chat_id"] == LOG for x in BOT.mandati) and sincr, "confermata: canale, GM, log, foglio Scelte")
ok(premi("pen:ok").risposte[-1].startswith("Niente da confermare"), "doppio tocco su Conferma: una sola penalità")
ok(P.conteggi() == {T["id"]: 1}, "conteggio della stagione")
P.aggiungi(T["id"], "Seconda", "Luca", ADMIN)
ok(P.conteggi()[T["id"]] == 2 and "<b>2</b>" in P.testo_squadra(T["id"]), "si sommano: 2")
# revoca
pid = db._q("SELECT id FROM penalita ORDER BY id LIMIT 1", one=True)["id"]
premi(f"pen:r:{pid}")
BOT.mandati.clear()
q = premi(f"pen:rok:{pid}")
ok(P.conteggi()[T["id"]] == 1 and any(x["id"] == can[0]["id"] and "Revocata" in x["text"] for x in BOT.modifiche)
   and any(x["chat_id"] == GM and "revocata" in x["text"] for x in BOT.mandati), "revoca: conteggio giù, canale corretto, GM avvisato")
ok("<s>" in P.testo_squadra(T["id"], admin=True) and "<s>" not in P.testo_squadra(T["id"]), "le revocate le vede solo l'admin (barrate)")
ok(premi(f"pen:rok:{pid}").risposte[-1] == "Già revocata.", "revoca due volte: no")
# stagione nuova: si azzerano, resta lo storico
db._q("UPDATE penalita SET stagione = '2000'")
ok(P.conteggi() == {} and "Storico: 2000: 1" in P.testo_squadra(T["id"]), "stagione nuova: zero, nello storico quella vecchia")
# GM: /penalita la propria squadra
m = Msg(); asyncio.run(P.cmd_penalita(upd(GM, msg=m), CTX))
ok("Penalità di" in m.risposte[-1][0], "/penalita del GM: la sua squadra")
# foglio Scelte: il numero nel payload
db._q("UPDATE penalita SET stagione = %s", (settings.stagione_corrente(),))
try:
    pay = gas_client._build_scelte_payload()
    ok(next(t for t in pay["teams"] if t["team_id"] == T["id"])["penalita"] == 1, "payload del foglio Scelte: penalita")
except FileNotFoundError:
    print("(divisions.json assente: payload Scelte non provato)")
db._q("TRUNCATE penalita")

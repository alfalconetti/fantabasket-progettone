"""I bot sono solo per la lega (shared/solo_lega, Luca 31/10): in privato rispondono solo GM, admin e dev (agli altri
«bot riservato ai GM»), dai gruppi e canali che non sono della lega escono da soli e lo dicono al dev."""
import asyncio, json, os, sys, tempfile
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from shared import solo_lega as L
from telegram.ext import ApplicationHandlerStop

for bot in ("fantabasket-main", "fantabasket-aste-beta", "fantabasket-ipanchinari", "fantabasket-loucabot"):
    t = open(os.path.join(ROOT, bot, "bot.py"), encoding="utf-8").read()
    ok("solo_lega.installa(app)" in t and t.index("solo_lega.installa") < t.index("solo_gruppo_admin.installa"),
       f"{bot}: guardia della lega installata, prima di quella dei comandi admin")

# config finta: GM 101 e 102, admin e dev 900, chat della lega -1 (canale), -2 (gruppo admin), -5 (gruppo della lega)
d = tempfile.mkdtemp()
json.dump({"admin_ids": [900], "dev_id": 900, "main_channel_id": -1, "admin_group_id": "-2", "gruppo_lega_id": -5,
           "stagione_corrente": "2026", "mercato_aperto": True}, open(os.path.join(d, "g.json"), "w"))
json.dump({"teams": [{"id": "team01", "gm_ids": [101]}, {"id": "team02", "gm_ids": ["102"]}]}, open(os.path.join(d, "t.json"), "w"))
os.environ["GLOBALS_PATH"], os.environ["TEAMS_PATH"] = os.path.join(d, "g.json"), os.path.join(d, "t.json")
ok(L.autorizzati() == {101, 102, 900} and L.chat_della_lega() == {-1, -2, -5}, "GM, admin e dev; chat della lega da globals.json")
ok(L.esito("private", 101, 101) == "ok" and L.esito("private", 900, 900) == "ok" and L.esito("private", 555, 555) == "riservato",
   "in privato: GM e admin sì, gli altri no")
ok(L.esito("supergroup", -5, 555) == "ok" and L.esito("supergroup", -2, 555) == "ok" and L.esito("channel", -1, None) == "ok",
   "nei gruppi e canali della lega: tutti")
ok(L.esito("supergroup", -999, 101) == "esci" and L.esito("channel", -998, None) == "esci", "gruppo o canale sconosciuto: esce (anche se a scrivere è un GM)")


class Bot:
    def __init__(self): self.fatto = []
    async def leave_chat(self, c): self.fatto.append(("esci", c))
    async def send_message(self, c, t, **k): self.fatto.append(("msg", c, t))
    async def answer_guest_query(self, **k): self.fatto.append(("guest", k["result"].title))


class Msg:
    def __init__(self, f): self.f = f
    async def reply_text(self, t, **k): self.f.append(("risposta", t))


def upd(tipo, chat_id, uid, **x):
    b = Bot()
    u = NS(effective_chat=NS(type=tipo, id=chat_id, title="Gruppo X", username=None),
           effective_user=NS(id=uid, full_name="Tizio") if uid else None,
           effective_message=Msg(b.fatto), callback_query=None, inline_query=None, my_chat_member=None, guest_message=None)
    for k, v in x.items():
        setattr(u, k, v)
    return u, NS(bot=b), b


def gira(u, c):
    try:
        asyncio.run(L.guardia(u, c))
        return "passa"
    except ApplicationHandlerStop:
        return "fermo"

u, c, b = upd("private", 555, 555)
ok(gira(u, c) == "fermo" and b.fatto == [("risposta", L.RISERVATO)] and "scrivi al dev" in L.RISERVATO,
   "sconosciuto in privato: «bot riservato ai GM», e se è un errore il dev")
u, c, b = upd("private", 101, 101)
ok(gira(u, c) == "passa" and not b.fatto, "GM in privato: passa")
u, c, b = upd("supergroup", -999, 555)
ok(gira(u, c) == "fermo" and ("esci", -999) in b.fatto and any(x[0] == "msg" and x[1] == 900 and "sono uscito" in x[2] for x in b.fatto),
   "gruppo sconosciuto: esce e lo dice al dev")
u, c, b = upd("supergroup", -999, 555, my_chat_member=NS(new_chat_member=NS(status="left")))
ok(gira(u, c) == "passa" and not b.fatto, "uscito (o tolto) da un gruppo: niente di più")
u, c, b = upd("supergroup", -5, 555)
ok(gira(u, c) == "passa", "gruppo della lega: passa")
fatti = []
async def _segna(f, t): f.append(t)
u, c, b = upd("private", 555, 555, callback_query=NS(answer=lambda t, show_alert=False: _segna(fatti, t)))
ok(gira(u, c) == "fermo" and fatti == [L.RISERVATO], "bottone premuto da uno sconosciuto: l'avviso")
u, c, b = upd("private", 555, 555, guest_message=NS(from_user=NS(id=555), guest_query_id="q1"))
ok(gira(u, c) == "fermo" and b.fatto == [("guest", "Bot riservato ai GM della lega")], "guest mode da uno sconosciuto: riservato")
u, c, b = upd("private", 101, 101, guest_message=NS(from_user=NS(id=101), guest_query_id="q2"))
ok(gira(u, c) == "passa", "guest mode da un GM: passa")
json.dump({"teams": [{"id": "team01", "gm_ids": [101, 555]}]}, open(os.path.join(d, "t.json"), "w"))
os.utime(os.path.join(d, "t.json"), (1e9 + 5, 1e9 + 5))
ok(L.esito("private", 555, 555) == "ok", "GM nuovo in teams.json: autorizzato senza riavvio")
json.dump({}, open(os.path.join(d, "g.json"), "w"))
os.utime(os.path.join(d, "g.json"), (1e9 + 7, 1e9 + 7))
ok(L.esito("supergroup", -999, 1) == "ok", "globals.json senza chat: non esce da niente (meglio che uscire dal gruppo admin)")

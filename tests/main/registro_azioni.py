import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v6.0.0 (Luca, 19/10): registro delle azioni. Ogni azione lascia una riga (chi, veste, cosa, squadre,
prima → dopo); admin e dev anche sul canale log in un formato unico, GM e job solo nel registro; il
registro non fa mai fallire un'azione; /registro: admin tutto, GM solo la sua squadra."""
import asyncio, io, json, os, types
import database as db, settings, teams as tm
from shared import azioni as A
from handlers import registro as RG
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db._q("DELETE FROM registro_azioni")
ok(db._qval("SELECT to_regclass('registro_azioni') IS NOT NULL"), "migrate_db crea la tabella")

# ── shared/azioni ──
u = types.SimpleNamespace(id=900, full_name="Luca F", username="luca")
r = A.registra(db._q, "main", u, "admin", "prova", squadre="team01", giocatore_id=None, oggetto="X", prima=1, dopo={"a": 1})
ok(r and r["chi_nome"] == "Luca F (@luca)" and r["squadre"] == ["team01"] and r["prima"] == "1" and r["dopo"] == '{"a": 1}',
   "registra: chi, squadre come lista, prima e dopo come testo")
ok(A.registra(db._q, "main", u, "boh", "prova") is None, "veste sconosciuta: niente riga (e niente eccezione)")
def rotto(*a, **k): raise RuntimeError("db giù")
ok(A.registra(rotto, "main", u, "admin", "prova") is None, "database giù: registra non solleva")
riga = A.riga_log({"veste": "admin", "chi_nome": "Luca <F>", "azione": "taglio", "squadre": ["team01", "team02"],
                   "oggetto": "LeBron", "prima": "20M × 2", "dopo": "tagliato", "nota": "gratuito"}, lambda t: {"team01": "Alfa"}.get(t, t))
ok(riga == "🛠 admin Luca &lt;F&gt; · <b>taglio</b> · Alfa · team02\nLeBron: 20M × 2 → <b>tagliato</b> · <i>gratuito</i>",
   "riga di log nel formato unico, HTML protetto: " + riga.replace("\n", " | "))
ok(A.riga_log({"veste": "dev", "chi_nome": "D", "azione": "sync"}).startswith("🧰 dev D · <b>sync</b>"), "dev: 🧰")

mandati = []
class Bot:
    async def send_message(self, **k): mandati.append(k)
class BotRotto:
    async def send_message(self, **k): raise RuntimeError("telegram giù")
asyncio.run(A.azione(rotto, Bot(), -3, "main", u, "admin", "senza db", oggetto="Y", prima="a", dopo="b"))
ok(mandati and mandati[-1]["chat_id"] == -3 and "Y: a → <b>b</b>" in mandati[-1]["text"],
   "database giù: la riga sul canale log arriva lo stesso")
ok(asyncio.run(A.azione(db._q, BotRotto(), -3, "main", u, "admin", "telegram giù")) is not None, "Telegram giù: la riga nel registro c'è")
mandati.clear()
asyncio.run(RG.segna(Bot(), types.SimpleNamespace(id=101, full_name="GM Alfa", username=None), "gm", "palette", squadre="team01"))
asyncio.run(RG.segna(Bot(), None, "sistema", "job", squadre="team01"))
ok(not mandati, "gm e sistema: niente sul canale log")
asyncio.run(RG.segna(Bot(), u, "dev", "sync dei fogli", dopo="fatto"))
ok(len(mandati) == 1 and mandati[0]["chat_id"] == -3 and mandati[0]["text"].startswith("🧰 dev Luca F (@luca)"),
   "dev: sul canale log del bot principale")

# ── comandi admin che prima non lasciavano niente ──
from handlers import admin_panel as AP, stagione as ST, ruoli as RU
risposte = []
class M:
    async def reply_text(s, t, **k): risposte.append(t)
def cmd(f, args, uid=900):
    upd = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid, first_name="Luca", full_name="Luca", username="luca"),
                                effective_message=M(), effective_chat=types.SimpleNamespace(id=uid, type="private"))
    asyncio.run(f(upd, types.SimpleNamespace(args=args, bot=Bot(), user_data={})))
import gas_client; gas_client.sync_teams = lambda ids: True
mandati.clear()
cmd(AP.cmd_set_cap_penalizzato, ["team02", "4"])
r = db._q("SELECT * FROM registro_azioni WHERE azione = 'cap penalizzato'", one=True)
ok(r and r["veste"] == "admin" and r["squadre"] == ["team02"] and r["prima"] == "0M" and r["dopo"] == "4M", "/set_cap_penalizzato nel registro")
ok(any(m["chat_id"] == -3 and "<b>cap penalizzato</b> · Beta" in m["text"] for m in mandati), "/set_cap_penalizzato sul canale log")
g = json.load(open(os.environ["GLOBALS_PATH"])); s = int(g["stagione_corrente"])
cmd(ST.cmd_trade_deadline, [f"{s + 1}-02-05"])
ok(db._qval("SELECT dopo FROM registro_azioni WHERE azione = 'trade deadline'") == f"{s + 1}-02-05", "/trade_deadline nel registro")
cmd(RU.cmd_deadline_ruoli, [f"{s}-10-20", "23:59"])
ok(db._qval("SELECT dopo FROM registro_azioni WHERE azione = 'deadline ruoli'") == "20/10 alle 23:59", "/deadline_ruoli nel registro")
cmd(AP.cmd_set_cap_penalizzato, ["team02", "4"], uid=101)
ok(db._qval("SELECT count(*) FROM registro_azioni WHERE azione = 'cap penalizzato'") == 1, "comando rifiutato (GM): nessuna riga")

# ── /registro ──
A.registra(db._q, "aste", (102, "GM Beta"), "gm", "offerta", squadre=["team02"], oggetto="Tizio (asta FA #3)", dopo="5M Beta")
A.registra(db._q, "main", (900, "Luca"), "admin", "trade approvata ed eseguita", squadre=["team01", "team02"], oggetto="TRADE-1")
file_ = []
class BotF(Bot):
    async def send_document(self, **k): file_.append(k)
def registro(uid, args):
    file_.clear(); risposte.clear()
    upd = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=M(),
                                effective_chat=types.SimpleNamespace(id=uid, type="private"))
    asyncio.run(RG.cmd_registro(upd, types.SimpleNamespace(args=args, bot=BotF())))
    return file_[0]["document"].getvalue().decode() if file_ else (risposte[-1] if risposte else "")
t = registro(900, [])
ok(t.startswith("# Registro delle azioni") and "| Quando | Bot | Chi |" in t and "cap penalizzato" in t and "bot aste" in t,
   "admin: tutto, in Markdown, anche le righe del bot aste")
t = registro(101, [])
ok("TRADE-1" in t and "cap penalizzato" not in t and "Tizio" not in t, "GM di Alfa: solo le righe con la sua squadra (la trade sì)")
ok("solo il registro della tua squadra" in registro(101, ["Beta"]), "GM: un'altra squadra no")
ok("Tizio" in registro(102, ["aste"]) and "TRADE-1" not in registro(102, ["aste"]), "GM di Beta, filtro aste")
ok("⛔" in registro(999, []), "chi non è GM né admin: niente")
t = registro(900, ["admin", "cap"])
ok("cap penalizzato" in t and "trade deadline" not in t and "veste admin" in t, "filtri: veste e azione")
f, d = RG.filtri(["30", "loucabot", "@luca", "Gamma"])
ok(f == {"giorni": 30, "bot": "louca", "chi_testo": "@luca", "squadra": "team03"}, f"filtri: giorni, bot, chi, squadra {f}")
# pannello admin
q = types.SimpleNamespace(from_user=types.SimpleNamespace(id=101), message=types.SimpleNamespace(chat_id=101), data="reg:7",
                          answer=lambda *a, **k: asyncio.sleep(0))
file_.clear(); asyncio.run(RG.cb_registro(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=BotF())))
ok(not file_, "📜 Registro del pannello: solo admin")
q.from_user = types.SimpleNamespace(id=900)
asyncio.run(RG.cb_registro(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=BotF())))
ok(file_ and "ultimi 7 giorni" in file_[0]["caption"], "📜 Registro del pannello: gli ultimi 7 giorni")
kb = [b.callback_data for r in AP._kb_admin_home().inline_keyboard for b in r]
ok("reg:7" in kb, "📜 Registro nel pannello admin")
db._q("DELETE FROM registro_azioni")
_ = (io, settings, tm)

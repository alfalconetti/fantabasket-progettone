import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.38.0 (Luca, 27/11): «nessuna trade si può eseguire dopo la deadline, solo gli admin possono forzare dal loro
pannello con un warning aggiuntivo». Esecuzione rifiutata a trade chiuse; approvazione admin e «Ufficializza ora» con
l'avviso e il bottone ⚠️ Forza; voti dei GM fermi; al cambio di fase l'elenco delle trade rimaste a metà."""
import asyncio, types, json, os
import database as db
db.init_db(); db.migrate_db()
db._q("TRUNCATE trade RESTART IDENTITY CASCADE")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
def fase(f):
    g = json.load(open(os.environ["GLOBALS_PATH"])); g["fase"] = f; json.dump(g, open(os.environ["GLOBALS_PATH"], "w"))
import settings
S = settings.stagione_corrente()
from handlers import trade_esegui as TE, trade_voto as TV, admin_panel as A, stagione as ST
class Bot:
    async def send_message(self, **k): pass
class Q:
    def __init__(s, data, uid=900):
        s.data, s.t, s.kb = data, None, None
        s.from_user = types.SimpleNamespace(id=uid, first_name="Adm", username="adm")
        s.message = types.SimpleNamespace(text_html="📨 Trade")
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.t, s.kb = t, k.get("reply_markup")
def tap(cb, data, uid=900):
    q = Q(data, uid); asyncio.run(cb(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), types.SimpleNamespace(bot=Bot()))); return q
def bottoni(kb): return [b.callback_data for r in kb.inline_keyboard for b in r] if kb else []
tid = db.crea_trade_bozza("team01", 2, S)
db._q("UPDATE trade SET stato='in_approvazione' WHERE id=%s", (tid,))
fase("regular-season-deadline")
try:
    asyncio.run(TE._esegui_trade(types.SimpleNamespace(bot=Bot()), tid, "TRADE-X"))
    ok(False, "doveva rifiutare")
except TE.TradeNonEseguibile as e:
    ok("chiuse" in str(e), f"a trade chiuse l'esecuzione si rifiuta ({e})")
q = tap(TV.cb_admin_trade, f"trade_admin:ok:{tid}")
ok("Le trade sono chiuse" in q.t and f"trade_admin:forza:{tid}" in bottoni(q.kb) and db.get_trade(tid)["stato"] == "in_approvazione",
   "Approva a trade chiuse: avviso e bottone ⚠️ Forza, la trade resta in attesa")
q = tap(A.cb_ufficializza, f"adm_uff:{tid}")
ok("Le trade sono chiuse" in q.t and f"adm_uff:{tid}:forza" in bottoni(q.kb), "Ufficializza ora dal pannello: avviso e ⚠️ Forza")
t2 = db.crea_trade_bozza("team02", 2, S)
db._q("UPDATE trade SET stato='proposta' WHERE id=%s", (t2,))
db._q("INSERT INTO trade_voti (trade_id, team_id) VALUES (%s, 'team02')", (t2,)) if db._q("SELECT to_regclass('trade_voti') AS t", one=True)["t"] else None
import teams as tm
gm = (tm.get_team_by_id("team02") or {}).get("gm_ids", [0])[0]
q = tap(TV.cb_voto_gm, f"trade_voto:si:{t2}:team02", uid=int(gm))
ok("chiuse" in (q.t or ""), f"i voti dei GM sono fermi ({q.t})")
testo = ST.testo_trade_ferme()
ok("rimaste a metà" in testo and testo.count("•") == 2, "al cambio di fase: l'elenco delle trade rimaste a metà")
fase("regular-season-fa")
q = tap(TV.cb_admin_trade, f"trade_admin:ok:{tid}")
ok("Le trade sono chiuse" not in (q.t or ""), "a trade aperte niente avviso (si prova a eseguire)")
db._q("TRUNCATE trade RESTART IDENTITY CASCADE")

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""Registro delle azioni dal bot aste (aste v68, main v6.0.0): righe con bot 'aste', squadre e giocatore
presi dall'asta; azioni admin anche sul canale log del bot aste nel formato unico."""
import asyncio, types
from datetime import datetime, timedelta, timezone
import database as db, pg_client as pg
import registro as RG
from shared import azioni as A
pg.init_pg(); db.init_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
A.migra(pg.q); pg.q("DELETE FROM registro_azioni")
gid = pg.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES ('Reg Prova', 'Reg Prova', 'reg prova') RETURNING id", one=True)["id"]
ora = datetime.now(timezone.utc)
aid = db.crea_asta("FA", "Reg Prova", None, ora.isoformat(), (ora + timedelta(hours=18)).isoformat(), stagione="2026")
db.registra_offerta(aid, "team02", 7, ora.isoformat()); db.aggiorna_offerta(aid, "team02", 7, (ora + timedelta(hours=18)).isoformat())
c = RG.campi_asta(db.get_asta(aid), "team03")
ok(c["squadre"] == ["team02", "team03"] and c["giocatore_id"] == gid and c["oggetto"] == f"Reg Prova (asta FA #{aid})",
   f"dall'asta (riga sqlite): squadre, giocatore (per nome) e oggetto {c}")

mandati = []
class Bot:
    username = "astebot"
    async def send_message(self, **k): mandati.append(k); return types.SimpleNamespace(message_id=1)
    async def edit_message_text(self, **k): pass
class JQ:
    def get_jobs_by_name(self, n): return []
class Q:
    def __init__(s, data, uid): s.data, s.from_user, s.t = data, types.SimpleNamespace(id=uid, first_name="Luca", username="luca"), None
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.t = t
from handlers import admin_aste as AA, admin as AD
q = Q(f"admin_annulla:{aid}", 900)
asyncio.run(AA.admin_annulla_callback(types.SimpleNamespace(callback_query=q, effective_user=q.from_user),
                                      types.SimpleNamespace(bot=Bot(), job_queue=JQ())))
r = pg.q("SELECT * FROM registro_azioni WHERE bot = 'aste' AND azione = 'asta annullata'", one=True)
ok(r and r["veste"] == "admin" and r["squadre"] == ["team02"] and r["giocatore_id"] == gid and r["prima"] == "aperta, 7M"
   and r["dopo"] == "annullata" and r["dettagli"]["asta_id"] == aid, f"/annulla_asta: nel registro con prima → dopo {r and dict(r)}")
logl = [m for m in mandati if m.get("chat_id") == -30]
ok(len(logl) == 1 and logl[0]["text"].startswith("🛠 admin Luca (@luca) · <b>asta annullata</b> · Beta"),
   "/annulla_asta: una riga sul canale log del bot aste (log_channel_id), formato unico")
mandati.clear()
upd = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900, first_name="Luca", username="luca", full_name="Luca"),
                            effective_message=types.SimpleNamespace(reply_text=lambda *a, **k: asyncio.sleep(0)))
asyncio.run(AD.chiudi_mercato(upd, types.SimpleNamespace(bot=Bot())))
asyncio.run(AD.apri_mercato(upd, types.SimpleNamespace(bot=Bot())))
reg = pg.q("SELECT prima, dopo FROM registro_azioni WHERE bot = 'aste' AND azione = 'mercato FA' ORDER BY id", many=True)
ok([(x["prima"], x["dopo"]) for x in reg] == [("aperto", "chiuso"), ("chiuso", "aperto")]
   and len([m for m in mandati if m.get("chat_id") == -30]) == 2, "mercato chiuso e riaperto: registro e canale log")
# offerta di un GM: solo nel registro
aid2 = db.crea_asta("FA", "Reg Prova", None, ora.isoformat(), (ora + timedelta(hours=18)).isoformat(), stagione="2026")
from handlers import offerte as OF
mandati.clear()
asyncio.run(OF._registro_offerta(types.SimpleNamespace(bot=Bot()), types.SimpleNamespace(id=103, first_name="G", username=None, full_name="GM Gamma"),
                                 "gm", db.get_asta(aid2), {"id": "team03", "nome": "Gamma"}, 5, False))
r = pg.q("SELECT * FROM registro_azioni WHERE bot = 'aste' AND azione = 'offerta'", one=True)
ok(r and r["veste"] == "gm" and r["squadre"] == ["team03"] and r["dopo"] == "5M Gamma" and r["prima"] == "0M" and not mandati,
   "offerta del GM: nel registro, niente sul canale log")
asyncio.run(OF._registro_offerta(types.SimpleNamespace(bot=Bot()), None, "gm", db.get_asta(aid2), {"id": "team03", "nome": "Gamma"}, 6, False))
ok(pg.q("SELECT count(*) AS n FROM registro_azioni WHERE azione = 'offerta'", one=True)["n"] == 1,
   "offerta per conto (/crea_offerta): la riga la scrive il comando admin, non doppia")
pg.q("DELETE FROM registro_azioni"); pg.q("DELETE FROM giocatori WHERE id = %s", (gid,))

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.38.0 (Luca, 27/11): /annulla_firma_asta — la firma di un'asta FA si annulla e l'asta si riapre con l'offerta in
testa di prima: via contratto e movimento su PG, contratto del bot aste tolto, canale, GM, registro, coda del foglio.
Non dopo altri movimenti del giocatore, non per le RFA."""
import asyncio, types
import database as db, pg_client as pg
from datetime import datetime, timezone
from shared import azioni as A
pg.init_pg(); db.init_db(); A.migra(pg.q)
pg.q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
pg.q("DELETE FROM registro_azioni")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
mandati = []
class Bot:
    username = "bot"
    async def send_message(self, chat_id=None, text="", **k):
        mandati.append({"chat_id": chat_id, "text": text, **k}); return types.SimpleNamespace(message_id=1)
    async def edit_message_text(self, *a, **k): pass
class JQ:
    def get_jobs_by_name(self, n): return []
CTX = types.SimpleNamespace(bot=Bot(), job_queue=JQ(), args=[])
class Q:
    def __init__(s, data, uid):
        s.data, s.from_user, s.testi = data, types.SimpleNamespace(id=uid, first_name="Luca", username="luca", full_name="Luca"), []
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.testi.append((t, k))
def premi(fn, data, uid=900):
    q = Q(data, uid); asyncio.run(fn(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), CTX)); return q
def bottoni(k):
    return [b.callback_data for r in k.inline_keyboard for b in r] if k else []
import handlers.firma as F
ora = datetime.now(timezone.utc)
pg.q("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES ('Per Conto','Per Conto','per conto')")
aid = db.crea_asta(tipo="FA", giocatore="Per Conto", squadra_proprietaria=None, creata_at=ora.isoformat(), scade_at=ora.isoformat())
db.aggiorna_offerta(aid, "team01", 4, ora.isoformat())
db.chiudi_asta(aid, ora.isoformat())

# firma per conto (come in firma_per_conto), poi l'annullamento
q = premi(F.firma_apri_callback, f"pc_firma_apri:{aid}")
q = premi(F.firma_callback, f"pc_firma:{aid}:2")
bs = bottoni(q.testi[-1][1]["reply_markup"])
ruolo = next((b for b in bs if b.startswith("pc_firma_ruolo")), None)
if ruolo:
    q = premi(F.firma_ruolo_callback, ruolo); bs = bottoni(q.testi[-1][1]["reply_markup"])
premi(F.firma_confirm_callback, next(b for b in bs if b.startswith("pc_firma_confirm")))
ok(db.get_asta(aid)["stato"] == "CONCLUSA" and pg.q("SELECT count(*) AS n FROM contratti WHERE attivo", one=True)["n"] == 1, "firmata")
import handlers.admin_annulla_firma as AF
m = types.SimpleNamespace(risposte=[])
async def _r(t, **k): m.risposte.append((t, k))
m.reply_text = _r
def cmd(args, uid=900):
    asyncio.run(AF.cmd_annulla_firma_asta(types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=m),
                                          types.SimpleNamespace(bot=Bot(), job_queue=JQ(), args=args)))
    return m.risposte[-1]
ok("⛔" in cmd([str(aid)], uid=101)[0], "solo admin")
t, k = cmd([str(aid), "6"])
ok("torna <b>aperta</b>" in t and "6 ore" in t and f"annfa:{aid}:6" in bottoni(k["reply_markup"]), "anteprima con gli effetti e la conferma")
mandati.clear()
code = pg.q("SELECT count(*) AS n FROM gas_sync_queue", one=True)["n"]
q = premi(AF.cb_annulla_firma_asta, f"annfa:{aid}:6")
a = db.get_asta(aid)
ok(q.testi[-1][0].startswith("✅") and a["stato"] == "APERTA" and a["offerente_team_id"] == "team01" and a["offerta_corrente"] == 4
   and not a["team_firma"], "asta di nuovo aperta, con l'offerta in testa di prima " + q.testi[-1][0])
ok(pg.q("SELECT count(*) AS n FROM contratti", one=True)["n"] == 0
   and pg.q("SELECT count(*) AS n FROM movimenti_giocatori WHERE tipo='signed'", one=True)["n"] == 0
   and not db.get_conn().execute("SELECT 1 FROM contratti WHERE asta_id=?", (aid,)).fetchone(),
   "via contratto e movimento su PG e il contratto del bot aste")
ok(any("Firma annullata" in x["text"] for x in mandati) and any("riaperta" in x["text"] for x in mandati)
   and any("la tua offerta di 4M è in testa" in x["text"] for x in mandati), "canale principale, canale aste, GM avvisati")
ok(pg.q("SELECT count(*) AS n FROM gas_sync_queue", one=True)["n"] == code + 1, "foglio in coda")
ok(pg.q("SELECT 1 FROM registro_azioni WHERE azione LIKE 'firma da asta annullata%%'", one=True), "nel registro")
ok("non firmata" in cmd([str(aid)])[0], "di nuovo: l'asta è aperta, non c'è niente da annullare")
# firmata e poi tagliata: no
db.chiudi_asta(aid, ora.isoformat())
q = premi(F.firma_apri_callback, f"pc_firma_apri:{aid}")
q = premi(F.firma_callback, f"pc_firma:{aid}:2")
bs = bottoni(q.testi[-1][1]["reply_markup"])
ruolo = next((b for b in bs if b.startswith("pc_firma_ruolo")), None)
if ruolo:
    q = premi(F.firma_ruolo_callback, ruolo); bs = bottoni(q.testi[-1][1]["reply_markup"])
premi(F.firma_confirm_callback, next(b for b in bs if b.startswith("pc_firma_confirm")))
gid = pg.q("SELECT id FROM giocatori WHERE nome_norm='per conto'", one=True)["id"]
pg.q("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,stagione) VALUES ('cut',%s,'team01','2026')", (gid,))
ok("altri movimenti" in cmd([str(aid)])[0], "dopo un taglio: non si annulla")

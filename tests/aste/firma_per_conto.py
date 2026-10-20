import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""Aste v69 (Luca, 20/10): /firma_per_conto — un admin sceglie anni (e ruolo) al posto del GM
vincitore, con gli stessi bottoni e controlli. Annuncio sul canale principale di sempre, GM avvisato,
nel registro come admin «per conto della squadra»."""
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

# elenco senza id: le aste che aspettano gli anni
m = types.SimpleNamespace(risposte=[]); 
async def _r(t, **k): m.risposte.append((t, k))
m.reply_text = _r
u = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900), effective_message=m)
asyncio.run(F.cmd_firma_per_conto(u, CTX))
ok(f"pc_firma_apri:{aid}" in bottoni(m.risposte[-1][1].get("reply_markup")), "/firma_per_conto: le aste in attesa degli anni come bottoni")
u2 = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=101), effective_message=m)
asyncio.run(F.cmd_firma_per_conto(u2, CTX))
ok("⛔" in m.risposte[-1][0], "un GM non può usarlo")
q = premi(F.firma_apri_callback, f"pc_firma_apri:{aid}")
t, k = q.testi[-1]
ok("Firma per conto di" in t and f"pc_firma:{aid}:1" in bottoni(k["reply_markup"]), "apre la scelta degli anni per conto")
ok("⛔" in premi(F.firma_callback, f"pc_firma:{aid}:2", uid=101).testi[-1][0], "i bottoni per conto: solo admin")
q = premi(F.firma_callback, f"pc_firma:{aid}:2")
bs = bottoni(q.testi[-1][1]["reply_markup"])
ruolo = next((b for b in bs if b.startswith("pc_firma_ruolo")), None)
if ruolo:                                                     # in regular season: prima il ruolo
    q = premi(F.firma_ruolo_callback, ruolo); bs = bottoni(q.testi[-1][1]["reply_markup"])
conf = next(b for b in bs if b.startswith("pc_firma_confirm"))
ok("Per conto di" in q.testi[-1][0], "conferma: dice che è per conto")
mandati.clear()
q = premi(F.firma_confirm_callback, conf)
a = db.get_asta(aid)
ok(a["stato"] == "CONCLUSA" and a["anni_contratto"] == 2 and "Per conto di" in q.testi[-1][0], "firmato: 4M × 2, asta conclusa")
canale = [x for x in mandati if x["chat_id"] == -1]
ok(canale and "Per Conto" in canale[-1]["text"] and "4M × 2 anni" in canale[-1]["text"], "annuncio sul canale principale di sempre")
gm = [x for x in mandati if x["chat_id"] in (101, 111)]
ok(len(gm) == 2 and all("ha completato la firma per te" in x["text"] for x in gm), "i GM della squadra avvisati")
r = pg.q("SELECT * FROM registro_azioni WHERE bot='aste' AND azione LIKE 'firma dopo l''asta FA%%'", one=True)
ok(r and r["veste"] == "admin" and r["azione"].endswith("per conto della squadra"), f"registro: admin, per conto {r and r['azione']}")
ok("❌" in F._testo_per_conto(aid)[0], "asta già firmata: per conto non si riapre")
ok(pg.q("SELECT count(*) AS n FROM contratti", one=True)["n"] == 1, "un solo contratto")
# il GM normale continua a funzionare (callback senza pc_)
aid2 = db.crea_asta(tipo="FA", giocatore="Per Conto Due", squadra_proprietaria=None, creata_at=ora.isoformat(), scade_at=ora.isoformat())
db.aggiorna_offerta(aid2, "team01", 3, ora.isoformat()); db.chiudi_asta(aid2, ora.isoformat())
ok("⛔" in premi(F.firma_callback, f"firma:{aid2}:1", uid=900).testi[-1][0], "senza pc_ l'admin non è il GM: come prima")
q = premi(F.firma_callback, f"firma:{aid2}:1", uid=101)
ok(not any(b.startswith("pc_") for b in bottoni(q.testi[-1][1]["reply_markup"])), "il GM vincitore: bottoni normali")
pg.q("DELETE FROM registro_azioni")

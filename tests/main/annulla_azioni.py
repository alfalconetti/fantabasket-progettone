import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.20.2 (Luca, 21/11): annullare un taglio, annullare o correggere una firma registrata, dal pannello admin."""
import asyncio, types, json, os
import database as db
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio, ruoli_pendenti, cambi_ruolo RESTART IDENTITY CASCADE")
db._q("DELETE FROM registro_azioni")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
g = json.load(open(os.environ["GLOBALS_PATH"])); g["fase"] = "offseason-fa"; json.dump(g, open(os.environ["GLOBALS_PATH"], "w"))
import settings
S = settings.stagione_corrente()
def gioc(n, t, imp, anni=1):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,%s,%s,%s,'normale') RETURNING id", (gid, t, imp, anni, S))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id,timestamp) VALUES ('signed',%s,%s,%s,%s,NOW() - INTERVAL '30 days')", (gid, t, S, c)); return gid
grosso = gioc("Grosso", "team01", 20, 2)
piccolo = gioc("Piccolo", "team01", 1, 1)
altro = gioc("Altro", "team02", 8, 2)
import teams as tm
from handlers import tagli as T, annulla_azioni as AA, admin_panel as A
msgs = []
class Bot:
    async def send_message(self, **k): msgs.append(k)
class Q:
    def __init__(s, data): s.data, s.t, s.kb, s.from_user = data, None, None, types.SimpleNamespace(id=900, first_name="Adm", username="adm")
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.t, s.kb = t, k.get("reply_markup")
def tap(cb, data):
    q = Q(data); asyncio.run(cb(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), types.SimpleNamespace(bot=Bot()))); return q
def bottoni(kb): return [b.callback_data for r in kb.inline_keyboard for b in r] if kb else []
usati = lambda: db.get_tagli_gratuiti_usati("team01", S)

# ── annulla taglio ──
v = T.esegui_taglio(tm.get_team_by_id("team01"), grosso)
T.esegui_taglio(tm.get_team_by_id("team01"), piccolo)
ok(usati() == 1 and db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s", (grosso,)) > 0, "due tagli: uno gratuito, uno con le rate")
q = tap(AA.cb_annulla_taglio, "annt:l")
tid_g = next(t["id"] for t in db.tagli_recenti() if t["giocatore_id"] == grosso)
tid_p = next(t["id"] for t in db.tagli_recenti() if t["giocatore_id"] == piccolo)
ok(f"annt:t:{tid_g}" in bottoni(q.kb) and f"annt:t:{tid_p}" in bottoni(q.kb), "lista dei tagli recenti")
q = tap(AA.cb_annulla_taglio, f"annt:t:{tid_g}")
ok("si tolgono le rate" in q.t and f"annt:ok:{tid_g}" in bottoni(q.kb), "anteprima con gli effetti e la conferma")
msgs.clear()
q = tap(AA.cb_annulla_taglio, f"annt:ok:{tid_g}")
ok(q.t.startswith("✅") and db._qval("SELECT attivo FROM contratti WHERE giocatore_id=%s", (grosso,))
   and db._qval("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s", (grosso,)) == 0
   and db._qval("SELECT count(*) FROM movimenti_giocatori WHERE giocatore_id=%s AND tipo='cut'", (grosso,)) == 0,
   "annullato: contratto di nuovo attivo, niente rate, niente movimento del taglio " + (q.t or ""))
ok(any("Taglio annullato" in m["text"] for m in msgs) and any("annullato il taglio" in m["text"] for m in msgs), "canale e avviso al GM")
r = db._q("SELECT * FROM registro_azioni WHERE azione = 'taglio annullato'", one=True)
ok(r and r["giocatore_id"] == grosso and r["dopo"] == "di nuovo 20M × 2", "registro: prima → dopo")
asyncio.run(AA.applica_annulla_taglio(Bot(), tid_p))
ok(usati() == 0 and db._qval("SELECT attivo FROM contratti WHERE giocatore_id=%s", (piccolo,)), "taglio gratuito annullato: torna disponibile")
q = tap(AA.cb_annulla_taglio, f"annt:t:{tid_g}")
ok("non trovato" in q.t, "un taglio annullato non c'è più")
# taglio seguito da una firma altrove: non si annulla
T.esegui_taglio(tm.get_team_by_id("team01"), piccolo)
tid_p2 = next(t["id"] for t in db.tagli_recenti() if t["giocatore_id"] == piccolo)
c2 = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,'team02',2,1,%s,'normale') RETURNING id", (piccolo, S))
db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,'team02',%s,%s)", (piccolo, S, c2))
q = tap(AA.cb_annulla_taglio, f"annt:t:{tid_p2}")
ok("Non si può" in q.t and "annt:ok" not in " ".join(bottoni(q.kb)), "rifirmato da un'altra squadra: non si annulla (" + q.t.split("\n")[-1] + ")")
try:
    db.annulla_taglio(tid_p2); ok(False, "annulla_taglio doveva rifiutare")
except ValueError:
    ok(db._qval("SELECT count(*) FROM contratti WHERE giocatore_id=%s AND attivo", (piccolo,)) == 1, "e anche la funzione rifiuta, niente cambia")

# ── firme registrate ──
class Msg:
    def __init__(s): s.t = []
    async def reply_text(s, t, **k): s.t.append(t)
def cmd(f, args, msg=None):
    msg = msg or Msg()
    asyncio.run(f(types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900, first_name="Adm", username="adm"), effective_message=msg),
                  types.SimpleNamespace(args=args, bot=Bot())))
    return msg
nuovo = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES ('Nuovo Fa','Nuovo Fa','nuovo fa') RETURNING id")
cmd(A.cmd_registra_firma, ["team02", "3", "1", "Nuovo", "Fa"])
ff = db.firme_registrate()
ok(len(ff) == 1 and ff[0]["giocatore_id"] == nuovo and ff[0]["importo"] == 3, f"la firma registrata è in lista (nota «firma registrata») {ff}")
fid = ff[0]["id"]
q = tap(AA.cb_annulla_firma, "annf:l")
ok(f"annf:t:{fid}" in bottoni(q.kb), "✍️ Firme registrate: la lista")
q = tap(AA.cb_annulla_firma, f"annf:t:{fid}")
ok(f"/correggi_firma {fid}" in q.t and f"annf:ok:{fid}" in bottoni(q.kb), "scheda: annulla e il comando per correggere")
m = cmd(AA.cmd_correggi_firma, [str(fid), "20", "1"])
ok("anni non validi" in m.t[-1], "correzione con anni non validi per l'importo: rifiutata")
m = cmd(AA.cmd_correggi_firma, [str(fid), "4", "2"])
ok(m.t[-1].startswith("✅") and db._q("SELECT importo, anni_originali FROM contratti WHERE giocatore_id=%s AND attivo", (nuovo,), one=True) == {"importo": 4, "anni_originali": 2},
   "/correggi_firma: importo e anni nuovi")
ok(db._q("SELECT * FROM registro_azioni WHERE azione = 'firma registrata corretta'", one=True)["prima"] == "3M × 1", "registro della correzione")
db._q("INSERT INTO ruoli_pendenti (giocatore_id, team_id, origine, scadenza) VALUES (%s, 'team02', 'firma', NOW() + INTERVAL '1 day')", (nuovo,))
q = tap(AA.cb_annulla_firma, f"annf:ok:{fid}")
ok(q.t.startswith("✅") and not db._q("SELECT 1 FROM contratti WHERE giocatore_id=%s", (nuovo,), one=True)
   and db._qval("SELECT count(*) FROM movimenti_giocatori WHERE giocatore_id=%s", (nuovo,)) == 0
   and db._qval("SELECT stato FROM ruoli_pendenti WHERE giocatore_id=%s", (nuovo,)) == "annullata",
   "firma annullata: niente contratto né movimento, dichiarazione di ruolo chiusa " + q.t)
ok(db._q("SELECT * FROM registro_azioni WHERE azione = 'firma registrata annullata'", one=True)["dopo"] == "free agent", "registro dell'annullamento")
# una firma normale (non registrata a mano) non è in lista
ok(all(f["giocatore_id"] != altro for f in db.firme_registrate()), "le firme normali non sono tra quelle registrate")
ok(db.controlli_coerenza() == [] or all("storico" in p for p in db.controlli_coerenza()), f"coerenza dopo gli annullamenti {db.controlli_coerenza()}")

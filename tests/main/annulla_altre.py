import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.38.0 (Luca, 27/11): annullare un decadimento (con le spalmature tolte agli altri e l'RFA), un ritiro di un free
agent, una DPE, un'attivazione dei diritti 2nd, un cambio ruolo; il menu ↩️ Annulla azioni."""
import asyncio, types, json, os
import database as db
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio, ruoli_pendenti, cambi_ruolo, rookie, rfa_dichiarati, "
      "spalmature_tolte RESTART IDENTITY CASCADE")
db._q("DELETE FROM registro_azioni")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
g = json.load(open(os.environ["GLOBALS_PATH"])); g["fase"] = "regular-season-fa"; json.dump(g, open(os.environ["GLOBALS_PATH"], "w"))
import settings
S = settings.stagione_corrente()
def gioc(n, t=None, imp=5, anni=2):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    if t:
        c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,%s,%s,%s,'normale') RETURNING id", (gid, t, imp, anni, S))
        db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id,timestamp) VALUES ('signed',%s,%s,%s,%s,NOW() - INTERVAL '30 days')", (gid, t, S, c))
    return gid
def spalmatura(gid, team, importo=3):
    cut = db._qval("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,stagione,timestamp) VALUES ('cut',%s,%s,%s,NOW() - INTERVAL '60 days') RETURNING id", (gid, team, S))
    db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo,transazione_id) VALUES (%s,%s,%s,%s,%s,%s)",
          (team, gid, S, S, importo, cut))
from handlers import annulla_azioni as AA, decadimento as D
msgs = []
class Bot:
    async def send_message(self, **k): msgs.append(k)
class Q:
    def __init__(s, data): s.data, s.t, s.kb, s.from_user = data, None, None, types.SimpleNamespace(id=900, first_name="Adm", username="adm")
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.t, s.kb = t, k.get("reply_markup")
    def get_bot(s): return Bot()
def tap(cb, data):
    q = Q(data); asyncio.run(cb(types.SimpleNamespace(callback_query=q, effective_user=q.from_user), types.SimpleNamespace(bot=Bot()))); return q
def bottoni(kb): return [b.callback_data for r in kb.inline_keyboard for b in r] if kb else []
n = lambda sql, *p: db._qval(sql, p)

# ── decadimento per ritiro, con la spalmatura di chi l'aveva tagliato e un RFA dichiarato ──
ritirato = gioc("Ritirato", "team01", 6)
spalmatura(ritirato, "team02", 4)
cid = n("SELECT id FROM contratti WHERE giocatore_id=%s", ritirato)
db._q("INSERT INTO rfa_dichiarati (stagione,team_id,giocatore_id,contratto_id) VALUES (%s,'team01',%s,%s)", (S, ritirato, cid))
err = asyncio.run(D.applica_decadimento(Bot(), "team01", ritirato, "ritiro", "Adm"))
ok(err is None and n("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s", ritirato) == 0
   and n("SELECT count(*) FROM spalmature_tolte WHERE giocatore_id=%s", ritirato) == 1
   and n("SELECT stato FROM rfa_dichiarati WHERE giocatore_id=%s", ritirato) == "revocata",
   "decadimento per ritiro: tolta la spalmatura di team02 (salvata), RFA revocato")
q = tap(AA.cb_annulla_decadimento, "decann:l")
did = next(d["id"] for d in db.decadimenti_recenti() if d["giocatore_id"] == ritirato)
ok(f"decann:t:{did}" in bottoni(q.kb), "lista dei decadimenti")
q = tap(AA.cb_annulla_decadimento, f"decann:t:{did}")
ok("tornano le spalmature tolte" in q.t and "4M" in q.t and f"decann:ok:{did}" in bottoni(q.kb), "scheda con gli effetti (la spalmatura di team02)")
msgs.clear()
q = tap(AA.cb_annulla_decadimento, f"decann:ok:{did}")
ok(q.t.startswith("✅") and n("SELECT attivo FROM contratti WHERE id=%s", cid)
   and n("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s AND team_id='team02'", ritirato) == 1
   and n("SELECT count(*) FROM movimenti_giocatori WHERE giocatore_id=%s AND tipo='decadimento'", ritirato) == 0
   and n("SELECT stato FROM rfa_dichiarati WHERE giocatore_id=%s", ritirato) == "attiva",
   "annullato: contratto attivo, spalmatura di team02 rimessa, niente movimento, RFA di nuovo dichiarato " + (q.t or ""))
ok(any("Decadimento annullato" in m["text"] and "team02" not in m["text"] for m in msgs), "sul canale (coi nomi delle squadre)")
ok(db._q("SELECT * FROM registro_azioni WHERE azione='decadimento annullato'", one=True)["nota"].startswith("rimesse le spalmature"),
   "registro: con le spalmature rimesse")
# decaduto e poi firmato da un'altra: non si annulla
asyncio.run(D.applica_decadimento(Bot(), "team01", ritirato, "altro", "Adm"))
did2 = next(d["id"] for d in db.decadimenti_recenti() if d["giocatore_id"] == ritirato)
c2 = n("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,'team03',2,1,%s,'normale') RETURNING id", ritirato, S)
db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,'team03',%s,%s)", (ritirato, S, c2))
q = tap(AA.cb_annulla_decadimento, f"decann:t:{did2}")
ok("Non si può" in q.t and "decann:ok" not in " ".join(bottoni(q.kb)), "rifirmato da un'altra squadra: no (" + q.t.split("\n")[-1] + ")")
# decadimento di prima della v7.38.0 che aveva tolto spalmature: non si possono rimettere
vecchio = gioc("Vecchio", "team01")
vcid = n("SELECT id FROM contratti WHERE giocatore_id=%s", vecchio)
db._q("UPDATE contratti SET attivo=FALSE WHERE id=%s", (vcid,))
vt = n("INSERT INTO transazioni (tipo,giocatore_id,team_id_da,stagione,contratto_id,note) VALUES ('decadimento',%s,'team01',%s,%s,'Decadimento: Ritiro') RETURNING id", vecchio, S, vcid)
db._q("INSERT INTO registro_azioni (bot,veste,azione,giocatore_id,nota) VALUES ('main','admin','decadimento approvato',%s,'Ritiro; tolte le spalmature di Beta')", (vecchio,))
ok("non sono state salvate" in (db.perche_no_annulla_decadimento(db.decadimento(vt)) or ""), "vecchio decadimento con spalmature tolte: non si annulla")

# ── ritiro di un free agent ──
fa = gioc("Svincolato")
spalmatura(fa, "team02", 2); spalmatura(fa, "team03", 1)
tolte = db.cancella_spalmate_ritirato(fa, S)
ok(len(tolte) == 2 and n("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s", fa) == 0, "/ritiro_fa: spalmature tolte (e salvate)")
q = tap(AA.cb_annulla_ritiro, "ritann:l")
rid = next(b for b in bottoni(q.kb) if b.startswith("ritann:t:"))
q = tap(AA.cb_annulla_ritiro, rid)
import teams as tm
ok(tm.get_team_by_id("team02")["nome"] in q.t and tm.get_team_by_id("team03")["nome"] in q.t, "scheda: le spalmature da rimettere, coi nomi")
q = tap(AA.cb_annulla_ritiro, rid.replace(":t:", ":ok:"))
ok(q.t.startswith("✅") and n("SELECT count(*) FROM impatto_taglio WHERE giocatore_id=%s", fa) == 2, "ritiro annullato: spalmature rimesse")
ok(not db.ritiri_fa_recenti(), "e non è più in lista")

# ── DPE ──
inf = gioc("Infortunato", "team01", 10)
db.inserisci_dpe(inf, "team01", S, 10, 5, True, "Adm")
dpe = db.dpe_recenti()[0]
q = tap(AA.cb_annulla_dpe, f"dpeann:t:{dpe['id']}")
ok("torna a 10M" in q.t and "slot" in q.t, "scheda DPE pre-deadline: importo pieno e slot")
msgs.clear()
q = tap(AA.cb_annulla_dpe, f"dpeann:ok:{dpe['id']}")
ok(q.t.startswith("✅") and not db.get_dpe_attiva(inf, S) and any("DPE annullata" in m["text"] for m in msgs), "DPE annullata, sul canale")
db.inserisci_dpe(inf, "team01", S, 10, 5, False, "Adm")
dpe = db.dpe_recenti()[0]
db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_da,ruolo_a,stagione,tipo) VALUES (%s,'team01','G','F',%s,'dpe_extra')", (inf, S))
ok("già stato usato" in (db.perche_no_annulla_dpe(dpe) or ""), "DPE post-deadline col cambio extra usato: prima il cambio")

# ── attivazione dei diritti 2nd ──
from handlers import rookie as RK
rk = gioc("Rookie Due")
rid = n("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft) VALUES (%s,'team02',2,30,%s) RETURNING id", rk, S)
RK.esegui_attivazione(rid, "team02", 1, 2)
att = db.attivazioni_recenti()[0]
ok(att["giocatore_id"] == rk and att["importo"] == 1, "l'attivazione è in lista")
q = tap(AA.cb_annulla_attivazione, f"attann:t:{att['id']}")
ok("torna ad avere i diritti" in q.t, "scheda dell'attivazione")
q = tap(AA.cb_annulla_attivazione, f"attann:ok:{att['id']}")
ok(q.t.startswith("✅") and not db.get_contratto_attivo(rk) and not n("SELECT firmato FROM rookie WHERE id=%s", rid)
   and n("SELECT count(*) FROM movimenti_giocatori WHERE giocatore_id=%s", rk) == 0
   and any(r["id"] == rid for r in db.get_diritti_2nd_team("team02")),
   "attivazione annullata: niente contratto né movimento, di nuovo tra i diritti " + (q.t or ""))

# ── cambio ruolo ──
cr = gioc("Ruolo", "team03")
db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_da,ruolo_a,stagione,tipo,timestamp) VALUES (%s,'team03',NULL,'G',%s,'iniziale',NOW() - INTERVAL '10 days')", (cr, S))
db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_da,ruolo_a,stagione,tipo,timestamp) VALUES (%s,'team03','G','F',%s,'ordinario',NOW() - INTERVAL '5 days')", (cr, S))
db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_da,ruolo_a,stagione,tipo,timestamp) VALUES (%s,'team03','F','C',%s,'ordinario',NOW() - INTERVAL '2 days')", (cr, S))
ruolo = lambda: n("SELECT ruolo FROM ruolo_attuale WHERE giocatore_id=%s AND stagione=%s", cr, S)
cc = [c for c in db.cambi_ruolo_recenti() if c["giocatore_id"] == cr]
ok([c["ruolo_a"] for c in cc] == ["C", "F"] and [c["ultimo"] for c in cc] == [True, False], "in lista i cambi, non la dichiarazione iniziale")
q = tap(AA.cb_annulla_cambio, f"crann:t:{cc[1]['id']}")
ok("Non si può" in q.t, "non l'ultimo: no")
q = tap(AA.cb_annulla_cambio, f"crann:ok:{cc[0]['id']}")
ok(q.t.startswith("✅") and ruolo() == "F", "annullato l'ultimo: torna F")
q = tap(AA.cb_annulla_cambio, f"crann:ok:{cc[1]['id']}")
ok(q.t.startswith("✅") and ruolo() == "G", "poi anche quello prima: torna G")
db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_da,ruolo_a,stagione,tipo,scadenza,ruolo_ripristino,timestamp) VALUES (%s,'team03','G','C',%s,'saedro',NOW() - INTERVAL '1 day','G',NOW() - INTERVAL '3 days')", (cr, S))
db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_da,ruolo_a,stagione,tipo,timestamp) VALUES (%s,'team03','C','G',%s,'saedro',NOW() - INTERVAL '1 day')", (cr, S))
cc = [c for c in db.cambi_ruolo_recenti() if c["giocatore_id"] == cr]
ok(len(cc) == 1 and "già finita" in (db.perche_no_annulla_cambio(cc[0]) or ""), "Saedro finita: il ritorno non è in lista e la Saedro non si annulla")

# ── rinnovo rookie III-IV ──
import psycopg2.extras
from handlers import stagione as ST
rr = gioc("Rookie Tre")
vec = n("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,'team04',2,2,%s,'rookie') RETURNING id", rr, str(int(S) - 2))
with db.get_conn() as conn:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        nuovo = ST._nuovo_contratto(cur, {"contratto_id": vec, "giocatore_id": rr, "nome": "Rookie Tre", "importo_nuovo": 4,
                                          "anni_nuovi": 2, "tipo": "rookie"}, int(S), "renewed", "Rinnovo rookie III-IV: scala III anno 4M", True)
x = db.rinnovi_rookie_recenti()[0]
ok(x["giocatore_id"] == rr and x["vecchio"] == vec and not db.perche_no_annulla_rinnovo_rookie(x), "il rinnovo rookie è in lista, col contratto di prima")
q = tap(AA.cb_annulla_rinnovo_rookie, f"rrann:ok:{x['id']}")
ok(q.t.startswith("✅") and db.get_contratto_attivo(rr)["id"] == vec and not n("SELECT count(*) FROM contratti WHERE id=%s", nuovo),
   "annullato: torna il contratto rookie di prima " + (q.t or ""))

# ── menu ──
q = tap(AA.cb_annulla_home, "ann:home")
ok({"annt:l", "annf:l", "decann:l", "ritann:l", "dpeann:l", "attann:l", "crann:l", "rna:scegli", "rrann:l"} <= set(bottoni(q.kb)), "↩️ Annulla azioni: tutte le voci")
from handlers import admin_panel as A
ok("ann:home" in bottoni(A._kb_admin_home()), "nel menu admin")

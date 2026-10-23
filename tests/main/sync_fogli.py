import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""Il foglio Roster si aggiorna sempre per tutte le squadre (v3.9.4), qualunque cosa chieda il chiamante."""
import database as db, gas_client, teams as tm
db.init_db(); db.migrate_db()
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
inviati=[]
gas_client._get_config=lambda: ("http://finto", "token")
gas_client._build_team_payload=lambda tid: {"team_id": tid}
gas_client._do_sync=lambda url, tok, payload, attempt=1: inviati.append([t["team_id"] for t in payload["teams"]])
import threading
class T:
    def __init__(s, target, args, daemon): s.f, s.a = target, args
    def start(s): s.f(*s.a)
threading.Thread=T
tutte=sorted(t["id"] for t in tm.get_all_teams())
gas_client.sync_teams(["team02"]); ok(sorted(inviati[-1])==tutte, f"sync_teams(['team02']) → tutte le {len(tutte)} squadre")
gas_client.sync_after_taglio("team03"); ok(any(sorted(x)==tutte for x in inviati[1:]), "sync_after_taglio → tutte")
gas_client.sync_teams_sync(["team01"]); ok(sorted(inviati[-1])==tutte, "sync manuale → tutte")

# ── v6.5.4 (Luca, 23/10): sul foglio Roster i nomi di Basketball-Reference (quelli di BrefRaw) ──
import importlib
gc = importlib.reload(gas_client)
gc._get_config = lambda: ("http://finto", "token")
db._q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio, rookie RESTART IDENTITY CASCADE")
def _g(bref, common):
    return db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES (%s, %s, %s) RETURNING id", (bref, common, common.lower()))
jok = _g("Nikola Jokić", "Nikola Jokic")
jjj = _g("Jaren Jackson Jr.", "Jaren Jackson")
sen = _g("", "Senza Bref")
dieci = _g("Dieci Giornić", "Dieci Giornic")
tag = _g("Tagliato Brefović", "Tagliato Brefovic")
for gid, imp, tipo in ((jok, 30, "normale"), (jjj, 20, "normale"), (sen, 5, "normale"), (dieci, 1, "10day")):
    cid = db._qval("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) "
                   "VALUES (%s, 'team01', %s, 2, '2026', %s) RETURNING id", (gid, imp, tipo))
    db._q("INSERT INTO transazioni (tipo, giocatore_id, team_id_a, stagione, contratto_id) VALUES ('signed', %s, 'team01', '2026', %s)", (gid, cid))
db._q("INSERT INTO impatto_taglio (team_id, giocatore_id, stagione_taglio, stagione, importo) VALUES ('team01', %s, '2026', '2026', 2)", (tag,))
pl = gc._build_team_payload("team01")
nomi = [x["nome"] for x in pl["giocatori"]]
ok("Nikola Jokić" in nomi and "Jaren Jackson Jr." in nomi and "Senza Bref" in nomi and "Nikola Jokic" not in nomi,
   f"foglio Roster: nomi di Basketball-Reference (accenti, Jr.), il nome comune solo se manca quello bref {nomi}")
ok([x["nome"] for x in pl["dieci_giorni"]] == ["Dieci Giornić"] and [x["nome"] for x in pl["impatti_tagli"]] == ["Tagliato Brefović"],
   "anche la riga 10-DAY e i tagli col nome bref")

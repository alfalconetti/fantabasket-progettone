import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""/status [SQUADRA] (v7.1.0): injury status dei giocatori sotto contratto dall'ultimo snapshot, con da quando."""
import asyncio, types
from datetime import date
import db, status as ST
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()
db.q("TRUNCATE nba_infortuni")
db.q("DELETE FROM contratti WHERE giocatore_id IN (SELECT id FROM giocatori WHERE nome_bref LIKE 'Stat %%')")
db.q("DELETE FROM giocatori WHERE nome_bref LIKE 'Stat %%'")
gid = {}
for i, espn in ((1, "s1"), (2, "s2"), (3, "s3"), (4, None)):
    gid[i] = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id",
                  (f"Stat {i}", f"Stat {i}", f"stat {i}", espn), one=True)["id"]
    db.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) "
         "VALUES (%s, 'team01', 5, 2, '2026', 'normale', TRUE)", (gid[i],))
db.salva_infortuni(date(2026, 11, 3), [{"atleta": "s1", "nome": "Stat 1", "squadra": "NYK", "stato": "Out", "dettaglio": "Knee"},
                                       {"atleta": "s2", "nome": "Stat 2", "squadra": "BOS", "stato": "Questionable"}])
db.salva_infortuni(date(2026, 11, 4), [{"atleta": "s1", "nome": "Stat 1", "squadra": "NYK", "stato": "Out", "dettaglio": "Knee; out until Dec"},
                                       {"atleta": "s2", "nome": "Stat 2", "squadra": "BOS", "stato": "Day-To-Day"}])
t = ST.testo("team01")
ok("Stat 1</b> (NYK): <b>Out</b> dal 03/11" in t and "out until Dec" in t, "Out da due snapshot: dal primo, col dettaglio dell'ultimo")
ok("Stat 2</b> (BOS): <b>Day-To-Day</b> dal 04/11" in t, "stato cambiato: dal giorno del cambio")
ok(t.index("Stat 1") < t.index("Stat 2"), "prima gli Out")
ok("Gli altri 1" in t and "Non abbinati a ESPN" in t and "Stat 4" in t, "sani contati, non abbinati elencati")
risp = []
class M:
    async def reply_text(s, x, **k): risp.append(x)
asyncio.run(ST.cmd_status(types.SimpleNamespace(effective_message=M(), effective_user=types.SimpleNamespace(id=101)),
                          types.SimpleNamespace(args=[])))
ok(risp and "Status di" in risp[-1], "senza argomenti: la squadra del GM")
asyncio.run(ST.cmd_status(types.SimpleNamespace(effective_message=M(), effective_user=types.SimpleNamespace(id=999)),
                          types.SimpleNamespace(args=["xyzxyz"])))
ok("non trovata" in risp[-1], "squadra sbagliata")
db.q("TRUNCATE nba_infortuni")
db.q("DELETE FROM contratti WHERE giocatore_id = ANY(%s)", (list(gid.values()),))
db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (list(gid.values()),))

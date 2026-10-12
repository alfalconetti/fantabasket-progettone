import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v3.12.0: cap e slot da shared/cap.py, la stessa implementazione per i due bot. Ogni caso
che conta: in corso, x0, x0 dichiarato RFA, DPE prima e dopo la deadline, spalmature."""
import database as db
from shared import cap
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio, rfa_dichiarati RESTART IDENTITY CASCADE")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
S = "2026"


def gioc(n, imp, anni, sf, team="team01"):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    cid = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                   "VALUES (%s,%s,%s,%s,%s,'normale') RETURNING id", (gid, team, imp, anni, sf))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,%s,%s)",
          (gid, team, sf, cid))
    return gid, cid


corso, _ = gioc("In Corso", 10, 2, "2026")
x0, _ = gioc("Finito", 5, 1, "2025")                       # x0 nel 2026
rfa, crfa = gioc("Rfa Dichiarato", 7, 1, "2025")           # x0 dichiarato RFA
dpe_pre, _ = gioc("Dpe Prima", 20, 2, "2026")              # DPE prima della deadline: 15, niente slot
dpe_post, _ = gioc("Dpe Dopo", 8, 2, "2026")               # DPE dopo la deadline: 6, lo slot resta
db._q("INSERT INTO rfa_dichiarati (stagione,team_id,giocatore_id,contratto_id,da) VALUES (%s,'team01',%s,%s,'prova')", (S, rfa, crfa))
db._q("INSERT INTO dpe (giocatore_id,team_id,stagione,importo_originale,importo_dpe,pre_deadline) VALUES (%s,'team01',%s,20,15,TRUE)", (dpe_pre, S))
db._q("INSERT INTO dpe (giocatore_id,team_id,stagione,importo_originale,importo_dpe,pre_deadline) VALUES (%s,'team01',%s,8,6,FALSE)", (dpe_post, S))
db._q("INSERT INTO impatto_taglio (team_id,giocatore_id,stagione_taglio,stagione,importo) VALUES ('team01',%s,%s,%s,3)", (x0, S, S))

pesi = {n: cap.peso_cap(db._q, g, S) for n, g in (("corso", corso), ("x0", x0), ("rfa", rfa), ("pre", dpe_pre), ("post", dpe_post))}
ok(pesi == {"corso": 10, "x0": 0, "rfa": 7, "pre": 15, "post": 6}, f"peso sul cap per giocatore {pesi}")
slot = {n: cap.occupa_slot(db._q, g, S) for n, g in (("corso", corso), ("x0", x0), ("rfa", rfa), ("pre", dpe_pre), ("post", dpe_post))}
ok(slot == {"corso": True, "x0": False, "rfa": False, "pre": False, "post": True},
   f"slot: x0 e RFA no, DPE prima della deadline no, DPE dopo sì {slot}")
ok(cap.cap_occupato(db._q, "team01", S) == 10 + 7 + 15 + 6 + 3 == db.cap_occupato_team("team01", S),
   "cap occupato = contratti che pesano + spalmature, uguale dal bot principale")
roster = db.get_roster_team("team01")
ok(db.slot_occupati(roster) == cap.giocatori_in_slot(db._q, "team01", S) == 2,
   "slot dal roster del bot principale = conteggio condiviso (quello del bot aste)")
ok(db.cap_roster(roster) == 38, "cap del roster nelle immagini (senza spalmature)")
ok(db.peso_cap_giocatore(rfa, S) == 7 and db.occupa_slot(dpe_post, S), "funzioni del bot principale = funzioni condivise")

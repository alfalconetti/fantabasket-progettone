import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.9.0: Quasi NBA Cup nel bot principale: /quasi_cup in privato, il cambio ruolo Cup solo per la vincitrice e
uno a stagione (tipo 'cup' ammesso dal vincolo di cambi_ruolo)."""
import database as db
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from handlers import cambi_ruolo as CR
from handlers import lega

S = CR._stagione()
db._q("TRUNCATE lega_cup")
db._q("DELETE FROM cambi_ruolo WHERE tipo = 'cup'")
ok(not CR.cup_vinta("team01") and not CR.cup_disponibile("team01"), "nessuna Cup vinta: niente cambio Cup")
db._q("""INSERT INTO lega_cup (stagione, turno, giornata, casa, trasferta, punti_casa, punti_trasferta, vince, convalidato)
         VALUES (%s, 2, 5, 'team02', 'team01', 300, 250, 'casa', NOW())""", (S,))
ok(CR.cup_disponibile("team02") and not CR.cup_disponibile("team01"), "finale convalidata: il cambio Cup solo alla vincitrice")
errori, _ = CR.verifica("team01", -1, "PG", "cup", False)
ok(errori, "verifica: chi non ha vinto non può usarlo")
gid = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES ('Cup Prova', 'Cup Prova', 'cup prova') RETURNING id")
db._q("INSERT INTO cambi_ruolo (giocatore_id, team_id, ruolo_da, ruolo_a, stagione, tipo) VALUES (%s, 'team02', 'PG', 'SG', %s, 'cup')", (gid, S))
ok(CR.cup_vinta("team02") and not CR.cup_disponibile("team02"), "usato: uno a stagione (il vincolo del database ammette 'cup')")
ok("cup" in CR.ETICHETTE and CR.TIPI["c"] == "cup", "tipo ed etichetta")
ok(any(getattr(h, "commands", None) == frozenset({"quasi_cup"}) for h in lega.get_handlers()), "/quasi_cup registrato (in privato)")
db._q("DELETE FROM cambi_ruolo WHERE giocatore_id = %s", (gid,))
db._q("DELETE FROM giocatori WHERE id = %s", (gid,))
db._q("TRUNCATE lega_cup")

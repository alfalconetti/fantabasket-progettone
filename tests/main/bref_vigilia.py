import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# v7.6.0 (Luca, 11/11): alle 20 della sera prima di una giornata con squadre a media si riscarica bref.
# Gira dopo le prove di loucabot (lega_giornate): giornate 95-98.
from datetime import date, datetime, timedelta, timezone
import database as db
import settings
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from handlers.bref import giornate_vigilia
from shared.regole import orario

S = settings.stagione_corrente()
db._q("DELETE FROM lega_giornate WHERE stagione = %s AND numero BETWEEN 95 AND 99", (S,))
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'bv%%'")
OGGI = date(2027, 3, 9)
ROMA = __import__("zoneinfo").ZoneInfo("Europe/Rome")
ORE20 = lambda d: datetime(d.year, d.month, d.day, 20, 0, tzinfo=ROMA)
# v7.37.0 (Luca, 27/11): conta il giorno NBA (ET) di inizio, dal, non la data di Roma della prima partita
# 95: dal oggi, prima partita stanotte all'01:30 di Roma, con squadre a media → sì
# 96: dal oggi, ma nessuna squadra a media → no
# 97: dal dopodomani → no
# 98: dal domani, prima partita NBA domani alle 20 di Roma (pomeriggio ET; prima_partita non calcolata, media dal file):
#     stasera no (stanotte si gioca ancora la giornata prima), domani un'ora prima della partita, alle 19
# 99: dal domani, prima partita dopodomani all'01:00 di Roma → stasera no, domani sera sì
for n, dal, prima, media, mfile in ((95, date(2027, 3, 9), datetime(2027, 3, 10, 0, 30, tzinfo=timezone.utc), ["LAL"], []),
                                    (96, date(2027, 3, 9), datetime(2027, 3, 10, 0, 30, tzinfo=timezone.utc), [], []),
                                    (97, date(2027, 3, 11), datetime(2027, 3, 12, 0, 30, tzinfo=timezone.utc), ["BOS"], []),
                                    (98, date(2027, 3, 10), None, None, ["MIA"]),
                                    (99, date(2027, 3, 10), datetime(2027, 3, 11, 0, 0, tzinfo=timezone.utc), ["DAL"], [])):
    db._q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al, prima_partita, media, media_file) VALUES (%s, %s, 'regular', %s, %s, %s, %s, %s)",
          (S, n, dal, dal + timedelta(days=2), prima, media, mfile))
db._q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES ('bv1', %s, 2, %s, %s, 'MIA', 'NY', 'STATUS_SCHEDULED')",
      (S, date(2027, 3, 10), datetime(2027, 3, 10, 19, 0, tzinfo=timezone.utc)))
v = sorted(r["numero"] for r in giornate_vigilia(S, OGGI, ORE20(OGGI)) if r["numero"] >= 95)
ok(v == [95], f"stasera: solo la giornata con squadre a media che inizia stanotte, non quella del giorno NBA dopo {v}")
d = OGGI + timedelta(days=1)
v = sorted(r["numero"] for r in giornate_vigilia(S, d, ORE20(d)) if r["numero"] >= 95)
ok(v == [99], f"domani alle 20: la 99 sì, la 98 no (già iniziata: la sua vigilia era alle 19) {v}")
ok(not [r for r in giornate_vigilia(S, OGGI - timedelta(days=1), ORE20(OGGI - timedelta(days=1))) if r["numero"] >= 95], "il giorno prima: niente")
from handlers.bref import ora_vigilia
r99 = next(r for r in giornate_vigilia(S, d, None) if r["numero"] == 99)
r98 = next(r for r in giornate_vigilia(S, d, None) if r["numero"] == 98)
ok(ora_vigilia(r99, d) == ORE20(d), f"prima partita all'01:00: alle 20 {ora_vigilia(r99, d)}")
ok(ora_vigilia(r98, d) == ORE20(d).replace(hour=19), f"prima partita alle 20 di Roma: un'ora prima, alle 19 {ora_vigilia(r98, d)}")
v = sorted(r["numero"] for r in giornate_vigilia(S, d, ORE20(d).replace(hour=19)) if r["numero"] >= 95)
ok(v == [98, 99], f"alle 19 la 98 non è ancora iniziata: c'è {v}")
ok(orario("bref_vigilia").strftime("%H:%M") == "20:00", "orari.bref_vigilia: le 20")

db._q("DELETE FROM lega_giornate WHERE stagione = %s AND numero BETWEEN 95 AND 99", (S,))
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'bv%%'")

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
db._q("DELETE FROM lega_giornate WHERE stagione = %s AND numero BETWEEN 95 AND 98", (S,))
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'bv%%'")
OGGI = date(2027, 3, 9)
# 95: prima partita domani all'01:30 di Roma (00:30 UTC), con squadre a media → sì
# 96: domani, ma nessuna squadra a media → no
# 97: dopodomani → no
# 98: prima_partita non ancora calcolata: la prima partita NBA della giornata, domani alle 20 di Roma; media dal file → sì
for n, dal, prima, media, mfile in ((95, date(2027, 3, 9), datetime(2027, 3, 10, 0, 30, tzinfo=timezone.utc), ["LAL"], []),
                                    (96, date(2027, 3, 9), datetime(2027, 3, 10, 0, 30, tzinfo=timezone.utc), [], []),
                                    (97, date(2027, 3, 11), datetime(2027, 3, 12, 0, 30, tzinfo=timezone.utc), ["BOS"], []),
                                    (98, date(2027, 3, 10), None, None, ["MIA"])):
    db._q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al, prima_partita, media, media_file) VALUES (%s, %s, 'regular', %s, %s, %s, %s, %s)",
          (S, n, dal, dal + timedelta(days=2), prima, media, mfile))
db._q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES ('bv1', %s, 2, %s, %s, 'MIA', 'NY', 'STATUS_SCHEDULED')",
      (S, date(2027, 3, 10), datetime(2027, 3, 10, 19, 0, tzinfo=timezone.utc)))
v = {r["numero"]: r for r in giornate_vigilia(S, OGGI) if r["numero"] >= 95}
ok(sorted(v) == [95, 98] and v[95]["media"] == ["LAL"] and v[98]["media"] == ["MIA"],
   f"la sera prima: solo le giornate con squadre a media che iniziano domani (anche senza prima_partita) {sorted(v)}")
ok(not [r for r in giornate_vigilia(S, OGGI - timedelta(days=1)) if r["numero"] >= 95], "due giorni prima: niente")
ok(orario("bref_vigilia").strftime("%H:%M") == "20:00", "orari.bref_vigilia: le 20")

db._q("DELETE FROM lega_giornate WHERE stagione = %s AND numero BETWEEN 95 AND 98", (S,))
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'bv%%'")

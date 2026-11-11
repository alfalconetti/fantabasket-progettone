import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""Chi prende la media prende la fantamedia di Basketball-Reference (v7.6.0, Luca 11/11): l'ultima rilevazione prima
della prima partita della giornata; le giornate prima di MEDIA_BREF_DAL restano coi tabellini ESPN."""
from datetime import date, datetime, timedelta, timezone
import db, config
import calcolo
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()
S = config.stagione()
B1 = str(int(S) + 1)


def pulizia():
    db.q("DELETE FROM nba_tabellini WHERE atleta LIKE 'mb%%'"); db.q("DELETE FROM nba_partite WHERE espn_id LIKE 'mb%%'")
    db.q("DELETE FROM bref_stats WHERE nome_bref LIKE 'Media Bref %%'"); db.q("DELETE FROM giocatori WHERE espn_id LIKE 'mb%%'")


pulizia()
for a, n in (("mb1", "Media Bref Uno"), ("mb2", "Media Bref Due")):
    db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s)", (n, n, n.lower(), a))
# ESPN: due partite prima della giornata, 20 e 30 → media 25
for i, d in enumerate((date(2026, 11, 2), date(2026, 11, 4))):
    db.q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES (%s, %s, 2, %s, %s, 'MBA', 'MBB', 'STATUS_FINAL')",
         (f"mb_p{i}", S, d, datetime.combine(d, datetime.min.time(), timezone.utc)))
    for a in ("mb1", "mb2"):
        db.q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, pts, fp) VALUES (%s, %s, %s, 'MBA', TRUE, 30, 10, %s)",
             (f"mb_p{i}", a, a, 20 + 10 * i))
# bref: la rilevazione della sera prima (fantamedia 31,50 su 12) e una dopo l'inizio della giornata (40), che non conta
PRIMA = datetime(2026, 11, 21, 0, 30, tzinfo=timezone.utc)
z = ", fga, fgm, ftm, fta, fg3m, orb, drb, ast, stl, blk, tov"
for ts, pts, g in ((PRIMA - timedelta(hours=5, minutes=30), 63, 12), (PRIMA - timedelta(days=2), 50, 10), (PRIMA + timedelta(hours=8), 80, 13)):
    db.q(f"INSERT INTO bref_stats (timestamp, stagione, nome_bref, team, g, pts{z}) VALUES (%s, %s, 'Media Bref Uno', 'MBA', %s, %s, 0,0,0,0,0,0,0,0,0,0,0)",
         (ts, B1, g, pts))

nuova = {"dal": date(2026, 11, 20), "al": date(2026, 11, 22), "prima_partita": PRIMA, "media": ["MBA"], "numero": None}
vecchia = {**nuova, "dal": date(2026, 11, 6), "al": date(2026, 11, 8), "prima_partita": datetime(2026, 11, 7, 0, 30, tzinfo=timezone.utc)}
m = db.medie_assenti(["mb1", "mb2"], S, nuova)
ok(m["mb1"] == {"media": 31.5, "partite": 12, "fonte": "bref"}, f"giornata nuova: la fantamedia bref della sera prima, non quella dopo {m.get('mb1')}")
ok(m["mb2"]["media"] == 25.0 and "fonte" not in m["mb2"], "senza bref: la media dei tabellini ESPN")
mv = db.medie_assenti(["mb1"], S, vecchia)
ok(mv["mb1"]["media"] == 25.0 and "fonte" not in mv["mb1"], "giornata prima di MEDIA_BREF_DAL: i tabellini ESPN, come alla convalida")
ok(db.medie_assenti([], S, nuova) == {}, "nessun giocatore")
# ricalcolo giorni dopo: le rilevazioni di bref arrivate dopo l'inizio non cambiano niente
db.q(f"INSERT INTO bref_stats (timestamp, stagione, nome_bref, team, g, pts{z}) VALUES (NOW(), %s, 'Media Bref Uno', 'MBA', 20, 100, 0,0,0,0,0,0,0,0,0,0,0)", (B1,))
ok(db.medie_assenti(["mb1"], S, nuova)["mb1"]["media"] == 31.5, "ricalcolo dopo: la stessa rilevazione (quella prima della prima partita)")
# senza prima_partita salvata: la prima partita NBA dei giorni della giornata, mai «adesso»
db.q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES ('mb_p9', %s, 2, %s, %s, 'MBB', 'MBC', 'STATUS_FINAL')",
     (S, date(2026, 11, 20), PRIMA))
ok(db.medie_assenti(["mb1"], S, {**nuova, "prima_partita": None})["mb1"]["media"] == 31.5, "senza prima_partita: la prima partita NBA della giornata")
db.q("DELETE FROM nba_partite WHERE espn_id = 'mb_p9'")
ok(db.medie_assenti(["mb1"], S, {**nuova, "prima_partita": None})["mb1"]["media"] == 25.0,
   "senza partite: le 12 di New York del primo giorno (17 UTC del 20/11): conta la rilevazione di due giorni prima")

# il calcolo: la squadra NBA non gioca nella giornata → la media di bref, con la nota
p = calcolo.punteggio_giocatori(S, nuova, ["mb1", "mb2"])
ok(p["mb1"]["come"] == "media" and p["mb1"]["fp"] == 31.5 and "media Basketball-Reference su 12 partite" in p["mb1"]["nota"],
   f"calcolo: prende la media di bref {p['mb1']}")
ok(p["mb2"]["come"] == "media" and p["mb2"]["fp"] == 25.0 and "Basketball-Reference" not in p["mb2"]["nota"], "calcolo: senza bref quella ESPN")
pv = calcolo.punteggio_giocatori(S, vecchia, ["mb1"])
ok(pv["mb1"]["fp"] == 25.0, "calcolo di una giornata vecchia: invariato")

pulizia()

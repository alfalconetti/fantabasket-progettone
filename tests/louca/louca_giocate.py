import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.15.0 (Luca, 15/11): % di partite giocate notte per notte (classifica.giocate_notte_per_notte). Roster: le
partite della squadra NBA mentre il giocatore era nella squadra del fantabasket (registro), cambio di squadra NBA
(nba_movimenti), assente senza tabellino, DNP, chi non ha mai giocato fuori. Quintetto: i titolari schierati."""
from datetime import datetime, timedelta, timezone

import db
import classifica as C
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()
S = "1999"                                               # una stagione tutta per la prova
t0 = datetime(1999, 11, 1, 23, 0, tzinfo=timezone.utc)


def pulisci():
    for t in ("lega_giornate", "lega_calcoli"):
        db.q(f"DELETE FROM {t} WHERE stagione = %s", (S,))
    if db.q("SELECT to_regclass('ipa_formazioni') AS t", one=True)["t"]:
        db.q("DELETE FROM ipa_formazioni WHERE stagione = %s", (S,))
    db.q("DELETE FROM nba_tabellini WHERE atleta LIKE 'gn%%'")
    db.q("DELETE FROM nba_partite WHERE espn_id LIKE 'gn%%'")
    db.q("DELETE FROM nba_movimenti WHERE atleta LIKE 'gn%%'")
    for r in db.q("SELECT id FROM giocatori WHERE nome_bref LIKE 'Gioc Notte%%'", many=True) or []:
        db.q("DELETE FROM transazioni WHERE giocatore_id = %s", (r["id"],))
        db.q("DELETE FROM giocatori WHERE id = %s", (r["id"],))


pulisci()
try:
    for i in range(6):
        for sq, avv in (("GNA", "GNX"), ("GNB", "GNY")):
            db.q("""INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato)
                    VALUES (%s, %s, 2, %s, %s, %s, %s, 'STATUS_FINAL')""",
                 (f"gn_{sq[-1].lower()}{i}", S, (t0 + timedelta(days=i)).date(), t0 + timedelta(days=i), sq, avv))
    g = {}
    for n, espn in (("X", "gnx"), ("Y", "gny"), ("Z", "gnz")):
        g[n] = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id",
                    (f"Gioc Notte {n}", f"Gioc Notte {n}", f"gioc notte {n.lower()}", espn), one=True)["id"]

    def mov(gid, da, a, ts):
        db.q("""INSERT INTO transazioni (oggetto, tipo, giocatore_id, team_id_da, team_id_a, stagione, timestamp)
                VALUES ('giocatore', %s, %s, %s, %s, %s, %s)""", ("trade" if da else "iniziale", gid, da, a, S, ts))
    mov(g["X"], None, "team01", t0 - timedelta(days=60))
    mov(g["X"], "team01", "team02", t0 + timedelta(days=4, hours=12))       # dalla 6ª partita è di team02
    mov(g["Y"], None, "team01", t0 - timedelta(days=60))
    mov(g["Z"], None, "team02", t0 - timedelta(days=60))

    def tab(partita, atleta, sq, giocato, fp=20):
        db.q("""INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, fp) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
             (partita, atleta, atleta, sq, giocato, 30 if giocato else 0, fp if giocato else 0))
    # X (GNA): gioca le prime tre, la 4ª assente (niente tabellino), la 5ª DNP, la 6ª gioca
    for i in (0, 1, 2, 5):
        tab(f"gn_a{i}", "gnx", "GNA", True)
    tab("gn_a4", "gnx", "GNA", False)
    # Y: solo un DNP in tutta la stagione → fuori
    tab("gn_a0", "gny", "GNA", False)
    # Z: GNA fino al giorno 2, poi GNB (nba_movimenti); gioca a0, a1, b3, b4; b5 DNP
    for p, sq in (("gn_a0", "GNA"), ("gn_a1", "GNA"), ("gn_b3", "GNB"), ("gn_b4", "GNB")):
        tab(p, "gnz", sq, True)
    tab("gn_b5", "gnz", "GNB", False)
    db.q("INSERT INTO nba_movimenti (atleta, giorno, da, a) VALUES ('gnz', %s, 'GNA', 'GNB')", ((t0 + timedelta(days=3)).date(),))

    r = C.giocate_notte_per_notte(S)
    ok(abs(r["team01"]["gioc_roster"] - 60.0) < 1e-6,
       f"team01: X 3 giocate su 5 partite mentre era suo (assente e DNP contano come non giocate), Y fuori ({r['team01']})")
    ok(abs(r["team02"]["gioc_roster"] - 100 * 5 / 7) < 1e-6,
       f"team02: X 1 su 1 dopo la trade, Z 4 su 6 con il cambio di squadra NBA ({r['team02']})")
    ok(r["team01"]["gioc_q"] is None and r["team02"]["gioc_q"] is None, "senza formazioni schierate: quintetto vuoto")
    ok(C.giocate_notte_per_notte("1998") == {}, "stagione senza partite: niente")
    # quintetto: i titolari schierati nella G1 (giorni 0–2) convalidata; la G2 non convalidata non conta
    db.q("""CREATE TABLE IF NOT EXISTS ipa_formazioni (stagione TEXT NOT NULL, giornata INT NOT NULL, team_id TEXT NOT NULL,
              ruolo TEXT NOT NULL, giocatore_id INT, PRIMARY KEY (stagione, giornata, team_id, ruolo))""")
    for n, dal, al in ((1, 0, 2), (2, 3, 5)):
        db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES (%s, %s, 'regular', %s, %s)",
             (S, n, (t0 + timedelta(days=dal)).date(), (t0 + timedelta(days=al)).date()))
        db.q("INSERT INTO lega_calcoli (stagione, giornata, stato, risultati) VALUES (%s, %s, %s, '[]')",
             (S, n, "convalidata" if n == 1 else "da_convalidare"))
        db.q("INSERT INTO ipa_formazioni VALUES (%s, %s, 'team01', 'PG', %s), (%s, %s, 'team02', 'C', %s)", (S, n, g["X"], S, n, g["Z"]))
    r = C.giocate_notte_per_notte(S)
    ok(abs(r["team01"]["gioc_q"] - 100.0) < 1e-6 and abs(r["team02"]["gioc_q"] - 100 * 2 / 3) < 1e-6,
       f"quintetto: i titolari schierati nelle giornate convalidate, sulle partite della giornata ({r['team01']['gioc_q']}, {r['team02']['gioc_q']})")
finally:
    pulisci()

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.20.0 (Luca, 21/11, mockup approvato): /rendimento_situazione, la media per quintetto, panchina, tribuna e free
agent, divisa per squadra (shared.situazione), e il periodo dei comandi di statistiche (shared.periodo)."""
import json
import os
from datetime import date, datetime, timedelta, timezone

import db
from shared import periodo as PER
from shared import situazione as SIT
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()
S = "1998"
t0 = datetime(1998, 11, 1, 23, 0, tzinfo=timezone.utc)

# ── periodo ──
ok(PER.leggi(["Mario", "Hezonja"]) == ("Mario Hezonja", PER.Periodo()), "solo il nome: la stagione")
ok(PER.leggi(["Hezonja", "10"]) == ("Hezonja", PER.Periodo(ultime=10)), "un numero: le ultime N giocate")
try:
    PER.leggi(["Hezonja", "5"]); ok(False, "N = 5 rifiutato")
except PER.Errore as e:
    ok("maggiore di 5" in str(e), "N = 5: rifiutato, con la spiegazione")
ok(PER.leggi(["Hezonja", "01-11-26"]) == ("Hezonja", PER.Periodo(dal=date(2026, 11, 1))), "una data: da lì a oggi")
ok(PER.leggi(["Nikola", "Jokic", "15/11/2026", "01-11-26"]) == ("Nikola Jokic", PER.Periodo(dal=date(2026, 11, 1), al=date(2026, 11, 15))),
   "due date (anche al contrario e in formati diversi): l'intervallo")
ok(PER.leggi(["76ers"]) == ("76ers", PER.Periodo()) and PER.leggi(["Hezonja", "6"])[1].ultime == 6, "un nome che è un numero da solo resta un nome; 6 va bene")
ok(PER.Periodo(ultime=10).descrizione("x") == "ultime 10 partite giocate"
   and PER.Periodo(dal=date(2026, 11, 1), al=date(2026, 11, 15)).descrizione("x") == "dal 01/11/2026 al 15/11/2026", "descrizione del periodo")


def pulisci():
    db.q("DELETE FROM lega_giornate WHERE stagione = %s", (S,))
    for t in ("ipa_formazioni", "ipa_panchine"):
        if db.q("SELECT to_regclass(%s) AS t", (t,), one=True)["t"]:
            db.q(f"DELETE FROM {t} WHERE stagione = %s", (S,))
    db.q("DELETE FROM nba_tabellini WHERE atleta = 'sitx'")
    db.q("DELETE FROM nba_partite WHERE espn_id LIKE 'sit%%'")
    for r in db.q("SELECT id FROM giocatori WHERE nome_bref = 'Sit Uno'", many=True) or []:
        db.q("DELETE FROM transazioni WHERE giocatore_id = %s", (r["id"],))
        db.q("DELETE FROM giocatori WHERE id = %s", (r["id"],))


pulisci()
try:
    db.q("""CREATE TABLE IF NOT EXISTS ipa_formazioni (stagione TEXT NOT NULL, giornata INT NOT NULL, team_id TEXT NOT NULL,
              ruolo TEXT NOT NULL, giocatore_id INT, PRIMARY KEY (stagione, giornata, team_id, ruolo))""")
    db.q("""CREATE TABLE IF NOT EXISTS ipa_panchine (stagione TEXT NOT NULL, giornata INT NOT NULL, team_id TEXT NOT NULL,
              titolo TEXT, righe JSONB NOT NULL, inviata TIMESTAMPTZ NOT NULL DEFAULT NOW(), da BIGINT,
              fonte TEXT NOT NULL DEFAULT 'gm', in_ritardo BOOLEAN NOT NULL DEFAULT FALSE, messaggio_canale BIGINT,
              PRIMARY KEY (stagione, giornata, team_id))""")
    for n, dal, al in ((1, 0, 2), (2, 3, 5), (3, 6, 8)):
        db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES (%s, %s, 'regular', %s, %s)",
             (S, n, (t0 + timedelta(days=dal)).date(), (t0 + timedelta(days=al)).date()))
    x = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES ('Sit Uno', 'Sit Uno', 'sit uno', 'sitx') RETURNING id",
             one=True)["id"]
    for i in range(9):
        db.q("""INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato)
                VALUES (%s, %s, 2, %s, %s, 'SIA', 'SIB', 'STATUS_FINAL')""",
             (f"sit{i}", S, (t0 + timedelta(days=i)).date(), t0 + timedelta(days=i)))
        giocato = i != 2                                         # il giorno 2 DNP: non conta
        db.q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, fp) VALUES (%s, 'sitx', 'Sit Uno', 'SIA', %s, %s, %s)",
             (f"sit{i}", giocato, 30 if giocato else 0, 10 + i if giocato else 0))

    def mov(tipo, da, a, giorni):
        db.q("""INSERT INTO transazioni (oggetto, tipo, giocatore_id, team_id_da, team_id_a, stagione, timestamp)
                VALUES ('giocatore', %s, %s, %s, %s, %s, %s)""", (tipo, x, da, a, S, t0 + timedelta(days=giorni)))
    mov("iniziale", None, "team01", -30)
    mov("taglio", "team01", None, 3.5)                           # free agent dalla partita del giorno 4
    mov("firma", None, "team02", 5.5)                            # a team02 dal giorno 6
    db.q("INSERT INTO ipa_formazioni VALUES (%s, 1, 'team01', 'SF', %s)", (S, x))                     # G1 in quintetto
    db.q("INSERT INTO ipa_panchine (stagione, giornata, team_id, righe) VALUES (%s, 2, 'team01', %s)",   # G2 in panchina
         (S, json.dumps([{"giocatore_id": x, "testo": "Sit"}])))
    # G3: team02 non lo schiera → tribuna

    gare = SIT.partite(x, PER.Periodo(), S)
    ok([(r["data"].day - t0.day, r["dove"]) for r in gare] ==
       [(0, "quintetto"), (1, "quintetto"), (3, "panchina"), (4, "free agent"), (5, "free agent"),
        (6, "tribuna"), (7, "tribuna"), (8, "tribuna")], f"ogni partita giocata con dov'era (la DNP no) {[(r['data'], r['dove']) for r in gare]}")
    d = SIT.dati(x, PER.Periodo(), S)
    rq = {r["t"]: (r["v"], r["s"]) for r in d["riquadri"]}
    ok(rq == {"Media": ("14,25", "8 partite"), "In quintetto": ("10,50", "2 partite"), "In panchina": ("13,00", "1 partita"),
              "In tribuna": ("17,00", "3 partite"), "Free agent": ("14,50", "2 partite")}, f"riquadri: media totale e per situazione {rq}")
    ok([r["id"] for r in d["righe"]] == ["team01", "team02", "free agent"], f"righe: le squadre nell'ordine, free agent in fondo {[r['id'] for r in d['righe']]}")
    t1 = d["righe"][0]
    ok([c and (c["media"], c["g"]) for c in t1["celle"]] == [("10,50", 2), ("13,00", 1), None] and t1["totale"]["media"] == "11,33"
       and t1["quando"] == f"{t0:%d/%m} – {(t0 + timedelta(days=3)):%d/%m}", "team01: quintetto e panchina, totale di riga e date")
    ok(d["righe"][1]["celle"][2].get("migliore") and d["righe"][2]["celle"] == [None, None, None]
       and [c["media"] for c in d["totali"]] == ["10,50", "13,00", "17,00"], "casella migliore in oro, free agent solo nel totale, totali di colonna")
    tx = SIT.testo(d)
    ok("Media <b>14,25</b> (8)" in tx and "🆓 Free agent <b>14,50</b> (2)" in tx, "il riepilogo in testo")
    png = SIT.immagine(d)
    ok(png[:4] == b"\x89PNG", "la tabella come immagine")
    if os.environ.get("SIT_PNG"):
        open(os.environ["SIT_PNG"], "wb").write(png)
    d6 = SIT.dati(x, PER.Periodo(ultime=6), S)
    ok(d6["totale"]["g"] == 6 and d6["riquadri"][1]["v"] == "—" and "ultime 6 partite giocate" in d6["periodo"],
       "ultime 6 giocate: dal giorno 3, niente quintetto")
    dd = SIT.dati(x, PER.Periodo(dal=(t0 + timedelta(days=6)).date()), S)
    ok(len(dd["righe"]) == 1 and SIT.immagine(dd)[:4] == b"\x89PNG", "da una data, una squadra sola: l'immagine c'è lo stesso (v7.20.1)")
    import asyncio, types
    _inv = []
    class _M:
        async def reply_text(self, t, **k): _inv.append(("testo", t))
        async def reply_photo(self, p, **k): _inv.append(("foto", p[:4]))
    SIT_stag = SIT.L.stagione
    SIT.L.stagione = lambda: S
    asyncio.run(SIT.rispondi(_M(), x, PER.Periodo(dal=(t0 + timedelta(days=6)).date())))
    SIT.L.stagione = SIT_stag
    ok([k for k, _v in _inv] == ["foto"], "/rendimento_situazione: solo l'immagine, anche con una squadra sola (v7.20.2)")
    ok(SIT.dati(x, PER.Periodo(dal=date(1999, 6, 1)), S) is None, "nessuna partita nel periodo: None")
    # v7.20.1: /player, giornata e dov'era in ogni partita (anche la DNP)
    pp = SIT.per_partita(x, ["sit0", "sit2", "sit3", "sit4", "sit7", "nessuna"], S)
    ok(pp == {"sit0": {"giornata": 1, "dove": "quintetto"}, "sit2": {"giornata": 1, "dove": "quintetto"},
              "sit3": {"giornata": 2, "dove": "panca"}, "sit4": {"giornata": 2, "dove": "fa"}, "sit7": {"giornata": 3, "dove": "tribuna"}},
       f"/player: giornata e dov'era per partita, anche la DNP {pp}")
finally:
    pulisci()

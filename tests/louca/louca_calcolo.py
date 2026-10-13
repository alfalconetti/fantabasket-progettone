import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""loucabot v4: tabellini ESPN (risposta vera ridotta di NYK-SAS del 1/3/2026 in
tests/louca/espn-summary-20260301.json), fantapunti del regolamento, infortunati, punteggio del
giocatore nella giornata (partite, media, zero), FADD, supplementari, abbinamento con l'anagrafica."""
import asyncio, json, os
from datetime import date, datetime, timezone
import db, nba, calcolo
db.init_db()
db.q("TRUNCATE nba_tabellini, nba_infortuni, nba_atleti, lega_giornate, lega_partite, nba_partite")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
QUI = os.path.dirname(os.path.abspath(__file__))
vero = json.load(open(os.path.join(QUI, "espn-summary-20260301.json")))

# ── tabellino vero e formula ──
tab = nba.leggi_tabellino(vero, "401810723")
fp = {r["nome"]: r["fp"] for r in tab}
ok((fp["Mikal Bridges"], fp["Josh Hart"], fp["Jalen Brunson"], fp["Victor Wembanyama"]) == (41.25, 31.75, 30.75, 29.75),
   "fantapunti del regolamento sul tabellino vero (Bridges 41,25, Hart 31,75, Brunson 30,75, Wembanyama 29,75)")
clarkson = next(r for r in tab if r["nome"] == "Jordan Clarkson")
ok(not clarkson["giocato"] and clarkson["fp"] == 0 and len(tab) == 28, "a referto senza entrare (DNP): giocato = no")
w = next(r for r in tab if r["nome"] == "Victor Wembanyama")
ok((w["squadra"], w["titolare"], w["minuti"], w["fgm"], w["fga"], w["tpm"], w["ftm"], w["fta"], w["oreb"], w["dreb"], w["tov"])
   == ("SAS", True, 34, 8, 17, 1, 8, 9, 1, 12, 7), "statistiche lette (sigla SA → SAS)")

# ── scaricamento: solo partite finite senza tabellino, una volta ──
def partita(pid, giorno, casa, trasf, stato="STATUS_FINAL", stagione="2026"):
    d = date.fromisoformat(giorno)
    db.salva_partite_nba([{"espn_id": pid, "stagione": stagione, "tipo": 2, "data_et": d,
                           "inizio": datetime(d.year, d.month, d.day, 23, 0, tzinfo=timezone.utc),
                           "casa": casa, "trasferta": trasf, "stato": stato}])
partita("401810723", "2026-03-01", "NYK", "SAS", stagione="2025")
partita("futura", "2026-03-02", "NYK", "BOS", "STATUS_SCHEDULED", stagione="2025")
ok(db.partite_senza_tabellino() == ["401810723"], "da scaricare: solo le partite finite senza tabellino")
async def finto(pid):
    return vero
r = asyncio.run(nba.scarica_tabellini(db.partite_senza_tabellino(), scarica=finto, pausa=0))
ok(r["partite"] == 1 and r["giocatori"] == 28 and db.partite_senza_tabellino() == [], "tabellino salvato, non si riscarica")
asyncio.run(nba.scarica_tabellini(["401810723"], scarica=finto, pausa=0))
ok(db.q("SELECT COUNT(*) AS n FROM nba_tabellini", one=True)["n"] == 28, "riscaricato a mano: sostituisce, niente doppioni")

# ── infortunati ──
voci = nba.leggi_infortuni(vero)
ok(len(voci) == 5 and {"atleta": "4066259", "nome": "De'Aaron Fox", "squadra": "SAS", "stato": "Day-To-Day"}.items()
   <= next(v for v in voci if v["nome"] == "De'Aaron Fox").items(), "infortunati letti dalla risposta vera")
solo_link = {"injuries": [{"abbreviation": "LAL", "injuries": [{"status": "Out", "athlete": {
    "displayName": "Prova Link", "links": [{"href": "https://www.espn.com/nba/player/_/id/12345/prova"}]}}]}]}
ok(nba.leggi_infortuni(solo_link) == [{"atleta": "12345", "nome": "Prova Link", "squadra": "LAL", "stato": "Out", "dettaglio": ""}],
   "infortunati: id dal link quando manca il campo id")
async def finti_inf():
    return vero
asyncio.run(nba.scarica_infortuni(scarica=finti_inf))
ok(db.q("SELECT COUNT(*) AS n FROM nba_infortuni", one=True)["n"] == 5, "snapshot degli infortunati salvato")
asyncio.run(nba.scarica_infortuni(scarica=finti_inf))
ok(db.q("SELECT COUNT(DISTINCT preso) AS n FROM nba_infortuni", one=True)["n"] == 2, "un secondo snapshot si aggiunge, non sostituisce")

# quale snapshot conta per il calcolo: l'ultimo prima della prima partita del giorno; pulizia dopo 7 giorni
from datetime import datetime as _dt, timezone as _tz, timedelta as _td
db.q("TRUNCATE nba_infortuni, nba_tabellini, nba_partite CASCADE")
G1 = date(2026, 11, 10)
def snap(quando, stato):
    db.q("INSERT INTO nba_infortuni (giorno, atleta, nome, stato, preso) VALUES (%s, '77', 'Gioc 77', %s, %s)", (G1, stato, quando))
inizio = _dt(2026, 11, 11, 0, 0, tzinfo=_tz.utc)                       # 19:00 a New York
db.salva_partite_nba([{"espn_id": "s1", "stagione": "2026", "tipo": 2, "data_et": G1, "casa": "NYK", "trasferta": "BOS",
                       "inizio": inizio, "stato": "STATUS_FINAL"}])
snap(inizio - _td(hours=8), "Questionable"); snap(inizio - _td(minutes=30), "Out"); snap(inizio + _td(hours=3), "Day-To-Day")
ok(db.snapshot_del_giorno([G1])[G1] == inizio - _td(minutes=30) and db.infortuni(["77"], [G1]) == {("77", G1): "Out"},
   "conta lo snapshot subito prima della prima partita (quello di notte durante le partite no)")
ok(db.pulisci_snapshot(G1 + _td(days=3)) == 0 and db.q("SELECT COUNT(*) AS n FROM nba_infortuni", one=True)["n"] == 3,
   "nell'ultima settimana si tengono tutti")
ok(db.pulisci_snapshot(G1 + _td(days=8)) == 2 and db.infortuni(["77"], [G1]) == {("77", G1): "Out"},
   "più vecchi di una settimana: resta solo quello che conta, il calcolo non cambia")
db.q("TRUNCATE nba_infortuni, nba_tabellini, nba_partite CASCADE")

# ── punteggio del giocatore nella giornata ──
def riga(pid, atleta, squadra, fp, giocato=True):
    db.salva_tabellino(pid, [x for x in db.q("SELECT * FROM nba_tabellini WHERE partita = %s", (pid,), many=True) or []] + [{
        "partita": pid, "atleta": atleta, "nome": f"Gioc {atleta}", "squadra": squadra, "titolare": True,
        "giocato": giocato, "minuti": 30 if giocato else 0, "pts": 0, "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0,
        "ftm": 0, "fta": 0, "oreb": 0, "dreb": 0, "ast": 0, "stl": 0, "blk": 0, "tov": 0, "pf": 0, "fp": fp}])
partita("p00", "2026-10-29", "DEN", "PHX"); riga("p00", "6", "DEN", 18)
partita("p0", "2026-10-28", "MIA", "NYK"); riga("p0", "4", "MIA", 24); riga("p0", "5", "MIA", 16)
partita("p1", "2026-11-02", "NYK", "SAS"); riga("p1", "1", "NYK", 40); riga("p1", "2", "SAS", 10)
riga("p1", "3", "NYK", 0, giocato=False); riga("p1", "9", "SAS", 8)
partita("p2", "2026-11-03", "NYK", "BOS"); riga("p2", "1", "NYK", 20); riga("p2", "8", "NYK", 12)
partita("p3", "2026-11-03", "DEN", "LAL", "STATUS_POSTPONED")
G = {"numero": 5, "dal": date(2026, 11, 2), "al": date(2026, 11, 3), "media": ["MIA"], "media_file": []}
db.salva_infortuni(date(2026, 11, 2), [{"atleta": "5", "nome": "Gioc 5", "stato": "Out"},
                                       {"atleta": "3", "nome": "Gioc 3", "stato": "Questionable"}])
db.salva_infortuni(date(2026, 11, 3), [{"atleta": "5", "nome": "Gioc 5", "stato": "Out"},
                                       {"atleta": "3", "nome": "Gioc 3", "stato": "Out"},
                                       {"atleta": "4", "nome": "Gioc 4", "stato": "Probable"}])
P = calcolo.punteggio_giocatori("2026", G, ["1", "2", "3", "4", "5", "6", "8", "9", "ignoto"])
ok(P["1"]["fp"] == 30 and P["1"]["come"] == "partite", "due partite nella giornata: media matematica (40 e 20 → 30)")
ok(P["2"]["fp"] == 10, "una partita: i suoi fantapunti")
ok(P["3"]["fp"] == 0 and P["3"]["come"] == "zero", "la sua squadra gioca, lui no (DNP): 0")
ok(P["4"]["fp"] == 24 and P["4"]["come"] == "media", "squadra a media (MIA), disponibile (Probable): media della stagione")
ok(P["5"]["fp"] == 0 and "indisponibile" in P["5"]["nota"], "squadra a media ma infortunato in tutti i giorni: 0, niente media")
ok(P["6"]["fp"] == 18 and "rinviata" in P["6"]["nota"], "solo partita rinviata: media della stagione")
ok(P["ignoto"]["fp"] == 0 and "sconosciuta" in P["ignoto"]["nota"], "giocatore mai visto: 0")
db.q("DELETE FROM nba_infortuni WHERE giorno = '2026-11-03'")
P2 = calcolo.punteggio_giocatori("2026", G, ["5"])
ok(P2["5"]["fp"] == 0, "indisponibile nell'unico snapshot della giornata: 0")
db.q("TRUNCATE nba_infortuni")
P3 = calcolo.punteggio_giocatori("2026", G, ["5"])
ok(P3["5"]["fp"] == 16 and "non verificata" in P3["5"]["nota"], "nessuno snapshot: media, con l'avviso")
db.salva_infortuni(date(2026, 11, 2), [{"atleta": "5", "nome": "Gioc 5", "stato": "Out"},
                                       {"atleta": "3", "nome": "Gioc 3", "stato": "Questionable"}])
db.salva_infortuni(date(2026, 11, 3), [{"atleta": "5", "nome": "Gioc 5", "stato": "Out"},
                                       {"atleta": "3", "nome": "Gioc 3", "stato": "Out"}])

# ── squadra: FADD ──
Q = [{"atleta": "1", "ruolo": "SF", "nome": "Uno"}, {"atleta": "3", "ruolo": "PG", "nome": "Tre"},
     {"atleta": "2", "ruolo": "C", "nome": "Due"}, {"atleta": "4", "ruolo": "SG", "nome": "Quattro"},
     {"atleta": "6", "ruolo": "PF", "nome": "Sei"}]
B = [{"atleta": "9", "ruolo": "SF", "nome": "Nove"}, {"atleta": "8", "ruolo": "PG", "nome": "Otto"},
     {"atleta": "5", "ruolo": "PG", "nome": "Cinque"}]
S = calcolo.punteggio_squadra(G, Q, B, P)
ok(S["fadd"] and S["fadd"]["esce"]["atleta"] == "3" and S["fadd"]["entra"]["atleta"] == "8" and S["totale"] == 94,
   f"FADD: il titolare PG senza partite e sempre col tag lascia il posto al primo panchinaro PG (totale 94) {S['fadd']}")
ok([x["atleta"] for x in S["panchina"]] == ["9", "5"], "dopo la FADD la panchina scala")
S2 = calcolo.punteggio_squadra(G, Q, [B[0]], P)
ok(S2["fadd"] is None and S2["totale"] == 82 and any("nessun panchinaro" in a for a in S2["avvisi"]),
   "FADD possibile ma nessun panchinaro del ruolo: resta lo 0, con l'avviso")
db.salva_infortuni(date(2026, 11, 3), [{"atleta": "5", "nome": "Gioc 5", "stato": "Out"},
                                       {"atleta": "3", "nome": "Gioc 3", "stato": "Probable"}])
ok(calcolo.punteggio_squadra(G, Q, B, P)["fadd"] is None, "FADD: senza il tag in tutti i giorni non si sostituisce")
partita("p4", "2026-11-04", "NYK", "CHI")
G3 = {**G, "al": date(2026, 11, 4)}
db.salva_infortuni(date(2026, 11, 3), [{"atleta": "3", "nome": "Gioc 3", "stato": "Out"}])
S3 = calcolo.punteggio_squadra(G3, Q, B, calcolo.punteggio_giocatori("2026", G3, ["1", "2", "3", "4", "6", "8", "9", "5"]))
ok(S3["fadd"] is None and any("decide un admin" in a for a in S3["avvisi"]), "FADD: manca lo snapshot di un giorno → decide un admin")

# ── esito e supplementari ──
sq = lambda tot, pan=(): {"totale": tot, "panchina": [{"fp": x} for x in pan]}
ok(calcolo.esito(sq(100), sq(90))["vince"] == "casa", "scarto di 5 o più (bonus casa compreso): vince chi ha di più")
e1 = calcolo.esito(sq(100), sq(104), bonus=3)
ok(e1["regolamentari"] == (103, 104) and e1["supplementari"] >= 1, "scarto sotto 5 col bonus: supplementari")
e2 = calcolo.esito(sq(100, (10, 20)), sq(102, (10, 10)))
ok((e2["vince"], e2["supplementari"], e2["casa"], e2["trasferta"]) == ("casa", 2, 133, 122),
   "supplementari: un panchinaro alla volta finché lo scarto è di almeno 5")
e3 = calcolo.esito(sq(100), sq(103))
ok(e3["vince"] == "trasferta" and e3["supplementari"] == 5, "pari fino al decimo uomo: vince la trasferta")
ok(calcolo.esito(sq(100), sq(102), bonus=5)["vince"] == "trasferta" and calcolo.esito(sq(100), sq(95), bonus=5)["vince"] == "casa",
   "playoff: bonus casa 5")

# ── abbinamento con l'anagrafica ──
if db.q("SELECT to_regclass('giocatori') AS t", one=True)["t"]:
    # migrazione dalla v4: lega_espn → giocatori.espn_id
    gv = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES ('Vecchio Abb', 'Vecchio Abb', 'vecchio abb') "
              "RETURNING id", one=True)["id"]
    db.q("CREATE TABLE lega_espn (giocatore_id INT PRIMARY KEY, atleta TEXT NOT NULL UNIQUE, nome_espn TEXT NOT NULL, "
         "metodo TEXT NOT NULL, aggiornato TIMESTAMPTZ NOT NULL DEFAULT NOW())")
    db.q("INSERT INTO lega_espn VALUES (%s, '777', 'Vecchio Abb ESPN', 'admin')", (gv,))
    db.migra()
    ok(db.abbinamenti().get(gv) == "777" and db.q("SELECT to_regclass('lega_espn') AS t", one=True)["t"] is None,
       "migrazione: gli abbinamenti della v4 passano in giocatori.espn_id, lega_espn eliminata")
    db.q("DELETE FROM giocatori WHERE id = %s", (gv,))
    ids = [db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES (%s, %s, %s) RETURNING id",
                (n, n, n.lower()), one=True)["id"] for n in ("Zyxw Testone Jr.", "Ábcd Pròva", "Dupl Icato", "Dupl Icato")]
    r = calcolo.abbina_auto({"901": "Zyxw Testone", "902": "Abcd Prova", "903": "Dupl Icato"})
    ab = db.abbinamenti()
    ok(r["nuovi"] == 2 and ab.get(ids[0]) == "901" and ab.get(ids[1]) == "902" and r["ambigui"] == ["Dupl Icato"],
       "abbinamento: nomi senza accenti e Jr. riconosciuti, omonimi lasciati all'admin")
    db.abbina(ids[2], "903", "Dupl Icato", "admin")
    db.abbina(ids[3], "903", "Dupl Icato", "admin")
    ok(db.abbinamenti().get(ids[3]) == "903" and ids[2] not in db.abbinamenti(), "abbinamento a mano: l'ultimo sostituisce")
    nomi = {r["id"]: r["nome_espn"] for r in db.q("SELECT id, nome_espn FROM giocatori WHERE id = ANY(%s)", (ids,), many=True)}
    ok(nomi[ids[0]] == "Zyxw Testone" and nomi[ids[2]] is None, "id e nome ESPN nell'anagrafica (giocatori.espn_id, nome_espn)")
    db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (ids,))
else:
    print("ℹ️ tabella giocatori assente (lancia prima le prove del bot principale): abbinamento non provato")
ok(calcolo.norm("Nikola Đurišić") == calcolo.norm("Nikola Durisic") and calcolo.norm("Kelly Oubre Jr.") == "kellyoubre",
   "nomi normalizzati")
db.q("TRUNCATE nba_tabellini, nba_infortuni, nba_atleti, nba_partite")

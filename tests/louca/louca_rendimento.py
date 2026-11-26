import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""/rendimento e /rendimento_carriera (v7.4.0, Luca 09/11): stagione partita per partita, carriera da Basketball-Reference,
giocatori storici cercati tra i nomi di Basketball-Reference."""
import asyncio, types
from datetime import date, datetime, timedelta, timezone
import db, config
from shared import rendimento as R
import rendimento as LR
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()
S = config.stagione()
B1 = str(int(S) + 1)                                    # Basketball-Reference: la stagione in corso col suo anno di fine


def pulisci():
    db.q("DELETE FROM nba_tabellini WHERE atleta LIKE 'rd%%'"); db.q("DELETE FROM nba_partite WHERE espn_id LIKE 'rd%%'")
    db.q("DELETE FROM bref_stats WHERE nome_bref LIKE 'Rend %%' OR nome_bref IN ('Vecchio Storico', 'Deron Rendi', 'Deron Rendi Jr.', 'Michael Jorrdan', 'Jorrdan Mikey')")
    db.q("DELETE FROM nba_tabellini WHERE atleta LIKE 'rd%%'")
    for r in db.q("SELECT id FROM giocatori WHERE nome_bref LIKE 'Rend %%'", many=True) or []:
        db.q("DELETE FROM transazioni WHERE giocatore_id = %s", (r["id"],)); db.q("DELETE FROM contratti WHERE giocatore_id = %s", (r["id"],))
        db.q("DELETE FROM giocatori WHERE id = %s", (r["id"],))


pulisci()
gid = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES ('Rend Uno', 'Rend Uno', 'rend uno', 'rd1') RETURNING id", one=True)["id"]
db.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) VALUES (%s, 'team02', 7, 2, %s, 'normale', TRUE)", (gid, S))
t0 = datetime(int(S), 10, 20, 23, 0, tzinfo=timezone.utc)
# registro: all'avvio team01, tagliato dopo la 4ª partita, firmato da team02 dopo la 6ª
mov = [("iniziale", None, "team01", t0 - timedelta(days=60)), ("cut", "team01", None, t0 + timedelta(days=3, hours=12)),
       ("signed", None, "team02", t0 + timedelta(days=5, hours=12))]
for tipo, da, a, ts in mov:
    db.q("INSERT INTO transazioni (oggetto, tipo, giocatore_id, team_id_da, team_id_a, stagione, timestamp) VALUES ('giocatore', %s, %s, %s, %s, %s, %s)",
         (tipo, gid, da, a, S, ts))
# 10 partite: 7 di regular season (una non giocata, una a 0 punti e 0 minuti), una di play-in, due di playoff
fps = [20, 30, 25, None, 35, 0, 40, 28, 33, 45]
tipi = [2, 2, 2, 2, 2, 2, 2, 5, 3, 3]
for i, (fp, tipo) in enumerate(zip(fps, tipi)):
    pid = f"rd_p{i}"
    db.q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES (%s, %s, %s, %s, %s, 'RDA', 'RDB', 'STATUS_FINAL')",
         (pid, S, tipo, (t0 + timedelta(days=i)).date(), t0 + timedelta(days=i)))
    db.q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, fp) VALUES (%s, 'rd1', 'Rend Uno', 'RDA', %s, %s, %s)",
         (pid, fp is not None, 0 if fp in (None, 0) else 30, fp or 0))
# una di preseason: non c'è
db.q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES ('rd_pre', %s, 1, %s, %s, 'RDA', 'RDB', 'STATUS_FINAL')",
     (S, (t0 - timedelta(days=10)).date(), t0 - timedelta(days=10)))
db.q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, fp) VALUES ('rd_pre', 'rd1', 'Rend Uno', 'RDA', TRUE, 20, 99)")

d = R.dati_stagione(gid)
p = d["partite"]
ok(len(p) == 10 and all(x["fp"] != 99 for x in p), "/rendimento: tutte le partite tranne la preseason")
ok(p[3]["fp"] is None and p[5]["fp"] is None, "× per chi non ha giocato e per lo 0 con 0 minuti (non fa media, come /player)")
ok([x["tipo"] for x in p].count("post") == 3 and d["post"] == 7, "play-in e playoff accorpati, dal primo")
ok([x["sq"] for x in p] == ["team01"] * 4 + ["_libero"] * 2 + ["team02"] * 4, "squadra del fantabasket a ogni partita (registro): team01, libero, team02")
ok([(f["sq"], f["g"]) for f in d["fasce"]] == [("team01", 3), ("_libero", 1), ("team02", 4)], f"fasce con le partite che contano {d['fasce']}")
ok(abs(p[4]["prog"] - (20 + 30 + 25 + 35) / 4) < 1e-6 and p[4]["mobile"] is None and abs(p[8]["mobile"] - (25 + 35 + 40 + 28 + 33) / 5) < 1e-6,
   "media dall'inizio e delle ultime 5 (solo con 5 partite che contano)")
ok(d["media_big"] == "29,63" and "playoff 39,00 (2)" in d["media_sotto"], f"in alto la media di regular season e play-in (come /player) {d['media_big']} · {d['media_sotto']}")
ok(d["migliore"]["fp"] == 45 and "vs RDB" in d["migliore"]["t"], "la migliore, con l'avversario")
ok(d["y_min"] == 0 and d["y_max"] >= 50, "asse y da 0 a sopra la migliore")
# v7.24.0 (Luca, 22/11): la distribuzione e il decile nella lega
ok(R.quantile([1, 2, 3, 4], .5) == 2.5 and R.quantile([10], .9) == 10 and R.decile(30, [10, 20, 25, 40]) == (8, 75)
   and R.decile(5, [10, 20]) == (1, 0) and R.decile(50, [10, 20]) == (10, 100), "quantili (interpolazione lineare) e decile")
ok(d["distr"] and "mediana 29,00" in d["distr"]["testo"] and d["distr"]["min"] == 20 and d["distr"]["max"] == 40 and d["distr"]["lo"] == 0,
   f"/rendimento: distribuzione delle partite della media (regular season e play-in) {d['distr']}")
_ml = R.medie_lega(S)
ok(_ml.get("rd1") == (sum([20, 30, 25, 35, 40, 28]) / 6, 6), f"medie della lega: solo partite giocate davvero {_ml.get('rd1')}")
ok(d["distr"]["lega"] == "" or "decile della lega" in d["distr"]["lega"], "decile solo se ci sono giocatori con almeno 10 partite")
ok(R.distribuzione([10, 20], 15, "x", stagione=S) is None, "distribuzione: sotto le 5 partite niente")
# v7.34.0: il percentile nel ruolo (gruppi G, F, C delle posizioni eleggibili, stessa soglia di partite)
_tutte = {"me": (30, 20), "g1": (20, 20), "g2": (40, 20), "f1": (10, 20), "f2": (12, 20), "c1": (50, 20), "poche": (5, 3)}
_pos = {"me": {"SG", "SF"}, "g1": {"PG"}, "g2": {"SG"}, "f1": {"PF"}, "f2": {"SF", "C"}, "c1": {"C"}, "poche": {"PG"}}
_t = R.testo_ruolo(30, "me", _tutte, _pos)
ok(_t == "Nel ruolo: tra le guardie 6° decile, meglio del 50% (2) · tra le ali 10° decile, meglio del 100% (2)",
   "percentile nel ruolo: un pezzo per gruppo eleggibile, solo chi ha abbastanza partite")
ok(R.testo_ruolo(30, "x", _tutte, _pos) == "" and R.testo_ruolo(30, "c1", _tutte, _pos).startswith("Nel ruolo: tra i centri"),
   "percentile nel ruolo: niente senza posizioni, «i centri»")
# v7.6.2 (Luca, 11/11): i riquadri, i mesi, la media tratteggiata, le barre da 0
_rq = {r["t"]: r for r in d["riquadri"]}
ok(list(_rq) == ["Fantamedia", "Ultime 5", "Migliore", "Peggiore"] and _rq["Fantamedia"]["v"] == "29,63"
   and _rq["Migliore"]["v"] == "45,00" and _rq["Migliore"]["s"].startswith("vs RDB · ") and _rq["Ultime 5"]["s"][0] in "▲▼",
   f"i quattro riquadri {d['riquadri']}")
ok(d["mesi"] and d["mesi"][0]["i"] == 0 and all(m["lbl"] in R.MESI for m in d["mesi"]), f"i mesi sull'asse {d['mesi']}")
ok(d["media_val"] == 29.625 and d["y_barre"] >= 50 and d["giocate"] == sum(1 for p in d["partite"] if p["fp"] is not None),
   "media della stagione, asse delle barre, partite giocate")
# v7.16.0 (Luca, 16/11): l'etichetta del contratto in testata (non più nella riga), le date sull'asse
ok(d["contratto"]["importo"].endswith("M") and d["contratto"]["anni"].startswith("×") and d["contratto"]["squadra"]
   and ", " not in d["sotto"].split(" · ")[-1] or "×" not in d["sotto"], f"etichetta del contratto e riga senza contratto ({d['contratto']}, {d['sotto']})")
ok(all(x["i"] % 5 == 2 and all(abs(x["i"] - m["i"]) > 1 for m in d["mesi"]) for x in d["date"])
   and all(len(x["lbl"]) == 5 and x["lbl"][2] == "/" for x in d["date"]), f"una data ogni 5 partite, non attaccata ai mesi ({d['date']})")
png = R.immagine(d)
if _os.environ.get("REND_PNG"): open(_os.environ["REND_PNG"] + "_stagione.json", "w").write(__import__("json").dumps(d, default=str, ensure_ascii=False))
if _os.environ.get("REND_PNG"): open(_os.environ["REND_PNG"] + "_stagione.png", "wb").write(png)
ok(png[:4] == b"\x89PNG", "immagine della stagione")
# v7.20.2 (Luca, 21/11): il periodo, come /rendimento_situazione
from shared import periodo as PER
from datetime import date as _date_cls
dp = R.dati_stagione(gid, None, PER.Periodo(dal=(t0 + timedelta(days=4)).date()))
ok([x["fp"] for x in dp["partite"]][:3] == [35, None, 40] and len(dp["partite"]) == 6, "da una data: solo le partite da lì")
ok(dp["riquadri"][0]["t"] == "Nel periodo" and f"{PER.stagione_txt(S)}: 29,63" in dp["riquadri"][0]["s"] and "dal " in dp["titolo"]
   and dp["media_lbl"] == "media del periodo", f"riquadro «Nel periodo» con la media della stagione, periodo nel titolo {dp['riquadri'][0]} {dp['titolo']}")
du = R.dati_stagione(gid, None, PER.Periodo(ultime=6))
ok(du["giocate"] == 6 and du["partite"][0]["fp"] == 25 and "ultime 6" in du["titolo"], f"ultime 6 giocate: dalla sesta giocata dalla fine, DNP in mezzo come tacche {[x['fp'] for x in du['partite']]}")
ok(R.dati_stagione(gid, None, PER.Periodo(dal=_date_cls(2001, 1, 1), al=_date_cls(2001, 2, 1))) is None, "periodo senza partite: None")
ok(R.dati_stagione(gid)["riquadri"][0]["t"] == "Fantamedia" and "media_lbl" in R.dati_stagione(gid), "senza periodo com'era")
ok(R.immagine(dp)[:4] == b"\x89PNG", "immagine col periodo")
# v7.20.2 (Luca, 21/11): a cavallo di due stagioni, titoli veri, media della stagione principale
_P = str(int(S) - 1)
for _i in range(3):                                      # tre partite della stagione prima (una di playoff NBA)
    _pid = f"rd_old{_i}"
    _t = datetime(int(_P) + 1, 4, 1 + _i, 23, 0, tzinfo=timezone.utc)
    db.q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES (%s, %s, %s, %s, %s, 'RDA', 'RDB', 'STATUS_FINAL')",
         (_pid, _P, 3 if _i == 2 else 2, _t.date(), _t))
    db.q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, fp) VALUES (%s, 'rd1', 'Rend Uno', 'RDA', TRUE, 30, %s)", (_pid, 10 + _i))
dx = R.dati_stagione(gid, None, PER.Periodo(ultime=10))
ok(dx["stagioni"] == [_P, S] and dx["stagioni_sep"] == [{"i": 2, "lbl": PER.stagione_txt(S)}] and dx["titolo"].startswith("Stagioni ")
   and dx["post_inizi"][0] == 1, f"ultime 10: a cavallo, linea dove inizia la stagione nuova, playoff NBA di ognuna {dx['stagioni_sep']} {dx['post_inizi']} {dx['titolo']}")
ok(f"{PER.stagione_txt(S)}: 29,63" in dx["riquadri"][0]["s"], f"media della stagione con più partite nel periodo {dx['riquadri'][0]}")
dt = R.dati_stagione(gid, None, PER.Periodo(ultime=50))
ok("tutte le 11 partite giocate nei dati del bot" in dt["titolo"], f"ultime 50 con 11 giocate: lo dice {dt['titolo']}")
_v10 = sorted(p["fp"] for p in dx["partite"] if p["fp"] is not None and p["media_player"])
ok(dx["distr"] and dx["distr"]["min"] == _v10[0] and dx["distr"]["max"] == _v10[-1] and len(_v10) >= 5,
   f"v7.24.0: col periodo la distribuzione è sulle partite del periodo {dx['distr']} {_v10}")
_primo = R.primo_dato()
dd = R.dati_stagione(gid, None, PER.Periodo(dal=_date_cls(2000, 1, 1)))
ok(f"dal {_primo:%d/%m/%Y} (primi dati del bot) a oggi" in dd["titolo"], f"data prima dei dati del bot: lo dice {dd['titolo']}")
d2 = R.dati_stagione(gid, None, PER.Periodo(dal=_date_cls(int(_P) + 1, 4, 1), al=_date_cls(int(_P) + 1, 4, 3)))
ok(d2["titolo"] == f"Stagione {PER.stagione_txt(_P)} · dal 01/04/{int(_P) + 1} al 03/04/{int(_P) + 1}"
   and f"{PER.stagione_txt(_P)}: " in d2["riquadri"][0]["s"], f"solo la stagione prima {d2['titolo']} {d2['riquadri'][0]}")
_fut = PER.descrizione_vera(PER.Periodo(dal=_date_cls(2030, 1, 1), al=_date_cls(2031, 1, 1)), 0, None, oggi=_date_cls(2030, 6, 1))
ok(_fut == "dal 01/01/2030 a oggi", f"«al» nel futuro: a oggi ({_fut})")
try:
    PER.leggi(["Rend", "Uno", "32-13-26"]); ok(False, "data sbagliata accettata")
except PER.Errore as er:
    ok("Non capisco la data «32-13-26»" in str(er), "data scritta male: lo dice invece di cercarla nel nome")
ok(R.immagine(dx)[:4] == b"\x89PNG", "immagine a cavallo")
db.q("DELETE FROM nba_tabellini WHERE partita LIKE 'rd_old%%'"); db.q("DELETE FROM nba_partite WHERE espn_id LIKE 'rd_old%%'")



# carriera: Basketball-Reference, più istantanee, una stagione con due squadre (riga del totale), la stagione in corso dai tabellini
def bref(stagione, nome, team, g, fm_pts, ts):
    db.q("""INSERT INTO bref_stats (timestamp, stagione, nome_bref, team, g, mp, fgm, fga, fg_pct, fg3m, fg3a, fg3_pct, ftm, fta, ft_pct,
              orb, drb, trb, ast, stl, blk, tov, pf, pts) VALUES (%s, %s, %s, %s, %s, 30, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, %s)""",
         (ts, stagione, nome, team, g, fm_pts))
oggi = datetime.now(timezone.utc)
bref("2024", "Rend Uno", "SAC", 40, 20, oggi - timedelta(days=900))
bref("2024", "Rend Uno", "SAC", 60, 30, oggi - timedelta(days=800))        # l'ultima istantanea vale
bref("2025", "Rend Uno", "2TM", 70, 40, oggi - timedelta(days=400))
bref("2025", "Rend Uno", "SAC", 30, 30, oggi - timedelta(days=400))
bref("2025", "Rend Uno", "MIA", 40, 50, oggi - timedelta(days=400))
bref(B1, "Rend Uno", "RDA", 9, 80, oggi)                                   # la stagione in corso di bref: non si usa (tabellini)
dc = R.dati_carriera(gid, "Rend Uno")
st = dc["stagioni"]
ok([x["lbl"] for x in st] == ["23-24", "24-25", f"{(int(S)) % 100:02d}-{(int(S) + 1) % 100:02d}"], f"stagioni in ordine, quella in corso una volta {[x['lbl'] for x in st]}")
ok(st[0]["g"] == 60 and st[0]["fm"] == 15.0, "l'ultima istantanea di Basketball-Reference (fantamedia = pts × 0,5 qui)")
ok(st[1]["g"] == 70 and st[1]["fm"] == 20.0 and st[1]["team"] == ["SAC·MIA"], "cambio di squadra: la riga del totale e le squadre in ordine")
ok(st[2]["in_corso"] and st[2]["g"] == 6 and st[2]["fm_t"] == "29,63" and [f["id"] for f in st[2]["fanta"]] == ["team01", "team02"],
   "stagione in corso dai tabellini (regular season e play-in, come /player), con tutte le squadre del fantabasket in ordine (libero in mezzo no)")
tot = 60 + 70 + 6
ok(dc["media_big"] == R._t((15 * 60 + 20 * 70 + 178 / 6 * 6) / tot) and f"{tot} partite in 3 stagioni" in dc["media_sotto"], "media in carriera pesata sulle partite")
# v7.18.0 (Luca, 18/11): il contratto di ogni stagione sotto la squadra del fantabasket; la media per /player
_fz = {f["id"]: f["contratto"] for f in st[2]["fanta"]}
ok(_fz == {"team01": "", "team02": "7M ×2"}, f"/rendimento_carriera: il contratto della stagione sotto la squadra (chi l'ha tagliato prima della firma no) {_fz}")
# v7.26.0 (Luca, 23/11): le 9 categorie in carriera, pesate sulle partite (bref: medie × partite; in corso: tabellini)
_md = {m["t"]: m["v"] for m in dc["medie"]}
ok(_md["pts"] == f"{(30 * 60 + 40 * 70) / tot:.1f}".replace(".", ",") and _md["FG%"] == "—" and len(dc["medie"]) == 9
   and dc["sotto_medie"].startswith(f"{tot} partite in 3 stagioni · 30,") and "dai tabellini ESPN" in dc["sotto_medie"],
   f"/rendimento_carriera: le 9 categorie in carriera {dc['medie']} {dc['sotto_medie']}")
_n9, _s9 = R.nove_categorie([{"g": 10, "tot": {"fgm": 50.0, "fga": 100.0, "ftm": 9.0, "fta": 10.0, "tpm": 1.0, "tpa": 4.0, "pts": 200.0}},
                             {"g": 30, "tot": {"fgm": 30.0, "fga": 100.0, "ftm": 1.0, "fta": 10.0, "pts": 300.0}}])
_n9 = {m["t"]: m["v"] for m in _n9}
ok(_n9["FG%"] == "40,0" and _n9["FT%"] == "50,0" and _n9["pts"] == "12,5" and "(25,0%)" in _s9 and "Basketball-Reference" in _s9,
   f"9 categorie: percentuali come segnati / tentati della carriera, non media delle percentuali {_n9} {_s9}")
_mc = R.media_carriera(gid, "Rend Uno")
ok(_mc["g"] == tot and _mc["stagioni"] == 3 and R._t(_mc["media"]) == dc["media_big"], f"media in carriera per /player, uguale a /rendimento_carriera {_mc}")
_cid = db.q("SELECT id FROM contratti WHERE giocatore_id = %s", (gid,), one=True)["id"]
db.q("UPDATE contratti SET team_id = 'team03' WHERE id = %s", (_cid,))
db.q("INSERT INTO transazioni (oggetto, tipo, giocatore_id, team_id_da, team_id_a, stagione, contratto_id, timestamp) VALUES ('giocatore', 'traded', %s, 'team02', 'team03', %s, %s, %s)",
     (gid, S, _cid, t0 + timedelta(days=8)))
ok(R.contratto_stagione(gid, "team02", int(S) + 1) == "7M ×2" and R.contratto_stagione(gid, "team03", int(S) + 1) == "7M ×2"
   and R.contratto_stagione(gid, "team01", int(S) + 1) == "" and R.contratto_stagione(gid, "team03", int(S) + 2) == "7M ×1"
   and R.contratto_stagione(gid, "team03", int(S) + 3) == "", "scambiato: lo stesso contratto per chi l'ha ceduto e chi l'ha preso, gli anni scendono")
db.q("DELETE FROM transazioni WHERE giocatore_id = %s AND tipo = 'traded'", (gid,)); db.q("UPDATE contratti SET team_id = 'team02' WHERE id = %s", (_cid,))
png = R.immagine(dc)
if _os.environ.get("REND_PNG"): open(_os.environ["REND_PNG"] + "_carriera.png", "wb").write(png)
ok(png[:4] == b"\x89PNG", "immagine della carriera")

# un giocatore storico: solo in Basketball-Reference, tante stagioni
for k, anno in enumerate(range(2003, 2024)):
    bref(str(anno), "Vecchio Storico", ["CLE", "MIA", "LAL"][k // 8], 70, 60 + k, oggi - timedelta(days=9000 - k * 300))
bref("2012", "Vecchio Storico", "3TM", 70, 70, oggi - timedelta(days=5000))
bref("2012", "Vecchio Storico", "NYK", 20, 70, oggi - timedelta(days=5000))
bref("2012", "Vecchio Storico", "BOS", 20, 70, oggi - timedelta(days=5000))
ok(R.nomi_bref("storico vecchio") == ["Vecchio Storico"] and R.nomi_bref("Vecchio Storico") == ["Vecchio Storico"], "nomi di bref in qualsiasi ordine")
dh = R.dati_carriera(None, "Vecchio Storico")
ok(len(dh["stagioni"]) == 21 and dh["stagioni"][0]["lbl"] == "02-03" and not any(x["fanta"] for x in dh["stagioni"]) and "non è nel bot" in dh["sotto"],
   "giocatore storico: tutte le stagioni, senza fantabasket")
png = R.immagine(dh)
if _os.environ.get("REND_PNG"): open(_os.environ["REND_PNG"] + "_storico.png", "wb").write(png)
ok(png[:4] == b"\x89PNG", "immagine del giocatore storico")

# /top_storica (v7.4.0): la classifica di una stagione passata dalle medie di Basketball-Reference
import top_giocatori as TG
ok(TG.leggi_storica(["2014"], S)[:3] == ("2014", 1, 20) and TG.leggi_storica(["2014-15", "50"], S)[:3] == ("2014", 1, 50)
   and TG.leggi_storica(["14-15", "10", "30"], S)[:3] == ("2014", 10, 30) and TG.leggi_storica(["2009/10"], S)[0] == "2009",
   "anno come nella lega (2014 = 2014-15), anche «2014-15», «14-15», N, DA A")
ok("c'è /top" in TG.leggi_storica([S], S)[3] and TG.leggi_storica([], S)[3].startswith("Uso:"), "stagione in corso: /top; senza anno: l'uso")
bref("2012", "Rend Uno", "SAC", 69, 200, oggi - timedelta(days=5000))       # 2011-12: Vecchio Storico (3TM, 70 G) e Rend Uno
bref("2012", "Rend Poco", "SAC", 20, 300, oggi - timedelta(days=5000))      # 20 partite su 70: sotto il 40%
cl = [x for x in TG.classifica_storica("2011") if x["nome"] in ("Rend Uno", "Vecchio Storico", "Rend Poco")]
ok([x["nome"] for x in cl] == ["Rend Uno", "Vecchio Storico"] and cl[1]["squadra"] == "MIA·NYK·BOS" and cl[1]["partite"] == 70,
   f"classifica: fantamedia, minimo di partite, chi ha cambiato squadra col totale e le squadre {cl}")
tt, _n = TG.testo_storica("2011", 1, 500)
ok("stagione 2011-12" in tt and "Rend Uno 100,00 · 69 G · 30,0′ · SAC" in tt and "Rend Poco" not in tt, "testo\n" + tt[:400])
ok("Nessun dato" in TG.testo_storica("1990", 1, 20)[0], "stagione senza dati")

# i comandi
out = []
class M:
    async def reply_text(s, t, **k): out.append(("testo", t, k.get("reply_markup")))
    async def reply_photo(s, f, **k): out.append(("foto", len(f), None))
u = types.SimpleNamespace(effective_message=M(), effective_user=types.SimpleNamespace(id=101))
asyncio.run(R.cmd_rendimento(u, types.SimpleNamespace(args=["Rend", "Uno"])))
asyncio.run(R.cmd_rendimento_carriera(u, types.SimpleNamespace(args=["Rend", "Uno"])))
asyncio.run(R.cmd_rendimento_carriera(u, types.SimpleNamespace(args=["Vecchio", "Storico"])))
asyncio.run(R.cmd_rendimento(u, types.SimpleNamespace(args=["Vecchio", "Storico"])))
asyncio.run(R.cmd_rendimento_carriera(u, types.SimpleNamespace(args=["Nessunissimo"])))
asyncio.run(R.cmd_rendimento(u, types.SimpleNamespace(args=[])))
# il nome (Luca, 09/11: «Deron Williams» dava i Williams della lega): esatto nel bot, se no Basketball-Reference
bref("2010", "Deron Rendi", "UTA", 76, 80, oggi - timedelta(days=6000))
_n0 = len(out)
asyncio.run(R.cmd_rendimento_carriera(u, types.SimpleNamespace(args=["Deron", "Rendi"])))
asyncio.run(R.cmd_rendimento_carriera(u, types.SimpleNamespace(args=["Rendi", "Deron"])))
asyncio.run(R.cmd_rendimento_carriera(u, types.SimpleNamespace(args=["Rend"])))
ok(out[_n0][0] == "foto" and out[_n0 + 1][0] == "foto", "un nome che è solo in Basketball-Reference: dritto alla carriera, anche al contrario")
bref("2011", "Deron Rendi Jr.", "UTA", 70, 30, oggi - timedelta(days=5000))
ok(R.nomi_bref("'Deron Rendi'") == ["Deron Rendi"] and R.scegli_carriera("'Deron Rendi'")[0][1] == "Deron Rendi"
   and R.scegli_carriera("’Deron Rendi Jr.’")[0][1] == "Deron Rendi Jr." and R.nomi_bref("'Rendi Deron'") == [],
   "v7.25.0: /rendimento_carriera tra apici: solo il nome esatto (il padre, non il Jr.; niente altro ordine)")
_bott = [b.callback_data for r in out[_n0 + 2][2].inline_keyboard for b in r] if out[_n0 + 2][2] else []
ok(out[_n0 + 2][1] == "Quale?" and "rcb:Rend Uno" in _bott and "rcb:Deron Rendi" in _bott, f"nome a metà: i nomi di Basketball-Reference {_bott}")
bref("2000", "Michael Jorrdan", "CHI", 80, 60, oggi - timedelta(days=9500)); bref("2016", "Jorrdan Mikey", "MIL", 40, 20, oggi - timedelta(days=3500))
ok(R.nomi_bref("Micheal Jorrdan") == ["Michael Jorrdan"], f"nome scritto male: il più simile, se nettamente {R.nomi_bref('Micheal Jorrdan')}")
ok(R._gid_da_bref("Rend Uno") == gid and R._gid_da_bref("Deron Rendi") is None, "un nome di bref che è nel bot si ricollega al giocatore")
ok([x[0] for x in out[:3]] == ["foto"] * 3, "/rendimento e /rendimento_carriera (anche di un giocatore storico) mandano l'immagine")
ok(out[3][0] == "testo" and "/rendimento_carriera" in out[3][1], "/rendimento di uno storico: rimanda a /rendimento_carriera")
# meno di 5 partite giocate: niente grafico, troppo pochi dati (Luca, 11/11)
_min = R.MIN_PARTITE
R.MIN_PARTITE = 99
_k = len(out)
asyncio.run(R.cmd_rendimento(u, types.SimpleNamespace(args=["Rend", "Uno"])))
R.MIN_PARTITE = _min
ok(out[_k][0] == "testo" and out[_k][1].startswith("Troppo pochi dati: Rend Uno ha giocato") and "almeno 99" in out[_k][1],
   "/rendimento con troppe poche partite: il messaggio, niente immagine")
_dc = R.dati_carriera(gid, "Rend Uno")
ok(R.TEMPLATE_CARRIERA.endswith("rendimento_carriera.typ") and [r["t"] for r in _dc["riquadri"]] == ["Fantamedia", "Stagioni", "Migliore", "In corso"]
   and _dc["riquadri"][1]["v"] == str(len(_dc["stagioni"])) and _dc["riquadri"][3]["v"] != "—" and _dc["media_val"] > 0,
   f"/rendimento_carriera: il suo template, coi quattro riquadri (v7.6.4) {_dc['riquadri']}")
_dh = R.dati_carriera(None, "Vecchio Storico")
ok(_dh["riquadri"][3]["v"] == "—" and _dh["riquadri"][3]["s"].startswith("non gioca nel "), f"senza stagione in corso: lo dice {_dh['riquadri'][3]}")
ok("nemmeno tra quelli di Basketball-Reference" in out[4][1] and out[5][1].startswith("Uso:"), "nome che non c'è da nessuna parte, uso")
hs = LR.get_handlers()
ok({"rendimento", "rendimento_carriera"} <= {next(iter(h.commands)) for h in hs if hasattr(h, "commands")}, "loucabot: i due comandi")
import re as _re
ok(all(_re.match(R.PATTERN, x) for x in ("rs:12", "rc:3", "rcb:LeBron James")) and not _re.match(R.PATTERN, "pl:3"), "callback dei bottoni")
# /confronto e /confronto_carriera (v7.4.3, Luca 10/11)
from shared import confronto as CF
ok(CF.dividi("Wemby vs Chet") == ("Wemby", "Chet") and CF.dividi("A contro B C") == ("A", "B C") and CF.dividi("A, B") == ("A", "B")
   and CF.dividi("Shai Gilgeous-Alexander - Luka") == ("Shai Gilgeous-Alexander", "Luka") and CF.dividi("solo uno") is None,
   "i due nomi: vs, contro, virgola, trattino staccato (non quello dei nomi)")
gid2 = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES ('Rend Due', 'Rend Due', 'rend due', 'rd2') RETURNING id", one=True)["id"]
for i in range(0, 10, 2):
    db.q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, fp) VALUES (%s, 'rd2', 'Rend Due', 'RDB', TRUE, 25, %s)",
         (f"rd_p{i}", 10 + i))
dcs = CF.dati_stagione(gid, gid2)
ok(dcs["a"]["contratto"]["importo"] and dcs["b"]["contratto"]["testo"] in ("svincolato", "diritti rookie", "")
   and all(0 < x["x"] <= 1 and x["lbl"].split("/")[0] in ("10", "20") for x in dcs["date"]),
   f"/confronto: etichette del contratto e il 10 e il 20 di ogni mese ({dcs['a']['contratto']}, {dcs['b']['contratto']}, {dcs['date']})")
ok(dcs and len(dcs["punti_a"]) == 10 and len(dcs["punti_b"]) == 5 and dcs["punti_a"][0]["x"] == 0 and dcs["punti_a"][-1]["x"] == 1
   and dcs["punti_b"][1]["x"] == dcs["punti_a"][2]["x"], "stagione: punti sulle date, allineati tra i due")
rq = {r["t"]: r for r in dcs["riquadri"]}
tb = {r["t"]: r for r in dcs["tabella"]}
ok(rq["Fantamedia"]["a"] == "29,63" and rq["Fantamedia"]["m"] == "a" and tb["Partite"]["b"] == "4"
   and tb["Play-in e playoff NBA"]["a"] == "39,00 (2)" and rq["Migliore"]["a"] == "45,00" and "Peggiore" in rq,
   f"v7.9.7: riquadri a due valori e tabella col resto, il migliore segnato {dcs['riquadri']} {dcs['tabella']}")
ok(dcs["post_x"] is not None and dcs["fanta"] is None, "play-in e playoff NBA in fondo; senza calendario dei playoff niente fascia")
# v7.28.3 (Luca, 24/11): testa a testa, sera per sera tra quelle in cui hanno giocato tutti e due
_sa = {x["giorno"]: x["fp"] for x in R.dati_stagione(gid)["partite"] if x["fp"] is not None}
_sb = {x["giorno"]: x["fp"] for x in R.dati_stagione(gid2)["partite"] if x["fp"] is not None}
_ins = set(_sa) & set(_sb)
_tt = rq["Testa a testa"]
ok(_ins and _tt["a"] == str(sum(_sa[g] > _sb[g] for g in _ins)) and _tt["b"] == str(sum(_sb[g] > _sa[g] for g in _ins))
   and f"{len(_ins)} insieme" in _tt["s"] and dcs["riquadri"][-1]["t"] == "Testa a testa", f"/confronto: testa a testa {_tt}")
# i nostri playoff: fascia e riquadro, dal calendario dei playoff importato (v7.9.7, Luca 15/11)
db.q("""CREATE TABLE IF NOT EXISTS lega_giornate_playoff (stagione TEXT NOT NULL, numero_p INT NOT NULL, giorni DATE[] NOT NULL,
        dal DATE NOT NULL, al DATE NOT NULL, media_file TEXT[] NOT NULL DEFAULT '{}', importato TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (stagione, numero_p))""")
db.q("DELETE FROM lega_giornate_playoff WHERE stagione = %s", (S,))
from datetime import date as _date
_gg = [_date.fromisoformat(x) for x in sorted({p["giorno"] for p in R.dati_stagione(gid)["partite"]})]
db.q("INSERT INTO lega_giornate_playoff (stagione, numero_p, giorni, dal, al) VALUES (%s, 1, %s, %s, %s)",
     (S, [_gg[3]], _gg[3], _gg[3]))
db.q("INSERT INTO lega_giornate_playoff (stagione, numero_p, giorni, dal, al) VALUES (%s, 2, %s, %s, %s)",
     (S, [_gg[5]], _gg[5], _gg[5]))
dcf = CF.dati_stagione(gid, gid2)
rq2 = {r["t"]: r for r in dcf["riquadri"]}
ok(dcf["fanta"] and dcf["fanta"]["lbl"] == "P1–P2" and 0 < dcf["fanta"]["x0"] < dcf["fanta"]["x1"] < 1 and "Nei nostri playoff" in rq2
   and "Peggiore" not in rq2 and "Peggiore" in {r["t"] for r in dcf["tabella"]}, "nostri playoff: fascia, riquadro, il peggiore in tabella")
drf = R.dati_stagione(gid)
ok(drf["fanta"] and drf["fanta"]["n"] == 2 and drf["riquadri"][3]["t"] == "Nei nostri playoff", "/rendimento: fascia e riquadro dei nostri playoff")
_png_r = R.immagine(drf) if hasattr(R, "immagine") else None
pngf = CF.immagine(dcf)
if _os.environ.get("REND_PNG"):
    open(_os.environ["REND_PNG"] + "_confronto_nostri.png", "wb").write(pngf)
    if _png_r:
        open(_os.environ["REND_PNG"] + "_stagione_nostri.png", "wb").write(_png_r)
ok(pngf[:4] == b"\x89PNG", "immagine coi nostri playoff")
db.q("DELETE FROM lega_giornate_playoff WHERE stagione = %s", (S,))
dcc = CF.dati_carriera((gid, "Rend Uno"), (None, "Vecchio Storico"))
ok(len(dcc["stagioni"]) == 21 and dcc["stagioni"][0]["n"] == "1ª" and [x["sa"] for x in dcc["stagioni"][:4]] == ["11-12", "23-24", "24-25", dc["stagioni"][-1]["lbl"]]
   and dcc["stagioni"][0]["sb"] == "02-03" and dcc["stagioni"][4]["a"] is None and sum(x["pb"] for x in dcc["stagioni"]) == 1,
   "carriera: allineate per stagione di carriera, chi ne ha meno lascia vuoto, una migliore per uno")
png = CF.immagine(dcs); png2 = CF.immagine(dcc)
if _os.environ.get("REND_PNG"):
    open(_os.environ["REND_PNG"] + "_confronto.png", "wb").write(png); open(_os.environ["REND_PNG"] + "_confronto_carriera.png", "wb").write(png2)
ok(png[:4] == b"\x89PNG" and png2[:4] == b"\x89PNG", "le due immagini")
out.clear()
for f, args in ((CF.cmd_confronto, ["Rend", "Uno", "vs", "Rend", "Due"]), (CF.cmd_confronto_carriera, ["Rend", "Uno", "vs", "Vecchio", "Storico"]),
                (CF.cmd_confronto, ["Rend", "vs", "Rend", "Due"]), (CF.cmd_confronto, ["Rend", "Uno", "vs", "Rend", "Uno"]),
                (CF.cmd_confronto, ["Rend", "Uno", "vs", "Vecchio", "Storico"]), (CF.cmd_confronto, ["Rend", "Uno"]),
                (CF.cmd_confronto_carriera, ["Rend", "Uno", "vs", "Nessunissimo"])):
    asyncio.run(f(u, types.SimpleNamespace(args=args)))
ok(out[0][0] == "foto" and out[1][0] == "foto", "/confronto e /confronto_carriera (con uno storico) mandano l'immagine")
_cb = [b.callback_data for r_ in out[2][2].inline_keyboard for b in r_] if out[2][2] else []
ok(out[2][1] == "Quale «Rend» (il primo)?" and _cb and all(c.startswith("cf:0:") for c in _cb) and "stesso giocatore" in out[3][1],
   f"v7.25.0: nome ambiguo nel confronto: i bottoni per il primo; lo stesso due volte {out[2]}")
ok("/confronto_carriera" in out[4][1] and out[5][1].startswith("Uso:") and "nemmeno tra quelli" in out[6][1], "storico in /confronto, un nome solo, nome che non c'è")
# v7.25.0 (Luca, 22/11): tutti e due ambigui, prima il primo poi il secondo sullo stesso messaggio, poi l'immagine
out.clear()
_ctx = types.SimpleNamespace(args=["Rend", "vs", "Rend"], user_data={}, bot_data={})
asyncio.run(CF.cmd_confronto(u, _ctx))
_st = _ctx.user_data["confronto"]
_i0 = next(i for i, (e_, v_) in enumerate(_st["voci"][0]) if e_.startswith("Rend Uno"))
_i1 = next(i for i, (e_, v_) in enumerate(_st["voci"][1]) if e_.startswith("Rend Due"))
_mod = []
class _Q:
    def __init__(s, d): s.data, s.message, s.from_user = d, M(), types.SimpleNamespace(id=101, first_name="Luca")
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): _mod.append((t, k.get("reply_markup")))
asyncio.run(CF.cb_confronto(types.SimpleNamespace(callback_query=_Q(f"cf:0:{_i0}")), _ctx))
_cb1 = [b.callback_data for r_ in _mod[-1][1].inline_keyboard for b in r_] if _mod and _mod[-1][1] else []
ok(_mod and _mod[-1][0] == "Quale «Rend» (il secondo)?" and _cb1 and all(c.startswith("cf:1:") for c in _cb1),
   f"confronto: scelto il primo, i bottoni per il secondo sullo stesso messaggio {_mod[-1:]}")
asyncio.run(CF.cb_confronto(types.SimpleNamespace(callback_query=_Q(f"cf:1:{_i1}")), _ctx))
ok(out and out[-1][0] == "foto" and _mod[-1][0] == "⚖️ ⬇️", f"confronto: scelto anche il secondo, l'immagine {out[-1:]} {_mod[-1:]}")
asyncio.run(CF.cb_confronto(types.SimpleNamespace(callback_query=_Q(f"cf:1:{_i1}")), _ctx))
ok(out[-1][0] == "foto" and len([x for x in out if x[0] == "foto"]) == 1, "confronto: un bottone già usato non rifà l'immagine")
out.clear()
_d1 = (t0 + timedelta(days=4)).strftime("%d-%m-%y")
for f, args in ((R.cmd_rendimento, ["Rend", "Uno", _d1]), (R.cmd_rendimento, ["Rend", "Uno", "3"]),
                (CF.cmd_confronto, ["Rend", "Uno", "vs", "Rend", "Due", "6"]), (CF.cmd_confronto, ["Rend", "Uno", "vs", "Rend", "Due", "4"])):
    asyncio.run(f(u, types.SimpleNamespace(args=args, user_data={})))
ok(out[0][0] == "foto" and "maggiore di 5" in out[1][1] and out[2][0] == "foto" and "maggiore di 5" in out[3][1],
   f"v7.20.2: /rendimento NOME DATA e /confronto A vs B N col periodo; N ≤ 5 rifiutato {[o[:2] for o in out]}")
# v7.20.2: /confronto a cavallo di due stagioni: l'estate tagliata con la banda off-season
_tv = datetime(int(S), 4, 2, 23, 0, tzinfo=timezone.utc)
db.q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES ('rd_oldc', %s, 2, %s, %s, 'RDA', 'RDB', 'STATUS_FINAL')",
     (str(int(S) - 1), _tv.date(), _tv))
db.q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, fp) VALUES ('rd_oldc', 'rd1', 'Rend Uno', 'RDA', TRUE, 30, 22)")
dco = CF.dati_stagione(gid, gid2, None, PER.Periodo(dal=_date_cls(int(S), 1, 1)))
_xa = [p_["x"] for p_ in dco["punti_a"]]
ok(len(dco["offseason"]) == 1 and dco["offseason"][0]["lbl"] == PER.stagione_txt(S) and _xa[0] < dco["offseason"][0]["x0"] < dco["offseason"][0]["x1"] <= _xa[1]
   and dco["titolo"].startswith("Stagioni "), f"/confronto a cavallo: banda off-season tra le due stagioni {dco['offseason']} {_xa[:2]} {dco['titolo']}")
ok(CF.immagine(dco)[:4] == b"\x89PNG", "immagine del confronto a cavallo")
db.q("DELETE FROM nba_tabellini WHERE partita = 'rd_oldc'"); db.q("DELETE FROM nba_partite WHERE espn_id = 'rd_oldc'")
ok({next(iter(h.commands)) for h in LR.get_handlers() if hasattr(h, "commands")} == {"rendimento", "rendimento_carriera", "confronto", "confronto_carriera", "rendimento_situazione"},
   "loucabot: anche /confronto, /confronto_carriera e /rendimento_situazione (v7.20.0)")
pulisci()

# v7.24.2 (Luca, 22/11): i tabellini di prima del bot vanno in archivio all'avvio (i dati partono dalla 2026-27)
db.q("DELETE FROM nba_tabellini WHERE partita IN ('pb1', 'pb2')"); db.q("DELETE FROM nba_partite WHERE espn_id IN ('pb1', 'pb2')")
db.q("CREATE TABLE IF NOT EXISTS nba_tabellini_prima_del_bot (LIKE nba_tabellini INCLUDING DEFAULTS)")
db.q("DELETE FROM nba_tabellini_prima_del_bot WHERE partita IN ('pb1', 'pb2')")
for _pid, _g in (("pb1", date(2026, 1, 1)), ("pb2", date(2026, 10, 25))):
    db.q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES (%s, %s, 2, %s, %s, 'CHA', 'BOS', 'STATUS_FINAL')",
         (_pid, "2025" if _g.year == 2026 and _g.month < 7 else "2026", _g, datetime(_g.year, _g.month, _g.day, 23, tzinfo=timezone.utc)))
    db.q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, fp) VALUES (%s, 'pbx', 'Prima Bot', 'CHA', TRUE, 30, 20)", (_pid,))
_n = db.archivia_prima_del_bot()
ok(_n >= 1 and not db.q("SELECT 1 FROM nba_tabellini WHERE partita = 'pb1'", one=True)
   and db.q("SELECT 1 FROM nba_tabellini_prima_del_bot WHERE partita = 'pb1' AND atleta = 'pbx'", one=True)
   and db.q("SELECT 1 FROM nba_tabellini WHERE partita = 'pb2'", one=True),
   "avvio: i tabellini di prima del bot in archivio, quelli della stagione restano")
ok(db.archivia_prima_del_bot() == 0, "avvio: il secondo giro non sposta niente")
db.q("DELETE FROM nba_tabellini WHERE partita IN ('pb1', 'pb2')"); db.q("DELETE FROM nba_tabellini_prima_del_bot WHERE partita IN ('pb1', 'pb2')")
db.q("DELETE FROM nba_partite WHERE espn_id IN ('pb1', 'pb2')")

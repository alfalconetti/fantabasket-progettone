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
    db.q("DELETE FROM bref_stats WHERE nome_bref LIKE 'Rend %%' OR nome_bref IN ('Vecchio Storico', 'Deron Rendi')")
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
png = R.immagine(d)
if _os.environ.get("REND_PNG"): open(_os.environ["REND_PNG"] + "_stagione.png", "wb").write(png)
ok(png[:4] == b"\x89PNG", "immagine della stagione")

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
ok(st[2]["in_corso"] and st[2]["g"] == 6 and st[2]["fm_t"] == "29,63" and st[2]["fanta"], "stagione in corso dai tabellini (regular season e play-in, come /player), col tondo della squadra")
tot = 60 + 70 + 6
ok(dc["media_big"] == R._t((15 * 60 + 20 * 70 + 178 / 6 * 6) / tot) and f"{tot} partite in 3 stagioni" in dc["media_sotto"], "media in carriera pesata sulle partite")
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
_bott = [b.callback_data for r in out[_n0 + 2][2].inline_keyboard for b in r] if out[_n0 + 2][2] else []
ok(out[_n0 + 2][1] == "Quale?" and "rcb:Rend Uno" in _bott and "rcb:Deron Rendi" in _bott, f"nome a metà: i nomi di Basketball-Reference {_bott}")
ok(R._gid_da_bref("Rend Uno") == gid and R._gid_da_bref("Deron Rendi") is None, "un nome di bref che è nel bot si ricollega al giocatore")
ok([x[0] for x in out[:3]] == ["foto"] * 3, "/rendimento e /rendimento_carriera (anche di un giocatore storico) mandano l'immagine")
ok(out[3][0] == "testo" and "/rendimento_carriera" in out[3][1], "/rendimento di uno storico: rimanda a /rendimento_carriera")
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
ok(dcs and len(dcs["a"]["punti"]) == 10 and len(dcs["b"]["punti"]) == 5 and dcs["a"]["punti"][0]["x"] == 0 and dcs["a"]["punti"][-1]["x"] == 1
   and dcs["b"]["punti"][1]["x"] == dcs["a"]["punti"][2]["x"], "stagione: punti sulle date, allineati tra i due")
rr = {r["voce"]: r for r in dcs["righe"]}
ok(rr["Fantamedia"]["a"] == "29,63" and rr["Fantamedia"]["meglio"] == "a" and rr["Partite"]["b"] == "4" and rr["Playoff"]["a"] == "39,00 (2)"
   and rr["Migliore partita"]["a"] == "45,00", f"tabella: come /player, il migliore segnato {dcs['righe']}")
ok(dcs["post_x"] is not None, "play-in e playoff in fondo")
dcc = CF.dati_carriera((gid, "Rend Uno"), (None, "Vecchio Storico"))
ok(len(dcc["anni"]) == 21 and dcc["anni"][0]["k"] == "1ª" and [x["a"]["lbl"] for x in dcc["anni"][:4]] == ["11-12", "23-24", "24-25", dc["stagioni"][-1]["lbl"]]
   and dcc["anni"][0]["b"]["lbl"] == "02-03" and dcc["anni"][4]["a"] is None, "carriera: allineate per stagione di carriera, chi ne ha meno lascia vuoto")
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
ok("può essere" in out[2][1] and "Rend Due" in out[2][1] and "stesso giocatore" in out[3][1], "nome ambiguo: li elenca; lo stesso due volte")
ok("/confronto_carriera" in out[4][1] and out[5][1].startswith("Uso:") and "nemmeno tra quelli" in out[6][1], "storico in /confronto, un nome solo, nome che non c'è")
ok({next(iter(h.commands)) for h in LR.get_handlers() if hasattr(h, "commands")} == {"rendimento", "rendimento_carriera", "confronto", "confronto_carriera"},
   "loucabot: anche /confronto e /confronto_carriera")
pulisci()

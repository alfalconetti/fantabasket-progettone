import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v6.5.0 (Luca, 23/10): /carriera, due timeline in parallelo dal 25/07/2026 (fantabasket e NBA reale)
e i cambi di squadra NBA salvati da loucabot (nba_movimenti)."""
import asyncio, importlib.util, json, os, types
from datetime import date, datetime, timezone
import database as db
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe RESTART IDENTITY CASCADE")
# tabelle di loucabot (nba_atleti, nba_movimenti) e bref_stats nello stesso database
spec = importlib.util.spec_from_file_location("louca_db", os.path.join(ROOT, "fantabasket-loucabot", "db.py"))
ldb = importlib.util.module_from_spec(spec); spec.loader.exec_module(ldb); ldb.init_db()
db._q("TRUNCATE nba_atleti, nba_movimenti")
db._q(open(os.path.join(ROOT, "fantabasket-main", "bref_schema.sql")).read())
db._q("TRUNCATE bref_stats")

def g(n, espn=None):
    return db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id", (n, n, n.lower(), espn))
def c(gid, t, imp, anni, att=True, tipo="normale"):
    return db._qval("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) "
                    "VALUES (%s, %s, %s, %s, '2026', %s, %s) RETURNING id", (gid, t, imp, anni, tipo, att))
def tx(tipo, gid, da, a, cid, ts, note=None, trade=None, oggetto="giocatore"):
    db._q("INSERT INTO transazioni (tipo, oggetto, giocatore_id, team_id_da, team_id_a, stagione, contratto_id, timestamp, note, trade_id) "
          "VALUES (%s, %s, %s, %s, %s, '2026', %s, %s, %s, %s)", (tipo, oggetto, gid, da, a, cid, ts, note, trade))
def trade():
    return db._qval("INSERT INTO trade (stato, stagione, n_squadre, proposta_da) VALUES ('approvata', '2026', 2, 'team01') RETURNING id")

p = g("Gio Prova", "e1")
c1 = c(p, "team01", 10, 3, att=False)
tx("signed", p, None, "team01", c1, "2026-07-25 22:00+02", "migrazione iniziale")
t1, t2 = trade(), trade()
tx("traded", p, "team01", "team02", c1, "2026-08-10 12:00+02", None, t1)
tx("traded", p, "team02", "team03", c1, "2026-09-01 12:00+02", "TRADE-X", t2)
tx("traded", p, "team03", "team02", c1, "2026-09-01 13:00+02", "ANNULLAMENTO TRADE-X", t2)
tx("cut", p, "team02", None, c1, "2026-09-20 12:00+02")
c2 = c(p, "team04", 3, 1)
tx("signed", p, None, "team04", c2, "2026-09-25 12:00+02", "Firma FA bot aste — Gio Prova 3M x1")
db._q("INSERT INTO dpe (giocatore_id, team_id, stagione, importo_originale, importo_dpe, timestamp) VALUES (%s, 'team04', '2026', 3, 1, '2026-10-05 12:00+02')", (p,))
tx("signed", p, None, "team09", c2, "2026-06-01 12:00+02", "prima del bot: non si vede")
# un rookie coi soli diritti
r = g("Rook Prova")
db._q("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft) VALUES (%s, 'team02', 1, 4, '2026')", (r,))
tx("iniziale", r, None, "team02", None, "2026-07-25 22:00+02", "Situazione all'avvio", oggetto="diritti")

# NBA: al 25/07 a CHA (bref), poi trade a SAC vista da ESPN il 05/02 e da bref il 07/02 (non si ripete)
for ts, team in [("2026-10-22", "CHO"), ("2026-10-23", "CHO"), ("2027-02-07", "SAC"), ("2027-02-08", "SAC")]:
    db._q("INSERT INTO bref_stats (timestamp, stagione, nome_bref, team, g) VALUES (%s, '2027', 'Gio Prova', %s, 1)", (ts, team))
ldb.salva_atleti([{"atleta": "e1", "nome": "Gio Prova", "squadra": "CHA"}], giorno=date(2026, 10, 23))
ldb.salva_atleti([{"atleta": "e1", "nome": "Gio Prova", "squadra": "SAC"}], giorno=date(2027, 2, 5))
mv = db._q("SELECT giorno, da, a FROM nba_movimenti WHERE atleta = 'e1'", many=True)
ok(len(mv) == 1 and mv[0]["da"] == "CHA" and mv[0]["a"] == "SAC" and mv[0]["giorno"] == date(2027, 2, 5),
   f"loucabot: il cambio di squadra dei roster ESPN finisce in nba_movimenti col giorno {mv}")
ldb.salva_atleti([{"atleta": "e1", "nome": "Gio Prova", "squadra": "SAC"}], giorno=date(2027, 2, 6))
ok(db._qval("SELECT COUNT(*) FROM nba_movimenti WHERE atleta = 'e1'") == 1, "stessa squadra: nessun movimento nuovo")

import handlers.carriera as C
f = C.eventi_fanta(p)
et = [(x["etichetta"], x["titolo"]) for x in f]
nomi = {t: C.tm.get_team_by_id(t)["nome"] for t in ("team01", "team02", "team04")}
ok(et == [("All'avvio", nomi["team01"]), ("Trade", nomi["team02"]), ("Taglio", "Free agent"), ("Firma FA", nomi["team04"]), ("DPE", nomi["team04"])],
   f"fantabasket: avvio, trade, (trade annullata sparita), taglio, firma all'asta, DPE; niente prima del 25/07 {et}")
ok("10M × 3" in f[0]["dettaglio"] and "2026-27" in f[0]["dettaglio"] and f"da {nomi['team01']}" in f[1]["dettaglio"]
   and "asta vinta: 3M × 1" in f[3]["dettaglio"] and "pesa 1M invece di 3M" in f[4]["dettaglio"], "dettagli: contratto, da chi, asta, DPE")
fr = C.eventi_fanta(r)
ok(fr and fr[0]["etichetta"] == "Draft" and "Draft 2026, 1° giro #4" in fr[0]["dettaglio"], "rookie coi soli diritti: parte dal draft")
# rookie del draft 2026 già sotto contratto all'avvio: parte dal draft anche lui (Luca, 23/10)
rc = g("Rook Firmato")
db._q("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft) VALUES (%s, 'team03', 1, 9, '2026')", (rc,))
tx("signed", rc, None, "team03", c(rc, "team03", 4, 4, tipo="rookie"), "2026-07-25 22:00+02", "migrazione iniziale")
fc = C.eventi_fanta(rc)
ok(fc and fc[0]["etichetta"] == "Draft" and "Draft 2026, 1° giro #9" in fc[0]["dettaglio"] and "4M × 4 · rookie" in fc[0]["dettaglio"],
   f"rookie del draft 2026 con contratto all'avvio: parte dal draft col contratto {fc[:1]}")
ro = g("Rook Vecchio")
db._q("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft) VALUES (%s, 'team03', 1, 2, '2024')", (ro,))
tx("signed", ro, None, "team03", c(ro, "team03", 8, 4, tipo="rookie"), "2026-07-25 22:00+02", "migrazione iniziale")
ok(C.eventi_fanta(ro)[0]["etichetta"] == "All'avvio", "rookie di un draft precedente: All'avvio (il draft è prima del bot)")
n = C.eventi_nba("e1", "Gio Prova")
ok([(x["etichetta"], x["a"]) for x in n] == [("Al 25/07", "CHA"), ("Cambio squadra", "SAC")] and "Charlotte" in n[1]["dettaglio"],
   f"NBA: Charlotte al 25/07 (sigla di bref CHO → CHA), poi Sacramento una volta sola (ESPN; bref due giorni dopo non si ripete) {[(x['etichetta'], x['a']) for x in n]}")
nb = C.eventi_nba(None, "Gio Prova")
ok([x["a"] for x in nb] == ["CHA", "SAC"] and "Basketball-Reference" in nb[1]["dettaglio"], "senza ESPN: il cambio dalle righe di Basketball-Reference")

d = C.dati(p)
rr = d["righe"]
ok(rr[0]["giorno"] == "25/07" and rr[0]["fanta"] and rr[0]["nba"] and rr[0]["fanta_sq"]["nome"] == nomi["team01"] and rr[0]["nba_sq"]["sigla"] == "CHA",
   "prima riga: il 25/07 da tutte e due le parti")
taglio = next(x for x in rr if x["fanta"] and x["fanta"]["etichetta"] == "Taglio")
ok(taglio["fanta_sq"] is None and taglio["nba_resta"] == "Charlotte Hornets", "da free agent niente barra; dall'altra parte la squadra del momento")
ok(rr[-1]["nba"] and rr[-1]["nba"]["titolo"] == "Sacramento Kings" and rr[-1]["fanta_resta"] == nomi["team04"], "ultima riga: la trade NBA, nel fanta la squadra di adesso")
ok(d["ora"]["fanta"] == nomi["team04"] and d["ora"]["contratto"] == "3M × 1" and d["ora"]["nba"] == "Sacramento Kings"
   and "3 squadre" in d["breve"]["fanta"] and "1 trade" in d["breve"]["fanta"] and "2 squadre · 1 cambio" == d["breve"]["nba"],
   f"testata e riassunto {d['ora']} {d['breve']}")
try:
    import typst
    png = typst.compile(os.path.join(ROOT, "fantabasket-main", "carriera.typ"), root="/", format="png", ppi=72,
                        sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})
    ok(png[:4] == b"\x89PNG", "carriera.typ compila (senza foto: le iniziali; loghi segnaposto)")
    vuoto = C.dati(g("Senza Niente"))
    png = typst.compile(os.path.join(ROOT, "fantabasket-main", "carriera.typ"), root="/", format="png", ppi=72,
                        sys_inputs={"dati": json.dumps(vuoto, ensure_ascii=False, default=str)})
    ok(png[:4] == b"\x89PNG" and vuoto["breve"]["fanta"].startswith("nessun movimento"), "giocatore senza movimenti: compila lo stesso")
except ImportError:
    pass

# comando
out = []
class M:
    async def reply_text(s, t, **k): out.append((t, k))
    async def reply_photo(s, **k): out.append(("FOTO", k))
async def finto(gid): return "/nonesiste.png"
C.genera_png = finto
up = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=101), effective_message=M())
asyncio.run(C.cmd_carriera(up, types.SimpleNamespace(args=[])))
ok("Uso" in out[-1][0], "/carriera senza nome: istruzioni")
asyncio.run(C.cmd_carriera(up, types.SimpleNamespace(args=["prova"])))
k = out[-1][1].get("reply_markup")
ok(k and {b.callback_data for r_ in k.inline_keyboard for b in r_} >= {f"car:{p}", f"car:{r}"}, "nome non esatto: bottoni coi giocatori simili")

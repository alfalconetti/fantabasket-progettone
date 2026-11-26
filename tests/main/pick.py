import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# /pick (v7.3.0, Luca 09/11): di chi è una pick e la sua storia
import asyncio, types
import database as db
import settings
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe RESTART IDENTITY CASCADE")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
import handlers.pick as PK

S = settings.stagione_corrente()
pross = str(int(S) + 1)
# argomenti
ok(PK.leggi_argomenti([], S)[:3] == (None, 1, pross), f"default: la tua squadra, 1° giro, il prossimo draft ({pross})")
ok(PK.leggi_argomenti(["Alfa", "2", "2029"], S)[:3] == ("Alfa", 2, "2029"), "squadra, giro, anno")
ok(PK.leggi_argomenti(["29", "r2", "Beta", "Team"], S)[:3] == ("Beta Team", 2, "2029"), "in qualsiasi ordine, anno corto, «r2», squadra di più parole")
ok(PK.leggi_argomenti(["2°"], S)[:3] == (None, 2, pross), "«2°»")

def pick(orig, att, anno, giro, **k):
    return db._qval("INSERT INTO pick (proprietario_orig, proprietario_att, anno, round, protezioni, scattata, numero_scelta) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id", (orig, att, anno, giro, k.get("prot"), k.get("usata", False), k.get("num")))
def trade(ref, stato="approvata"):
    return db._qval("INSERT INTO trade (trade_ref, stato, stagione, n_squadre, proposta_da) VALUES (%s, %s, '2026', 2, 'team01') RETURNING id", (ref, stato))
def mov(pid, tipo, da, a, ts, tid=None, nota=None):
    db._q("INSERT INTO transazioni (oggetto, tipo, pick_id, team_id_da, team_id_a, stagione, trade_id, note, timestamp) "
          "VALUES ('pick', %s, %s, %s, %s, '2026', %s, %s, %s)", (tipo, pid, da, a, tid, nota, ts))

p1 = pick("team01", "team03", pross, 1, prot='{"top": 3}')
t1, t2 = trade("TRADE-2026-005"), trade("TRADE-2026-009", "annullata")
mov(p1, "iniziale", None, "team01", "2026-07-25 12:00+00", nota="Situazione all'avvio del registro (v3.10.0)")
mov(p1, "traded", "team01", "team02", "2026-09-01 18:00+00", t1, "TRADE-2026-005")
mov(p1, "traded", "team02", "team04", "2026-09-20 18:00+00", t2, "TRADE-2026-009")
mov(p1, "traded", "team04", "team02", "2026-09-21 09:00+00", t2, "ANNULLAMENTO TRADE-2026-009")
t3 = trade("TRADE-2026-012")
mov(p1, "traded", "team02", "team03", "2026-10-02 18:00+00", t3, "TRADE-2026-012")
sc = PK.scheda(db._q("SELECT * FROM pick WHERE id = %s", (p1,), one=True))
righe = sc.split("\n")
st = [r for r in righe if r.startswith("•")]
ok(len(st) == 4, "storia: avvio, tre trade (l'annullamento sulla riga della trade, non a parte)\n" + sc)
ok("all'avvio del bot" in st[0] and "TRADE-2026-005" in st[1] and "TRADE-2026-009" in st[2] and "annullata il 21/09/2026" in st[2]
   and "TRADE-2026-012" in st[3], "storia in ordine, con i numeri delle trade e la trade annullata segnata")
ok("Proprietario:" in sc and "(è ancora sua)" not in sc and "Protezioni: top 3" in sc and "/trova_trade" in sc,
   "proprietario di adesso, protezioni, rimando a /trova_trade")

p2 = pick("team01", "team01", pross, 2)
sc2 = PK.scheda(db._q("SELECT * FROM pick WHERE id = %s", (p2,), one=True))
ok("è ancora sua" in sc2 and "non è mai stata scambiata" in sc2 and "/trova_trade" not in sc2, "pick mai scambiata\n" + sc2)

gu = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES ('Scelto Uno', 'Scelto Uno', 'scelto uno') RETURNING id")
p3 = pick("team02", "team05", "2026", 1, usata=True, num=7)
db._q("INSERT INTO rookie (giocatore_id, team_id, anno_draft, round, pick_numero) VALUES (%s, 'team05', '2026', 1, 7)", (gu,))
sc3 = PK.scheda(db._q("SELECT * FROM pick WHERE id = %s", (p3,), one=True))
ok("Già usata" in sc3 and "#7" in sc3 and "Scelto Uno" in sc3, "pick già usata: numero e giocatore scelto\n" + sc3)

# ── v7.36.0: event sourcing delle pick (com'erano a una data, dal registro) ──
from datetime import datetime as _dt, timezone as _tz
db._q("INSERT INTO trade_items (trade_id, tipo, pick_id, team_id_da, team_id_a, protezione) VALUES (%s, 'pick', %s, 'team01', 'team02', %s)",
      (t1, p1, '{"top": 3}'))
db._q("INSERT INTO trade_items (trade_id, tipo, pick_id, team_id_da, team_id_a) VALUES (%s, 'pick', %s, 'team02', 'team04')", (t2, p1))
al = lambda iso: {p["id"]: p for p in db.pick_al(iso)}
ok(p1 not in al("2026-07-01T00:00:00+00:00"), "prima del primo movimento la pick non c'è")
ok(al("2026-08-01T00:00:00+00:00")[p1]["proprietario_att"] == "team01" and al("2026-08-01T00:00:00+00:00")[p1]["protezioni"] is None,
   "1/8: ancora di team01, senza protezione")
ok(al("2026-09-10T00:00:00+00:00")[p1]["proprietario_att"] == "team02" and al("2026-09-10T00:00:00+00:00")[p1]["protezioni"],
   "10/9: di team02 con la protezione messa nella trade")
ok(al("2026-09-20T20:00:00+00:00")[p1]["proprietario_att"] == "team04" and al("2026-09-22T00:00:00+00:00")[p1]["proprietario_att"] == "team02",
   "la trade poi annullata: di team04 fino all'annullamento, poi di nuovo di team02")
mov(p3, "iniziale", None, "team02", "2026-07-25 12:00+00")
mov(p3, "rookie", "team02", "team05", "2026-08-15 12:00+00")
ok(al("2026-08-01T00:00:00+00:00")[p3]["scattata"] is False and al("2026-08-01T00:00:00+00:00")[p3]["numero_scelta"] is None
   and al("2026-08-20T00:00:00+00:00")[p3]["scattata"] and al("2026-08-20T00:00:00+00:00")[p3]["numero_scelta"] == 7,
   "usata solo dal giorno del draft, col numero")

# il comando (v7.22.0, Luca 22/11): squadra, giro e anno → il dettaglio; il resto sono le immagini
out = []
class M:
    async def reply_text(s, t, **k): out.append(t)
    async def reply_photo(s, p, **k): out.append(("foto", k.get("caption"), p))
import teams as tm
gm = next((x for x in (tm.get_team_by_id("team01") or {}).get("gm_ids", [])), 101)
ok(PK.leggi(["Alfa", "2029"]) == ("Alfa", None, "2029") and PK.leggi([]) == (None, None, None) and PK.leggi(["2", "28"]) == (None, 2, "2028"),
   "argomenti senza default")
async def main():
    m = M()
    upd = lambda uid: types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=m)
    for uid, args in ((gm, []), (999999, ["team01", "2", pross]), (999999, ["team01", "2", "2040"]), (999999, ["Nessunaaaa"]),
                      (999999, []), (999999, ["team01"]), (999999, ["team01", pross]), (999999, ["team01", "1"]), (gm, [pross]),
                      (gm, ["2"]), (999999, [pross]), (gm, ["2", pross])):
        await PK.cmd_pick(upd(uid), types.SimpleNamespace(args=args))
    for args in ([pross], [pross, "2"], ["2040"]):
        await PK.cmd_pick_lega(upd(999999), types.SimpleNamespace(args=args))
    await PK.cmd_pick(upd(999999), types.SimpleNamespace(args=["aiuto"]))
    await PK.cmd_pick_lega(upd(999999), types.SimpleNamespace(args=["Aiuto"]))
asyncio.run(main())
ok(out[0][0] == "foto" and "Le pick di" in out[0][1], "/pick senza argomenti: l'immagine delle pick della tua squadra")
ok(isinstance(out[1], str) and f"Pick {pross} · 2° giro" in out[1], "/pick team01 2 ANNO: il dettaglio con la storia")
ok("Nessuna pick 2040" in out[2] and "Le pick vanno dal" in out[2], "anno senza pick: lo dice, con gli anni che ci sono")
ok("non trovata" in out[3], "squadra che non c'è")
ok(out[4].startswith("Uso:"), "senza squadra e non GM: l'uso")
ok(all(o[0] == "foto" and "Le pick di" in o[1] for o in out[5:10]),
   "/pick SQUADRA, SQUADRA ANNO, SQUADRA GIRO e, da GM, /pick ANNO e /pick GIRO: le pick della squadra (v7.22.2: senza squadra la tua)")
ok(out[10].startswith("Uso:"), "/pick ANNO da chi non è GM: l'uso (tutta la lega è /pick_lega)")
ok(isinstance(out[11], str) and f"Pick {pross} · 2° giro" in out[11] and "Alfa" in out[11],
   "/pick GIRO ANNO da GM = il dettaglio della sua pick")
ok(out[12][0] == "foto" and f"draft {pross}" in out[12][1] and out[13][0] == "foto" and "2° giro" in out[13][1],
   "v7.22.2: /pick_lega ANNO e /pick_lega ANNO GIRO: tutto un draft")
ok("Nessuna pick del draft 2040" in out[14], "/pick_lega ANNO senza pick: lo dice")
ok(out[15].startswith("🎯 <b>/pick</b>") and "/pick_lega 2028" in out[15] and out[16].startswith("🎯 <b>/pick</b>"),
   "/pick aiuto e /pick_lega aiuto: tutti i modi, con una squadra vera negli esempi")
_ds = PK.dati_squadra(tm.get_team_by_id("team03"))
_r = next(r for r in _ds["righe"] if r["anno"] == pross)
ok(_r["giri"][0] and _r["giri"][0][0]["orig"] == "team01" and not _r["giri"][0][0]["propria"] and _r["giri"][0][0]["prot"] == "top 3",
   f"/pick team03: in mano la 1ª {pross} di team01, protetta top 3 {_r}")
_ds1 = PK.dati_squadra(tm.get_team_by_id("team01"), pross)
_r1 = _ds1["righe"][0]
ok(len(_ds1["righe"]) == 1 and [c["a"] for c in _r1["cedute"]] == ["team03"] and _r1["giri"][1][0]["propria"]
   and "in mano: 0 di 1° giro, 1 di 2° giro" in _ds1["titolo"], f"/pick team01 ANNO: le cedute, la sua 2ª, il titolo {_ds1['titolo']}")
ok(PK.dati_squadra(tm.get_team_by_id("team01"), None, 2)["giri"] == [2], "/pick SQUADRA GIRO: solo quel giro")
_pa = PK.palette(tm.get_team_by_id("team01"))
ok(all(k in _pa for k in ("header", "riga1", "riga2", "pick", "t_header", "t_pick")), "i colori della palette della squadra")
_dv = PK.dati_squadra({"id": "team05", "nome": "Squadra Sparita"}, "2026")   # una squadra non più in teams.json
ok(_dv["righe"][0]["giri"][0][0]["usata"] == "#7 · Scelto Uno", f"pick già usata: numero e giocatore {_dv['righe'][0]}")
_da = PK.dati_anno("2026")
ok(any(c["k"] == "usata" and c["usata"] == "#7 · Scelto Uno" for r in _da["righe"] for c in r["celle"]), "/pick 2026: la pick usata")
for _n, _t, _d in (("squadra", PK.TEMPLATE_SQUADRA, PK.dati_squadra(tm.get_team_by_id("team03"))),
                   ("anno", PK.TEMPLATE_ANNO, PK.dati_anno(pross)), ("usata", PK.TEMPLATE_SQUADRA, _dv),
                   ("anno_giro", PK.TEMPLATE_ANNO, PK.dati_anno(pross, 2))):
    _png = PK.immagine(_t, _d)
    if _os.environ.get("PICK_PNG"): open(_os.environ["PICK_PNG"].replace(".png", f"_{_n}.png"), "wb").write(_png)
    ok(_png[:4] == b"\x89PNG", f"immagine {_n}")

# /pick_lega (v7.3.0): tutte le pick in un'immagine, sigle diverse tra loro
ok(PK.sigle([{"id": "a", "nome": "Montecelio Redskins"}, {"id": "b", "nome": "Monterotondo Moose"}, {"id": "c", "nome": "Tibur", "sigla": "tbr"},
             {"id": "d", "nome": "Montecelio Bis"}]) == {"a": "MON", "b": "MOT", "c": "TBR", "d": "MOE"},
   "sigle: prime tre lettere, diverse tra loro, il campo sigla vale prima " + str(PK.sigle([{"id": "a", "nome": "Montecelio Redskins"}, {"id": "b", "nome": "Monterotondo Moose"}, {"id": "d", "nome": "Montecelio Bis"}])))
_sq = tm.get_all_teams()
ok(len(set(PK.sigle(_sq).values())) == len(_sq), f"sigle delle squadre di prova tutte diverse {PK.sigle(_sq)}")
db._q("DELETE FROM transazioni WHERE oggetto = 'pick'"); db._q("DELETE FROM trade_items WHERE pick_id IS NOT NULL"); db._q("DELETE FROM pick")
_anni = [str(int(S) + i) for i in range(1, 4)]
for t in _sq:
    for a in _anni:
        for gg in (1, 2):
            pick(t["id"], t["id"], a, gg)
db._q("UPDATE pick SET proprietario_att = 'team02', protezioni = '{\"top\": 5}' WHERE proprietario_orig = 'team01' AND anno = %s AND round = 1", (_anni[0],))
db._q("UPDATE pick SET proprietario_att = 'team03' WHERE proprietario_orig = 'team01' AND anno = %s AND round = 2", (_anni[1],))
_dl = PK.dati_lega()
_r1 = next(r for r in _dl["righe"] if r["team"] == "team01")
ok(_dl["anni"] == _anni and _r1["celle"][0] == {"k": "altra", "a": "team02", "prot": True} and _r1["celle"][3]["a"] == "team03"
   and _r1["celle"][1] == {"k": "propria", "a": "team01"}, "dati: chi ce l'ha, protetta, propria")
_r2 = next(r for r in _dl["righe"] if r["team"] == "team02")
ok(_r1["mano1"] == 2 and _r1["mano2"] == 2 and _r2["mano1"] == 4 and _r2["mano2"] == 3, "in mano: per giro, sue e di altri")
_png = PK.immagine_lega(_dl)
if _os.environ.get("PICK_PNG"): open(_os.environ["PICK_PNG"], "wb").write(_png)
ok(_png[:4] == b"\x89PNG" and len(_png) > 20000, "immagine Typst")
out.clear()
class MF(M):
    async def reply_photo(s, p, **k): out.append(("foto", k.get("caption")))
asyncio.run(PK.cmd_pick_lega(types.SimpleNamespace(effective_user=types.SimpleNamespace(id=1), effective_message=MF()), types.SimpleNamespace(args=[])))
ok(out and out[0][0] == "foto" and "/pick SQUADRA" in out[0][1], "/pick_lega manda l'immagine")
_al = _dt(2026, 9, 10, 23, 59, tzinfo=_tz.utc)
_pz = db._qval("INSERT INTO pick (proprietario_orig, proprietario_att, anno, round) VALUES ('team01', 'team03', %s, 1) RETURNING id", (pross,))
mov(_pz, "iniziale", None, "team01", "2026-07-25 12:00+00"); mov(_pz, "traded", "team01", "team02", "2026-09-01 18:00+00")
mov(_pz, "traded", "team02", "team03", "2026-10-02 18:00+00")
_ds = PK.dati_squadra(tm.get_team_by_id("team02"), pross, 1, None, _al)
ok(any(c["orig"] == "team01" for r in _ds["righe"] for g in r["giri"] for c in g) and _ds["quando"] == "com'era al 10/09/2026",
   "/pick SQUADRA ANNO DATA: le pick in mano allora (oggi di un'altra), e l'immagine lo dice")
ok(PK.immagine(PK.TEMPLATE_SQUADRA, _ds)[:4] == b"\x89PNG", "immagine a una data")
ok(PK.estrai_data(["Alfa", "2028", "10/09/2026"]) == (["Alfa", "2028"], _al) and PK.estrai_data(["28", "1"])[1] is None,
   "la data si riconosce, l'anno no")
out.clear()
asyncio.run(PK.cmd_pick_lega(types.SimpleNamespace(effective_user=types.SimpleNamespace(id=1), effective_message=MF()),
                             types.SimpleNamespace(args=[pross, "10/09/2026"])))
ok(out and out[0][0] == "foto" and "com'erano al 10/09/2026" in out[0][1], "/pick_lega ANNO DATA: l'immagine di allora")
out.clear()
asyncio.run(PK.cmd_pick_lega(types.SimpleNamespace(effective_user=types.SimpleNamespace(id=1), effective_message=MF()),
                             types.SimpleNamespace(args=["10/09/2099"])))
ok(out and "futuro" in out[0], "data nel futuro: no")

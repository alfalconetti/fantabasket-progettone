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

# il comando
out = []
class M:
    async def reply_text(s, t, **k): out.append(t)
import teams as tm
gm = next((x for x in (tm.get_team_by_id("team01") or {}).get("gm_ids", [])), 101)
async def main():
    m = M()
    upd = lambda uid: types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=m)
    await PK.cmd_pick(upd(gm), types.SimpleNamespace(args=[]))
    await PK.cmd_pick(upd(999999), types.SimpleNamespace(args=["team01", "2"]))
    await PK.cmd_pick(upd(999999), types.SimpleNamespace(args=["team01", "2040"]))
    await PK.cmd_pick(upd(999999), types.SimpleNamespace(args=["Nessunaaaa"]))
    await PK.cmd_pick(upd(999999), types.SimpleNamespace(args=[]))
asyncio.run(main())
ok(out[0].startswith("🎯") and f"Pick {pross} · 1° giro" in out[0], "/pick senza argomenti: la tua 1° giro del prossimo draft")
ok(f"Pick {pross} · 2° giro" in out[1], "/pick team01 2")
ok("Nessuna pick 2040" in out[2] and "Le pick vanno dal" in out[2], "anno senza pick: lo dice, con gli anni che ci sono")
ok("non trovata" in out[3], "squadra che non c'è")
ok(out[4].startswith("Uso:"), "senza squadra e non GM: l'uso")

# /pick_lega (v7.3.0): tutte le pick in un'immagine, sigle diverse tra loro
ok(PK.sigle([{"id": "a", "nome": "Montecelio Redskins"}, {"id": "b", "nome": "Monterotondo Moose"}, {"id": "c", "nome": "Tibur", "sigla": "tbr"},
             {"id": "d", "nome": "Montecelio Bis"}]) == {"a": "MON", "b": "MOT", "c": "TBR", "d": "MOE"},
   "sigle: prime tre lettere, diverse tra loro, il campo sigla vale prima " + str(PK.sigle([{"id": "a", "nome": "Montecelio Redskins"}, {"id": "b", "nome": "Monterotondo Moose"}, {"id": "d", "nome": "Montecelio Bis"}])))
_sq = tm.get_all_teams()
ok(len(set(PK.sigle(_sq).values())) == len(_sq), f"sigle delle squadre di prova tutte diverse {PK.sigle(_sq)}")
db._q("DELETE FROM transazioni WHERE oggetto = 'pick'"); db._q("DELETE FROM pick")
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

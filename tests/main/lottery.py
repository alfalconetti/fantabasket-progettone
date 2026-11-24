import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# v7.27.1 (Luca, 23/11): lottery (algoritmo di Henry, seme drand), sanzioni delle penalità, reveal, ordine del draft
import json, os, tempfile, types, asyncio, hashlib
from datetime import datetime, timedelta, timezone
_d = tempfile.mkdtemp()
_t = json.load(open(os.environ["TEAMS_PATH"]))
_t["teams"] = [{"id": f"team{i:02d}", "nome": f"Squadra {chr(64 + i)}", "gm_nome": f"GM{i}", "gm_ids": [1000 + i]} for i in range(1, 25)]
json.dump(_t, open(f"{_d}/teams.json", "w"))
_g = json.load(open(os.environ["GLOBALS_PATH"]))
_g.update(fase="offseason-break", stagione_corrente="2026", admin_ids=[900], main_channel_id=-1, admin_group_id=-2)
json.dump(_g, open(f"{_d}/globals.json", "w"))
os.environ["TEAMS_PATH"], os.environ["GLOBALS_PATH"] = f"{_d}/teams.json", f"{_d}/globals.json"
def fase(f, st):
    g = json.load(open(f"{_d}/globals.json")); g.update(fase=f, stagione_corrente=st); json.dump(g, open(f"{_d}/globals.json", "w"))

import database as db, settings
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from shared import lottery as LT, lottery_vista as LV
import handlers.lottery as LO

# ── il sorteggio ──
ok(LT.estrai(list("ABCDEFGHIJKL"), "ab" * 32) == LT.estrai(list("ABCDEFGHIJKL"), "ab" * 32)
   and sorted(LT.estrai(list("ABCDEFGHIJKL"), "cd" * 32)) == list("ABCDEFGHIJKL"), "estrazione deterministica dal seme, sempre una permutazione")
_c = [[0] * 12 for _ in range(12)]
for k in range(20000):
    for s_, p_ in enumerate(LT.scegli(LT.uniforme(hashlib.sha256(str(k).encode()).hexdigest()))):
        _c[s_][p_] += 1
_scarto = max(abs(_c[s_][p_] / 20000 - LT.ODDS[s_][p_]) for s_ in range(12) for p_ in range(12))
_imp = all(_c[s_][p_] == 0 for s_ in range(12) for p_ in range(12) if LT.ODDS[s_][p_] == 0)
ok(_scarto < 0.02 and _imp, f"20000 estrazioni: frequenze come la matrice (scarto massimo {_scarto:.4f}), mai una pick impossibile")
ok(LT.scendi(list("ABCDEFGHIJKLMNOP"), {"K": 1}) == list("ABCDEFGHIJLKMNOP"), "−1: scende di una, quella sotto sale")
ok(LT.scendi(list("ABCDEFGHIJKLMNOP"), {"J": 2, "K": 1}) == list("ABCDEFGHILMJKNOP"),
   "due sulla stessa posizione: prima quella che partiva più in alto")
ok(LT.scendi(list("ABCDE"), {"D": 5}) == list("ABCED"), "non oltre l'ultima")
ok(LT.round_al(datetime.fromtimestamp(1000 + 30, tz=timezone.utc), {"genesis_time": 1000, "period": 3}) == 11
   and LT.round_al(datetime.fromtimestamp(1000 + 31, tz=timezone.utc), {"genesis_time": 1000, "period": 3}) == 12, "round drand dall'ora")

# firma BLS (v7.27.3): con chiavi di prova
try:
    from py_ecc.optimized_bls12_381 import G2, multiply
    from py_ecc.bls.hash_to_curve import hash_to_G1
    from py_ecc.bls.point_compression import compress_G1, compress_G2
    _H = hash_to_G1(hashlib.sha256((77).to_bytes(8, "big")).digest(), LT.DST, hashlib.sha256)
    _sig = compress_G1(multiply(_H, 4242)).to_bytes(48, "big").hex()
    _a, _b = compress_G2(multiply(G2, 4242))
    _pk = (_a.to_bytes(48, "big") + _b.to_bytes(48, "big")).hex()
    ok(LT.verifica_firma(77, _sig, _pk) is True and LT.verifica_firma(78, _sig, _pk) is False, "firma BLS: giusta sul suo round, sbagliata su un altro")
except ImportError:
    ok(LT.verifica_firma(77, "00", "00") is None, "senza py_ecc la firma non si verifica (None)")

# ── sanzioni ──
ok(LO.effetti(7, True, True) == {"giu1": 2, "giu2": 2, "cap": 0} and LO.effetti(7, True, False) == {"giu1": 2, "giu2": 0, "cap": 0}
   and LO.effetti(8, False, True) == {"giu1": 0, "giu2": 2, "cap": 2} and LO.effetti(6, False, False) == {"giu1": 0, "giu2": 0, "cap": 2}
   and LO.effetti(2, True, True) == {"giu1": 0, "giu2": 0, "cap": 0}, "regole delle sanzioni")
db._q("DELETE FROM registro_azioni")
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, draft, draft_scelte, "
      "sanzioni, lottery, lega_classifica_finale RESTART IDENTITY CASCADE")
db._q("DELETE FROM penalita")
T = [f"team{i:02d}" for i in range(1, 25)]
for i, t in enumerate(T, 1):          # classifica: team01 la migliore … team24 l'ultima; ai playoff le prime 12
    db._q("INSERT INTO lega_classifica_finale (stagione, team, posto, playoff, w, l) VALUES ('2026', %s, %s, %s, %s, %s)",
          (t, i, i <= 12, 38 - i, i))
    for rnd in (1, 2):
        db._q("INSERT INTO pick (proprietario_orig, proprietario_att, anno, round) VALUES (%s, %s, '2027', %s)", (t, t, rnd))
# penalità 2026: team24 3 (ha le sue pick: −1 e −1), team20 6 senza la sua 2nd (1st −2), team14 4 senza pick (cap −1)
for t, n in (("team24", 3), ("team20", 6), ("team14", 4)):
    for _ in range(n):
        db._q("INSERT INTO penalita (team_id, stagione, motivo, assegnata_da) VALUES (%s, '2026', 'prova', 'admin')", (t,))
db._q("UPDATE pick SET proprietario_att = 'team01' WHERE proprietario_orig = 'team20' AND round = 2")
db._q("UPDATE pick SET proprietario_att = 'team02' WHERE proprietario_orig = 'team14'")
ok(LV.seed_lottery("2026") == T[12:][::-1] and LV.fisse("2026") == T[:12][::-1] and LV.secondo_giro("2026") == T[::-1],
   "seed della lottery dall'ultima, 13ª–24ª e secondo giro in ordine inverso")

inviati = []
class Bot:
    async def send_message(self, chat_id, text, **k):
        inviati.append((chat_id, text, k.get("reply_markup"))); return types.SimpleNamespace(message_id=len(inviati), chat_id=chat_id)
    async def send_photo(self, chat_id, photo, **k):
        inviati.append((chat_id, "FOTO", None))
    async def send_media_group(self, chat_id, media, **k):
        inviati.append((chat_id, "ALLEGATI", [m.media.filename for m in media]))
bot = Bot()
run = asyncio.run
run(LO.passaggio_break(bot))
_s = LO.sanzioni_anno("2027")
ok(_s["team24"] == {"n": 3, "propria1": True, "propria2": True, "giu1": 1, "giu2": 1, "cap": 0}
   and _s["team20"]["giu1"] == 2 and _s["team20"]["giu2"] == 0 and _s["team14"]["cap"] == 1, f"sanzioni dalle penalità {_s}")
ok(any(c == -2 and "Sanzioni per il draft 2027" in tx and kb for c, tx, kb in inviati), "riepilogo agli admin da confermare")
class Q:
    def __init__(s, d, uid=900): s.data, s.from_user, s.t = d, types.SimpleNamespace(id=uid, first_name="Admin"), None
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.t = t
run(LO.cb_sanzioni(types.SimpleNamespace(callback_query=Q("lsz:ok:2026")), types.SimpleNamespace(bot=bot)))
ok(db._qval("SELECT COUNT(*) FROM sanzioni WHERE confermate") == 3 and any(c == -1 and "Sanzioni" in tx for c, tx, _ in inviati),
   "confermate: sul canale")

# ── odds ──
d = LV.dati_odds("2026")
ok(d and d["lottery"][0]["squadra"] == "Squadra X" and d["lottery"][0]["odds"][0] == 14.0 and d["fisse"][0]["pick"] == "13ª"
   and d["fisse"][-1]["squadra"] == "Squadra A", "dati delle odds")
ok(LV.immagine_odds(d)[:4] == b"\x89PNG", "immagine delle odds")
_oggi = [{**r, "posto": r["posto"]} for r in LV.classifica("2026")]
d2 = LV.dati_odds("2026", _oggi, "se finisse oggi · 20 giornate")
ok(d2["quando"] == "se finisse oggi · 20 giornate" and "in corso" in d2["sotto"] and LV.immagine_odds(d2)[:4] == b"\x89PNG",
   "odds «se finisse oggi» (/lottery di loucabot)")
from shared import draft_vista as DV
_pv = DV.provvisorio("2026", _oggi, "20 giornate")
ok(_pv[0]["pick"][0]["lotto"] == "lottery · seed 1" and _pv[0]["pick"][0]["squadra"] == "Squadra X" and _pv[0]["pick"][12]["lotto"] == ""
   and _pv[0]["pick"][12]["scala"].startswith("scala ") and _pv[1]["pick"][0]["n"] == 25 and "soggette alla lottery" in _pv[0]["sotto"],
   "/draft se finisse oggi: le 12 della lottery in ordine di seed, poi 13ª–24ª, secondo giro")
ok(DV.immagine(_pv[0])[:4] == b"\x89PNG", "immagine del draft provvisorio")
open("/tmp/draft_provvisorio.png", "wb").write(DV.immagine(_pv[0]))
_fin = []
async def _foto(p, **k): _fin.append("FOTO")
_m = types.SimpleNamespace(reply_photo=_foto, reply_text=lambda *a, **k: None)
asyncio.run(DV.cmd_draft(types.SimpleNamespace(effective_message=_m), types.SimpleNamespace(args=[]), oggi=lambda: ("2026", _oggi, "20 giornate", True)))
ok(_fin == ["FOTO"], "/draft senza draft: il primo giro se finisse oggi")

# ── la lottery nella fase draft ──
fase("offseason-draft", "2027")
run(LO.promemoria(bot))
ok("lottery_quando" in inviati[-1][1], "fase draft: promemoria agli admin")
LT.info = lambda: {"genesis_time": 1692803367, "period": 3}
risposte = []
class M:
    async def reply_text(s, t, **k): risposte.append(t)
def upd(uid): return types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=M())
quando = (datetime.now(timezone.utc) + timedelta(hours=2)).astimezone(LO.ROMA)
run(LO.cmd_lottery_quando(upd(900), types.SimpleNamespace(bot=bot, args=[f"{quando:%d/%m/%Y}", f"{quando:%H:%M}"])))
r = LO.stato("2027")
ok(r and r["seed"][0] == "team24" and risposte[-1].startswith("✅"), f"lottery fissata {risposte[-1:]}")
ok(any(c == -1 and "Lottery del draft 2027" in tx and r["impronta"] in tx and "lottery_verifica.py estrai --round" in tx
       and LT.link_round(r["round"]) in tx for c, tx, _ in inviati), "annuncio: round, seed, impronta, link al round, come rifarla")
ok(any(c == -1 and tx == "ALLEGATI" and kb == ["lottery.py", "lottery_verifica.py", "LEGGIMI.txt"] for c, tx, kb in inviati),
   "v7.27.3: allegati il codice e le istruzioni")
_lg = LO.leggimi("2027", r)
ok(r["impronta"] in _lg and f"--round {r['round']}" in _lg and "sha256sum lottery.py" in _lg and LT.link_round(r["round"]) in _lg,
   "LEGGIMI: impronta, comando, link, come controllare il codice")
# lo script da solo, coi due file in una cartella qualsiasi
import subprocess, shutil
_dir = tempfile.mkdtemp()
_sh = LT.CARTELLA
for _f in ("lottery.py", "lottery_verifica.py"):
    shutil.copy(os.path.join(_sh, _f), _dir)
_out = subprocess.run([_sys.executable, "lottery_verifica.py", "estrai", "--randomness", "5e" * 32, "--squadre", ",".join(LV.seed_lottery("2026"))],
                      cwd=_dir, capture_output=True, text=True, env={"PATH": os.environ.get("PATH", "")}).stdout
ok(r["impronta"] in _out and "1. " + LT.estrai(LV.seed_lottery("2026"), "5e" * 32)[0] in _out,
   f"lo script allegato funziona da solo, con la stessa impronta {_out[:80]}")
ok(run(LO.passo(bot, quando - timedelta(minutes=1))) is None, "prima dell'ora non succede niente")
LT.randomness = lambda rnd: (_ for _ in ()).throw(LT.LotteryError("non ancora"))
ok(run(LO.passo(bot, quando + timedelta(seconds=5))) == "attesa", "round non ancora uscito: si aspetta")
LT.randomness = lambda rnd: "5e" * 32
t0 = quando + timedelta(seconds=30)
ok(run(LO.passo(bot, t0)) == "estratta", "estratta")
estr = LO.stato("2027")["estratto"]
ok(estr == LT.estrai(LV.seed_lottery("2026"), "5e" * 32), "l'estrazione è quella dello script di verifica")
inviati.clear()
esiti = [run(LO.passo(bot, t0 + timedelta(minutes=k, seconds=1))) for k in range(0, 13)]
ok(esiti[:11] == [f"passo {k}" for k in range(1, 12)] and esiti[11] == "svelata", f"una pick al minuto dalla 12ª alla 1ª {esiti}")
ok(sum(1 for c, tx, _ in inviati if c == -1 and tx.startswith("🎟 <b>Pick")) == 12 and inviati[0][1].startswith("🎟 <b>Pick 12</b>"),
   "12 messaggi sul canale, dalla 12ª")
_t20 = next(tx for c, tx, _ in inviati if "Squadra T</b>" in tx and tx.startswith("🎟"))
ok("scende di 2" in _t20, f"la pick penalizzata lo dice {_t20[:120]}")
g1 = [r["pick_id"] for r in db._q("SELECT pick_id FROM draft_scelte WHERE anno = '2027' AND giro = 1 ORDER BY numero", many=True)]
orig = {r["id"]: r["proprietario_orig"] for r in db._q("SELECT id, proprietario_orig FROM pick", many=True)}
atteso1, _ = LO.ordine_primo_giro("2027", estr)
ok([orig[p] for p in g1] == atteso1 and len(g1) == 24, "ordine del primo giro scritto nel draft")
ok(atteso1.index("team20") == estr.index("team20") + 2 or atteso1.index("team20") >= 11, "team20 scende di 2")
g2 = db._q("SELECT numero, pick_id, penalita FROM draft_scelte WHERE anno = '2027' AND giro = 2 ORDER BY numero", many=True)
ok([orig[r["pick_id"]] for r in g2][:3] == ["team23", "team24", "team22"] and g2[1]["penalita"] == 1 and g2[0]["numero"] == 25,
   f"secondo giro: inverso della classifica, team24 −1 {[orig[r['pick_id']] for r in g2][:3]}")
ok(any(c == -2 and "/set_cap_penalizzato team14 1" in tx for c, tx, _ in inviati), "agli admin il cap da ridurre")
ok(run(LO.passo(bot, t0 + timedelta(hours=1))) is None, "a lottery finita non succede più niente")
p = LO.parziale("2027", estr, 1)
ok(p[:11] == [None] * 11 or p.count(None) == 11, "a metà reveal: le pick non svelate restano ignote")

# v7.28.1 (Luca, 24/11): /draft anche nel principale, dalla classifica di oggi salvata da loucabot; senza anno il
# draft passato fino alla 10ª giornata della stagione dopo
fase("regular-season-fa", "2027")
db._q(LV.TABELLA_OGGI); db._q("DELETE FROM lega_classifica_oggi")
def _oggi_salva(giornate):
    db._q("DELETE FROM lega_classifica_oggi")
    for r in _oggi:
        db._q("INSERT INTO lega_classifica_oggi (stagione, team, posto, playoff, w, l, giornate) VALUES ('2027', %s, %s, %s, %s, %s, %s)",
              (r["team"], r["posto"], r["playoff"], r.get("w", 0), r.get("l", 0), giornate))
_visti = []
_dati, _prov = DV.dati, DV.provvisorio
DV.dati = lambda anno, giro: (_visti.append(f"draft {anno}"), _dati(anno, giro))[1]
DV.provvisorio = lambda st, righe, quando: (_visti.append(f"previsione {int(st) + 1}"), _prov(st, righe, quando))[1]
def _draft(*args):
    asyncio.run(DV.cmd_draft(types.SimpleNamespace(effective_message=_m), types.SimpleNamespace(args=list(args))))
    return _visti[-1] if _visti else None
_oggi_salva(9)
st, rr, q, mat = DV.righe_draft()
ok(st == "2027" and len(rr) == 24 and q == "se finisse oggi · 9 giornate" and not mat, "righe_draft dalla classifica salvata da loucabot")
ok(_draft() == "draft 2027", "con 9 giornate convalidate /draft è ancora il draft passato")
ok(_draft("2028") == "previsione 2028", "/draft 2028: la previsione anche prima")
_oggi_salva(10)
ok(_draft() == "previsione 2028", "dalla 10ª giornata /draft è la previsione del prossimo")
ok(_draft("2027") == "draft 2027", "/draft 2027: sempre il draft passato")
DV.dati, DV.provvisorio = _dati, _prov
db._q("DELETE FROM lega_classifica_oggi")

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# v7.27.0 (Luca, 23/11): protezioni delle pick: «protetta 1-4», solo la propria 1st ceduta la prima volta
import asyncio, types, json
import database as db, teams as tm
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from shared import protezioni as P

ok(P.leggi("1st round pick 2027 by Alfa protetta 1-4") == {"da": 1, "a": 4} and P.leggi("protetto 3") == {"da": 3, "a": 3}
   and P.leggi("Protetta top 5") == {"da": 1, "a": 5} and P.leggi("1st round pick 2027 by Alfa") is None, "grammatica: «protetta 1-4», «protetta 3»")
try:
    P.leggi("protetta 1-30"); _e = False
except P.Errore:
    _e = True
ok(_e, "protezione oltre la 24ª: errore")
ok(P.togli("1st round pick 2027 by Alfa protetta 1-4") == "1st round pick 2027 by Alfa", "togli la protezione dal resto della riga")
ok(P.testo({"da": 1, "a": 4}) == "protetta 1-4" and P.testo('{"da": 2, "a": 2}') == "protetta 2" and P.testo(None) == "", "testo")
ok(P.scatta({"da": 1, "a": 4}, 4) and not P.scatta({"da": 1, "a": 4}, 5) and not P.scatta(None, 1), "scatta sulla posizione dopo le penalità")
_p = {"round": 1, "proprietario_orig": "team01", "proprietario_att": "team01", "protezioni": None, "scattata": False}
ok(P.proteggibile(_p, "team01", False) and not P.proteggibile(_p, "team01", True) and not P.proteggibile({**_p, "round": 2}, "team01", False)
   and not P.proteggibile({**_p, "proprietario_att": "team02"}, "team02", False) and not P.proteggibile({**_p, "protezioni": {"da": 1, "a": 3}}, "team01", False),
   "proteggibile: solo la propria 1st, mai scambiata, senza protezione")

# nel database: bozza, protezione, esecuzione, annullamento
db._q("DELETE FROM registro_azioni")
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni RESTART IDENTITY CASCADE")
for t in ("team01", "team02"):
    for rnd in (1, 2):
        db._q("INSERT INTO pick (proprietario_orig, proprietario_att, anno, round) VALUES (%s, %s, '2027', %s)", (t, t, rnd))
p1 = db._qval("SELECT id FROM pick WHERE proprietario_orig = 'team01' AND round = 1")
p2 = db._qval("SELECT id FROM pick WHERE proprietario_orig = 'team01' AND round = 2")
tid = db.crea_trade_bozza("team01", 2, "2026")
for t in ("team01", "team02"):
    db._q("INSERT INTO trade_squadre (trade_id, team_id, ordine) VALUES (%s, %s, 1)", (tid, t))
i1 = db.aggiungi_item_trade(tid, "pick", "team01", "team02", pick_id=p1)
i2 = db.aggiungi_item_trade(tid, "pick", "team01", "team02", pick_id=p2)
ok([x["pick_id"] for x in db.picks_proteggibili(tid)] == [p1], "bozza: proteggibile solo la 1st")
# builder: i bottoni
import handlers.trade_comune as TCM
class Q:
    def __init__(s, d): s.data, s.from_user, s.t, s.kb = d, types.SimpleNamespace(id=1), None, None
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.t, s.kb = t, k.get("reply_markup")
_gm = tm.get_team_by_id("team01")
_uid = int((_gm.get("gm_ids") or [0])[0]) if _gm else 0
async def go(d):
    q = Q(d); q.from_user = types.SimpleNamespace(id=_uid)
    await TCM.cb_protezioni(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(user_data={}))
    return q
q = asyncio.run(go(f"tprot:l:{tid}"))
ok(q.kb and q.kb.inline_keyboard[0][0].callback_data == f"tprot:p:{i1}", f"builder: elenco delle pick da proteggere {q.t and q.t[:40]}")
q = asyncio.run(go(f"tprot:s:{i1}:4"))
ok(P.testo(db.get_item_trade(i1)["protezione"]) == "protetta 1-4" and "protetta 1-4" in q.kb.inline_keyboard[0][0].text, "builder: «protetta 1-4» sulla bozza")
ok("🛡 protetta 1-4" in TCM._testo_riepilogo(tid), "riepilogo della trade con la protezione")
# v7.28.1 (Luca, 24/11): chi non cede niente compare lo stesso, con «/»; la protezione anche sul canale
_an = TCM._formatta_annuncio_canale(tid)
_n2 = tm.get_team_by_id("team02")["nome"]
ok(f"<b>{_n2} cede:</b>\n/" in _an and "protetta 1-4" in _an, f"annuncio sul canale: «cede: /» e la protezione\n{_an}")
ok("<i>Cede:</i> /" in TCM._testo_riepilogo(tid), "riepilogo: «Cede: /» per chi riceve e basta")
# esecuzione e annullamento
import handlers.trade_esegui as TE
TE._scrivi_trade(tid, "TRADE-PROVA-001", "admin")
ok(P.testo(db._q("SELECT protezioni FROM pick WHERE id = %s", (p1,), one=True)["protezioni"]) == "protetta 1-4"
   and db._q("SELECT protezioni FROM pick WHERE id = %s", (p2,), one=True)["protezioni"] is None, "trade eseguita: la 1st è protetta")
db._q("UPDATE trade SET stato = 'approvata', trade_ref = 'TRADE-PROVA-001' WHERE id = %s", (tid,))
ok(db.pick_scambiata_prima(p1) and not db.picks_proteggibili(tid), "dopo la trade la pick non si protegge più")
TE._scrivi_trade(tid, "TRADE-PROVA-001", "admin", inverti=True)
ok(db._q("SELECT protezioni, proprietario_att FROM pick WHERE id = %s", (p1,), one=True) == {"protezioni": None, "proprietario_att": "team01"},
   "trade annullata: la pick torna e la protezione sparisce")

# import dal testo
from handlers import trade_parser as TP
db._q("TRUNCATE trade, trade_items, trade_squadre, trade_voti, transazioni RESTART IDENTITY CASCADE")
_t1, _t2 = tm.get_team_by_id("team01"), tm.get_team_by_id("team02")
testo = (f"TRADE\n\n{_t1['nome']} cede:\n1st round pick 2027 by {_t1['nome']} protetta 1-5\n\n"
         f"{_t2['nome']} cede:\n2nd round pick 2027 by {_t2['nome']} protetta 1-3\n")
sq, err = TP.parsa_trade(testo, "2026", tm.get_all_teams())
_it = [i for s_ in sq for i in s_.cede]
ok(_it[0].protezione == {"da": 1, "a": 5} and not _it[0].errori, f"import: «protetta 1-5» sulla propria 1st {_it[0].errori}")
ok(_it[1].protezione is None and any("propria 1st" in e for e in _it[1].errori), "import: sulla 2nd la protezione è un errore")
# v7.28.1: chi non cede niente, «/»: niente errori, e l'anteprima lo riscrive così
_sq1, _err1 = TP.parsa_trade(f"TRADE\n\n{_t1['nome']} cede:\n1st round pick 2027 by {_t1['nome']}\n\n{_t2['nome']} cede:\n/\n", "2026", tm.get_all_teams())
ok(not _err1 and len(_sq1) == 2 and not [i for i in _sq1[1].cede] and not any(i.errori for s_ in _sq1 for i in s_.cede),
   f"import: «cede: /» vuol dire niente {_err1}")
ok(f"<b>{_t2['nome']} cede:</b>\n  /" in TP.formatta_trade(_sq1), "anteprima dell'import: «cede: /»")

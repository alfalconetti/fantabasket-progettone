import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# v7.27.0 (Luca, 23/11): il draft a turni: ordine, GM in privato, approvazione degli admin, 1st firmate, 2nd diritti,
# protezioni, annunci, ordine sul canale, tabellone, controllo di cap e slot
import json, os, tempfile, types, asyncio
_d = tempfile.mkdtemp()
_t = json.load(open(os.environ["TEAMS_PATH"]))
_t["teams"] = [{"id": f"team{i:02d}", "nome": f"Squadra {chr(64 + i)}", "gm_nome": f"GM{i}", "gm_ids": [1000 + i]} for i in range(1, 25)]
json.dump(_t, open(f"{_d}/teams.json", "w"))
_g = json.load(open(os.environ["GLOBALS_PATH"]))
_g.update(fase="offseason-draft", stagione_corrente="2027", admin_ids=[900], main_channel_id=-1, admin_group_id=-2)
json.dump(_g, open(f"{_d}/globals.json", "w"))
os.environ["TEAMS_PATH"], os.environ["GLOBALS_PATH"] = f"{_d}/teams.json", f"{_d}/globals.json"

import database as db, settings
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
import handlers.draft as D
from shared import draft_vista as DV

db._q("DELETE FROM messaggi_fissi WHERE chiave LIKE 'draft-%%'")      # l'ordine sul canale: nuovo a ogni prova
db._q("DELETE FROM registro_azioni")
db._q("TRUNCATE giocatori, contratti, pick, rookie, trade, trade_items, trade_squadre, trade_voti, transazioni, draft, draft_scelte RESTART IDENTITY CASCADE")
for i in range(1, 25):
    for rnd in (1, 2):
        db._q("INSERT INTO pick (proprietario_orig, proprietario_att, anno, round) VALUES (%s, %s, '2027', %s)", (f"team{i:02d}",) * 2 + (rnd,))
# la 1st di B ce l'ha A (scambiata, protetta 1-4); la 1st di C ce l'ha D (senza protezione)
db._q("""UPDATE pick SET proprietario_att = 'team01', protezioni = '{"da": 1, "a": 4}' WHERE proprietario_orig = 'team02' AND round = 1""")
db._q("UPDATE pick SET proprietario_att = 'team04' WHERE proprietario_orig = 'team03' AND round = 1")

inviati = []
class Bot:
    async def send_message(self, chat_id, text, **k):
        inviati.append((chat_id, text, k.get("reply_markup"))); return types.SimpleNamespace(message_id=len(inviati), chat_id=chat_id)
    async def edit_message_text(self, chat_id=None, message_id=None, text=None, **k):
        inviati.append(("edit", chat_id, text))
    async def send_photo(self, chat_id, photo, **k):
        inviati.append((chat_id, "FOTO", k.get("caption")))
risposte = []
class M:
    def __init__(s, t=""): s.text = t
    async def reply_text(s, t, **k): risposte.append(t)
    async def reply_photo(s, p, **k): risposte.append("FOTO")
bot = Bot()
def upd(uid, testo=""):
    return types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid, first_name="X"), effective_message=M(testo),
                                 effective_chat=types.SimpleNamespace(id=uid, type="private"))
def ctx(*args):
    return types.SimpleNamespace(bot=bot, args=list(args), user_data={}, bot_data={})
run = asyncio.run

# ordine: primo giro A B C … X (B -1), secondo giro al contrario
ordine1 = "\n".join(f"{i} Squadra {chr(64 + i)}" + (" -1" if i == 13 else "") for i in range(1, 25))
run(D.cmd_draft_ordine(upd(900, "/draft_ordine 1\n" + ordine1), ctx()))
ordine2 = "\n".join(f"Squadra {chr(64 + 25 - i)}" for i in range(1, 25))
run(D.cmd_draft_ordine(upd(900, "/draft_ordine 2\n" + ordine2), ctx()))
n = db._q("SELECT giro, COUNT(*) AS n FROM draft_scelte GROUP BY giro ORDER BY giro", many=True)
ok([x["n"] for x in n] == [24, 24] and "ORDINE SCELTE AL DRAFT 2027" in risposte[-1], f"ordine dei due giri {n}")
t = DV.testo_ordine("2027")
ok("2 | GM2 (protetta 1-4)" in t and "3 | GM4 (via GM3)" in t and "13 | GM13 (-1)" in t and "25 | GM24" in t,
   f"ordine in testo: protezione che scatta, via, penalità {t[:300]}")
run(D.cmd_draft_ordine(upd(900, "/draft_ordine 1\nSquadra A\nSquadra A"), ctx()))
ok("24 righe" in risposte[-1], "ordine: servono 24 righe")

# avvio
inviati.clear()
run(D.cmd_draft_avvia(upd(900), ctx()))
ok(risposte[-1].startswith("▶️") and D.stato("2027") == "in_corso", "avvio nella fase draft")
ok(any(c == -1 and "ORDINE SCELTE" in tx for c, tx, *_ in inviati) and any(c == 1001 and "Tocca a te" in tx for c, tx, *_ in inviati),
   "sul canale l'ordine, al GM della pick 1 il messaggio in privato")
# chi non tocca non sceglie
run(D.cmd_scelgo(upd(1002), ctx("Cam", "Boozer")))
ok(risposte[-1].startswith("Non tocca a te"), "/scelgo di chi non tocca")
run(D.cmd_scelgo(upd(1001), ctx("Cam", "Boozer")))
ok("mandato agli admin" in risposte[-1] and any(c == -2 and "Cam Boozer" in tx and kb for c, tx, kb in [x for x in inviati if len(x) == 3 and x[0] != "edit"]),
   "/scelgo: agli admin coi bottoni")
sid = DV.corrente("2027")["id"]
class Q:
    def __init__(s, d, uid=900): s.data, s.from_user, s.t = d, types.SimpleNamespace(id=uid, first_name="Admin"), None
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.t = t
q = Q(f"drs:ok:{sid}", 1001)
run(D.cb_scelta(types.SimpleNamespace(callback_query=q), ctx()))
ok(q.t is None, "solo gli admin approvano")
q = Q(f"drs:ok:{sid}")
run(D.cb_scelta(types.SimpleNamespace(callback_query=q), ctx()))
ok("Da dove viene" in q.t, "approvato: chiede la provenienza")
inviati.clear()
run(D.cmd_draft_da(upd(900), ctx("Duke")))
g = db._q("SELECT g.id, c.importo, c.anni_originali, c.team_id, c.tipo FROM giocatori g JOIN contratti c ON c.giocatore_id = g.id WHERE g.nome_common = 'Cam Boozer'", one=True)
ok(g and (g["importo"], g["anni_originali"], g["team_id"], g["tipo"]) == (12, 2, "team01", "rookie"), f"1st firmata alla rookie scale (pick 1 → 12x2) {g}")
ok(any(c == -1 and tx.startswith("🏀 Con la prima scelta al draft 2027 <b>GM1</b> seleziona <b>Cam Boozer</b>, da Duke") for c, tx, *_ in inviati if c != "edit"),
   "annuncio sul canale")
ok(any(c == 1001 + 1 and "Tocca a te" in tx and "protetta 1-4" in tx for c, tx, *_ in inviati if c != "edit"),
   "pick 2: la protezione scatta, tocca a B (non ad A che l'aveva)")
# pick 2: B; l'admin chiede un altro nome, poi l'admin sceglie lui
run(D.cmd_scelgo(upd(1002), ctx("AJ", "Dybantza")))
sid = DV.corrente("2027")["id"]
q = Q(f"drs:no:{sid}")
run(D.cb_scelta(types.SimpleNamespace(callback_query=q), ctx()))
ok(DV.corrente("2027")["stato"] == "attesa", "↩️ un altro nome: si torna ad aspettare")
run(D.cmd_draft_scegli(upd(900), ctx("AJ", "Dybantsa")))
run(D.cmd_draft_da(upd(900), ctx("BYU")))
p2 = db._q("SELECT proprietario_att, scattata, numero_scelta FROM pick WHERE proprietario_orig = 'team02' AND round = 1", one=True)
ok(p2 == {"proprietario_att": "team02", "scattata": True, "numero_scelta": 2}, f"protezione scattata: la pick torna a B, usata {p2}")
ok("2 | GM2 (protetta 1-4) - AJ Dybantsa" in DV.testo_ordine("2027"), "ordine: la scelta fatta con la protezione")
# pick 3: D via C; nome già in anagrafica
gid_x = db._qval("INSERT INTO giocatori (nome_common, nome_norm, nome_bref) VALUES ('Vecchio Nome', 'vecchio nome', 'Vecchio Nome') RETURNING id")
run(D.cmd_scelgo(upd(1004), ctx("Vecchio", "Nome")))
ok(any(c == -2 and "c'è già" in tx for c, tx, *_ in inviati if c != "edit"), "nome già nell'anagrafica: lo dice agli admin")
run(D.cmd_draft_nome(upd(900), ctx("Vecchio", "Nome")))
q = Q(f"drs:ok:{DV.corrente('2027')['id']}")
run(D.cb_scelta(types.SimpleNamespace(callback_query=q), ctx()))
inviati.clear()
run(D.cmd_draft_da(upd(900), ctx("Real", "Madrid")))
ok(db._q("SELECT giocatore_id, squadra, via FROM draft_scelte WHERE numero = 3", one=True) == {"giocatore_id": gid_x, "squadra": "team04", "via": "team03"},
   "pick 3: sceglie chi l'ha in mano (via C), usa l'anagrafica che c'è")
ok(any(c == -1 and "GM4</b> (via GM3) seleziona" in tx for c, tx, *_ in inviati if c != "edit"), "annuncio con «via»")
# il resto del primo giro (veloce: l'admin sceglie per tutti) → tabellone a fine giro
for k in range(4, 25):
    run(D.cmd_draft_scegli(upd(900), ctx(f"Rookie {k}")))
    if k == 24:
        inviati.clear()
    run(D.cmd_draft_da(upd(900), ctx("Nowhere")))
ok(any(c == -1 and tx == "FOTO" for c, tx, *_ in inviati if c != "edit"), "fine del primo giro: il tabellone sul canale")
ok(db._q("SELECT importo FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id WHERE g.nome_common = 'Rookie 24'", one=True)["importo"] == 3,
   "pick 24: 3x2")
# secondo giro: diritti
run(D.cmd_draft_scegli(upd(900), ctx("Secondo", "Giro")))
run(D.cmd_draft_da(upd(900), ctx("Gonzaga")))
r = db._q("SELECT r.round, r.firmato, r.team_id, r.pick_numero FROM rookie r JOIN giocatori g ON g.id = r.giocatore_id WHERE g.nome_common = 'Secondo Giro'", one=True)
ok(r == {"round": 2, "firmato": False, "team_id": "team24", "pick_numero": 25}
   and not db._q("SELECT 1 FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id WHERE g.nome_common = 'Secondo Giro'", one=True),
   f"2nd: diritti, nessun contratto {r}")
ok(any(c == -1 and "Con la 25ª scelta al draft 2027" in tx for c, tx, *_ in inviati if c != "edit"), "dal secondo giro «la 25ª scelta»")
# v7.36.0: il rookie è legato alla pick con cui è stato scelto (rookie.pick_id), anche al primo giro
_pl = db._q("""SELECT r.pick_id, p.anno, p.round, p.numero_scelta, p.scattata FROM rookie r JOIN giocatori g ON g.id = r.giocatore_id
               JOIN pick p ON p.id = r.pick_id WHERE g.nome_common IN ('Secondo Giro', 'Rookie 24') ORDER BY p.round""", many=True)
ok([(x["round"], x["numero_scelta"], x["scattata"]) for x in _pl] == [(1, 24, True), (2, 25, True)],
   f"rookie.pick_id: la pick usata, al primo e al secondo giro {_pl}")
import handlers.pick as _PK
ok(_PK._scelto(db._q("SELECT * FROM pick WHERE id = %s", (_pl[1]["pick_id"],), one=True))["nome_common"] == "Secondo Giro",
   "/pick: chi è stato scelto con la pick, dal legame")
ok(not db._q("SELECT 1 FROM information_schema.columns WHERE table_name = 'rookie' AND column_name = 'scadenza_diritti'", one=True),
   "rookie.scadenza_diritti tolta")
# pausa e ripresa, correzione
run(D.cmd_draft_pausa(upd(900), ctx()))
run(D.cmd_scelgo(upd(1023), ctx("Tizio")))
ok(D.stato("2027") == "pausa" and risposte[-1] == "Il draft non è in corso.", "in pausa non si sceglie")
run(D.cmd_draft_riprendi(upd(900), ctx()))
run(D.cmd_draft_correggi(upd(900), ctx("25", "Secondo", "Giro", "Jr.")))
ok("Secondo Giro Jr." in DV.testo_ordine("2027"), "correzione di una scelta fatta")
# tabellone e /draft
d1 = DV.dati("2027", 1)
ok(d1["pick"][1]["prot"] == "protetta 1-4" and d1["pick"][2]["via"] == "Squadra C" and d1["pick"][12]["sanz"] == "−1 penalità"
   and d1["pick"][0]["scala"] == "firmato 12M ×2" and d1["ora"] is None, "dati del tabellone del primo giro")
ok(DV.immagine(d1)[:4] == b"\x89PNG" and DV.immagine(DV.dati("2027", 2))[:4] == b"\x89PNG", "l'immagine di tutti e due i giri")
risposte.clear()
run(DV.cmd_draft(upd(1001), ctx()))
ok(risposte == ["FOTO"], "/draft: il primo giro")
risposte.clear()
run(DV.cmd_draft(upd(1001), ctx("2027", "2")))
ok(risposte == ["FOTO"] and DV.leggi_args(["2"]) == (None, 2) and DV.leggi_args(["2027"]) == ("2027", 1) and DV.leggi_args([]) == (None, 1),
   "/draft 2 il secondo giro, /draft ANNO [GIRO]")
run(DV.cmd_draft(upd(1001), ctx("2019")))
ok("Nessun draft 2019" in risposte[-1], "/draft di un anno che non c'è")
# controllo di cap e slot (con 2 1st in mano A sfora gli slot pieni)
ok(isinstance(D.controllo_cap("2027"), list) and D.testo_controllo("2027").startswith(("✅", "⚠️")), "controllo cap e slot")
ok(DV.scelta_testo(1) == "la prima scelta" and DV.scelta_testo(24) == "la ventiquattresima scelta" and DV.scelta_testo(48) == "la 48ª scelta",
   "le scelte in parole")
# v7.36.0: i rookie di prima si legano alla pick usata con lo stesso anno, giro e numero (migrazione all'avvio)
_pv = db._qval("INSERT INTO pick (proprietario_orig, proprietario_att, anno, round, scattata, numero_scelta) "
               "VALUES ('team01', 'team02', '2020', 1, TRUE, 7) RETURNING id")
_gv = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES ('Vecchio Rookie', 'Vecchio Rookie', 'vecchio rookie') RETURNING id")
db._q("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft, firmato) VALUES (%s, 'team02', 1, 7, '2020', TRUE)", (_gv,))
db.migrate_db()
ok(db._qval("SELECT pick_id FROM rookie WHERE giocatore_id = %s", (_gv,)) == _pv, "rookie di prima legato alla sua pick alla migrazione")

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v5.8.0: /settings per argomenti coi bottoni, anteprima e conferma, canale log e principale; i numeri
del regolamento (anche quelli che mancano nel file, al default) e i pesi dei fantapunti uno per uno."""
import asyncio, json, os, types
import database as db, settings
from shared import regole
from handlers import impostazioni as I, admin_panel as AP
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
glob = settings.load_globals()
CANALE, LOG = -100, -300
settings.load_globals = lambda: {**glob, "main_channel_id": CANALE, "log_channel_id_main": LOG}
ADMIN = int(settings.admin_ids()[0])
GM = 999999
P = settings.SETTINGS_PATH
originale = open(P).read()


class Bot:
    def __init__(s): s.mandati = []
    async def send_message(s, chat_id, text, **k): s.mandati.append({"chat_id": chat_id, "text": text})
BOT = Bot()
class Q:
    def __init__(s, data, uid): s.data, s.from_user, s.testi, s.risposte = data, types.SimpleNamespace(id=uid, first_name="Luca", username=None), [], []
    async def answer(s, t=None, **k): s.risposte.append(t)
    async def edit_message_text(s, t, **k): s.testi.append((t, k))
class Msg:
    def __init__(s, t=""): s.text, s.risposte = t, []
    async def reply_text(s, t, **k): s.risposte.append((t, k))
CTX = types.SimpleNamespace(bot=BOT, user_data={}, args=[])
def upd(uid, q=None, msg=None):
    return types.SimpleNamespace(callback_query=q, effective_message=msg,
                                 effective_user=types.SimpleNamespace(id=uid, first_name="Luca", username=None))
def premi(data, uid=ADMIN):
    q = Q(data, uid); asyncio.run(I.cb_settings(upd(uid, q), CTX)); return q
def comando(*args, uid=ADMIN):
    m = Msg(); CTX.args = list(args); asyncio.run(I.cmd_settings(upd(uid, msg=m), CTX)); return m
bottoni = lambda kb: [b.callback_data for r in kb.inline_keyboard for b in r]

# solo admin, nel pannello admin
ok(not comando(uid=GM).risposte and premi("set:home", GM).risposte == ["⛔ Solo admin."], "solo gli admin")
ok("set:home" in bottoni(AP._kb_admin_home()), "«⚙️ Impostazioni» nel pannello admin")

# argomenti e voci: tutte le chiavi del file sono raggiungibili
m = comando()
kb = m.risposte[0][1]["reply_markup"]
ok("Impostazioni" in m.risposte[0][0] and {"set:g:cap", "set:g:fp", "set:g:partita", "set:g:tabelle"} <= set(bottoni(kb)),
   "/settings: argomenti coi bottoni")
nel_file = set(json.load(open(P)))
coperte = {v[1].split(".")[0] for v in I.voci()} | set(I.TABELLE)
ok(nel_file <= coperte and set(regole.DEFAULT) <= coperte, f"tutte le chiavi del file e del regolamento hanno una voce {sorted(nel_file - coperte) or ''}")
t = premi("set:g:partita").testi[-1][0]
ok("Bonus casa: <b>3 punti</b> <i>(default)</i>" in t, "chiave che manca nel file: valore di default, segnato")
t = premi("set:g:fp").testi[-1][0]
ok("Rimbalzo difensivo: <b>1,25</b>" in t and "/dev_ricalcola_fp" in t, "pesi dei fantapunti uno per uno, con la nota sul ricalcolo")
t = premi("set:g:tabelle").testi[-1][0]
ok("Rookie scale" in t and "fascia 1" in t, "tabelle in sola lettura")

# cambio coi bottoni: voce → valore → anteprima → conferma
i = next(n for n, v in enumerate(I.voci()) if v[1] == "bonus_casa")
q = Q(f"set:k:{i}", ADMIN)
st = asyncio.run(I.cb_voce(upd(ADMIN, q), CTX))
ok(st == I.VALORE and "Scrivi il nuovo valore" in q.testi[-1][0] and "Tra 0 e 50" in q.testi[-1][0], "voce scelta: chiede il valore coi limiti")
m = Msg("cento")
ok(asyncio.run(I.msg_valore(upd(ADMIN, msg=m), CTX)) == I.VALORE and "numero" in m.risposte[-1][0], "valore non numerico: lo richiede")
m = Msg("80")
ok(asyncio.run(I.msg_valore(upd(ADMIN, msg=m), CTX)) == I.VALORE and "tra 0 e 50" in m.risposte[-1][0], "fuori dai limiti: lo richiede")
m = Msg("4,5")
asyncio.run(I.msg_valore(upd(ADMIN, msg=m), CTX))
ok("3 punti (default) → <b>4,5 punti</b>" in m.risposte[-1][0], "anteprima: vecchio → nuovo, con la virgola")
ok(regole.bonus_casa() == 3 and "bonus_casa" not in json.load(open(P)), "niente scritto prima della conferma")
q = premi("set:ok")
ok(json.load(open(P))["bonus_casa"] == 4.5 and regole.bonus_casa() == 4.5, "confermato: scritto nel file e letto subito dai bot")
can = [x for x in BOT.mandati if x["chat_id"] == CANALE]
log = [x for x in BOT.mandati if x["chat_id"] == LOG]
ok(len(can) == 1 and "Bonus casa: 3 punti → <b>4,5 punti</b>" in can[0]["text"] and log and "admin Luca" in log[0]["text"],
   "sul canale principale e sul canale log (con chi l'ha cambiata)")
ok(premi("set:ok").testi[-1][0].startswith("Niente da confermare") and len(BOT.mandati) == 2, "doppio tocco su Conferma: una sola modifica")
ok(json.load(open(P))["cap_regular"] == 150 and "rookie_scale" in json.load(open(P)), "le altre chiavi restano")

# scorciatoia /settings chiave valore, sempre con conferma
m = comando("cap_regular", "155")
ok("150 M → <b>155 M</b>" in m.risposte[-1][0] and json.load(open(P))["cap_regular"] == 150, "/settings chiave valore: anteprima")
premi("set:no")
ok(json.load(open(P))["cap_regular"] == 150 and len(BOT.mandati) == 2, "annullata: niente cambia")
ok("non trovata" in comando("bonus", "3").risposte[-1][0] and "bonus_casa" in comando("bonus", "3").risposte[-1][0],
   "chiave sbagliata: suggerisce le simili")
ok("intero" in comando("roster_max", "15,5").risposte[-1][0], "intero richiesto")
ok("numero vero" in comando("bonus_casa", "inf").risposte[-1][0] and "numero" in comando("bonus_casa", "nan").risposte[-1][0],
   "inf e nan rifiutati")
mg = Msg(); CTX.args = []
asyncio.run(I.cmd_settings(types.SimpleNamespace(callback_query=None, effective_message=mg, effective_chat=types.SimpleNamespace(type="supergroup"),
                                                 effective_user=types.SimpleNamespace(id=ADMIN, first_name="Luca", username=None)), CTX))
ok("in privato" in mg.risposte[-1][0], "nei gruppi no: si usa in privato")
os.chmod(P, 0o640)
comando("salary_floor", "116"); premi("set:ok")
ok(oct(os.stat(P).st_mode & 0o777) == "0o640" and json.load(open(P))["salary_floor"] == 116 and not os.path.exists(P + ".tmp"),
   "file riscritto con gli stessi permessi, niente file temporanei")

# un peso dei fantapunti: il trigger di basketball-reference si aggiorna subito
comando("pesi_fantapunti.pts", "1"); premi("set:ok")
d = json.load(open(P))
ok(d["pesi_fantapunti"]["pts"] == 1 and d["pesi_fantapunti"]["ast"] == 2 and regole.pesi_fantapunti()["pts"] == 1,
   "peso dei fantapunti: cambia solo quello")
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Prova Settings'")
db._q("INSERT INTO bref_stats (stagione, nome_bref, pts, ast, orb, drb, fg3m, fga, fgm, fta, ftm, stl, blk, tov) "
      "VALUES ('2099', 'Prova Settings', 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)")
ok(float(db._qval("SELECT fantamedia FROM bref_stats WHERE nome_bref = 'Prova Settings'")) == 10,
   "basketball-reference coi pesi nuovi subito (10 punti × 1)")
ok("/dev_ricalcola_fp" in [x for x in BOT.mandati if x["chat_id"] == LOG][-1]["text"], "il log ricorda /dev_ricalcola_fp")
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Prova Settings'")

open(P, "w").write(originale)
regole.allinea_bref(db._q)

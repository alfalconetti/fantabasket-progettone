import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v6.2.0 (Luca, 23/10): i ruoli dei giocatori arrivati con una trade in un messaggio unico sul canale
principale, che si aggiorna a ogni dichiarazione; dentro anche quelli assegnati in automatico (una sola
posizione eleggibile) e quelli estratti allo scadere delle 48 ore. Le firme restano un annuncio a sé."""
import asyncio, json, os, types
import database as db, settings
from handlers import ruoli_rs as RS
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
P = os.environ["GLOBALS_PATH"]
g = json.load(open(P)); g["fase"] = "regular-season-fa"; g["main_channel_id"] = -1; json.dump(g, open(P, "w"))
db._q("DELETE FROM ruoli_messaggi"); db._q("DELETE FROM ruoli_pendenti")
def gioc(n, pos, team):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    db._q("INSERT INTO posizioni_eleggibili (giocatore_id, posizioni, fonte) VALUES (%s,%s,'prova')", (gid, pos))
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                 "VALUES (%s,%s,1,2,'2026','normale') RETURNING id", (gid, team))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,'2026',%s)", (gid, team, c))
    return gid
due = gioc("Trade Due Pos", "SG,SF", "team01")
uno = gioc("Trade Un Pos", "C", "team01")
tre = gioc("Trade Altro", "PG,SG", "team02")
canale, gm = [], []
class Bot:
    n = 500
    async def send_message(s, chat_id, text, **k):
        Bot.n += 1
        (canale if chat_id == -1 else gm).append({"chat_id": chat_id, "text": text, "id": Bot.n, **k})
        return types.SimpleNamespace(message_id=Bot.n)
    async def edit_message_text(s, chat_id=None, message_id=None, text="", **k):
        canale.append({"chat_id": chat_id, "id": message_id, "text": text, "modifica": True})
B = Bot()
REF = "TRADE-2026-901"
RS._sync_roster = lambda: None
asyncio.run(RS.apri_pendenti(B, "team01", [due, uno], "trade", REF))
asyncio.run(RS.apri_pendenti(B, "team02", [tre], "trade", REF))
nuovi = [x for x in canale if not x.get("modifica")]
ok(len(nuovi) == 1 and "Ruoli dopo la trade TRADE-2026-901" in canale[-1]["text"], "un solo messaggio sul canale per la trade (le due squadre insieme)")
t = canale[-1]["text"]
ok("Trade Un Pos → <b>C</b> <i>(unica posizione eleggibile)</i>" in t and "Trade Due Pos → ⏳ da dichiarare" in t
   and "Trade Altro → ⏳" in t, "dentro l'assegnato in automatico e quelli da dichiarare\n" + t)
pid = db._qval("SELECT id FROM ruoli_pendenti WHERE giocatore_id = %s AND stato = 'aperta'", (due,))
class Q:
    def __init__(s, data, uid): s.data, s.from_user, s.testi = data, types.SimpleNamespace(id=uid, first_name="G", username=None), []
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.testi.append(t)
import teams as tm
tm_vero = tm.get_team_by_gm
tm.get_team_by_gm = lambda uid: tm.get_team_by_id("team01") if uid == 101 else None
asyncio.run(RS.cb_dichiara(types.SimpleNamespace(callback_query=Q(f"rp:{pid}:SF", 101)), types.SimpleNamespace(bot=B)))
tm.get_team_by_gm = tm_vero
t = canale[-1]["text"]
ok(canale[-1].get("modifica") and canale[-1]["id"] == nuovi[0]["id"] and "Trade Due Pos → <b>SF</b> <i>(dichiarato dal GM)</i>" in t,
   "la dichiarazione del GM aggiorna lo stesso messaggio (niente annuncio nuovo)")
db._q("UPDATE ruoli_pendenti SET scadenza = NOW() - INTERVAL '1 minute' WHERE giocatore_id = %s AND stato = 'aperta'", (tre,))
asyncio.run(RS.job_scadenze(types.SimpleNamespace(bot=B)))
t = canale[-1]["text"]
ok(canale[-1].get("modifica") and "Trade Altro → <b>" in t and "🎲" in t and "Tutti i ruoli sono ufficiali" in t
   and len([x for x in canale if not x.get("modifica")]) == 1, "l'estratto allo scadere finisce nello stesso messaggio, poi «tutti ufficiali»\n" + t)
# una firma: annuncio a sé come prima
canale.clear()
f = gioc("Firma Libera", "PG,SG", "team03")
asyncio.run(RS.apri_pendenti(B, "team03", [f], "firma"))
ok(not canale and db._qval("SELECT count(*) FROM ruoli_messaggi") == 1, "firma: niente messaggio di trade (il GM riceve i bottoni come prima)")
# pulizia
ids = [due, uno, tre, f]
db._q("DELETE FROM ruoli_pendenti WHERE giocatore_id = ANY(%s)", (ids,)); db._q("DELETE FROM ruoli_messaggi")
db._q("DELETE FROM cambi_ruolo WHERE giocatore_id = ANY(%s)", (ids,))
db._q("DELETE FROM transazioni WHERE giocatore_id = ANY(%s)", (ids,)); db._q("DELETE FROM contratti WHERE giocatore_id = ANY(%s)", (ids,))
db._q("DELETE FROM posizioni_eleggibili WHERE giocatore_id = ANY(%s)", (ids,)); db._q("DELETE FROM giocatori WHERE id = ANY(%s)", (ids,))
_ = settings

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# v7.3.0 (Luca, 09/11): /player, /status e /calendario anche nel bot principale, col codice di loucabot in shared/.
# Gira dopo le prove di loucabot (le tabelle nba_* e lega_* le crea lui): i suoi dati in giornate 90-92 e atleti «lc*».
import asyncio, types
from datetime import date, datetime, timedelta, timezone
import database as db
import settings
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from shared import lettura as L
import handlers.lega as LG
import comandi

S = settings.stagione_corrente()
# pulizia di prove vecchie
db._q("DELETE FROM nba_infortuni WHERE atleta LIKE 'lc%%'"); db._q("DELETE FROM nba_tabellini WHERE atleta LIKE 'lc%%'")
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'lc%%'"); db._q("DELETE FROM nba_atleti WHERE atleta LIKE 'lc%%'")
db._q("DELETE FROM lega_partite WHERE stagione = %s AND giornata >= 90", (S,)); db._q("DELETE FROM lega_giornate WHERE stagione = %s AND numero >= 90", (S,))
for _n in ("Lega Uno", "Lega Due"):
    _g = db._qval("SELECT id FROM giocatori WHERE nome_common = %s", (_n,))
    if _g:
        db._q("DELETE FROM transazioni WHERE giocatore_id = %s", (_g,)); db._q("DELETE FROM contratti WHERE giocatore_id = %s", (_g,))
        db._q("DELETE FROM giocatori WHERE id = %s", (_g,))

# il database di shared è quello del bot principale
ok(L.q("SELECT 1 AS x", one=True)["x"] == 1, "shared.lettura usa il database del bot principale")

g1 = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES ('Lega Uno', 'Lega Uno', 'lega uno', 'lc1') RETURNING id")
g2 = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES ('Lega Due', 'Lega Due', 'lega due', 'lc2') RETURNING id")
for gid in (g1, g2):
    db._q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) VALUES (%s, 'team01', 5, 2, %s, 'normale', TRUE)", (gid, S))
db._q("INSERT INTO nba_atleti (atleta, nome, squadra) VALUES ('lc1', 'Lega Uno', 'LCA'), ('lc2', 'Lega Due', 'LCA')")
ora = datetime.now(timezone.utc)
db._q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES "
      "('lc_p1', %s, 2, %s, %s, 'LCA', 'LCB', 'STATUS_FINAL'), ('lc_p2', %s, 2, %s, %s, 'LCB', 'LCA', 'STATUS_SCHEDULED')",
      (S, (ora - timedelta(days=2)).date(), ora - timedelta(days=2), S, (ora + timedelta(days=1)).date(), ora + timedelta(days=1)))
db._q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, pts, fp) VALUES ('lc_p1', 'lc1', 'Lega Uno', 'LCA', TRUE, 30, 20, 31.5)")
db._q("INSERT INTO nba_infortuni (giorno, atleta, nome, squadra, stato, dettaglio, preso) VALUES (%s, 'lc2', 'Lega Due', 'LCA', 'Out', 'Caviglia', %s)",
      (ora.date(), ora + timedelta(days=3650)))       # lo snapshot più recente di tutti

# /player: la scheda di loucabot (stessa funzione), coi dati del bot principale
sc = LG.G.scheda(g1)
ok("🏀 <b>Lega Uno</b>" in sc and "🇺🇸 NBA: <b>LCA</b>" in sc and "📅 Prossima: @ <b>LCB</b>" in sc and "Fantabasket: <b>" in sc
   and "media <b>31,50</b>" in sc and "Ultime partite" in sc, "/player: NBA, prossima partita, fantabasket, media, ultime\n" + sc)
out = []
class M:
    async def reply_text(s, t, **k): out.append(t)
    async def reply_photo(s, *a, **k): out.append(k.get("caption") or "foto")
upd = lambda uid: types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=M(), effective_chat=types.SimpleNamespace(type="private"))
asyncio.run(LG.cmd_player(upd(101), types.SimpleNamespace(args=["Lega", "Uno"])))
ok(out and "Lega Uno" in out[-1], "/player NOME nel bot principale")
asyncio.run(LG.cmd_player(upd(101), types.SimpleNamespace(args=["Lega"])))
ok(out[-1] == "Quale?", "/player con più giocatori: i bottoni")

# /status
st = __import__("shared.status_squadra", fromlist=["x"]).testo("team01")
ok("Lega Due" in st and "<b>Out</b>" in st and "Caviglia" in st, "/status: gli Out dell'ultimo snapshot\n" + st)
asyncio.run(LG.cmd_status(upd(101), types.SimpleNamespace(args=[])))
ok("Status di" in out[-1], "/status senza squadra: quella del GM")

# /calendario
oggi = datetime.now(timezone(timedelta(hours=-5))).date()
for n, dal in ((90, oggi), (91, oggi + timedelta(days=7)), (92, oggi + timedelta(days=14))):
    db._q("INSERT INTO lega_giornate (stagione, numero, dal, al) VALUES (%s, %s, %s, %s)", (S, n, dal, dal + timedelta(days=6)))
    db._q("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES (%s, %s, 'team01', 'team02')", (S, n))
asyncio.run(LG.cmd_calendario(upd(101), types.SimpleNamespace(args=["90"])))
ok("Giornata 90" in out[-1] and "in casa (+3)" in out[-1] and "G91" in out[-1] and "G92" in out[-1],
   "/calendario N: la giornata del GM e le prossime\n" + out[-1])
asyncio.run(LG.cmd_calendario(upd(999999), types.SimpleNamespace(args=["90", "team02"])))
ok("in trasferta" in out[-1], "/calendario N SQUADRA")
asyncio.run(LG.cmd_calendario(upd(999999), types.SimpleNamespace(args=["90"])))
ok(out[-1].startswith("Uso:"), "/calendario senza squadra e non GM: l'uso")

# solo in privato: nei gruppi sono di loucabot (niente risposte doppie), e nel menu dei gruppi non ci sono
from telegram.ext import filters
hs = {h.commands and next(iter(h.commands)): h for h in LG.get_handlers() if hasattr(h, "commands")}
ok(all(hs[c].filters is not None and "PRIVATE" in str(hs[c].filters).upper() for c in ("player", "status", "calendario")),
   "/player, /status, /calendario: solo in privato")
li = comandi.liste_comandi(settings.fase())
gruppo = {c.command for c in li["group"]}
ok(not gruppo & {"player", "status", "calendario"} and {"player", "status", "calendario"} <= {c.command for c in li["gm"]}
   and "pick" in gruppo, "menu: nei gruppi no, in privato sì (/pick sì anche nei gruppi)")
app = types.SimpleNamespace(handlers={0: LG.get_handlers()})
ok({"player", "status", "calendario"} <= comandi.trova_solo_privato(app), "fuori dal menu del gruppo admin")

# pulizia
db._q("DELETE FROM nba_infortuni WHERE atleta LIKE 'lc%%'"); db._q("DELETE FROM nba_tabellini WHERE atleta LIKE 'lc%%'")
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'lc%%'"); db._q("DELETE FROM nba_atleti WHERE atleta LIKE 'lc%%'")
db._q("DELETE FROM lega_partite WHERE stagione = %s AND giornata >= 90", (S,)); db._q("DELETE FROM lega_giornate WHERE stagione = %s AND numero >= 90", (S,))
for gid in (g1, g2):
    db._q("DELETE FROM contratti WHERE giocatore_id = %s", (gid,)); db._q("DELETE FROM giocatori WHERE id = %s", (gid,))

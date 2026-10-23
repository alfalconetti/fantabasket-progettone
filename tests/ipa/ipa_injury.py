import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""IPanchinari v30: avvisi dell'injury report ai GM (infortuni.py) e /toggle_injures; loucabot v44:
injury report ogni mezz'ora nella prima sera di una giornata (handlers_calcolo.finestra_fitta)."""
import asyncio, importlib.util, os, types
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import config, db, infortuni as INJ

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
spec = importlib.util.spec_from_file_location("louca_db", os.path.join(ROOT, "fantabasket-loucabot", "db.py"))
ldb = importlib.util.module_from_spec(spec); spec.loader.exec_module(ldb); ldb.init_db()
db.init_db()
db.q("TRUNCATE ipa_quintetto, ipa_injury_visto, ipa_injury_spenti, nba_infortuni")
S = config.stagione()

vecchi = [r["id"] for r in db.q("SELECT id FROM giocatori WHERE nome_bref LIKE %s", ("Inj %",), many=True) or []]
if vecchi:
    db.q("DELETE FROM cambi_ruolo WHERE giocatore_id = ANY(%s)", (vecchi,))
    db.q("DELETE FROM contratti WHERE giocatore_id = ANY(%s)", (vecchi,))
    db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (vecchi,))
gid = {}
for nome, team, espn in [("Inj Brunson", "team01", "inj1"), ("Inj Hart", "team01", "inj2"), ("Inj Booker", "team02", "inj3"),
                         ("Inj Nessuno", "team03", None)]:
    g = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id",
             (nome, nome, nome.lower(), espn), one=True)["id"]
    db.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s, %s, 5, 2, %s, 'normale')",
         (g, team, S))
    gid[nome] = g
db.q("INSERT INTO ipa_quintetto (team_id, ruolo, giocatore_id, fonte) VALUES ('team01', 'PG', %s, 'admin')", (gid["Inj Brunson"],))

t0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
def snap(minuti, voci, altri=6):
    """Uno snapshot: voci {atleta: stato} più `altri` infortunati di altre squadre (sempre uguali)."""
    preso = t0 + timedelta(minutes=minuti)
    righe = dict(voci, **{f"x{i}": "Out" for i in range(altri)})
    for a, st in righe.items():
        db.q("INSERT INTO nba_infortuni (giorno, atleta, nome, squadra, stato, dettaglio, preso) VALUES (%s, %s, %s, 'NYK', %s, %s, %s)",
             (preso.date(), a, a, st, "Knee soreness" if a == "inj1" else "", preso))

class Bot:
    def __init__(s): s.mandati = []
    async def send_message(s, chat_id, text, **k):
        if chat_id == 111: raise RuntimeError("Forbidden: bot can't initiate conversation with a user")
        s.mandati.append((chat_id, text))
B = Bot()
gira = lambda: asyncio.run(INJ.controlla(B))

snap(0, {"inj1": "Probable", "inj3": "Out"})
ok(gira() == 0 and not B.mandati and db.q("SELECT preso FROM ipa_injury_visto", one=True)["preso"] == t0,
   "prima volta: solo il punto di partenza, nessun avviso")
ok(gira() == 0, "nessuno snapshot nuovo: niente")

# due snapshot nuovi prima del giro del bot: si confronta col visto, non col penultimo
snap(30, {"inj1": "Questionable", "inj3": "Out"})
snap(60, {"inj1": "Out", "inj2": "Day-To-Day"})
n = gira()
a = [t for c, t in B.mandati if c == 101]
ok(n == 2 and len(a) == 1 and len([1 for c, _ in B.mandati if c == 102]) == 1,
   f"un messaggio per GM della squadra (Alfa: 101; 111 non ha avviato il bot e non blocca; Beta: 102) {[(c) for c, _ in B.mandati]}")
ok(a and "Inj Brunson" in a[0] and "Probable" in a[0] and "Out" in a[0] and "nel tuo quintetto (PG)" in a[0]
   and "Knee soreness" in a[0] and "Inj Hart" in a[0] and "Day-To-Day" in a[0] and "disponibile" in a[0],
   "Alfa: Probable → Out (dal visto, il Questionable di mezzo non conta), nel quintetto, dettaglio; Hart nuovo nella lista")
b = [t for c, t in B.mandati if c == 102]
ok(b and "Inj Booker" in b[0] and "disponibile (fuori dalla lista)" in b[0], "Beta: Booker esce dalla lista → disponibile")
ok(all("/toggle_injures" in t for _, t in B.mandati), "sotto ogni avviso /toggle_injures")
ok(not any(c == 103 for c, _ in B.mandati), "nessun avviso a chi non ha cambi")

# /toggle_injures
class Msg:
    def __init__(s): s.r = []
    async def reply_text(s, t, **k): s.r.append(t)
def toggle(uid, tipo="private"):
    m = Msg()
    asyncio.run(INJ.cmd_toggle_injures(types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=m,
                                                             effective_chat=types.SimpleNamespace(type=tipo)), None))
    return m.r[-1]
ok("spenti" in toggle(101), "/toggle_injures: spenti")
B.mandati.clear()
snap(90, {"inj1": "Probable", "inj2": "Day-To-Day"})
gira()
ok(not any(c == 101 for c, _ in B.mandati), "spenti: niente avvisi a 101")
ok("accesi" in toggle(101), "/toggle_injures di nuovo: accesi")
ok("GM" in toggle(999) and "privato" in toggle(101, "group"), "chi non è GM e chi lo scrive in un gruppo")

# snapshot incompleto (risposta di ESPN a metà): nessun avviso
B.mandati.clear()
snap(120, {"inj1": "Out"}, altri=1)
ok(gira() == 0 and not any(c > 0 for c, _ in B.mandati) and any("incompleto" in t for _, t in B.mandati),
   "snapshot con meno della metà dei giocatori: nessun avviso ai GM, una riga sul canale log")

# loucabot: finestra dell'injury report ogni mezz'ora
import sys
sys.path.insert(0, os.path.join(ROOT, "fantabasket-loucabot"))
sys.modules.pop("db", None); sys.modules.pop("config", None)
HC = importlib.import_module("handlers_calcolo")
roma = ZoneInfo("Europe/Rome")
g = [{"numero": 3, "dal": date(2026, 10, 27), "prima_partita": datetime(2026, 10, 28, 0, 30, tzinfo=roma)}]
f = lambda h, m=0, d=27: HC.finestra_fitta(datetime(2026, 10, d, h, m, tzinfo=roma), g)
ok(f(18, 59) is None and f(19, 0) and f(23, 50) and f(0, 29, 28) and f(0, 30, 28) is None and f(20, 0, 26) is None,
   "ogni mezz'ora dalle 19 del primo giorno alla prima partita, non prima, non dopo, non il giorno prima")

# pulizia: i giocatori di prova non restano nelle squadre (le altre prove cercano per nome)
_ids = list(gid.values())
db.q("DELETE FROM ipa_quintetto WHERE giocatore_id = ANY(%s)", (_ids,))
db.q("DELETE FROM contratti WHERE giocatore_id = ANY(%s)", (_ids,))
db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (_ids,))
db.q("TRUNCATE ipa_injury_visto, ipa_injury_spenti, nba_infortuni")

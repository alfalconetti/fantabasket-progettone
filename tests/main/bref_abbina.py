import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v5.4.1: abbinamento dei nomi di Basketball-Reference all'anagrafica (giocatori.nome_bref):
automatico con lo stesso nome senza accenti, uno per uno coi bottoni quando c'è solo un simile,
log di chi è abbinato e di chi a roster su bref non c'è."""
import asyncio, types
import database as db
from handlers import bref as BR
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
NOMI = ["Nikola Topic", "Zaccharie Risacher Prova", "Gioc Bref Visto", "Gioc Doppio", "Gioc Doppio Bis"]
db._q("DELETE FROM bref_nuovi WHERE nome_bref LIKE 'Nikola Topi%%' OR nome_bref LIKE 'Zacc%%' OR nome_bref LIKE 'Gioc %%'")
db._q("DELETE FROM bref_stats WHERE nome_bref LIKE 'Nikola Topi%%' OR nome_bref LIKE 'Zacc%%' OR nome_bref LIKE 'Gioc %%'")
db._q("DELETE FROM giocatori WHERE nome_bref LIKE 'Nikola Topi%%' OR nome_bref LIKE 'Zacc%%' OR nome_bref LIKE 'Gioc %%'")
gid = {n: db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES (%s, %s, %s) RETURNING id", (n, n, n.lower()))
       for n in NOMI}
db._q("INSERT INTO bref_stats (stagione, nome_bref, pts) VALUES ('2099', 'Gioc Bref Visto', 10)")

# 1. automatico: «Nikola Topić» su bref = «Nikola Topic» in anagrafica (mai visto su bref)
fatti = BR.abbina_auto(["Nikola Topić", "Gioc Bref Vistó", "Gioc Nuovo Davvero"])
ok(fatti == [("Nikola Topic", "Nikola Topić")]
   and db._qval("SELECT nome_bref FROM giocatori WHERE id = %s", (gid["Nikola Topic"],)) == "Nikola Topić",
   "automatico: stesso nome senza accenti, giocatore mai visto su bref → nome_bref aggiornato")
ok(db._qval("SELECT nome_bref FROM giocatori WHERE id = %s", (gid["Gioc Bref Visto"],)) == "Gioc Bref Visto",
   "chi su bref c'è già non si tocca (sarebbe un omonimo)")
ok(db._qval("SELECT stato FROM bref_nuovi WHERE nome_bref = 'Nikola Topić'") == "abbinato", "segnato in bref_nuovi come abbinato")

# 2. proposta: «Zaccharie Risacher Prov» ha un simile → bottoni 🔗/🆕; «Gioc Nuovo Davvero» no → solo ✅
for n in ("Zaccharie Risacher Prov", "Gioc Nuovo Davvero"):
    db._q("INSERT INTO bref_nuovi (nome_bref, team, g) VALUES (%s, 'ATL', 3)", (n,))
testo, kb = BR._testo_nuovi()
cb = [b.callback_data for riga in kb.inline_keyboard for b in riga]
idz = db._qval("SELECT id FROM bref_nuovi WHERE nome_bref = 'Zaccharie Risacher Prov'")
ok(f"brefn:l:{idz}:{gid['Zaccharie Risacher Prova']}" in cb and f"brefn:c:{idz}" in cb and "brefn:ok" in cb
   and "Crea i 1 senza simili" in str([b.text for r in kb.inline_keyboard for b in r]),
   "proposta: chi ha un simile si decide uno per uno (🔗/🆕), ✅ crea solo quelli senza simili")

for i in range(100):
    db._q("INSERT INTO bref_nuovi (nome_bref, team, g) VALUES (%s, 'ATL', 1) ON CONFLICT DO NOTHING", (f"Gioc Lunghissimo Nome Numero {i:03d}",))
t_lungo, _ = BR._testo_nuovi()
ok(len(t_lungo) < 4096 and "… e altri" in t_lungo, f"100 nomi nuovi: il messaggio resta sotto il limite di Telegram ({len(t_lungo)} caratteri)")
db._q("DELETE FROM bref_nuovi WHERE nome_bref LIKE 'Gioc Lunghissimo%%'")
class Q:
    def __init__(s, data): s.data, s.from_user, s.testi = data, types.SimpleNamespace(id=1, first_name="Luca"), []
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): s.testi.append(t)
import settings
settings.dev_id = lambda: 1
async def premi(data):
    class _Bot:
        async def send_message(s, **k): pass
    q = Q(data); await BR.cb_nuovi(types.SimpleNamespace(callback_query=q), types.SimpleNamespace(bot=_Bot())); return q
asyncio.run(premi("brefn:ok"))
ok(db._qval("SELECT 1 FROM giocatori WHERE nome_bref = 'Gioc Nuovo Davvero'") and
   not db._qval("SELECT 1 FROM giocatori WHERE nome_bref = 'Zaccharie Risacher Prov'"),
   "✅ crea quello senza simili, non quello col simile")
asyncio.run(premi(f"brefn:l:{idz}:{gid['Zaccharie Risacher Prova']}"))
ok(db._qval("SELECT nome_bref FROM giocatori WHERE id = %s", (gid["Zaccharie Risacher Prova"],)) == "Zaccharie Risacher Prov"
   and db._qval("SELECT stato FROM bref_nuovi WHERE id = %s", (idz,)) == "abbinato", "🔗 abbina al giocatore che c'è già")

# 3. a roster ma mai visti su bref
db._q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s, 'team01', 1, 1, '2026', 'rookie')",
      (gid["Gioc Doppio"],))
ok(any(x["nome_common"] == "Gioc Doppio" for x in BR.senza_bref()), "a roster senza nessuna riga bref: nel log")

db._q("DELETE FROM contratti WHERE giocatore_id = ANY(%s)", (list(gid.values()),))
db._q("DELETE FROM bref_nuovi WHERE nome_bref LIKE 'Nikola Topi%%' OR nome_bref LIKE 'Zacc%%' OR nome_bref LIKE 'Gioc %%'")
db._q("DELETE FROM bref_stats WHERE nome_bref LIKE 'Gioc %%'")
db._q("DELETE FROM giocatori WHERE nome_bref LIKE 'Nikola Topi%%' OR nome_bref LIKE 'Zacc%%' OR nome_bref LIKE 'Gioc %%'")

# ── stagione non ancora iniziata su bref (v6.1.3): niente «Import beautifulsoup4 failed», niente BrefRaw svuotato ──
import pandas as _pd, bref_scraper as BS, gas_client as _gc
def _senza_tabelle(*a, **k):
    assert k.get("flavor") == "lxml", "read_html senza flavor=lxml: ripiega su bs4"
    raise ValueError("No tables found")
_pd.read_html = _senza_tabelle
try:
    BS.scrape_bref_df("2099"); ok(False, "pagina senza tabella: doveva dare BrefVuoto")
except BS.BrefVuoto:
    ok(True, "pagina senza tabella (stagione non iniziata) → BrefVuoto")
_inviati, _fogli = [], []
_gc.sync_bref_raw = lambda csv: _fogli.append(csv) or True
_g = dict(settings.load_globals()); _g.update(fase="regular-season-fa", log_channel_id_main=-77)
_vecchio_lg = settings.load_globals; settings.load_globals = lambda: _g
class _B:
    async def send_message(self, **k): _inviati.append(k)
asyncio.run(BR.job_bref(types.SimpleNamespace(bot=_B())))
settings.load_globals = _vecchio_lg
ok(len(_inviati) == 1 and _inviati[0]["text"].startswith("⏳ Bref") and "❌" not in _inviati[0]["text"] and not _fogli,
   f"job bref a stagione non iniziata: ⏳ sul canale log, foglio BrefRaw non toccato {_inviati}")

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""IPanchinari v39 (progettone v7.10.0): nelle giornate P dei playoff formazioni, promemoria, stato, report e
congelamento dei quintetti solo per le squadre che giocano (comune.in_gioco, shared/playoff_base.in_gioco)."""
import asyncio, importlib.util, json, os
from datetime import date, datetime, timedelta, timezone
import config, db, comune, quintetti as QU

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
spec = importlib.util.spec_from_file_location("louca_db", os.path.join(ROOT, "fantabasket-loucabot", "db.py"))
ldb = importlib.util.module_from_spec(spec); spec.loader.exec_module(ldb); ldb.init_db()
db.init_db()
S = config.stagione()
db.q("TRUNCATE lega_giornate, lega_partite")
oggi = date.today()
db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al, prima_partita) VALUES (%s, 1, 'regular', %s, %s, %s)",
     (S, oggi - timedelta(days=9), oggi - timedelta(days=3), datetime.now(timezone.utc) - timedelta(days=9)))
db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al, prima_partita) VALUES (%s, 2, 'playoff', %s, %s, %s)",
     (S, oggi + timedelta(days=1), oggi + timedelta(days=2), datetime.now(timezone.utc) + timedelta(days=1)))
db.q("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES (%s, 2, 'team01', 'team02')", (S,))
g1, g2 = db.giornata(S, 1), db.giornata(S, 2)
ok(len(comune.in_gioco(S, g1)) == len(config.squadre()), "regular season: tutte le squadre")
ok([t["id"] for t in comune.in_gioco(S, g2)] == ["team01", "team02"], "giornata P: solo chi ha una partita")
st = QU.testo_stato(g2)
nomi = {t["id"]: t["nome"] for t in config.squadre()}
ok(nomi["team01"] in st and nomi["team03"] not in st, "/stato della giornata P: solo chi gioca")


class Bot:
    def __init__(self):
        self.a = []

    async def send_message(self, chat_id, text, **k):
        self.a.append(chat_id)


b = Bot()
asyncio.run(QU.manda_promemoria(b, g2))
gm = {int(x) for t in config.squadre() if t["id"] in ("team01", "team02") for x in t.get("gm_ids", [])}
ok(set(b.a) == gm, f"promemoria della giornata P solo ai GM di chi gioca {b.a}")
# v7.35.5 (prova generale dei playoff): alla chiusura della giornata P quintetti congelati e panchine mancanti solo
# per chi gioca; le eliminate e le prime due al primo turno non risultano «senza panchina» (niente penalità)
db.q("UPDATE lega_giornate SET prima_partita = %s WHERE stagione = %s AND numero = 2", (datetime.now(timezone.utc) - timedelta(minutes=5), S))
db.q("DELETE FROM ipa_formazioni WHERE stagione = %s AND giornata = 2", (S,))
db.q("DELETE FROM ipa_panchine WHERE stagione = %s AND giornata = 2", (S,))
db.q("DELETE FROM ipa_stato_giornata WHERE stagione = %s AND giornata = 2", (S,))
db.salva_panchina(S, 2, "team01", None, [{"giocatore_id": None, "testo": "P1", "ruolo": "PG"}])
class Bot2:
    def __init__(self): self.a = []
    async def send_message(self, chat_id=None, text=None, **k): self.a.append((chat_id, text))
b2 = Bot2()
asyncio.run(QU.job_giornate(type("C", (), {"bot": b2})()))
_form = {r["team_id"] for r in db.q("SELECT team_id FROM ipa_formazioni WHERE stagione = %s AND giornata = 2", (S,), many=True) or []}
_st = db.stato_giornata(S, 2)
_manc = _st.get("mancanti")
_manc = json.loads(_manc) if isinstance(_manc, str) else _manc
ok(_st["chiusa"] and _form == {"team01", "team02"}, f"chiusura della giornata P: quintetti congelati solo per chi gioca {_form}")
ok(_manc == ["team02"], f"senza panchina solo chi gioca e non l'ha mandata, non le altre {_manc}")
db.q("DELETE FROM ipa_formazioni WHERE stagione = %s AND giornata IN (1, 2)", (S,))
db.q("DELETE FROM ipa_panchine WHERE stagione = %s AND giornata IN (1, 2)", (S,))
db.q("DELETE FROM ipa_stato_giornata WHERE stagione = %s AND giornata IN (1, 2)", (S,))   # anche la 1, chiusa dal job
db.q("TRUNCATE lega_giornate, lega_partite")

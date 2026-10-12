import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""loucabot v1: lettura del CSV del calendario, controlli, import, partite NBA da ESPN (risposta
vera ridotta in tests/louca/espn-20261022.json), squadre a media e scadenze, /calendario."""
import asyncio, json, os, types
from datetime import date, datetime, timezone
import db, nba, calendario as cal, handlers as H
db.init_db()
db.q("TRUNCATE lega_giornate, lega_partite, nba_partite")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
QUI = os.path.dirname(os.path.abspath(__file__))

CSV = """Week 1 20/10 - 22/10,,,,
Alfa,,V,,Beta
,,,,
Gamma,,V,,Delta
,,,,
Week 2 23/10 - 24/10 (media OKC),,,,
Delta,,V,,alfa
,,,,
Beta,,V,,Gamma
Week 3 31/12 - 2/1 (media cle, den),,,,
Alfa,,V,,Gamma
Delta,,V,,Beta
"""
giornate, partite = cal.leggi_csv(CSV, "2026")
ok([(g["numero"], g["dal"], g["al"], g["media_file"]) for g in giornate] ==
   [(1, date(2026, 10, 20), date(2026, 10, 22), []), (2, date(2026, 10, 23), date(2026, 10, 24), ["OKC"]),
    (3, date(2026, 12, 31), date(2027, 1, 2), ["CLE", "DEN"])],
   "CSV: giornate, date (anche a cavallo dell'anno) e squadre a media dal titolo")
ok(len(partite) == 6 and partite[0] == (1, "Alfa", "Beta"), "CSV: partite con casa e trasferta")

def errore(testo):
    try:
        cal.importa(testo, "2026"); return ""
    except cal.ErroreCalendario as e:
        return str(e)
ok("Zeta" in errore(CSV.replace("Delta,,V,,Beta", "Delta,,V,,Zeta")), "squadra sconosciuta: import rifiutato")
ok("due volte" in errore(CSV.replace("Delta,,V,,Beta", "Delta,,V,,Alfa")), "squadra due volte nella stessa giornata: rifiutato")
ok("prima della fine" in errore(CSV.replace("Week 2 23/10", "Week 2 21/10")), "giornate sovrapposte: rifiutato")
ok(db.giornate("2026") == [], "dopo un errore non si salva niente")
r = cal.importa(CSV, "2026")
ok((r["giornate"], r["partite"]) == (3, 6) and r["dubbi"] == [] and len(db.partite_giornata("2026", 2)) == 2,
   "import: 3 giornate, 6 partite (nomi senza maiuscole riconosciuti)")
ok(db.partita_squadra("2026", 2, "team01")["trasferta"] == "team01", "Alfa in trasferta alla giornata 2")
cal.importa(CSV, "2026")
ok(len(db.partite_giornata("2026", 1)) == 2, "reimport: sostituisce, niente doppioni")

# ESPN: risposta vera del 22/10/2026 (ridotta)
vero = json.load(open(os.path.join(QUI, "espn-20261022.json")))
p = nba.leggi_giorno(vero)
ok([(x["trasferta"], x["casa"], x["data_et"], x["tipo"], x["stagione"], x["stato"]) for x in p] ==
   [("CLE", "PHI", date(2026, 10, 22), 2, "2026", "STATUS_SCHEDULED"),
    ("DEN", "OKC", date(2026, 10, 22), 2, "2026", "STATUS_SCHEDULED")],
   "ESPN: partite, giorno della costa est (DEN-OKC alle 01:30 UTC è ancora il 22), stagione 2026")
ok(nba.giorni_stagione(vero)[0] == date(2026, 10, 3) and nba.sigla("GS") == "GSW" and nba.sigla("UTAH") == "UTA",
   "ESPN: elenco dei giorni della stagione, sigle come le nostre")

def evento(i, giorno, ora_utc, casa, trasf, stato="STATUS_SCHEDULED"):
    return {"id": str(i), "date": f"{giorno}T{ora_utc}Z", "season": {"year": 2027, "type": 2},
            "competitions": [{"competitors": [{"homeAway": "home", "team": {"abbreviation": casa}},
                                              {"homeAway": "away", "team": {"abbreviation": trasf}}],
                              "status": {"type": {"name": stato}}}]}
GIORNI = {
    date(2026, 10, 20): [evento(1, "2026-10-20", "23:00", "PHI", "CLE"), evento(2, "2026-10-20", "23:30", "OKC", "DEN"),
                         # NBA Cup: partite con squadre ancora da decidere, non sono squadre NBA
                         evento(8, "2026-10-21", "02:00", "TBD", "TBD"), evento(9, "2026-10-21", "03:00", "OKC", "W12")],
    date(2026, 10, 23): [evento(3, "2026-10-23", "23:00", "DEN", "CLE")],
    date(2026, 10, 24): [evento(4, "2026-10-24", "18:00", "PHI", "CLE", "STATUS_POSTPONED"),
                         evento(5, "2026-10-25", "00:00", "PHI", "DEN")],
    date(2027, 1, 1): [evento(6, "2027-01-01", "20:00", "PHI", "OKC")],
}
async def finto(g):
    return {"leagues": [{"calendar": [f"{d}T07:00Z" for d in GIORNI]}], "events": GIORNI.get(g, [])}
r = asyncio.run(nba.sincronizza(list(GIORNI), scarica=finto, pausa=0))
ok(r["partite"] == 8 and db.squadre_nba("2026") == {"PHI", "CLE", "OKC", "DEN"},
   "sincronizzazione: partite salvate; TBD e sigle sconosciute non contano come squadre")
ok(nba.sigla("W12") == "TBD" and nba.sigla("TBD") == "TBD" and len(nba.NBA) == 30, "segnaposto della NBA Cup → TBD")
cal.ricalcola("2026", oggi=date(2026, 10, 1))
g1, g2, g3 = (db.giornata("2026", n) for n in (1, 2, 3))
ok(g1["media"] == [] and g1["prima_partita"] == datetime(2026, 10, 20, 23, 0, tzinfo=timezone.utc),
   "G1: giocano tutti, scadenza alla prima partita (20/10 23:00 UTC)")
ok(g2["media"] == ["OKC"], "G2: OKC senza partite (la partita rinviata di CLE non conta, ma CLE gioca il 23)")
ok(g3["media"] == ["CLE", "DEN"], "G3: a media CLE e DEN")
ok(cal.differenze_file("2026") == [], "le squadre a media calcolate coincidono con il calendario")
GIORNI[date(2026, 10, 23)] = [evento(3, "2026-10-23", "21:00", "DEN", "CLE")]
GIORNI[date(2026, 10, 24)] = [evento(4, "2026-10-24", "18:00", "PHI", "CLE", "STATUS_POSTPONED"),
                              evento(5, "2026-10-25", "00:00", "PHI", "DEN"), evento(7, "2026-10-24", "22:00", "OKC", "PHI")]
asyncio.run(nba.sincronizza([date(2026, 10, 23), date(2026, 10, 24)], scarica=finto, pausa=0))
cambi = cal.ricalcola("2026", oggi=date(2026, 10, 1))
ok(any("giornata 2" in c and "prima partita" in c for c in cambi) and any("giornata 2" in c and "a media nessuno" in c for c in cambi),
   f"cambi segnalati: nuova scadenza e OKC che ora gioca {cambi}")
ok(cal.differenze_file("2026") == ["giornata 2: calendario OKC, partite NBA nessuno"], "differenza col calendario segnalata")
ok(cal.corrente("2026", oggi=date(2026, 10, 23))["numero"] == 2 and cal.corrente("2026", oggi=date(2027, 2, 1)) is None,
   "giornata corrente")

# /calendario di un GM e /giornata
class Msg:
    def __init__(s): s.t = []; s.document = None; s.reply_to_message = None
    async def reply_text(s, t, **k): s.t.append(t)
def comando(cb, uid, args=()):
    m = Msg()
    asyncio.run(cb(types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_message=m,
                                         effective_chat=types.SimpleNamespace(id=uid)),
                   types.SimpleNamespace(args=list(args), bot=None)))
    return m.t[-1]
t = comando(H.cmd_calendario, 101, ["1"])
ok("Giornata 1" in t and "in casa (+3)" in t and "Beta" in t and "G2" in t and "✈️" in t,
   "/calendario: giornata, avversario, casa, le prossime")
t = comando(H.cmd_calendario, 101, ["3"])
ok("A media" in t and "CLE, DEN" in t, "/calendario: squadre a media")
t = comando(H.cmd_giornata, 999, ["2"])
ok("Delta – Alfa" in t and "Beta – Gamma" in t, "/giornata: tutte le partite")
ok("Solo admin" in comando(H.cmd_importa_calendario, 101), "/importa_calendario solo admin")

# canale log di loucabot: chiave sua, altrimenti quello del bot principale
import json as _json, config
_g = _json.load(open(config.GLOBALS_PATH))
ok(config.canale_log() == _g["log_channel_id_main"], "canale log: senza log_channel_id_louca usa quello del bot principale")
_json.dump({**_g, "log_channel_id_louca": -77}, open(config.GLOBALS_PATH, "w"))
ok(config.canale_log() == -77, "canale log: log_channel_id_louca")
class _Bot:
    def __init__(s): s.m = []
    async def send_message(s, **k): s.m.append(k)
_b = _Bot()
import handlers as _h
asyncio.run(_h.log(_b, "prova"))
ok(_b.m and _b.m[0]["chat_id"] == -77, "riga di log mandata al canale di loucabot")
async def _sync_finto(giorni=None, **k):
    return {"giorni": 18, "partite": 0, "errori": []}
_h.nba.sincronizza = _sync_finto
_ctx = types.SimpleNamespace(bot=_Bot())
asyncio.run(_h.job_sync(_ctx))
ok(any(x["chat_id"] == -77 and "8:30" in x["text"] for x in _ctx.bot.m),
   f"sincronizzazione delle 8:30 annotata sul canale log {_ctx.bot.m}")
_json.dump(_g, open(config.GLOBALS_PATH, "w"))

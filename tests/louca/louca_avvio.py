import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.19.0 (dopo il 19/11, Telegram muto per loucabot): l'attesa di Telegram all'avvio senza crash
(shared.attesa_telegram), il download che non ha bisogno di Telegram mentre si aspetta, e i job a orario fisso
saltati rifatti all'avvio (avvio.py)."""
import asyncio
import types
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import db
import avvio
db.init_db()
from shared import attesa_telegram as AT
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
ROME = ZoneInfo("Europe/Rome")

# ── attesa ──
risposte = iter([TimeoutError(), TimeoutError(), 200])
chiamate, pause, lavoro = [], [], []


def get(url, timeout):
    chiamate.append(url)
    r = next(risposte)
    if isinstance(r, Exception):
        raise r
    return types.SimpleNamespace(status_code=r, json=lambda: {"ok": True})


secondi = AT.attendi("TOKEN", "prova", mentre=lambda: lavoro.append(1), get=get, dormi=pause.append, attese=(15, 30), rete=lambda: True)
ok(len(chiamate) == 3 and pause == [15, 30] and len(lavoro) == 2,
   f"Telegram non risponde due volte: aspetta 15 e 30 secondi, intanto lavora, poi parte ({pause}, {len(lavoro)})")
ok(AT.ULTIMA_ATTESA == secondi and "TOKEN" in chiamate[0] and "getMe" in chiamate[0], "chiede getMe col token del bot")
ok(AT.ULTIMA_SENZA_RETE == 0, "rete ok durante l'attesa: niente tempo senza rete")
AT.ULTIMA_ATTESA, AT.ULTIMA_SENZA_RETE = 4400, 0
ok(AT.nota_avvio() == "\n⚠️ Ripartito dopo 1 h 13 min: 📡 Telegram non rispondeva a questo bot (la rete del server andava: problema di Telegram).",
   f"nota nel messaggio di avvio: è Telegram {AT.nota_avvio()!r}")
AT.ULTIMA_SENZA_RETE = 4400
ok("🌐 la rete del server non funzionava (problema della tua rete, non di Telegram)" in AT.nota_avvio(), "nota: è la rete del server")
AT.ULTIMA_SENZA_RETE = 3000
ok("rete del server non funzionava (circa 50 min), poi Telegram non rispondeva a questo bot (circa 23 min)" in AT.nota_avvio(),
   f"nota: prima la rete, poi Telegram {AT.nota_avvio()!r}")
pause.clear()
risposte = iter([TimeoutError(), TimeoutError(), 200])
AT.attendi("T", "prova", get=get, dormi=pause.append, attese=(15, 30), rete=lambda: False)
ok(AT.ULTIMA_SENZA_RETE == AT.ULTIMA_ATTESA, "rete giù a ogni tentativo: tutta l'attesa è senza rete")
AT.ULTIMA_ATTESA = AT.ULTIMA_SENZA_RETE = 0
ok(AT.nota_avvio() == "", "nessuna nota se Telegram ha risposto subito")
pause.clear()
AT.attendi("T", "prova", get=lambda u, timeout: types.SimpleNamespace(status_code=200, json=lambda: {"ok": True}), dormi=pause.append, rete=lambda: True)
ok(pause == [] and AT.ULTIMA_ATTESA == 0, "Telegram risponde subito: nessuna attesa")


def rotto():
    raise RuntimeError("ESPN giù")


risposte = iter([TimeoutError(), 200])
AT.attendi("T", "prova", mentre=rotto, get=get, dormi=lambda s: None, rete=lambda: True)
ok(True, "un errore nel lavoro durante l'attesa non ferma l'attesa")

# ── download senza Telegram: al massimo ogni 5 minuti ──
avvio._ultimo.update(giro=1000.0, infortuni=0.0)
ok(avvio.scarica_senza_telegram(ora=lambda: 1100.0) == "", "un altro giro di download prima di 5 minuti: niente")

# ── job saltati ──
avvio.migra()
db.q("DELETE FROM job_eseguiti")
fatti = []


async def job_a(context):
    fatti.append("a")


REC = {"calcolo": (time(10, 0), job_a), "controllo_notte": (time(20, 0), job_a)}
adesso = datetime(2026, 11, 20, 15, 0, tzinfo=ROME)
ok(avvio.da_recuperare(REC, adesso) == [] and avvio.ultimo("calcolo") == adesso,
   "prima volta (deploy): nessun recupero, si segna solo l'ora di adesso")
avvio.segna("calcolo", datetime(2026, 11, 19, 10, 2, tzinfo=ROME))          # ieri: oggi alle 10 il bot era giù
avvio.segna("controllo_notte", datetime(2026, 11, 19, 20, 1, tzinfo=ROME))  # ieri sera ok, oggi alle 20 non ancora
ok(avvio.da_recuperare(REC, adesso) == ["calcolo"], "alle 15 il calcolo delle 10 saltato si rifà, il controllo delle 20 no")
ok(avvio.da_recuperare(REC, datetime(2026, 11, 20, 21, 0, tzinfo=ROME)) == ["calcolo", "controllo_notte"],
   "alle 21 tutti e due, nell'ordine della giornata")
avvio.segna("calcolo", datetime(2026, 11, 17, 10, 2, tzinfo=ROME))
ok(avvio.da_recuperare(REC, datetime(2026, 11, 20, 9, 0, tzinfo=ROME)) == [],
   "un'ora dovuta più di 20 ore fa non si rifà (ieri alle 10, adesso le 9)")


class JQ:
    def __init__(self):
        self.messi = []

    def run_once(self, cb, when, name):
        self.messi.append((name, when, cb))


app = types.SimpleNamespace(job_queue=JQ())
avvio.segna("calcolo", datetime(2026, 11, 19, 10, 2, tzinfo=ROME))
nomi = avvio.recupera(app, REC, datetime(2026, 11, 20, 21, 0, tzinfo=ROME))
ok([(n, w) for n, w, _c in app.job_queue.messi] == [("recupero_calcolo", 60), ("recupero_controllo_notte", 90)],
   f"recupero: uno ogni mezzo minuto dal primo minuto {[(n, w) for n, w, _c in app.job_queue.messi]}")
asyncio.run(app.job_queue.messi[0][2](None))
ok(fatti == ["a"] and avvio.ultimo("calcolo") > datetime(2026, 11, 20, tzinfo=ROME), "il job rifatto segna l'ora in job_eseguiti")
ok(avvio.testo_recuperati(nomi) == "🔁 Saltati mentre il bot era giù, li rifaccio ora: calcolo, controllo finale della notte.",
   "il messaggio nel canale di log")
# ── v7.20.2: Telegram che cade col bot acceso ──
risposte = {"ok": False}
avvio.CONTROLLO = lambda: risposte["ok"]
avvio.GIU.update(dal=None, senza_rete=False)
prima = avvio.ultimo("calcolo")
asyncio.run(avvio.segnato("calcolo", job_a)(None))
ok(avvio.ultimo("calcolo") == prima and avvio.GIU["dal"] is not None, "job finito con Telegram giù: non si segna, e si sa da quando")
inviati = []


class _Bot:
    async def send_message(self, **k):
        inviati.append(k)


ctx = types.SimpleNamespace(application=types.SimpleNamespace(job_queue=JQ()), bot=_Bot())
ok(asyncio.run(avvio.job_sentinella(ctx, REC, datetime(2026, 11, 20, 21, 0, tzinfo=ROME))) == "", "sentinella: ancora giù, niente")
risposte["ok"] = True
avvio.GIU["dal"] = datetime(2026, 11, 20, 9, 40, tzinfo=ROME)
avvio.segna("calcolo", datetime(2026, 11, 19, 10, 2, tzinfo=ROME))
avvio.segna("controllo_notte", datetime(2026, 11, 20, 20, 1, tzinfo=ROME))
t = asyncio.run(avvio.job_sentinella(ctx, REC, datetime(2026, 11, 20, 21, 0, tzinfo=ROME)))
ok([n for n, _w, _c in ctx.application.job_queue.messi] == ["recupero_calcolo"] and avvio.GIU["dal"] is None
   and "dalle 09:40 alle 21:00" in t and "calcolo" in t and ("Telegram" in t or "Rete" in t),
   f"Telegram tornato: rifà il calcolo non segnato e lo dice {t!r}")
ok(asyncio.run(avvio.job_sentinella(ctx, REC)) == "", "poi, tutto normale: niente")
asyncio.run(avvio.segnato("calcolo", job_a)(None))
ok(avvio.ultimo("calcolo") > datetime(2026, 11, 20, 21, 0, tzinfo=ROME), "con Telegram ok il job si segna")
avvio.CONTROLLO = None
db.q("DELETE FROM job_eseguiti")

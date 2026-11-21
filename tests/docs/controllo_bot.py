import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401
"""v7.19.0: scripts/controllo_bot.py (sul server, controllo dei bot verso Telegram): problemi, un avviso solo,
il messaggio quando torna a posto, col primo bot che risponde. Niente rete: chiamate e container finti."""
import importlib.util, json, os, sys, tempfile
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("controllo_bot", os.path.join(ROOT, "scripts", "controllo_bot.py"))
CB = importlib.util.module_from_spec(spec); spec.loader.exec_module(CB)
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "secrets")); os.makedirs(os.path.join(d, "config"))
for f, t in (("bot_token_main.txt", "TMAIN"), ("bot_token_loucabot.txt", "TLOUCA")):
    open(os.path.join(d, "secrets", f), "w").write(t)
json.dump({"log_channel_id": -100}, open(os.path.join(d, "config", "globals.json"), "w"))
CB.QUI = d
CB.STATO = os.path.join(d, "stato.json")
giu = {"TLOUCA"}
mandati = []


def chiama(tok, metodo, dati=None, timeout=15):
    if metodo == "sendMessage":
        mandati.append((tok, dati["text"]))
        return True, 0.1, ""
    return (False, 15.0, "TimeoutError") if tok in giu else (True, 0.1, "")


CB.chiama = chiama
rete = {"ok": True}
CB.rete_ok = lambda: rete["ok"]
riavvio = set()
CB.container = lambda s: "restarting" if s in riavvio else "running"
sys.argv = ["controllo_bot.py"]
CB.main()
ok(len(mandati) == 1 and mandati[0][0] == "TMAIN" and mandati[0][1].startswith("⚠️ 📡 loucabot: Telegram non gli risponde")
   and "gli altri bot sì" in mandati[0][1], f"loucabot muto, rete ok: «è Telegram con questo bot», col bot principale {mandati}")
CB.main()
ok(len(mandati) == 1, "al giro dopo, ancora giù: nessun secondo avviso")
giu.clear()
CB.main()
ok(len(mandati) == 2 and mandati[1][1].startswith("✅ loucabot di nuovo a posto"), f"tornato: il messaggio di ritorno {mandati[-1]}")
ok(json.load(open(CB.STATO)) == {}, "lo stato si svuota")
# v7.19.1: la rete del server giù → si segna anche se l'avviso non parte, al ritorno un messaggio solo
rete["ok"] = False
CB.main()
st = json.load(open(CB.STATO))
ok(len(mandati) == 2 and "_rete" in st and st["_rete"]["avvisato"] is False, "rete del server giù: niente avviso possibile, ma resta segnato")
rete["ok"] = True
CB.main()
ok(len(mandati) == 3 and mandati[2][1].startswith("✅ La rete del server è tornata: non funzionava dalle")
   and "non era potuto partire" in mandati[2][1] and json.load(open(CB.STATO)) == {},
   f"rete tornata: inizio, fine e durata, e che l'avviso non era partito {mandati[-1][1]!r}")
# tutti i bot muti con la rete ok: è Telegram
giu.update({"TMAIN", "TLOUCA"})
CB.main()
st = json.load(open(CB.STATO))
ok("_telegram" in st and "loucabot" not in st and "problema di Telegram, non tuo" in st["_telegram"]["testo"],
   "nessun bot risponde ma la rete sì: un problema solo, «di Telegram, non tuo»")
giu.clear()
CB.main()
ok(mandati[-1][1].startswith("✅ Telegram risponde di nuovo a tutti i bot"), "Telegram tornato per tutti")
# container in riavvio con Telegram ok: è il bot
riavvio.add("loucabot")
CB.main()
ok(mandati[-1][1].startswith("⚠️ 🐳 loucabot") and "il problema è nel bot" in mandati[-1][1], f"container in riavvio, Telegram ok: «il problema è nel bot» {mandati[-1][1]!r}")

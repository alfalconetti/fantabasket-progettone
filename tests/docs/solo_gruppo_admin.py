"""Comandi admin e dev solo in privato e nel gruppo admin (shared/solo_gruppo_admin, Luca 31/10): la guardia c'è in
tutti e quattro i bot, i comandi pubblici di ognuno non contengono comandi admin, e nei gruppi diversi dal gruppo
admin un comando admin si ferma prima degli handler."""
import asyncio, json, os, subprocess, sys
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)

BOT = {
    "fantabasket-main": ({"roster", "assets", "carriera", "trova_trade", "build_trade", "my_trades", "annulla"},
                         {"broadcast", "reboot", "dev", "dev_log", "sync_sheets", "backup"}),
    "fantabasket-aste-beta": ({"team", "listteams", "me", "offri", "nuova_fa", "team_detail"},
                              {"chiudi_asta", "annulla_asta", "set_cap", "add_cap", "set_fase", "broadcast", "reboot", "admin", "aste"}),
    "fantabasket-ipanchinari": ({"panchina", "quintetto", "soprannomi", "guida"},
                                {"stato", "quintetti", "controlli", "report_formazioni", "quintetto_admin", "dev", "reboot"}),
    "fantabasket-loucabot": ({"classifica", "partita", "giornata", "calendario", "live_results", "player", "live"},
                             {"calcola", "ricalcola", "ricontrolla", "tanking", "fantapunti", "set_valid_status",
                              "congela", "storico_calcolo", "controllo_notte", "dev", "reboot", "update"}),
    "fantabasket-klra": ({"sistemi", "classifica", "partita", "giornata", "top", "confronta", "pdf_giornata", "calendario"},
                         {"klra_verifica"}),
}

for bot, (devono, mai) in BOT.items():
    klra = bot == "fantabasket-klra"
    codice = ("import json, klra.comandi as comandi" if klra else "import json, comandi") + "; print(json.dumps(sorted(comandi.comandi_pubblici())))"
    r = subprocess.run([sys.executable, "-c", codice], cwd=os.path.join(ROOT, bot), capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": ".:..:../fantabasket-loucabot" if klra else ".:.."})
    try:
        pub = set(json.loads(r.stdout.strip().splitlines()[-1]))
    except Exception:
        ok(False, f"{bot}: comandi_pubblici() non calcolabile ({r.stderr.strip()[-300:]})")
        continue
    ok(devono <= pub, f"{bot}: i comandi dei GM e dei gruppi passano nei gruppi {sorted(devono - pub) or ''}")
    ok(not (mai & pub), f"{bot}: nessun comando admin o dev tra i pubblici {sorted(mai & pub) or ''}")
    t = open(os.path.join(ROOT, bot, "klra", "bot.py") if klra else os.path.join(ROOT, bot, "bot.py"), encoding="utf-8").read()
    ok("solo_gruppo_admin.installa(app, " in t, f"{bot}: guardia installata in bot.py")

# la guardia
from shared import solo_gruppo_admin as S
from telegram.ext import ApplicationHandlerStop

ADMIN = -1001
g = S.guardia({"classifica"}, lambda: ADMIN)


def prova(testo, tipo, chat_id):
    msg = NS(text=testo, caption=None)
    upd = NS(message=msg, edited_message=None, channel_post=None, edited_channel_post=None,
             effective_chat=NS(type=tipo, id=chat_id), effective_user=NS(id=7))
    try:
        asyncio.run(g(upd, None))
        return "passa"
    except ApplicationHandlerStop:
        return "fermo"

ok(prova("/calcola 3", "supergroup", -2002) == "fermo", "comando admin nel gruppo della lega: fermato")
ok(prova("/calcola@loucabot", "group", -2002) == "fermo", "anche con @nomebot")
ok(prova("/CALCOLA", "supergroup", -2002) == "fermo", "anche in maiuscolo")
ok(prova("/calcola", "channel", -3003) == "fermo", "comando admin in un canale: fermato")
ok(prova("/calcola 3", "supergroup", ADMIN) == "passa", "nel gruppo admin passa")
ok(prova("/calcola 3", "private", 7) == "passa", "in privato passa (il comando controlla da sé chi è admin)")
ok(prova("/classifica", "supergroup", -2002) == "passa", "comando pubblico nel gruppo della lega: passa")
ok(prova("/start", "supergroup", -2002) == "passa" and prova("/annulla", "supergroup", -2002) == "passa", "/start e /annulla sempre")
ok(prova("ciao /calcola", "supergroup", -2002) == "passa", "un messaggio che non è un comando non si tocca")
g2 = S.guardia({"classifica"}, lambda: None)
try:
    asyncio.run(g2(NS(message=NS(text="/tanking", caption=None), edited_message=None, channel_post=None,
                      edited_channel_post=None, effective_chat=NS(type="supergroup", id=-1001), effective_user=None), None))
    ok(False, "senza gruppo admin configurato nessun gruppo fa da gruppo admin")
except ApplicationHandlerStop:
    ok(True, "senza gruppo admin configurato nessun gruppo fa da gruppo admin")
ok(S.comando(NS(text=None, caption="/importa_calendario")) == "importa_calendario", "comando nella didascalia di un file")

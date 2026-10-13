"""Ogni comando citato nelle guide, negli aiuti (/admin, /dev) e nei menu "/" esiste davvero nel suo bot."""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)

def leggi(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()

def registrati(bot):
    nomi = set()
    for d, _, files in os.walk(os.path.join(ROOT, bot)):
        for f in files:
            if f.endswith(".py"):
                for m in re.finditer(r'CommandHandler\(\s*\[?((?:"\w+"\s*,?\s*)+)', leggi(d, f)):
                    nomi |= set(re.findall(r'"(\w+)"', m.group(1)))
    return nomi

def funzione(path, nome):
    """Il corpo di una funzione (testo fino alla prossima def di primo livello)."""
    t = leggi(path)
    i = t.index(f"async def {nome}(")
    j = t.find("\nasync def ", i + 1)
    k = t.find("\ndef ", i + 1)
    fine = min(x for x in (j, k, len(t)) if x != -1)
    return t[i:fine]

def citati(testo):
    return set(re.findall(r'(?<![\w/.<~])/([a-z][a-z0-9_]*)(?![\w/.])', testo))

for bot, testi in {
    "fantabasket-main": [("guida GM", leggi("fantabasket-main/docs/guida_gm.md")),
                         ("guida admin", leggi("fantabasket-main/docs/guida_admin.md")),
                         ("guida dev", leggi("fantabasket-main/docs/guida_dev.md")),
                         ("/dev", funzione("fantabasket-main/handlers/dev.py", "cmd_dev"))],
    "fantabasket-aste-beta": [("guida GM", leggi("fantabasket-aste-beta/docs/guida_gm.md")),
                              ("guida admin", leggi("fantabasket-aste-beta/docs/guida_admin.md")),
                              ("guida dev", leggi("fantabasket-aste-beta/docs/guida_dev.md")),
                              ("/admin e /dev", funzione("fantabasket-aste-beta/handlers/admin.py", "cmd_admin")
                               + funzione("fantabasket-aste-beta/handlers/dev.py", "dev_help")),
                              ("/start", funzione("fantabasket-aste-beta/handlers/offerte.py", "start_deep_link"))],
}.items():
    reg = registrati(bot)
    tutti = registrati("fantabasket-main") | registrati("fantabasket-aste-beta")
    for nome, t in testi:
        # la guida dev cita anche i comandi dell'altro bot
        mancanti = sorted(citati(t) - (tutti if nome == "guida dev" else reg))
        ok(not mancanti, f"{bot} {nome}: comandi citati tutti esistenti {mancanti or ''}")
    menu = set(re.findall(r'BotCommand\(\s*"(\w+)"', leggi(bot, "comandi.py")))
    menu |= set(re.findall(r'BotCommand\(\s*"(\w+)" if', leggi(bot, "comandi.py")))
    menu |= set(re.findall(r'else "(\w+)"', leggi(bot, "comandi.py")))
    ok(not (menu - reg), f"{bot} menu '/': tutti i comandi esistono {sorted(menu - reg) or ''}")

# v3.13.0: lo specchietto regolamento ↔ codice cita comandi dei due bot
tutti = registrati("fantabasket-main") | registrati("fantabasket-aste-beta")
mancanti = sorted(citati(leggi("docs/regolamento_e_codice.md")) - tutti)
ok(not mancanti, f"docs/regolamento_e_codice.md: comandi citati tutti esistenti {mancanti or ''}")

# v4.0.0: loucabot (README e /guida) e i suoi comandi del menu
reg = registrati("fantabasket-loucabot") | {"dev_log", "dev_pg", "reboot"}   # shared/dev_comune.py
for nome, t in [("README", leggi("fantabasket-loucabot/README.md")),
                ("guida GM", leggi("fantabasket-loucabot/docs/guida_gm.md")),
                ("guida admin", leggi("fantabasket-loucabot/docs/guida_admin.md")),
                ("guida dev", leggi("fantabasket-loucabot/docs/guida_dev.md")),
                ("/start e /dev", funzione("fantabasket-loucabot/handlers.py", "cmd_start")
                 + funzione("fantabasket-loucabot/handlers.py", "cmd_dev"))]:
    # le guide di loucabot citano i comandi di IPanchinari per le correzioni del calcolo (e viceversa)
    mancanti = sorted(citati(t) - reg - registrati("fantabasket-ipanchinari"))
    ok(not mancanti, f"loucabot {nome}: comandi citati tutti esistenti (qui o in IPanchinari) {mancanti or ''}")
menu = set(re.findall(r'BotCommand\(\s*"(\w+)"', leggi("fantabasket-loucabot", "comandi.py")))
ok(menu and not (menu - reg), f"loucabot menu '/': tutti i comandi esistono {sorted(menu - reg) or ''}")

# v5.0.0: IPanchinari (README, guide, /start e /dev) e i suoi comandi del menu
reg = registrati("fantabasket-ipanchinari") | {"dev_log", "dev_pg", "reboot"}
for nome, t in [("README", leggi("fantabasket-ipanchinari/README.md")),
                ("guida GM", leggi("fantabasket-ipanchinari/docs/guida_gm.md")),
                ("guida admin", leggi("fantabasket-ipanchinari/docs/guida_admin.md")),
                ("guida dev", leggi("fantabasket-ipanchinari/docs/guida_dev.md")),
                ("/start e /dev", funzione("fantabasket-ipanchinari/handlers.py", "cmd_start")
                 + funzione("fantabasket-ipanchinari/handlers.py", "cmd_dev"))]:
    mancanti = sorted(citati(t) - reg - registrati("fantabasket-loucabot"))
    ok(not mancanti, f"IPanchinari {nome}: comandi citati tutti esistenti (qui o in loucabot) {mancanti or ''}")
menu = set(re.findall(r'BotCommand\(\s*"(\w+)"', leggi("fantabasket-ipanchinari", "comandi.py")))
ok(menu and not (menu - reg), f"IPanchinari menu '/': tutti i comandi esistono {sorted(menu - reg) or ''}")

# il contrario: ogni comando registrato sta in una delle tre guide del suo bot (GM, admin, dev)
COMUNI = set(re.findall(r'CommandHandler\("(\w+)"', leggi("shared/dev_comune.py")))
for bot, extra in [("fantabasket-main", set()), ("fantabasket-aste-beta", set()),
                   ("fantabasket-loucabot", COMUNI), ("fantabasket-ipanchinari", COMUNI)]:
    guide = "".join(leggi(bot, "docs", f"guida_{x}.md") for x in ("gm", "admin", "dev"))
    senza = sorted((registrati(bot) | extra) - citati(guide))
    ok(not senza, f"{bot}: ogni comando è in una guida {senza or ''}")

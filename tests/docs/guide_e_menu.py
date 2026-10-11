"""Ogni comando citato nelle guide, negli aiuti (/admin, /dev) e nei menu "/" esiste davvero nel suo bot."""
import os, re, sys
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
    return set(re.findall(r'(?<![\w/.<])/([a-z][a-z_]*)', testo))

for bot, testi in {
    "fantabasket-main": [("guida GM", leggi("fantabasket-main/docs/guida_gm.md")),
                         ("guida admin", leggi("fantabasket-main/docs/guida_admin.md")),
                         ("/dev", funzione("fantabasket-main/handlers/dev.py", "cmd_dev"))],
    "fantabasket-aste-beta": [("guida GM", leggi("fantabasket-aste-beta/docs/guida_gm.md")),
                              ("guida admin", leggi("fantabasket-aste-beta/docs/guida_admin.md")),
                              ("/admin e /dev", funzione("fantabasket-aste-beta/handlers/admin.py", "cmd_admin")
                               + funzione("fantabasket-aste-beta/handlers/dev.py", "dev_help"))],
}.items():
    reg = registrati(bot)
    for nome, t in testi:
        mancanti = sorted(citati(t) - reg)
        ok(not mancanti, f"{bot} {nome}: comandi citati tutti esistenti {mancanti or ''}")
    menu = set(re.findall(r'BotCommand\(\s*"(\w+)"', leggi(bot, "comandi.py")))
    menu |= set(re.findall(r'BotCommand\(\s*"(\w+)" if', leggi(bot, "comandi.py")))
    menu |= set(re.findall(r'else "(\w+)"', leggi(bot, "comandi.py")))
    ok(not (menu - reg), f"{bot} menu '/': tutti i comandi esistono {sorted(menu - reg) or ''}")

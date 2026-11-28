import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401
"""v7.19.0 (Luca, 21/11): l'ordine dei comandi nel menu «/» di ogni bot, come nella proposta approvata. Ogni bot
in un processo suo (i moduli si chiamano tutti comandi.py)."""
import os, subprocess, sys
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def liste(cartella, chiamata):
    codice = ("import json, comandi\n"
              f"l = comandi.{chiamata}\n"
              "print(json.dumps({k: [b.command for b in v] for k, v in l.items()}))")
    r = subprocess.run([sys.executable, "-c", codice], cwd=os.path.join(ROOT, cartella), capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": ".:.."}, timeout=120)
    import json
    return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {"errore": r.stderr[-300:]}


m = liste("fantabasket-main", "liste_comandi('regular-season-fa')")
ok(m.get("gm", [])[:7] == ["menu", "guida", "roster", "assets", "my_team", "penalita", "registro"]
   and m["gm"][-2:] == ["palette", "annulla"], f"bot principale, GM: menu e guida, poi la squadra … palette e annulla in fondo {m.get('gm', m)[:7]}")
ok(m["admin"][:len(m["gm"])] == m["gm"] and "admin_menu" in m["admin"][len(m["gm"]):],
   "bot principale, admin: prima i comandi dei GM, poi quelli admin (v7.20.0, Luca: non in cima)")
ok(m["dev"][:len(m["admin"])] == m["admin"] and len(set(m["dev"])) == len(m["dev"]), "dev: quelli admin e poi i suoi, nessun doppione")
lo = liste("fantabasket-loucabot", "liste_comandi()")
ok(lo.get("gm", [])[:3] == ["guida", "calendario", "giornata"] and lo["gm"][-4:] == ["pdf_giornata", "pdf_partite", "pdf_roster", "pdf_assets"]
   and lo["gm"].index("roster") == lo["gm"].index("giocatori_build") + 1 == lo["gm"].index("giocatori") + 2,
   f"loucabot: guida, la giornata, … i PDF in fondo {lo.get('gm', lo)[:3]}")
ip = liste("fantabasket-ipanchinari", "liste_comandi()")
ok(ip.get("gm", [])[:2] == ["build_panchina", "panchina"], f"IPanchinari: build_panchina per primo {ip.get('gm', ip)[:2]}")
asb = liste("fantabasket-aste-beta", "liste_comandi('offseason-fa', True, True)")
ok(asb.get("gm", [])[:2] == ["offri", "nuova_fa"] and asb["gm"][-2:] == ["guida", "annulla"], f"bot aste col mercato aperto: offri per primo {asb.get('gm', asb)[:2]}")

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401
"""v7.20.4 (Luca, 21/11): negli esempi dei bot squadre vere a caso (shared/esempi.py), nelle guide segnaposti;
Alfa, Beta, Gamma, Delta sono le squadre finte delle prove e non devono stare fuori da tests/."""
import os, re, sys, json
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, R)
from shared import esempi as ES
veri = [t["nome"] for t in json.load(open(os.environ["TEAMS_PATH"]))["teams"]]
viste = {ES.squadra() for _ in range(200)}
ok(viste <= set(veri) and len(viste) > 1, f"esempi: squadre vere della lega, a caso ({sorted(viste)})")
a, b = ES.due()
ok(a != b and {a, b} <= set(veri), "due squadre diverse")
ok(ES.filtro("Los Tizi") == '"Los Tizi"' and ES.filtro("Alfa") == "Alfa", "nei filtri chiave:valore, virgolette se ci sono spazi")
_tp = os.environ["TEAMS_PATH"]; os.environ["TEAMS_PATH"] = "/nonesiste.json"
ok(ES.due() in (("Squadra A", "Squadra B"), ("Squadra B", "Squadra A")), "senza teams.json: Squadra A, Squadra B")
os.environ["TEAMS_PATH"] = _tp
finte = re.compile(r"\b(Alfa|Gamma|Delta)\b")
trovate = []
for cart, dirs, files in os.walk(R):
    dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__", ".git", "mockup_da_fare")]
    for f in files:
        if f.endswith((".py", ".md", ".typ")) and f not in ("CHANGELOG.md", "MIGRATION.md"):
            p = os.path.join(cart, f)
            for n, riga in enumerate(open(p, encoding="utf-8"), 1):
                if finte.search(riga) and "Delta Force" not in riga:
                    trovate.append(f"{os.path.relpath(p, R)}:{n}")
ok(not trovate, f"nessuna squadra finta delle prove fuori da tests/ {trovate[:8]}")

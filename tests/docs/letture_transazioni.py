"""Registro unico (v3.10.0): `transazioni` contiene anche pick, diritti ed eventi di squadra.
Chi ricostruisce un roster deve leggere la vista `movimenti_giocatori`. Questa prova fallisce
se `transazioni` viene letta (FROM/JOIN) fuori dalle funzioni che sanno cosa stanno facendo."""
import ast, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
AMMESSE = {
    "fantabasket-main/database.py": {
        "_migra_registro_unico", "storico_pick_diritti_presente", "_eventi_trade_asset",
        "crea_storico_pick_diritti", "_verifica_storico_asset", "controlli_coerenza",
        "get_tagli_gratuiti_usati", "get_pick_at", "get_diritti_at", "movimento_asset_periodo",
        "movimenti_carriera"},
}
RE = re.compile(r"\b(FROM|JOIN)\s+transazioni\b", re.IGNORECASE)
trovate = []
for cartella in ("fantabasket-main", "fantabasket-aste-beta", "shared"):
    for d, _, files in os.walk(os.path.join(ROOT, cartella)):
        if "__pycache__" in d:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(d, f); rel = os.path.relpath(path, ROOT)
            src = open(path, encoding="utf-8").read()
            if not RE.search(src):
                continue
            albero = ast.parse(src)
            funzioni = [(n.lineno, n.end_lineno, n.name) for n in ast.walk(albero)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for m in RE.finditer(src):
                riga = src.count("\n", 0, m.start()) + 1
                dentro = [f for f in funzioni if f[0] <= riga <= f[1]]
                nome = min(dentro, key=lambda f: f[1] - f[0])[2] if dentro else "<modulo>"
                if nome not in AMMESSE.get(rel, set()):
                    trovate.append(f"{rel}:{riga} in {nome}")
ok(not trovate, "nessuna lettura di `transazioni` fuori dalle funzioni ammesse" + (": " + ", ".join(trovate) if trovate else ""))

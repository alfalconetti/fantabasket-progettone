"""Ogni nome preso da un modulo del progettone esiste davvero in quel modulo (v3.13.0).

pyflakes controlla i nomi del file, non quelli degli altri moduli: un `from handlers.trade
import _label_bozza` scritto dentro una funzione, o un `db.funzione_rinominata(...)`, passano
tutti i controlli e falliscono solo quando qualcuno preme quel bottone. Questa prova legge i
sorgenti (senza importarli) e controlla:
  - `from modulo import nome`, anche dentro le funzioni: `nome` è definito o importato in
    `modulo` (o è un suo sottomodulo);
  - `alias.nome` con `import modulo as alias`: `nome` esiste in `modulo`;
  - `alias.nome = ...` (le prove che sostituiscono una funzione): `nome` è DEFINITO in
    `modulo`, non solo importato, altrimenti la sostituzione non avrebbe effetto.
Vale per i due bot, shared/, le prove e gli script della prova generale."""
import ast, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)

# cartella dei sorgenti → cartelle in cui cercare i moduli (come PYTHONPATH=.:.. nei container)
ZONE = {
    "fantabasket-main": ["fantabasket-main", "."],
    "fantabasket-aste-beta": ["fantabasket-aste-beta", "."],
    "shared": ["."],
    "tests/main": ["fantabasket-main", ".", "tests"],
    "tests/aste": ["fantabasket-aste-beta", ".", "tests"],
    "scripts/prova_generale": ["fantabasket-main", "."],
    "fantabasket-loucabot": ["fantabasket-loucabot", "."],
    "tests/louca": ["fantabasket-loucabot", ".", "tests"],
}
# file che girano in un'altra cartella rispetto alla loro zona
ZONE_FILE = {"scripts/prova_generale/foto_aste.py": ["fantabasket-aste-beta", "."]}

_cache = {}


def trova(modulo, radici):
    """File locale del modulo (None se è una libreria esterna)."""
    pezzi = modulo.split(".")
    for r in radici:
        base = os.path.join(ROOT, r, *pezzi)
        for f in (base + ".py", os.path.join(base, "__init__.py")):
            if os.path.isfile(f):
                return f
        if os.path.isdir(base) and pezzi[0] in ("handlers", "validators", "shared"):
            return base          # pacchetto senza __init__ (namespace package)
    return None


def nomi_modulo(path, radici):
    """(definiti, importati) a livello di modulo; None se il modulo crea nomi al volo."""
    if path in _cache:
        return _cache[path]
    _cache[path] = (set(), set())    # contro i cicli
    if os.path.isdir(path):
        sub = {f[:-3] for f in os.listdir(path) if f.endswith(".py")} | \
              {d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))}
        _cache[path] = (sub, set())
        return _cache[path]
    albero = ast.parse(open(path, encoding="utf-8").read())
    definiti, importati = set(), set()

    def bersagli(t):
        for x in ast.walk(t):
            if isinstance(x, ast.Name):
                definiti.add(x.id)

    def visita(corpo):
        for n in corpo:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definiti.add(n.name)
                if n.name == "__getattr__":
                    definiti.add("*")
            elif isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                    bersagli(t)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    importati.add(a.asname or a.name.split(".")[0])
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    if a.name == "*":
                        mod = trova(n.module or "", radici)
                        if mod:
                            d, i = nomi_modulo(mod, radici)
                            importati.update(d | i)
                    else:
                        importati.add(a.asname or a.name)
            else:
                for campo in ("body", "orelse", "finalbody", "handlers"):
                    visita(getattr(n, campo, []) or [])
                if isinstance(n, (ast.For, ast.AsyncFor, ast.With, ast.AsyncWith)):
                    for t in ([n.target] if hasattr(n, "target") else [i.optional_vars for i in n.items if i.optional_vars]):
                        bersagli(t)
    visita(albero.body)
    # `global x` dentro una funzione crea x nel modulo
    for n in ast.walk(albero):
        if isinstance(n, ast.Global):
            definiti.update(n.names)
    _cache[path] = (definiti, importati)
    return _cache[path]


def ha(path, nome, radici, definito=False):
    d, i = nomi_modulo(path, radici)
    if "*" in d:
        return True
    if nome in d or (not definito and nome in i):
        return True
    # sottomodulo di un pacchetto (from handlers import trade)
    cartella = path if os.path.isdir(path) else (os.path.dirname(path) if path.endswith("__init__.py") else None)
    return bool(cartella) and (os.path.isfile(os.path.join(cartella, nome + ".py"))
                               or os.path.isdir(os.path.join(cartella, nome)))


errori, controllati = [], 0
for zona in ZONE:
    for d, _, files in os.walk(os.path.join(ROOT, zona)):
        if "__pycache__" in d:
            continue
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            path = os.path.join(d, f)
            rel = os.path.relpath(path, ROOT)
            radici = ZONE_FILE.get(rel, ZONE[zona])
            albero = ast.parse(open(path, encoding="utf-8").read())
            alias = {}    # nome locale → file del modulo
            for n in ast.walk(albero):
                if isinstance(n, ast.Import):
                    for a in n.names:
                        if a.asname or "." not in a.name:
                            mod = trova(a.name, radici)
                            if mod:
                                alias.setdefault(a.asname or a.name, set()).add(mod)
                elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                    mod = trova(n.module, radici)
                    if not mod:
                        continue
                    for a in n.names:
                        if a.name == "*":
                            continue
                        controllati += 1
                        if not ha(mod, a.name, radici):
                            errori.append(f"{rel}:{n.lineno} from {n.module} import {a.name}")
                        sub = trova(f"{n.module}.{a.name}", radici)
                        if sub:
                            alias.setdefault(a.asname or a.name, set()).add(sub)
            # nomi locali che coprono l'alias (parametri, variabili): niente controllo su quelli
            locali = {x.arg for x in ast.walk(albero) if isinstance(x, ast.arg)}
            locali |= {x.id for x in ast.walk(albero) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}
            for n in ast.walk(albero):
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias \
                        and n.value.id not in locali:
                    controllati += 1
                    store = isinstance(n.ctx, ast.Store)
                    if not any(ha(m, n.attr, radici, definito=store) for m in alias[n.value.id]):
                        cosa = "sostituisce" if store else "usa"
                        errori.append(f"{rel}:{n.lineno} {cosa} {n.value.id}.{n.attr}")

ok(not errori, f"nomi presi da altri moduli: {controllati} controllati"
   + (", non trovati: " + "; ".join(sorted(set(errori))) if errori else ", tutti esistono"))

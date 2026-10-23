import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v6.4.0: nel backup c'è tutta config/ tranne config/foto (le foto dei giocatori, che loucabot
riscarica da solo da ESPN): peserebbero decine di MB contro il limite di 50 MB di Telegram."""
import io, os, tempfile, zipfile
import scheduler as SC
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "foto")); os.makedirs(os.path.join(d, "loghi"))
open(os.path.join(d, "globals.json"), "w").write("{}")
open(os.path.join(d, "loghi", "team01_logo.png"), "wb").write(b"x")
open(os.path.join(d, "foto", "123.png"), "wb").write(b"x" * 1000)
os.environ["CONFIG_DIR"] = d
os.environ["ASTE_DB_PATH"] = os.path.join(d, "non_esiste.db")
SC._pg_dump = lambda: b"-- dump finto"
SC.info_secrets_cifrati = lambda: None
nomi = zipfile.ZipFile(io.BytesIO(SC._crea_backup_zip())).namelist()
ok("config/globals.json" in nomi and "config/loghi/team01_logo.png" in nomi, "backup: config e loghi dentro")
ok(not any(n.startswith("config/foto") for n in nomi), f"backup: le foto dei giocatori no {nomi}")

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""Le migrazioni di avvio su un database vuoto (v7.18.0, dopo il crash della v7.17.0: l'ALTER di tabellini_corretti
veniva prima della CREATE e le altre prove non se ne accorgevano, perché il database delle prove aveva già la tabella).
Crea un database nuovo accanto a quello delle prove, ci fa girare quello che fa main() di ogni bot prima di avviarsi,
dopo lo schema che il container postgres carica al primo avvio, nell'ordine del server (bot principale, loucabot, IPanchinari), due volte (la seconda: niente deve rompersi a ripartire),
poi lo cancella. Il codice eseguito è proprio quello di main() fino a ApplicationBuilder, così una migrazione nuova
aggiunta lì è provata senza toccare questa prova. klra ha il suo database: lo prova klra_motore."""
import inspect, os, re, subprocess, sys, textwrap
import psycopg2

ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URL = os.environ["DATABASE_URL"]
NOME = "fbt_migrazioni_vuoto"
VUOTO = re.sub(r"/[^/?]+(\?|$)", f"/{NOME}\\1", URL)


def admin(sql):
    c = psycopg2.connect(URL)
    c.autocommit = True
    with c.cursor() as cur:
        cur.execute(sql)
    c.close()


# il pezzo di main() prima di ApplicationBuilder, eseguito nel modulo bot
CODICE = textwrap.dedent('''
    import inspect, textwrap, sys
    import bot
    righe = inspect.getsource(bot.main).splitlines()[1:]
    corpo = []
    for r in righe:
        if "ApplicationBuilder" in r or "_token" in r or "_read_secret" in r:
            break
        corpo.append(r)
    assert any("init_db" in r for r in corpo), "main() senza init_db"
    exec(textwrap.dedent("\\n".join(corpo)), bot.__dict__)
    print("MIGRATO")
''')

admin(f"DROP DATABASE IF EXISTS {NOME}")
admin(f"CREATE DATABASE {NOME}")
try:
    # come il container postgres al primo avvio: fantabasket-main/schema.sql (docker-entrypoint-initdb.d), poi i bot
    c = psycopg2.connect(VUOTO)
    c.autocommit = True
    with c.cursor() as cur:
        cur.execute(open(os.path.join(ROOT, "fantabasket-main", "schema.sql")).read())
    c.close()
    for giro in (1, 2):
        for d in ("fantabasket-main", "fantabasket-loucabot", "fantabasket-ipanchinari"):
            env = {**os.environ, "DATABASE_URL": VUOTO, "PG_URL": VUOTO, "PYTHONPATH": ".:.."}
            r = subprocess.run([sys.executable, "-c", CODICE], cwd=os.path.join(ROOT, d), env=env, capture_output=True, text=True, timeout=300)
            fine = (r.stdout + r.stderr).strip().splitlines()
            ok(r.returncode == 0 and "MIGRATO" in r.stdout,
               f"{d}: le migrazioni di avvio su un database {'vuoto' if giro == 1 else 'già migrato (riavvio)'}"
               + ("" if r.returncode == 0 else " — " + " | ".join(fine[-4:])))
finally:
    admin(f"DROP DATABASE IF EXISTS {NOME}")

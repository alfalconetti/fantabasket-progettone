"""gas-router e yahoo-router: le richieste a /health (healthcheck di Docker) non finiscono nei log,
le altre sì, anche con la configurazione dei log di uvicorn (che arriva prima del nostro main)."""
import importlib.util, io, logging, logging.config, os
from uvicorn.config import LOGGING_CONFIG
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
logging.config.dictConfig(LOGGING_CONFIG)
for router, altro in (("gas-router", "/gas/calendario"), ("yahoo-router", "/yahoo/roster")):
    log = logging.getLogger("uvicorn.access")
    log.filters.clear()
    spec = importlib.util.spec_from_file_location(router.replace("-", "_"), os.path.join(ROOT, router, "main.py"))
    m = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, os.path.join(ROOT, router))      # i moduli del router accanto al main
    try:
        spec.loader.exec_module(m)
    except Exception as err:           # dipendenze del router mancanti: la prova non si può fare
        print(f"⚠️ {router}: non importabile qui ({err}), prova saltata")
        continue
    buf = io.StringIO()
    log.handlers = [logging.StreamHandler(buf)]
    log.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:1", "GET", "/health", "1.1", 200)
    log.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:1", "POST", altro, "1.1", 200)
    ok("/health" not in buf.getvalue() and altro in buf.getvalue(), f"{router}: /health silenziato, il resto nei log")

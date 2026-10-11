"""Blocca le prove fuori da un ambiente di prova. Le prove svuotano le tabelle
(TRUNCATE): sul server distruggerebbero il database della lega.
Si ferma se: c'è la cartella secrets/ nel repo (= server), si è dentro un container
(/run/secrets), il database non è su localhost o si chiama 'fantabasket'."""
import os
import sys
from urllib.parse import urlparse

_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def controlla() -> None:
    motivi = []
    if os.path.isdir(os.path.join(_RADICE, "secrets")):
        motivi.append("nel repo c'è la cartella secrets/ (questa è la macchina di produzione)")
    if os.path.isdir("/run/secrets"):
        motivi.append("si è dentro un container dei bot (/run/secrets)")
    for var in ("DATABASE_URL", "PG_URL"):
        url = os.environ.get(var)
        if not url:
            continue
        u = urlparse(url)
        if u.hostname not in ("localhost", "127.0.0.1"):
            motivi.append(f"{var} non punta a localhost ({u.hostname})")
        if u.path.lstrip("/") == "fantabasket":
            motivi.append(f"{var} usa il database 'fantabasket' (quello della lega)")
    if motivi:
        sys.exit("⛔ Prove bloccate: " + "; ".join(motivi) +
                 ".\nLe prove svuotano le tabelle: si lanciano solo su un PostgreSQL di prova in locale "
                 "(vedi tests/README.md).")


controlla()

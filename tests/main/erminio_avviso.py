import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.1.0 (Luca, 05/11): con /data_erminio il GM della squadra che ha il giocatore riceve le posizioni nuove e la
scadenza del cambio Erminio; niente se svincolato o se la finestra è chiusa."""
import asyncio, types
from datetime import date, timedelta
import database as db
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from handlers import posizioni as PO


def gioc(nome, team=None):
    gid = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES (%s, %s, %s) RETURNING id", (nome, nome, nome.lower()))
    if team:
        db._q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) "
              "VALUES (%s, %s, 5, 2, '2026', 'normale', TRUE)", (gid, team))
    db._q("INSERT INTO posizioni_eleggibili (giocatore_id, posizioni, fonte, timestamp) VALUES (%s, 'PG', 'yahoo', NOW() - INTERVAL '30 days')", (gid,))
    db._q("INSERT INTO posizioni_eleggibili (giocatore_id, posizioni, fonte) VALUES (%s, 'PG,SG', 'yahoo')", (gid,))
    return gid


def pulisci():
    for t in ("contratti", "posizioni_eleggibili", "transazioni"):
        db._q(f"DELETE FROM {t} WHERE giocatore_id IN (SELECT id FROM giocatori WHERE nome_bref LIKE 'Erminio %%')")
    db._q("DELETE FROM giocatori WHERE nome_bref LIKE 'Erminio %%'")


pulisci()
gioc("Erminio Uno", "team01"); gioc("Erminio Due")
mandati, risposte = [], []


class Bot:
    async def send_message(self, chat_id, text, **k):
        if "Erminio</b>: Yahoo" in text:              # solo gli avvisi ai GM (il registro scrive anche sul canale log)
            mandati.append((chat_id, text))


class Msg:
    async def reply_text(self, t, **k): risposte.append(t)


def comando(args):
    mandati.clear()
    u = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=900, full_name="Admin", username=None), effective_message=Msg(),
                              effective_chat=types.SimpleNamespace(type="private", id=900))
    asyncio.run(PO.cmd_data_erminio(u, types.SimpleNamespace(args=args, bot=Bot())))


ieri = date.today() - timedelta(days=1)
comando(["Erminio", "Uno", ieri.strftime("%d/%m/%Y")])
fino = (ieri + timedelta(days=14)).strftime("%d/%m/%Y")
ok(sorted(c for c, _ in mandati) == [101, 111] and all("SG" in t and fino in t and "/cambio_ruolo" in t for _, t in mandati),
   "i GM della squadra avvisati: posizione nuova, scadenza, come fare")
ok("Avvisato il GM" in risposte[-1], "e l'admin lo sa")
comando(["Erminio", "Due", ieri.strftime("%d/%m/%Y")])
ok(mandati == [], "svincolato: nessun avviso")
comando(["Erminio", "Uno", (date.today() - timedelta(days=20)).strftime("%d/%m/%Y")])
ok(mandati == [], "finestra di 14 giorni già chiusa: nessun avviso")
pulisci()

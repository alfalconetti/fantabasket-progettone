import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v5.10.0: /report_dati, la salute dei dati in un file Markdown."""
import asyncio, json, os, types
from datetime import date, datetime, timedelta, timezone
import database as db, settings, teams as tm
from handlers import report_dati as RD, admin_panel as AP
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio, rookie, richieste_admin RESTART IDENTITY CASCADE")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
S = settings.stagione_corrente()
T1, T2 = [t["id"] for t in tm.get_all_teams()[:2]]


def fase(f):
    g = json.load(open(os.environ["GLOBALS_PATH"])); g["fase"] = f; json.dump(g, open(os.environ["GLOBALS_PATH"], "w"))


def gioc(n, pos, team, ruolo=None, imp=5, anni=2, firma=None, tipo="normale", espn=True, nascita=True, scad=None):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm,espn_id,data_nascita) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                   (n, n, n.lower(), f"e{n}" if espn else None, date(2000, 1, 1) if nascita else None))
    if pos:
        db._q("INSERT INTO posizioni_eleggibili (giocatore_id, posizioni, fonte) VALUES (%s,%s,'prova')", (gid, pos))
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo,scadenza_10day) "
                 "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id", (gid, team, imp, anni, firma or S, tipo, scad))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,%s,%s)", (gid, team, S, c))
    db._q("INSERT INTO bref_stats (stagione, nome_bref, pts) VALUES (%s, %s, 10)", (S, n))
    if ruolo:
        db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_a,stagione,tipo) VALUES (%s,%s,%s,%s,'iniziale')", (gid, team, ruolo, S))
    return gid


db._q("DELETE FROM bref_stats WHERE stagione = %s", (S,))
for i, r in enumerate(["PG", "PG", "SG", "SG", "SF", "SF", "PF", "PF", "C", "C"]):
    gioc(f"Alfa{i}", r, T1, r)
gioc("Senza Espn", "SF", T2, "SF", espn=False)
gioc("Senza Pos", None, T2, "PG")
gioc("Senza Ruolo", "C", T2)
gioc("Fuori Ruolo", "PG", T2, "C")
gioc("Vecchio", "SF", T2, "SF", anni=1, firma=str(int(S) - 2))
gioc("Zero", "SF", T2, "SF", anni=1, firma=str(int(S) - 1))
gioc("Corto", "PF", T2, "PF", imp=25, anni=1)
gioc("Dieci", "C", T2, "C", imp=0, tipo="10day", scad=datetime.now(timezone.utc) - timedelta(days=5))
gioc("Senza Nascita", "PF", T2, "PF", nascita=False)
mai = gioc("Mai Bref", "PF", T2, "PF")
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Mai Bref'")

fase("regular-season-fa")
md = RD.report()
sez = lambda titolo: md.split(f" {titolo}\n", 1)[1].split("\n## ", 1)[0]
ok(md.startswith(f"# Controllo dei dati — stagione {S}") and "## Riepilogo" in md, "intestazione e riepilogo")
ok("Senza Espn" in sez("Senza id ESPN (i loro punti non contano)") and "Alfa0" not in sez("Senza id ESPN (i loro punti non contano)"),
   "senza id ESPN")
ok("Senza Pos" in sez("Senza posizioni eleggibili"), "senza posizioni eleggibili")
ok("Senza Ruolo" in sez("Senza ruolo (in stagione)") and "Dieci" not in sez("Senza ruolo (in stagione)"), "senza ruolo in stagione (il 10-day no)")
ok("| Fuori Ruolo | C | PG |" in sez("Ruolo non più tra le eleggibili"), "ruolo non più tra le eleggibili")
c = sez("Contratti da guardare")
reg = sez("Coerenza del registro (transazioni)")
ok("Vecchio" in reg and "Zero" in reg and "Vecchio" not in c, "contratti finiti ancora attivi: dalla coerenza (una volta sola)")
ok("Corto" not in c, "anni sotto il minimo per l'importo: non segnalati (rinnovi e contratti storici)")
ok("Dieci" in c and "scaduto il" in c and "importo non positivo" not in c.split("Dieci")[1].split("\n")[0], "10-day scaduto ancora attivo (importo 0 normale)")
ok("Senza Nascita" in sez("Senza data di nascita"), "senza data di nascita")
ok("Mai Bref" in sez("Mai visti su basketball-reference") and "Alfa0" not in sez("Mai visti su basketball-reference"), "mai visti su bref")
ok("| Senza id ESPN (i loro punti non contano) | ⚠️ 1 |" in md and "| Coerenza del registro (transazioni) | ⚠️" in md,
   "riepilogo con ✅ e ⚠️ per controllo")
ok(f"| {tm.get_team_by_id(T1)['nome']} |" not in sez("Minimi dei ruoli impossibili (4 G, 4 F, 2 C)"), "squadra in regola non tra i minimi impossibili")
fase("offseason-rinnovi")
md2 = RD.report()
ok("Senza ruolo (in stagione)" not in md2, "nei rinnovi: niente «senza ruolo»")
fase("regular-season-fa")

class Bot:
    def __init__(s): s.doc = []
    async def send_document(s, chat_id, document, filename, caption=None, **k): s.doc.append((filename, document.getvalue()))
BOT = Bot()
CTX = types.SimpleNamespace(bot=BOT, args=[])
ADMIN = int(settings.admin_ids()[0])
u = lambda uid: types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid), effective_chat=types.SimpleNamespace(id=uid))
asyncio.run(RD.cmd_report_dati(u(999999), CTX))
asyncio.run(RD.cmd_report_dati(u(ADMIN), CTX))
ok(len(BOT.doc) == 1 and BOT.doc[0][0].startswith("dati-") and b"## Riepilogo" in BOT.doc[0][1], "/report_dati: solo admin, file .md")
ok("rdati:md" in [b.callback_data for r in AP._kb_admin_home().inline_keyboard for b in r], "«🩺 Controllo dati» nel pannello admin")
db._q("TRUNCATE giocatori, contratti, transazioni RESTART IDENTITY CASCADE")
db._q("DELETE FROM bref_stats WHERE stagione = %s", (S,))

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v5.9.0: /report_ruoli, i ruoli di tutte le squadre in un file Markdown (riepilogo, minimi, note)."""
import asyncio, json, os, types
from datetime import datetime, timedelta, timezone
import database as db, settings, teams as tm
from handlers import report_ruoli as RR, ruoli as RU
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio, rookie, richieste_admin RESTART IDENTITY CASCADE")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
S = settings.stagione_corrente()
T1, T2, T3 = [t["id"] for t in tm.get_all_teams()[:3]]


def gioc(n, pos, team, ruolo=None, tipo="normale"):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    db._q("INSERT INTO posizioni_eleggibili (giocatore_id, posizioni, fonte) VALUES (%s,%s,'prova')", (gid, pos))
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                 "VALUES (%s,%s,5,2,%s,%s) RETURNING id", (gid, team, S, tipo))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,%s,%s)", (gid, team, S, c))
    if ruolo:
        db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_a,stagione,tipo) VALUES (%s,%s,%s,%s,'iniziale')", (gid, team, ruolo, S))
    return gid


# T1 in regola: 4 guardie, 4 ali, 2 centri (+ un 10-day e una Saedro in corso)
for i, r in enumerate(["PG", "PG", "SG", "SG", "SF", "SF", "PF", "PF", "C", "C"]):
    g = gioc(f"Alfa {r}{i} | pipe", r, T1, r)
dieci = gioc("Alfa Dieci", "C", T1, "C", tipo="10day")
sae = gioc("Alfa Saedro", "SF,PF", T1)
db._q("INSERT INTO cambi_ruolo (giocatore_id,team_id,ruolo_a,stagione,tipo,scadenza) VALUES (%s,%s,'PF',%s,'saedro',%s)",
      (sae, T1, S, datetime.now(timezone.utc) + timedelta(days=5)))
# T2: un solo centro e due giocatori senza ruolo che possono fare C → 🟡
for i, r in enumerate(["PG", "PG", "SG", "SG", "SF", "SF", "PF", "PF", "C"]):
    gioc(f"Beta {r}{i}", r, T2, r)
senza = gioc("Beta Senza", "PF,C", T2)
db._q("INSERT INTO ruoli_pendenti (giocatore_id, team_id, origine, riferimento, scadenza) VALUES (%s,%s,'firma','prova',%s)",
      (senza, T2, datetime.now(timezone.utc) + timedelta(hours=30)))
db._q("INSERT INTO ruoli_bozze (giocatore_id, team_id, stagione, ruolo) VALUES (%s,%s,%s,'C')", (senza, T2, S))
fuori = gioc("Beta Fuori", "PG", T2, "SG")      # ruolo non più tra le eleggibili
# T3: tutte guardie → ❌
for i in range(10):
    gioc(f"Gamma PG{i}", "PG", T3, "PG")

md = RR.report()
ok(md.startswith(f"# Report ruoli — stagione {S}") and "Minimi: 4 guardie (PG/SG), 4 ali (SF/PF), 2 centri (C)" in md,
   "intestazione con stagione, fase, ora e minimi da settings.json")
riga = lambda nome: next(l for l in md.splitlines() if l.startswith(f"| {nome} |"))
n1, n2, n3 = (tm.get_team_by_id(x)["nome"] for x in (T1, T2, T3))
ok("| 4/4 | 5/4 | 2/2 |" in riga(n1) and "✅ rispettati" in riga(n1), "riepilogo: squadra in regola (il 10-day non conta)")
ok("🟡 da completare" in riga(n2) and "| 1 | 1 |" in riga(n2), "riepilogo: senza ruolo che può coprire il centro → 🟡, una in sospeso")
ok("❌ mancano 6" in riga(n3) and "| 10/4 | 0/4 | 0/2 |" in riga(n3), "riepilogo: tutte guardie → ❌ mancano 6")
ok(f"1/{len(tm.get_all_teams())}** squadre rispettano i minimi" in md, "conteggio in cima")
ok("| C | Alfa Dieci | C | 10-day (non conta per i minimi) |" in md, "nota: 10-day")
ok("Alfa Saedro | PF, SF |" not in md and "| PF | Alfa Saedro | SF, PF | Saedro fino al" in md, "nota: Saedro in corso")
ok("| ❔ | Beta Senza | PF, C | da dichiarare entro" in md and "bozza C non confermata" in md, "nota: senza ruolo, in sospeso con la scadenza, bozza")
ok("SG non è più tra le eleggibili" in md, "nota: ruolo fuori dalle eleggibili")
ok("Alfa PG0 \\| pipe" in md, "il carattere | dei nomi non rompe le tabelle")
ok(md.count(f"\n## ") == len(tm.get_all_teams()) + 1, "una sezione per ogni squadra (anche quelle col roster vuoto)")

# comando e bottone: solo admin, manda un .md
class Bot:
    def __init__(s): s.doc = []
    async def send_document(s, chat_id, document, filename, caption=None, **k): s.doc.append((chat_id, filename, document.getvalue()))
BOT = Bot()
CTX = types.SimpleNamespace(bot=BOT, args=[])
ADMIN = int(settings.admin_ids()[0])
u = lambda uid: types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid, first_name="Luca"),
                                      effective_chat=types.SimpleNamespace(id=uid))
asyncio.run(RR.cmd_report_ruoli(u(999999), CTX))
ok(not BOT.doc, "solo gli admin")
asyncio.run(RR.cmd_report_ruoli(u(ADMIN), CTX))
ok(BOT.doc and BOT.doc[0][1].startswith("ruoli-") and BOT.doc[0][1].endswith(".md") and b"## Riepilogo" in BOT.doc[0][2],
   "/report_ruoli: file .md")
kb = []
class Q:
    data, from_user = "rrep:md", types.SimpleNamespace(id=ADMIN, first_name="Luca")
    message = types.SimpleNamespace(chat_id=ADMIN)
    async def answer(s, *a, **k): pass
    async def edit_message_text(s, t, **k): kb.append(k.get("reply_markup"))
asyncio.run(RR.cb_report_ruoli(types.SimpleNamespace(callback_query=Q()), CTX))
ok(len(BOT.doc) == 2, "anche dal bottone")
asyncio.run(RU.cb_admin_lista(types.SimpleNamespace(callback_query=Q()), CTX))
ok("rrep:md" in [b.callback_data for r in kb[-1].inline_keyboard for b in r], "bottone «📄 Report ruoli (.md)» in «🎽 Ruoli squadre»")
db._q("TRUNCATE giocatori, contratti, transazioni RESTART IDENTITY CASCADE")

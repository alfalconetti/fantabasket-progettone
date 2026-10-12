import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v58 (main v3.11): x0 fuori da cap e slot, RFA dichiarati nel bot principale che pesano
sul cap, aste RFA aperte da sole nella fase RFA e proprietario allineato alle trade."""
import asyncio, json, os, types
import database as db, pg_client as pg
pg.init_pg(); db.init_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
pg.q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio, rfa_dichiarati RESTART IDENTITY CASCADE")


def fase(f, stagione="2027"):
    g = json.load(open(os.environ["GLOBALS_PATH"])); g["fase"] = f; g["stagione_corrente"] = stagione
    json.dump(g, open(os.environ["GLOBALS_PATH"], "w"))


def gioc(n, team, imp, anni, sf):
    gid = pg.q("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id",
               (n, n, n.lower()), one=True)["id"]
    cid = pg.q("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
               "VALUES (%s,%s,%s,%s,%s,'normale') RETURNING id", (gid, team, imp, anni, sf), one=True)["id"]
    pg.q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,%s,%s)",
         (gid, team, sf, cid))
    return gid, cid


fase("offseason-rinnovi")
a, ca = gioc("Arturo Rfa", "team01", 20, 1, "2026")      # x0 nel 2027
b, _ = gioc("Bruno Finito", "team02", 7, 1, "2026")       # x0 non dichiarato
c, _ = gioc("Carlo Corso", "team01", 10, 2, "2027")       # in corso
ok(pg.get_cap_contratti("team01") == 10 and pg.get_roster_count("team01") == 1, "x0 fuori da cap e slot (team01: 10M, 1 giocatore)")
ok(pg.get_cap_contratti("team02") == 0, "x0 non dichiarato: 0")
pg.q("INSERT INTO rfa_dichiarati (stagione,team_id,giocatore_id,contratto_id,da) VALUES ('2027','team01',%s,%s,'test')", (a, ca))
ok(pg.get_cap_contratti("team01") == 30 and pg.get_roster_count("team01") == 1, "RFA dichiarato: pesa sul cap (30M), non sullo slot")


class Msg:
    message_id = 77


class Bot:
    username = "astebot"
    def __init__(self): self.out = []; self.edit = []
    async def send_message(self, chat_id=None, text=None, **k): self.out.append((chat_id, text)); return Msg()
    async def edit_message_text(self, *a, **k): self.edit.append(k)


from handlers.rfa import job_rfa
bot = Bot(); ctx = types.SimpleNamespace(bot=bot)
asyncio.run(job_rfa(ctx))
ok(not db.aste_rfa_in_corso(), "fuori dalla fase RFA: nessuna asta aperta")
fase("offseason-rfa")
asyncio.run(job_rfa(ctx))
aste = db.aste_rfa_in_corso()
ok(len(aste) == 1 and (aste[0]["giocatore"], aste[0]["squadra_proprietaria"], aste[0]["vecchio_compenso"], aste[0]["giocatore_id"])
   == ("Arturo Rfa", "team01", 20, a), "fase RFA: asta aperta da sola per il dichiarato (proprietario, vecchio contratto, id)")
ok(any(ch == -10 and "Arturo Rfa" in t for ch, t in bot.out) and aste[0]["canale_msg_id"] == 77, "pubblicata sul canale")
ok(set(db.get_watchers(aste[0]["id"])) == {101, 111} and any(ch == 101 for ch, _ in bot.out), "i GM del proprietario la seguono e sono avvisati")
asyncio.run(job_rfa(ctx))
ok(len(db.aste_rfa_in_corso()) == 1, "giro dopo: nessun doppione")

# trade durante l'asta: il contratto x0 passa a team03 → i diritti passano a team03
pg.q("UPDATE contratti SET team_id='team03' WHERE id=%s", (ca,))
bot.out.clear(); asyncio.run(job_rfa(ctx))
ok(db.get_asta(aste[0]["id"])["squadra_proprietaria"] == "team03" and bot.edit and any(ch == -30 for ch, _ in bot.out),
   "RFA scambiato: proprietario dell'asta allineato, canale aggiornato, avviso nel log")
# fine asta: contratto chiuso e firma del vincitore (in corso) → il proprietario non cambia più
pg.q("UPDATE contratti SET attivo=FALSE WHERE id=%s", (ca,))
pg.q("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,'team04',25,2,'2027','normale')", (a,))
asyncio.run(job_rfa(ctx))
ok(db.get_asta(aste[0]["id"])["squadra_proprietaria"] == "team03", "contratto nuovo del vincitore: ignorato")
ok(pg.get_cap_contratti("team03") == 0, "dopo l'asta la dichiarazione non pesa più")

# v61: cap e slot da shared/cap.py anche qui. DPE dopo la deadline: importo ridotto, lo slot resta
pg.q("INSERT INTO dpe (giocatore_id,team_id,stagione,importo_originale,importo_dpe,pre_deadline) VALUES (%s,'team01','2027',10,7,FALSE)", (c,))
ok(pg.get_cap_contratti("team01") == 7 and pg.get_roster_count("team01") == 1, "DPE dopo la deadline: cap ridotto, slot occupato")
pg.q("UPDATE dpe SET pre_deadline = TRUE WHERE giocatore_id = %s", (c,))
ok(pg.get_cap_contratti("team01") == 7 and pg.get_roster_count("team01") == 0, "DPE prima della deadline: slot liberato")

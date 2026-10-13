import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v65: quando qualcosa si decide d'ufficio perché è scaduto il tempo (3 anni di penale nella firma
FA, anni minimi RFA, pareggio non deciso), l'annuncio sul canale principale lo dice."""
import asyncio, types
import database as db, pg_client as pg
from datetime import datetime, timezone, timedelta
pg.init_pg(); db.init_db()
pg.q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
canale = []
class Bot:
    username = "bot"
    async def send_message(self, chat_id=None, text="", **k):
        if chat_id == -1:
            canale.append(text)
        return types.SimpleNamespace(message_id=1)
    async def edit_message_text(self, *a, **k): pass
def ctx(aid=None):
    return types.SimpleNamespace(bot=Bot(), job=types.SimpleNamespace(data={"asta_id": aid}), job_queue=None)
ora = datetime.now(timezone.utc)
for n in ("Kevin Durant", "Gioc Prova Due", "Gioc Prova Tre"):
    pg.q("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s)", (n, n, n.lower()))
import handlers.firma as F

# FA: il vincitore non sceglie gli anni → 3 anni di penale, e il canale lo dice
aid = db.crea_asta(tipo="FA", giocatore="Kevin Durant", squadra_proprietaria=None, creata_at=ora.isoformat(), scade_at=ora.isoformat())
db.aggiorna_offerta(aid, "team01", 5, ora.isoformat())
db.chiudi_asta(aid, ora.isoformat())
asyncio.run(F.firma_automatica(ctx(aid)))
aid_fa = aid
t = canale[-1] if canale else ""
ok("5M × 3 anni" in t and "⏰ <i>Tempo scaduto: il vincitore non ha scelto gli anni: 3 anni d'ufficio (penale)</i>" in t,
   f"FA, anni non scelti: sul canale 3 anni e tempo scaduto\n{t}")

# FA scelta in tempo: niente nota
canale.clear()
aid = db.crea_asta(tipo="FA", giocatore="Gioc Prova Due", squadra_proprietaria=None, creata_at=ora.isoformat(), scade_at=ora.isoformat())
db.aggiorna_offerta(aid, "team01", 3, ora.isoformat())
db.chiudi_asta(aid, ora.isoformat())
asyncio.run(F._registra_firma_finale(ctx(aid), aid, 2, "team01"))
ok(canale and "Tempo scaduto" not in canale[-1], "anni scelti in tempo: niente nota")

# RFA: anni minimi d'ufficio e pareggio non deciso → entrambe le note
canale.clear()
aid = db.crea_asta(tipo="RFA", giocatore="Gioc Prova Tre", squadra_proprietaria="team02", creata_at=ora.isoformat(),
                   scade_at=ora.isoformat(), vecchio_compenso=0)
db.aggiorna_offerta(aid, "team01", 22, ora.isoformat())
db.chiudi_asta(aid, (ora - timedelta(days=3)).isoformat())
db.set_anni_offerti(aid, 2, automatici=True)
import handlers.firma_pareggio as FP
asyncio.run(FP.pareggio_automatico(ctx(aid)))
t = next((x for x in canale if "non pareggia" in x), "")
ok("il vincitore non ha scelto gli anni: minimi per fascia d'ufficio" in t
   and "il proprietario non ha deciso entro il termine: niente pareggio" in t,
   f"RFA: anni minimi e pareggio scaduto, tutti e due sul canale\n{t}")
import utils
TM = {"team01": "Alfa", "team02": "Beta"}
m = utils.build_canale_message(db.get_asta(aid_fa), [], TM)
ok("5M × 3 anni — Alfa" in m and "⏰ <i>Tempo scaduto: il vincitore non ha scelto gli anni: 3 anni d'ufficio (penale)</i>" in m,
   f"messaggio dell'asta sul canale aste: tempo scaduto anche lì\n{m}")
m = utils.build_canale_message(db.get_asta(aid), [], TM)
ok("22M × 2 anni — Alfa</b>" in m and m.count("Tempo scaduto") == 2 and "(pareggio)" not in m, "RFA andata al vincitore: messaggio dell'asta con le note")

# RFA in attesa di pareggio con anni d'ufficio: già nel messaggio dell'asta
aid2 = db.crea_asta(tipo="RFA", giocatore="Gioc Prova Quattro", squadra_proprietaria="team02", creata_at=ora.isoformat(),
                    scade_at=ora.isoformat(), vecchio_compenso=0)
db.aggiorna_offerta(aid2, "team01", 12, ora.isoformat())
db.chiudi_asta(aid2, ora.isoformat())
db.set_anni_offerti(aid2, 1, automatici=True)
m = utils.build_canale_message(db.get_asta(aid2), [], TM)
ok("IN ATTESA DI PAREGGIO" in m and "Tempo scaduto: il vincitore non ha scelto gli anni" in m, "in attesa di pareggio: anni d'ufficio segnalati")

# il proprietario pareggia: il messaggio dell'asta dice lui, all'importo del pareggio, senza note
pg.q("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES ('Gioc Prova Quattro','Gioc Prova Quattro','gioc prova quattro')")
canale.clear()
asyncio.run(F._registra_firma_finale(ctx(aid2), aid2, 2, "team02", importo_override=13, pareggiato=True))
m = utils.build_canale_message(db.get_asta(aid2), [], TM)
ok("13M × 2 anni — Beta (pareggio)" in m and "Tempo scaduto" not in m and "Beta pareggia" in canale[-1],
   f"pareggio: chi firma davvero e a quanto (prima diceva il vincitore e l'offerta)\n{m}")

# RFA senza offerte: il proprietario rifirma, non "pareggia"
aid3 = db.crea_asta(tipo="RFA", giocatore="Gioc Prova Tre", squadra_proprietaria="team02", creata_at=ora.isoformat(),
                    scade_at=ora.isoformat(), vecchio_compenso=0)
db.chiudi_asta(aid3, ora.isoformat())
canale.clear()
asyncio.run(F._registra_firma_finale(ctx(aid3), aid3, 1, "team02", importo_override=2, pareggiato=True))
m = utils.build_canale_message(db.get_asta(aid3), [], TM)
ok("rifirma" in canale[-1] and "pareggia" not in canale[-1] and "— Beta</b>" in m and "(pareggio)" not in m,
   "RFA senza offerte rifirmato dal proprietario: niente pareggio")
pg.q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")   # pulizia

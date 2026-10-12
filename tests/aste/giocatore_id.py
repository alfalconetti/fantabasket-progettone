import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v57: l'asta ricorda l'id del giocatore deciso all'apertura; la firma non riabbina più
per nome (che con un nome cambiato o un omonimo creava un giocatore nuovo)."""
import asyncio, types
import database as db, teams as tm, pg_client as pg
from datetime import datetime, timezone, timedelta
pg.init_pg(); db.init_db()
pg.q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio RESTART IDENTITY CASCADE")
ok=lambda c,m: print(("✅" if c else "❌ FAIL"), m)
gid=pg.q("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES ('Kevin Durant','Kevin Durant','kevin durant') RETURNING id",one=True)["id"]
import handlers.offerte as O
class Bot:
    username="bot"
    async def send_message(self,**k): return types.SimpleNamespace(message_id=1)
    async def edit_message_text(self,*a,**k): pass
ctx=types.SimpleNamespace(bot=Bot())
team=tm.get_team_by_id("team01")
aid,err=asyncio.run(O.apri_asta_fa(ctx, team, "Kevin Durant", 5, [101]))
ok(err is None and db.get_asta(aid)["giocatore_id"]==gid, f"apertura FA: id salvato ({gid})")
# il nome in anagrafica cambia dopo l'apertura (correzione con /dev_player)
pg.q("UPDATE giocatori SET nome_common='Kevin Wayne Durant', nome_norm='kevin wayne durant' WHERE id=%s",(gid,))
db.chiudi_asta(aid, datetime.now(timezone.utc).isoformat())
import handlers.firma as F
asyncio.run(F._registra_firma_finale(ctx, aid, 3, "team01"))
ok(pg.q("SELECT count(*) AS n FROM giocatori",one=True)["n"]==1, "firma: nessun giocatore nuovo creato")
ok(pg.q("SELECT giocatore_id FROM contratti WHERE attivo AND team_id='team01'",one=True)["giocatore_id"]==gid, "firma: contratto sul giocatore giusto")
# asta vecchia senza id: si ricade sul nome, senza creare niente se non c'è
vecchia=db.crea_asta(tipo="FA",giocatore="Nessuno Esiste",squadra_proprietaria=None,creata_at="x",scade_at="x")
ok(pg.id_giocatore_asta(db.get_asta(vecchia)) is None and pg.q("SELECT count(*) AS n FROM giocatori",one=True)["n"]==1, "asta senza id: ricerca per nome, nessuna creazione")

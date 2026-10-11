import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types
from datetime import datetime, timezone, timedelta
import database as db, teams as tm
db.init_db()
from handlers.offerte import _esegui_offerta, _check_partecipazione
class Bot:
    username="b"
    async def send_message(self, chat_id, text, **k): return types.SimpleNamespace(message_id=1)
    async def edit_message_text(self, *a, **k): pass
async def main():
    now=datetime.now(timezone.utc)
    aid=db.crea_asta(tipo="RFA", giocatore="Jalen Williams", squadra_proprietaria="team01", vecchio_compenso=10,
                     creata_at=now.isoformat(), scade_at=(now+timedelta(hours=18)).isoformat(), stagione="2026")
    t=tm.get_team_by_id("team01")
    print("deep link (_check_partecipazione):", _check_partecipazione(t, dict(db.get_asta(aid))))
    ctx=types.SimpleNamespace(bot=Bot(), job_queue=None)
    try:
        err=await _esegui_offerta(ctx, t, aid, 3, 101)
    except Exception as e:
        err=f"(eccezione dopo la registrazione: {type(e).__name__})"
    a=db.get_asta(aid)
    print("/offerta (_esegui_offerta):", err, "| miglior offerente ora:", a["offerente_team_id"], a["offerta_corrente"])
    assert err and a["offerente_team_id"] is None, "il proprietario non deve poter offrire sul proprio RFA"
    print("✅ rfa_proprietario")
asyncio.run(main())

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
import asyncio, types
from datetime import datetime, timezone
import database as db, teams as tm
db.init_db()
from handlers.offerte import _cap_libero, apri_asta_fa
class Bot:
    username="b"
    async def send_message(self, chat_id, text, **k): return types.SimpleNamespace(message_id=1)
async def main():
    t=tm.get_team_by_id("team01")
    print("cap libero iniziale:", _cap_libero("team01"), "slot virt:", db.get_slot_virtuali("team01"))
    aid,err=await apri_asta_fa(types.SimpleNamespace(bot=Bot()), t, "LeBron James", 25, [101])
    print("asta aperta (APERTA):", _cap_libero("team01"), "slot virt:", db.get_slot_virtuali("team01"))
    db.chiudi_asta(aid, datetime.now(timezone.utc).isoformat())
    print("asta chiusa, firma non ancora fatta (CHIUSA):", _cap_libero("team01"), "slot virt:", db.get_slot_virtuali("team01"))
    aid2,err=await apri_asta_fa(types.SimpleNamespace(bot=Bot()), t, "Kevin Durant", 25, [101])
    print("seconda asta da 25M con lo stesso cap:", "APERTA" if aid2 else err)
    assert aid2 is None, "con il cap impegnato dall'asta chiusa la seconda non deve aprirsi"
    print("✅ cap_asta_chiusa")
asyncio.run(main())
import settings as _st
print(("✅" if _st.offerta_massima()==141 else "❌ FAIL"), f"offerta massima 150 − 9 = 141 ({_st.offerta_massima()})")

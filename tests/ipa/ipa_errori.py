import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server
"""Error handler comune (shared/dev_comune.py) di loucabot e IPanchinari: "Message is not modified"
non arriva sul canale log; gli errori di rete solo lì (non al dev); gli altri errori al canale e al dev, con chi e quale bottone o comando."""
import asyncio, types
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
from shared import dev_comune
from telegram.error import BadRequest, TimedOut

ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
mandati, risposte = [], []
class Bot:
    async def send_message(self, chat_id, text): mandati.append((chat_id, text))
async def risp(): risposte.append(1)
def up(cb=None, testo=None):
    return types.SimpleNamespace(effective_user=types.SimpleNamespace(full_name="Alfa GM", id=7),
                                 callback_query=types.SimpleNamespace(data=cb, answer=risp) if cb else None,
                                 effective_message=types.SimpleNamespace(text=testo) if testo else None)
h = dev_comune.error_handler("IPanchinari", lambda: -3, lambda: 7)
ctx = lambda e: types.SimpleNamespace(error=e, bot=Bot())

asyncio.run(h(up("q:ok:team01:3"), ctx(BadRequest("Message is not modified: specified new message content and reply "
                                                  "markup are exactly the same as a current content and reply markup of the message"))))
ok(not mandati and risposte == [1], "bottone premuto due volte: niente sul canale log, il bottone smette di girare")
asyncio.run(h(up(), ctx(TimedOut())))
ok(len(mandati) == 1 and mandati[0][0] == -3 and "errore di rete" in mandati[0][1], "rete: sul canale log, non al dev")
mandati.clear()
asyncio.run(h(up("pb:ok:5"), ctx(ValueError("boh"))))
ok(len(mandati) == 2 and "bottone pb:ok:5" in mandati[0][1] and "Alfa GM (7)" in mandati[0][1],
   "errore vero: canale log e dev, con chi e quale bottone")
mandati.clear()
asyncio.run(h(up(testo="/quintetto_admin Alfa"), ctx(KeyError("x"))))
ok(mandati and "/quintetto_admin" in mandati[0][1] and "Alfa\n" not in mandati[0][1], "errore da comando: il comando, non il testo intero")

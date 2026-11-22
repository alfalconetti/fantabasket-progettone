import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# v7.25.0 (Luca, 22/11, mockup approvato): i «Quale?» a pagine e di chi ha cercato, la ricerca tra apici.
import asyncio, types
import database as db
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from telegram.ext import ApplicationHandlerStop
from shared import pagine as PG, parole_nome as PN, giocatore as G

# apici
ok(PN.verbatim("'Tim Hardaway'") == "Tim Hardaway" and PN.verbatim("’Tim Hardaway’") == "Tim Hardaway"
   and PN.verbatim("«Tim Hardaway»") == "Tim Hardaway" and PN.verbatim('"Tim Hardaway"') == "Tim Hardaway"
   and PN.verbatim("Tim Hardaway") is None and PN.verbatim("D'Angelo") is None and PN.verbatim("'D'Angelo Russell'") == "D'Angelo Russell",
   "apici: dritti, curvi, virgolette; un apostrofo nel nome non conta")
ok(not PN.identico("Tim Hardaway", "Tim Hardaway Jr.") and PN.identico("tim hardaway jr", "Tim Hardaway Jr.")
   and PN.identico("Nikola Jovic", "Nikola Jović") and not PN.identico("Hardaway Tim", "Tim Hardaway"),
   "identico: suffissi e ordine contano, accenti e maiuscole no")

# tastiera
voci = [(f"Gioc {i}" + (" ✅" if i < 3 else ""), f"pl:{i}") for i in range(20)]
k0, k2 = PG.tastiera(voci, 0), PG.tastiera(voci, 2)
ok(len(k0.inline_keyboard) == 9 and [b.callback_data for b in k0.inline_keyboard[-1]] == ["pg:x", "pg:x", "pg:1"]
   and [b.text for b in k0.inline_keyboard[-1]] == ["·", "1/3", "▶️"], "pagina 1: 8 nomi e «· 1/3 ▶️»")
ok(len(k2.inline_keyboard) == 5 and [b.callback_data for b in k2.inline_keyboard[-1]] == ["pg:1", "pg:x", "pg:x"], "ultima pagina: 4 nomi e «◀️ 3/3 ·»")
ok(PG.testo_pagina("Quale?", voci, 1) == "Quale? 20 giocatori, prima quelli a roster ✅ · pagina 2 di 3"
   and PG.testo_pagina("Quale?", voci[:8]) == "Quale?" and len(PG.tastiera(voci[:8]).inline_keyboard) == 8,
   "fino a 8: come prima, senza frecce né conteggio")

# manda, guardia, frecce
class Msg:
    def __init__(s, uid): s.from_user, s.chat_id, s.message_id, s.inviati = types.SimpleNamespace(id=uid, first_name="Marco"), -5, None, []
    async def reply_text(s, t, **k):
        s.inviati.append((t, k)); return types.SimpleNamespace(chat_id=-5, message_id=77)
ctx = types.SimpleNamespace(bot_data={}, user_data={})
m = Msg(1)
asyncio.run(PG.manda(m, ctx, voci))
ok(m.inviati[-1][0].startswith("Quale? 20 giocatori") and (-5, 77) in ctx.bot_data["quale"], "manda: prima pagina e registro del messaggio")
avvisi, mod = [], []
class Q:
    def __init__(s, uid, data): s.from_user, s.data, s.message = types.SimpleNamespace(id=uid), data, types.SimpleNamespace(chat_id=-5, message_id=77)
    async def answer(s, t=None, **k): avvisi.append(t)
    async def edit_message_text(s, t, **k): mod.append((t, k.get("reply_markup")))
try:
    asyncio.run(PG.guardia(types.SimpleNamespace(callback_query=Q(2, "pl:4")), ctx)); fermato = False
except ApplicationHandlerStop:
    fermato = True
ok(fermato and avvisi[-1] == "È la ricerca di Marco: fai la tua.", "guardia: un altro preme un nome del «Quale?» di Marco: avviso e stop")
try:
    asyncio.run(PG.guardia(types.SimpleNamespace(callback_query=Q(1, "pl:4")), ctx)); fermato = False
except ApplicationHandlerStop:
    fermato = True
ok(not fermato, "guardia: chi ha cercato passa")
_q = Q(1, "pg:2"); _q.message = types.SimpleNamespace(chat_id=-5, message_id=77)
asyncio.run(PG.cb_pagina(types.SimpleNamespace(callback_query=_q), ctx))
ok(mod and mod[-1][0].endswith("pagina 3 di 3") and mod[-1][1].inline_keyboard[0][0].callback_data == "pl:16", "frecce: pagina 3 nello stesso messaggio")
asyncio.run(PG.cb_pagina(types.SimpleNamespace(callback_query=Q(1, "pg:1")), types.SimpleNamespace(bot_data={})))
ok(avvisi[-1] == "Ricerca scaduta: rifalla.", "frecce dopo un riavvio: ricerca scaduta")

# ricerca tra apici e niente tetto, sui giocatori veri
for n in ("Tim Provaway", "Tim Provaway Jr.") + tuple(f"Paginato {i:02d}" for i in range(12)):
    db._q("DELETE FROM giocatori WHERE nome_common = %s", (n,))
    db._q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES (%s, %s, %s)", (n, n, n.lower()))
ok({g["nome_common"] for g in G.cerca("Tim Provaway")} == {"Tim Provaway", "Tim Provaway Jr."}
   and [g["nome_common"] for g in G.cerca("'Tim Provaway'")] == ["Tim Provaway"], "/player: tra apici solo il nome esatto, senza Jr.")
ok(len(G.cerca("Paginato")) == 12, "cerca: tutti i giocatori (prima 8), il «Quale?» va a pagine")
ok([g["nome_common"] for g in db.cerca_giocatori("'tim provaway'")] == ["Tim Provaway"], "bot principale: cerca_giocatori tra apici")
from handlers.posizioni import _cerca_giocatori
_c, _e = _cerca_giocatori("'Tim Provaway Jr.'")
ok(_e and [g["nome_common"] for g in _c] == ["Tim Provaway Jr."], "/set_posizioni e /carriera: tra apici")
for n in ("Tim Provaway", "Tim Provaway Jr.") + tuple(f"Paginato {i:02d}" for i in range(12)):
    db._q("DELETE FROM giocatori WHERE nome_common = %s", (n,))

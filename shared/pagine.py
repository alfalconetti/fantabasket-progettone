"""
I «Quale?» a pagine e di chi ha cercato (v7.25.0, Luca 22/11, mockup approvato).

Pagine («se supera il limite andrebbe messo pagine»): prima ogni bot tagliava la lista dei giocatori trovati a 8 (o 5)
senza dirlo, e dove non c'era un tetto Telegram avrebbe rifiutato la tastiera (circa 100 bottoni al massimo). Ora 8 per
pagina, sotto la riga «◀️ · 1/4 · ▶️», in cima quanti sono e la pagina; fino a 8 come prima, senza frecce. Le frecce
cambiano pagina nello stesso messaggio (callback «pg:<pagina>»).

Di chi ha cercato (Luca, 22/11: «e se la tastiera viene usata da uno che non è l'utente che ha cercato su un
gruppo?»): ogni «Quale?» mandato con `manda` è segnato col suo messaggio; `guardia` (gruppo -1, prima di tutti gli
altri handler) ferma i bottoni premuti da un altro con un avviso. Così anche il periodo di /rendimento e /situazione,
salvato per chi ha cercato, non si perde. Il registro è in memoria (bot_data, gli ultimi MAX_MESSAGGI): dopo un
riavvio i vecchi «Quale?» tornano liberi e le frecce dicono «rifai la ricerca».

Uso: `await manda(msg, context, voci, "Quale?")` con voci = [(etichetta, callback_data)]; per cambiare un «Quale?»
già mandato (es. il secondo nome di /confronto) `await modifica(q, context, voci, testo)`. Il bot registra
`handlers()`: la guardia (group=-1) e le frecce.
"""
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K

PER_PAGINA = 8
MAX_MESSAGGI = 500
CHIAVE = "quale"


def _pagine(voci: list) -> int:
    return max(1, -(-len(voci) // PER_PAGINA))


def tastiera(voci: list, pagina: int = 0) -> K:
    tot = _pagine(voci)
    righe = [[B(e, callback_data=c)] for e, c in voci[pagina * PER_PAGINA:(pagina + 1) * PER_PAGINA]]
    if tot > 1:
        righe.append([B("◀️", callback_data=f"pg:{pagina - 1}") if pagina > 0 else B("·", callback_data="pg:x"),
                      B(f"{pagina + 1}/{tot}", callback_data="pg:x"),
                      B("▶️", callback_data=f"pg:{pagina + 1}") if pagina < tot - 1 else B("·", callback_data="pg:x")])
    return K(righe)


def testo_pagina(testo: str, voci: list, pagina: int = 0) -> str:
    if len(voci) <= PER_PAGINA:
        return testo
    roster = ", prima quelli a roster ✅" if any("✅" in e for e, _ in voci) else ""
    return f"{testo} {len(voci)} giocatori{roster} · pagina {pagina + 1} di {_pagine(voci)}"


def _registro(context) -> dict:
    bd = getattr(context, "bot_data", None)
    return bd.setdefault(CHIAVE, {}) if bd is not None else {}


def _segna(context, m, voci, testo, utente) -> None:
    if getattr(m, "chat_id", None) is None or getattr(m, "message_id", None) is None:
        return                                         # niente messaggio vero (prove): niente registro
    reg = _registro(context)
    while len(reg) >= MAX_MESSAGGI:
        reg.pop(next(iter(reg)))
    reg[(m.chat_id, m.message_id)] = {"voci": voci, "testo": testo, "utente": getattr(utente, "id", None),
                                      "nome": getattr(utente, "first_name", None) or "un altro"}


def _pulite(voci) -> list[tuple[str, str]]:
    return [(str(e), str(c)[:64]) for e, c in voci]


async def manda(msg, context, voci: list[tuple[str, str]], testo: str = "Quale?", utente=None):
    """Manda il «Quale?» (prima pagina) in risposta a `msg` e lo segna come di chi ha cercato."""
    voci = _pulite(voci)
    m = await msg.reply_text(testo_pagina(testo, voci), reply_markup=tastiera(voci))
    _segna(context, m, voci, testo, utente or getattr(msg, "from_user", None))
    return m


async def modifica(q, context, voci: list[tuple[str, str]], testo: str = "Quale?"):
    """Cambia un «Quale?» già mandato (stesso messaggio, stesso padrone)."""
    voci = _pulite(voci)
    await q.edit_message_text(testo_pagina(testo, voci), reply_markup=tastiera(voci))
    _segna(context, q.message, voci, testo, q.from_user)


async def guardia(update, context):
    """Prima di ogni bottone: se è un «Quale?» di un altro, avviso e basta."""
    from telegram.ext import ApplicationHandlerStop
    q = update.callback_query
    if not q or not q.message:
        return
    x = _registro(context).get((q.message.chat_id, q.message.message_id))
    if x and x["utente"] and q.from_user and q.from_user.id != x["utente"]:
        await q.answer(f"È la ricerca di {x['nome']}: fai la tua.", show_alert=True)
        raise ApplicationHandlerStop


async def cb_pagina(update, context):
    q = update.callback_query
    val = q.data.split(":", 1)[1]
    if val == "x":
        await q.answer()
        return
    x = _registro(context).get((q.message.chat_id, q.message.message_id)) if q.message else None
    if not x:
        await q.answer("Ricerca scaduta: rifalla.", show_alert=True)
        return
    voci = x["voci"]
    pagina = max(0, min(int(val), _pagine(voci) - 1))
    await q.answer()
    await q.edit_message_text(testo_pagina(x["testo"], voci, pagina), reply_markup=tastiera(voci, pagina))


def handlers() -> list[tuple]:
    """[(handler, gruppo)]: la guardia prima di tutto, poi le frecce."""
    from telegram.ext import CallbackQueryHandler
    return [(CallbackQueryHandler(guardia), -1), (CallbackQueryHandler(cb_pagina, pattern=r"^pg:(x|-?\d+)$"), 0)]

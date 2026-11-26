"""
Archivio del foglio di controllo del calcolo a fine stagione (v7.36.0, deciso con Luca il 13/10 e il 26/11).

I tab «Calcolo GN» e «Calcolo PN» hanno lo stesso nome ogni stagione: senza archiviarli, il primo calcolo della
stagione nuova riscriverebbe «Calcolo G1» di quella vecchia. /archivia_calcolo (admin), dopo la finale dei playoff:
anteprima, conferma, poi il gas copia tutti i tab in un file nuovo («Calcolo 2026-27 · archivio») e li toglie dal
foglio di controllo. I calcoli restano comunque nel database (lega_calcoli, lega_calcoli_storico, /storico_calcolo).
Una volta per stagione (tabella lega_archivio_calcolo); callback arc:ok:<stagione>.
"""
import html
import logging

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.ext import CommandHandler, CallbackQueryHandler

import config
import db

logger = logging.getLogger(__name__)
e = lambda x: html.escape(str(x), quote=False)


def migra() -> None:
    db.q("""CREATE TABLE IF NOT EXISTS lega_archivio_calcolo (
              stagione  TEXT PRIMARY KEY,
              url       TEXT,
              tab       INT,
              chi       TEXT,
              quando    TIMESTAMPTZ NOT NULL DEFAULT NOW())""")


def anni(s: str) -> str:
    return f"{s}-{(int(s) + 1) % 100:02d}"


def stagione_da_archiviare() -> str | None:
    """La stagione dei tab che ci sono adesso: la prima con un calcolo e non ancora archiviata (finché non è archiviata, i
    tab della stagione dopo non si scrivono: blocco_tab)."""
    r = db.q("""SELECT min(c.stagione) AS s FROM lega_calcoli c
                WHERE NOT EXISTS (SELECT 1 FROM lega_archivio_calcolo a WHERE a.stagione = c.stagione)""", one=True)
    return r["s"] if r and r["s"] else None


def blocco_tab(stagione: str) -> str | None:
    """Il foglio di controllo ha ancora i tab di una stagione prima, non archiviata: scrivere «Calcolo G1» della stagione
    nuova li sovrascriverebbe. Il messaggio per l'admin, o None."""
    try:
        r = db.q("""SELECT max(c.stagione) AS s FROM lega_calcoli c WHERE c.stagione < %s
                    AND NOT EXISTS (SELECT 1 FROM lega_archivio_calcolo a WHERE a.stagione = c.stagione)""", (stagione,), one=True)
    except Exception:
        return None
    if r and r["s"]:
        return f"il foglio di controllo ha ancora i tab della stagione {anni(r['s'])}: prima /archivia_calcolo"
    return None


def nome_archivio(s: str) -> str:
    return f"Calcolo {anni(s)} · archivio"


def problemi(s: str) -> list[str]:
    """Perché non ancora: la stagione è quella in corso e i playoff non sono finiti."""
    from shared import playoff_base as PB
    if s == config.stagione():
        return PB.problemi_fine_stagione(s)
    return []


def anteprima(s: str) -> tuple[str, K | None]:
    giornate = db.q("SELECT giornata FROM lega_calcoli WHERE stagione = %s ORDER BY giornata", (s,), many=True) or []
    from shared import codici_giornata as CG
    nomi = [CG.codice(g["giornata"], s).split(" ")[0] for g in giornate]
    t = (f"📦 <b>Archivio del foglio di controllo · {anni(s)}</b>\n\n"
         f"I tab del calcolo ({len(nomi)}: {e(', '.join(nomi[:3]))}{'…' if len(nomi) > 3 else ''}"
         f"{' ' + e(nomi[-1]) if len(nomi) > 3 else ''}) vanno in un file nuovo, <b>{e(nome_archivio(s))}</b>, "
         "e si tolgono dal foglio di controllo: la stagione nuova riparte da «Calcolo G1» senza sovrascrivere niente.\n"
         "I calcoli restano nel bot (/storico_calcolo).")
    p = problemi(s)
    if p:
        return t + "\n\n⛔ <b>Non ancora</b>:\n• " + "\n• ".join(e(x) for x in p), None
    return t, K([[B("📦 Archivia e azzera", callback_data=f"arc:ok:{s}"), B("✖️ No", callback_data="arc:no")]])


async def esegui(s: str, chi: str, manda=None) -> dict:
    import foglio
    r = await foglio.manda_gas("calcolo_archivia", {"action": "calcolo_archivia", "archivio": nome_archivio(s), "azzera": True}, manda)
    if r.get("error"):
        raise RuntimeError(r["error"])
    db.q("INSERT INTO lega_archivio_calcolo (stagione, url, tab, chi) VALUES (%s, %s, %s, %s) ON CONFLICT (stagione) DO NOTHING",
         (s, r.get("url") or "", int(r.get("copiati") or 0), chi))
    return r


async def cmd_archivia_calcolo(update, context):
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    s = stagione_da_archiviare()
    if not s:
        r = db.q("SELECT * FROM lega_archivio_calcolo ORDER BY stagione DESC LIMIT 1", one=True)
        await msg.reply_text("Niente da archiviare." + (f" L'ultimo archivio: {anni(r['stagione'])}, {r['url']}" if r else ""))
        return
    t, kb = anteprima(s)
    await msg.reply_text(t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


async def cb_archivio(update, context):
    q = update.callback_query
    if not config.is_admin(q.from_user.id):
        await q.answer("Solo admin.", show_alert=True)
        return
    p = q.data.split(":")
    if p[1] == "no":
        await q.answer()
        await q.edit_message_text("Archivio annullato: il foglio di controllo resta com'è.")
        return
    s = p[2]
    if s != stagione_da_archiviare() or problemi(s):
        await q.answer("Non più valido: rifai /archivia_calcolo.", show_alert=True)
        return
    await q.answer("Archivio in corso…")
    chi = q.from_user.full_name or str(q.from_user.id)
    try:
        r = await esegui(s, chi)
    except Exception as err:
        logger.warning("Archivio del foglio di controllo %s: %s", s, err)
        await q.edit_message_text(f"❌ Archivio non riuscito, il foglio di controllo resta com'era: {e(str(err))[:300]}")
        return
    from registro import segna_sync
    from handlers import log
    segna_sync(q.from_user, "admin", "foglio di controllo archiviato", oggetto=f"stagione {anni(s)}",
               dopo=f"{r.get('copiati', 0)} tab in {nome_archivio(s)}, tolti dal foglio di controllo", nota=r.get("url") or None)
    await log(context.bot, f"📦 Foglio di controllo {anni(s)} archiviato da {e(chi)}: {r.get('copiati', 0)} tab → {r.get('url', '')}")
    await q.edit_message_text(f"✅ <b>Foglio di controllo {anni(s)} archiviato</b>: {r.get('copiati', 0)} tab nel file "
                              f"<a href=\"{e(r.get('url', ''))}\">{e(nome_archivio(s))}</a>, tolti dal foglio di controllo.",
                              parse_mode="HTML", disable_web_page_preview=True)


def get_handlers() -> list:
    return [CommandHandler("archivia_calcolo", cmd_archivia_calcolo), CallbackQueryHandler(cb_archivio, pattern=r"^arc:")]

"""
Basketball-Reference — job giornaliero e giocatori nuovi (v3.7.0).

Job (10:00, solo regular season e playoff), una sola richiesta alla pagina per_game:
- append in bref_stats per chi ha giocato (G aumentate);
- foglio BrefRaw sincronizzato con la tabella (formule del foglio collegate);
- messaggio sul canale log: giocatori aggiornati + 🔀 cambi squadra NBA;
- giocatori di bref non in anagrafica → messaggio al dev con ✅ Crea tutti / ❌ Ignora.
  L'elenco sta in bref_nuovi: i bottoni funzionano anche dopo un riavvio e gli
  ignorati non vengono riproposti. Accanto a ogni nome, gli eventuali giocatori già
  in anagrafica con un nome simile (per non creare doppioni).
"""
import asyncio
import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

import database as db
import settings
import nomi
from utils import normalizza
from settings import FASI_RUOLI_RS

logger = logging.getLogger(__name__)

MAX_RIGHE = 60


def _testo_nuovi() -> tuple[str, InlineKeyboardMarkup | None]:
    proposti = db._q("SELECT * FROM bref_nuovi WHERE stato = 'proposto' ORDER BY nome_bref", many=True) or []
    if not proposti:
        return "🆕 Nessun giocatore nuovo in attesa.", None
    anagrafica = db._q("SELECT id, nome_common, nome_bref, nome_yahoo FROM giocatori", many=True) or []
    righe = [f"🆕 <b>Giocatori nuovi su Basketball-Reference</b> ({len(proposti)})",
             "<i>Non sono in anagrafica. Creandoli, le loro statistiche (già salvate) si collegano da sole.</i>", ""]
    for p in proposti[:MAX_RIGHE]:
        riga = f"• {html.escape(p['nome_bref'])} ({p['team'] or '?'}, {p['g'] or 0} G)"
        simili = [g["nome_common"] for g, _ in nomi.simili(p["nome_bref"], anagrafica, max_n=2)]
        if simili:
            riga += f" — ⚠️ simile a: {html.escape(', '.join(simili))}"
        righe.append(riga)
    if len(proposti) > MAX_RIGHE:
        righe.append(f"… e altri {len(proposti) - MAX_RIGHE}")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Crea tutti", callback_data="brefn:ok"),
                                InlineKeyboardButton("❌ Ignora", callback_data="brefn:no")]])
    return "\n".join(righe), kb


async def job_bref(context: ContextTypes.DEFAULT_TYPE) -> None:
    g = settings.load_globals()
    if g.get("fase", "") not in FASI_RUOLI_RS:
        logger.debug("Bref scraper saltato — fase: %s", g.get("fase"))
        return
    stagione_bref = str(int(g.get("stagione_corrente", 2026)) + 1)
    log_ch = g.get("log_channel_id_main")
    try:
        from bref_scraper import run_giornaliero
        esito = await asyncio.to_thread(run_giornaliero, stagione_bref)
    except Exception as e:
        logger.error("Bref scraper fallito: %s", e)
        if log_ch:
            await context.bot.send_message(chat_id=log_ch, parse_mode="HTML",
                                           text=f"❌ Bref scraper fallito: <code>{html.escape(str(e))[:300]}</code>")
        return

    # Foglio BrefRaw
    foglio = "✅"
    try:
        import gas_client
        ok = await asyncio.to_thread(gas_client.sync_bref_raw, esito["csv"])
        foglio = "✅" if ok else "⚠️ (riprova tra 30s)"
    except Exception as e:
        foglio = "⚠️"
        logger.warning("BrefRaw: %s", e)

    if log_ch:
        righe = [f"📊 Bref {stagione_bref}: <b>{esito['inseriti']}</b> giocatori aggiornati "
                 f"(su {esito['giocatori']}) · foglio BrefRaw {foglio}"]
        if esito["cambi"]:
            righe.append("\n🔀 <b>Cambi squadra NBA</b>")
            righe += [f"• {html.escape(n)}: {da} → <b>{a}</b>" for n, da, a in esito["cambi"]]
        try:
            await context.bot.send_message(chat_id=log_ch, text="\n".join(righe), parse_mode="HTML")
        except Exception as e:
            logger.warning("Messaggio bref sul canale log: %s", e)

    # Giocatori nuovi: solo quelli mai visti (né proposti, né creati, né ignorati)
    aggiunti = 0
    for nome, team, gp in esito["nuovi"]:
        r = db._qval("INSERT INTO bref_nuovi (nome_bref, team, g) VALUES (%s, %s, %s) "
                     "ON CONFLICT (nome_bref) DO NOTHING RETURNING 1", (nome, team, gp))
        aggiunti += 1 if r else 0
    if aggiunti and settings.dev_id():
        testo, kb = _testo_nuovi()
        try:
            await context.bot.send_message(chat_id=settings.dev_id(), text=testo, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning("Proposta giocatori nuovi al dev: %s", e)


def _autorizzato(uid: int) -> bool:
    return uid == settings.dev_id() or settings.is_admin(uid)


async def cb_nuovi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _autorizzato(query.from_user.id):
        await query.answer("⛔ Solo il dev o un admin.", show_alert=True)
        return
    await query.answer()
    chi = query.from_user.first_name or str(query.from_user.id)
    if query.data == "brefn:no":
        n = db._qval("WITH x AS (UPDATE bref_nuovi SET stato = 'ignorato', deciso = NOW(), da = %s "
                     "WHERE stato = 'proposto' RETURNING 1) SELECT count(*) FROM x", (chi,)) or 0
        await query.edit_message_text(f"❌ {n} giocatori ignorati: non verranno riproposti.")
        return
    creati = []
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT nome_bref FROM bref_nuovi WHERE stato = 'proposto' FOR UPDATE")
            for (nome,) in cur.fetchall():
                cur.execute("SELECT 1 FROM giocatori WHERE nome_bref = %s", (nome,))
                if not cur.fetchone():
                    cur.execute("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES (%s, %s, %s)",
                                (nome, nome, normalizza(nome)))   # stessa normalizzazione del resto del bot
                    creati.append(nome)
                cur.execute("UPDATE bref_nuovi SET stato = 'creato', deciso = NOW(), da = %s WHERE nome_bref = %s",
                            (chi, nome))
    elenco = ", ".join(html.escape(n) for n in creati[:40]) + (" …" if len(creati) > 40 else "")
    await query.edit_message_text(f"✅ Creati <b>{len(creati)}</b> giocatori: {elenco or '—'}", parse_mode="HTML")


def get_handlers() -> list:
    return [CallbackQueryHandler(cb_nuovi, pattern=r"^brefn:(ok|no)$")]

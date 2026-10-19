"""
Basketball-Reference — job giornaliero e giocatori nuovi (v3.7.0).

Job (10:00, solo regular season e playoff), una sola richiesta alla pagina per_game:
- append in bref_stats per chi ha giocato (G aumentate);
- foglio BrefRaw sincronizzato con la tabella (formule del foglio collegate);
- messaggio sul canale log: giocatori aggiornati + 🔀 cambi squadra NBA;
- giocatori di bref non in anagrafica (v5.4.1):
  · abbinati da soli a un giocatore già in anagrafica se il nome, senza accenti e
    punteggiatura, è lo stesso di uno e un solo giocatore che su bref non c'è ancora
    (tipicamente un rookie scritto «Topic» e su bref «Topić»): giocatori.nome_bref diventa
    quello di bref, così le sue statistiche si collegano;
  · gli altri al dev: chi ha un nome simile in anagrafica con 🔗 (abbina a quello) o 🆕 (crea),
    uno per uno; ✅ crea solo quelli senza simili; ❌ ignora. L'elenco sta in bref_nuovi: i
    bottoni funzionano anche dopo un riavvio e gli ignorati non vengono riproposti.
- sul canale log anche chi è stato abbinato e i giocatori a roster che su bref non ci sono
  ancora (rookie non ancora entrati, o nome diverso da sistemare).
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



MAX_RIGHE = 40         # nomi senza simili elencati (il messaggio resta sotto il limite di Telegram)
MAX_DUBBI = 8          # righe con i bottoni 🔗/🆕 per volta


def _anagrafica() -> list[dict]:
    return db._q("SELECT id, nome_common, nome_bref, nome_yahoo FROM giocatori", many=True) or []


def abbina_auto(nuovi: list[str]) -> list[tuple[str, str]]:
    """I nomi di bref non in anagrafica che corrispondono (nomi.chiave: senza accenti né
    punteggiatura) a uno e un solo giocatore che su bref non c'è ancora: giocatori.nome_bref
    diventa quello di bref. → [(nome in anagrafica, nome bref)]."""
    if not nuovi:
        return []
    visti = {r["nome_bref"] for r in db._q("SELECT DISTINCT nome_bref FROM bref_stats", many=True) or []}
    indice: dict[str, list[dict]] = {}
    for g in _anagrafica():
        if g["nome_bref"] in visti:
            continue
        for k in nomi._chiavi(g):
            indice.setdefault(k, []).append(g)
    per_chiave: dict[str, int] = {}
    for n in nuovi:
        per_chiave[nomi.chiave(n)] = per_chiave.get(nomi.chiave(n), 0) + 1
    fatti = []
    for n in nuovi:
        k = nomi.chiave(n)
        cand = {g["id"]: g for g in indice.get(k, [])}
        if len(cand) != 1 or per_chiave[k] != 1:
            continue
        g = next(iter(cand.values()))
        _collega(g["id"], n, "auto")
        fatti.append((g["nome_common"], n))
    return fatti


def _collega(gid: int, nome_bref: str, chi: str) -> None:
    db._q("UPDATE giocatori SET nome_bref = %s WHERE id = %s", (nome_bref, gid))
    db._q("""INSERT INTO bref_nuovi (nome_bref, stato, deciso, da) VALUES (%s, 'abbinato', NOW(), %s)
             ON CONFLICT (nome_bref) DO UPDATE SET stato = 'abbinato', deciso = NOW(), da = EXCLUDED.da""", (nome_bref, chi))
    logger.info("bref: %s collegato al giocatore %s (%s)", nome_bref, gid, chi)


def senza_bref() -> list[dict]:
    """Giocatori a roster di cui su bref non c'è nessuna riga (mai): rookie non ancora entrati,
    o nome in anagrafica diverso da quello di bref."""
    return db._q("""SELECT g.nome_common, c.team_id FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                    WHERE c.attivo AND NOT EXISTS (SELECT 1 FROM bref_stats b WHERE b.nome_bref = g.nome_bref)
                    ORDER BY c.team_id, g.nome_common""", many=True) or []


def _testo_nuovi() -> tuple[str, InlineKeyboardMarkup | None]:
    proposti = db._q("SELECT * FROM bref_nuovi WHERE stato = 'proposto' ORDER BY nome_bref", many=True) or []
    if not proposti:
        return "🆕 Nessun giocatore nuovo in attesa.", None
    anagrafica = _anagrafica()
    sicuri, dubbi = [], []
    for p in proposti:
        sim = nomi.simili(p["nome_bref"], anagrafica, max_n=1)
        (dubbi if sim else sicuri).append((p, sim[0][0] if sim else None))
    righe = [f"🆕 <b>Giocatori nuovi su Basketball-Reference</b> ({len(proposti)})",
             "<i>Non sono in anagrafica. Creandoli (o abbinandoli a chi c'è già), le loro statistiche "
             "(già salvate) si collegano da sole.</i>"]
    if dubbi:
        righe += ["", "<b>Con un nome simile in anagrafica</b> — 🔗 è lui (abbina) · 🆕 è un altro (crea):"]
        righe += [f"• {html.escape(p['nome_bref'])} ({p['team'] or '?'}, {p['g'] or 0} G) ↔ "
                  f"{html.escape(g['nome_common'])}" for p, g in dubbi[:MAX_DUBBI]]
        if len(dubbi) > MAX_DUBBI:
            righe.append(f"… e altri {len(dubbi) - MAX_DUBBI} dopo questi")
    if sicuri:
        righe += ["", "<b>Senza simili</b>:"]
        righe += [f"• {html.escape(p['nome_bref'])} ({p['team'] or '?'}, {p['g'] or 0} G)" for p, _ in sicuri[:MAX_RIGHE]]
        if len(sicuri) > MAX_RIGHE:
            righe.append(f"… e altri {len(sicuri) - MAX_RIGHE}")
    tasti = [[InlineKeyboardButton(f"🔗 {g['nome_common'][:28]}", callback_data=f"brefn:l:{p['id']}:{g['id']}"),
              InlineKeyboardButton(f"🆕 {p['nome_bref'][:28]}", callback_data=f"brefn:c:{p['id']}")]
             for p, g in dubbi[:MAX_DUBBI]]
    fondo = []
    if sicuri:
        fondo.append(InlineKeyboardButton(f"✅ Crea i {len(sicuri)} senza simili", callback_data="brefn:ok"))
    fondo.append(InlineKeyboardButton("❌ Ignora tutti", callback_data="brefn:no"))
    tasti.append(fondo)
    return "\n".join(righe), InlineKeyboardMarkup(tasti)


async def job_bref(context: ContextTypes.DEFAULT_TYPE) -> None:
    g = settings.load_globals()
    if g.get("fase", "") not in FASI_RUOLI_RS:
        logger.debug("Bref scraper saltato — fase: %s", g.get("fase"))
        return
    stagione_bref = str(int(g.get("stagione_corrente", 2026)) + 1)
    log_ch = g.get("log_channel_id_main")
    try:
        from bref_scraper import run_giornaliero, BrefVuoto
        esito = await asyncio.to_thread(run_giornaliero, stagione_bref)
    except BrefVuoto as e:
        # stagione non ancora iniziata su bref: niente errore, niente foglio BrefRaw svuotato
        logger.info("Bref %s: %s", stagione_bref, e)
        if log_ch:
            await context.bot.send_message(chat_id=log_ch, parse_mode="HTML",
                                           text=f"⏳ Bref {stagione_bref}: tabella non ancora disponibile "
                                                "(stagione non iniziata su basketball-reference), riprovo domani.")
        return
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

    abbinati = abbina_auto([n for n, _, _ in esito["nuovi"]])
    if abbinati:
        presi = {b for _, b in abbinati}
        esito["nuovi"] = [x for x in esito["nuovi"] if x[0] not in presi]
    if log_ch:
        righe = [f"📊 Bref {stagione_bref}: <b>{esito['inseriti']}</b> giocatori aggiornati "
                 f"(su {esito['giocatori']}) · foglio BrefRaw {foglio}"]
        if abbinati:
            righe.append("\n🔗 <b>Abbinati a Basketball-Reference</b> (stesso nome senza accenti)")
            righe.append(", ".join(f"{html.escape(a)} = {html.escape(b)}" for a, b in abbinati[:20])
                         + (f" … e altri {len(abbinati) - 20}" if len(abbinati) > 20 else ""))
        mancano = senza_bref()
        if mancano:
            righe.append(f"\n⚠️ <b>A roster ma mai visti su bref</b> ({len(mancano)}): rookie non ancora entrati, "
                         "o nome diverso da quello di bref")
            righe.append(", ".join(f"{html.escape(x['nome_common'])} ({html.escape(x['team_id'])})" for x in mancano[:25])
                         + (" …" if len(mancano) > 25 else ""))
        if esito["cambi"]:
            righe.append("\n🔀 <b>Cambi squadra NBA</b>")
            righe += [f"• {html.escape(n)}: {da} → <b>{a}</b>" for n, da, a in esito["cambi"][:30]]
            if len(esito["cambi"]) > 30:
                righe.append(f"… e altri {len(esito['cambi']) - 30}")
        try:
            testo_log = "\n".join(righe)
            if len(testo_log) > 4000:                      # limite di Telegram: si taglia a una riga intera
                testo_log = testo_log[:3990].rsplit("\n", 1)[0] + "\n…"
            await context.bot.send_message(chat_id=log_ch, text=testo_log, parse_mode="HTML")
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
    veste = "dev" if query.from_user.id == settings.dev_id() else "admin"
    from handlers.registro import segna
    if query.data == "brefn:no":
        n = db._qval("WITH x AS (UPDATE bref_nuovi SET stato = 'ignorato', deciso = NOW(), da = %s "
                     "WHERE stato = 'proposto' RETURNING 1) SELECT count(*) FROM x", (chi,)) or 0
        await query.edit_message_text(f"❌ {n} giocatori ignorati: non verranno riproposti.")
        await segna(context.bot, query.from_user, veste, "bref: nuovi ignorati", oggetto=f"{n} giocatori", dopo="ignorati")
        return
    parti = query.data.split(":")
    if parti[1] in ("l", "c"):
        p = db._q("SELECT * FROM bref_nuovi WHERE id = %s", (int(parti[2]),), one=True)
        if not p or p["stato"] != "proposto":
            pass                                          # già deciso (altro tocco, altro admin)
        elif parti[1] == "l":
            prima = db._qval("SELECT nome_bref FROM giocatori WHERE id = %s", (int(parti[3]),))
            _collega(int(parti[3]), p["nome_bref"], chi)
            await segna(context.bot, query.from_user, veste, "bref: giocatore collegato", giocatore_id=int(parti[3]),
                        oggetto=(db.get_giocatore(int(parti[3])) or {}).get("nome_common"), prima=prima or "—",
                        dopo=p["nome_bref"])
        else:
            if not db._qval("SELECT 1 FROM giocatori WHERE nome_bref = %s", (p["nome_bref"],)):
                db._q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES (%s, %s, %s)",
                      (p["nome_bref"], p["nome_bref"], normalizza(p["nome_bref"])))
            db._q("UPDATE bref_nuovi SET stato = 'creato', deciso = NOW(), da = %s WHERE id = %s", (chi, p["id"]))
            await segna(context.bot, query.from_user, veste, "bref: giocatore creato",
                        giocatore_id=db._qval("SELECT id FROM giocatori WHERE nome_bref = %s", (p["nome_bref"],)),
                        oggetto=p["nome_bref"], dopo="creato")
        testo, kb = _testo_nuovi()
        await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
        return
    senza_simili = {p["nome_bref"] for p in (db._q("SELECT nome_bref FROM bref_nuovi WHERE stato = 'proposto'", many=True) or [])
                    if not nomi.simili(p["nome_bref"], _anagrafica(), max_n=1)}
    creati = []
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT nome_bref FROM bref_nuovi WHERE stato = 'proposto' FOR UPDATE")
            for (nome,) in cur.fetchall():
                if nome not in senza_simili:              # quelli con un simile si decidono uno per uno
                    continue
                cur.execute("SELECT 1 FROM giocatori WHERE nome_bref = %s", (nome,))
                if not cur.fetchone():
                    cur.execute("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES (%s, %s, %s)",
                                (nome, nome, normalizza(nome)))   # stessa normalizzazione del resto del bot
                    creati.append(nome)
                cur.execute("UPDATE bref_nuovi SET stato = 'creato', deciso = NOW(), da = %s WHERE nome_bref = %s",
                            (chi, nome))
    elenco = ", ".join(html.escape(n) for n in creati[:40]) + (" …" if len(creati) > 40 else "")
    if creati:
        await segna(context.bot, query.from_user, veste, "bref: giocatori creati", oggetto=f"{len(creati)} giocatori",
                    dopo="creati", nota=", ".join(creati)[:800])
    testo, kb = _testo_nuovi()
    await query.edit_message_text(f"✅ Creati <b>{len(creati)}</b> giocatori: {elenco or '—'}\n\n" + testo,
                                  parse_mode="HTML", reply_markup=kb)


def get_handlers() -> list:
    return [CallbackQueryHandler(cb_nuovi, pattern=r"^brefn:(ok|no|l:\d+:\d+|c:\d+)$")]

"""
10-day contract (regolamento): una volta a stagione per squadra, in regular season prima della
chiusura della free agency (fase regular-season-fa), un free agent senza asta, senza peso sul
cap e senza occupare uno slot, per 10 giorni dall'ora della firma; decade però solo alla
convalida (ufficialità) dell'ultima giornata in cui era in squadra: chi inizia una giornata in
una squadra la finisce (deciso con Luca il 14/10). Ogni free agent al massimo con due squadre a stagione. Si chiama solo
se nel ruolo da coprire non c'è nessun giocatore disponibile (OUT o fuori rotazione): decidono
gli admin.

GM:    /firma_10day NOME (o /menu → ⏱ 10-day → ✍️ e il nome) → giocatore → ruolo da coprire → richiesta al
       gruppo admin, con le regole e i giocatori della squadra in quel ruolo con lo status ESPN.
Admin: ✅ Approva / ❌ Rifiuta sulla richiesta (callback tdq:); /firma_10day_admin NOME (o
       /admin_menu → ⏱ 10-day → ✍️ e il nome) firma direttamente per qualsiasi squadra; lo
       stesso pannello mostra quelli in corso e li può chiudere prima (⏹).

Nel database: contratti tipo '10day' (importo 0, x1 della stagione, scadenza_10day = firma + 10
giorni), transazioni '10day_firma' e '10day_scadenza', ruolo in cambi_ruolo ('post_firma', il
ruolo da coprire). shared/cap.py lo esclude da cap e slot; IPanchinari e il calcolo lo vedono
come gli altri giocatori della squadra. Alla scadenza (job ogni 15 minuti) il contratto si
chiude e il giocatore torna free agent: per riprenderlo serve un'asta.

Callback: td: (GM), tda: (admin che firma), tdq: (richiesta nel gruppo admin), tdadm: (pannello).
"""
import html
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from psycopg2.extras import RealDictCursor

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from telegram.ext import ConversationHandler, MessageHandler, filters

import database as db
import nomi
import settings
import teams as tm
from settings import solo_privato
from shared import ruoli_core as core

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
ET = ZoneInfo("America/New_York")

FASI_10DAY = {"regular-season-fa"}
GIORNI = 10
ORA_FINE_GIORNATA = time(12, 0)    # la giornata finisce il giorno dopo l'ultima notte, alle 12 (ora di Roma)
FUORI_FASE = "❌ Il 10-day si firma solo in regular season, prima della chiusura della free agency."
REGOLE = ("• una volta a stagione per squadra, prima della chiusura della free agency\n"
          "• solo se nel ruolo da coprire non c'è nessun giocatore disponibile (OUT o fuori dalle rotazioni): "
          "decidono gli admin\n"
          "• niente asta, niente cap, niente slot\n"
          "• dura 10 giorni dall'ora della firma, ma decade solo alla convalida dell'ultima giornata in cui era in squadra\n"
          "• ogni free agent al massimo con due squadre a stagione\n"
          "• alla scadenza torna free agent: per riprenderlo serve un'asta")


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _stagione() -> str:
    return settings.stagione_corrente()


def _is_admin(uid: int) -> bool:
    return uid in [int(a) for a in settings.admin_ids()]


def _nome_team(team_id: str | None) -> str:
    t = tm.get_team_by_id(team_id) if team_id else None
    return t["nome"] if t else (team_id or "?")


def max_squadre() -> int:
    return int(settings.get().get("max_10day_per_giocatore", 2))


def aperto() -> bool:
    return settings.fase() in FASI_10DAY


# ══ scadenza ════════════════════════════════════════════════════════════════

def _giornate(stagione: str) -> list[dict]:
    """Le giornate del calendario di loucabot (vuoto se loucabot non c'è)."""
    try:
        if not db._qval("SELECT to_regclass('public.lega_giornate') IS NOT NULL"):
            return []
        return db._q("SELECT numero, dal, al, prima_partita FROM lega_giornate WHERE stagione = %s ORDER BY numero",
                     (stagione,), many=True) or []
    except Exception as err:
        logger.warning("Giornate per il 10-day: %s", err)
        return []


def _intervallo(g: dict) -> tuple[datetime, datetime]:
    """Da quando a quando una giornata è "in corso": dalla prima partita al giorno dopo l'ultima
    notte alle 12 (ora di Roma), quando di solito è già calcolata."""
    inizio = g["prima_partita"] or datetime.combine(g["dal"], time(0, 0), ET)
    fine = datetime.combine(g["al"] + timedelta(days=1), ORA_FINE_GIORNATA, ROMA)
    return inizio, fine


def _convalidate(stagione: str) -> set[int] | None:
    """Giornate convalidate da loucabot (None se la tabella non c'è)."""
    try:
        if not db._qval("SELECT to_regclass('public.lega_calcoli') IS NOT NULL"):
            return None
        return {r["giornata"] for r in db._q("SELECT giornata FROM lega_calcoli WHERE stagione = %s AND stato = 'convalidata'",
                                             (stagione,), many=True) or []}
    except Exception as err:
        logger.warning("Giornate convalidate per il 10-day: %s", err)
        return None


def giornate_aperte(base: datetime, ora: datetime | None = None, stagione: str | None = None) -> list[int]:
    """Le giornate che tengono ancora il 10-day: iniziate durante il contratto (dalla firma,
    base − 10 giorni, ai 10 giorni) e non ancora convalidate. Il contratto decade all'ufficialità
    (convalida) dell'ultima giornata in cui era presente, non prima. Senza le tabelle di loucabot
    vale la fine della giornata (giorno dopo l'ultima notte, alle 12)."""
    stagione = stagione or _stagione()
    ora = ora or datetime.now(timezone.utc)
    firma = base - timedelta(days=GIORNI)
    convalidate = _convalidate(stagione)
    aperte = []
    for g in _giornate(stagione):
        inizio, fine = _intervallo(g)
        if inizio > base or fine < firma:
            continue
        if convalidate is None:
            if ora < fine:
                aperte.append(g["numero"])
        elif g["numero"] not in convalidate:
            aperte.append(g["numero"])
    return aperte


def in_corso_alla_scadenza(base: datetime, stagione: str | None = None) -> int | None:
    """La giornata in corso quando finiscono i 10 giorni (lo terrà fino alla sua convalida)."""
    for g in _giornate(stagione or _stagione()):
        inizio, fine = _intervallo(g)
        if inizio <= base < fine:
            return g["numero"]
    return None


def scaduto(base: datetime, ora: datetime | None = None) -> bool:
    ora = ora or datetime.now(timezone.utc)
    return ora >= base and not giornate_aperte(base, ora)


def testo_scadenza(base: datetime, stagione: str | None = None) -> str:
    n = in_corso_alla_scadenza(base, stagione)
    if n:
        return f"alla convalida della giornata {n}"
    return "al " + base.astimezone(ROMA).strftime("%d/%m alle %H:%M")


def breve_scadenza(base: datetime) -> str:
    """Per la legenda del roster: "fino al 26/10" o "fino alla convalida della G3"."""
    n = in_corso_alla_scadenza(base)
    return f"fino alla convalida della G{n}" if n else "fino al " + base.astimezone(ROMA).strftime("%d/%m")


# ══ dati ════════════════════════════════════════════════════════════════════

def usato(team_id: str, stagione: str | None = None) -> dict | None:
    """Il 10-day della squadra in questa stagione (giocatore e quando), se l'ha già usato."""
    return db._q("""SELECT t.giocatore_id, t.timestamp, g.nome_common FROM movimenti_giocatori t
                    JOIN giocatori g ON g.id = t.giocatore_id
                    WHERE t.tipo = '10day_firma' AND t.team_id_a = %s AND t.stagione = %s
                    ORDER BY t.timestamp LIMIT 1""", (team_id, stagione or _stagione()), one=True)


def squadre_del_giocatore(gid: int, stagione: str | None = None) -> list[str]:
    return [r["team_id_a"] for r in db._q(
        """SELECT DISTINCT team_id_a FROM movimenti_giocatori WHERE tipo = '10day_firma' AND giocatore_id = %s
           AND stagione = %s""", (gid, stagione or _stagione()), many=True) or []]


def attivi() -> list[dict]:
    return db._q("""SELECT c.id, c.giocatore_id, c.team_id, c.scadenza_10day, g.nome_common
                    FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                    WHERE c.attivo AND c.tipo = '10day' ORDER BY c.scadenza_10day""", many=True) or []


def attivo_squadra(team_id: str) -> dict | None:
    return next((c for c in attivi() if c["team_id"] == team_id), None)


def free_agent() -> list[dict]:
    """Giocatori senza contratto attivo e senza diritti 2nd non attivati."""
    return db._q("""SELECT g.* FROM giocatori g
                    WHERE NOT EXISTS (SELECT 1 FROM contratti c WHERE c.giocatore_id = g.id AND c.attivo)
                      AND NOT EXISTS (SELECT 1 FROM rookie r WHERE r.giocatore_id = g.id
                                      AND r.firmato = FALSE AND r.diritti_scaduti = FALSE)""", many=True) or []


def cerca(nome: str, max_n: int = 8) -> list[dict]:
    """Free agent col nome: esatti, poi quelli che lo contengono, poi i simili."""
    fa = free_agent()
    trovati = nomi.esatti(nome, fa)
    if not trovati:
        k = nomi.chiave(nome)
        trovati = [g for g in fa if k and any(k in c for c in nomi._chiavi(g))]
    if not trovati:
        trovati = [g for g, _ in nomi.simili(nome, fa, soglia=0.75, max_n=max_n)]
    return sorted(trovati, key=lambda g: g["nome_common"])[:max_n]


def asta_aperta(gid: int) -> bool:
    """C'è un'asta in corso su di lui nel bot aste (aste.db in sola lettura; senza file: no)."""
    import os
    import sqlite3
    path = os.environ.get("ASTE_DB_PATH", "/data_aste/aste.db")
    if not os.path.isfile(path):
        return False
    nome = (db.get_giocatore(gid) or {}).get("nome_common", "")
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            colonne = {r[1] for r in con.execute("PRAGMA table_info(aste)")}
            filtro = "(giocatore_id = ? OR giocatore = ?)" if "giocatore_id" in colonne else "(? IS NULL OR giocatore = ?)"
            return bool(con.execute(f"""SELECT 1 FROM aste WHERE stato IN ('APERTA', 'CHIUSA', 'PAREGGIO') AND {filtro}
                                        LIMIT 1""", (gid, nome)).fetchone())
        finally:
            con.close()
    except Exception as err:
        logger.warning("Aste aperte per il 10-day: %s", err)
        return False


def eleggibili(gid: int) -> list[str]:
    return core.eleggibili(db._q, gid)


def verifica(team_id: str, gid: int, ruolo: str | None = None) -> list[str]:
    """Errori che impediscono il 10-day (vuoto = si può)."""
    errori = []
    s = _stagione()
    if not aperto():
        return [FUORI_FASE]
    u = usato(team_id, s)
    if u:
        errori.append(f"{_nome_team(team_id)} ha già usato il 10-day in questa stagione ({u['nome_common']}).")
    c = db.get_contratto_attivo(gid)
    if c:
        errori.append(f"È sotto contratto con {_nome_team(c['team_id'])}" + (" (10-day)." if c["tipo"] == "10day" else "."))
    elif db._qval("""SELECT count(*) FROM rookie WHERE giocatore_id = %s AND firmato = FALSE
                     AND diritti_scaduti = FALSE""", (gid,)):
        errori.append("Ci sono diritti 2nd non attivati su di lui: non è un free agent.")
    elif asta_aperta(gid):
        errori.append("C'è un'asta in corso su di lui nel bot delle aste.")
    squadre = squadre_del_giocatore(gid, s)
    if team_id in squadre and not u:
        errori.append("Questa squadra l'ha già firmato con un 10-day in questa stagione.")
    elif len(squadre) >= max_squadre():
        errori.append(f"Già firmato con un 10-day da {len(squadre)} squadre in questa stagione "
                      f"({', '.join(_nome_team(t) for t in squadre)}): massimo {max_squadre()}.")
    if ruolo is not None:
        eleg = eleggibili(gid)
        if not eleg:
            errori.append("Non ha posizioni eleggibili registrate (Yahoo): prima /set_posizioni_eleggibili.")
        elif ruolo not in eleg:
            errori.append(f"{ruolo} non è tra le sue posizioni eleggibili ({', '.join(eleg)}).")
    return errori


def nel_ruolo(team_id: str, ruolo: str) -> list[dict]:
    """I giocatori della squadra col ruolo, con lo status dell'ultimo snapshot ESPN (se c'è)."""
    righe = db._q("""SELECT g.id, g.nome_common, g.espn_id FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                     JOIN ruolo_attuale r ON r.giocatore_id = g.id AND r.stagione = %s
                     WHERE c.attivo AND c.team_id = %s AND r.ruolo = %s ORDER BY g.nome_common""",
                  (_stagione(), team_id, ruolo), many=True) or []
    stati = {}
    try:
        if righe and db._qval("SELECT to_regclass('public.nba_infortuni') IS NOT NULL"):
            ultimo = db._qval("SELECT MAX(preso) FROM nba_infortuni")
            if ultimo:
                stati = {r["atleta"]: r["stato"] for r in db._q(
                    "SELECT atleta, stato FROM nba_infortuni WHERE preso = %s AND atleta = ANY(%s)",
                    (ultimo, [r["espn_id"] for r in righe if r["espn_id"]]), many=True) or []}
    except Exception as err:
        logger.warning("Status ESPN per il 10-day: %s", err)
    for r in righe:
        r["stato"] = stati.get(r["espn_id"]) if r["espn_id"] else None
    return righe


def _elenco_ruolo(team_id: str, ruolo: str) -> str:
    righe = nel_ruolo(team_id, ruolo)
    if not righe:
        return "nessuno"
    return ", ".join(f"{e(r['nome_common'])} ({e(r['stato']) if r['stato'] else 'sano per ESPN'})" for r in righe)


# ══ firma e scadenza ════════════════════════════════════════════════════════

def registra(team_id: str, gid: int, ruolo: str, chi: str) -> dict:
    """Contratto, movimento e ruolo in una transazione. {contratto_id, scadenza}."""
    s = _stagione()
    base = datetime.now(timezone.utc) + timedelta(days=GIORNI)
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM giocatori WHERE id = %s FOR UPDATE", (gid,))
            cur.execute("SELECT 1 FROM contratti WHERE giocatore_id = %s AND attivo", (gid,))
            if cur.fetchone():
                raise ValueError("ha già un contratto attivo")
            cur.execute("""INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma,
                                                  tipo, attivo, scadenza_10day)
                           VALUES (%s, %s, 0, 1, %s, '10day', TRUE, %s) RETURNING id""", (gid, team_id, s, base))
            cid = cur.fetchone()["id"]
            cur.execute("""INSERT INTO transazioni (tipo, oggetto, giocatore_id, team_id_da, team_id_a, stagione,
                                                    contratto_id, note)
                           VALUES ('10day_firma', 'giocatore', %s, NULL, %s, %s, %s, %s)""",
                        (gid, team_id, s, cid, f"10-day {ruolo} ({chi})"))
            cur.execute("""INSERT INTO cambi_ruolo (giocatore_id, team_id, ruolo_da, ruolo_a, stagione, tipo)
                           VALUES (%s, %s, NULL, %s, %s, 'post_firma')""", (gid, team_id, ruolo, s))
    return {"contratto_id": cid, "scadenza": base}


def chiudi(contratto_id: int, nota: str) -> dict | None:
    """Chiude il 10-day (scaduto o chiuso da un admin). None se era già chiuso."""
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""UPDATE contratti SET attivo = FALSE WHERE id = %s AND attivo AND tipo = '10day'
                           RETURNING giocatore_id, team_id, stagione_firma""", (contratto_id,))
            c = cur.fetchone()
            if not c:
                return None
            cur.execute("""INSERT INTO transazioni (tipo, oggetto, giocatore_id, team_id_da, team_id_a, stagione,
                                                    contratto_id, note)
                           VALUES ('10day_scadenza', 'giocatore', %s, %s, NULL, %s, %s, %s)""",
                        (c["giocatore_id"], c["team_id"], _stagione(), contratto_id, nota))
    return dict(c)


async def _manda(bot, chat_id, testo: str, **k):
    if not chat_id:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=testo, parse_mode="HTML", **k)
    except Exception as err:
        logger.warning("10-day, messaggio a %s: %s", chat_id, err)


async def _ai_gm(bot, team_id: str, testo: str):
    for uid in (tm.get_team_by_id(team_id) or {}).get("gm_ids", []):
        await _manda(bot, uid, testo)


async def _log(bot, testo: str):
    await _manda(bot, settings.load_globals().get("log_channel_id_main"), testo)


def _sync(team_id: str):
    try:
        import gas_client
        gas_client.sync_after_firma(team_id)
    except Exception as err:
        logger.warning("Sync foglio dopo il 10-day: %s", err)


async def esegui(bot, team_id: str, gid: int, ruolo: str, chi: str) -> str:
    """Firma, annunci (canale, GM, log) e foglio. Il testo dell'esito."""
    r = registra(team_id, gid, ruolo, chi)
    nome = e((db.get_giocatore(gid) or {}).get("nome_common", gid))
    fino = testo_scadenza(r["scadenza"])
    await _manda(bot, settings.load_globals().get("main_channel_id"),
                 f"⏱ <b>{e(_nome_team(team_id))}</b> firma <b>{nome}</b> con un 10-day ({ruolo})\n"
                 f"<i>Fino {fino}. Non pesa sul cap e non occupa uno slot.</i>")
    await _log(bot, f"⏱ 10-day: {nome} → {e(_nome_team(team_id))} ({ruolo}), fino {fino} — {e(chi)}")
    _sync(team_id)
    return f"✅ <b>{nome}</b> firmato con un 10-day da {e(_nome_team(team_id))} come {ruolo}, fino {fino}."


async def job_scadenza(context: ContextTypes.DEFAULT_TYPE):
    """Ogni 15 minuti: i 10-day scaduti si chiudono, il giocatore torna free agent."""
    try:
        ora = datetime.now(timezone.utc)
        for c in attivi():
            if not c["scadenza_10day"]:
                continue
            if not scaduto(c["scadenza_10day"], ora) or not chiudi(c["id"], "Fine del 10-day"):
                continue
            testo = (f"⏱ <b>{e(_nome_team(c['team_id']))}</b>: finito il 10-day di <b>{e(c['nome_common'])}</b>, "
                     f"torna free agent (per riprenderlo serve un'asta)")
            await _manda(context.bot, settings.load_globals().get("main_channel_id"), testo)
            await _ai_gm(context.bot, c["team_id"], testo)
            await _log(context.bot, testo)
            _sync(c["team_id"])
    except Exception as err:
        logger.exception("job_scadenza 10-day: %s", err)
        await _log(context.bot, f"⚠️ Scadenza dei 10-day: {e(repr(err))}")


# ══ GM ══════════════════════════════════════════════════════════════════════

def _info_squadra(team_id: str) -> str:
    a = attivo_squadra(team_id)
    if a:
        return f"In corso: <b>{e(a['nome_common'])}</b>, fino {testo_scadenza(a['scadenza_10day'])}."
    u = usato(team_id)
    if u:
        return f"Già usato in questa stagione ({e(u['nome_common'])})."
    return "Disponibile in questa stagione."


def testo_home(team_id: str) -> str:
    return (f"⏱ <b>10-day contract</b> — {e(_nome_team(team_id))}\n{_info_squadra(team_id)}\n\n"
            f"<b>Regole</b>\n{REGOLE}\n\nPer chiederlo: ✍️ qui sotto e scrivi il nome (o "
            f"<code>/firma_10day NOME</code>), poi scegli il ruolo da coprire. Decide un admin.")


def _kb_giocatori(trovati: list[dict], prefisso: str) -> K:
    return K([[B(g["nome_common"], callback_data=f"{prefisso}:g:{g['id']}")] for g in trovati]
             + [[B("✖️ Chiudi", callback_data=f"{prefisso}:x")]])


def _kb_ruoli(gid: int, dati: str, prefisso: str) -> K | None:
    eleg = eleggibili(gid)
    if not eleg:
        return None
    return K([[B(r, callback_data=f"{prefisso}:r:{gid}:{dati}{r}") for r in eleg],
              [B("✖️ Chiudi", callback_data=f"{prefisso}:x")]])


@solo_privato
async def cmd_firma_10day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    team = tm.get_team_by_gm(uid)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    nome = " ".join(context.args or []).strip()
    if not nome:
        await update.effective_message.reply_text(testo_home(team["id"]), parse_mode="HTML")
        return
    if not aperto():
        await update.effective_message.reply_text(FUORI_FASE)
        return
    trovati = cerca(nome)
    if not trovati:
        await update.effective_message.reply_text(f"Nessun free agent trovato con «{nome}».")
        return
    await update.effective_message.reply_text("⏱ <b>10-day</b> — quale giocatore?", parse_mode="HTML",
                                              reply_markup=_kb_giocatori(trovati, "td"))


async def cb_gm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parti = q.data.split(":")
    team = tm.get_team_by_gm(q.from_user.id)
    if not team:
        await q.answer("⛔ Non sei registrato come GM.", show_alert=True)
        return
    await q.answer()
    azione = parti[1]
    if azione == "x":
        await q.edit_message_text("Chiuso.")
        return
    if azione == "home":
        kb = ([[B("✍️ Scrivi il nome del giocatore", callback_data="td:nome")]] if aperto() else []) + \
             [[B("← Menu", callback_data="menu:home")]]
        await q.edit_message_text(testo_home(team["id"]), parse_mode="HTML", reply_markup=K(kb))
        return
    gid = int(parti[2])
    nome = e((db.get_giocatore(gid) or {}).get("nome_common", gid))
    if azione == "g":
        errori = verifica(team["id"], gid)
        kb = _kb_ruoli(gid, "", "td")
        if errori or not kb:
            await q.edit_message_text("❌ " + "\n❌ ".join(errori or [f"{nome} non ha posizioni eleggibili registrate: "
                                                                    "chiedi a un admin."]))
            return
        await q.edit_message_text(f"⏱ <b>{nome}</b> — quale ruolo deve coprire?\n<i>Puoi chiederlo solo se in quel "
                                  f"ruolo non hai nessun giocatore disponibile.</i>", parse_mode="HTML", reply_markup=kb)
        return
    ruolo = parti[3]
    errori = verifica(team["id"], gid, ruolo)
    if errori:
        await q.edit_message_text("❌ " + "\n❌ ".join(errori))
        return
    if azione == "r":
        await q.edit_message_text(
            f"⏱ Chiedi il 10-day di <b>{nome}</b> come <b>{ruolo}</b>?\n\n"
            f"Nel ruolo {ruolo} hai: {_elenco_ruolo(team['id'], ruolo)}\n\n<b>Regole</b>\n{REGOLE}",
            parse_mode="HTML", reply_markup=K([[B("📨 Chiedi agli admin", callback_data=f"td:ok:{gid}:{ruolo}"),
                                                B("✖️ Annulla", callback_data="td:x")]]))
    elif azione == "ok":
        if not db.apri_richiesta("10day", gid, team["id"]):
            await q.edit_message_text("⏳ C'è già una richiesta di 10-day in attesa per questo giocatore.")
            return
        await _richiesta(context.bot, team["id"], gid, ruolo, q.from_user)
        await q.edit_message_text(f"📨 Richiesta di 10-day per {nome} ({ruolo}) mandata agli admin. "
                                  f"Ti arriva un messaggio quando decidono.")
        await _log(context.bot, f"📨 Richiesta 10-day: {nome} → {e(team['nome'])} ({ruolo})")


async def _richiesta(bot, team_id: str, gid: int, ruolo: str, user):
    nome = e((db.get_giocatore(gid) or {}).get("nome_common", gid))
    chi = e(user.first_name or user.id)
    testo = (f"⏱ <b>Richiesta 10-day</b> — {e(_nome_team(team_id))} ({chi})\n"
             f"<b>{nome}</b> per coprire il ruolo <b>{ruolo}</b>\n\n"
             f"Giocatori della squadra in ruolo {ruolo}: {_elenco_ruolo(team_id, ruolo)}\n"
             f"<i>Da approvare solo se nessuno di questi è disponibile (OUT o fuori dalle rotazioni).</i>\n\n"
             f"<b>Regole</b>\n{REGOLE}")
    await _manda(bot, settings.load_globals().get("admin_group_id"), testo,
                 reply_markup=K([[B("✅ Approva", callback_data=f"tdq:ok:{team_id}:{gid}:{ruolo}"),
                                  B("❌ Rifiuta", callback_data=f"tdq:no:{team_id}:{gid}:{ruolo}")]]))


async def cb_richiesta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    _, esito, team_id, gid, ruolo = q.data.split(":")
    gid = int(gid)
    admin = q.from_user.first_name or str(q.from_user.id)
    await q.answer()
    nome = e((db.get_giocatore(gid) or {}).get("nome_common", gid))
    gia = "\n\nℹ️ <b>Richiesta già gestita</b>"
    if esito == "no":
        if db.chiudi_richiesta("10day", gid, "rifiutata", admin) == "gestita":
            await q.edit_message_text(q.message.text_html + gia, parse_mode="HTML")
            return
        await q.edit_message_text(q.message.text_html + f"\n\n❌ <b>Rifiutata</b> da {e(admin)}", parse_mode="HTML")
        await _ai_gm(context.bot, team_id, f"❌ La richiesta di 10-day per {nome} ({ruolo}) è stata rifiutata.")
        await _log(context.bot, f"❌ 10-day di {nome} → {e(_nome_team(team_id))} rifiutato da {e(admin)}")
        return
    ultima = db._qval("SELECT stato FROM richieste_admin WHERE tipo = '10day' AND chiave = %s ORDER BY id DESC LIMIT 1",
                      (gid,))
    if ultima in ("approvata", "rifiutata", "scaduta"):
        await q.edit_message_text(q.message.text_html + gia, parse_mode="HTML")
        return
    errori = verifica(team_id, gid, ruolo)
    if errori:
        db.chiudi_richiesta("10day", gid, "scaduta")
        await q.edit_message_text(q.message.text_html + "\n\n⚠️ Non applicabile: " + e("; ".join(errori)), parse_mode="HTML")
        await _ai_gm(context.bot, team_id, f"⚠️ Il 10-day di {nome} non si può più fare: {e('; '.join(errori))}")
        return
    if db.chiudi_richiesta("10day", gid, "approvata", admin) == "gestita":
        await q.edit_message_text(q.message.text_html + gia, parse_mode="HTML")
        return
    try:
        esito_txt = await esegui(context.bot, team_id, gid, ruolo, f"approvato da {admin}")
    except Exception as err:
        db.riapri_richiesta("10day", gid)
        logger.exception("10-day: %s", err)
        await q.edit_message_text(q.message.text_html + f"\n\n⚠️ Errore: {e(err)}", parse_mode="HTML")
        return
    await q.edit_message_text(q.message.text_html + f"\n\n✅ <b>Approvata</b> da {e(admin)}", parse_mode="HTML")
    await _ai_gm(context.bot, team_id, esito_txt)


# ══ admin ═══════════════════════════════════════════════════════════════════

async def cmd_firma_10day_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    nome = " ".join(context.args or []).strip()
    if not nome:
        await update.effective_message.reply_text(
            "Uso: /firma_10day_admin NOME — poi squadra e ruolo. Firma direttamente, senza richiesta.\n\n"
            + REGOLE)
        return
    if not aperto():
        await update.effective_message.reply_text(FUORI_FASE)
        return
    trovati = cerca(nome)
    if not trovati:
        await update.effective_message.reply_text(f"Nessun free agent trovato con «{nome}».")
        return
    await update.effective_message.reply_text("⏱ <b>10-day (admin)</b> — quale giocatore?", parse_mode="HTML",
                                              reply_markup=_kb_giocatori(trovati, "tda"))


async def cb_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    parti = q.data.split(":")
    azione = parti[1]
    if azione == "x":
        await q.edit_message_text("Chiuso.")
        return
    gid = int(parti[2])
    nome = e((db.get_giocatore(gid) or {}).get("nome_common", gid))
    if azione == "g":                                    # squadra
        kb = [[B(f"{t['nome']}" + (" (usato)" if usato(t["id"]) else ""), callback_data=f"tda:t:{gid}:{t['id']}")]
              for t in tm.get_all_teams()]
        kb.append([B("✖️ Chiudi", callback_data="tda:x")])
        await q.edit_message_text(f"⏱ <b>{nome}</b> — per quale squadra?", parse_mode="HTML", reply_markup=K(kb))
        return
    team_id = parti[3]
    if azione == "t":                                    # ruolo
        errori = verifica(team_id, gid)
        kb = _kb_ruoli(gid, f"{team_id}:", "tda")
        if errori or not kb:
            await q.edit_message_text("❌ " + "\n❌ ".join(errori or [f"{nome} non ha posizioni eleggibili: "
                                                                    "prima /set_posizioni_eleggibili."]))
            return
        await q.edit_message_text(f"⏱ <b>{nome}</b> → {e(_nome_team(team_id))}: quale ruolo copre?",
                                  parse_mode="HTML", reply_markup=kb)
        return
    ruolo = parti[4]
    errori = verifica(team_id, gid, ruolo)
    if errori:
        await q.edit_message_text("❌ " + "\n❌ ".join(errori))
        return
    if azione == "r":
        await q.edit_message_text(
            f"⏱ Firmi <b>{nome}</b> con un 10-day per <b>{e(_nome_team(team_id))}</b> come <b>{ruolo}</b>?\n\n"
            f"Nel ruolo {ruolo} la squadra ha: {_elenco_ruolo(team_id, ruolo)}",
            parse_mode="HTML", reply_markup=K([[B("✅ Firma", callback_data=f"tda:ok:{gid}:{team_id}:{ruolo}"),
                                                B("✖️ Annulla", callback_data="tda:x")]]))
    elif azione == "ok":
        admin = q.from_user.first_name or str(q.from_user.id)
        db.chiudi_richiesta("10day", gid, "approvata", admin)
        try:
            esito = await esegui(context.bot, team_id, gid, ruolo, f"firmato da {admin}")
        except Exception as err:
            logger.exception("10-day admin: %s", err)
            await q.edit_message_text(f"⚠️ Errore: {e(err)}")
            return
        await q.edit_message_text(esito, parse_mode="HTML")
        await _ai_gm(context.bot, team_id, f"🛠 Un admin ha registrato un 10-day: {esito[2:]}")


def testo_pannello() -> tuple[str, K]:
    righe = ["⏱ <b>10-day in corso</b>"]
    kb = []
    for c in attivi():
        righe.append(f"• {e(_nome_team(c['team_id']))}: <b>{e(c['nome_common'])}</b>, fino "
                     f"{testo_scadenza(c['scadenza_10day'])}")
        kb.append([B(f"⏹ Chiudi ora: {c['nome_common']}", callback_data=f"tdadm:end:{c['id']}")])
    if len(righe) == 1:
        righe.append("Nessuno.")
    righe += ["", "✍️ per firmarne uno per una squadra (o <code>/firma_10day_admin NOME</code>); ⏹ per chiuderne "
                  "uno prima. Le richieste dei GM arrivano nel gruppo admin."]
    if aperto():
        kb.append([B("✍️ Firma un 10-day (scrivi il nome)", callback_data="tdadm:nome")])
    kb.append([B("← Menu admin", callback_data="adm:home")])
    return "\n".join(righe), K(kb)


async def cb_pannello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    parti = q.data.split(":")
    if parti[1] == "end":
        await q.edit_message_text("Chiudi subito il 10-day? Il giocatore torna free agent.",
                                  reply_markup=K([[B("⏹ Sì, chiudi", callback_data=f"tdadm:endok:{parti[2]}"),
                                                   B("← Indietro", callback_data="tdadm:list")]]))
        return
    if parti[1] == "endok":
        admin = q.from_user.first_name or str(q.from_user.id)
        c = chiudi(int(parti[2]), f"Chiuso prima da {admin}")
        if c:
            nome = e((db.get_giocatore(c["giocatore_id"]) or {}).get("nome_common", c["giocatore_id"]))
            testo = (f"⏱ <b>{e(_nome_team(c['team_id']))}</b>: 10-day di <b>{nome}</b> chiuso da un admin, "
                     f"torna free agent")
            await _manda(context.bot, settings.load_globals().get("main_channel_id"), testo)
            await _ai_gm(context.bot, c["team_id"], testo)
            await _log(context.bot, testo + f" ({e(admin)})")
            _sync(c["team_id"])
    testo, kb = testo_pannello()
    await q.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)


# ══ nome scritto dopo il bottone ✍️ (GM e admin) ══════════════════════════════

NOME = 1


async def cb_chiedi_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    admin = q.data.startswith("tdadm:")
    if admin and not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return ConversationHandler.END
    if not admin and not tm.get_team_by_gm(q.from_user.id):
        await q.answer("⛔ Non sei registrato come GM.", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    if not aperto():
        await q.edit_message_text(FUORI_FASE)
        return ConversationHandler.END
    context.user_data["10day_admin"] = admin
    await q.edit_message_text("✍️ Scrivi il nome del free agent (anche solo una parte). /annulla per uscire.")
    return NOME


async def msg_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = context.user_data.pop("10day_admin", False)
    nome = (update.effective_message.text or "").strip()
    trovati = cerca(nome)
    if not trovati:
        await update.effective_message.reply_text(f"Nessun free agent trovato con «{nome}». Riprova o /annulla.")
        context.user_data["10day_admin"] = admin
        return NOME
    titolo = "⏱ <b>10-day (admin)</b> — quale giocatore?" if admin else "⏱ <b>10-day</b> — quale giocatore?"
    await update.effective_message.reply_text(titolo, parse_mode="HTML",
                                              reply_markup=_kb_giocatori(trovati, "tda" if admin else "td"))
    return ConversationHandler.END


async def annulla_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("10day_admin", None)
    await update.effective_message.reply_text("Annullato.")
    return ConversationHandler.END


def get_handlers() -> list:
    return [
        ConversationHandler(
            entry_points=[CallbackQueryHandler(cb_chiedi_nome, pattern=r"^(?:td|tdadm):nome$")],
            states={NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, msg_nome)]},
            fallbacks=[CommandHandler(["annulla", "annulla_admin"], annulla_nome)],
            conversation_timeout=600, name="dieci_giorni_nome"),
        CommandHandler("firma_10day", cmd_firma_10day),
        CommandHandler("firma_10day_admin", cmd_firma_10day_admin),
        CallbackQueryHandler(cb_gm, pattern=r"^td:(?:x|home|g:\d+|(?:r|ok):\d+:[A-Z]{1,2})$"),
        CallbackQueryHandler(cb_admin, pattern=r"^tda:(?:x|g:\d+|t:\d+:[\w-]+|(?:r|ok):\d+:[\w-]+:[A-Z]{1,2})$"),
        CallbackQueryHandler(cb_richiesta, pattern=r"^tdq:(?:ok|no):[\w-]+:\d+:[A-Z]{1,2}$"),
        CallbackQueryHandler(cb_pannello, pattern=r"^tdadm:(?:list|end:\d+|endok:\d+)$"),
    ]

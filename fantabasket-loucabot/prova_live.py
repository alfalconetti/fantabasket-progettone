"""
Prova del live sulle partite di preseason (deciso con Luca il 14/10): `/dev_prova_live` fa girare
il live vero (stesso calcolo, stesso messaggio, ogni 10 minuti dalla prima partita alle 8 del
mattino dopo, poi alle 10:05) su una giornata finta fatta delle notti indicate, con gli
accoppiamenti della prossima giornata e i quintetti e le panchine di adesso.

Isolata da tutto il resto:
- il messaggio va solo al dev, in privato (mai sul canale principale);
- **non scrive niente nel database**: partite e tabellini di ESPN restano in memoria (le partite di
  preseason, tipo 1, non entrano mai in nba_tabellini), niente lega_live, lega_calcoli,
  lega_risultati, foglio;
- per il calcolo, `db.partite_nba` e `db.tabellini_atleti` sono sostituite con i dati in memoria
  solo durante il calcolo, che è sincrono: nel frattempo nessun altro pezzo del bot gira.
Lo stato è in memoria: se il bot si riavvia la prova si ferma (si rilancia).

/dev_prova_live [GG/MM/AAAA ...] (giorni NBA, ora della costa est; senza date: oggi) · /dev_prova_live stop
"""
import asyncio
import html
import logging
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import config
import db
import live
import nba
import risultati as R

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
NOME_JOB = "dev_prova_live"
STATO: dict = {}                 # giorni, chat, message_id, aggiornato, partite, tabellini, finite, fatti_10


def e(x) -> str:
    return html.escape(str(x), quote=False)


@contextmanager
def dati_in_memoria(partite: list[dict], tabellini: list[dict]):
    """db.partite_nba e db.tabellini_atleti dai dati in memoria (tutti i tipi, preseason compresa)."""
    vecchie = db.partite_nba, db.tabellini_atleti

    def partite_nba(dal, al, tipi=None):
        return [p for p in partite if dal <= p["data_et"] <= al]

    def tabellini_atleti(atleti, dal, al):
        a = set(atleti)
        return sorted((r for r in tabellini if r["atleta"] in a and dal <= r["data_et"] <= al), key=lambda r: r["inizio"])
    db.partite_nba, db.tabellini_atleti = partite_nba, tabellini_atleti
    try:
        yield
    finally:
        db.partite_nba, db.tabellini_atleti = vecchie


async def scarica(st: dict, tutte: bool = False, scarica_giorno=None, scarica_partita=None) -> None:
    """Tabellone dei giorni e tabellini (in corso; finite una volta sola, o tutte con `tutte`). Solo in memoria."""
    client = None
    if scarica_giorno is None or scarica_partita is None:
        client = nba._client()
        scarica_giorno = scarica_giorno or (lambda d: nba.scarica_giorno(client, d))
        scarica_partita = scarica_partita or (lambda pid: nba._get(client, nba.BASE + "summary", {"event": pid}))
    try:
        partite = []
        for d in st["giorni"]:
            partite += nba.leggi_giorno(await scarica_giorno(d))
            await asyncio.sleep(0.3)
        st["partite"] = partite
        per_partita = {p["espn_id"]: p for p in partite}
        da_scaricare = [p["espn_id"] for p in partite
                        if p["stato"] not in live.NON_INIZIATE and (tutte or p["espn_id"] not in st["finite"])]
        for pid in da_scaricare:
            p = per_partita[pid]
            righe = nba.leggi_tabellino(await scarica_partita(pid), pid)
            for r in righe:
                r.update(data_et=p["data_et"], stato_partita=p["stato"], inizio=p["inizio"])
            st["tabellini"] = [r for r in st["tabellini"] if r["partita"] != pid] + righe
            if p["stato"] == "STATUS_FINAL":
                st["finite"].add(pid)
            await asyncio.sleep(1.0)
    finally:
        if client:
            await client.aclose()


def calcola(st: dict) -> dict:
    s = config.stagione()
    vera = st["vera"]
    finta = {**vera, "numero": 0, "dal": min(st["giorni"]), "al": max(st["giorni"]), "media": None, "media_file": [],
             "tipo": "regular"}
    with dati_in_memoria(st["partite"], st["tabellini"]):
        c = R.calcola(s, 0, g=finta, sch=R.schieramenti_attuali(s, vera["numero"]), stagione_nba=s,
                      partite=st["accoppiamenti"])
        c["_testo"] = live.testo(c, st["aggiornato"], prova=True)
    return c


def finestre(st: dict) -> list[tuple[date, datetime, datetime]]:
    """[(giorno, prima partita, 8:00 del mattino dopo)] dei giorni con partite."""
    out = {}
    for p in st["partite"]:
        if p["stato"] in ("STATUS_POSTPONED", "STATUS_CANCELED"):
            continue
        out[p["data_et"]] = min(out.get(p["data_et"], p["inizio"]), p["inizio"])
    return [(d, i, datetime.combine(d + timedelta(days=1), live.FINE_NOTTE, ROMA)) for d, i in sorted(out.items())]


def cosa_fare(st: dict, ora: datetime) -> str | None:
    ultimo = st.get("aggiornato")
    for d, inizio, fine in finestre(st):
        if inizio <= ora < fine:
            return "live" if not ultimo or ora - ultimo >= live.OGNI - timedelta(seconds=30) else None
        c10 = datetime.combine(d + timedelta(days=1), live.ORA_CONTROLLO, ROMA)
        if c10 <= ora < c10 + live.OGNI and d not in st["fatti_10"]:
            st["fatti_10"].add(d)
            return "controllo"
    return None


def finita(st: dict, ora: datetime) -> bool:
    return ora >= datetime.combine(max(st["giorni"]) + timedelta(days=1), live.ORA_CONTROLLO, ROMA) + live.OGNI


async def giro(bot, st: dict, ora: datetime, forza: bool = False, **scarichi) -> str | None:
    quale = "live" if forza else cosa_fare(st, ora)
    if not quale:
        return None
    await scarica(st, tutte=quale == "controllo", **scarichi)
    st["aggiornato"] = ora
    c = calcola(st)
    t = c["_testo"].replace("(non pubblicato sul canale)", "(preseason, solo a te: niente sul canale, niente nel database)")
    if st.get("message_id"):
        try:
            await bot.edit_message_text(chat_id=st["chat"], message_id=st["message_id"], text=t, parse_mode="HTML")
        except Exception as err:
            if "not modified" not in str(err).lower():
                raise
    else:
        m = await bot.send_message(chat_id=st["chat"], text=t, parse_mode="HTML")
        st["message_id"] = m.message_id
    return quale


async def job(context: ContextTypes.DEFAULT_TYPE):
    st = STATO.get("prova")
    if not st:
        return
    ora = datetime.now(timezone.utc)
    try:
        if not st["partite"]:
            await scarica(st)
        await giro(context.bot, st, ora)
    except Exception as err:
        logger.warning("Prova del live: %s", err)
        if not st.get("errore") or ora - st["errore"] >= timedelta(hours=1):
            st["errore"] = ora
            await context.bot.send_message(chat_id=st["chat"], text=f"⚠️ Prova del live: {err}"[:500])
    if finita(st, ora):
        STATO.pop("prova", None)
        context.job.schedule_removal()
        await context.bot.send_message(chat_id=st["chat"], text="🧪 Prova del live finita.")


async def cmd_dev_prova_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (config.dev_id() and update.effective_user.id == config.dev_id()):
        return
    msg = update.effective_message
    for j in context.job_queue.get_jobs_by_name(NOME_JOB):
        j.schedule_removal()
    if context.args and context.args[0].lower() == "stop":
        STATO.pop("prova", None)
        await msg.reply_text("🧪 Prova del live fermata.")
        return
    try:
        from shared.date_comandi import leggi_data
        lette = [leggi_data(x) for x in context.args]
        if not all(lette):
            raise ValueError("data")
        giorni = sorted(set(lette)) or [nba.oggi_et()]
        assert giorni[-1] - giorni[0] <= timedelta(days=4)
    except Exception:
        await msg.reply_text("Uso: /dev_prova_live [GG/MM/AAAA …] (giorni NBA, al massimo 5; senza date: oggi) · /dev_prova_live stop")
        return
    import calendario as cal
    s = config.stagione()
    vera = cal.corrente(s)
    if not vera:
        await msg.reply_text("Nessuna giornata nel calendario da cui prendere gli accoppiamenti.")
        return
    st = {"giorni": giorni, "chat": update.effective_chat.id, "vera": vera, "accoppiamenti": db.partite_giornata(s, vera["numero"]),
          "partite": [], "tabellini": [], "finite": set(), "fatti_10": set(), "message_id": None, "aggiornato": None}
    try:
        await scarica(st)
    except Exception as err:
        await msg.reply_text(f"⚠️ ESPN: {err}")
        return
    STATO["prova"] = st
    f = finestre(st)
    if not f:
        STATO.pop("prova", None)
        await msg.reply_text(f"Nessuna partita NBA nei giorni {', '.join(f'{d:%d/%m}' for d in giorni)}.")
        return
    context.job_queue.run_repeating(job, interval=timedelta(minutes=1), first=5, name=NOME_JOB)
    await msg.reply_text(
        f"🧪 Prova del live avviata: {len(st['partite'])} partite ({', '.join(f'{d:%d/%m}' for d in giorni)}), accoppiamenti "
        f"della giornata {vera['numero']}, quintetti e panchine di adesso.\n"
        + "\n".join(f"• notte del {d:%d/%m}: dalle {i.astimezone(ROMA):%H:%M} alle {fi.astimezone(ROMA):%H:%M}, poi alle 10:05"
                    for d, i, fi in f)
        + "\nIl messaggio arriva solo qui; niente sul canale e niente nel database. /dev_prova_live stop per fermarla.")


def get_handlers() -> list:
    return [CommandHandler("dev_prova_live", cmd_dev_prova_live)]

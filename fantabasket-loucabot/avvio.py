"""Loucabot quando Telegram non risponde, e i job a orario fisso saltati (v7.19.0, dopo il 19/11).

1. `scarica_senza_telegram()`: la chiama shared.attesa_telegram.attendi mentre aspetta Telegram. Partite NBA dei
   giorni vicini, tabellini delle partite finite che non li hanno, snapshot degli infortunati: tutto ESPN e
   database, niente Telegram. Al massimo ogni 5 minuti (gli infortunati ogni 30), così quando il bot riparte il
   live trova già i tabellini.
2. Job a orario fisso recuperati: ogni job in `RECUPERABILI` segna in `job_eseguiti` quando è finito; all'avvio,
   se l'ultima ora in cui doveva girare (oggi o ieri, al massimo 20 ore fa) è dopo l'ultima esecuzione, si rifà
   una volta (uno ogni mezzo minuto, nell'ordine della giornata) e il canale di log lo dice. La prima volta che
   un job non ha nessuna riga si segna solo l'ora di adesso: dopo un deploy non si rifà tutto.
   Non si recuperano: foglio parziale (a metà giornata, poi superato), snapshot degli infortunati a ore fisse
   (si rifanno da soli), i job ogni minuto (live, foto, formazioni: ripartono da soli).
3. Telegram che cade col bot acceso (v7.20.2, Luca 21/11): i job continuano a girare e i download da ESPN si fanno
   lo stesso (il live scarica prima di pubblicare), ma un job a orario fisso che finisce mentre Telegram non risponde
   non si segna come fatto (`segnato` lo controlla con getMe). `job_sentinella`, ogni 5 minuti, se ne accorge;
   quando Telegram torna rifà i job non segnati (come all'avvio) e lo scrive sul canale di log, con dalle–alle e se
   era la rete del server o Telegram.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import db

logger = logging.getLogger(__name__)
ROME = ZoneInfo("Europe/Rome")
OGNI = 300                 # secondi tra due giri di download mentre si aspetta Telegram
OGNI_INFORTUNI = 1800
MAX_RITARDO = timedelta(hours=20)
_ultimo = {"giro": 0.0, "infortuni": 0.0}


def scarica_senza_telegram(ora=time.monotonic) -> str:
    """Un giro di download che non ha bisogno di Telegram; "" se è troppo presto per un altro giro."""
    if _ultimo["giro"] and ora() - _ultimo["giro"] < OGNI:
        return ""
    _ultimo["giro"] = ora()
    import handlers_calcolo as hc
    import nba

    async def giro():
        pezzi = []
        r = await nba.sincronizza(nba.giorni_vicini(prima=2, dopo=1))
        pezzi.append(f"{r['partite']} partite")
        pezzi.append(hc.testo_tabellini(await hc.aggiorna_tabellini()))
        if not _ultimo["infortuni"] or ora() - _ultimo["infortuni"] >= OGNI_INFORTUNI:
            _ultimo["infortuni"] = ora()
            pezzi.append(await hc.snapshot_infortuni())
        return ", ".join(pezzi)

    loop = asyncio.new_event_loop()          # un loop suo: quello di run_polling non va toccato
    try:
        testo = loop.run_until_complete(giro())
    finally:
        loop.close()
    logger.info("Senza Telegram, scaricato: %s", testo)
    return testo


# ── job a orario fisso ─────────────────────────────────────────────────────────

def migra() -> None:
    db.q("""CREATE TABLE IF NOT EXISTS job_eseguiti (
                nome   TEXT PRIMARY KEY,
                ultimo TIMESTAMPTZ NOT NULL)""")


def segna(nome: str, quando: datetime | None = None) -> None:
    db.q("""INSERT INTO job_eseguiti (nome, ultimo) VALUES (%s, %s)
            ON CONFLICT (nome) DO UPDATE SET ultimo = EXCLUDED.ultimo""", (nome, quando or datetime.now(ROME)))


def ultimo(nome: str) -> datetime | None:
    r = db.q("SELECT ultimo FROM job_eseguiti WHERE nome = %s", (nome,), one=True)
    return r["ultimo"] if r else None


# v7.20.2: Telegram col bot acceso. CONTROLLO: funzione senza argomenti → Telegram risponde? (la imposta bot.py col
# token; None nelle prove = sempre sì). GIU: da quando non risponde e se intanto mancava anche la rete del server.
CONTROLLO = None
GIU = {"dal": None, "senza_rete": False}
RECUPERABILI: dict = {}    # quelli di bot.py (lo stesso dict)


async def telegram_ok() -> bool:
    if CONTROLLO is None:
        return True
    return bool(await asyncio.to_thread(CONTROLLO))


def segna_giu(adesso: datetime | None = None, rete=None) -> None:
    if GIU["dal"] is None:
        from shared import attesa_telegram
        GIU["dal"] = adesso or datetime.now(ROME)
        GIU["senza_rete"] = not (rete or attesa_telegram.rete_ok)()
        logger.warning("Telegram non risponde (rete del server %s)", "giù" if GIU["senza_rete"] else "ok")


def segnato(nome: str, job):
    """Il job che, finito, segna l'ora in job_eseguiti (anche se il job ha già gestito i suoi errori), solo se
    Telegram risponde (v7.20.2): se no resta da rifare quando torna (job_sentinella)."""
    async def eseguito(context):
        await job(context)
        if GIU["dal"] is not None or not await telegram_ok():
            segna_giu()
            logger.warning("Job %s finito con Telegram giù: si rifà quando torna", nome)
            return
        try:
            segna(nome)
        except Exception as e:
            logger.warning("job_eseguiti %s: %s", nome, e)
    eseguito.__name__ = getattr(job, "__name__", nome)
    return eseguito


def ultima_ora(orario, adesso: datetime) -> datetime:
    """L'ultima volta (oggi o ieri) in cui un job alle `orario` (ora di Roma) doveva girare."""
    oggi = datetime.combine(adesso.date(), orario.replace(tzinfo=None), ROME)
    return oggi if oggi <= adesso else oggi - timedelta(days=1)


def da_recuperare(recuperabili: dict, adesso: datetime | None = None) -> list[str]:
    """I nomi dei job saltati, nell'ordine della giornata. `recuperabili`: {nome: (orario, job)}."""
    adesso = adesso or datetime.now(ROME)
    out = []
    for nome, (orario, _job) in recuperabili.items():
        dovuto = ultima_ora(orario, adesso)
        u = ultimo(nome)
        if u is None:                                     # prima volta (deploy): da qui in avanti
            segna(nome, adesso)
            continue
        if u < dovuto and adesso - dovuto <= MAX_RITARDO:
            out.append((dovuto, nome))
    return [n for _d, n in sorted(out)]


def recupera(app, recuperabili: dict, adesso: datetime | None = None) -> list[str]:
    """Mette in coda i job saltati (uno ogni 30 secondi, dal primo minuto) e ne ritorna i nomi."""
    nomi = da_recuperare(recuperabili, adesso)
    for i, nome in enumerate(nomi):
        app.job_queue.run_once(segnato(nome, recuperabili[nome][1]), when=60 + 30 * i, name=f"recupero_{nome}")
    if nomi:
        logger.info("Job saltati da rifare: %s", ", ".join(nomi))
    return nomi


NOMI = {"sync_nba": "sincronizzazione del mattino", "primo_controllo": "primo controllo della notte",
        "calcolo": "calcolo", "controllo_tanking": "controllo tanking", "top_notte": "top della notte",
        "controllo_notte": "controllo finale della notte"}


def testo_tornato(dal: datetime, al: datetime, senza_rete: bool, nomi: list[str]) -> str:
    from shared import attesa_telegram
    chi = "🌐 Rete del server giù" if senza_rete else "📡 Telegram non rispondeva"
    t = (f"{chi} dalle {dal.astimezone(ROME):%H:%M} alle {al.astimezone(ROME):%H:%M} "
         f"({attesa_telegram.durata((al - dal).total_seconds())}), col bot acceso: i download da ESPN sono andati avanti.")
    if nomi:
        t += "\n🔁 Job saltati, li rifaccio ora: " + ", ".join(NOMI.get(n, n) for n in nomi) + "."
    return t


async def job_sentinella(context, recuperabili: dict | None = None, adesso: datetime | None = None) -> str:
    """Ogni 5 minuti (v7.20.2): Telegram risponde? Al ritorno rifà i job a orario fisso non segnati e lo dice."""
    if not await telegram_ok():
        segna_giu(adesso)
        return ""
    if GIU["dal"] is None:
        return ""
    dal, senza_rete = GIU["dal"], GIU["senza_rete"]
    GIU.update(dal=None, senza_rete=False)
    if recuperabili is None:
        recuperabili = RECUPERABILI
    nomi = recupera(context.application, recuperabili, adesso)
    testo = testo_tornato(dal, adesso or datetime.now(ROME), senza_rete, nomi)
    import config
    if config.canale_log():
        try:
            await context.bot.send_message(chat_id=config.canale_log(), text=testo)
        except Exception as e:
            logger.warning("Avviso di Telegram tornato: %s", e)
    return testo


def testo_recuperati(nomi: list[str]) -> str:
    return ("🔁 Saltati mentre il bot era giù, li rifaccio ora: " + ", ".join(NOMI.get(n, n) for n in nomi) + ".") if nomi else ""


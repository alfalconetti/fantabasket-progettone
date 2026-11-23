"""
Sorteggio del calendario di regular season con drand (v7.28.0, Luca 15/11 e 23/11), come la lottery del draft.

1. /calendario_quando GG/MM HH:MM (admin): fissa il sorteggio. Sul canale principale l'annuncio: il round drand che
   esce a quell'ora, le due conference con le 12 squadre in ordine alfabetico (da divisions.json), l'impronta del
   codice (SHA-256 di shared/calendario_sorteggio.py), il link al round; allegati calendario_sorteggio.py, lottery.py
   (scarica il round) e LEGGIMI.txt. Si può rifissare finché il sorteggio non è fatto. Senza argomenti: lo stato.
2. All'ora (job_sorteggio, ogni 30 secondi): la randomness del round (due relay concordi, SHA-256 e firma BLS come
   la lottery; se il round non c'è ancora si riprova, vale sempre quello annunciato), il calendario a 38 giornate
   (shared/calendario_sorteggio.genera: struttura di Henry, mai più di 2 di fila in casa o fuori), salvato in
   lega_calendario_sorteggio; sul canale il risultato col CSV giornata,casa,trasferta; agli admin il promemoria delle date.
3. /importa_date (admin, didascalia del CSV o in risposta): le date delle 38 giornate, `giornata,giorno1[,…,giorno4]`
   con in fondo, se si vuole, le squadre NBA a media (formato come /importa_playoff). Unite al sorteggio diventano il
   calendario della stagione (calendario.importa, come un CSV degli admin: stessi controlli, stesso salvataggio).

La stagione: quella corrente se non ha ancora il calendario, altrimenti la successiva (il sorteggio si fa d'estate).
"""
import html
import io
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import classifica as C
import config
import db
from shared import calendario_sorteggio as CS
from shared import lottery as LT

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
TEMPI = {"read_timeout": 60, "write_timeout": 60, "connect_timeout": 30}
e = lambda x: html.escape(str(x), quote=False)
ESEMPIO = "giornata,giorno1,giorno2,giorno3\nG1,20/10/2027,21/10/2027,22/10/2027\nG2,23/10,24/10,OKC NOP\n…\nG38,02/02/2028,03/02/2028"
MAX_GIORNI = 4


def migra() -> None:
    db.q("""CREATE TABLE IF NOT EXISTS lega_calendario_sorteggio (
              stagione    TEXT PRIMARY KEY,
              quando      TIMESTAMPTZ NOT NULL,
              round       BIGINT NOT NULL,
              conf_a      JSONB NOT NULL,                 -- {"nome": …, "squadre": [team_id, …]} in ordine alfabetico
              conf_b      JSONB NOT NULL,
              impronta    TEXT NOT NULL,                  -- SHA-256 di calendario_sorteggio.py all'annuncio
              stato       TEXT NOT NULL DEFAULT 'annunciato',   -- annunciato → estratto → date (calendario importato)
              randomness  TEXT,
              giornate    JSONB,                          -- [[[casa, trasferta], …] × 38], team_id
              estratto    TIMESTAMPTZ)""")


def stagione() -> str:
    s = config.stagione()
    return s if not db.giornate(s) else str(int(s) + 1)


def anni(s: str) -> str:
    return f"{s}-{(int(s) + 1) % 100:02d}"


def stato(s: str) -> dict | None:
    migra()
    return db.q("SELECT * FROM lega_calendario_sorteggio WHERE stagione = %s", (s,), one=True)


def _j(x):
    return x if isinstance(x, (list, dict)) else json.loads(x)


def _chiave(t: str) -> str:
    from shared.squadre import normalizza
    return normalizza(config.nome(t))


def conference() -> list[dict]:
    """Le due conference (ordine di divisions.json), squadre in ordine alfabetico. ValueError se non sono 12 e 12."""
    import playoff
    conf, nomi = C.conference(), playoff.conferenze()
    if len(nomi) != 2:
        raise ValueError("servono due conference in divisions.json")
    out = [{"nome": n, "squadre": sorted((t for t, c in conf.items() if c == n and config.squadra(t)), key=_chiave)} for n in nomi]
    for c in out:
        if len(c["squadre"]) != 12:
            raise ValueError(f"la conference {c['nome']} ha {len(c['squadre'])} squadre, ne servono 12")
    if any("," in config.nome(t) for c in out for t in c["squadre"]):
        raise ValueError("un nome di squadra contiene una virgola: lo script le usa per separare le squadre")
    return out


def _nomi(squadre: list[str]) -> str:
    return ",".join(config.nome(t) for t in squadre)


def comando(r: dict) -> str:
    a, b = _j(r["conf_a"]), _j(r["conf_b"])
    return f'python3 calendario_sorteggio.py genera --round {r["round"]} --a "{_nomi(a["squadre"])}" --b "{_nomi(b["squadre"])}"'


def testo_annuncio(r: dict) -> str:
    a, b = _j(r["conf_a"]), _j(r["conf_b"])
    q = r["quando"].astimezone(ROMA)
    return (f"📅 <b>Sorteggio del calendario {anni(r['stagione'])}</b>: il {q:%d/%m} alle {q:%H:%M}.\n\n"
            f"Il seme è il round <b>{r['round']}</b> di drand (rete quicknet, League of Entropy), che esce a quell'ora: "
            "nessuno lo conosce prima, chiunque lo può leggere dopo.\n\n"
            f"<b>{e(a['nome'])}</b>: " + ", ".join(e(config.nome(t)) for t in a["squadre"]) + "\n"
            f"<b>{e(b['nome'])}</b>: " + ", ".join(e(config.nome(t)) for t in b["squadre"]) + "\n\n"
            "Struttura: andata nella conference (G1–G11), contro l'altra conference (G12–G23), ritorno (G24–G34), "
            "ultime 4 tra tutti (G35–G38); 19 in casa e 19 fuori, <b>mai più di 2 di fila in casa o fuori</b>.\n\n"
            f"Impronta del codice (SHA-256 di calendario_sorteggio.py): <code>{r['impronta']}</code>\n"
            f"Il round su drand, da aprire nel browser dopo l'ora: {LT.link_round(r['round'])}\n"
            "Per rifarlo: i file allegati qui sotto (calendario_sorteggio.py, lottery.py, LEGGIMI.txt con le istruzioni), "
            f"poi <code>{e(comando(r))}</code>")


def leggimi(r: dict) -> str:
    q = r["quando"].astimezone(ROMA)
    return f"""SORTEGGIO DEL CALENDARIO {anni(r['stagione'])} · COME VERIFICARLO

Sorteggio: {q:%d/%m/%Y} alle {q:%H:%M} (ora di Roma).
Seme: il round {r['round']} di drand, rete quicknet (League of Entropy). Esce a quell'ora: prima non lo conosce nessuno.
Impronta del codice (SHA-256 di calendario_sorteggio.py): {r['impronta']}

COSA SERVE
- Python 3.9 o più recente (python.org, o già installato su Mac e Linux). Nient'altro: solo la libreria standard.
- I file allegati calendario_sorteggio.py e lottery.py nella stessa cartella (lottery.py serve solo a scaricare
  il round da drand).
- Facoltativo: «pip install py_ecc» per verificare anche la firma crittografica del round.

1. CONTROLLARE CHE IL CODICE SIA QUELLO ANNUNCIATO
   Da terminale, nella cartella dei file:
       sha256sum calendario_sorteggio.py            (Linux)
       shasum -a 256 calendario_sorteggio.py        (Mac)
       certutil -hashfile calendario_sorteggio.py SHA256   (Windows)
   Il risultato deve essere: {r['impronta']}

2. RIFARE IL SORTEGGIO (dopo l'ora)
       {comando(r)}
   Le squadre di ogni conference in ordine alfabetico, come nell'annuncio. Esce il calendario delle 38 giornate e,
   per ogni squadra, casa (C) e fuori (f) giornata per giornata: deve essere quello pubblicato sul canale.
   Con «--csv calendario.csv» lo scrive anche in un file.

3. CONTROLLARE IL NUMERO CASUALE SENZA LO SCRIPT
   Aprire nel browser (dopo l'ora): {LT.link_round(r['round'])}
   Il campo «randomness» deve essere quello scritto dal bot sul canale; con
       python3 calendario_sorteggio.py genera --randomness QUEL_NUMERO --a "…" --b "…"
   lo script non scarica niente.

4. VEDERE LO SCHEMA E I SUOI CONTROLLI
       python3 calendario_sorteggio.py schema

COME FUNZIONA
Nel file c'è un calendario «a posti» (A1-A12, B1-B12) che rispetta tutte le regole: la struttura di Henry (andata,
interconference, ritorno a campi invertiti, ultime 4, 6 squadre A in casa in ogni giornata interconference, 17 in casa
nelle prime 34) e in più mai più di 2 partite di fila nello stesso campo. Il caso decide soltanto chi va in quale
posto: le 12 squadre di ogni conference mescolate con numeri ricavati dalla randomness del round con SHA-256. Ogni
posto ha le stesse garanzie, quindi qualunque sorteggio le rispetta; i controlli di Henry e quelli in più girano su
ogni calendario generato.
"""


async def allega_codice(bot, chat, r: dict) -> None:
    from telegram import InputMediaDocument
    import os
    file = [("calendario_sorteggio.py", open(os.path.join(LT.CARTELLA, "calendario_sorteggio.py"), "rb").read()),
            ("lottery.py", open(os.path.join(LT.CARTELLA, "lottery.py"), "rb").read()),
            ("LEGGIMI.txt", leggimi(r).encode())]
    await bot.send_media_group(chat_id=chat, media=[InputMediaDocument(io.BytesIO(b), filename=n) for n, b in file], **TEMPI)


def leggi_quando(args: list[str]) -> datetime:
    from shared.date_comandi import leggi_data
    if len(args) < 2:
        raise ValueError("Uso: /calendario_quando GG/MM[/AAAA] HH:MM (ora di Roma)")
    d = leggi_data(args[0]) or leggi_data(f"{args[0]}/{datetime.now(ROMA).year}")
    if not d:
        raise ValueError(f"Data non chiara: «{args[0]}» (GG/MM o GG/MM/AAAA).")
    try:
        h, m = (int(x) for x in args[1].replace(".", ":").split(":"))
        q = datetime(d.year, d.month, d.day, h, m, tzinfo=ROMA)
    except ValueError:
        raise ValueError("L'ora come HH:MM, es. 21:00.")
    if q <= datetime.now(ROMA) + timedelta(minutes=10):
        raise ValueError("Il sorteggio va fissato almeno 10 minuti avanti.")
    return q


def testo_stato(s: str) -> str:
    r = stato(s)
    if not r:
        return (f"📅 Calendario {anni(s)}: sorteggio non ancora fissato.\n\n"
                "<code>/calendario_quando GG/MM HH:MM</code> lo fissa e lo annuncia sul canale.")
    q = r["quando"].astimezone(ROMA)
    if r["stato"] == "annunciato":
        return f"📅 Calendario {anni(s)}: sorteggio fissato il {q:%d/%m} alle {q:%H:%M}, round drand {r['round']}. Si può rifissare."
    passo = ("mancano le date: /importa_date col CSV" if r["stato"] == "estratto" else "date importate, calendario in vigore")
    return f"📅 Calendario {anni(s)}: sorteggiato il {q:%d/%m} col round {r['round']}; {passo}."


async def cmd_calendario_quando(update, context):
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    s = stagione()
    if not context.args:
        await msg.reply_text(testo_stato(s), parse_mode="HTML")
        return
    r = stato(s)
    if r and r["stato"] != "annunciato":
        await msg.reply_text(f"❌ Il calendario {anni(s)} è già sorteggiato (round {r['round']}).")
        return
    try:
        cc = conference()
        q = leggi_quando(context.args)
        rnd = LT.round_al(q)
    except (ValueError, LT.LotteryError) as er:
        await msg.reply_text(f"❌ {er}")
        return
    db.q("""INSERT INTO lega_calendario_sorteggio (stagione, quando, round, conf_a, conf_b, impronta)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (stagione) DO UPDATE SET quando = EXCLUDED.quando, round = EXCLUDED.round, conf_a = EXCLUDED.conf_a,
              conf_b = EXCLUDED.conf_b, impronta = EXCLUDED.impronta""",
         (s, q, rnd, json.dumps(cc[0]), json.dumps(cc[1]), CS.impronta()))
    r = stato(s)
    ch = config.globali().get("main_channel_id")
    if ch:
        await context.bot.send_message(chat_id=ch, text=testo_annuncio(r), parse_mode="HTML", disable_web_page_preview=True)
        await allega_codice(context.bot, ch, r)
    from handlers import _chi, log
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "sorteggio del calendario fissato", oggetto=f"stagione {anni(s)}",
               dopo=f"{q:%d/%m %H:%M}, round {rnd}")
    await log(context.bot, f"📅 Sorteggio del calendario {anni(s)} fissato da {_chi(update)}: {q:%d/%m %H:%M}, round {rnd}")
    await msg.reply_text(f"✅ Sorteggio fissato: {q:%d/%m alle %H:%M}, round drand {rnd}." +
                         (" Annunciato sul canale." if ch else " ⚠️ Manca il canale principale: niente annuncio."))


# ── il sorteggio all'ora fissata ──────────────────────────────────────────────

def csv_sorteggio(giornate: list) -> bytes:
    righe = ["giornata,casa,trasferta"] + [f"{n},{config.nome(c)},{config.nome(t)}" for n, g in enumerate(giornate, 1) for c, t in g]
    return ("\n".join(righe) + "\n").encode("utf-8")


def testo_risultato(r: dict) -> str:
    a, b = _j(r["conf_a"]), _j(r["conf_b"])
    giornate = _j(r["giornate"])
    righe = [f"📅 <b>Calendario {anni(r['stagione'])} sorteggiato</b> col round <b>{r['round']}</b> di drand.",
             f"Randomness: <code>{r['randomness']}</code>", "",
             "Casa (C) e fuori (f), dalla G1 alla G38:"]
    for conf in (a, b):
        righe += ["", f"<b>{e(conf['nome'])}</b>"]
        for t in sorted(conf["squadre"], key=_chiave):
            righe.append(f"<code>{CS.campi(giornate, t)}</code> {e(config.nome(t))}")
    righe += ["", "Tutte le partite nel file qui sotto. Le date arrivano con l'import degli admin.",
              f"Per rifarlo: i file e il LEGGIMI dell'annuncio, o il round su drand: {LT.link_round(r['round'])}"]
    return "\n".join(righe)


async def passo(bot, ora: datetime | None = None) -> str | None:
    migra()
    ora = ora or datetime.now(timezone.utc)
    r = db.q("SELECT * FROM lega_calendario_sorteggio WHERE stato = 'annunciato' AND quando <= %s ORDER BY quando LIMIT 1",
             (ora,), one=True)
    if not r:
        return None
    try:
        rnd = LT.randomness(r["round"])
    except LT.LotteryError as er:
        return f"round {r['round']} non ancora disponibile: {er}"
    a, b = _j(r["conf_a"]), _j(r["conf_b"])
    giornate = CS.genera(a["squadre"], b["squadre"], rnd)
    db.q("UPDATE lega_calendario_sorteggio SET stato = 'estratto', randomness = %s, giornate = %s, estratto = NOW() "
         "WHERE stagione = %s AND stato = 'annunciato'", (rnd, json.dumps(giornate), r["stagione"]))
    r = stato(r["stagione"])
    ch = config.globali().get("main_channel_id")
    if ch:
        await bot.send_message(chat_id=ch, text=testo_risultato(r)[:4096], parse_mode="HTML", disable_web_page_preview=True)
        await bot.send_document(chat_id=ch, document=io.BytesIO(csv_sorteggio(giornate)),
                                filename=f"calendario_{anni(r['stagione'])}.csv", **TEMPI)
    gruppo = config.gruppo_admin()
    if gruppo:
        await bot.send_message(chat_id=gruppo, text=f"📅 Calendario {anni(r['stagione'])} sorteggiato. Ora le date delle 38 "
                               f"giornate: /importa_date col CSV.\n\n<code>{e(ESEMPIO)}</code>", parse_mode="HTML")
    return f"calendario {anni(r['stagione'])} sorteggiato (round {r['round']})"


async def job_sorteggio(context) -> None:
    try:
        esito = await passo(context.bot)
        if esito and "sorteggiato" in esito:
            from handlers import log
            await log(context.bot, f"📅 {e(esito)}")
    except Exception:
        logger.exception("sorteggio del calendario")


# ── le date ────────────────────────────────────────────────────────────────────

def leggi_date(testo: str, s: str) -> list[dict]:
    """[{numero, dal, al, media_file}] dal CSV delle date (38 giornate). Errore con tutti i problemi trovati."""
    from calendario_playoff import _data
    errori, out = [], []
    for i, riga in enumerate(testo.replace("\r", "").split("\n"), 1):
        celle = [c.strip() for c in re.split(r"[;,\t]", riga)]
        celle = [c for c in celle if c]
        if not celle:
            continue
        m = re.fullmatch(r"[Gg]?(\d{1,2})", celle[0])
        if not m:
            if i == 1:
                continue
            errori.append(f"riga {i}: «{celle[0]}» non è una giornata (G1…G{CS.GIORNATE})")
            continue
        n, giorni, media = int(m.group(1)), [], []
        for c in celle[1:]:
            d = _data(c, s)
            if d:
                giorni.append(d)
            elif re.fullmatch(r"[A-Za-z]{2,4}( +[A-Za-z]{2,4})*", c):
                media += c.upper().split()
            else:
                errori.append(f"riga {i}: «{c}» non è una data né delle sigle NBA")
        if not 1 <= len(giorni) <= MAX_GIORNI:
            errori.append(f"riga {i}: G{n} ha {len(giorni)} giorni (da 1 a {MAX_GIORNI})")
            continue
        if any(y - x != timedelta(days=1) for x, y in zip(giorni, giorni[1:])):
            errori.append(f"riga {i}: G{n}, i giorni non sono consecutivi")
            continue
        out.append({"numero": n, "dal": giorni[0], "al": giorni[-1], "media_file": sorted(set(media))})
    nn = sorted(g["numero"] for g in out)
    if not errori and nn != list(range(1, CS.GIORNATE + 1)):
        errori.append(f"servono le giornate da G1 a G{CS.GIORNATE}, una volta ciascuna (trovate {len(nn)})")
    if errori:
        raise ValueError("\n".join(errori))
    return sorted(out, key=lambda g: g["numero"])


def testo_csv(giornate_date: list[dict], partite: list) -> str:
    """Il calendario nel formato del CSV degli admin («Week N GG/MM - GG/MM (media …)», «casa,,V,,trasferta»)."""
    righe = []
    for g in giornate_date:
        righe.append(f"Week {g['numero']} {g['dal']:%d/%m} - {g['al']:%d/%m}" +
                     (f" (media {','.join(g['media_file'])})" if g["media_file"] else "") + ",,,,")
        righe += [f"{config.nome(c)},,V,,{config.nome(t)}" for c, t in partite[g["numero"] - 1]]
        righe.append(",,,,")
    return "\n".join(righe) + "\n"


def importa_date(testo: str, s: str | None = None) -> dict:
    """Date + sorteggio → calendario della stagione (calendario.importa). ValueError se manca qualcosa."""
    import calendario
    s = s or stagione_sorteggiata()
    r = stato(s) if s else None
    if not r or r["stato"] == "annunciato":
        raise ValueError("prima il sorteggio del calendario (/calendario_quando), poi le date")
    gg = leggi_date(testo, s)
    try:
        esito = calendario.importa(testo_csv(gg, _j(r["giornate"])), s)
    except calendario.ErroreCalendario as er:
        raise ValueError(str(er))
    db.q("UPDATE lega_calendario_sorteggio SET stato = 'date' WHERE stagione = %s", (s,))
    return esito


def stagione_sorteggiata() -> str | None:
    """La stagione più recente col sorteggio fatto (le date si importano dopo, anche quando il calendario c'è già)."""
    migra()
    r = db.q("SELECT stagione FROM lega_calendario_sorteggio WHERE stato <> 'annunciato' ORDER BY stagione DESC LIMIT 1", one=True)
    return r["stagione"] if r else None


async def cmd_importa_date(update, context):
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    doc = msg.document or (msg.reply_to_message.document if msg.reply_to_message else None)
    if not doc:
        await msg.reply_text("Manda il CSV con le date delle 38 giornate con didascalia /importa_date, oppure rispondi con "
                             f"/importa_date al messaggio che lo contiene. Formato:\n\n{ESEMPIO}\n\n"
                             f"Da 1 a {MAX_GIORNI} giorni NBA consecutivi; in fondo, se vuoi, le squadre NBA a media.")
        return
    dati = bytes(await (await doc.get_file()).download_as_bytearray())
    try:
        testo = dati.decode("utf-8-sig")
    except UnicodeDecodeError:
        testo = dati.decode("latin-1")
    try:
        r = importa_date(testo)
    except ValueError as er:
        await msg.reply_text(f"❌ <b>Date non importate</b>\n\n{e(er)[:3500]}", parse_mode="HTML")
        return
    import calendario
    if r["stagione"] == config.stagione():
        calendario.ricalcola()
    from handlers import _chi, log
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "date del calendario importate", oggetto=f"stagione {anni(r['stagione'])}",
               dopo=f"{r['giornate']} giornate, dal {r['dal']:%d/%m/%Y} al {r['al']:%d/%m/%Y}")
    await log(context.bot, f"📅 Date del calendario {anni(r['stagione'])} importate da {_chi(update)}: "
                           f"{r['giornate']} giornate, dal {r['dal']:%d/%m/%Y} al {r['al']:%d/%m/%Y}")
    await msg.reply_text(f"✅ <b>Calendario {anni(r['stagione'])}</b>: sorteggio e date uniti, {r['giornate']} giornate, "
                         f"{r['partite']} partite, dal {r['dal']:%d/%m/%Y} al {r['al']:%d/%m/%Y}.\n\n"
                         "Controllo con le partite NBA: /calendario_check (quando ESPN ha il calendario della stagione).",
                         parse_mode="HTML")


def get_handlers() -> list:
    from telegram.ext import CommandHandler, MessageHandler, filters
    return [CommandHandler("calendario_quando", cmd_calendario_quando),
            CommandHandler("importa_date", cmd_importa_date),
            MessageHandler(filters.Document.ALL & filters.CaptionRegex(r"^/importa_date"), cmd_importa_date)]

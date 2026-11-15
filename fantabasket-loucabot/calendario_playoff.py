"""
Calendario dei playoff (v7.9.5, Luca 14/11): le date delle giornate P, importate da un CSV (/importa_playoff).

Formato: una riga per giornata, `giornata,giorno1[,giorno2][,giorno3][,media]` (anche col «;»), riga di intestazione
facoltativa. La giornata: P1…P22, oppure il numero G (P1 = la giornata dopo l'ultima di regular season, es. G39),
oppure solo il numero (vale P). I giorni: date NBA (ora della costa est, come il calendario di regular season)
consecutive, scritte 15/04/2027, 15/04/27, 2027-04-15 o 15/04 (l'anno dalla stagione). L'ultima colonna, se c'è, sono
le squadre NBA che prendono la media scritte a mano (sigle separate da spazi), da confrontare con quelle calcolate.
Fino a 22 giornate (il massimo possibile), numerate di seguito da P1, dopo l'ultima giornata di regular season e
senza sovrapporsi.

I nostri playoff si giocano durante la parte finale della regular season NBA (Luca, 14/11: non in contemporanea coi
playoff NBA), quindi le partite NBA di quei giorni ci sono già nel calendario NBA.

Le date stanno in lega_giornate_playoff, non ancora in lega_giornate: entrano in calendario (e quindi nel calcolo, nel
live, nelle formazioni) solo col passaggio ai playoff, un passo che si farà dopo. Intanto per ogni giornata il bot
calcola la prima partita e le squadre che prendono la media dalle partite NBA (come calendario.calcola).
"""
import html
import re
from datetime import date, datetime, timedelta

import config
import db
from shared import codici_giornata as CG

ESEMPIO = ("giornata,giorno1,giorno2,giorno3\n"
           "P1,18/04/2027,19/04/2027,20/04/2027\n"
           "P2,21/04/2027,22/04/2027\n"
           "P3,23/04/2027,24/04/2027,25/04/2027,MIA BOS")


class Errore(ValueError):
    pass


def migra() -> None:
    db.q("""CREATE TABLE IF NOT EXISTS lega_giornate_playoff (
              stagione      TEXT NOT NULL,
              numero_p      INT  NOT NULL,                      -- P1 … P22
              giorni        DATE[] NOT NULL,                    -- giorni NBA (costa est), consecutivi
              dal           DATE NOT NULL,
              al            DATE NOT NULL,
              media_file    TEXT[] NOT NULL DEFAULT '{}',       -- squadre a media scritte nel CSV (facoltative)
              importato     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (stagione, numero_p))""")


def _data(x: str, stagione: str) -> date | None:
    x = x.strip()
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(x, f).date()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", x)
    if m:
        g, mese = int(m.group(1)), int(m.group(2))
        try:
            return date(int(stagione) + (0 if mese >= 10 else 1), mese, g)
        except ValueError:
            return None
    return None


def leggi(testo: str, stagione: str, ultima: int) -> list[dict]:
    """[{numero_p, giorni, dal, al, media_file}] dal CSV, controllato. Errore con tutti i problemi trovati."""
    errori, out = [], []
    for i, riga in enumerate(testo.replace("\r", "").split("\n"), 1):
        celle = [c.strip() for c in re.split(r"[;,\t]", riga)]
        celle = [c for c in celle if c]
        if not celle:
            continue
        cod = celle[0].upper()
        m = re.fullmatch(r"([GP]?)(\d{1,3})", cod)
        if not m:
            if i == 1:                                   # intestazione
                continue
            errori.append(f"riga {i}: «{celle[0]}» non è una giornata (P1…P22 o G{ultima + 1}…)")
            continue
        n = int(m.group(2))
        p = n - ultima if m.group(1) == "G" else n
        giorni, media = [], []
        for c in celle[1:]:
            d = _data(c, stagione)
            if d:
                giorni.append(d)
            elif re.fullmatch(r"[A-Za-z]{2,4}( +[A-Za-z]{2,4})*", c):
                media += c.upper().split()
            else:
                errori.append(f"riga {i}: «{c}» non è una data né delle sigle NBA")
        if not 1 <= p <= CG.MAX_PLAYOFF:
            errori.append(f"riga {i}: {cod} fuori dai playoff (P1…P{CG.MAX_PLAYOFF}, cioè G{ultima + 1}…G{ultima + CG.MAX_PLAYOFF})")
            continue
        if not 1 <= len(giorni) <= 3:
            errori.append(f"riga {i}: P{p} ha {len(giorni)} giorni (da 1 a 3)")
            continue
        if any(b - a != timedelta(days=1) for a, b in zip(giorni, giorni[1:])):
            errori.append(f"riga {i}: P{p}, i giorni non sono consecutivi")
            continue
        out.append({"numero_p": p, "giorni": giorni, "dal": giorni[0], "al": giorni[-1], "media_file": sorted(set(media))})
    nn = [g["numero_p"] for g in out]
    if out and sorted(nn) != list(range(1, len(nn) + 1)):
        errori.append(f"le giornate vanno numerate di seguito da P1 (trovate: {', '.join(f'P{x}' for x in nn)})")
    out.sort(key=lambda g: g["numero_p"])
    for a, b in zip(out, out[1:]):
        if b["dal"] <= a["al"]:
            errori.append(f"P{b['numero_p']} inizia il {b['dal']:%d/%m} prima della fine di P{a['numero_p']} ({a['al']:%d/%m})")
    if not out and not errori:
        errori.append("nessuna giornata nel file")
    if errori:
        raise Errore("\n".join(errori))
    return out


def importa(testo: str, stagione: str | None = None) -> list[dict]:
    s = stagione or config.stagione()
    ultima = CG.ultima_rs(s)
    if ultima is None:
        raise Errore("prima va importato il calendario di regular season (/importa_calendario): P1 è la giornata dopo l'ultima")
    gg = leggi(testo, s, ultima)
    fine_rs = db.giornata(s, ultima)
    if fine_rs and gg[0]["dal"] <= fine_rs["al"]:
        raise Errore(f"P1 inizia il {gg[0]['dal']:%d/%m}, prima della fine dell'ultima giornata di regular season "
                     f"(G{ultima}, fino al {fine_rs['al']:%d/%m})")
    migra()
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lega_giornate_playoff WHERE stagione = %s", (s,))
            for g in gg:
                cur.execute("INSERT INTO lega_giornate_playoff (stagione, numero_p, giorni, dal, al, media_file) "
                            "VALUES (%s, %s, %s, %s, %s, %s)", (s, g["numero_p"], g["giorni"], g["dal"], g["al"], g["media_file"]))
    return gg


def giornate(stagione: str | None = None) -> list[dict]:
    migra()
    return db.q("SELECT * FROM lega_giornate_playoff WHERE stagione = %s ORDER BY numero_p",
                (stagione or config.stagione(),), many=True) or []


def controllo(stagione: str | None = None) -> str:
    """Il riepilogo (dopo l'import e con /calendario_playoff): per ogni P la G, i giorni, la prima partita e le squadre
    che prendono la media dalle partite NBA di adesso, confrontate con quelle del file se ci sono."""
    import calendario
    s = stagione or config.stagione()
    gg = giornate(s)
    if not gg:
        return "Nessun calendario dei playoff: mandalo con /importa_playoff (il CSV come allegato)."
    ultima = CG.ultima_rs(s) or 0
    sq = db.squadre_nba(s)
    e = lambda x: html.escape(str(x), quote=False)
    righe = [f"🏆 <b>Calendario dei playoff {s}</b>: {len(gg)} giornate, P1 = G{ultima + 1}", ""]
    diverse = 0
    for g in gg:
        c = calendario.calcola(g, sq)
        giorni = ", ".join(f"{d:%d/%m}" for d in g["giorni"])
        riga = f"<b>P{g['numero_p']}</b> (G{ultima + g['numero_p']}) · {giorni}"
        if not c["partite_nba"]:
            riga += " · <i>nessuna partita NBA in calendario</i>"
        else:
            riga += f" · prima partita {calendario.ora(c['prima_partita'])}"
            media = c["media"] or []
            riga += f" · a media: {', '.join(media) or 'nessuno'}"
            if g["media_file"] and sorted(g["media_file"]) != sorted(media):
                diverse += 1
                riga += f" ⚠️ nel file: {', '.join(g['media_file'])}"
        righe.append(riga)
    righe += ["", (f"⚠️ {diverse} {'giornata' if diverse == 1 else 'giornate'} con squadre a media diverse da quelle del file." if diverse else
                   "Le squadre a media sono calcolate dalle partite NBA di adesso (fine della regular season NBA): se il "
                   "calendario NBA cambia (rinvii), ricontrolla con /calendario_playoff.")]
    righe.append("<i>Le giornate P entrano in calendario col passaggio ai playoff.</i>")
    return "\n".join(righe)


async def cmd_importa_playoff(update, context):
    """/importa_playoff come didascalia del CSV, o in risposta al messaggio col CSV (admin)."""
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    doc = msg.document or (msg.reply_to_message.document if msg.reply_to_message else None)
    if not doc:
        await msg.reply_text("Manda il CSV del calendario dei playoff con didascalia /importa_playoff, oppure rispondi con "
                             f"/importa_playoff al messaggio che lo contiene. Formato:\n\n{ESEMPIO}\n\n"
                             "Fino a 22 giornate, giorni consecutivi (da 1 a 3); in fondo, se vuoi, le squadre NBA a media.")
        return
    dati = bytes(await (await doc.get_file()).download_as_bytearray())
    try:
        testo = dati.decode("utf-8-sig")
    except UnicodeDecodeError:
        testo = dati.decode("latin-1")
    try:
        gg = importa(testo)
    except Errore as err:
        await msg.reply_text(f"❌ <b>Calendario dei playoff non importato</b>\n\n{html.escape(str(err))[:3500]}", parse_mode="HTML")
        return
    from handlers import _chi, log
    from registro import segna_sync                        # v7.13.0: anche nel registro, non solo sul canale log
    segna_sync(update.effective_user, "admin", "calendario dei playoff importato", oggetto=f"stagione {config.stagione()}",
               dopo=f"{len(gg)} giornate, dal {gg[0]['dal']:%d/%m} al {gg[-1]['al']:%d/%m}")
    await msg.reply_text(controllo(), parse_mode="HTML")
    await log(context.bot, f"🏆 Calendario dei playoff importato da {_chi(update)}: {len(gg)} giornate, "
                           f"dal {gg[0]['dal']:%d/%m} al {gg[-1]['al']:%d/%m}")


async def cmd_calendario_playoff(update, context):
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    await msg.reply_text(controllo(), parse_mode="HTML")


def get_handlers() -> list:
    from telegram.ext import CommandHandler, MessageHandler, filters
    return [CommandHandler("importa_playoff", cmd_importa_playoff),
            MessageHandler(filters.Document.ALL & filters.CaptionRegex(r"^/importa_playoff"), cmd_importa_playoff),
            CommandHandler("calendario_playoff", cmd_calendario_playoff)]

"""
Quasi NBA Cup in loucabot (v7.9.0, Luca 14/11): regole, dati e immagine in shared/quasi_cup.py.

- esiti(s, n, risultati): le partite della Cup (Q1 semifinali, Q2 finale) della giornata G n, dai punteggi di
  squadra del calcolo della G (stesse formazioni) con calcolo.esito: in casa la meglio classificata, bonus casa
  della regular season, scarto, supplementari. Lista vuota se nella giornata non si gioca la Cup o se le squadre
  non si sanno ancora (qualificazione non convalidata tutta, semifinali non convalidate).
- Calcolo definitivo: handlers_risultati.esegui mette gli esiti in c["cup"], risultati.salva_calcolo li salva in
  lega_calcoli.cup, risultati.convalida li scrive in lega_cup insieme alla giornata (una convalida sola).
- Live: live.aggiorna, nello stesso giro del live della G (stesse regole e frequenza), chiama aggiorna_live: un
  messaggio a parte sul canale principale per il turno, con l'immagine di /quasi_cup, sostituita a ogni giro.
  Alla convalida (dopo_convalida) il messaggio resta e diventa definitivo; dopo la finale, in più, il messaggio
  della vincitrice col premio.
- /quasi_cup: l'immagine a chi la chiede (anche nel bot principale).
"""
import asyncio
import html
import json
import logging
from datetime import datetime, timezone

import calcolo
import config
import db
from shared import quasi_cup as QC
from shared import regole

logger = logging.getLogger(__name__)
TEMPI = {"read_timeout": 60, "write_timeout": 60, "connect_timeout": 30}


CAMPI = ("turno", "giornata", "casa", "trasferta", "punti_casa", "punti_trasferta", "supp_casa", "supp_trasferta",
         "supplementari", "vince")


def completi(s: str, n: int, risultati: list[dict], anche_provvisori: bool = False) -> list[dict]:
    """Le partite della Cup nella giornata G n, con tutto quello che ha una partita del calcolo (sc, st, esito: per
    /partita, /giornata e il live). Con `anche_provvisori` (solo per mostrarle) anche le semifinali «se finisse oggi»."""
    info = QC.giornate(s)
    t = QC.turno_di(s, n, info)
    if not t or (t == 1 and not anche_provvisori and not QC.qualificazione_chiusa(s, info)):
        return []
    squadre = {}
    for r in risultati:
        squadre[r["casa"]], squadre[r["trasferta"]] = r["sc"], r["st"]
    bonus = regole.bonus_casa()
    out = []
    for casa, tr in QC.abbinamenti(s, t, info):
        if casa not in squadre or tr not in squadre:
            continue
        es = calcolo.esito(squadre[casa], squadre[tr], bonus)
        out.append({"turno": t, "giornata": n, "casa": casa, "trasferta": tr, "sc": squadre[casa], "st": squadre[tr], "esito": es,
                    "punti_casa": es["regolamentari"][0], "punti_trasferta": es["regolamentari"][1],
                    "supp_casa": es["punti_supplementari"][0] if es["punti_supplementari"] else None,
                    "supp_trasferta": es["punti_supplementari"][1] if es["punti_supplementari"] else None,
                    "supplementari": es["supplementari"], "vince": es["vince"]})
    return out


def esiti(s: str, n: int, risultati: list[dict]) -> list[dict]:
    """Le partite della Cup della giornata G n da salvare (lega_calcoli.cup, lega_cup, lega_cup_live)."""
    return [{k: r[k] for k in CAMPI} for r in completi(s, n, risultati)]


# ── Q1 e Q2 nei comandi (v7.9.1, Luca 14/11): /partita Q1, /giornata Q1, /risultati Q1, /live Q1, /pdf_giornata Q1 ──

def leggi_turno(args) -> tuple[int | None, list[str]]:
    """«Q1» o «Q2» tra gli argomenti di un comando: (turno, gli altri argomenti). Codici: G regular season, Q Cup."""
    import re
    args = list(args or [])
    for i, a in enumerate(args):
        m = re.fullmatch(r"[Qq]([12])", a.strip())
        if m:
            return int(m.group(1)), args[:i] + args[i + 1:]
    return None, args


def giornata_turno(s: str, t: int) -> dict | None:
    return QC.giornate(s)["q1" if t == 1 else "q2"]


def calcolo_turno(s: str, t: int) -> tuple[dict, dict] | None:
    """(giornata G, calcolo) del turno: il calcolo della G (live.calcolo) con le partite della Cup al posto di quelle
    del campionato. None se il turno non è in calendario."""
    import live
    g = giornata_turno(s, t)
    if not g:
        return None
    c = live.calcolo(s, g["numero"])
    return g, {**c, "risultati": completi(s, g["numero"], c["risultati"], anche_provvisori=True)}


def stato_turno(s: str, t: int, n: int) -> str | None:
    """convalidata (in lega_cup) / calcolata (proposta con la Cup da convalidare) / None."""
    if QC.risultati_cup(s, t):
        return "convalidata"
    r = db.q("SELECT stato, cup FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (s, n), one=True)
    return "calcolata" if r and r.get("cup") else None


def salvati(s: str, t: int) -> dict:
    return {r["casa"]: r for r in QC.risultati_cup(s, t)}


def nome_fase(s: str, t: int, casa: str) -> str:
    if t == 2:
        return "Finale"
    coppie = QC.abbinamenti(s, 1)
    k = next((i for i, cp in enumerate(coppie) if cp[0] == casa), 0)
    return f"Semifinale {k + 1}"


def seed(s: str) -> dict:
    """{team: posizione} delle qualificate (1–4)."""
    return {x["team"]: i + 1 for i, x in enumerate(QC.classifica(s)[:QC.QUALIFICATE])}


def provvisorio(s: str, t: int) -> bool:
    """Semifinali «se finisse oggi»: la qualificazione non è ancora tutta convalidata."""
    return t == 1 and not QC.qualificazione_chiusa(s)


def senza_squadre(s: str, t: int) -> str | None:
    """Il motivo per cui il turno non ha ancora le squadre (o non c'è), se no None."""
    if not giornata_turno(s, t):
        return f"La Q{t} non è in calendario: servono le giornate dopo il {QC.finestra(s)[1]:%d/%m}."
    if not QC.abbinamenti(s, t):
        return ("Le semifinali non hanno ancora le squadre: nessun risultato convalidato in qualificazione." if t == 1 else
                "La finale (Q2) avrà le squadre dopo la convalida delle semifinali (Q1).")
    return None


def testo_turno(s: str, t: int) -> str:
    """/risultati Q1: le partite del turno in testo, coi punteggi se ci sono (convalidati, calcolati o live)."""
    from numeri import testo as tp
    e = html.escape
    motivo = senza_squadre(s, t)
    g = giornata_turno(s, t)
    testa = (f"🏅 <b>Quasi NBA Cup · Q{t} ({QC.TURNI[t].lower()})</b>"
             + (f" · giornata {g['numero']}, {g['dal']:%d/%m} – {g['al']:%d/%m}" if g else ""))
    if motivo:
        return f"{testa}\n\n{e(motivo)}"
    n = g["numero"]
    stato = stato_turno(s, t, n)
    sv = salvati(s, t)
    iniziata = bool(g.get("prima_partita") and g["prima_partita"] <= datetime.now(timezone.utc))
    c = calcolo_turno(s, t)[1] if (iniziata or stato) and not sv else None
    righe = [testa, ""]
    for i, (casa, tr) in enumerate(QC.abbinamenti(s, t)):
        if i:
            righe.append("")
        r = sv.get(casa) or (next((x for x in c["risultati"] if x["casa"] == casa), None) if c else None)
        a, b = e(config.nome(casa)), e(config.nome(tr))
        fase = nome_fase(s, t, casa)
        if not r:
            righe.append(f"<i>{fase}</i>: {a} – {b} (in casa {a})")
            continue
        riga = f"<i>{fase}</i>: {a} <b>{tp(r['punti_casa'])}</b> – <b>{tp(r['punti_trasferta'])}</b> {b}"
        if r.get("supp_casa") is not None:
            riga += f" · suppl. {tp(r['supp_casa'])}–{tp(r['supp_trasferta'])}"
        if sv or stato:
            riga += f" → <b>{a if r['vince'] == 'casa' else b}</b>"
        righe.append(riga)
    if provvisorio(s, t):
        righe += ["", "<i>Se finisse oggi: la qualificazione non è ancora tutta convalidata.</i>"]
    elif sv:
        righe += ["", "<i>Risultati convalidati.</i>"]
    elif stato == "calcolata":
        righe += ["", "⏳ <i>Calcolati con la giornata, in attesa della convalida di un admin.</i>"]
    elif c:
        righe += ["", "🔴 <i>Live: provvisori.</i>"]
    righe += ["", f"<i>Stesse formazioni e stessi punti della giornata {n}; in casa la meglio classificata, col bonus casa. "
                  f"Il dettaglio con /partita Q{t}.</i>"]
    return "\n".join(righe)


def testo_admin(cup: list[dict]) -> str:
    """Le partite della Cup nella proposta da convalidare."""
    if not cup:
        return ""
    from numeri import testo as tp
    e = html.escape
    t = cup[0]["turno"]
    righe = ["", f"🏅 <b>Quasi NBA Cup · Q{t} ({QC.TURNI[t].lower()})</b>, con le formazioni di questa giornata:"]
    for r in cup:
        casa, tr = config.nome(r["casa"]), config.nome(r["trasferta"])
        riga = f"{e(casa)} <b>{tp(r['punti_casa'])}</b> – <b>{tp(r['punti_trasferta'])}</b> {e(tr)}"
        if r["supplementari"]:
            riga += f" · {r['supplementari']} suppl. {tp(r['supp_casa'])}–{tp(r['supp_trasferta'])}"
        righe.append(riga + f" → <b>{e(casa if r['vince'] == 'casa' else tr)}</b>")
    return "\n".join(righe)


def scrivi(cur, s: str, n: int, cup: list[dict]) -> None:
    """Alla convalida della giornata n (nella stessa transazione di risultati.convalida)."""
    cur.execute("DELETE FROM lega_cup WHERE stagione = %s AND giornata = %s", (s, n))
    for r in cup or []:
        cur.execute("""INSERT INTO lega_cup (stagione, turno, giornata, casa, trasferta, punti_casa, punti_trasferta,
                         supp_casa, supp_trasferta, vince, convalidato) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                    (s, r["turno"], n, r["casa"], r["trasferta"], r["punti_casa"], r["punti_trasferta"],
                     r["supp_casa"], r["supp_trasferta"], r["vince"]))


# ── messaggio sul canale ───────────────────────────────────────────────────────

def _salva(s: str, t: int, **campi) -> None:
    db.q("INSERT INTO lega_cup_live (stagione, turno) VALUES (%s, %s) ON CONFLICT DO NOTHING", (s, t))
    for k, v in campi.items():
        db.q(f"UPDATE lega_cup_live SET {k} = %s WHERE stagione = %s AND turno = %s", (v, s, t))


async def _pubblica(bot, s: str, t: int, ora: datetime, nota: str) -> str:
    """Manda o sostituisce l'immagine del turno sul canale principale."""
    canale = config.globali().get("main_channel_id")
    if not canale:
        return "canale principale non configurato"
    d = QC.dati(s, ora)
    png = await asyncio.to_thread(QC.immagine, d)
    cap = QC.didascalia(d) + (f"\n<i>{nota}</i>" if nota else "")
    st = QC.live(s, t) or {}
    if st.get("message_id"):
        from telegram import InputMediaPhoto
        try:
            await bot.edit_message_media(chat_id=st["chat_id"], message_id=st["message_id"],
                                         media=InputMediaPhoto(png, caption=cap, parse_mode="HTML"), **TEMPI)
            return "aggiornata"
        except Exception as err:
            t_err = str(err).lower()
            if "not modified" in t_err:
                return "aggiornata"
            if not any(x in t_err for x in ("not found", "can't be edited", "message to edit")):
                raise                                     # rete lenta: si riprova al giro dopo, senza doppioni
            logger.info("Cup Q%s: messaggio non sostituibile (%s), ne mando uno nuovo", t, err)
    m = await bot.send_photo(chat_id=canale, photo=png, caption=cap, parse_mode="HTML", **TEMPI)
    _salva(s, t, chat_id=canale, message_id=m.message_id)
    return "pubblicata"


async def aggiorna_live(bot, s: str, n: int, c: dict, ora: datetime) -> str | None:
    """Dal giro del live della G n (live.aggiorna, che ha già fatto il calcolo c): se nella giornata si gioca la Cup."""
    t = QC.turno_di(s, n)
    if not t:
        return None
    cup = c.get("cup")
    if cup is None:
        cup = esiti(s, n, c["risultati"])
    if not cup:
        return None
    st = QC.live(s, t) or {}
    if st.get("chiuso"):
        return None
    _salva(s, t, risultati=json.dumps(cup, default=str), aggiornato=ora)
    esito = await _pubblica(bot, s, t, ora, "Provvisori: si convalidano con la giornata.")
    return f"Cup Q{t} {esito}"


async def dopo_convalida(bot, s: str, n: int) -> str:
    """Alla convalida della giornata n: il messaggio della Cup diventa definitivo (resta sul canale); dopo la finale
    anche il messaggio della vincitrice."""
    t = QC.turno_di(s, n)
    if not t or not QC.risultati_cup(s, t):
        return ""
    ora = datetime.now(timezone.utc)
    gia = (QC.live(s, t) or {}).get("chiuso")
    _salva(s, t, chiuso=ora)
    esito = await _pubblica(bot, s, t, ora, "")
    righe = [f"Cup Q{t} definitiva sul canale ({esito})"]
    vinc = QC.campione(s) if t == 2 else None
    canale = config.globali().get("main_channel_id")
    if vinc and canale and not gia:
        nome = html.escape(config.nome(vinc))
        await bot.send_message(chat_id=canale, parse_mode="HTML", text=(
            f"🏆 <b>{nome} vince la Quasi NBA Cup {html.escape(s)}!</b>\n\n"
            f"Premio: un <b>cambio ruolo Cup</b> in più per il resto della stagione (nel bot principale, tra i cambi ruolo) "
            f"e la vittoria di ogni spareggio per il seed in regular season."))
        righe.append("annunciata la vincitrice")
    return ", ".join(righe)


# ── /quasi_cup ─────────────────────────────────────────────────────────────────

def get_handlers() -> list:
    from telegram.ext import CommandHandler
    return [CommandHandler("quasi_cup", QC.cmd_quasi_cup, block=False)]

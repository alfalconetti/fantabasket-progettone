"""Cose comuni di IPanchinari: giornata di riferimento, orari, partite dei giocatori, canale log."""
import html
import logging
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import config
import db

logger = logging.getLogger(__name__)
e = html.escape
ROMA = ZoneInfo("Europe/Rome")
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
# Da ripetere ovunque si parla di aggiornare il quintetto nel bot: fa fede Yahoo.
FAVORE = "non è obbligatorio, per il regolamento fa fede Yahoo: tenerlo aggiornato qui è un favore agli admin"


def adesso() -> datetime:
    return datetime.now(timezone.utc)


def ora(t) -> str:
    if not t:
        return "?"
    t = t.astimezone(ROMA)
    return f"{GIORNI[t.weekday()]} {t:%d/%m} alle {t:%H:%M}"


def scadenza(g: dict):
    """La scadenza di una giornata: la prima partita NBA (calcolata da loucabot)."""
    return g.get("prima_partita")


def aperta(g: dict, quando=None) -> bool:
    s = scadenza(g)
    return bool(s) and (quando or adesso()) < s


def prossima_giornata(stagione: str | None = None, quando=None) -> dict | None:
    """La giornata per cui si manda la panchina: la prima con la scadenza non ancora passata."""
    quando = quando or adesso()
    return next((g for g in db.giornate(stagione or config.stagione()) if scadenza(g) and quando < scadenza(g)), None)


def giornata_in_corso(stagione: str | None = None, quando=None) -> dict | None:
    """La giornata già iniziata (scadenza passata) e non ancora finita (giorni NBA)."""
    quando = quando or adesso()
    oggi = quando.astimezone(ZoneInfo("America/New_York")).date()
    return next((g for g in db.giornate(stagione or config.stagione())
                 if scadenza(g) and scadenza(g) <= quando and g["al"] >= oggi), None)


def ora_promemoria(g: dict):
    """Le 8:00 (Roma) dell'ultimo giorno prima della prima partita: se si gioca di notte, la
    mattina prima; se la prima partita è nel pomeriggio italiano, la mattina stessa."""
    s = scadenza(g)
    if not s:
        return None
    s_roma = s.astimezone(ROMA)
    p = datetime.combine(s_roma.date(), dtime(8, 0), tzinfo=ROMA)
    if p >= s_roma:
        p -= timedelta(days=1)
    return p


def partite_squadre_nba(g: dict) -> dict[str, list[dict]]:
    """{sigla NBA: partite della giornata} (le rinviate restano, segnate)."""
    out = {}
    for p in db.partite_nba(g["dal"], g["al"]):
        for sq, avv, casa in ((p["casa"], p["trasferta"], True), (p["trasferta"], p["casa"], False)):
            out.setdefault(sq, []).append({**p, "avversario": avv, "in_casa": casa})
    return out


def testo_partite(sigla: str | None, partite: dict[str, list[dict]], media: list[str] | None) -> str:
    if not sigla:
        return "squadra NBA ?"
    mie = partite.get(sigla, [])
    if not mie:
        return f"{sigla}: 📉 nessuna partita (media)" if media is None or sigla in (media or []) else f"{sigla}: nessuna partita"
    pezzi = []
    for p in mie:
        d = p["data_et"]
        x = f"{GIORNI[d.weekday()]} {d.day} {'vs' if p['in_casa'] else '@'} {p['avversario']}"
        if p["stato"] in ("STATUS_POSTPONED", "STATUS_CANCELED"):
            x += " (rinviata)"
        pezzi.append(x)
    return f"{sigla}: " + ", ".join(pezzi)


_SEGNI = {"out": "🔴", "suspension": "🔴", "doubtful": "🟠", "questionable": "🟡", "day-to-day": "🟡", "probable": "🟢"}


def segno_stato(stato: str | None) -> str:
    """" 🔴 Out", " 🟡 Day-To-Day"… per un nome nei bottoni e nei testi; "" se sano."""
    if not stato:
        return ""
    return f" {_SEGNI.get(stato.strip().lower(), '⚪')} {stato}"


def stati(ids) -> tuple[dict[int, str], str]:
    """({giocatore: " 🔴 Out"}, riga "🩺 Stato ESPN delle …" o "") per i giocatori indicati."""
    st, quando = db.stati_espn(list(ids))
    return ({g: segno_stato(v["stato"]) for g, v in st.items()},
            f"🩺 Infortunati da ESPN, aggiornati {ora(quando)}" if quando else "")


async def log(bot, testo: str):
    """Una riga sul canale log (parte tecnica)."""
    if not config.canale_log():
        return
    try:
        await bot.send_message(chat_id=config.canale_log(), text=testo, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as err:
        logger.warning("Canale log: %s", err)


def chi(update) -> str:
    u = update.effective_user
    return e(u.full_name or str(u.id)) if u else "?"

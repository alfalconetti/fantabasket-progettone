"""
Partite NBA da ESPN (site.api.espn.com, pubblico, senza chiave). Basketball-Reference resta la
riserva: stessa informazione, ma in HTML.

Una risposta di ESPN per un giorno contiene anche l'elenco di tutti i giorni con partite della
stagione (leagues[0].calendar): così la sincronizzazione completa sa quali giorni chiedere.
Le date di ESPN sono in UTC; il "giorno" di una partita è quello della costa est, come nei
calendari NBA e nel nostro.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

import os
URL = os.environ.get("ESPN_URL", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard")
ET = ZoneInfo("America/New_York")

# sigle di ESPN → sigle NBA (quelle che usiamo nel calendario: GSW, NOP, NYK, SAS, UTA, WAS)
SIGLE = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS", "PHO": "PHX", "BRK": "BKN"}

# le 30 squadre: tutto il resto (le partite della NBA Cup ancora da decidere, "TBD") è un segnaposto
NBA = frozenset("ATL BOS BKN CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP NYK "
                "OKC ORL PHI PHX POR SAC SAS TOR UTA WAS".split())
SEGNAPOSTO = "TBD"

NON_GIOCATE = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_SUSPENDED"}


def sigla(abbr: str) -> str:
    s = SIGLE.get(abbr, abbr)
    return s if s in NBA else SEGNAPOSTO


def stagione_lega(anno_espn: int) -> str:
    """ESPN chiama 2027 la stagione 2026-27, per noi è la 2026."""
    return str(int(anno_espn) - 1)


def leggi_giorno(dati: dict) -> list[dict]:
    """Partite di una risposta di ESPN."""
    out = []
    for e in dati.get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        squadre = {c.get("homeAway"): sigla(c["team"]["abbreviation"]) for c in comp.get("competitors", [])}
        if "home" not in squadre or "away" not in squadre:
            continue
        inizio = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        stato = ((comp.get("status") or e.get("status") or {}).get("type") or {}).get("name", "STATUS_SCHEDULED")
        out.append({
            "espn_id": str(e["id"]),
            "stagione": stagione_lega(e["season"]["year"]),
            "tipo": int(e["season"]["type"]),
            "data_et": inizio.astimezone(ET).date(),
            "inizio": inizio,
            "casa": squadre["home"],
            "trasferta": squadre["away"],
            "stato": stato,
        })
    return out


def giorni_stagione(dati: dict) -> list[date]:
    """I giorni con partite della stagione, dalla stessa risposta."""
    giorni = []
    for lega in dati.get("leagues", []):
        for t in lega.get("calendar", []):
            if isinstance(t, str):
                giorni.append(datetime.fromisoformat(t.replace("Z", "+00:00")).date())
    return sorted(set(giorni))


async def scarica_giorno(client, giorno: date) -> dict:
    r = await client.get(URL, params={"dates": giorno.strftime("%Y%m%d"), "limit": "100"})
    r.raise_for_status()
    return r.json()


async def sincronizza(giorni: list[date] | None = None, scarica=None, pausa: float = 0.3) -> dict:
    """Scarica i giorni indicati (tutta la stagione se None) e li salva.
    `scarica(giorno)` si può sostituire nelle prove. Restituisce un riepilogo."""
    import db
    client = None
    if scarica is None:
        import httpx                      # arriva con python-telegram-bot
        client = httpx.AsyncClient(timeout=30, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)

        async def scarica(g):
            return await scarica_giorno(client, g)
    try:
        if giorni is None:
            primo = await scarica(date.today())
            giorni = giorni_stagione(primo)
        salvate, errori = 0, []
        for g in giorni:
            try:
                salvate += db.salva_partite_nba(leggi_giorno(await scarica(g)))
            except Exception as e:
                errori.append(f"{g}: {e}")
                logger.warning("ESPN %s: %s", g, e)
            if pausa:
                await asyncio.sleep(pausa)
        return {"giorni": len(giorni), "partite": salvate, "errori": errori}
    finally:
        if client:
            await client.aclose()


def giorni_vicini(oggi: date | None = None, prima: int = 3, dopo: int = 14) -> list[date]:
    oggi = oggi or datetime.now(ET).date()
    return [oggi + timedelta(days=d) for d in range(-prima, dopo + 1)]

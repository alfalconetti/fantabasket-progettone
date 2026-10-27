"""
Partite NBA da ESPN (site.api.espn.com, pubblico, senza chiave). Basketball-Reference resta la
riserva: stessa informazione, ma in HTML.

Una risposta di ESPN per un giorno contiene anche l'elenco di tutti i giorni con partite della
stagione (leagues[0].calendar): così la sincronizzazione completa sa quali giorni chiedere.
Le date di ESPN sono in UTC; il "giorno" di una partita è quello della costa est, come nei
calendari NBA e nel nostro.
"""
import asyncio

import httpx                      # arriva con python-telegram-bot
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

import os
BASE = os.environ.get("ESPN_BASE", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/")
URL = os.environ.get("ESPN_URL", BASE + "scoreboard")
ET = ZoneInfo("America/New_York")


def oggi_et():
    return datetime.now(ET).date()

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


async def _json(client, url: str, params: dict | None = None, tentativi: int = 3) -> dict:
    """GET e JSON, riprovando un paio di volte (v57, Luca 27/10: di notte ESPN a volte risponde vuoto,
    «Expecting value», e il live saltava 20 minuti per una risposta storta)."""
    for i in range(tentativi):
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except (ValueError, httpx.TransportError, httpx.HTTPStatusError) as err:
            rotta = isinstance(err, httpx.HTTPStatusError) and err.response.status_code < 500 and err.response.status_code != 429
            if rotta or i == tentativi - 1:      # 404 e simili non cambiano riprovando
                raise
            await asyncio.sleep(2 * (i + 1))


async def scarica_giorno(client, giorno: date) -> dict:
    return await _json(client, URL, {"dates": giorno.strftime("%Y%m%d"), "limit": "100"})


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


# ── tabellini (box score) e fantapunti ─────────────────────────────────────────

def _client():
    import httpx                      # arriva con python-telegram-bot
    return httpx.AsyncClient(timeout=30, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)


async def _get(client, url: str, params: dict | None = None) -> dict:
    return await _json(client, url, params)


def _coppia(v: str) -> tuple[int, int]:
    a, _, b = str(v).partition("-")
    return int(a or 0), int(b or 0)


def fantapunti(t: dict, pesi: dict | None = None) -> float:
    """Regolamento (pesi_fantapunti in config/settings.json, default in shared/regole.py): punto +0,5,
    assist +2, rimbalzo offensivo +2, difensivo +1,25, tripla segnata +1,5, tiro dal campo tentato −0,5
    e segnato +1, libero tentato −0,75 e segnato +1, recupero +2, stoppata +2, palla persa −2.
    Si calcolano quando si scarica il tabellino e si salvano: dopo un cambio dei pesi, /dev_ricalcola_fp."""
    from shared import regole
    pesi = pesi or regole.pesi_fantapunti()
    return round(sum(float(p) * float(t.get(k) or 0) for k, p in pesi.items()), 2)


def leggi_tabellino(dati: dict, partita: str) -> list[dict]:
    """Una riga per giocatore a referto. `giocato` = è entrato in campo (ha le statistiche): chi è a
    referto senza entrare (DNP) ha giocato False; gli infortunati non sono proprio nel tabellino."""
    out = []
    for squadra in (dati.get("boxscore") or {}).get("players", []):
        sigla_sq = sigla(squadra["team"]["abbreviation"])
        for st in squadra.get("statistics", [])[:1]:
            chiavi = st.get("keys") or []
            for a in st.get("athletes", []):
                riga = {"partita": partita, "atleta": str(a["athlete"]["id"]), "nome": a["athlete"]["displayName"],
                        "squadra": sigla_sq, "titolare": bool(a.get("starter")), "giocato": False, "minuti": 0,
                        "pts": 0, "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0, "oreb": 0,
                        "dreb": 0, "ast": 0, "stl": 0, "blk": 0, "tov": 0, "pf": 0, "fp": 0.0}
                valori = a.get("stats") or []
                if valori and not a.get("didNotPlay"):
                    k = dict(zip(chiavi, valori))
                    n = lambda x: int(k.get(x) or 0) if str(k.get(x) or "0").lstrip("-").isdigit() else 0
                    riga["fgm"], riga["fga"] = _coppia(k.get("fieldGoalsMade-fieldGoalsAttempted", "0-0"))
                    riga["tpm"], riga["tpa"] = _coppia(k.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "0-0"))
                    riga["ftm"], riga["fta"] = _coppia(k.get("freeThrowsMade-freeThrowsAttempted", "0-0"))
                    riga.update(giocato=True, minuti=n("minutes"), pts=n("points"), oreb=n("offensiveRebounds"),
                                dreb=n("defensiveRebounds"), ast=n("assists"), stl=n("steals"), blk=n("blocks"),
                                tov=n("turnovers"), pf=n("fouls"))
                    riga["fp"] = fantapunti(riga)
                out.append(riga)
    return out


async def scarica_tabellini(partite: list[str], scarica=None, pausa: float = 1.0, finale: bool = True) -> dict:
    """Scarica e salva i tabellini delle partite indicate (id ESPN). `scarica(id)` si può sostituire
    nelle prove. Una partita va scaricata una volta sola: chi chiama passa solo quelle finite e
    senza tabellino (db.partite_senza_tabellino)."""
    import db
    client = None
    if scarica is None:
        client = _client()

        async def scarica(pid):
            return await _get(client, BASE + "summary", {"event": pid})
    salvate, righe, errori = 0, 0, []
    try:
        for pid in partite:
            try:
                tab = leggi_tabellino(await scarica(pid), pid)
                if not tab:
                    raise ValueError("tabellino vuoto")
                db.salva_tabellino(pid, tab, finale=finale)
                salvate += 1
                righe += len(tab)
            except Exception as e:
                errori.append(f"{pid}: {e}")
                logger.warning("Tabellino %s: %s", pid, e)
            if pausa:
                await asyncio.sleep(pausa)
    finally:
        if client:
            await client.aclose()
    return {"partite": salvate, "giocatori": righe, "errori": errori}


# ── infortunati ────────────────────────────────────────────────────────────────

def leggi_infortuni(dati) -> list[dict]:
    """Ogni voce con un giocatore e uno stato, ovunque sia nella risposta (la struttura di ESPN
    cambia tra endpoint). L'id del giocatore viene dal campo id o dal link /id/NNN/."""
    import re
    out, visti = [], set()

    def visita(x, squadra=None):
        if isinstance(x, dict):
            sq = x.get("abbreviation") or squadra
            if isinstance(x.get("team"), dict):
                sq = x["team"].get("abbreviation") or sq
            a = x.get("athlete")
            if isinstance(a, dict) and isinstance(x.get("status"), str):
                aid = a.get("id")
                if not aid:
                    for link in a.get("links") or []:
                        m = re.search(r"/id/(\d+)", str(link.get("href", "")))
                        if m:
                            aid = m.group(1)
                            break
                if aid and str(aid) not in visti:
                    visti.add(str(aid))
                    det = x.get("details") or {}
                    out.append({"atleta": str(aid), "nome": a.get("displayName") or "",
                                "squadra": sigla(sq) if sq else None, "stato": x["status"],
                                "dettaglio": " ".join(str(v) for v in (det.get("type"), det.get("detail"),
                                                                        x.get("shortComment")) if v)[:300]})
            for k, v in x.items():
                if k != "athlete":
                    visita(v, sq)
        elif isinstance(x, list):
            for v in x:
                visita(v, squadra)
    visita(dati)
    return out


async def scarica_infortuni(scarica=None) -> dict:
    """Snapshot della lista infortunati di ESPN, salvato per il giorno di oggi (costa est). Per il
    calcolo conta quello subito prima delle partite (db.snapshot_del_giorno); il più recente è lo
    stato che IPanchinari mostra nei builder."""
    import db
    client = None
    if scarica is None:
        client = _client()

        async def scarica():
            return await _get(client, BASE + "injuries")
    try:
        voci = leggi_infortuni(await scarica())
    finally:
        if client:
            await client.aclose()
    if not voci:
        raise ValueError("nessun infortunato nella risposta (struttura cambiata?)")
    giorno = datetime.now(ET).date()
    db.salva_infortuni(giorno, voci)
    return {"giorno": giorno, "giocatori": len(voci)}


# ── giocatori NBA (per l'abbinamento con l'anagrafica prima che ci siano tabellini) ──

SIGLE_ESPN = {v: k for k, v in SIGLE.items() if k not in ("PHO", "BRK")}


def leggi_roster(dati: dict, squadra: str) -> list[dict]:
    out = []
    for a in dati.get("athletes", []):
        voci = a.get("items") if isinstance(a, dict) and "items" in a else [a]
        for x in voci:
            if isinstance(x, dict) and x.get("id") and x.get("displayName"):
                esp = (x.get("experience") or {}).get("years") if isinstance(x.get("experience"), dict) else None
                out.append({"atleta": str(x["id"]), "nome": x["displayName"], "squadra": squadra,
                            "esperienza": esp if isinstance(esp, int) else None})
    return out


async def scarica_giocatori(scarica=None, pausa: float = 1.0) -> list[dict]:
    client = None
    if scarica is None:
        client = _client()

        async def scarica(sq):
            return await _get(client, BASE + f"teams/{SIGLE_ESPN.get(sq, sq).lower()}/roster")
    out = []
    try:
        for sq in sorted(NBA):
            try:
                out += leggi_roster(await scarica(sq), sq)
            except Exception as e:
                logger.warning("Roster ESPN %s: %s", sq, e)
            if pausa:
                await asyncio.sleep(pausa)
    finally:
        if client:
            await client.aclose()
    return out

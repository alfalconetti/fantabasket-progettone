"""
Foto dei giocatori da ESPN (Luca, 23/10), per /player (e in futuro altre immagini).

- Indirizzo: la foto ridimensionata dal «combiner» di ESPN (520×380: nitida sul telefono, poche decine di KB), se non
  risponde quella intera (`a.espncdn.com/i/headshots/nba/players/full/<id ESPN>.png`).
- Cache su disco: config/foto/<id ESPN>.png (config/ non va su git; se si perdono, il job le riscarica), più
  config/foto/indice.json con quando è stata presa e la squadra NBA di allora.
- Piano, per non farsi limitare: un job ogni minuto che, **solo nella notte americana** (2:00–6:00
  a New York), scarica al massimo UNA foto per giro: prima quelle che mancano ai giocatori a roster,
  poi chi ha cambiato squadra NBA, poi quelle più vecchie di 14 giorni. Circa 240 a notte: la prima
  volta i giocatori a roster si riempiono in un paio di notti, poi bastano pochi minuti.
- Una foto che ESPN non ha (rookie, two-way) si segna «mancante» e si riprova dopo 3 giorni.
- /player non scarica niente: se la foto non c'è ancora manda solo il testo.
"""
import json
import logging
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import db

logger = logging.getLogger(__name__)
# /foto nel container = config/foto sul server (config/ è montata in sola lettura, questa no)
CARTELLA = os.environ.get("FOTO_DIR") or os.path.join(os.path.dirname(os.environ.get("TEAMS_PATH", "/config/teams.json")), "foto")
INDICE = os.path.join(CARTELLA, "indice.json")
ET = ZoneInfo("America/New_York")
NOTTE = (time(2, 0), time(6, 0))          # notte americana: poco traffico su ESPN
VECCHIA = timedelta(days=14)
RIPROVA_MANCANTE = timedelta(days=3)
URL_PICCOLA = "https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/{a}.png&w=520&h=380"
URL_INTERA = "https://a.espncdn.com/i/headshots/nba/players/full/{a}.png"


def percorso(atleta: str) -> str | None:
    """Il file della foto, se c'è."""
    p = os.path.join(CARTELLA, f"{atleta}.png")
    return p if atleta and os.path.exists(p) else None


def _indice() -> dict:
    try:
        with open(INDICE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _salva_indice(ind: dict) -> None:
    os.makedirs(CARTELLA, exist_ok=True)
    tmp = INDICE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ind, f)
    os.replace(tmp, INDICE)


def da_scaricare(ora: datetime | None = None) -> list[str]:
    """Gli atleti a roster (con id ESPN) la cui foto va presa, in ordine di urgenza."""
    ora = ora or datetime.now(timezone.utc)
    ind = _indice()
    righe = db.q("""SELECT DISTINCT g.espn_id AS atleta, a.squadra FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                    LEFT JOIN nba_atleti a ON a.atleta = g.espn_id WHERE c.attivo AND g.espn_id IS NOT NULL""", many=True) or []
    mancano, cambiate, vecchie, da_riprovare = [], [], [], []
    for r in righe:
        a, x = r["atleta"], ind.get(r["atleta"])
        if not x:
            mancano.append(a)
            continue
        quando = datetime.fromisoformat(x["preso"])
        if x.get("mancante"):
            if ora - quando >= RIPROVA_MANCANTE:
                da_riprovare.append(a)
        elif not percorso(a):
            mancano.append(a)
        elif r["squadra"] and x.get("squadra") and r["squadra"] != x["squadra"]:
            cambiate.append(a)
        elif ora - quando >= VECCHIA:
            vecchie.append((quando, a))
    vecchie = [a for _, a in sorted(vecchie)]
    return mancano + cambiate + vecchie + da_riprovare


async def scarica(atleta: str, client=None) -> bool:
    """Scarica la foto di un atleta (prima piccola, se no intera). True se c'è."""
    import httpx
    chiudi = client is None
    client = client or httpx.AsyncClient(timeout=20, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
    ind = _indice()
    squadra = (db.q("SELECT squadra FROM nba_atleti WHERE atleta = %s", (atleta,), one=True) or {}).get("squadra")
    ok = False
    try:
        for url in (URL_PICCOLA, URL_INTERA):
            r = await client.get(url.format(a=atleta))
            if r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n" and len(r.content) > 1500:
                os.makedirs(CARTELLA, exist_ok=True)
                tmp = os.path.join(CARTELLA, f"{atleta}.png.tmp")
                with open(tmp, "wb") as f:
                    f.write(r.content)
                os.replace(tmp, os.path.join(CARTELLA, f"{atleta}.png"))
                ok = True
                break
            if r.status_code == 429:                        # limitati: ci si ferma, si riprova domani
                raise RuntimeError("ESPN: troppe richieste (429)")
    finally:
        if chiudi:
            await client.aclose()
    ind[atleta] = {"preso": datetime.now(timezone.utc).isoformat(), "squadra": squadra, **({} if ok else {"mancante": True})}
    _salva_indice(ind)
    return ok


_stop_fino: dict = {"t": None}


async def job_foto(context) -> None:
    """Ogni minuto: nella notte americana una foto alla volta."""
    ora = datetime.now(timezone.utc)
    et = ora.astimezone(ET).time()
    if not (NOTTE[0] <= et < NOTTE[1]):
        return
    if _stop_fino["t"] and ora < _stop_fino["t"]:
        return
    try:
        coda = da_scaricare(ora)
        if coda:
            await scarica(coda[0])
    except Exception as err:
        logger.warning("Foto ESPN: %s", err)
        if "429" in str(err):
            _stop_fino["t"] = ora + timedelta(hours=20)     # fermi fino alla notte dopo

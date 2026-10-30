"""
Foto dei giocatori da ESPN (Luca, 23/10), per /player (e in futuro altre immagini).

- Indirizzo: la foto ridimensionata dal «combiner» di ESPN (520×380: nitida sul telefono, poche decine di KB), se non
  risponde quella intera (`a.espncdn.com/i/headshots/nba/players/full/<id ESPN>.png`).
- Cache su disco: config/foto/<id ESPN>.png (config/ non va su git; se si perdono, il job le riscarica), più
  config/foto/indice.json con quando è stata presa e la squadra NBA di allora.
- Piano, per non farsi limitare: un job ogni minuto che, **solo nella notte americana** (2:00–6:00
  a New York), scarica al massimo UNA foto per giro: prima quelle che mancano ai giocatori a roster,
  poi a tutti gli altri attivi in NBA (in un roster ESPN), poi a tutti gli altri giocatori del database
  con un id ESPN (Luca, 30/10); poi chi ha cambiato squadra NBA, poi quelle più vecchie di 14 giorni
  (90 per chi non gioca). Circa 240 a notte: la prima
  volta i giocatori a roster si riempiono nella prima notte, tutti gli attivi (circa 530) in 2-3 notti,
  il resto del database qualche notte dopo,
  poi bastano pochi minuti (rinnovo ogni 14 giorni).
- Una foto che ESPN non ha (rookie, two-way) si segna «mancante» e si riprova dopo 3 giorni (30 per chi non gioca).
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
VECCHIA_ALTRI = timedelta(days=90)           # chi non è a roster né in un roster NBA: la foto non cambia
RIPROVA_MANCANTE_ALTRI = timedelta(days=30)
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
    """Gli atleti la cui foto va presa, in ordine di urgenza (tre livelli: 1 a roster, 2 attivi in NBA cioè in un
    roster ESPN adesso, 3 tutti gli altri del database con un id ESPN; Luca, 30/10):
    mancanti dei livelli 1, 2, 3; poi chi ha cambiato squadra; poi le vecchie (livelli 1-2 dopo 14 giorni, il
    livello 3 dopo 90: chi non gioca non cambia foto); poi le «mancanti» da riprovare (dopo 3 giorni, 30 per il 3)."""
    ora = ora or datetime.now(timezone.utc)
    ind = _indice()
    righe = db.q("""SELECT g.espn_id AS atleta, a.squadra, 1 AS livello FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                    LEFT JOIN nba_atleti a ON a.atleta = g.espn_id WHERE c.attivo AND g.espn_id IS NOT NULL
                    UNION
                    SELECT a.atleta, a.squadra, 2 FROM nba_atleti a WHERE a.squadra IS NOT NULL
                    UNION
                    SELECT a.atleta, a.squadra, 3 FROM nba_atleti a WHERE a.squadra IS NULL
                    UNION
                    SELECT g.espn_id, NULL, 3 FROM giocatori g WHERE g.espn_id IS NOT NULL AND g.espn_id <> ''""", many=True) or []
    livello = {}
    for r in righe:                                   # un atleta una volta sola, al livello più urgente
        a = r["atleta"]
        if a and (a not in livello or r["livello"] < livello[a][0]):
            livello[a] = (r["livello"], r["squadra"])
    mancano = {1: [], 2: [], 3: []}
    cambiate, vecchie, da_riprovare = [], [], []
    for a, (lv, squadra) in sorted(livello.items(), key=lambda kv: (kv[1][0], kv[0])):
        x = ind.get(a)
        if not x or (not x.get("mancante") and not percorso(a)):
            mancano[lv].append(a)
            continue
        quando = datetime.fromisoformat(x["preso"])
        if x.get("mancante"):
            if ora - quando >= (RIPROVA_MANCANTE if lv < 3 else RIPROVA_MANCANTE_ALTRI):
                da_riprovare.append(a)
        elif squadra and x.get("squadra") and squadra != x["squadra"]:
            cambiate.append(a)
        elif ora - quando >= (VECCHIA if lv < 3 else VECCHIA_ALTRI):
            vecchie.append((quando, a))
    vecchie = [a for _, a in sorted(vecchie)]
    return mancano[1] + mancano[2] + mancano[3] + cambiate + vecchie + da_riprovare


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


def stato_foto(ora: datetime | None = None) -> dict:
    """Per /dev_foto (v6.9.0): quante foto ci sono dei giocatori a roster e quali mancano."""
    ora = ora or datetime.now(timezone.utc)
    ind = _indice()
    righe = db.q("""SELECT DISTINCT g.id, g.nome_common, g.espn_id, c.team_id FROM contratti c
                    JOIN giocatori g ON g.id = c.giocatore_id WHERE c.attivo ORDER BY g.nome_common""", many=True) or []
    attivi = [r["atleta"] for r in (db.q("SELECT atleta FROM nba_atleti WHERE squadra IS NOT NULL", many=True) or [])]
    tutti = {r["atleta"] for r in (db.q("""SELECT atleta FROM nba_atleti UNION SELECT espn_id FROM giocatori
                                           WHERE espn_id IS NOT NULL AND espn_id <> ''""", many=True) or []) if r["atleta"]}
    out = {"roster": len(righe), "con_foto": 0, "attivi": len(attivi), "attivi_con_foto": sum(1 for a in attivi if percorso(a)),
           "tutti": len(tutti), "tutti_con_foto": sum(1 for a in tutti if percorso(a)), "senza_espn": [], "espn_non_ha": [], "da_prendere": [],
           "in_cartella": sum(1 for f in (os.listdir(CARTELLA) if os.path.isdir(CARTELLA) else []) if f.endswith(".png")),
           "coda": len(da_scaricare(ora))}
    for r in righe:
        a = r["espn_id"]
        if not a:
            out["senza_espn"].append(r)
        elif percorso(a):
            out["con_foto"] += 1
        elif (ind.get(a) or {}).get("mancante"):
            out["espn_non_ha"].append(r)
        else:
            out["da_prendere"].append(r)
    return out


async def cmd_dev_foto(update, context) -> None:
    """/dev_foto (solo dev): foto dei giocatori a roster, presenti e mancanti."""
    import html
    import config
    if update.effective_user.id != config.dev_id():
        return
    st = stato_foto()
    elenco = lambda xs: ", ".join(f"{html.escape(x['nome_common'])} ({html.escape(config.nome(x['team_id']))})" for x in xs[:30]) \
        + (f" … e altri {len(xs) - 30}" if len(xs) > 30 else "")
    righe = [f"📸 <b>Foto ESPN dei giocatori a roster</b>: {st['con_foto']} su {st['roster']}",
             f"Giocatori attivi in NBA (roster ESPN): {st['attivi_con_foto']} su {st['attivi']}",
             f"Tutti i giocatori del database con un id ESPN: {st['tutti_con_foto']} su {st['tutti']}",
             f"In cartella {st['in_cartella']} foto · in coda per il job notturno {st['coda']} "
             f"(2:00–6:00 a New York, una al minuto)"]
    for chiave, titolo in (("da_prendere", "Da prendere (il job ci arriva)"),
                           ("espn_non_ha", "ESPN non ce l'ha (si riprova ogni 3 giorni)"),
                           ("senza_espn", "Senza id ESPN (/espn_mancanti)")):
        if st[chiave]:
            righe += ["", f"<b>{titolo}</b>: {len(st[chiave])}", elenco(st[chiave])]
    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")

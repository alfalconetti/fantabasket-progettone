"""
Il calendario sul foglio Google "Calendario" (stesso file del Roster), tramite gas-router e la
stessa web app del Roster (azione "calendario").

A ogni aggiornamento si ricarica tutta la pagina, colonne A:E: lo script svuota i valori di A:E
(la formattazione resta) e scrive la griglia. La griglia è il CSV importato tale e quale (per
ogni giornata l'intestazione "Week N gg/mm - gg/mm (media …)" su A:E unite, poi per ogni partita
la riga "Casa | punti | V | punti | Trasferta", sotto quella dei supplementari e due vuote), con
le squadre a media calcolate dalle partite NBA nelle intestazioni e i punteggi da lega_risultati
in B e D. Si aggiorna all'import, quando cambiano le squadre a media, con /calendario_foglio e
dopo ogni giornata convalidata.
"""
import csv
import io
import logging
import os
import re

import calendario as cal
import db

logger = logging.getLogger(__name__)

RE_MEDIA = re.compile(r"\s*\(\s*media[^)]*\)", re.I)


def intestazione(originale: str, media: list[str] | None) -> str:
    """L'intestazione del CSV con le squadre a media aggiornate (None = lascia com'è)."""
    if media is None:
        return originale
    base = RE_MEDIA.sub("", originale).rstrip()
    return f"{base} (media {','.join(media)})" if media else base


def _num(x):
    return None if x is None else float(x)


def griglia(stagione: str) -> list[list]:
    """Tutta la pagina Calendario, colonne A:E, dal CSV importato: intestazioni con le squadre a
    media calcolate (testo tutto in A, il resto vuoto: A:E sono unite), squadre e V come nel CSV,
    punteggi in B e D da lega_risultati (regolamentari nella riga delle squadre, supplementari
    subito sotto). Le celle senza valore sono stringhe vuote."""
    testo = db.csv_calendario(stagione)
    if not testo:
        return []
    righe = [list(r) for r in csv.reader(io.StringIO(testo))]
    nomi = {c.strip() for r in righe for c in (r[:1] + r[4:5]) if c.strip()}
    mappa, _, _ = cal.abbina_squadre({n for n in nomi if not cal.RE_GIORNATA.match(n)})
    ris = db.risultati(stagione)
    gg = {g["numero"]: g for g in db.giornate(stagione)}
    out, numero, sotto = [], None, None
    for r in righe:
        celle = ([c.strip() for c in r] + [""] * 5)[:5]
        m = cal.RE_GIORNATA.match(",".join(r))
        if m:
            numero = int(m.group(1))
            g = gg.get(numero)
            testo_int = ",".join(r).strip().rstrip(",").strip()
            out.append([intestazione(testo_int, g["media"] if g else None), "", "", "", ""])
            sotto = None
            continue
        riga = list(celle)
        if celle[0] and celle[2].upper() == "V" and celle[4]:
            x = ris.get((numero, mappa.get(celle[0]), mappa.get(celle[4])))
            if x and x["punti_casa"] is not None:
                riga[1], riga[3] = _num(x["punti_casa"]), _num(x["punti_trasferta"])
            sotto = x
        elif sotto is not None:
            if sotto["supp_casa"] is not None:
                riga[1], riga[3] = _num(sotto["supp_casa"]), _num(sotto["supp_trasferta"])
            sotto = None
        out.append(riga)
    while out and all(v == "" for v in out[-1]):
        out.pop()
    return out


def configurato() -> bool:
    return bool(os.environ.get("GAS_ROUTER_URL"))


async def invia(righe: list[list], manda=None) -> dict:
    """POST al gas-router (/gas/calendario). `manda(payload)` si può sostituire nelle prove."""
    payload = {"action": "calendario", "righe": righe}
    if manda:
        return await manda(payload)
    import httpx
    tok_file = os.environ.get("GAS_ROUTER_TOKEN_FILE", "")
    token = open(tok_file).read().strip() if tok_file and os.path.exists(tok_file) else ""
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(os.environ["GAS_ROUTER_URL"].rstrip("/") + "/gas/calendario", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


async def manda_gas(endpoint: str, payload: dict, manda=None) -> dict:
    """POST al gas-router (/gas/<endpoint>). `manda(payload)` si può sostituire nelle prove."""
    if manda:
        return await manda(payload)
    import httpx
    tok_file = os.environ.get("GAS_ROUTER_TOKEN_FILE", "")
    token = open(tok_file).read().strip() if tok_file and os.path.exists(tok_file) else ""
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(os.environ["GAS_ROUTER_URL"].rstrip("/") + f"/gas/{endpoint}", json=payload,
                              headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


async def aggiorna(stagione: str, manda=None) -> str:
    """Aggiorna il foglio e restituisce una riga di esito per il canale log."""
    if not manda and not configurato():
        return "foglio non configurato (GAS_ROUTER_URL)"
    g = griglia(stagione)
    if not g:
        return "nessun calendario importato"
    try:
        r = await invia(g, manda)
    except Exception as err:
        logger.warning("Foglio Calendario: %s", err)
        return f"⚠️ foglio non aggiornato ({type(err).__name__}: {str(err)[:150]})"
    if r.get("error"):
        return f"⚠️ foglio non aggiornato: {str(r['error'])[:200]}"
    return f"foglio Calendario ricaricato ({r.get('righe', len(g))} righe)"

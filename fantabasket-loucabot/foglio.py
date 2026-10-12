"""
Il calendario sul foglio Google "Calendario" (stesso file del Roster), tramite gas-router.

Il foglio ha una formattazione sua che non va toccata. Il CSV importato è la mappa delle sue
righe: per ogni giornata un'intestazione "Week N gg/mm - gg/mm (media …)" (celle unite A:E), poi
per ogni partita la riga "Casa | punti | V | punti | Trasferta", subito sotto la riga dei
supplementari e due righe vuote.

loucabot manda allo script, giornata per giornata, le righe del blocco con i valori da scrivere
e None per "non toccare": l'intestazione (squadre a media calcolate dalle partite NBA) e i
punteggi in B e D (regolamentari nella riga delle squadre, supplementari subito sotto) dalla
tabella lega_risultati. Lo script trova la giornata cercando "Week N" nella colonna A e scrive
solo le celle che cambiano: niente si cancella, niente perde la formattazione.
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


def blocchi(stagione: str) -> list[dict]:
    """[{numero, righe: [[A, B, C, D, E] con None = non toccare]}] dal CSV importato."""
    testo = db.csv_calendario(stagione)
    if not testo:
        return []
    righe = [list(r) for r in csv.reader(io.StringIO(testo))]
    nomi = {c.strip() for r in righe for c in (r[:1] + r[4:5]) if c.strip()}
    mappa, _, _ = cal.abbina_squadre({n for n in nomi if not cal.RE_GIORNATA.match(n)})
    ris = db.risultati(stagione)
    gg = {g["numero"]: g for g in db.giornate(stagione)}
    out, blocco, numero, sotto = [], None, None, None
    for r in righe:
        celle = ([c.strip() for c in r] + [""] * 5)[:5]
        m = cal.RE_GIORNATA.match(",".join(r))
        if m:
            numero = int(m.group(1))
            g = gg.get(numero)
            blocco = {"numero": numero, "righe": [[intestazione(",".join(r).strip().rstrip(",").strip(),
                                                                 g["media"] if g else None), None, None, None, None]]}
            out.append(blocco)
            sotto = None
            continue
        if blocco is None:
            continue
        riga = [None] * 5
        if celle[0] and celle[2].upper() == "V" and celle[4]:
            x = ris.get((numero, mappa.get(celle[0]), mappa.get(celle[4])))
            if x and x["punti_casa"] is not None:
                riga[1], riga[3] = _num(x["punti_casa"]), _num(x["punti_trasferta"])
            sotto = x
        elif sotto is not None:
            if sotto["supp_casa"] is not None:
                riga[1], riga[3] = _num(sotto["supp_casa"]), _num(sotto["supp_trasferta"])
            sotto = None
        blocco["righe"].append(riga)
    for b in out:                       # niente righe finali senza niente da scrivere
        while len(b["righe"]) > 1 and all(v is None for v in b["righe"][-1]):
            b["righe"].pop()
    return out


def configurato() -> bool:
    return bool(os.environ.get("GAS_ROUTER_URL"))


async def invia(blocchi_: list[dict], manda=None) -> dict:
    """POST al gas-router (/gas/calendario). `manda(payload)` si può sostituire nelle prove."""
    payload = {"action": "calendario", "blocchi": blocchi_}
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


async def aggiorna(stagione: str, manda=None) -> str:
    """Aggiorna il foglio e restituisce una riga di esito per il canale log."""
    if not manda and not configurato():
        return "foglio non configurato (GAS_ROUTER_URL)"
    b = blocchi(stagione)
    if not b:
        return "nessun calendario importato"
    try:
        r = await invia(b, manda)
    except Exception as err:
        logger.warning("Foglio Calendario: %s", err)
        return f"⚠️ foglio non aggiornato ({type(err).__name__}: {str(err)[:150]})"
    if r.get("error"):
        return f"⚠️ foglio non aggiornato: {str(r['error'])[:200]}"
    esito = f"foglio Calendario: {r.get('celle', 0)} celle aggiornate"
    if r.get("non_trovate"):
        esito += f", ⚠️ giornate non trovate nel foglio: {', '.join(map(str, r['non_trovate']))}"
    return esito

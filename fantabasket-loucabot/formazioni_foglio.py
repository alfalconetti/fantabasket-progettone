"""
Formazioni sul foglio di controllo (v31, chiesto da Luca il 18/10, per trasparenza verso i GM).

Alla scadenza, quando IPanchinari congela quintetti e panchine, nel tab «Calcolo GN» del foglio di
controllo esce l'elenco degli schierati: per ogni partita, per ogni squadra, i 5 del quintetto
e la panchina in ordine, col ruolo e la squadra NBA. Niente punteggi né formule: quelli arrivano
col calcolo della mattina dopo l'ultima notte, che riscrive lo stesso tab per intero.

Se un admin corregge una formazione o una panchina a giornata chiusa, il tab si riscrive al giro
dopo (job ogni 5 minuti, che confronta un'impronta delle formazioni con quella dell'ultima
scrittura: tabella lega_foglio_formazioni). Dopo il calcolo il job non tocca più la giornata
(le correzioni passano da /ricalcola).
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

import config
import db
import risultati as R
from shared import rosa

logger = logging.getLogger(__name__)
from zoneinfo import ZoneInfo
ROMA = ZoneInfo("Europe/Rome")


def migra() -> None:
    db.q("""CREATE TABLE IF NOT EXISTS lega_foglio_formazioni (
              stagione TEXT NOT NULL,
              giornata INT  NOT NULL,
              firma    TEXT NOT NULL,
              scritto  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (stagione, giornata))""")


def firma(sch: dict) -> str:
    return hashlib.sha1(json.dumps(sch, sort_keys=True, default=str).encode()).hexdigest()


def _squadre_nba(gioc: dict) -> dict:
    atleti = [x["espn_id"] for x in gioc.values() if x.get("espn_id")]
    if not atleti:
        return {}
    return {**db.ultima_squadra(atleti, "9999-12-31"), **db.squadre_roster(atleti)}


def griglia(s: str, n: int, sch: dict | None = None) -> dict:
    """Il tab «Calcolo GN» con le sole formazioni (stesse matrici di risultati.griglia)."""
    g = db.giornata(s, n)
    sch = sch if sch is not None else R.schieramenti(s, n)
    partite = db.partite_giornata(s, n)
    ids = set()
    for x in sch.values():
        ids |= {v for v in x["quintetto"].values() if v}
        ids |= {r.get("giocatore_id") for r in (x["panchina"] or []) if r.get("giocatore_id")}
    gioc = R._giocatori(list(ids), s)
    nba = _squadre_nba(gioc)
    COL = ["Squadra", "Posto", "Ruolo", "Giocatore", "Squadra NBA", "Note"]
    W = len(COL)
    righe, sf, tx, pe, fo = [], [], [], [], []

    def nuova(valori=None, sfondo=R.SF_BIANCO, colore=R.NERO, peso="normal"):
        v = list(valori or []) + [""] * (W - len(valori or []))
        righe.append(v[:W]); sf.append([sfondo] * W); tx.append([colore] * W); pe.append([peso] * W); fo.append([""] * W)

    scad = g.get("prima_partita") if g else None
    nuova([f"Giornata {n} · formazioni congelate alla scadenza"
           + (f" ({scad.astimezone(ROMA):%d/%m %H:%M})" if scad else "")], peso="bold")
    nuova(["Solo gli schierati: punteggi e formule arrivano col calcolo, la mattina dopo l'ultima notte, che riscrive "
           "questo tab. Le correzioni degli admin si vedono qui entro qualche minuto."])
    nuova()
    nuova(COL, sfondo=R.SF_TESTA, colore="#ffffff", peso="bold")
    for k, p in enumerate(partite, 1):
        nuova([f"Partita {k}: {config.nome(p['casa'])} (casa) – {config.nome(p['trasferta'])}"], sfondo=R.SF_PART, peso="bold")
        for t in (p["casa"], p["trasferta"]):
            x = sch.get(t, {"quintetto": {}, "panchina": None})
            nome_t = config.nome(t)
            # ceduti prima della scadenza (registro dei movimenti): il panchinario esce, il titolare va corretto
            ced = rosa.ceduti(db.q, t, [r.get("giocatore_id") for r in (x["panchina"] or []) if r.get("giocatore_id")]
                              + [v for v in x["quintetto"].values() if v], scad) if scad else set()
            titolari = set()
            for ruolo in R.RUOLI:
                gid = x["quintetto"].get(ruolo)
                gg = gioc.get(gid) or {}
                titolari.add(gid)
                nuova([nome_t, f"Q-{ruolo}", ruolo, gg.get("nome_common") or "—", nba.get(gg.get("espn_id"), ""),
                       ("non più in squadra alla scadenza: da correggere" if gid in ced else "") if gid else "posto vuoto: 0"],
                      colore=R.BLU)
            if x["panchina"] is None:
                nuova([nome_t, "P", "", "panchina non mandata", "", "si gioca senza supplementari"], sfondo=R.SF_PANCA, colore=R.BLU)
                continue
            for i, b in enumerate(x["panchina"], 1):
                gid = b.get("giocatore_id")
                gg = gioc.get(gid) or {}
                nuova([nome_t, f"P{i}", b.get("ruolo") or gg.get("ruolo") or "", gg.get("nome_common") or b.get("testo") or "—",
                       nba.get(gg.get("espn_id"), ""),
                       "ceduto prima della scadenza: tolto dalla panchina, gli altri scalano" if gid and gid in ced
                       else "anche titolare: tolto dalla panchina, gli altri scalano" if gid and gid in titolari else ""],
                      sfondo=R.SF_PANCA, colore=R.BLU)
        nuova()
    return {"nome": f"Calcolo G{n}", "righe": righe, "sfondi": sf, "testi": tx, "pesi": pe, "formati": fo,
            "congela": {"righe": 0, "colonne": 0}}


def da_scrivere(s: str, ora: datetime) -> list[int]:
    """Giornate chiuse su IPanchinari, non ancora calcolate, iniziate da poco."""
    try:
        calcolate = {r["giornata"] for r in db.q("SELECT giornata FROM lega_calcoli WHERE stagione = %s", (s,), many=True) or []}
    except Exception:
        calcolate = set()
    out = []
    for g in db.giornate(s):
        if g["numero"] in calcolate or not g.get("prima_partita"):
            continue
        if g["prima_partita"] <= ora and g["prima_partita"] >= ora - timedelta(days=14) and R.giornata_chiusa(s, g["numero"]):
            out.append(g["numero"])
    return out


async def aggiorna(bot=None, ora: datetime | None = None, manda=None) -> list[str]:
    """Scrive il tab delle giornate la cui formazione è cambiata dall'ultima scrittura."""
    import foglio
    if not manda and not foglio.configurato():
        return []
    ora = ora or datetime.now(timezone.utc)
    s = config.stagione()
    fatti = []
    for n in da_scrivere(s, ora):
        sch = R.schieramenti(s, n)
        f = firma(sch)
        prima = db.q("SELECT firma FROM lega_foglio_formazioni WHERE stagione = %s AND giornata = %s", (s, n), one=True)
        if prima and prima["firma"] == f:
            continue
        r = await foglio.manda_gas("calcolo", R.payload_foglio(griglia(s, n, sch)), manda)
        if r.get("error"):
            raise RuntimeError(str(r["error"])[:200])
        db.q("""INSERT INTO lega_foglio_formazioni (stagione, giornata, firma) VALUES (%s, %s, %s)
                ON CONFLICT (stagione, giornata) DO UPDATE SET firma = EXCLUDED.firma, scritto = NOW()""", (s, n, f))
        fatti.append(f"📋 Formazioni della giornata {n} sul foglio di controllo ({'aggiornate' if prima else 'congelate'})")
    if bot and fatti:
        from handlers import log
        for t in fatti:
            await log(bot, t)
    return fatti


async def job_formazioni(context):
    try:
        await aggiorna(context.bot)
    except Exception as err:
        logger.warning("Formazioni sul foglio: %s", err)

"""
Regole dei ruoli — UNICA implementazione, usata dal bot main e dal bot aste.

Nessuna dipendenza dai bot: ogni funzione che legge/scrive il DB riceve `q`,
la funzione di query del bot chiamante:
    q(sql, params=(), one=False, many=False) -> dict | list[dict] | None
(nel main è database._q, nel bot aste pg_client.q).

Vincoli del regolamento: almeno 4 guardie (PG/SG), 4 ali (SF/PF), 2 centri (C).
"""
import random

RUOLI = ["PG", "SG", "SF", "PF", "C"]
CATEGORIA = {"PG": "G", "SG": "G", "SF": "F", "PF": "F", "C": "C"}
MINIMI = {"G": 4, "F": 4, "C": 2}

# Fasi con ruoli attivi: dichiarazioni post-trade/firma e cambi ruolo
FASI_RUOLI_RS = {"regular-season-fa", "regular-season-deadline", "playoff"}

GIORNI_RIACQUISTO = 60


# ── calcolo puro ──────────────────────────────────────────────────────────────

def deficit_minimo(fissi: list[str], flessibili: list[set[str]]) -> int:
    """Posti mancanti ai minimi nel caso migliore (0 = esiste un'assegnazione valida).
    fissi: ruoli già assegnati; flessibili: per ogni giocatore senza ruolo, le eleggibili."""
    g = sum(CATEGORIA.get(r) == "G" for r in fissi)
    f = sum(CATEGORIA.get(r) == "F" for r in fissi)
    c = sum(CATEGORIA.get(r) == "C" for r in fissi)
    cap = lambda n, k: min(n, MINIMI[k])
    stati = {(cap(g, "G"), cap(f, "F"), cap(c, "C"))}
    for eleggibili in flessibili:
        cats = {CATEGORIA[r] for r in eleggibili if r in CATEGORIA}
        if not cats:
            continue
        nuovi = set()
        for sg, sf, sc in stati:
            for k in cats:
                nuovi.add((cap(sg + (k == "G"), "G"), cap(sf + (k == "F"), "F"), cap(sc + (k == "C"), "C")))
        stati = nuovi
    return min((MINIMI["G"] - sg) + (MINIMI["F"] - sf) + (MINIMI["C"] - sc) for sg, sf, sc in stati)


# ── letture ──────────────────────────────────────────────────────────────────

def eleggibili(q, gid: int) -> list[str]:
    r = q("SELECT posizioni FROM posizioni_attuali WHERE giocatore_id = %s", (gid,), one=True)
    pos = set((r["posizioni"] if r else "").split(","))
    return [p for p in RUOLI if p in pos]


def deficit_team(q, team_id: str, stagione: str, togli=(), aggiungi=(), imposti: dict | None = None) -> int:
    """Deficit del roster di team_id, eventualmente con giocatori tolti/aggiunti e ruoli
    imposti {gid: ruolo}. Fissi = ruoli ufficiali della squadra nella stagione."""
    imposti = imposti or {}
    roster = {r["giocatore_id"] for r in q(
        "SELECT giocatore_id FROM roster_attuale WHERE team_id = %s", (team_id,), many=True) or []}
    gids = (roster - set(togli)) | set(aggiungi)
    if not gids:
        return deficit_minimo([], [])
    ufficiali = {r["giocatore_id"]: r["ruolo"] for r in q(
        "SELECT giocatore_id, ruolo FROM ruolo_attuale WHERE stagione = %s AND team_id = %s",
        (stagione, team_id), many=True) or []}
    posizioni = {r["giocatore_id"]: set((r["posizioni"] or "").split(",")) for r in q(
        "SELECT giocatore_id, posizioni FROM posizioni_attuali WHERE giocatore_id = ANY(%s)",
        (list(gids),), many=True) or []}
    fissi, flessibili = [], []
    for gid in gids:
        ruolo = imposti.get(gid) or ufficiali.get(gid)
        if ruolo:
            fissi.append(ruolo)
        else:
            flessibili.append(posizioni.get(gid, set()))
    return deficit_minimo(fissi, flessibili)


def scelta_valida(q, team_id: str, stagione: str, gid: int, ruolo: str, in_arrivo: bool = False) -> bool:
    """Il ruolo lascia rispettabili i minimi (o almeno non peggiora la situazione)?
    in_arrivo=True se il giocatore non è ancora nel roster (es. firma in corso)."""
    extra = [gid] if in_arrivo else []
    prima = deficit_team(q, team_id, stagione, aggiungi=extra)
    dopo = deficit_team(q, team_id, stagione, aggiungi=extra, imposti={gid: ruolo})
    return dopo == 0 or dopo <= prima


def ruolo_riacquisto(q, gid: int, team_id: str) -> str | None:
    """Regola dei 60 giorni: il vecchio ruolo, se la squadra ha avuto il giocatore di recente."""
    uscito = q("""SELECT 1 AS x FROM transazioni WHERE giocatore_id = %s AND team_id_da = %s
                  AND timestamp >= NOW() - (%s || ' days')::interval LIMIT 1""",
               (gid, team_id, str(GIORNI_RIACQUISTO)), one=True)
    if not uscito:
        return None
    r = q("""SELECT ruolo_a FROM cambi_ruolo WHERE giocatore_id = %s AND team_id = %s
             ORDER BY timestamp DESC, id DESC LIMIT 1""", (gid, team_id), one=True)
    return r["ruolo_a"] if r else None


def estrai_ruolo(q, team_id: str, stagione: str, gid: int, in_arrivo: bool = False) -> str | None:
    """Estrazione casuale tra le eleggibili, preferendo quelle compatibili coi minimi."""
    eleg = eleggibili(q, gid)
    if not eleg:
        return None
    validi = [r for r in eleg if scelta_valida(q, team_id, stagione, gid, r, in_arrivo)] or eleg
    return random.choice(validi)


# ── scrittura ─────────────────────────────────────────────────────────────────

def registra_ruolo(q, gid: int, team_id: str, ruolo: str, stagione: str, tipo: str,
                   ruolo_da: str | None = None) -> None:
    q("INSERT INTO cambi_ruolo (giocatore_id, team_id, ruolo_da, ruolo_a, stagione, tipo) "
      "VALUES (%s, %s, %s, %s, %s, %s)", (gid, team_id, ruolo_da, ruolo, stagione, tipo))

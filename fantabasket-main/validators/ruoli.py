"""
Vincoli di ruolo del roster (regolamento): almeno 4 guardie (PG/SG), 4 ali (SF/PF), 2 centri (C).

I giocatori con ruolo ufficiale sono FISSI; quelli senza (appena arrivati, in attesa
di dichiarazione) sono FLESSIBILI e possono coprire una qualsiasi categoria tra le
loro posizioni eleggibili. `deficit_minimo` calcola quanti "posti" mancano nel caso
migliore: 0 = esiste un'assegnazione che rispetta i vincoli.
"""
import database as db

CATEGORIA = {"PG": "G", "SG": "G", "SF": "F", "PF": "F", "C": "C"}
MINIMI    = {"G": 4, "F": 4, "C": 2}


def deficit_minimo(fissi: list[str], flessibili: list[set[str]]) -> int:
    """fissi: ruoli già assegnati; flessibili: per ogni giocatore, i ruoli eleggibili."""
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


def deficit_team(team_id: str, stagione: str, togli=(), aggiungi=(), imposti: dict | None = None) -> int:
    """Deficit del roster di team_id (eventualmente modificato: giocatori tolti/aggiunti,
    ruoli imposti {gid: ruolo}). Ruoli ufficiali = quelli della squadra in questa stagione."""
    imposti = imposti or {}
    gids = ({r["giocatore_id"] for r in db.get_roster_team(team_id) or []} - set(togli)) | set(aggiungi)
    if not gids:
        return deficit_minimo([], [])
    ufficiali = {r["giocatore_id"]: r["ruolo"] for r in db._q(
        "SELECT giocatore_id, ruolo FROM ruolo_attuale WHERE stagione = %s AND team_id = %s",
        (stagione, team_id), many=True) or []}
    posizioni = {r["giocatore_id"]: set((r["posizioni"] or "").split(",")) for r in db._q(
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

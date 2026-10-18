"""
Di che squadra era un giocatore in un certo momento (v5.11.0), dal registro dei movimenti del bot
principale (movimenti_giocatori = transazioni sui giocatori): l'ultimo movimento fino a quel momento
dice dove stava (team_id_a; NULL = tagliato, svincolato).

Usato alla scadenza delle panchine: un panchinario ceduto prima della scadenza esce dalla panchina e
gli altri scalano (calcolo di loucabot), e la chiusura di IPanchinari lo segnala agli admin (penalità).
Chi è ceduto dopo la scadenza conta per la vecchia squadra fino a fine giornata.

Nessuna dipendenza dai bot: riceve q, la funzione di query del bot chiamante
(q(sql, params, one=False, many=False)).
"""


def squadre_al(q, giocatori, quando) -> dict[int, str | None]:
    """{giocatore: squadra in quel momento (None = senza squadra)}. Chi non ha nessun movimento fino a
    quel momento non c'è nel risultato (sconosciuto: meglio non concludere niente)."""
    ids = [int(g) for g in giocatori if g]
    if not ids or quando is None:
        return {}
    if not q("SELECT to_regclass('movimenti_giocatori') AS t", one=True)["t"]:
        return {}
    righe = q("""SELECT DISTINCT ON (giocatore_id) giocatore_id, team_id_a FROM movimenti_giocatori
                 WHERE giocatore_id = ANY(%s) AND timestamp <= %s
                 ORDER BY giocatore_id, timestamp DESC, id DESC""", (ids, quando), many=True) or []
    return {r["giocatore_id"]: r["team_id_a"] for r in righe}


def ceduti(q, team_id: str, giocatori, quando) -> set[int]:
    """I giocatori che in quel momento sicuramente non erano della squadra."""
    dove = squadre_al(q, giocatori, quando)
    return {g for g, t in dove.items() if t != team_id}

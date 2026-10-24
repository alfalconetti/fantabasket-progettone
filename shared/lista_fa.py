"""
Chi «gioca in NBA» per la lista dei free agent (Luca, 24/10), la stessa regola nel bot aste (/lista_fa,
avviso all'apertura dell'asta) e nel bot principale (report delle posizioni eleggibili mancanti).

- Si mostra al massimo la stagione prima: chi non gioca in NBA da più di una stagione non c'è mai.
- Switch: quando almeno il 70% dei giocatori FIRMATI nella lega (contratti attivi: un numero stabile)
  ha giocato nella stagione in corso, conta solo la stagione in corso.
- «Ha giocato» = ha almeno una riga di bref_stats in quella stagione (si aggiungono solo quando gioca).

Le stagioni sono quelle di Basketball-Reference: la nostra stagione «2026» (2026-27) per bref è «2027».
`q(sql, params, one=..., many=...)` è la funzione di query del bot che chiama (righe come dict).
"""
QUOTA_GIOCATO = 0.7


def stagione_bref(stagione_corrente) -> str:
    return str(int(stagione_corrente) + 1)


def quota_firmati(q, stagione_corrente) -> tuple[float, int]:
    """(quota dei firmati che hanno giocato nella stagione in corso, numero dei firmati)."""
    st = stagione_bref(stagione_corrente)
    r = q("""SELECT COUNT(DISTINCT g.id) AS firmati,
                    COUNT(DISTINCT g.id) FILTER (WHERE EXISTS (
                        SELECT 1 FROM bref_stats b WHERE lower(b.nome_bref) = lower(g.nome_bref) AND b.stagione = %s)) AS giocato
             FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id WHERE c.attivo""", (st,), one=True) or {}
    firmati = r.get("firmati") or 0
    return ((r.get("giocato") or 0) / firmati if firmati else 0.0), firmati


def switch_fatto(q, stagione_corrente) -> bool:
    quota, firmati = quota_firmati(q, stagione_corrente)
    return bool(firmati) and quota >= QUOTA_GIOCATO


def stagioni_valide(q, stagione_corrente) -> tuple[str, ...]:
    """Le stagioni di bref che contano adesso: quella in corso e, prima dello switch, quella prima."""
    st = stagione_bref(stagione_corrente)
    return (st,) if switch_fatto(q, stagione_corrente) else (st, str(int(st) - 1))

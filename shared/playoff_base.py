"""
Playoff, le cose che servono a tutti i bot (v7.10.0, Luca 15/11). Il resto (seed, bozza, tabellone, serie) è in
fantabasket-loucabot/playoff.py.

- problemi_passaggio(s): cosa manca per passare alla fase playoff (`/set_fase` del bot principale la blocca):
  l'ultima giornata di regular season convalidata e il calendario dei playoff importato (/importa_playoff);
- in_gioco(q, s, g): le squadre che giocano la giornata g. In regular season tutte (None); in una giornata P solo
  quelle che ci hanno una partita (le prime due al primo turno e le eliminate non mandano la formazione: IPanchinari).
"""
from shared import codici_giornata as CG
from shared import lettura as L


def rs_finita(s: str | None = None) -> bool:
    s = s or L.stagione()
    u = CG.ultima_rs(s)
    if u is None:
        return False
    r = L.q("SELECT count(*) AS n FROM lega_risultati WHERE stagione = %s AND giornata = %s AND convalidato IS NOT NULL",
            (s, u), one=True)
    return bool(r and r["n"])


def giornate_importate(s: str | None = None) -> int:
    try:
        r = L.q("SELECT count(*) AS n FROM lega_giornate_playoff WHERE stagione = %s", (s or L.stagione(),), one=True)
    except Exception:                                    # tabella non ancora creata (loucabot non ancora aggiornato)
        return 0
    return int(r["n"]) if r else 0


def problemi_passaggio(s: str | None = None) -> list[str]:
    s = s or L.stagione()
    out = []
    u = CG.ultima_rs(s)
    if u is None:
        out.append("non c'è il calendario della regular season")
    elif not rs_finita(s):
        out.append(f"l'ultima giornata di regular season (G{u}) non è ancora convalidata")
    if not giornate_importate(s):
        out.append("non c'è il calendario dei playoff: va importato con /importa_playoff in loucabot")
    return out


def in_gioco(q, s: str, g: dict) -> set[str] | None:
    """None = tutte (regular season); in una giornata P le squadre con una partita in lega_partite."""
    if (g or {}).get("tipo") != "playoff":
        return None
    righe = q("SELECT casa, trasferta FROM lega_partite WHERE stagione = %s AND giornata = %s", (s, g["numero"]), many=True) or []
    return {t for r in righe for t in (r["casa"], r["trasferta"])}

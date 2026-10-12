"""
Ricerca di una squadra da testo libero, uguale nei due bot (v3.12.1): /roster, /assets,
/team_diff del bot principale e /team del bot aste.

Ordine: id esatto (team07) → nome squadra o nome del GM esatti (senza maiuscole e accenti)
→ inizio del nome ("buf" → Buffalo Brownies) → somiglianza (difflib, soglia 0,6).
"""
import difflib
import unicodedata


def normalizza(s: str) -> str:
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def cerca_squadra(query: str, squadre: list[dict]) -> dict | None:
    """La squadra di `squadre` (righe di teams.json) che corrisponde a `query`, o None."""
    q = normalizza(query)
    if not q:
        return None
    # 1. id esatto
    for t in squadre:
        if t["id"] == query.strip():
            return t
    campi = lambda t: [c for c in (t.get("nome", ""), t.get("gm_nome", "")) if c]
    # 2. nome squadra o GM esatti, normalizzati
    for t in squadre:
        if any(normalizza(c) == q for c in campi(t)):
            return t
    # 3. inizio del nome
    for t in squadre:
        if any(normalizza(c).startswith(q) for c in campi(t)):
            return t
    # 4. somiglianza
    candidati = {normalizza(c): t for t in squadre for c in campi(t)}
    match = difflib.get_close_matches(q, candidati.keys(), n=1, cutoff=0.6)
    return candidati[match[0]] if match else None

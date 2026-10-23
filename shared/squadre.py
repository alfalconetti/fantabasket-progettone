"""
Ricerca di una squadra da testo libero, uguale nei due bot (v3.12.1): /roster, /assets,
/team_diff del bot principale e /team del bot aste.

Ordine: id esatto (team07) → nome squadra o nome del GM esatti (senza maiuscole e accenti)
→ inizio del nome ("buf" → Buffalo Brownies) → parola per parola (v6.4.3, Luca 23/10: "Paris" →
GM Cristian Paris, "redskins" → Montecelio Redskins, "redsk" → inizio di una parola, "redskin" → una
parola quasi uguale; deve essere una squadra sola, se ce ne sono più d'una nessuna) → somiglianza
del nome intero (difflib, soglia 0,6).
"""
import difflib
import unicodedata


def normalizza(s: str) -> str:
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _parole(s: str) -> list[str]:
    return [p for p in "".join(c if c.isalnum() else " " for c in normalizza(s)).split() if p]


def per_parole(query: str, squadre: list[dict]) -> dict | None:
    """La sola squadra in cui ogni parola di `query` è una parola del nome della squadra o del GM
    (anche mescolate: "paris redskins"); se nessuna, la sola in cui ogni parola è l'inizio di una
    parola; se nessuna, quasi uguale (≥ 0,8, parole di almeno 4 lettere). Così "rossi" è Rossi e non
    Rossini. None se nessuna o se più d'una (meglio niente che la squadra sbagliata)."""
    qp = _parole(query)
    if not qp:
        return None
    parole = lambda t: _parole(t.get("nome", "")) + _parole(t.get("gm_nome", ""))
    for prova in (lambda q, w: q == w,
                  lambda q, w: w.startswith(q),
                  lambda q, w: len(q) >= 4 and difflib.SequenceMatcher(None, q, w).ratio() >= 0.8):
        trovate = {t["id"]: t for t in squadre if all(any(prova(q, w) for w in parole(t)) for q in qp)}
        if len(trovate) == 1:
            return next(iter(trovate.values()))
        if trovate:
            return None
    return None


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
    # 4. parola per parola: ogni parola cercata è l'inizio di una parola del nome (o quasi uguale)
    t = per_parole(q, squadre)
    if t:
        return t
    # 5. somiglianza del nome intero
    candidati = {normalizza(c): t for t in squadre for c in campi(t)}
    match = difflib.get_close_matches(q, candidati.keys(), n=1, cutoff=0.6)
    return candidati[match[0]] if match else None

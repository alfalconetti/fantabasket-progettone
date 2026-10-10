"""
Abbinamento dei nomi dei giocatori, più severo di get_team_by_query (0.6).
Usato da /set_nascita e dalla proposta dei giocatori nuovi di Basketball-Reference.

- chiave(): minuscolo, senza accenti, senza punteggiatura (punti, apostrofi,
  trattini), spazi compattati → "Dončić" = "doncic", "D'Angelo" = "dangelo",
  "Jaren Jackson Jr." = "jaren jackson jr"
- esatti(): giocatori con la stessa chiave su nome_common, nome_bref o nome_yahoo
- simili(): somiglianza difflib >= SOGLIA sul nome intero (mai salvataggi
  automatici: chi chiama chiede sempre conferma)
"""
import difflib
import re
import unicodedata

SOGLIA = 0.88


def chiave(nome: str) -> str:
    s = unicodedata.normalize("NFD", nome or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'’`\-]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())


def _chiavi(g: dict) -> set[str]:
    return {chiave(g.get(c) or "") for c in ("nome_common", "nome_bref", "nome_yahoo") if g.get(c)}


def esatti(nome: str, giocatori: list[dict]) -> list[dict]:
    k = chiave(nome)
    return [g for g in giocatori if k and k in _chiavi(g)]


def simili(nome: str, giocatori: list[dict], soglia: float = SOGLIA, max_n: int = 5) -> list[tuple[dict, float]]:
    k = chiave(nome)
    if not k:
        return []
    punteggi = []
    for g in giocatori:
        migliore = max((difflib.SequenceMatcher(None, k, c).ratio() for c in _chiavi(g)), default=0)
        if migliore >= soglia:
            punteggi.append((g, migliore))
    punteggi.sort(key=lambda x: -x[1])
    return punteggi[:max_n]

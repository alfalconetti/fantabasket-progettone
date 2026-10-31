"""
Nomi dei giocatori scritti in qualsiasi ordine (Luca, 31/10: «Clowney Noah» non trovava Noah Clowney).

Lo usano le ricerche dei giocatori di tutti i bot, come ultimo tentativo prima della somiglianza o insieme
all'abbinamento esatto:
- parole(): minuscolo, senza accenti né punteggiatura (punti, apostrofi, trattini), suffissi Jr./Sr./II… tolti;
- stesse_parole(a, b): le stesse parole in un altro ordine («clowney noah» = «Noah Clowney»);
- contiene_parole(q, nome): ogni parola scritta è dentro una parola del nome («clown noah» → Noah Clowney);
- ordinata(): le parole in ordine alfabetico, per confronti di somiglianza indipendenti dall'ordine.
"""
import re
import unicodedata

SUFFISSI = {"jr", "sr", "ii", "iii", "iv", "v"}
_LETTERE = str.maketrans({"đ": "d", "Đ": "d", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "ß": "ss", "æ": "ae"})


def parole(testo: str) -> list[str]:
    s = unicodedata.normalize("NFKD", (testo or "").translate(_LETTERE)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[’'`.\-]", "", s)
    out = [p for p in re.split(r"[^a-z0-9]+", s) if p]
    senza = [p for p in out if p not in SUFFISSI]
    return senza or out


def stesse_parole(a: str, b: str) -> bool:
    pa = parole(a)
    return bool(pa) and sorted(pa) == sorted(parole(b))


def contiene_parole(q: str, nome: str) -> bool:
    pq, pn = parole(q), parole(nome)
    return bool(pq) and len(pq) <= len(pn) and all(any(x in n for n in pn) for x in pq)


def ordinata(testo: str) -> str:
    return " ".join(sorted(parole(testo)))

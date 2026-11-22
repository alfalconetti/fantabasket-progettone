"""
Nomi dei giocatori scritti in qualsiasi ordine (Luca, 31/10: «Clowney Noah» non trovava Noah Clowney).

Lo usano le ricerche dei giocatori di tutti i bot, come ultimo tentativo prima della somiglianza o insieme
all'abbinamento esatto:
- parole(): minuscolo, senza accenti né punteggiatura (punti, apostrofi, trattini), suffissi Jr./Sr./II… tolti;
- stesse_parole(a, b): le stesse parole in un altro ordine («clowney noah» = «Noah Clowney»);
- contiene_parole(q, nome): ogni parola scritta è dentro una parola del nome («clown noah» → Noah Clowney);
- ordinata(): le parole in ordine alfabetico, per confronti di somiglianza indipendenti dall'ordine;
- verbatim(testo) / identico(testo, nome) (v7.25.0, Luca 22/11): un nome tra apici ('Tim Hardaway', anche ’…’, "…",
  «…») si cerca solo così com'è: niente suffissi tolti, niente altro ordine («Tim Hardaway» non è più Tim Hardaway Jr.).
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


APICI = {"'": "'", "’": "’", "‘": "’", '"': '"', "“": "”", "”": "”", "«": "»", "`": "`"}


def verbatim(testo: str) -> str | None:
    """Il nome dentro gli apici, se il testo è tutto tra apici; se no None."""
    t = (testo or "").strip()
    if len(t) >= 3 and t[0] in APICI and t[-1] in (APICI[t[0]], t[0], "'", "’"):
        dentro = t[1:-1].strip()
        return dentro or None
    return None


def senza_apici(testo: str) -> str:
    v = verbatim(testo)
    return v if v is not None else (testo or "").strip()


def _tutte(testo: str) -> str:
    s = unicodedata.normalize("NFKD", (testo or "").translate(_LETTERE)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[’'`.\-]", "", s)
    return " ".join(p for p in re.split(r"[^a-z0-9]+", s) if p)


def identico(testo: str, nome: str) -> bool:
    """Lo stesso nome, suffissi compresi e nello stesso ordine (maiuscole, accenti e punteggiatura a parte)."""
    a = _tutte(testo)
    return bool(a) and a == _tutte(nome)

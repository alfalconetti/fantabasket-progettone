"""
Lettura del messaggio della panchina e abbinamento delle righe ai giocatori della squadra.

Il messaggio è quello che i GM scrivono da sempre: 5 righe, un panchinaro per riga, in ordine,
spesso con soprannomi ("Ja the sniper Morant", "Nique il califfo Clifford"). Un titolo
facoltativo sta sopra, separato da una riga vuota (o, se le righe sono più di 5, sono le prime).

L'abbinamento cerca solo tra i giocatori della squadra (una quindicina): per ogni giocatore
conta quante parole del suo nome compaiono nella riga, il cognome vale doppio, tollerando
errori di battitura, abbreviazioni e iniziali. Una riga già vista per quella squadra (alias,
salvato quando il GM conferma) si riconosce subito. Se il primo candidato non stacca il
secondo, decide il GM coi bottoni.
"""
import difflib
import re
import unicodedata

SUFFISSI = {"jr", "sr", "ii", "iii", "iv", "v"}
_LETTERE = str.maketrans({"đ": "d", "Đ": "d", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "ß": "ss", "æ": "ae"})
RE_NUMERO = re.compile(r"^\s*(?:\d{1,2}\s*[.)\-:°]|[-•*·–—]|\d{1,2}\s+(?=\D))\s*")
MAX_PANCHINA = 5
SOGLIA = 0.55          # sotto: nessun candidato credibile
STACCO = 0.15          # il primo deve staccare il secondo di tanto per essere sicuro


def parole(testo: str) -> list[str]:
    s = unicodedata.normalize("NFKD", (testo or "").translate(_LETTERE)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[’'`.]", "", s)
    return [p for p in re.split(r"[^a-z0-9]+", s) if p]


def chiave(testo: str) -> str:
    """La riga normalizzata, per gli alias."""
    return " ".join(parole(testo))


def leggi_messaggio(testo: str) -> tuple[str | None, list[str], str | None]:
    """(titolo, righe della panchina, errore)."""
    blocchi, cur = [], []
    for r in (testo or "").splitlines():
        if r.strip():
            cur.append(r.strip())
        elif cur:
            blocchi.append(cur)
            cur = []
    if cur:
        blocchi.append(cur)
    if not blocchi:
        return None, [], "messaggio vuoto"
    righe = blocchi[-1]
    titolo = [" ".join(b) for b in blocchi[:-1]]
    if len(righe) > MAX_PANCHINA:
        titolo.append(" ".join(righe[:-MAX_PANCHINA]))
        righe = righe[-MAX_PANCHINA:]
    righe = [RE_NUMERO.sub("", r).strip() or r for r in righe]
    return ("\n".join(titolo).strip() or None), righe, None


def _simile(p: str, q: str) -> float:
    """Quanto la parola p della riga somiglia alla parola q del nome."""
    if p == q:
        return 1.0
    if len(p) >= 4 and len(q) >= 4 and difflib.SequenceMatcher(None, p, q).ratio() >= 0.8:
        return 0.85
    if min(len(p), len(q)) >= 3 and (p.startswith(q) or q.startswith(p)):
        return 0.7
    if len(p) == 1 and q.startswith(p):
        return 0.4
    return 0.0


def _punteggio_nome(riga: list[str], nome: str) -> float:
    """Parole del nome = separate da spazi (un nome col trattino è una parola sola, che si
    riconosce da uno qualunque dei suoi pezzi); il cognome vale doppio. Le iniziali di tutto il
    nome (SGA, KAT) valgono come un abbinamento quasi certo."""
    nomi = [parole(w) for w in nome.split()]
    nomi = [w for w in nomi if w and not (len(w) == 1 and w[0] in SUFFISSI)]
    if not nomi or not riga:
        return 0.0
    def s_parola(pezzi):
        return max(_simile(p, q) for p in riga for q in pezzi)
    pesi = [1.0] * (len(nomi) - 1) + [2.0]
    voto = sum(w * s_parola(pz) for pz, w in zip(nomi, pesi)) / sum(pesi)
    iniziali = "".join(q[0] for pz in nomi for q in pz)
    if len(iniziali) >= 2 and iniziali in riga:
        voto = max(voto, 0.9)
    return voto


def punteggio(riga: str, giocatore: dict) -> float:
    pr = [p for p in parole(riga) if p not in SUFFISSI]
    nomi = {giocatore.get(k) for k in ("nome_common", "nome_bref", "nome_yahoo", "nome_espn")} - {None, ""}
    return max((_punteggio_nome(pr, n) for n in nomi), default=0.0)


def abbina_riga(riga: str, roster: list[dict], alias: dict[str, int] | None = None) -> dict:
    """{testo, candidati: [id, …] (i migliori), scelto: id o None, certo: bool}."""
    ids = {g["id"] for g in roster}
    a = (alias or {}).get(chiave(riga))
    if a in ids:
        return {"testo": riga, "candidati": [a], "scelto": a, "certo": True}
    voti = sorted(((punteggio(riga, g), g["id"]) for g in roster), reverse=True)
    buoni = [(v, i) for v, i in voti if v >= SOGLIA]
    if not buoni:                                   # solo il nome di battesimo ("Shai", "Luka magic", "Herbet")
        pr = [p for p in parole(riga) if p not in SUFFISSI]
        per_nome = [g["id"] for g in roster
                    if any(_simile(p, n) >= 0.7 for w in (g.get("nome_common") or "").split()[:-1]
                           for n in parole(w) for p in pr)]
        buoni = [(SOGLIA, i) for i in per_nome]
    candidati = [i for _, i in buoni[:3]]
    certo = bool(buoni) and (len(buoni) == 1 or buoni[0][0] - buoni[1][0] >= STACCO)
    return {"testo": riga, "candidati": candidati, "scelto": buoni[0][1] if certo else None, "certo": certo}


def abbina_panchina(righe: list[str], roster: list[dict], alias: dict[str, int] | None = None) -> list[dict]:
    """Abbina tutte le righe; un giocatore già scelto con certezza non si propone per le altre."""
    out = [abbina_riga(r, roster, alias) for r in righe]
    presi = {x["scelto"] for x in out if x["certo"]}
    for x in out:
        if not x["certo"]:
            x["candidati"] = [c for c in x["candidati"] if c not in presi]
            if len(x["candidati"]) == 1 and punteggio(x["testo"], next(g for g in roster if g["id"] == x["candidati"][0])) >= SOGLIA:
                x["scelto"], x["certo"] = x["candidati"][0], True
                presi.add(x["scelto"])
    return out

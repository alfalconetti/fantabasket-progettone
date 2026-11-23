"""
Sorteggio del calendario di regular season (v7.28.0, Luca 15/11 e 23/11): 38 giornate con la struttura di Henry e il
seme da drand, come la lottery.

Struttura (dallo script di Henry, repo QF: Calendario.py e Calendario_ultime4.py):
- G1-G11 andata intraconference (ogni coppia della stessa conference una volta);
- G12-G23 interconference (ogni A contro ogni B una volta; 6 squadre A in casa per giornata; 6 casa e 6 fuori a testa);
- G24-G34 ritorno: stesse giornate dell'andata, casa e trasferta invertite; 17 in casa e 17 fuori a testa;
- G35-G38 le ultime 4: tra tutte le 24, 2 in casa e 2 fuori a testa, nessuna coppia due volte.
In più (Luca 15/11: «troppi pezzi di partite in casa e in trasferta»): **mai più di 2 partite di fila in casa o fuori**,
su tutte le 38 giornate, passaggi tra le fasi compresi.

Come: SCHEMA qui sotto è un calendario a posti (A1-A12, B1-B12) che rispetta tutto; l'ha trovato una volta per tutte
un risolutore di vincoli (CP-SAT di OR-Tools), cercando il minimo di «doppie» (due di fila nello stesso campo). Il
caso decide soltanto chi va in quale posto: le 12 squadre di ogni conference mescolate (Fisher-Yates) con numeri
uniformi ricavati dalla randomness di un round drand annunciato prima, con SHA-256. Ogni posto ha le stesse
garanzie, quindi qualunque sorteggio le rispetta, e chiunque rifà lo stesso sorteggio con lo stesso round.

Solo libreria standard. Per scaricare un round da drand serve lottery.py nella stessa cartella (o nel repo).

Uso:
    python3 calendario_sorteggio.py genera --round N --a "SQ1,SQ2,…" --b "SQ13,…" [--csv FILE]
    python3 calendario_sorteggio.py genera --randomness HEX --a "…" --b "…"
    python3 calendario_sorteggio.py schema          (lo schema a posti e i suoi controlli)
Le squadre di ogni conference nell'ordine annunciato (alfabetico).
"""
import argparse
import csv
import hashlib
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations

MASSIMO_DI_FILA = 2
GIORNATE = 38

# Il calendario a posti: per giornata le partite «CASA-TRASFERTA».
SCHEMA = [
    "A1-A2 A3-A9 A4-A10 A6-A5 A8-A12 A11-A7 B1-B6 B2-B8 B3-B7 B5-B4 B10-B9 B12-B11",  # G1
    "A2-A12 A5-A3 A7-A6 A9-A8 A10-A1 A11-A4 B4-B12 B6-B3 B7-B10 B8-B1 B9-B5 B11-B2",  # G2
    "A1-A5 A3-A11 A4-A2 A6-A9 A8-A10 A12-A7 B1-B9 B3-B8 B5-B7 B10-B4 B11-B6 B12-B2",  # G3
    "A4-A3 A5-A8 A7-A2 A9-A12 A10-A6 A11-A1 B2-B10 B4-B11 B6-B12 B7-B1 B8-B5 B9-B3",  # G4
    "A1-A9 A2-A10 A5-A11 A6-A4 A8-A7 A12-A3 B1-B4 B3-B2 B5-B6 B10-B8 B11-B9 B12-B7",  # G5
    "A3-A8 A4-A5 A7-A1 A9-A2 A10-A12 A11-A6 B2-B1 B4-B3 B7-B11 B8-B12 B9-B6 B10-B5",  # G6
    "A1-A4 A2-A3 A5-A7 A8-A11 A10-A9 A12-A6 B2-B9 B3-B10 B6-B8 B7-B4 B11-B1 B12-B5",  # G7
    "A3-A1 A4-A9 A5-A12 A6-A8 A7-A10 A11-A2 B1-B12 B4-B2 B5-B3 B8-B11 B9-B7 B10-B6",  # G8
    "A1-A6 A2-A5 A8-A4 A9-A7 A10-A3 A12-A11 B2-B5 B3-B1 B6-B7 B8-B4 B11-B10 B12-B9",  # G9
    "A5-A10 A6-A2 A7-A3 A8-A1 A11-A9 A12-A4 B3-B12 B5-B11 B6-B4 B7-B2 B9-B8 B10-B1",  # G10
    "A1-A12 A2-A8 A3-A6 A4-A7 A9-A5 A10-A11 B1-B5 B2-B6 B4-B9 B8-B7 B11-B3 B12-B10",  # G11
    "A5-B1 A6-B8 A7-B2 A8-B4 A11-B12 A12-B11 B3-A9 B5-A2 B6-A3 B7-A1 B9-A10 B10-A4",  # G12
    "A1-B9 A2-B6 A3-B10 A4-B1 A9-B5 A10-B3 B2-A11 B4-A12 B7-A7 B8-A5 B11-A6 B12-A8",  # G13
    "A1-B4 A5-B11 A6-B7 A8-B2 A9-B10 A12-B12 B1-A2 B3-A3 B5-A11 B6-A4 B8-A10 B9-A7",  # G14
    "A2-B8 A3-B9 A7-B5 A10-B6 A11-B3 A12-B1 B2-A1 B4-A4 B7-A8 B10-A6 B11-A9 B12-A5",  # G15
    "A2-B7 A4-B11 A5-B4 A6-B2 A9-B9 A10-B12 B1-A3 B3-A7 B5-A8 B6-A12 B8-A11 B10-A1",  # G16
    "A1-B5 A3-B8 A7-B6 A8-B10 A11-B1 A12-B3 B2-A9 B4-A6 B7-A10 B9-A5 B11-A2 B12-A4",  # G17
    "A2-B9 A3-B12 A4-B2 A6-B5 A9-B7 A10-B11 B1-A8 B3-A1 B4-A7 B6-A5 B8-A12 B10-A11",  # G18
    "A1-B8 A5-B3 A7-B10 A8-B6 A9-B1 A11-B4 B2-A10 B5-A4 B7-A12 B9-A6 B11-A3 B12-A2",  # G19
    "A2-B4 A3-B5 A4-B9 A5-B7 A10-B10 A12-B2 B1-A7 B3-A6 B6-A11 B8-A8 B11-A1 B12-A9",  # G20
    "A1-B1 A6-B6 A7-B12 A8-B3 A9-B8 A11-B11 B2-A5 B4-A3 B5-A10 B7-A4 B9-A12 B10-A2",  # G21
    "A2-B2 A3-B7 A4-B3 A5-B5 A10-B4 A12-B10 B1-A6 B6-A9 B8-A7 B9-A11 B11-A8 B12-A1",  # G22
    "A1-B6 A4-B8 A6-B12 A7-B11 A8-B9 A11-B7 B1-A10 B2-A3 B3-A2 B4-A9 B5-A12 B10-A5",  # G23
    "A2-A1 A5-A6 A7-A11 A9-A3 A10-A4 A12-A8 B4-B5 B6-B1 B7-B3 B8-B2 B9-B10 B11-B12",  # G24
    "A1-A10 A3-A5 A4-A11 A6-A7 A8-A9 A12-A2 B1-B8 B2-B11 B3-B6 B5-B9 B10-B7 B12-B4",  # G25
    "A2-A4 A5-A1 A7-A12 A9-A6 A10-A8 A11-A3 B2-B12 B4-B10 B6-B11 B7-B5 B8-B3 B9-B1",  # G26
    "A1-A11 A2-A7 A3-A4 A6-A10 A8-A5 A12-A9 B1-B7 B3-B9 B5-B8 B10-B2 B11-B4 B12-B6",  # G27
    "A3-A12 A4-A6 A7-A8 A9-A1 A10-A2 A11-A5 B2-B3 B4-B1 B6-B5 B7-B12 B8-B10 B9-B11",  # G28
    "A1-A7 A2-A9 A5-A4 A6-A11 A8-A3 A12-A10 B1-B2 B3-B4 B5-B10 B6-B9 B11-B7 B12-B8",  # G29
    "A3-A2 A4-A1 A6-A12 A7-A5 A9-A10 A11-A8 B1-B11 B4-B7 B5-B12 B8-B6 B9-B2 B10-B3",  # G30
    "A1-A3 A2-A11 A8-A6 A9-A4 A10-A7 A12-A5 B2-B4 B3-B5 B6-B10 B7-B9 B11-B8 B12-B1",  # G31
    "A3-A10 A4-A8 A5-A2 A6-A1 A7-A9 A11-A12 B1-B3 B4-B8 B5-B2 B7-B6 B9-B12 B10-B11",  # G32
    "A1-A8 A2-A6 A3-A7 A4-A12 A9-A11 A10-A5 B1-B10 B2-B7 B4-B6 B8-B9 B11-B5 B12-B3",  # G33
    "A5-A9 A6-A3 A7-A4 A8-A2 A11-A10 A12-A1 B3-B11 B5-B1 B6-B2 B7-B8 B9-B4 B10-B12",  # G34
    "A1-A2 A3-B3 A4-A12 A9-B10 A10-A11 B1-A5 B2-A7 B4-A6 B5-A8 B8-B7 B11-B6 B12-B9",  # G35
    "A2-B1 A5-B11 A6-A3 A7-A1 A8-A9 A11-B8 A12-A10 B3-B12 B6-B4 B7-B5 B9-A4 B10-B2",  # G36
    "A1-B6 A3-A2 A4-A11 A9-A5 A10-A8 B1-A12 B2-A6 B4-B7 B5-A7 B8-B3 B11-B9 B12-B10",  # G37
    "A2-A9 A5-A10 A6-B11 A7-B1 A8-A3 A11-B12 A12-B5 B3-A4 B6-B2 B7-A1 B9-B4 B10-B8",  # G38
]


class ErroreCalendario(ValueError):
    pass


def posti(conf: str) -> list[str]:
    return [f"{conf}{i}" for i in range(1, 13)]


def schema() -> list[list[tuple[str, str]]]:
    return [[tuple(p.split("-")) for p in g.split()] for g in SCHEMA]


# ── i controlli di Henry, copiati dal suo Calendario.py (34 giornate) e Calendario_ultime4.py (le ultime 4) ──────

def check_teams(conf_a, conf_b):
    if len(conf_a) != 12 or len(conf_b) != 12:
        raise ValueError("Devono esserci esattamente 12 squadre in Conference A e 12 in Conference B.")
    teams = list(conf_a) + list(conf_b)
    duplicates = [team for team, count in Counter(teams).items() if count > 1]
    if duplicates:
        raise ValueError(f"Le squadre devono avere nomi unici. Duplicati: {duplicates}")


def count_home_away(all_rounds):
    stats = defaultdict(lambda: {"home": 0, "away": 0})
    for giornata in all_rounds:
        for home, away in giornata:
            stats[home]["home"] += 1
            stats[away]["away"] += 1
    return stats


def phase_for_day(day_number):
    if 1 <= day_number <= 11:
        return "intraconference_andata"
    if 12 <= day_number <= 23:
        return "interconference"
    if 24 <= day_number <= 34:
        return "intraconference_ritorno"
    raise ValueError(f"Giornata non valida: {day_number}")


def validate_schedule(all_rounds, conf_a, conf_b):
    """
    Controlli:
    1) 34 giornate totali.
    2) Ogni giornata ha 12 partite e ogni squadra gioca una sola volta.
    3) Giornate 1-11 e 24-34 solo intraconference.
    4) Giornate 12-23 solo interconference.
    5) Ogni coppia intra-conference compare due volte, una casa e una fuori.
    6) Ogni coppia interconference compare una volta.
    7) Ogni squadra ha 17 casa e 17 trasferta.
    8) Nell'interconference ogni squadra ha 6 casa e 6 trasferta.
    """
    check_teams(conf_a, conf_b)

    teams = set(conf_a) | set(conf_b)
    set_a = set(conf_a)
    set_b = set(conf_b)

    if len(all_rounds) != 34:
        raise ValueError(f"Numero giornate errato: {len(all_rounds)}. Atteso: 34.")

    if sum(len(g) for g in all_rounds) != 34 * 12:
        raise ValueError("Numero partite totale errato. Attese 408 partite.")

    def same_conference(x, y):
        return (x in set_a and y in set_a) or (x in set_b and y in set_b)

    # 1) validazione giornate + struttura blocchi
    for idx, giornata in enumerate(all_rounds, start=1):
        if len(giornata) != 12:
            raise ValueError(f"Giornata {idx}: numero partite diverso da 12.")

        seen = []
        for home, away in giornata:
            if home == away:
                raise ValueError(f"Giornata {idx}: {home} gioca contro se stessa.")
            if home not in teams or away not in teams:
                raise ValueError(f"Giornata {idx}: squadra non riconosciuta in {home}-{away}.")
            seen.extend([home, away])

        if len(set(seen)) != 24:
            raise ValueError(f"Giornata {idx}: una squadra gioca piu' di una volta.")
        if set(seen) != teams:
            raise ValueError(f"Giornata {idx}: non tutte le squadre sono presenti.")

        if 1 <= idx <= 11 or 24 <= idx <= 34:
            if not all(same_conference(home, away) for home, away in giornata):
                raise ValueError(f"Giornata {idx}: deve contenere solo partite intraconference.")
        elif 12 <= idx <= 23:
            if any(same_conference(home, away) for home, away in giornata):
                raise ValueError(f"Giornata {idx}: deve contenere solo partite interconference.")

    # 2) conteggio accoppiamenti
    intra_counts = defaultdict(list)
    inter_counts = defaultdict(int)
    inter_rounds = all_rounds[11:23]

    for giornata in all_rounds:
        for home, away in giornata:
            if same_conference(home, away):
                intra_counts[frozenset((home, away))].append((home, away))
            else:
                a = home if home in set_a else away
                b = away if away in set_b else home
                inter_counts[(a, b)] += 1

    for conf in (conf_a, conf_b):
        for x, y in combinations(conf, 2):
            matches = intra_counts[frozenset((x, y))]
            if len(matches) != 2:
                raise ValueError(f"Coppia intra {x}-{y}: attese 2 partite, trovate {len(matches)}.")
            homes = {m[0] for m in matches}
            if homes != {x, y}:
                raise ValueError(f"Coppia intra {x}-{y}: casa/trasferta non invertita correttamente.")

    for a in conf_a:
        for b in conf_b:
            if inter_counts[(a, b)] != 1:
                raise ValueError(f"Coppia inter {a}-{b}: attesa 1 partita, trovate {inter_counts[(a, b)]}.")

    # 3) bilancio totale casa/trasferta
    stats = count_home_away(all_rounds)
    for team in teams:
        h = stats[team]["home"]
        a = stats[team]["away"]
        if h != 17 or a != 17:
            raise ValueError(f"{team}: casa={h}, trasferta={a}, atteso 17/17.")

    # 4) bilancio casa/trasferta solo interconference
    inter_stats = count_home_away(inter_rounds)
    for team in teams:
        h = inter_stats[team]["home"]
        a = inter_stats[team]["away"]
        if h != 6 or a != 6:
            raise ValueError(f"{team}: interconference casa={h}, trasferta={a}, atteso 6/6.")

    return True



def verifica_giornate(
    giornate, squadre):
    conteggi = defaultdict(lambda: {"casa": 0, "trasferta": 0, "partite": 0})
    accoppiamenti: set[tuple[str, str]] = set()

    if len(giornate) != 4:
        raise ValueError("Il calendario deve contenere quattro giornate.")

    for numero, giornata in enumerate(giornate, start=1):
        if len(giornata) != 12:
            raise ValueError(f"Giornata {numero}: devono esserci 12 partite.")

        presenti: set[str] = set()
        for casa, trasferta in giornata:
            if casa in presenti or trasferta in presenti:
                raise ValueError(f"Giornata {numero}: una squadra compare più volte.")
            presenti.update((casa, trasferta))

            conteggi[casa]["casa"] += 1
            conteggi[casa]["partite"] += 1
            conteggi[trasferta]["trasferta"] += 1
            conteggi[trasferta]["partite"] += 1

            coppia = tuple(sorted((casa, trasferta)))
            if coppia in accoppiamenti:
                raise ValueError(f"Accoppiamento ripetuto: {coppia[0]} - {coppia[1]}")
            accoppiamenti.add(coppia)

        if presenti != set(squadre):
            raise ValueError(f"Giornata {numero}: l'elenco delle squadre non è completo.")

    for squadra in squadre:
        risultato = conteggi[squadra]
        if risultato != {"casa": 2, "trasferta": 2, "partite": 4}:
            raise ValueError(f"Vincolo non rispettato per {squadra}: {risultato}")


# ── i controlli in più ────────────────────────────────────────────────────────────────────────────────────────────

def campi(giornate, squadra: str) -> str:
    """C in casa, f fuori, una lettera per giornata."""
    return "".join("C" if any(c == squadra for c, _ in g) else "f" for g in giornate)


def di_fila(sequenza: str) -> int:
    lunga = cur = 0
    for i, x in enumerate(sequenza):
        cur = cur + 1 if i and x == sequenza[i - 1] else 1
        lunga = max(lunga, cur)
    return lunga


def valida(giornate, conf_a, conf_b) -> None:
    """Tutti i controlli: quelli di Henry sulle 34 e sulle ultime 4, poi le serie e i totali."""
    if len(giornate) != GIORNATE:
        raise ErroreCalendario(f"giornate: {len(giornate)}, attese {GIORNATE}")
    try:
        validate_schedule(giornate[:34], conf_a, conf_b)
        verifica_giornate(giornate[34:], list(conf_a) + list(conf_b))
    except ValueError as er:
        raise ErroreCalendario(str(er))
    for t in list(conf_a) + list(conf_b):
        s = campi(giornate, t)
        if s.count("C") != 19:
            raise ErroreCalendario(f"{t}: {s.count('C')} in casa su 38, attese 19")
        if di_fila(s) > MASSIMO_DI_FILA:
            raise ErroreCalendario(f"{t}: {di_fila(s)} di fila nello stesso campo ({s}), al massimo {MASSIMO_DI_FILA}")


# ── il sorteggio ──────────────────────────────────────────────────────────────────────────────────────────────────

def uniforme(randomness_hex: str, etichetta: str) -> float:
    """Il numero in [0, 1): primi 8 byte di SHA-256(randomness ‖ etichetta), diviso 2^64."""
    h = hashlib.sha256(bytes.fromhex(randomness_hex) + etichetta.encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def mescola(squadre: list[str], randomness_hex: str, conf: str) -> list[str]:
    """Fisher-Yates: dall'ultimo posto al secondo, scambio con un posto a caso tra i precedenti (compreso)."""
    out = list(squadre)
    for i in range(len(out) - 1, 0, -1):
        j = int(uniforme(randomness_hex, f"calendario {conf} {i}") * (i + 1))
        out[i], out[j] = out[j], out[i]
    return out


def assegna(conf_a: list[str], conf_b: list[str], randomness_hex: str) -> dict[str, str]:
    """{posto: squadra}: A1 = la prima squadra A dopo il mescolamento, e così via."""
    if len(conf_a) != 12 or len(conf_b) != 12 or len(set(conf_a) | set(conf_b)) != 24:
        raise ErroreCalendario("servono 12 squadre per conference, tutte diverse")
    a, b = mescola(conf_a, randomness_hex, "A"), mescola(conf_b, randomness_hex, "B")
    return dict(zip(posti("A") + posti("B"), a + b))


def genera(conf_a: list[str], conf_b: list[str], randomness_hex: str) -> list[list[tuple[str, str]]]:
    """Il calendario: per giornata le partite (casa, trasferta), controllato."""
    chi = assegna(conf_a, conf_b, randomness_hex)
    giornate = [[(chi[c], chi[t]) for c, t in g] for g in schema()]
    valida(giornate, conf_a, conf_b)
    return giornate


def impronta() -> str:
    """SHA-256 di questo file: si pubblica prima del sorteggio, così si sa che il codice non cambia."""
    return hashlib.sha256(open(__file__, "rb").read()).hexdigest()


# ── da terminale ──────────────────────────────────────────────────────────────────────────────────────────────────

def _drand(rnd: int) -> str:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import lottery as LT
    except ImportError:
        from shared import lottery as LT
    return LT.randomness(rnd)


def _stampa(giornate, conf_a, conf_b) -> None:
    for n, g in enumerate(giornate, 1):
        print(f"\n=== Giornata {n} - {phase_for_day(n) if n <= 34 else 'ultime_4'} ===")
        for c, t in g:
            print(f"{c} - {t}")
    print("\nCasa (C) e fuori (f), giornata per giornata:")
    for t in list(conf_a) + list(conf_b):
        s = campi(giornate, t)
        print(f"{s}  {t} (casa {s.count('C')}, al massimo {di_fila(s)} di fila)")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Sorteggio del calendario: rifarlo e controllarlo.")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("genera")
    seme = g.add_mutually_exclusive_group(required=True)
    seme.add_argument("--round", type=int, help="il round drand annunciato (scaricato dai relay)")
    seme.add_argument("--randomness", help="la randomness del round, se già nota (esadecimale)")
    g.add_argument("--a", required=True, help="le 12 squadre della prima conference, separate da virgole")
    g.add_argument("--b", required=True, help="le 12 squadre della seconda conference")
    g.add_argument("--csv", help="scrive anche un CSV giornata,casa,trasferta")
    sub.add_parser("schema")
    x = p.parse_args(argv)
    print(f"Impronta di questo file (SHA-256): {impronta()}")
    if x.cmd == "schema":
        conf_a, conf_b = posti("A"), posti("B")
        giornate = schema()
        valida(giornate, conf_a, conf_b)
        _stampa(giornate, conf_a, conf_b)
        doppie = sum(sum(1 for i in range(1, GIORNATE) if s[i] == s[i - 1]) for s in (campi(giornate, t) for t in conf_a + conf_b))
        print(f"\nSchema valido: tutti i controlli superati; {doppie} doppie in tutto, mai più di {MASSIMO_DI_FILA} di fila.")
        return
    conf_a = [s.strip() for s in x.a.split(",") if s.strip()]
    conf_b = [s.strip() for s in x.b.split(",") if s.strip()]
    rnd = x.randomness or _drand(x.round)
    print(f"Round {x.round or '—'} · randomness {rnd}")
    giornate = genera(conf_a, conf_b, rnd)
    _stampa(giornate, conf_a, conf_b)
    if x.csv:
        with open(x.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["giornata", "casa", "trasferta"])
            for n, gg in enumerate(giornate, 1):
                for c, t in gg:
                    w.writerow([n, c, t])
        print(f"\nCSV: {x.csv}")
    print("\nCalendario valido: tutti i controlli superati.")


if __name__ == "__main__":
    main()

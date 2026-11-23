#!/usr/bin/env python3
"""
Verifica della lottery del draft (v7.27.1, Luca 23/11: «uno script lottery standalone che dimostri la bontà del
sorteggio»). Usa lo stesso codice del bot (shared/lottery.py: matrice e algoritmo di Henry, seme da drand), solo la
libreria standard di Python: si scarica il repo e si lancia, niente bot e niente database.

    python3 strumenti/lottery_verifica.py simula [N]          # N estrazioni (default 200000): frequenze contro la matrice
    python3 strumenti/lottery_verifica.py matrice             # la matrice, i controlli e la scomposizione
    python3 strumenti/lottery_verifica.py estrai --round R --squadre "A,B,…,L"
                                                              # rifà un'estrazione vera dal round drand dichiarato
    python3 strumenti/lottery_verifica.py estrai --randomness HEX --squadre "A,…"   # senza rete, col valore del round

Le squadre vanno in ordine di seed: la prima è l'ultima in classifica. L'impronta stampata è lo SHA-256 di
shared/lottery.py: deve essere quella pubblicata sul canale prima dell'estrazione.
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from shared import lottery as LT          # noqa: E402


def matrice() -> None:
    LT.validate_odds_matrix(LT.ODDS)
    print("Matrice delle odds (righe: seed 1 = l'ultima; colonne: pick 1..12), in %:")
    print("seed " + " ".join(f"{p:>6}" for p in range(1, 13)))
    for i, r in enumerate(LT.ODDS, 1):
        print(f"{i:>4} " + " ".join(f"{100 * x:6.2f}" for x in r))
    dec = LT.decomposizione()
    print(f"\nOK: righe e colonne sommano a 1. Scomposizione di Birkhoff: {len(dec)} permutazioni, pesi in totale "
          f"{sum(w for w, _ in dec):.12f}.")
    ric = [[0.0] * 12 for _ in range(12)]
    for w, perm in dec:
        for s, p in enumerate(perm):
            ric[s][p] += w
    err = max(abs(ric[s][p] - LT.ODDS[s][p]) for s in range(12) for p in range(12))
    print(f"Ricomponendo le permutazioni si ritrova la matrice: scarto massimo {err:.2e}.")
    print(f"Impronta di shared/lottery.py: {LT.impronta()}")


def simula(n: int) -> None:
    conta = [[0] * 12 for _ in range(12)]
    for k in range(n):
        seme = hashlib.sha256(f"simulazione-{k}".encode()).hexdigest()
        perm = LT.scegli(LT.uniforme(seme))
        for s, p in enumerate(perm):
            conta[s][p] += 1
    print(f"{n} estrazioni simulate (semi = SHA-256 di «simulazione-k»). Per ogni seed: frequenza osservata della pick "
          "(in %) e, sotto, la matrice.")
    print("seed " + " ".join(f"{p:>6}" for p in range(1, 13)))
    peggio, chi2, gradi = 0.0, 0.0, 0
    for s in range(12):
        print(f"{s + 1:>4} " + " ".join(f"{100 * c / n:6.2f}" for c in conta[s]))
        print("     " + " ".join(f"{100 * x:6.2f}" for x in LT.ODDS[s]))
        for p in range(12):
            atteso = LT.ODDS[s][p] * n
            if atteso > 0:
                chi2 += (conta[s][p] - atteso) ** 2 / atteso
                gradi += 1
            elif conta[s][p]:
                print(f"  !! seed {s + 1} alla pick {p + 1}: impossibile ma uscito {conta[s][p]} volte")
            peggio = max(peggio, abs(conta[s][p] / n - LT.ODDS[s][p]))
    print(f"\nScarto massimo tra frequenza e matrice: {100 * peggio:.3f} punti percentuali "
          f"(per {n} estrazioni ci si aspetta al massimo qualche decimo).")
    print(f"Chi quadro (indicativo, celle non nulle): {chi2:.1f} su circa {gradi} celle.")
    print("Ogni estrazione è un ordine valido: ogni pick a una sola squadra, per costruzione (permutazioni).")


def estrai(args) -> None:
    squadre = [x.strip() for x in args.squadre.split(",") if x.strip()]
    if args.randomness:
        val = args.randomness
    else:
        if not args.round:
            sys.exit("Serve --round (il round drand dichiarato) o --randomness.")
        val = LT.randomness(args.round)
    u = LT.uniforme(val)
    ordine = LT.estrai(squadre, val)
    print(f"Round {args.round or '—'} · randomness {val}\nu = {u:.12f}\nImpronta del codice: {LT.impronta()}\n")
    print("Ordine estratto (prima delle discese per le penalità):")
    for i, t in enumerate(ordine, 1):
        print(f"{i:>3}. {t} (seed {squadre.index(t) + 1})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cosa", required=True)
    s = sub.add_parser("simula")
    s.add_argument("n", nargs="?", type=int, default=200000)
    sub.add_parser("matrice")
    e = sub.add_parser("estrai")
    e.add_argument("--round", type=int)
    e.add_argument("--randomness")
    e.add_argument("--squadre", required=True, help="12 squadre in ordine di seed, separate da virgole")
    a = ap.parse_args()
    if a.cosa == "simula":
        simula(a.n)
    elif a.cosa == "matrice":
        matrice()
    else:
        estrai(a)


if __name__ == "__main__":
    main()

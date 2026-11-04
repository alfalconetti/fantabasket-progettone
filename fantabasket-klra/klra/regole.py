"""
I parametri di un sistema di punteggio: cosa si può cambiare, i valori dell'Ufficiale, la descrizione
di cosa cambia rispetto all'Ufficiale.

Un sistema è un dict con cinque sezioni (tutte le voci hanno un default = le regole della lega):
- pesi:     peso di ogni statistica nei fantapunti di una partita (i 12 dell'Ufficiale più falli e minuti);
- giocatore: bonus e malus di una partita del giocatore (0 = spento) e il tetto ai fantapunti di una partita;
- squadra:  bonus e malus della squadra nella giornata;
- partita:  bonus casa, scarto, supplementari, FADD, chi non gioca, panchina;
- classifica: a vittorie (come l'Ufficiale) o a punti.

L'Ufficiale non è congelato: i suoi valori si leggono ogni volta da config/settings.json (shared/regole),
come fa loucabot. Gli altri li cambia solo chi li ha creati (Luca, 04/11); la cache dei risultati è per firma.
"""
import copy
import hashlib
import json

from shared import regole as R

STATISTICHE = ["pts", "ast", "oreb", "dreb", "tpm", "fga", "fgm", "fta", "ftm", "stl", "blk", "tov", "pf", "minuti"]
NOMI_STAT = {"pts": "Punto", "ast": "Assist", "oreb": "Rimbalzo offensivo", "dreb": "Rimbalzo difensivo",
             "tpm": "Tripla segnata", "fga": "Tiro dal campo tentato", "fgm": "Tiro dal campo segnato",
             "fta": "Libero tentato", "ftm": "Libero segnato", "stl": "Recupero", "blk": "Stoppata",
             "tov": "Palla persa", "pf": "Fallo", "minuti": "Minuto giocato"}

# bonus del giocatore in una partita: (nome, condizione detta a parole)
BONUS_GIOCATORE = {
    "doppia_doppia":    ("Doppia doppia", "10 o più in due tra punti, rimbalzi, assist, recuperi e stoppate"),
    "tripla_doppia":    ("Tripla doppia", "10 o più in tre, al posto della doppia doppia"),
    "quadrupla_doppia": ("Quadrupla doppia", "10 o più in quattro, al posto della tripla"),
    "cinque_x_cinque":  ("5x5", "almeno 5 in punti, rimbalzi, assist, recuperi e stoppate"),
    "punti_40":         ("Serata da 40", "40 punti o più"),
    "rimbalzi_20":      ("20 rimbalzi", "20 rimbalzi o più"),
    "assist_15":        ("15 assist", "15 assist o più"),
    "stoppate_5":       ("5 stoppate", "5 stoppate o più"),
    "mano_calda":       ("Mano calda", "almeno 8 tiri dal campo col 70% o più"),
    "mattone":          ("Mattone", "almeno 10 tiri dal campo sotto il 30%"),
    "custode":          ("Custode del pallone", "30 minuti o più senza palle perse"),
    "sei_falli":        ("Fuori per falli", "6 falli"),
    "vittoria_nba":     ("Vittoria NBA", "la sua squadra NBA vince la partita"),
}
BONUS_SQUADRA = {
    "quintetto_bonus":  ("Quintetto completo", "tutti e 5 i titolari almeno alla soglia"),
    "mvp_bonus":        ("MVP di giornata", "il titolare coi fantapunti più alti della giornata, alla sua squadra"),
    "negativo_malus":   ("Titolare sotto zero", "per ogni titolare con fantapunti negativi"),
}
SUPPLEMENTARI = {"panchina": "supplementari coi panchinari (Ufficiale)",
                 "pareggio": "pareggio, niente supplementari",
                 "nessuno": "vince chi fa di più, niente scarto né supplementari"}
PARI_FINALE = {"trasferta": "vince la squadra in trasferta (Ufficiale)", "pareggio": "pareggio"}
ASSENTI = {"media": "la sua media della stagione (Ufficiale)", "percentuale": "una percentuale della media", "zero": "0"}
CLASSIFICA = {"vittorie": "vittorie e sconfitte (Ufficiale)", "punti": "a punti"}
# fantamedie (Luca, 04/11): chi ha giocato nella giornata prende la sua media della stagione fino al giorno prima
FANTAPUNTI = {"partite": "i fantapunti delle sue partite (Ufficiale)",
              "media": "la sua media della stagione prima della giornata, se non ha ancora giocato quella dell'anno prima (fantamedie)"}


def ufficiale() -> dict:
    """Le regole della lega adesso (config/settings.json)."""
    pesi = {k: 0 for k in STATISTICHE}
    pesi.update({k: v for k, v in R.pesi_fantapunti().items()})
    return {
        "pesi": pesi,
        "giocatore": {**{k: 0 for k in BONUS_GIOCATORE}, "tetto": None},
        "squadra": {"quintetto_bonus": 0, "quintetto_soglia": 20, "mvp_bonus": 0, "negativo_malus": 0},
        "partita": {"bonus_casa": R.bonus_casa(), "bonus_casa_playoff": R.bonus_casa(playoff=True),
                    "scarto": R.scarto_minimo(), "supplementari": "panchina", "pari_finale": "trasferta",
                    "panchina": R.giocatori_panchina(), "fadd": True, "assenti": "media", "assenti_pct": 100,
                    "fantapunti": "partite"},
        "classifica": {"modo": "vittorie", "vittoria": 3, "vittoria_supp": 2, "sconfitta_supp": 1, "pareggio": 1,
                       "sconfitta": 0},
    }


def completa(p: dict | None) -> dict:
    """Le voci mancanti (sistemi creati prima che esistessero) prendono il valore dell'Ufficiale di adesso;
    le voci sconosciute si tolgono."""
    base = ufficiale()
    p = p or {}
    out = copy.deepcopy(base)
    for sez, voci in base.items():
        for k in voci:
            if isinstance(p.get(sez), dict) and k in p[sez]:
                out[sez][k] = p[sez][k]
    return out


def firma(p: dict) -> str:
    """Impronta dei parametri: la cache dei risultati è per firma (l'Ufficiale cambia se cambia settings.json)."""
    return hashlib.sha256(json.dumps(completa(p), sort_keys=True).encode()).hexdigest()[:16]


def _n(x) -> str:
    if x is None:
        return "nessuno"
    if isinstance(x, bool):
        return "sì" if x else "no"
    if isinstance(x, (int, float)):
        return f"{x:g}".replace(".", ",").replace("-", "−")
    return str(x)


def differenze(p: dict, rispetto: dict | None = None, breve: bool = False) -> list[str]:
    """Cosa cambia rispetto all'Ufficiale (o a un altro sistema), a parole, una riga per voce (breve: senza le
    condizioni dei bonus, per bande e liste)."""
    def bonus(nome, cond, v, extra=""):
        if not v:
            return f"{nome}: tolto"
        return f"{nome} {'+' if v > 0 else ''}{_n(v)}" + ("" if breve else f" ({cond}{extra})")
    a, b = completa(rispetto) if rispetto else ufficiale(), completa(p)
    out = []
    for k in STATISTICHE:
        if a["pesi"][k] != b["pesi"][k]:
            out.append(f"{NOMI_STAT[k]}: {_n(a['pesi'][k])} → {_n(b['pesi'][k])}")
    for k, (nome, cond) in BONUS_GIOCATORE.items():
        if a["giocatore"][k] != b["giocatore"][k]:
            out.append(bonus(nome, cond, b["giocatore"][k]))
    if a["giocatore"]["tetto"] != b["giocatore"]["tetto"]:
        out.append(f"Tetto ai fantapunti di una partita: {_n(b['giocatore']['tetto'])}")
    for k, (nome, cond) in BONUS_SQUADRA.items():
        if a["squadra"][k] != b["squadra"][k] or (k == "quintetto_bonus" and b["squadra"][k]
                                                    and a["squadra"]["quintetto_soglia"] != b["squadra"]["quintetto_soglia"]):
            extra = f", soglia {_n(b['squadra']['quintetto_soglia'])}" if k == "quintetto_bonus" else ""
            out.append(bonus(nome, cond, b["squadra"][k], extra))
    pa, pb = a["partita"], b["partita"]
    for k, nome in (("bonus_casa", "Bonus casa"), ("bonus_casa_playoff", "Bonus casa nei playoff"), ("scarto", "Scarto per vincere"),
                    ("panchina", "Panchinari che entrano")):
        if pa[k] != pb[k]:
            out.append(f"{nome}: {_n(pa[k])} → {_n(pb[k])}")
    if pa["supplementari"] != pb["supplementari"]:
        out.append(f"Sotto lo scarto: {SUPPLEMENTARI[pb['supplementari']]}")
    if pa["pari_finale"] != pb["pari_finale"] and pb["supplementari"] == "panchina":
        out.append(f"Pari anche dopo i supplementari: {PARI_FINALE[pb['pari_finale']]}")
    if pa["fantapunti"] != pb["fantapunti"]:
        out.append("Chi gioca prende " + FANTAPUNTI[pb["fantapunti"]])
    if pa["fadd"] != pb["fadd"]:
        out.append("FADD: " + ("sì" if pb["fadd"] else "no"))
    if (pa["assenti"], pa["assenti_pct"]) != (pb["assenti"], pb["assenti_pct"]):
        out.append("Chi non gioca e la sua squadra non ha partite: "
                   + (f"il {_n(pb['assenti_pct'])}% della media" if pb["assenti"] == "percentuale" else ASSENTI[pb["assenti"]]))
    ca, cb = a["classifica"], b["classifica"]
    if cb["modo"] == "punti" and (ca["modo"] != "punti" or ca != cb):
        out.append(f"Classifica a punti: vittoria {_n(cb['vittoria'])}, ai supplementari {_n(cb['vittoria_supp'])}-"
                   f"{_n(cb['sconfitta_supp'])}, pareggio {_n(cb['pareggio'])}, sconfitta {_n(cb['sconfitta'])}")
    elif cb["modo"] != ca["modo"]:
        out.append("Classifica: vittorie e sconfitte")
    return out

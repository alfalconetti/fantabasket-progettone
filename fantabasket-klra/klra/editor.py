"""
L'editor dei sistemi (mockup approvato da Luca il 04/11): si parte da una copia di un sistema qualsiasi
(o dalla modifica del proprio), cinque sezioni di bottoni, un bottone per voce col valore attuale.
- voci numeriche: si tocca e si scrive il nuovo valore (virgola o punto, anche negativo);
- voci a scelta (supplementari, pari finale, chi non gioca, classifica) e FADD: cambiano a ogni tocco;
- 💾 Salva: per una copia chiede il nome, per la modifica del proprio sistema salva e basta.
La bozza resta nel database klra se si chiude a metà (/sistemi → ✏️ Riprendi la bozza).
"""
from klra import regole as KR

SEZIONI = {
    "pesi": "🎯 Fantapunti",
    "giocatore": "🌟 Bonus giocatore",
    "squadra": "👥 Bonus squadra",
    "partita": "⚔️ Partita",
    "classifica": "🏆 Classifica",
}

# voce → (etichetta breve, tipo, limiti); tipo: num (float), int, scelta (dizionario delle scelte), bool, num_o_niente
VOCI = {
    "pesi": {k: (v, "num", (-50, 50)) for k, v in KR.NOMI_STAT.items()},
    "giocatore": {**{k: (v[0], "num", (-50, 50)) for k, v in KR.BONUS_GIOCATORE.items()},
                  "tetto": ("Tetto a partita", "num_o_niente", (0, 500))},
    "squadra": {"quintetto_bonus": ("Quintetto completo", "num", (-100, 100)),
                "quintetto_soglia": ("Soglia del quintetto", "num", (-100, 200)),
                "mvp_bonus": ("MVP di giornata", "num", (-100, 100)),
                "negativo_malus": ("Titolare sotto zero", "num", (-100, 100))},
    "partita": {"bonus_casa": ("Bonus casa", "num", (-50, 50)),
                "bonus_casa_playoff": ("Bonus casa playoff", "num", (-50, 50)),
                "scarto": ("Scarto per vincere", "num", (0, 200)),
                "supplementari": ("Sotto lo scarto", "scelta", KR.SUPPLEMENTARI),
                "pari_finale": ("Pari dopo i supp.", "scelta", KR.PARI_FINALE),
                "panchina": ("Panchinari che entrano", "int", (0, 5)),
                "fadd": ("FADD", "bool", None),
                "fantapunti": ("Chi gioca prende", "scelta", KR.FANTAPUNTI),
                "assenti": ("Chi non gioca", "scelta", KR.ASSENTI),
                "assenti_pct": ("% della media", "num", (0, 100))},
    "classifica": {"modo": ("Classifica", "scelta", KR.CLASSIFICA),
                   "vittoria": ("Vittoria", "num", (-10, 10)),
                   "vittoria_supp": ("Vittoria ai supp.", "num", (-10, 10)),
                   "sconfitta_supp": ("Sconfitta ai supp.", "num", (-10, 10)),
                   "pareggio": ("Pareggio", "num", (-10, 10)),
                   "sconfitta": ("Sconfitta", "num", (-10, 10))},
}
BREVI = {"panchina": "panchina", "pareggio": "pareggio", "nessuno": "chi fa di più", "trasferta": "trasferta",
         "media": "media", "percentuale": "% media", "partite": "le partite", "zero": "0", "vittorie": "V-S", "punti": "a punti"}


def mostra(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "sì" if v else "no"
    if isinstance(v, (int, float)):
        return f"{v:g}".replace(".", ",").replace("-", "−")
    return BREVI.get(v, str(v))


def visibile(P: dict, sez: str, voce: str) -> bool:
    """Le voci che contano con le altre scelte (es. «% della media» solo se chi non gioca prende una percentuale)."""
    if sez == "partita" and voce == "assenti_pct":
        return P["partita"]["assenti"] == "percentuale"
    if sez == "partita" and voce == "pari_finale":
        return P["partita"]["supplementari"] != "pareggio"
    if sez == "classifica" and voce != "modo":
        return P["classifica"]["modo"] == "punti"
    if sez == "squadra" and voce == "quintetto_soglia":
        return bool(P["squadra"]["quintetto_bonus"])
    return True


def tocca(P: dict, sez: str, voce: str) -> bool:
    """Per scelte e sì/no: passa al valore dopo. True se fatto (False: è una voce da scrivere)."""
    _, tipo, lim = VOCI[sez][voce]
    if tipo == "bool":
        P[sez][voce] = not P[sez][voce]
        return True
    if tipo == "scelta":
        chiavi = list(lim)
        i = chiavi.index(P[sez][voce]) if P[sez][voce] in chiavi else -1
        P[sez][voce] = chiavi[(i + 1) % len(chiavi)]
        return True
    return False


def leggi_valore(sez: str, voce: str, testo: str):
    """(valore, errore) dal testo scritto."""
    _, tipo, (lo, hi) = VOCI[sez][voce]
    t = (testo or "").strip().lower().replace(",", ".").replace("−", "-").replace(" ", "")
    if tipo == "num_o_niente" and t in ("-", "—", "no", "nessuno", "niente", "0"):
        return None, None
    try:
        x = float(t)
    except ValueError:
        return None, "Scrivi un numero (es. 3, −1,5" + (", oppure «nessuno»" if tipo == "num_o_niente" else "") + ")."
    if not lo <= x <= hi:
        return None, f"Il valore va da {mostra(lo)} a {mostra(hi)}."
    if tipo == "int":
        if x != int(x):
            return None, "Serve un numero intero."
        return int(x), None
    if round(x * 4) != x * 4:
        return None, "Usa multipli di 0,25 (i fantapunti si contano così)."
    return (int(x) if x == int(x) else x), None

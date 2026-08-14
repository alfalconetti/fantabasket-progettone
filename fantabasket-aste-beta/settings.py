"""
Lettura centralizzata di settings.json — bot aste beta.
File condiviso con bot main. Tutte le costanti di business vengono lette da qui.
Il file viene riletto a ogni chiamata — modificabile live senza restart.
"""
import json
import os

SETTINGS_PATH = os.environ.get("SETTINGS_PATH", "/config/settings.json")


def get() -> dict:
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── aste ───────────────────────────────────────────────────────────────────────

def durata_asta_ore() -> int:
    return get()["durata_asta_ore"]

def timeout_firma_fa_ore() -> int:
    return get()["timeout_firma_fa_ore"]

def timeout_firma_rfa_ore() -> int:
    return get()["timeout_firma_rfa_ore"]

def timeout_pareggio_ore() -> int:
    return get()["timeout_pareggio_ore"]

def rilancio_minimo() -> int:
    return get()["rilancio_minimo"]

def paginazione_aste() -> int:
    return get()["paginazione_aste"]

def paginazione_fa() -> int:
    return get()["paginazione_fa"]

def notifica_minuti_scadenza() -> int:
    return get()["notifica_minuti_scadenza"]

# ── contratti ──────────────────────────────────────────────────────────────────

def fascia_bassa_max() -> int:
    return get()["fascia_bassa_max"]

def fascia_media_max() -> int:
    return get()["fascia_media_max"]

def soglia_anni_2() -> int:
    return get()["soglia_anni_2"]

def soglia_anni_3() -> int:
    return get()["soglia_anni_3"]

# ── cap e roster ───────────────────────────────────────────────────────────────

def cap_massimo() -> int:
    """Cap regular season (150M) — fisso, usato per calcoli interni."""
    return get()["cap_regular"]

def cap_limite() -> int:
    """Cap massimo consentito: 165M in offseason, 150M in regular season."""
    import utils as _utils
    fase = _utils.load_globals().get("fase", "")
    if fase.startswith("offseason"):
        return get()["cap_offseason"]
    return get()["cap_regular"]

def slot_massimo() -> int:
    return get()["roster_max"]

def numero_teams() -> int:
    return get()["numero_teams"]

def backup_intervallo_ore() -> int:
    return get().get("backup_intervallo_ore", 12)

def offerta_massima() -> int:
    """
    Massimo spendibile su un singolo giocatore durante le aste:
    cap_regular - (roster_max - 1) * 1M
    Garantisce che restino fondi per riempire gli altri slot al minimo.
    """
    s = get()
    return s["cap_regular"] - (s["roster_max"] - 1)

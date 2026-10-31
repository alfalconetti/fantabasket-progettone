"""
I numeri del regolamento, in un posto solo (v5.8.0): si leggono da config/settings.json, e una chiave
che manca vale il default qui sotto (i valori del regolamento 2026-27). Si cambiano lì, di solito
dopo la riunione di lega di giugno; il file si rilegge quando cambia, senza riavviare.

Usato da tutti i bot (shared/ è montato in ognuno; loucabot e IPanchinari leggono settings.json
dalla stessa cartella config). Gli altri numeri del bot principale (cap, roster, aste, rinnovi…)
restano in settings.py, come prima.

Attenzione ai pesi dei fantapunti: i fantapunti si calcolano quando si scarica un tabellino e si
salvano nel database. Dopo un cambio dei pesi: /dev_ricalcola_fp su loucabot (ricalcola dalle
statistiche già salvate, senza ESPN).
"""
import json
import logging
import math
import os

logger = logging.getLogger(__name__)

SETTINGS_PATH = os.environ.get("SETTINGS_PATH", "/config/settings.json")

PESI_FANTAPUNTI = {"pts": 0.5, "ast": 2, "oreb": 2, "dreb": 1.25, "tpm": 1.5, "fga": -0.5, "fgm": 1,
                   "fta": -0.75, "ftm": 1, "stl": 2, "blk": 2, "tov": -2}

DEFAULT = {
    # loucabot: calcolo della giornata
    "pesi_fantapunti": PESI_FANTAPUNTI,
    "bonus_casa": 3,
    "bonus_casa_playoff": 5,
    "scarto_minimo": 5,                 # sotto, si va ai supplementari
    # IPanchinari e calcolo: panchina e supplementari (un panchinaro a testa per volta)
    "giocatori_panchina": 5,
    # bot principale
    "roster_min_guardie": 4,
    "roster_min_ali": 4,
    "roster_min_centri": 2,
    "ore_comunicazione_ruolo": 48,      # per dichiarare il ruolo dopo una firma o una trade
    "giorni_riacquisto_ruolo": 60,      # ripreso entro tanti giorni: torna col vecchio ruolo
    "max_cambi_ruolo_ordinari": 2,
    "giorni_erminio": 14,
    "giorni_saedro": 10,
    "max_tagli_gratuiti": 3,
    "giorni_10day": 10,
    "riduzione_dpe_percento": 25,       # arrotondata per eccesso
}

_cache: dict = {"mtime": None, "dati": {}}
_avvisi: set = set()


def _avvisa(testo: str, *args) -> None:
    """Un avviso una volta sola per lo stesso problema (i pesi si leggono a ogni riga di tabellino)."""
    k = testo % args
    if k not in _avvisi:
        _avvisi.add(k)
        logger.warning(k)


def _settings() -> dict:
    try:
        m = os.path.getmtime(SETTINGS_PATH)
        if m != _cache["mtime"]:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                _cache["dati"], _cache["mtime"] = json.load(f), m
    except (OSError, ValueError) as err:
        # file illeggibile (o a metà di una scrittura): l'ultima lettura buona, se no i default
        _avvisa("settings.json illeggibile (%s): uso l'ultima lettura buona", err)
    return _cache["dati"] if isinstance(_cache["dati"], dict) else {}


def _numero(v, default):
    """Un numero valido (anche scritto come testo, "1,5" compreso), se no il default: un valore storto
    nel file non deve mai far cadere un bot."""
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return v if math.isfinite(v) else default
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(x):
        return default
    return int(x) if x == int(x) else x


def valore(chiave: str):
    v = _settings().get(chiave)
    d = DEFAULT[chiave]
    if v is None:
        return d
    if isinstance(d, dict):
        if not isinstance(v, dict):
            _avvisa("settings.json: %s non è un dizionario, uso i default", chiave)
            return dict(d)
        # solo le voci conosciute, ognuna un numero (le altre restano ai default)
        out = {}
        for k, dk in d.items():
            x = _numero(v.get(k), None)
            if x is None and k in v:
                _avvisa("settings.json: %s.%s = %r non è un numero, uso %r", chiave, k, v[k], dk)
            out[k] = dk if x is None else x
        return out
    n = _numero(v, None)
    if n is None:
        _avvisa("settings.json: %s = %r non è un numero, uso %r", chiave, v, d)
        return d
    return n


def pesi_fantapunti() -> dict:
    return valore("pesi_fantapunti")


# colonne di bref_stats (medie per partita di basketball-reference) per le statistiche dei pesi
COLONNE_BREF = {"pts": "pts", "ast": "ast", "oreb": "orb", "dreb": "drb", "tpm": "fg3m", "fga": "fga", "fgm": "fgm",
                "fta": "fta", "ftm": "ftm", "stl": "stl", "blk": "blk", "tov": "tov"}


def espressione_sql(colonne: dict | None = None, prefisso: str = "") -> str:
    """I fantapunti come espressione SQL coi pesi di adesso (numeri, mai testo: niente iniezioni)."""
    colonne = colonne or {k: k for k in PESI_FANTAPUNTI}
    # pesi come NUMERIC, non double: con le medie di bref a un decimale (12.3 × 1.25) il double
    # arrotonderebbe in modo diverso dalla vecchia colonna generata
    return " + ".join(f"{prefisso}{colonne[k]} * ({float(p)!r}::numeric)" for k, p in pesi_fantapunti().items() if k in colonne)


def allinea_bref(q) -> None:
    """bref_stats.fantamedia coi pesi di settings.json. Fino alla v5.7 era una colonna generata coi pesi
    scritti nello schema (bref_schema.sql): diventa una colonna normale riempita da un trigger, che si
    riscrive coi pesi di adesso (all'avvio del bot principale e con /dev_ricalcola_fp). Il trigger
    vale anche per bref_scraper.py, che scrive la tabella per conto suo."""
    col = q("""SELECT is_generated FROM information_schema.columns
               WHERE table_name = 'bref_stats' AND column_name = 'fantamedia'""", one=True)
    if not col:
        return
    expr = espressione_sql(COLONNE_BREF, "NEW.")
    # una sola istruzione, quindi una sola transazione: o tutto o niente (mai la colonna normale senza
    # il trigger, che lascerebbe vuota la fantamedia delle righe nuove)
    q(("ALTER TABLE bref_stats ALTER COLUMN fantamedia DROP EXPRESSION; " if col["is_generated"] == "ALWAYS" else "")
      + f"""CREATE OR REPLACE FUNCTION bref_fantamedia() RETURNS trigger AS $f$
          BEGIN NEW.fantamedia := ROUND(({expr})::numeric, 2); RETURN NEW; END $f$ LANGUAGE plpgsql;
          CREATE OR REPLACE TRIGGER bref_fantamedia BEFORE INSERT OR UPDATE ON bref_stats
          FOR EACH ROW EXECUTE FUNCTION bref_fantamedia()""")


def bonus_casa(playoff: bool = False) -> float:
    return valore("bonus_casa_playoff" if playoff else "bonus_casa")


def scarto_minimo() -> float:
    return valore("scarto_minimo")


def giocatori_panchina() -> int:
    return int(valore("giocatori_panchina"))


def minimi_ruolo() -> dict:
    return {"G": int(valore("roster_min_guardie")), "F": int(valore("roster_min_ali")), "C": int(valore("roster_min_centri"))}


def ore_dichiarazione_ruolo() -> int:
    return int(valore("ore_comunicazione_ruolo"))


def giorni_riacquisto_ruolo() -> int:
    return int(valore("giorni_riacquisto_ruolo"))


def max_cambi_ordinari() -> int:
    return int(valore("max_cambi_ruolo_ordinari"))


def giorni_erminio() -> int:
    return int(valore("giorni_erminio"))


def giorni_saedro() -> int:
    return int(valore("giorni_saedro"))


def max_tagli_gratuiti() -> int:
    return int(valore("max_tagli_gratuiti"))


def giorni_10day() -> int:
    return int(valore("giorni_10day"))


def riduzione_dpe() -> float:
    return float(valore("riduzione_dpe_percento")) / 100


# ── orari dei job (Luca, 23/10) ───────────────────────────────────────────────
# In settings.json: "orari": {"bref": "12:00", ...} (ora di Roma, "HH:MM"); una chiave che manca o
# scritta male vale il default. Gli orari dei job giornalieri si leggono all'avvio: dopo un cambio
# serve un riavvio del bot, non un rilascio. Quelli letti al momento (fine del blocco delle panchine,
# promemoria di IPanchinari, fine del live) valgono subito.
ORARI = {
    # bot principale
    "bref": "12:00",                    # basketball-reference aggiorna in tarda mattinata (prima le 10)
    "scadenza_diritti": "09:00",
    "promemoria_deadline_ruoli": "10:00",
    "report_ruoli": "17:00",
    "report_nascite": "09:30",          # il lunedì
    "report_spalmature": "09:45",       # il 1° del mese
    "report_posizioni": "09:15",        # posizioni eleggibili mancanti, al gruppo admin se cambiano (il lunedì comunque)
    "coerenza": "01:00",
    "backup_settimanale": "00:30",      # il sabato
    # loucabot
    "calcolo": "07:45",                 # calcolo definitivo, il mattino dopo l'ultima notte
    "fine_live_notte": "08:00",         # ultimo aggiornamento del live della notte
    "sync_nba": "08:30",                # partite, tabellini, infortunati
    "top_notte": "09:00",               # top 20 della notte nel gruppo della lega (Luca, 30/10)
    "controllo_tanking": "11:00",       # il mattino dopo la prima notte della giornata, solo al gruppo admin (Luca, 25/10)
    "tanking_injury": "21:00",          # per il tanking conta l'injury report fino alle 21 del primo giorno (tradizione, Luca 31/10)
    "controllo_tabellini": "10:00",     # non più usato dalla v60 (era il controllo delle 10)
    "primo_controllo": "11:05",         # primo controllo dell'ultima notte, anche a giornata convalidata (Luca, 30/10)
    "controllo_notte": "20:00",         # controllo finale della notte prima, poi congelata (come Yahoo; Luca, 30/10)
    "foglio_parziale": "10:00",         # tab «Calcolo GN» provvisorio nei giorni in mezzo alla giornata (l'ultimo: calcolo delle 7:45)     # tabellini corretti da ESPN? (il live si aggiorna 5 minuti dopo)
    "partita_nuova": "16:00",           # /partita senza argomenti passa alla giornata nuova dalle 16 del suo primo giorno
    "injury_fitti": "19:00",            # primo giorno di una giornata: injury report ogni mezz'ora da qui alla prima partita
    # IPanchinari
    "fine_blocco_panchine": "06:00",    # giorno dopo l'ultima notte: si apre la giornata successiva
    "promemoria_quintetti": "08:00",    # dell'ultimo giorno prima della prima partita
    # bot aste
    "check_cap_stagionale": "13:00",
}


def orario(nome: str):
    """L'orario `nome` (datetime.time, senza fuso: il fuso lo mette chi lo usa, sempre Roma)."""
    from datetime import time
    d = ORARI[nome]
    v = (_settings().get("orari") or {}).get(nome) if isinstance(_settings().get("orari"), dict) else None
    for x in (v, d):
        if x is None:
            continue
        try:
            h, m = str(x).strip().replace(".", ":").split(":")
            t = time(int(h), int(m))
            return t
        except (ValueError, TypeError):
            if x is v:
                _avvisa("settings.json: orari.%s = %r non è un orario HH:MM, uso %s", nome, v, d)
    raise ValueError(nome)

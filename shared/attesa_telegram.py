"""Avvio senza crash quando Telegram non risponde a un bot (v7.19.0).

Il 17/11 (IPanchinari) e il 19/11 (loucabot) Telegram ha smesso per ore di rispondere a un solo bot, gli
altri ok: all'avvio `getMe` andava in timeout, python-telegram-bot sollevava TimedOut, il container andava in
crash e Docker lo riavviava, in giro continuo, coi log pieni di traceback e senza nessun job (neanche quelli
che parlano solo con ESPN e col database).

`attendi(token, nome, mentre=None)`, chiamata prima di `run_polling`: prova `getMe` con un timeout corto e,
finché non risponde, aspetta con attese crescenti (15 s, 30 s, 60 s, poi ogni 2 minuti), una riga di log per
tentativo, e intanto chiama `mentre()` (per loucabot: scarica partite e tabellini, che non hanno bisogno di
Telegram). Ritorna i secondi passati ad aspettare (0 se ha risposto subito): il bot lo dice nel canale di log
appena riparte.
"""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

ULTIMA_ATTESA = 0                    # secondi aspettati all'ultimo avvio (per il messaggio di avvio)
ULTIMA_SENZA_RETE = 0                # di questi, quanti con la rete del server giù (non solo Telegram)
CONTROLLO_RETE = ("https://site.api.espn.com/", "https://www.google.com/generate_204")
ATTESE = (15, 30, 60, 120)          # secondi tra un tentativo e l'altro; poi sempre l'ultima
TIMEOUT = 10                         # secondi per getMe


def risponde(token: str, timeout: float = TIMEOUT, get=None) -> bool:
    """True se Telegram risponde a getMe per questo token. `get` si può sostituire nelle prove."""
    get = get or httpx.get
    try:
        r = get(f"https://api.telegram.org/bot{token}/getMe", timeout=timeout)
        return r.status_code == 200 and bool(r.json().get("ok"))
    except Exception as e:                       # timeout, rete: il token non finisce nel log
        logger.warning("Telegram non risponde (%s)", type(e).__name__)
        return False


def rete_ok(get=None, timeout: float = 5) -> bool:
    """La rete del server funziona? (v7.19.1, Luca: «capire subito se è la mia rete o Telegram») Basta che
    risponda uno degli indirizzi di controllo, qualsiasi codice HTTP."""
    get = get or httpx.get
    for url in CONTROLLO_RETE:
        try:
            get(url, timeout=timeout)
            return True
        except Exception:
            continue
    return False


def attendi(token: str, nome: str, mentre=None, get=None, dormi=time.sleep, attese=ATTESE, rete=None) -> int:
    """Aspetta che Telegram risponda al bot; `mentre()` a ogni giro di attesa. Ritorna i secondi aspettati.
    A ogni tentativo fallito guarda anche se la rete del server funziona (`rete()`), per dire dopo di chi era
    il problema."""
    global ULTIMA_SENZA_RETE
    rete = rete or (lambda: rete_ok(get=get))
    inizio = time.monotonic()
    i = 0
    senza_rete = 0
    while not risponde(token, get=get):
        pausa = attese[min(i, len(attese) - 1)]
        giu = not rete()
        if giu:
            senza_rete += pausa
        logger.warning("%s: %s, riprovo tra %d s (tentativo %d)", nome,
                       "la rete del server non funziona" if giu else "Telegram non risponde a getMe (la rete va)",
                       pausa, i + 1)
        if mentre:
            try:
                mentre()
            except Exception as e:
                logger.warning("%s: lavoro durante l'attesa: %s", nome, e)
        dormi(pausa)
        i += 1
    global ULTIMA_ATTESA
    aspettati = int(time.monotonic() - inizio)
    ULTIMA_ATTESA = aspettati if i else 0
    ULTIMA_SENZA_RETE = min(senza_rete, ULTIMA_ATTESA) if i else 0
    if i:
        logger.info("%s: Telegram risponde di nuovo dopo %d s e %d tentativi", nome, aspettati, i)
    return aspettati if i else 0


def durata(secondi: float) -> str:
    m = max(1, round(secondi / 60))
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


def nota_avvio() -> str:
    """Da aggiungere al messaggio di avvio nel canale di log se all'avvio si è aspettato: di chi era il problema."""
    if not ULTIMA_ATTESA:
        return ""
    solo_tg = ULTIMA_ATTESA - ULTIMA_SENZA_RETE
    if ULTIMA_SENZA_RETE and solo_tg > 60:
        perche = (f"🌐 la rete del server non funzionava (circa {durata(ULTIMA_SENZA_RETE)}), poi Telegram non rispondeva "
                  f"a questo bot (circa {durata(solo_tg)})")
    elif ULTIMA_SENZA_RETE:
        perche = "🌐 la rete del server non funzionava (problema della tua rete, non di Telegram)"
    else:
        perche = "📡 Telegram non rispondeva a questo bot (la rete del server andava: problema di Telegram)"
    return f"\n⚠️ Ripartito dopo {durata(ULTIMA_ATTESA)}: {perche}."

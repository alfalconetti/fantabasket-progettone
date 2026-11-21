#!/usr/bin/env python3
"""Controllo dei bot verso Telegram, sul server (v7.19.0; dopo il 17/11 e il 19/11: Telegram non rispondeva a un
solo bot per ore, gli altri ok).

Prima guarda se la **rete del server** funziona (ESPN, Google): se no il problema è la rete di casa, non Telegram,
e lo dice così (v7.19.1, Luca: «capire sempre subito se è un problema della mia rete o di Telegram»). Poi per ogni
bot: `getMe` e `getMyCommands` con un timeout (15 s) e lo stato del container. Le diagnosi:
  🌐 rete del server giù · 📡 Telegram non risponde a tutti i bot (rete ok: problema di Telegram) ·
  📡 Telegram non risponde a un bot (gli altri sì) · 🐳 container in riavvio o fermo (Telegram ok: problema del bot).
Avvisa nel canale di log con un bot che risponde (prima il principale), una volta sola; se l'avviso non può partire
(rete giù) si segna lo stesso, e al ritorno arriva un messaggio solo con inizio, fine e durata.
Lo stato tra un giro e l'altro è in ~/.fantabasket_controllo.json.

Uso, dalla cartella del progetto:
    python3 scripts/controllo_bot.py            # controlla, stampa e avvisa
    python3 scripts/controllo_bot.py --muto     # controlla e stampa, senza messaggi
Per farlo girare da solo ogni 10 minuti (crontab -e):
    */10 * * * * cd ~/bots/fantabasket-progettone && python3 scripts/controllo_bot.py >> ~/controllo_bot.log 2>&1
Solo libreria standard: niente da installare. Il token non viene mai stampato.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

QUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT = [  # (nome, file del token in secrets/, servizio di docker compose)
    ("bot principale", "bot_token_main.txt", "bot-main"),
    ("bot aste", "bot_token_aste_beta.txt", "bot-aste-beta"),
    ("loucabot", "bot_token_loucabot.txt", "loucabot"),
    ("IPanchinari", "bot_token_ipanchinari.txt", "ipanchinari"),
    ("klra", "bot_token_klra.txt", "klra"),
]
STATO = os.path.expanduser("~/.fantabasket_controllo.json")
TIMEOUT = 15


def token(file: str) -> str | None:
    p = os.path.join(QUI, "secrets", file)
    return open(p).read().strip() if os.path.exists(p) else None


def chiama(tok: str, metodo: str, dati: dict | None = None, timeout: float = TIMEOUT) -> tuple[bool, float, str]:
    """(risposto bene, secondi, errore) per una chiamata all'API di Telegram."""
    inizio = time.time()
    try:
        corpo = urllib.parse.urlencode(dati).encode() if dati else None
        with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/{metodo}", data=corpo, timeout=timeout) as r:
            ok = json.loads(r.read()).get("ok", False)
        return ok, time.time() - inizio, "" if ok else "risposta non ok"
    except Exception as e:
        return False, time.time() - inizio, type(e).__name__


def container(servizio: str) -> str:
    """'running', 'restarting', 'exited'… o 'assente'."""
    try:
        cid = subprocess.run(["docker", "compose", "ps", "-aq", servizio], cwd=QUI, capture_output=True, text=True,
                             timeout=30).stdout.strip()
        if not cid:
            return "assente"
        return subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", cid.splitlines()[0]],
                              capture_output=True, text=True, timeout=30).stdout.strip() or "sconosciuto"
    except Exception as e:
        return f"non letto ({type(e).__name__})"


def canale_log() -> int | None:
    try:
        return json.load(open(os.path.join(QUI, "config", "globals.json"))).get("log_channel_id")
    except Exception:
        return None


def durata(secondi: float) -> str:
    m = max(1, round(secondi / 60))
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


def controlla() -> list[dict]:
    esiti = []
    for nome, file, servizio in BOT:
        tok = token(file)
        if not tok:
            continue                                  # bot non configurato su questo server (es. klra)
        me = chiama(tok, "getMe")
        cmd = chiama(tok, "getMyCommands")
        st = container(servizio)
        problemi = []
        if not me[0]:
            problemi.append(f"getMe {me[2] or 'errore'} dopo {me[1]:.0f} s")
        if not cmd[0]:
            problemi.append(f"getMyCommands {cmd[2] or 'errore'} dopo {cmd[1]:.0f} s")
        if st == "restarting":
            problemi.append("container in riavvio continuo")
        elif st not in ("running", "assente"):
            problemi.append(f"container {st}")
        esiti.append({"nome": nome, "tok": tok, "me": me, "cmd": cmd, "container": st, "problemi": problemi,
                      "servizio": servizio})
    return esiti


CONTROLLO_RETE = ("https://site.api.espn.com/", "https://www.google.com/generate_204")


def rete_ok() -> bool:
    """La rete del server funziona: risponde almeno un indirizzo di controllo (qualsiasi codice HTTP)."""
    for url in CONTROLLO_RETE:
        try:
            urllib.request.urlopen(url, timeout=8).close()
            return True
        except urllib.error.HTTPError:
            return True                                 # ha risposto, anche se con un errore HTTP
        except Exception:
            continue
    return False


def avvisa(esiti: list[dict], testo: str) -> bool:
    """Manda il testo nel canale di log col primo bot che risponde (il principale per primo)."""
    chat = canale_log()
    if not chat:
        print("canale di log non trovato in config/globals.json: nessun avviso")
        return False
    for e in esiti:
        if e["me"][0] and chiama(e["tok"], "sendMessage", {"chat_id": chat, "text": testo})[0]:
            return True
    print("nessun bot risponde: avviso non mandato (resta segnato, arriva al ritorno)")
    return False


def ora_txt(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%d/%m %H:%M")


def diagnosi(esiti: list[dict], rete: bool) -> dict:
    """{chiave: testo} dei problemi di adesso. Chiavi: "_rete", "_telegram" (tutti i bot), nome del bot."""
    if not rete:
        return {"_rete": "🌐 La rete del server non funziona (non rispondono né Telegram né ESPN né Google): "
                         "è un problema della tua rete, non di Telegram."}
    out = {}
    muti = [e for e in esiti if not e["me"][0]]
    if esiti and len(muti) == len(esiti):
        out["_telegram"] = ("📡 Telegram non risponde a nessun bot, ma la rete del server funziona: è un problema di "
                            "Telegram, non tuo.")
    for e in esiti:
        if e in muti and "_telegram" in out:
            continue
        if not e["me"][0] or not e["cmd"][0]:
            out[e["nome"]] = (f"📡 {e['nome']}: Telegram non gli risponde (" + "; ".join(e["problemi"]) +
                              "), gli altri bot sì e la rete funziona: è Telegram con questo bot, di solito passa da solo.")
        elif e["problemi"]:
            out[e["nome"]] = (f"🐳 {e['nome']}: " + "; ".join(e["problemi"]) +
                              ". Telegram gli risponde: il problema è nel bot (docker compose logs --tail 60 "
                              + e["servizio"] + ").")
    return out


def main():
    muto = "--muto" in sys.argv
    rete = rete_ok()
    esiti = controlla() if rete else []
    ora = time.time()
    print(f"{datetime.now():%d/%m %H:%M}  rete del server {'ok' if rete else 'GIÙ'}")
    for e in esiti:
        print(f"{datetime.now():%d/%m %H:%M}  {e['nome']:15} getMe {'ok' if e['me'][0] else 'NO'} ({e['me'][1]:.1f}s)  "
              f"getMyCommands {'ok' if e['cmd'][0] else 'NO'} ({e['cmd'][1]:.1f}s)  container {e['container']}")
    try:
        stato = json.load(open(STATO))
    except Exception:
        stato = {}
    adesso = diagnosi(esiti, rete)
    for k, testo in adesso.items():
        if k not in stato:
            mandato = not muto and avvisa(esiti, "⚠️ " + testo + " Avviso quando torna.")
            stato[k] = {"dal": ora, "testo": testo, "avvisato": mandato}
    for k in [k for k in stato if k not in adesso]:
        if not rete and k != "_rete":
            continue                                  # a rete giù non si sa niente dei bot: si aspetta
        x = stato[k] if isinstance(stato[k], dict) else {"dal": stato[k], "testo": k, "avvisato": True}
        if k == "_rete":
            ritorno = f"✅ La rete del server è tornata: non funzionava dalle {ora_txt(x['dal'])} alle {ora_txt(ora)} (circa {durata(ora - x['dal'])})."
        elif k == "_telegram":
            ritorno = f"✅ Telegram risponde di nuovo a tutti i bot, dopo circa {durata(ora - x['dal'])} (dalle {ora_txt(x['dal'])})."
        else:
            ritorno = f"✅ {k} di nuovo a posto, dopo circa {durata(ora - x['dal'])} (dalle {ora_txt(x['dal'])})."
        if not x.get("avvisato"):
            ritorno += "\n(L'avviso all'inizio non era potuto partire.)"
        if muto or avvisa(esiti, ritorno):
            stato.pop(k, None)
    with open(STATO, "w") as f:
        json.dump(stato, f)


if __name__ == "__main__":
    main()

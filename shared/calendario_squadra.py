"""
/calendario [N] [SQUADRA] di una squadra (loucabot; v7.3.0 anche nel bot principale, Luca 09/11): la giornata
(date, scadenza della formazione, chi prende la media), l'avversario, casa o trasferta, il risultato se convalidato,
e le prossime tre. Il codice in comune sta qui; senza squadra loucabot mostra la giornata intera (immagine), il bot
principale chiede la squadra.
"""
import html
from datetime import datetime
from zoneinfo import ZoneInfo

from shared import lettura as L
from shared.numeri import testo as tp

ET = ZoneInfo("America/New_York")
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def e(x) -> str:
    return html.escape(str(x), quote=False)


def ora(t) -> str:
    if not t:
        return "?"
    t = t.astimezone(ZoneInfo("Europe/Rome"))
    return f"{GIORNI[t.weekday()]} {t:%d/%m} alle {t:%H:%M}"


def giornate(s: str) -> list[dict]:
    return L.q("SELECT * FROM lega_giornate WHERE stagione = %s ORDER BY numero", (s,), many=True) or []


def giornata(s: str, n: int) -> dict | None:
    return L.q("SELECT * FROM lega_giornate WHERE stagione = %s AND numero = %s", (s, n), one=True)


def corrente(s: str, oggi=None) -> dict | None:
    """La giornata in corso o la prossima (giorni NBA)."""
    oggi = oggi or datetime.now(ET).date()
    return next((g for g in giornate(s) if g["al"] >= oggi), None)


def partita_squadra(s: str, n: int, team_id: str) -> dict | None:
    return L.q("SELECT * FROM lega_partite WHERE stagione = %s AND giornata = %s AND %s IN (casa, trasferta)",
               (s, n, team_id), one=True)


def risultato(s: str, n: int, p: dict) -> dict | None:
    """Il risultato convalidato di una partita della lega, se c'è."""
    return L.q("SELECT * FROM lega_risultati WHERE stagione = %s AND giornata = %s AND casa = %s AND convalidato IS NOT NULL",
               (s, n, p["casa"]), one=True)


def stato_calcolo(s: str, n: int) -> str | None:
    try:
        r = L.q("SELECT stato FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (s, n), one=True)
    except Exception:
        return None
    return r["stato"] if r else None


def riga_giornata(g: dict) -> str:
    righe = [f"📅 <b>Giornata {g['numero']}</b> · {g['dal']:%d/%m} – {g['al']:%d/%m}"]
    if g.get("prima_partita"):
        righe.append(f"⏰ Formazione e panchina entro <b>{ora(g['prima_partita'])}</b> (prima partita NBA)")
    media = g["media"] if g.get("media") is not None else g.get("media_file")
    if media:
        righe.append(f"📈 Prendono la media (senza partite NBA): <b>{', '.join(media)}</b>")
    return "\n".join(righe)


def riga_partita(s: str, n: int, p: dict) -> str:
    """«Casa – Trasferta», col risultato se la giornata è convalidata (vincente in grassetto)."""
    casa, tr = e(L.nome(p["casa"])), e(L.nome(p["trasferta"]))
    r = risultato(s, n, p)
    if not r:
        return f"• {casa} – {tr}"
    if r["vince"] == "casa":
        casa = f"<b>{casa}</b>"
    elif r["vince"] == "trasferta":
        tr = f"<b>{tr}</b>"
    t = f"• {casa} {tp(r['punti_casa'])} – {tp(r['punti_trasferta'])} {tr}"
    if r["supp_casa"] is not None:
        t += f" <i>(supp. {tp(r['supp_casa'])} – {tp(r['supp_trasferta'])})</i>"
    if r["vince"] == "pari":                               # solo nei sistemi di klra (v7.1.0)
        t += " · 🤝 pareggio"
    return t


def testo_squadra(s: str, g: dict, team: dict, piede: str) -> str:
    """La giornata g di una squadra e le prossime tre. piede: la riga in corsivo in fondo (i comandi del bot)."""
    righe = [riga_giornata(g), ""]
    p = partita_squadra(s, g["numero"], team["id"])
    if p:
        casa = p["casa"] == team["id"]
        avv = p["trasferta"] if casa else p["casa"]
        righe.append(f"🏀 <b>{e(team['nome'])}</b> {'in casa (+3)' if casa else 'in trasferta'} contro "
                     f"<b>{e(L.nome(avv))}</b>")
        if risultato(s, g["numero"], p):
            righe.append(riga_partita(s, g["numero"], p))
    prossime = [x for x in giornate(s) if x["numero"] > g["numero"]][:3]
    if prossime:
        righe += ["", "<b>Le prossime</b>"]
        for x in prossime:
            p = partita_squadra(s, x["numero"], team["id"])
            if p:
                casa = p["casa"] == team["id"]
                righe.append(f"• G{x['numero']} {x['dal']:%d/%m}: {'🏠' if casa else '✈️'} "
                             f"{e(L.nome(p['trasferta'] if casa else p['casa']))}")
    if piede:
        righe += ["", f"<i>{piede}</i>"]
    return "\n".join(righe)


def argomenti(args) -> tuple[int | None, str]:
    """(numero di giornata, testo della squadra) da /calendario [N] [SQUADRA] (in qualsiasi ordine)."""
    n, resto = None, []
    for a in args or []:
        if n is None and a.isdigit():
            n = int(a)
        else:
            resto.append(a)
    return n, " ".join(resto).strip()

"""
Cam Thomas exception riconosciuta dal bot (v7.30.0, Luca 26/11). Regolamento, Specifica regola 1: un giocatore
tagliato da una franchigia NBA, senza cambiare campionato, può decadere gratis dopo un mese senza squadra **a mercato
NBA aperto**; la regola si applica durante la regular season NBA, e chi è senza squadra a cavallo di due stagioni può
decadere solo 10 giorni dopo l'inizio della regular season.

Le timeline sono quelle NBA, non della lega:
- mercato NBA aperto dall'inizio della free agency NBA (1° luglio, `nba_inizio_mercato` in globals.json come MM-GG)
  alla trade deadline NBA (`nba_trade_deadline` in globals.json, per stagione: /deadline_nba); dalla deadline al
  1° luglio è chiuso e i giorni non contano;
- regular season NBA dal calendario (nba_partite, tipo 2).

Quindi: si contano 30 giorni senza squadra a mercato aperto dal taglio (quelli dopo la deadline ripartono dal 1°
luglio); il giorno in cui si arriva a 30, se cade prima della regular season (estate, preseason), diventa l'inizio della
regular season + 10. Esempi: tagliato a novembre, dopo 30 giorni; a ottobre in preseason, dopo 30 giorni (non prima di
10 giorni di regular season); d'estate, 10 giorni dopo l'inizio della regular season; a metà gennaio senza arrivare a 30
entro la deadline, o a marzo, la stagione dopo, 10 giorni dopo l'inizio della regular season.

Il bot propone e basta: la decisione resta degli admin, caso per caso (non sa se ha firmato in un altro campionato:
allora il motivo è «altra lega»). Dati: i roster ESPN delle 8:30 (nba_atleti.squadra, NULL = in nessun roster) e i
cambi visti da loucabot (nba_movimenti, dal 23/10/2026: `a` NULL = uscito da tutti i roster); chi era già fuori prima
conta dal 23/10/2026 («almeno»).
"""
from datetime import date, timedelta

from shared import lettura as L

GIORNI = 30            # un mese senza squadra, a mercato NBA aperto
DOPO_INIZIO = 10       # non prima di 10 giorni di regular season
INIZIO_DATI = date(2026, 10, 23)   # da qui loucabot registra i cambi di squadra NBA


def stagione_di(d: date) -> int:
    return d.year if d.month >= 7 else d.year - 1


def inizio_rs(s: int) -> date | None:
    r = L.q("SELECT MIN(data_et) AS d FROM nba_partite WHERE stagione = %s AND tipo = 2", (str(s),), one=True)
    return r["d"] if r and r["d"] else None


def deadline(s: int) -> date | None:
    """La trade deadline NBA della stagione `s` (globals.json `nba_trade_deadline`: {"2026": "2027-02-05"}, o una data
    sola, se cade in quella stagione). Non quella della lega."""
    v = L.globali().get("nba_trade_deadline")
    raw = v.get(str(s)) if isinstance(v, dict) else v
    try:
        d = date.fromisoformat(str(raw or ""))
    except ValueError:
        return None
    return d if date(s, 7, 1) <= d <= date(s + 1, 6, 30) else None


def inizio_mercato(s: int) -> date:
    """L'inizio della free agency NBA della stagione `s` (globals.json `nba_inizio_mercato` MM-GG, se no 07-01)."""
    mm, gg = (int(x) for x in str(L.globali().get("nba_inizio_mercato") or "07-01").split("-"))
    return date(s, mm, gg)


def mercato_aperto(s: int) -> tuple[date, date, bool]:
    """(dal, al, deadline nota) del mercato NBA aperto nella stagione `s`; senza deadline fino al 30 giugno."""
    dl = deadline(s)
    return inizio_mercato(s), (dl or date(s + 1, 6, 30)), dl is not None


def trenta(dal: date) -> tuple[date, bool]:
    """Il giorno in cui chi è senza squadra dal giorno `dal` arriva a 30 giorni a mercato aperto; se le deadline usate erano tutte note."""
    s, contati, note = stagione_di(dal), 0, True
    for _ in range(5):
        da, al, nota = mercato_aperto(s)
        da = max(da, dal + timedelta(days=1))
        if da <= al:
            note = note and nota
            if contati + (al - da).days + 1 >= GIORNI:
                return da + timedelta(days=GIORNI - contati - 1), note
            contati += (al - da).days + 1
        s += 1
    return date.max, note


def senza_squadra_dal(atleta: str) -> tuple[bool, date | None]:
    """(in un roster NBA adesso, da quando è fuori da tutti i roster; None = da prima del 23/10/2026 o mai visto)."""
    a = L.q("SELECT squadra FROM nba_atleti WHERE atleta = %s", (atleta,), one=True)
    if a and a["squadra"]:
        return True, None
    m = L.q("SELECT giorno, a FROM nba_movimenti WHERE atleta = %s ORDER BY giorno DESC, id DESC LIMIT 1", (atleta,), one=True)
    return False, (m["giorno"] if m and m["a"] is None else None)


def valuta(atleta: str, oggi: date | None = None) -> dict | None:
    """None se ha una squadra NBA; se no {dal, almeno, d30, idoneo_dal, idoneo, perche, deadline_nota}."""
    oggi = oggi or date.today()
    in_roster, dal = senza_squadra_dal(atleta)
    if in_roster:
        return None
    almeno = dal is None
    dal = dal or INIZIO_DATI
    d30, note = trenta(dal)
    idoneo_dal, perche = None, ""
    if d30 != date.max:
        ini = inizio_rs(stagione_di(d30))
        if ini and d30 >= ini + timedelta(days=DOPO_INIZIO):
            idoneo_dal, perche = d30, f"{GIORNI} giorni senza squadra a mercato NBA aperto"
        elif ini:
            idoneo_dal = ini + timedelta(days=DOPO_INIZIO)
            perche = (f"{GIORNI} giorni a mercato aperto già il {d30:%d/%m}, ma non prima di {DOPO_INIZIO} giorni "
                      "di regular season")
    return {"dal": dal, "almeno": almeno, "d30": d30, "idoneo_dal": idoneo_dal,
            "idoneo": bool(idoneo_dal and idoneo_dal <= oggi), "perche": perche, "deadline_nota": note}


def testo(v: dict | None, oggi: date | None = None) -> str:
    """Una riga per gli admin: da quando è senza squadra e da quando può decadere."""
    oggi = oggi or date.today()
    if v is None:
        return "ha una squadra NBA (nei roster ESPN di stamattina)"
    dal = (f"senza squadra NBA {'almeno ' if v['almeno'] else ''}dal {v['dal']:%d/%m/%Y} ({(oggi - v['dal']).days} giorni"
           + (", prima il bot non registrava i cambi)" if v["almeno"] else ")"))
    if not v["idoneo_dal"]:
        quando = "non si sa ancora da quando può decadere (manca l'inizio della regular season NBA nel calendario)"
    elif v["idoneo"]:
        quando = f"può decadere dal {v['idoneo_dal']:%d/%m/%Y} ({v['perche']})"
    else:
        quando = f"non ancora: potrà decadere dal {v['idoneo_dal']:%d/%m/%Y} ({v['perche']})"
    nota = "" if v["deadline_nota"] else " · ⚠️ trade deadline NBA non impostata: conto il mercato aperto fino a giugno"
    return f"{dal}; {quando}{nota}"

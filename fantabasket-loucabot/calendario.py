"""
Calendario della lega: lettura del CSV, controlli, import, e per ogni giornata la scadenza della
formazione e le squadre NBA a media, calcolate dalle partite NBA.

Il CSV è quello pubblicato dagli admin, una giornata dopo l'altra:

    Week 2 23/10 - 24/10 (media OKC),,,,
    Ntilikinerz,,V,,Champapon Newborns          ← casa, "V", trasferta
    ,,,,

Le date sono giorni NBA (costa est). L'anno si ricava dalla stagione: da luglio a dicembre è
l'anno in cui inizia, da gennaio quello dopo.
Regolamento: "giocatori indisponibili non prenderanno la media, ma zero"; le squadre NBA senza
partite nella giornata prendono la media (giornate 2 e 3 del 2026-27: OKC e NOP).
"""
import csv
import io
import re
from datetime import date, datetime, timezone

import config
import db
import nba

RE_GIORNATA = re.compile(r"^\s*(?:week|giornata)\s+(\d+)\s+(\d{1,2})/(\d{1,2})\s*-\s*(\d{1,2})/(\d{1,2})"
                         r"(?:\s*\(\s*media\s+([^)]*)\))?", re.I)


class ErroreCalendario(Exception):
    pass


def _data(giorno: int, mese: int, stagione: str) -> date:
    anno = int(stagione) if mese >= 7 else int(stagione) + 1
    return date(anno, mese, giorno)


def leggi_csv(testo: str, stagione: str) -> tuple[list[dict], list[tuple[int, str, str]]]:
    """(giornate, partite con i nomi come nel file). Non controlla le squadre."""
    giornate, partite, corrente = [], [], None
    for n, riga in enumerate(csv.reader(io.StringIO(testo)), 1):
        celle = [c.strip() for c in riga]
        if not any(celle):
            continue
        m = RE_GIORNATA.match(",".join(riga))       # "(media DAL,LAL)" anche se le virgole spezzano la riga
        if m:
            g, d1, m1, d2, m2, media = m.groups()
            corrente = int(g)
            media = sorted({x.strip().upper() for x in (media or "").split(",") if x.strip()})
            giornate.append({"numero": corrente, "dal": _data(int(d1), int(m1), stagione),
                             "al": _data(int(d2), int(m2), stagione), "media_file": media})
            continue
        casa = celle[0]
        trasferta = next((c for c in celle[2:] if c and c.upper() != "V"), "")
        if casa and trasferta:
            if corrente is None:
                raise ErroreCalendario(f"riga {n}: partita prima della prima giornata")
            partite.append((corrente, casa, trasferta))
        elif casa:
            raise ErroreCalendario(f"riga {n}: non capisco «{','.join(riga)}»")
    return giornate, partite


def abbina_squadre(nomi: set[str]) -> tuple[dict, list[str], list[str]]:
    """{nome nel file: team_id} e nomi non trovati. Solo nome della squadra o id esatti (senza
    maiuscole e accenti): in un import un abbinamento per somiglianza può sbagliare squadra, quindi
    per i nomi non trovati si propone soltanto quella più simile."""
    from shared.squadre import cerca_squadra, normalizza
    tutte = config.squadre()
    mappa, mancanti = {}, []
    for nome in sorted(nomi):
        t = next((x for x in tutte if normalizza(x["nome"]) == normalizza(nome) or x["id"] == nome.strip()), None)
        if t:
            mappa[nome] = t["id"]
        else:
            simile = cerca_squadra(nome, tutte)
            mancanti.append(f"«{nome}»" + (f" (forse {simile['nome']}?)" if simile else ""))
    return mappa, mancanti, []


def controlla(giornate: list[dict], partite: list[tuple[int, str, str]], squadre_ids: set[str]) -> list[str]:
    """Errori che impediscono l'import."""
    errori = []
    numeri = [g["numero"] for g in giornate]
    if numeri != list(range(1, len(numeri) + 1)):
        errori.append(f"giornate non in ordine da 1: {numeri[:10]}…")
    for a, b in zip(giornate, giornate[1:]):
        if b["dal"] <= a["al"]:
            errori.append(f"giornata {b['numero']}: inizia ({b['dal']:%d/%m}) prima della fine della {a['numero']}")
    for g in giornate:
        if g["al"] < g["dal"]:
            errori.append(f"giornata {g['numero']}: finisce prima di iniziare")
        qui = [s for n, c, t in partite if n == g["numero"] for s in (c, t)]
        if sorted(qui) != sorted(squadre_ids):
            doppie = sorted({s for s in qui if qui.count(s) > 1})
            assenti = sorted(set(squadre_ids) - set(qui))
            errori.append(f"giornata {g['numero']}: " + "; ".join(
                x for x in (f"due volte {', '.join(map(config.nome, doppie))}" if doppie else "",
                            f"manca {', '.join(map(config.nome, assenti))}" if assenti else "") if x))
    return errori


def importa(testo: str, stagione: str | None = None) -> dict:
    """Legge, controlla e salva il calendario. Solleva ErroreCalendario con l'elenco dei problemi."""
    stagione = stagione or config.stagione()
    giornate, partite_nomi = leggi_csv(testo, stagione)
    if not giornate:
        raise ErroreCalendario("nessuna giornata trovata (righe come «Week 1 20/10 - 22/10»)")
    mappa, mancanti, dubbi = abbina_squadre({s for _, c, t in partite_nomi for s in (c, t)})
    if mancanti:
        raise ErroreCalendario("squadre non trovate in teams.json: " + ", ".join(mancanti))
    partite = [(g, mappa[c], mappa[t]) for g, c, t in partite_nomi]
    errori = controlla(giornate, partite, {t["id"] for t in config.squadre()})
    if errori:
        raise ErroreCalendario("\n".join(errori))
    db.sostituisci_calendario(stagione, giornate, partite)
    db.salva_csv_calendario(stagione, testo)
    return {"stagione": stagione, "giornate": len(giornate), "partite": len(partite), "dubbi": dubbi,
            "dal": giornate[0]["dal"], "al": giornate[-1]["al"]}


# ── calcoli dalle partite NBA ─────────────────────────────────────────────────

def calcola(g: dict, squadre_nba: set[str]) -> dict:
    """Prima partita (scadenza della formazione) e squadre senza partite (a media)."""
    partite = [p for p in db.partite_nba(g["dal"], g["al"]) if p["stato"] not in ("STATUS_POSTPONED", "STATUS_CANCELED")]
    giocano = {s for p in partite for s in (p["casa"], p["trasferta"])} & nba.NBA
    return {"prima_partita": min((p["inizio"] for p in partite), default=None),
            "media": sorted(squadre_nba - giocano) if partite else None,
            "partite_nba": len(partite)}


def ricalcola(stagione: str | None = None, oggi: date | None = None) -> list[str]:
    """Ricalcola tutte le giornate e restituisce le differenze rispetto al calcolo precedente
    (solo per le giornate non ancora finite)."""
    stagione = stagione or config.stagione()
    squadre_nba = db.squadre_nba(stagione)
    oggi = oggi or datetime.now(nba.ET).date()
    cambi = []
    for g in db.giornate(stagione):
        c = calcola(g, squadre_nba)
        if g["calcolato"] and g["al"] >= oggi:
            if c["prima_partita"] != g["prima_partita"] and g["prima_partita"]:
                cambi.append(f"giornata {g['numero']}: la prima partita passa da "
                             f"{ora(g['prima_partita'])} a {ora(c['prima_partita'])}")
            if (c["media"] or []) != (g["media"] or []) and g["media"] is not None:
                cambi.append(f"giornata {g['numero']}: prendono la media {', '.join(c['media'] or []) or 'nessuno'} "
                             f"(prima {', '.join(g['media'] or []) or 'nessuno'})")
        db.salva_calcolo(stagione, g["numero"], c["prima_partita"], c["media"])
    return cambi


def differenze_file(stagione: str | None = None) -> list[str]:
    """Giornate in cui le squadre a media calcolate non sono quelle scritte nel calendario."""
    out = []
    for g in db.giornate(stagione or config.stagione()):
        if g["media"] is None:
            continue
        if sorted(g["media"]) != sorted(g["media_file"] or []):
            out.append(f"giornata {g['numero']}: calendario {', '.join(g['media_file']) or 'nessuno'}, "
                       f"partite NBA {', '.join(g['media']) or 'nessuno'}")
    return out


def corrente(stagione: str | None = None, oggi: date | None = None) -> dict | None:
    """La giornata in corso o la prossima (giorni NBA)."""
    oggi = oggi or datetime.now(nba.ET).date()
    return next((g for g in db.giornate(stagione or config.stagione()) if g["al"] >= oggi), None)


def da_mostrare(s: str, ora: datetime | None = None) -> dict | None:
    """La giornata senza numero di /partita, /giornata e /risultati (Luca, 25/10): quella in corso, la
    stessa fino alla convalida; dopo la convalida la successiva, ma solo dalle 16 (orari.partita_nuova) del suo primo giorno: fino ad allora quella appena finita."""
    from zoneinfo import ZoneInfo
    from shared import regole
    ora = ora or datetime.now(timezone.utc)
    gg = db.giornate(s)
    convalidate = {r["giornata"] for r in db.q("SELECT giornata FROM lega_calcoli WHERE stagione = %s AND stato = 'convalidata'",
                                                (s,), many=True) or []}
    i = next((k for k, g in enumerate(gg) if g["numero"] not in convalidate), None)
    if i is None:
        return gg[-1] if gg else None
    da = datetime.combine(gg[i]["dal"], regole.orario("partita_nuova"), tzinfo=ZoneInfo("Europe/Rome"))
    if i > 0 and ora < da:
        return gg[i - 1]
    return gg[i]


def ora(t) -> str:
    if not t:
        return "?"
    from zoneinfo import ZoneInfo
    giorni = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
    t = t.astimezone(ZoneInfo("Europe/Rome"))
    return f"{giorni[t.weekday()]} {t:%d/%m} alle {t:%H:%M}"

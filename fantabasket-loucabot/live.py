"""
Punteggi live (v18, deciso con Luca il 13-14/10): un messaggio sul canale principale per giornata,
pubblicato alla palla a due della prima partita e modificato ogni 10 minuti, col calcolo intero
come quello definitivo (risultati.calcola: medie, media della stagione, FADD, bonus casa,
supplementari) sui tabellini live di ESPN. Sotto: risultati provvisori, da valutare e convalidare
da un admin, e l'ora dell'ultimo aggiornamento.

Quando: per ogni notte della giornata dalla prima partita della notte alle 8:00 (Roma) del mattino
dopo, ogni 10 minuti; poi un aggiornamento alle 10:05, dopo il controllo dei tabellini delle 10
(ESPN a volte riassegna le statistiche). Il job gira ogni minuto e decide lui (così il messaggio
esce al tipoff, non fino a 10 minuti dopo).

Cosa scarica a ogni aggiornamento: il tabellone ESPN della notte (una richiesta) e i tabellini
delle partite in corso, una alla volta con una pausa. Le partite finite si scaricano una volta
sola. I tabellini parziali si salvano senza segnare la partita come "con tabellino"
(db.salva_tabellino(..., finale=False)): a partita finita il tabellino definitivo si riscarica
comunque (qui, alle 7:45 o alle 8:30). Se ESPN risponde con un errore si salta il giro e si
riprova dopo 20 minuti, con una riga sul canale log (al massimo una all'ora).

Tabella lega_live: un messaggio per giornata (chat, id, ultimo aggiornamento, prossimo tentativo).
"""
import html
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import config
import db
import nba
import risultati as R
from numeri import testo as tp

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
OGNI = timedelta(minutes=10)
from shared import regole as _rg       # orari in settings.json («orari»), letti all'avvio
FINE_NOTTE = _rg.orario("fine_live_notte")      # fine degli aggiornamenti della notte (mattino dopo, Roma)
# 5 minuti dopo il controllo dei tabellini (handlers_risultati.job_controllo)
ORA_CONTROLLO = (datetime.combine(date(2000, 1, 1), _rg.orario("controllo_tabellini")) + timedelta(minutes=5)).time()
DOPO_ERRORE = timedelta(minutes=20)
FINITE = ("STATUS_FINAL", "STATUS_POSTPONED", "STATUS_CANCELED")
NON_INIZIATE = ("STATUS_SCHEDULED", "STATUS_POSTPONED", "STATUS_CANCELED")


def e(x) -> str:
    return html.escape(str(x), quote=False)


def migra() -> None:
    db.q("""CREATE TABLE IF NOT EXISTS lega_live (
              stagione    TEXT NOT NULL,
              giornata    INT  NOT NULL,
              chat_id     BIGINT,
              message_id  BIGINT,
              aggiornato  TIMESTAMPTZ,
              prossimo    TIMESTAMPTZ,                   -- dopo un errore di ESPN: non prima di
              errore_log  TIMESTAMPTZ,                   -- ultimo errore scritto sul canale log
              PRIMARY KEY (stagione, giornata))""")
    # v37 (Luca, 23/10): alla convalida il live si cancella (chiuso: niente più aggiornamenti) e sul
    # canale esce il messaggio dei risultati definitivi (definitivo_id: a una nuova convalida si modifica)
    db.q("ALTER TABLE lega_live ADD COLUMN IF NOT EXISTS chiuso TIMESTAMPTZ")
    db.q("ALTER TABLE lega_live ADD COLUMN IF NOT EXISTS definitivo_id BIGINT")
    # esiti al momento della pubblicazione: a una nuova convalida (ricalcolo dopo il controllo delle 10)
    # si confrontano e, se cambia chi vince, esce un messaggio in più (Luca, 23/10)
    db.q("ALTER TABLE lega_live ADD COLUMN IF NOT EXISTS esiti JSONB")


def stato(s: str, n: int) -> dict | None:
    return db.q("SELECT * FROM lega_live WHERE stagione = %s AND giornata = %s", (s, n), one=True)


def _salva(s: str, n: int, **campi) -> None:
    db.q("INSERT INTO lega_live (stagione, giornata) VALUES (%s, %s) ON CONFLICT DO NOTHING", (s, n))
    for k, v in campi.items():
        db.q(f"UPDATE lega_live SET {k} = %s WHERE stagione = %s AND giornata = %s", (v, s, n))


# ── quando ─────────────────────────────────────────────────────────────────────

def notti(g: dict) -> list[tuple[date, datetime, datetime]]:
    """[(giorno ET, prima partita della notte, fine degli aggiornamenti: 8:00 del mattino dopo)]."""
    out = {}
    for p in db.partite_nba(g["dal"], g["al"]):
        if p["stato"] in ("STATUS_POSTPONED", "STATUS_CANCELED") or not p["inizio"]:
            continue
        d = p["data_et"]
        out[d] = min(out.get(d, p["inizio"]), p["inizio"])
    return [(d, inizio, datetime.combine(d + timedelta(days=1), FINE_NOTTE, ROMA)) for d, inizio in sorted(out.items())]


def cosa_fare(g: dict, ora: datetime, st: dict | None) -> tuple[str | None, date | None]:
    """("live" | "controllo" | None, notte): se e quale aggiornamento fare adesso."""
    if st and st.get("prossimo") and ora < st["prossimo"]:
        return None, None
    ultimo = st.get("aggiornato") if st else None
    for d, inizio, fine in notti(g):
        if inizio <= ora < fine:
            if not st or not st.get("message_id") or not ultimo or ora - ultimo >= OGNI - timedelta(seconds=30):
                return "live", d
            return None, None
        controllo = datetime.combine(d + timedelta(days=1), ORA_CONTROLLO, ROMA)
        if controllo <= ora < controllo + OGNI and st and st.get("message_id") and (not ultimo or ultimo < controllo):
            return "controllo", d
    return None, None


def giornate_attive(s: str, ora: datetime) -> list[dict]:
    """Giornate iniziate e non finite da più di un giorno (dove può servire un aggiornamento), non
    convalidate: una giornata convalidata ha il messaggio dei definitivi e il live non c'è più (v54: /live
    ripubblicava il live della giornata appena convalidata)."""
    oggi = ora.astimezone(ZoneInfo("America/New_York")).date()
    chiuse = {r["giornata"] for r in db.q("SELECT giornata FROM lega_live WHERE stagione = %s AND chiuso IS NOT NULL",
                                          (s,), many=True) or []}
    return [g for g in db.giornate(s)
            if g.get("prima_partita") and g["prima_partita"] <= ora and g["al"] >= oggi - timedelta(days=2)
            and g["numero"] not in chiuse]


# ── dati ───────────────────────────────────────────────────────────────────────

async def scarica(g: dict, d: date, controllo: bool = False) -> dict:
    """Tabellone della notte d e tabellini: in corso (parziali), finite senza tabellino; con
    `controllo` riscarica le finite della notte (se la giornata non è già nel calcolo definitivo:
    lì ci pensa il controllo delle 10)."""
    r = await nba.sincronizza([d])
    if r["errori"]:
        raise RuntimeError("; ".join(r["errori"]))
    partite = [p for p in db.partite_nba(d, d) if p["espn_id"] in {x["espn_id"] for x in db.partite_nba(g["dal"], g["al"])}]
    in_corso = [p["espn_id"] for p in partite if p["stato"] not in FINITE and p["stato"] not in NON_INIZIATE]
    finite = [p["espn_id"] for p in partite if p["stato"] == "STATUS_FINAL" and (controllo or not p.get("tabellino"))]
    if controllo and db.q("SELECT 1 AS x FROM lega_calcoli WHERE stagione = %s AND giornata = %s",
                          (g["stagione"], g["numero"]), one=True):
        finite = [p for p in finite if p not in {x["espn_id"] for x in partite if x.get("tabellino")}]
    errori = []
    prima = _righe(finite) if controllo else {}
    if in_corso:
        errori += (await nba.scarica_tabellini(in_corso, finale=False))["errori"]
    if finite:
        errori += (await nba.scarica_tabellini(finite))["errori"]
    if errori:
        raise RuntimeError("; ".join(errori))
    cambi = {}
    if controllo:
        dopo = _righe(finite)
        cambi = {k: (prima.get(k), dopo.get(k)) for k in set(prima) | set(dopo) if prima.get(k) != dopo.get(k)}
    return {"in_corso": len(in_corso), "finite": len(finite), "cambi": cambi}


def _righe(partite: list[str]) -> dict:
    """{(partita, atleta): (fantapunti, minuti, nome)} dei tabellini salvati."""
    if not partite:
        return {}
    return {(r["partita"], r["atleta"]): (float(r["fp"]), r["minuti"], r["nome"]) for r in db.q(
        "SELECT partita, atleta, fp, minuti, nome FROM nba_tabellini WHERE partita = ANY(%s)", (partite,), many=True) or []}


def testo_cambi(n: int, d: date, cambi: dict, c: dict) -> str | None:
    """La riga per il canale log: tabellini di giocatori schierati cambiati da ESPN dopo la notte."""
    schierati = {x["atleta"] for sq in c["squadre"].values() for x in sq["quintetto"] + sq["panchina"] if x.get("atleta")}
    contano = {k: v for k, v in cambi.items() if k[1] in schierati}
    if not contano:
        return None
    righe = []
    for (_, a), (pr, do) in sorted(contano.items(), key=lambda x: (x[1][1] or x[1][0])[2]):
        righe.append(f"• {e((do or pr)[2])}: {tp(pr[0]) if pr else '—'} → {tp(do[0]) if do else '—'} fantapunti"
                     + (f" (minuti {pr[1]} → {do[1]})" if pr and do and pr[1] != do[1] else ""))
    return (f"🔎 Live G{n}, controllo delle 10:05 sulla notte del {d:%d/%m}: ESPN ha cambiato {len(contano)} tabellini "
            f"di giocatori schierati (il messaggio live è già aggiornato):\n" + "\n".join(righe))


def calcolo(s: str, n: int) -> dict:
    """Il calcolo della giornata come quello definitivo: formazioni congelate (o i quintetti di
    adesso se IPanchinari non ha ancora chiuso la giornata) e panchine."""
    sch = None if R.giornata_chiusa(s, n) else R.schieramenti_attuali(s, n)
    return R.calcola(s, n, sch=sch)


def _da_giocare(c: dict, giocatori: list[dict]) -> tuple[int, int]:
    """(in campo adesso, ancora da giocare) tra i giocatori indicati: la loro squadra NBA sta
    giocando, o ha ancora una partita della giornata non iniziata (stanotte o nelle notti dopo)."""
    partite = db.partite_nba(c["giornata"]["dal"], c["giornata"]["al"])
    adesso = {sq for p in partite if p["stato"] not in FINITE and p["stato"] not in NON_INIZIATE for sq in (p["casa"], p["trasferta"])}
    dopo = {sq for p in partite if p["stato"] == "STATUS_SCHEDULED" for sq in (p["casa"], p["trasferta"])}
    live = poi = 0
    for x in giocatori:
        p = c["punti"].get(x.get("atleta")) or {}
        sq = p.get("squadra")
        if sq in adesso:
            live += 1
        elif sq in dopo:
            poi += 1
    return live, poi


def ancora_in_ballo(c: dict, giocatori: list[dict]) -> tuple[int, int, float]:
    """(devono giocare, devono rigiocare, punti fatti finora da chi deve rigiocare) tra i titolari
    indicati (Luca, 23/10): chi ha ancora una partita della giornata (in corso o da iniziare) e non ne
    ha ancora finita nessuna; chi ne ha già finita almeno una e ne ha un'altra, coi fantapunti che ha
    già fatto nella giornata (quelli in ballo: possono cambiare con la partita che gli resta)."""
    partite = db.partite_nba(c["giornata"]["dal"], c["giornata"]["al"])
    det = c.get("dettaglio") or {}
    notti, medie = det.get("notti") or {}, det.get("medie") or {}
    giocare = rigiocare = 0
    in_ballo = 0.0
    for x in giocatori:
        a = x.get("atleta")
        sq = (c["punti"].get(a) or {}).get("squadra")
        if not a or not sq:
            continue
        sue = [p for p in partite if sq in (p["casa"], p["trasferta"])]
        restano = [p for p in sue if p["stato"] not in FINITE]
        if not restano:
            continue
        finite = {p["data_et"] for p in sue if p["stato"] in FINITE}
        fatte = {d: fp for d, fp in (notti.get(a) or {}).items() if d in finite}
        if fatte:
            rigiocare += 1
            in_ballo += sum(float(fp or 0) for fp in fatte.values())
        else:
            giocare += 1
    _ = medie
    return giocare, rigiocare, round(in_ballo, 2)


def avvisi_brevi(c: dict) -> list[str]:
    """Gli avvisi del calcolo, una riga per squadra (per l'anteprima agli admin)."""
    import re
    per: dict[str, list[str]] = {}
    altri = []
    for a in c.get("avvisi") or []:
        nome, sep, resto = a.partition(": ")
        if not sep:
            altri.append(a)
            continue
        m = re.match(r"quintetto incompleto \(([^)]*)\)", resto)
        if m:
            posti = [x.strip() for x in m.group(1).split(",")]
            breve = "quintetto vuoto" if len(posti) == 5 else "manca " + ", ".join(x.replace("Q-", "") for x in posti)
        elif resto.startswith("panchina non mandata"):
            breve = "senza panchina"
        elif resto.startswith("senza id ESPN"):
            breve = resto.split(" (")[0]
        else:
            breve = resto
        per.setdefault(nome, []).append(breve)
    if not per and not altri:
        return ["", "✅ Nessun avviso: quintetti completi e panchine mandate."]
    out = ["", f"⚠️ <b>Avvisi del calcolo</b> ({len(per)} squadre)"]
    out += [f"• {e(n)}: {e('; '.join(v))}" for n, v in sorted(per.items())]
    out += [f"• {e(a)}" for a in altri]
    return out


MAX_DA_GIOCARE = 4      # con più di 4 dei 10 in campo ancora da giocare (o in campo) niente esito (Luca, 14/10)


LIMITE = 3900          # Telegram: 4096 caratteri per messaggio


async def manda_anteprima(bot, chat_id, c: dict, ora: datetime) -> None:
    """L'anteprima del messaggio live con gli avvisi del calcolo. Se insieme non ci stanno in un
    messaggio, gli avvisi vanno in un file .md sul canale log."""
    t = testo(c, ora, prova=True)
    av = avvisi_brevi(c)
    insieme = t + "\n" + "\n".join(av)
    if len(insieme) <= LIMITE:
        await bot.send_message(chat_id=chat_id, text=insieme, parse_mode="HTML")
        return
    import io
    import re
    canale = config.canale_log()
    nota = "\n\n⚠️ Gli avvisi del calcolo sono troppi per un messaggio: " + ("file sul canale log." if canale else "canale log non configurato.")
    await bot.send_message(chat_id=chat_id, text=t[:LIMITE - len(nota)] + nota, parse_mode="HTML")
    if canale:
        md = "\n".join(["# Avvisi del calcolo, giornata " + str(c["giornata"]["numero"]), ""]
                       + [html.unescape(re.sub(r"</?b>", "**", x)) for x in av if x])
        await bot.send_document(chat_id=canale, document=io.BytesIO(md.encode("utf-8")),
                                filename=f"avvisi-G{c['giornata']['numero']}.md",
                                caption=f"⚠️ Avvisi del calcolo, giornata {c['giornata']['numero']} (anteprima del live)")


def esito_live(r: dict, casa: str, tr: str) -> str:
    """L'esito del calcolo, "al momento": chi vince, coi supplementari se servono."""
    chi = e(casa if r["vince"] == "casa" else tr)
    if r["supplementari"] and not r["sc"]["panchina"] and not r["st"]["panchina"]:
        return f"al momento vince {chi} (nessuna delle due ha la panchina: niente supplementari)"
    if r["supplementari"]:
        return (f"al momento vince {chi} ai supplementari ({r['supplementari']}): "
                f"{tp(r['esito']['casa'])} – {tp(r['esito']['trasferta'])}")
    return f"al momento vince {chi}"


def testo(c: dict, ora: datetime, prova: bool = False) -> str:
    g = c["giornata"]
    righe = [f"🔴 <b>Giornata {g['numero']} · punteggi live</b>", ""]
    for i, r in enumerate(c["risultati"]):
        if i:
            righe.append("")                       # una riga vuota tra una partita e l'altra (Luca, 20/10)
        casa, tr = config.nome(r["casa"]), config.nome(r["trasferta"])
        righe.append(f"<b>{e(casa)}</b> {tp(r['punti_casa'])} – {tp(r['punti_trasferta'])} <b>{e(tr)}</b>")
        lc, pc = _da_giocare(c, r["sc"]["titolari"])
        lt, pt = _da_giocare(c, r["st"]["titolari"])
        stato_g = []
        if lc or lt:
            stato_g.append(f"🏀 in campo {lc}–{lt}")
        mc, mt = a_media(c, r["sc"]["titolari"]), a_media(c, r["st"]["titolari"])
        if mc or mt:                               # chi prende la media (Luca, 23/10)
            stato_g.append(f"📈 prendono media {mc}–{mt}")
        # «⏳ da giocare» per squadra, per esteso, nelle righe sotto (Luca, 23/10)
        vuoti = [n for n, sq in ((casa, r["sc"]), (tr, r["st"])) if not any(x.get("atleta") for x in sq["titolari"])]
        if vuoti:                                  # senza giocatori non c'è niente da stimare
            pezzi = [f"⚠️ quintetto vuoto: {e(', '.join(vuoti))}"] + stato_g
        else:
            pezzi = ([] if lc + lt + pc + pt > MAX_DA_GIOCARE else [f"▶ {esito_live(r, casa, tr)}"]) + stato_g
        if pezzi:
            righe.append("   " + " · ".join(pezzi))
        # chi manca, per squadra e per esteso (Luca, 23/10): quanti devono ancora giocare, quanti
        # rigiocano (hanno già una partita finita) e quanti punti hanno fatto finora (quelli in ballo)
        for nome, sq in ((casa, r["sc"]), (tr, r["st"])):
            dg, dr, finora = ancora_in_ballo(c, sq["titolari"])
            if dg or dr:
                righe.append(f"   {e(nome)}: devono giocare {dg} · devono rigiocare {dr}"
                             + (f" (finora {tp(finora)})" if dr else ""))
    righe += ["", f"<i>Risultati provvisori, stimati sui tabellini live di ESPN con le regole del calcolo (bonus casa "
                  f"+{c['bonus']:g}, FADD, supplementari): li valuta e convalida un admin.\n"
                  f"Ultimo aggiornamento: {ora.astimezone(ROMA):%d/%m alle %H:%M}</i>"]
    if prova:
        righe.insert(0, "🧪 <b>PROVA</b> (non pubblicato sul canale)\n")
    return "\n".join(righe)


def a_media(c: dict, giocatori: list[dict]) -> int:
    """Quanti dei titolari indicati prendono la media (la loro squadra NBA non gioca nella giornata)."""
    return sum(1 for x in giocatori if x.get("atleta") and (c["punti"].get(x["atleta"]) or {}).get("come") == "media")


def stato_titolari(c: dict, giocatori: list[dict], partite: list[dict]) -> dict:
    """Per il tabellone: in campo adesso, da giocare (nessuna partita finita), da rigiocare (una finita e
    un'altra ancora) coi punti già fatti, a media; finito = nessuno ha più partite."""
    det = c.get("dettaglio") or {}
    notti_fp = det.get("notti") or {}
    campo = giocare = rigiocare = media = 0
    finora = 0.0
    for x in giocatori:
        a = x.get("atleta")
        p = (c["punti"].get(a) or {}) if a else {}
        if p.get("come") == "media":
            media += 1
            continue
        sq = p.get("squadra")
        if not a or not sq:
            continue
        sue = [q for q in partite if sq in (q["casa"], q["trasferta"])]
        if any(q["stato"] not in FINITE and q["stato"] not in NON_INIZIATE for q in sue):
            campo += 1
            continue
        if not any(q["stato"] not in FINITE for q in sue):
            continue
        finite = {q["data_et"] for q in sue if q["stato"] in FINITE}
        fatte = [float(fp or 0) for dd, fp in (notti_fp.get(a) or {}).items() if dd in finite]
        if fatte:
            rigiocare += 1
            finora += sum(fatte)
        else:
            giocare += 1
    return {"campo": campo, "giocare": giocare, "rigiocare": rigiocare, "media": media, "finora": tp(round(finora, 2)),
            "finito": campo + giocare + rigiocare == 0}


TEMPLATE = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "live.typ")


def _squadra_img(t: str) -> dict:
    import re
    from partita import _logo
    nome = config.nome(t)
    col = (config.squadra(t) or {}).get("colore_header") or ""
    return {"nome": nome, "iniziale": (nome[:1] or "?").upper(), "logo": _logo(t),
            "colore": col if re.fullmatch(r"#[0-9A-Fa-f]{6}", col) else "#5F01D1"}


def dati_immagine(c: dict, ora: datetime) -> dict:
    """Il JSON per live.typ: una scheda per partita (Luca, 23/10)."""
    g = c["giornata"]
    partite = db.partite_nba(g["dal"], g["al"])
    iniziate = [dd for dd, inizio, _f in notti(g) if inizio <= ora]
    out = []
    for k, r in enumerate(c["risultati"], 1):
        casa, tr = config.nome(r["casa"]), config.nome(r["trasferta"])
        lc, pc = _da_giocare(c, r["sc"]["titolari"])
        lt, pt = _da_giocare(c, r["st"]["titolari"])
        vuoti = [n for n, sq in ((casa, r["sc"]), (tr, r["st"])) if not any(x.get("atleta") for x in sq["titolari"])]
        avanti, nota = "", ""
        if vuoti:
            nota = "QUINTETTO VUOTO: " + ", ".join(vuoti).upper()
        elif lc + lt + pc + pt > MAX_DA_GIOCARE:
            nota = f"HANNO GIOCATO IN MENO DI {10 - MAX_DA_GIOCARE}"
        else:
            avanti = r["vince"]
            if r["supplementari"] and not r["sc"]["panchina"] and not r["st"]["panchina"]:
                nota = "PARI · SENZA PANCHINE NIENTE SUPPL."
            elif r["supplementari"]:
                nota = f"SI VA AI SUPPL. · {tp(r['esito']['casa'])} – {tp(r['esito']['trasferta'])}"
        lati = []
        for t, sq, punti in ((r["casa"], r["sc"], r["punti_casa"]), (r["trasferta"], r["st"], r["punti_trasferta"])):
            lati.append({**_squadra_img(t), **stato_titolari(c, sq["titolari"], partite), "punti": tp(punti)})
        out.append({"k": k, "casa": lati[0], "tras": lati[1], "avanti": avanti, "nota": nota})
    return {"n": g["numero"], "date": f"{g['dal']:%d/%m} – {g['al']:%d/%m}",
            "notte": f"del {max(iniziate):%d/%m}" if iniziate else "",
            "ora": f"{ora.astimezone(ROMA):%H:%M}", "partite": out, "soglia": 10 - MAX_DA_GIOCARE,
            "bonus": f"{c['bonus']:g}"}


_AVVISO_FONT = {"fatto": False}


def font_emoji() -> bool:
    """C'è il font delle emoji a colori (fonts-noto-color-emoji nel Dockerfile)? Senza, nel tabellone quadratini."""
    import glob
    return bool(glob.glob("/usr/share/fonts/**/NotoColorEmoji*.ttf", recursive=True))


def immagine(d: dict) -> bytes:
    import json
    import typst
    return typst.compile(TEMPLATE, root="/", format="png", ppi=170, sys_inputs={"dati": json.dumps(d, ensure_ascii=False)})


# tempi larghi per mandare la foto (circa mezzo MB): coi default di python-telegram-bot, a volte, timeout
TEMPI = {"read_timeout": 60, "write_timeout": 60, "connect_timeout": 30}
# errori di Telegram per cui la foto non si può mettere al posto del messaggio di prima: solo allora se ne fa uno nuovo
DA_RIFARE = ("there is no media", "message to edit not found", "message can't be edited", "message_id_invalid",
             "wrong type of the web page content")


def _messaggio_da_rifare(err) -> bool:
    t = str(err).lower()
    return "not modified" not in t and any(x in t for x in DA_RIFARE)


def didascalia(c: dict, ora: datetime) -> str:
    return (f"🔴 <b>Giornata {c['giornata']['numero']} · live</b> · aggiornato alle {ora.astimezone(ROMA):%H:%M}\n"
            f"<i>Provvisori, li convalida un admin. Il testo completo: /live_results nel bot</i>")


# ── pubblicazione ──────────────────────────────────────────────────────────────

async def aggiorna(bot, g: dict, d: date | None, ora: datetime, controllo: bool = False, scarica_fn=None) -> str:
    """Scarica, calcola e pubblica (o modifica) il messaggio della giornata. L'esito in breve."""
    s, n = g["stagione"], g["numero"]
    canale = config.globali().get("main_channel_id")
    if not canale:
        return "canale principale non configurato (main_channel_id)"
    esito_scarico = None
    if d is not None:
        esito_scarico = await (scarica_fn or scarica)(g, d, controllo)
    c = calcolo(s, n)
    if controllo and esito_scarico and esito_scarico.get("cambi"):
        riga = testo_cambi(n, d, esito_scarico["cambi"], c)
        if riga:
            from handlers import log
            await log(bot, riga)
    # sul canale un'immagine (live.typ) che si sostituisce a ogni aggiornamento (Luca, 23/10); il testo con /live_results
    import asyncio
    png = await asyncio.to_thread(immagine, dati_immagine(c, ora))
    if not _AVVISO_FONT["fatto"] and not font_emoji():      # una volta per avvio: il deploy non ha installato il font
        _AVVISO_FONT["fatto"] = True
        from handlers import log
        await log(bot, "⚠️ Live: manca il font delle emoji (fonts-noto-color-emoji), nel tabellone escono quadratini. "
                       "Ricostruire loucabot: docker compose up --build -d --force-recreate loucabot")
    cap = didascalia(c, ora)
    st = stato(s, n)
    nuovo = not (st and st.get("message_id"))
    if not nuovo:
        from telegram import InputMediaPhoto
        from telegram.error import NetworkError, TimedOut
        try:
            await bot.edit_message_media(chat_id=st["chat_id"], message_id=st["message_id"],
                                         media=InputMediaPhoto(png, caption=cap, parse_mode="HTML"), **TEMPI)
        except (TimedOut, NetworkError) as err:
            if "not modified" in str(err).lower():
                pass
            elif isinstance(err, TimedOut) or not _messaggio_da_rifare(err):
                # rete lenta o Telegram che non risponde: la foto può essere stata sostituita lo stesso, quindi
                # il messaggio NON si cancella; si salta il giro (v54: col timeout delle 2:15 del 26/10 cancellava
                # il live e ne mandava uno nuovo, rimasto orfano perché anche l'invio era andato in timeout)
                raise
            else:
                nuovo = True
        except Exception as err:
            if "not modified" not in str(err).lower():
                if not _messaggio_da_rifare(err):
                    raise
                nuovo = True
        if nuovo:
            # il messaggio di prima era di testo (live di prima della v53) o non c'è più: se ne manda uno nuovo
            logger.info("Live G%s: foto non sostituibile, ne mando una nuova", n)
            try:
                await bot.delete_message(chat_id=st["chat_id"], message_id=st["message_id"])
            except Exception:
                pass
    if nuovo:
        m = await bot.send_photo(chat_id=canale, photo=png, caption=cap, parse_mode="HTML", **TEMPI)
        _salva(s, n, chat_id=canale, message_id=m.message_id)
    _salva(s, n, aggiornato=ora, prossimo=None)
    return " · ".join(f"{config.nome(r['casa'])} {tp(r['punti_casa'])}–{tp(r['punti_trasferta'])} {config.nome(r['trasferta'])}"
                      for r in c["risultati"])


def _esiti(s: str, n: int) -> dict[str, dict]:
    """{casa: {vince, trasferta, punti}} dei risultati convalidati."""
    righe = db.q("""SELECT casa, trasferta, vince, punti_casa, punti_trasferta FROM lega_risultati
                    WHERE stagione = %s AND giornata = %s AND convalidato IS NOT NULL""", (s, n), many=True) or []
    return {r["casa"]: {"vince": r["vince"], "trasferta": r["trasferta"],
                        "punti": [float(r["punti_casa"] or 0), float(r["punti_trasferta"] or 0)]} for r in righe}


def testo_definitivo(s: str, g: dict, chi: str, quando: datetime, aggiornato: bool = False) -> str:
    """Il messaggio sul canale principale coi risultati convalidati (Luca, 23/10)."""
    from handlers import riga_partita
    righe = [f"🏁 <b>Giornata {g['numero']} · risultati definitivi</b> · notti {g['dal']:%d/%m}–{g['al']:%d/%m}", ""]
    for i, p in enumerate(db.partite_giornata(s, g["numero"])):
        if i:
            righe.append("")
        righe.append(riga_partita(s, g["numero"], p))
    righe += ["", f"<i>{'🔄 Aggiornati dopo il ricontrollo dei tabellini' if aggiornato else 'Convalidati'} da {e(chi)} "
                  f"il {quando.astimezone(ROMA):%d/%m alle %H:%M}. Dettagli: /giornata {g['numero']}</i>"]
    return "\n".join(righe)


async def pubblica_definitivo(bot, s: str, n: int, chi: str, quando: datetime | None = None) -> str:
    """Alla convalida: messaggio dei risultati definitivi sul canale principale (a una nuova convalida
    si modifica lo stesso) e il messaggio live cancellato; da lì il live non si aggiorna più.
    Restituisce una riga di esito."""
    quando = quando or datetime.now(timezone.utc)
    migra()                                              # colonne nuove anche se il bot non è ripartito
    canale = config.globali().get("main_channel_id")
    g = db.giornata(s, n)
    st = stato(s, n) or {}
    esito = []
    nuovi = _esiti(s, n)
    vecchi = st.get("esiti") or {}
    if isinstance(vecchi, str):
        import json
        vecchi = json.loads(vecchi)
    if canale and g:
        t = testo_definitivo(s, g, chi, quando, aggiornato=bool(st.get("definitivo_id")))
        fatto = False
        if st.get("definitivo_id"):
            try:
                await bot.edit_message_text(chat_id=canale, message_id=st["definitivo_id"], text=t, parse_mode="HTML")
                fatto = True
            except Exception as err:
                fatto = "not modified" in str(err).lower()
        if not fatto:
            m = await bot.send_message(chat_id=canale, text=t, parse_mode="HTML")
            _salva(s, n, definitivo_id=m.message_id)
        esito.append("risultati definitivi sul canale" + (" (aggiornati)" if fatto else ""))
        # nuova convalida: se cambia chi vince una partita, un messaggio in più (il resto solo modificato)
        cambiati = [(c, v, nuovi[c]) for c, v in vecchi.items() if c in nuovi and v.get("vince") != nuovi[c]["vince"]]
        if cambiati:
            righe = [f"⚠️ <b>Giornata {n}: cambia un risultato</b> dopo il ricontrollo dei tabellini ESPN", ""]
            for c, _v, nv in cambiati:
                vince = c if nv["vince"] == "casa" else nv["trasferta"]
                perde = nv["trasferta"] if nv["vince"] == "casa" else c
                righe.append(f"• Ora vince <b>{e(config.nome(vince))}</b> su {e(config.nome(perde))} "
                             f"({tp(nv['punti'][0])} – {tp(nv['punti'][1])})")
            righe += ["", "<i>Il messaggio dei risultati definitivi qui sopra è aggiornato.</i>"]
            try:
                await bot.send_message(chat_id=canale, text="\n".join(righe), parse_mode="HTML",
                                       reply_to_message_id=st.get("definitivo_id") or None)
            except Exception as err:
                logger.warning("Avviso esito cambiato G%s: %s", n, err)
            esito.append(f"{len(cambiati)} esiti cambiati: avviso sul canale")
    if st.get("message_id") and not st.get("chiuso"):
        try:
            await bot.delete_message(chat_id=st["chat_id"], message_id=st["message_id"])
            esito.append("live cancellato")
        except Exception as err:                         # più vecchio di 48 ore: Telegram non lo cancella
            logger.info("Live G%s: non cancellato (%s)", n, err)
            esito.append("live non cancellabile (più di 48 ore): cancellalo a mano")
    import json
    _salva(s, n, chiuso=quando, esiti=json.dumps(nuovi))
    return ", ".join(esito) or "niente da pubblicare (manca main_channel_id)"


async def tick(bot, ora: datetime | None = None, scarica_fn=None) -> list[str]:
    """Un giro del job: per ogni giornata attiva l'aggiornamento che serve adesso."""
    from handlers import log
    ora = ora or datetime.now(timezone.utc)
    s = config.stagione()
    fatti = []
    for g in giornate_attive(s, ora):
        g = {**g, "stagione": s}
        st = stato(s, g["numero"])
        if st and st.get("chiuso"):                        # giornata convalidata: il live non c'è più
            continue
        quale, d = cosa_fare(g, ora, st)
        if not quale:
            continue
        try:
            fatti.append(await aggiorna(bot, g, d, ora, controllo=quale == "controllo", scarica_fn=scarica_fn))
            if quale == "controllo" or not st or not st.get("message_id"):
                await log(bot, f"🔴 Live G{g['numero']}: " + ("pubblicato sul canale" if quale == "live" else
                                                              "aggiornamento delle 10 dopo il controllo dei tabellini"))
        except Exception as err:
            logger.warning("Live G%s: %s", g["numero"], err)
            _salva(s, g["numero"], prossimo=ora + DOPO_ERRORE)
            if not st or not st.get("errore_log") or ora - st["errore_log"] >= timedelta(hours=1):
                _salva(s, g["numero"], errore_log=ora)
                await log(bot, f"⚠️ Live G{g['numero']}: aggiornamento saltato ({e(str(err))[:200]}), "
                               f"riprovo fra {int(DOPO_ERRORE.total_seconds() // 60)} minuti")
    return fatti


async def job_live(context):
    try:
        await tick(context.bot)
    except Exception as err:
        logger.exception("job_live: %s", err)


# ── /live_results ──────────────────────────────────────────────────────────────

def _pezzi(t: str, limite: int = LIMITE) -> list[str]:
    """Il testo in più messaggi, tagliando tra una partita e l'altra (riga vuota)."""
    out, cur = [], ""
    for blocco in t.split("\n\n"):
        if cur and len(cur) + 2 + len(blocco) > limite:
            out.append(cur)
            cur = blocco
        else:
            cur = f"{cur}\n\n{blocco}" if cur else blocco
    if cur:
        out.append(cur)
    return [x[:4096] for x in out]


def giornata_live(s: str, n: int | None = None) -> dict | None:
    """La giornata del live: quella chiesta, o quella col live aperto più recente, o la giornata in corso."""
    if n:
        return db.giornata(s, n)
    r = db.q("SELECT giornata FROM lega_live WHERE stagione = %s AND message_id IS NOT NULL AND chiuso IS NULL "
             "ORDER BY giornata DESC LIMIT 1", (s,), one=True)
    if r:
        return db.giornata(s, r["giornata"])
    import calendario
    return calendario.da_mostrare(s)


async def cmd_live_results(update, context):
    """/live_results [N]: il testo completo del live (anche lungo, in più messaggi), dai tabellini già scaricati."""
    import asyncio
    msg = update.effective_message
    s = config.stagione()
    n = next((int(x.lstrip("Gg")) for x in (context.args or []) if x.lstrip("Gg").isdigit()), None)
    g = giornata_live(s, n)
    if not g:
        await msg.reply_text("Nessuna giornata da mostrare." if not n else f"La giornata {n} non c'è.")
        return
    st = stato(s, g["numero"]) or {}
    if st.get("chiuso"):
        await msg.reply_text(f"La giornata {g['numero']} è già convalidata: i risultati definitivi con /giornata {g['numero']}.")
        return
    if g["dal"] > datetime.now(nba.ET).date() and not st.get("message_id"):
        await msg.reply_text(f"La giornata {g['numero']} non è ancora iniziata.")
        return
    c = await asyncio.to_thread(calcolo, s, g["numero"])
    ora = st.get("aggiornato") or datetime.now(timezone.utc)
    for pezzo in _pezzi(testo(c, ora)):
        await msg.reply_text(pezzo, parse_mode="HTML")

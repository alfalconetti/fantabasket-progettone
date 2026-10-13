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
FINE_NOTTE = time(8, 0)               # fine degli aggiornamenti della notte (mattino dopo, Roma)
ORA_CONTROLLO = time(10, 5)           # dopo il controllo dei tabellini delle 10 (handlers_risultati.job_controllo)
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
    """Giornate iniziate e non finite da più di un giorno (dove può servire un aggiornamento)."""
    oggi = ora.astimezone(ZoneInfo("America/New_York")).date()
    return [g for g in db.giornate(s)
            if g.get("prima_partita") and g["prima_partita"] <= ora and g["al"] >= oggi - timedelta(days=2)]


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


def esito_live(r: dict, casa: str, tr: str, aperti: bool) -> str:
    """Finché qualcuno (titolari o panchina) deve ancora giocare: chi è avanti e di quanto, bonus
    casa compreso. Quando tutti hanno finito: l'esito del calcolo, supplementari compresi."""
    if aperti:
        scarto = r["punti_casa"] - r["punti_trasferta"]
        if scarto == 0:
            return "pari"
        return f"{e(casa if scarto > 0 else tr)} avanti di {tp(abs(scarto))}"
    chi = e(casa if r["vince"] == "casa" else tr)
    if r["supplementari"] and not r["sc"]["panchina"] and not r["st"]["panchina"]:
        return f"{chi} vince (nessuna delle due ha la panchina: niente supplementari)"
    if r["supplementari"]:
        return f"{chi} vince ai supplementari ({r['supplementari']}): {tp(r['esito']['casa'])} – {tp(r['esito']['trasferta'])}"
    return f"{chi} vince"


def testo(c: dict, ora: datetime, prova: bool = False) -> str:
    g = c["giornata"]
    righe = [f"🔴 <b>Giornata {g['numero']} · punteggi live</b>", ""]
    for r in c["risultati"]:
        casa, tr = config.nome(r["casa"]), config.nome(r["trasferta"])
        righe.append(f"<b>{e(casa)}</b> {tp(r['punti_casa'])} – {tp(r['punti_trasferta'])} <b>{e(tr)}</b>")
        lc, pc = _da_giocare(c, r["sc"]["titolari"])
        lt, pt = _da_giocare(c, r["st"]["titolari"])
        bc = sum(_da_giocare(c, r["sc"]["panchina"]))
        bt = sum(_da_giocare(c, r["st"]["panchina"]))
        aperti = bool(lc or lt or pc or pt or bc or bt)
        stato_g = []
        if lc or lt:
            stato_g.append(f"🏀 in campo {lc}–{lt}")
        if pc or pt:
            stato_g.append(f"⏳ da giocare {pc}–{pt}")
        righe.append(f"   ▶ {esito_live(r, casa, tr, aperti)}" + (" · " + " · ".join(stato_g) if stato_g else ""))
    righe += ["", f"<i>Risultati provvisori, stimati sui tabellini live di ESPN con le regole del calcolo (bonus casa "
                  f"+{c['bonus']:g}, FADD, supplementari): li valuta e convalida un admin.\n"
                  f"Ultimo aggiornamento: {ora.astimezone(ROMA):%d/%m alle %H:%M}</i>"]
    if prova:
        righe.insert(0, "🧪 <b>PROVA</b> (non pubblicato sul canale)\n")
        righe += avvisi_brevi(c)
    return "\n".join(righe)


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
    t = testo(c, ora)
    st = stato(s, n)
    if st and st.get("message_id"):
        try:
            await bot.edit_message_text(chat_id=st["chat_id"], message_id=st["message_id"], text=t, parse_mode="HTML")
        except Exception as err:
            if "not modified" not in str(err).lower():
                raise
    else:
        m = await bot.send_message(chat_id=canale, text=t, parse_mode="HTML")
        _salva(s, n, chat_id=canale, message_id=m.message_id)
    _salva(s, n, aggiornato=ora, prossimo=None)
    return " · ".join(f"{config.nome(r['casa'])} {tp(r['punti_casa'])}–{tp(r['punti_trasferta'])} {config.nome(r['trasferta'])}"
                      for r in c["risultati"])


async def tick(bot, ora: datetime | None = None, scarica_fn=None) -> list[str]:
    """Un giro del job: per ogni giornata attiva l'aggiornamento che serve adesso."""
    from handlers import log
    ora = ora or datetime.now(timezone.utc)
    s = config.stagione()
    fatti = []
    for g in giornate_attive(s, ora):
        g = {**g, "stagione": s}
        st = stato(s, g["numero"])
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

"""
/partita (Luca, 21 e 23/10): una sfida del fantabasket come immagine (Typst, partita.typ), in verticale:
tabellone in alto (loghi, punteggio, supplementari, stato), poi le due squadre una sotto l'altra con
quintetto e panchina, una colonna per ogni notte della giornata (la data in testa) e la colonna
«Conta», cioè quello che il giocatore porta davvero alla squadra (la media delle sue partite nella
giornata, la media della stagione se la sua squadra NBA non gioca, 0, o niente se è uscito per la
FADD). In fondo le spiegazioni: FADD, giocatori a media, supplementari, avvisi del calcolo.

Celle delle notti: i fantapunti se ha giocato, DNP se la sua squadra ha giocato ma lui no, «vs XXX» o
«@XXX» se deve ancora giocare quella notte (in futuro o in corso), vuota se la sua squadra non gioca.

Argomenti: niente (la propria squadra, la giornata in corso: la stessa fino alla convalida, poi la
successiva), SQUADRA [GN], SQUADRA SQUADRA (le loro sfide della stagione: se più d'una si sceglie coi
bottoni). Squadre per nome, id o GM.
"""
import html
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import config
import db
import risultati as R
from numeri import testo as tp

logger = logging.getLogger(__name__)
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "partita.typ")
LOGHI = os.path.join(os.path.dirname(os.environ.get("TEAMS_PATH", "/config/teams.json")), "loghi")
RUOLI = ["PG", "SG", "SF", "PF", "C"]
FINITA, SALTATE = "STATUS_FINAL", ("STATUS_POSTPONED", "STATUS_CANCELED")
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _logo(team_id: str) -> str:
    for ext in ("png", "jpg", "jpeg"):
        p = os.path.join(LOGHI, f"{team_id}_logo.{ext}")
        if os.path.exists(p):
            return p
    return ""


def _stato_calcolo(s: str, n: int) -> str | None:
    r = db.q("SELECT stato FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (s, n), one=True)
    return r["stato"] if r else None


# ── quale giornata, quali squadre ─────────────────────────────────────────────

def giornata_di_default(s: str, ora: datetime | None = None) -> dict | None:
    """La giornata da mostrare senza numero: in calendario.da_mostrare (v52, la stessa per /giornata e /risultati)."""
    import calendario
    return calendario.da_mostrare(s, ora)


def sfide(s: str, a: str, b: str | None = None) -> list[dict]:
    """Le partite del calendario di a (con b, se c'è): [{giornata, casa, trasferta}] in ordine."""
    out = []
    for g in db.giornate(s):
        p = db.partita_squadra(s, g["numero"], a)
        if p and (not b or b in (p["casa"], p["trasferta"])):
            out.append({"giornata": g["numero"], "casa": p["casa"], "trasferta": p["trasferta"]})
    return out


def leggi_argomenti(args: list[str], squadre: list[dict]) -> tuple[list[dict], int | None, str | None]:
    """(squadre trovate, giornata, errore). La giornata: «G5» o «5». Due squadre separate da «-»,
    «vs», «,» oppure, se no, provando a dividere le parole in due nomi."""
    from shared.squadre import cerca_squadra
    import re
    n = None
    resto = []
    for a in args:
        m = re.fullmatch(r"[Gg]?(\d{1,2})", a.strip())
        if m and n is None:
            n = int(m.group(1))
        else:
            resto.append(a)
    testo = " ".join(resto).strip()
    if not testo:
        return [], n, None
    pezzi = [p.strip() for p in re.split(r"\s+(?:-|–|vs\.?|contro)\s+|,", testo, flags=re.I) if p.strip()]
    if len(pezzi) == 2:
        tt = [cerca_squadra(p, squadre) for p in pezzi]
        return ([t for t in tt if t], n, None) if all(tt) else ([], n, f"Squadra non trovata: «{pezzi[tt.index(None)]}»")
    intera = cerca_squadra(testo, squadre)
    parole = testo.split()
    # due nomi attaccati («Alfa Beta»): una divisione in cui entrambe le metà sono squadre (nome esatto o inizio)
    from shared.squadre import campi_ricerca, normalizza, per_parole
    def esatta(q):
        qn = normalizza(q)
        return next((t for t in squadre if t["id"] == q or any(normalizza(c).startswith(qn) for c in campi_ricerca(t))),
                    None) or per_parole(q, squadre)
    for i in range(1, len(parole)):
        x, y = esatta(" ".join(parole[:i])), esatta(" ".join(parole[i:]))
        if x and y and x["id"] != y["id"] and not (intera and normalizza(intera.get("nome", "")) == normalizza(testo)):
            return [x, y], n, None
    return ([intera] if intera else []), n, (None if intera else f"Squadra non trovata: «{testo}»")


# ── dati per l'immagine ────────────────────────────────────────────────────────

def _cella(x: dict | None, a: str | None, sq: str | None, d, partite_giorno: dict, tab: dict) -> dict:
    """La casella della notte d: {t: testo, k: tipo} (k: fp, live, dnp, prossima, rinviata, vuota)."""
    p = partite_giorno.get((sq, d)) if sq else None
    if not p:
        return {"t": "", "k": "vuota"}
    vs = ("vs " if p["casa"] == sq else "@") + (p["trasferta"] if p["casa"] == sq else p["casa"])
    r = tab.get((a, d)) if a else None
    if p["stato"] in SALTATE:
        return {"t": "rinv.", "k": "rinviata"}
    if p["stato"] == FINITA:
        if r and r.get("giocato") and not (float(r["fp"] or 0) == 0 and not r.get("minuti")):
            return {"t": tp(r["fp"]), "k": "fp"}
        return {"t": "DNP", "k": "dnp"}
    if p["stato"] == "STATUS_SCHEDULED":
        return {"t": vs, "k": "prossima"}
    if r and r.get("giocato"):                                    # in corso, tabellino parziale
        return {"t": tp(r["fp"]), "k": "live"}
    return {"t": vs, "k": "live"}


def dati(s: str, n: int, casa: str, trasferta: str, ora: datetime | None = None) -> dict:
    import foto
    import live
    ora = ora or datetime.now(timezone.utc)
    g = db.giornata(s, n)
    c = live.calcolo(s, n)
    r = next((x for x in c["risultati"] if x["casa"] == casa and x["trasferta"] == trasferta), None)
    if not r:
        raise ValueError(f"nella giornata {n} non c'è {config.nome(casa)} – {config.nome(trasferta)}")
    giorni = [g["dal"] + timedelta(days=i) for i in range((g["al"] - g["dal"]).days + 1)]
    atleti = [x["atleta"] for t in (casa, trasferta) for x in c["squadre"][t]["quintetto"] + c["squadre"][t]["panchina"] if x.get("atleta")]
    tab = {}
    for row in db.tabellini_atleti(atleti, g["dal"], g["al"]):
        tab[(row["atleta"], row["data_et"])] = row
    partite_giorno = {}
    for p in db.partite_nba(g["dal"], g["al"]):
        for sq in (p["casa"], p["trasferta"]):
            partite_giorno[(sq, p["data_et"])] = p
    stato_c = _stato_calcolo(s, n)
    # giornata convalidata: in testa il risultato salvato (quello ufficiale); se il ricalcolo di oggi
    # desse altro (tabellini corretti dopo, decisioni cambiate) lo si dice nelle note
    salvato = db.q("SELECT * FROM lega_risultati WHERE stagione = %s AND giornata = %s AND casa = %s AND convalidato IS NOT NULL",
                   (s, n, casa), one=True) if stato_c == "convalidata" else None
    iniziata = bool(g.get("prima_partita") and g["prima_partita"] <= ora)
    stato = ("convalidata" if stato_c == "convalidata" else "calcolata" if stato_c else
             "in corso" if iniziata else "da giocare")
    es = r["esito"]
    note: list[str] = []
    squadre_out = []
    supp = r["supplementari"]
    for t, sq_calc, lato in ((casa, r["sc"], "casa"), (trasferta, r["st"], "trasferta")):
        orig = c["squadre"][t]
        fadd = sq_calc.get("fadd")
        esce = fadd["esce"].get("atleta") if fadd else None
        entra = fadd["entra"].get("atleta") if fadd else None
        in_supp = [b.get("atleta") for b in sq_calc["panchina"][:supp]]
        tit_atleti = {y.get("atleta") for y in orig["quintetto"] if y.get("atleta")}
        righe = []
        for i, x in enumerate(orig["quintetto"] + orig["panchina"]):
            tit = i < len(orig["quintetto"])
            a = x.get("atleta")
            p = c["punti"].get(a) or {}
            sq_nba = p.get("squadra")
            celle = [_cella(x, a, sq_nba, d, partite_giorno, tab) for d in giorni]
            conta, tag = "", ""
            if not x.get("gid"):
                conta, tag = ("0" if tit else ""), ("vuoto" if tit else "")
            elif tit and a and a == esce:
                conta, tag = "—", "esce"
            elif tit:
                conta = tp(p.get("fp", 0.0)) if stato != "da giocare" else ""
                tag = "media" if p.get("come") == "media" else ""
            elif a and a == entra:
                conta, tag = tp(p.get("fp", 0.0)), "entra"
            elif x.get("ceduto"):
                tag = "ceduto"
            elif a and a in tit_atleti:                   # titolare anche in panchina: lì vale 0 (Luca, 23/10)
                conta, tag = "0", "doppio"
            elif a and a in in_supp:
                conta, tag = tp(p.get("fp", 0.0)), f"S{in_supp.index(a) + 1}"
            if p.get("come") == "media" and (tit or tag in ("entra",) or tag.startswith("S")):
                note.append(f"{x.get('nome')}: {p.get('nota') or 'prende la media'}")
            m = (c.get("dettaglio") or {}).get("medie", {}).get(a) if a else None
            righe.append({"posto": (x.get("ruolo") or "") if tit else str(i - len(orig["quintetto"]) + 1),
                          # in panchina il ruolo (quello della giornata: congelato alla scadenza) tra parentesi
                          "ruolo": "" if tit else (x.get("ruolo") or ""),
                          "titolare": tit, "nome": x.get("nome") or "—", "nba": sq_nba or "", "celle": celle,
                          "media": tp(m) if m is not None else ("0,00" if a else ""),
                          "conta": conta, "tag": tag, "foto": (foto.percorso(a) or "") if a else ""})
        if fadd:
            note.append(f"FADD {config.nome(t)}: esce {fadd['esce'].get('nome')} ({fadd.get('motivo')}), "
                        f"entra {fadd['entra'].get('nome')} dalla panchina, stesso ruolo")
        tot = sq_calc["totale"]
        bonus = c["bonus"] if lato == "casa" else 0
        squadre_out.append({
            "id": t, "nome": config.nome(t), "gm": (config.squadra(t) or {}).get("gm_nome", ""), "logo": _logo(t),
            "lato": lato, "totale": tp(tot), "bonus": tp(bonus) if bonus else "",
            "punti": tp(salvato["punti_casa" if lato == "casa" else "punti_trasferta"]) if salvato else
                     tp(es["regolamentari"][0 if lato == "casa" else 1]),
            "supp": (tp(salvato["supp_casa" if lato == "casa" else "supp_trasferta"]) if salvato and salvato["supp_casa"] is not None
                     else "" if salvato else
                     tp(es["punti_supplementari"][0 if lato == "casa" else 1]) if es.get("punti_supplementari") else ""),
            "vince": (salvato["vince"] if salvato else r["vince"]) == lato, "righe": righe,
            "tribuna": tribuna(t, g, ora, iniziata, {x.get("gid") for x in orig["quintetto"] + orig["panchina"] if x.get("gid")},
                               giorni, partite_giorno),
            "panchina_mandata": orig["panchina"] != [] or bool(sq_calc["panchina"])})
    if salvato and (abs(float(salvato["punti_casa"] or 0) - es["regolamentari"][0]) > 0.001
                    or abs(float(salvato["punti_trasferta"] or 0) - es["regolamentari"][1]) > 0.001 or salvato["vince"] != r["vince"]):
        note.insert(0, f"In testa il risultato convalidato. Ricalcolando oggi verrebbe {tp(es['regolamentari'][0])} – "
                       f"{tp(es['regolamentari'][1])} (tabellini o decisioni cambiati dopo la convalida): la tabella è quella di oggi")
    if supp == 0 and salvato and salvato["supp_casa"] is not None:
        supp = 1
    media_nba = g.get("media") if g.get("media") is not None else (g.get("media_file") or [])
    if supp:
        note.append(f"Supplementari: scarto sotto {tp(__import__('shared.regole', fromlist=['x']).scarto_minimo())} punti, "
                    f"{supp} {'giro' if supp == 1 else 'giri'} di panchinari in ordine (S1, S2…)")
    nomi = {config.nome(casa), config.nome(trasferta)}
    note += [a for a in c["avvisi"] if a.split(": ")[0] in nomi and "FADD" not in a]
    return {
        "titolo": f"Giornata {n}", "date": f"{g['dal']:%d/%m} – {g['al']:%d/%m}", "stato": stato,
        "notti": [f"{GIORNI[d.weekday()]} {d:%d/%m}" for d in giorni],
        "squadre": squadre_out, "supplementari": supp, "bonus": tp(c["bonus"]),
        "media_nba": ", ".join(media_nba) if media_nba else "",
        "note": list(dict.fromkeys(note)),
        "aggiornato": f"{ora.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Rome')):%d/%m alle %H:%M}",
        "dati_alle": dati_alle(s, n, g, ora) if stato != "da giocare" else "",
    }


def rosa_al(team_id: str, quando) -> list[int]:
    """I giocatori della squadra in quel momento, dal registro dei movimenti (come shared/rosa)."""
    righe = db.q("""SELECT DISTINCT ON (giocatore_id) giocatore_id, team_id_a FROM movimenti_giocatori
                    WHERE timestamp <= %s AND oggetto = 'giocatore'
                    ORDER BY giocatore_id, timestamp DESC, id DESC""", (quando,), many=True) or []
    return [x["giocatore_id"] for x in righe if x["team_id_a"] == team_id]


def tribuna(team_id: str, g: dict, ora: datetime, iniziata: bool, schierati: set, giorni: list, partite_giorno: dict) -> list[dict]:
    """La tribuna di /partita (Luca, 02/11): i giocatori a roster né in quintetto né in panchina, col loro punteggio
    della giornata. A roster alla scadenza (prima partita della giornata; prima, adesso): chi è ceduto dopo resta
    nella tribuna della squadra vecchia fino a fine giornata, come per tutto il resto. Per ognuno `t`:
    - la media delle partite in cui è entrato, e tra parentesi le singole se sono più d'una («25,00 (20,00 · 30,00)»);
    - «vs XXX» / «@XXX» se non ha ancora giocato e la sua squadra deve giocare;
    - «DNP» se la squadra ha giocato e lui no; «—» se la sua squadra NBA non gioca nella giornata;
    - «NA» se non ha una squadra NBA (o non è abbinato a ESPN).
    In ordine: punteggi dal più alto, poi chi deve giocare, poi DNP, «—», NA."""
    try:
        quando = g["prima_partita"] if iniziata and g.get("prima_partita") else ora
        gids = [x for x in rosa_al(team_id, quando) if x not in schierati]
    except Exception as err:                       # registro dei movimenti non leggibile: niente tribuna
        logger.warning("Tribuna %s: %s", team_id, err)
        return []
    if not gids:
        return []
    info = {x["id"]: x for x in db.q("""SELECT g.id, g.nome_common, g.espn_id, a.squadra FROM giocatori g
                                         LEFT JOIN nba_atleti a ON a.atleta = g.espn_id WHERE g.id = ANY(%s)""",
                                      (gids,), many=True) or []}
    atleti = [x["espn_id"] for x in info.values() if x.get("espn_id")]
    tab = {}
    for row in db.tabellini_atleti(atleti, g["dal"], g["al"]) if atleti else []:
        tab.setdefault(row["atleta"], []).append(row)
    out = []
    for gid in gids:
        x = info.get(gid) or {}
        a = x.get("espn_id")
        righe = tab.get(a, []) if a else []
        sq = (righe[-1]["squadra"] if righe else None) or x.get("squadra")
        nome = x.get("nome_common") or "—"
        if not a or not sq:
            out.append({"nome": nome, "t": "NA", "k": "na", "o": (4, 0)})
            continue
        fp = [float(rr["fp"]) for rr in righe if rr.get("giocato") and not (float(rr["fp"] or 0) == 0 and not rr.get("minuti"))]
        sue = [partite_giorno[(sq, d)] for d in giorni if (sq, d) in partite_giorno]
        if fp:
            m = sum(fp) / len(fp)
            t = tp(m) + (f" ({' · '.join(tp(v) for v in fp)})" if len(fp) > 1 else "")
            out.append({"nome": nome, "t": t, "k": "fp", "o": (0, -m)})
            continue
        if not sue:
            out.append({"nome": nome, "t": "—", "k": "vuota", "o": (3, 0)})
            continue
        prossime = [p for p in sue if p["stato"] not in (FINITA,) + SALTATE]
        if prossime:
            p = prossime[0]
            vs = ("vs " if p["casa"] == sq else "@") + (p["trasferta"] if p["casa"] == sq else p["casa"])
            out.append({"nome": nome, "t": vs, "k": "prossima", "o": (1, p["inizio"].timestamp() if p.get("inizio") else 0)})
            continue
        out.append({"nome": nome, "t": "DNP", "k": "dnp", "o": (2, 0)})
    out.sort(key=lambda z: (z["o"], z["nome"]))
    return [{k: v for k, v in z.items() if k != "o"} for z in out]


def ultimo_aggiornamento(s: str, n: int, g: dict) -> datetime | None:
    """Quando sono stati scaricati gli ultimi tabellini della giornata: l'ultimo giro del live (lega_live.aggiornato)
    o l'ultimo tabellino definitivo delle sue partite NBA (nba_partite.tabellino), il più recente (Luca, 01/11)."""
    live = db.q("SELECT aggiornato FROM lega_live WHERE stagione = %s AND giornata = %s", (s, n), one=True) or {}
    tab = db.q("SELECT MAX(tabellino) AS t FROM nba_partite WHERE data_et BETWEEN %s AND %s", (g["dal"], g["al"]), one=True) or {}
    tempi = [x for x in (live.get("aggiornato"), tab.get("t")) if x]
    return max(tempi) if tempi else None


def dati_alle(s: str, n: int, g: dict, ora: datetime) -> str:
    """«dati aggiornati alle 01:35» (oggi) o «… il 31/10 alle 08:30»; vuoto se non c'è ancora niente."""
    from zoneinfo import ZoneInfo
    t = ultimo_aggiornamento(s, n, g)
    if not t:
        return ""
    roma = ZoneInfo("Europe/Rome")
    t, oggi = t.astimezone(roma), ora.astimezone(roma).date()
    return f"dati aggiornati alle {t:%H:%M}" if t.date() == oggi else f"dati aggiornati il {t:%d/%m} alle {t:%H:%M}"


def immagine(d: dict) -> bytes:
    import typst
    return typst.compile(TEMPLATE, root="/", format="png", ppi=170,
                         sys_inputs={"dati": json.dumps(d, ensure_ascii=False)})


# ── comando ────────────────────────────────────────────────────────────────────

async def _manda(msg, s: str, n: int, casa: str, trasferta: str):
    import asyncio
    d = await asyncio.to_thread(dati, s, n, casa, trasferta)
    png = await asyncio.to_thread(immagine, d)
    sq = d["squadre"]
    did = f"{e(sq[0]['nome'])} {sq[0]['punti']} – {sq[1]['punti']} {e(sq[1]['nome'])}"
    await msg.reply_photo(png, caption=f"🏀 Giornata {n} · {did} · {d['stato']}", parse_mode="HTML")


async def cmd_partita(update, context):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
    msg = update.effective_message
    s = config.stagione()
    sq, n, err = leggi_argomenti(list(context.args or []), config.squadre())
    if err:
        await msg.reply_text(f"❌ {err}\nUso: /partita [SQUADRA] [GN] oppure /partita SQUADRA SQUADRA "
                             "(es. /partita Alfa G3, /partita Alfa - Beta)")
        return
    if not sq:
        mia = config.squadra_del_gm(update.effective_user.id)
        if not mia:
            await msg.reply_text("Uso: /partita SQUADRA [GN] oppure /partita SQUADRA SQUADRA (es. /partita Alfa G3).")
            return
        sq = [mia]
    if len(sq) == 2:
        lista = sfide(s, sq[0]["id"], sq[1]["id"])
        if n:
            lista = [x for x in lista if x["giornata"] == n]
        if not lista:
            await msg.reply_text(f"{e(sq[0]['nome'])} e {e(sq[1]['nome'])} non si affrontano"
                                 + (f" nella giornata {n}." if n else " in questa stagione."), parse_mode="HTML")
            return
        if len(lista) > 1:
            kb = [[B(f"G{x['giornata']}: {config.nome(x['casa'])} – {config.nome(x['trasferta'])}",
                     callback_data=f"pt:{x['giornata']}:{x['casa']}:{x['trasferta']}")] for x in lista]
            await msg.reply_text("Quale partita?", reply_markup=K(kb))
            return
        x = lista[0]
    else:
        g = db.giornata(s, n) if n else giornata_di_default(s)
        if not g:
            await msg.reply_text("Nessuna giornata in calendario." if not n else f"Giornata {n} non trovata.")
            return
        p = db.partita_squadra(s, g["numero"], sq[0]["id"])
        if not p:
            await msg.reply_text(f"{e(sq[0]['nome'])} non gioca nella giornata {g['numero']}.", parse_mode="HTML")
            return
        x = {"giornata": g["numero"], "casa": p["casa"], "trasferta": p["trasferta"]}
    try:
        await _manda(msg, s, x["giornata"], x["casa"], x["trasferta"])
    except Exception as err:
        logger.warning("/partita: %s", err)
        await msg.reply_text(f"❌ Non riesco a preparare la partita: {e(str(err))[:200]}", parse_mode="HTML")


async def cb_partita(update, context):
    q = update.callback_query
    _, n, casa, tr = q.data.split(":")
    await q.answer()
    try:
        await q.edit_message_text(f"⏳ Giornata {n}: {config.nome(casa)} – {config.nome(tr)}…")
        await _manda(q.message, config.stagione(), int(n), casa, tr)
    except Exception as err:
        logger.warning("/partita: %s", err)
        await q.message.reply_text(f"❌ Non riesco a preparare la partita: {e(str(err))[:200]}")


def get_handlers() -> list:
    from telegram.ext import CallbackQueryHandler, CommandHandler
    return [CommandHandler("partita", cmd_partita), CallbackQueryHandler(cb_partita, pattern=r"^pt:\d+:")]

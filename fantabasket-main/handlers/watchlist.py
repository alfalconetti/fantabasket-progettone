"""
Watchlist (v7.8.0, Luca 13–14/11): ogni GM segue dei giocatori e riceve in privato quello che li riguarda.
Privata (nessuno sa chi segue chi), nessun limite. Dati in shared/watchlist.py.

Comandi, solo in privato e solo per i GM: /watch NOME, /unwatch NOME, /watchlist (la grafica di /giocatori),
/watch_soglia (la grande prestazione: default media +15 o 50 fantapunti). Sotto /player, in privato, «👁 Segui».
Se il giocatore non gioca in NBA da più di una stagione /watch lo dice (come all'apertura delle aste).

Avvisi subito (job ogni 5 minuti, `job_avvisi`): asta aperta (registro del bot aste), movimenti (vista
movimenti_giocatori: firma, trade, taglio, 10-day…), injury report solo le cose serie (Out, Doubtful, sospeso, e
quando ne esce), grande prestazione (partite finite). Valgono solo per quello che succede dopo l'aggiunta
(watchlist.da), e ognuno arriva una volta (watch_avvisi). Report alle 9:30 (orari.watch_report, `job_report`):
un'immagine con la notte dei giocatori seguiti (shared/watchlist.typ), solo se qualcuno ha giocato.
"""
import asyncio
import html
import io
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.ext import CallbackQueryHandler, CommandHandler, filters

from shared import giocatore as G
from shared import lettura as L
from shared import watchlist as W

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
ET = ZoneInfo("America/New_York")
TIPI = (2, 5)                                    # regular season e play-in, come /player
GRAVI = {"Out": "Out", "Doubtful": "Doubtful", "Suspension": "sospeso"}
APERTURE = ("asta FA aperta", "asta FA aperta per conto della squadra", "asta RFA aperta", "asta RFA aperta a mano",
            "asta riaperta")
MOVIMENTI = {"signed": "firmato da {a}", "firma": "firmato da {a}", "rookie_firma": "firmato da {a} (rookie)",
             "10day_firma": "10-day con {a}", "traded": "scambiato: da {da} a {a}", "trade": "scambiato: da {da} a {a}",
             "cut": "tagliato da {da}, ora è FA", "taglio": "tagliato da {da}, ora è FA",
             "10day_scadenza": "finito il 10-day con {da}, ora è FA", "expired": "contratto finito con {da}, ora è FA",
             "decaduto": "decaduto da {da}, ora è FA", "renewed": "rinnovato da {a}"}

e = lambda x: html.escape(str(x), quote=False)


# ── comandi ─────────────────────────────────────────────────────────────────────

def _gm(update) -> bool:
    import settings
    uid = update.effective_user.id
    return bool(L.squadra_del_gm(uid)) or settings.is_admin(uid)


def non_gioca(gid: int) -> str:
    """L'avviso di /watch per chi non gioca in NBA da più di una stagione (stessa regola dell'apertura delle aste:
    nessuna riga di Basketball-Reference nella stagione in corso né in quella prima)."""
    s = int(L.stagione())
    try:
        r = L.q("""SELECT MAX(b.stagione) AS u FROM giocatori g JOIN bref_stats b ON lower(b.nome_bref) = lower(g.nome_bref)
                   WHERE g.id = %s""", (gid,), one=True)
    except Exception:
        return ""
    u = (r or {}).get("u")
    if u and int(u) >= s:                     # bref «2026» = 2025-26: ha giocato la stagione scorsa o questa
        return ""
    if not u:
        return "\n⚠️ Non risulta aver mai giocato in NBA (nessuna stagione su Basketball-Reference)."
    y = int(u) - 1
    return f"\n⚠️ Non gioca in NBA dal {y}-{str(y + 1)[-2:]}."


def _testo_aggiunto(gid: int, nuovo: bool) -> str:
    nome = (L.q("SELECT nome_common FROM giocatori WHERE id = %s", (gid,), one=True) or {}).get("nome_common", "?")
    if not nuovo:
        return f"👁 Segui già <b>{e(nome)}</b>."
    return (f"👁 Ora segui <b>{e(nome)}</b>: ti avviso di aste, movimenti, infortuni seri e grandi partite, "
            f"e alle 9:30 c'è il report della notte." + non_gioca(gid))


async def cmd_watch(update, context):
    msg = update.effective_message
    if not _gm(update):
        await msg.reply_text("La watchlist è per i GM della lega.")
        return
    testo = " ".join(context.args or [])
    if not testo:
        await msg.reply_text("Uso: /watch NOME (es. /watch Jalen Duren). La tua lista: /watchlist")
        return
    trovati = G.cerca(testo)
    if not trovati:
        await msg.reply_text(f"Nessun giocatore si chiama «{testo}».")
        return
    from shared import pagine as PG                    # v7.25.0: a pagine, di chi ha cercato; tra apici il nome esatto
    from shared.parole_nome import senza_apici
    if len(trovati) > 1 and L.norm(trovati[0]["nome_common"]) != L.norm(senza_apici(testo)):
        await PG.manda(msg, context, [(x["nome_common"], f"wl:+:{x['id']}") for x in trovati], "Quale vuoi seguire?")
        return
    gid = trovati[0]["id"]
    await msg.reply_text(_testo_aggiunto(gid, W.aggiungi(update.effective_user.id, gid)), parse_mode="HTML")


async def cmd_unwatch(update, context):
    msg = update.effective_message
    uid = update.effective_user.id
    testo = " ".join(context.args or [])
    if not testo:
        await msg.reply_text("Uso: /unwatch NOME. La tua lista: /watchlist")
        return
    miei = W.seguiti(uid)
    trovati = [x for x in G.cerca(testo) if x["id"] in miei]
    if not trovati:
        await msg.reply_text(f"Nella tua watchlist non c'è nessuno che si chiama «{testo}».")
        return
    from shared import pagine as PG
    from shared.parole_nome import senza_apici
    if len(trovati) > 1 and L.norm(trovati[0]["nome_common"]) != L.norm(senza_apici(testo)):
        await PG.manda(msg, context, [(x["nome_common"], f"wl:-:{x['id']}") for x in trovati], "Quale togli?")
        return
    W.togli(uid, trovati[0]["id"])
    await msg.reply_text(f"👁 Non segui più <b>{e(trovati[0]['nome_common'])}</b>.", parse_mode="HTML")


async def cmd_watchlist(update, context):
    """La watchlist con la grafica di /giocatori (filtro watch, più gli altri filtri scritti dopo)."""
    msg = update.effective_message
    if not W.seguiti(update.effective_user.id):
        await msg.reply_text("La tua watchlist è vuota: /watch NOME per seguire un giocatore.")
        return
    from shared import elenco_giocatori as EG
    r = await asyncio.to_thread(EG.risposta, "watch " + " ".join(context.args or []), update.effective_user.id, True)
    await EG.manda(msg, r)


def leggi_soglia(args: list[str]) -> tuple[float | None, float | None] | None:
    """«+20» = sopra la media, «45» = assoluta, anche insieme; «default» = tutte e due di default. None se sbagliato."""
    if [a.lower() for a in args] == ["default"]:
        return (None, None)
    sopra = assoluta = None
    for a in args:
        a = a.replace(",", ".")
        try:
            if a.startswith("+"):
                sopra = float(a[1:])
            else:
                assoluta = float(a)
        except ValueError:
            return None
    return (sopra, assoluta) if args else None


async def cmd_watch_soglia(update, context):
    msg = update.effective_message
    uid = update.effective_user.id
    if context.args:
        v = leggi_soglia(context.args)
        if v is None:
            await msg.reply_text("Uso: /watch_soglia +20 (sopra la media) · /watch_soglia 45 (fantapunti) · "
                                 "/watch_soglia +20 45 · /watch_soglia default")
            return
        vecchia = W.soglia(uid)
        W.imposta_soglia(uid, v[0] if v[0] is not None or context.args[0].lower() == "default" else vecchia[0],
                         v[1] if v[1] is not None or context.args[0].lower() == "default" else vecchia[1])
    s = W.soglia(uid)
    f = lambda x: f"{x:g}".replace(".", ",")
    await msg.reply_text(f"🔥 Grande prestazione: almeno <b>media +{f(s[0])}</b> o <b>{f(s[1])} fantapunti</b>."
                         + ("\nCambiala con /watch_soglia +20, /watch_soglia 45 o tutte e due; /watch_soglia default." if not context.args else ""),
                         parse_mode="HTML")


def bottone(gid: int, uid: int):
    """«👁 Segui» / «👁 Non seguire più» sotto /player (in privato, per i GM)."""
    if W.segue(uid, gid):
        return K([[B("👁 Non seguire più", callback_data=f"wl:-:{gid}:p")]])
    return K([[B("👁 Segui", callback_data=f"wl:+:{gid}:p")]])


def bottoni_player(gid: int, chat):
    """Per G.handlers: solo in privato e solo per i GM (la chat privata ha l'id dell'utente)."""
    import settings
    if getattr(chat, "type", "") != "private":
        return None
    uid = chat.id
    if not (L.squadra_del_gm(uid) or settings.is_admin(uid)):
        return None
    return bottone(gid, uid)


async def cb_watch(update, context):
    q = update.callback_query
    parti = q.data.split(":")
    segno, gid = parti[1], int(parti[2])
    uid = q.from_user.id
    if segno == "+":
        nuovo = W.aggiungi(uid, gid)
        if len(parti) > 3:                          # dal bottone sotto /player: si gira il bottone
            await q.answer("👁 Ora lo segui" + (non_gioca(gid).replace("\n", " ") if nuovo else ""), show_alert=bool(non_gioca(gid)))
            await q.edit_message_reply_markup(bottone(gid, uid))
            return
        await q.answer()
        await q.edit_message_text(_testo_aggiunto(gid, nuovo), parse_mode="HTML")
    else:
        W.togli(uid, gid)
        if len(parti) > 3:
            await q.answer("👁 Non lo segui più")
            await q.edit_message_reply_markup(bottone(gid, uid))
            return
        await q.answer()
        nome = (L.q("SELECT nome_common FROM giocatori WHERE id = %s", (gid,), one=True) or {}).get("nome_common", "?")
        await q.edit_message_text(f"👁 Non segui più <b>{e(nome)}</b>.", parse_mode="HTML")


for _f in (cmd_watch, cmd_unwatch, cmd_watchlist, cmd_watch_soglia):
    _f._solo_privato = True


def get_handlers() -> list:
    privato = filters.ChatType.PRIVATE
    return [CommandHandler("watch", cmd_watch, filters=privato),
            CommandHandler("unwatch", cmd_unwatch, filters=privato),
            CommandHandler("watchlist", cmd_watchlist, filters=privato, block=False),
            CommandHandler("watch_soglia", cmd_watch_soglia, filters=privato),
            CallbackQueryHandler(cb_watch, pattern=r"^wl:[+-]:\d+(:p)?$")]


# ── avvisi subito ────────────────────────────────────────────────────────────────

def _nome(gid: int) -> str:
    return (L.q("SELECT nome_common FROM giocatori WHERE id = %s", (gid,), one=True) or {}).get("nome_common", "?")


def _situazione(gid: int) -> str:
    """«FA», «Squadra», «diritti di Squadra»: tra parentesi accanto al nome negli avvisi."""
    c = L.q("SELECT team_id FROM contratti WHERE giocatore_id = %s AND attivo LIMIT 1", (gid,), one=True)
    if c:
        return L.nome(c["team_id"])
    try:
        d = L.q("""SELECT team_id FROM rookie WHERE giocatore_id = %s AND NOT firmato AND NOT diritti_scaduti
                   ORDER BY id DESC LIMIT 1""", (gid,), one=True)
    except Exception:
        d = None
    return f"diritti di {L.nome(d['team_id'])}" if d else "FA"


def avvisi_aste(seg: dict, dal) -> list[tuple[int, str, str]]:
    """(utente, chiave, testo) delle aste aperte su giocatori seguiti, dal registro del bot aste."""
    out = []
    righe = L.q("""SELECT id, quando, chi_id, giocatore_id, oggetto, dopo, azione FROM registro_azioni
                   WHERE bot = 'aste' AND azione = ANY(%s) AND quando >= %s AND giocatore_id = ANY(%s)""",
                (list(APERTURE), dal, list(seg)), many=True) or []
    for r in righe:
        for uid, da in seg[r["giocatore_id"]].items():
            if r["quando"] <= da or uid == r["chi_id"]:
                continue                                    # prima di seguirlo, o l'ha aperta lui
            t = (f"🔨 <b>Asta aperta</b> su <b>{e(_nome(r['giocatore_id']))}</b> ({e(_situazione(r['giocatore_id']))})"
                 + (f": {e(r['dopo'])}" if r.get("dopo") else "") + " · sul bot aste")
            out.append((uid, f"asta:{r['id']}", t))
    return out


def avvisi_movimenti(seg: dict, dal) -> list[tuple[int, str, str]]:
    out = []
    righe = L.q("""SELECT id, timestamp, tipo, giocatore_id, team_id_da, team_id_a FROM movimenti_giocatori
                   WHERE timestamp >= %s AND giocatore_id = ANY(%s) AND tipo = ANY(%s)""",
                (dal, list(seg), list(MOVIMENTI)), many=True) or []
    for r in righe:
        t = MOVIMENTI[r["tipo"]].format(da=L.nome(r["team_id_da"]) if r["team_id_da"] else "?",
                                        a=L.nome(r["team_id_a"]) if r["team_id_a"] else "?")
        for uid, da in seg[r["giocatore_id"]].items():
            if r["timestamp"] > da:
                out.append((uid, f"mov:{r['id']}", f"🔁 <b>{e(_nome(r['giocatore_id']))}</b>: {e(t)}"))
    return out


def avvisi_infortuni(seg: dict) -> list[tuple[int, str, str]]:
    """Solo le cose serie (Luca, 14/11): diventa Out, Doubtful o sospeso, o ne esce. Confronta gli ultimi due report."""
    try:
        prese = [r["preso"] for r in L.q("SELECT DISTINCT preso FROM nba_infortuni ORDER BY preso DESC LIMIT 2", many=True) or []]
    except Exception:
        return []
    if len(prese) < 2:
        return []
    atl = {r["espn_id"]: r["id"] for r in L.q("SELECT id, espn_id FROM giocatori WHERE id = ANY(%s) AND espn_id IS NOT NULL",
                                              (list(seg),), many=True) or []}
    if not atl:
        return []
    stati = {}
    for r in L.q("SELECT atleta, stato, dettaglio, preso FROM nba_infortuni WHERE preso = ANY(%s) AND atleta = ANY(%s)",
                 (prese, list(atl)), many=True) or []:
        stati[(r["atleta"], r["preso"])] = r
    out = []
    for a, gid in atl.items():
        ora, prima = stati.get((a, prese[0])), stati.get((a, prese[1]))
        s_ora = (ora or {}).get("stato")
        s_prima = (prima or {}).get("stato")
        if s_ora == s_prima:
            continue
        if s_ora in GRAVI:
            det = f" ({e(ora['dettaglio'][:60])})" if ora.get("dettaglio") else ""
            t = f"🩹 <b>{e(_nome(gid))}</b>: <b>{GRAVI[s_ora]}</b>{det}" + (f", prima {e(s_prima)}" if s_prima else "")
        elif s_prima in GRAVI:
            t = f"✅ <b>{e(_nome(gid))}</b>: non è più {GRAVI[s_prima]}" + (f" (ora {e(s_ora)})" if s_ora else ", fuori dall'injury report")
        else:
            continue                                        # Q, DTD, Probable: non sono cose serie
        for uid, da in seg[gid].items():
            if prese[0] > da:
                out.append((uid, f"inf:{a}:{prese[0].isoformat()}", t))
    return out


def media_prima(atleta: str, stagione: str, prima_di) -> float | None:
    """La fantamedia della stagione prima di una partita (regular season e play-in, chi è entrato)."""
    r = L.q("""SELECT t.fp, t.giocato, t.minuti FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
               WHERE t.atleta = %s AND p.stagione = %s AND p.tipo = ANY(%s) AND p.inizio < %s""",
            (atleta, stagione, list(TIPI), prima_di), many=True) or []
    fp = [float(x["fp"]) for x in r if L.conta(x)]
    return sum(fp) / len(fp) if fp else None


def _vs(p: dict, squadra: str) -> str:
    casa = squadra == p["casa"]
    avv = p["trasferta"] if casa else p["casa"]
    ris = ""
    if p.get("punti_casa") is not None and p.get("punti_trasferta") is not None:
        noi, loro = (p["punti_casa"], p["punti_trasferta"]) if casa else (p["punti_trasferta"], p["punti_casa"])
        ris = f" · {'V' if noi > loro else 'S'} {noi}-{loro}"
    return f"{'vs' if casa else '@'} {avv}{ris}"


def avvisi_prestazioni(seg: dict, dal) -> list[tuple[int, str, str]]:
    """Grande prestazione nelle partite finite: fp ≥ media + sopra, o fp ≥ assoluta (soglia di ogni GM)."""
    atl = {r["espn_id"]: r["id"] for r in L.q("SELECT id, espn_id FROM giocatori WHERE id = ANY(%s) AND espn_id IS NOT NULL",
                                              (list(seg),), many=True) or []}
    if not atl:
        return []
    try:
        righe = L.q("""SELECT t.*, p.inizio, p.casa, p.trasferta, p.punti_casa, p.punti_trasferta, p.stagione AS st
                       FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                       WHERE p.stato = 'STATUS_FINAL' AND p.inizio >= %s AND p.tipo = ANY(%s) AND t.atleta = ANY(%s)""",
                    (dal, list(TIPI), list(atl)), many=True) or []
    except Exception:
        return []
    out = []
    for r in righe:
        if not L.conta(r):
            continue
        fp = float(r["fp"])
        media = media_prima(r["atleta"], r["st"], r["inizio"])
        gid = atl[r["atleta"]]
        for uid, da in seg[gid].items():
            if r["inizio"] <= da or not W.grande(fp, media, W.soglia(uid)):
                continue
            m = f", media {G.tp(media)} ({'+' if fp >= media else ''}{G.tp(fp - media)})" if media is not None else ""
            out.append((uid, f"perf:{r['partita']}:{r['atleta']}",
                        f"🔥 <b>{e(_nome(gid))}</b> ({e(_situazione(gid))}) · <b>{G.tp(fp)}</b> stanotte {e(_vs(r, r['squadra']))}{m}"))
    return out


async def job_avvisi(context) -> None:
    """Ogni 5 minuti: gli avvisi nuovi dei giocatori seguiti, a chi li segue, una volta sola."""
    seg = await asyncio.to_thread(W.tutti)
    if not seg:
        return
    dal = datetime.now(timezone.utc) - timedelta(days=2)
    tutti = []
    for f, args in ((avvisi_aste, (seg, dal)), (avvisi_movimenti, (seg, dal)), (avvisi_infortuni, (seg,)),
                    (avvisi_prestazioni, (seg, dal))):
        try:
            tutti += await asyncio.to_thread(f, *args)
        except Exception as err:
            logger.warning("Watchlist, %s: %s", f.__name__, err)
    for uid, chiave, testo in tutti:
        if not W.nuovo_avviso(uid, chiave):
            continue
        try:
            await context.bot.send_message(chat_id=uid, text=testo, parse_mode="HTML")
        except Exception as err:                            # bot bloccato, chat mai aperta: niente
            logger.info("Watchlist, avviso a %s: %s", uid, err)


# ── il report delle 9:30 ────────────────────────────────────────────────────────

def notte_di(ora: datetime | None = None) -> date:
    """La notte NBA appena finita: il giorno di New York di ieri, guardando da Roma la mattina."""
    ora = ora or datetime.now(ROMA)
    return (ora.astimezone(ROMA) - timedelta(days=1)).date()


def dati_report(uid: int, notte: date) -> dict | None:
    """I dati dell'immagine del report di uid per la notte (giorno ET). None se nessuno dei suoi ha giocato."""
    ids = W.seguiti(uid)
    if not ids:
        return None
    from shared import elenco_giocatori as EG
    s = L.stagione()
    oggi = int(s)
    info = {x["id"]: x for x in EG.dati(oggi, oggi) if x["id"] in ids}
    gioc = L.q("SELECT id, nome_common, espn_id FROM giocatori WHERE id = ANY(%s)", (list(ids),), many=True) or []
    atl = {g["espn_id"]: g for g in gioc if g["espn_id"]}
    if not atl:
        return None
    partite = L.q("""SELECT * FROM nba_partite WHERE data_et = %s AND tipo = ANY(%s) AND stato = 'STATUS_FINAL'""",
                  (notte, list(TIPI)), many=True) or []
    if not partite:
        return None
    pid = {p["espn_id"]: p for p in partite}
    in_campo = {p["casa"] for p in partite} | {p["trasferta"] for p in partite}
    tab = {r["atleta"]: r for r in L.q("SELECT * FROM nba_tabellini WHERE partita = ANY(%s) AND atleta = ANY(%s)",
                                       (list(pid), list(atl)), many=True) or []}
    sq = L.squadre_roster(list(atl))
    soglia = W.soglia(uid)
    giocato, non_giocato = [], []
    from shared.elenco_giocatori import stato as stato_x, _colore
    for a, g in atl.items():
        x = info.get(g["id"]) or {}
        r = tab.get(a)
        if r and L.conta(r):
            p = pid[r["partita"]]
            fp = float(r["fp"])
            media = media_prima(a, s, p["inizio"])
            tid = (x.get("contratto") or {}).get("team_id") or x.get("diritti")
            u = G.ultime_dati([{**r, "data_et": p["data_et"], "casa": p["casa"], "trasferta": p["trasferta"]}], [])
            giocato.append({"nome": g["nome_common"], "foto": L.foto(a) or "", "iniziali": "".join(w[0] for w in g["nome_common"].split()[:2]).upper(),
                            "tipo": stato_x(x) if x else "fa", "squadra": L.nome(tid) if tid else "",
                            "colore": _colore(tid) if tid else "#1B8A4B", "partita": _vs(p, r["squadra"]),
                            "riga": u[0]["riga"] if u else "", "fp": G.tp(fp), "fpv": fp,
                            "media": G.tp(media) if media is not None else "—", "delta": G.tp(abs(fp - media)) if media is not None else "",
                            "delta_v": (fp - media) if media is not None else 0, "top": W.grande(fp, media, soglia),
                            "inf": G.INF_BREVE.get(x.get("inf") or "", x.get("inf") or "")})
        else:
            motivo = ("a referto senza entrare" if r else
                      (f"{x['inf']}" if x.get("inf") else "non ha giocato") if sq.get(a) in in_campo else "la sua squadra non giocava")
            non_giocato.append(f"{g['nome_common']} ({motivo})")
    if not giocato:
        return None
    giocato.sort(key=lambda r: -r["fpv"])
    m = giocato[0]
    return {"sotto": f"notte del {notte:%d/%m} · {len(ids)} {'giocatore seguito' if len(ids) == 1 else 'giocatori seguiti'}, "
                     f"{len(giocato)} in campo",
            "migliore": f"{m['nome']} · {m['fp']}", "giocato": giocato, "non_giocato": sorted(non_giocato)}


def immagine_report(d: dict) -> bytes:
    return W.immagine(d)


async def job_report(context) -> None:
    """Alle 9:30 (orari.watch_report): il report della notte a chi ha una watchlist, se qualcuno dei suoi ha giocato."""
    notte = notte_di()
    for uid in await asyncio.to_thread(W.utenti):
        try:
            d = await asyncio.to_thread(dati_report, uid, notte)
            if not d or not W.nuovo_avviso(uid, f"report:{notte.isoformat()}"):
                continue
            png = await asyncio.to_thread(immagine_report, d)
            await context.bot.send_photo(chat_id=uid, photo=png, caption=f"👁 Watchlist · notte del {notte:%d/%m}")
        except Exception as err:
            logger.info("Watchlist, report a %s: %s", uid, err)

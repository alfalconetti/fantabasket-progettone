"""
/player GIOCATORE (tutti, v5.4.0): dove gioca nella realtà e nel fantabasket, con la media e le
statistiche della stagione. Solo lettura: anagrafica e contratti del bot principale, tabellini,
roster e infortunati di ESPN già nel database (niente richieste a ESPN).

- NBA: squadra dei roster ESPN di adesso (se no quella dell'ultimo tabellino), status dall'ultimo
  snapshot degli infortunati (assente = sano).
- Fantabasket (Luca, 23/10): posizioni eleggibili sempre; se firmato squadra, ruolo della stagione
  (o la dichiarazione aperta) e stato del contratto (importo × anni rimasti e fino a quando, rookie,
  10-day, DPE, x0 e RFA); se no free agent o diritti rookie di chi.
- Stagione: partite di regular season e play-in che contano (come la media del calcolo: uno 0 con
  0 minuti no), media dei fantapunti all'ottavo, medie per partita e percentuali al tiro.
- Ultime 5 partite.
Con più giocatori dallo stesso nome, bottoni (callback pl:<id>).
"""
import html

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import calcolo
import config
import db
from numeri import ottavi, testo as tp

TIPI = (2, 5)          # regular season e play-in, come la media della stagione


def e(x) -> str:
    return html.escape(str(x), quote=False)


def cerca(testo: str) -> list[dict]:
    """Giocatori dell'anagrafica col nome indicato (anche senza id ESPN), prima quelli a roster."""
    import difflib
    n = calcolo.norm(testo)
    if not n:
        return []
    tutti = db.q("""SELECT g.id, g.nome_common, g.espn_id,
                           EXISTS (SELECT 1 FROM contratti c WHERE c.giocatore_id = g.id AND c.attivo) AS a_roster
                    FROM giocatori g""", many=True) or []
    esatti = [g for g in tutti if calcolo.norm(g["nome_common"]) == n]
    trovati = esatti or [g for g in tutti if n in calcolo.norm(g["nome_common"])]
    if not trovati:
        nomi = {calcolo.norm(g["nome_common"]): g for g in tutti}
        trovati = [nomi[x] for x in difflib.get_close_matches(n, list(nomi), n=5, cutoff=0.75)]
    return sorted(trovati, key=lambda g: (not g["a_roster"], g["espn_id"] is None, g["nome_common"]))[:8]


def _pct(fatti: int, tentati: int) -> str:
    return f"{100 * fatti / tentati:.1f}%".replace(".", ",") if tentati else "—"


def _media(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def scheda(gid: int) -> str:
    s = config.stagione()
    g = db.q("SELECT id, nome_common, espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    if not g:
        return "Giocatore non trovato."
    righe = [f"🏀 <b>{e(g['nome_common'])}</b>", ""]
    a = g["espn_id"]

    # ── NBA ──
    if a:
        sq = (db.squadre_roster([a]).get(a) or db.ultima_squadra([a], "9999-12-31").get(a))
        ultimo = db.q("SELECT MAX(preso) AS p FROM nba_infortuni", one=True)
        inf = None
        if ultimo and ultimo["p"]:
            inf = db.q("SELECT stato, dettaglio FROM nba_infortuni WHERE atleta = %s AND preso = %s", (a, ultimo["p"]), one=True)
        stato = f" · 🩹 {e(inf['stato'])}" + (f" <i>({e(inf['dettaglio'][:80])})</i>" if inf.get("dettaglio") else "") if inf else ""
        righe.append(f"🇺🇸 NBA: <b>{e(sq) if sq else 'senza squadra'}</b>{stato}")
    else:
        righe.append("🇺🇸 NBA: <i>non abbinato a ESPN (niente statistiche)</i>")

    # ── fantabasket (Luca, 23/10): posizioni eleggibili sempre; se firmato ruolo e stato del contratto ──
    def _q1(sql, params):
        try:
            return db.q(sql, params, one=True)
        except Exception:                      # tabella del bot principale che manca (prove, database vuoto)
            return None
    pos = _q1("SELECT posizioni FROM posizioni_attuali WHERE giocatore_id = %s", (gid,))
    eleg = [r for r in ("PG", "SG", "SF", "PF", "C") if r in set(((pos or {}).get("posizioni") or "").split(","))]
    righe.append("📋 Posizioni eleggibili: " + (f"<b>{', '.join(eleg)}</b>" if eleg else "<i>non registrate</i>"))
    c = db.q("""SELECT c.*, (SELECT r.ruolo FROM ruolo_attuale r WHERE r.giocatore_id = c.giocatore_id AND r.stagione = %s LIMIT 1) AS ruolo,
                       (SELECT d.importo_dpe FROM dpe d WHERE d.giocatore_id = c.giocatore_id AND d.team_id = c.team_id
                         AND d.stagione = %s LIMIT 1) AS importo_dpe
                FROM contratti c WHERE c.giocatore_id = %s AND c.attivo LIMIT 1""", (s, s, gid), one=True)
    if c:
        righe.append(f"🏆 Fantabasket: <b>{e(config.nome(c['team_id']))}</b>")
        # ruolo della stagione, o la dichiarazione ancora aperta
        pend = _q1("SELECT scadenza FROM ruoli_pendenti WHERE giocatore_id = %s AND team_id = %s AND stato = 'aperta' LIMIT 1",
                   (gid, c["team_id"]))
        if c.get("ruolo"):
            righe.append(f"🎽 Ruolo: <b>{e(c['ruolo'])}</b>")
        elif pend:
            righe.append(f"🎽 Ruolo: <i>da dichiarare entro {pend['scadenza'].astimezone(__import__('zoneinfo').ZoneInfo('Europe/Rome')):%d/%m %H:%M}</i>")
        else:
            righe.append("🎽 Ruolo: <i>non ancora ufficiale</i>")
        # stato del contratto
        anni = int(c["anni_originali"]) - (int(s) - int(c["stagione_firma"]))
        fine = int(c["stagione_firma"]) + int(c["anni_originali"]) - 1
        stagione_txt = lambda y: f"{y}-{str(y + 1)[-2:]}"
        if c["tipo"] == "10day":
            contratto = "10-day" + (f", firmato il {c['firmato_at']:%d/%m}" if c.get("firmato_at") else "")
        elif anni <= 0:
            rfa = _q1("SELECT 1 AS x FROM rfa_dichiarati WHERE contratto_id = %s AND stato = 'attiva'", (c["id"],))
            contratto = (f"{c['importo']}M, contratto finito (x0)" + (" · dichiarato RFA" if rfa else
                         " · a fine stagione la squadra può dichiararlo RFA"))
        else:
            contratto = (f"{c['importo']}M × {anni} {'anno' if anni == 1 else 'anni'} rimasti (fino al {stagione_txt(fine)}; "
                         f"firmato nel {stagione_txt(int(c['stagione_firma']))} per {c['anni_originali']})")
        if c["tipo"] == "rookie":
            contratto += " · contratto rookie"
        if c.get("importo_dpe") is not None:
            contratto += f" · 🏥 DPE quest'anno (pesa {c['importo_dpe']}M)"
        righe.append(f"📝 Contratto: {e(contratto)}")
    else:
        diritti = _q1("""SELECT team_id, scadenza_diritti FROM rookie WHERE giocatore_id = %s AND NOT firmato
                         AND NOT diritti_scaduti ORDER BY id DESC LIMIT 1""", (gid,))
        if diritti:
            righe.append(f"🏆 Fantabasket: <b>svincolato</b>, diritti rookie di <b>{e(config.nome(diritti['team_id']))}</b>"
                         + (f" (scadono il {diritti['scadenza_diritti']:%d/%m/%Y})" if diritti.get("scadenza_diritti") else ""))
        else:
            righe.append("🏆 Fantabasket: <b>svincolato</b> (free agent)")

    if not a:
        return "\n".join(righe)

    # ── stagione ──
    tab = db.q("""SELECT t.*, p.data_et, p.casa, p.trasferta FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                  WHERE t.atleta = %s AND p.stagione = %s AND p.tipo = ANY(%s) ORDER BY p.inizio""",
               (a, s, list(TIPI)), many=True) or []
    contano = [r for r in tab if calcolo.conta(r)]
    righe.append("")
    if not contano:
        righe.append(f"📊 Stagione {e(s)}: nessuna partita giocata" + (f" ({len(tab)} a referto senza entrare)" if tab else ""))
        return "\n".join(righe)
    n = len(contano)
    tot = {k: sum(int(r[k]) for r in contano) for k in ("minuti", "pts", "oreb", "dreb", "ast", "stl", "blk", "tov",
                                                       "fgm", "fga", "tpm", "tpa", "ftm", "fta")}
    media_fp = ottavi(sum(float(r["fp"]) for r in contano) / n)
    righe += [f"📊 <b>Stagione {e(s)}</b>: {n} partite · media <b>{tp(media_fp)}</b> fantapunti",
              f"{_media(tot['minuti'] / n)} min · {_media(tot['pts'] / n)} punti · {_media((tot['oreb'] + tot['dreb']) / n)} rimbalzi "
              f"· {_media(tot['ast'] / n)} assist · {_media(tot['stl'] / n)} recuperi · {_media(tot['blk'] / n)} stoppate "
              f"· {_media(tot['tov'] / n)} perse",
              f"Tiro {_pct(tot['fgm'], tot['fga'])} · da tre {_pct(tot['tpm'], tot['tpa'])} · liberi {_pct(tot['ftm'], tot['fta'])}"]

    # ── ultime 5 ──
    righe += ["", "<b>Ultime partite</b>"]
    for r in tab[-5:]:
        avv = r["trasferta"] if r["squadra"] == r["casa"] else r["casa"]
        dove = "vs" if r["squadra"] == r["casa"] else "@"
        if not calcolo.conta(r):
            righe.append(f"• {r['data_et']:%d/%m} {dove} {e(avv)}: non è entrato")
            continue
        righe.append(f"• {r['data_et']:%d/%m} {dove} {e(avv)}: {r['minuti']}′ · {r['pts']} pt · {r['oreb'] + r['dreb']} rb · "
                     f"{r['ast']} as → <b>{tp(float(r['fp']))}</b>")
    return "\n".join(righe)


async def cmd_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    testo = " ".join(context.args or [])
    if not testo:
        await msg.reply_text("Uso: /player NOME (es. /player Wembanyama)")
        return
    trovati = cerca(testo)
    if not trovati:
        await msg.reply_text(f"Nessun giocatore si chiama «{testo}».")
        return
    if len(trovati) > 1 and calcolo.norm(trovati[0]["nome_common"]) != calcolo.norm(testo):
        await msg.reply_text("Quale?", reply_markup=K([[B(x["nome_common"] + (" ✅" if x["a_roster"] else ""),
                                                           callback_data=f"pl:{x['id']}")] for x in trovati]))
        return
    await manda(msg, trovati[0]["id"])


def _foto(gid: int) -> str | None:
    import foto
    g = db.q("SELECT espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    return foto.percorso(g["espn_id"]) if g and g.get("espn_id") else None


async def manda(msg, gid: int) -> None:
    """La scheda; con la foto ESPN se c'è già (foto.py: si scarica di notte, qui mai). La didascalia di
    una foto arriva a 1024 caratteri: oltre, la foto e sotto il testo."""
    t = scheda(gid)
    f = _foto(gid)
    img = None
    if f:
        try:
            img = immagine(gid, f)
        except Exception as err:                          # Typst o foto rovinata: solo testo
            import logging
            logging.getLogger(__name__).warning("Foto di /player: %s", err)
    if not img:
        await msg.reply_text(t, parse_mode="HTML")
        return
    if len(t) <= 1024:
        await msg.reply_photo(img, caption=t, parse_mode="HTML")
        return
    await msg.reply_photo(img)
    await msg.reply_text(t, parse_mode="HTML")


def immagine(gid: int, f: str) -> bytes:
    """La foto ESPN (trasparente) su uno sfondo viola 640×420 col nome (foto_player.typ): su
    Telegram una PNG trasparente può uscire su fondo nero, e una foto piccola si vede sgranata."""
    import json, os, typst
    g = db.q("SELECT nome_common, espn_id FROM giocatori WHERE id = %s", (gid,), one=True) or {}
    sq = db.squadre_roster([g.get("espn_id")]).get(g.get("espn_id")) if g.get("espn_id") else None
    c = db.q("SELECT team_id FROM contratti WHERE giocatore_id = %s AND attivo LIMIT 1", (gid,), one=True)
    sotto = " · ".join(x for x in (sq or "", config.nome(c["team_id"]) if c else "") if x)
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "foto_player.typ")
    return typst.compile(tpl, root="/", format="png", ppi=144,
                         sys_inputs={"dati": json.dumps({"foto": os.path.abspath(f), "nome": g.get("nome_common", ""),
                                                          "sotto": sotto}, ensure_ascii=False)})


async def cb_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = int(q.data.split(":")[1])
    if _foto(gid):                                   # con la foto: il «Quale?» si toglie, la scheda arriva sotto
        await q.edit_message_text("🏀 ⬇️")
        await manda(q.message, gid)
        return
    await q.edit_message_text(scheda(gid), parse_mode="HTML")


def get_handlers() -> list:
    return [CommandHandler("player", cmd_player), CallbackQueryHandler(cb_player, pattern=r"^pl:\d+$")]

"""
/player GIOCATORE (tutti, v5.4.0): dove gioca nella realtà e nel fantabasket, con la media e le
statistiche della stagione. Solo lettura: anagrafica e contratti del bot principale, tabellini,
roster e infortunati di ESPN già nel database (niente richieste a ESPN).

- NBA: squadra dei roster ESPN di adesso (se no quella dell'ultimo tabellino), status dall'ultimo
  snapshot degli infortunati (assente = sano).
- Fantabasket: squadra, ruolo della stagione, contratto (importo × anni rimasti; rookie, 10-day,
  DPE, x0), o svincolato.
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

    # ── fantabasket ──
    c = db.q("""SELECT c.*, (SELECT r.ruolo FROM ruolo_attuale r WHERE r.giocatore_id = c.giocatore_id AND r.stagione = %s LIMIT 1) AS ruolo,
                       (SELECT d.importo_dpe FROM dpe d WHERE d.giocatore_id = c.giocatore_id AND d.team_id = c.team_id
                         AND d.stagione = %s LIMIT 1) AS importo_dpe
                FROM contratti c WHERE c.giocatore_id = %s AND c.attivo LIMIT 1""", (s, s, gid), one=True)
    if c:
        anni = int(c["anni_originali"]) - (int(s) - int(c["stagione_firma"]))
        if c["tipo"] == "10day":
            contratto = "10-day"
        else:
            contratto = f"{c['importo']} × {max(anni, 0)} {'anno' if anni == 1 else 'anni'}"
            if anni <= 0:
                contratto = f"{c['importo']} (x0, ultimo anno finito)"
            if c["tipo"] == "rookie":
                contratto += " · rookie"
            if c.get("importo_dpe") is not None:
                contratto += f" · DPE (pesa {c['importo_dpe']})"
        ruolo = f" · {e(c['ruolo'])}" if c.get("ruolo") else ""
        righe.append(f"🏆 Fantabasket: <b>{e(config.nome(c['team_id']))}</b>{ruolo} · {e(contratto)}")
    else:
        righe.append("🏆 Fantabasket: <b>svincolato</b>")

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
    await msg.reply_text(scheda(trovati[0]["id"]), parse_mode="HTML")


async def cb_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(scheda(int(q.data.split(":")[1])), parse_mode="HTML")


def get_handlers() -> list:
    return [CommandHandler("player", cmd_player), CallbackQueryHandler(cb_player, pattern=r"^pl:\d+$")]

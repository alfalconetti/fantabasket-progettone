"""
/trova_trade NUMERO o GIOCATORE (Luca, 23/10 e 31/10; mockup approvato il 31/10): un'immagine che riassume una
trade ufficiale (con il numero TRADE-AAAA-NNN: approvata, o approvata e poi annullata).

- Ricerca: per numero («014», «TRADE-2026-014», «2026-014») o per nome di un giocatore (le trade ufficiali in cui
  c'è, come giocatore o come diritti; più d'una → bottoni). Bozze, proposte e rifiutate non ci sono.
- Una colonna per squadra (2-3 in fila, 4 in una griglia 2×2): «riceve» e «cede», ogni asset con da chi arriva /
  a chi va (nelle trade a tre non si ricava una dall'altra). Giocatori con ruolo e contratto di allora (dal
  movimento della trade), pick con anno, giro, di chi era e protezioni, diritti con giro, numero e anno del draft.
- Cap e roster **al momento della trade**, subito prima e subito dopo (roster a una data dal registro, DPE e
  spalmature registrate fino a quel momento): per una trade annullata, quelli di quando era stata eseguita.
- Percorso: solo quello che è successo davvero (Luca, 31/10: non serve che accettino tutti, un GM può mandarla
  direttamente agli admin, ci sono le trade scritte dagli admin): proposta o scritta da un admin, le accettazioni e
  i rifiuti con l'ora (trade_voti), mandata agli admin senza le accettazioni che mancano, approvata, annullata.
Dati in `dati(trade_id)`, disegno in trova_trade.typ (Typst, stile di /carriera ma in verde).
"""
import asyncio
import html
import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import timedelta

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db
import teams as tm
from utils import ROME

logger = logging.getLogger(__name__)
TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "trova_trade.typ")
PPI = 220                                   # pagina di 520pt → circa 1600 pixel
UFFICIALI = ("approvata", "annullata")
RUOLI = {"PG", "SG", "SF", "PF", "C"}


def e(x) -> str:
    return html.escape(str(x), quote=False)


# ── ricerca ─────────────────────────────────────────────────────────────────────

def per_numero(testo: str) -> dict | None:
    """«014», «14», «2026-014», «TRADE-2026-014»: la trade ufficiale con quel numero (la più recente, se l'anno manca)."""
    m = re.fullmatch(r"(?:trade[-\s]?)?(?:(\d{4})[-\s/])?0*(\d{1,4})", (testo or "").strip().lower())
    if not m:
        return None
    anno, num = m.group(1), int(m.group(2))
    righe = db._q("SELECT * FROM trade WHERE trade_ref IS NOT NULL AND stato = ANY(%s) ORDER BY approvata_at DESC NULLS LAST",
                  (list(UFFICIALI),), many=True) or []
    for t in righe:
        mm = re.search(r"(\d{4})-0*(\d+)$", t["trade_ref"] or "")
        if mm and int(mm.group(2)) == num and (not anno or mm.group(1) == anno):
            return t
    return None


def per_giocatore(testo: str) -> tuple[list[dict], list[dict]]:
    """(giocatori trovati, trade ufficiali che li riguardano, dalla più recente)."""
    from shared.parole_nome import parole
    trovati = db.cerca_giocatori(" ".join(parole(testo))) or []
    if not trovati:
        return [], []
    ids = [g["id"] for g in trovati]
    trade = db._q("""SELECT DISTINCT t.* FROM trade t JOIN trade_items i ON i.trade_id = t.id
                     WHERE t.trade_ref IS NOT NULL AND t.stato = ANY(%s) AND i.giocatore_id = ANY(%s)
                     ORDER BY t.approvata_at DESC NULLS LAST""", (list(UFFICIALI), ids), many=True) or []
    return trovati, trade


# ── dati per l'immagine ─────────────────────────────────────────────────────────

def _sq(team_id: str) -> dict:
    from handlers.carriera import sq_fanta
    s = sq_fanta(team_id) or {"nome": team_id, "sigla": team_id[:2].upper(), "colore": "#4B5563", "logo": ""}
    t = tm.get_team_by_id(team_id) or {}
    return {**s, "id": team_id, "gm": t.get("gm_nome") or ""}


def _nome_team(team_id: str) -> str:
    return (tm.get_team_by_id(team_id) or {}).get("nome", team_id)


def _ora(dt) -> str:
    return dt.astimezone(ROME).strftime("%d/%m %H:%M") if dt else ""


def _stagione_al(dt) -> int:
    d = dt.astimezone(ROME)
    return d.year if d.month >= 7 else d.year - 1


def _protezioni(p) -> str:
    if not p:
        return ""
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except ValueError:
            return p
    if isinstance(p, dict):
        return ", ".join(f"{k} {v}" for k, v in p.items())
    return str(p)


def _contratto(trade_id: int, gid: int, stagione: int) -> str:
    """Il contratto che aveva quando è stato scambiato (dal movimento della trade)."""
    c = db._q("""SELECT c.importo, c.anni_originali, c.stagione_firma, c.tipo FROM movimenti_giocatori t
                 JOIN contratti c ON c.id = t.contratto_id
                 WHERE t.trade_id = %s AND t.giocatore_id = %s AND t.tipo = 'traded' ORDER BY t.id LIMIT 1""",
              (trade_id, gid), one=True)
    if not c:
        return ""
    anni = int(c["anni_originali"]) - (stagione - int(c["stagione_firma"]))
    fino = int(c["stagione_firma"]) + int(c["anni_originali"]) - 1
    extra = {"rookie": " · rookie", "10day": " · 10-day"}.get(c.get("tipo"), "")
    return f"{c['importo']}M × {max(anni, 0)} (fino al {fino}-{str(fino + 1)[-2:]}){extra}"


def _ruolo(gid: int, stagione: int) -> str:
    r = db._q("SELECT ruolo FROM ruolo_attuale WHERE giocatore_id = %s AND stagione = %s", (gid, str(stagione)), one=True)
    return r["ruolo"] if r and r.get("ruolo") in RUOLI else ""


def _asset(it: dict, trade_id: int, stagione: int) -> dict:
    if it["tipo"] == "giocatore":
        det = " · ".join(x for x in (_ruolo(it["giocatore_id"], stagione), _contratto(trade_id, it["giocatore_id"], stagione)) if x)
        return {"tipo": "giocatore", "nome": it.get("nome_common") or f"giocatore {it['giocatore_id']}", "dettaglio": det}
    if it["tipo"] == "pick":
        p = db.get_pick(it["pick_id"]) or {}
        giro = "1° giro" if p.get("round") == 1 else "2° giro"
        di = "propria" if p.get("proprietario_orig") == it["team_id_da"] else f"di {_nome_team(p.get('proprietario_orig', '?'))}"
        prot = _protezioni(p.get("protezioni"))
        num = f" · diventata la #{p['numero_scelta']}" if p.get("scattata") and p.get("numero_scelta") else ""
        return {"tipo": "pick", "nome": f"{giro} {p.get('anno', '?')}", "dettaglio": di + (f" · {prot}" if prot else "") + num}
    r = db._q("SELECT round, pick_numero, anno_draft FROM rookie WHERE giocatore_id = %s ORDER BY id DESC LIMIT 1",
              (it["giocatore_id"],), one=True) or {}
    det = f"{'1°' if r.get('round') == 1 else '2°'} giro, #{r['pick_numero']} del {r['anno_draft']}" if r else ""
    return {"tipo": "diritti", "nome": f"Diritti di {it.get('nome_common') or it['giocatore_id']}", "dettaglio": det}


def _cap_roster(team_id: str, quando, stagione: int) -> tuple[int, int]:
    """(cap, giocatori in roster) della squadra in quel momento: contratti che pesano dal roster a quella data,
    con le DPE già approvate, più le spalmature della stagione dei tagli fatti fino ad allora."""
    iso = quando.isoformat()
    roster = db.get_roster_team_at(team_id, iso)
    dpe = db.get_dpe_at(team_id, str(stagione), iso)
    righe = [r for r in roster if r.get("tipo_contratto") != "10day"]
    pesano = [r for r in righe if not r.get("x0") or r.get("rfa")]
    cap = sum(int(dpe.get(r["giocatore_id"], r.get("importo") or 0)) for r in pesano)
    sp = db._q("""SELECT COALESCE(SUM(i.importo), 0) AS tot FROM impatto_taglio i
                  LEFT JOIN movimenti_giocatori t ON t.id = i.transazione_id
                  WHERE i.team_id = %s AND i.stagione = %s AND (t.timestamp IS NULL OR t.timestamp <= %s)""",
               (team_id, str(stagione), iso), one=True)
    return cap + int((sp or {}).get("tot") or 0), len([r for r in righe if not r.get("x0")])


def _percorso(t: dict, squadre: list[str]) -> list[dict]:
    out = []
    da_admin = t.get("proposta_da") == "admin"
    reg = db._q("""SELECT azione, chi_nome, veste, quando, dopo FROM registro_azioni
                   WHERE (dettagli->>'trade_id')::int = %s ORDER BY quando""", (t["id"],), many=True) or []
    if da_admin:
        chi = next((r["chi_nome"] for r in reg if r["veste"] == "admin" and r["chi_nome"]), None)
        out.append({"segno": "scritta", "testo": f"Scritta da un admin{f' ({chi})' if chi else ''}", "quando": _ora(t["timestamp"])})
    else:
        sq = tm.get_team_by_id(t["proposta_da"]) or {}
        gm = sq.get("gm_nome")
        out.append({"segno": "scritta", "testo": f"Proposta da {gm + ' (' + sq.get('nome', t['proposta_da']) + ')' if gm else sq.get('nome', t['proposta_da'])}",
                    "quando": _ora(t["timestamp"])})
    voti = db.get_voti_trade(t["id"]) or []
    for v in sorted([v for v in voti if v["voto"] in ("accettato", "rifiutato")], key=lambda v: v.get("timestamp") or t["timestamp"]):
        out.append({"segno": "ok" if v["voto"] == "accettato" else "no",
                    "testo": f"{'Accettata' if v['voto'] == 'accettato' else 'Rifiutata'} da {_nome_team(v['team_id'])}",
                    "quando": _ora(v.get("timestamp"))})
    if not da_admin:
        accettate = {v["team_id"] for v in voti if v["voto"] == "accettato"} | {t["proposta_da"]}
        mancano = [_nome_team(s) for s in squadre if s not in accettate]
        inv = next((r for r in reversed(reg) if r["azione"] == "trade inviata agli admin"), None)
        if mancano or inv:
            chi = f" da {inv['chi_nome']}" if inv and inv.get("chi_nome") else ""
            out.append({"segno": "admin", "testo": f"Mandata agli admin{chi}" + (" senza le accettazioni di " + ", ".join(mancano) if mancano else ""),
                        "quando": _ora(inv["quando"]) if inv else ""})
    if t.get("approvata_at"):
        chi = t.get("approvata_da") or ""
        chi = _nome_team(chi) if tm.get_team_by_id(chi) else chi
        out.append({"segno": "ok", "testo": f"Approvata{f' da {chi}' if chi else ''}: eseguita", "quando": _ora(t["approvata_at"])})
    if t["stato"] == "annullata":
        r = next((r for r in reversed(reg) if r["azione"] == "trade annullata"), None)
        chi = f" da {r['chi_nome']}" if r and r.get("chi_nome") else ""
        out.append({"segno": "annullata", "testo": f"Annullata{chi}: giocatori, pick e diritti tornati indietro",
                    "quando": _ora(r["quando"] if r else t.get("aggiornato"))})
    return out


def dati(trade_id: int) -> dict:
    t = db.get_trade(trade_id)
    squadre = [s["team_id"] for s in sorted(db.get_squadre_trade(trade_id) or [], key=lambda s: s["ordine"])]
    items = db.get_items_trade(trade_id) or []
    quando = t.get("approvata_at") or t["timestamp"]
    stagione = int(t.get("stagione") or _stagione_al(quando))
    prima, dopo = quando - timedelta(milliseconds=1), quando + timedelta(seconds=1)
    assets = {it["id"]: _asset(it, trade_id, stagione) for it in items}
    _ordine = {"giocatore": 0, "pick": 1, "diritti": 2}
    colonne = []
    for s in squadre:
        cp, rp = _cap_roster(s, prima, stagione)
        cd, rd = _cap_roster(s, dopo, stagione)
        diff = cd - cp
        riceve = [{**assets[i["id"]], "altra": _sq(i["team_id_da"])}
                  for i in sorted([i for i in items if i["team_id_a"] == s], key=lambda i: _ordine.get(i["tipo"], 9))]
        cede = [{**assets[i["id"]], "altra": _sq(i["team_id_a"])}
                for i in sorted([i for i in items if i["team_id_da"] == s], key=lambda i: _ordine.get(i["tipo"], 9))]
        colonne.append({**_sq(s), "riceve": riceve, "cede": cede,
                        "cap": {"prima": str(cp), "dopo": str(cd), "diff": ("+" if diff > 0 else "−" if diff < 0 else "±") + str(abs(diff))},
                        "roster": {"prima": str(rp), "dopo": str(rd)}})
    stato_nota = f"eseguita il {_ora(t['approvata_at']).replace(' ', ' alle ')}" if t.get("approvata_at") else ""
    if t["stato"] == "annullata":
        stato_nota = "eseguita e poi annullata"
    return {"numero": t["trade_ref"], "data": quando.astimezone(ROME).strftime("%d/%m/%Y"), "stato": t["stato"],
            "stato_nota": stato_nota, "asset": len(items), "squadre": colonne, "percorso": _percorso(t, squadre)}


async def immagine(trade_id: int) -> str:
    d = dati(trade_id)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    cmd = ["typst", "compile", "--root", "/", "--ppi", str(PPI), "--input", "dati=" + json.dumps(d, ensure_ascii=False, default=str),
           os.path.abspath(TEMPLATE), tmp.name]
    r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
    if r.returncode != 0:
        try:
            os.unlink(tmp.name)                       # niente PNG vuoti lasciati in /tmp
        except OSError:
            pass
        logger.error("Typst trova_trade: %s", r.stderr)
        raise RuntimeError(f"Errore Typst: {r.stderr[:300]}")
    return tmp.name


# ── comando ─────────────────────────────────────────────────────────────────────

async def _manda(msg, trade_id: int):
    try:
        path = await immagine(trade_id)
    except Exception as err:
        logger.exception("trova_trade %s", trade_id)
        await msg.reply_text(f"❌ Non riesco a disegnare la trade: {e(str(err)[:200])}")
        return
    try:
        t = db.get_trade(trade_id) or {}
        with open(path, "rb") as f:
            await msg.reply_photo(photo=f, caption=f"🔁 {t.get('trade_ref', '')}")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def cmd_trova_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    testo = " ".join(context.args or []).strip()
    if not testo:
        await msg.reply_text("Uso: /trova_trade NUMERO (es. /trova_trade 014) oppure /trova_trade GIOCATORE "
                             "— solo le trade ufficiali, approvate o annullate.")
        return
    t = per_numero(testo)
    if t:
        await _manda(msg, t["id"])
        return
    gioc, trade = per_giocatore(testo)
    if not gioc:
        await msg.reply_text("Nessuna trade con quel numero e nessun giocatore con quel nome.")
        return
    if not trade:
        nomi = ", ".join(g["nome_common"] for g in gioc[:5])
        await msg.reply_text(f"Nessuna trade ufficiale per {e(nomi)}.")
        return
    if len(trade) == 1:
        await _manda(msg, trade[0]["id"])
        return
    kb = K([[B(f"{x['trade_ref']} · {_ora(x.get('approvata_at')).split(' ')[0]}" + (" (annullata)" if x["stato"] == "annullata" else ""),
               callback_data=f"ttr:{x['id']}")] for x in trade[:10]])
    await msg.reply_text(f"{len(trade)} trade ufficiali: quale?", reply_markup=kb)


async def cb_trova_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        tid = int(q.data.split(":")[1])
    except (IndexError, ValueError):
        return
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _manda(q.message, tid)


def get_handlers() -> list:
    return [CommandHandler("trova_trade", cmd_trova_trade), CallbackQueryHandler(cb_trova_trade, pattern=r"^ttr:\d+$")]

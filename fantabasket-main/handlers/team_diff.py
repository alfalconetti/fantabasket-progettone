"""
/team_diff [team_id] [DD-MM-YY] [DD-MM-YY]

Mostra la differenza del roster tra due date (o tra una data e oggi).
Solo il confronto tra i due snapshot — nessun tracciamento degli eventi intermedi.
Contratti (v3.8.1): IN col contratto alla data finale, OUT con quello alla data
iniziale, e i giocatori rimasti con un contratto diverso tra le due date.
Se un giocatore è entrato e uscito nel periodo non appare in nessuna lista.

Esempi:
  /team_diff                       → tua squadra, ultima settimana
  /team_diff bulls                 → bulls, ultima settimana
  /team_diff 01-01-25              → tua squadra, da 01/01/25 ad oggi
  /team_diff bulls 01-01-25        → bulls, da 01/01/25 ad oggi
  /team_diff 01-01-25 01-06-25     → tua squadra, tra le due date
  /team_diff bulls 01-01-25 01-06-25
"""
import html
import logging
from datetime import datetime, timezone, timedelta

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
import settings
import teams as tm

logger = logging.getLogger(__name__)

# ── snapshot roster a una certa data ─────────────────────────────────────────

def _stagione_at(at: datetime) -> int:
    """Stagione della lega a una data: da luglio quella che inizia (2026 = 2026-27)."""
    return at.year if at.month >= 7 else at.year - 1


def _snapshot_contratti(team_id: str, at: datetime) -> dict[int, dict]:
    """{giocatore_id: contratto a quella data} per il roster della squadra.
    Contratto: id, importo effettivo (con l'eventuale DPE già approvata a quella
    data), importo originale, anni residui calcolati sulla stagione di quella data."""
    stagione = _stagione_at(at)
    dpe = db.get_dpe_at(team_id, str(stagione), at.isoformat())
    out = {}
    for r in db.get_roster_team_at(team_id, at.isoformat()):
        if r.get("tipo_contratto") == "rookie":
            scala = int(r.get("anni_scala") or 0)
            anni = 2 if scala in (0, 2) else 1
        elif r.get("anni_originali"):
            s_firma = int(r.get("stagione_firma") or stagione)
            anni = max(1, int(r["anni_originali"]) - (stagione - s_firma))
        else:
            anni = None
        importo = r.get("importo")
        out[r["giocatore_id"]] = {
            "contratto_id": r.get("contratto_id"),
            "importo": dpe.get(r["giocatore_id"], importo),
            "importo_orig": importo,
            "anni": anni,
        }
    return out


def _fmt_contratto(c: dict | None) -> str:
    """'20x2', con DPE '15x2 (DPE, era 20)', '?' se non ricostruibile."""
    if not c or c.get("importo") is None:
        return "?"
    testo = f"{c['importo']}x{c['anni'] if c.get('anni') else '?'}"
    if c.get("importo_orig") is not None and c["importo"] != c["importo_orig"]:
        testo += f" (DPE, era {c['importo_orig']})"
    return testo


def _snapshot_pick(team_id: str, at: datetime) -> set[int]:
    """IDs pick possedute da team_id a una certa data."""
    rows = db.get_pick_at(team_id, at.isoformat())
    return {r["id"] for r in rows}


def _snapshot_diritti(team_id: str, at: datetime) -> set[int]:
    """IDs diritti rookie posseduti a una certa data."""
    rows = db.get_diritti_at(team_id, at.isoformat())
    return {r["id"] for r in rows}


# ── etichetta motivo movimento ────────────────────────────────────────────────

def _motivo_giocatore(team_id: str, giocatore_id: int,
                       da: datetime, a: datetime, verso: str) -> str:
    """
    Cerca in transazioni il primo evento che giustifica l'entrata/uscita
    nel periodo da→a. verso = 'in' | 'out'
    """
    rows = db.get_transazioni_giocatore_periodo(giocatore_id, da.isoformat(), a.isoformat())
    for r in rows:
        if verso == "in" and r["team_id_a"] == team_id:
            return {
                "signed":      "FA",
                "traded":      "Trade",
                "rookie_firma":"Draft",
                "10day_firma": "10-Day",
            }.get(r["tipo"], r["tipo"].capitalize())
        if verso == "out" and r["team_id_da"] == team_id:
            return {
                "traded": "Trade",
                "cut":    "Tagliato",
                "expired":"Scaduto",
                "decaduto":"Ritirato",
                "decadimento":"Decaduto",
                "dpe_attivata":"DPE",
            }.get(r["tipo"], r["tipo"].capitalize())
    return "—"


def _motivo_pick(pick_id: int, team_id: str, da: datetime, a: datetime, verso: str) -> str:
    row = db.get_primo_trade_pick_periodo(pick_id, da.isoformat(), a.isoformat())
    return "Trade" if row else "—"


# ── formattazione ─────────────────────────────────────────────────────────────

def _fmt_data(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y")


async def cmd_team_diff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = list(context.args or [])

    # Parsing argomenti
    team   = None
    dates  = []

    for arg in args:
        try:
            d = datetime.strptime(arg, "%d-%m-%y").replace(tzinfo=timezone.utc)
            dates.append(d)
            continue
        except ValueError:
            pass
        t = tm.get_team_by_query(arg)
        if t:
            team = t
        else:
            await update.effective_message.reply_text(f"❌ Team '{arg}' non trovato.")
            return

    if team is None:
        team = tm.get_team_by_gm(user.id)
        if not team:
            await update.effective_message.reply_text(
                "⛔ Non sei registrato come GM. Usa /team_diff <team_id>."
            )
            return

    now = datetime.now(timezone.utc)
    if len(dates) == 0:
        data_a   = now
        data_da  = now - timedelta(days=7)
    elif len(dates) == 1:
        data_da  = dates[0]
        data_a   = now
    else:
        data_da  = min(dates[0], dates[1])
        data_a   = max(dates[0], dates[1])

    if data_da >= data_a:
        await update.effective_message.reply_text("❌ La data iniziale deve essere precedente alla finale.")
        return

    await update.effective_message.reply_text("⏳ Calcolo variazioni...")

    team_id = team["id"]

    # Snapshot inizio e fine (con i contratti a ciascuna data)
    c_da   = _snapshot_contratti(team_id, data_da)
    c_a    = _snapshot_contratti(team_id, data_a)
    g_da   = set(c_da)
    g_a    = set(c_a)
    p_da   = _snapshot_pick(team_id, data_da)
    p_a    = _snapshot_pick(team_id, data_a)
    d_da   = _snapshot_diritti(team_id, data_da)
    d_a    = _snapshot_diritti(team_id, data_a)

    # Differenze
    g_in   = g_a  - g_da
    g_out  = g_da - g_a
    p_in   = p_a  - p_da
    p_out  = p_da - p_a
    d_in   = d_a  - d_da
    d_out  = d_da - d_a
    # Rimasti in squadra ma con un contratto diverso (nuovo contratto, DPE…). Il solo
    # scalare di un anno tra una stagione e l'altra non conta come cambio.
    g_cambiati = [gid for gid in g_da & g_a
                  if c_da[gid]["contratto_id"] != c_a[gid]["contratto_id"]
                  or c_da[gid]["importo"] != c_a[gid]["importo"]]

    if not any([g_in, g_out, p_in, p_out, d_in, d_out, g_cambiati]):
        await update.effective_message.reply_text(
            f"📊 <b>{team['nome']}</b>\n"
            f"{_fmt_data(data_da)} → {_fmt_data(data_a)}\n\n"
            "Nessuna variazione nel periodo.",
            parse_mode="HTML",
        )
        return

    righe = [
        f"📊 <b>{team['nome']}</b>",
        f"<i>{_fmt_data(data_da)} → {_fmt_data(data_a)}</i>",
        "",
    ]

    if g_in or p_in or d_in:
        righe.append("🟢 <b>IN</b>")
        for gid in g_in:
            g = db.get_giocatore(gid)
            nome = g["nome_common"] if g else f"#{gid}"
            motivo = _motivo_giocatore(team_id, gid, data_da, data_a, "in")
            righe.append(f"  • {html.escape(nome)} {_fmt_contratto(c_a.get(gid))} <i>({motivo})</i>")
        for pid in p_in:
            p = db.get_pick(pid)
            if p:
                rnd  = "1st" if p["round"] == 1 else "2nd"
                orig = (tm.get_team_by_id(p["proprietario_orig"]) or {}).get("nome", p["proprietario_orig"])
                prot = f" — {p['protezioni']}" if p.get("protezioni") else ""
                righe.append(f"  • {rnd} pick {p['anno']} by {orig}{prot} <i>(Trade)</i>")
        for did in d_in:
            r = db.get_rookie(did)
            if r:
                g = db.get_giocatore(r["giocatore_id"])
                nome = g["nome_common"] if g else f"#{r['giocatore_id']}"
                righe.append(f"  • Diritti di {nome} <i>(Draft)</i>")
        righe.append("")

    if g_out or p_out or d_out:
        righe.append("🔴 <b>OUT</b>")
        for gid in g_out:
            g = db.get_giocatore(gid)
            nome = g["nome_common"] if g else f"#{gid}"
            motivo = _motivo_giocatore(team_id, gid, data_da, data_a, "out")
            righe.append(f"  • {html.escape(nome)} {_fmt_contratto(c_da.get(gid))} <i>({motivo})</i>")
        for pid in p_out:
            p = db.get_pick(pid)
            if p:
                rnd  = "1st" if p["round"] == 1 else "2nd"
                orig = (tm.get_team_by_id(p["proprietario_orig"]) or {}).get("nome", p["proprietario_orig"])
                righe.append(f"  • {rnd} pick {p['anno']} by {orig} <i>(Trade)</i>")
        for did in d_out:
            r = db.get_rookie(did)
            if r:
                g = db.get_giocatore(r["giocatore_id"])
                nome = g["nome_common"] if g else f"#{r['giocatore_id']}"
                righe.append(f"  • Diritti di {nome} <i>(—)</i>")
        righe.append("")

    if g_cambiati:
        righe.append("🔁 <b>CONTRATTO CAMBIATO</b>")
        for gid in sorted(g_cambiati, key=lambda g: -(c_a[g]["importo"] or 0)):
            g = db.get_giocatore(gid)
            nome = g["nome_common"] if g else f"#{gid}"
            righe.append(f"  • {html.escape(nome)} {_fmt_contratto(c_da[gid])} → {_fmt_contratto(c_a[gid])}")

    await update.effective_message.reply_text(
        "\n".join(righe).rstrip(), parse_mode="HTML"
    )


def get_handlers() -> list:
    return [CommandHandler("team_diff", cmd_team_diff)]

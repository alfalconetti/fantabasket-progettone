"""
Promemoria spalmature (v3.9.1).

Regolamento: se un giocatore si ritira o va in un'altra lega, il suo stipendio non pesa
più neanche su chi l'aveva tagliato in passato. Il bot non può saperlo da solo: ogni
mese manda al gruppo admin i free agent con spalmature ancora attive, con l'ultima
partita rilevata su Basketball-Reference, così gli admin controllano chi si è ritirato
e lo chiudono con /ritiro_fa <nome>.

  job_report_spalmature   il 1° di ogni mese alle 9:45 → gruppo admin (solo se c'è qualcuno)
  /report_spalmature      lo stesso report su richiesta (admin)
"""
import html
import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
import settings
import teams as tm
from utils import ROME

logger = logging.getLogger(__name__)


def _righe_report() -> list[dict]:
    """Free agent (nessun contratto attivo) con spalmature dalla stagione corrente in poi."""
    stagione = settings.stagione_corrente()
    return db._q("""
        SELECT g.id, g.nome_common,
               json_agg(json_build_object('team', it.team_id, 'tot', it.tot) ORDER BY it.team_id) AS squadre,
               SUM(it.tot) AS totale,
               b.ultima, b.stagione_bref, b.team_bref,
               ct.data_ct
        FROM (SELECT giocatore_id, team_id, SUM(importo) AS tot FROM impatto_taglio
              WHERE stagione >= %s GROUP BY giocatore_id, team_id) it
        JOIN giocatori g ON g.id = it.giocatore_id
        LEFT JOIN LATERAL (SELECT timestamp AS ultima, stagione AS stagione_bref, team AS team_bref
                           FROM bref_stats WHERE nome_bref = g.nome_bref
                           ORDER BY timestamp DESC LIMIT 1) b ON TRUE
        LEFT JOIN LATERAL (SELECT MAX(timestamp) AS data_ct FROM movimenti_giocatori
                           WHERE giocatore_id = g.id AND tipo = 'decadimento'
                             AND note LIKE '%%Cam Thomas%%') ct ON TRUE
        WHERE NOT EXISTS (SELECT 1 FROM contratti c WHERE c.giocatore_id = g.id AND c.attivo = TRUE)
        GROUP BY g.id, g.nome_common, b.ultima, b.stagione_bref, b.team_bref, ct.data_ct
        ORDER BY b.ultima NULLS FIRST, g.nome_common
    """, (stagione,), many=True) or []


def _nome_team(team_id: str) -> str:
    t = tm.get_team_by_id(team_id)
    return t["nome"] if t else team_id


def testi_report() -> list[str]:
    """Messaggi del report (spezzati se lunghi). Lista vuota se non c'è nessuno."""
    righe = _righe_report()
    if not righe:
        return []
    blocchi = []
    for r in righe:
        squadre = ", ".join(f"{_nome_team(s['team'])} {s['tot']}M" for s in r["squadre"])
        if r["ultima"]:
            ultima = (f"ultima partita rilevata {r['ultima'].astimezone(ROME).strftime('%d/%m/%Y')}"
                      f" ({r['team_bref'] or '?'}, stagione {r['stagione_bref']})")
        else:
            ultima = "mai rilevato su Basketball-Reference"
        extra = (f"\n   ✂️ Cam Thomas il {r['data_ct'].astimezone(ROME).strftime('%d/%m/%Y')}"
                 if r["data_ct"] else "")
        blocchi.append(f"• <b>{html.escape(r['nome_common'])}</b> — {squadre}\n   {ultima}{extra}")
    testa = (f"🧾 <b>Spalmature di free agent</b> — {len(righe)} giocatori\n"
             f"<i>Se qualcuno si è ritirato o gioca in un'altra lega: /ritiro_fa nome "
             f"(le sue spalmature smettono di pesare).</i>\n\n")
    out, corrente = [], testa
    for b in blocchi:
        if len(corrente) + len(b) > 3800:
            out.append(corrente)
            corrente = ""
        corrente += b + "\n"
    out.append(corrente)
    return out


async def cmd_report_spalmature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not settings.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    for t in testi_report() or ["🧾 Nessun free agent con spalmature attive."]:
        await update.effective_message.reply_text(t, parse_mode="HTML")


async def job_report_spalmature(context: ContextTypes.DEFAULT_TYPE):
    """1° del mese, 9:45 — al gruppo admin, solo se c'è qualcuno."""
    try:
        gruppo = settings.admin_group_id()
        if not gruppo:
            return
        for t in testi_report():
            await context.bot.send_message(chat_id=gruppo, text=t, parse_mode="HTML")
    except Exception as e:
        logger.warning("Report spalmature: %s", e)


def get_handlers() -> list:
    return [CommandHandler("report_spalmature", cmd_report_spalmature)]

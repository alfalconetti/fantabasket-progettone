"""
Date di nascita dei giocatori (v3.7.0) — inserimento manuale, niente automatismi.

/set_nascita <nome> <GG-MM-AAAA>          un giocatore
/set_nascita                              più giocatori, uno per riga:
Nome Cognome GG-MM-AAAA
...
(anche GG/MM/AAAA o AAAA-MM-GG)

Abbinamento dei nomi (nomi.py), più severo del solito:
- nome esatto (senza accenti, maiuscole, punteggiatura) e unico → salvato subito;
- altrimenti candidati con somiglianza >= 0.88 o omonimi → bottoni da confermare
  (callback autosufficiente nasc:<gid>:<AAAAMMGG>, funziona anche dopo un riavvio);
- niente sopra la soglia → "non trovato".

/nascite_mancanti e report settimanale (lunedì 9:30, al dev): giocatori sotto
contratto senza data di nascita, in un blocco pronto da completare e rimandare.
"""
import html
import logging
import re
from datetime import date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
import settings
import teams as tm
import nomi

logger = logging.getLogger(__name__)

_RE_DATA = re.compile(r"^(?P<nome>.+?)\s+(?:(?P<g>\d{1,2})[-/.](?P<m>\d{1,2})[-/.](?P<a>\d{4})"
                      r"|(?P<a2>\d{4})-(?P<m2>\d{1,2})-(?P<g2>\d{1,2}))\s*$")


def _parse_riga(riga: str) -> tuple[str, date] | None:
    m = _RE_DATA.match(riga.strip())
    if not m:
        return None
    try:
        if m.group("a"):
            d = date(int(m.group("a")), int(m.group("m")), int(m.group("g")))
        else:
            d = date(int(m.group("a2")), int(m.group("m2")), int(m.group("g2")))
    except ValueError:
        return None
    if not (1960 <= d.year <= date.today().year - 15):
        return None
    return m.group("nome").strip(), d


def _anagrafica() -> list[dict]:
    return db._q("""SELECT g.id, g.nome_common, g.nome_bref, g.nome_yahoo, g.data_nascita, c.team_id
                    FROM giocatori g
                    LEFT JOIN contratti c ON c.giocatore_id = g.id AND c.attivo = TRUE""", many=True) or []


def _etichetta(g: dict) -> str:
    t = tm.get_team_by_id(g["team_id"]) if g.get("team_id") else None
    return g["nome_common"] + (f" ({t['nome']})" if t else "")


def _salva(gid: int, d: date) -> str:
    prima = db._qval("SELECT data_nascita FROM giocatori WHERE id = %s", (gid,))
    db._q("UPDATE giocatori SET data_nascita = %s WHERE id = %s", (d, gid))
    nome = (db.get_giocatore(gid) or {}).get("nome_common", str(gid))
    extra = f" <i>(prima {prima.strftime('%d/%m/%Y')})</i>" if prima and prima != d else ""
    return f"✅ {html.escape(nome)}: {d.strftime('%d/%m/%Y')}{extra}"


@settings.solo_privato
async def cmd_set_nascita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not settings.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    testo = update.effective_message.text or ""
    corpo = testo.split(None, 1)[1] if len(testo.split(None, 1)) > 1 else ""
    righe = [r for r in corpo.splitlines() if r.strip()]
    if not righe:
        await update.effective_message.reply_text(
            "Uso:\n/set_nascita Nome Cognome GG-MM-AAAA\n\noppure più giocatori, uno per riga:\n"
            "/set_nascita\nNome Cognome GG-MM-AAAA\nNome Cognome GG-MM-AAAA\n\n/nascite_mancanti per l'elenco da completare.")
        return

    anagrafica = _anagrafica()
    salvati, non_trovati, non_valide, da_scegliere = [], [], [], []
    for riga in righe:
        p = _parse_riga(riga)
        if not p:
            non_valide.append(riga.strip())
            continue
        nome, d = p
        esatti = nomi.esatti(nome, anagrafica)
        if len(esatti) == 1:
            salvati.append(_salva(esatti[0]["id"], d))
            continue
        candidati = esatti or [g for g, _ in nomi.simili(nome, anagrafica)]
        if candidati:
            da_scegliere.append((nome, d, candidati, bool(esatti)))
        else:
            non_trovati.append(nome)

    out = []
    if salvati:
        out += [f"<b>Salvate ({len(salvati)})</b>"] + salvati
    if non_trovati:
        out += ["", f"<b>❓ Non trovati ({len(non_trovati)})</b> — controlla il nome"] + \
               [f"• {html.escape(n)}" for n in non_trovati]
    if non_valide:
        out += ["", f"<b>⚠️ Righe non valide ({len(non_valide)})</b> — formato: Nome GG-MM-AAAA"] + \
               [f"• {html.escape(r)}" for r in non_valide]
    if da_scegliere:
        out += ["", f"🔎 {len(da_scegliere)} da confermare qui sotto."]
    await update.effective_message.reply_text("\n".join(out) or "Niente da fare.", parse_mode="HTML")

    for nome, d, candidati, omonimi in da_scegliere:
        kb = [[InlineKeyboardButton(_etichetta(g), callback_data=f"nasc:{g['id']}:{d.strftime('%Y%m%d')}")]
              for g in candidati]
        kb.append([InlineKeyboardButton("❌ Nessuno", callback_data="nasc:x")])
        motivo = "Ci sono omonimi" if omonimi else "Nessun nome esatto"
        await update.effective_message.reply_text(
            f"🔎 «{html.escape(nome)}» → {d.strftime('%d/%m/%Y')}\n<i>{motivo}: chi intendevi?</i>",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def cb_nascita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not settings.is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    await query.answer()
    if query.data == "nasc:x":
        await query.edit_message_text(query.message.text_html + "\n\n❌ Nessuno: non salvato.", parse_mode="HTML")
        return
    _, gid, ymd = query.data.split(":")
    d = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]))
    await query.edit_message_text(_salva(int(gid), d), parse_mode="HTML")


def testi_mancanti() -> list[str]:
    """Messaggi con i giocatori sotto contratto senza data di nascita (spezzati se lunghi)."""
    righe = db._q("""SELECT g.nome_common, c.team_id FROM contratti c
                     JOIN giocatori g ON g.id = c.giocatore_id
                     WHERE c.attivo = TRUE AND g.data_nascita IS NULL
                     ORDER BY c.team_id, g.nome_common""", many=True) or []
    if not righe:
        return []
    nomi_righe = [f"{r['nome_common']} " for r in righe]
    blocchi, corrente = [], []
    for n in nomi_righe:
        if sum(len(x) + 1 for x in corrente) + len(n) > 3300:
            blocchi.append(corrente)
            corrente = []
        corrente.append(n)
    blocchi.append(corrente)
    out = []
    for i, b in enumerate(blocchi):
        testa = (f"🎂 <b>Date di nascita mancanti</b> — {len(righe)} giocatori sotto contratto\n"
                 f"<i>Copia il blocco, aggiungi le date (GG-MM-AAAA) e rimandalo.</i>\n\n") if i == 0 else ""
        out.append(testa + f"<pre>{html.escape('/set_nascita' + chr(10) + chr(10).join(b))}</pre>")
    return out


async def cmd_nascite_mancanti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not settings.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    testi = testi_mancanti() or ["🎂 Nessuna data di nascita mancante."]
    for t in testi:
        await update.effective_message.reply_text(t, parse_mode="HTML")


async def job_report_nascite(context: ContextTypes.DEFAULT_TYPE):
    """Lunedì 9:30 — al dev, solo se manca qualcosa."""
    try:
        if settings.dev_id():
            for t in testi_mancanti():
                await context.bot.send_message(chat_id=settings.dev_id(), text=t, parse_mode="HTML")
    except Exception as e:
        logger.warning("Report date di nascita: %s", e)


def get_handlers() -> list:
    return [
        CommandHandler("set_nascita", cmd_set_nascita),
        CommandHandler("nascite_mancanti", cmd_nascite_mancanti),
        CallbackQueryHandler(cb_nascita, pattern=r"^nasc:(?:x|\d+:\d{8})$"),
    ]

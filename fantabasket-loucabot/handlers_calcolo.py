"""Comandi e job del calcolo: tabellini, infortunati, abbinamento con ESPN, fantapunti.

Admin: /tabellini (anche snapshot degli infortunati), /espn_giocatori, /espn_mancanti, /espn_abbina ID_GIOCATORE ID_ESPN, /fantapunti [N]
Job:   tabellini e abbinamenti nella sincronizzazione delle 8:30 (handlers.job_sync),
       snapshot degli infortunati ogni 4 ore e 30 minuti prima della prima partita del giorno.
"""
import difflib
import html
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import calcolo
import calendario as cal
import config
import db
import nba

logger = logging.getLogger(__name__)
e = html.escape


async def _solo_admin(update) -> bool:
    if config.is_admin(update.effective_user.id):
        return True
    await update.effective_message.reply_text("⛔ Solo admin.")
    return False


async def aggiorna_tabellini() -> dict:
    """Tabellini delle partite finite che non li hanno, poi abbinamento automatico dei giocatori nuovi."""
    from datetime import datetime
    r = await nba.scarica_tabellini(db.partite_senza_tabellino(fino=datetime.now(nba.ET).date()))
    r["abbinamento"] = calcolo.abbina_auto(db.atleti_espn_visti())
    return r


def testo_tabellini(r: dict) -> str:
    t = f"{r['partite']} tabellini ({r['giocatori']} righe)"
    if r["errori"]:
        t += f", ⚠️ {len(r['errori'])} non scaricati"
    if r.get("abbinamento", {}).get("nuovi"):
        t += f", {r['abbinamento']['nuovi']} giocatori abbinati a ESPN"
    return t


async def snapshot_infortuni() -> str:
    try:
        r = await nba.scarica_infortuni()
        return f"{r['giocatori']} infortunati"
    except Exception as err:
        logger.warning("Infortunati: %s", err)
        return f"⚠️ infortunati non scaricati ({type(err).__name__}: {e(str(err))[:150]})"


async def job_prepartita(context: ContextTypes.DEFAULT_TYPE):
    """Ogni 10 minuti: uno snapshot degli infortunati 30-40 minuti prima della prima partita NBA
    del giorno (il report subito prima delle partite), una volta sola."""
    from datetime import datetime, timedelta, timezone
    ora_ = datetime.now(timezone.utc)
    r = db.q("SELECT MIN(inizio) AS t FROM nba_partite WHERE inizio > %s AND inizio <= %s",
             (ora_, ora_ + timedelta(minutes=40)), one=True)
    if not r or not r["t"]:
        return
    gia = db.q("SELECT 1 FROM nba_infortuni WHERE preso >= %s LIMIT 1", (r["t"] - timedelta(minutes=45),), one=True)
    if not gia:
        await job_infortuni(context)


async def job_infortuni(context: ContextTypes.DEFAULT_TYPE):
    from handlers import log
    esito = await snapshot_infortuni()
    if esito.startswith("⚠️"):
        await log(context.bot, f"🩹 Snapshot infortunati: {esito}")


async def cmd_tabellini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _solo_admin(update):
        return
    da_fare = db.partite_senza_tabellino()
    await update.effective_message.reply_text(f"⏳ Scarico {len(da_fare)} tabellini da ESPN (circa un secondo l'uno)…")
    r = await aggiorna_tabellini()
    inf = await snapshot_infortuni()
    await update.effective_message.reply_text("✅ " + testo_tabellini(r) + f"; snapshot: {inf}"
                                              + ("\n" + "\n".join(e(x) for x in r["errori"][:10]) if r["errori"] else ""),
                                              parse_mode="HTML")
    from handlers import log, _chi
    await log(context.bot, f"📊 /tabellini di {_chi(update)}: {testo_tabellini(r)}; snapshot: {inf}")


async def cmd_espn_giocatori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scarica i roster delle 30 squadre da ESPN e abbina i nomi all'anagrafica."""
    if not await _solo_admin(update):
        return
    await update.effective_message.reply_text("⏳ Scarico i roster NBA da ESPN (30 richieste, mezzo minuto)…")
    atleti = await nba.scarica_giocatori()
    db.salva_atleti(atleti)
    r = calcolo.abbina_auto(db.atleti_espn_visti())
    mancanti = [x for x in db.giocatori_a_roster(config.stagione()) if not x["atleta"]]
    righe = [f"✅ {len(atleti)} giocatori NBA da ESPN, {r['nuovi']} abbinati ora all'anagrafica.",
             f"A roster nella lega senza id ESPN: <b>{len(mancanti)}</b>" + (" → /espn_mancanti" if mancanti else " 🎉")]
    if r["ambigui"]:
        righe.append(f"Nomi ambigui (da abbinare a mano): {e(', '.join(r['ambigui'][:15]))}")
    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")
    from handlers import log, _chi
    await log(context.bot, f"👥 /espn_giocatori di {_chi(update)}: {len(atleti)} giocatori ESPN, {r['nuovi']} abbinati, "
                           f"{len(mancanti)} a roster senza id")


async def cmd_espn_mancanti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _solo_admin(update):
        return
    mancanti = [x for x in db.giocatori_a_roster(config.stagione()) if not x["atleta"]]
    if not mancanti:
        await update.effective_message.reply_text("✅ Tutti i giocatori a roster hanno l'id ESPN.")
        return
    gia = set(db.abbinamenti().values())
    liberi = {a: n for a, n in db.atleti_espn_visti().items() if a not in gia}
    per_norm = {}
    for a, n in liberi.items():
        per_norm.setdefault(calcolo.norm(n), []).append((a, n))
    righe = [f"❔ <b>Giocatori a roster senza id ESPN</b> ({len(mancanti)})",
             "<i>/espn_abbina ID_GIOCATORE ID_ESPN — l'id ESPN è il numero nel link del giocatore su espn.com</i>", ""]
    for x in mancanti:
        simili = difflib.get_close_matches(calcolo.norm(x["nome_common"]), list(per_norm), n=2, cutoff=0.6)
        prop = "; ".join(f"{e(n)} <code>{a}</code>" for s in simili for a, n in per_norm[s])
        righe.append(f"• <code>{x['giocatore_id']}</code> {e(x['nome_common'])} ({e(config.nome(x['team_id']))})"
                     + (f" → forse {prop}" if prop else ""))
    from shared.messaggi import manda_lungo
    await manda_lungo(context.bot, update.effective_chat.id, "\n".join(righe), "espn-mancanti")


async def cmd_espn_abbina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _solo_admin(update):
        return
    args = context.args or []
    if len(args) != 2 or not all(x.isdigit() for x in args):
        await update.effective_message.reply_text("Uso: /espn_abbina ID_GIOCATORE ID_ESPN (numeri, da /espn_mancanti)")
        return
    gid, atleta = int(args[0]), args[1]
    g = next((x for x in db.giocatori_anagrafica() if x["id"] == gid), None)
    if not g:
        await update.effective_message.reply_text(f"Nessun giocatore con id {gid} in anagrafica.")
        return
    nome_espn = db.atleti_espn_visti().get(atleta, "?")
    db.abbina(gid, atleta, nome_espn, "admin")
    await update.effective_message.reply_text(
        f"✅ {e(g['nome_common'])} ↔ ESPN {atleta} ({e(nome_espn)})", parse_mode="HTML")
    from handlers import log, _chi
    await log(context.bot, f"🔗 {_chi(update)} abbina {e(g['nome_common'])} (id {gid}) a ESPN {atleta} ({e(nome_espn)})")


def testo_fantapunti(stagione: str, g: dict) -> str:
    roster = db.giocatori_a_roster(stagione)
    p = calcolo.punteggio_giocatori(stagione, g, [x["atleta"] for x in roster if x["atleta"]])
    righe = [f"📊 <b>Fantapunti giornata {g['numero']}</b> · {g['dal']:%d/%m} – {g['al']:%d/%m}",
             "<i>Tutti i giocatori a roster (il calcolo coi quintetti e le panchine di IPanchinari è da fare).</i>"]
    simbolo = {"partite": "", "media": "📉 ", "zero": ""}
    for team in config.squadre():
        suoi = [x for x in roster if x["team_id"] == team["id"]]
        if not suoi:
            continue
        righe += ["", f"<b>{e(team['nome'])}</b>"]
        for x in sorted(suoi, key=lambda x: -(p.get(x["atleta"], {}).get("fp") or 0)):
            if not x["atleta"]:
                righe.append(f"• {e(x['nome_common'])} {x['ruolo'] or ''}: ❔ senza id ESPN")
                continue
            q = p[x["atleta"]]
            nota = f" <i>({e(q['nota'])})</i>" if q["nota"] and q["come"] != "partite" or len(q["partite"]) > 1 else ""
            righe.append(f"• {simbolo[q['come']]}{e(x['nome_common'])} {x['ruolo'] or ''}: <b>{q['fp']:.2f}</b>{nota}")
    return "\n".join(righe)


async def cmd_fantapunti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _solo_admin(update):
        return
    s = config.stagione()
    n = None
    if context.args and context.args[0].isdigit():
        n = int(context.args[0])
    g = db.giornata(s, n) if n else cal.corrente(s)
    if not g:
        await update.effective_message.reply_text("Giornata non trovata.")
        return
    from shared.messaggi import manda_lungo
    await manda_lungo(context.bot, update.effective_chat.id, testo_fantapunti(s, g), f"fantapunti-G{g['numero']}",
                      riassunto=f"📊 Fantapunti giornata {g['numero']}")


async def cmd_dev_giornata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dev_giornata [N]: tutto quello che il bot sa di una giornata (la corrente se manca N)."""
    if not (config.dev_id() and update.effective_user.id == config.dev_id()):
        return
    s = config.stagione()
    n = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    g = db.giornata(s, n) if n else cal.corrente(s)
    if not g:
        await update.effective_message.reply_text("Giornata non trovata.")
        return
    partite = db.q("SELECT stato, COUNT(*) AS n, COUNT(tabellino) AS t FROM nba_partite WHERE data_et BETWEEN %s AND %s "
                   "AND tipo = ANY(%s) GROUP BY stato ORDER BY stato", (g["dal"], g["al"], [2, 3, 5]), many=True) or []
    snap = db.q("SELECT giorno, COUNT(DISTINCT preso) AS n FROM nba_infortuni WHERE giorno BETWEEN %s AND %s "
                "GROUP BY giorno ORDER BY giorno", (g["dal"], g["al"]), many=True) or []
    ris = db.q("SELECT COUNT(*) AS n, COUNT(convalidato) AS c FROM lega_risultati WHERE stagione = %s AND giornata = %s",
               (s, g["numero"]), one=True)
    righe = [f"🔧 <b>Giornata {g['numero']}</b> ({g['tipo']}) · {g['dal']} → {g['al']} (giorni ET)",
             f"Scadenza: {cal.ora(g['prima_partita'])} · calcolata {g['calcolato'] or '—'}",
             f"Media calcolata: {', '.join(g['media']) if g['media'] is not None else 'non calcolata'} · "
             f"nel calendario: {', '.join(g['media_file']) or 'nessuno'}",
             "Partite NBA: " + (", ".join(f"{p['stato'].replace('STATUS_', '').lower()} {p['n']} (tabellini {p['t']})"
                                          for p in partite) or "nessuna"),
             "Snapshot infortunati: " + (", ".join(f"{f['giorno']:%d/%m} {f['n']}" for f in snap) or "nessuno"),
             f"Risultati: {ris['n']} (convalidati {ris['c']})"]
    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")


def get_handlers() -> list:
    return [
        CommandHandler("dev_giornata", cmd_dev_giornata),
        CommandHandler("tabellini", cmd_tabellini),
        CommandHandler("espn_giocatori", cmd_espn_giocatori),
        CommandHandler("espn_mancanti", cmd_espn_mancanti),
        CommandHandler("espn_abbina", cmd_espn_abbina),
        CommandHandler("fantapunti", cmd_fantapunti),
    ]

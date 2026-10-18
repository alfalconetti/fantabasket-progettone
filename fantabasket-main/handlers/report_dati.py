"""
/report_dati (admin, v5.10.0): la salute dei dati, in un file Markdown. Raccoglie in un posto i
controlli che oggi sono sparsi (/espn_mancanti di loucabot, /nascite_mancanti, la coerenza
notturna, bref) e ne aggiunge qualcuno, per trovare prima della giornata quello che romperebbe il
calcolo o i controlli. Anche dal pannello admin: «🩺 Controllo dati» (callback rdati:md).

Sezioni (ognuna con ✅ o il numero di cose da guardare):
  1. Calcolo: giocatori a roster senza id ESPN (i loro punti non contano, 0).
  2. Ruoli: senza posizioni eleggibili, senza ruolo (in stagione), ruolo non più tra le eleggibili,
     squadre che non possono rispettare i minimi.
  3. Squadre: sopra il cap, sotto il floor (in stagione), troppi o troppo pochi giocatori.
  4. Contratti: importo non positivo, 10-day scaduti da più di due giorni e ancora attivi (i contratti finiti ancora attivi li segnala la coerenza, al punto 6).
  5. Anagrafica: senza data di nascita, mai visti su basketball-reference (a parte, come ℹ️, i rookie al
     primo anno, cioè del draft della stagione, e gli esordienti NBA con 0 anni di esperienza su ESPN:
     è normale finché non debuttano).
  6. Registro: il controllo di coerenza (database.controlli_coerenza).
Solo lettura: non corregge niente.
"""
import asyncio
import io
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db
import settings
import teams as tm
from shared import regole, ruoli_core as core

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
FASI_STAGIONE = {"regular-season-fa", "regular-season-deadline", "playoff"}


def _md(x) -> str:
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")


def _roster() -> list[dict]:
    return db._q("""SELECT c.id AS contratto_id, c.giocatore_id, c.team_id, c.importo, c.anni_originali, c.stagione_firma,
                           c.tipo, c.scadenza_10day, g.nome_common, g.nome_bref, g.espn_id, g.data_nascita,
                           (SELECT p.posizioni FROM posizioni_attuali p WHERE p.giocatore_id = g.id) AS posizioni,
                           (SELECT r.ruolo FROM ruolo_attuale r WHERE r.giocatore_id = g.id AND r.stagione = %s) AS ruolo
                    FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                    WHERE c.attivo ORDER BY c.team_id, g.nome_common""", (settings.stagione_corrente(),), many=True) or []


def controlli(adesso: datetime | None = None) -> list[tuple[str, list[str], list[list[str]], str]]:
    """[(titolo, intestazione, righe, nota)]: una tabella per controllo, righe vuote = tutto a posto."""
    adesso = adesso or datetime.now(timezone.utc)
    s = settings.stagione_corrente()
    fase = settings.fase()
    in_stagione = fase in FASI_STAGIONE
    squadre = {t["id"]: t for t in tm.get_all_teams()}
    nome = lambda tid: (squadre.get(tid) or {}).get("nome", tid)
    rows = _roster()
    out = []

    # 1. calcolo
    out.append(("Senza id ESPN (i loro punti non contano)", ["Squadra", "Giocatore"],
                [[nome(r["team_id"]), r["nome_common"]] for r in rows if not r["espn_id"]],
                "Si abbinano su loucabot: /espn_mancanti, /espn_abbina ID_GIOCATORE ID_ESPN."))

    # 2. ruoli
    out.append(("Senza posizioni eleggibili", ["Squadra", "Giocatore"],
                [[nome(r["team_id"]), r["nome_common"]] for r in rows if not (r["posizioni"] or "").strip()],
                "Si aggiungono con /import_posizioni_eleggibili o /set_posizioni_eleggibili."))
    if in_stagione:
        out.append(("Senza ruolo (in stagione)", ["Squadra", "Giocatore", "Eleggibili"],
                    [[nome(r["team_id"]), r["nome_common"], r["posizioni"] or "—"] for r in rows
                     if not r["ruolo"] and r["tipo"] != "10day"],
                    "Dopo trade e firme: pannello → ⏳ Ruoli in sospeso (dopo 48 ore il bot estrae)."))
    out.append(("Ruolo non più tra le eleggibili", ["Squadra", "Giocatore", "Ruolo", "Eleggibili"],
                [[nome(r["team_id"]), r["nome_common"], r["ruolo"], r["posizioni"]] for r in rows
                 if r["ruolo"] and (r["posizioni"] or "").strip() and r["ruolo"] not in r["posizioni"].split(",")],
                "Yahoo ha tolto la posizione: il ruolo resta valido finché non si cambia (cambio forzato se serve)."))
    m = regole.minimi_ruolo()
    defi = []
    for tid in squadre:
        d = core.deficit_team(db._q, tid, s)
        if d:
            defi.append([nome(tid), str(d)])
    out.append((f"Minimi dei ruoli impossibili ({m['G']} G, {m['F']} F, {m['C']} C)", ["Squadra", "Posti mancanti"], defi,
                "Anche con la scelta migliore dei ruoli mancanti. Dettaglio: /report_ruoli."))

    # 3. squadre
    cap_r, slot_r, n_r = [], [], []
    for tid, t in squadre.items():
        cap = db.cap_occupato_team(tid, s)
        limite = settings.cap_limite_team(t)
        if cap > limite:
            cap_r.append([t["nome"], f"{cap}M", f"tetto {limite}M"])
        elif in_stagione and cap < settings.salary_floor():
            cap_r.append([t["nome"], f"{cap}M", f"floor {settings.salary_floor()}M"])
        ros = db.get_roster_team(tid) or []
        n = db.slot_occupati(ros)
        if n > settings.max_roster():
            slot_r.append([t["nome"], str(n), f"massimo {settings.max_roster()}"])
        elif in_stagione and n < settings.min_roster():
            slot_r.append([t["nome"], str(n), f"minimo {settings.min_roster()}"])
    out.append(("Cap fuori dai limiti", ["Squadra", "Cap occupato", "Limite"], cap_r, ""))
    out.append(("Giocatori a roster fuori dai limiti (slot)", ["Squadra", "Slot occupati", "Limite"], slot_r,
                "Slot: DPE approvate prima della deadline e 10-day non contano."))

    # 4. contratti
    con = []
    for r in rows:
        if r["tipo"] == "10day":
            if r["scadenza_10day"] and r["scadenza_10day"] < adesso - timedelta(days=2):
                con.append([nome(r["team_id"]), r["nome_common"], "10-day",
                            f"scaduto il {r['scadenza_10day'].astimezone(ROMA):%d/%m} e ancora attivo"])
            continue
        # contratti finiti ancora attivi (x0 fuori dalle fasi dei rinnovi): li segnala già la coerenza (sezione 6)
        if (r["importo"] or 0) <= 0:
            con.append([nome(r["team_id"]), r["nome_common"], f"{r['importo']}", "importo non positivo"])
        # niente controllo degli anni minimi per importo: vale per le firme all'asta (lo fa il bot aste),
        # non per rinnovi e contratti storici (sulla copia vera del 12/10 dava 17 falsi allarmi)
    out.append(("Contratti da guardare", ["Squadra", "Giocatore", "Contratto", "Cosa"], con,
                "Da verificare: possono essere casi voluti (contratti storici, decisioni degli admin)."))

    # 5. anagrafica
    out.append(("Senza data di nascita", ["Squadra", "Giocatore"],
                [[nome(r["team_id"]), r["nome_common"]] for r in rows if not r["data_nascita"]],
                "Servono per età e classifiche: /set_nascita, /nascite_mancanti."))
    try:
        mai, rookie = [], []
        for r in senza_bref(s):
            if r["anno_draft"] == s:
                rookie.append([nome(r["team_id"]), r["nome_common"], f"rookie al primo anno (draft {s})"])
            elif r["esperienza"] == 0:
                rookie.append([nome(r["team_id"]), r["nome_common"], "esordiente NBA (ESPN: 0 anni di esperienza)"])
            else:
                perche = ([f"rookie del draft {r['anno_draft']}"] if r["anno_draft"] else []) + \
                         ([f"ESPN: {r['esperienza']} anni in NBA"] if r["esperienza"] else [])
                mai.append([nome(r["team_id"]), r["nome_common"], "; ".join(perche) or "—"])
    except Exception as err:
        mai, rookie = [["?", f"controllo non riuscito: {err}", ""]], []
    out.append(("Mai visti su basketball-reference", ["Squadra", "Giocatore", "Note"], mai,
                "Senza fantamedia. Di solito: non ha giocato nelle stagioni che ci sono su bref (infortunio lungo, "
                "senza squadra), oppure il nome dell'anagrafica è diverso da quello di bref (si abbina dal report bref "
                "delle 9, coi bottoni 🔗)."))
    out.append(("Mai visti su bref: rookie e esordienti", ["Squadra", "Giocatore", "Perché"], rookie,
                "Normale finché non debuttano: compaiono su bref alla prima partita giocata.", "info"))

    # 6. registro
    try:
        reg = [[p] for p in db.controlli_coerenza()]
    except Exception as err:
        reg = [[f"controllo non riuscito: {err}"]]
    out.append(("Coerenza del registro (transazioni)", ["Problema"], reg, "Lo stesso controllo della notte (/dev_coerenza)."))
    return out


def senza_bref(stagione: str) -> list[dict]:
    """A roster e mai visti su bref, con l'anno del draft del fantabasket (tabella rookie) e gli anni
    di esperienza NBA dai roster ESPN (nba_atleti.esperienza di loucabot, se c'è)."""
    esp = "NULL::int"
    if db._q("""SELECT 1 AS x FROM information_schema.columns WHERE table_name = 'nba_atleti' AND column_name = 'esperienza'""",
             one=True):
        esp = "(SELECT a.esperienza FROM nba_atleti a WHERE a.atleta = g.espn_id)"
    return db._q(f"""SELECT g.id, g.nome_common, c.team_id,
                            (SELECT r.anno_draft FROM rookie r WHERE r.giocatore_id = g.id ORDER BY r.anno_draft DESC LIMIT 1) AS anno_draft,
                            {esp} AS esperienza
                     FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                     WHERE c.attivo AND NOT EXISTS (SELECT 1 FROM bref_stats b WHERE b.nome_bref = g.nome_bref)
                     ORDER BY c.team_id, g.nome_common""", many=True) or []


def _esito(sez: tuple) -> str:
    r, info = sez[2], len(sez) > 4 and sez[4] == "info"
    if not r:
        return "✅"
    return f"ℹ️ {len(r)}" if info else f"⚠️ {len(r)}"


def report(adesso: datetime | None = None) -> str:
    adesso = adesso or datetime.now(timezone.utc)
    try:
        from handlers.admin_panel import FASI_LABEL
        fase = FASI_LABEL.get(settings.fase(), settings.fase())
    except Exception:
        fase = settings.fase()
    sez = controlli(adesso)
    da_guardare = sum(1 for x in sez if x[2] and _esito(x).startswith("⚠️"))
    righe = [f"# Controllo dei dati — stagione {settings.stagione_corrente()}", "",
             f"Fase: {fase} · {adesso.astimezone(ROMA):%d/%m/%Y %H:%M} (ora italiana)  ",
             f"**{da_guardare}** controlli su {len(sez)} con qualcosa da guardare. Solo lettura: il bot non corregge niente.", "",
             "## Riepilogo", "", "| Controllo | Esito |", "|---|---|"]
    righe += [f"| {_md(x[0])} | {_esito(x)} |" for x in sez]
    for x in sez:
        t, testa, r, nota = x[:4]
        righe += ["", f"## {_esito(x).split()[0]} {_md(t)}", ""]
        if nota:
            righe += [f"_{_md(nota)}_", ""]
        if not r:
            righe.append("Tutto a posto.")
            continue
        righe += ["| " + " | ".join(testa) + " |", "|" + "---|" * len(testa)]
        righe += ["| " + " | ".join(_md(x) for x in riga) + " |" for riga in r]
    return "\n".join(righe) + "\n"


async def _manda(bot, chat_id: int):
    adesso = datetime.now(timezone.utc)
    testo = await asyncio.to_thread(report, adesso)     # tante query: in un thread, il bot resta libero
    await bot.send_document(chat_id=chat_id, document=io.BytesIO(testo.encode("utf-8")),
                            filename=f"dati-{adesso.astimezone(ROMA):%Y%m%d-%H%M}.md",
                            caption=f"🩺 Controllo dei dati ({adesso.astimezone(ROMA):%d/%m %H:%M})")


async def cmd_report_dati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not settings.is_admin(update.effective_user.id):
        return
    await _manda(context.bot, update.effective_chat.id)


async def cb_report_dati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not settings.is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer("Preparo il controllo…")
    await _manda(context.bot, q.message.chat_id)


def get_handlers() -> list:
    return [CommandHandler("report_dati", cmd_report_dati), CallbackQueryHandler(cb_report_dati, pattern=r"^rdati:md$")]

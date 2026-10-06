"""
Posizioni eleggibili (Yahoo) — import da CSV.

  /import_posizioni_eleggibili (admin, privato) → invio file CSV → anteprima → conferma
  /set_posizioni_eleggibili <nome> <PG,SG> (admin) → correzione puntuale (fonte 'manuale')

CSV (prodotto dallo script in console del browser sulle pagine giocatori Yahoo):
    yahoo_id;nome;team;posizioni
    5352;Nikola Jokić;DEN;C

Abbinamento al DB, in ordine:
  1. yahoo_id già salvato su giocatori
  2. nome esatto (nome_yahoo, nome_common, nome_bref), normalizzato
  3. nome senza suffissi (Jr., III, ...)
  4. iniziale + cognome ("K. Caldwell-Pope"), solo se univoco

Tabella posizioni_eleggibili = event log: si aggiunge una riga SOLO se il set di
posizioni di un giocatore cambia (prima riga = primo import). Vista posizioni_attuali.
L'import salva su giocatori anche yahoo_id e nome_yahoo.
Tutto in un'unica transazione.
"""
import csv
import io
import logging
import re
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters,
)

import database as db
import settings
from settings import solo_privato
from utils import normalizza

logger = logging.getLogger(__name__)

ATTENDI_FILE, CONFERMA = range(2)
POS_ORDINE = ["PG", "SG", "G", "SF", "PF", "F", "C"]
_SUFFISSI  = {"jr", "sr", "ii", "iii", "iv", "v"}
_MAX_LISTA = 25


# ── logica pura (testabile) ───────────────────────────────────────────────────

def posizioni_canoniche(raw: str) -> str | None:
    """'SF, PG' → 'PG,SF'. None se contiene posizioni non valide o è vuota."""
    pos = {p.strip().upper() for p in (raw or "").split(",") if p.strip()}
    if not pos or not pos <= set(POS_ORDINE):
        return None
    return ",".join(p for p in POS_ORDINE if p in pos)


def _chiave(nome: str) -> str:
    n = normalizza(nome).replace(".", " ").replace("'", "").replace("’", "")
    return " ".join(n.split())


def _senza_suffisso(k: str) -> str:
    t = k.split()
    while len(t) > 1 and t[-1] in _SUFFISSI:
        t.pop()
    return " ".join(t)


def nome_abbreviato(nome: str) -> bool:
    """'K. Caldwell-Pope': forma accorciata della lista giocatori Yahoo, non il nome vero."""
    return bool(re.match(r"^[A-Z]\. ", nome or ""))


def leggi_csv(contenuto: str) -> tuple[list, list]:
    """Ritorna (righe valide, errori)."""
    righe, errori = [], []
    reader = csv.DictReader(io.StringIO(contenuto.lstrip("\ufeff")), delimiter=";")
    attese = {"yahoo_id", "nome", "team", "posizioni"}
    if not reader.fieldnames or not attese <= {f.strip() for f in reader.fieldnames}:
        return [], [f"Intestazione non valida: serve {';'.join(sorted(attese))}"]
    for n, r in enumerate(reader, start=2):
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        pos = posizioni_canoniche(r["posizioni"])
        if not r["yahoo_id"].isdigit():
            errori.append(f"riga {n}: yahoo_id non valido ({r['yahoo_id']!r})")
        elif not r["nome"]:
            errori.append(f"riga {n}: nome mancante")
        elif pos is None:
            errori.append(f"riga {n}: posizioni non valide ({r['posizioni']!r})")
        else:
            righe.append({**r, "yahoo_id": int(r["yahoo_id"]), "posizioni": pos})
    return righe, errori


def pianifica_import(righe: list, giocatori: list, attuali: dict, sotto_contratto: set) -> dict:
    """
    giocatori: dict con id, nome_common, nome_bref, nome_yahoo, yahoo_id
    attuali:   {giocatore_id: 'PG,SG'} (ultima riga di posizioni_eleggibili)
    Non scrive nulla: restituisce il piano.
    """
    per_yid = {g["yahoo_id"]: g["id"] for g in giocatori if g.get("yahoo_id")}
    yid_di  = {g["id"]: g.get("yahoo_id") for g in giocatori}
    nome_y  = {g["id"]: g.get("nome_yahoo") for g in giocatori}
    nome_c  = {g["id"]: g["nome_common"] for g in giocatori}

    esatto, base, iniz = defaultdict(set), defaultdict(set), defaultdict(set)
    for g in giocatori:
        for campo in ("nome_yahoo", "nome_common", "nome_bref"):
            if g.get(campo):
                k = _chiave(g[campo]); esatto[k].add(g["id"])
                b = _senza_suffisso(k); base[b].add(g["id"])
                t = b.split()
                if len(t) >= 2:
                    iniz[(t[0][0], " ".join(t[1:]))].add(g["id"])

    piano = {"aggiornamenti": [], "non_trovati": [], "ambigui": [], "conflitti": [],
             "metodi": defaultdict(int)}
    usati = {}
    for r in righe:
        gid, metodo = per_yid.get(r["yahoo_id"]), "yahoo_id"
        if gid is None:
            k = _chiave(r["nome"]); b = _senza_suffisso(k)
            m = re.match(r"^([a-z]) (.+)$", b)
            fasi = (("nome", esatto.get(k, set())),
                    ("senza suffisso", base.get(b, set())),
                    ("iniziale+cognome", iniz.get((m.group(1), m.group(2)), set()) if m else set()))
            for metodo, cand in fasi:
                if len(cand) == 1:
                    gid = next(iter(cand)); break
                if len(cand) > 1:
                    piano["ambigui"].append((r, sorted(f"{nome_c[c]} [id {c}]" for c in cand))); break
            if gid is None:
                if not any(len(c) > 1 for _, c in fasi):
                    piano["non_trovati"].append(r)
                continue
            if yid_di.get(gid) and yid_di[gid] != r["yahoo_id"]:
                piano["conflitti"].append((r, f"{nome_c[gid]} ha già yahoo_id {yid_di[gid]}"))
                continue
        if gid in usati:
            piano["conflitti"].append((r, f"{nome_c[gid]} già abbinato a '{usati[gid]}'"))
            continue
        usati[gid] = r["nome"]
        piano["metodi"][metodo] += 1

        vecchie = attuali.get(gid)
        stato = "nuovo" if vecchie is None else ("invariato" if vecchie == r["posizioni"] else "cambiato")
        # Il nome accorciato della lista Yahoo non va in nome_yahoo: si tiene
        # quello già salvato o, se manca, il nome comune
        nome_yahoo = (nome_y.get(gid) or nome_c[gid]) if nome_abbreviato(r["nome"]) else r["nome"]
        piano["aggiornamenti"].append({
            "giocatore_id": gid, "nome": nome_c[gid], "riga": r, "metodo": metodo,
            "vecchie": vecchie, "nuove": r["posizioni"], "stato": stato,
            "nome_yahoo": nome_yahoo,
            "set_yahoo": yid_di.get(gid) != r["yahoo_id"] or nome_y.get(gid) != nome_yahoo,
        })

    piano["sotto_contratto_mancanti"] = sorted(
        nome_c[g] for g in sotto_contratto if g not in usati and g in nome_c)
    return piano


def riepilogo(piano: dict, righe_tot: int, errori: list) -> str:
    agg = piano["aggiornamenti"]
    conta = lambda s: sum(1 for a in agg if a["stato"] == s)
    m = piano["metodi"]
    out = [
        "📥 <b>Anteprima import posizioni</b>\n",
        f"Righe valide: <b>{righe_tot}</b>" + (f" (scartate {len(errori)})" if errori else ""),
        f"Abbinate: <b>{len(agg)}</b> — " + ", ".join(f"{k} {v}" for k, v in m.items()),
        f"• nuove: <b>{conta('nuovo')}</b> · cambiate: <b>{conta('cambiato')}</b> · invariate: {conta('invariato')}",
        f"Non trovate: {len(piano['non_trovati'])} · ambigue: {len(piano['ambigui'])} · conflitti: {len(piano['conflitti'])}",
    ]
    cambiati = [a for a in agg if a["stato"] == "cambiato"]
    if cambiati:
        out.append("\n🔄 <b>Posizioni cambiate</b> (per la Erminio rule):")
        for a in cambiati[:_MAX_LISTA]:
            v, n = set(a["vecchie"].split(",")), set(a["nuove"].split(","))
            diff = " ".join([f"+{p}" for p in POS_ORDINE if p in n - v] +
                            [f"−{p}" for p in POS_ORDINE if p in v - n])
            out.append(f"• {a['nome']}: {a['vecchie']} → {a['nuove']} ({diff})")
        if len(cambiati) > _MAX_LISTA:
            out.append(f"… e altre {len(cambiati) - _MAX_LISTA}")
    if piano["sotto_contratto_mancanti"]:
        out.append(f"\n⚠️ <b>Sotto contratto senza posizioni ({len(piano['sotto_contratto_mancanti'])})</b>:")
        out.append(", ".join(piano["sotto_contratto_mancanti"][:_MAX_LISTA]))
    for titolo, lista in (("❓ Ambigue", piano["ambigui"]), ("⛔ Conflitti", piano["conflitti"])):
        if lista:
            out.append(f"\n{titolo}:")
            for r, info in lista[:_MAX_LISTA]:
                info = " / ".join(info) if isinstance(info, list) else info
                out.append(f"• {r['nome']} ({r['team']}): {info}")
    if errori:
        out.append("\n🚫 Righe scartate:\n" + "\n".join(errori[:10]))
    return "\n".join(out)


# ── DB ────────────────────────────────────────────────────────────────────────

def carica_dati() -> tuple[list, dict, set]:
    giocatori = db._q("SELECT id, nome_common, nome_bref, nome_yahoo, yahoo_id FROM giocatori", many=True) or []
    attuali = {r["giocatore_id"]: r["posizioni"]
               for r in db._q("SELECT giocatore_id, posizioni FROM posizioni_attuali", many=True) or []}
    sotto = {r["giocatore_id"] for r in db._q("SELECT giocatore_id FROM roster_attuale", many=True) or []}
    return giocatori, attuali, sotto


def applica_import(piano: dict, fonte: str = "import") -> tuple[int, int]:
    """Scrive tutto in un'unica transazione. Ritorna (righe posizioni inserite, giocatori aggiornati)."""
    inserite = aggiornati = 0
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for a in piano["aggiornamenti"]:
                if a["set_yahoo"]:
                    cur.execute("UPDATE giocatori SET yahoo_id = %s, nome_yahoo = %s WHERE id = %s",
                                (a["riga"]["yahoo_id"], a["nome_yahoo"], a["giocatore_id"]))
                    aggiornati += 1
                if a["stato"] != "invariato":
                    cur.execute("INSERT INTO posizioni_eleggibili (giocatore_id, posizioni, fonte) "
                                "VALUES (%s, %s, %s)", (a["giocatore_id"], a["nuove"], fonte))
                    inserite += 1
    return inserite, aggiornati


# ── Telegram ──────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id in [int(a) for a in settings.admin_ids()]


@solo_privato
async def cmd_import_posizioni(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Comando riservato agli admin.")
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "📥 Mandami il file CSV delle posizioni (<code>yahoo_id;nome;team;posizioni</code>).\n"
        "<i>Prima vedrai un'anteprima, niente viene salvato senza conferma.\n"
        "Per annullare: /annulla</i>", parse_mode="HTML")
    return ATTENDI_FILE


async def ricevi_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    doc = update.effective_message.document
    try:
        dati = await (await doc.get_file()).download_as_bytearray()
        contenuto = bytes(dati).decode("utf-8-sig")
    except UnicodeDecodeError:
        await update.effective_message.reply_text("❌ Il file non è in UTF-8. Risalvalo come UTF-8 e rimandalo.")
        return ATTENDI_FILE

    righe, errori = leggi_csv(contenuto)
    if not righe:
        await update.effective_message.reply_text("❌ Nessuna riga valida.\n" + "\n".join(errori[:10]))
        return ATTENDI_FILE

    piano = pianifica_import(righe, *carica_dati())
    context.user_data["import_posizioni_piano"] = piano
    await update.effective_message.reply_text(
        riepilogo(piano, len(righe), errori), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Salva", callback_data="pos_imp_ok"),
            InlineKeyboardButton("❌ Annulla", callback_data="pos_imp_no"),
        ]]),
    )
    if piano["non_trovati"]:
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["yahoo_id", "nome", "team", "posizioni"])
        for r in piano["non_trovati"]:
            w.writerow([r["yahoo_id"], r["nome"], r["team"], r["posizioni"]])
        await update.effective_message.reply_document(
            InputFile(io.BytesIO(buf.getvalue().encode("utf-8")), filename="posizioni_non_trovate.csv"),
            caption=f"{len(piano['non_trovati'])} righe non abbinate (di solito FA non presenti nel DB)")
    return CONFERMA


async def cb_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    piano = context.user_data.pop("import_posizioni_piano", None)
    if query.data == "pos_imp_no" or not piano:
        await query.edit_message_text("Import annullato, nessuna modifica.")
        return ConversationHandler.END
    try:
        inserite, aggiornati = applica_import(piano)
    except Exception as e:
        logger.exception("Import posizioni fallito")
        await query.edit_message_text(f"❌ Import fallito, nessuna modifica salvata (rollback).\n<code>{e}</code>",
                                      parse_mode="HTML")
        return ConversationHandler.END
    await query.edit_message_text(
        f"✅ <b>Posizioni importate</b>\n"
        f"Nuove righe di posizioni: <b>{inserite}</b>\n"
        f"Giocatori con yahoo_id/nome Yahoo aggiornati: <b>{aggiornati}</b>", parse_mode="HTML")
    logger.info("Import posizioni: %d righe, %d giocatori aggiornati (da %s)",
                inserite, aggiornati, query.from_user.id)
    return ConversationHandler.END


async def cmd_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("import_posizioni_piano", None)
    await update.effective_message.reply_text("Import annullato.")
    return ConversationHandler.END


# ── /set_posizioni_eleggibili ────────────────────────────────────────────────

def _cerca_giocatori(nome: str) -> tuple[list, bool]:
    """(candidati, esatto). Esatto/senza suffisso su tutti i nomi, altrimenti i 5 più simili."""
    import difflib
    giocatori = db._q("SELECT id, nome_common, nome_bref, nome_yahoo FROM giocatori", many=True) or []
    k = _senza_suffisso(_chiave(nome))
    esatti = [g for g in giocatori
              if any(_senza_suffisso(_chiave(g[c])) == k for c in ("nome_common", "nome_bref", "nome_yahoo") if g.get(c))]
    if esatti:
        return esatti, True
    simili = sorted(giocatori, key=lambda g: -difflib.SequenceMatcher(None, k, _chiave(g["nome_common"])).ratio())
    return simili[:5], False


def imposta_posizioni_manuali(gid: int, posizioni: str) -> tuple[str | None, bool]:
    """Aggiunge una riga all'event log se il set cambia. Ritorna (vecchie, cambiate)."""
    r = db._q("SELECT posizioni FROM posizioni_attuali WHERE giocatore_id = %s", (gid,), one=True)
    vecchie = r["posizioni"] if r else None
    if vecchie == posizioni:
        return vecchie, False
    db._q("INSERT INTO posizioni_eleggibili (giocatore_id, posizioni, fonte) VALUES (%s, %s, 'manuale')",
          (gid, posizioni))
    return vecchie, True


@solo_privato
async def cmd_set_posizioni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Comando riservato agli admin.")
        return
    pos = posizioni_canoniche(context.args[-1]) if len(context.args or []) >= 2 else None
    if not pos:
        await update.effective_message.reply_text(
            "Uso: /set_posizioni_eleggibili <nome giocatore> <posizioni>\n"
            "Es: /set_posizioni_eleggibili Giannis Antetokounmpo PF,C")
        return
    nome = " ".join(context.args[:-1])
    candidati, esatto = _cerca_giocatori(nome)
    if esatto and len(candidati) == 1:
        await _applica_set_posizioni(update.effective_message.reply_text, candidati[0], pos)
        return
    if not candidati:
        await update.effective_message.reply_text(f"Nessun giocatore trovato per «{nome}».")
        return
    titolo = "Più giocatori con questo nome" if esatto else f"Nessun match esatto per «{nome}». Intendevi"
    kb = [[InlineKeyboardButton(f"{g['nome_common']} [id {g['id']}]", callback_data=f"spe:{g['id']}:{pos}")]
          for g in candidati]
    kb.append([InlineKeyboardButton("❌ Annulla", callback_data="spe:no")])
    await update.effective_message.reply_text(f"{titolo}:", reply_markup=InlineKeyboardMarkup(kb))


async def _applica_set_posizioni(rispondi, g: dict, pos: str):
    vecchie, cambiate = imposta_posizioni_manuali(g["id"], pos)
    if cambiate:
        await rispondi(f"✅ {g['nome_common']}: {vecchie or 'nessuna'} → <b>{pos}</b>", parse_mode="HTML")
    else:
        await rispondi(f"ℹ️ {g['nome_common']} ha già le posizioni {pos}, nessuna modifica.")


async def cb_set_posizioni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    await query.answer()
    if query.data == "spe:no":
        await query.edit_message_text("Annullato.")
        return
    _, gid, pos = query.data.split(":")
    g = db._q("SELECT id, nome_common FROM giocatori WHERE id = %s", (int(gid),), one=True)
    if g and posizioni_canoniche(pos):
        await _applica_set_posizioni(query.edit_message_text, g, posizioni_canoniche(pos))


def get_handlers() -> list:
    return [
        CommandHandler("set_posizioni_eleggibili", cmd_set_posizioni),
        CallbackQueryHandler(cb_set_posizioni, pattern=r"^spe:(no|\d+:[A-Z,]+)$"),
        ConversationHandler(
        entry_points=[CommandHandler("import_posizioni_eleggibili", cmd_import_posizioni)],
        states={
            ATTENDI_FILE: [MessageHandler(filters.Document.ALL, ricevi_file)],
            CONFERMA:     [CallbackQueryHandler(cb_conferma, pattern=r"^pos_imp_(ok|no)$")],
        },
        fallbacks=[CommandHandler("annulla", cmd_annulla)],
        per_user=True, per_chat=True, per_message=False,
        conversation_timeout=600,
    ),
    ]

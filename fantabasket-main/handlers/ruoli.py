"""
Dichiarazione ruoli — fase `offseason-ruoli` (tra offseason-fa e regular-season-fa).

GM:    /dichiarazione_ruoli  oppure bottone "🎽 Dichiara ruoli" nel /menu (solo in fase)
Admin: /admin_menu → "🎽 Ruoli squadre" (qualsiasi fase, per qualsiasi squadra)
       /deadline_ruoli AAAA-MM-GG [HH:MM]

- Ogni stagione si dichiara tutto da capo, scegliendo tra le posizioni eleggibili
  (posizioni_attuali). Ruoli possibili: PG, SG, SF, PF, C.
- Le scelte sono BOZZE (tabella ruoli_bozze, sopravvivono ai riavvii) finché non si
  preme Conferma: allora diventano eventi in cambi_ruolo (tipo 'iniziale';
  'forzato_admin' se un admin modifica un ruolo già ufficiale). Vale l'ultimo evento.
- Conferma anche parziale (segnalata). Vincoli 4G/4F/2C solo come avviso.
- Giocatori con una sola posizione eleggibile: ruolo già impostato.
- Import da messaggio: una riga per giocatore "Nome RUOLO", match solo sul proprio
  roster (esatto → parole del nome → fuzzy con conferma).
- Job: promemoria in privato il giorno prima della deadline (10:00), report giornaliero
  sul canale log alle 17:00, elenco mancanti agli admin a fine fase.
"""
import difflib
import json
import logging
import os
import re
from datetime import datetime, date, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters,
)

import database as db
import settings
import teams as tm
from settings import solo_privato
from utils import normalizza

logger = logging.getLogger(__name__)

FASE_RUOLI = "offseason-ruoli"
RUOLI      = ["PG", "SG", "SF", "PF", "C"]
_SUFFISSI  = {"jr", "sr", "ii", "iii", "iv", "v"}
ATTENDI_TESTO, CONFERMA_FUZZY = range(2)

try:
    from zoneinfo import ZoneInfo
    ROME = ZoneInfo("Europe/Rome")
except Exception:  # pragma: no cover
    ROME = None


# ══ dati ════════════════════════════════════════════════════════════════════

def _stagione() -> str:
    return settings.stagione_corrente()


def stato_team(team_id: str) -> list[dict]:
    """Per ogni giocatore a roster: eleggibili, ruolo ufficiale, bozza, scelta corrente."""
    stagione = _stagione()
    roster = db.get_roster_team(team_id) or []
    gids = [r["giocatore_id"] for r in roster]
    if not gids:
        return []
    pos = {r["giocatore_id"]: r["posizioni"] for r in db._q(
        "SELECT giocatore_id, posizioni FROM posizioni_attuali WHERE giocatore_id = ANY(%s)",
        (gids,), many=True) or []}
    uff = {r["giocatore_id"]: r["ruolo"] for r in db._q(
        "SELECT giocatore_id, ruolo FROM ruolo_attuale WHERE stagione = %s AND team_id = %s",
        (stagione, team_id), many=True) or []}
    boz = {r["giocatore_id"]: r["ruolo"] for r in db._q(
        "SELECT giocatore_id, ruolo FROM ruoli_bozze WHERE stagione = %s AND team_id = %s",
        (stagione, team_id), many=True) or []}
    out = []
    for r in sorted(roster, key=lambda r: (-r["importo"], r["nome_common"])):
        gid = r["giocatore_id"]
        eleg = [p for p in RUOLI if p in (pos.get(gid) or "").split(",")]
        auto = eleg[0] if len(eleg) == 1 else None
        scelta = boz.get(gid) or uff.get(gid) or auto
        out.append({
            "gid": gid, "nome": r["nome_common"], "eleggibili": eleg,
            "ufficiale": uff.get(gid), "bozza": boz.get(gid), "auto": auto, "scelta": scelta,
        })
    return out


def riassunto(stato: list) -> dict:
    tot = len(stato)
    ufficiali = sum(1 for s in stato if s["ufficiale"])
    da_confermare = [s for s in stato if s["scelta"] and s["scelta"] != s["ufficiale"]]
    mancanti = [s for s in stato if not s["scelta"]]
    return {"tot": tot, "ufficiali": ufficiali, "da_confermare": da_confermare,
            "mancanti": mancanti, "completo": tot > 0 and ufficiali == tot}


def avvisi_vincoli(ruoli: list[str]) -> list[str]:
    g = sum(r in ("PG", "SG") for r in ruoli)
    f = sum(r in ("SF", "PF") for r in ruoli)
    c = sum(r == "C" for r in ruoli)
    out = []
    if g < 4: out.append(f"guardie (PG/SG): {g}/4")
    if f < 4: out.append(f"ali (SF/PF): {f}/4")
    if c < 2: out.append(f"centri (C): {c}/2")
    return out


def salva_bozza(team_id: str, gid: int, ruolo: str | None) -> None:
    stagione = _stagione()
    if ruolo is None:
        db._q("DELETE FROM ruoli_bozze WHERE team_id = %s AND stagione = %s AND giocatore_id = %s",
              (team_id, stagione, gid))
    else:
        db._q("""INSERT INTO ruoli_bozze (team_id, stagione, giocatore_id, ruolo)
                 VALUES (%s, %s, %s, %s)
                 ON CONFLICT (team_id, stagione, giocatore_id)
                 DO UPDATE SET ruolo = EXCLUDED.ruolo, aggiornato = NOW()""",
              (team_id, stagione, gid, ruolo))


def conferma_ruoli(team_id: str, da_admin: bool) -> list[dict]:
    """Ufficializza le scelte diverse dal ruolo ufficiale, in un'unica transazione."""
    stagione = _stagione()
    stato = stato_team(team_id)
    nuovi = [s for s in stato if s["scelta"] and s["scelta"] != s["ufficiale"]]
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for s in nuovi:
                tipo = "forzato_admin" if (da_admin and s["ufficiale"]) else "iniziale"
                cur.execute(
                    "INSERT INTO cambi_ruolo (giocatore_id, team_id, ruolo_da, ruolo_a, stagione, tipo) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (s["gid"], team_id, s["ufficiale"], s["scelta"], stagione, tipo))
            cur.execute("DELETE FROM ruoli_bozze WHERE team_id = %s AND stagione = %s",
                        (team_id, stagione))
    return nuovi


# ══ deadline ═══════════════════════════════════════════════════════════════

def get_deadline() -> datetime | None:
    raw = settings.load_globals().get("deadline_ruoli")
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(raw)
        return d.replace(tzinfo=ROME) if d.tzinfo is None and ROME else d
    except ValueError:
        return None


def _deadline_str() -> str:
    d = get_deadline()
    return d.strftime("%d/%m alle %H:%M") if d else "non impostata"


def _deadline_passata() -> bool:
    d = get_deadline()
    return bool(d and datetime.now(d.tzinfo) > d)


# ══ autorizzazioni ══════════════════════════════════════════════════════════

def _is_admin(user_id: int) -> bool:
    return user_id in [int(a) for a in settings.admin_ids()]


def _accesso(user_id: int, team_id: str) -> str | None:
    """None se può operare su team_id, altrimenti il motivo."""
    if _is_admin(user_id):
        return None
    t = tm.get_team_by_gm(user_id)
    if not t or t["id"] != team_id:
        return "⛔ Puoi dichiarare solo i ruoli della tua squadra."
    if settings.fase() != FASE_RUOLI:
        return "❌ La dichiarazione ruoli è aperta solo nella fase di dichiarazione ruoli."
    if _deadline_passata():
        return "⌛ La deadline per la dichiarazione ruoli è passata: contatta un admin."
    return None


# ══ viste ═══════════════════════════════════════════════════════════════════

def _testo_vista(team_id: str, stato: list, admin: bool) -> str:
    team = tm.get_team_by_id(team_id)
    r = riassunto(stato)
    righe = [
        f"🎽 <b>Dichiarazione ruoli — {team['nome'] if team else team_id}</b>"
        + (" <i>(modalità admin)</i>" if admin else ""),
        f"Stagione {_stagione()} · deadline: <b>{_deadline_str()}</b>",
        f"Ufficiali: <b>{r['ufficiali']}/{r['tot']}</b>"
        + (f" · da confermare: <b>{len(r['da_confermare'])}</b>" if r["da_confermare"] else "")
        + (f" · mancanti: <b>{len(r['mancanti'])}</b>" if r["mancanti"] else ""),
        "",
        "✅ ufficiale · ✏️ da confermare · 🔒 unica posizione · ❔ da scegliere",
        "<i>Le scelte diventano ufficiali solo con ✅ Conferma.</i>",
    ]
    avv = avvisi_vincoli([s["scelta"] for s in stato if s["scelta"]])
    if avv and not r["mancanti"]:
        righe.append("\n⚠️ Vincoli roster non rispettati: " + ", ".join(avv))
    return "\n".join(righe)


def _label(s: dict) -> str:
    if not s["eleggibili"]:
        return f"⚠️ {s['nome']} — posizioni mancanti"
    if not s["scelta"]:
        return f"❔ {s['nome']} ({'/'.join(s['eleggibili'])})"
    if s["scelta"] == s["ufficiale"]:
        icona = "✅"
    elif s["auto"] and not s["bozza"]:
        icona = "🔒"
    else:
        icona = "✏️"
    return f"{icona} {s['scelta']} · {s['nome']}"


def _kb_vista(team_id: str, stato: list) -> InlineKeyboardMarkup:
    righe = [[InlineKeyboardButton(_label(s), callback_data=f"rl:g:{team_id}:{s['gid']}")]
             for s in stato]
    righe.append([
        InlineKeyboardButton("📥 Importa da testo", callback_data=f"rl:i:{team_id}"),
        InlineKeyboardButton("✅ Conferma",         callback_data=f"rl:c:{team_id}"),
    ])
    righe.append([InlineKeyboardButton("✖️ Chiudi", callback_data="rl:close")])
    return InlineKeyboardMarkup(righe)


async def _mostra_vista(update: Update, team_id: str, admin: bool, nuovo: bool = False):
    stato = stato_team(team_id)
    if not stato:
        testo, kb = "Il roster è vuoto.", None
    else:
        testo, kb = _testo_vista(team_id, stato, admin), _kb_vista(team_id, stato)
    if update.callback_query and not nuovo:
        await update.callback_query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
    else:
        await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=kb)


# ══ comandi e callback (GM + admin) ═════════════════════════════════════════

@solo_privato
async def cmd_dichiarazione_ruoli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    team_id = None
    if context.args and _is_admin(uid):
        t = tm.get_team_by_query(" ".join(context.args))
        team_id = t["id"] if t else None
    if team_id is None:
        t = tm.get_team_by_gm(uid)
        if not t:
            await update.effective_message.reply_text(
                "⛔ Non sei registrato come GM." + (" Da admin: /dichiarazione_ruoli <squadra>" if _is_admin(uid) else ""))
            return
        team_id = t["id"]
    motivo = _accesso(uid, team_id)
    if motivo:
        await update.effective_message.reply_text(motivo)
        return
    await _mostra_vista(update, team_id, admin=_admin_su_altro(uid, team_id))


async def cb_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bottone del /menu principale."""
    query = update.callback_query
    t = tm.get_team_by_gm(query.from_user.id)
    if not t:
        await query.answer("⛔ Non sei registrato come GM.", show_alert=True)
        return
    motivo = _accesso(query.from_user.id, t["id"])
    if motivo:
        await query.answer(motivo, show_alert=True)
        return
    await query.answer()
    await _mostra_vista(update, t["id"], admin=False)


def _admin_su_altro(uid: int, team_id: str) -> bool:
    t = tm.get_team_by_gm(uid)
    return _is_admin(uid) and (not t or t["id"] != team_id)


async def cb_ruoli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if query.data == "rl:close":
        await query.answer()
        await query.edit_message_text("Dichiarazione ruoli chiusa. Le bozze restano salvate.")
        return
    parti = query.data.split(":")
    azione, team_id = parti[1], parti[2]
    motivo = _accesso(uid, team_id)
    if motivo:
        await query.answer(motivo, show_alert=True)
        return
    admin = _admin_su_altro(uid, team_id)

    if azione == "v":
        await query.answer()
        await _mostra_vista(update, team_id, admin)

    elif azione == "g":                                   # scelta ruolo di un giocatore
        gid = int(parti[3])
        s = next((s for s in stato_team(team_id) if s["gid"] == gid), None)
        if not s:
            await query.answer("Giocatore non più a roster.", show_alert=True)
            await _mostra_vista(update, team_id, admin)
            return
        await query.answer()
        if not s["eleggibili"]:
            testo = (f"⚠️ <b>{s['nome']}</b> non ha posizioni eleggibili registrate.\n"
                     f"Un admin deve impostarle con /set_posizioni_eleggibili.")
            kb = [[InlineKeyboardButton("← Indietro", callback_data=f"rl:v:{team_id}")]]
        else:
            stato_txt = f"ufficiale: <b>{s['ufficiale']}</b>" if s["ufficiale"] else "nessun ruolo ufficiale"
            testo = (f"🎽 <b>{s['nome']}</b>\nEleggibile: {', '.join(s['eleggibili'])} · {stato_txt}\n\n"
                     f"Scegli il ruolo:")
            kb = [[InlineKeyboardButton(("● " if p == s["scelta"] else "") + p,
                                        callback_data=f"rl:s:{team_id}:{gid}:{p}")
                   for p in s["eleggibili"]]]
            if s["bozza"]:
                kb.append([InlineKeyboardButton("🗑 Togli la scelta", callback_data=f"rl:x:{team_id}:{gid}")])
            kb.append([InlineKeyboardButton("← Indietro", callback_data=f"rl:v:{team_id}")])
        await query.edit_message_text(testo, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    elif azione in ("s", "x"):                            # salva / togli bozza
        gid = int(parti[3])
        ruolo = parti[4] if azione == "s" else None
        s = next((s for s in stato_team(team_id) if s["gid"] == gid), None)
        if not s or (ruolo and ruolo not in s["eleggibili"]):
            await query.answer("Ruolo non eleggibile per questo giocatore.", show_alert=True)
            return
        salva_bozza(team_id, gid, ruolo)
        await query.answer(f"{s['nome']}: {ruolo}" if ruolo else "Scelta tolta")
        await _mostra_vista(update, team_id, admin)

    elif azione == "c":                                   # riepilogo prima della conferma
        stato = stato_team(team_id)
        r = riassunto(stato)
        await query.answer()
        if not r["da_confermare"]:
            testo = "Non ci sono scelte nuove da confermare." + (
                f"\n\nMancano ancora: {', '.join(s['nome'] for s in r['mancanti'])}" if r["mancanti"] else "")
            kb = [[InlineKeyboardButton("← Indietro", callback_data=f"rl:v:{team_id}")]]
        else:
            righe = ["✅ <b>Conferma ruoli</b>\n", "Diventano ufficiali:"]
            for s in r["da_confermare"]:
                da = f" (era {s['ufficiale']})" if s["ufficiale"] else ""
                righe.append(f"• {s['nome']}: <b>{s['scelta']}</b>{da}")
            if r["mancanti"]:
                righe.append(f"\n⚠️ <b>Conferma parziale</b> — senza ruolo: "
                             + ", ".join(s["nome"] for s in r["mancanti"]))
            avv = avvisi_vincoli([s["scelta"] for s in stato if s["scelta"]])
            if avv:
                righe.append("⚠️ Vincoli roster: " + ", ".join(avv) + " (solo avviso in offseason)")
            testo = "\n".join(righe)
            kb = [[InlineKeyboardButton("✅ Confermo", callback_data=f"rl:ok:{team_id}"),
                   InlineKeyboardButton("← Indietro", callback_data=f"rl:v:{team_id}")]]
        await query.edit_message_text(testo, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    elif azione == "ok":                                  # conferma definitiva
        await query.answer()
        nuovi = conferma_ruoli(team_id, da_admin=admin)
        r = riassunto(stato_team(team_id))
        await query.edit_message_text(
            f"✅ Ruoli ufficializzati: <b>{len(nuovi)}</b>\n"
            f"Ufficiali: <b>{r['ufficiali']}/{r['tot']}</b>"
            + (f"\n⚠️ Mancano ancora: {', '.join(s['nome'] for s in r['mancanti'])}" if r["mancanti"] else ""),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎽 Torna ai ruoli", callback_data=f"rl:v:{team_id}")]]))
        await _log_conferma(context, team_id, nuovi, r, query.from_user, admin)
        try:
            # Sync del roster di TUTTE le squadre (un'unica chiamata, foglio Scelte escluso)
            import gas_client
            gas_client.sync_teams([t["id"] for t in tm.get_all_teams()])
        except Exception as e:
            logger.warning("GAS sync dopo ruoli %s: %s", team_id, e)


async def _log_conferma(context, team_id, nuovi, r, user, admin):
    ch = settings.load_globals().get("log_channel_id_main")
    if not ch or not nuovi:
        return
    team = tm.get_team_by_id(team_id)
    chi = user.first_name or user.username or str(user.id)
    testo = (f"🎽 <b>Ruoli — {team['nome'] if team else team_id}</b>"
             + (f" (admin {chi})" if admin else f" ({chi})") + "\n"
             + ", ".join(f"{s['nome']} {s['scelta']}" for s in nuovi)
             + f"\nUfficiali: {r['ufficiali']}/{r['tot']}")
    try:
        await context.bot.send_message(chat_id=ch, text=testo, parse_mode="HTML")
    except Exception as e:
        logger.warning("Log conferma ruoli: %s", e)


# ══ import da testo ═════════════════════════════════════════════════════════

def _chiave(nome: str) -> str:
    n = normalizza(nome).replace(".", " ").replace("'", "").replace("’", "")
    t = n.split()
    while len(t) > 1 and t[-1] in _SUFFISSI:
        t.pop()
    return " ".join(t)


def parse_righe(testo: str) -> tuple[list, list]:
    """'LeBron SF' → [(riga, 'lebron', 'SF')], errori."""
    voci, errori = [], []
    for riga in testo.splitlines():
        r = riga.strip()
        if not r:
            continue
        m = re.match(r"^(.+?)[\s:\-–,]+([A-Za-z]{1,2})\s*$", r)
        if not m or m.group(2).upper() not in RUOLI:
            errori.append(f"«{r}»: formato non riconosciuto (serve «Nome RUOLO»)")
            continue
        voci.append((r, m.group(1).strip(), m.group(2).upper()))
    return voci, errori


def abbina(nome: str, stato: list) -> tuple[str, dict | None, list]:
    """('esatto'|'parole'|'fuzzy'|'ambiguo'|'nessuno', giocatore, candidati)."""
    q = _chiave(nome)
    q_tok = q.split()
    chiavi = {s["gid"]: _chiave(s["nome"]) for s in stato}
    esatti = [s for s in stato if chiavi[s["gid"]] == q]
    if len(esatti) == 1:
        return "esatto", esatti[0], []
    parole = [s for s in stato if q_tok and all(t in chiavi[s["gid"]].split() for t in q_tok)]
    if len(parole) == 1:
        return "parole", parole[0], []
    if len(parole) > 1:
        return "ambiguo", None, parole
    punteggi = []
    for s in stato:
        tok = chiavi[s["gid"]].split()
        score = max([difflib.SequenceMatcher(None, q, chiavi[s["gid"]]).ratio()] +
                    [difflib.SequenceMatcher(None, q, t).ratio() for t in tok])
        punteggi.append((score, s))
    punteggi.sort(key=lambda x: -x[0])
    if punteggi and punteggi[0][0] >= 0.6:
        return "fuzzy", punteggi[0][1], []
    return "nessuno", None, []


async def cb_import_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    team_id = query.data.split(":")[2]
    motivo = _accesso(query.from_user.id, team_id)
    if motivo:
        await query.answer(motivo, show_alert=True)
        return ConversationHandler.END
    await query.answer()
    context.user_data["rl_import"] = {"team_id": team_id}
    await query.edit_message_text(
        "📥 <b>Importa ruoli da testo</b>\n\nMandami un messaggio con una riga per giocatore:\n"
        "<code>LeBron SF\nCurry PG\nJokic C</code>\n\n"
        "Basta il nome, il cognome o il nome completo. Le scelte vanno in bozza: "
        "le ufficializzi poi con ✅ Conferma.\n<i>Per annullare: /annulla</i>",
        parse_mode="HTML")
    return ATTENDI_TESTO


async def ricevi_testo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    imp = context.user_data.get("rl_import")
    if not imp:
        return ConversationHandler.END
    team_id = imp["team_id"]
    stato = stato_team(team_id)
    voci, errori = parse_righe(update.effective_message.text)
    imp.update(ok=[], errori=errori, fuzzy=[], visti=set())
    for riga, nome, ruolo in voci:
        tipo, s, cand = abbina(nome, stato)
        if tipo in ("esatto", "parole"):
            _valida_e_accoda(imp, riga, s, ruolo)
        elif tipo == "fuzzy":
            imp["fuzzy"].append((riga, nome, ruolo, s["gid"]))
        elif tipo == "ambiguo":
            imp["errori"].append(f"«{riga}»: ambiguo ({', '.join(c['nome'] for c in cand)}), scrivi il nome completo")
        else:
            imp["errori"].append(f"«{riga}»: nessun giocatore del roster corrisponde")
    return await _prossimo_fuzzy(update, context)


def _valida_e_accoda(imp: dict, riga: str, s: dict, ruolo: str) -> None:
    if not s["eleggibili"]:
        imp["errori"].append(f"«{riga}»: {s['nome']} non ha posizioni eleggibili registrate")
    elif ruolo not in s["eleggibili"]:
        imp["errori"].append(f"«{riga}»: {s['nome']} non è eleggibile come {ruolo} ({'/'.join(s['eleggibili'])})")
    else:
        if s["gid"] in imp["visti"]:
            imp["errori"].append(f"«{riga}»: {s['nome']} compare più volte, vale l'ultima riga")
        imp["visti"].add(s["gid"])
        imp["ok"].append((s["gid"], s["nome"], ruolo))


async def _prossimo_fuzzy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    imp = context.user_data["rl_import"]
    if imp["fuzzy"]:
        riga, nome, ruolo, gid = imp["fuzzy"][0]
        s = next(s for s in stato_team(imp["team_id"]) if s["gid"] == gid)
        testo = f"🔎 «{nome}» → intendevi <b>{s['nome']}</b> ({ruolo})?"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Sì", callback_data="rli:y"),
                                    InlineKeyboardButton("❌ No", callback_data="rli:n")]])
        if update.callback_query:
            await update.callback_query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
        else:
            await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=kb)
        return CONFERMA_FUZZY
    return await _chiudi_import(update, context)


async def cb_fuzzy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    imp = context.user_data.get("rl_import")
    if not imp or not imp["fuzzy"]:
        return ConversationHandler.END
    riga, nome, ruolo, gid = imp["fuzzy"].pop(0)
    if query.data == "rli:y":
        s = next(s for s in stato_team(imp["team_id"]) if s["gid"] == gid)
        _valida_e_accoda(imp, riga, s, ruolo)
    else:
        imp["errori"].append(f"«{riga}»: abbinamento rifiutato, scrivi il nome completo")
    return await _prossimo_fuzzy(update, context)


async def _chiudi_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    imp = context.user_data.pop("rl_import")
    team_id = imp["team_id"]
    for gid, _, ruolo in imp["ok"]:
        salva_bozza(team_id, gid, ruolo)
    stato = stato_team(team_id)
    saltati = [s["nome"] for s in stato if s["gid"] not in imp["visti"] and not s["scelta"]]
    righe = [f"📥 <b>Import completato</b> — {len(imp['ok'])} ruoli messi in bozza"]
    if imp["ok"]:
        righe.append(", ".join(f"{n} {r}" for _, n, r in imp["ok"]))
    if imp["errori"]:
        righe.append("\n⚠️ <b>Da sistemare:</b>\n" + "\n".join(f"• {e}" for e in imp["errori"]))
    if saltati:
        righe.append("\n❔ <b>Non indicati e ancora senza ruolo:</b> " + ", ".join(saltati))
    righe.append("\n<i>Ricorda: diventano ufficiali solo con ✅ Conferma.</i>")
    msg = update.effective_message
    if update.callback_query:
        await update.callback_query.edit_message_text("\n".join(righe), parse_mode="HTML")
    else:
        await msg.reply_text("\n".join(righe), parse_mode="HTML")
    await _mostra_vista(update, team_id, _admin_su_altro(update.effective_user.id, team_id), nuovo=True)
    return ConversationHandler.END


async def cmd_annulla_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("rl_import", None)
    await update.effective_message.reply_text("Import ruoli annullato.")
    return ConversationHandler.END


# ══ admin ═══════════════════════════════════════════════════════════════════

def stato_lega() -> list[tuple[dict, dict]]:
    return [(t, riassunto(stato_team(t["id"]))) for t in tm.get_all_teams()]


async def cb_admin_lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    await query.answer()
    kb = []
    for t, r in stato_lega():
        icona = "✅" if r["completo"] else ("🟡" if r["ufficiali"] else "❌")
        kb.append([InlineKeyboardButton(f"{icona} {t['nome']} ({r['ufficiali']}/{r['tot']})",
                                        callback_data=f"rl:v:{t['id']}")])
    kb.append([InlineKeyboardButton("← Menu admin", callback_data="adm:home")])
    await query.edit_message_text(
        f"🎽 <b>Ruoli squadre</b> — stagione {_stagione()}\nDeadline: <b>{_deadline_str()}</b>\n"
        f"Scegli una squadra per impostare i ruoli al posto del GM.",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


@solo_privato
async def cmd_deadline_ruoli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_message.reply_text(
            f"Deadline attuale: {_deadline_str()}\nUso: /deadline_ruoli AAAA-MM-GG [HH:MM] (default 23:59)")
        return
    try:
        giorno = date.fromisoformat(context.args[0])
        ora = context.args[1] if len(context.args) > 1 else "23:59"
        d = datetime.fromisoformat(f"{giorno.isoformat()}T{ora}")
    except ValueError:
        await update.effective_message.reply_text("❌ Formato non valido. Es: /deadline_ruoli 2026-10-20 23:59")
        return
    path = os.environ.get("GLOBALS_PATH", "/config/globals.json")
    g = json.load(open(path))
    g["deadline_ruoli"] = d.strftime("%Y-%m-%dT%H:%M")
    json.dump(g, open(path, "w"), indent=2, ensure_ascii=False)
    await update.effective_message.reply_text(f"✅ Deadline dichiarazione ruoli: {_deadline_str()}")


def _riepilogo_lega_testo() -> str:
    stati = stato_lega()
    compl = sum(1 for _, r in stati if r["completo"])
    parz  = sum(1 for _, r in stati if r["ufficiali"] and not r["completo"])
    zero  = sum(1 for _, r in stati if not r["ufficiali"])
    return (f"🎽 <b>Dichiarazione ruoli</b> — complete <b>{compl}/{len(stati)}</b>"
            f" · parziali {parz} · nessuna {zero}\nDeadline: {_deadline_str()}")


async def job_report_giornaliero(context: ContextTypes.DEFAULT_TYPE):
    """17:00 — sul canale log, solo durante la fase."""
    try:
        if settings.fase() != FASE_RUOLI:
            return
        ch = settings.load_globals().get("log_channel_id_main")
        if ch:
            await context.bot.send_message(chat_id=ch, text=_riepilogo_lega_testo(), parse_mode="HTML")
    except Exception as e:
        logger.warning("job_report_giornaliero ruoli: %s", e)


async def job_promemoria_deadline(context: ContextTypes.DEFAULT_TYPE):
    """10:00 — se la deadline è domani, messaggio privato ai GM con dichiarazione incompleta."""
    try:
        if settings.fase() != FASE_RUOLI:
            return
        d = get_deadline()
        oggi = datetime.now(d.tzinfo).date() if d else None
        if not d or d.date() - oggi != timedelta(days=1):
            return
        for t, r in stato_lega():
            if r["completo"]:
                continue
            mancano = [s["nome"] for s in stato_team(t["id"]) if not s["ufficiale"]]
            testo = (f"⏰ <b>Domani ({_deadline_str()}) scade la dichiarazione ruoli.</b>\n"
                     f"Senza ruolo ufficiale: {', '.join(mancano)}\n\nUsa /dichiarazione_ruoli")
            for gm_id in t.get("gm_ids", []):
                try:
                    await context.bot.send_message(chat_id=gm_id, text=testo, parse_mode="HTML")
                except Exception as e:
                    logger.warning("Promemoria ruoli a %s: %s", gm_id, e)
    except Exception as e:
        logger.warning("job_promemoria_deadline: %s", e)


async def report_fine_fase(bot) -> None:
    """Chiamata al cambio fase in uscita da offseason-ruoli: mancanti al gruppo admin."""
    g = settings.load_globals()
    gruppo = g.get("admin_group_id")
    if not gruppo:
        return
    righe = []
    for t, r in stato_lega():
        if not r["completo"]:
            mancano = [s["nome"] for s in stato_team(t["id"]) if not s["ufficiale"]]
            righe.append(f"• <b>{t['nome']}</b> ({r['ufficiali']}/{r['tot']}): {', '.join(mancano)}")
    testo = ("🎽 <b>Fine dichiarazione ruoli</b>\n" +
             ("Tutte le squadre hanno dichiarato tutti i ruoli. ✅" if not righe else
              "Giocatori senza ruolo ufficiale (regolamento: ruolo casuale tra quelli disponibili):\n"
              + "\n".join(righe) + "\n\nImpostabili da /admin_menu → 🎽 Ruoli squadre."))
    try:
        await bot.send_message(chat_id=gruppo, text=testo, parse_mode="HTML")
    except Exception as e:
        logger.warning("report_fine_fase ruoli: %s", e)


async def report_vincoli_inizio_rs(bot) -> None:
    """Al passaggio a regular-season-fa: squadre che non rispettano i minimi 4G/4F/2C
    (con i ruoli ufficiali; chi non ha ruolo conta come flessibile tra le eleggibili)."""
    from shared import ruoli_core as core
    gruppo = settings.load_globals().get("admin_group_id")
    if not gruppo:
        return
    righe = []
    for t in tm.get_all_teams():
        deficit = core.deficit_team(db._q, t["id"], _stagione())
        if deficit == 0:
            continue
        stato = stato_team(t["id"])
        uff = [s["ufficiale"] for s in stato if s["ufficiale"]]
        g = sum(r in ("PG", "SG") for r in uff)
        f = sum(r in ("SF", "PF") for r in uff)
        c = sum(r == "C" for r in uff)
        senza = [s["nome"] for s in stato if not s["ufficiale"]]
        righe.append(f"• <b>{t['nome']}</b>: G {g}/4 · F {f}/4 · C {c}/2"
                     + (f" — senza ruolo: {', '.join(senza)}" if senza else ""))
    testo = ("🏀 <b>Inizio regular season — vincoli dei ruoli</b>\n" +
             ("Tutte le squadre rispettano i minimi (4 guardie, 4 ali, 2 centri). ✅" if not righe else
              "Squadre che non rispettano i minimi (4 G, 4 F, 2 C), nemmeno con la scelta migliore "
              "dei ruoli mancanti:\n" + "\n".join(righe) +
              "\n\nSi sistemano con un cambio forzato (/admin_menu → 🔁 Cambi ruolo) o sul mercato."))
    try:
        await bot.send_message(chat_id=gruppo, text=testo, parse_mode="HTML")
    except Exception as e:
        logger.warning("report_vincoli_inizio_rs: %s", e)


# ══ registrazione ═══════════════════════════════════════════════════════════

def get_handlers() -> list:
    conv_import = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_import_start, pattern=r"^rl:i:[\w-]+$")],
        states={
            ATTENDI_TESTO:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_testo)],
            CONFERMA_FUZZY: [CallbackQueryHandler(cb_fuzzy, pattern=r"^rli:[yn]$")],
        },
        fallbacks=[CommandHandler("annulla", cmd_annulla_import)],
        per_user=True, per_chat=True, per_message=False, conversation_timeout=600,
    )
    return [
        conv_import,
        CommandHandler("dichiarazione_ruoli", cmd_dichiarazione_ruoli),
        CommandHandler("deadline_ruoli", cmd_deadline_ruoli),
        CallbackQueryHandler(cb_home, pattern=r"^rl:home$"),
        CallbackQueryHandler(cb_admin_lista, pattern=r"^rladm:list$"),
        CallbackQueryHandler(cb_ruoli, pattern=r"^rl:(close|[vgsxc]:[\w-]+(:\d+(:[A-Z]{1,2})?)?|ok:[\w-]+)$"),
    ]

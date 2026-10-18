"""
Penalità (v5.6.0, decise con Luca il 16/10): richiami alle squadre dati dagli admin per i motivi
più vari, con una motivazione. Si sommano nella stagione (penalità 1, 2, 3…) e si azzerano con
la stagione nuova (restano nello storico). Gli effetti (posizioni in meno al draft, cap
penalizzato) li applicano gli admin a mano: qui si registrano soltanto. Non c'entrano col cap
penalizzato di teams.json.

Admin: /admin_menu → ⚠️ Penalità (o /penalita) → ➕ Nuova → squadra → motivazione scritta
       (conversazione) → anteprima → ✅ Conferma. Pubblicata sul canale principale, mandata ai GM
       della squadra, riga sul canale log, foglio Scelte aggiornato ("Penalità: N" sotto il GM).
       Dal pannello, per squadra, l'elenco e 🗑 Revoca (con conferma): il messaggio sul canale
       si corregge (❌ revocata), avviso ai GM e al log.
GM:    /penalita (o /menu → ⚠️ Penalità): quelle della propria squadra in questa stagione;
       /penalita SQUADRA per un'altra squadra (tutti le possono vedere: sono pubbliche).

Tabella penalita (c'era già in schema.sql, mai usata): stagione, team, motivo, chi (assegnata_da) e quando
(timestamp); in più (v5.6.0) da_id, canale_msg (messaggio sul canale), revocata, revocata_da.
Callback: pen:adm, pen:new, pen:s:<team> (→ motivazione), pen:ok, pen:no, pen:t:<team>,
pen:r:<id>, pen:rok:<id>, pen:mie.
"""
import html
import logging

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import database as db
import settings
import teams as tm

logger = logging.getLogger(__name__)
MOTIVO = 1
MAX_MOTIVO = 600


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _stagione() -> str:
    return settings.stagione_corrente()


def _is_admin(uid: int) -> bool:
    return uid in [int(a) for a in settings.admin_ids()]


def _nome(team_id: str) -> str:
    t = tm.get_team_by_id(team_id)
    return t["nome"] if t else team_id


def migra() -> None:
    """La tabella c'era già in schema.sql (mai usata): si completa con le colonne nuove."""
    db._q("""CREATE TABLE IF NOT EXISTS penalita (
               id           SERIAL PRIMARY KEY,
               timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               team_id      TEXT NOT NULL,
               stagione     TEXT NOT NULL,
               motivo       TEXT NOT NULL,
               assegnata_da TEXT NOT NULL)""")
    for col in ("da_id BIGINT", "canale_msg BIGINT", "revocata TIMESTAMPTZ", "revocata_da TEXT"):
        db._q(f"ALTER TABLE penalita ADD COLUMN IF NOT EXISTS {col}")
    db._q("CREATE INDEX IF NOT EXISTS idx_penalita_team ON penalita (team_id, stagione)")


# ── dati ───────────────────────────────────────────────────────────────────────

def elenco(team_id: str, stagione: str | None = None, anche_revocate: bool = False) -> list[dict]:
    return db._q(f"""SELECT * FROM penalita WHERE team_id = %s AND stagione = %s
                     {'' if anche_revocate else 'AND revocata IS NULL'} ORDER BY timestamp, id""",
                 (team_id, stagione or _stagione()), many=True) or []


def conteggi(stagione: str | None = None) -> dict[str, int]:
    """{team: penalità valide della stagione} (solo chi ne ha)."""
    return {r["team_id"]: r["n"] for r in db._q(
        """SELECT team_id, COUNT(*) AS n FROM penalita WHERE stagione = %s AND revocata IS NULL GROUP BY team_id""",
        (stagione or _stagione(),), many=True) or []}


def aggiungi(team_id: str, motivo: str, chi: str, chi_id: int | None) -> tuple[dict, int]:
    r = db._q("""INSERT INTO penalita (stagione, team_id, motivo, assegnata_da, da_id) VALUES (%s, %s, %s, %s, %s) RETURNING *""",
              (_stagione(), team_id, motivo, chi, chi_id), one=True)
    return r, len(elenco(team_id))


def revoca(pid: int, chi: str) -> dict | None:
    return db._q("""UPDATE penalita SET revocata = NOW(), revocata_da = %s WHERE id = %s AND revocata IS NULL RETURNING *""",
                 (chi, pid), one=True)


# ── messaggi ───────────────────────────────────────────────────────────────────

async def _manda(bot, chat_id, testo: str, **k):
    if not chat_id:
        return None
    try:
        return await bot.send_message(chat_id=chat_id, text=testo, parse_mode="HTML", **k)
    except Exception as err:
        logger.warning("Penalità, messaggio a %s: %s", chat_id, err)
        return None


async def _ai_gm(bot, team_id: str, testo: str):
    for uid in (tm.get_team_by_id(team_id) or {}).get("gm_ids", []):
        await _manda(bot, uid, testo)


async def _log(bot, testo: str):
    await _manda(bot, settings.load_globals().get("log_channel_id_main"), testo)


def _sync_scelte():
    try:
        import gas_client
        gas_client.sync_scelte()
    except Exception as err:
        logger.warning("Sync foglio Scelte dopo una penalità: %s", err)


def testo_canale(p: dict, n: int) -> str:
    return (f"⚠️ <b>Penalità a {e(_nome(p['team_id']))}</b> — la {n}ª della stagione\n\n"
            f"<b>Motivazione:</b> {e(p['motivo'])}")


def _riga(p: dict, i: int | None = None) -> str:
    from zoneinfo import ZoneInfo
    quando = p["timestamp"].astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y")
    t = f"{f'{i}. ' if i else '• '}{quando} — {e(p['motivo'])}"
    if p.get("revocata"):
        t = f"<s>{t}</s> <i>(revocata da {e(p['revocata_da'] or '?')})</i>"
    return t


def testo_squadra(team_id: str, admin: bool = False) -> str:
    valide = elenco(team_id)
    righe = [f"⚠️ <b>Penalità di {e(_nome(team_id))}</b> — stagione {e(_stagione())}: <b>{len(valide)}</b>", ""]
    tutte = elenco(team_id, anche_revocate=admin)
    if not tutte:
        righe.append("Nessuna penalità in questa stagione. 👏")
    n = 0
    for p in tutte:
        if not p.get("revocata"):
            n += 1
            righe.append(_riga(p, n) + (f" <i>(da {e(p['assegnata_da'] or '?')})</i>" if admin else ""))
        else:
            righe.append(_riga(p))
    vecchie = db._q("""SELECT stagione, COUNT(*) AS n FROM penalita WHERE team_id = %s AND stagione <> %s AND revocata IS NULL
                       GROUP BY stagione ORDER BY stagione DESC""", (team_id, _stagione()), many=True) or []
    if vecchie:
        righe += ["", "Storico: " + " · ".join(f"{e(v['stagione'])}: {v['n']}" for v in vecchie)]
    return "\n".join(righe)


# ── pannello admin ─────────────────────────────────────────────────────────────

def pannello() -> tuple[str, K]:
    c = conteggi()
    righe = [f"⚠️ <b>Penalità</b> — stagione {e(_stagione())}", ""]
    if c:
        righe += [f"• {e(_nome(t))}: <b>{n}</b>" for t, n in sorted(c.items(), key=lambda x: (-x[1], _nome(x[0])))]
    else:
        righe.append("Nessuna penalità in questa stagione.")
    tasti = [[B("➕ Nuova penalità", callback_data="pen:new")]]
    tasti += [[B(f"📋 {_nome(t)} ({n})", callback_data=f"pen:t:{t}")] for t, n in sorted(c.items(), key=lambda x: _nome(x[0]))]
    tasti.append([B("← Menu", callback_data="adm:home")])
    return "\n".join(righe), K(tasti)


def _kb_squadre(prefisso: str) -> K:
    squadre = sorted(tm.get_all_teams(), key=lambda t: t["nome"])
    bot = [B(t["nome"][:24], callback_data=f"{prefisso}{t['id']}") for t in squadre]
    righe = [bot[i:i + 2] for i in range(0, len(bot), 2)]
    righe.append([B("← Indietro", callback_data="pen:adm")])
    return K(righe)


async def cmd_penalita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/penalita: admin il pannello; GM la propria squadra; /penalita SQUADRA un'altra."""
    uid = update.effective_user.id
    msg = update.effective_message
    if context.args:
        team = tm.get_team_by_query(" ".join(context.args))
        if not team:
            await msg.reply_text("Squadra non trovata.")
            return
        testo = testo_squadra(team["id"], admin=_is_admin(uid) and update.effective_chat.type == "private")
        kb = None
        if _is_admin(uid) and update.effective_chat.type == "private":
            kb = _kb_revoche(team["id"])
        await msg.reply_text(testo, parse_mode="HTML", reply_markup=kb)
        return
    if _is_admin(uid) and update.effective_chat.type == "private":
        t, k = pannello()
        await msg.reply_text(t, parse_mode="HTML", reply_markup=k)
        return
    team = tm.get_team_by_gm(uid)
    if not team:
        await msg.reply_text("Uso: /penalita SQUADRA")
        return
    await msg.reply_text(testo_squadra(team["id"]), parse_mode="HTML")


def _kb_revoche(team_id: str) -> K:
    righe = [[B(f"🗑 Revoca la {i}ª ({p['timestamp']:%d/%m})", callback_data=f"pen:r:{p['id']}")]
             for i, p in enumerate(elenco(team_id), 1)]
    righe.append([B("← Penalità", callback_data="pen:adm")])
    return K(righe)


async def cb_penalita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parti = q.data.split(":")
    azione = parti[1]
    uid = q.from_user.id
    if azione == "mie":
        await q.answer()
        team = tm.get_team_by_gm(uid)
        await q.edit_message_text(testo_squadra(team["id"]) if team else "Non sei registrato come GM.", parse_mode="HTML",
                                  reply_markup=K([[B("← Menu", callback_data="menu:home")]]))
        return
    if not _is_admin(uid):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    chi = q.from_user.first_name or str(uid)
    if azione == "adm":
        await q.answer()
        t, k = pannello()
        await q.edit_message_text(t, parse_mode="HTML", reply_markup=k)
    elif azione == "new":
        await q.answer()
        await q.edit_message_text("⚠️ <b>Nuova penalità</b> — a quale squadra?", parse_mode="HTML", reply_markup=_kb_squadre("pen:s:"))
    elif azione == "t":
        await q.answer()
        await q.edit_message_text(testo_squadra(parti[2], admin=True), parse_mode="HTML", reply_markup=_kb_revoche(parti[2]))
    elif azione == "r":
        p = db._q("SELECT * FROM penalita WHERE id = %s", (int(parti[2]),), one=True)
        if not p or p["revocata"]:
            await q.answer("Già revocata.", show_alert=True)
            return
        await q.answer()
        await q.edit_message_text(f"🗑 Revocare questa penalità di <b>{e(_nome(p['team_id']))}</b>?\n\n{_riga(p)}",
                                  parse_mode="HTML", reply_markup=K([[B("✅ Sì, revoca", callback_data=f"pen:rok:{p['id']}"),
                                                                      B("❌ No", callback_data=f"pen:t:{p['team_id']}")]]))
    elif azione == "rok":
        p = revoca(int(parti[2]), chi)
        if not p:
            await q.answer("Già revocata.", show_alert=True)
            return
        await q.answer("Revocata")
        n = len(elenco(p["team_id"]))
        canale = settings.load_globals().get("main_channel_id")
        if canale and p.get("canale_msg"):
            try:
                await context.bot.edit_message_text(chat_id=canale, message_id=p["canale_msg"], parse_mode="HTML",
                                                    text=f"<s>⚠️ Penalità a {e(_nome(p['team_id']))}</s>\n\n"
                                                         f"<b>Motivazione:</b> {e(p['motivo'])}\n\n❌ <b>Revocata</b> dagli admin.")
            except Exception as err:
                logger.warning("Penalità revocata, messaggio sul canale: %s", err)
        await _ai_gm(context.bot, p["team_id"], f"✅ La penalità del {p['timestamp']:%d/%m} alla tua squadra è stata <b>revocata</b> "
                                                f"dagli admin.\nMotivazione era: {e(p['motivo'])}\nPenalità in questa stagione: <b>{n}</b>")
        from handlers.registro import segna
        await segna(context.bot, q.from_user, "admin", "penalità revocata", squadre=p["team_id"],
                    oggetto=f"penalità del {p['timestamp']:%d/%m}", prima=f"{n + 1} in stagione", dopo=f"{n} in stagione",
                    nota=p["motivo"])
        _sync_scelte()
        await q.edit_message_text(testo_squadra(p["team_id"], admin=True), parse_mode="HTML", reply_markup=_kb_revoche(p["team_id"]))
    elif azione == "ok":
        bozza = context.user_data.pop("pen_bozza", None)
        if not bozza:
            await q.answer("Niente da confermare (già fatto o scaduto).", show_alert=True)
            return
        await q.answer("Registrata")
        p, n = aggiungi(bozza["team"], bozza["motivo"], chi, uid)
        m = await _manda(context.bot, settings.load_globals().get("main_channel_id"), testo_canale(p, n))
        if m:
            db._q("UPDATE penalita SET canale_msg = %s WHERE id = %s", (m.message_id, p["id"]))
        await _ai_gm(context.bot, p["team_id"], f"⚠️ <b>La tua squadra ha ricevuto una penalità</b> — la {n}ª di questa stagione.\n\n"
                                                f"<b>Motivazione:</b> {e(p['motivo'])}\n\nPer chiarimenti scrivi agli admin.")
        from handlers.registro import segna
        await segna(context.bot, q.from_user, "admin", "penalità assegnata", squadre=p["team_id"], oggetto="penalità",
                    prima=f"{n - 1} in stagione", dopo=f"{n} in stagione", nota=p["motivo"])
        _sync_scelte()
        await q.edit_message_text(f"✅ Penalità registrata: <b>{e(_nome(p['team_id']))}</b> è a <b>{n}</b> in questa stagione.\n"
                                  "Pubblicata sul canale e mandata ai GM.", parse_mode="HTML",
                                  reply_markup=K([[B("← Penalità", callback_data="pen:adm")]]))
    elif azione == "no":
        context.user_data.pop("pen_bozza", None)
        await q.answer("Annullata")
        t, k = pannello()
        await q.edit_message_text(t, parse_mode="HTML", reply_markup=k)


# ── motivazione (conversazione) ────────────────────────────────────────────────

async def cb_squadra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    team_id = q.data.split(":")[2]
    context.user_data["pen_team"] = team_id
    n = len(elenco(team_id))
    await q.edit_message_text(f"⚠️ Penalità a <b>{e(_nome(team_id))}</b> (sarebbe la {n + 1}ª della stagione).\n\n"
                              "✍️ Scrivi la <b>motivazione</b> (verrà pubblicata sul canale). /annulla per uscire.",
                              parse_mode="HTML")
    return MOTIVO


async def msg_motivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team_id = context.user_data.pop("pen_team", None)
    motivo = (update.effective_message.text or "").strip()
    if not team_id:
        return ConversationHandler.END
    if len(motivo) < 3 or len(motivo) > MAX_MOTIVO:
        context.user_data["pen_team"] = team_id
        await update.effective_message.reply_text(f"La motivazione deve essere tra 3 e {MAX_MOTIVO} caratteri. Riscrivila o /annulla.")
        return MOTIVO
    context.user_data["pen_bozza"] = {"team": team_id, "motivo": motivo}
    n = len(elenco(team_id)) + 1
    await update.effective_message.reply_text(
        "📝 <b>Anteprima</b> — così uscirà sul canale:\n\n"
        + testo_canale({"team_id": team_id, "motivo": motivo}, n)
        + "\n\nI GM della squadra ricevono lo stesso messaggio. Confermi?",
        parse_mode="HTML", reply_markup=K([[B("✅ Conferma", callback_data="pen:ok"), B("❌ Annulla", callback_data="pen:no")]]))
    return ConversationHandler.END


async def annulla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pen_team", None)
    context.user_data.pop("pen_bozza", None)
    await update.effective_message.reply_text("Annullato.")
    return ConversationHandler.END


def get_handlers() -> list:
    return [
        ConversationHandler(
            entry_points=[CallbackQueryHandler(cb_squadra, pattern=r"^pen:s:[\w-]+$")],
            states={MOTIVO: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, msg_motivo)]},
            fallbacks=[CommandHandler(["annulla", "annulla_admin"], annulla)],
            conversation_timeout=900, name="penalita_motivo"),
        CommandHandler("penalita", cmd_penalita),
        CallbackQueryHandler(cb_penalita, pattern=r"^pen:(?:adm|new|ok|no|mie|t:[\w-]+|r:\d+|rok:\d+)$"),
    ]

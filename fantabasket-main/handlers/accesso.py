"""
Richieste di accesso e riassegnazione dal menu (v6.26.0, Luca 04/11).

- Uno sconosciuto in privato riceve «bot riservato ai GM» con il bottone 🙋 Richiedi accesso (shared/solo_lega, che
  lascia passare solo quel bottone e chiama `richiedi`). La richiesta (id, nome e username Telegram) si salva in
  `richieste_accesso` e arriva **al dev** in privato coi bottoni «🔁 Assegna una squadra» e «🙈 Ignora»: così non serve
  cercare lo user_id. Una richiesta ogni 24 ore per persona.
- «🔁 Assegna una squadra» → elenco delle squadre → il riepilogo di /riassegna (admin_panel.conferma_riassegna) col
  nome Telegram come nome del GM (si cambia poi da ✏️ Nomi squadre e GM).
- Menu admin → 👤 Riassegna squadra: le richieste in attesa degli ultimi 30 giorni, ognuna col suo bottone, e
  l'uso di /riassegna per chi non ha fatto richiesta.
"""
import html
import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import database as db
import settings
import teams as tm

logger = logging.getLogger(__name__)
ATTESA = timedelta(hours=24)


def e(x) -> str:
    return html.escape(str(x), quote=False)


def migra() -> None:
    db._q("""CREATE TABLE IF NOT EXISTS richieste_accesso (
               user_id  BIGINT PRIMARY KEY,
               nome     TEXT NOT NULL,
               username TEXT,
               quando   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               stato    TEXT NOT NULL DEFAULT 'attesa')""")


def segna_stato(uid: int, stato: str) -> None:
    migra()
    db._q("UPDATE richieste_accesso SET stato = %s WHERE user_id = %s", (stato, int(uid)))


def richiesta(uid: int) -> dict | None:
    migra()
    return db._q("SELECT * FROM richieste_accesso WHERE user_id = %s", (int(uid),), one=True)


def in_attesa(giorni: int = 30) -> list[dict]:
    migra()
    return db._q("""SELECT * FROM richieste_accesso WHERE stato = 'attesa' AND quando > NOW() - %s * INTERVAL '1 day'
                    ORDER BY quando DESC LIMIT 20""", (giorni,), many=True) or []


def _is_admin(uid: int) -> bool:
    from handlers.admin_panel import is_admin
    return is_admin(uid)


def _kb_richiesta(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Assegna una squadra", callback_data=f"riass:utente:{uid}"),
                                  InlineKeyboardButton("🙈 Ignora", callback_data=f"riass:ignora:{uid}")]])


async def richiedi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Il bottone 🙋 Richiedi accesso di uno sconosciuto (chiamato dalla guardia di shared/solo_lega)."""
    q, u = update.callback_query, update.effective_user
    prima = richiesta(u.id)
    ora = datetime.now(timezone.utc)
    if prima and prima["stato"] == "attesa" and ora - prima["quando"] < ATTESA:
        await q.answer("La richiesta è già arrivata al dev: aspetta che ti assegni la squadra.", show_alert=True)
        return
    nome = (u.full_name or "").strip() or str(u.id)
    db._q("""INSERT INTO richieste_accesso (user_id, nome, username, quando, stato) VALUES (%s, %s, %s, NOW(), 'attesa')
             ON CONFLICT (user_id) DO UPDATE SET nome = EXCLUDED.nome, username = EXCLUDED.username,
               quando = NOW(), stato = 'attesa'""", (u.id, nome, u.username))
    dev = settings.dev_id()
    if dev:
        try:
            await context.bot.send_message(
                int(dev), f"🙋 <b>Richiesta di accesso</b>\n{e(nome)}" + (f" (@{e(u.username)})" if u.username else "")
                + f"\nuser_id <code>{u.id}</code>", parse_mode="HTML", reply_markup=_kb_richiesta(u.id))
        except Exception as err:
            logger.warning("Richiesta di accesso al dev: %s", err)
    await q.answer()
    try:
        await q.edit_message_text("✅ Richiesta inviata al dev: quando ti assegna la squadra ti arriva un messaggio.")
    except Exception:
        pass
    logger.info("Richiesta di accesso da %s (%s)", u.id, nome)


def _kb_squadre(uid: int) -> InlineKeyboardMarkup:
    b = [InlineKeyboardButton(f"{t['nome']}" + (f" · {t['gm_nome']}" if t.get("gm_nome") else ""),
                              callback_data=f"riass:sq:{uid}:{t['id']}") for t in tm.get_all_teams()]
    righe = [b[i:i + 2] for i in range(0, len(b), 2)]
    return InlineKeyboardMarkup(righe + [[InlineKeyboardButton("❌ Annulla", callback_data="riass:no")]])


async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("Solo admin.", show_alert=True)
        return
    await q.answer()
    parti = q.data.split(":")
    azione = parti[1]
    if azione == "menu":
        rr = in_attesa()
        testo = ["👤 <b>Riassegna squadra</b>", ""]
        if rr:
            testo.append("Richieste di accesso in attesa (ultimi 30 giorni): scegli chi.")
        else:
            testo.append("Nessuna richiesta di accesso in attesa.")
        testo += ["", "<i>Il nuovo GM può scrivere /start a questo bot e premere 🙋 Richiedi accesso: ti arriva qui. "
                      "Altrimenti: /riassegna team_id user_id Nome.</i>"]
        kb = [[InlineKeyboardButton(f"🙋 {r['nome']}" + (f" @{r['username']}" if r.get("username") else ""),
                                    callback_data=f"riass:utente:{r['user_id']}")] for r in rr]
        kb.append([InlineKeyboardButton("← Menu admin", callback_data="adm:home")])
        await q.edit_message_text("\n".join(testo), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return
    uid = int(parti[2])
    r = richiesta(uid)
    nome = (r or {}).get("nome") or str(uid)
    if azione == "ignora":
        segna_stato(uid, "ignorata")
        await q.edit_message_text(f"🙈 Richiesta di {e(nome)} ({uid}) ignorata.", parse_mode="HTML")
        return
    if azione == "utente":
        altra = tm.get_team_by_gm(uid)
        if altra:
            await q.edit_message_text(f"ℹ️ {e(nome)} è già GM di <b>{e(altra['nome'])}</b>.", parse_mode="HTML")
            return
        await q.edit_message_text(f"🔁 A quale squadra assegno <b>{e(nome)}</b> ({uid})?", parse_mode="HTML",
                                  reply_markup=_kb_squadre(uid))
        return
    if azione == "sq":
        team = tm.get_team_by_id(parti[3])
        if not team:
            await q.edit_message_text("❌ Squadra non trovata.")
            return
        from handlers.admin_panel import conferma_riassegna
        t, kb = conferma_riassegna(context, team, uid, nome,
                                   nota="\n<i>Nome del GM da Telegram: si cambia da ✏️ Nomi squadre e GM.</i>")
        await q.edit_message_text(t, parse_mode="HTML", reply_markup=kb)


def handlers() -> list:
    return [CallbackQueryHandler(cb, pattern=r"^riass:(menu|utente:-?\d+|ignora:-?\d+|sq:-?\d+:[^:]+)$")]

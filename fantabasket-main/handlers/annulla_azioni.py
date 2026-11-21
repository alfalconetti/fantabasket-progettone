"""
Annullare un taglio, annullare o correggere una firma registrata (v7.20.2, Luca 21/11; priorità 1 di
docs/AZIONI_ANNULLABILI.md). Solo admin, dal pannello:

- /admin_menu → ✂️ Taglia giocatore → ↩️ Annulla un taglio (`annt:l` → `annt:t:<id>` → `annt:ok:<id>`): il contratto torna
  attivo, spariscono le rate e il movimento del taglio (un taglio gratuito torna disponibile), foglio, registro e
  messaggio sul canale (il taglio era stato annunciato).
- /admin_menu → ✍️ Firme registrate (`annf:l` → `annf:t:<id>` → `annf:ok:<id>`): via contratto e movimento, le
  dichiarazioni di ruolo della firma chiuse, foglio e registro (la firma registrata non era sul canale).
- `/correggi_firma ID IMPORTO ANNI`: importo e anni giusti, con i controlli di /registra_firma (anni minimi, Cam Thomas).

Si cancellano i movimenti sbagliati invece di aggiungerne di contrari (database.annulla_taglio / annulla_firma); non
si può se dopo il giocatore ha avuto altri movimenti. Nel registro delle azioni resta tutto, prima → dopo.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.ext import CallbackQueryHandler, CommandHandler

import database as db
import settings
import teams as tm

logger = logging.getLogger(__name__)
ROME = ZoneInfo("Europe/Rome")


def _is_admin(uid: int) -> bool:
    return uid in [int(a) for a in settings.load_globals().get("admin_ids", [])]


def _nome(t: str | None) -> str:
    return (tm.get_team_by_id(t) or {}).get("nome", t or "—")


def _quando(ts) -> str:
    return f"{ts.astimezone(ROME):%d/%m %H:%M}"


def _admin_tag(user) -> str:
    return (user.first_name or str(user.id)) + (f" (@{user.username})" if getattr(user, "username", None) else "")


def _contratto(r: dict) -> str:
    return f"{r['importo']}M × {r['anni_originali']}"


async def _canale(bot, testo: str) -> None:
    ch = settings.load_globals().get("main_channel_id")
    if ch:
        try:
            await bot.send_message(chat_id=ch, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio sul canale: %s", e)


def _sync(team_id: str) -> None:
    try:
        import gas_client
        gas_client.sync_teams([team_id])
    except Exception as e:
        logger.warning("GAS sync %s: %s", team_id, e)


async def _ai_gm(bot, team_id: str, testo: str) -> None:
    for gm in (tm.get_team_by_id(team_id) or {}).get("gm_ids", []):
        try:
            await bot.send_message(chat_id=int(gm), text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Avviso al GM: %s", e)


# ── taglio ─────────────────────────────────────────────────────────────────────

def _riga_taglio(t: dict) -> str:
    return f"{t['nome_common']} · {_nome(t['team_id_da'])} · {_quando(t['timestamp'])}"


def effetti_taglio(t: dict) -> str:
    rate = ", ".join(f"{r['stagione']}: {r['importo']}M" for r in t["rate"])
    righe = [f"• torna a {_nome(t['team_id_da'])} col contratto {_contratto(t)} (stagione di firma {t['stagione_firma']})"]
    righe.append("• torna disponibile un taglio gratuito" if t["gratuito"] else f"• si tolgono le rate della spalmatura ({rate or 'nessuna'})")
    righe.append("• il taglio sparisce dai movimenti (carriera, roster alla data); nel registro resta la riga")
    righe.append("• messaggio sul canale e al GM, foglio aggiornato")
    return "\n".join(righe)


async def applica_annulla_taglio(bot, tid: int, user=None) -> str:
    t = db.taglio(tid)
    if not t:
        return "❌ Taglio non trovato."
    try:
        db.annulla_taglio(tid)
    except ValueError as e:
        return f"❌ Non si può: {e}."
    from handlers.registro import segna
    await segna(bot, user, "admin", "taglio annullato", squadre=t["team_id_da"], giocatore_id=t["giocatore_id"],
                oggetto=t["nome_common"], prima=f"tagliato il {_quando(t['timestamp'])}", dopo=f"di nuovo {_contratto(t)}",
                nota=("taglio gratuito restituito" if t["gratuito"] else
                      "tolte le rate: " + ", ".join(f"{r['stagione']} {r['importo']}M" for r in t["rate"])))
    chi = _admin_tag(user) if user else "un admin"
    await _canale(bot, f"↩️ <b>Taglio annullato</b>: <b>{t['nome_common']}</b> torna a <b>{_nome(t['team_id_da'])}</b> "
                       f"({_contratto(t)})" + ("" if t["gratuito"] else ", senza spalmatura") + f".\n<i>Corretto da {chi}</i>")
    await _ai_gm(bot, t["team_id_da"], f"🛠 Un admin ha annullato il taglio di <b>{t['nome_common']}</b>: è di nuovo nel tuo roster.")
    _sync(t["team_id_da"])
    from handlers.admin_panel import _avviso_cap_slot
    team = tm.get_team_by_id(t["team_id_da"]) or {"id": t["team_id_da"]}
    return f"✅ Taglio di <b>{t['nome_common']}</b> annullato." + _avviso_cap_slot(team, settings.stagione_corrente())


async def cb_annulla_taglio(update, context):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    parti = q.data.split(":")
    if parti[1] == "l":
        tt = db.tagli_recenti()
        kb = [[B(_riga_taglio(t)[:60], callback_data=f"annt:t:{t['id']}")] for t in tt]
        kb.append([B("← Taglio admin", callback_data="adm:taglia")])
        await q.edit_message_text("↩️ <b>Annulla un taglio</b> (ultimi 90 giorni) — quale?" if tt else "Nessun taglio negli ultimi 90 giorni.",
                                  parse_mode="HTML", reply_markup=K(kb))
        return
    tid = int(parti[2])
    t = db.taglio(tid)
    if not t:
        await q.edit_message_text("❌ Taglio non trovato.")
        return
    if parti[1] == "t":
        perche = db.perche_no_annulla_taglio(t)
        if perche:
            await q.edit_message_text(f"↩️ <b>{_riga_taglio(t)}</b>\n\n❌ Non si può annullare: {perche}.", parse_mode="HTML",
                                      reply_markup=K([[B("← Indietro", callback_data="annt:l")]]))
            return
        await q.edit_message_text(f"↩️ <b>Annullare il taglio di {t['nome_common']}?</b>\n{_riga_taglio(t)}\n\n{effetti_taglio(t)}",
                                  parse_mode="HTML", reply_markup=K([[B("✅ Annulla il taglio", callback_data=f"annt:ok:{tid}"),
                                                                      B("← Indietro", callback_data="annt:l")]]))
        return
    esito = await applica_annulla_taglio(context.bot, tid, q.from_user)
    await q.edit_message_text(esito, parse_mode="HTML", reply_markup=K([[B("← Menu admin", callback_data="adm:home")]]))


# ── firma registrata ───────────────────────────────────────────────────────────

def _riga_firma(f: dict) -> str:
    return f"{f['nome_common']} · {_nome(f['team_id_a'])} · {_contratto(f)} · {_quando(f['timestamp'])}"


async def applica_annulla_firma(bot, tid: int, user=None) -> str:
    f = db.firma_registrata(tid)
    if not f:
        return "❌ Firma non trovata."
    try:
        db.annulla_firma(tid)
    except ValueError as e:
        return f"❌ Non si può: {e}."
    from handlers.registro import segna
    await segna(bot, user, "admin", "firma registrata annullata", squadre=f["team_id_a"], giocatore_id=f["giocatore_id"],
                oggetto=f["nome_common"], prima=_contratto(f), dopo="free agent", nota=f"firma del {_quando(f['timestamp'])}")
    await _ai_gm(bot, f["team_id_a"], f"🛠 Un admin ha annullato la firma registrata di <b>{f['nome_common']}</b>: non è più nel tuo roster.")
    _sync(f["team_id_a"])
    return f"✅ Firma di <b>{f['nome_common']}</b> annullata: è di nuovo free agent."


async def cb_annulla_firma(update, context):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    parti = q.data.split(":")
    if parti[1] == "l":
        ff = db.firme_registrate()
        kb = [[B(_riga_firma(f)[:60], callback_data=f"annf:t:{f['id']}")] for f in ff]
        kb.append([B("← Menu admin", callback_data="adm:home")])
        await q.edit_message_text("✍️ <b>Firme registrate</b> (/registra_firma, ultimi 90 giorni) — quale?" if ff else
                                  "Nessuna firma registrata negli ultimi 90 giorni.", parse_mode="HTML", reply_markup=K(kb))
        return
    tid = int(parti[2])
    f = db.firma_registrata(tid)
    if not f:
        await q.edit_message_text("❌ Firma non trovata.")
        return
    if parti[1] == "t":
        perche = db.perche_no_firma(f)
        if perche:
            await q.edit_message_text(f"✍️ <b>{_riga_firma(f)}</b>\n\n❌ Non si può più annullare né correggere: {perche}.",
                                      parse_mode="HTML", reply_markup=K([[B("← Indietro", callback_data="annf:l")]]))
            return
        await q.edit_message_text(
            f"✍️ <b>{_riga_firma(f)}</b>\n\n"
            f"<b>↩️ Annulla</b>: via contratto e movimento (torna free agent), chiuse le dichiarazioni di ruolo della firma, "
            f"foglio aggiornato, avviso al GM; nel registro resta la riga.\n"
            f"<b>✏️ Correggi</b> importo o anni: <code>/correggi_firma {tid} IMPORTO ANNI</code>",
            parse_mode="HTML", reply_markup=K([[B("↩️ Annulla la firma", callback_data=f"annf:ok:{tid}"),
                                                B("← Indietro", callback_data="annf:l")]]))
        return
    esito = await applica_annulla_firma(context.bot, tid, q.from_user)
    await q.edit_message_text(esito, parse_mode="HTML", reply_markup=K([[B("← Menu admin", callback_data="adm:home")]]))


async def cmd_correggi_firma(update, context):
    """/correggi_firma ID IMPORTO ANNI (admin): l'ID è nella scheda della firma (✍️ Firme registrate)."""
    msg = update.effective_message
    if not _is_admin(update.effective_user.id):
        return
    a = context.args or []
    if len(a) != 3 or not all(x.isdigit() for x in a):
        await msg.reply_text("Uso: /correggi_firma ID IMPORTO ANNI — l'ID è nella scheda della firma "
                             "(/admin_menu → ✍️ Firme registrate). Es: /correggi_firma 1234 3 2")
        return
    tid, importo, anni = (int(x) for x in a)
    f = db.firma_registrata(tid)
    if not f:
        await msg.reply_text("❌ Firma registrata non trovata.")
        return
    if anni not in (1, 2, 3) or anni < settings.anni_minimi_contratto(importo) or importo < 1:
        await msg.reply_text(f"❌ {importo}M × {anni}: anni non validi (1-3; da {settings.soglia_anni_2()}M almeno 2, "
                             f"da {settings.soglia_anni_3()}M obbligatori 3).")
        return
    minimo = db.minimo_cam_thomas(f["giocatore_id"], f["team_id_a"])
    if minimo and importo < minimo:
        await msg.reply_text(f"❌ Cam Thomas exception: per {f['nome_common']} servono almeno {minimo}M.")
        return
    if (importo, anni) == (f["importo"], f["anni_originali"]):
        await msg.reply_text("È già così.")
        return
    try:
        db.correggi_firma(tid, importo, anni)
    except ValueError as e:
        await msg.reply_text(f"❌ Non si può: {e}.")
        return
    from handlers.registro import segna
    await segna(context.bot, update.effective_user, "admin", "firma registrata corretta", squadre=f["team_id_a"],
                giocatore_id=f["giocatore_id"], oggetto=f["nome_common"], prima=_contratto(f), dopo=f"{importo}M × {anni}")
    await _ai_gm(context.bot, f["team_id_a"], f"🛠 Un admin ha corretto il contratto di <b>{f['nome_common']}</b>: "
                                              f"{importo}M × {anni} (prima {_contratto(f)}).")
    _sync(f["team_id_a"])
    from handlers.admin_panel import _avviso_cap_slot
    team = tm.get_team_by_id(f["team_id_a"]) or {"id": f["team_id_a"]}
    await msg.reply_text(f"✅ <b>{f['nome_common']}</b> ({_nome(f['team_id_a'])}): {_contratto(f)} → <b>{importo}M × {anni}</b>."
                         + _avviso_cap_slot(team, settings.stagione_corrente()), parse_mode="HTML")


def get_handlers() -> list:
    return [CallbackQueryHandler(cb_annulla_taglio, pattern=r"^annt:(?:l|(?:t|ok):\d+)$"),
            CallbackQueryHandler(cb_annulla_firma, pattern=r"^annf:(?:l|(?:t|ok):\d+)$"),
            CommandHandler("correggi_firma", cmd_correggi_firma)]

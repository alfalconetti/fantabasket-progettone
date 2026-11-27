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

v7.38.0 (Luca, 27/11: «implementa le cose da rendere annullabili»; ordine di docs/AZIONI_ANNULLABILI.md), stesso
schema elenco → scheda con gli effetti → conferma, e tutto insieme in /admin_menu → ↩️ Annulla azioni (`ann:home`):
- decadimento (`decann:`): il contratto torna attivo, tornano le spalmature tolte (anche alle altre squadre, salvate
  dalla v7.38.0 in `spalmature_tolte`), l'RFA revocato, sparisce il movimento; canale, GM, fogli;
- ritiro di un free agent (`ritann:`): tornano le spalmature tolte da /ritiro_fa;
- DPE (`dpeann:`): via la DPE (torna l'importo pieno e, se era prima della deadline, lo slot); non se il cambio ruolo
  extra di una DPE post-deadline è già stato usato;
- attivazione dei diritti 2nd (`attann:`): via contratto e movimento, il rookie torna coi diritti;
- cambio ruolo (`crann:`): via il cambio, il giocatore torna al ruolo di prima e il cambio torna disponibile; solo
  l'ultimo del giocatore;
- rinnovo rookie III-IV (`rrann:`): via il contratto nuovo, torna quello rookie di prima (x0), solo nella stagione.
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


# ── v7.38.0: decadimento, ritiro FA, DPE, attivazione diritti, cambio ruolo ─────────────────────────────

def _sync_tutte(squadre: list[str]) -> None:
    try:
        import gas_client
        gas_client.sync_teams(list(squadre))
    except Exception as e:
        logger.warning("GAS sync %s: %s", squadre, e)


async def _flusso(q, pref: str, titolo: str, elenco: list, riga, scheda, perche, effetti, applica, indietro: str):
    """Elenco → scheda (con perché no o effetti) → conferma, uguale per tutte le azioni annullabili."""
    parti = q.data.split(":")
    if parti[1] == "l":
        kb = [[B(riga(x)[:60], callback_data=f"{pref}:t:{x['id']}")] for x in elenco]
        kb.append([B("← Indietro", callback_data=indietro)])
        await q.edit_message_text(f"↩️ <b>{titolo}</b> — quale?" if elenco else f"↩️ {titolo}: niente di recente.",
                                  parse_mode="HTML", reply_markup=K(kb))
        return
    x = scheda(int(parti[2]))
    if not x:
        await q.edit_message_text("❌ Non trovato.", reply_markup=K([[B("← Indietro", callback_data=f"{pref}:l")]]))
        return
    if parti[1] == "t":
        no = perche(x)
        if no:
            await q.edit_message_text(f"↩️ <b>{riga(x)}</b>\n\n❌ Non si può annullare: {no}.", parse_mode="HTML",
                                      reply_markup=K([[B("← Indietro", callback_data=f"{pref}:l")]]))
            return
        await q.edit_message_text(f"↩️ <b>Annullare?</b>\n{riga(x)}\n\n{effetti(x)}", parse_mode="HTML",
                                  reply_markup=K([[B("✅ Annulla", callback_data=f"{pref}:ok:{x['id']}"),
                                                   B("← Indietro", callback_data=f"{pref}:l")]]))
        return
    esito = await applica(q.get_bot(), x, q.from_user)
    await q.edit_message_text(esito, parse_mode="HTML", reply_markup=K([[B("← Annulla azioni", callback_data="ann:home"),
                                                                       B("← Menu admin", callback_data="adm:home")]]))


def _chi(user) -> str:
    return _admin_tag(user) if user else "un admin"


# decadimento

def _riga_dec(d: dict) -> str:
    from handlers.decadimento import MOTIVI, causa_da_nota
    return f"{d['nome_common']} · {_nome(d['team_id_da'])} · {MOTIVI.get(causa_da_nota(d['note']), '?')} · {_quando(d['timestamp'])}"


def _effetti_dec(d: dict) -> str:
    sp = db.spalmature_di(f"dec:{d['id']}")
    righe = [f"• torna a {_nome(d['team_id_da'])} col contratto {d['importo']}M × {d['anni_originali']}"]
    if sp:
        righe.append("• tornano le spalmature tolte: " + ", ".join(f"{_nome(r['team_id'])} {r['stagione']} {r['importo']}M" for r in sp))
    righe.append("• se era un RFA dichiarato torna dichiarato (se la squadra non ne ha dichiarato un altro)")
    righe.append("• il decadimento sparisce dai movimenti (e con lui la Cam Thomas exception); nel registro resta la riga")
    righe.append("• messaggio sul canale e al GM, fogli aggiornati")
    return "\n".join(righe)


async def _applica_dec(bot, d: dict, user) -> str:
    try:
        altre = db.annulla_decadimento(d["id"])
    except ValueError as e:
        return f"❌ Non si può: {e}."
    from handlers.registro import segna
    await segna(bot, user, "admin", "decadimento annullato", squadre=[d["team_id_da"]] + altre, giocatore_id=d["giocatore_id"],
                oggetto=d["nome_common"], prima="decaduto", dopo=f"di nuovo {d['importo']}M × {d['anni_originali']}",
                nota=("rimesse le spalmature di " + ", ".join(_nome(t) for t in altre)) if altre else None)
    await _canale(bot, f"↩️ <b>Decadimento annullato</b>: <b>{d['nome_common']}</b> torna a <b>{_nome(d['team_id_da'])}</b> "
                       f"({d['importo']}M × {d['anni_originali']})"
                       + (f"; tornano le spalmature di {', '.join(_nome(t) for t in altre)}" if altre else "")
                       + f".\n<i>Corretto da {_chi(user)}</i>")
    await _ai_gm(bot, d["team_id_da"], f"🛠 Un admin ha annullato il decadimento di <b>{d['nome_common']}</b>: è di nuovo nel tuo roster.")
    _sync_tutte([d["team_id_da"]] + altre)
    from handlers.admin_panel import _avviso_cap_slot
    return (f"✅ Decadimento di <b>{d['nome_common']}</b> annullato."
            + _avviso_cap_slot(tm.get_team_by_id(d["team_id_da"]) or {"id": d["team_id_da"]}, settings.stagione_corrente()))


async def cb_annulla_decadimento(update, context):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    await _flusso(q, "decann", "Annulla un decadimento (ultimi 6 mesi)", db.decadimenti_recenti() if q.data == "decann:l" else [],
                  _riga_dec, db.decadimento, db.perche_no_annulla_decadimento, _effetti_dec, _applica_dec, "ann:home")


# ritiro di un free agent

def _ritiri() -> list[dict]:
    out = []
    for r in db.ritiri_fa_recenti():
        r["id"] = int(r["gruppo"].split(":")[1]) * 10 ** 10 + int(r["gruppo"].split(":")[2])   # gruppo → numero per il bottone
        out.append(r)
    return out


def _ritiro(n: int) -> dict | None:
    return next((r for r in _ritiri() if r["id"] == n), None)


def _riga_rit(r: dict) -> str:
    return f"{r['nome_common']} · ritiro FA · {_quando(r['quando'])}"


def _righe_rit(r: dict) -> str:
    return ", ".join(_nome(x.split(" ", 1)[0]) + " " + x.split(" ", 1)[1] for x in r["righe"])


def _effetti_rit(r: dict) -> str:
    return ("• tornano le spalmature tolte: " + _righe_rit(r)
            + "\n• fogli aggiornati, avviso ai GM; nel registro resta la riga")


async def _applica_rit(bot, r: dict, user) -> str:
    try:
        squadre = db.annulla_ritiro_fa(r["gruppo"])
    except ValueError as e:
        return f"❌ Non si può: {e}."
    from handlers.registro import segna
    await segna(bot, user, "admin", "ritiro del free agent annullato", squadre=squadre, giocatore_id=r["giocatore_id"],
                oggetto=r["nome_common"], prima="spalmature tolte", dopo="spalmature rimesse", nota=_righe_rit(r))
    for t in squadre:
        await _ai_gm(bot, t, f"🛠 Un admin ha annullato il ritiro di <b>{r['nome_common']}</b>: la spalmatura del suo taglio torna a pesare.")
    _sync_tutte(squadre)
    return f"✅ Ritiro di <b>{r['nome_common']}</b> annullato: spalmature rimesse a {', '.join(_nome(t) for t in squadre)}."


async def cb_annulla_ritiro(update, context):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    await _flusso(q, "ritann", "Annulla un ritiro di un free agent (/ritiro_fa)", _ritiri() if q.data == "ritann:l" else [],
                  _riga_rit, _ritiro, lambda r: None, _effetti_rit, _applica_rit, "ann:home")


# DPE

def _riga_dpe(d: dict) -> str:
    return f"{d['nome_common']} · {_nome(d['team_id'])} · {d['importo_originale']}→{d['importo_dpe']}M · {_quando(d['timestamp'])}"


def _effetti_dpe(d: dict) -> str:
    righe = [f"• {d['nome_common']} torna a {d['importo_originale']}M per la stagione {d['stagione']} (cap)"]
    righe.append("• torna a occupare lo slot del roster" if d["pre_deadline"] else "• si toglie il cambio ruolo extra (non ancora usato)")
    righe.append("• messaggio sul canale e al GM, foglio aggiornato; nel registro resta la riga")
    return "\n".join(righe)


async def _applica_dpe(bot, d: dict, user) -> str:
    try:
        db.annulla_dpe(d["id"])
    except ValueError as e:
        return f"❌ Non si può: {e}."
    from handlers.registro import segna
    await segna(bot, user, "admin", "DPE annullata", squadre=d["team_id"], giocatore_id=d["giocatore_id"], oggetto=d["nome_common"],
                prima=f"{d['importo_dpe']}M (DPE {d['stagione']})", dopo=f"{d['importo_originale']}M")
    await _canale(bot, f"↩️ <b>DPE annullata</b>: <b>{d['nome_common']}</b> ({_nome(d['team_id'])}) torna a "
                       f"{d['importo_originale']}M.\n<i>Corretto da {_chi(user)}</i>")
    await _ai_gm(bot, d["team_id"], f"🛠 Un admin ha annullato la DPE di <b>{d['nome_common']}</b>: torna a {d['importo_originale']}M.")
    _sync(d["team_id"])
    from handlers.admin_panel import _avviso_cap_slot
    return (f"✅ DPE di <b>{d['nome_common']}</b> annullata."
            + _avviso_cap_slot(tm.get_team_by_id(d["team_id"]) or {"id": d["team_id"]}, settings.stagione_corrente()))


async def cb_annulla_dpe(update, context):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    await _flusso(q, "dpeann", "Annulla una DPE (ultimi 6 mesi)", db.dpe_recenti() if q.data == "dpeann:l" else [],
                  _riga_dpe, db.dpe_per_id, db.perche_no_annulla_dpe, _effetti_dpe, _applica_dpe, "ann:home")


# attivazione dei diritti 2nd

def _riga_att(a: dict) -> str:
    return f"{a['nome_common']} · {_nome(a['team_id_a'])} · {a['importo']}M × {a['anni_originali']} · {_quando(a['timestamp'])}"


def _effetti_att(a: dict) -> str:
    return (f"• via il contratto {a['importo']}M × {a['anni_originali']}: {_nome(a['team_id_a'])} torna ad avere i diritti\n"
            "• chiuse le dichiarazioni di ruolo dell'attivazione\n"
            "• l'attivazione sparisce dai movimenti; nel registro resta la riga\n• messaggio sul canale e al GM, foglio aggiornato")


async def _applica_att(bot, a: dict, user) -> str:
    try:
        db.annulla_attivazione(a["id"])
    except ValueError as e:
        return f"❌ Non si può: {e}."
    from handlers.registro import segna
    await segna(bot, user, "admin", "attivazione dei diritti annullata", squadre=a["team_id_a"], giocatore_id=a["giocatore_id"],
                oggetto=a["nome_common"], prima=f"{a['importo']}M × {a['anni_originali']}", dopo="diritti", nota=a["note"])
    await _canale(bot, f"↩️ <b>Attivazione annullata</b>: <b>{a['nome_common']}</b> torna tra i diritti di "
                       f"<b>{_nome(a['team_id_a'])}</b>.\n<i>Corretto da {_chi(user)}</i>")
    await _ai_gm(bot, a["team_id_a"], f"🛠 Un admin ha annullato l'attivazione di <b>{a['nome_common']}</b>: hai di nuovo i diritti.")
    _sync(a["team_id_a"])
    return f"✅ Attivazione di <b>{a['nome_common']}</b> annullata: di nuovo diritti."


async def cb_annulla_attivazione(update, context):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    await _flusso(q, "attann", "Annulla un'attivazione dei diritti (ultimi 6 mesi)", db.attivazioni_recenti() if q.data == "attann:l" else [],
                  _riga_att, db.attivazione, db.perche_no_annulla_attivazione, _effetti_att, _applica_att, "ann:home")


# cambio ruolo

def _riga_cr(c: dict) -> str:
    from handlers.cambi_ruolo import ETICHETTE
    return f"{c['nome_common']} {c['ruolo_da'] or '—'}→{c['ruolo_a']} · {_nome(c['team_id'])} · {ETICHETTE.get(c['tipo'], c['tipo'])} · {_quando(c['timestamp'])}"


def _effetti_cr(c: dict) -> str:
    from handlers.cambi_ruolo import ETICHETTE
    return (f"• {c['nome_common']} torna {c['ruolo_da'] or 'senza ruolo'}\n"
            f"• il cambio ({ETICHETTE.get(c['tipo'], c['tipo'])}) torna disponibile\n"
            "• messaggio sul canale e al GM, foglio aggiornato; nel registro resta la riga")


async def _applica_cr(bot, c: dict, user) -> str:
    try:
        db.annulla_cambio_ruolo(c["id"])
    except ValueError as e:
        return f"❌ Non si può: {e}."
    from handlers.registro import segna
    await segna(bot, user, "admin", "cambio ruolo annullato", squadre=c["team_id"], giocatore_id=c["giocatore_id"],
                oggetto=c["nome_common"], prima=c["ruolo_a"], dopo=c["ruolo_da"], nota=c["tipo"])
    await _canale(bot, f"↩️ <b>Cambio ruolo annullato</b>: <b>{c['nome_common']}</b> ({_nome(c['team_id'])}) torna "
                       f"{c['ruolo_da'] or 'senza ruolo'}.\n<i>Corretto da {_chi(user)}</i>")
    await _ai_gm(bot, c["team_id"], f"🛠 Un admin ha annullato il cambio ruolo di <b>{c['nome_common']}</b> "
                                    f"({c['ruolo_da'] or '—'} → {c['ruolo_a']}): il cambio torna disponibile.")
    try:
        from handlers.cambi_ruolo import _sync as _sync_ruoli
        _sync_ruoli()
    except Exception as e:
        logger.warning("Sync ruoli: %s", e)
    return f"✅ Cambio ruolo di <b>{c['nome_common']}</b> annullato: torna {c['ruolo_da'] or 'senza ruolo'}."


async def cb_annulla_cambio(update, context):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    await _flusso(q, "crann", "Annulla un cambio ruolo (ultimi 60 giorni)", db.cambi_ruolo_recenti() if q.data == "crann:l" else [],
                  _riga_cr, db.cambio_ruolo, db.perche_no_annulla_cambio, _effetti_cr, _applica_cr, "ann:home")


# rinnovo rookie III-IV

def _riga_rr(r: dict) -> str:
    return f"{r['nome_common']} · {_nome(r['team_id_a'])} · {r['importo']}M × {r['anni_originali']} · {_quando(r['timestamp'])}"


def _effetti_rr(r: dict) -> str:
    return (f"• via il contratto del rinnovo ({r['importo']}M × {r['anni_originali']}): torna il contratto rookie di prima, "
            "finito (x0), di nuovo da rinnovare o da dichiarare RFA\n"
            "• il rinnovo sparisce dai movimenti; nel registro resta la riga\n• avviso al GM, foglio aggiornato")


async def _applica_rr(bot, r: dict, user) -> str:
    try:
        db.annulla_rinnovo_rookie(r["id"])
    except ValueError as e:
        return f"❌ Non si può: {e}."
    from handlers.registro import segna
    await segna(bot, user, "admin", "rinnovo rookie annullato", squadre=r["team_id_a"], giocatore_id=r["giocatore_id"],
                oggetto=r["nome_common"], prima=f"{r['importo']}M × {r['anni_originali']}", dopo="x0", nota=r["note"])
    await _ai_gm(bot, r["team_id_a"], f"🛠 Un admin ha annullato il rinnovo rookie di <b>{r['nome_common']}</b>: "
                                      "è di nuovo da rinnovare (o da dichiarare RFA).")
    _sync(r["team_id_a"])
    return f"✅ Rinnovo rookie di <b>{r['nome_common']}</b> annullato."


async def cb_annulla_rinnovo_rookie(update, context):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    await _flusso(q, "rrann", "Annulla un rinnovo rookie (questa stagione)", db.rinnovi_rookie_recenti() if q.data == "rrann:l" else [],
                  _riga_rr, db.rinnovo_rookie, db.perche_no_annulla_rinnovo_rookie, _effetti_rr, _applica_rr, "ann:home")


# tutto insieme: /admin_menu → ↩️ Annulla azioni

async def cb_annulla_home(update, context):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    voci = [("✂️ Un taglio", "annt:l"), ("✍️ Una firma registrata", "annf:l"), ("🏁 Un decadimento", "decann:l"),
            ("👋 Un ritiro di un FA", "ritann:l"), ("🏥 Una DPE", "dpeann:l"), ("🏀 Un'attivazione dei diritti", "attann:l"),
            ("🔁 Un cambio ruolo", "crann:l"), ("📝 Un rinnovo (¼ o ½)", "rna:scegli"), ("🔁 Un rinnovo rookie", "rrann:l")]
    kb = [[B(l, callback_data=c) for l, c in voci[i:i + 2]] for i in range(0, len(voci), 2)]
    kb.append([B("← Menu admin", callback_data="adm:home")])
    await q.edit_message_text("↩️ <b>Annulla azioni</b>\nCosa annullare? Ogni annullamento mostra prima gli effetti e "
                              "lascia la riga nel registro.\n<i>Le trade si annullano con /annulla_trade_admin, le penalità da "
                              "⚠️ Penalità, i 10-day da ⏱ 10-day.</i>", parse_mode="HTML", reply_markup=K(kb))


def get_handlers() -> list:
    return [CallbackQueryHandler(cb_annulla_taglio, pattern=r"^annt:(?:l|(?:t|ok):\d+)$"),
            CallbackQueryHandler(cb_annulla_firma, pattern=r"^annf:(?:l|(?:t|ok):\d+)$"),
            CallbackQueryHandler(cb_annulla_decadimento, pattern=r"^decann:(?:l|(?:t|ok):\d+)$"),
            CallbackQueryHandler(cb_annulla_ritiro, pattern=r"^ritann:(?:l|(?:t|ok):\d+)$"),
            CallbackQueryHandler(cb_annulla_dpe, pattern=r"^dpeann:(?:l|(?:t|ok):\d+)$"),
            CallbackQueryHandler(cb_annulla_attivazione, pattern=r"^attann:(?:l|(?:t|ok):\d+)$"),
            CallbackQueryHandler(cb_annulla_cambio, pattern=r"^crann:(?:l|(?:t|ok):\d+)$"),
            CallbackQueryHandler(cb_annulla_rinnovo_rookie, pattern=r"^rrann:(?:l|(?:t|ok):\d+)$"),
            CallbackQueryHandler(cb_annulla_home, pattern=r"^ann:home$"),
            CommandHandler("correggi_firma", cmd_correggi_firma)]

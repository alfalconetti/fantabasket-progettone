"""
/settings (admin, v5.8.0): le impostazioni di config/settings.json divise per argomento, con nome in
italiano, valore di adesso, unità e limiti. Si cambiano coi bottoni (o /settings chiave valore),
sempre con anteprima e conferma; ogni modifica va sul canale log e sul canale principale.

Pannello admin → «⚙️ Impostazioni». Callback:
  set:home          argomenti
  set:g:<gruppo>    voci di un argomento
  set:k:<n>         cambia la voce n (→ scrivi il valore → anteprima)
  set:ok / set:no   conferma o annulla la bozza

Le chiavi dei numeri del regolamento (shared/regole.py) che mancano nel file valgono il default e si
vedono come «(default)»: alla prima modifica finiscono nel file. I pesi dei fantapunti sono voci a sé
(pesi_fantapunti.pts …); dopo un cambio il trigger di basketball-reference si riscrive subito e il
messaggio ricorda /dev_ricalcola_fp su loucabot. Le tabelle (rookie scale, minimi dei contratti) si
vedono ma si cambiano nel file. Le chiavi che non sono nel catalogo finiscono in «Altre».
"""
import html
import json
import logging
import math
import os

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler,
                          MessageHandler, filters)

import settings
from shared import regole

logger = logging.getLogger(__name__)

VALORE = 1

# (chiave, nome, tipo: int | num, minimo, massimo, unità)
GRUPPI = [
    ("cap", "💰 Cap e roster", [
        ("cap_regular", "Cap in regular season", "int", 50, 500, "M"),
        ("cap_offseason", "Cap in offseason (luxury)", "int", 50, 500, "M"),
        ("salary_floor", "Salary floor", "int", 0, 500, "M"),
        ("roster_max", "Giocatori a roster, massimo", "int", 5, 30, ""),
        ("roster_min_regular", "Giocatori a roster, minimo in stagione", "int", 0, 30, ""),
        ("roster_min_guardie", "Minimo guardie (PG/SG)", "int", 0, 15, ""),
        ("roster_min_ali", "Minimo ali (SF/PF)", "int", 0, 15, ""),
        ("roster_min_centri", "Minimo centri (C)", "int", 0, 15, ""),
    ]),
    ("contratti", "📝 Contratti e rinnovi", [
        ("soglia_anni_2", "Contratto almeno x2 da", "int", 1, 200, "M"),
        ("soglia_anni_3", "Contratto almeno x3 da", "int", 1, 200, "M"),
        ("max_rinnovi_standard", "Rinnovi normali a squadra", "int", 0, 15, ""),
        ("stepien_anni", "Stepien: finestra di anni", "int", 1, 10, "anni"),
        ("doncic_soglia_1", "Doncic: prima fascia da", "num", 0, 100, "FP"),
        ("doncic_soglia_2", "Doncic: seconda fascia da", "num", 0, 100, "FP"),
    ]),
    ("ruoli", "🎽 Ruoli", [
        ("ore_comunicazione_ruolo", "Ore per dichiarare il ruolo (firma, trade)", "int", 1, 240, "ore"),
        ("giorni_riacquisto_ruolo", "Ripreso entro: torna col vecchio ruolo", "int", 0, 365, "giorni"),
        ("max_cambi_ruolo_ordinari", "Cambi ruolo ordinari a stagione", "int", 0, 20, ""),
        ("giorni_erminio", "Erminio: entro", "int", 0, 90, "giorni"),
        ("giorni_saedro", "Saedro: durata", "int", 1, 90, "giorni"),
    ]),
    ("tagli", "✂️ Tagli, DPE e 10-day", [
        ("max_tagli_gratuiti", "Tagli 1x1 gratuiti a stagione", "int", 0, 20, ""),
        ("riduzione_dpe_percento", "Riduzione del contratto con la DPE", "num", 0, 100, "%"),
        ("giorni_10day", "Durata del 10-day", "int", 1, 60, "giorni"),
        ("max_10day_per_giocatore", "10-day per giocatore a stagione", "int", 0, 10, ""),
    ]),
    ("partita", "🏀 Partita", [
        ("bonus_casa", "Bonus casa", "num", 0, 50, "punti"),
        ("bonus_casa_playoff", "Bonus casa nei playoff", "num", 0, 50, "punti"),
        ("scarto_minimo", "Scarto per vincere senza supplementari", "num", 0, 50, "punti"),
        ("giocatori_panchina", "Giocatori in panchina (= supplementari)", "int", 1, 10, ""),
    ]),
    ("fp", "🧮 Fantapunti", [
        (f"pesi_fantapunti.{k}", n, "num", -20, 20, "")
        for k, n in [("pts", "Punto"), ("ast", "Assist"), ("oreb", "Rimbalzo offensivo"), ("dreb", "Rimbalzo difensivo"),
                     ("tpm", "Tripla segnata"), ("fga", "Tiro dal campo tentato"), ("fgm", "Tiro dal campo segnato"),
                     ("fta", "Libero tentato"), ("ftm", "Libero segnato"), ("stl", "Recupero"), ("blk", "Stoppata"),
                     ("tov", "Palla persa")]
    ]),
    ("aste", "🔨 Aste e free agency", [
        ("durata_asta_ore", "Durata dell'asta dopo l'ultimo rilancio", "int", 1, 240, "ore"),
        ("rilancio_minimo", "Rilancio minimo", "int", 1, 50, "M"),
        ("timeout_firma_fa_ore", "Tempo per firmare dopo un'asta FA", "int", 1, 240, "ore"),
        ("timeout_firma_rfa_ore", "Tempo per firmare dopo un'asta RFA", "int", 1, 240, "ore"),
        ("timeout_pareggio_ore", "Tempo per pareggiare (RFA)", "int", 1, 240, "ore"),
        ("fascia_bassa_max", "Pareggio RFA: fascia bassa fino a", "int", 0, 200, "M"),
        ("fascia_media_max", "Pareggio RFA: fascia media fino a", "int", 0, 200, "M"),
        ("notifica_minuti_scadenza", "Avviso prima della scadenza di un'asta", "int", 1, 600, "minuti"),
    ]),
    ("sistema", "🛠 Sistema", [
        ("numero_teams", "Squadre della lega", "int", 2, 60, ""),
        ("paginazione_aste", "Aste per pagina", "int", 1, 50, ""),
        ("paginazione_fa", "Free agent per pagina", "int", 1, 50, ""),
        ("backup_intervallo_ore", "Backup del bot aste ogni", "int", 1, 168, "ore"),
    ]),
]
TABELLE = {"rookie_scale": "Rookie scale", "tabella_minimo_contratto": "Minimi dei contratti per fantapunti"}
NOTE = {"fp": "Dopo un cambio dei pesi: /dev_ricalcola_fp su loucabot per ricalcolare la stagione "
              "(le giornate convalidate restano come sono).",
        "partita": "Valgono per i calcoli da adesso: le giornate convalidate restano come sono."}


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _file() -> dict:
    with open(settings.SETTINGS_PATH, encoding="utf-8") as f:
        return json.load(f)


def voci() -> list[tuple]:
    """Tutte le voci modificabili: catalogo + chiavi semplici del file che non ci sono ("altre")."""
    out = [(g, *v) for g, _, vv in GRUPPI for v in vv]
    note = {v[1].split(".")[0] for v in out} | set(TABELLE)
    for k, v in _file().items():
        if k not in note and isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(("altre", k, k, "int" if isinstance(v, int) else "num", None, None, ""))
    return out


def gruppi() -> list[tuple[str, str]]:
    g = [(x, n) for x, n, _ in GRUPPI]
    if any(v[0] == "altre" for v in voci()):
        g.append(("altre", "🗂 Altre"))
    return g + [("tabelle", "📋 Tabelle")]


def leggi(chiave: str):
    """(valore, è il default?)"""
    d = _file()
    if chiave.startswith("pesi_fantapunti."):
        k = chiave.split(".", 1)[1]
        mie = d.get("pesi_fantapunti") or {}
        return (mie[k], False) if k in mie else (regole.PESI_FANTAPUNTI[k], True)
    if chiave in d:
        return d[chiave], False
    if chiave in regole.DEFAULT:
        return regole.DEFAULT[chiave], True
    return None, True


def fmt(v) -> str:
    if isinstance(v, float):
        v = int(v) if v == int(v) else v
    return str(v).replace(".", ",")


def converti(voce: tuple, testo: str):
    """→ (valore, errore)"""
    _, _, nome, tipo, mn, mx, _ = voce
    t = (testo or "").strip().replace(",", ".")
    try:
        v = int(t) if tipo == "int" else float(t)
    except ValueError:
        return None, f"Serve un numero {'intero' if tipo == 'int' else '(anche con la virgola)'}."
    if not math.isfinite(v):
        return None, "Serve un numero vero."
    if tipo == "num" and v == int(v):
        v = int(v)
    if mn is not None and not (mn <= v <= mx):
        return None, f"Il valore deve stare tra {fmt(mn)} e {fmt(mx)}."
    return v, None


def scrivi(chiave: str, valore) -> None:
    """Scrive una sola chiave rileggendo il file (non sovrascrive cambi fatti nel frattempo), in modo atomico."""
    d = _file()
    if chiave.startswith("pesi_fantapunti."):
        d["pesi_fantapunti"] = {**regole.PESI_FANTAPUNTI, **(d.get("pesi_fantapunti") or {}), chiave.split(".", 1)[1]: valore}
    else:
        d[chiave] = valore
    testo = json.dumps(d, ensure_ascii=False, indent=2)
    p = settings.SETTINGS_PATH
    tmp = p + ".tmp"
    try:
        st = os.stat(p)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(testo)
        os.chmod(tmp, st.st_mode & 0o7777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)       # resta di chi era (modificabile da fuori come prima)
        except (PermissionError, AttributeError):
            pass
        os.replace(tmp, p)
    except OSError:
        # cartella non scrivibile: come prima della v5.8.0, sul file stesso
        if os.path.exists(tmp):
            os.remove(tmp)
        with open(p, "w", encoding="utf-8") as f:
            f.write(testo)


# ── testi e tastiere ───────────────────────────────────────────────────────────

def home() -> tuple[str, K]:
    kb = [B(n, callback_data=f"set:g:{g}") for g, n in gruppi()]
    return ("⚙️ <b>Impostazioni</b>\nScegli un argomento. Ogni modifica chiede conferma e va sul canale log e sul "
            "canale principale.\nScorciatoia: <code>/settings chiave valore</code>",
            K([kb[i:i + 2] for i in range(0, len(kb), 2)]))


def _riga(v: tuple) -> str:
    val, dflt = leggi(v[1])
    unita = f" {v[6]}" if v[6] else ""
    return f"• {e(v[2])}: <b>{e(fmt(val))}{e(unita)}</b>" + (" <i>(default)</i>" if dflt else "")


def gruppo(g: str) -> tuple[str, K]:
    indietro = [B("← Argomenti", callback_data="set:home")]
    if g == "tabelle":
        d = _file()
        righe = ["📋 <b>Tabelle</b> (si cambiano nel file config/settings.json)", ""]
        tab = d.get("tabella_minimo_contratto") or []
        righe.append(f"<b>{TABELLE['tabella_minimo_contratto']}</b>")
        righe += [f"• {fmt(x.get('da'))}–{fmt(x.get('a'))} FP → {x.get('minimo')}M" for x in tab] or ["—"]
        righe += ["", f"<b>{TABELLE['rookie_scale']}</b>"]
        for fascia, anni in (d.get("rookie_scale") or {}).items():
            righe.append(f"• fascia {e(fascia)}: " + " · ".join(f"{x.get('anno')}° {x.get('imp')}M x{x.get('anni')}" for x in anni))
        return "\n".join(righe), K([indietro])
    tutte = voci()
    nome = dict(gruppi()).get(g, g)
    mie = [(i, v) for i, v in enumerate(tutte) if v[0] == g]
    righe = [f"<b>{e(nome)}</b>", ""] + [_riga(v) for _, v in mie]
    if g in NOTE:
        righe += ["", f"<i>{e(NOTE[g])}</i>"]
    righe += ["", "Tocca una voce per cambiarla."]
    kb = [[B(f"✏️ {v[2]}", callback_data=f"set:k:{i}")] for i, v in mie]
    return "\n".join(righe), K(kb + [indietro])


def anteprima(v: tuple, nuovo) -> tuple[str, K]:
    vecchio, dflt = leggi(v[1])
    unita = f" {v[6]}" if v[6] else ""
    t = (f"⚙️ <b>{e(v[2])}</b>\n<code>{e(v[1])}</code>\n\n{e(fmt(vecchio))}{e(unita)}{' (default)' if dflt else ''} → "
         f"<b>{e(fmt(nuovo))}{e(unita)}</b>\n\nConfermi? Va sul canale log e sul canale principale.")
    if v[0] in NOTE:
        t += f"\n\n<i>{e(NOTE[v[0]])}</i>"
    return t, K([[B("✅ Conferma", callback_data="set:ok"), B("❌ Annulla", callback_data="set:no")]])


async def _manda(bot, chat_id, testo: str):
    if not chat_id:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=testo, parse_mode="HTML")
    except Exception as err:
        logger.warning("Impostazioni, messaggio a %s: %s", chat_id, err)


def _chi(user) -> str:
    return (user.first_name or str(user.id)) + (f" (@{user.username})" if user.username else "")


async def applica(bot, user, chiave: str, nuovo) -> str:
    v = next(x for x in voci() if x[1] == chiave)
    vecchio, _ = leggi(chiave)
    scrivi(chiave, nuovo)
    unita = f" {v[6]}" if v[6] else ""
    extra = ""
    if chiave.startswith("pesi_fantapunti."):
        try:
            import database as db
            regole.allinea_bref(db._q)
        except Exception as err:
            logger.warning("bref_stats: trigger non aggiornato (%s)", err)
        extra = "\nPer ricalcolare i fantapunti della stagione: /dev_ricalcola_fp su loucabot."
    g = settings.load_globals()
    pubblico = f"⚙️ <b>Impostazioni</b> · {e(v[2])}: {e(fmt(vecchio))}{e(unita)} → <b>{e(fmt(nuovo))}{e(unita)}</b>"
    await _manda(bot, g.get("main_channel_id"), pubblico)
    await _manda(bot, g.get("log_channel_id_main"), f"{pubblico}\n<code>{e(chiave)}</code> · admin {e(_chi(user))}{e(extra)}")
    return pubblico + e(extra)


# ── handler ───────────────────────────────────────────────────────────────────

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/settings → argomenti; /settings chiave → la voce; /settings chiave valore → anteprima."""
    if not settings.is_admin(update.effective_user.id):
        return
    msg = update.effective_message
    chat = getattr(update, "effective_chat", None)
    if chat and getattr(chat, "type", "private") != "private":
        await msg.reply_text("⚙️ /settings si usa in privato col bot.")
        return
    args = context.args or []
    if not args:
        t, kb = home()
        await msg.reply_text(t, parse_mode="HTML", reply_markup=kb)
        return
    v = next((x for x in voci() if x[1] == args[0]), None)
    if not v:
        if args[0] in TABELLE:
            t, kb = gruppo("tabelle")
            await msg.reply_text(t, parse_mode="HTML", reply_markup=kb)
            return
        simili = [x[1] for x in voci() if args[0].lower() in x[1].lower() or args[0].lower() in x[2].lower()][:8]
        await msg.reply_text(f"❌ Chiave <code>{e(args[0])}</code> non trovata."
                             + (("\nForse: " + ", ".join(f"<code>{e(s)}</code>" for s in simili)) if simili else "")
                             + "\n/settings per l'elenco.", parse_mode="HTML")
        return
    if len(args) < 2:
        await msg.reply_text(_riga(v) + f"\n<code>/settings {e(v[1])} VALORE</code>", parse_mode="HTML")
        return
    nuovo, err = converti(v, args[1])
    if err:
        await msg.reply_text(f"❌ {e(err)}")
        return
    context.user_data["set_bozza"] = (v[1], nuovo)
    t, kb = anteprima(v, nuovo)
    await msg.reply_text(t, parse_mode="HTML", reply_markup=kb)


async def cb_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not settings.is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer()
    parti = q.data.split(":")
    if parti[1] == "home":
        t, kb = home()
    elif parti[1] == "g":
        t, kb = gruppo(parti[2])
    elif parti[1] == "no":
        context.user_data.pop("set_bozza", None)
        t, kb = "Annullato: niente è cambiato.", K([[B("← Argomenti", callback_data="set:home")]])
    elif parti[1] == "ok":
        bozza = context.user_data.pop("set_bozza", None)
        if not bozza:
            t, kb = "Niente da confermare (già fatto o scaduto).", K([[B("← Argomenti", callback_data="set:home")]])
        else:
            fatto = await applica(context.bot, q.from_user, *bozza)
            g = next((x[0] for x in voci() if x[1] == bozza[0]), "home")
            t, kb = "✅ Fatto.\n\n" + fatto, K([[B("← Torna all'argomento", callback_data=f"set:g:{g}")]])
    else:
        return
    await q.edit_message_text(t, parse_mode="HTML", reply_markup=kb)


async def cb_voce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not settings.is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    tutte = voci()
    i = int(q.data.split(":")[2])
    if i >= len(tutte):
        return ConversationHandler.END
    v = tutte[i]
    context.user_data["set_voce"] = v[1]
    limiti = f"\nTra {fmt(v[4])} e {fmt(v[5])}" + (", intero." if v[3] == "int" else ", anche con la virgola.") if v[4] is not None else ""
    await q.edit_message_text(f"✏️ {_riga(v)}{limiti}\n\nScrivi il nuovo valore. /annulla per uscire.", parse_mode="HTML")
    return VALORE


async def msg_valore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chiave = context.user_data.get("set_voce")
    v = next((x for x in voci() if x[1] == chiave), None)
    if not v:
        return ConversationHandler.END
    nuovo, err = converti(v, update.effective_message.text)
    if err:
        await update.effective_message.reply_text(f"❌ {err} Riscrivilo o /annulla.")
        return VALORE
    context.user_data.pop("set_voce", None)
    context.user_data["set_bozza"] = (v[1], nuovo)
    t, kb = anteprima(v, nuovo)
    await update.effective_message.reply_text(t, parse_mode="HTML", reply_markup=kb)
    return ConversationHandler.END


async def annulla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("set_voce", None)
    context.user_data.pop("set_bozza", None)
    await update.effective_message.reply_text("Annullato.")
    return ConversationHandler.END


def get_handlers() -> list:
    return [
        ConversationHandler(
            entry_points=[CallbackQueryHandler(cb_voce, pattern=r"^set:k:\d+$")],
            states={VALORE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, msg_valore)]},
            fallbacks=[CommandHandler(["annulla", "annulla_admin"], annulla)],
            conversation_timeout=900, name="impostazioni_valore", allow_reentry=True),
        CommandHandler("settings", cmd_settings),
        CallbackQueryHandler(cb_settings, pattern=r"^set:(?:home|ok|no|g:\w+)$"),
    ]

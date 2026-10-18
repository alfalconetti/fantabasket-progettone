"""
Squadre: /list, /listteams (cap e slot di tutte), /team (una squadra), /firme, e per i GM
/autocap e /autoslot (cap e slot anticipati, con i bottoni per azzerarli: reset_cap_ant:,
reset_slot_ant:). /team, /autocap e /autoslot sono registrati in user.py.
"""
import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import teams as tm
import utils
import settings
from handlers.admin_comune import is_admin

logger = logging.getLogger(__name__)


# ── /listteams ────────────────────────────────────────────────────────────────

async def listteams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cap e slot di tutte le squadre, una riga ciascuna — disponibile a tutti.
    Avvisi: in offseason chi sta sopra il cap di regular season (150 meno la penalità),
    in regular season chi è sotto il salary floor."""
    s = settings.get()
    stagione = utils.load_globals().get("stagione_corrente", "2025")
    offseason = utils.load_globals().get("fase", "").startswith("offseason")
    tetto = settings.cap_limite()
    slot_max = s.get("roster_max", 15)
    if offseason:
        intest = f"<b>🏀 Squadre</b> — offseason (tetto {tetto}M, in regular season {s['cap_regular']}M)"
    else:
        intest = f"<b>🏀 Squadre</b> — regular season (tetto {tetto}M meno penalità, floor {s['salary_floor']}M)"
    righe = [intest, ""]
    for t in tm.get_all_teams():
        cap_disp, slot_disp = utils.cap_slot_display(t, stagione)
        occupato = utils.cap_impegnato_display(t, stagione)
        pen = int(t.get("cap_penalizzato") or 0)
        tetto_t = tetto - settings.penalita_cap(t)
        cap_virt, slot_virt = db.get_cap_virtuale(t["id"]), db.get_slot_virtuali(t["id"])
        riga = (f"<b>{t['nome']}</b> (<code>{t['id']}</code>) — 💰 {occupato}/{tetto_t}M · "
                f"{cap_disp - cap_virt}M liberi · 🪑 {slot_max - slot_disp}/{slot_max}")
        if cap_virt or slot_virt:
            riga += f" · ⏳ {cap_virt}M e {slot_virt} slot in aste"
        if offseason and occupato > s["cap_regular"] - pen:
            riga += f" ⚠️ sopra {s['cap_regular'] - pen} in RS"
        elif not offseason and occupato < s["salary_floor"]:
            riga += f" ⚠️ sotto il floor"
        if cap_disp - cap_virt < 0 or slot_disp - slot_virt < 0:
            riga += " 🔴 negativo"
        righe.append(riga)
    blocco = ""
    for r in righe:                          # spezza solo tra una riga e l'altra (tag HTML interi)
        if len(blocco) + len(r) > 3900:
            await update.effective_message.reply_text(blocco, parse_mode="HTML")
            blocco = ""
        blocco += r + "\n"
    await update.effective_message.reply_text(blocco, parse_mode="HTML")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista asciutta nome/id/gm — solo admin."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    all_teams = tm.get_all_teams()
    righe = ["<b>📋 Squadre</b>\n"]
    for t in all_teams:
        gm_nome = t.get("gm_nome", "—")
        righe.append(f"<b>{t['nome']}</b> — <code>{t['id']}</code> — {gm_nome}")

    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")


# ── /autocap ─────────────────────────────────────────────────────────────────

async def autocap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    GM aggiunge cap anticipato temporaneo (48h) in caso di trade notturna non ancora ufficializzata.
    Il cap anticipato viene sommato al cap libero reale per permettere offerte.
    Notifica al gruppo admin con bottone Reset.
    """
    import pg_client
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if team is None:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text(
            "Uso: /autocap &lt;importo&gt;\nEsempio: /autocap 15\n\n"
            "<i>⚠️ Solo per emergenze notturne — trade appena avvenuta non ancora ufficializzata. "
            "La richiesta viene segnalata agli admin. "
            "Il cap anticipato scade automaticamente dopo 48h. "
            "In caso di dichiarazione falsa saranno applicate penalità.</i>",
            parse_mode="HTML",
        )
        return

    try:
        importo = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ L'importo deve essere un numero intero.")
        return

    if importo <= 0:
        await update.effective_message.reply_text("❌ L'importo deve essere positivo.")
        return

    # Controlla che non superi cap_limite
    stagione = utils.load_globals().get("stagione_corrente", "2025")
    cap_pen  = settings.penalita_cap(team)  # 0 in offseason: tetto 165 per tutti
    if pg_client.pg_disponibile():
        cap_occ = pg_client.get_cap_contratti(team["id"], stagione) + pg_client.get_impatto_taglio(team["id"], stagione) + cap_pen
    else:
        cap_occ = settings.cap_massimo() - team.get("cap_disponibile", 0)
    cap_libero_reale = settings.cap_limite() - cap_occ

    if importo > cap_libero_reale + importo:  # non può mai avere più di cap_limite totale
        await update.effective_message.reply_text(
            f"❌ Importo non valido. Il tuo cap libero reale è {cap_libero_reale}M."
        )
        return

    # Salva cap anticipato su PG (sostituisce eventuale precedente)
    pg_client.set_cap_anticipato(team["id"], importo)
    from registro import segna
    await segna(context.bot, user, "gm", "cap anticipato", squadre=team["id"], oggetto="cap anticipato",
                dopo=f"+{importo}M", nota="in attesa della trade")

    from datetime import datetime, timezone
    ora = utils.format_dt(datetime.now(timezone.utc).isoformat())
    await update.effective_message.reply_text(
        f"✅ Cap anticipato di <b>+{importo}M</b> aggiunto.\n"
        f"Scade automaticamente tra 48h.\n\n"
        f"<i>La richiesta è stata segnalata agli admin.</i>",
        parse_mode="HTML",
    )

    # Notifica gruppo admin con bottone Reset
    admin_group_id = utils.load_globals().get("admin_group_id")
    if admin_group_id:
        gm_tag = f"@{user.username}" if user.username else user.first_name
        notifica = (
            f"⚡ <b>Cap anticipato richiesto</b>\n\n"
            f"👤 {user.first_name} ({gm_tag}) — <b>{team['nome']}</b>\n"
            f"💰 +{importo}M anticipati\n"
            f"📊 Cap libero reale: {cap_libero_reale}M\n"
            f"🕐 {ora} — scade tra 48h\n\n"
            f"<i>Verifica che la trade sia in corso. "
            f"Resetta dopo l'ufficializzazione o in caso di abuso (+ penalità).</i>"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔄 Reset cap anticipato",
                callback_data=f"reset_cap_ant:{team['id']}"
            )
        ]])
        try:
            msg = await context.bot.send_message(
                chat_id=admin_group_id, text=notifica,
                parse_mode="HTML", reply_markup=kb
            )
            # Salva message_id per poter editare il messaggio al reset
            pg_client.set_cap_anticipato(team["id"], importo, message_id=msg.message_id)
        except Exception as e:
            logger.warning("notifica autocap gruppo admin: %s", e)

    logger.info("autocap: team=%s importo=%d gm=%d", team["id"], importo, user.id)


async def cb_reset_cap_anticipato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin resetta il cap anticipato di un team — con check che non vada in negativo."""
    import pg_client
    query = update.callback_query
    await query.answer()
    team_id = query.data.split(":")[1]
    team    = tm.get_team_by_id(team_id)

    stagione   = utils.load_globals().get("stagione_corrente", "2025")
    cap_pen    = settings.penalita_cap(team)  # 0 in offseason: tetto 165 per tutti
    cap_ant    = pg_client.get_cap_anticipato(team_id)
    cap_virt   = 0  # cap virtuale dalle offerte in corso

    # Importa db SQLite del bot aste per cap_virtuale
    try:
        import database as db_aste
        cap_virt = db_aste.get_cap_virtuale(team_id)
    except Exception:
        pass

    if pg_client.pg_disponibile():
        cap_occ = pg_client.get_cap_contratti(team_id, stagione) + pg_client.get_impatto_taglio(team_id, stagione) + cap_pen
    else:
        cap_occ = settings.cap_massimo() - (team.get("cap_disponibile", 0) if team else 0)

    cap_libero_reale = settings.cap_limite() - cap_occ - cap_virt

    if cap_libero_reale < 0:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"⚠️ <b>Reset impossibile</b>\n\n"
            f"<b>{team['nome'] if team else team_id}</b> andrebbe in negativo di "
            f"<b>{abs(cap_libero_reale)}M</b> senza il cap anticipato.\n"
            f"La trade deve essere prima ufficializzata.",
            parse_mode="HTML",
        )
        return

    pg_client.reset_cap_anticipato(team_id)
    from registro import segna
    await segna(context.bot, query.from_user, "admin", "cap anticipato tolto", squadre=team_id, oggetto="cap anticipato",
                dopo="tolto")
    await query.edit_message_text(
        query.message.text + f"\n\n✅ <b>Cap anticipato resettato</b> da {query.from_user.first_name}.",
        parse_mode="HTML",
        reply_markup=None,
    )
    logger.info("reset_cap_anticipato: team=%s admin=%d", team_id, query.from_user.id)


async def cb_reset_slot_anticipato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin resetta lo slot anticipato di un team."""
    import pg_client
    query = update.callback_query
    await query.answer()
    team_id = query.data.split(":")[1]
    team    = tm.get_team_by_id(team_id)

    slot_ant  = pg_client.get_slot_anticipato(team_id)
    try:
        import database as db_aste
        slot_virt = db_aste.get_slot_virtuali(team_id)
    except Exception:
        slot_virt = 0

    slot_reale = pg_client.get_slot_totale(team_id, stagione=utils.get_stagione_corrente()) - slot_ant - slot_virt
    if slot_reale < 0:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"⚠️ <b>Reset impossibile</b>\n\n"
            f"<b>{team['nome'] if team else team_id}</b> andrebbe sotto il minimo roster senza lo slot anticipato.",
            parse_mode="HTML",
        )
        return

    pg_client.reset_slot_anticipato(team_id)
    from registro import segna
    await segna(context.bot, query.from_user, "admin", "slot anticipato tolto", squadre=team_id,
                oggetto="slot anticipato", prima=f"+{slot_ant}", dopo="tolto")
    await query.edit_message_text(
        query.message.text + f"\n\n✅ <b>Slot anticipato resettato</b> da {query.from_user.first_name}.",
        parse_mode="HTML",
        reply_markup=None,
    )
    logger.info("reset_slot_anticipato: team=%s admin=%d", team_id, query.from_user.id)


# ── /auto_slot ───────────────────────────────────────────────────────────────

async def auto_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GM aggiunge slot anticipato temporaneo (48h) — analogo ad autocap."""
    import pg_client
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if team is None:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text(
            "Uso: /autoslot &lt;quantita&gt;\nEsempio: /autoslot 1\n\n"
            "<i>⚠️ Solo per emergenze notturne. "
            "Lo slot anticipato scade automaticamente dopo 48h.</i>",
            parse_mode="HTML",
        )
        return
    try:
        quantita = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ La quantità deve essere un numero intero.")
        return
    if quantita <= 0:
        await update.effective_message.reply_text("❌ La quantità deve essere positiva.")
        return

    slot_reale = pg_client.get_slot_totale(team["id"]) if pg_client.pg_disponibile() else team.get("slot_disponibili", 0)
    if slot_reale + quantita > settings.slot_massimo():
        await update.effective_message.reply_text(
            f"❌ Non puoi anticipare {quantita} slot — supereresti il massimo roster ({settings.slot_massimo()})."
        )
        return

    pg_client.set_slot_anticipato(team["id"], quantita)
    from registro import segna
    await segna(context.bot, user, "gm", "slot anticipato", squadre=team["id"], oggetto="slot anticipato",
                dopo=f"+{quantita}", nota="in attesa della trade")
    from datetime import datetime, timezone
    ora = utils.format_dt(datetime.now(timezone.utc).isoformat())
    await update.effective_message.reply_text(
        f"✅ Slot anticipato di <b>+{quantita}</b> aggiunto.\n"
        f"Scade automaticamente tra 48h.\n\n"
        f"<i>La richiesta è stata segnalata agli admin.</i>",
        parse_mode="HTML",
    )

    admin_group_id = utils.load_globals().get("admin_group_id")
    if admin_group_id:
        gm_tag = f"@{user.username}" if user.username else user.first_name
        notifica = (
            f"⚡ <b>Slot anticipato richiesto</b>\n\n"
            f"👤 {user.first_name} ({gm_tag}) — <b>{team['nome']}</b>\n"
            f"🪑 +{quantita} slot anticipati\n"
            f"🕐 {ora} — scade tra 48h\n\n"
            f"<i>Verifica che la trade sia in corso. Resetta dopo l'ufficializzazione.</i>"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔄 Reset slot anticipato",
                callback_data=f"reset_slot_ant:{team['id']}"
            )
        ]])
        try:
            msg = await context.bot.send_message(
                chat_id=admin_group_id, text=notifica,
                parse_mode="HTML", reply_markup=kb
            )
            pg_client.set_slot_anticipato(team["id"], quantita, message_id=msg.message_id)
        except Exception as e:
            logger.warning("notifica autoslot gruppo admin: %s", e)

    logger.info("autoslot: team=%s quantita=%d gm=%d", team["id"], quantita, user.id)


# ── /team ─────────────────────────────────────────────────────────────────────

async def cmd_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mostra la situazione completa di una squadra. Disponibile a tutti.
    Uso: /team [squadra] — id, nome della squadra o del GM, anche solo l'inizio o con un
    errore di battitura (stessa ricerca di /roster nel bot principale). Senza argomento:
    la propria squadra.
    """
    if context.args:
        testo = " ".join(context.args)
        team = tm.get_team_by_query(testo)
        if team is None:
            await update.effective_message.reply_text(
                f"❌ Nessuna squadra trovata per «{html.escape(testo)}». Usa /listteams per la lista.",
                parse_mode="HTML",
            )
            return
    else:
        team = tm.get_team_by_gm(update.effective_user.id)
        if team is None:
            await update.effective_message.reply_text(
                "Uso: /team &lt;squadra&gt; — id, nome della squadra o del GM\n"
                "Esempio: /team team07 oppure /team Rossi",
                parse_mode="HTML",
            )
            return
    team_id = team["id"]

    stagione       = utils.load_globals().get("stagione_corrente", "2025")
    cap_tot, slot_tot = utils.cap_slot_display(team, stagione)
    cap_virtuale   = db.get_cap_virtuale(team_id)
    slot_impegnati = db.get_slot_virtuali(team_id)
    cap_libero     = cap_tot - cap_virtuale
    slot_liberi    = slot_tot - slot_impegnati
    offerte_vince  = db.get_offerte_vincenti_team(team_id)

    fase = utils.load_globals().get("fase", "offseason")
    cap_pen = team.get("cap_penalizzato", 0)
    s = settings.get()
    cap_impegnati_contratti  = utils.cap_impegnato_display(team, stagione)
    slot_impegnati_contratti = s.get("slot_massimo", 15) - slot_tot

    righe = [
        f"🏀 <b>{team['nome']}</b>",
        f"<i>ID: <code>{team_id}</code></i>",
        "",
        f"💰 <b>{cap_impegnati_contratti}M</b> impegnati (contratti + tagli)",
        f"💰 Cap disponibile {utils.etichetta_cap()}: <b>{cap_tot}M</b>",
        f"⏳ Cap virtualmente impegnato: <b>{cap_virtuale}M</b>",
        f"✅ Cap effettivamente libero: <b>{cap_libero}M</b>",
    ]

    if fase.startswith("offseason"):
        rfa_attive = db.get_rfa_proprietario(team_id)
        if rfa_attive:
            cap_rfa = sum(r["vecchio_compenso"] or 0 for r in rfa_attive)
            nomi_rfa = ", ".join(r["giocatore"] for r in rfa_attive)
            righe.append(f"⚠️ Cap occupato da RFA: <b>{cap_rfa}M</b> ({nomi_rfa})")
        # In offseason il tetto è 165 per tutti; in RS si perde il margine
        # di luxury (165 → 150) e si applica l'eventuale penalità
        delta = s["cap_offseason"] - s["cap_regular"] + cap_pen
        cap_rs = cap_libero - delta
        nota_pen = f", penalità {cap_pen}M" if cap_pen else ""
        righe.append(f"📉 Cap libero in Regular Season: <b>{cap_rs}M</b> (-{delta}M{nota_pen})")

    righe += [
        "",
        f"🪑 <b>{slot_impegnati_contratti}</b> slot impegnati in contratti",
        f"🪑 Slot totali: <b>{slot_tot}</b>",
        f"⏳ Slot virtualmente impegnati: <b>{slot_impegnati}</b>",
        f"✅ Slot effettivamente liberi: <b>{slot_liberi}</b>",
    ]

    if offerte_vince:
        righe.append("")
        righe.append("<i>Offerte vincenti in corso:</i>")
        for o in offerte_vince:
            righe.append(
                f"  • {o['giocatore']} — {o['offerta_corrente']}M "
                f"(scade {utils.format_dt(o['scade_at'])})"
            )

    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")


# ── /firme ────────────────────────────────────────────────────────────────────

async def cmd_firme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ultime N firme concluse con nome squadra invece di team_id.
    Solo admin. Uso: /firme [N] (default 10)
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    try:
        n = int(context.args[0]) if context.args else 10
        if n <= 0 or n > 100:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text("❌ N deve essere un intero tra 1 e 100.")
        return

    firme = db.get_ultime_firme(n)
    if not firme:
        await update.effective_message.reply_text("Nessuna firma conclusa nel DB.")
        return

    teams_map_dict = {t["id"]: t["nome"] for t in tm.get_all_teams()}
    righe = [f"✍️ <b>Ultime {len(firme)} firme</b>", ""]
    for f in firme:
        team_nome = teams_map_dict.get(f["offerente_team_id"], f["offerente_team_id"])
        anni = f["anni_contratto"] or "?"
        righe.append(
            f"#{f['id']} <b>{f['giocatore']}</b> → {team_nome}\n"
            f"  💰 {f['offerta_corrente']}M × {anni} anni — "
            f"{utils.format_dt(f['conclusa_at'])}"
        )

    testo = "\n".join(righe)
    from shared.messaggi import manda_lungo     # se è lungo arriva come file .md
    await manda_lungo(context.bot, update.effective_chat.id, testo, "firme")

"""
Handler per il decadimento contratti.
Casi: ritiro, firma in altra lega, giocatore svincolato da lungo tempo.
Il contratto viene annullato senza impatto sui tagli gratuiti.
Flusso GM: richiesta → gruppo admin → approvazione → DB + canale
Flusso admin: diretto da /admin_menu → 🏁 Decadimento (decadm:)
"""
import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler
)

import database as db
import teams as tm
import settings
from settings import solo_privato, richiede_fase, FASI_TRADE_APERTE
from utils import format_dt, ROME
from datetime import datetime

logger = logging.getLogger(__name__)

# Stati ConversationHandler
DEC_SQUADRA, DEC_GIOCATORE, DEC_MOTIVO = range(50, 53)

MOTIVI = {
    "ritiro":     "🏁 Ritiro dal basket",
    "altra_lega": "🌍 Firma in altra lega",
    "cam_thomas": "✂️ Cam Thomas exception",
    "altro":      "📝 Altro",
}
# Cam Thomas exception (regolamento, Tagli): giocatore tagliato in NBA e senza squadra da
# almeno un mese di mercato NBA aperto → il GM può chiedere il decadimento gratuito
# (condizioni verificate dagli admin). Le spalmature restano. Se la stessa squadra lo
# rifirma entro un anno deve dargli almeno il contratto precedente: il bot aste lo
# controlla leggendo questa transazione (nota "Cam Thomas").
NOTA_CAM_THOMAS = "Cam Thomas"
TOGLIE_ALTRE = ("ritiro", "altra_lega")        # tolgono anche le spalmature di chi l'aveva tagliato prima


def causa_da_nota(nota: str | None) -> str:
    """La chiave di MOTIVI dalla nota della transazione (anche scritta a mano, con o senza emoji)."""
    n = (nota or "").lower()
    if "cam thomas" in n:
        return "cam_thomas"
    if "ritiro" in n:
        return "ritiro"
    if "altra lega" in n:
        return "altra_lega"
    return "altro"


def cambio_causa(vecchia: str, nuova: str) -> str | None:
    """Perché un cambio di causa non si può fare (None se si può). Da ritiro o altra lega a una causa che lascia
    le spalmature no: quelle tolte alle altre squadre non si rimettono in automatico."""
    if vecchia == nuova:
        return "è già questa la causa"
    if vecchia in TOGLIE_ALTRE and nuova not in TOGLIE_ALTRE:
        return ("con ritiro o altra lega sono già state tolte le spalmature delle altre squadre che l'avevano tagliato, "
                "e non si rimettono da sole: chiedi al dev")
    return None


# ── Flusso GM ──────────────────────────────────────────────────────────────────

@solo_privato
async def cmd_decadimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END

    roster = db.get_roster_team(team["id"], senza_10day=True)
    if not roster:
        await update.effective_message.reply_text("Il tuo roster è vuoto.")
        return ConversationHandler.END

    context.user_data["dec_team_id"] = team["id"]
    stagione = settings.stagione_corrente()
    bottoni = []
    for r in sorted(roster, key=lambda x: -x["importo"]):
        anni = _anni_residui(r, stagione)
        label = f"{r['nome_common']} {r['importo']}x{anni}"
        bottoni.append([InlineKeyboardButton(label, callback_data=f"dec_giocat:{r['giocatore_id']}")])
    bottoni.append([InlineKeyboardButton("❌ Annulla", callback_data="dec_annulla")])

    from handlers import nav
    await nav.mostra(update,
        "⚠️ <b>Decadimento contratto</b>\n\n"
        "Seleziona il giocatore il cui contratto è decaduto "
        "(ritiro, firma in altra lega, ecc.).\n\n"
        "<i>Il contratto verrà annullato senza impatto sui tagli gratuiti.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )
    return DEC_GIOCATORE


async def cb_dec_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ingresso dal bottone del /menu (stesso flusso di /decadimento)."""
    await update.callback_query.answer()
    return await cmd_decadimento(update, context)


async def cb_dec_giocatore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    gid = int(query.data.split(":")[1])
    context.user_data["dec_giocatore_id"] = gid

    giocatore = db.get_giocatore(gid)
    context.user_data["dec_giocatore_nome"] = giocatore["nome_common"]

    bottoni = [[InlineKeyboardButton(label, callback_data=f"dec_motivo:{key}")]
               for key, label in MOTIVI.items()]
    bottoni.append([InlineKeyboardButton("❌ Annulla", callback_data="dec_annulla")])

    await query.edit_message_text(
        f"<b>{giocatore['nome_common']}</b> — seleziona il motivo:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )
    return DEC_MOTIVO


async def cb_dec_motivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    motivo_key  = query.data.split(":")[1]
    motivo_label = MOTIVI.get(motivo_key, motivo_key)

    team_id  = context.user_data["dec_team_id"]
    gid      = context.user_data["dec_giocatore_id"]
    nome     = context.user_data["dec_giocatore_nome"]
    team     = tm.get_team_by_id(team_id)
    user     = update.effective_user
    gm_tag   = f"@{user.username}" if user.username else user.first_name

    if not db.apri_richiesta("decadimento", gid, team_id):
        await query.edit_message_text(
            f"⏳ C'è già una richiesta di decadimento in attesa per <b>{nome}</b>: aspetta la risposta degli admin.",
            parse_mode="HTML")
        context.user_data.clear()
        return ConversationHandler.END

    from handlers.registro import segna
    await segna(context.bot, user, "gm", "decadimento chiesto", squadre=team_id, giocatore_id=gid, oggetto=nome,
                nota=motivo_label)
    await query.edit_message_text(
        f"⏳ Richiesta inviata al gruppo admin.\n\n"
        f"Giocatore: <b>{nome}</b>\n"
        f"Motivo: {motivo_label}",
        parse_mode="HTML",
    )

    # Notifica gruppo admin
    admin_group_id = settings.load_globals().get("admin_group_id")
    if admin_group_id:
        testo = (
            f"⚠️ <b>Richiesta decadimento contratto</b>\n\n"
            f"👤 {user.first_name} ({gm_tag}) — <b>{team['nome']}</b>\n"
            f"🏀 Giocatore: <b>{nome}</b>\n"
            f"📋 Motivo: {motivo_label}\n"
            + (f"✂️ {riga_cam_thomas(gid)}\n" if motivo_key == "cam_thomas" else "") + "\n"
            f"<i>Il contratto verrà annullato senza impatto sui tagli gratuiti. "
            f"Lo slot roster verrà liberato.</i>"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approva", callback_data=f"dec_approva:{team_id}:{gid}:{motivo_key}"),
            InlineKeyboardButton("❌ Rifiuta", callback_data=f"dec_rifiuta:{team_id}:{gid}"),
        ]])
        try:
            await context.bot.send_message(
                chat_id=admin_group_id, text=testo,
                parse_mode="HTML", reply_markup=kb
            )
        except Exception as e:
            logger.warning("Notifica decadimento gruppo admin: %s", e)

    context.user_data.clear()
    return ConversationHandler.END


async def cb_dec_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Richiesta annullata.")
    context.user_data.clear()
    return ConversationHandler.END


# ── Applicazione (comune a approvazione e admin diretto) ──────────────────────

def _is_admin(uid: int) -> bool:
    return uid in [int(a) for a in settings.admin_ids()]


async def _ai_gm(bot, team_id: str, testo: str) -> None:
    for gm in (tm.get_team_by_id(team_id) or {}).get("gm_ids", []):
        try:
            await bot.send_message(chat_id=int(gm), text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Avviso al GM decadimento: %s", e)


def _admin_tag(user) -> str:
    tag = user.first_name or str(user.id)
    return tag + (f" (@{user.username})" if user.username else "")


async def applica_decadimento(bot, team_id: str, gid: int, motivo_key: str, admin_tag: str, user=None,
                              per_conto: bool = False) -> str | None:
    """Esegue il decadimento e lo annuncia. Restituisce un messaggio d'errore o None."""
    motivo_label = MOTIVI.get(motivo_key, motivo_key)
    stagione  = settings.stagione_corrente()
    team      = tm.get_team_by_id(team_id) or {"nome": team_id}
    giocatore = db.get_giocatore(gid)
    contratto = db.get_contratto_attivo(gid)
    if not giocatore:
        return "❌ Giocatore non trovato."
    if not contratto or contratto.get("team_id") != team_id:
        return "❌ Contratto non trovato o già scaduto."
    if contratto.get("tipo") == "10day":
        return "❌ È un 10-day: si chiude dal pannello admin (⏱ 10-day)."

    # Ritiro / altra lega: smettono di pesare anche le spalmature di chi l'aveva tagliato
    # (non per "altro", es. Cam Thomas exception: il giocatore resta in NBA)
    tutte = motivo_key in ("ritiro", "altra_lega")
    altre = db.registra_decadimento(giocatore_id=gid, team_id=team_id, stagione=stagione,
                                    contratto_id=contratto["id"], note=f"Decadimento: {motivo_label}",
                                    tutte_le_squadre=tutte)
    nomi_altre = ", ".join((tm.get_team_by_id(t) or {}).get("nome", t) for t in altre)
    from handlers.registro import segna
    await segna(bot, user, "admin", "decadimento per conto della squadra" if per_conto else "decadimento approvato",
                squadre=[team_id] + list(altre), giocatore_id=gid, oggetto=giocatore["nome_common"],
                prima=f"{contratto['importo']}M × {db.anni_residui(contratto, stagione)}", dopo="decaduto",
                nota=motivo_label + (f"; tolte le spalmature di {nomi_altre}" if altre else ""))

    ora = format_dt(datetime.now(ROME))
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        testo_canale = (
            f"📋 <b>{team['nome']}</b> — Decadimento contratto\n\n"
            f"Il contratto di <b>{giocatore['nome_common']}</b> è decaduto.\n"
            f"Motivo: {motivo_label}\n"
            f"Lo slot roster è stato liberato."
            + (f"\nTolte anche le spalmature dei tagli passati: {nomi_altre}." if altre else "")
            + f"\n\n<i>Approvato da {admin_tag} — {ora}</i>"
        )
        try:
            await bot.send_message(chat_id=main_channel, text=testo_canale, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio canale decadimento: %s", e)
    try:
        import gas_client
        gas_client.sync_after_taglio(team_id)
        if altre:
            gas_client.sync_teams(altre)
    except Exception as e:
        logger.warning("GAS sync decadimento: %s", e)
    logger.info("Decadimento: team=%s giocatore=%d motivo=%s admin=%s", team_id, gid, motivo_key, admin_tag)
    return None


# ── Callback approvazione admin (dal gruppo admin) ─────────────────────────────

async def cb_dec_approva(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo gli admin possono approvare.", show_alert=True)
        return
    await query.answer()
    parts      = query.data.split(":")
    team_id    = parts[1]
    gid        = int(parts[2])
    motivo_key = parts[3] if len(parts) > 3 else "altro"
    admin_tag  = _admin_tag(query.from_user)
    esito_r = db.chiudi_richiesta("decadimento", gid, "approvata", admin_tag)
    if esito_r == "gestita":
        await query.edit_message_text(query.message.text_html + "\n\nℹ️ <b>Richiesta già gestita</b>", parse_mode="HTML")
        return
    try:
        errore = await applica_decadimento(context.bot, team_id, gid, motivo_key, admin_tag, user=query.from_user)
    except Exception:
        db.riapri_richiesta("decadimento", gid)
        raise
    if errore:
        await query.edit_message_text(query.message.text_html + f"\n\n{errore}", parse_mode="HTML")
        return
    await query.edit_message_text(query.message.text_html + f"\n\n✅ <b>Approvato</b> da {admin_tag}",
                                  parse_mode="HTML", reply_markup=None)
    nome = (db.get_giocatore(gid) or {}).get("nome_common", str(gid))
    await _ai_gm(context.bot, team_id, f"✅ Decadimento del contratto di <b>{nome}</b> approvato.")


async def cb_dec_rifiuta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo gli admin possono rifiutare.", show_alert=True)
        return
    await query.answer()
    _, team_id, gid = query.data.split(":")
    if db.chiudi_richiesta("decadimento", int(gid), "rifiutata", _admin_tag(query.from_user)) == "gestita":
        await query.edit_message_text(query.message.text_html + "\n\nℹ️ <b>Richiesta già gestita</b>", parse_mode="HTML")
        return
    await query.edit_message_text(query.message.text_html + f"\n\n❌ <b>Rifiutato</b> da {_admin_tag(query.from_user)}",
                                  parse_mode="HTML", reply_markup=None)
    nome = (db.get_giocatore(int(gid)) or {}).get("nome_common", gid)
    from handlers.registro import segna
    await segna(context.bot, query.from_user, "admin", "decadimento rifiutato", squadre=team_id, giocatore_id=int(gid),
                oggetto=nome, prima="chiesto", dopo="rifiutato")
    await _ai_gm(context.bot, team_id, f"❌ Richiesta di decadimento per <b>{nome}</b> rifiutata dagli admin.")


# ── Admin diretto: /admin_menu → 🏁 Decadimento ───────────────────────────────
# adm:dec → decadm:t:<team> → decadm:g:<team>:<gid> → decadm:m:<team>:<gid>:<motivo> → decadm:ok:...

async def admin_lista_team(query) -> None:
    tutti = tm.get_all_teams()
    bottoni = [InlineKeyboardButton(t["nome"], callback_data=f"decadm:t:{t['id']}") for t in tutti]
    righe = [bottoni[i:i + 2] for i in range(0, len(bottoni), 2)]
    righe.append([InlineKeyboardButton("✏️ Correggi la causa di un decadimento", callback_data="decor:l")])
    righe.append([InlineKeyboardButton("← Menu admin", callback_data="adm:home")])
    await query.edit_message_text("🏁 <b>Decadimento (admin)</b> — scegli la squadra:",
                                  parse_mode="HTML", reply_markup=InlineKeyboardMarkup(righe))


async def cb_dec_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    await query.answer()
    parti = query.data.split(":")
    azione, team_id = parti[1], parti[2]
    team = tm.get_team_by_id(team_id) or {"nome": team_id}

    if azione == "t":
        stagione = settings.stagione_corrente()
        roster = sorted(db.get_roster_team(team_id, senza_10day=True) or [], key=lambda x: -x["importo"])
        kb = [[InlineKeyboardButton(f"{r['nome_common']} {r['importo']}x{_anni_residui(r, stagione)}",
                                    callback_data=f"decadm:g:{team_id}:{r['giocatore_id']}")] for r in roster]
        kb.append([InlineKeyboardButton("← Squadre", callback_data="adm:dec")])
        await query.edit_message_text(f"🏁 <b>{team['nome']}</b> — il contratto di chi è decaduto?",
                                      parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    gid = int(parti[3])
    nome = (db.get_giocatore(gid) or {}).get("nome_common", str(gid))
    if azione == "g":
        kb = [[InlineKeyboardButton(label, callback_data=f"decadm:m:{team_id}:{gid}:{k}")] for k, label in MOTIVI.items()]
        kb.append([InlineKeyboardButton("← Indietro", callback_data=f"decadm:t:{team_id}")])
        await query.edit_message_text(f"🏁 <b>{nome}</b> ({team['nome']}) — motivo:",
                                      parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    motivo = parti[4]
    if azione == "m":
        await query.edit_message_text(
            f"🏁 Confermi il decadimento del contratto di <b>{nome}</b> ({team['nome']})?\n"
            f"Motivo: {MOTIVI.get(motivo, motivo)}\n"
            + (f"✂️ {riga_cam_thomas(gid)}\n" if motivo == "cam_thomas" else "") + "\n"
            f"<i>Contratto annullato senza impatto sui tagli gratuiti, slot roster liberato.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Conferma", callback_data=f"decadm:ok:{team_id}:{gid}:{motivo}"),
                InlineKeyboardButton("← Indietro", callback_data=f"decadm:g:{team_id}:{gid}"),
            ]]))
        return

    if azione == "ok":
        admin_tag = _admin_tag(query.from_user)
        db.chiudi_richiesta("decadimento", gid, "approvata", admin_tag)  # eventuale richiesta del GM
        errore = await applica_decadimento(context.bot, team_id, gid, motivo, admin_tag, user=query.from_user,
                                            per_conto=True)
        if errore:
            await query.edit_message_text(errore)
            return
        await query.edit_message_text(f"✅ Contratto di <b>{nome}</b> decaduto ({team['nome']}).", parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Menu admin", callback_data="adm:home")]]))
        await _ai_gm(context.bot, team_id, f"🛠 Un admin ha registrato il decadimento del contratto di <b>{nome}</b> "
                                          f"({MOTIVI.get(motivo, motivo)}).")


# ── Correggere la causa (v7.19.0, Luca 20/11: «ho sbagliato a inserire la causa») ──────────────────────────
# decor:l → decor:t:<transazione> → decor:m:<transazione>:<causa> → decor:ok:<transazione>:<causa>

def _riga_dec(d: dict) -> str:
    team = (tm.get_team_by_id(d["team_id_da"]) or {}).get("nome", d["team_id_da"])
    return f"{d['nome_common']} · {team} · {MOTIVI[causa_da_nota(d['note'])]} · {format_dt(d['timestamp'])[:5]}"


async def applica_correzione(bot, tid: int, nuova: str, admin_tag: str, user=None) -> str:
    """Cambia la causa del decadimento `tid`. Ritorna il testo dell'esito (errore con ❌)."""
    d = db.decadimento(tid)
    if not d:
        return "❌ Decadimento non trovato."
    vecchia = causa_da_nota(d["note"])
    perche = cambio_causa(vecchia, nuova)
    if perche:
        return f"❌ Non si può: {perche}."
    altre = db.correggi_causa_decadimento(tid, f"Decadimento: {MOTIVI[nuova]}",
                                          togli_altre=nuova in TOGLIE_ALTRE and vecchia not in TOGLIE_ALTRE)
    team = tm.get_team_by_id(d["team_id_da"]) or {"nome": d["team_id_da"]}
    nomi_altre = ", ".join((tm.get_team_by_id(t) or {}).get("nome", t) for t in altre)
    from handlers.registro import segna
    await segna(bot, user, "admin", "causa del decadimento corretta", squadre=[d["team_id_da"]] + list(altre),
                giocatore_id=d["giocatore_id"], oggetto=d["nome_common"], prima=MOTIVI[vecchia], dopo=MOTIVI[nuova],
                nota=(f"tolte le spalmature di {nomi_altre}" if altre else None))
    testo = (f"📋 <b>{team['nome']}</b> — Correzione\n\nIl motivo del decadimento di <b>{d['nome_common']}</b> "
             f"è {MOTIVI[nuova]} (non {MOTIVI[vecchia]})."
             + (f"\nTolte anche le spalmature dei tagli passati: {nomi_altre}." if altre else "")
             + (f"\nSe {team['nome']} lo rifirma entro un anno deve dargli almeno il contratto di prima." if nuova == "cam_thomas" else "")
             + f"\n\n<i>Corretto da {admin_tag} — {format_dt(datetime.now(ROME))}</i>")
    ch = settings.load_globals().get("main_channel_id")
    if ch:
        try:
            await bot.send_message(chat_id=ch, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio correzione decadimento: %s", e)
    if altre:
        try:
            import gas_client
            gas_client.sync_teams(altre)
        except Exception as e:
            logger.warning("GAS sync correzione decadimento: %s", e)
    return f"✅ Causa corretta: <b>{d['nome_common']}</b> ({team['nome']}) → {MOTIVI[nuova]}."


async def cb_dec_correggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    await query.answer()
    parti = query.data.split(":")
    azione = parti[1]
    if azione == "l":
        recenti = db.decadimenti_recenti()
        kb = [[InlineKeyboardButton(_riga_dec(d)[:60], callback_data=f"decor:t:{d['id']}")] for d in recenti]
        kb.append([InlineKeyboardButton("← Decadimento", callback_data="adm:dec")])
        await query.edit_message_text("✏️ <b>Correggi la causa di un decadimento</b> (ultimi 6 mesi) — quale?"
                                      if recenti else "Nessun decadimento negli ultimi 6 mesi.",
                                      parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return
    tid = int(parti[2])
    d = db.decadimento(tid)
    if not d:
        await query.edit_message_text("❌ Decadimento non trovato.")
        return
    vecchia = causa_da_nota(d["note"])
    if azione == "t":
        kb = [[InlineKeyboardButton(label, callback_data=f"decor:m:{tid}:{k}")]
              for k, label in MOTIVI.items() if not cambio_causa(vecchia, k)]
        kb.append([InlineKeyboardButton("← Indietro", callback_data="decor:l")])
        nota = ("\n\n<i>Da ritiro o altra lega si passa solo all'altra delle due: le spalmature tolte alle altre squadre "
                "non si rimettono da sole.</i>" if vecchia in TOGLIE_ALTRE else "")
        await query.edit_message_text(f"✏️ <b>{_riga_dec(d)}</b>\n\nCausa di adesso: {MOTIVI[vecchia]}. Quella giusta?" + nota,
                                      parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return
    nuova = parti[3]
    if nuova not in MOTIVI:
        return
    if azione == "m":
        effetti = []
        if nuova in TOGLIE_ALTRE and vecchia not in TOGLIE_ALTRE:
            effetti.append("si tolgono anche le spalmature delle altre squadre che l'avevano tagliato in passato")
        if nuova == "cam_thomas":
            effetti.append("se la squadra lo rifirma entro un anno deve dargli almeno il contratto di prima")
        if vecchia == "cam_thomas":
            effetti.append("non vale più il minimo della Cam Thomas per rifirmarlo")
        await query.edit_message_text(
            f"✏️ <b>{d['nome_common']}</b>: da {MOTIVI[vecchia]} a {MOTIVI[nuova]}?\n\n"
            + ("Effetti: " + "; ".join(effetti) + "." if effetti else "Cambia solo la causa scritta.")
            + "\nNel registro resta la riga della correzione, sul canale un messaggio.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Conferma", callback_data=f"decor:ok:{tid}:{nuova}"),
                InlineKeyboardButton("← Indietro", callback_data=f"decor:t:{tid}")]]))
        return
    if azione == "ok":
        esito = await applica_correzione(context.bot, tid, nuova, _admin_tag(query.from_user), user=query.from_user)
        await query.edit_message_text(esito, parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Menu admin", callback_data="adm:home")]]))


# ── Helper ─────────────────────────────────────────────────────────────────────

def _anni_residui(r: dict, stagione: str) -> int:
    return db.anni_residui(r, stagione)


# ── /ritiro_fa: free agent ritirato o andato in un'altra lega ──────────────────

async def cmd_ritiro_fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ritiro_fa <nome> (admin) — giocatore SENZA contratto che si ritira o va in un'altra
    lega: le spalmature dei tagli passati smettono di pesare sul cap di chi l'aveva tagliato.
    Per un giocatore sotto contratto si usa il decadimento normale."""
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    nome = " ".join(context.args or []).strip()
    if not nome:
        await update.effective_message.reply_text("Uso: /ritiro_fa <nome giocatore>")
        return
    import html as _html
    from utils import normalizza
    trovati = db.cerca_giocatori(normalizza(nome)) or []
    esatti = [g for g in trovati if g["nome_norm"] == normalizza(nome)]
    scelti = esatti or trovati
    if len(scelti) != 1:
        elenco = "\n".join(f"• {_html.escape(g['nome_common'])}" for g in scelti[:10]) or "nessuno"
        await update.effective_message.reply_text(
            f"Serve il nome esatto di un solo giocatore. Trovati:\n{elenco}", parse_mode="HTML")
        return
    g = scelti[0]
    c = db.get_contratto_attivo(g["id"])
    if c:
        await update.effective_message.reply_text(
            f"❌ {_html.escape(g['nome_common'])} è sotto contratto con {c['team_id']}: usa il decadimento "
            f"(/admin_menu → 🏁 Decadimento, motivo ritiro o altra lega).", parse_mode="HTML")
        return
    tolte = db.cancella_spalmate_ritirato(g["id"], settings.stagione_corrente())
    if not tolte:
        await update.effective_message.reply_text(
            f"ℹ️ {_html.escape(g['nome_common'])}: nessuna spalmatura da togliere.", parse_mode="HTML")
        return
    per_team = {}
    for r in tolte:
        per_team[r["team_id"]] = per_team.get(r["team_id"], 0) + r["importo"]
    righe = [f"• {(tm.get_team_by_id(t) or {}).get('nome', t)}: −{imp}M in totale" for t, imp in per_team.items()]
    testo = (f"🏁 <b>{_html.escape(g['nome_common'])}</b> si è ritirato / ha lasciato la NBA: "
             f"le spalmature dei tagli passati non pesano più sul cap.\n" + "\n".join(righe))
    await update.effective_message.reply_text(testo, parse_mode="HTML")
    from handlers.registro import segna
    await segna(context.bot, update.effective_user, "admin", "free agent ritirato", squadre=list(per_team),
                giocatore_id=g["id"], oggetto=g["nome_common"],
                prima="spalmature: " + ", ".join(f"{(tm.get_team_by_id(t) or {}).get('nome', t)} {imp}M" for t, imp in per_team.items()),
                dopo="tolte")
    ch = settings.load_globals().get("main_channel_id")
    if ch:
        try:
            await context.bot.send_message(chat_id=ch, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio ritiro_fa: %s", e)
    try:
        import gas_client
        gas_client.sync_teams(list(per_team))
    except Exception as e:
        logger.warning("GAS sync ritiro_fa: %s", e)


# ── Registrazione handler ──────────────────────────────────────────────────────

# ── Cam Thomas exception riconosciuta dal bot (v7.30.0, Luca 26/11) ──────────────────────────────────────
# Ogni mattina (dopo i roster ESPN delle 8:30) i giocatori a contratto senza squadra NBA che possono decadere con la
# Cam Thomas exception (shared/cam_thomas.py): un avviso per contratto nel gruppo admin, col bottone che apre la
# conferma del decadimento con quel motivo. Solo agli admin; la decisione resta loro, caso per caso.

def riga_cam_thomas(gid: int) -> str:
    from shared import cam_thomas as CT
    g = db.get_giocatore(gid) or {}
    if not g.get("espn_id"):
        return "senza id ESPN: da controllare a mano"
    try:
        return CT.testo(CT.valuta(g["espn_id"]))
    except Exception as e:
        logger.warning("Cam Thomas, %s: %s", gid, e)
        return "non riesco a controllare da quando è senza squadra"


def migra_cam_thomas() -> None:
    db._q("""CREATE TABLE IF NOT EXISTS cam_thomas_avvisi (
               contratto_id INT PRIMARY KEY,
               giocatore_id INT NOT NULL,
               team_id      TEXT NOT NULL,
               quando       TIMESTAMPTZ NOT NULL DEFAULT NOW())""")


def candidati_cam_thomas(oggi=None) -> list[dict]:
    """I contratti (non 10-day) di giocatori senza squadra NBA che possono decadere con la Cam Thomas exception."""
    from shared import cam_thomas as CT
    if not db._q("SELECT to_regclass('public.nba_atleti') IS NOT NULL AND to_regclass('public.nba_movimenti') IS NOT NULL AS c", one=True)["c"]:
        return []
    rr = db._q("""SELECT c.id AS contratto_id, c.giocatore_id, c.team_id, c.importo, g.nome_common, g.espn_id
                  FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                  JOIN nba_atleti a ON a.atleta = g.espn_id
                  WHERE c.attivo AND c.tipo <> '10day' AND a.squadra IS NULL""", many=True) or []
    out = []
    for r in rr:
        v = CT.valuta(r["espn_id"], oggi)
        if v and v["idoneo"]:
            out.append({**r, "valuta": v, "testo": CT.testo(v, oggi)})
    return out


def avviso_deadline_nba(oggi=None) -> str | None:
    """Se la regular season NBA è iniziata e la trade deadline NBA della stagione non c'è: la richiesta agli admin."""
    from datetime import date
    from shared import cam_thomas as CT
    oggi = oggi or date.today()
    s = CT.stagione_di(oggi)
    ini = CT.inizio_rs(s)
    if not ini or oggi < ini or CT.deadline(s):
        return None
    return (f"📅 Manca la <b>trade deadline NBA</b> della stagione {s}-{str(s + 1)[-2:]}: serve a contare i giorni della "
            "Cam Thomas exception. <code>/deadline_nba GG/MM/AAAA</code> (per esempio 01/02).")


async def cmd_deadline_nba(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deadline_nba [GG/MM/AAAA] (admin): la trade deadline NBA reale (globals.json `nba_trade_deadline`)."""
    from datetime import date
    from shared import cam_thomas as CT
    from shared.date_comandi import leggi_data
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    g = settings.load_globals()
    s = CT.stagione_di(date.today())
    if not context.args:
        d = CT.deadline(s)
        await update.effective_message.reply_text(
            f"📅 Trade deadline NBA {s}-{str(s + 1)[-2:]}: <b>{d.strftime('%d/%m/%Y') if d else 'non impostata'}</b>"
            + "\nServe a contare i giorni della Cam Thomas exception (il mercato NBA è aperto dal 1° luglio alla deadline).\nPer cambiarla: <code>/deadline_nba GG/MM/AAAA</code>",
            parse_mode="HTML")
        return
    d = leggi_data(context.args[0]) or leggi_data(f"{context.args[0]}/{s + 1}")
    if not d or not date(s, 7, 1) <= d <= date(s + 1, 6, 30):
        await update.effective_message.reply_text(f"❌ Data non valida o fuori dalla stagione {s}-{str(s + 1)[-2:]}. Es: /deadline_nba 01/02/{s + 1}")
        return
    vecchie = g.get("nba_trade_deadline")
    vecchie = dict(vecchie) if isinstance(vecchie, dict) else {}
    prima = vecchie.get(str(s))
    vecchie[str(s)] = d.isoformat()                           # una per stagione: servono anche quelle passate
    g["nba_trade_deadline"] = vecchie
    settings.save_globals(g)
    from handlers.registro import segna
    await segna(context.bot, update.effective_user, "admin", "trade deadline NBA", oggetto="trade deadline NBA",
                prima=str(prima or ""), dopo=d.isoformat())
    await update.effective_message.reply_text(f"✅ Trade deadline NBA: <b>{d.strftime('%d/%m/%Y')}</b>.", parse_mode="HTML")


async def job_cam_thomas(context) -> None:
    gruppo = settings.admin_group_id()
    if not gruppo:
        return
    try:
        migra_cam_thomas()
        from datetime import date
        avviso = avviso_deadline_nba()
        if avviso and date.today().weekday() == 0:            # il lunedì, finché manca
            await context.bot.send_message(chat_id=gruppo, text=avviso, parse_mode="HTML")
        for r in candidati_cam_thomas():
            if not db._q("INSERT INTO cam_thomas_avvisi (contratto_id, giocatore_id, team_id) VALUES (%s, %s, %s) "
                         "ON CONFLICT DO NOTHING RETURNING contratto_id", (r["contratto_id"], r["giocatore_id"], r["team_id"]), one=True):
                continue
            team = tm.get_team_by_id(r["team_id"]) or {"nome": r["team_id"]}
            await context.bot.send_message(
                chat_id=gruppo, parse_mode="HTML",
                text=(f"✂️ <b>Cam Thomas exception possibile</b>: <b>{html.escape(r['nome_common'])}</b> "
                      f"({html.escape(team['nome'])}, {r['importo']}M)\n{html.escape(r['testo'])}\n\n"
                      "<i>Da valutare caso per caso: tagliato in NBA e non passato a un altro campionato (in quel caso il "
                      "motivo è «altra lega»). Se la squadra lo riprende entro un anno, le costa almeno questo contratto.</i>"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🏁 Decadimento Cam Thomas", callback_data=f"decadm:m:{r['team_id']}:{r['giocatore_id']}:cam_thomas")]]))
    except Exception:
        logger.exception("Cam Thomas exception, avvisi")


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("decadimento", cmd_decadimento),
                      CallbackQueryHandler(cb_dec_start, pattern=r"^dec_start$")],
        states={
            DEC_GIOCATORE: [CallbackQueryHandler(cb_dec_giocatore, pattern=r"^dec_giocat:\d+$")],
            DEC_MOTIVO:    [CallbackQueryHandler(cb_dec_motivo,    pattern=r"^dec_motivo:\w+$")],
        },
        fallbacks=[
            CallbackQueryHandler(cb_dec_annulla, pattern=r"^dec_annulla$"),
            CommandHandler("annulla", cb_dec_annulla),
        ],
        conversation_timeout=300,
        per_message=False,
    )
    return [
        conv,
        CommandHandler("ritiro_fa", cmd_ritiro_fa),
        CommandHandler("deadline_nba", cmd_deadline_nba),
        CallbackQueryHandler(cb_dec_approva, pattern=r"^dec_approva:.+:\d+:\w+$"),
        CallbackQueryHandler(cb_dec_rifiuta, pattern=r"^dec_rifiuta:.+:\d+$"),
        CallbackQueryHandler(cb_dec_admin,   pattern=r"^decadm:(?:t:[\w-]+|g:[\w-]+:\d+|(?:m|ok):[\w-]+:\d+:\w+)$"),
        CallbackQueryHandler(cb_dec_correggi, pattern=r"^decor:(?:l|t:\d+|(?:m|ok):\d+:\w+)$"),
    ]

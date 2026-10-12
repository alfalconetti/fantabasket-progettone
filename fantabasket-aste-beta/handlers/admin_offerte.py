"""
Aste e offerte per conto di una squadra: /apri_asta, /crea_offerta, /nuova_rfa (RFA a mano;
le dichiarate le apre handlers/rfa.py), /annulla_offerta (con cap negativo chiede conferma:
annulla_off_cap:).
"""
import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import teams as tm
import utils
from handlers.helpers import aggiorna_canale as _aggiorna_canale, log_warn as _log_warn
from handlers.admin_comune import is_admin, _admin_label, _richiedi_conferma_cap_negativo

logger = logging.getLogger(__name__)


# ── /nuova_rfa ────────────────────────────────────────────────────────────────

async def nuova_rfa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    args = context.args
    if len(args) < 3:
        await update.effective_message.reply_text(
            "Uso: /nuova_rfa <giocatore> <team_id> <vecchio_compenso>\n"
            "Esempio: /nuova_rfa Luka Doncic lakers 25"
        )
        return

    try:
        vecchio_compenso = int(args[-1])
    except ValueError:
        await update.effective_message.reply_text("❌ Il vecchio compenso deve essere un numero intero.")
        return

    team_id   = args[-2]
    giocatore_input = " ".join(args[:-2])

    if not giocatore_input:
        await update.effective_message.reply_text("❌ Nome giocatore mancante.")
        return

    team = tm.get_team_by_id(team_id)
    if team is None:
        await update.effective_message.reply_text(f"❌ Team ID '<code>{team_id}</code>' non trovato. Usa /listteams.", parse_mode="HTML")
        return

    # max 1 RFA per team per stagione
    stagione = utils.get_stagione_corrente()
    if db.team_ha_rfa_stagione(team_id, stagione):
        await update.effective_message.reply_text(f"❌ {team['nome']} ha già utilizzato la RFA questa stagione.")
        return

    # Il giocatore deve essere sotto contratto con la squadra proprietaria: il nome
    # viene preso dal roster (prima testo libero: con un errore di battitura alla
    # firma veniva creato un giocatore nuovo e il vecchio contratto restava attivo)
    import pg_client
    giocatore = giocatore_input.strip()
    if pg_client.pg_disponibile():
        roster = pg_client.nomi_roster(team_id)
        esatto, suggerimento = utils.trova_giocatore_generico(giocatore, roster)
        if not esatto:
            if suggerimento:
                await update.effective_message.reply_text(
                    f"🔎 «{html.escape(giocatore)}» non è un nome esatto del roster di {team['nome']}. Intendevi:\n\n"
                    f"<code>/nuova_rfa {html.escape(suggerimento)} {team_id} {vecchio_compenso}</code>",
                    parse_mode="HTML")
            else:
                await update.effective_message.reply_text(
                    f"❌ «{html.escape(giocatore)}» non è sotto contratto con {team['nome']}.", parse_mode="HTML")
            return
        giocatore = esatto

    if db.giocatore_gia_in_asta(giocatore):
        await update.effective_message.reply_text(f"❌ Esiste già un'asta aperta per {giocatore}.")
        return

    from handlers.rfa import pubblica_asta_rfa
    asta_id, scade = await pubblica_asta_rfa(context.bot, team_id, giocatore, vecchio_compenso,
                                             pg_client.id_in_roster(team_id, giocatore),
                                             _admin_label(update.effective_user))

    await update.effective_message.reply_text(
        f"✅ Asta RFA aperta per <b>{giocatore}</b>\n"
        f"Proprietario: {team['nome']} | Vecchio compenso: {vecchio_compenso}M\n"
        f"Scade: {utils.format_dt(scade.isoformat())}",
        parse_mode="HTML",
    )
    logger.info("Nuova RFA: asta_id=%d giocatore=%s proprietario=%s compenso=%d admin=%d",
                asta_id, giocatore, team_id, vecchio_compenso, update.effective_user.id)


# ── /annulla_offerta ──────────────────────────────────────────────────────────

async def annulla_offerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return
    if not context.args:
        await update.effective_message.reply_text("Uso: /annulla_offerta <asta_id>")
        return
    try:
        asta_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso.")
        return
    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] != "APERTA":
        await update.effective_message.reply_text("❌ Asta non trovata o non aperta.")
        return

    # preview senza eseguire — controlla se il nuovo vincitore avrebbe cap negativo
    preview = db.preview_annulla_ultima_offerta(asta_id)
    if preview is None:
        await update.effective_message.reply_text("❌ Nessuna offerta da annullare.")
        return

    admin_label = _admin_label(update.effective_user)

    if preview["nuovo_team"]:
        team_data = tm.get_team_by_id(preview["nuovo_team"])
        if team_data:
            stagione_ao = utils.load_globals().get("stagione_corrente", "2025")
            cap_disp, _ = utils.cap_slot_display(team_data, stagione_ao)
            cap_virt = db.get_cap_virtuale(preview["nuovo_team"])
            cap_post = cap_virt + preview["nuovo_importo"]
            if cap_post > cap_disp:
                admin_group_id = utils.get_admin_group_id()
                if not admin_group_id:
                    await update.effective_message.reply_text(
                        "❌ Annullando questa offerta il cap virtuale di una squadra andrebbe in negativo, "
                        "ma <code>admin_group_id</code> non è configurato. Impossibile richiedere conferma.",
                        parse_mode="HTML",
                    )
                    return
                await _richiedi_conferma_cap_negativo(
                    context, dict(asta), 0, admin_group_id, admin_label,
                    cap_disp, cap_virt, cap_post, "annulla_off_cap"
                )
                await update.effective_message.reply_text(
                    f"⚠️ Richiesta di conferma inviata al gruppo admin.\n"
                    f"Annullando l'offerta su <b>{asta['giocatore']}</b> il cap virtuale "
                    f"di una squadra andrebbe in negativo.",
                    parse_mode="HTML",
                )
                return

    result = db.annulla_ultima_offerta(asta_id)
    if result is None:
        await update.effective_message.reply_text("❌ Nessuna offerta da annullare.")
        return

    admin_label = _admin_label(update.effective_user)
    teams_map = {t["id"]: t["nome"] for t in tm.get_all_teams()}
    team_el = teams_map.get(result["team_eliminato"], result["team_eliminato"])
    nuovo_team = teams_map.get(result["nuovo_team"], "nessuno") if result["nuovo_team"] else "nessuno"

    await _aggiorna_canale(context, asta_id)

    channel_id = utils.get_channel_id()
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=(
                f"⚠️ <b>Offerta annullata da {admin_label}</b>\n"
                f"🏀 {asta['giocatore']}\n"
                f"Offerta eliminata: {result['offerta_eliminata']}M — {team_el}\n"
                f"Offerta attuale: {result['nuovo_importo']}M — {nuovo_team}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await _log_warn(context, f"Annuncio annulla_offerta canale fallito: {e}")

    # check cap virtuale del team ripristinato
    warning_cap = ""
    if result["nuovo_team"]:
        import database as _db2
        import teams as _tm2
        cap_virt = _db2.get_cap_virtuale(result["nuovo_team"])
        team_data = _tm2.get_team_by_id(result["nuovo_team"])
        if team_data:
            stagione_ao2 = utils.load_globals().get("stagione_corrente", "2025")
            cap_disp_ao2, _ = utils.cap_slot_display(team_data, stagione_ao2)
            if (cap_disp_ao2 - cap_virt) < 0:
                warning_cap = (
                    f"\n\n⚠️ <b>Attenzione:</b> {teams_map.get(result['nuovo_team'], result['nuovo_team'])} "
                    f"ha cap virtuale negativo ({cap_disp_ao2}M disponibile, "
                    f"{cap_virt}M impegnato). Potrebbe essere necessario un intervento manuale."
                )

    # notifica GM a cui è stata annullata l'offerta
    team_el_obj = tm.get_team_by_id(result["team_eliminato"]) if result["team_eliminato"] else None
    if team_el_obj:
        for gm_id in team_el_obj["gm_ids"]:
            try:
                await context.bot.send_message(
                    chat_id=gm_id,
                    text=(
                        f"⚠️ La tua offerta di <b>{result['offerta_eliminata']}M</b> "
                        f"per <b>{asta['giocatore']}</b> è stata annullata da <b>{admin_label}</b>.\n"
                        f"Offerta attuale: <b>{result['nuovo_importo']}M — {nuovo_team}</b>"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                await _log_warn(context, f"Notifica annulla_offerta GM {gm_id}: {e}")

    # notifica watcher (escluso il GM già notificato)
    gm_ids_notificati = set(team_el_obj["gm_ids"]) if team_el_obj else set()
    watchers = db.get_watchers(asta_id)
    for gm_id in watchers:
        if gm_id not in gm_ids_notificati:
            try:
                await context.bot.send_message(
                    chat_id=gm_id,
                    text=(
                        f"⚠️ Offerta annullata da <b>{admin_label}</b> su <b>{asta['giocatore']}</b>\n"
                        f"Offerta eliminata: {result['offerta_eliminata']}M — {team_el}\n"
                        f"Offerta attuale: <b>{result['nuovo_importo']}M — {nuovo_team}</b>"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                await _log_warn(context, f"Notifica annulla_offerta watcher {gm_id}: {e}")

    await update.effective_message.reply_text(
        f"✅ Ultima offerta di <b>{team_el}</b> ({result['offerta_eliminata']}M) annullata.\n"
        f"Offerta attuale: <b>{result['nuovo_importo']}M — {nuovo_team}</b>{warning_cap}",
        parse_mode="HTML",
    )
    logger.info("annulla_offerta: asta_id=%d offerta=%d admin=%d", asta_id, result["offerta_eliminata"], update.effective_user.id)


# ── /annulla_offerta con cap negativo: conferma ─────────────────────────────────

async def annulla_off_cap_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback di conferma per annullamento offerta con cap virtuale negativo."""
    query = update.callback_query
    await query.answer()

    _, asta_id_s, _ = query.data.split(":")
    asta_id = int(asta_id_s)

    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] != "APERTA":
        await query.edit_message_text("❌ Asta non più aperta.")
        return

    result = db.annulla_ultima_offerta(asta_id)
    if result is None:
        await query.edit_message_text("❌ Nessuna offerta da annullare.")
        return

    admin_label = _admin_label(query.from_user)
    teams_map = {t["id"]: t["nome"] for t in tm.get_all_teams()}
    team_el   = teams_map.get(result["team_eliminato"], result["team_eliminato"])
    nuovo_team = teams_map.get(result["nuovo_team"], "nessuno") if result["nuovo_team"] else "nessuno"

    await _aggiorna_canale(context, asta_id)

    channel_id = utils.get_channel_id()
    try:
        await context.bot.send_message(
            chat_id=channel_id,
            text=(
                f"⚠️ <b>Offerta annullata da {admin_label}</b> (confermato dal gruppo admin)\n"
                f"🏀 {asta['giocatore']}\n"
                f"Offerta eliminata: {result['offerta_eliminata']}M — {team_el}\n"
                f"Offerta attuale: {result['nuovo_importo']}M — {nuovo_team}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await _log_warn(context, f"Annuncio annulla_offerta canale fallito: {e}")

    await query.edit_message_text(
        f"✅ Offerta annullata su <b>{asta['giocatore']}</b>.\n"
        f"⚠️ Il cap virtuale di <b>{nuovo_team}</b> potrebbe essere in negativo — verificare.",
        parse_mode="HTML",
    )
    logger.info("annulla_off_cap_callback: asta_id=%d admin=%d", asta_id, query.from_user.id)


# ── /crea_offerta ─────────────────────────────────────────────────────────────

async def crea_offerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Offerta one-shot per conto di un team specifico, senza ConversationHandler.
    Solo admin. Uso: /crea_offerta <team_id> <asta_id> <importo>
    Tutti i check vengono applicati. Nessun retry.
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    if len(context.args) != 3:
        await update.effective_message.reply_text(
            "Uso: /crea_offerta &lt;team_id&gt; &lt;asta_id&gt; &lt;importo&gt;\n"
            "Esempio: /crea_offerta team07 42 25",
            parse_mode="HTML",
        )
        return

    team_id = context.args[0]
    try:
        asta_id = int(context.args[1])
        importo = int(context.args[2])
    except ValueError:
        await update.effective_message.reply_text(
            "❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso."
        )
        return

    team = tm.get_team_by_id(team_id)
    if not team:
        await update.effective_message.reply_text(
            f"❌ Team '<code>{team_id}</code>' non trovato. Usa /listteams per la lista.",
            parse_mode="HTML",
        )
        return

    asta = db.get_asta(asta_id)
    if not asta or asta["stato"] != "APERTA":
        await update.effective_message.reply_text(
            "❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso."
        )
        return

    admin_label = _admin_label(update.effective_user)
    from handlers.offerte import _esegui_offerta
    gm_id = team["gm_ids"][0] if team["gm_ids"] else 0
    errore = await _esegui_offerta(context, team, asta_id, importo, gm_id)
    if errore:
        await update.effective_message.reply_text(f"❌ {errore}")
    else:
        asta_upd = db.get_asta(asta_id)
        await update.effective_message.reply_text(
            f"✅ Offerta di <b>{importo}M</b> per <b>{asta['giocatore']}</b> "
            f"registrata per <b>{team['nome']}</b>.\n"
            f"Scade: {utils.format_dt(asta_upd['scade_at'])}",
            parse_mode="HTML",
        )
        channel_id = utils.get_channel_id()
        try:
            await context.bot.send_message(
                chat_id=channel_id,
                text=(
                    f"🔧 Offerta registrata da <b>{admin_label}</b> per conto di <b>{team['nome']}</b>:\n"
                    f"<b>{importo}M</b> su <b>{asta['giocatore']}</b>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            await _log_warn(context, f"Annuncio crea_offerta canale fallito: {e}")
        await _log_warn(context,
            f"🏀 Offerta creata da admin <b>{admin_label}</b>: "
            f"{team['nome']} → {asta['giocatore']} {importo}M"
        )
    logger.info("crea_offerta: team=%s asta_id=%d importo=%d admin=%d",
                team_id, asta_id, importo, update.effective_user.id)


# ── /apri_asta (per conto di una squadra) ─────────────────────────────────────

async def apri_asta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Apre un'asta FA per conto di una squadra, con la sua offerta iniziale.
    Solo admin. Uso: /apri_asta <team_id> <importo> <nome giocatore>
    Stessa ricerca del nome e stessi controlli di /nuova_fa (mercato, cap, slot…).
    Il nome deve corrispondere a un solo giocatore della lista FA: se è ambiguo o
    approssimato il bot propone i nomi esatti da ricopiare (niente stato in memoria).
    """
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Non sei autorizzato.")
        return

    uso = ("Uso: /apri_asta &lt;team_id&gt; &lt;importo&gt; &lt;nome giocatore&gt;\n"
           "Esempio: /apri_asta team07 5 LeBron James")
    if len(context.args) < 3:
        await update.effective_message.reply_text(uso, parse_mode="HTML")
        return
    team_id = context.args[0]
    try:
        importo = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("❌ L'importo deve essere un numero intero.\n\n" + uso,
                                                  parse_mode="HTML")
        return
    testo_nome = " ".join(context.args[2:])

    team = tm.get_team_by_id(team_id)
    if not team:
        await update.effective_message.reply_text(
            f"❌ Team '<code>{html.escape(team_id)}</code>' non trovato. Usa /listteams per la lista.",
            parse_mode="HTML",
        )
        return

    nome_esatto, suggerimento, omonimi = utils.trova_giocatore_fa(testo_nome)
    if not nome_esatto:
        if suggerimento and suggerimento.startswith("__cognome__"):
            candidati = omonimi
        elif omonimi:
            candidati = omonimi
        elif suggerimento:
            candidati = [suggerimento]
        else:
            candidati = []
        if not candidati:
            await update.effective_message.reply_text(
                f"❌ <b>{html.escape(testo_nome)}</b> non trovato nella lista FA.", parse_mode="HTML")
            return
        righe = [f"<code>/apri_asta {html.escape(team_id)} {importo} {html.escape(n)}</code>" for n in candidati]
        await update.effective_message.reply_text(
            f"🔎 «{html.escape(testo_nome)}» non è un nome esatto. Intendevi:\n\n" + "\n".join(righe) +
            "\n\n<i>Tocca il comando giusto per copiarlo e rimandalo.</i>",
            parse_mode="HTML",
        )
        return

    from handlers.offerte import apri_asta_fa
    asta_id, errore = await apri_asta_fa(context, team, nome_esatto, importo, list(team.get("gm_ids", [])))
    if errore:
        await update.effective_message.reply_text(f"❌ {errore}", parse_mode="HTML")
        return

    admin_label = _admin_label(update.effective_user)
    asta = db.get_asta(asta_id)
    await update.effective_message.reply_text(
        f"✅ Asta FA <b>#{asta_id}</b> aperta per <b>{nome_esatto}</b> per conto di <b>{team['nome']}</b> "
        f"con offerta iniziale <b>{importo}M</b>.\nScade: {utils.format_dt(asta['scade_at'])}",
        parse_mode="HTML",
    )
    try:
        await context.bot.send_message(
            chat_id=utils.get_channel_id(),
            text=(f"🔧 Asta aperta da <b>{html.escape(admin_label)}</b> per conto di <b>{team['nome']}</b>:\n"
                  f"<b>{nome_esatto}</b>, offerta iniziale <b>{importo}M</b>"),
            parse_mode="HTML",
        )
    except Exception as e:
        await _log_warn(context, f"Annuncio apri_asta canale fallito: {e}")
    for gm_id in team.get("gm_ids", []):
        try:
            await context.bot.send_message(
                chat_id=gm_id,
                text=(f"🔧 Un admin ha aperto per la tua squadra l'asta FA per <b>{nome_esatto}</b> "
                      f"con offerta iniziale <b>{importo}M</b>.\n"
                      f"Scade: {utils.format_dt(asta['scade_at'])}. Ricevi gli aggiornamenti (/silenzia {asta_id} per smettere)."),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Avviso apri_asta al GM %s fallito: %s", gm_id, e)
    await _log_warn(context,
        f"🏀 Asta aperta da admin <b>{html.escape(admin_label)}</b>: "
        f"{team['nome']} → {nome_esatto} {importo}M (asta #{asta_id})"
    )
    logger.info("apri_asta: team=%s giocatore=%s importo=%d asta_id=%d admin=%d",
                team_id, nome_esatto, importo, asta_id, update.effective_user.id)

"""
Attivazione diritti 2nd pick:
  GM:    /attiva_diritti (o 🏀 Rookie nel /menu) → diritto → conferma contratto scale → firma
  Admin: /admin_menu → 🏀 Attiva diritti → squadra → diritto → conferma (per conto del GM,
         in qualsiasi fase; il GM riceve un messaggio)
Entrambi passano da esegui_attivazione() (controlli + scrittura in un'unica transazione DB)
e da _dopo_attivazione() (canale, ruolo da dichiarare in RS, sync fogli).

Il contratto (importo e anni) è predefinito dalla rookie scale in settings.json.
Non viene chiesto importo libero — solo conferma o annulla.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters,
)
from datetime import datetime, timezone

import database as db
import settings
from settings import solo_privato, richiede_fase, FASI_TRADE_APERTE
import teams as tm

logger = logging.getLogger(__name__)

SCEGLI_ROOKIE, INSERISCI_IMPORTO_R, SCEGLI_ANNI_R, CONFERMA_R = range(4)
_ANNULLA_HINT = "\n<i>Per annullare: /annulla</i>"


def _slot_scala(pick_numero: int) -> dict | None:
    """Contratto dalla rookie scale per l'attivazione dei diritti: sempre colonna I anno."""
    for fascia, valori in settings.get().get("rookie_scale", {}).items():
        limiti = fascia.split("-")
        if int(limiti[0]) <= pick_numero <= int(limiti[-1]):
            return valori[0] if valori else None
    return None


class AttivazioneNonEseguibile(Exception):
    """Controllo fallito: il messaggio va mostrato così com'è."""


def _label_diritto(r: dict) -> str:
    slot = _slot_scala(r["pick_numero"])
    contratto = f" — {slot['imp']}x{slot['anni']}" if slot else ""
    return f"{r['nome_common']} (#{r['pick_numero']} {r['anno_draft']}){contratto}"


def esegui_attivazione(rookie_id: int, team_id: str, importo: int, anni: int) -> dict:
    """Controlli e scrittura dell'attivazione in un'unica transazione: contratto rookie,
    rookie firmato, transazione 'rookie_firma'. Restituisce la riga rookie (+ nome).
    Solleva AttivazioneNonEseguibile se i diritti non sono più attivabili o il cap non basta."""
    import psycopg2.extras
    stagione = settings.stagione_corrente()
    team = tm.get_team_by_id(team_id)
    cap_lib = settings.cap_limite_team(team) - db.cap_occupato_team(team_id, stagione)
    if cap_lib < importo:
        raise AttivazioneNonEseguibile(
            f"❌ Cap insufficiente: liberi {cap_lib}M, contratto da scala {importo}M.")
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT r.*, g.nome_common FROM rookie r JOIN giocatori g ON g.id = r.giocatore_id "
                        "WHERE r.id = %s FOR UPDATE OF r", (rookie_id,))
            r = cur.fetchone()
            if (not r or r["team_id"] != team_id or r["round"] != 2
                    or r["firmato"] or r["diritti_scaduti"]):
                raise AttivazioneNonEseguibile("❌ Diritti non più disponibili per questa squadra "
                                               "(già attivati, scaduti o ceduti).")
            cur.execute("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) "
                        "VALUES (%s, %s, %s, %s, %s, 'rookie') RETURNING id",
                        (r["giocatore_id"], team_id, importo, anni, stagione))
            contratto_id = cur.fetchone()["id"]
            cur.execute("UPDATE rookie SET firmato = TRUE, anno_firma = %s WHERE id = %s", (stagione, rookie_id))
            cur.execute("INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, "
                        "contratto_id, rookie_scale, note) VALUES ('rookie_firma', %s, NULL, %s, %s, %s, TRUE, %s)",
                        (r["giocatore_id"], team_id, stagione, contratto_id,
                         f"Attivazione diritti 2nd — pick #{r['pick_numero']} {r['anno_draft']}"))
    return dict(r)


async def _dopo_attivazione(bot, team_id: str, r: dict, importo: int, anni: int,
                            admin_nome: str | None = None) -> None:
    """Annuncio sul canale, avviso al GM se ha fatto un admin, ruolo da dichiarare (RS), sync fogli."""
    team = tm.get_team_by_id(team_id) or {"nome": team_id}
    anni_str = "anno" if anni == 1 else "anni"
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        testo = (f"🏀 <b>{team.get('gm_nome', team['nome'])}</b> attiva i diritti di "
                 f"<b>{r['nome_common']}</b>\n"
                 f"📋 {importo}M × {anni} {anni_str} (#{r['pick_numero']} {r['anno_draft']})")
        if admin_nome:
            testo += f"\n<i>Registrata da un admin ({admin_nome})</i>"
        try:
            await bot.send_message(chat_id=main_channel, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio canale attiva_diritti fallito: %s", e)
    if admin_nome:
        for gm in team.get("gm_ids", []):
            try:
                await bot.send_message(chat_id=int(gm), parse_mode="HTML",
                                       text=f"🛠 Un admin ha attivato per te i diritti di <b>{r['nome_common']}</b>: "
                                            f"{importo}M × {anni} {anni_str}.")
            except Exception as e:
                logger.warning("Avviso al GM attiva_diritti fallito: %s", e)
    logger.info("Rookie firma: team=%s giocatore=%d importo=%d admin=%s",
                team_id, r["giocatore_id"], importo, admin_nome)
    try:
        from handlers.ruoli_rs import apri_pendenti
        await apri_pendenti(bot, team_id, [r["giocatore_id"]], "rookie",
                            f"#{r['pick_numero']} {r['anno_draft']}")
    except Exception as e:
        logger.warning("Dichiarazione ruolo dopo attiva_diritti: %s", e)
    try:
        import gas_client
        gas_client.sync_after_rookie(team_id)
    except Exception as e:
        logger.warning("GAS sync rookie fallito: %s", e)


@solo_privato
@richiede_fase(*FASI_TRADE_APERTE, msg="❌ L'attivazione dei diritti rookie non è disponibile in questa fase.")
async def cmd_attiva_diritti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return ConversationHandler.END

    diritti = db.get_diritti_2nd_team(team["id"])
    if not diritti:
        await update.effective_message.reply_text("Non hai diritti di 2nd pick da attivare.")
        return ConversationHandler.END

    bottoni = [
        [InlineKeyboardButton(_label_diritto(r), callback_data=f"att_r:{r['id']}")]
        for r in diritti
    ]
    await update.effective_message.reply_text(
        "Seleziona il rookie da firmare:" + _ANNULLA_HINT,
        reply_markup=InlineKeyboardMarkup(bottoni),
    )
    return SCEGLI_ROOKIE


async def cb_scegli_rookie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Seleziona rookie → mostra direttamente il contratto da scala e chiede conferma."""
    query = update.callback_query
    await query.answer()
    rookie_id = int(query.data.split(":")[1])
    rookie    = db.get_rookie(rookie_id)
    if not rookie:
        await query.edit_message_text("❌ Rookie non trovato.")
        return ConversationHandler.END
    team = tm.get_team_by_gm(query.from_user.id)
    if (not team or rookie["team_id"] != team["id"] or rookie.get("firmato")
            or rookie.get("diritti_scaduti")):
        await query.edit_message_text("❌ Diritti non disponibili per la tua squadra.")
        return ConversationHandler.END

    context.user_data["att_rookie_id"] = rookie_id
    giocatore = db.get_giocatore(rookie["giocatore_id"])

    # Contratto predefinito dalla rookie scale (anno I)
    pic  = rookie["pick_numero"]
    slot = _slot_scala(pic)

    if not slot:
        # Fascia non trovata: fallback a input manuale (non dovrebbe succedere)
        await query.edit_message_text(
            f"🏀 <b>{giocatore['nome_common']}</b>\n"
            f"Pick #{pic} — Draft {rookie['anno_draft']}\n\n"
            f"⚠️ Contratto non trovato nella scala. Inserisci l'importo manualmente (minimo 1M):"
            + _ANNULLA_HINT,
            parse_mode="HTML",
        )
        return INSERISCI_IMPORTO_R

    importo = slot["imp"]
    anni    = slot["anni"]
    context.user_data["att_importo"]   = importo
    context.user_data["att_anni"]      = anni
    context.user_data["att_imp_base"]  = importo
    context.user_data["att_anni_base"] = anni

    anni_str = "anno" if anni == 1 else "anni"
    await query.edit_message_text(
        f"🏀 <b>{giocatore['nome_common']}</b>\n"
        f"Pick #{pic} — Draft {rookie['anno_draft']}\n\n"
        f"📋 Contratto dalla rookie scale:\n"
        f"<b>{importo}M × {anni} {anni_str}</b>\n\n"
        f"Confermi la firma?" + _ANNULLA_HINT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Conferma", callback_data="att_r_ok"),
            InlineKeyboardButton("❌ Annulla",  callback_data="att_r_no"),
        ]]),
    )
    return CONFERMA_R


async def inserisci_importo_r(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fallback: input manuale importo (solo se slot non trovato nella scala)."""
    testo = update.effective_message.text.strip()
    if not testo.isdigit():
        await update.effective_message.reply_text(
            "❌ Inserisci un numero intero." + _ANNULLA_HINT, parse_mode="HTML"
        )
        return INSERISCI_IMPORTO_R

    importo = int(testo)
    if importo < 1:
        await update.effective_message.reply_text("❌ Minimo 1M." + _ANNULLA_HINT, parse_mode="HTML")
        return INSERISCI_IMPORTO_R

    context.user_data["att_importo"] = importo
    anni = 1  # diritti 2nd sempre x1 se fuori scala
    context.user_data["att_anni"] = anni

    rookie    = db.get_rookie(context.user_data["att_rookie_id"])
    giocatore = db.get_giocatore(rookie["giocatore_id"])

    await update.effective_message.reply_text(
        f"🏀 Confermi firma?\n\n"
        f"Giocatore: <b>{giocatore['nome_common']}</b>\n"
        f"Contratto: <b>{importo}M × {anni} anno</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Conferma", callback_data="att_r_ok"),
            InlineKeyboardButton("❌ Annulla",  callback_data="att_r_no"),
        ]]),
    )
    return CONFERMA_R


async def cb_conferma_firma_rookie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user  = update.effective_user
    team  = tm.get_team_by_gm(user.id)

    rookie_id = context.user_data.pop("att_rookie_id", None)
    importo   = context.user_data.pop("att_importo", None)
    anni      = context.user_data.pop("att_anni", 1)
    context.user_data.pop("att_imp_base", None)
    context.user_data.pop("att_anni_base", None)

    if rookie_id is None or importo is None or not team:
        await query.edit_message_text("❌ Sessione scaduta. Riprova con /attiva_diritti.")
        return ConversationHandler.END

    try:
        r = esegui_attivazione(rookie_id, team["id"], importo, anni)
    except AttivazioneNonEseguibile as e:
        await query.edit_message_text(f"{e}\nContatta un admin se ritieni ci sia un errore.")
        return ConversationHandler.END

    anni_str = "anno" if anni == 1 else "anni"
    nota_ruolo = ("\n\n🎽 Ti arriva subito la richiesta del ruolo (48h)."
                  if settings.fase() in settings.FASI_RUOLI_RS else "")
    await query.edit_message_text(
        f"✅ <b>{r['nome_common']}</b> firmato!\n"
        f"Contratto: <b>{importo}M × {anni} {anni_str}</b> (rookie scale){nota_ruolo}",
        parse_mode="HTML",
    )
    await _dopo_attivazione(context.bot, team["id"], r, importo, anni)
    return ConversationHandler.END


async def cb_annulla_firma_rookie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    for k in ("att_rookie_id", "att_importo", "att_anni", "att_imp_base", "att_anni_base"):
        context.user_data.pop(k, None)
    await query.edit_message_text("Firma annullata.")
    return ConversationHandler.END


async def cmd_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Operazione annullata.")
    return ConversationHandler.END


# ── Admin: attivazione per conto di una squadra ─────────────────────────────
# /admin_menu → 🏀 Attiva diritti (adm:rookie) → attadm:t:<team> → attadm:r:<id> → attadm:ok:<id>
# Nessun vincolo di fase: l'admin può intervenire sempre (avviso se per i GM è chiusa).

def _is_admin(uid: int) -> bool:
    return uid in [int(a) for a in settings.admin_ids()]


async def admin_lista_team(query) -> None:
    """Squadre con diritti 2nd attivabili (chiamata da admin_panel, azione 'rookie')."""
    righe = []
    for t in tm.get_all_teams():
        n = len(db.get_diritti_2nd_team(t["id"]))
        if n:
            righe.append([InlineKeyboardButton(f"{t['nome']} ({n})", callback_data=f"attadm:t:{t['id']}")])
    righe.append([InlineKeyboardButton("← Menu admin", callback_data="adm:home")])
    testo = "🏀 <b>Attiva diritti (admin)</b> — scegli la squadra:" if len(righe) > 1 \
        else "🏀 Nessuna squadra ha diritti 2nd da attivare."
    if settings.fase() not in FASI_TRADE_APERTE:
        testo += "\n<i>⚠️ In questa fase i GM non possono attivarli: stai intervenendo come admin.</i>"
    await query.edit_message_text(testo, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(righe))


async def cb_admin_attiva(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Solo admin.", show_alert=True)
        return
    await query.answer()
    _, azione, arg = query.data.split(":")

    if azione == "t":
        team = tm.get_team_by_id(arg) or {"nome": arg}
        diritti = db.get_diritti_2nd_team(arg)
        kb = [[InlineKeyboardButton(_label_diritto(r), callback_data=f"attadm:r:{r['id']}")] for r in diritti]
        kb.append([InlineKeyboardButton("← Squadre", callback_data="adm:rookie")])
        await query.edit_message_text(
            f"🏀 <b>{team['nome']}</b> — diritti 2nd da attivare:" if diritti else f"{team['nome']}: nessun diritto da attivare.",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    r = db.get_rookie(int(arg))
    if not r:
        await query.edit_message_text("❌ Diritto non trovato.")
        return
    giocatore = db.get_giocatore(r["giocatore_id"]) or {"nome_common": str(r["giocatore_id"])}
    team = tm.get_team_by_id(r["team_id"]) or {"nome": r["team_id"]}
    slot = _slot_scala(r["pick_numero"])
    indietro = InlineKeyboardButton("← Indietro", callback_data=f"attadm:t:{r['team_id']}")
    if not slot:
        await query.edit_message_text(
            f"⚠️ Nessun contratto in rookie_scale per la pick #{r['pick_numero']}: "
            f"correggi settings.json (o usa /registra_firma).",
            reply_markup=InlineKeyboardMarkup([[indietro]]))
        return
    importo, anni = slot["imp"], slot["anni"]
    anni_str = "anno" if anni == 1 else "anni"

    if azione == "r":
        stagione = settings.stagione_corrente()
        cap_lib = settings.cap_limite_team(team) - db.cap_occupato_team(r["team_id"], stagione)
        await query.edit_message_text(
            f"🏀 <b>{giocatore['nome_common']}</b> — {team['nome']}\n"
            f"Pick #{r['pick_numero']} — Draft {r['anno_draft']}\n\n"
            f"📋 Contratto dalla rookie scale: <b>{importo}M × {anni} {anni_str}</b>\n"
            f"Cap libero della squadra: {cap_lib}M\n\nConfermi l'attivazione per conto del GM?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Attiva", callback_data=f"attadm:ok:{r['id']}"), indietro]]))
        return

    if azione == "ok":
        admin_nome = query.from_user.first_name or str(query.from_user.id)
        try:
            riga = esegui_attivazione(r["id"], r["team_id"], importo, anni)
        except AttivazioneNonEseguibile as e:
            await query.edit_message_text(str(e), reply_markup=InlineKeyboardMarkup([[indietro]]))
            return
        await query.edit_message_text(
            f"✅ <b>{riga['nome_common']}</b> firmato per {team['nome']}: {importo}M × {anni} {anni_str}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Squadre", callback_data="adm:rookie")]]))
        await _dopo_attivazione(context.bot, r["team_id"], riga, importo, anni, admin_nome=admin_nome)


# ── Scadenza diritti 2nd (bottone dal job check_scadenza_diritti) ─────────────

async def cb_scadi_diritti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conferma admin: marca come scaduti i diritti 2nd al secondo anno,
    poi annuncia nel gruppo admin e sul canale principale."""
    query = update.callback_query
    user  = query.from_user
    if user.id not in [int(a) for a in settings.admin_ids()]:
        await query.answer("⛔ Solo gli admin possono confermare.", show_alert=True)
        return

    anno = int(query.data.split(":")[1])
    info = db.info_scadenza_diritti()
    if not info or anno != info["anno_draft"]:
        await query.answer("❌ Anno non valido per la scadenza di questa stagione.", show_alert=True)
        return
    if info["giorni_mancanti"] > 0:
        await query.answer(
            f"⏳ I diritti {anno} scadono il {info['scadenza'].strftime('%d/%m/%Y')}: "
            f"non ancora confermabile.", show_alert=True)
        return

    await query.answer()
    scaduti = db.scadi_diritti_anno(anno)
    admin_nome = user.first_name or user.username or str(user.id)

    if not scaduti:
        await query.edit_message_text(
            f"ℹ️ Nessun diritto 2nd {anno} da far scadere (già confermato?)."
        )
        return

    # Elenco per squadra
    per_team: dict[str, list[str]] = {}
    for r in scaduti:
        per_team.setdefault(r["team_id"], []).append(r["nome_common"])
    righe = []
    for team_id, nomi in sorted(per_team.items()):
        t = tm.get_team_by_id(team_id)
        righe.append(f"• <b>{t['nome'] if t else team_id}</b>: {', '.join(sorted(nomi))}")
    elenco = "\n".join(righe)

    await query.edit_message_text(
        f"✅ <b>Diritti 2nd {anno} scaduti</b> — confermato da {admin_nome}.\n"
        f"{len(scaduti)} giocatori tornano free agent:\n\n{elenco}",
        parse_mode="HTML",
    )

    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        try:
            await context.bot.send_message(
                chat_id=main_channel,
                text=(f"⌛ <b>Scadenza diritti 2nd round {anno}</b>\n\n"
                      f"I seguenti giocatori non firmati diventano free agent:\n\n{elenco}"),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Annuncio canale scadenza diritti fallito: %s", e)

    logger.info("Diritti 2nd %d scaduti (%d) da %s", anno, len(scaduti), admin_nome)

    try:
        import gas_client
        gas_client.sync_scelte()
    except Exception as e:
        logger.warning("GAS sync scelte dopo scadenza diritti fallito: %s", e)


def get_handlers() -> list:
    conv = ConversationHandler(
        # Anche la scelta del rookie è un ingresso: la lista può arrivare dal /menu,
        # che la mostra senza avviare la conversazione
        entry_points=[CommandHandler("attiva_diritti", cmd_attiva_diritti),
                      CallbackQueryHandler(cb_scegli_rookie, pattern=r"^att_r:\d+$")],
        states={
            SCEGLI_ROOKIE: [
                CallbackQueryHandler(cb_scegli_rookie, pattern=r"^att_r:\d+$"),
            ],
            INSERISCI_IMPORTO_R: [
                # Fallback manuale (solo se slot non trovato nella scala)
                MessageHandler(filters.TEXT & ~filters.COMMAND, inserisci_importo_r),
            ],
            CONFERMA_R: [
                CallbackQueryHandler(cb_conferma_firma_rookie, pattern=r"^att_r_ok$"),
                CallbackQueryHandler(cb_annulla_firma_rookie,  pattern=r"^att_r_no$"),
            ],
        },
        fallbacks=[CommandHandler("annulla", cmd_annulla)],
        per_user=True,
        per_chat=True,
        per_message=False,
        conversation_timeout=300,
    )
    return [conv, CallbackQueryHandler(cb_scadi_diritti, pattern=r"^scadi_diritti:\d+$"),
            CallbackQueryHandler(cb_admin_attiva, pattern=r"^attadm:(?:t:[\w-]+|r:\d+|ok:\d+)$")]

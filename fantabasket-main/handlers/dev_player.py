"""
/dev_player <nome> — mostra anagrafica completa di un giocatore con bottoni per modificare
ogni campo. Solo dev.

Campi anagrafici (no warning): nome_common, nome_bref, nome_yahoo, nome_norm, data_nascita
Campi contrattuali (warning + log): team_id, importo, anni_originali, stagione_firma, tipo
"""
import logging
import unicodedata

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

import database as db
import settings

logger = logging.getLogger(__name__)

DP_SCEGLI_CAMPO, DP_INSERISCI = range(30, 32)
_HINT = "\n<i>/annulla_dev per uscire</i>"

_CAMPI_ANAGRAFICI   = ["nome_common", "nome_bref", "nome_yahoo", "nome_norm", "data_nascita"]
_CAMPI_CONTRATTUALI = ["team_id", "importo", "anni_originali", "stagione_firma", "tipo"]
_CAMPI_ROOKIE       = ["pick_numero", "anno_draft", "anni_scala"]


def _is_dev(user_id: int) -> bool:
    return user_id == settings.dev_id()


def _testo_giocatore(gid: int) -> str:
    g = db.get_giocatore(gid)
    if not g:
        return "Giocatore non trovato."
    c = db.get_contratto_attivo(gid)
    r = db.get_rookie_by_giocatore(gid)

    righe = [
        f"🏀 <b>{g['nome_common']}</b> <code>#{gid}</code>",
        "",
        "<b>Anagrafica</b>",
        f"  nome_common:  <code>{g['nome_common']}</code>",
        f"  nome_bref:    <code>{g['nome_bref']}</code>",
        f"  nome_yahoo:   <code>{g.get('nome_yahoo') or '—'}</code>",
        f"  nome_norm:    <code>{g['nome_norm']}</code>",
        f"  data_nascita: <code>{g.get('data_nascita') or '—'}</code>",
    ]

    if c:
        from settings import stagione_corrente
        anni_res = c["anni_originali"] - (int(stagione_corrente()) - int(c["stagione_firma"]))
        righe += [
            "",
            "<b>Contratto</b>",
            f"  team_id:       <code>{c['team_id']}</code>",
            f"  importo:       <code>{c['importo']}M</code>",
            f"  anni_originali:<code>{c['anni_originali']}</code> (residui: {max(0,anni_res)})",
            f"  stagione_firma:<code>{c['stagione_firma']}</code>",
            f"  tipo:          <code>{c['tipo']}</code>",
        ]
    else:
        righe += ["", "<i>Nessun contratto attivo — FA</i>"]

    if r:
        righe += [
            "",
            "<b>Rookie</b>",
            f"  pick_numero: <code>{r['pick_numero']}</code>",
            f"  anno_draft:  <code>{r['anno_draft']}</code>",
            f"  anni_scala:  <code>{r['anni_scala']}</code>",
            f"  firmato:     <code>{r['firmato']}</code>",
        ]

    return "\n".join(righe)


def _kb_giocatore(gid: int) -> InlineKeyboardMarkup:
    righe = []
    for campo in _CAMPI_ANAGRAFICI:
        righe.append([InlineKeyboardButton(
            f"✏️ {campo}", callback_data=f"dp:a:{gid}:{campo}"
        )])
    righe.append([InlineKeyboardButton("── contratto ──", callback_data="dp:noop")])
    for campo in _CAMPI_CONTRATTUALI:
        righe.append([InlineKeyboardButton(
            f"⚠️ {campo}", callback_data=f"dp:c:{gid}:{campo}"
        )])
    righe.append([InlineKeyboardButton("── rookie ──", callback_data="dp:noop")])
    for campo in _CAMPI_ROOKIE:
        righe.append([InlineKeyboardButton(
            f"⚠️ {campo}", callback_data=f"dp:r:{gid}:{campo}"
        )])
    return InlineKeyboardMarkup(righe)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


# ── /dev_player ───────────────────────────────────────────────────────────────

async def cmd_dev_player(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_dev(update.effective_user.id):
        return ConversationHandler.END

    if not context.args:
        await update.effective_message.reply_text(
            "Uso: /dev_player <nome>\nEsempio: /dev_player Jokic"
        )
        return ConversationHandler.END

    nome = " ".join(context.args)
    results = db.cerca_giocatori(_norm(nome))

    if not results:
        await update.effective_message.reply_text(f"❌ Nessun giocatore trovato per '{nome}'.")
        return ConversationHandler.END

    if len(results) == 1:
        gid = results[0]["id"]
        await update.effective_message.reply_text(
            _testo_giocatore(gid), parse_mode="HTML",
            reply_markup=_kb_giocatore(gid)
        )
        return DP_SCEGLI_CAMPO

    # Più risultati → mostra lista
    bottoni = [
        [InlineKeyboardButton(
            f"{r['nome_common']} ({r['nome_bref']})",
            callback_data=f"dp:sel:{r['id']}"
        )]
        for r in results[:10]
    ]
    await update.effective_message.reply_text(
        f"Trovati {len(results)} giocatori. Seleziona:" + _HINT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(bottoni),
    )
    return DP_SCEGLI_CAMPO


async def cb_dp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    if query.data == "dp:noop":
        await query.answer()
        return DP_SCEGLI_CAMPO

    await query.answer()
    parts = query.data.split(":")

    # Selezione da lista multipla
    if parts[1] == "sel":
        gid = int(parts[2])
        await query.edit_message_text(
            _testo_giocatore(gid), parse_mode="HTML",
            reply_markup=_kb_giocatore(gid)
        )
        return DP_SCEGLI_CAMPO

    # Selezione campo
    categoria = parts[1]  # a=anagrafico, c=contrattuale, r=rookie
    gid       = int(parts[2])
    campo     = parts[3]

    context.user_data["dp_gid"]       = gid
    context.user_data["dp_campo"]     = campo
    context.user_data["dp_categoria"] = categoria

    warning = ""
    if categoria in ("c", "r"):
        warning = (
            "\n\n⚠️ <b>Attenzione:</b> stai modificando un campo operativo. "
            "L'operazione verrà loggata sul canale."
        )

    await query.edit_message_text(
        f"Inserisci il nuovo valore per <b>{campo}</b>:{warning}" + _HINT,
        parse_mode="HTML",
    )
    return DP_INSERISCI


async def dp_ricevi_valore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_dev(update.effective_user.id):
        return ConversationHandler.END

    valore    = update.effective_message.text.strip()
    gid       = context.user_data.pop("dp_gid", None)
    campo     = context.user_data.pop("dp_campo", None)
    categoria = context.user_data.pop("dp_categoria", "a")

    if not gid or not campo:
        await update.effective_message.reply_text("❌ Sessione scaduta.")
        return ConversationHandler.END

    from database import _q
    try:
        if categoria == "a":
            # Campo anagrafico: aggiorna direttamente in giocatori
            if campo == "nome_norm":
                valore = _norm(valore)
            _q(f"UPDATE giocatori SET {campo} = %s WHERE id = %s", (valore or None, gid))
            await update.effective_message.reply_text(
                f"✅ <b>{campo}</b> aggiornato.",
                parse_mode="HTML",
                reply_markup=_kb_giocatore(gid),
            )
            await update.effective_message.reply_text(
                _testo_giocatore(gid), parse_mode="HTML"
            )

        elif categoria == "c":
            # Campo contrattuale: aggiorna contratto attivo + log
            contratto = db.get_contratto_attivo(gid)
            if not contratto:
                await update.effective_message.reply_text("❌ Nessun contratto attivo.")
                return DP_SCEGLI_CAMPO
            valore_db = int(valore) if campo in ("importo", "anni_originali") else valore
            _q(f"UPDATE contratti SET {campo} = %s WHERE id = %s",
               (valore_db, contratto["id"]))
            await _log_modifica(update, context, gid, campo, valore)
            await update.effective_message.reply_text(
                f"✅ <b>{campo}</b> aggiornato. Operazione loggata.",
                parse_mode="HTML",
                reply_markup=_kb_giocatore(gid),
            )
            await update.effective_message.reply_text(
                _testo_giocatore(gid), parse_mode="HTML"
            )

        elif categoria == "r":
            # Campo rookie
            rookie = db.get_rookie_by_giocatore(gid)
            if not rookie:
                await update.effective_message.reply_text("❌ Nessun record rookie.")
                return DP_SCEGLI_CAMPO
            valore_db = int(valore) if campo in ("pick_numero", "anni_scala") else valore
            _q(f"UPDATE rookie SET {campo} = %s WHERE id = %s",
               (valore_db, rookie["id"]))
            await _log_modifica(update, context, gid, campo, valore)
            await update.effective_message.reply_text(
                f"✅ <b>{campo}</b> aggiornato. Operazione loggata.",
                parse_mode="HTML",
                reply_markup=_kb_giocatore(gid),
            )
            await update.effective_message.reply_text(
                _testo_giocatore(gid), parse_mode="HTML"
            )

    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore: <code>{e}</code>", parse_mode="HTML")

    return DP_SCEGLI_CAMPO


async def _log_modifica(update, context, gid: int, campo: str, valore: str):
    g = db.get_giocatore(gid)
    nome = g["nome_common"] if g else f"#{gid}"
    log_channel = settings.load_globals().get("log_channel_id")
    if log_channel:
        try:
            await context.bot.send_message(
                chat_id=log_channel,
                text=(
                    f"⚠️ <b>Dev edit</b> — {update.effective_user.first_name}\n"
                    f"Giocatore: <b>{nome}</b> #{gid}\n"
                    f"Campo: <code>{campo}</code>\n"
                    f"Nuovo valore: <code>{valore}</code>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Log modifica fallito: %s", e)


async def cmd_annulla_dev(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("dp_gid", None)
    context.user_data.pop("dp_campo", None)
    context.user_data.pop("dp_categoria", None)
    await update.effective_message.reply_text("Operazione annullata.")
    return ConversationHandler.END


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("dev_player", cmd_dev_player)],
        states={
            DP_SCEGLI_CAMPO: [
                CallbackQueryHandler(cb_dp, pattern=r"^dp:.+$"),
            ],
            DP_INSERISCI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, dp_ricevi_valore),
            ],
        },
        fallbacks=[CommandHandler("annulla_dev", cmd_annulla_dev)],
        per_user=True,
        per_chat=True,
        conversation_timeout=300,
    )
    return [conv]

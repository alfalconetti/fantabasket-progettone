"""
I bot sono solo per la lega (Luca, 31/10: «solo i 24 GM possono usare tutto»).

Ogni bot installa questa guardia prima di tutti gli handler (gruppo -101, prima di quella dei comandi admin):
- **chat private** (e guest mode del bot principale): rispondono solo GM (`gm_ids` di teams.json), admin
  (`admin_ids`) e dev (`dev_id`) di globals.json. Agli altri: «bot riservato ai GM della lega», e niente altro;
- **gruppi e canali**: solo quelli della lega, cioè tutti gli id negativi scritti in globals.json (gruppo della
  lega, gruppo admin, canali, canali di log). In un gruppo o canale che non conosce il bot esce da solo, appena
  ce lo aggiungono o appena ci arriva qualcosa, e lo dice al dev in privato;
- nei gruppi della lega risponde a tutti quelli che ci sono (i gruppi li gestiscono gli admin).

teams.json e globals.json si rileggono quando cambiano: un GM nuovo è autorizzato appena è nel file.
"""
import json
import logging
import os

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ApplicationHandlerStop, TypeHandler

logger = logging.getLogger(__name__)

GRUPPO_GUARDIA = -101
RISERVATO = ("🔒 Questo bot è riservato ai GM della lega.\n"
             "Se pensi che sia un errore, scrivi al dev.")
_cache: dict[str, tuple[float, object]] = {}


def _leggi(var: str, default: str):
    path = os.environ.get(var, default)
    try:
        m = os.path.getmtime(path)
    except OSError:
        return {}
    c = _cache.get(path)
    if c and c[0] == m:
        return c[1]
    try:
        with open(path, encoding="utf-8") as f:
            dati = json.load(f)
    except (OSError, ValueError):
        return c[1] if c else {}
    _cache[path] = (m, dati)
    return dati


def _intero(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def autorizzati() -> set[int]:
    g = _leggi("GLOBALS_PATH", "/config/globals.json") or {}
    t = _leggi("TEAMS_PATH", "/config/teams.json") or {}
    squadre = t.get("teams", []) if isinstance(t, dict) else t
    out = {_intero(x) for sq in squadre or [] for x in (sq.get("gm_ids") or [])}
    out |= {_intero(x) for x in g.get("admin_ids") or []}
    out.add(_intero(g.get("dev_id")))
    return {x for x in out if x}


def chat_della_lega() -> set[int]:
    """Tutti gli id negativi (gruppi e canali) scritti in globals.json, a qualsiasi profondità."""
    out = set()

    def guarda(v):
        if isinstance(v, dict):
            for x in v.values():
                guarda(x)
        elif isinstance(v, list):
            for x in v:
                guarda(x)
        elif not isinstance(v, bool):
            n = _intero(v)
            if n is not None and n < 0:
                out.add(n)
    guarda(_leggi("GLOBALS_PATH", "/config/globals.json") or {})
    return out


def esito(tipo_chat: str | None, chat_id, user_id) -> str:
    """«ok», «riservato» (privato di uno non autorizzato) o «esci» (gruppo o canale che non è della lega)."""
    if tipo_chat in ("group", "supergroup", "channel"):
        lega = chat_della_lega()
        if not lega:                     # globals.json non letto o senza chat: meglio non uscire da niente
            return "ok"
        return "ok" if _intero(chat_id) in lega else "esci"
    if tipo_chat == "private" or tipo_chat is None:
        if user_id is None:
            return "ok"
        return "ok" if _intero(user_id) in autorizzati() else "riservato"
    return "ok"


async def _avvisa_dev(bot, chat, chi) -> None:
    dev = _intero((_leggi("GLOBALS_PATH", "/config/globals.json") or {}).get("dev_id"))
    if not dev:
        return
    nome = getattr(chat, "title", None) or getattr(chat, "username", None) or chat.id
    da = f" da {chi.full_name} ({chi.id})" if chi else ""
    try:
        await bot.send_message(dev, f"👋 Mi hanno aggiunto a «{nome}» ({chat.id}){da}: non è della lega, sono uscito.")
    except Exception:
        pass


async def guardia(update: Update, context) -> None:
    bot = context.bot
    guest = getattr(update, "guest_message", None)
    if guest is not None:                                  # guest mode (bot principale): conta chi chiede
        u = getattr(guest, "from_user", None)
        if u and _intero(u.id) not in autorizzati():
            qid = getattr(guest, "guest_query_id", None)
            if qid:
                try:
                    import uuid
                    await bot.answer_guest_query(guest_query_id=qid, result=InlineQueryResultArticle(
                        id=str(uuid.uuid4()), title="Bot riservato ai GM della lega",
                        input_message_content=InputTextMessageContent(RISERVATO)))
                except Exception as err:
                    logger.info("Guest non autorizzato %s: %s", u.id, err)
            raise ApplicationHandlerStop
        return
    chat, user = update.effective_chat, update.effective_user
    mcm = update.my_chat_member
    if mcm and mcm.new_chat_member and mcm.new_chat_member.status in ("left", "kicked"):
        return                           # tolto da un gruppo (anche dopo essere uscito da solo): niente da fare
    e = esito(chat.type if chat else None, chat.id if chat else None, user.id if user else None)
    if e == "ok":
        return
    if e == "esci":
        logger.warning("Chat %s (%s) non della lega: esco", chat.id, chat.type)
        try:
            await bot.leave_chat(chat.id)
        except Exception as err:
            logger.warning("Uscita dalla chat %s non riuscita: %s", chat.id, err)
        await _avvisa_dev(bot, chat, user)
        raise ApplicationHandlerStop
    # privato di uno non autorizzato
    logger.info("Utente %s non autorizzato: bot riservato ai GM", user.id)
    try:
        if update.callback_query:
            await update.callback_query.answer(RISERVATO, show_alert=True)
        elif update.inline_query:
            await update.inline_query.answer([], cache_time=60)
        elif update.effective_message:
            await update.effective_message.reply_text(RISERVATO)
    except Exception:
        pass
    raise ApplicationHandlerStop


def installa(app) -> None:
    app.add_handler(TypeHandler(Update, guardia), group=GRUPPO_GUARDIA)

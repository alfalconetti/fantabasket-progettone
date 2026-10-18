"""
Registro delle azioni nel bot principale (v6.0.0): `segna` per i flussi del bot e `/registro` per
consultarlo (anche dal pannello admin, «📜 Registro»). Il registro è unico per tutti i bot
(`shared/azioni.py`, tabella registro_azioni): da qui si vedono anche bot aste, loucabot e IPanchinari.

/registro [filtri] (admin: tutto; GM: solo le righe della sua squadra), filtri in qualsiasi ordine:
  N (giorni, es. 7) · squadra (id, nome o GM) · giocatore (nome) · admin|gm|dev|sistema ·
  principale|aste|loucabot|ipanchinari · altro testo = azione (es. taglio) · @username o nome di chi
Il risultato è un file Markdown.
"""
import io
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db
import settings
import teams as tm
from settings import solo_privato
from shared import azioni as A

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
BOT_ALIAS = {"principale": "main", "main": "main", "aste": "aste", "loucabot": "louca", "louca": "louca",
             "ipanchinari": "ipa", "ipa": "ipa", "panchinari": "ipa"}


def _nome(team_id: str) -> str:
    t = tm.get_team_by_id(team_id)
    return t["nome"] if t else team_id


async def segna(bot, user, veste: str, azione: str, **campi) -> dict | None:
    """Registra l'azione (e, se admin o dev, la riga sul canale log del bot principale). Non solleva."""
    try:
        chat = settings.load_globals().get("log_channel_id_main")
    except Exception:
        chat = None
    return await A.azione(db._q, bot, chat, "main", user, veste, azione, nomi_squadre=_nome, **campi)


async def solo_log(bot, user, veste: str, azione: str, **campi) -> None:
    """Solo la riga sul canale log (admin e dev): il riassunto di un'azione in blocco, le cui righe sono
    già nel registro una per una (segna_sync)."""
    try:
        chat = settings.load_globals().get("log_channel_id_main")
    except Exception:
        chat = None
    await A.azione(db._q, bot, chat, "main", user, veste, azione, nomi_squadre=_nome, nel_registro=False, **campi)


def segna_sync(user, veste: str, azione: str, **campi) -> dict | None:
    """Solo il registro (per funzioni non async o job senza bot): niente canale log."""
    return A.registra(db._q, "main", user, veste, azione, **campi)


# ── /registro ──────────────────────────────────────────────────────────────────

def filtri(args: list[str]) -> tuple[dict, list[str]]:
    """Dagli argomenti: ({filtri per azioni.cerca}, [descrizione dei filtri])."""
    f, desc = {}, []
    resto = []
    for a in args:
        al = a.lower()
        if a.isdigit() and int(a) <= 3650:
            f["giorni"] = int(a); desc.append(f"ultimi {a} giorni")
        elif al in A.VESTI:
            f["veste"] = al; desc.append(f"veste {al}")
        elif al in BOT_ALIAS:
            f["bot"] = BOT_ALIAS[al]; desc.append(A.NOMI_BOT[BOT_ALIAS[al]])
        elif a.startswith("@") and len(a) > 1:
            f["chi_testo"] = a; desc.append(f"chi {a}")
        else:
            resto.append(a)
    if resto:
        testo = " ".join(resto)
        t = tm.get_team_by_query(testo)
        if t:
            f["squadra"] = t["id"]; desc.append(f"squadra {t['nome']}")
        else:
            from utils import normalizza
            gioc = db.cerca_giocatori(normalizza(testo)) or []
            if len(gioc) == 1:
                f["giocatore_id"] = gioc[0]["id"]; desc.append(f"giocatore {gioc[0]['nome_common']}")
            else:
                f["azione_"] = testo; desc.append(f"azione «{testo}»")
    return f, desc


def testo_md(righe: list[dict], desc: list[str], limite: int) -> str:
    e = lambda x: str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")
    out = [f"# Registro delle azioni", "",
           f"Filtri: {', '.join(desc) or 'nessuno'} · {len(righe)} righe"
           + (f" (le ultime {limite})" if len(righe) >= limite else "") + "  ",
           f"Estratto il {datetime.now(timezone.utc).astimezone(ROMA):%d/%m/%Y %H:%M} (ora italiana). "
           "Le azioni prima della v6.0.0 non sono nel registro.", "",
           "| Quando | Bot | Chi | Veste | Azione | Squadre | Oggetto | Prima → dopo | Nota |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in righe:
        pd = "" if r.get("prima") is None and r.get("dopo") is None else f"{e(r.get('prima') or '—')} → {e(r.get('dopo') or '—')}"
        out.append(f"| {r['quando'].astimezone(ROMA):%d/%m/%Y %H:%M} | {A.NOMI_BOT.get(r['bot'], r['bot'])} | "
                   f"{e(r.get('chi_nome') or '—')} | {r['veste']} | {e(r['azione'])} | "
                   f"{e(', '.join(_nome(s) for s in (r.get('squadre') or [])))} | {e(r.get('oggetto') or '')} | {pd} | "
                   f"{e(r.get('nota') or '')} |")
    return "\n".join(out) + "\n"


async def _manda(bot, chat_id: int, user, args: list[str]) -> str | None:
    """Manda il file; None se va bene, altrimenti il motivo del rifiuto."""
    admin = settings.is_admin(user.id)
    f, desc = filtri(args)
    if not admin:
        t = tm.get_team_by_gm(user.id)
        if not t:
            return "⛔ Il registro lo vedono gli admin e i GM (solo per la loro squadra)."
        if f.get("squadra") and f["squadra"] != t["id"]:
            return "⛔ Puoi vedere solo il registro della tua squadra."
        f["squadra"] = t["id"]
        desc = [d for d in desc if not d.startswith("squadra")] + [f"squadra {t['nome']}"]
    limite = 500
    import asyncio
    righe = await asyncio.to_thread(A.cerca, db._q, limite=limite, **f)
    testo = testo_md(righe, desc, limite)
    adesso = datetime.now(timezone.utc).astimezone(ROMA)
    await bot.send_document(chat_id=chat_id, document=io.BytesIO(testo.encode("utf-8")),
                            filename=f"registro-{adesso:%Y%m%d-%H%M}.md",
                            caption=f"📜 Registro delle azioni ({len(righe)} righe)" + (f" — {', '.join(desc)}" if desc else ""))
    return None


@solo_privato
async def cmd_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    motivo = await _manda(context.bot, update.effective_chat.id, u, list(context.args or []))
    if motivo:
        await update.effective_message.reply_text(motivo)


async def cb_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pannello admin → 📜 Registro: gli ultimi 7 giorni."""
    q = update.callback_query
    if not settings.is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer("Preparo il registro…")
    await _manda(context.bot, q.message.chat_id, q.from_user, ["7"])


def get_handlers() -> list:
    return [CommandHandler("registro", cmd_registro), CallbackQueryHandler(cb_registro, pattern=r"^reg:7$")]

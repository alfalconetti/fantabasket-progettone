"""
Soprannomi (alias): le righe confermate nelle panchine, che la volta dopo si riconoscono da sole.

Seguono il giocatore, non la squadra: quando un giocatore cambia squadra i suoi soprannomi valgono
per la squadra nuova (e non più per la vecchia, perché lì non è più a roster). /soprannomi li
mostra per i giocatori della propria squadra, chiunque li abbia scritti, e coi bottoni si
cancellano quelli sbagliati o vecchi. /soprannomi SQUADRA mostra quelli di un'altra squadra: i GM
li possono solo guardare (niente bottoni), gli admin anche cancellare.

Callback: so:p:<team>:<pagina> · so:d:<team>:<id alias>:<pagina>.
"""
import logging

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import abbina
import config
import db
from comune import chi, e, log

logger = logging.getLogger(__name__)
PER_PAGINA = 10


def elenco(team_id: str) -> tuple[list[dict], dict[int, str]]:
    """(soprannomi dei giocatori della squadra, nomi). Senza quelli uguali al nome vero."""
    roster = db.roster(team_id, config.stagione())
    nomi = {g["id"]: g["nome_common"] for g in roster}
    al = [a for a in db.alias_giocatori(list(nomi)) if a["alias"] != abbina.chiave(nomi.get(a["giocatore_id"], ""))]
    ordine = {gid: i for i, gid in enumerate(nomi)}
    al.sort(key=lambda a: (ordine.get(a["giocatore_id"], 999), a["alias"]))
    return al, nomi


def schermata(team_id: str, pagina: int = 0, modifica: bool = True) -> tuple[str, K | None]:
    """Il messaggio di /soprannomi; senza `modifica` (GM su un'altra squadra) solo il testo."""
    al, nomi = elenco(team_id)
    t = [f"🏷 <b>Soprannomi di {e(config.nome(team_id))}</b>", ""]
    if not al:
        t.append("Nessuno per ora. Si imparano da soli quando confermi una panchina con una riga che il bot non conosceva.")
        return "\n".join(t), None
    per_gioc: dict[int, list[str]] = {}
    for a in al:
        da = f" <i>(da {e(config.nome(a['team_id']))})</i>" if a["team_id"] != team_id else ""
        per_gioc.setdefault(a["giocatore_id"], []).append(f"«{e(a['alias'])}»{da}")
    for gid, lista in per_gioc.items():
        t.append(f"<b>{e(nomi[gid])}</b>: " + " · ".join(lista))
    t += ["", "Il bot riconosce queste righe senza chiedere. Seguono il giocatore anche se cambia squadra."
              + (" Tocca 🗑 per cancellarne uno (sbagliato o vecchio)." if modifica else "")]
    if not modifica:
        return "\n".join(t), None
    pagine = max(1, -(-len(al) // PER_PAGINA))
    pagina = max(0, min(pagina, pagine - 1))
    tasti = [[B(f"🗑 {a['alias'][:30]} → {nomi[a['giocatore_id']]}",        # nome intero: gli omonimi
                callback_data=f"so:d:{team_id}:{a['id']}:{pagina}")]
             for a in al[pagina * PER_PAGINA:(pagina + 1) * PER_PAGINA]]
    nav = []
    if pagina > 0:
        nav.append(B("⬅️", callback_data=f"so:p:{team_id}:{pagina - 1}"))
    if pagine > 1:
        nav.append(B(f"{pagina + 1}/{pagine}", callback_data=f"so:p:{team_id}:{pagina}"))
    if pagina < pagine - 1:
        nav.append(B("➡️", callback_data=f"so:p:{team_id}:{pagina + 1}"))
    if nav:
        tasti.append(nav)
    return "\n".join(t), K(tasti)


async def cmd_soprannomi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/soprannomi (la propria squadra) · /soprannomi SQUADRA (GM: solo guardare; admin: anche cancellare)."""
    uid = update.effective_user.id
    mia = config.squadra_del_gm(uid)
    if not mia and not config.is_admin(uid):
        await update.effective_message.reply_text("Non risulti GM di nessuna squadra.")
        return
    team = mia
    if context.args:
        from shared.squadre import cerca_squadra
        team = cerca_squadra(" ".join(context.args), config.squadre())
    if not team:
        await update.effective_message.reply_text("Uso: /soprannomi (la tua squadra) · /soprannomi SQUADRA (un'altra).")
        return
    modifica = config.is_admin(uid) or uid in config.gm_ids(team["id"])
    testo, tasti = schermata(team["id"], modifica=modifica)
    await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=tasti)


async def cb_soprannomi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parti = q.data.split(":")
    azione, team_id = parti[1], parti[2]
    uid = update.effective_user.id
    if uid not in config.gm_ids(team_id) and not config.is_admin(uid):
        await q.answer("Non è la tua squadra.", show_alert=True)
        return
    pagina = int(parti[-1])
    if azione == "d":
        al, nomi = elenco(team_id)
        a = next((x for x in al if x["id"] == int(parti[3])), None)
        if not a:
            await q.answer("Già cancellato.")
        else:
            db.elimina_alias(a["id"])
            await q.answer("Cancellato")
            await log(context.bot, f"🏷 Soprannome «{e(a['alias'])}» → {e(nomi[a['giocatore_id']])} cancellato da "
                                   f"{chi(update)} ({e(config.nome(team_id))})")
    else:
        await q.answer()
    testo, tasti = schermata(team_id, pagina)
    await q.edit_message_text(testo, parse_mode="HTML", reply_markup=tasti)


def get_handlers() -> list:
    return [CommandHandler("soprannomi", cmd_soprannomi), CallbackQueryHandler(cb_soprannomi, pattern=r"^so:")]

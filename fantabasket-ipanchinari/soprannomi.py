"""
Soprannomi (alias): le righe confermate nelle panchine, che la volta dopo si riconoscono da sole.

Seguono il giocatore, non la squadra: quando un giocatore cambia squadra i suoi soprannomi valgono
per la squadra nuova (e non più per la vecchia, perché lì non è più a roster). /soprannomi li
mostra per i giocatori della propria squadra, chiunque li abbia scritti, e coi bottoni si
cancellano quelli sbagliati o vecchi. /soprannomi SQUADRA mostra quelli di un'altra squadra: i GM
li possono solo guardare (niente bottoni), gli admin anche cancellare.

/soprannomi tutti (admin): tutti i soprannomi della lega, prima quelli che col nome del giocatore
non c'entrano niente (somiglianza bassa): in un file .md completo e i sospetti nel messaggio.

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


def somiglianza(alias_: str, nome: str) -> float:
    """Da 0 a 1: quanto il soprannome somiglia al nome (intero, nome, cognome, iniziali).
    1 se è un pezzo del nome o ne è l'inizio (es. «giannis», «sga», «wemby»)."""
    from difflib import SequenceMatcher
    a, n = abbina.chiave(alias_), abbina.chiave(nome)
    if not a or not n:
        return 0.0
    parti = n.split()
    iniziali = "".join(p[0] for p in parti)
    if a.replace(" ", "") in n.replace(" ", "") or a == iniziali or any(
            len(p) >= 3 and (p.startswith(a[:4]) or a.startswith(p[:4])) for p in parti):
        return 1.0
    candidati = [n, n.replace(" ", ""), iniziali] + parti
    return max(SequenceMatcher(None, a.replace(" ", ""), c).ratio() for c in candidati)


SOGLIA_SOSPETTI = 0.5


def tutti() -> list[dict]:
    """Tutti i soprannomi (diversi dal nome vero), con giocatore, squadra di adesso, chi li ha
    scritti e la somiglianza; dal più sospetto."""
    righe = db.q("""SELECT a.id, a.alias, a.team_id AS da, a.creato, g.id AS giocatore_id, g.nome_common AS nome,
                           (SELECT c.team_id FROM contratti c WHERE c.giocatore_id = g.id AND c.attivo LIMIT 1) AS squadra
                    FROM ipa_alias a JOIN giocatori g ON g.id = a.giocatore_id""", many=True) or []
    out = []
    for x in righe:
        if x["alias"] == abbina.chiave(x["nome"]):
            continue
        out.append({**x, "somiglianza": somiglianza(x["alias"], x["nome"])})
    out.sort(key=lambda x: (x["somiglianza"], x["nome"], x["alias"]))
    return out


def file_tutti(lista: list[dict]) -> str:
    md = ["# Soprannomi della lega", "",
          f"{len(lista)} soprannomi. Somiglianza col nome da 0 a 1: sotto {SOGLIA_SOSPETTI} sono «sospetti» "
          "(non c'entrano col nome: magari sensati, magari solo confondono).", "",
          "| Soprannome | Giocatore | Squadra di adesso | Scritto da | Somiglianza |", "|---|---|---|---|---|"]
    for x in lista:
        md.append(f"| {'⚠️ ' if x['somiglianza'] < SOGLIA_SOSPETTI else ''}«{x['alias']}» | {x['nome']} | "
                  f"{config.nome(x['squadra']) if x['squadra'] else '— (svincolato)'} | {config.nome(x['da'])} | {x['somiglianza']:.2f} |")
    md += ["", "Per cancellarne uno: /soprannomi SQUADRA (la squadra di adesso del giocatore) e 🗑."]
    return "\n".join(md)


async def manda_tutti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import io
    lista = tutti()
    sospetti = [x for x in lista if x["somiglianza"] < SOGLIA_SOSPETTI]
    t = [f"🏷 <b>Soprannomi della lega</b>: {len(lista)}, di cui <b>{len(sospetti)} sospetti</b> "
         f"(col nome non c'entrano niente)", ""]
    for x in sospetti[:30]:
        t.append(f"• «{e(x['alias'])}» → {e(x['nome'])} <i>({e(config.nome(x['squadra'])) if x['squadra'] else 'svincolato'}"
                 f", scritto da {e(config.nome(x['da']))})</i>")
    if len(sospetti) > 30:
        t.append(f"… e altri {len(sospetti) - 30} nel file")
    t += ["", "Tutti nel file, dal più sospetto. Per cancellarne uno: /soprannomi SQUADRA e 🗑."]
    await update.effective_message.reply_text("\n".join(t)[:4000], parse_mode="HTML")
    await update.effective_message.reply_document(document=io.BytesIO(file_tutti(lista).encode("utf-8")),
                                                  filename="soprannomi.md")


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
    if context.args and context.args[0].lower() == "tutti":
        if not config.is_admin(uid):
            await update.effective_message.reply_text("⛔ /soprannomi tutti è solo per gli admin.")
            return
        await manda_tutti(update, context)
        return
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
            from registro import segna_sync
            segna_sync(update.effective_user, "admin" if config.is_admin(update.effective_user.id)
                       and update.effective_user.id not in config.gm_ids(team_id) else "gm",
                       "soprannome cancellato", squadre=team_id, giocatore_id=a["giocatore_id"],
                       oggetto=f"«{a['alias']}»", prima=nomi[a["giocatore_id"]], dopo="cancellato")
            await q.answer("Cancellato")
            await log(context.bot, f"🏷 Soprannome «{e(a['alias'])}» → {e(nomi[a['giocatore_id']])} cancellato da "
                                   f"{chi(update)} ({e(config.nome(team_id))})")
    else:
        await q.answer()
    testo, tasti = schermata(team_id, pagina)
    await q.edit_message_text(testo, parse_mode="HTML", reply_markup=tasti)


def get_handlers() -> list:
    return [CommandHandler("soprannomi", cmd_soprannomi), CallbackQueryHandler(cb_soprannomi, pattern=r"^so:")]

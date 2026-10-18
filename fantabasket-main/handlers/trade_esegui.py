"""
Trade: scrittura di una trade approvata nel database (contratti, pick, diritti, DPE, RFA
dichiarati, movimenti) e suo annullamento con /annulla_trade_admin. `_scrivi_trade` è l'unico
punto che sposta gli asset: con inverti=True li riporta indietro.
"""
import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import settings
from settings import solo_privato
import teams as tm
from utils import ROME, format_dt
from handlers.trade_comune import _notifica_squadre

logger = logging.getLogger(__name__)


# ── scrittura della trade (anche al contrario, per annullarla) ──────────────────

class TradeNonEseguibile(Exception):
    """La trade non può essere eseguita/annullata così com'è: nessuna modifica è stata salvata."""


def _nome_item(item: dict) -> str:
    return item.get("nome_common") or f"#{item.get('giocatore_id') or item.get('pick_id')}"


def _scrivi_trade(trade_id: int, trade_ref: str, approvata_da: str | None, inverti: bool = False) -> None:
    """Esegue (o, con inverti=True, annulla) TUTTE le scritture di una trade in
    un'unica transazione DB: o passano tutte o nessuna. Ogni asset viene
    verificato prima di essere spostato; se qualcosa non torna → TradeNonEseguibile."""
    trade    = db.get_trade(trade_id)
    items    = db.get_items_trade(trade_id)
    stagione = trade["stagione"]
    nota_tx  = f"ANNULLAMENTO {trade['trade_ref']}" if inverti else trade_ref
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stato FROM trade WHERE id = %s FOR UPDATE", (trade_id,))
            stato = (cur.fetchone() or [None])[0]
            if inverti and stato != "approvata":
                raise TradeNonEseguibile(f"la trade è in stato '{stato}', non 'approvata'")
            if not inverti and stato == "approvata":
                raise TradeNonEseguibile("la trade risulta già approvata ed eseguita")
            if not inverti and stato in ("rifiutata_gm", "rifiutata_admin", "annullata"):
                raise TradeNonEseguibile(f"la trade è in stato '{stato}'")
            cur.execute("SELECT team_id FROM trade_squadre WHERE trade_id = %s", (trade_id,))
            squadre = {r[0] for r in cur.fetchall()}
            # registro unico (v3.10.0): pick e diritti hanno il loro movimento, se lo storico esiste
            registra_asset = db.storico_pick_diritti_presente(cur)
            for item in items:
                if item["team_id_a"] not in squadre or item["team_id_da"] not in squadre \
                        or item["team_id_a"] == item["team_id_da"]:
                    raise TradeNonEseguibile(f"{_nome_item(item)}: destinatario non valido "
                                             f"('{item['team_id_a']}'), va riassegnato dalla bozza")
                da, a = (item["team_id_a"], item["team_id_da"]) if inverti else (item["team_id_da"], item["team_id_a"])
                if item["tipo"] == "giocatore":
                    gid = item["giocatore_id"]
                    cur.execute("SELECT id, team_id FROM contratti WHERE giocatore_id = %s AND attivo = TRUE FOR UPDATE",
                                (gid,))
                    c = cur.fetchone()
                    if not c:
                        raise TradeNonEseguibile(f"{_nome_item(item)} non ha più un contratto attivo")
                    if c[1] != da:
                        raise TradeNonEseguibile(f"{_nome_item(item)} non è più nella squadra che lo cede")
                    cur.execute("UPDATE contratti SET team_id = %s WHERE id = %s", (a, c[0]))
                    # la DPE della stagione segue il giocatore (regolamento: chi lo riceve
                    # se lo porta dietro con l'importo ridotto e lo slot libero)
                    cur.execute("UPDATE dpe SET team_id = %s WHERE giocatore_id = %s AND team_id = %s "
                                "AND stagione = %s", (a, gid, da, settings.stagione_corrente()))
                    # RFA dichiarato (Luca, 12/10/2026): prima delle aste RFA la dichiarazione
                    # decade (chi lo cede può dichiararne un altro); con le aste aperte segue il
                    # giocatore e il bot aste allinea il proprietario dell'asta. L'annullamento
                    # rimette le cose com'erano: una delle due righe sotto non fa niente.
                    st_rfa = settings.stagione_corrente()
                    if inverti:
                        db.ripristina_rfa_trade(cur, gid, a, st_rfa, trade_id)
                        db.sposta_rfa_trade(cur, gid, da, a, st_rfa)
                    elif settings.rfa_perso_in_trade():
                        db.revoca_rfa_trade(cur, gid, da, st_rfa, trade_id)
                    else:
                        db.sposta_rfa_trade(cur, gid, da, a, st_rfa)
                    cur.execute("INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, "
                                "contratto_id, trade_id, note) VALUES ('traded', %s, %s, %s, %s, %s, %s, %s)",
                                (gid, da, a, stagione, c[0], trade_id, nota_tx))
                elif item["tipo"] == "pick":
                    cur.execute("UPDATE pick SET proprietario_att = %s WHERE id = %s AND proprietario_att = %s",
                                (a, item["pick_id"], da))
                    if cur.rowcount != 1:
                        raise TradeNonEseguibile(f"pick #{item['pick_id']} non più della squadra che la cede")
                    if registra_asset:
                        cur.execute("INSERT INTO transazioni (oggetto, tipo, pick_id, team_id_da, team_id_a, stagione, "
                                    "trade_id, note) VALUES ('pick', 'traded', %s, %s, %s, %s, %s, %s)",
                                    (item["pick_id"], da, a, stagione, trade_id, nota_tx))
                elif item["tipo"] == "diritti":
                    cur.execute("UPDATE rookie SET team_id = %s WHERE giocatore_id = %s AND team_id = %s "
                                "AND firmato = FALSE AND diritti_scaduti = FALSE",
                                (a, item["giocatore_id"], da))
                    if cur.rowcount != 1:
                        raise TradeNonEseguibile(f"diritti di {_nome_item(item)} non più attivi nella squadra che li cede")
                    if registra_asset:
                        cur.execute("INSERT INTO transazioni (oggetto, tipo, giocatore_id, team_id_da, team_id_a, stagione, "
                                    "trade_id, note) VALUES ('diritti', 'traded', %s, %s, %s, %s, %s, %s)",
                                    (item["giocatore_id"], da, a, stagione, trade_id, nota_tx))
            if inverti:
                cur.execute("UPDATE trade SET stato = 'annullata', aggiornato = NOW() WHERE id = %s", (trade_id,))
            else:
                cur.execute("UPDATE trade SET stato = 'approvata', trade_ref = %s, approvata_da = %s, "
                            "approvata_at = NOW(), bozza_num = NULL, aggiornato = NOW() WHERE id = %s",
                            (trade_ref, approvata_da, trade_id))


async def _esegui_trade(context, trade_id: int, trade_ref: str, approvata_da: str | None = None, user=None):
    """Approva ed esegue la trade in un'unica transazione DB (vedi _scrivi_trade),
    poi notifiche, sync e dichiarazioni di ruolo. Solleva TradeNonEseguibile se
    non è eseguibile: in quel caso il DB non è stato toccato."""
    trade    = db.get_trade(trade_id)
    items    = db.get_items_trade(trade_id)
    fase_corrente = settings.fase()
    from validators.trade import rfa_che_decadono
    rfa_persi = rfa_che_decadono(items, settings.stagione_corrente())   # prima di scrivere: dopo non lo sono più
    rfa_coinvolti = [i for i in items if i["tipo"] == "giocatore"
                     and db.rfa_dichiarato(i["giocatore_id"], settings.stagione_corrente())]

    _scrivi_trade(trade_id, trade_ref, approvata_da or trade.get("approvata_da"))
    logger.info("Trade %s eseguita.", trade_ref)
    from handlers.trade_comune import segna_trade
    await segna_trade(context.bot, user, "admin", "trade approvata ed eseguita", trade_id,
                      prima="in approvazione", dopo=trade_ref)

    # Notifica tutti i GM coinvolti
    squadre = [s["team_id"] for s in db.get_squadre_trade(trade_id)]
    for team_id in squadre:
        team = tm.get_team_by_id(team_id)
        if not team:
            continue
        testo = f"✅ <b>Trade {trade_ref} eseguita!</b>"
        riceve_giocatori = any(i["tipo"] == "giocatore" and i["team_id_a"] == team_id for i in items)
        if not riceve_giocatori:
            pass
        elif fase_corrente in settings.FASI_RUOLI_RS:
            testo += "\nPer i nuovi giocatori ti arrivano qui i ruoli da dichiarare (48h), se ce n'è bisogno."
        elif fase_corrente == "offseason-ruoli":
            testo += "\nRicordati di dichiarare i ruoli dei nuovi giocatori con /dichiarazione_ruoli."
        for i in rfa_persi:
            nome_g = html.escape(i.get("nome_common") or str(i["giocatore_id"]))
            if i["team_id_da"] == team_id:
                testo += (f"\n🔓 <b>{nome_g}</b> era il tuo RFA dichiarato: con la trade la dichiarazione decade. "
                          f"Se vuoi puoi dichiararne un altro con /dichiara_rfa.")
            elif i["team_id_a"] == team_id:
                testo += (f"\nℹ️ <b>{nome_g}</b> arriva con il contratto finito (x0) e senza dichiarazione RFA: "
                          f"non pesa sul cap.")
        for gm_id in team.get("gm_ids", []):
            try:
                await context.bot.send_message(
                    chat_id=gm_id, text=testo, parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Notifica GM %d fallita: %s", gm_id, e)

    # RFA: una riga per giocatore sul canale log e riepilogo aggiornato sul canale principale
    if rfa_coinvolti:
        from handlers.stagione import log_rfa, aggiorna_riepilogo_rfa
        persi = {i["giocatore_id"] for i in rfa_persi}
        for i in rfa_coinvolti:
            nome_g = html.escape(i.get("nome_common") or str(i["giocatore_id"]))
            da = html.escape((tm.get_team_by_id(i["team_id_da"]) or {}).get("nome", i["team_id_da"]))
            a = html.escape((tm.get_team_by_id(i["team_id_a"]) or {}).get("nome", i["team_id_a"]))
            if i["giocatore_id"] in persi:
                await log_rfa(context.bot, f"🔓 <b>RFA — {da}</b>: <b>{nome_g}</b> ceduto a {a} con la "
                                           f"{trade_ref}, la dichiarazione decade")
            else:
                await log_rfa(context.bot, f"➡️ <b>RFA</b>: <b>{nome_g}</b> passa da {da} a {a} con la "
                                           f"{trade_ref}, insieme alla dichiarazione")
        await aggiorna_riepilogo_rfa(context.bot)

    # Sync GAS — roster e scelte
    try:
        import gas_client
        gas_client.sync_after_trade(trade_id)
    except Exception as e:
        logger.warning("sync GAS dopo trade fallito: %s", e)

    # Ruoli in regular season: dichiarazioni in sospeso per i giocatori ricevuti
    try:
        from handlers.ruoli_rs import apri_pendenti
        for team_id in squadre:
            ricevuti = [i["giocatore_id"] for i in items
                        if i["tipo"] == "giocatore" and i["team_id_a"] == team_id]
            await apri_pendenti(context.bot, team_id, ricevuti, "trade", trade_ref)
    except Exception as e:
        logger.warning("Apertura dichiarazioni ruolo post-trade: %s", e)


# ── annullamento di una trade approvata ─────────────────────────────────────────

async def _rollback_trade(trade_id: int):
    """
    Inverte una trade già eseguita, in un'unica transazione DB:
    giocatori, pick e diritti tornano al mittente, transazioni inverse, stato 'annullata'.
    Solleva TradeNonEseguibile se un asset non è più dove dovrebbe (nessuna modifica salvata).
    """
    trade = db.get_trade(trade_id)
    _scrivi_trade(trade_id, trade["trade_ref"], None, inverti=True)
    logger.info("Trade %s annullata e rollback eseguito.", trade["trade_ref"])

    # Sync GAS — roster e scelte
    try:
        import gas_client
        squadre = db.get_squadre_trade(trade_id)
        team_ids = [s["team_id"] for s in squadre]
        gas_client.sync_teams(team_ids)
        gas_client.sync_scelte()
    except Exception as e:
        logger.warning("sync GAS dopo rollback trade fallito: %s", e)


async def _valida_rollback(trade_id: int) -> list[str]:
    """
    Verifica che il rollback sia possibile: tutti gli asset ricevuti
    devono essere ancora nei team che li avevano ricevuti.
    Restituisce lista di errori (vuota = rollback possibile).
    """
    items  = db.get_items_trade(trade_id)
    errori = []

    for item in items:
        if item["tipo"] == "giocatore":
            gid       = item["giocatore_id"]
            contratto = db.get_contratto_attivo(gid)
            nome      = item.get("nome_common", f"#{gid}")
            if not contratto:
                errori.append(f"{nome} non ha più un contratto attivo")
            elif contratto["team_id"] != item["team_id_a"]:
                team_att = tm.get_team_by_id(contratto["team_id"])
                nome_att = team_att["nome"] if team_att else contratto["team_id"]
                team_att_orig = tm.get_team_by_id(item["team_id_a"])
                nome_orig = team_att_orig["nome"] if team_att_orig else item["team_id_a"]
                errori.append(
                    f"{nome}: dovrebbe essere a {nome_orig} ma è a {nome_att}"
                )

        elif item["tipo"] == "pick":
            pick = db.get_pick(item["pick_id"])
            if not pick:
                errori.append(f"Pick #{item['pick_id']} non trovata nel DB")
            elif pick["proprietario_att"] != item["team_id_a"]:
                team_att = tm.get_team_by_id(pick["proprietario_att"])
                nome_att = team_att["nome"] if team_att else pick["proprietario_att"]
                team_att_orig = tm.get_team_by_id(item["team_id_a"])
                nome_orig = team_att_orig["nome"] if team_att_orig else item["team_id_a"]
                rnd  = "1st" if pick["round"] == 1 else "2nd"
                errori.append(
                    f"Pick {rnd} {pick['anno']}: dovrebbe essere a {nome_orig} ma è a {nome_att}"
                )

        elif item["tipo"] == "diritti":
            rookie = db._q("SELECT * FROM rookie WHERE giocatore_id = %s AND firmato = FALSE "
                           "AND diritti_scaduti = FALSE ORDER BY anno_draft DESC LIMIT 1",
                           (item["giocatore_id"],), one=True)
            nome   = item.get("nome_common", f"#{item['giocatore_id']}")
            if not rookie:
                errori.append(f"Diritti di {nome} non più attivi (firmati o scaduti)")
            elif rookie["team_id"] != item["team_id_a"]:
                team_att = tm.get_team_by_id(rookie["team_id"])
                nome_att = team_att["nome"] if team_att else rookie["team_id"]
                team_att_orig = tm.get_team_by_id(item["team_id_a"])
                nome_orig = team_att_orig["nome"] if team_att_orig else item["team_id_a"]
                errori.append(
                    f"Diritti di {nome}: dovrebbe essere a {nome_orig} ma è a {nome_att}"
                )

    return errori

@solo_privato
async def cmd_annulla_trade_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /annulla_trade_admin <trade_ref>
    Es: /annulla_trade_admin TRADE-2026-003
    Riservato agli admin. Annulla una trade già eseguita e notifica il canale.
    """
    from settings import load_globals
    user = update.effective_user
    if user.id not in [int(a) for a in load_globals().get("admin_ids", [])]:
        await update.effective_message.reply_text("⛔ Non sei admin.")
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Uso: /annulla_trade_admin <trade_ref>\n"
            "Es: /annulla_trade_admin TRADE-2026-003"
        )
        return

    trade_ref = context.args[0].upper()
    trade     = db.get_trade_by_ref(trade_ref)

    if not trade:
        await update.effective_message.reply_text(f"❌ Trade '{trade_ref}' non trovata.")
        return

    if trade["stato"] != "approvata":
        await update.effective_message.reply_text(
            f"❌ La trade {trade_ref} è in stato '{trade['stato']}' — solo le trade approvate possono essere annullate."
        )
        return

    await update.effective_message.reply_text(f"⏳ Verifica compatibilità {trade_ref}...")

    errori = await _valida_rollback(trade["id"])
    if errori:
        testo = (
            f"❌ <b>Impossibile annullare {trade_ref}</b>\n\n"
            f"Alcuni asset sono stati spostati nel frattempo:\n"
        )
        for e in errori:
            testo += f"  • {e}\n"
        await update.effective_message.reply_text(testo, parse_mode="HTML")
        return

    await update.effective_message.reply_text("✅ Compatibilità OK, eseguo il rollback...")
    try:
        await _rollback_trade(trade["id"])
    except TradeNonEseguibile as e:
        await update.effective_message.reply_text(
            f"❌ Rollback non eseguito: {e}. Nessuna modifica è stata salvata.")
        return

    admin_nome = user.first_name or str(user.id)
    from handlers.trade_comune import segna_trade
    await segna_trade(context.bot, user, "admin", "trade annullata", trade["id"], prima=trade_ref, dopo="annullata",
                      nota="giocatori, pick e diritti tornati alle squadre di prima")
    from datetime import datetime
    ora = format_dt(datetime.now(ROME))
    # se la trade aveva toccato un RFA, la dichiarazione è tornata: riepilogo aggiornato
    try:
        from handlers.stagione import aggiorna_riepilogo_rfa
        await aggiorna_riepilogo_rfa(context.bot)
    except Exception as e:
        logger.warning("Riepilogo RFA dopo l'annullamento: %s", e)

    # Annuncio canale
    main_channel = load_globals().get("main_channel_id")
    if main_channel:
        try:
            await context.bot.send_message(
                chat_id=main_channel,
                text=(
                    f"⚠️ <b>Trade annullata</b>\n\n"
                    f"La trade <code>{trade_ref}</code> è stata annullata.\n"
                    f"Tutti i giocatori e le pick sono stati ripristinati.\n\n"
                    f"<i>Annullata da {admin_nome} alle {ora}</i>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Annuncio annullamento canale fallito: %s", e)

    await update.effective_message.reply_text(
        f"✅ <b>{trade_ref}</b> annullata. Roster e pick ripristinati.",
        parse_mode="HTML",
    )
    # tutte le squadre coinvolte (prima: solo il proponente, e con `testo` non definito → crash)
    await _notifica_squadre(context, trade["id"],
                            f"⚠️ La trade <b>{trade_ref}</b> è stata annullata dagli admin: "
                            f"giocatori, pick e diritti sono tornati alle squadre di prima.", escludi=("admin",))

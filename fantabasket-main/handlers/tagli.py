"""
Gestione tagli con calcolo impatto taglio automatico.

Percentuali impatto taglio dal regolamento:
  x1 → 3 anni: 50-30-20
  x2 → 4 anni: 60-50-50-40
  x3 → 5 anni: 70-70-60-50-50

Per contratti ≤5M: tabella fissa (vedi _TABELLA_SPALMATA_BASSA).
"""
import logging
import math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
import settings
from settings import solo_privato, richiede_fase, FASI_TRADE_APERTE
import teams as tm
from shared import regole

logger = logging.getLogger(__name__)

# tagli 1x1 gratuiti a stagione: regole.max_tagli_gratuiti() (config/settings.json, 3)


def _e_taglio_gratuito(importo: int, anni_residui: int) -> bool:
    """Contratto 1M x1 → taglio senza impatto (nessun impatto taglio, conta nel limite stagionale)."""
    return importo == 1 and anni_residui == 1

# Percentuali impatto taglio per importo > 5M
_PERC_SPALMATA = {
    1: [0.50, 0.30, 0.20],
    2: [0.60, 0.50, 0.50, 0.40],
    3: [0.70, 0.70, 0.60, 0.50, 0.50],
}

# Tabella fissa per contratti ≤5M (importo: {anni: [rate]})
_TABELLA_SPALMATA_BASSA = {
    1: {1: [1],       2: [1, 1],          3: [1, 1, 1]},
    2: {1: [1, 1],    2: [1, 1, 1, 1],    3: [2, 1, 1, 1, 1]},
    3: {1: [1, 1, 1], 2: [2, 2, 1, 1],    3: [2, 2, 2, 2, 1]},
    4: {1: [2, 1, 1], 2: [2, 2, 2, 2],    3: [3, 3, 2, 2, 2]},
    5: {1: [2, 2, 1], 2: [3, 3, 2, 2],    3: [4, 3, 3, 3, 2]},
}


def calcola_impatto_taglio(importo: int, anni_residui: int, stagione_taglio: str) -> list[dict]:
    """
    Calcola le rate di impatto taglio.
    La somma delle rate = anni_residui × importo.
    anni_residui viene cappato a 3 (massimo previsto dal regolamento).
    """
    anno_base   = int(stagione_taglio)
    anni_res    = min(anni_residui, 3)  # il regolamento va fino a x3

    if importo <= 5 and importo in _TABELLA_SPALMATA_BASSA:
        rate_raw = _TABELLA_SPALMATA_BASSA[importo].get(anni_res, [importo])
        return [
            {"stagione": str(anno_base + i), "importo": r}
            for i, r in enumerate(rate_raw)
        ]

    perc   = _PERC_SPALMATA[anni_res]
    rate   = [math.ceil(importo * p) for p in perc]
    target = anni_residui * importo   # usa anni_residui originale per il totale
    diff   = sum(rate) - target
    # Toglie l'eccedenza dovuta agli arrotondamenti partendo dall'ultima rata,
    # senza mai portarne una sotto 1 (es. 7x1: 4-3-2 → 4-2-1, non 4-3)
    for i in range(len(rate) - 1, -1, -1):
        if diff <= 0:
            break
        togli = min(diff, rate[i] - 1)
        rate[i] -= togli
        diff    -= togli

    return [
        {"stagione": str(anno_base + i), "importo": r}
        for i, r in enumerate(rate) if r > 0
    ]


def _anni_residui(contratto: dict, stagione_corrente: str) -> int:
    """Anni residui del contratto, uguali per tutti (anche i rookie, v3.11.0: ogni pezzo
    della scala è un contratto suo). 0 = contratto finito (x0)."""
    return db.anni_residui(contratto, stagione_corrente)


# ── /taglia <giocatore_id> ────────────────────────────────────────────────────

@solo_privato
@richiede_fase(*FASI_TRADE_APERTE, msg="❌ I tagli non sono disponibili in questa fase.")
async def cmd_taglia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return

    if not context.args:
        # Mostra roster con bottoni
        roster = [r for r in db.get_roster_team(team["id"], senza_10day=True) or [] if not r.get("x0")]   # x0 scadono da soli
        if not roster:
            await update.effective_message.reply_text("Il tuo roster è vuoto.")
            return
        bottoni = [
            [InlineKeyboardButton(
                f"{r['nome_common']} ({r['importo']}M)",
                callback_data=f"taglia_sel:{r['giocatore_id']}"
            )]
            for r in roster
        ]
        await update.effective_message.reply_text(
            "Seleziona il giocatore da tagliare:",
            reply_markup=InlineKeyboardMarkup(bottoni),
        )
        return

    try:
        gid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ ID giocatore non valido.")
        return

    await _mostra_anteprima_taglio(update.effective_message, team, gid)


async def cb_seleziona_taglio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid  = int(query.data.split(":")[1])
    user = update.effective_user
    team = tm.get_team_by_gm(user.id)
    await _mostra_anteprima_taglio(query, team, gid)


class TaglioNonEseguibile(Exception):
    """Taglio non consentito: il messaggio va mostrato così com'è."""


def _valuta_taglio(team: dict, gid: int) -> dict:
    """Tutto quello che serve per anteprima e conferma, calcolato allo stesso modo:
    contratto, anni residui, gratuito (1x1 con meno di 3 gratuiti usati), rate,
    eventuale blocco (roster sotto il minimo in RS) e avviso (minimi dei ruoli)."""
    contratto = db.get_contratto_attivo(gid)
    if not contratto or contratto["team_id"] != team["id"]:
        raise TaglioNonEseguibile("❌ Giocatore non trovato nel tuo roster.")
    if contratto["tipo"] == "10day":
        raise TaglioNonEseguibile("❌ È un 10-day: non si taglia, scade da solo. Per chiuderlo prima chiedi a un admin.")
    stagione = settings.stagione_corrente()
    anni_res = _anni_residui(contratto, stagione)
    if anni_res <= 0:
        raise TaglioNonEseguibile("❌ Il contratto è finito (x0): non si taglia, scade da solo all'inizio "
                                  "della free agency (oppure lo dichiari RFA).")
    usati = db.get_tagli_gratuiti_usati(team["id"], stagione)
    # 1x1: gratuito solo entro i 3 a stagione; dal 4° è un taglio normale (spalmatura 1x1).
    # Prima il 4° 1x1 era vietato, ma il regolamento consente tagli illimitati.
    gratuito = _e_taglio_gratuito(contratto["importo"], anni_res) and usati < regole.max_tagli_gratuiti()
    rate = [] if gratuito else calcola_impatto_taglio(contratto["importo"], anni_res, stagione)
    avviso = None
    if settings.fase() in settings.FASI_RUOLI_RS:
        roster = db.get_roster_team(team["id"]) or []
        dopo = db.slot_occupati(roster) - 1
        if dopo < settings.min_roster():
            raise TaglioNonEseguibile(
                f"❌ Dopo il taglio il roster scenderebbe a {dopo} giocatori, sotto il minimo di "
                f"{settings.min_roster()} in regular season.")
        try:
            from validators.ruoli import deficit_team
            prima_d = deficit_team(team["id"], stagione)
            dopo_d = deficit_team(team["id"], stagione, togli=[gid])
        except Exception as e:
            logger.warning("Controllo ruoli taglio: %s", e)
            prima_d = dopo_d = 0
        if dopo_d > 0 and dopo_d > prima_d:
            raise TaglioNonEseguibile(
                "❌ Dopo il taglio il roster non rispetterebbe più i minimi dei ruoli (4 G, 4 F, 2 C) "
                "con i ruoli ufficiali: taglio non consentito in regular season.")
    return {"contratto": contratto, "stagione": stagione, "anni_res": anni_res,
            "gratuito": gratuito, "usati": usati, "rate": rate, "avviso": avviso,
            "giocatore": db.get_giocatore(gid)}


async def _mostra_anteprima_taglio(msg_or_query, team: dict, gid: int,
                                   cb_ok: str | None = None, cb_no: str = "taglia_no"):
    async def _rispondi(testo, kb=None):
        if hasattr(msg_or_query, "edit_message_text"):
            await msg_or_query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
        else:
            await msg_or_query.reply_text(testo, parse_mode="HTML", reply_markup=kb)
    try:
        v = _valuta_taglio(team, gid)
    except TaglioNonEseguibile as e:
        await _rispondi(str(e))
        return
    c, nome = v["contratto"], v["giocatore"]["nome_common"]
    if v["gratuito"]:
        testo = (
            f"✂️ <b>Taglio senza impatto — {nome}</b>\n\n"
            f"Contratto: <b>1M × 1 anno</b>\n"
            f"✅ Nessun impatto taglio sul cap.\n"
            f"Tagli gratuiti rimanenti dopo questo: <b>{regole.max_tagli_gratuiti() - v['usati'] - 1}/{regole.max_tagli_gratuiti()}</b>"
        )
    else:
        righe = [f"✂️ <b>Taglio — {nome}</b>\n",
                 f"Contratto: {c['importo']}M × {v['anni_res']} anni residui\n"]
        if _e_taglio_gratuito(c["importo"], v["anni_res"]):
            righe.append(f"<i>Tagli 1x1 gratuiti già usati ({regole.max_tagli_gratuiti()}/{regole.max_tagli_gratuiti()}): "
                         f"questo pesa sul cap.</i>\n")
        righe.append("<b>Impatto taglio sul cap:</b>")
        righe += [f"  • Stagione {r['stagione']}: {r['importo']}M" for r in v["rate"]]
        testo = "\n".join(righe)
    if v["avviso"]:
        testo += "\n\n" + v["avviso"]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma taglio", callback_data=cb_ok or f"taglia_ok:{gid}"),
        InlineKeyboardButton("❌ Annulla",          callback_data=cb_no),
    ]])
    await _rispondi(testo, kb)


def esegui_taglio(team: dict, gid: int) -> dict:
    """Taglio vero e proprio, uguale per GM e admin (v3.10.0: prima l'admin aveva un percorso
    suo, senza controlli di regular season e non atomico). Ricalcola tutto con _valuta_taglio,
    poi contratto chiuso + movimento 'cut' + rate in un'unica transazione DB.
    Solleva TaglioNonEseguibile; restituisce la valutazione con `nota`."""
    v = _valuta_taglio(team, gid)   # gratuiti usati e roster possono essere cambiati dall'anteprima
    c, stagione, gratuito, rate = v["contratto"], v["stagione"], v["gratuito"], v["rate"]
    nome = v["giocatore"]["nome_common"]
    v["nota"] = (f"Taglio senza impatto 1x1 — {nome}" if gratuito
                 else f"Taglio {nome} {c['importo']}M x{v['anni_res']}")
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE contratti SET attivo = FALSE WHERE id = %s AND attivo = TRUE "
                        "AND team_id = %s RETURNING id", (c["id"], team["id"]))
            if not cur.fetchone():
                raise TaglioNonEseguibile("❌ Giocatore non più in questo roster.")
            cur.execute("INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, "
                        "contratto_id, gratuito, note) VALUES ('cut', %s, %s, NULL, %s, %s, %s, %s) RETURNING id",
                        (gid, team["id"], stagione, c["id"], gratuito, v["nota"]))
            trans_id = cur.fetchone()[0]
            for r in rate:
                cur.execute("INSERT INTO impatto_taglio (team_id, giocatore_id, stagione_taglio, stagione, "
                            "importo, transazione_id) VALUES (%s, %s, %s, %s, %s, %s)",
                            (team["id"], gid, stagione, r["stagione"], r["importo"], trans_id))
    logger.info("Taglio: team=%s giocatore=%d gratuito=%s", team["id"], gid, gratuito)
    return v


def testi_taglio(team: dict, v: dict) -> tuple[str, str]:
    """(risposta a chi taglia, annuncio sul canale)."""
    c, rate, nome = v["contratto"], v["rate"], v["giocatore"]["nome_common"]
    if v["gratuito"]:
        usati = v["usati"] + 1
        risposta = (f"✅ <b>{nome}</b> tagliato gratuitamente.\n"
                    f"Tagli gratuiti usati questa stagione: <b>{usati}/{regole.max_tagli_gratuiti()}</b>")
        canale = (f"✂️ <b>{team['gm_nome']}</b> taglia <b>{nome}</b>\n"
                  f"Contratto: {c['importo']}M × 1 anno — nessun impatto\n"
                  f"Tagli gratuiti rimasti: <b>{regole.max_tagli_gratuiti() - usati}/{regole.max_tagli_gratuiti()}</b>")
    else:
        righe_imp = "\n".join(f"  • {r['stagione']}: {r['importo']}M" for r in rate)
        risposta = (f"✅ <b>{nome}</b> tagliato.\n\nImpatto taglio:\n{righe_imp}"
                    + (f"\n\n{v['avviso']}" if v["avviso"] else ""))
        rate_str = " · ".join(f"{r['stagione']}: {r['importo']}M" for r in rate)
        canale = (f"✂️ <b>{team['gm_nome']}</b> taglia <b>{nome}</b>\n"
                  f"Contratto precedente: {c['importo']}M × {v['anni_res']} "
                  f"{'anno' if v['anni_res'] == 1 else 'anni'}\n"
                  f"Impatto taglio: {rate_str}")
    return risposta, canale


async def dopo_taglio(bot, team: dict, v: dict, admin_nome: str | None = None, user=None) -> None:
    """Registro delle azioni, annuncio sul canale, avviso al GM se ha tagliato un admin, sync dei fogli.
    Veste: admin se arriva dal pannello (admin_nome), gm se dal /taglia del GM."""
    from handlers.registro import segna
    c = v["contratto"]
    await segna(bot, user, "admin" if admin_nome else "gm", "taglio", squadre=team["id"],
                giocatore_id=v["giocatore"].get("id") or c.get("giocatore_id"), oggetto=v["giocatore"]["nome_common"],
                prima=f"{c['importo']}M × {v['anni_res']}", dopo="tagliato",
                nota=("gratuito" if v["gratuito"] else "rate: " + ", ".join(f"{r['stagione']} {r['importo']}M" for r in v["rate"])))
    _, canale = testi_taglio(team, v)
    if admin_nome:
        canale += f"\n<i>Registrato da un admin ({admin_nome})</i>"
        for gm in team.get("gm_ids", []):
            try:
                await bot.send_message(chat_id=int(gm), parse_mode="HTML",
                                       text=f"🛠 Un admin ha tagliato <b>{v['giocatore']['nome_common']}</b> "
                                            f"dal tuo roster.")
            except Exception as e:
                logger.warning("Avviso al GM taglio admin fallito: %s", e)
    main_channel = settings.load_globals().get("main_channel_id")
    if main_channel:
        try:
            await bot.send_message(chat_id=main_channel, text=canale, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio canale taglio fallito: %s", e)
    try:
        import gas_client
        gas_client.sync_after_taglio(team["id"])
    except Exception as e:
        logger.warning("GAS sync taglio fallito: %s", e)


async def cb_conferma_taglio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gid  = int(query.data.split(":")[1])
    team = tm.get_team_by_gm(update.effective_user.id)
    if not team:
        await query.edit_message_text("⛔ Non sei registrato come GM.")
        return
    if settings.fase() not in FASI_TRADE_APERTE:   # bottone premuto dopo la chiusura del mercato
        await query.edit_message_text("❌ I tagli non sono disponibili in questa fase.")
        return
    try:
        v = esegui_taglio(team, gid)
    except TaglioNonEseguibile as e:
        await query.edit_message_text(str(e))
        return
    risposta, _ = testi_taglio(team, v)
    await query.edit_message_text(risposta, parse_mode="HTML")
    await dopo_taglio(context.bot, team, v, user=update.effective_user)


async def cb_annulla_taglio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Taglio annullato.")


def get_handlers() -> list:
    return [
        CommandHandler("taglia", cmd_taglia),
        CallbackQueryHandler(cb_seleziona_taglio,  pattern=r"^taglia_sel:\d+$"),
        CallbackQueryHandler(cb_conferma_taglio,   pattern=r"^taglia_ok:\d+$"),
        CallbackQueryHandler(cb_annulla_taglio,    pattern=r"^taglia_no$"),
    ]

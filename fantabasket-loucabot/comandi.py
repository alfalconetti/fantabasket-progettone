"""
Comandi Telegram (menu "/" del client) di loucabot, per scope, come negli altri due bot:
gruppi → calendario e giornata; privato → in più la guida; admin (in privato e nel gruppo admin)
→ in più i comandi admin; dev → in più quelli dev. Si registrano all'avvio.
"""
import logging

from telegram import (BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllChatAdministrators, BotCommandScopeAllPrivateChats,
                      BotCommandScopeChat, BotCommandScopeDefault)

import config

logger = logging.getLogger(__name__)


ORDINE_GM = [
    "guida",
    "calendario", "giornata", "live", "risultati", "live_results", "partita", "notte",          # la giornata
    "classifica", "classifica_conference", "classifica_full", "classifica_home_away", "rendimento_team",
    "playoff", "lottery", "quasi_cup", "calendario_full",                                                 # classifiche
    "player", "prestazione", "giocatori",
    "roster", "assets", "pick", "pick_lega", "draft", "prospetto_rinnovi", "team_diff", "carriera", "trova_trade", "penalita",  # squadre (v7.21.0, dal main)
    "top", "top_storica", "status", "rendimento", "rendimento_carriera", "rendimento_situazione",
    "confronto", "confronto_carriera",                                                         # giocatori
    "pdf_giornata", "pdf_partite", "pdf_roster", "pdf_assets",                                 # PDF in fondo
]


def liste_comandi() -> dict:
    gruppi = [
        BotCommand("calendario", "La giornata tua o di una squadra [N] [SQUADRA]"),
        BotCommand("calendario_full", "Tutto il calendario di una squadra, coi risultati [SQUADRA]"),
        BotCommand("giornata",   "Tutte le partite di una giornata [N] (Q1, Q2: Quasi Cup), coi risultati"),
        BotCommand("risultati",  "I risultati di una giornata in testo [N] (Q1, Q2: Quasi Cup)"),
        BotCommand("live",       "L'immagine del live della giornata [N] (Q1, Q2: Quasi Cup)"),
        BotCommand("top",        "Migliori per fantamedia: [N] o [DA A], [firmati]"),
        BotCommand("top_storica", "Migliori per fantamedia di una stagione passata: ANNO [N] o [DA A]"),
        BotCommand("pdf_giornata", "La giornata in PDF: risultati e partite [N] (Q1, Q2: Quasi Cup)"),
        BotCommand("pdf_partite", "Tutte le partite di una squadra in PDF [SQUADRA] [STAGIONE]"),
        BotCommand("live_results", "Il live della giornata in testo, completo [N]"),
        BotCommand("notte",      "I tuoi schierati in una notte NBA [SQUADRA] [DATA]"),
        BotCommand("player",     "Un giocatore: squadra NBA e fantabasket, media, statistiche"),
        BotCommand("prestazione", "La notte di un giocatore: tabellino e fantapunti [nome] [data]"),
        BotCommand("giocatori",  "Cerca tra i giocatori: ruolo, squadra, FA, top per media… [filtri] (aiuto)"),
        BotCommand("status",     "Injury status dei giocatori di una squadra [SQUADRA]"),
        BotCommand("rendimento", "La stagione di un giocatore partita per partita [nome]"),
        BotCommand("rendimento_situazione", "Media in quintetto, panchina, tribuna e da free agent [nome] [periodo]"),
        BotCommand("rendimento_carriera", "La fantamedia stagione per stagione, anche dei giocatori storici [nome]"),
        BotCommand("confronto", "Due giocatori a confronto nella stagione: A vs B"),
        BotCommand("confronto_carriera", "Due carriere a confronto, anche storiche: A vs B"),
        BotCommand("partita", "Una sfida in dettaglio (immagine) [SQUADRA] [GN] o SQUADRA - SQUADRA; Q1, Q2 la Quasi Cup"),
        BotCommand("classifica", "La classifica (immagine)"),
        BotCommand("classifica_full", "La classifica con tutte le statistiche"),
        BotCommand("classifica_conference", "La classifica divisa per conference"),
        BotCommand("classifica_home_away", "La classifica in casa e in trasferta (due immagini)"),
        BotCommand("rendimento_team", "Il rendimento di una squadra giornata per giornata, panchina compresa"),
        BotCommand("quasi_cup", "La Quasi NBA Cup: qualificazione e tabellone (immagine)"),
        BotCommand("playoff", "Il tabellone dei playoff (prima dei playoff: se finisse oggi)"),
        BotCommand("lottery", "Le odds della lottery del draft (prima della fine: se finisse oggi)"),
        # v7.21.0 (Luca, 21/11): le viste del bot principale (vista.py); nei gruppi risponde loucabot
        BotCommand("roster",  "Roster di una squadra [SQUADRA] [DD-MM-YY]"),
        BotCommand("assets",  "Asset completi di una squadra [SQUADRA] [DD-MM-YY]"),
        BotCommand("pick", "Le pick in mano a una squadra [SQUADRA] [ANNO] [1|2]; con giro e anno la storia (aiuto)"),
        BotCommand("pick_lega", "Tutte le pick della lega in un'immagine [ANNO] [1|2]: con l'anno tutto un draft"),
        BotCommand("draft", "Il tabellone del draft: il primo giro, con 2 il secondo [ANNO] [1|2]"),
        BotCommand("prospetto_rinnovi", "I rinnovi della prossima offseason, stimati [SQUADRA]"),
        BotCommand("team_diff", "Variazioni di roster [SQUADRA] [da] [a]"),
        BotCommand("carriera", "Carriera di un giocatore: fantabasket e NBA [nome]"),
        BotCommand("trova_trade", "Una trade ufficiale: per numero o per giocatore"),
        BotCommand("penalita", "Le penalità della tua squadra, o di SQUADRA"),
        BotCommand("pdf_roster", "I roster di tutte le squadre in un PDF [DATA]"),
        BotCommand("pdf_assets", "Gli asset di tutte le squadre in un PDF [DATA]"),
    ]
    gm = gruppi + [
        BotCommand("guida",      "Guida per i GM"),
    ]
    admin = gm + [
        BotCommand("calendario_quando",  "Sorteggio del calendario con drand: GG/MM HH:MM (senza, lo stato)"),
        BotCommand("importa_date",       "Le date delle 38 giornate dopo il sorteggio (CSV allegato)"),
        BotCommand("importa_playoff",    "Importa le date dei playoff (CSV allegato)"),
        BotCommand("set_seed",           "Playoff: SQUADRA N, la squadra al seed N (prima del blocco)"),
        BotCommand("calendario_playoff", "Le giornate dei playoff: date, prima partita, squadre a media"),
        BotCommand("fantapunti",         "Fantapunti della giornata, giocatori a roster [N]"),
        BotCommand("set_valid_status",   "Status di un giocatore per il calcolo: GIOCATORE N"),
        BotCommand("ricalcola",          "Ricalcola la giornata N (riscarica solo le notti non congelate)"),
        BotCommand("calcola",            "Calcola subito la giornata [N], se le partite sono finite"),
        BotCommand("ricontrolla",        "Ricontrolla i tabellini di una notte aperta [GG/MM]"),
        BotCommand("storico_calcolo",    "Versioni calcolate della giornata N e cosa è cambiato"),
        BotCommand("tanking",            "Controllo tanking della giornata [N]: indizi nelle formazioni"),
        BotCommand("congelamento",       "Quali giornate si ricontrollano e quali sono congelate"),
        BotCommand("congelamento_notti", "Le notti: aperte (fino alle 20 del giorno dopo) o congelate"),
        BotCommand("congela",            "Congela tutte le notti della giornata N"),
        BotCommand("scongela",           "Riapre i tabellini della giornata N"),
        BotCommand("congela_notte",      "Congela la notte GG/MM: niente più riscarichi da ESPN"),
        BotCommand("scongela_notte",     "Riapre i tabellini della notte GG/MM"),
        BotCommand("controllo_notte",    "Rifà il controllo finale della notte GG/MM"),
        BotCommand("correggi_tabellino", "Corregge i fantapunti: GIOCATORE GN VALORE [GG/MM]"),
        BotCommand("update",             "Aggiorna subito i punteggi live sul canale"),
        BotCommand("calendario_check",   "Scadenze e squadre a media, confronto col calendario"),
        BotCommand("importa_calendario", "Importa il CSV del calendario (didascalia del file)"),
        BotCommand("nba_sync",           "Riscarica le partite NBA della stagione"),
        BotCommand("calendario_foglio",  "Aggiorna il foglio Google Calendario"),
        BotCommand("tabellini",          "Scarica i tabellini mancanti e snapshot infortunati"),
        BotCommand("espn_giocatori",     "Roster NBA da ESPN e abbinamento con l'anagrafica"),
        BotCommand("espn_mancanti",      "Giocatori a roster senza id ESPN"),
        BotCommand("espn_abbina",        "Abbina a mano [id_giocatore] [id_espn]"),
        BotCommand("guida_admin",        "Guida per gli admin"),
    ]
    dev = admin + [
        BotCommand("dev",         "Comandi dev"),
        BotCommand("guida_dev",   "Guida tecnica di loucabot"),
        BotCommand("dev_version", "Versione del bot"),
        BotCommand("job_status",  "Job programmati"),
        BotCommand("dev_giornata", "Stato di una giornata [N]"),
        BotCommand("dev_prova_calcolo", "Prova del calcolo: GG/MM/AAAA GG/MM/AAAA"),
        BotCommand("dev_prova_live",    "Prova del live su notti vere, anche preseason [GG/MM/AAAA …|stop]"),
        BotCommand("dev_ricalcola_fp",  "Fantapunti coi pesi di settings.json [STAGIONE]"),
        BotCommand("dev_log",     "Ultime righe di log [N]"),
        BotCommand("dev_pg",      "Connessione a PostgreSQL"),
        BotCommand("dev_foto",    "Foto ESPN dei giocatori a roster"),
        BotCommand("dev_live_frequenza", "Frequenza del live [MINUTI MINUTI_TARDI HH:MM]"),
        BotCommand("reboot",      "Riavvia il bot"),
    ]
    # v7.19.0 (Luca, 21/11): un ordine sensato per i GM; per admin e dev i loro comandi dopo, come prima
    from shared.ordine_comandi import ordina
    gm_ord = ordina(gm, ORDINE_GM)
    admin = gm_ord + [b for b in admin if b.command not in {x.command for x in gm}]
    dev = admin + [b for b in dev if b.command not in {x.command for x in admin}]
    return {"gruppi": ordina(gruppi, ORDINE_GM), "gm": gm_ord, "admin": admin, "dev": dev}


def comandi_pubblici() -> set[str]:
    """I comandi che passano nei gruppi diversi dal gruppo admin (shared/solo_gruppo_admin, Luca 31/10): quelli
    del menu dei GM (che comprende quelli dei gruppi)."""
    return {x.command for x in liste_comandi()["gm"]}


async def registra_comandi(bot) -> None:
    c = liste_comandi()
    try:
        await bot.set_my_commands(c["gruppi"], scope=BotCommandScopeAllGroupChats())
        # anche per gli amministratori di un gruppo (Luca, 30/10: diventato admin del gruppo della lega non vedeva più
        # /partita e /classifica); il gruppo admin ha il suo menu qui sotto
        await bot.set_my_commands(c["gruppi"], scope=BotCommandScopeAllChatAdministrators())
        await bot.set_my_commands(c["gm"], scope=BotCommandScopeDefault())
        await bot.set_my_commands(c["gm"], scope=BotCommandScopeAllPrivateChats())
        if config.gruppo_admin():
            try:
                await bot.set_my_commands(c["admin"], scope=BotCommandScopeChat(chat_id=config.gruppo_admin()))
            except Exception as e:       # il bot non è (ancora) nel gruppo admin
                logger.warning("Comandi nel gruppo admin: %s", e)
        dev = config.dev_id()
        for aid in config.admin_ids():
            if dev and aid == dev:
                continue
            try:
                await bot.set_my_commands(c["admin"], scope=BotCommandScopeChat(chat_id=aid))
            except Exception:
                pass                     # admin che non ha mai scritto al bot
        if dev:
            try:
                await bot.set_my_commands(c["dev"], scope=BotCommandScopeChat(chat_id=dev))
            except Exception:
                pass
        logger.info("Comandi registrati.")
    except Exception as e:
        logger.warning("Registrazione comandi fallita: %s", e)

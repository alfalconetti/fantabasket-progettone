"""
Comandi Telegram (menu "/" del client) di loucabot, per scope, come negli altri due bot:
gruppi → calendario e giornata; privato → in più la guida; admin (in privato e nel gruppo admin)
→ in più i comandi admin; dev → in più quelli dev. Si registrano all'avvio.
"""
import logging

from telegram import (BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats,
                      BotCommandScopeChat, BotCommandScopeDefault)

import config

logger = logging.getLogger(__name__)


def liste_comandi() -> dict:
    gruppi = [
        BotCommand("calendario", "La giornata tua o di una squadra [N] [SQUADRA]"),
        BotCommand("calendario_full", "Tutto il calendario di una squadra, coi risultati [SQUADRA]"),
        BotCommand("giornata",   "Tutte le partite di una giornata [N], coi risultati"),
        BotCommand("risultati",  "Come /giornata: i risultati di una giornata [N]"),
        BotCommand("live_results", "Il live della giornata in testo, completo [N]"),
        BotCommand("notte",      "I tuoi schierati in una notte NBA [SQUADRA] [DATA]"),
        BotCommand("player",     "Un giocatore: squadra NBA e fantabasket, media, statistiche"),
        BotCommand("partita", "Una sfida in dettaglio (immagine) [SQUADRA] [GN] o SQUADRA - SQUADRA"),
        BotCommand("classifica", "La classifica (immagine)"),
        BotCommand("classifica_full", "La classifica con tutte le statistiche"),
        BotCommand("classifica_conference", "La classifica divisa per conference"),
    ]
    gm = gruppi + [
        BotCommand("guida",      "Guida per i GM"),
    ]
    admin = gm + [
        BotCommand("fantapunti",         "Fantapunti della giornata, giocatori a roster [N]"),
        BotCommand("set_valid_status",   "Status di un giocatore per il calcolo: GIOCATORE N"),
        BotCommand("ricalcola",          "Ricalcola la giornata N (riscarica solo le notti non congelate)"),
        BotCommand("congelamento",       "Quali giornate si ricontrollano e quali sono congelate"),
        BotCommand("congelamento_notti", "Le notti: aperte (fino alle 20 del giorno dopo) o congelate"),
        BotCommand("congela",            "Congela tutte le notti della giornata N"),
        BotCommand("scongela",           "Riapre i tabellini della giornata N"),
        BotCommand("congela_notte",      "Congela la notte GG/MM: niente più riscarichi da ESPN"),
        BotCommand("scongela_notte",     "Riapre i tabellini della notte GG/MM"),
        BotCommand("controllo_notte",    "Rifà il controllo finale della notte GG/MM"),
        BotCommand("correggi_tabellino", "Corregge i fantapunti: GIOCATORE GN VALORE [GG/MM]"),
        BotCommand("live",               "Aggiorna subito i punteggi live sul canale"),
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
        BotCommand("reboot",      "Riavvia il bot"),
    ]
    return {"gruppi": gruppi, "gm": gm, "admin": admin, "dev": dev}


async def registra_comandi(bot) -> None:
    c = liste_comandi()
    try:
        await bot.set_my_commands(c["gruppi"], scope=BotCommandScopeAllGroupChats())
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

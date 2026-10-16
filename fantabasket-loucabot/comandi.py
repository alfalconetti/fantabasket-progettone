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
        BotCommand("calendario", "La tua giornata e le prossime [N]"),
        BotCommand("giornata",   "Tutte le partite di una giornata [N], coi risultati"),
        BotCommand("player",     "Un giocatore: squadra NBA e fantabasket, media, statistiche"),
        BotCommand("classifica", "La classifica (immagine)"),
        BotCommand("classifica_full", "La classifica con tutte le statistiche"),
    ]
    gm = gruppi + [
        BotCommand("guida",      "Guida per i GM"),
    ]
    admin = gm + [
        BotCommand("fantapunti",         "Fantapunti della giornata, giocatori a roster [N]"),
        BotCommand("set_valid_status",   "Status di un giocatore per il calcolo: GIOCATORE N"),
        BotCommand("ricalcola",          "Riscarica i tabellini e ricalcola la giornata N"),
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

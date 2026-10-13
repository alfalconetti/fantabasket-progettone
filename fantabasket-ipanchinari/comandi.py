"""
Comandi Telegram (menu "/" del client) di IPanchinari, per scope come negli altri bot:
privato → panchina, quintetto, guida; admin (in privato e nel gruppo admin) → in più i comandi
admin; dev → in più quelli dev. Nei gruppi il bot non ha comandi. Si registrano all'avvio.
"""
import logging

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat, BotCommandScopeDefault

import config

logger = logging.getLogger(__name__)


def liste_comandi() -> dict:
    gm = [
        BotCommand("panchina",  "La panchina che hai mandato (per cambiarla rimandala)"),
        BotCommand("build_panchina", "Componi la panchina coi bottoni"),
        BotCommand("quintetto", "Il tuo quintetto: cambialo o confermalo"),
        BotCommand("guida",     "Guida per i GM"),
    ]
    admin = gm + [
        BotCommand("stato",            "Conferme e panchine della giornata [N]"),
        BotCommand("quintetto_admin",  "Quintetto di una squadra: coi bottoni, o SQUADRA e sotto i 5"),
        BotCommand("quintetti_import", "Quintetti di tutte le squadre (testo o file)"),
        BotCommand("panchina_admin",   "Panchina di una squadra: coi bottoni, o SQUADRA e sotto le righe"),
        BotCommand("guida_admin",      "Guida per gli admin"),
    ]
    dev = admin + [
        BotCommand("dev",         "Comandi dev"),
        BotCommand("guida_dev",   "Guida tecnica"),
        BotCommand("dev_version", "Versione del bot"),
        BotCommand("job_status",  "Job programmati"),
        BotCommand("dev_promemoria", "Anteprima del promemoria [SQUADRA]"),
        BotCommand("dev_log",     "Ultime righe di log [N]"),
        BotCommand("dev_pg",      "Connessione a PostgreSQL"),
        BotCommand("reboot",      "Riavvia il bot"),
    ]
    return {"gm": gm, "admin": admin, "dev": dev}


async def registra_comandi(bot) -> None:
    c = liste_comandi()
    try:
        await bot.set_my_commands(c["gm"], scope=BotCommandScopeDefault())
        await bot.set_my_commands(c["gm"], scope=BotCommandScopeAllPrivateChats())
        if config.gruppo_admin():
            try:
                await bot.set_my_commands(c["admin"], scope=BotCommandScopeChat(chat_id=config.gruppo_admin()))
            except Exception as e:
                logger.warning("Comandi nel gruppo admin: %s", e)
        dev = config.dev_id()
        for aid in config.admin_ids():
            if dev and aid == dev:
                continue
            try:
                await bot.set_my_commands(c["admin"], scope=BotCommandScopeChat(chat_id=aid))
            except Exception:
                pass
        if dev:
            try:
                await bot.set_my_commands(c["dev"], scope=BotCommandScopeChat(chat_id=dev))
            except Exception:
                pass
        logger.info("Comandi registrati.")
    except Exception as e:
        logger.warning("Registrazione comandi fallita: %s", e)

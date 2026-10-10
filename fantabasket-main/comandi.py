"""
Comandi Telegram (menu "/" del client) filtrati per fase.

Le voci GM legate a una fase compaiono solo quando la fase le permette, con le
stesse costanti usate dai comandi e dal /menu: così il menu dei comandi di
Telegram non mostra azioni che il bot rifiuterebbe. Si registrano all'avvio e a
ogni cambio di fase (admin_panel._esegui_cambio_fase).
"""
import logging

from telegram import (BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats,
                      BotCommandScopeChat, BotCommandScopeDefault)

import settings
from settings import FASI_TRADE_APERTE

logger = logging.getLogger(__name__)


def _fasi_comando() -> dict:
    """comando → fasi in cui è disponibile (i comandi non elencati sono sempre visibili)."""
    from handlers.dpe import FASI_DPE
    return {
        "build_trade":         FASI_TRADE_APERTE,
        "import_trade":        FASI_TRADE_APERTE,
        "taglia":              FASI_TRADE_APERTE,
        "attiva_diritti":      FASI_TRADE_APERTE,
        "decadimento":         FASI_TRADE_APERTE,
        "dpe":                 set(FASI_DPE),
        "dichiarazione_ruoli": {"offseason-ruoli"},
        "cambio_ruolo":        settings.FASI_RUOLI_RS,
    }


def liste_comandi(fase: str) -> dict:
    """Le liste per scope, già filtrate sulla fase."""
    cmd_group = [
        BotCommand("roster",  "Roster squadra [team_id] [DD-MM-YY]"),
        BotCommand("assets",  "Asset completi squadra [team_id]"),
    ]
    cmd_base = cmd_group + [
        BotCommand("menu",           "Menu principale"),
    ]
    cmd_gm = cmd_base + [
        BotCommand("build_trade",    "Costruisci una trade"),
        BotCommand("import_trade",   "Importa trade da testo"),
        BotCommand("bozze_trade",    "Le tue bozze di trade"),
        BotCommand("my_trades",      "Tutte le tue trade e che fine hanno fatto"),
        BotCommand("edit_trade",     "Modifica una bozza [numero]"),
        BotCommand("taglia",         "Taglia un giocatore"),
        BotCommand("dpe",            "Richiedi Disabled Player Exception"),
        BotCommand("attiva_diritti", "Attiva diritti 2nd pick"),
        BotCommand("dichiarazione_ruoli", "Dichiara i ruoli (fase dichiarazione ruoli)"),
        BotCommand("cambio_ruolo", "Cambio ruolo (regular season e playoff)"),
        BotCommand("decadimento",    "Segnala contratto decaduto (ritiro, altra lega)"),
        BotCommand("my_team",        "Info e impostazioni del tuo team"),
        BotCommand("palette",        "Personalizza colori roster/assets"),
        BotCommand("team_diff",      "Variazioni roster [team_id] [da] [a]"),
        BotCommand("annulla_trade",  "Annulla la trade in corso"),
        BotCommand("annulla",        "Esci da qualsiasi conversazione bloccata"),
        BotCommand("guida",          "Guida completa per i GM"),
    ]
    cmd_admin = cmd_gm + [
        BotCommand("admin_menu",          "Pannello admin"),
        BotCommand("set_fase",            "Cambia fase della stagione"),
        BotCommand("approva_trade",       "Approva una trade in attesa"),
        BotCommand("annulla_trade_admin", "Annulla una trade approvata"),
        BotCommand("registra_firma",      "Registra firma manuale [team] [giocatore] [importo] [anni]"),
        BotCommand("annulla_admin",       "Esci da operazione admin bloccata"),
        BotCommand("guida_admin",         "Guida completa per gli admin"),
        BotCommand("settings",            "Modifica settings [chiave] [valore]"),
        BotCommand("import_posizioni_eleggibili", "Importa posizioni eleggibili Yahoo (CSV)"),
        BotCommand("set_posizioni_eleggibili",    "Correggi posizioni di un giocatore [nome] [PG,SG]"),
        BotCommand("deadline_ruoli",              "Deadline dichiarazione ruoli [AAAA-MM-GG] [HH:MM]"),
        BotCommand("data_erminio",                "Data aggiunta posizione su Yahoo [nome] [AAAA-MM-GG]"),
    ]
    cmd_dev = cmd_admin + [
        BotCommand("dev",          "Lista comandi dev"),
        BotCommand("dev_version",  "Versione bot"),
        BotCommand("dev_log",      "Ultime N righe log [N]"),
        BotCommand("dev_trade",    "Ultime N trade approvate [N]"),
        BotCommand("dev_pg",       "Stato connessione PostgreSQL"),
        BotCommand("dev_roster",   "Dump roster raw [team_id]"),
        BotCommand("dev_player",   "Anagrafica giocatore [nome]"),
        BotCommand("job_status",   "Job attivi nella JobQueue"),
        BotCommand("broadcast",    "Messaggio a tutti i GM"),
        BotCommand("sync_sheets",  "Sync manuale roster su Google Sheets"),
        BotCommand("backup",       "Backup manuale al canale log"),
        BotCommand("reboot",       "Riavvia il bot"),
    ]


    fasi = _fasi_comando()
    def _filtra(cmds):
        return [c for c in cmds if c.command not in fasi or fase in fasi[c.command]]
    return {"group": cmd_group, "base": cmd_base, "gm": _filtra(cmd_gm),
            "admin": _filtra(cmd_admin), "dev": _filtra(cmd_dev)}


async def registra_comandi(bot) -> None:
    g              = settings.load_globals()
    admin_ids      = g.get("admin_ids", [])
    dev_id         = g.get("dev_id")
    admin_group_id = g.get("admin_group_id")
    c = liste_comandi(settings.fase())
    try:
        await bot.set_my_commands(c["group"], scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands(c["base"],  scope=BotCommandScopeDefault())
        await bot.set_my_commands(c["gm"],    scope=BotCommandScopeAllPrivateChats())
        if admin_group_id:
            await bot.set_my_commands(c["admin"], scope=BotCommandScopeChat(chat_id=admin_group_id))
        for aid in admin_ids:
            if dev_id and int(aid) == int(dev_id):
                continue
            try:
                await bot.set_my_commands(c["admin"], scope=BotCommandScopeChat(chat_id=aid))
            except Exception:
                pass
        if dev_id:
            try:
                await bot.set_my_commands(c["dev"], scope=BotCommandScopeChat(chat_id=dev_id))
            except Exception:
                pass
        logger.info("Comandi registrati per la fase %s.", settings.fase())
    except Exception as e:
        logger.warning("Registrazione comandi fallita: %s", e)

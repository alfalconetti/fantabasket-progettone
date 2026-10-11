"""
Menu dei comandi del bot aste (il "/" di Telegram), per ruolo e per fase (v53).

Scope: chat private (GM), ogni admin, il dev, gruppi (solo comandi pubblici).
Fase: la cambia il bot principale nel globals.json condiviso, quindi il bot aste la
controlla ogni 5 minuti (job_aggiorna_comandi) e ri-registra il menu solo se cambia
qualcosa tra fase, mercato FA aperto e presenza di aste aperte.
"""
import logging

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats, BotCommandScopeChat

import database as db
import utils

logger = logging.getLogger(__name__)

_ultimo_stato = None


def _stato() -> tuple:
    g = utils.load_globals()
    fase = g.get("fase", "")
    mercato_fa = bool(g.get("mercato_aperto", False))
    # si può offrire: FA aperta, fase RFA, o aste ancora aperte (es. iniziate prima della deadline)
    offerte = mercato_fa or fase == "offseason-rfa" or bool(db.get_aste_aperte())
    return fase, mercato_fa, offerte


def liste_comandi(fase: str, mercato_fa: bool, offerte: bool) -> dict:
    gm = [BotCommand("me", "Il tuo cap e i tuoi slot"),
          BotCommand("team", "Cap e slot di una squadra: /team <id>")]
    if mercato_fa:
        gm += [BotCommand("lista_fa", "Free agent disponibili"),
               BotCommand("nuova_fa", "Apri l'asta per un FA: /nuova_fa <giocatore>")]
    if offerte:
        gm += [BotCommand("offri", "Aste aperte, con il bottone per offrire"),
               BotCommand("offerta", "Offerta diretta: /offerta asta <id> <importo>"),
               BotCommand("watch", "Segui un'asta"),
               BotCommand("autocap", "Cap anticipato (emergenza notturna)"),
               BotCommand("autoslot", "Slot anticipato (emergenza notturna)")]
    gm += [BotCommand("watched", "Aste che segui"),
           BotCommand("guida", "Guida al bot aste"),
           BotCommand("annulla", "Annulla l'operazione in corso")]

    admin = list(gm) + [
        BotCommand("list", "Squadre: nome, id e GM"),
        BotCommand("listteams", "Cap e slot di tutte le squadre"),
        BotCommand("aste", "Aste in corso"),
        BotCommand("all_aste", "Tutte le aste, anche chiuse"),
        BotCommand("firme", "Firme recenti"),
    ]
    if mercato_fa:
        admin.append(BotCommand("apri_asta", "Apri un'asta FA per conto di una squadra"))
    if offerte:
        admin.append(BotCommand("crea_offerta", "Offerta per conto di una squadra"))
    if fase.startswith("offseason"):
        admin.append(BotCommand("nuova_rfa", "Apri un'asta RFA"))
    admin += [
        BotCommand("chiudi_asta", "Chiudi un'asta"),
        BotCommand("annulla_asta", "Annulla un'asta"),
        BotCommand("annulla_offerta", "Annulla l'ultima offerta di un'asta"),
        BotCommand("riapri_asta", "Riapri un'asta chiusa o annullata"),
        BotCommand("estendi_asta", "Sposta in avanti la scadenza di N ore"),
        BotCommand("stato_asta", "Tutti i dati di un'asta"),
        BotCommand("ripubblica_asta", "Ripubblica il messaggio di un'asta"),
        BotCommand("set_cap_penalizzato", "Penalità cap: /set_cap_penalizzato <id> <valore>"),
        BotCommand("chiudi_mercato" if mercato_fa else "apri_mercato",
                   "Chiudi il mercato FA (emergenza)" if mercato_fa else "Apri il mercato FA (emergenza)"),
        BotCommand("admin", "Elenco comandi admin"),
        BotCommand("guida_admin", "Guida admin"),
        BotCommand("backup_ora", "Backup d'emergenza del solo DB aste"),
    ]
    dev = list(admin) + [
        BotCommand("dev", "Comandi dev"),
        BotCommand("dev_version", "Versione"),
        BotCommand("dev_aste_stato", "Stato interno delle aste"),
        BotCommand("dev_cap", "Cap di tutte le squadre"),
        BotCommand("dev_rfa", "Stato RFA"),
        BotCommand("dev_firme", "Log firme dettagliato"),
        BotCommand("dev_watched", "Watchlist globale"),
        BotCommand("dev_log", "Log recenti"),
        BotCommand("job_status", "Job schedulati"),
        BotCommand("broadcast", "Messaggio a tutti i GM"),
        BotCommand("reboot", "Riavvia il bot aste"),
    ]
    gruppi = [BotCommand("team", "Cap e slot di una squadra: /team <id>"),
              BotCommand("listteams", "Cap e slot di tutte le squadre")]
    return {"gm": gm, "admin": admin, "dev": dev, "gruppi": gruppi}


async def registra_comandi(bot, forza: bool = False) -> None:
    global _ultimo_stato
    stato = _stato()
    if stato == _ultimo_stato and not forza:
        return
    liste = liste_comandi(*stato)
    g = utils.load_globals()
    try:
        await bot.set_my_commands(liste["gm"], scope=BotCommandScopeAllPrivateChats())
        await bot.set_my_commands(liste["gruppi"], scope=BotCommandScopeAllGroupChats())
        dev_id = g.get("dev_id")
        for aid in g.get("admin_ids", []):
            if dev_id and int(aid) == int(dev_id):
                continue
            try:
                await bot.set_my_commands(liste["admin"], scope=BotCommandScopeChat(chat_id=int(aid)))
            except Exception as e:
                logger.warning("Comandi admin %s: %s", aid, e)
        if dev_id:
            await bot.set_my_commands(liste["dev"], scope=BotCommandScopeChat(chat_id=int(dev_id)))
        _ultimo_stato = stato
        logger.info("Comandi bot aste registrati (fase=%s, FA=%s, offerte=%s).", *stato)
    except Exception as e:
        logger.warning("Registrazione comandi aste fallita: %s", e)


async def job_aggiorna_comandi(context) -> None:
    await registra_comandi(context.bot)

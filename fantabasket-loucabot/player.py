"""
/player GIOCATORE (tutti, v5.4.0): la scheda di un giocatore. Dalla v7.3.0 (Luca, 09/11) il codice sta in
shared/giocatore.py, perché /player c'è anche nel bot principale (in privato; nei gruppi risponde loucabot).
Qui restano i nomi di sempre per il resto di loucabot, per klra (che sostituisce `scheda` per aggiungere il
sistema) e per le prove.
"""
from telegram.ext import CallbackQueryHandler, CommandHandler

import calcolo  # noqa: F401  — usato da congelamento (player.calcolo.norm)
import db  # noqa: F401  — le prove sostituiscono db.q
from shared import giocatore as G
from shared.elenco_giocatori import cmd_giocatori
from shared.giocatore import (ANNO_BOT, FONTE, GIORNI, NOTA_FIRMA, NOTA_FIRMA_FINO_AL, TIPI, ULTIME_MEDIA,  # noqa: F401
                              anno_prima, cerca, e, eta, immagine, partite_squadra, prossima_partita,
                              scadenza_diritti, testo_su, ultime)


def scheda(gid: int) -> str:
    return G.scheda(gid)


def _foto(gid: int) -> str | None:
    import foto                                      # la cartella delle foto di loucabot (FOTO_DIR)
    g = db.q("SELECT espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    return foto.percorso(g["espn_id"]) if g and g.get("espn_id") else None


def extra(gid: int) -> str:
    """Testo da mandare sotto l'immagine di /player (v7.7.0): qui niente; klra lo sostituisce con la stagione
    col sistema attivo."""
    return ""


# la scheda (testo, se l'immagine non viene), la foto e il testo in più si cercano qui a ogni chiamata: klra li sostituisce
cmd_player, manda, cb_player = G.handlers(lambda gid: scheda(gid), lambda gid: _foto(gid), extra_di=lambda gid: extra(gid))


def get_handlers() -> list:
    return [CommandHandler("player", cmd_player), CallbackQueryHandler(cb_player, pattern=r"^pl:\d+$"),
            CommandHandler("giocatori", cmd_giocatori)]                    # v7.5.0: shared/elenco_giocatori.py

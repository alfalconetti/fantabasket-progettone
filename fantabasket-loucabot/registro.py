"""
Registro delle azioni da loucabot (v6.0.0 del bot principale): stesso registro unico degli altri bot
(`shared/azioni.py`, tabella registro_azioni nel database condiviso), si consulta con /registro sul
bot principale.

Qui le azioni da admin avevano già la loro riga sul canale log, col nome di chi: quella resta com'è
e il registro si aggiunge con segna_sync (niente doppioni sul canale). segna() (registro + riga nel
formato unico sul canale log) è per le azioni che sul log non lasciavano niente.
"""
import config
import db
from shared import azioni as A


async def segna(bot, user, veste: str, azione: str, **campi) -> dict | None:
    """Registro e, se admin o dev, la riga sul canale log di loucabot. Non solleva mai."""
    try:
        chat = config.canale_log()
    except Exception:
        chat = None
    return await A.azione(db.q, bot, chat, "louca", user, veste, azione, nomi_squadre=config.nome, **campi)


def segna_sync(user, veste: str, azione: str, **campi) -> dict | None:
    """Solo il registro. Non solleva mai."""
    return A.registra(db.q, "louca", user, veste, azione, **campi)

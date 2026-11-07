"""
Avviso al GM quando un admin che non è GM di quella squadra le cambia quintetto, formazione o panchina
(v7.1.0, Luca 05/11). In privato a tutti i gm_ids della squadra, tranne chi ha fatto la modifica. Se il GM non ha mai
avviato il bot Telegram rifiuta: si scrive nel log e si va avanti.
"""
import html
import logging

import config

logger = logging.getLogger(__name__)


def e(x) -> str:
    return html.escape(str(x), quote=False)


def destinatari(team_id: str, chi_id: int) -> list[int]:
    """I GM da avvisare: nessuno se chi ha modificato è GM di quella squadra."""
    gm = [int(x) for x in config.gm_ids(team_id)]
    return [] if int(chi_id) in gm else gm


async def avvisa(bot, team_id: str, user, cosa: str, dettaglio: str = "") -> int:
    """cosa: frase dopo «ha …» (es. «cambiato il quintetto»); dettaglio: righe in più (prima → dopo). → avvisati."""
    nome = getattr(user, "full_name", None) or "un admin"
    testo = (f"✏️ <b>{e(nome)}</b> (admin) ha {cosa} di <b>{e(config.nome(team_id))}</b>."
             + (f"\n{dettaglio}" if dettaglio else "")
             + "\n\n<i>Se qualcosa non torna, scrivi a un admin. Lo vedi anche con /quintetto e /panchina.</i>")
    n = 0
    for uid in destinatari(team_id, user.id):
        try:
            await bot.send_message(chat_id=uid, text=testo, parse_mode="HTML")
            n += 1
        except Exception as err:
            logger.info("Avviso modifica admin al GM %s non mandato: %s", uid, err)
    return n

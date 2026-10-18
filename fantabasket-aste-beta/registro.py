"""
Registro delle azioni dal bot aste (v6.0.0 del bot principale, aste v68): stesso registro unico
degli altri bot (`shared/azioni.py`, tabella registro_azioni nel database condiviso), si consulta
con /registro sul bot principale. Le azioni da admin e da dev vanno anche sul canale log del bot
aste (log_channel_id), nel formato unico; quelle dei GM e dei job solo nel registro.
"""
import pg_client
import teams as tm
import utils
from shared import azioni as A


def _nome(team_id: str) -> str:
    t = tm.get_team_by_id(team_id)
    return t["nome"] if t else team_id


async def segna(bot, user, veste: str, azione: str, **campi) -> dict | None:
    """Registro (e, se admin o dev, la riga sul canale log del bot aste). Non solleva mai: senza
    PostgreSQL la riga sul log arriva lo stesso."""
    try:
        chat = utils.get_log_channel_id()
    except Exception:
        chat = None
    return await A.azione(pg_client.q, bot, chat, "aste", user, veste, azione, nomi_squadre=_nome, **campi)


def segna_sync(user, veste: str, azione: str, **campi) -> dict | None:
    """Solo il registro (funzioni non async, job senza bot). Non solleva mai."""
    return A.registra(pg_client.q, "aste", user, veste, azione, **campi)


def _gid(nome: str) -> int | None:
    """Id del giocatore dal nome dell'asta (le aste hanno solo il nome). None se non univoco."""
    try:
        from utils import normalizza
        r = pg_client.q("SELECT id FROM giocatori WHERE nome_common = %s OR nome_norm = %s",
                        (nome, normalizza(nome)), many=True) or []
        return r[0]["id"] if len(r) == 1 else None
    except Exception:
        return None


def campi_asta(asta, *squadre_extra) -> dict:
    """squadre (chi ha l'offerta, il proprietario RFA, altre), giocatore e oggetto di un'asta
    (riga sqlite3.Row o dict)."""
    a = dict(asta)
    sq = [s for s in (a.get("offerente_team_id"), a.get("squadra_proprietaria"), *squadre_extra) if s]
    return {"squadre": list(dict.fromkeys(sq)), "giocatore_id": a.get("giocatore_id") or _gid(a.get("giocatore") or ""),
            "oggetto": f"{a.get('giocatore')} (asta {a.get('tipo')} #{a.get('id')})",
            "dettagli": {"asta_id": a.get("id")}}


async def segna_asta(bot, user, veste: str, azione: str, asta: dict, *squadre_extra, **campi) -> dict | None:
    """segna() per un'asta: squadre coinvolte, giocatore e oggetto dall'asta. Non solleva mai."""
    try:
        base = campi_asta(asta, *squadre_extra)
    except Exception as err:
        import logging
        logging.getLogger(__name__).warning("Registro, dati dell'asta: %s", err)
        base = {"oggetto": str(azione)}
    base.update(campi)
    return await segna(bot, user, veste, azione, **base)

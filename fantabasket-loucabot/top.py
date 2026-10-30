"""
Top 20 della notte (Luca, 30/10): alle 9 (orari.top_notte) nel gruppo della lega (globals.gruppo_lega_id).

- La classifica: i 20 migliori fantapunti della notte NBA appena passata tra i giocatori **schierati** nella
  giornata (quintetto e panchina, anche i panchinari non entrati nel calcolo), con partita, squadra del fanta
  e titolare o panchina.
- Sotto, «Prestazioni notevoli di giocatori firmati non schierati»: chi, tra tutti i giocatori sotto
  contratto, sarebbe nella top 20 ma non era schierato (con la squadra che l'ha lasciato fuori). Se nessuno,
  la sezione non c'è.
- Fantapunti dai tabellini di ESPN (fonte: site.api.espn.com), come il calcolo: contano solo le partite in
  cui è entrato (calcolo.conta). Alle 9 non sono ancora ricontrollati (11:05 e controllo finale delle 20):
  lo dice in fondo.
- Senza gruppo_lega_id non pubblica (riga nel log). La notte fuori da una giornata (pausa) si salta.
"""
import html
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import calcolo as CA
import config
import db
from numeri import testo as tp

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
QUANTI = 20


def e(x) -> str:
    return html.escape(str(x), quote=False)


def schierati(s: str, g: dict) -> dict[int, tuple[str, str]]:
    """giocatore_id → (squadra del fanta, "titolare" | "panchina") nella giornata."""
    import notte
    out = {}
    for sq in config.squadre():
        quintetto, panchina, _ = notte.schieramento(s, sq["id"], g)
        for gid in (panchina or []):
            gid = gid.get("giocatore_id") if isinstance(gid, dict) else gid
            if gid:
                out[int(gid)] = (sq["id"], "panchina")
        for gid in (quintetto or {}).values():
            if gid:
                out[int(gid)] = (sq["id"], "titolare")
    return out


def righe_notte(d: date) -> list[dict]:
    """Le prestazioni della notte dei giocatori sotto contratto (una per giocatore: la migliore)."""
    righe = db.q("""SELECT t.atleta, t.nome, t.squadra, t.fp, t.minuti, t.giocato, gi.id AS giocatore_id,
                           c.team_id, p.casa, p.trasferta
                    FROM nba_tabellini t
                    JOIN nba_partite p ON p.espn_id = t.partita
                    JOIN giocatori gi ON gi.espn_id = t.atleta
                    JOIN contratti c ON c.giocatore_id = gi.id AND c.attivo
                    WHERE p.data_et = %s AND p.tipo = ANY(%s)""", (d, [2, 3, 5]), many=True) or []
    per = {}
    for r in righe:
        if CA.conta(r) and (r["atleta"] not in per or float(r["fp"]) > float(per[r["atleta"]]["fp"])):
            per[r["atleta"]] = r
    return sorted(per.values(), key=lambda r: (-float(r["fp"]), r["nome"]))


def _partita(r: dict) -> str:
    if r["squadra"] == r["casa"]:
        return f"{r['casa']} vs {r['trasferta']}"
    return f"{r['trasferta']} @ {r['casa']}"


def testo(s: str, d: date) -> str | None:
    """Il messaggio, o None se la notte non è in una giornata o nessuno schierato ha giocato."""
    import notte
    g = notte.giornata_della_notte(s, d)
    if not g:
        return None
    sch = schierati(s, g)
    tutte = righe_notte(d)
    nostri = [r for r in tutte if r["giocatore_id"] in sch][:QUANTI]
    if not nostri:
        return None
    out = [f"🌙 <b>Top {QUANTI} della notte</b> · {d:%d/%m} (G{g['numero']})", ""]
    for i, r in enumerate(nostri, 1):
        team, come = sch[r["giocatore_id"]]
        out.append(f"{i}. <b>{e(r['nome'])}</b> {tp(float(r['fp']))} · {_partita(r)} · {e(config.nome(team))}"
                   + (" <i>(panchina)</i>" if come == "panchina" else ""))
    fuori = [r for r in tutte[:QUANTI] if r["giocatore_id"] not in sch]
    if fuori:
        out += ["", "👀 <b>Prestazioni notevoli di giocatori firmati non schierati</b>"]
        for r in fuori:
            out.append(f"• {e(r['nome'])} {tp(float(r['fp']))} · {_partita(r)} · {e(config.nome(r['team_id']))}")
    out += ["", "<i>Fantapunti dai tabellini di ESPN, non ancora ricontrollati (11:05 e controllo finale delle 20): "
                "possono cambiare.</i>"]
    return "\n".join(out)


def ieri() -> date:
    """La notte appena passata: il giorno prima di oggi a Roma (il job gira alle 9)."""
    return datetime.now(ROMA).date() - timedelta(days=1)


async def job_top_notte(context):
    """9:00 (orari.top_notte): scarica i tabellini mancanti della notte e pubblica la top 20 nel gruppo della lega."""
    from handlers import log
    import nba
    d = ieri()
    s = config.stagione()
    gruppo = config.globali().get("gruppo_lega_id")
    try:
        mancanti = db.partite_senza_tabellino(fino=d, dal=d)
        if mancanti:
            await nba.scarica_tabellini(mancanti)
        t = testo(s, d)
    except Exception as err:
        logger.exception("Top della notte %s", d)
        await log(context.bot, f"⚠️ Top {QUANTI} della notte del {d:%d/%m} non riuscita ({e(str(err))[:200]})")
        return
    if not t:
        return
    if not gruppo:
        logger.info("Top della notte %s: gruppo_lega_id non impostato in globals.json, non pubblico", d)
        return
    try:
        await context.bot.send_message(int(gruppo), t, parse_mode="HTML")
    except Exception as err:
        logger.warning("Top della notte %s: invio non riuscito: %s", d, err)
        await log(context.bot, f"⚠️ Top {QUANTI} della notte del {d:%d/%m}: invio al gruppo non riuscito ({e(str(err))[:200]})")

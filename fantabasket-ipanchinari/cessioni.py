"""
Cessioni: un giocatore che esce dalla squadra (trade o taglio nel bot principale) mentre è nel
quintetto del bot o in una panchina mandata. Ogni pochi minuti il job confronta quintetto,
panchina della prossima giornata e formazione e panchina della giornata in corso con la rosa di
oggi; per ogni giocatore che non c'è più avvisa i GM della squadra e il canale log, una volta
sola (tabella ipa_cessioni; se il giocatore torna in squadra il ricordo si cancella).

Il quintetto non va per forza aggiornato (fa fede Yahoo, è un favore agli admin); la panchina
della prossima giornata invece va rimandata con 5 giocatori della squadra. Per la giornata in
corso decidono gli admin.
"""
import logging

from telegram.ext import ContextTypes

import config
import db
from comune import FAVORE, e, giornata_in_corso, log, ora, prossima_giornata

logger = logging.getLogger(__name__)


def trova(team_id: str, stagione: str, g: dict | None, in_corso: dict | None) -> list[tuple[int, str, str]]:
    """[(giocatore, chiave, dove)] dei giocatori non più in squadra e ancora schierati."""
    rosa = {x["id"] for x in db.roster(team_id, stagione)}
    out = []
    for ruolo, gid in db.quintetto(team_id).items():
        if gid not in rosa:
            out.append((gid, "quintetto", f"nel quintetto del bot ({ruolo}): se vuoi aggiornalo con /quintetto ({FAVORE})"))
    if g:
        p = db.panchina(stagione, g["numero"], team_id)
        for r in (p["righe"] if p else []):
            if r["giocatore_id"] not in rosa:
                out.append((r["giocatore_id"], f"panchina G{g['numero']}",
                            f"nella panchina della giornata {g['numero']}: rimandala con 5 giocatori della tua squadra "
                            f"entro {ora(g['prima_partita'])}"))
    if in_corso and db.stato_giornata(stagione, in_corso["numero"])["chiusa"]:
        n = in_corso["numero"]
        for ruolo, gid in db.formazione(stagione, n, team_id).items():
            if gid and gid not in rosa:
                out.append((gid, f"formazione G{n}", f"nel quintetto della giornata {n} in corso ({ruolo}): ne tiene conto un admin"))
        p = db.panchina(stagione, n, team_id)
        for r in (p["righe"] if p else []):
            if r["giocatore_id"] not in rosa:
                out.append((r["giocatore_id"], f"panchina G{n}", f"nella panchina della giornata {n} in corso: ne tiene conto un admin"))
    return out


async def controlla(bot) -> int:
    """Avvisi nuovi mandati (uno per giocatore e squadra)."""
    s = config.stagione()
    g, in_corso = prossima_giornata(s), giornata_in_corso(s)
    mandati = 0
    for t in config.squadre():
        rosa = {x["id"] for x in db.roster(t["id"], s)}
        gia = db.cessioni_avvisate(t["id"])
        db.dimentica_cessioni(t["id"], [gid for gid, _ in gia if gid in rosa])
        gia = {x for x in gia if x[0] not in rosa}
        nuovi: dict[int, list[tuple[str, str]]] = {}
        for gid, chiave, dove in trova(t["id"], s, g, in_corso):
            if (gid, chiave) not in gia:
                nuovi.setdefault(gid, []).append((chiave, dove))
        if not nuovi:
            continue
        nomi = db.nomi_giocatori(list(nuovi))
        for gid, dove in nuovi.items():
            dest = db.squadra_attuale(gid)
            dove_va = f"ora è di <b>{e(config.nome(dest))}</b>" if dest else "non ha più un contratto"
            nome = e(nomi.get(gid, str(gid)))
            testo = (f"🔁 <b>{nome}</b> non è più nella tua squadra ({dove_va}) ed era:\n"
                     + "\n".join(f"• {e(d)}" for _, d in dove))
            for uid in config.gm_ids(t["id"]):
                try:
                    await bot.send_message(chat_id=uid, text=testo, parse_mode="HTML")
                except Exception as err:                  # GM che non ha mai scritto al bot
                    logger.info("Avviso cessione a %s: %s", uid, err)
            await log(bot, f"🔁 Cessione: {nome} ({e(t['nome'])} → {e(config.nome(dest)) if dest else 'svincolato'}) "
                           f"era schierato: " + ", ".join(e(c) for c, _ in dove))
            for chiave, _ in dove:
                db.segna_cessione(t["id"], gid, chiave)
            mandati += 1
    return mandati


async def job_cessioni(context: ContextTypes.DEFAULT_TYPE):
    try:
        await controlla(context.bot)
    except Exception as err:
        logger.exception("Controllo cessioni: %s", err)
        await log(context.bot, f"⚠️ Controllo cessioni: {e(repr(err))}")

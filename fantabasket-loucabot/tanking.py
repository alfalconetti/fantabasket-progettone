"""
Controllo del tanking, parte 1 (Luca, 25/10 e 30/10): alle 11 del mattino dopo la prima notte di ogni giornata
(orari.controllo_tanking) un report **solo al gruppo admin** con gli indizi di formazioni che sembrano fatte per
perdere. Indizi, non verdetti: decidono gli admin (minutaggi, rientri, riposi sono scelte legittime).

Per ogni squadra, dalla formazione congelata (ipa_formazioni) e dalla panchina (ipa_panchine):
- posto del quintetto vuoto; panchina non mandata;
- titolare indisponibile (stato dell'injury report diverso da Probable, o deciso da un admin) mentre in rosa c'è
  un giocatore sano che può giocare quel posto e ha partite nella giornata;
- titolare sano ma con fantamedia nettamente più bassa di un escluso che può giocare quel posto (posizioni
  eleggibili di Yahoo), sano e con partite nella giornata: almeno SOGLIA_PUNTI (8) di media in più **oppure**
  SOGLIA_PERC (+30%). Un titolare senza partite prende la sua media (non è un indizio, salvo se indisponibile).
- Medie: fantapunti della stagione prima della giornata (db.medie_stagione, come il calcolo). Stato: quello che il
  GM sapeva quando ha schierato, cioè l'injury report alla scadenza (l'ultimo prima della prima partita della
  giornata: db.infortuni del primo giorno). Diverso apposta dalla FADD, che guarda l'ultimo prima della partita del
  giocatore, e senza gli status decisi dagli admin (Luca, 31/10): un Out dell'ultimo minuto, dopo la scadenza, non
  è un indizio di tanking.
- Se l'escluso adesso ha un altro ruolo (ruolo_attuale) lo dice: per metterlo lì servirebbe un cambio ruolo, che
  non si vuole imporre subito (Luca, 31/10).
- Le squadre nell'ultimo terzo della classifica sono segnate ⬇️ (lì il tanking conviene).
La parte 2 (a consuntivo dopo la convalida: efficienza rispetto alla formazione migliore, storico) è da fare.
"""
import html
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config
import db
from numeri import testo as tp

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
RUOLI = ["PG", "SG", "SF", "PF", "C"]
SOGLIA_PUNTI = 8.0
SOGLIA_PERC = 0.30
SANI = (None, "Probable")
EMOJI = {"Out": "🔴", "Doubtful": "🟠", "Questionable": "🟡", "Day-To-Day": "🟡"}


def e(x) -> str:
    return html.escape(str(x), quote=False)


def nettamente_meglio(escluso: float, titolare: float) -> bool:
    """+8 di media oppure +30% (Luca, 30/10)."""
    return escluso - titolare >= SOGLIA_PUNTI or (titolare > 0 and escluso >= titolare * (1 + SOGLIA_PERC))


def _posizioni(gids: list[int]) -> dict[int, set]:
    righe = db.q("SELECT giocatore_id, posizioni FROM posizioni_attuali WHERE giocatore_id = ANY(%s)", (list(gids),), many=True) or []
    return {r["giocatore_id"]: {p.strip() for p in (r["posizioni"] or "").split(",") if p.strip()} for r in righe}


def dati(s: str, g: dict) -> dict:
    """Tutto quello che serve, per squadra: {team: {quintetto, panchina, giocatori: {gid: info}}}."""
    import risultati as R
    sch = R.schieramenti(s, g["numero"])
    rose = {}
    for r in db.q("""SELECT c.team_id, g.id, g.nome_common, g.espn_id FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                     WHERE c.attivo""", many=True) or []:
        rose.setdefault(r["team_id"], {})[r["id"]] = {"gid": r["id"], "nome": r["nome_common"], "atleta": r["espn_id"]}
    tutti = {gid: x for rosa in rose.values() for gid, x in rosa.items()}
    atleti = [x["atleta"] for x in tutti.values() if x["atleta"]]
    medie = db.medie_stagione(atleti, s, g["dal"])
    squadra = {**db.ultima_squadra(atleti, g["dal"]), **db.squadre_roster(atleti)}
    partite = {}
    for p in db.partite_nba(g["dal"], g["al"]):
        if p["stato"] not in ("STATUS_POSTPONED", "STATUS_CANCELED"):
            for sq in (p["casa"], p["trasferta"]):
                partite[sq] = partite.get(sq, 0) + 1
    stato = {a: st for (a, d), st in db.infortuni(atleti, [g["dal"]]).items()}   # alla scadenza (vedi sopra)
    pos = _posizioni(list(tutti))
    ruoli = {r["giocatore_id"]: r["ruolo"] for r in (db.q("SELECT giocatore_id, ruolo FROM ruolo_attuale WHERE stagione = %s "
                                                          "AND giocatore_id = ANY(%s)", (s, list(tutti)), many=True) or [])}
    for gid, x in tutti.items():
        a = x["atleta"]
        x.update(media=(medie.get(a) or {}).get("media"), partite=partite.get(squadra.get(a), 0) if a else 0,
                 stato=stato.get(a), posizioni=pos.get(gid, set()), ruolo=ruoli.get(gid))
    return {t["id"]: {"quintetto": (sch.get(t["id"]) or {}).get("quintetto") or {},
                      "panchina": (sch.get(t["id"]) or {}).get("panchina"),
                      "giocatori": rose.get(t["id"], {})} for t in config.squadre()}


def _cambio(x: dict, ruolo: str) -> str:
    """Se l'escluso adesso ha un altro ruolo: per metterlo lì servirebbe un cambio ruolo, che non si vuole imporre
    subito (Luca, 31/10). Si segnala, l'indizio pesa meno."""
    return f" <i>(ora è {x['ruolo']}: servirebbe un cambio ruolo)</i>" if x.get("ruolo") and x["ruolo"] != ruolo else ""


def _chi(x: dict) -> str:
    media = tp(x["media"]) if x.get("media") is not None else "—"
    pz = f"{x['partite']} {'partita' if x['partite'] == 1 else 'partite'}"
    st = f" {EMOJI.get(x['stato'], '⚠️')} {x['stato']}" if x.get("stato") not in SANI else ""
    return f"{e(x['nome'])} (media {media}, {pz}{st})"


def indizi(squadra: dict) -> list[str]:
    """Le righe di indizio di una squadra (vuota se niente)."""
    q, gioc = squadra["quintetto"], squadra["giocatori"]
    titolari = {gid for gid in q.values() if gid}
    out = []
    if not q:
        return ["• quintetto non trovato (IPanchinari non ha chiuso la giornata?)"]
    for ruolo in RUOLI:
        gid = q.get(ruolo)
        if not gid:
            out.append(f"• {ruolo}: <b>posto vuoto</b>")
            continue
        t = gioc.get(gid) or {"nome": f"giocatore {gid}", "media": None, "partite": 0, "stato": None, "posizioni": set()}
        alternative = sorted([x for g2, x in gioc.items() if g2 not in titolari and ruolo in x["posizioni"]
                              and x["partite"] > 0 and x["stato"] in SANI and x.get("media") is not None],
                             key=lambda x: -x["media"])
        if t["stato"] not in SANI:
            if alternative:
                out.append(f"• {ruolo}: titolare <b>indisponibile</b> {_chi(t)} · in rosa sano {_chi(alternative[0])}{_cambio(alternative[0], ruolo)}")
            continue
        if t["partite"] == 0:
            continue                                   # prende la sua media: non è un indizio
        if alternative and nettamente_meglio(alternative[0]["media"], t.get("media") or 0):
            diff = alternative[0]["media"] - (t.get("media") or 0)
            out.append(f"• {ruolo}: {_chi(t)} · fuori {_chi(alternative[0])} <b>+{tp(diff)}</b>{_cambio(alternative[0], ruolo)}")
    if not squadra["panchina"]:
        out.append("• <b>panchina non mandata</b>")
    return out


def testo(s: str, g: dict) -> str:
    d = dati(s, g)
    try:
        import classifica as C
        righe, conv = C.calcola(s)
        posto = {r["team"]: r["pos"] for r in righe} if conv else {}
    except Exception as err:                          # la classifica non deve fermare il controllo
        logger.warning("Tanking, classifica: %s", err)
        posto = {}
    n_sq = len(config.squadre())
    out = [f"🕵️ <b>Controllo tanking · giornata {g['numero']}</b> (dopo la prima notte, {g['dal']:%d/%m})",
           "<i>Solo per gli admin. Indizi, non verdetti: minutaggi, rientri e riposi sono scelte legittime.</i>"]
    trovati = 0
    for t in sorted(config.squadre(), key=lambda t: posto.get(t["id"], 0), reverse=True):
        r = indizi(d[t["id"]])
        if not r:
            continue
        trovati += 1
        p = posto.get(t["id"])
        fondo = " ⬇️" if p and p > n_sq * 2 / 3 else ""
        out += ["", f"<b>{e(config.nome(t['id']))}</b>" + (f" · {p}ª in classifica{fondo}" if p else "")] + r
    if not trovati:
        out += ["", "✅ Nessun indizio: tutte le formazioni sono plausibili."]
    else:
        out += ["", f"<i>Soglia: un escluso sano, con partite e che può giocare quel posto (posizioni eleggibili), con "
                    f"almeno +{tp(SOGLIA_PUNTI)} di media o +{int(SOGLIA_PERC * 100)}% sul titolare. Medie della stagione "
                    f"prima della giornata; stato dall'injury report alla scadenza, cioè quello che il GM sapeva quando ha schierato.</i>"]
    return "\n".join(out)


def giornata_di_oggi(s: str):
    """La giornata la cui prima notte è appena passata (il job gira la mattina dopo)."""
    ieri = datetime.now(ROMA).date() - timedelta(days=1)
    return next((g for g in db.giornate(s) if g["dal"] == ieri), None)


async def job_tanking(context):
    from handlers import log
    import live
    s = config.stagione()
    g = giornata_di_oggi(s)
    if not g or not config.gruppo_admin():
        return
    try:
        t = testo(s, g)
    except Exception as err:
        logger.exception("Controllo tanking G%s", g["numero"])
        await log(context.bot, f"⚠️ Controllo tanking della giornata {g['numero']} non riuscito ({e(str(err))[:200]})")
        return
    for pezzo in live._pezzi(t):
        await context.bot.send_message(chat_id=config.gruppo_admin(), text=pezzo, parse_mode="HTML")


async def cmd_tanking(update, context):
    """/tanking [N] (admin): il report di adesso, a chi lo chiede (senza N la giornata in corso o l'ultima iniziata)."""
    import live
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    s = config.stagione()
    arg = (context.args or [""])[0].lstrip("Gg")
    if arg.isdigit():
        g = db.giornata(s, int(arg))
    else:
        oggi = datetime.now(ROMA).date()
        iniziate = [x for x in db.giornate(s) if x["dal"] < oggi]
        g = iniziate[-1] if iniziate else None
    if not g:
        await msg.reply_text("Uso: /tanking [N] (una giornata già iniziata)")
        return
    for pezzo in live._pezzi(testo(s, g)):
        await msg.reply_text(pezzo, parse_mode="HTML")

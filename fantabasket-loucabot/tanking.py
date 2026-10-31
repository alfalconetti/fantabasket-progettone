"""
Controllo del tanking, parte 1 (Luca, 25/10 e 30/10): alle 11 del mattino dopo la prima notte di ogni giornata
(orari.controllo_tanking) un report **solo al gruppo admin** con gli indizi di formazioni che sembrano fatte per
perdere. Indizi, non verdetti: decidono gli admin (minutaggi, rientri, riposi sono scelte legittime).

Per ogni squadra, dalla formazione congelata (ipa_formazioni) e dalla panchina (ipa_panchine):
- posto del quintetto vuoto; panchina non mandata;
- titolare **Out** alle 21 (vedi sotto) che **non ha giocato** nessuna partita della giornata, mentre in rosa c'era
  un giocatore sano che poteva giocare quel posto e aveva partite (Luca, 31/10: «uno dato Out e che non rigioca»).
  Questionable, Doubtful, Day-To-Day sono scommesse legittime, non indizi. Che non rigiochi si sa solo quando la sua
  squadra ha finito le partite della giornata: alle 11 dopo la prima notte si segnala solo chi ha già finito; gli
  altri nel **secondo giro a fine giornata**, dopo il calcolo delle 7:45 (testo(fine=True), solo questi casi);
- titolare sano ma con fantamedia nettamente più bassa di un escluso che può giocare quel posto (posizioni
  eleggibili di Yahoo), sano e con partite nella giornata: almeno SOGLIA_PUNTI (8) di media in più **oppure**
  SOGLIA_PERC (+30%). Un titolare senza partite prende la sua media (non è un indizio, salvo se indisponibile).
- Medie: fantapunti della stagione prima della giornata (db.medie_stagione, come il calcolo). Stato: quello che il
  GM poteva sapere quando ha schierato. Per tradizione della lega (Luca, 31/10) l'ultimo injury report **prima
  delle 21 italiane** del primo giorno (`orari.tanking_injury`), o prima della scadenza se la prima partita è prima
  delle 21 (riferimento). Diverso apposta dalla FADD, che guarda l'ultimo prima della partita del giocatore, e senza
  gli status decisi dagli admin: un Out arrivato dopo le 21 non è un indizio di tanking.
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


def riferimento(g: dict) -> datetime:
    """Fino a quando conta l'injury report per il tanking: le 21 italiane (orari.tanking_injury) del primo giorno della
    giornata, o la scadenza (prima partita) se viene prima."""
    from shared import regole
    rif = datetime.combine(g["dal"], regole.orario("tanking_injury"), tzinfo=ROMA)
    scad = g.get("prima_partita")
    if not scad:
        r = db.q("SELECT MIN(inizio) AS t FROM nba_partite WHERE data_et = %s AND tipo = ANY(%s)", (g["dal"], [2, 3, 5]), one=True)
        scad = (r or {}).get("t")
    return min(rif, scad) if scad else rif


def stati_al(atleti: list[str], quando: datetime) -> tuple[dict, datetime | None]:
    """({atleta: stato} nell'ultimo snapshot preso entro `quando` (negli ultimi 3 giorni), quando è stato preso)."""
    r = db.q("SELECT MAX(preso) AS t FROM nba_infortuni WHERE preso <= %s AND preso > %s",
             (quando, quando - timedelta(days=3)), one=True)
    t = (r or {}).get("t")
    if not t or not atleti:
        return {}, t
    righe = db.q("SELECT atleta, stato FROM nba_infortuni WHERE preso = %s AND atleta = ANY(%s)", (t, list(atleti)), many=True) or []
    return {x["atleta"]: x["stato"] for x in righe}, t


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
    partite, restano, ultima = {}, {}, {}
    for p in db.partite_nba(g["dal"], g["al"]):
        if p["stato"] not in ("STATUS_POSTPONED", "STATUS_CANCELED"):
            for sq in (p["casa"], p["trasferta"]):
                partite[sq] = partite.get(sq, 0) + 1
                ultima[sq] = max(ultima.get(sq, p["data_et"]), p["data_et"])
                if p["stato"] != "STATUS_FINAL":
                    restano[sq] = restano.get(sq, 0) + 1
    import calcolo as CA
    giocate = {}
    for r in db.tabellini_atleti(atleti, g["dal"], g["al"]):
        if CA.conta(r):
            giocate[r["atleta"]] = giocate.get(r["atleta"], 0) + 1
    stato, _ = stati_al(atleti, riferimento(g))                 # alle 21 (vedi sopra), senza status degli admin
    pos = _posizioni(list(tutti))
    ruoli = {r["giocatore_id"]: r["ruolo"] for r in (db.q("SELECT giocatore_id, ruolo FROM ruolo_attuale WHERE stagione = %s "
                                                          "AND giocatore_id = ANY(%s)", (s, list(tutti)), many=True) or [])}
    for gid, x in tutti.items():
        a = x["atleta"]
        sq = squadra.get(a) if a else None
        x.update(media=(medie.get(a) or {}).get("media"), partite=partite.get(sq, 0) if sq else 0,
                 restano=restano.get(sq, 0) if sq else 0, ultima=ultima.get(sq), giocate=giocate.get(a, 0),
                 stato=stato.get(a), posizioni=pos.get(gid, set()), ruolo=ruoli.get(gid))
    return {t["id"]: {"dal": g["dal"], "quintetto": (sch.get(t["id"]) or {}).get("quintetto") or {},
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


def indizi(squadra: dict, fine: bool = False) -> list[str]:
    """Le righe di indizio di una squadra (vuota se niente). `fine`: secondo giro a fine giornata, solo i titolari Out
    alle 21 che non hanno giocato e la cui squadra giocava dopo la prima notte (gli altri sono già nel report delle 11)."""
    q, gioc = squadra["quintetto"], squadra["giocatori"]
    titolari = {gid for gid in q.values() if gid}
    out = []
    if not q:
        return [] if fine else ["• quintetto non trovato (IPanchinari non ha chiuso la giornata?)"]
    for ruolo in RUOLI:
        gid = q.get(ruolo)
        if not gid:
            if not fine:
                out.append(f"• {ruolo}: <b>posto vuoto</b>")
            continue
        t = gioc.get(gid) or {"nome": f"giocatore {gid}", "media": None, "partite": 0, "restano": 0, "giocate": 0,
                              "ultima": None, "stato": None, "posizioni": set()}
        alternative = sorted([x for g2, x in gioc.items() if g2 not in titolari and ruolo in x["posizioni"]
                              and x["partite"] > 0 and x["stato"] in SANI and x.get("media") is not None],
                             key=lambda x: -x["media"])
        if t["stato"] == "Out":
            # «dato Out e che non rigioca» (Luca, 31/10): solo quando la sua squadra ha finito le partite della giornata
            finita = not t.get("restano")
            dopo = bool(t.get("ultima") and t["ultima"] > squadra.get("dal", t["ultima"]))
            if alternative and not t.get("giocate") and finita and (dopo if fine else True):
                out.append(f"• {ruolo}: titolare <b>Out alle 21</b> e non ha giocato {_chi(t)} · in rosa sano "
                           f"{_chi(alternative[0])}{_cambio(alternative[0], ruolo)}")
            continue
        if fine or t["partite"] == 0:
            continue                                   # senza partite prende la sua media: non è un indizio
        if alternative and nettamente_meglio(alternative[0]["media"], t.get("media") or 0):
            diff = alternative[0]["media"] - (t.get("media") or 0)
            out.append(f"• {ruolo}: {_chi(t)} · fuori {_chi(alternative[0])} <b>+{tp(diff)}</b>{_cambio(alternative[0], ruolo)}")
    if not squadra["panchina"] and not fine:
        out.append("• <b>panchina non mandata</b>")
    return out


def testo(s: str, g: dict, fine: bool = False) -> str | None:
    """Il report. `fine` (dopo il calcolo delle 7:45): solo i titolari Out alle 21 rimasti fuori, None se nessuno."""
    d = dati(s, g)
    try:
        import classifica as C
        righe, conv = C.calcola(s)
        posto = {r["team"]: r["pos"] for r in righe} if conv else {}
    except Exception as err:                          # la classifica non deve fermare il controllo
        logger.warning("Tanking, classifica: %s", err)
        posto = {}
    n_sq = len(config.squadre())
    rif = riferimento(g).astimezone(ROMA)
    out = [f"🕵️ <b>Controllo tanking · giornata {g['numero']}</b> "
           + (f"a fine giornata: titolari Out alle {rif:%H:%M} del {rif:%d/%m} che non hanno giocato"
              if fine else f"(dopo la prima notte, {g['dal']:%d/%m})"),
           "<i>Solo per gli admin. Indizi, non verdetti: minutaggi, rientri e riposi sono scelte legittime.</i>"]
    trovati = 0
    for t in sorted(config.squadre(), key=lambda t: posto.get(t["id"], 0), reverse=True):
        r = indizi(d[t["id"]], fine)
        if not r:
            continue
        trovati += 1
        p = posto.get(t["id"])
        fondo = " ⬇️" if p and p > n_sq * 2 / 3 else ""
        out += ["", f"<b>{e(config.nome(t['id']))}</b>" + (f" · {p}ª in classifica{fondo}" if p else "")] + r
    if not trovati and fine:
        return None
    if not trovati:
        out += ["", "✅ Nessun indizio: tutte le formazioni sono plausibili."]
    else:
        out += ["", f"<i>Soglia: un escluso sano, con partite e che può giocare quel posto (posizioni eleggibili), con "
                    f"almeno +{tp(SOGLIA_PUNTI)} di media o +{int(SOGLIA_PERC * 100)}% sul titolare. Medie della stagione "
                    f"prima della giornata. Stato dall'injury report delle {rif:%H:%M} del {rif:%d/%m} (quello che il GM poteva sapere): conta solo Out, e solo se poi non ha giocato; "
                    f"chi gioca ancora nelle notti dopo si guarda a fine giornata.</i>"]
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


async def manda_fine(bot, s: str, g: dict) -> None:
    """Secondo giro a fine giornata (dopo il calcolo delle 7:45): i titolari Out alle 21 che non hanno giocato."""
    import live
    from handlers import log
    if not config.gruppo_admin():
        return
    try:
        t = testo(s, g, fine=True)
    except Exception as err:
        logger.exception("Tanking a fine giornata G%s", g["numero"])
        await log(bot, f"⚠️ Controllo tanking a fine giornata {g['numero']} non riuscito ({e(str(err))[:200]})")
        return
    if not t:
        await log(bot, f"🕵️ Tanking a fine giornata {g['numero']}: nessun titolare Out alle 21 rimasto fuori")
        return
    for pezzo in live._pezzi(t):
        await bot.send_message(chat_id=config.gruppo_admin(), text=pezzo, parse_mode="HTML")


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

"""
/notte [SQUADRA o GM] [DATA] (Luca, 21/10): i giocatori schierati da una squadra (quintetto e
panchina) in una notte NBA: partita, orario o stato, fantapunti, infortuni.

- Squadra: quella del GM che scrive, oppure per nome, id o GM (shared/squadre.cerca_squadra).
- Notte: di default quella in corso o appena passata (giorno ET: prima di mezzogiorno a New York la
  notte appena finita, dopo quella di stasera); oppure una data (shared/date_comandi).
- Schieramento: la formazione congelata della giornata (ipa_formazioni) e la sua panchina; se la
  giornata non è ancora iniziata, il quintetto di adesso e la panchina mandata.
- I fantapunti sono quelli dei tabellini scaricati (anche parziali, a partita in corso): provvisori
  finché la giornata non è convalidata.
"""
import html
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import config
import db
import nba
import risultati as R
from numeri import testo as tp

ROMA = ZoneInfo("Europe/Rome")
ET = ZoneInfo("America/New_York")
RUOLI = ["PG", "SG", "SF", "PF", "C"]
FINITE = ("STATUS_FINAL",)
SALTATE = ("STATUS_POSTPONED", "STATUS_CANCELED")


def e(x) -> str:
    return html.escape(str(x), quote=False)


def notte_di_default(ora: datetime | None = None) -> date:
    """La notte in corso o appena passata: prima di mezzogiorno a New York quella di ieri (ET)."""
    ora_et = (ora or datetime.now(ET)).astimezone(ET)
    return ora_et.date() - timedelta(days=1) if ora_et.hour < 12 else ora_et.date()


def giornata_della_notte(s: str, d: date) -> dict | None:
    return next((g for g in db.giornate(s) if g["dal"] <= d <= g["al"]), None)


def schieramento(s: str, team_id: str, g: dict | None) -> tuple[dict, list, bool]:
    """(quintetto {ruolo: gid}, panchina [{giocatore_id, testo}], congelato?)."""
    if g:
        sch = R.schieramenti(s, g["numero"]).get(team_id) or {}
        if sch.get("quintetto"):
            return sch["quintetto"], sch.get("panchina") or [], True
        att = R.schieramenti_attuali(s, g["numero"]).get(team_id) or {}
        return att.get("quintetto") or {}, att.get("panchina") or [], False
    att = R.schieramenti_attuali(s, 0).get(team_id) or {}
    return att.get("quintetto") or {}, [], False


def _squadre_nba(atleti: list[str]) -> dict[str, str]:
    if not atleti:
        return {}
    righe = db.q("SELECT atleta, squadra FROM nba_atleti WHERE atleta = ANY(%s)", (list(atleti),), many=True) or []
    return {r["atleta"]: r["squadra"] for r in righe}


def riga_giocatore(etichetta: str, gid: int | None, gioc: dict, partite: dict, tab: dict, inf: dict,
                   testo: str | None = None) -> tuple[str, float]:
    """Una riga e i fantapunti contati (0 se non ha giocato)."""
    x = gioc.get(gid) or {}
    nome = x.get("nome_common") or "—"
    a = x.get("espn_id")
    sq = x.get("_sq")
    pezzi = [f"{etichetta} <b>{e(nome)}</b>" + (f" <i>«{e(testo)}»</i>" if testo and testo != nome else "")
             + (f" ({sq})" if sq else "")]
    if not gid:
        return pezzi[0] + " · vuoto", 0.0
    if not a:
        return pezzi[0] + " · ⚠️ senza id ESPN", 0.0
    p = partite.get(sq)
    stato = inf.get(a)
    fp = 0.0
    if not p:
        pezzi.append("non gioca")
    else:
        avv = p["trasferta"] if p["casa"] == sq else p["casa"]
        vs = ("vs " if p["casa"] == sq else "@ ") + avv
        t = tab.get((a, p["espn_id"]))
        if p["stato"] in SALTATE:
            pezzi.append(f"{vs} · rinviata")
        elif p["stato"] == "STATUS_SCHEDULED":
            pezzi.append(f"{vs} · {p['inizio'].astimezone(ROMA):%H:%M}" if p.get("inizio") else vs)
        elif t and t.get("giocato"):
            fp = float(t["fp"] or 0)
            pezzi.append(f"{vs} · <b>{tp(fp)}</b>" + (" 🏀 in corso" if p["stato"] not in FINITE else ""))
        elif p["stato"] in FINITE:
            pezzi.append(f"{vs} · DNP")
        else:
            pezzi.append(f"{vs} · 🏀 in corso")
    if stato and stato.lower() not in ("sano", "active"):
        pezzi.append(f"🩹 {e(stato)}")
    return " · ".join(pezzi), fp


def testo_notte(s: str, team: dict, d: date) -> str:
    g = giornata_della_notte(s, d)
    q, panca, congelato = schieramento(s, team["id"], g)
    ids = [v for v in q.values() if v] + [r.get("giocatore_id") for r in panca if r.get("giocatore_id")]
    gioc = R._giocatori(ids, s)
    atleti = [x["espn_id"] for x in gioc.values() if x.get("espn_id")]
    tab_righe = db.tabellini_atleti(atleti, d, d)
    tab = {(r["atleta"], r["partita"]): r for r in tab_righe}
    # squadra NBA: quella del tabellino di quella notte, se no l'ultima nota (tabellini, poi roster ESPN)
    sq_nba = {**_squadre_nba(atleti), **db.ultima_squadra(atleti, d + timedelta(days=1)),
              **{r["atleta"]: r["squadra"] for r in tab_righe if r.get("squadra")}}
    for x in gioc.values():
        x["_sq"] = sq_nba.get(x.get("espn_id"))
    partite = {}
    for p in db.partite_nba(d, d):
        for sq in (p["casa"], p["trasferta"]):
            partite[sq] = p
    inf = {a: st for (a, _g), st in db.infortuni(atleti, [d]).items()}
    titolo = (f"🌙 <b>{e(team['nome'])}</b> · notte del {d:%d/%m}"
              + (f" · giornata {g['numero']}" if g else " · fuori giornata"))
    righe = [titolo, ""]
    if not q and not panca:
        return titolo + "\n\nNessuna formazione per questa notte."
    righe.append("<b>Quintetto</b>" + ("" if congelato else " <i>(quello di adesso: la giornata non è ancora iniziata)</i>"))
    tot = 0.0
    for r in RUOLI:
        riga, fp = riga_giocatore(r, q.get(r), gioc, partite, tab, inf)
        righe.append(riga)
        tot += fp
    righe.append(f"<i>Titolari stanotte: {tp(tot)} fantapunti</i>")
    if panca:
        righe += ["", "<b>Panchina</b>"]
        for i, p in enumerate(panca, 1):
            riga, _ = riga_giocatore(f"{i}.", p.get("giocatore_id"), gioc, partite, tab, inf, p.get("testo"))
            righe.append(riga)
    elif g:
        righe += ["", "<i>Panchina non mandata.</i>"]
    righe += ["", "<i>Fantapunti dai tabellini ESPN, provvisori fino alla convalida della giornata (FADD e "
                  "supplementari si decidono a giornata finita).</i>"]
    return "\n".join(righe)


def _giorno_mese(testo: str) -> date | None:
    """«21/10» senza anno: quello più vicino a oggi (a gennaio, 28/12 è dell'anno prima)."""
    import re
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})$", str(testo).strip())
    if not m:
        return None
    oggi = datetime.now(ET).date()
    try:
        d = date(oggi.year, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    if d - oggi > timedelta(days=180):
        d = d.replace(year=d.year - 1)
    elif oggi - d > timedelta(days=180):
        d = d.replace(year=d.year + 1)
    return d


async def cmd_notte(update, context):
    from shared.date_comandi import leggi_data
    from shared.squadre import cerca_squadra
    msg = update.effective_message
    args = list(context.args or [])
    d = None
    resto = []
    for a in args:
        x = leggi_data(a) or _giorno_mese(a)
        if x and not d:
            d = x
        else:
            resto.append(a)
    team = cerca_squadra(" ".join(resto), config.squadre()) if resto else config.squadra_del_gm(update.effective_user.id)
    if not team:
        await msg.reply_text("Uso: /notte [SQUADRA o GM] [DATA] — senza squadra la tua, senza data la notte in corso "
                             "o appena passata. Es: /notte Alfa 21/10")
        return
    d = d or notte_di_default()
    _ = nba
    await msg.reply_text(testo_notte(config.stagione(), team, d), parse_mode="HTML")

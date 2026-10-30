"""
/carriera GIOCATORE (v6.5.0, Luca 23/10; per ora nel bot principale, poi nel bot delle statistiche):
immagine Typst (`carriera.typ`, toni blu) con due timeline in parallelo dal 25/07/2026, quando è
nato il bot: a sinistra il fantabasket, a destra la NBA reale. Al centro le date in ordine; accanto
una barra col colore della squadra di ogni periodo (niente barra da free agent).

Fantabasket (`database.movimenti_carriera`, più le DPE): in rosa all'avvio (migrazione iniziale), o il
draft per i diritti rookie all'avvio e per i rookie del draft 2026 già sotto contratto (anno, giro, numero), firme (asta, firma manuale, rookie,
10-day), trade (una trade annullata sparisce con il suo annullamento: il giocatore non si è mai
mosso), tagli, decadimenti, fine 10-day, rinnovi, DPE, trade e scadenza dei diritti.

NBA: la squadra al 25/07 (la prima nota), poi i cambi di squadra visti nei roster ESPN delle 8:30
(`nba_movimenti` di loucabot, dal 23/10/2026) e, per quelli prima o sfuggiti, i cambi nelle righe
giornaliere di Basketball-Reference (`bref_stats`: la data è quella in cui bref l'ha visto, cioè
dopo la prima partita con la squadra nuova). Un cambio di bref già visto da ESPN nei 30 giorni
prima non si ripete.

Loghi: quelli delle squadre del fantabasket (config/loghi); NBA da config/loghi/nba/<SIGLA>.png se
ci sono, se no un tondo col colore della squadra e la sigla. Foto: quelle di loucabot
(config/foto/<id ESPN>.png). Callback car:<giocatore_id> per scegliere tra più giocatori.
"""
import asyncio
import html
import re
import json
import logging
import os
import subprocess
import tempfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db
import settings
import teams as tm

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
DAL = date(2026, 7, 25)                 # nasce il bot: da qui partono le due timeline
TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "carriera.typ")
PPI = 288                               # pagina di 400pt (v6.5.2, più stretta) → 1600 pixel di larghezza
LOGHI_DIR = os.environ.get("LOGHI_DIR", "/config/loghi")
FOTO_DIR = os.environ.get("FOTO_DIR") or os.path.join(os.environ.get("CONFIG_DIR", "/config"), "foto")
GRIGIO_FA = "#9AA3B5"

# squadre NBA: nome e colore principale (per la barra e il segnaposto del logo)
NBA = {
    "ATL": ("Atlanta Hawks", "#C8102E"), "BOS": ("Boston Celtics", "#007A33"), "BKN": ("Brooklyn Nets", "#000000"),
    "CHA": ("Charlotte Hornets", "#1D1160"), "CHI": ("Chicago Bulls", "#CE1141"), "CLE": ("Cleveland Cavaliers", "#860038"),
    "DAL": ("Dallas Mavericks", "#00538C"), "DEN": ("Denver Nuggets", "#0E2240"), "DET": ("Detroit Pistons", "#C8102E"),
    "GSW": ("Golden State Warriors", "#1D428A"), "HOU": ("Houston Rockets", "#CE1141"), "IND": ("Indiana Pacers", "#002D62"),
    "LAC": ("LA Clippers", "#C8102E"), "LAL": ("Los Angeles Lakers", "#552583"), "MEM": ("Memphis Grizzlies", "#5D76A9"),
    "MIA": ("Miami Heat", "#98002E"), "MIL": ("Milwaukee Bucks", "#00471B"), "MIN": ("Minnesota Timberwolves", "#0C2340"),
    "NOP": ("New Orleans Pelicans", "#0C2340"), "NYK": ("New York Knicks", "#006BB6"), "OKC": ("Oklahoma City Thunder", "#007AC1"),
    "ORL": ("Orlando Magic", "#0077C0"), "PHI": ("Philadelphia 76ers", "#006BB6"), "PHX": ("Phoenix Suns", "#1D1160"),
    "POR": ("Portland Trail Blazers", "#E03A3E"), "SAC": ("Sacramento Kings", "#5A2D81"), "SAS": ("San Antonio Spurs", "#8A8D8F"),
    "TOR": ("Toronto Raptors", "#CE1141"), "UTA": ("Utah Jazz", "#002B5C"), "WAS": ("Washington Wizards", "#002B5C"),
}
SIGLE_BREF = {"BRK": "BKN", "PHO": "PHX", "CHO": "CHA", "NOH": "NOP", "GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP",
              "UTAH": "UTA", "WSH": "WAS"}


def e(x) -> str:
    return html.escape(str(x), quote=False)


def _c_e(tabella: str) -> bool:
    try:
        return bool(db._q("SELECT to_regclass(%s) AS t", (tabella,), one=True)["t"])
    except Exception:
        return False


# ── squadre ───────────────────────────────────────────────────────────────────

def _sigla_fanta(nome: str) -> str:
    parole = [p for p in nome.replace("-", " ").split() if p[:1].isalnum()]
    return "".join(p[0] for p in parole[:3]).upper() or nome[:3].upper()


def sq_fanta(team_id: str | None) -> dict | None:
    if not team_id:
        return None
    from handlers.roster import _logo_path, colori_effettivi
    t = tm.get_team_by_id(team_id) or {"id": team_id, "nome": team_id}
    return {"nome": t["nome"], "sigla": _sigla_fanta(t["nome"]), "colore": colori_effettivi(t)["header"],
            "logo": _logo_path(team_id)}


def sigla_nba(s: str | None) -> str | None:
    if not s:
        return None
    s = str(s).strip().upper()
    return SIGLE_BREF.get(s, s)


def sq_nba(sigla: str | None) -> dict | None:
    sigla = sigla_nba(sigla)
    if not sigla:
        return None
    nome, colore = NBA.get(sigla, (sigla, "#4B5563"))
    logo = next((p for p in (os.path.join(LOGHI_DIR, "nba", f"{sigla}.{x}") for x in ("png", "jpg", "webp")) if os.path.exists(p)), "")
    return {"nome": nome, "sigla": sigla, "colore": colore, "logo": logo}


FA = {"nome": "Free agent", "sigla": "FA", "colore": GRIGIO_FA, "logo": ""}


# ── fantabasket ───────────────────────────────────────────────────────────────

def _stag(y) -> str:
    y = int(y)
    return f"{y}-{str(y + 1)[-2:]}"


def _contratto(r: dict) -> str:
    if r.get("importo") is None:
        return ""
    return f"{r['importo']}M × {r['anni_originali']}" + (" · rookie" if r.get("tipo_contratto") == "rookie" or r.get("rookie_scale") else "")


def _ref(r: dict) -> str:
    """« · TRADE-2026-014»: il numero della trade, per ritrovarla (Luca, 23/10)."""
    return f" · {r['trade_ref']}" if r.get("trade_ref") else ""


def eventi_fanta(gid: int) -> list[dict]:
    """[{quando, tipo, etichetta, titolo, dettaglio, sq (dopo l'evento: dict o None = free agent)}]."""
    mov = db.movimenti_carriera(gid, datetime.combine(DAL, datetime.min.time(), tzinfo=ROMA))
    # trade annullate: l'annullamento e la trade originale (stesso trade_id) spariscono insieme
    annullate = {r["trade_id"] for r in mov if r["trade_id"] and (r.get("note") or "").upper().startswith("ANNULLAMENTO")}
    rookie = db._q("SELECT * FROM rookie WHERE giocatore_id = %s ORDER BY id DESC LIMIT 1", (gid,), one=True) or {}
    draft = (f"Draft {rookie['anno_draft']}, {rookie['round']}° giro #{rookie['pick_numero']}" if rookie.get("anno_draft") else "")
    nome = lambda t: (tm.get_team_by_id(t) or {}).get("nome", t) if t else "—"
    out = []
    for r in mov:
        if r["trade_id"] in annullate and r["tipo"] in ("traded", "trade"):
            continue
        tipo, nota = r["tipo"], (r.get("note") or "")
        ev = None
        if r["oggetto"] == "diritti":
            if tipo == "iniziale":
                ev = ("draft", "Draft", r["team_id_a"], (draft or "diritti rookie") + " · diritti all'avvio del bot")
            elif tipo in ("traded", "trade"):
                ev = ("trade", "Trade diritti", r["team_id_a"], f"diritti rookie da {nome(r['team_id_da'])}" + _ref(r))
            elif tipo == "rookie_diritti_scaduti":
                ev = ("scadenza", "Diritti scaduti", None, f"diritti di {nome(r['team_id_da'])} scaduti senza firma")
        elif ((tipo in ("signed", "firma", "iniziale") and "migrazione iniziale" in nota.lower() or tipo == "iniziale")
              and r.get("tipo_contratto") == "rookie" and rookie and str(rookie.get("anno_draft")) == str(DAL.year)):
            # rookie del draft di quest'anno già sotto contratto all'avvio: si parte dal draft (Luca, 23/10)
            ev = ("draft", "Draft", r["team_id_a"], f"{draft} · {_contratto(r)}")
        elif tipo in ("signed", "firma", "iniziale") and "migrazione iniziale" in nota.lower() or tipo == "iniziale":
            ev = ("avvio", "All'avvio", r["team_id_a"], "in rosa quando è nato il bot" + (f" · {_contratto(r)}" if _contratto(r) else "")
                  + (f" (firmato nel {_stag(r['stagione_firma'])})" if r.get("stagione_firma") else ""))
        elif tipo in ("signed", "firma"):
            asta = bool(re.search(r"\bast[ae]\b", nota.lower()))      # «Firma FA bot aste — …», «asta vinta»
            ev = ("firma", "Firma FA" if asta else "Firma", r["team_id_a"], ("asta vinta: " if asta else "") + (_contratto(r) or "contratto"))
        elif tipo == "rookie_firma":
            ev = ("rookie", "Firma rookie", r["team_id_a"], (draft + " · " if draft else "") + (_contratto(r) or "contratto rookie"))
        elif tipo in ("traded", "trade"):
            ev = ("trade", "Trade", r["team_id_a"], f"da {nome(r['team_id_da'])}" + _ref(r))
        elif tipo in ("cut", "taglio"):
            ev = ("taglio", "Taglio", None, f"tagliato da {nome(r['team_id_da'])}")
        elif tipo in ("decadimento", "decaduto", "expired"):
            ev = ("scadenza", "Decaduto" if tipo != "expired" else "Contratto finito", None, f"da {nome(r['team_id_da'])}")
        elif tipo == "renewed":
            ev = ("rinnovo", "Rinnovo", r["team_id_a"] or r["team_id_da"], _contratto(r) or "rinnovato")
        elif tipo == "10day_firma":
            ev = ("10-day", "10-day", r["team_id_a"], "contratto di 10 giorni")
        elif tipo == "10day_scadenza":
            ev = ("scadenza", "Fine 10-day", None, f"finito il 10-day con {nome(r['team_id_da'])}")
        if ev:
            out.append({"quando": r["timestamp"], "tipo": ev[0], "etichetta": ev[1], "team": ev[2], "dettaglio": ev[3]})
    for d in db._q("SELECT * FROM dpe WHERE giocatore_id = %s AND timestamp >= %s ORDER BY timestamp", (gid, DAL), many=True) or []:
        out.append({"quando": d["timestamp"], "tipo": "dpe", "etichetta": "DPE", "team": d["team_id"],
                    "dettaglio": f"pesa {d['importo_dpe']}M invece di {d['importo_originale']}M nel {d['stagione']}"})
    out.sort(key=lambda x: x["quando"])
    for x in out:
        x["sq"] = sq_fanta(x["team"]) if x["team"] else None
        x["titolo"] = x["sq"]["nome"] if x["sq"] else "Free agent"
        x["logo_sq"] = x["sq"] or FA
    return out


# ── NBA ───────────────────────────────────────────────────────────────────────

def eventi_nba(espn: str | None, nome_bref: str | None) -> list[dict]:
    """La squadra al 25/07 e i cambi dopo (roster ESPN, poi Basketball-Reference)."""
    espn_mov = []
    if espn and _c_e("nba_movimenti"):
        espn_mov = db._q("SELECT giorno, da, a FROM nba_movimenti WHERE atleta = %s AND giorno >= %s ORDER BY giorno, id",
                         (espn, DAL), many=True) or []
    bref, bref_primo = [], None
    if nome_bref and _c_e("bref_stats"):
        righe = db._q("""SELECT timestamp::date AS giorno, team FROM bref_stats WHERE nome_bref = %s AND timestamp >= %s
                         ORDER BY timestamp""", (nome_bref, DAL), many=True) or []
        prima = None
        for r in righe:
            t = sigla_nba(r["team"])
            if t and "TM" not in t and t != prima:
                bref_primo = bref_primo or t
                if prima:
                    bref.append({"giorno": r["giorno"], "da": prima, "a": t})
                prima = t
    adesso = None
    if espn and _c_e("nba_atleti"):
        adesso = (db._q("SELECT squadra FROM nba_atleti WHERE atleta = %s", (espn,), one=True) or {}).get("squadra")
    # prima squadra nota: quella da cui parte il primo cambio, se no la prima riga di bref, se no quella di adesso
    primi = sorted([(m["giorno"], sigla_nba(m["da"])) for m in espn_mov if m["da"]] + [(m["giorno"], m["da"]) for m in bref])
    iniziale = primi[0][1] if primi else (bref_primo or sigla_nba(adesso))
    out = []
    if iniziale:
        out.append({"quando": datetime.combine(DAL, datetime.min.time(), tzinfo=ROMA), "tipo": "avvio", "etichetta": "Al 25/07",
                    "a": iniziale, "dettaglio": "la sua squadra quando è nato il bot"})
    for m in espn_mov:
        da, a = sigla_nba(m["da"]), sigla_nba(m["a"])
        if a and da:
            et, det = "Cambio squadra", f"da {sq_nba(da)['nome']}"
        elif a:
            et, det = "Firma", "di nuovo in un roster NBA"
        else:
            et, det = "Svincolato", f"fuori dal roster di {sq_nba(da)['nome']}"
        out.append({"quando": datetime.combine(m["giorno"], datetime.min.time(), tzinfo=ROMA) + timedelta(hours=9),
                    "tipo": "trade" if a and da else ("firma" if a else "taglio"), "etichetta": et, "a": a, "dettaglio": det})
    visti = [(m["giorno"], sigla_nba(m["a"])) for m in espn_mov]
    for m in bref:
        if any(a == m["a"] and timedelta(0) <= m["giorno"] - g <= timedelta(days=30) for g, a in visti):
            continue
        out.append({"quando": datetime.combine(m["giorno"], datetime.min.time(), tzinfo=ROMA) + timedelta(hours=12),
                    "tipo": "trade", "etichetta": "Cambio squadra", "a": m["a"],
                    "dettaglio": f"da {sq_nba(m['da'])['nome']} (Basketball-Reference: prima partita con la squadra nuova)"})
    out.sort(key=lambda x: x["quando"])
    for x in out:
        x["sq"] = sq_nba(x["a"])
        x["titolo"] = x["sq"]["nome"] if x["sq"] else "Senza squadra"
        x["logo_sq"] = x["sq"] or FA
    return out


# ── dati per l'immagine ───────────────────────────────────────────────────────

def _carta(x: dict) -> dict:
    return {"tipo": x["tipo"], "etichetta": x["etichetta"], "titolo": x["titolo"], "dettaglio": x["dettaglio"], "sq": x["logo_sq"]}


def righe_timeline(fanta: list[dict], nba: list[dict]) -> list[dict]:
    """Una riga per giorno (più righe se nello stesso giorno ci sono più eventi da una parte), con la
    squadra di ogni parte dopo gli eventi della riga (per la barra) e, dal lato senza eventi, la
    squadra del momento scritta piano."""
    giorni = sorted({x["quando"].astimezone(ROMA).date() for x in fanta + nba})
    out, sf, sn = [], None, None
    # più eventi nello stesso giorno (due trade di fila): una riga ciascuno, la data solo sulla prima (Luca, 23/10)
    for g in giorni:
        f = [x for x in fanta if x["quando"].astimezone(ROMA).date() == g]
        n = [x for x in nba if x["quando"].astimezone(ROMA).date() == g]
        for i in range(max(len(f), len(n))):
            if i < len(f):
                sf = f[i]["sq"]
            if i < len(n):
                sn = n[i]["sq"]
            out.append({"giorno": f"{g:%d/%m}", "anno": f"{g:%Y}", "mostra_data": i == 0,
                        "fanta": _carta(f[i]) if i < len(f) else None, "nba": _carta(n[i]) if i < len(n) else None,
                        "fanta_sq": sf, "nba_sq": sn,
                        "fanta_resta": "" if i < len(f) else (sf["nome"] if sf else "Free agent"),
                        "nba_resta": "" if i < len(n) else (sn["nome"] if sn else "")})
    return out


def _breve_fanta(ev: list[dict]) -> str:
    if not ev:
        return "nessun movimento dal 25/07/2026"
    squadre = {x["team"] for x in ev if x["team"]}
    conta = lambda *t: sum(1 for x in ev if x["tipo"] in t)
    pezzi = [f"{len(squadre)} {'squadra' if len(squadre) == 1 else 'squadre'}"]
    for n, t in ((conta("trade"), "trade"), (conta("taglio"), "taglio" if conta("taglio") == 1 else "tagli"),
                 (conta("firma", "rookie", "10-day"), "firma" if conta("firma", "rookie", "10-day") == 1 else "firme"),
                 (conta("dpe"), "DPE")):
        if n:
            pezzi.append(f"{n} {t}")
    return " · ".join(pezzi)


def _breve_nba(ev: list[dict]) -> str:
    if not ev:
        return "squadra NBA non nota"
    squadre = {x["a"] for x in ev if x.get("a")}
    cambi = sum(1 for x in ev if x["tipo"] != "avvio")
    return f"{len(squadre)} {'squadra' if len(squadre) == 1 else 'squadre'}" + (f" · {cambi} {'cambio' if cambi == 1 else 'cambi'}" if cambi else " · nessun cambio")


def dati(gid: int, ora: datetime | None = None) -> dict:
    ora = ora or datetime.now(timezone.utc)
    g = db.get_giocatore(gid)
    if not g:
        raise ValueError("giocatore non trovato")
    stagione = settings.stagione_corrente()
    fanta = eventi_fanta(gid)
    nba = eventi_nba(g.get("espn_id"), g.get("nome_bref"))
    pos = db._q("SELECT posizioni FROM posizioni_attuali WHERE giocatore_id = %s", (gid,), one=True) if _c_e("posizioni_attuali") else None
    eleg = [r for r in ("PG", "SG", "SF", "PF", "C") if r in set(((pos or {}).get("posizioni") or "").split(","))]
    eta = None
    if g.get("data_nascita"):
        dn, oggi = g["data_nascita"], ora.astimezone(ROMA).date()
        eta = oggi.year - dn.year - ((oggi.month, oggi.day) < (dn.month, dn.day))
    c = db._q("SELECT * FROM contratti WHERE giocatore_id = %s AND attivo LIMIT 1", (gid,), one=True)
    if c:
        anni = int(c["anni_originali"]) - (int(stagione) - int(c["stagione_firma"]))
        fine = int(c["stagione_firma"]) + int(c["anni_originali"]) - 1
        contratto = "10-day" if c["tipo"] == "10day" else f"{c['importo']}M × {max(anni, 0)}"
        fino = ("contratto di 10 giorni" if c["tipo"] == "10day" else
                f"fino al {_stag(fine)} · firmato nel {_stag(c['stagione_firma'])}" + (" · rookie" if c["tipo"] == "rookie" else ""))
        fanta_ora = (tm.get_team_by_id(c["team_id"]) or {}).get("nome", c["team_id"])
    else:
        contratto, fino, fanta_ora = "—", "free agent", "Free agent"
    nba_ora = nba[-1]["titolo"] if nba else "squadra NBA non nota"
    foto = os.path.join(FOTO_DIR, f"{g['espn_id']}.png") if g.get("espn_id") else ""
    return {
        "nome": g["nome_common"], "posizioni": ", ".join(eleg) or "posizioni non registrate", "eta": eta,
        "foto": foto if foto and os.path.exists(foto) else "",
        "iniziali": "".join(p[0] for p in g["nome_common"].split()[:2]).upper(),
        "ora": {"fanta": fanta_ora, "nba": nba_ora, "contratto": contratto, "fino": fino},
        "dal": f"{DAL:%d/%m/%Y}", "righe": righe_timeline(fanta, nba),
        "breve": {"fanta": _breve_fanta(fanta), "nba": _breve_nba(nba)},
        "aggiornato": f"{ora.astimezone(ROMA):%d/%m alle %H:%M}",
    }



def _togli(path: str) -> None:
    """Cancella il PNG temporaneo (vuoto) di una compilazione Typst non riuscita."""
    try:
        os.unlink(path)
    except OSError:
        pass

async def genera_png(gid: int) -> str:
    d = dati(gid)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    cmd = ["typst", "compile", "--root", "/", "--ppi", str(PPI), "--input", "dati=" + json.dumps(d, ensure_ascii=False, default=str),
           os.path.abspath(TEMPLATE), tmp.name]
    r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
    if r.returncode != 0:
        logger.error("Typst carriera: %s", r.stderr)
        _togli(tmp.name)                 # niente PNG vuoti lasciati in /tmp
        raise RuntimeError(f"Errore Typst: {r.stderr[:300]}")
    return tmp.name


# ── comando ───────────────────────────────────────────────────────────────────

async def _manda(msg, gid: int):
    try:
        path = await genera_png(gid)
    except Exception as err:
        logger.exception("Carriera %s", gid)
        await msg.reply_text(f"❌ Non riesco a disegnare la carriera: {e(str(err)[:200])}", parse_mode="HTML")
        return
    try:
        nome = (db.get_giocatore(gid) or {}).get("nome_common", "")
        with open(path, "rb") as f:
            await msg.reply_photo(photo=f, caption=f"📜 Carriera di {nome} dal 25/07/2026")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def cmd_carriera(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    testo = " ".join(context.args or []).strip()
    if not testo:
        await msg.reply_text("Uso: /carriera GIOCATORE — i movimenti nel fantabasket e nella NBA dal 25/07/2026. Es: /carriera Brunson")
        return
    from handlers.posizioni import _cerca_giocatori
    trovati, esatto = _cerca_giocatori(testo)
    if not trovati:
        await msg.reply_text("Nessun giocatore con questo nome.")
        return
    if esatto and len(trovati) == 1:
        await _manda(msg, trovati[0]["id"])
        return
    kb = K([[B(x["nome_common"], callback_data=f"car:{x['id']}")] for x in trovati[:8]])
    await msg.reply_text("Quale giocatore?" if esatto else "Non trovo il nome esatto: intendevi?", reply_markup=kb)


async def cb_carriera(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        gid = int(q.data.split(":")[1])
    except (IndexError, ValueError):
        return
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _manda(q.message, gid)


def get_handlers() -> list:
    return [CommandHandler("carriera", cmd_carriera), CallbackQueryHandler(cb_carriera, pattern=r"^car:\d+$")]

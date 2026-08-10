"""
Generazione roster PNG tramite Typst.

/roster_png [team_id] — genera il roster come immagine e lo manda in chat.
Se team_id è omesso, usa il team del GM che chiama il comando.

Loghi: config/loghi/{team_id}_logo.png
Template: roster.typ nella root del bot
"""
import logging
import os
import subprocess
import math as _math


def _luminanza(hex_color: str) -> float:
    """Luminanza relativa WCAG."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    def lin(v): return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _text_on(hex_color: str) -> str:
    """Colore testo leggibile su sfondo dato (WCAG, soglia 0.179).
    Stringa vuota → sfondo chiaro di default → testo scuro."""
    if not hex_color or not hex_color.startswith("#"):
        return "#1a1a1a"
    try:
        return "#f0f0f0" if _luminanza(hex_color) < 0.179 else "#1a1a1a"
    except Exception:
        return "#1a1a1a"


def _text_on_muted(hex_color: str) -> str:
    if not hex_color or not hex_color.startswith("#"):
        return "#555555"
    try:
        return "#bbbbbb" if _luminanza(hex_color) < 0.179 else "#555555"
    except Exception:
        return "#555555"


def _footer_color(colore_primario: str, colore_sezione: str) -> str:
    """Colore effettivo del footer: c_sezione se impostato, altrimenti c_dark (primary.darken(20%))."""
    if colore_sezione and colore_sezione.startswith("#"):
        return colore_sezione
    # Simula darken(20%): mescola con nero
    h = colore_primario.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    r2, g2, b2 = int(r * 0.8), int(g * 0.8), int(b * 0.8)
    return f"#{r2:02x}{g2:02x}{b2:02x}"


import tempfile

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import database as db
import settings
import teams as tm
from settings import solo_privato
from utils import cognome as _cognome

logger = logging.getLogger(__name__)

TYPST_TEMPLATE  = os.path.join(os.path.dirname(__file__), "..", "roster.typ")
ASSETS_TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "assets.typ")
LOGHI_DIR       = os.environ.get("LOGHI_DIR", "/config/loghi")


# ── helpers ───────────────────────────────────────────────────────────────────

def _logo_path(team_id: str) -> str:
    """Restituisce il path del logo se esiste, stringa vuota altrimenti."""
    path = os.path.join(LOGHI_DIR, f"{team_id}_logo.png")
    return path if os.path.exists(path) else ""


def _flag(r: dict) -> str:
    """N=normale, A=RFA, R0-R3=rookie anno I-IV dello scale."""
    if r.get("tipo_contratto") == "rookie":
        scala = int(r.get("anni_scala") or 0)
        return f"R{min(scala, 3)}"
    return "N"


def _eta(data_nascita) -> int | None:
    """Età al giorno corrente in anni compiuti."""
    if not data_nascita:
        return None
    try:
        from datetime import date
        oggi = date.today()
        dn   = data_nascita if isinstance(data_nascita, date) else date.fromisoformat(str(data_nascita))
        return oggi.year - dn.year - ((oggi.month, oggi.day) < (dn.month, dn.day))
    except Exception:
        return None


def _build_giocatori_str(roster: list, contratti: list) -> str:
    """
    Costruisce la stringa giocatori per Typst:
    "Nome|importo|anni_res|flag;..."
    Ordinamento: importo DESC, cognome ASC.
    Flag: N=normale, A=RFA, R0-R3=rookie anno I-IV scale
    """
    stagione_int = int(settings.stagione_corrente())
    righe = []
    for r in sorted(roster, key=lambda x: (-( x.get("importo") or 0), _cognome(x["nome_common"]))):
        importo = r.get("importo", 0)
        tipo    = r.get("tipo_contratto", "normale")

        if tipo == "rookie":
            scala    = int(r.get("anni_scala") or 0)
            anni_res = 2 if scala in (0, 2) else 1
            flag     = f"R{min(scala, 3)}"
        else:
            anni_orig = r.get("anni_originali", 1)
            s_firma   = int(r.get("stagione_firma") or stagione_int)
            anni_res  = max(1, anni_orig - (stagione_int - s_firma))
            flag      = "N"

        nome = r["nome_common"].replace("|", " ").replace(";", " ")
        righe.append(f"{nome}|{importo}|{anni_res}|{flag}")
    return ";".join(righe)


async def _genera_roster_png(team: dict, stagione: str, as_of=None) -> str:
    """
    Genera il PNG del roster tramite Typst.
    as_of: datetime opzionale — se presente, mostra il roster a quella data.
    """
    team_id = team["id"]

    # Roster: attuale o storico
    if as_of:
        roster    = db.get_roster_team_at(team_id, as_of.isoformat())
        contratti = db.get_contratti_team_at(team_id, as_of.isoformat())
    else:
        roster    = db.get_roster_team(team_id)
        contratti = db.get_contratti_team(team_id)

    giocatori_str = _build_giocatori_str(roster, contratti)

    # Salary cap
    cap_contratti = sum(r.get("importo", 0) for r in roster)
    impatti       = db.get_impatto_taglio_team(team_id, stagione)
    cap_impatto   = sum(i.get("importo", 0) for i in impatti)
    cap_totale    = cap_contratti + cap_impatto
    salary        = str(cap_totale)
    salary_detail = f"{cap_contratti}+{cap_impatto}" if cap_impatto > 0 else str(cap_contratti)

    # Età media al giorno corrente
    eta_list = [_eta(r.get("data_nascita")) for r in roster]
    eta_list = [e for e in eta_list if e is not None]
    eta_str  = f"{sum(eta_list)/len(eta_list):.1f}" if eta_list else "—"

    # Colori
    colore  = team.get("colore_header", "#1A237E")
    c_riga1   = team.get("colore_riga1",   "")
    c_riga2   = team.get("colore_riga2",   "")
    c_sezione = team.get("colore_sezione", "")

    # Logo
    logo = _logo_path(team_id)

    # Tagli e cambi ruolo — placeholder, da collegare a DB quando implementato
    tagli_usati  = team.get("tagli_usati",  "0/3")
    cambi_usati  = team.get("cambi_usati",  "0/2")

    # Genera in file temporaneo
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()

    cmd = [
        "typst", "compile",
        "--input", f"team_nome={team['nome']}",
        "--input", f"team_gm={team.get('gm_nome', '')}",
        "--input", f"colore_header={colore}",

        "--input", f"colore_riga1={c_riga1}",
        "--input", f"colore_riga2={c_riga2}",
        "--input", f"colore_sezione={c_sezione}",
        "--input", f"text_on_riga1={_text_on(c_riga1)}",
        "--input", f"text_on_riga2={_text_on(c_riga2)}",
        "--input", f"text_on_sezione={_text_on(c_sezione)}",
        "--input", f"text_on_sezione_muted={_text_on_muted(c_sezione)}",
        "--input", f"text_on_footer={_text_on(_footer_color(colore, c_sezione))}",
        "--input", f"text_on_footer_muted={_text_on_muted(_footer_color(colore, c_sezione))}",
        "--input", f"salary_cap={salary}",
        "--input", f"salary_detail={salary_detail}",
        "--input", f"eta_media={eta_str}",
        "--input", f"tagli_usati={tagli_usati}",
        "--input", f"cambi_usati={cambi_usati}",
        "--input", f"logo_path={logo}",
        "--input", f"giocatori={giocatori_str}",
        os.path.abspath(TYPST_TEMPLATE),
        tmp.name,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Typst error: %s", result.stderr)
        raise RuntimeError(f"Errore Typst: {result.stderr[:300]}")

    return tmp.name


# ── handler ───────────────────────────────────────────────────────────────────

async def cmd_roster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /roster [team_id] [DD-MM-YY]

    Genera il roster come PNG.
    - team_id: default = squadra del GM che chiama
    - data:    default = oggi (roster attuale)
               se specificata, mostra il roster a quella data (event sourcing)
    """
    user = update.effective_user
    args = context.args or []

    # Parsing argomenti: team_id e/o data in qualsiasi ordine
    team    = None
    as_of   = None  # datetime o None

    for arg in args:
        # Prova a parsare come data DD-MM-YYYY o DD-MM-YY
        try:
            from datetime import datetime, timezone
            fmt = "%d-%m-%Y" if len(arg) == 10 else "%d-%m-%y"
            as_of = datetime.strptime(arg, fmt).replace(
                hour=23, minute=59, tzinfo=timezone.utc
            )
            continue
        except ValueError:
            pass
        # Altrimenti è un team_id
        team = tm.get_team_by_id(arg)
        if not team:
            await update.effective_message.reply_text(f"❌ Team '{arg}' non trovato.")
            return

    # Default team = squadra del GM
    if team is None:
        team = tm.get_team_by_gm(user.id)
        if not team:
            await update.effective_message.reply_text(
                "⛔ Non sei registrato come GM. Usa /roster <team_id>."
            )
            return

    if as_of:
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        if as_of > now:
            await update.effective_message.reply_text("❌ La data non può essere nel futuro.")
            return
        prima = db.get_prima_transazione()
        if prima and as_of < prima:
            await update.effective_message.reply_text(
                f"❌ Nessun dato disponibile prima del {prima.strftime('%d/%m/%Y')}."
            )
            return

    stagione = settings.stagione_corrente()
    data_label = as_of.strftime("%d/%m/%Y") if as_of else "attuale"
    await update.effective_message.reply_text(
        f"⏳ Generazione roster <b>{team['nome']}</b> — {data_label}...",
        parse_mode="HTML",
    )

    # Controlla roster non vuoto prima di invocare Typst
    if as_of:
        roster_check = db.get_roster_team_at(team["id"], as_of.isoformat())
    else:
        roster_check = db.get_roster_team(team["id"])
    if not roster_check:
        await update.effective_message.reply_text(
            f"⚠️ Nessun giocatore nel roster di <b>{team['nome']}</b>"
            + (f" al {data_label}" if as_of else "") + ".",
            parse_mode="HTML",
        )
        return

    png_path = None
    try:
        png_path = await _genera_roster_png(team, stagione, as_of=as_of)
        caption = f"🏀 {team['nome']} — Stagione {stagione}"
        if as_of:
            caption += f"\n📅 al {data_label}"
        with open(png_path, "rb") as f:
            await update.effective_message.reply_photo(photo=f, caption=caption)
    except Exception as e:
        logger.error("Errore roster %s: %s", team["id"], e)
        await update.effective_message.reply_text(f"❌ Errore: {e}")
    finally:
        if png_path and os.path.exists(png_path):
            os.unlink(png_path)


def _build_picks_str(picks: list, team_id: str) -> str:
    """Costruisce la stringa pick per Typst: 'anno|round|by;...'
    Include tutti gli anni da stagione+1 a max_pick_anno anche se vuoti.
    """
    stagione_int = int(settings.stagione_corrente())
    max_anno     = db.get_max_pick_anno() or stagione_int + 1

    # Indice picks per anno
    picks_per_anno: dict[int, list] = {a: [] for a in range(stagione_int + 1, max_anno + 1)}
    for p in picks:
        anno = int(p["anno"])
        if anno in picks_per_anno:
            picks_per_anno[anno].append(p)

    righe = []
    for anno in sorted(picks_per_anno):
        anno_picks = picks_per_anno[anno]
        if not anno_picks:
            righe.append(f"{anno}||")  # anno vuoto — Typst mostra cella senza pick
        else:
            for p in anno_picks:
                rnd = "1st" if p["round"] == 1 else "2nd"
                if p.get("proprietario_orig") == team_id:
                    by = "Propria"
                else:
                    t = tm.get_team_by_id(p.get("proprietario_orig", ""))
                    by = t["nome"] if t else p.get("proprietario_orig", "")
                righe.append(f"{anno}|{rnd}|{by}")
    return ";".join(righe)


def _build_diritti_str(diritti: list) -> str:
    """Costruisce la stringa diritti per Typst: 'Nome (#NN AAAA), ...'"""
    parts = []
    for d in diritti:
        pick = d.get("pick_numero", "?")
        anno = d.get("anno_draft", "?")
        parts.append(f"{d['nome_common']} (#{pick} {anno})")
    return ", ".join(parts)


async def _genera_assets_png(team: dict, stagione: str) -> str:
    """Genera il PNG assets (roster + pick + diritti) tramite Typst."""
    team_id = team["id"]

    roster   = db.get_roster_team(team_id)
    contratti = db.get_contratti_team(team_id)
    picks    = db.get_pick_team(team_id)
    diritti  = db.get_diritti_2nd_team(team_id)

    giocatori_str = _build_giocatori_str(roster, contratti)
    picks_str     = _build_picks_str(picks, team_id)
    diritti_str   = _build_diritti_str(diritti)

    cap_contratti = sum(r.get("importo", 0) for r in roster)
    impatti       = db.get_impatto_taglio_team(team_id, stagione)
    cap_impatto   = sum(i.get("importo", 0) for i in impatti)
    cap_totale    = cap_contratti + cap_impatto
    salary_detail = f"{cap_contratti}+{cap_impatto}" if cap_impatto > 0 else str(cap_contratti)

    eta_list = [_eta(r.get("data_nascita")) for r in roster]
    eta_list = [e for e in eta_list if e is not None]
    eta_str  = f"{sum(eta_list)/len(eta_list):.1f}" if eta_list else "—"

    logo = _logo_path(team_id)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()

    cmd = [
        "typst", "compile",
        "--input", f"team_nome={team['nome']}",
        "--input", f"team_gm={team.get('gm_nome', '')}",
        "--input", f"colore_header={team.get('colore_header', '#1A237E')}",

        "--input", f"colore_riga1={team.get('colore_riga1', '')}",
        "--input", f"colore_riga2={team.get('colore_riga2', '')}",
        "--input", f"colore_sezione={team.get('colore_sezione', '')}",
        "--input", f"colore_pick={team.get('colore_pick', '')}",
        "--input", f"colore_diritti={team.get('colore_diritti', '')}",
        "--input", f"text_on_riga1={_text_on(team.get('colore_riga1', ''))}",
        "--input", f"text_on_riga2={_text_on(team.get('colore_riga2', ''))}",
        "--input", f"text_on_sezione={_text_on(team.get('colore_sezione', ''))}",
        "--input", f"text_on_sezione_muted={_text_on_muted(team.get('colore_sezione', ''))}",
        "--input", f"text_on_footer={_text_on(_footer_color(team.get('colore', '#1A237E'), team.get('colore_sezione', '')))}",
        "--input", f"text_on_footer_muted={_text_on_muted(_footer_color(team.get('colore', '#1A237E'), team.get('colore_sezione', '')))}",
        "--input", f"text_on_pick={_text_on(team.get('colore_pick', ''))}",
        "--input", f"text_on_pick_muted={_text_on_muted(team.get('colore_pick', ''))}",
        "--input", f"text_on_dir={_text_on(team.get('colore_diritti', ''))}",
        "--input", f"salary_cap={cap_totale}",
        "--input", f"salary_detail={salary_detail}",
        "--input", f"eta_media={eta_str}",
        "--input", f"logo_path={logo}",
        "--input", f"giocatori={giocatori_str}",
        "--input", f"picks={picks_str}",
        "--input", f"diritti={diritti_str}",
        os.path.abspath(ASSETS_TEMPLATE),
        tmp.name,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Typst assets error: %s", result.stderr)
        raise RuntimeError(f"Errore Typst: {result.stderr[:300]}")

    return tmp.name


async def cmd_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /assets [team_id]
    Genera il PNG con roster, pick e diritti.
    """
    user = update.effective_user
    args = context.args or []

    team = None
    for arg in args:
        team = tm.get_team_by_id(arg)
        if not team:
            await update.effective_message.reply_text(f"❌ Team '{arg}' non trovato.")
            return

    if team is None:
        team = tm.get_team_by_gm(user.id)
        if not team:
            await update.effective_message.reply_text(
                "⛔ Non sei registrato come GM. Usa /assets <team_id>."
            )
            return

    stagione = settings.stagione_corrente()
    await update.effective_message.reply_text(
        f"⏳ Generazione asset <b>{team['nome']}</b>...",
        parse_mode="HTML",
    )

    png_path = None
    try:
        png_path = await _genera_assets_png(team, stagione)
        with open(png_path, "rb") as f:
            await update.effective_message.reply_photo(
                photo=f,
                caption=f"🏀 <b>{team['nome']}</b> — Asset completi {stagione}",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error("Errore generazione assets: %s", e)
        await update.effective_message.reply_text(f"❌ Errore: {e}")
    finally:
        if png_path and os.path.exists(png_path):
            os.unlink(png_path)


def get_handlers() -> list:
    return [
        CommandHandler("roster", cmd_roster),
        CommandHandler("assets", cmd_assets),
    ]

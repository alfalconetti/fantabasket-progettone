"""
Congelamento delle notti e delle giornate, correzioni dei tabellini.

v58 (Luca, 30/10: come Yahoo, per coerenza; sostituisce la regola delle «ultime 3 giornate» della v56):
ogni **notte** NBA si ricontrolla solo fino alle **20:00 (Roma) del giorno dopo** (`orari.controllo_notte`).
Alle 20 il controllo finale (handlers_risultati.job_controllo_finale) la riscarica un'ultima volta e chiede
agli admin di verificare su Yahoo gli eventuali cambi (✅ uguale · ❌ non corrisponde: tornano i valori di
prima); poi la notte è **congelata**: niente più riscarichi (nba.scarica_tabellini salta le partite di una
notte congelata che hanno già il tabellino), nemmeno col calcolo delle 7:45 o /ricalcola. Una giornata è
congelata quando lo sono tutte le sue notti.
A mano (vale più della regola): /congela_notte GG/MM, /scongela_notte GG/MM, e per una giornata intera
/congela N, /scongela N. Stato: /congelamento (giornate), /congelamento_notti (notti).
Ogni /congela, /scongela e /correggi_tabellino va nel registro, nel canale log e sul canale principale.

/correggi_tabellino GIOCATORE GN VALORE [DD/MM] (admin): i fantapunti di un giocatore in una partita della
giornata, senza riscaricare; poi /ricalcola N e la convalida (che aggiorna il messaggio dei risultati ufficiali
e, solo se cambia chi vince, manda l'avviso sul canale).

Playoff (da fare col tabellone): nessun ricontrollo, punteggi congelati quando inizia la giornata dopo; dalla
generazione del tabellone stop anche ai ricontrolli della regular season.
"""
import html
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import config
import db
import nba
from numeri import testo as tp

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
# statistiche del tabellino, coi nomi per i messaggi dei cambi (Luca, 30/10: il dettaglio di cosa è cambiato)
STATISTICHE = (("minuti", "minuti"), ("pts", "punti"), ("fgm", "tiri dal campo segnati"), ("fga", "tiri dal campo tentati"),
               ("tpm", "triple segnate"), ("tpa", "triple tentate"), ("ftm", "liberi segnati"), ("fta", "liberi tentati"),
               ("oreb", "rimbalzi offensivi"), ("dreb", "rimbalzi difensivi"), ("ast", "assist"), ("stl", "recuperi"),
               ("blk", "stoppate"), ("tov", "palle perse"))


def e(x) -> str:
    return html.escape(str(x), quote=False)


def migra() -> None:
    db.q("""CREATE TABLE IF NOT EXISTS lega_congelamento (
              stagione  TEXT NOT NULL,
              giornata  INT  NOT NULL,
              congelata BOOLEAN NOT NULL,                 -- scelta a mano: vale più della regola
              da        BIGINT,
              quando    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (stagione, giornata))""")
    db.q("""CREATE TABLE IF NOT EXISTS lega_notti_congelate (
              data_et   DATE PRIMARY KEY,                 -- notte NBA (giorno della costa est); scelta a mano
              congelata BOOLEAN NOT NULL,
              da        BIGINT,
              quando    TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    db.q("""CREATE TABLE IF NOT EXISTS lega_controlli_notte (
              id        SERIAL PRIMARY KEY,
              data_et   DATE NOT NULL,
              giornata  INT,
              prima     JSONB NOT NULL,                   -- righe di tabellino di prima dei cambi (per «non corrisponde»)
              dopo      JSONB NOT NULL,
              stato     TEXT NOT NULL DEFAULT 'da verificare',   -- da verificare / uguale / tenuti_prima; notti prima della giornata: da applicare / aggiornato / lasciato
              messaggio BIGINT,
              chi       TEXT,
              quando    TIMESTAMPTZ NOT NULL DEFAULT NOW())""")


def oggi_et():
    return datetime.now(nba.ET).date()


def adesso() -> datetime:
    return datetime.now(timezone.utc)


def fine_notte(d: date) -> datetime:
    """Quando la notte d (giorno ET) si congela: alle 20 (orari.controllo_notte) del giorno dopo, a Roma."""
    from shared import regole
    return datetime.combine(d + timedelta(days=1), regole.orario("controllo_notte"), ROMA)


def _mano_notti() -> dict:
    migra()
    return {r["data_et"]: r["congelata"] for r in db.q("SELECT data_et, congelata FROM lega_notti_congelate", many=True) or []}


def _mano_giornate(s: str) -> dict:
    migra()
    return {r["giornata"]: r["congelata"] for r in db.q("SELECT giornata, congelata FROM lega_congelamento WHERE stagione = %s",
                                                           (s,), many=True) or []}


def giornata_di(s: str, d: date) -> dict | None:
    return next((g for g in db.giornate(s) if g["dal"] <= d <= g["al"]), None)


def notte_congelata(d: date, s: str | None = None, ora: datetime | None = None, _mn=None, _mg=None, _g=None) -> bool:
    """La notte d non si riscarica più? A mano la notte, poi a mano la sua giornata, poi la regola delle 20."""
    mn = _mano_notti() if _mn is None else _mn
    if d in mn:
        return mn[d]
    s = s or config.stagione()
    g = _g if _g is not None else giornata_di(s, d)
    if g:
        mg = _mano_giornate(s) if _mg is None else _mg
        if g["numero"] in mg:
            return mg[g["numero"]]
    return (ora or adesso()) >= fine_notte(d)


def notti(g: dict) -> list[date]:
    return [g["dal"] + timedelta(days=i) for i in range((g["al"] - g["dal"]).days + 1)]


def stati(s: str, ora: datetime | None = None) -> dict[int, dict]:
    """{numero: {stato: 'da giocare'|'in corso'|'aperta'|'congelata', a_mano: bool, g: giornata}}: aperta = finita
    con almeno una notte non ancora congelata; congelata = tutte le notti congelate."""
    ora = ora or adesso()
    oggi = ora.astimezone(nba.ET).date()
    mn, mg = _mano_notti(), _mano_giornate(s)
    out = {}
    for g in db.giornate(s):
        n = g["numero"]
        if g["al"] >= oggi:
            out[n] = {"stato": "in corso" if g["dal"] <= oggi else "da giocare", "a_mano": False, "g": g}
            continue
        if n in mg:
            out[n] = {"stato": "congelata" if mg[n] else "aperta", "a_mano": True, "g": g}
            continue
        ferme = [notte_congelata(d, s, ora, mn, mg, g) for d in notti(g)]
        out[n] = {"stato": "congelata" if all(ferme) else "aperta", "a_mano": any(d in mn for d in notti(g)), "g": g}
    return out


def congelata(s: str, n: int) -> bool:
    """True se la giornata non si ricontrolla più (tutte le sue notti congelate)."""
    return (stati(s).get(n) or {}).get("stato") == "congelata"


def da_tenere(partite: list[str]) -> set[str]:
    """Le partite da NON riscaricare: con il tabellino già preso e la notte congelata (v58)."""
    if not partite:
        return set()
    righe = db.q("SELECT espn_id, data_et FROM nba_partite WHERE espn_id = ANY(%s) AND tabellino IS NOT NULL",
                 (list(partite),), many=True) or []
    if not righe:
        return set()
    s, mn = config.stagione(), _mano_notti()
    mg = _mano_giornate(s)
    cache = {}
    out = set()
    for r in righe:
        d = r["data_et"]
        if d not in cache:
            cache[d] = notte_congelata(d, s, None, mn, mg)
        if cache[d]:
            out.add(r["espn_id"])
    return out


# ── righe di tabellino e cambi, col dettaglio delle statistiche ────────────────

def righe(partite: list[str]) -> dict:
    """{(partita, atleta): riga completa} dei tabellini salvati."""
    if not partite:
        return {}
    return {(r["partita"], r["atleta"]): dict(r) for r in db.q("SELECT * FROM nba_tabellini WHERE partita = ANY(%s)",
                                                              (list(partite),), many=True) or []}


def _uguali(a: dict | None, b: dict | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a["fp"]) - float(b["fp"])) < 0.001 and all(int(a.get(k) or 0) == int(b.get(k) or 0) for k, _ in STATISTICHE)


def cambi(prima: dict, dopo: dict) -> dict:
    return {k: (prima.get(k), dopo.get(k)) for k in set(prima) | set(dopo) if not _uguali(prima.get(k), dopo.get(k))}


def dettaglio(a: dict | None, b: dict | None) -> str:
    """«rimbalzi difensivi 4 → 5, assist 3 → 4»: le statistiche cambiate."""
    if a is None:
        return "nuovo nel tabellino"
    if b is None:
        return "tolto dal tabellino"
    pezzi = [f"{nome} {int(a.get(k) or 0)} → {int(b.get(k) or 0)}" for k, nome in STATISTICHE
             if int(a.get(k) or 0) != int(b.get(k) or 0)]
    return ", ".join(pezzi) or "statistiche uguali"


def riga_cambio(a: dict | None, b: dict | None) -> str:
    x = b or a
    fa = tp(float(a["fp"])) if a else "—"
    fb = tp(float(b["fp"])) if b else "—"
    return f"• {e(x['nome'])}: {fa} → <b>{fb}</b> ({e(dettaglio(a, b))})"


def schierati(s: str, n: int) -> set[str]:
    """Id ESPN dei giocatori schierati nella giornata (quintetti e panchine)."""
    import risultati as R
    ids = set()
    for sq in R.schieramenti(s, n).values():
        ids |= {x for x in sq["quintetto"].values() if x} | {r.get("giocatore_id") for r in (sq["panchina"] or []) if r.get("giocatore_id")}
    if not ids:
        return set()
    return {r["espn_id"] for r in db.q("SELECT espn_id FROM giocatori WHERE id = ANY(%s) AND espn_id IS NOT NULL",
                                       (list(ids),), many=True) or []}


# ── comandi ────────────────────────────────────────────────────────────────────

def _chi(update) -> str:
    u = update.effective_user
    return u.full_name or str(u.id)


async def _annuncia(bot, testo: str) -> None:
    """Canale log e canale principale (Luca, 26/10: per correttezza)."""
    from handlers import log
    await log(bot, testo)
    canale = config.globali().get("main_channel_id")
    if canale:
        try:
            await bot.send_message(chat_id=canale, text=testo, parse_mode="HTML")
        except Exception as err:
            logger.warning("Canale principale: %s", err)


def _numero(x: str) -> int | None:
    m = re.fullmatch(r"[Gg]?(\d+)", x or "")
    return int(m.group(1)) if m else None


async def _cambia(update: Update, context: ContextTypes.DEFAULT_TYPE, congela: bool):
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    s = config.stagione()
    n = _numero((context.args or [""])[0])
    st = stati(s)
    if not n or n not in st:
        await msg.reply_text(f"Uso: /{'congela' if congela else 'scongela'} N (es. /{'congela' if congela else 'scongela'} 3)")
        return
    if st[n]["stato"] in ("in corso", "da giocare"):
        await msg.reply_text(f"La giornata {n} non è ancora finita: si congela o scongela solo una giornata finita.")
        return
    prima = st[n]["stato"]
    db.q("""INSERT INTO lega_congelamento (stagione, giornata, congelata, da) VALUES (%s, %s, %s, %s)
            ON CONFLICT (stagione, giornata) DO UPDATE SET congelata = EXCLUDED.congelata, da = EXCLUDED.da, quando = NOW()""",
         (s, n, congela, update.effective_user.id))
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "giornata congelata" if congela else "giornata scongelata",
               oggetto=f"giornata {n}", prima=prima, dopo="congelata" if congela else "aperta")
    testo = (f"🧊 <b>Giornata {n} congelata</b> da {e(_chi(update))}: i suoi tabellini non si riscaricano più da ESPN."
             if congela else
             f"🔓 <b>Giornata {n} scongelata</b> da {e(_chi(update))}: i suoi tabellini si ricontrollano di nuovo "
             f"(/ricalcola riscarica da ESPN tutte le sue notti).")
    await _annuncia(context.bot, testo)
    await msg.reply_text(testo + "\nLo stato di tutte: /congelamento", parse_mode="HTML")


async def cmd_congela(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _cambia(update, context, True)


async def cmd_scongela(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _cambia(update, context, False)


def testo_congelamento(s: str) -> str:
    st = stati(s)
    icone = {"aperta": "🔄", "congelata": "🧊", "in corso": "🔴", "da giocare": "⏳"}
    righe = ["🧊 <b>Congelamento delle giornate</b>", ""]
    for n in sorted(st):
        x = st[n]
        if x["stato"] == "da giocare" and n > min([m for m, y in st.items() if y["stato"] == "da giocare"] or [n]):
            continue                                  # delle future basta la prossima
        righe.append(f"{icone[x['stato']]} G{n} ({x['g']['dal']:%d/%m}–{x['g']['al']:%d/%m}): {x['stato']}"
                     + (" <i>(a mano)</i>" if x["a_mano"] else ""))
    righe += ["", "🔄 aperta: almeno una notte si ricontrolla ancora (fino alle 20 del giorno dopo, o scongelata a mano) · "
                  "🧊 congelata: tabellini fermi, /ricalcola non riscarica · 🔴 in corso · ⏳ da giocare",
              "Le notti una per una: /congelamento_notti",
              "Cambiare: /congela N · /scongela N · correggere un punteggio: /correggi_tabellino GIOCATORE GN VALORE [GG/MM]"]
    return "\n".join(righe)


async def cmd_congelamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    await update.effective_message.reply_text(testo_congelamento(config.stagione()), parse_mode="HTML")


def leggi_correzione(args: list[str]) -> tuple[str, int, float, tuple[int, int] | None] | None:
    """GIOCATORE GN VALORE [DD/MM] → (nome, n, valore, (giorno, mese) o None)."""
    a = list(args)
    data = None
    if a and re.fullmatch(r"\d{1,2}/\d{1,2}", a[-1]):
        d, m = a.pop().split("/")
        data = (int(d), int(m))
    if len(a) < 3:
        return None
    try:
        valore = float(a[-1].replace(",", "."))
    except ValueError:
        return None
    n = _numero(a[-2])
    if n is None:
        return None
    return " ".join(a[:-2]), n, valore, data


async def cmd_correggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/correggi_tabellino GIOCATORE GN VALORE [DD/MM] (admin)."""
    msg = update.effective_message
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    uso = "Uso: /correggi_tabellino GIOCATORE GN VALORE [GG/MM] (es. /correggi_tabellino Norman Powell G1 16)"
    x = leggi_correzione(context.args or [])
    if not x:
        await msg.reply_text(uso)
        return
    nome, n, valore, data = x
    s = config.stagione()
    g = db.giornata(s, n)
    if not g:
        await msg.reply_text(f"La giornata {n} non c'è.")
        return
    import player
    trovati = [t for t in player.cerca(nome) if t.get("espn_id")]
    if len(trovati) != 1 and not (trovati and player.calcolo.norm(trovati[0]["nome_common"]) == player.calcolo.norm(nome)):
        await msg.reply_text(f"Nessun giocatore (abbinato a ESPN) si chiama «{nome}»." if not trovati else
                             "Più giocatori: " + ", ".join(t["nome_common"] for t in trovati[:6]) + ". Scrivi il nome completo.")
        return
    gioc = trovati[0]
    righe = db.q("""SELECT t.partita, t.fp, p.data_et FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                    WHERE t.atleta = %s AND p.data_et BETWEEN %s AND %s ORDER BY p.inizio""",
                 (gioc["espn_id"], g["dal"], g["al"]), many=True) or []
    if data:
        righe = [r for r in righe if (r["data_et"].day, r["data_et"].month) == data]
    if not righe:
        await msg.reply_text(f"{gioc['nome_common']} non ha tabellini nella giornata {n}"
                             + (f" il {data[0]:02d}/{data[1]:02d}." if data else "."))
        return
    if len(righe) > 1:
        await msg.reply_text(f"{gioc['nome_common']} ha {len(righe)} partite nella giornata {n}: aggiungi la data, es. "
                             + " · ".join(f"/correggi_tabellino {gioc['nome_common']} G{n} {tp(valore)} {r['data_et']:%d/%m}"
                                          for r in righe))
        return
    r = righe[0]
    prima = float(r["fp"])
    db.q("UPDATE nba_tabellini SET fp = %s WHERE partita = %s AND atleta = %s", (valore, r["partita"], gioc["espn_id"]))
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "tabellino corretto", oggetto=f"giornata {n}, {gioc['nome_common']} ({r['data_et']:%d/%m})",
               prima=tp(prima), dopo=tp(valore))
    testo = (f"✏️ <b>Correzione G{n}</b>: {e(gioc['nome_common'])} ({r['data_et']:%d/%m}) {tp(prima)} → <b>{tp(valore)}</b> "
             f"fantapunti (admin {e(_chi(update))})")
    await _annuncia(context.bot, testo)
    await msg.reply_text(testo + f"\n\nOra /ricalcola {n} e la convalida per aggiornare i risultati."
                         + (f"\n⚠️ La notte del {r['data_et']:%d/%m} è ancora aperta: il controllo delle 20 o /ricalcola "
                            f"riscaricano da ESPN e possono rimettere il valore di ESPN. Per tenerla: /congela_notte {r['data_et']:%d/%m}"
                            if not notte_congelata(r["data_et"], s) else ""), parse_mode="HTML")


# ── le notti (v58) ─────────────────────────────────────────────────────────────

def leggi_data(x: str, s: str | None = None) -> date | None:
    """GG/MM → la data della stagione (da luglio l'anno della stagione, prima quello dopo)."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", x or "")
    if not m:
        return None
    d, mese = int(m.group(1)), int(m.group(2))
    anno = int(m.group(3)) if m.group(3) else int(s or config.stagione()) + (0 if mese >= 7 else 1)
    anno += 2000 if anno < 100 else 0
    try:
        return date(anno, mese, d)
    except ValueError:
        return None


async def _cambia_notte(update: Update, context: ContextTypes.DEFAULT_TYPE, congela: bool):
    msg = update.effective_message
    nome = "congela_notte" if congela else "scongela_notte"
    if not config.is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Solo admin.")
        return
    d = leggi_data((context.args or [""])[0])
    if not d:
        await msg.reply_text(f"Uso: /{nome} GG/MM (la notte NBA, giorno della costa est; es. /{nome} 29/10)")
        return
    if d >= oggi_et():
        await msg.reply_text(f"La notte del {d:%d/%m} non è ancora finita.")
        return
    prima = "congelata" if notte_congelata(d) else "aperta"
    migra()
    db.q("""INSERT INTO lega_notti_congelate (data_et, congelata, da) VALUES (%s, %s, %s)
            ON CONFLICT (data_et) DO UPDATE SET congelata = EXCLUDED.congelata, da = EXCLUDED.da, quando = NOW()""",
         (d, congela, update.effective_user.id))
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "notte congelata" if congela else "notte scongelata",
               oggetto=f"notte del {d:%d/%m}", prima=prima, dopo="congelata" if congela else "aperta")
    testo = (f"🧊 <b>Notte del {d:%d/%m} congelata</b> da {e(_chi(update))}: i suoi tabellini non si riscaricano più da ESPN."
             if congela else
             f"🔓 <b>Notte del {d:%d/%m} scongelata</b> da {e(_chi(update))}: i suoi tabellini si possono riscaricare "
             f"(/ricalcola, o /controllo_notte {d:%d/%m}).")
    await _annuncia(context.bot, testo)
    await msg.reply_text(testo + "\nLo stato delle notti: /congelamento_notti", parse_mode="HTML")


async def cmd_congela_notte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _cambia_notte(update, context, True)


async def cmd_scongela_notte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _cambia_notte(update, context, False)


def testo_notti(s: str, ora: datetime | None = None) -> str:
    """Le notti delle ultime due giornate iniziate (e quelle scelte a mano), con lo stato."""
    ora = ora or adesso()
    oggi = ora.astimezone(nba.ET).date()
    mn, mg = _mano_notti(), _mano_giornate(s)
    iniziate = [g for g in db.giornate(s) if g["dal"] <= oggi][-2:]
    righe_ = ["🌙 <b>Congelamento delle notti</b>", ""]
    viste = set()
    for g in iniziate:
        for d in notti(g):
            if d > oggi:
                continue
            viste.add(d)
            if d >= oggi:
                righe_.append(f"🔴 {d:%d/%m} (G{g['numero']}): in corso")
                continue
            ferma = notte_congelata(d, s, ora, mn, mg, g)
            fine = fine_notte(d).astimezone(ROMA)
            mano = " <i>(a mano)</i>" if d in mn else " <i>(giornata a mano)</i>" if g["numero"] in mg else ""
            righe_.append(f"{'🧊' if ferma else '🔄'} {d:%d/%m} (G{g['numero']}): "
                          + (f"congelata{mano}" if ferma else f"aperta fino al {fine:%d/%m} alle {fine:%H:%M}{mano}"))
    altre = sorted(d for d in mn if d not in viste)
    if altre:
        righe_ += ["", "Scelte a mano su notti più vecchie:"] + [f"{'🧊' if mn[d] else '🔄'} {d:%d/%m}" for d in altre]
    righe_ += ["", "Ogni notte si ricontrolla fino alle 20 del giorno dopo (controllo finale, poi congelata). "
                   "Cambiare: /congela_notte GG/MM · /scongela_notte GG/MM"]
    return "\n".join(righe_)


async def cmd_congelamento_notti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not config.is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Solo admin.")
        return
    await update.effective_message.reply_text(testo_notti(config.stagione()), parse_mode="HTML")


def get_handlers() -> list:
    return [CommandHandler("congela", cmd_congela), CommandHandler("scongela", cmd_scongela),
            CommandHandler("congelamento", cmd_congelamento), CommandHandler("correggi_tabellino", cmd_correggi),
            CommandHandler("congela_notte", cmd_congela_notte), CommandHandler("scongela_notte", cmd_scongela_notte),
            CommandHandler("congelamento_notti", cmd_congelamento_notti)]

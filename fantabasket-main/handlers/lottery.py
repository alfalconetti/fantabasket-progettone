"""
Sanzioni delle penalità e lottery del draft (v7.27.1, Luca 23/11). Il sorteggio è in shared/lottery.py (matrice e
algoritmo di Henry, seme da drand); la classifica finale la salva loucabot (shared/lottery_vista.py).

1. **Sanzioni** (passaggio a offseason-break): il bot conta le penalità non revocate della stagione e le scrive in
   `sanzioni`; riepilogo agli admin da confermare (✅), poi sul canale. La stagione dopo si riparte da zero (le
   penalità sono per stagione). L'effetto si decide **al momento della lottery**, da chi possiede le proprie pick:
   - propria 1st e propria 2nd: tutte e due scendono di una posizione ogni 3 penalità (per difetto);
   - solo la propria 1st: scende solo la 1st; solo la propria 2nd: la 2nd scende ogni 3 e cap −1M ogni 4;
   - nessuna delle due: cap −1M ogni 3. Il cap ridotto vale per la stagione dopo (`/set_cap_penalizzato`, lo dice il
     bot agli admin).
2. **Lottery nella fase draft** (Luca, 23/11): al passaggio alla fase draft il bot ricorda agli admin di fissare il
   momento (`/lottery_quando GG/MM HH:MM`). Sul canale: data e ora, round drand, seed (dall'ultima), impronta del
   codice, come rifarla (`strumenti/lottery_verifica.py`).
3. **All'ora** (`job_lottery`, ogni 20 secondi): randomness del round confermata da due relay (se non c'è ancora si
   aspetta: vale il round dichiarato), estrazione, poi **una pick al minuto dalla 12ª alla 1ª** sul canale, già con
   le discese; se una pick svelata dopo ne sposta una già uscita il messaggio lo dice. Alla fine l'ordine dei due giri
   del draft scritto in `draft_scelte` (`/draft_ordine` resta per le correzioni).
"""
import html
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db
import settings
import teams as tm
from shared import lottery as LT
from shared import lottery_vista as LV

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
PAUSA = timedelta(seconds=60)                 # tra una pick svelata e l'altra


def migra() -> None:
    db._q(LV.TABELLA)
    db._q("""CREATE TABLE IF NOT EXISTS sanzioni (
               stagione    TEXT NOT NULL,
               team_id     TEXT NOT NULL,
               penalita    INT NOT NULL,
               confermate  BOOLEAN NOT NULL DEFAULT FALSE,
               PRIMARY KEY (stagione, team_id))""")
    db._q("""CREATE TABLE IF NOT EXISTS lottery (
               anno        TEXT PRIMARY KEY,
               quando      TIMESTAMPTZ NOT NULL,
               round       INT NOT NULL,
               seed        JSONB NOT NULL,
               impronta    TEXT NOT NULL,
               stato       TEXT NOT NULL DEFAULT 'annunciata' CHECK (stato IN ('annunciata', 'estratta', 'svelata')),
               randomness  TEXT,
               estratto    JSONB,
               passo       INT NOT NULL DEFAULT 0,
               ultimo      TIMESTAMPTZ)""")


def _nome(t: str) -> str:
    x = tm.get_team_by_id(t)
    return x["nome"] if x else t


def _gm(t: str) -> str:
    x = tm.get_team_by_id(t) or {}
    return x.get("gm_nome") or x.get("nome") or t


# ── sanzioni ──────────────────────────────────────────────────────────────────

def conta_penalita(stagione: str) -> dict[str, int]:
    rr = db._q("SELECT team_id, COUNT(*) AS n FROM penalita WHERE stagione = %s AND revocata IS NULL GROUP BY team_id",
               (str(stagione),), many=True) or []
    return {r["team_id"]: int(r["n"]) for r in rr}


def effetti(n: int, propria1: bool, propria2: bool) -> dict:
    """{"giu1", "giu2", "cap"} dal numero di penalità e da quali proprie pick la squadra ha in mano."""
    if propria1 and propria2:
        return {"giu1": n // 3, "giu2": n // 3, "cap": 0}
    if propria1:
        return {"giu1": n // 3, "giu2": 0, "cap": 0}
    if propria2:
        return {"giu1": 0, "giu2": n // 3, "cap": n // 4}
    return {"giu1": 0, "giu2": 0, "cap": n // 3}


def sanzioni_anno(anno: str) -> dict[str, dict]:
    """Per il draft `anno` (stagione delle penalità = anno − 1): {squadra: {n, giu1, giu2, cap, propria1, propria2}}
    con chi ha le pick adesso."""
    st = str(int(anno) - 1)
    rr = db._q("SELECT team_id, penalita FROM sanzioni WHERE stagione = %s", (st,), many=True)
    n = {r["team_id"]: int(r["penalita"]) for r in rr} if rr else conta_penalita(st)
    ha1, ha2 = LV.chi_ha(anno, 1), LV.chi_ha(anno, 2)
    out = {}
    for t, k in n.items():
        if k <= 0:
            continue
        p1, p2 = ha1.get(t) == t, ha2.get(t) == t
        out[t] = {"n": k, "propria1": p1, "propria2": p2, **effetti(k, p1, p2)}
    return out


def testo_sanzioni(anno: str) -> str:
    s = sanzioni_anno(anno)
    if not s:
        return f"⚖️ <b>Sanzioni per il draft {anno}</b>: nessuna squadra con penalità."
    righe = []
    for t, x in sorted(s.items(), key=lambda kv: -kv[1]["n"]):
        eff = []
        if x["giu1"]:
            eff.append(f"1st −{x['giu1']}")
        if x["giu2"]:
            eff.append(f"2nd −{x['giu2']}")
        if x["cap"]:
            eff.append(f"cap −{x['cap']}M la stagione dopo")
        pick = ("ha la propria 1st e la propria 2nd" if x["propria1"] and x["propria2"] else "ha solo la propria 1st" if x["propria1"]
                else "ha solo la propria 2nd" if x["propria2"] else "non ha le proprie pick")
        righe.append(f"• {html.escape(_nome(t))}: {x['n']} penalità, {pick} → " + (", ".join(eff) or "nessun effetto"))
    return (f"⚖️ <b>Sanzioni per il draft {anno}</b> (penalità della stagione {int(anno) - 1})\n" + "\n".join(righe) +
            "\n<i>Le discese dipendono da chi ha le pick al momento della lottery: fino ad allora possono cambiare.</i>")


async def passaggio_break(bot) -> str:
    """Al passaggio a offseason-break: le penalità della stagione diventano sanzioni, riepilogo agli admin."""
    st = str(settings.stagione_corrente())
    n = conta_penalita(st)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sanzioni WHERE stagione = %s", (st,))
            for t, k in n.items():
                cur.execute("INSERT INTO sanzioni (stagione, team_id, penalita) VALUES (%s, %s, %s)", (st, t, k))
    gr = settings.admin_group_id()
    anno = str(int(st) + 1)
    if gr:
        await bot.send_message(chat_id=gr, parse_mode="HTML", text=testo_sanzioni(anno),
                               reply_markup=K([[B("✅ Conferma e pubblica", callback_data=f"lsz:ok:{st}")]]))
    return f"\n⚖️ Sanzioni: {len(n)} squadre con penalità, riepilogo agli admin"


async def cb_sanzioni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not settings.is_admin(q.from_user.id):
        await q.answer("Solo gli admin.", show_alert=True)
        return
    st = q.data.split(":")[2]
    await q.answer()
    db._q("UPDATE sanzioni SET confermate = TRUE WHERE stagione = %s", (st,))
    testo = testo_sanzioni(str(int(st) + 1))
    await q.edit_message_text(testo + f"\n\n✅ Confermate da {html.escape(q.from_user.first_name or 'admin')}", parse_mode="HTML")
    ch = settings.load_globals().get("main_channel_id")
    if ch:
        await context.bot.send_message(chat_id=ch, text=testo, parse_mode="HTML")
    from handlers.registro import segna
    await segna(context.bot, q.from_user, "admin", "sanzioni confermate", oggetto=f"stagione {st}")


# ── lottery: annuncio ─────────────────────────────────────────────────────────

def stato(anno: str) -> dict | None:
    return db._q("SELECT * FROM lottery WHERE anno = %s", (str(anno),), one=True)


def _seed(anno: str) -> list[str]:
    return LV.seed_lottery(str(int(anno) - 1))


def testo_annuncio(anno: str, r: dict) -> str:
    seed = r["seed"] if isinstance(r["seed"], list) else json.loads(r["seed"])
    q = r["quando"].astimezone(ROMA)
    nomi = ",".join(_nome(t) for t in seed)
    return (f"🎰 <b>Lottery del draft {anno}</b>: il {q:%d/%m} alle {q:%H:%M}.\n\n"
            f"Il seme è il round <b>{r['round']}</b> di drand (rete quicknet, League of Entropy), che esce a quell'ora: "
            "nessuno lo conosce prima, chiunque lo può leggere dopo.\n\n"
            "<b>Seed</b> (dall'ultima in classifica):\n" +
            "\n".join(f"{i}. {html.escape(_nome(t))}" for i, t in enumerate(seed, 1)) +
            f"\n\nOdds: la matrice del regolamento. Impronta del codice dell'estrazione (SHA-256 di shared/lottery.py): "
            f"<code>{r['impronta']}</code>\n"
            "Per rifarla: <code>python3 strumenti/lottery_verifica.py estrai --round "
            f"{r['round']} --squadre \"{html.escape(nomi)}\"</code>\n"
            "Le pick si svelano qui una al minuto, dalla 12ª alla 1ª, con le discese per le penalità.")


def leggi_quando(args: list[str]) -> datetime:
    from shared.date_comandi import leggi_data
    if len(args) < 2:
        raise ValueError("Uso: /lottery_quando GG/MM[/AAAA] HH:MM (ora di Roma)")
    d = leggi_data(args[0]) or leggi_data(f"{args[0]}/{datetime.now(ROMA).year}")
    if not d:
        raise ValueError(f"Data non chiara: «{args[0]}» (GG/MM o GG/MM/AAAA).")
    try:
        h, m = (int(x) for x in args[1].replace(".", ":").split(":"))
    except ValueError:
        raise ValueError("L'ora come HH:MM, es. 21:00.")
    q = datetime(d.year, d.month, d.day, h, m, tzinfo=ROMA)
    if q <= datetime.now(ROMA) + timedelta(minutes=10):
        raise ValueError("Il momento dell'estrazione va fissato almeno 10 minuti avanti.")
    return q


async def cmd_lottery_quando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/lottery_quando GG/MM HH:MM: fissa l'estrazione (solo nella fase draft, prima che parta)."""
    msg = update.effective_message
    if not settings.is_admin(update.effective_user.id):
        return
    anno = str(settings.stagione_corrente())
    if settings.fase() != "offseason-draft":
        await msg.reply_text("❌ La lottery si fa nella fase draft.")
        return
    r = stato(anno)
    if r and r["stato"] != "annunciata":
        await msg.reply_text("❌ L'estrazione è già fatta.")
        return
    seed = _seed(anno)
    if len(seed) != 12:
        await msg.reply_text(f"❌ Manca la classifica finale della stagione {int(anno) - 1} (la salva loucabot al blocco del "
                             f"tabellone dei playoff): squadre fuori dai playoff trovate {len(seed)} su 12.")
        return
    try:
        q = leggi_quando(context.args or [])
        rnd = LT.round_al(q)
    except (ValueError, LT.LotteryError) as er:
        await msg.reply_text(f"❌ {er}")
        return
    db._q("""INSERT INTO lottery (anno, quando, round, seed, impronta) VALUES (%s, %s, %s, %s, %s)
             ON CONFLICT (anno) DO UPDATE SET quando = EXCLUDED.quando, round = EXCLUDED.round, seed = EXCLUDED.seed,
             impronta = EXCLUDED.impronta""", (anno, q, rnd, json.dumps(seed), LT.impronta()))
    r = stato(anno)
    ch = settings.load_globals().get("main_channel_id")
    if ch:
        await context.bot.send_message(chat_id=ch, text=testo_annuncio(anno, r), parse_mode="HTML")
    from handlers.registro import segna
    await segna(context.bot, update.effective_user, "admin", "lottery fissata", oggetto=f"draft {anno}",
                dopo=f"{q:%d/%m %H:%M}, round {rnd}")
    await msg.reply_text(f"✅ Lottery fissata: {q:%d/%m alle %H:%M}, round drand {rnd}. Annunciata sul canale.")


# ── lottery: estrazione e reveal ──────────────────────────────────────────────

def ordine_primo_giro(anno: str, estratto: list[str]) -> tuple[list[str], dict[str, int]]:
    """(chi aveva la pick, dalla 1ª alla 24ª, già con le discese; {squadra: posizioni scese})."""
    s = sanzioni_anno(anno)
    giu = {t: x["giu1"] for t, x in s.items() if x["giu1"]}
    return LT.scendi(estratto + LV.fisse(str(int(anno) - 1)), giu), giu


def ordine_secondo_giro(anno: str) -> tuple[list[str], dict[str, int]]:
    s = sanzioni_anno(anno)
    giu = {t: x["giu2"] for t, x in s.items() if x["giu2"]}
    return LT.scendi(LV.secondo_giro(str(int(anno) - 1)), giu), giu


def parziale(anno: str, estratto: list[str], svelate: int) -> list[str | None]:
    """L'ordine del primo giro con le ultime `svelate` pick della lottery note (le altre None), con le discese: quello
    che si sa a quel punto del reveal."""
    noto = [None if i < 12 - svelate else t for i, t in enumerate(estratto)]
    segnaposto = [x if x else f"?{i}" for i, x in enumerate(noto)]
    s = sanzioni_anno(anno)
    giu = {t: x["giu1"] for t, x in s.items() if x["giu1"] and t in (set(t for t in noto if t) | set(LV.fisse(str(int(anno) - 1))))}
    fin = LT.scendi(segnaposto + LV.fisse(str(int(anno) - 1)), giu)
    return [None if x.startswith("?") else x for x in fin]


def testo_passo(anno: str, estratto: list[str], k: int) -> str:
    """Il messaggio della k-esima pick svelata (k = 1 → la 12ª)."""
    p = 13 - k                                      # posizione estratta che si svela
    t = estratto[p - 1]
    prima = parziale(anno, estratto, k - 1)
    ora = parziale(anno, estratto, k)
    s = sanzioni_anno(anno)
    riga = f"🎟 <b>Pick {p}</b> della lottery: <b>{html.escape(_nome(t))}</b>"
    pos = ora.index(t) + 1
    if s.get(t, {}).get("giu1"):
        riga += f", che per le penalità scende di {s[t]['giu1']} e va alla <b>{pos}ª</b>"
    mossi = [x for x in ora if x and x != t and x in prima and prima.index(x) != ora.index(x)]
    for x in mossi:
        riga += f"\n↕️ {html.escape(_nome(x))} {'sale' if ora.index(x) < prima.index(x) else 'scende'} alla {ora.index(x) + 1}ª"
    ha = LV.chi_ha(anno, 1)
    elenco = []
    for i, x in enumerate(ora[:14], 1):
        if x:
            via = f" (in mano a {html.escape(_nome(ha.get(x, x)))})" if ha.get(x, x) != x else ""
            elenco.append(f"{i}. {html.escape(_nome(x))}{via}")
    return riga + "\n\n" + "\n".join(elenco)


def scrivi_draft(anno: str) -> None:
    """L'ordine dei due giri in draft_scelte (al posto di quello che c'era), con le posizioni perse."""
    r = stato(anno)
    estratto = r["estratto"] if isinstance(r["estratto"], list) else json.loads(r["estratto"])
    g1, giu1 = ordine_primo_giro(anno, estratto)
    g2, giu2 = ordine_secondo_giro(anno)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO draft (anno) VALUES (%s) ON CONFLICT (anno) DO NOTHING", (anno,))
            cur.execute("DELETE FROM draft_scelte WHERE anno = %s AND stato <> 'fatta'", (anno,))
            for giro, ordine, giu in ((1, g1, giu1), (2, g2, giu2)):
                for i, t in enumerate(ordine, 1):
                    cur.execute("SELECT id FROM pick WHERE proprietario_orig = %s AND anno = %s AND round = %s", (t, anno, giro))
                    p = cur.fetchone()
                    if p:
                        cur.execute("INSERT INTO draft_scelte (anno, giro, numero, pick_id, penalita) VALUES (%s, %s, %s, %s, %s) "
                                    "ON CONFLICT (anno, numero) DO NOTHING", (anno, giro, i + (24 if giro == 2 else 0), p[0], giu.get(t, 0)))


async def passo(bot, ora: datetime | None = None) -> str | None:
    """Un passo della lottery (job ogni 20 secondi): estrazione all'ora fissata, poi una pick al minuto, poi l'ordine
    del draft. Restituisce cosa ha fatto (per le prove) o None."""
    ora = ora or datetime.now(timezone.utc)
    anno = str(settings.stagione_corrente())
    r = stato(anno)
    if not r or r["stato"] == "svelata" or ora < r["quando"]:
        return None
    ch = settings.load_globals().get("main_channel_id")
    if r["stato"] == "annunciata":
        try:
            val = LT.randomness(r["round"])
        except LT.LotteryError as er:
            logger.info("Lottery: %s, riprovo", er)
            return "attesa"
        seed = r["seed"] if isinstance(r["seed"], list) else json.loads(r["seed"])
        estratto = LT.estrai(seed, val)
        db._q("UPDATE lottery SET stato = 'estratta', randomness = %s, estratto = %s, passo = 0, ultimo = %s WHERE anno = %s",
              (val, json.dumps(estratto), ora - PAUSA, anno))
        if ch:
            await bot.send_message(chat_id=ch, parse_mode="HTML", text=(
                f"🎰 <b>Lottery del draft {anno}</b>: round drand {r['round']}, randomness <code>{val}</code>. "
                "Si parte dalla 12ª."))
        return "estratta"
    if r["stato"] == "estratta":
        if ora < r["ultimo"] + PAUSA:
            return None
        k = r["passo"] + 1
        estratto = r["estratto"] if isinstance(r["estratto"], list) else json.loads(r["estratto"])
        if ch:
            await bot.send_message(chat_id=ch, parse_mode="HTML", text=testo_passo(anno, estratto, k))
        db._q("UPDATE lottery SET passo = %s, ultimo = %s WHERE anno = %s", (k, ora, anno))
        if k < 12:
            return f"passo {k}"
        scrivi_draft(anno)
        db._q("UPDATE lottery SET stato = 'svelata' WHERE anno = %s", (anno,))
        from shared import draft_vista as DV
        if ch:
            await bot.send_message(chat_id=ch, parse_mode="HTML", text="🏁 Lottery finita: ecco l'ordine del draft.\n\n" + DV.testo_ordine(anno))
        gr = settings.admin_group_id()
        if gr:
            cap = [f"• {html.escape(_nome(t))}: cap −{x['cap']}M la stagione dopo → /set_cap_penalizzato {t} {x['cap']}"
                   for t, x in sanzioni_anno(anno).items() if x["cap"]]
            await bot.send_message(chat_id=gr, parse_mode="HTML", text=(
                f"🏁 Lottery {anno} finita: l'ordine dei due giri è scritto (correzioni con /draft_ordine). Il draft parte con "
                "▶️ nel sottomenu 🏀 Draft." + ("\n\nSanzioni sul cap da applicare:\n" + "\n".join(cap) if cap else "")))
        return "svelata"
    return None


async def job_lottery(context) -> None:
    try:
        await passo(context.bot)
    except Exception:
        logger.exception("Lottery: passo non riuscito")


async def promemoria(bot) -> str:
    """Al passaggio alla fase draft: ricordare agli admin di fissare l'estrazione (Luca, 23/11)."""
    gr = settings.admin_group_id()
    anno = str(settings.stagione_corrente())
    n = len(_seed(anno))
    testo = (f"🎰 <b>Fase draft</b>: fissate il momento della lottery del draft {anno} con "
             "<code>/lottery_quando GG/MM HH:MM</code> (ora di Roma, almeno 10 minuti avanti)." +
             ("" if n == 12 else f"\n⚠️ Manca la classifica finale della stagione {int(anno) - 1}: squadre della lottery {n} su 12."))
    if gr:
        await bot.send_message(chat_id=gr, text=testo, parse_mode="HTML")
    return "\n🎰 Promemoria della lottery agli admin"


async def cmd_lottery_stato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/lottery_stato: a che punto è (admin). /lottery è di loucabot: le odds."""
    if not settings.is_admin(update.effective_user.id):
        return
    anno = str(settings.stagione_corrente())
    r = stato(anno)
    if not r:
        await update.effective_message.reply_text(f"Lottery {anno} non ancora fissata: /lottery_quando GG/MM HH:MM.")
        return
    q = r["quando"].astimezone(ROMA)
    await update.effective_message.reply_text(f"🎰 Lottery {anno}: {q:%d/%m %H:%M}, round {r['round']}, {r['stato']}"
                                              + (f", svelate {r['passo']} su 12" if r["stato"] == "estratta" else "") + ".")


def get_handlers() -> list:
    return [CommandHandler("lottery_quando", cmd_lottery_quando), CommandHandler("lottery_stato", cmd_lottery_stato),
            CallbackQueryHandler(cb_sanzioni, pattern=r"^lsz:ok:\d+$")]

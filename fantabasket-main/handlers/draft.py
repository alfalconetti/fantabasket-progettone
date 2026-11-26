"""
Il draft (v7.27.0, Luca 23/11). Le viste (ordine in testo, tabellone, chi sceglie) sono in shared/draft_vista.py.

Come va:
- **Ordine** (`/draft_ordine GIRO` + una riga per pick, in ordine: squadra o GM di chi era la pick, «-1» per le
  posizioni perse con le penalità). Il primo giro viene dalla lottery, il secondo è l'inverso della classifica; le
  penalità già applicate. Si può rifare finché il draft non parte.
- **Avvio**: solo nella fase `offseason-draft` un admin lo fa partire (`/draft_avvia` o 🏀 Draft nel pannello). Sul
  canale il messaggio dell'ordine, che si aggiorna a ogni scelta.
- **A turno**: tocca a chi ha la pick in quel momento (le pick si scambiano fino alla scelta; se la 1st cade nella
  protezione, dopo le penalità, resta al proprietario di partenza). Il bot scrive in privato al GM, che manda
  `/scelgo NOME`; gli admin **approvano** (✅) o correggono (`/draft_nome NOME`) e scrivono **da dove viene**
  (`/draft_da COLLEGE`, solo per l'annuncio: non si salva). Gli admin possono anche scegliere loro (`/draft_scegli
  NOME`). Niente tempo per scegliere: se si allunga ci pensano gli admin. Niente pass.
- **Dopo ogni scelta**: anagrafica col nome approvato (id ESPN e nome bref si agganciano dopo, da soli), la **1st
  firmata** alla rookie scale della posizione (colonna del I anno, anche sopra il cap: il controllo si fa prima),
  la **2nd** diventa diritti; la pick è usata. Annuncio sul canale («Con la prima scelta al draft 2026 Andrea
  seleziona Cam Boozer, da Duke»), ordine aggiornato, a fine giro l'immagine del tabellone, poi il GM dopo.
- **Cap e slot** (`controllo_cap`): al passaggio alla fase draft e dopo ogni trade in quella fase, chi sforerebbe
  scegliendo con tutte le 1st che ha in mano: avviso agli admin (non blocca niente).
"""
import html
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db
import settings
import teams as tm
from shared import draft_vista as DV
from shared import protezioni as P

logger = logging.getLogger(__name__)

FASE = "offseason-draft"
CHIAVE_ORDINE = "draft-{anno}"


def anno() -> str:
    return str(settings.stagione_corrente())


def stato(a: str | None = None) -> str | None:
    r = db._q("SELECT stato FROM draft WHERE anno = %s", (a or anno(),), one=True)
    return r["stato"] if r else None


def _gm(team_id: str) -> str:
    return DV.gm(team_id)


# ── ordine ────────────────────────────────────────────────────────────────────

def leggi_ordine(testo: str, giro: int, a: str) -> list[dict]:
    """Le righe di /draft_ordine: «[N] SQUADRA [-1]» una per pick. [{"numero", "pick_id", "penalita", "team"}]."""
    import re
    righe = [r.strip() for r in testo.splitlines() if r.strip()]
    if len(righe) != 24:
        raise ValueError(f"Servono 24 righe, una per pick: ne ho {len(righe)}.")
    out, visti = [], set()
    for k, r in enumerate(righe):
        m = re.match(r"^(?:(\d{1,2})\s*[.|)\-]?\s+)?(.+?)(?:\s*\(?\s*-\s*(\d)\s*\)?)?$", r)
        if not m:
            raise ValueError(f"Riga {k + 1} non chiara: «{r}».")
        t = tm.get_team_by_query(m.group(2).strip())
        if not t:
            raise ValueError(f"Riga {k + 1}: squadra non trovata «{m.group(2).strip()}».")
        if t["id"] in visti:
            raise ValueError(f"Riga {k + 1}: {t['nome']} c'è due volte.")
        visti.add(t["id"])
        p = db._q("SELECT id FROM pick WHERE proprietario_orig = %s AND anno = %s AND round = %s", (t["id"], a, giro), one=True)
        if not p:
            raise ValueError(f"{t['nome']}: non trovo la sua pick del {giro}° giro {a}.")
        out.append({"numero": k + 1 + (24 if giro == 2 else 0), "pick_id": p["id"], "penalita": int(m.group(3) or 0), "team": t})
    return out


async def cmd_draft_ordine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not settings.is_admin(update.effective_user.id):
        return
    righe = (msg.text or "").split("\n")
    testa = righe[0].split()
    if len(testa) < 2 or testa[1] not in ("1", "2"):
        await msg.reply_text("Uso: /draft_ordine GIRO e sotto, una per riga, le 24 pick in ordine: la squadra (o il GM) "
                             "di chi era la pick, con «-1» se è scesa per le penalità.\nEs.\n/draft_ordine 1\n"
                             "1 SQUADRA\n2 SQUADRA1\n…\n13 SQUADRA2 -1")
        return
    giro, a = int(testa[1]), anno()
    if stato(a) not in (None, "pronto"):
        await msg.reply_text("❌ Il draft è già partito: l'ordine non si cambia più.")
        return
    try:
        ordine = leggi_ordine("\n".join(righe[1:]), giro, a)
    except ValueError as er:
        await msg.reply_text(f"❌ {er}")
        return
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO draft (anno) VALUES (%s) ON CONFLICT (anno) DO NOTHING", (a,))
            cur.execute("DELETE FROM draft_scelte WHERE anno = %s AND giro = %s", (a, giro))
            for o in ordine:
                cur.execute("INSERT INTO draft_scelte (anno, giro, numero, pick_id, penalita) VALUES (%s, %s, %s, %s, %s)",
                            (a, giro, o["numero"], o["pick_id"], o["penalita"]))
    from handlers.registro import segna
    await segna(context.bot, update.effective_user, "admin", "ordine del draft", oggetto=f"draft {a}", dopo=f"{giro}° giro")
    await msg.reply_text(DV.testo_ordine(a), parse_mode="HTML")


# ── turni ─────────────────────────────────────────────────────────────────────

async def _manda(bot, chat, testo, **k):
    try:
        return await bot.send_message(chat_id=chat, text=testo, parse_mode="HTML", **k)
    except Exception as e:
        logger.warning("Draft: messaggio a %s non mandato: %s", chat, e)


async def aggiorna_ordine(bot, a: str) -> None:
    """Il messaggio dell'ordine sul canale: modificato se c'è, se no mandato (messaggi_fissi)."""
    ch = settings.load_globals().get("main_channel_id")
    if not ch:
        return
    testo = DV.testo_ordine(a)
    m = db.get_messaggio_fisso(CHIAVE_ORDINE.format(anno=a))
    if m:
        try:
            await bot.edit_message_text(chat_id=m["chat_id"], message_id=m["message_id"], text=testo, parse_mode="HTML")
            return
        except Exception as e:
            if "not modified" in str(e).lower():
                return
            logger.warning("Draft: ordine non modificato (%s), lo rimando", e)
    nuovo = await _manda(bot, ch, testo)
    if nuovo:
        db.set_messaggio_fisso(CHIAVE_ORDINE.format(anno=a), int(ch), nuovo.message_id)


async def contatta(bot, a: str) -> None:
    """Scrive al GM che tocca (e lo dice agli admin)."""
    r = DV.corrente(a)
    if not r or stato(a) != "in_corso":
        return
    chi, via, prot = DV.chi_sceglie(r)
    t = tm.get_team_by_id(chi) or {"nome": chi}
    det = f" (via {_gm(via)})" if via else (f" ({prot}: è rimasta a te)" if prot else "")
    for g in t.get("gm_ids", []):
        await _manda(bot, int(g), f"⏰ <b>Tocca a te</b>: {DV.scelta_testo(r['numero'])} al draft {a}{det}, per {html.escape(t['nome'])}.\n"
                                  f"Scrivi <code>/scelgo NOME COGNOME</code>: il nome lo approvano gli admin.")
    gr = settings.admin_group_id()
    if gr:
        await _manda(bot, gr, f"⏰ Draft {a}: pick {r['numero']} · {html.escape(DV.etichetta(r))} ({html.escape(t['nome'])}). "
                              "Gli ho scritto in privato.")


async def cmd_scelgo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scelgo NOME: il GM che tocca propone il giocatore."""
    msg, u = update.effective_message, update.effective_user
    a = anno()
    nome = " ".join(context.args or []).strip()
    r = DV.corrente(a)
    if stato(a) != "in_corso" or not r:
        await msg.reply_text("Il draft non è in corso.")
        return
    chi, _, _ = DV.chi_sceglie(r)
    team = tm.get_team_by_gm(u.id)
    if not team or team["id"] != chi:
        await msg.reply_text(f"Non tocca a te: ora sceglie {_gm(chi)} (pick {r['numero']}).")
        return
    if not nome:
        await msg.reply_text("Scrivi il nome dopo il comando: /scelgo NOME COGNOME")
        return
    if r["stato"] == "approvata":
        await msg.reply_text("Gli admin hanno già approvato la tua scelta: manca solo l'annuncio.")
        return
    db._q("UPDATE draft_scelte SET nome_proposto = %s, proposto_da = %s, stato = 'proposta' WHERE id = %s", (nome, u.id, r["id"]))
    await msg.reply_text(f"📨 «{nome}» mandato agli admin: aspetta la conferma.")
    await _agli_admin(context.bot, r["id"])


def _gia_in_anagrafica(nome: str) -> list[dict]:
    from shared.parole_nome import identico
    return [g for g in (db._q("""SELECT g.id, g.nome_common, c.team_id FROM giocatori g
                                 LEFT JOIN contratti c ON c.giocatore_id = g.id AND c.attivo""", many=True) or [])
            if identico(nome, g["nome_common"])]


async def _agli_admin(bot, scelta_id: int) -> None:
    r = db._q("SELECT * FROM draft_scelte WHERE id = %s", (scelta_id,), one=True)
    rr = next(x for x in DV.righe(r["anno"]) if x["id"] == scelta_id)
    chi, _, _ = DV.chi_sceglie(rr)
    t = tm.get_team_by_id(chi) or {"nome": chi}
    gia = _gia_in_anagrafica(r["nome_proposto"])
    nota = ""
    if gia:
        nota = "\n⚠️ Nell'anagrafica c'è già: " + ", ".join(
            f"{html.escape(g['nome_common'])}" + (f" (sotto contratto con {html.escape(tm.get_team_by_id(g['team_id'])['nome'])})" if g.get("team_id") else "")
            for g in gia) + ": approvando si usa quello."
    gr = settings.admin_group_id()
    if gr:
        await _manda(bot, gr, f"🏀 Draft {r['anno']} · pick {r['numero']} · {html.escape(DV.etichetta(rr))} ({html.escape(t['nome'])}) "
                              f"sceglie: <b>{html.escape(r['nome_proposto'])}</b>{nota}\n"
                              "Se il nome va corretto: <code>/draft_nome NOME GIUSTO</code>, poi ✅.",
                     reply_markup=K([[B("✅ Approva", callback_data=f"drs:ok:{scelta_id}"),
                                      B("↩️ Chiedi un altro nome", callback_data=f"drs:no:{scelta_id}")]]))


async def cb_scelta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """drs:ok:<id> approva (poi la provenienza) · drs:no:<id> il GM riscrive."""
    q = update.callback_query
    if not settings.is_admin(q.from_user.id):
        await q.answer("Solo gli admin.", show_alert=True)
        return
    _, az, sid = q.data.split(":")
    r = db._q("SELECT * FROM draft_scelte WHERE id = %s", (int(sid),), one=True)
    if not r or r["stato"] not in ("proposta", "approvata"):
        await q.answer("Scelta già fatta o cambiata.", show_alert=True)
        return
    await q.answer()
    if az == "ok":
        db._q("UPDATE draft_scelte SET stato = 'approvata' WHERE id = %s", (r["id"],))
        await q.edit_message_text(f"✅ Approvato <b>{html.escape(r['nome_proposto'])}</b> (pick {r['numero']}, da {html.escape(q.from_user.first_name or 'admin')}).\n"
                                  "Da dove viene? <code>/draft_da COLLEGE O CLUB</code> (solo per l'annuncio).", parse_mode="HTML")
        return
    db._q("UPDATE draft_scelte SET stato = 'attesa', nome_proposto = NULL WHERE id = %s", (r["id"],))
    await q.edit_message_text(f"↩️ Chiesto un altro nome per la pick {r['numero']}.")
    rr = next(x for x in DV.righe(r["anno"]) if x["id"] == r["id"])
    chi, _, _ = DV.chi_sceglie(rr)
    for g in (tm.get_team_by_id(chi) or {}).get("gm_ids", []):
        await _manda(context.bot, int(g), f"↩️ Gli admin chiedono un altro nome (o lo stesso scritto giusto) per la pick {r['numero']}: "
                                          "<code>/scelgo NOME COGNOME</code>")


async def cmd_draft_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/draft_nome NOME: gli admin correggono il nome proposto per la pick che tocca."""
    if not settings.is_admin(update.effective_user.id):
        return
    nome = " ".join(context.args or []).strip()
    r = DV.corrente(anno())
    if not r or r["stato"] not in ("proposta", "approvata") or not nome:
        await update.effective_message.reply_text("Uso: /draft_nome NOME, quando c'è un nome proposto per la pick che tocca.")
        return
    db._q("UPDATE draft_scelte SET nome_proposto = %s, stato = 'proposta' WHERE id = %s", (nome, r["id"]))
    await _agli_admin(context.bot, r["id"])


async def cmd_draft_scegli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/draft_scegli NOME: l'admin sceglie per la squadra che tocca (approvato subito)."""
    if not settings.is_admin(update.effective_user.id):
        return
    nome = " ".join(context.args or []).strip()
    a = anno()
    r = DV.corrente(a)
    if stato(a) not in ("in_corso", "pausa") or not r or not nome:
        await update.effective_message.reply_text("Uso: /draft_scegli NOME, a draft in corso: sceglie per la squadra che tocca.")
        return
    db._q("UPDATE draft_scelte SET nome_proposto = %s, proposto_da = %s, stato = 'approvata' WHERE id = %s",
          (nome, update.effective_user.id, r["id"]))
    await update.effective_message.reply_text(f"✅ Pick {r['numero']}: <b>{html.escape(nome)}</b>. Da dove viene? "
                                              "<code>/draft_da COLLEGE O CLUB</code>", parse_mode="HTML")


async def cmd_draft_da(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/draft_da COLLEGE: la provenienza (solo per l'annuncio) e la scelta diventa ufficiale."""
    if not settings.is_admin(update.effective_user.id):
        return
    da = " ".join(context.args or []).strip()
    a = anno()
    r = DV.corrente(a)
    if not r or r["stato"] != "approvata" or not da:
        await update.effective_message.reply_text("Uso: /draft_da COLLEGE O CLUB, dopo aver approvato il nome della pick che tocca.")
        return
    try:
        fatta = esegui(r["id"], update.effective_user)
    except Exception as e:
        logger.exception("Draft: scelta non registrata")
        await update.effective_message.reply_text(f"❌ Scelta non registrata: {html.escape(str(e))}", parse_mode="HTML")
        return
    await update.effective_message.reply_text(f"✅ Pick {fatta['numero']} registrata.")
    await dopo_scelta(context.bot, update.effective_user, fatta, da)


def _scala(numero: int) -> tuple[int, int] | None:
    for fascia, valori in settings.get().get("rookie_scale", {}).items():
        lim = fascia.split("-")
        if int(lim[0]) <= numero <= int(lim[-1]) and valori:
            return int(valori[0]["imp"]), int(valori[0]["anni"])
    return None


def esegui(scelta_id: int, user=None) -> dict:
    """Scrive la scelta in un'unica transazione: anagrafica (o quella che c'è col nome identico), la 1st firmata alla
    rookie scale o i diritti della 2nd, la pick usata (tornata al proprietario di partenza se è scattata la
    protezione), la riga del draft fatta."""
    import psycopg2.extras
    from utils import normalizza
    r0 = db._q("SELECT * FROM draft_scelte WHERE id = %s", (scelta_id,), one=True)
    r = next(x for x in DV.righe(r0["anno"]) if x["id"] == scelta_id)
    chi, via, prot = DV.chi_sceglie(r)
    stagione = str(settings.stagione_corrente())
    nome = r["nome_proposto"]
    gia = _gia_in_anagrafica(nome)
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT stato FROM draft_scelte WHERE id = %s FOR UPDATE", (scelta_id,))
            if cur.fetchone()["stato"] != "approvata":
                raise ValueError("la scelta non è più da registrare")
            if gia:
                gid = gia[0]["id"]
            else:
                cur.execute("INSERT INTO giocatori (nome_common, nome_norm, nome_bref) VALUES (%s, %s, %s) RETURNING id",
                            (nome, normalizza(nome), nome))
                gid = cur.fetchone()["id"]
            nota = f"Draft {r['anno']}, pick {r['numero']}"
            if r["giro"] == 1:
                sc = _scala(r["numero"])
                if not sc:
                    raise ValueError(f"pick {r['numero']} fuori dalla rookie scale")
                cur.execute("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft, anno_firma, firmato, pick_id) "
                            "VALUES (%s, %s, 1, %s, %s, %s, TRUE, %s)", (gid, chi, r["numero"], r["anno"], stagione, r["pick_id"]))
                cur.execute("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) "
                            "VALUES (%s, %s, %s, %s, %s, 'rookie') RETURNING id", (gid, chi, sc[0], sc[1], stagione))
                cid = cur.fetchone()["id"]
                cur.execute("INSERT INTO transazioni (tipo, giocatore_id, team_id_da, team_id_a, stagione, contratto_id, rookie_scale, note) "
                            "VALUES ('rookie_firma', %s, NULL, %s, %s, %s, TRUE, %s)", (gid, chi, stagione, cid, nota))
            else:
                cur.execute("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft, firmato, pick_id) "
                            "VALUES (%s, %s, 2, %s, %s, FALSE, %s)", (gid, chi, r["numero"], r["anno"], r["pick_id"]))
                if db.storico_pick_diritti_presente(cur):
                    cur.execute("INSERT INTO transazioni (oggetto, tipo, giocatore_id, team_id_da, team_id_a, stagione, note) "
                                "VALUES ('diritti', 'rookie', %s, NULL, %s, %s, %s)", (gid, chi, stagione, nota))
            cur.execute("UPDATE pick SET scattata = TRUE, numero_scelta = %s, proprietario_att = %s WHERE id = %s",
                        (r["numero"], chi, r["pick_id"]))
            if db.storico_pick_diritti_presente(cur):
                cur.execute("INSERT INTO transazioni (oggetto, tipo, pick_id, team_id_da, team_id_a, stagione, note) "
                            "VALUES ('pick', 'rookie', %s, %s, %s, %s, %s)",
                            (r["pick_id"], r["proprietario_att"], chi, stagione, nota + (f", {prot}: resta a chi la cedeva" if prot else "")))
            cur.execute("UPDATE draft_scelte SET stato = 'fatta', squadra = %s, via = %s, protetta = %s, giocatore_id = %s, "
                        "fatta_at = %s WHERE id = %s", (chi, via, prot, gid, datetime.now(timezone.utc), scelta_id))
    return {**r, "squadra": chi, "via": via, "protetta": prot, "giocatore_id": gid, "nome": nome}


async def dopo_scelta(bot, user, f: dict, provenienza: str) -> None:
    """Registro, annuncio, ordine aggiornato, tabellone a fine giro, il GM dopo."""
    from handlers.registro import segna
    a = f["anno"]
    await segna(bot, user, "admin", "scelta al draft", squadre=f["squadra"], giocatore_id=f["giocatore_id"], oggetto=f["nome"],
                dopo=("firmato alla rookie scale" if f["giro"] == 1 else "diritti"), nota=f"draft {a}, pick {f['numero']}")
    ch = settings.load_globals().get("main_channel_id")
    via = f" (via {_gm(f['via'])})" if f.get("via") else ""
    if ch:
        await _manda(bot, ch, f"🏀 Con {DV.scelta_testo(f['numero'])} al draft {a} <b>{html.escape(_gm(f['squadra']))}</b>{html.escape(via)} "
                              f"seleziona <b>{html.escape(f['nome'])}</b>, da {html.escape(provenienza)}")
    await aggiorna_ordine(bot, a)
    if f["numero"] in (24, 48) and ch:
        import asyncio
        d = await asyncio.to_thread(DV.dati, a, f["giro"])
        if d:
            try:
                await bot.send_photo(chat_id=ch, photo=await asyncio.to_thread(DV.immagine, d),
                                     caption=f"Draft {a}: il {'primo' if f['giro'] == 1 else 'secondo'} giro")
            except Exception as e:
                logger.warning("Draft: tabellone non mandato: %s", e)
    try:
        import gas_client
        gas_client.sync_after_rookie(f["squadra"])
    except Exception as e:
        logger.warning("Draft: sync fogli: %s", e)
    if DV.corrente(a) is None:
        db._q("UPDATE draft SET stato = 'finito', finito_at = NOW() WHERE anno = %s", (a,))
        gr = settings.admin_group_id()
        if gr:
            await _manda(bot, gr, f"🏁 Draft {a} finito.")
        return
    await contatta(bot, a)


# ── admin: avvio, pausa, correzioni, controllo ───────────────────────────────

def _pronto(a: str) -> str | None:
    n = db._q("SELECT giro, COUNT(*) AS n FROM draft_scelte WHERE anno = %s GROUP BY giro", (a,), many=True) or []
    per = {x["giro"]: x["n"] for x in n}
    if per.get(1) != 24 or per.get(2) != 24:
        return "manca l'ordine: /draft_ordine 1 e /draft_ordine 2 (24 righe ciascuno)"
    return None


async def avvia(bot, user) -> str:
    a = anno()
    if settings.fase() != FASE:
        return "❌ Il draft parte solo nella fase draft."
    if stato(a) not in (None, "pronto"):
        return f"Il draft {a} è già partito."
    manca = _pronto(a)
    if manca:
        return f"❌ Non ancora: {manca}."
    db._q("UPDATE draft SET stato = 'in_corso', avviato_at = NOW() WHERE anno = %s", (a,))
    from handlers.registro import segna
    await segna(bot, user, "admin", "draft avviato", oggetto=f"draft {a}")
    await aggiorna_ordine(bot, a)
    await contatta(bot, a)
    return f"▶️ Draft {a} partito."


async def pausa(bot, riprendi: bool) -> str:
    a = anno()
    s = stato(a)
    if riprendi:
        if s != "pausa":
            return "Il draft non è in pausa."
        db._q("UPDATE draft SET stato = 'in_corso' WHERE anno = %s", (a,))
        await contatta(bot, a)
        return "▶️ Draft ripreso."
    if s != "in_corso":
        return "Il draft non è in corso."
    db._q("UPDATE draft SET stato = 'pausa' WHERE anno = %s", (a,))
    return "⏸️ Draft in pausa: nessuno viene contattato finché non riprende."


async def cmd_draft_avvia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if settings.is_admin(update.effective_user.id):
        await update.effective_message.reply_text(await avvia(context.bot, update.effective_user))


async def cmd_draft_pausa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if settings.is_admin(update.effective_user.id):
        await update.effective_message.reply_text(await pausa(context.bot, False))


async def cmd_draft_riprendi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if settings.is_admin(update.effective_user.id):
        await update.effective_message.reply_text(await pausa(context.bot, True))


async def cmd_draft_correggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/draft_correggi NUMERO NOME: corregge il nome di una scelta già fatta (l'anagrafica creata dal draft)."""
    if not settings.is_admin(update.effective_user.id):
        return
    args = context.args or []
    if len(args) < 2 or not args[0].isdigit():
        await update.effective_message.reply_text("Uso: /draft_correggi NUMERO NOME GIUSTO")
        return
    from utils import normalizza
    a, num, nome = anno(), int(args[0]), " ".join(args[1:])
    r = db._q("SELECT * FROM draft_scelte WHERE anno = %s AND numero = %s AND stato = 'fatta'", (a, num), one=True)
    if not r:
        await update.effective_message.reply_text(f"La pick {num} del draft {a} non è ancora stata scelta.")
        return
    vecchio = db._q("SELECT nome_common FROM giocatori WHERE id = %s", (r["giocatore_id"],), one=True)["nome_common"]
    db._q("UPDATE giocatori SET nome_common = %s, nome_norm = %s, nome_bref = %s WHERE id = %s",
          (nome, normalizza(nome), nome, r["giocatore_id"]))
    db._q("UPDATE draft_scelte SET nome_proposto = %s WHERE id = %s", (nome, r["id"]))
    from handlers.registro import segna
    await segna(context.bot, update.effective_user, "admin", "nome corretto al draft", giocatore_id=r["giocatore_id"],
                oggetto=nome, prima=vecchio, dopo=nome, nota=f"draft {a}, pick {num}")
    await aggiorna_ordine(context.bot, a)
    await update.effective_message.reply_text(f"✏️ Pick {num}: {vecchio} → {nome}.")


def controllo_cap(a: str | None = None, squadre: list[str] | None = None) -> list[str]:
    """Chi sforerebbe cap o slot scegliendo con tutte le 1st del draft che ha in mano (Luca, 23/11). Con l'ordine
    già fatto si usa la scala della posizione (e le protezioni che scattano), se no la scala più bassa (stima)."""
    a = a or anno()
    stagione = str(settings.stagione_corrente())
    ordine = {x["pick_id"]: x for x in (db._q("SELECT * FROM draft_scelte WHERE anno = %s AND giro = 1", (a,), many=True) or [])}
    picks = db._q("SELECT * FROM pick WHERE anno = %s AND round = 1 AND scattata = FALSE", (a,), many=True) or []
    minimo = min((int(v[0]["imp"]) for v in settings.get().get("rookie_scale", {}).values() if v), default=0)
    per = {}
    for p in picks:
        o = ordine.get(p["id"])
        chi = p["proprietario_att"]
        if o and P.scatta(p.get("protezioni"), o["numero"]):
            chi = p["proprietario_orig"]
        imp = (_scala(o["numero"]) or (minimo, 0))[0] if o else minimo
        per.setdefault(chi, []).append(imp)
    out = []
    for t in tm.get_all_teams():
        if squadre and t["id"] not in squadre:
            continue
        imp = per.get(t["id"], [])
        if not imp:
            continue
        cap_lib = settings.cap_limite_team(t) - db.cap_occupato_team(t["id"], stagione)
        occupati = db.slot_occupati(db.get_roster_team(t["id"]) or [])
        problemi = []
        if sum(imp) > cap_lib:
            problemi.append(f"cap: {len(imp)} 1st da {sum(imp)}M, liberi {cap_lib}M")
        if occupati + len(imp) > settings.max_roster():
            problemi.append(f"slot: {occupati} + {len(imp)} su {settings.max_roster()}")
        if problemi:
            out.append(f"• {html.escape(t['nome'])}: " + " · ".join(problemi))
    return out


def testo_controllo(a: str | None = None, squadre: list[str] | None = None) -> str:
    a = a or anno()
    righe = controllo_cap(a, squadre)
    stima = "" if db._q("SELECT 1 FROM draft_scelte WHERE anno = %s LIMIT 1", (a,), one=True) else \
        "\n<i>Ordine non ancora fatto: stima con la scala più bassa.</i>"
    if not righe:
        return f"✅ Draft {a}: scegliendo con tutte le 1st che hanno, nessuna squadra sfora cap o slot.{stima}"
    return f"⚠️ <b>Draft {a}: chi sforerebbe scegliendo con tutte le sue 1st</b>\n" + "\n".join(righe) + stima


async def cmd_draft_controllo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if settings.is_admin(update.effective_user.id):
        await update.effective_message.reply_text(testo_controllo(), parse_mode="HTML")


async def avviso_trade(bot, squadre: list[str]) -> None:
    """Dopo una trade nella fase draft: se una delle squadre ora sforerebbe, avviso agli admin (non blocca)."""
    if settings.fase() != FASE:
        return
    righe = controllo_cap(None, squadre)
    gr = settings.admin_group_id()
    if righe and gr:
        await _manda(bot, gr, "⚠️ <b>Dopo la trade, al draft sforerebbero</b> (scegliendo con tutte le 1st che hanno)\n" + "\n".join(righe))


# ── sottomenu 🏀 Draft del pannello admin ────────────────────────────────────

def kb_menu() -> K:
    s = stato(anno())
    righe = [[B("📋 Ordine", callback_data="drf:ordine"), B("📊 Cap e slot", callback_data="drf:cap")]]
    if s in (None, "pronto"):
        righe.insert(0, [B("▶️ Avvia il draft", callback_data="drf:avvia")])
    elif s == "in_corso":
        righe.insert(0, [B("🔁 Ricontatta il GM", callback_data="drf:ric"), B("⏸️ Pausa", callback_data="drf:pausa")])
    elif s == "pausa":
        righe.insert(0, [B("▶️ Riprendi", callback_data="drf:riprendi")])
    righe.append([B("← Menu", callback_data="adm:home")])
    return K(righe)


def testo_menu() -> str:
    a = anno()
    s = stato(a) or "senza ordine"
    r = DV.corrente(a)
    ora = f"\nTocca: pick {r['numero']} · {html.escape(DV.etichetta(r))}" if r and s in ("in_corso", "pausa") else ""
    try:
        from handlers.lottery import stato as st_lottery
        lt = st_lottery(a)
    except Exception:
        lt = None
    lot = (f"\n🎰 Lottery: {lt['stato']}" + (f", svelate {lt['passo']} su 12" if lt["stato"] == "estratta" else "")) if lt else \
        "\n🎰 Lottery da fissare: <code>/lottery_quando GG/MM HH:MM</code>"
    return (f"🏀 <b>Draft {a}</b> · {s}{ora}{lot}\n\n"
            "• <code>/draft_ordine 1</code> (e 2) con le 24 righe: solo per correggere l'ordine scritto dalla lottery\n"
            "• <code>/draft_scegli NOME</code>: scegli tu per chi tocca\n"
            "• <code>/draft_nome NOME</code>: correggi il nome proposto\n"
            "• <code>/draft_da COLLEGE</code>: la provenienza, e la scelta è fatta\n"
            "• <code>/draft_correggi NUMERO NOME</code>: correggi una scelta già fatta")


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not settings.is_admin(q.from_user.id):
        await q.answer("Solo gli admin.", show_alert=True)
        return
    az = q.data.split(":")[1]
    await q.answer()
    avviso = ""
    if az == "avvia":
        avviso = await avvia(context.bot, q.from_user)
    elif az in ("pausa", "riprendi"):
        avviso = await pausa(context.bot, az == "riprendi")
    elif az == "ric":
        await contatta(context.bot, anno())
        avviso = "🔁 GM ricontattato."
    elif az == "cap":
        avviso = testo_controllo()
    elif az == "ordine":
        avviso = DV.testo_ordine(anno()) if db._q("SELECT 1 FROM draft_scelte WHERE anno = %s LIMIT 1", (anno(),), one=True) \
            else "Ordine non ancora fatto: /draft_ordine 1 e /draft_ordine 2."
    await q.edit_message_text((avviso + "\n\n" if avviso else "") + testo_menu(), parse_mode="HTML", reply_markup=kb_menu())


def get_handlers() -> list:
    from settings import solo_privato
    return [
        CommandHandler("draft", solo_privato(DV.cmd_draft)),          # nei gruppi /draft lo fa loucabot
        CommandHandler("scelgo", solo_privato(cmd_scelgo)),
        CommandHandler("draft_ordine", cmd_draft_ordine),
        CommandHandler("draft_avvia", cmd_draft_avvia),
        CommandHandler("draft_pausa", cmd_draft_pausa),
        CommandHandler("draft_riprendi", cmd_draft_riprendi),
        CommandHandler("draft_scegli", cmd_draft_scegli),
        CommandHandler("draft_nome", cmd_draft_nome),
        CommandHandler("draft_da", cmd_draft_da),
        CommandHandler("draft_correggi", cmd_draft_correggi),
        CommandHandler("draft_controllo", cmd_draft_controllo),
        CallbackQueryHandler(cb_scelta, pattern=r"^drs:(ok|no):\d+$"),
        CallbackQueryHandler(cb_menu, pattern=r"^drf:(home|avvia|pausa|riprendi|ric|cap|ordine)$"),
    ]

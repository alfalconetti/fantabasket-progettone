"""Comandi e job del calcolo: tabellini, infortunati, abbinamento con ESPN, fantapunti.

Admin: /tabellini (anche snapshot degli infortunati), /espn_giocatori, /espn_mancanti, /espn_abbina ID_GIOCATORE ID_ESPN, /fantapunti [N],
       /set_valid_status GIOCATORE N (lo status che vale per il calcolo, scelto tra quelli degli snapshot)
Job:   tabellini e abbinamenti nella sincronizzazione delle 8:30 (handlers.job_sync),
       snapshot degli infortunati ogni 4 ore e 30 minuti prima della prima partita del giorno, solo dai ruoli
       dell'offseason ai playoff (config.FASI_SNAPSHOT).
"""
from numeri import testo as testo_punti
import difflib
import html
import logging

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import calcolo
import calendario as cal
import config
import db
import nba

logger = logging.getLogger(__name__)
e = html.escape


async def _solo_admin(update) -> bool:
    if config.is_admin(update.effective_user.id):
        return True
    await update.effective_message.reply_text("⛔ Solo admin.")
    return False


def da_scaricare(dal=None, al=None) -> list[str]:
    """Le partite finite senza tabellino: della stagione in corso (le vecchie non si ritentano ogni
    mattina), o con dal/al dei giorni indicati (/dev_prova_calcolo su notti della stagione scorsa)."""
    from datetime import datetime
    if dal is not None:
        return db.partite_senza_tabellino(fino=al, dal=dal)
    return db.partite_senza_tabellino(fino=datetime.now(nba.ET).date(), stagione=config.stagione())


async def aggiorna_tabellini(dal=None, al=None) -> dict:
    """Tabellini delle partite finite che non li hanno, poi abbinamento automatico dei giocatori nuovi."""
    r = await nba.scarica_tabellini(da_scaricare(dal, al))
    if r["errori"]:                              # quale partita e perché, per il log
        ids = [x.split(":", 1)[0] for x in r["errori"]]
        info = {p["espn_id"]: p for p in db.q("SELECT espn_id, data_et, casa, trasferta FROM nba_partite WHERE espn_id = ANY(%s)",
                                               (ids,), many=True) or []}
        r["errori"] = [(f"{info[i]['casa']}–{info[i]['trasferta']} del {info[i]['data_et']:%d/%m/%Y} ({x})" if i in info else x)
                       for i, x in zip(ids, r["errori"])]
    r["abbinamento"] = calcolo.abbina_auto(db.atleti_espn_visti())
    return r


def testo_tabellini(r: dict) -> str:
    t = f"{r['partite']} tabellini ({r['giocatori']} righe)"
    if r["errori"]:
        t += f", ⚠️ {len(r['errori'])} non scaricati: " + "; ".join(e(x)[:150] for x in r["errori"][:3])
    if r.get("abbinamento", {}).get("nuovi"):
        cp = r["abbinamento"].get("coppie") or []
        t += f", {r['abbinamento']['nuovi']} giocatori abbinati a ESPN" + (
            ": " + ", ".join(e(a) if a == b else f"{e(a)} = {e(b)}" for a, b in cp[:15]) + (" …" if len(cp) > 15 else "")
            if cp else "")
    return t


async def snapshot_infortuni() -> str:
    try:
        r = await nba.scarica_infortuni()
        return f"{r['giocatori']} infortunati"
    except Exception as err:
        logger.warning("Infortunati: %s", err)
        return f"⚠️ infortunati non scaricati ({type(err).__name__}: {e(str(err))[:150]})"


async def job_prepartita(context: ContextTypes.DEFAULT_TYPE):
    """Ogni 10 minuti: uno snapshot degli infortunati 30-40 minuti prima di ogni partita NBA (o gruppo di partite
    che iniziano insieme), se non ce n'è già uno: serve alla FADD, che guarda l'ultimo prima della partita della
    squadra del giocatore (db.snapshot_alla_partita, v68)."""
    from datetime import datetime, timedelta, timezone
    ora_ = datetime.now(timezone.utc)
    r = db.q("SELECT MIN(inizio) AS t FROM nba_partite WHERE inizio > %s AND inizio <= %s",
             (ora_, ora_ + timedelta(minutes=40)), one=True)
    if not r or not r["t"] or not config.snapshot_attivi():
        return
    gia = db.q("SELECT 1 FROM nba_infortuni WHERE preso >= %s LIMIT 1", (r["t"] - timedelta(minutes=45),), one=True)
    if not gia:
        await job_infortuni(context)


def finestra_fitta(ora_, giornate: list[dict]):
    """La giornata il cui primo giorno è in corso tra le `orari.injury_fitti` (19:00 a Roma del suo
    primo giorno NBA) e la prima partita, o None (Luca, 23/10: injury report ogni mezz'ora)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from shared import regole
    roma = ZoneInfo("Europe/Rome")
    for g in giornate:
        pp = g.get("prima_partita")
        if not pp or pp <= ora_:
            continue
        inizio = datetime.combine(g["dal"], regole.orario("injury_fitti"), tzinfo=roma)
        if inizio <= ora_ < pp:
            return g
    return None


async def job_injury_fitti(context: ContextTypes.DEFAULT_TYPE):
    """Ogni 5 minuti: nella sera della prima notte di una giornata, dalle 19 alla prima partita,
    uno snapshot degli infortunati ogni mezz'ora (IPanchinari avvisa i GM dei cambi). Una sola
    richiesta a ESPN per tutta la lega."""
    from datetime import datetime, timedelta, timezone
    if not config.snapshot_attivi():
        return
    ora_ = datetime.now(timezone.utc)
    if not finestra_fitta(ora_, db.giornate(config.stagione())):
        return
    if db.q("SELECT 1 FROM nba_infortuni WHERE preso >= %s LIMIT 1", (ora_ - timedelta(minutes=29),), one=True):
        return
    await job_infortuni(context)


async def job_infortuni(context: ContextTypes.DEFAULT_TYPE):
    from handlers import log
    if not config.snapshot_attivi():          # fuori stagione (dai rinnovi alla FA) non servono
        return
    esito = await snapshot_infortuni()
    if esito.startswith("⚠️"):
        await log(context.bot, f"🩹 Snapshot infortunati: {esito}")


async def cmd_tabellini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _solo_admin(update):
        return
    da_fare = da_scaricare()
    await update.effective_message.reply_text(f"⏳ Scarico {len(da_fare)} tabellini da ESPN (circa un secondo l'uno)…")
    r = await aggiorna_tabellini()
    inf = await snapshot_infortuni()
    await update.effective_message.reply_text("✅ " + testo_tabellini(r) + f"; snapshot: {inf}"
                                              + ("\n" + "\n".join(e(x) for x in r["errori"][:10]) if r["errori"] else ""),
                                              parse_mode="HTML")
    from handlers import log, _chi
    await log(context.bot, f"📊 /tabellini di {_chi(update)}: {testo_tabellini(r)}; snapshot: {inf}")
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "tabellini riscaricati", dopo=testo_tabellini(r), nota=f"snapshot: {inf}")


async def cmd_espn_giocatori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scarica i roster delle 30 squadre da ESPN e abbina i nomi all'anagrafica."""
    if not await _solo_admin(update):
        return
    await update.effective_message.reply_text("⏳ Scarico i roster NBA da ESPN (30 richieste, mezzo minuto)…")
    atleti = await nba.scarica_giocatori()
    db.salva_atleti(atleti)
    r = calcolo.abbina_auto(db.atleti_espn_visti())
    mancanti = [x for x in db.giocatori_a_roster(config.stagione()) if not x["atleta"]]
    righe = [f"✅ {len(atleti)} giocatori NBA da ESPN, {r['nuovi']} abbinati ora all'anagrafica.",
             f"A roster nella lega senza id ESPN: <b>{len(mancanti)}</b>" + (" → /espn_mancanti" if mancanti else " 🎉")]
    if r["ambigui"]:
        righe.append(f"Nomi ambigui (da abbinare a mano): {e(', '.join(r['ambigui'][:15]))}")
    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")
    from handlers import log, _chi
    await log(context.bot, f"👥 /espn_giocatori di {_chi(update)}: {len(atleti)} giocatori ESPN, {r['nuovi']} abbinati, "
                           f"{len(mancanti)} a roster senza id")
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "giocatori ESPN scaricati", oggetto=f"{len(atleti)} giocatori ESPN",
               dopo=f"{r['nuovi']} abbinati", nota=f"{len(mancanti)} a roster senza id")


async def cmd_espn_mancanti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _solo_admin(update):
        return
    mancanti = [x for x in db.giocatori_a_roster(config.stagione()) if not x["atleta"]]
    if not mancanti:
        await update.effective_message.reply_text("✅ Tutti i giocatori a roster hanno l'id ESPN.")
        return
    gia = set(db.abbinamenti().values())
    liberi = {a: n for a, n in db.atleti_espn_visti().items() if a not in gia}
    per_norm = {}
    for a, n in liberi.items():
        per_norm.setdefault(calcolo.norm(n), []).append((a, n))
    righe = [f"❔ <b>Giocatori a roster senza id ESPN</b> ({len(mancanti)})",
             "<i>/espn_abbina ID_GIOCATORE ID_ESPN — l'id ESPN è il numero nel link del giocatore su espn.com</i>", ""]
    for x in mancanti:
        simili = difflib.get_close_matches(calcolo.norm(x["nome_common"]), list(per_norm), n=2, cutoff=0.6)
        prop = "; ".join(f"{e(n)} <code>{a}</code>" for s in simili for a, n in per_norm[s])
        righe.append(f"• <code>{x['giocatore_id']}</code> {e(x['nome_common'])} ({e(config.nome(x['team_id']))})"
                     + (f" → forse {prop}" if prop else ""))
    from shared.messaggi import manda_lungo
    await manda_lungo(context.bot, update.effective_chat.id, "\n".join(righe), "espn-mancanti")


async def cmd_espn_abbina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _solo_admin(update):
        return
    args = context.args or []
    if len(args) != 2 or not all(x.isdigit() for x in args):
        await update.effective_message.reply_text("Uso: /espn_abbina ID_GIOCATORE ID_ESPN (numeri, da /espn_mancanti)")
        return
    gid, atleta = int(args[0]), args[1]
    g = next((x for x in db.giocatori_anagrafica() if x["id"] == gid), None)
    if not g:
        await update.effective_message.reply_text(f"Nessun giocatore con id {gid} in anagrafica.")
        return
    nome_espn = db.atleti_espn_visti().get(atleta, "?")
    prima = db.abbinamenti().get(gid)
    db.abbina(gid, atleta, nome_espn, "admin")
    from registro import segna_sync
    segna_sync(update.effective_user, "admin", "abbinamento ESPN", giocatore_id=gid, oggetto=g["nome_common"],
               prima=f"ESPN {prima}" if prima else "senza id ESPN", dopo=f"ESPN {atleta} ({nome_espn})")
    await update.effective_message.reply_text(
        f"✅ {e(g['nome_common'])} ↔ ESPN {atleta} ({e(nome_espn)})", parse_mode="HTML")
    from handlers import log, _chi
    await log(context.bot, f"🔗 {_chi(update)} abbina {e(g['nome_common'])} (id {gid}) a ESPN {atleta} ({e(nome_espn)})")


def testo_fantapunti(stagione: str, g: dict) -> str:
    roster = db.giocatori_a_roster(stagione)
    p = calcolo.punteggio_giocatori(stagione, g, [x["atleta"] for x in roster if x["atleta"]])
    righe = [f"📊 <b>Fantapunti giornata {g['numero']}</b> · {g['dal']:%d/%m} – {g['al']:%d/%m}",
             "<i>Tutti i giocatori a roster (il calcolo coi quintetti e le panchine di IPanchinari è da fare).</i>"]
    simbolo = {"partite": "", "media": "📈 ", "zero": ""}
    for team in config.squadre():
        suoi = [x for x in roster if x["team_id"] == team["id"]]
        if not suoi:
            continue
        righe += ["", f"<b>{e(team['nome'])}</b>"]
        for x in sorted(suoi, key=lambda x: -(p.get(x["atleta"], {}).get("fp") or 0)):
            if not x["atleta"]:
                righe.append(f"• {e(x['nome_common'])} {x['ruolo'] or ''}: ❔ senza id ESPN")
                continue
            q = p[x["atleta"]]
            nota = f" <i>({e(q['nota'])})</i>" if q["nota"] and q["come"] != "partite" or len(q["partite"]) > 1 else ""
            righe.append(f"• {simbolo[q['come']]}{e(x['nome_common'])} {x['ruolo'] or ''}: <b>{testo_punti(q['fp'])}</b>{nota}")
    return "\n".join(righe)


async def cmd_fantapunti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _solo_admin(update):
        return
    s = config.stagione()
    n = None
    if context.args and context.args[0].isdigit():
        n = int(context.args[0])
    g = db.giornata(s, n) if n else cal.corrente(s)
    if not g:
        await update.effective_message.reply_text("Giornata non trovata.")
        return
    from shared.messaggi import manda_lungo
    await manda_lungo(context.bot, update.effective_chat.id, testo_fantapunti(s, g), f"fantapunti-G{g['numero']}",
                      riassunto=f"📊 Fantapunti giornata {g['numero']}")


async def cmd_dev_giornata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dev_giornata [N]: tutto quello che il bot sa di una giornata (la corrente se manca N)."""
    if not (config.dev_id() and update.effective_user.id == config.dev_id()):
        return
    s = config.stagione()
    n = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    g = db.giornata(s, n) if n else cal.corrente(s)
    if not g:
        await update.effective_message.reply_text("Giornata non trovata.")
        return
    partite = db.q("SELECT stato, COUNT(*) AS n, COUNT(tabellino) AS t FROM nba_partite WHERE data_et BETWEEN %s AND %s "
                   "AND tipo = ANY(%s) GROUP BY stato ORDER BY stato", (g["dal"], g["al"], [2, 3, 5]), many=True) or []
    snap = db.q("SELECT giorno, COUNT(DISTINCT preso) AS n FROM nba_infortuni WHERE giorno BETWEEN %s AND %s "
                "GROUP BY giorno ORDER BY giorno", (g["dal"], g["al"]), many=True) or []
    ris = db.q("SELECT COUNT(*) AS n, COUNT(convalidato) AS c FROM lega_risultati WHERE stagione = %s AND giornata = %s",
               (s, g["numero"]), one=True)
    righe = [f"🔧 <b>Giornata {g['numero']}</b> ({g['tipo']}) · {g['dal']} → {g['al']} (giorni ET)",
             f"Scadenza: {cal.ora(g['prima_partita'])} · calcolata {g['calcolato'] or '—'}",
             f"Media calcolata: {', '.join(g['media']) if g['media'] is not None else 'non calcolata'} · "
             f"nel calendario: {', '.join(g['media_file']) or 'nessuno'}",
             "Partite NBA: " + (", ".join(f"{p['stato'].replace('STATUS_', '').lower()} {p['n']} (tabellini {p['t']})"
                                          for p in partite) or "nessuna"),
             "Snapshot infortunati: " + (", ".join(f"{f['giorno']:%d/%m} {f['n']}" for f in snap) or "nessuno"),
             f"Risultati: {ris['n']} (convalidati {ris['c']})"]
    await update.effective_message.reply_text("\n".join(righe), parse_mode="HTML")


# ── status valido per il calcolo (deciso da un admin) ─────────────────────────

def _ora(t) -> str:
    from zoneinfo import ZoneInfo
    return t.astimezone(ZoneInfo("Europe/Rome")).strftime("%H:%M")


def _cerca_giocatori(testo: str) -> list[dict]:
    """Giocatori dell'anagrafica abbinati a ESPN che corrispondono al nome (prima quelli a roster)."""
    n = calcolo.norm(testo)
    if not n:
        return []
    tutti = db.q("""SELECT g.id, g.nome_common, g.espn_id, EXISTS (SELECT 1 FROM contratti c WHERE c.giocatore_id = g.id AND c.attivo) AS a_roster
                    FROM giocatori g WHERE g.espn_id IS NOT NULL""", many=True) or []
    from shared import parole_nome as PN               # anche con le parole in un altro ordine (Luca, 31/10)
    esatti = [g for g in tutti if calcolo.norm(g["nome_common"]) == n or PN.stesse_parole(testo, g["nome_common"])]
    trovati = esatti or [g for g in tutti if n in calcolo.norm(g["nome_common"]) or PN.contiene_parole(testo, g["nome_common"])]
    if not trovati:
        nomi = {PN.ordinata(g["nome_common"]): g for g in tutti}
        trovati = [nomi[x] for x in difflib.get_close_matches(PN.ordinata(testo), list(nomi), n=5, cutoff=0.75)]
    return sorted(trovati, key=lambda g: (not g["a_roster"], g["nome_common"]))[:8]


def _scelte(snap: list[dict]) -> list:
    """Gli stati catturati dagli snapshot (None = sano), in un ordine fisso per i bottoni."""
    return sorted({s["stato"] for s in snap}, key=lambda x: (x is None, x or ""))


def schermata_status(gid: int, n: int) -> tuple[str, K | None]:
    s = config.stagione()
    g = db.giornata(s, n)
    gi = db.q("SELECT id, nome_common, espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    if not g or not gi or not gi["espn_id"]:
        return "Giornata o giocatore non trovati.", None
    snap = db.snapshot_giocatore(gi["espn_id"], g["dal"], g["al"])
    giorni_snap = sorted({x["giorno"] for x in snap})
    sq = db.squadre_della_giornata([gi["espn_id"]], g["dal"], g["al"])
    contano = {d: t for (a, d), t in db.snapshot_alla_partita(sq, giorni_snap).items()}
    deciso = db.status_validi(s, n, [gi["espn_id"]])
    t = [f"🩺 <b>{e(gi['nome_common'])}</b> · giornata {n} ({g['dal']:%d/%m}–{g['al']:%d/%m})", ""]
    if not snap:
        t.append("Nessuno snapshot degli infortunati in questa giornata: non c'è niente tra cui scegliere.")
        return "\n".join(t), None
    per_giorno: dict = {}
    for x in snap:
        segno = "★" if contano.get(x["giorno"]) == x["preso"] else ""
        per_giorno.setdefault(x["giorno"], []).append(f"{_ora(x['preso'])}{segno} {e(x['stato'] or 'sano')}")
    for d, lista in per_giorno.items():
        t.append(f"<b>{d:%d/%m}</b>: " + " · ".join(lista))
    t += ["", "★ = lo snapshot che conta per il calcolo in quel giorno: l'ultimo prima della partita della sua squadra "
              "(senza partita quel giorno, l'ultimo prima della prima partita NBA)."]
    if gi["espn_id"] in deciso:
        t.append(f"✅ <b>Deciso da un admin: {e(deciso[gi['espn_id']] or 'sano')}</b> (vale per tutta la giornata)")
    else:
        t.append("Per ora vale quello degli snapshot. Scegli lo status che vale per tutta la giornata:")
    tasti = [[B(("✅ " if gi["espn_id"] in deciso and deciso[gi["espn_id"]] == st else "") + (st or "sano (disponibile)"),
                callback_data=f"sv:s:{gid}:{n}:{i}")] for i, st in enumerate(_scelte(snap))]
    if gi["espn_id"] in deciso:
        tasti.append([B("↩️ Torna agli snapshot", callback_data=f"sv:a:{gid}:{n}")])
    return "\n".join(t), K(tasti)


async def cmd_set_valid_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/set_valid_status GIOCATORE N: lo status di un giocatore che vale per il calcolo della
    giornata N (media a 0 se indisponibile, FADD), scelto tra quelli catturati dagli snapshot."""
    if not await _solo_admin(update):
        return
    args = list(context.args or [])
    if len(args) < 2 or not args[-1].isdigit():
        await update.effective_message.reply_text("Uso: /set_valid_status GIOCATORE N (es. /set_valid_status Herbert Jones 3)")
        return
    n = int(args.pop())
    if not db.giornata(config.stagione(), n):
        await update.effective_message.reply_text(f"Giornata {n} non trovata.")
        return
    trovati = _cerca_giocatori(" ".join(args))
    if not trovati:
        await update.effective_message.reply_text(f"Nessun giocatore abbinato a ESPN si chiama «{e(' '.join(args))}».", parse_mode="HTML")
        return
    if len(trovati) > 1 and calcolo.norm(trovati[0]["nome_common"]) != calcolo.norm(" ".join(args)):
        await update.effective_message.reply_text("Quale?", reply_markup=K([[B(g["nome_common"], callback_data=f"sv:g:{g['id']}:{n}")]
                                                                           for g in trovati]))
        return
    testo, tasti = schermata_status(trovati[0]["id"], n)
    await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=tasti)


async def cb_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not config.is_admin(update.effective_user.id):
        await q.answer("Solo admin.", show_alert=True)
        return
    parti = q.data.split(":")
    azione, gid, n = parti[1], int(parti[2]), int(parti[3])
    s = config.stagione()
    gi = db.q("SELECT nome_common, espn_id FROM giocatori WHERE id = %s", (gid,), one=True)
    g = db.giornata(s, n)
    from handlers import log, _chi
    if azione == "s" and gi and g:
        scelte = _scelte(db.snapshot_giocatore(gi["espn_id"], g["dal"], g["al"]))
        i = int(parti[4])
        if i >= len(scelte):
            await q.answer("Gli snapshot sono cambiati: riprova.", show_alert=True)
        else:
            db.set_status_valido(s, n, gi["espn_id"], scelte[i], update.effective_user.id)
            from registro import segna_sync
            segna_sync(update.effective_user, "admin", "status valido", giocatore_id=gid, oggetto=gi["nome_common"],
                       prima="dagli snapshot", dopo=scelte[i] or "sano", nota=f"giornata {n}")
            await q.answer("Salvato")
            await log(context.bot, f"🩺 Status valido G{n} di {e(gi['nome_common'])}: <b>{e(scelte[i] or 'sano')}</b> "
                                   f"(deciso da {_chi(update)})")
    elif azione == "a" and gi:
        db.togli_status_valido(s, n, gi["espn_id"])
        from registro import segna_sync
        segna_sync(update.effective_user, "admin", "status valido tolto", giocatore_id=gid, oggetto=gi["nome_common"],
                   dopo="dagli snapshot", nota=f"giornata {n}")
        await q.answer("Torna agli snapshot")
        await log(context.bot, f"🩺 Status G{n} di {e(gi['nome_common'])}: di nuovo dagli snapshot ({_chi(update)})")
    else:
        await q.answer()
    testo, tasti = schermata_status(gid, n)
    await q.edit_message_text(testo, parse_mode="HTML", reply_markup=tasti)


def ricalcola_fp(stagione: str) -> dict:
    """Fantapunti della stagione coi pesi di adesso (config/settings.json), dalle statistiche già salvate:
    i tabellini di ESPN (nba_tabellini.fp) e le medie di basketball-reference (bref_stats.fantamedia,
    tabella del bot principale: il trigger si riscrive coi pesi nuovi e ricalcola). I risultati già
    convalidati (lega_risultati) restano come sono."""
    from shared import regole
    expr = regole.espressione_sql(prefisso="t.")
    n_tab = db.q(f"""WITH x AS (UPDATE nba_tabellini t SET fp = ROUND(({expr})::numeric, 2) FROM nba_partite p
                                WHERE p.espn_id = t.partita AND p.stagione = %s RETURNING 1)
                     SELECT COUNT(*) AS n FROM x""", (stagione,), one=True)["n"]
    n_bref = 0
    if db.q("SELECT to_regclass('bref_stats') AS t", one=True)["t"]:
        regole.allinea_bref(db.q)
        n_bref = db.q("""WITH x AS (UPDATE bref_stats SET stagione = stagione WHERE stagione = %s RETURNING 1)
                         SELECT COUNT(*) AS n FROM x""", (stagione,), one=True)["n"]
    return {"tabellini": n_tab, "bref": n_bref}


async def cmd_dev_ricalcola_fp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dev_ricalcola_fp [STAGIONE] (solo dev): dopo un cambio di pesi_fantapunti in settings.json."""
    if not (config.dev_id() and update.effective_user.id == config.dev_id()):
        return
    from handlers import log
    from shared import regole
    s = context.args[0] if context.args else config.stagione()
    r = ricalcola_fp(s)
    pesi = ", ".join(f"{k} {testo_punti(float(v))}" for k, v in regole.pesi_fantapunti().items())
    t = (f"🔁 Fantapunti della stagione {s} ricalcolati coi pesi di adesso: {r['tabellini']} righe di tabellini ESPN, "
         f"{r['bref']} righe di basketball-reference. Risultati già convalidati non toccati.\nPesi: {pesi}")
    await update.effective_message.reply_text(t)
    await log(context.bot, t)
    from registro import segna_sync
    segna_sync(update.effective_user, "dev", "fantapunti ricalcolati", oggetto=f"stagione {s}",
               dopo=f"{r['tabellini']} tabellini, {r['bref']} righe bref", nota=f"pesi: {pesi}")


def get_handlers() -> list:
    return [
        CommandHandler("set_valid_status", cmd_set_valid_status),
        CallbackQueryHandler(cb_status, pattern=r"^sv:"),
        CommandHandler("dev_giornata", cmd_dev_giornata),
        CommandHandler("tabellini", cmd_tabellini),
        CommandHandler("espn_giocatori", cmd_espn_giocatori),
        CommandHandler("espn_mancanti", cmd_espn_mancanti),
        CommandHandler("espn_abbina", cmd_espn_abbina),
        CommandHandler("fantapunti", cmd_fantapunti),
        CommandHandler("dev_ricalcola_fp", cmd_dev_ricalcola_fp),
    ]

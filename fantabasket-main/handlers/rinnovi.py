"""
Rinnovi normali (v7.32.0, regolamento «Rinnovi dei giocatori» + Luca, 26/11/2026).

  - Fase dei rinnovi: ogni squadra ha due rinnovi per stagione, uno da ¼ e uno da ½, in qualsiasi
    ordine, ognuno sul giocatore che vuole. Non si accumulano negli anni né si cedono.
  - Rinnovabili: i contratti appena diventati x1 con il cambio di stagione, e gli ex rookie usciti dal
    IV anno (x0, già con la Doncic d'ufficio se spettava: si parte da quell'importo). Un x1 arrivato con
    una trade lo rinnova chi lo ha adesso.
  - Nuovo contratto = vecchio + ¼ (o + ½) per eccesso all'intero, mai sotto il minimo della tabella per la
    fantamedia della stagione appena finita. Durata x2 o x3 (x3 obbligatorio da soglia_anni_3, 35M).
  - Vale da subito: sostituisce il contratto di questa stagione (movimento 'renewed').
  - Cap dopo il rinnovo: sopra 150M avviso (va rientrato per la regular season), sopra il tetto
    dell'offseason (165M) non si può.
  - Lo fanno il GM (/rinnovo o 📝 nel /menu) e gli admin dal pannello; si annulla entro 24 ore
    (torna il contratto di prima e il rinnovo torna libero).
Callback: rn:… (GM) e rna:<team>:… (admin), rna:scegli (elenco squadre).
"""
import html
import logging
from datetime import timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
import settings
import teams as tm
from settings import solo_privato
from handlers.stagione import FASE_RINNOVI, FASI_ADMIN_RINNOVI, StagioneErrore, fantamedia_max, _nuovo_contratto

logger = logging.getLogger(__name__)

# tipo → (simbolo, numeratore, denominatore): +¼ = ×5/4, +½ = ×3/2
TIPI = {"quarto": ("¼", 5, 4), "mezzo": ("½", 3, 2)}
ORE_ANNULLA = 24


def aumento(importo: int, tipo: str) -> int:
    """Vecchio stipendio + ¼ o + ½, per eccesso all'intero (aritmetica intera)."""
    _, num, den = TIPI[tipo]
    return -(-int(importo) * num // den)


def anni_possibili(importo: int) -> list[int]:
    return [3] if settings.anni_minimi_contratto(importo) >= 3 else [2, 3]


def _stagione() -> int:
    return int(settings.stagione_corrente())


def etichetta_stagione(s: int) -> str:
    return f"{s}-{str(s + 1)[2:]}"


def _num(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


# ── regole ─────────────────────────────────────────────────────────────────────

def usati(team_id: str, stagione: int | None = None) -> dict[str, dict]:
    """I rinnovi in vigore della squadra nella stagione: tipo → riga (con il nome del giocatore)."""
    s = str(stagione or _stagione())
    righe = db._q("""SELECT r.*, g.nome_common FROM rinnovi_normali r JOIN giocatori g ON g.id = r.giocatore_id
                     WHERE r.stagione = %s AND r.team_id = %s AND r.annullato IS NULL""", (s, team_id), many=True) or []
    return {r["tipo"]: r for r in righe}


def annullabile(r: dict) -> bool:
    from utils import ROME
    from datetime import datetime
    return datetime.now(ROME) - r["creato"] < timedelta(hours=ORE_ANNULLA)


def candidati(team_id: str) -> list[dict]:
    """Giocatori rinnovabili della squadra, ognuno con la base, la fantamedia e il minimo da tabella."""
    s = _stagione()
    out = []
    for r in db.get_roster_team(team_id, senza_10day=True):
        if r["tipo_contratto"] != "normale" or r.get("rfa"):
            continue
        x1 = r["anni_residui"] == 1 and int(r["stagione_firma"]) < s
        ex_rookie = r["anni_residui"] == 0 and int(r["anni_originali"]) == 0 and int(r["stagione_firma"]) == s
        if not (x1 or ex_rookie):
            continue
        fm = fantamedia_max(r["giocatore_id"], [s - 1])
        minimo = settings.minimo_contratto_per_media(fm) if fm is not None else 1
        out.append({**r, "base": int(r["importo_originale"]), "ex_rookie": ex_rookie, "fantamedia": fm,
                    "minimo": minimo, "anni_ora": 0 if ex_rookie else 1})
    return sorted(out, key=lambda c: (-c["base"], c["nome_common"]))


def opzione(c: dict, tipo: str) -> dict:
    """Il rinnovo `tipo` per il candidato: importo, anni possibili e da dove viene l'importo."""
    alzato = aumento(c["base"], tipo)
    imp = max(alzato, c["minimo"])
    return {"tipo": tipo, "simbolo": TIPI[tipo][0], "alzato": alzato, "importo": imp,
            "da_tabella": imp > alzato, "anni": anni_possibili(imp)}


def cap_dopo(team: dict, c: dict, importo: int) -> int:
    """Cap occupato della squadra se il candidato passa a `importo` (con l'eventuale Cam Thomas)."""
    s = str(_stagione())
    ora = db.cap_occupato_team(team["id"], s)
    peso_ora = int(c["importo"]) if c.get("pesa_cap") else 0
    return ora - peso_ora + max(int(importo), int(c.get("cam_thomas") or 0))


def blocco(team: dict, c: dict, importo: int) -> str | None:
    """Perché il rinnovo non si può fare (cap oltre il tetto, roster pieno per un x0), o None."""
    dopo = cap_dopo(team, c, importo)
    tetto = settings.cap_limite_team(team)
    if dopo > tetto:
        return f"cap a {dopo}M, sopra il tetto di {tetto}M"
    if not c.get("occupa_slot") and db.slot_occupati(db.get_roster_team(team["id"]) or []) >= settings.max_roster():
        return f"roster pieno ({settings.max_roster()}): l'x0 rinnovato occupa uno slot"
    return None


def esegui(team_id: str, giocatore_id: int, tipo: str, anni: int, da: str) -> dict:
    """Il rinnovo: contratto nuovo (normale, firmato in questa stagione) + movimento 'renewed' + riga in
    rinnovi_normali, tutto in una transazione. StagioneErrore se non si può."""
    import psycopg2
    import psycopg2.extras
    if tipo not in TIPI:
        raise StagioneErrore("❌ Rinnovo sconosciuto.")
    team = tm.get_team_by_id(team_id)
    s = _stagione()
    gia = usati(team_id, s).get(tipo)
    if gia:
        raise StagioneErrore(f"❌ Il rinnovo da {TIPI[tipo][0]} è già usato per {gia['nome_common']}.")
    c = next((x for x in candidati(team_id) if x["giocatore_id"] == giocatore_id), None)
    if not c:
        raise StagioneErrore("❌ Il giocatore non è rinnovabile per questa squadra (non all'ultimo anno, già "
                             "rinnovato o dichiarato RFA).")
    o = opzione(c, tipo)
    if anni not in o["anni"]:
        raise StagioneErrore(f"❌ A {o['importo']}M il contratto va fatto x3.")
    perche = blocco(team, c, o["importo"])
    if perche:
        raise StagioneErrore(f"❌ Non si può: {perche}.")
    prima, dopo = f"{c['base']}x{c['anni_ora']}", f"{o['importo']}x{anni}"
    nota = f"Rinnovo da {o['simbolo']}: {prima} → {dopo}" + (
        f" (minimo da tabella, fantamedia {_num(c['fantamedia'])})" if o["da_tabella"] else "")
    v = {"contratto_id": c["contratto_id"], "giocatore_id": giocatore_id, "nome": c["nome_common"],
         "importo_nuovo": o["importo"], "anni_nuovi": anni, "tipo": "normale"}
    try:
        with db.get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                nuovo = _nuovo_contratto(cur, v, s, "renewed", nota, False)
                cur.execute("""INSERT INTO rinnovi_normali (stagione, team_id, tipo, giocatore_id, contratto_vecchio,
                                                            contratto_nuovo, prima, dopo, da)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                            (str(s), team_id, tipo, giocatore_id, c["contratto_id"], nuovo, prima, dopo, da))
                rid = cur.fetchone()["id"]
    except psycopg2.errors.UniqueViolation:
        raise StagioneErrore(f"❌ Il rinnovo da {TIPI[tipo][0]} è appena stato usato.")
    return {**c, **o, "anni_scelti": anni, "prima": prima, "dopo": dopo, "id": rid, "nota": nota,
            "cap_dopo": cap_dopo(team, {**c, "importo": o["importo"], "pesa_cap": True}, o["importo"])}


def annulla(team_id: str, rinnovo_id: int) -> dict:
    r = db._q("SELECT r.*, g.nome_common FROM rinnovi_normali r JOIN giocatori g ON g.id = r.giocatore_id "
              "WHERE r.id = %s AND r.team_id = %s AND r.annullato IS NULL", (rinnovo_id, team_id), one=True)
    if not r:
        raise StagioneErrore("❌ Rinnovo non trovato o già annullato.")
    if not annullabile(r):
        raise StagioneErrore(f"❌ Sono passate più di {ORE_ANNULLA} ore: il rinnovo non si annulla più.")
    try:
        db.annulla_rinnovo(rinnovo_id)
    except ValueError as e:
        raise StagioneErrore(f"❌ Non si annulla: {e}.")
    return r


# ── testi ──────────────────────────────────────────────────────────────────────

def _cb(admin_team: str | None, *parti) -> str:
    return ":".join(["rna", admin_team, *parti] if admin_team else ["rn", *parti])


def _navigazione(admin_team: str | None) -> list:
    if admin_team:
        return [InlineKeyboardButton("← Squadre", callback_data="rna:scegli"),
                InlineKeyboardButton("← Menu admin", callback_data="adm:home")]
    return [InlineKeyboardButton("🏠 Menu", callback_data="menu:home"),
            InlineKeyboardButton("✖️ Chiudi", callback_data="nav:x")]


def _riga_fm(c: dict) -> str:
    fm = c["fantamedia"]
    return (f"fantamedia {etichetta_stagione(_stagione() - 1)}: {_num(fm)} → minimo {c['minimo']}M" if fm is not None
            else "nessuna fantamedia la stagione scorsa → minimo 1M")


def testo_lista(team: dict, admin_team: str | None) -> tuple[str, InlineKeyboardMarkup]:
    from utils import format_dt
    s = _stagione()
    u = usati(team["id"], s)
    cand = candidati(team["id"])
    kb_cand = []
    righe = [f"📝 <b>Rinnovi — {html.escape(team['nome'])}</b>",
             "<i>Due rinnovi a stagione, uno da ¼ e uno da ½, sui giocatori all'ultimo anno (appena diventati x1, o "
             "ex rookie usciti dal IV anno). Mai sotto il minimo da tabella per la fantamedia della stagione appena "
             f"finita. Durata x2 o x3 (x3 da {settings.soglia_anni_3()}M). Non sei obbligato a usarli tutti e due, né "
             f"insieme. Vale da subito, si annulla entro {ORE_ANNULLA} ore.</i>", ""]
    kb = []
    for tipo, (simbolo, _, _) in TIPI.items():
        r = u.get(tipo)
        if not r:
            righe.append(f"Da {simbolo}: <b>libero</b>")
            continue
        righe.append(f"Da {simbolo}: <b>{html.escape(r['nome_common'])}</b> {r['prima']} → {r['dopo']}")
        if annullabile(r):
            from utils import ROME
            righe[-1] += f" <i>(annullabile fino al {format_dt(r['creato'].astimezone(ROME) + timedelta(hours=ORE_ANNULLA))})</i>"
            kb.append([InlineKeyboardButton(f"↩️ Annulla il rinnovo di {r['nome_common']}",
                                            callback_data=_cb(admin_team, "u", str(r["id"])))])
    righe.append("")
    liberi = [t for t in TIPI if t not in u]
    if not liberi:
        righe.append("<i>Hai usato tutti e due i rinnovi.</i>")
    elif not cand:
        righe.append("Nessun giocatore da rinnovare.")
    else:
        righe.append("<b>Rinnovabili</b>")
        for c in cand:
            righe.append(f"• <b>{html.escape(c['nome_common'])}</b> {c['base']}x{c['anni_ora']}"
                         + (" (ex rookie)" if c["ex_rookie"] else "") + f" · {_riga_fm(c)}")
            kb_cand.append([InlineKeyboardButton(f"{c['nome_common']} ({c['base']}x{c['anni_ora']})",
                                                 callback_data=_cb(admin_team, "g", str(c["giocatore_id"])))])
    kb = kb_cand + kb + [_navigazione(admin_team)]
    return "\n".join(righe), InlineKeyboardMarkup(kb)


def testo_anteprima(team: dict, c: dict, admin_team: str | None) -> tuple[str, InlineKeyboardMarkup]:
    u = usati(team["id"])
    tetto_rs = settings.cap_massimo()
    righe = [f"📝 <b>Rinnovo — {html.escape(c['nome_common'])}</b>", "",
             f"Contratto attuale: {c['base']}x{c['anni_ora']}" + (" (ex rookie)" if c["ex_rookie"] else ""),
             _riga_fm(c)[0].upper() + _riga_fm(c)[1:], ""]
    kb = []
    for tipo in TIPI:
        o = opzione(c, tipo)
        esatto = c["base"] * TIPI[tipo][1] / TIPI[tipo][2]
        alzato = f"{o['alzato']}M" if o["da_tabella"] else f"<b>{o['alzato']}M</b>"
        conto = f"{c['base']} + {o['simbolo']} = " + (alzato if o["alzato"] == esatto else f"{_num(esatto)} → {alzato}")
        if o["da_tabella"]:
            conto += f" → <b>{o['importo']}M</b> (minimo da tabella)"
        if tipo in u:
            righe.append(f"<b>Da {o['simbolo']}</b>: {conto}\n   <i>già usato per {html.escape(u[tipo]['nome_common'])}</i>")
            continue
        dopo = cap_dopo(team, c, o["importo"])
        perche = blocco(team, c, o["importo"])
        riga = f"<b>Da {o['simbolo']}</b>: {conto}\n   cap dopo il rinnovo: {dopo}M"
        if perche:
            riga += f"\n   ⛔ non si può: {html.escape(perche)}"
        elif dopo > tetto_rs:
            riga += f"\n   ⚠️ sopra {tetto_rs}M: va rientrato entro l'inizio della regular season"
        righe.append(riga)
        if not perche:
            kb.append([InlineKeyboardButton(f"{o['simbolo']} · {o['importo']}x{a}",
                                            callback_data=_cb(admin_team, "s", str(c["giocatore_id"]), tipo, str(a)))
                       for a in o["anni"]])
    righe += ["", f"<i>Durata x2 o x3 (da {settings.soglia_anni_3()}M solo x3). Tocca un rinnovo per la simulazione, "
                  f"poi confermi. Puoi farne uno solo, o uno adesso e l'altro dopo; si annulla entro {ORE_ANNULLA} ore.</i>"]
    kb.append([InlineKeyboardButton("← Indietro", callback_data=_cb(admin_team, "l"))])
    return "\n".join(righe), InlineKeyboardMarkup(kb)


def testo_simulazione(team: dict, gid: int, tipo: str, anni: int, admin_team: str | None) -> tuple[str, InlineKeyboardMarkup]:
    """Il rinnovo scelto, simulato: contratto prima e dopo, fino a quando, cap prima e dopo. Niente è scritto finché
    non si conferma. StagioneErrore se non si può."""
    if tipo not in TIPI:
        raise StagioneErrore("❌ Rinnovo sconosciuto.")
    c = next((x for x in candidati(team["id"]) if x["giocatore_id"] == gid), None)
    if not c:
        raise StagioneErrore("❌ Giocatore non più rinnovabile.")
    gia = usati(team["id"]).get(tipo)
    if gia:
        raise StagioneErrore(f"❌ Il rinnovo da {TIPI[tipo][0]} è già usato per {gia['nome_common']}.")
    o = opzione(c, tipo)
    if anni not in o["anni"]:
        raise StagioneErrore(f"❌ A {o['importo']}M il contratto va fatto x3.")
    perche = blocco(team, c, o["importo"])
    if perche:
        raise StagioneErrore(f"❌ Non si può: {perche}.")
    s = _stagione()
    ora, dopo = db.cap_occupato_team(team["id"], str(s)), cap_dopo(team, c, o["importo"])
    tetto_rs = settings.cap_massimo()
    righe = [f"📝 <b>Simulazione — {html.escape(c['nome_common'])}</b>", "",
             f"Rinnovo da {o['simbolo']}, x{anni}",
             f"Contratto: {c['base']}x{c['anni_ora']} → <b>{o['importo']}x{anni}</b>, da questa stagione fino al "
             f"{etichetta_stagione(s + anni - 1)}" + (" (minimo da tabella)" if o["da_tabella"] else ""),
             f"Cap: {ora}M → <b>{dopo}M</b> (spazio: {tetto_rs - dopo}M sotto {tetto_rs}, "
             f"{settings.cap_limite_team(team) - dopo}M sotto {settings.cap_limite_team(team)})"]
    if dopo > tetto_rs:
        righe.append(f"⚠️ Sopra {tetto_rs}M: va rientrato entro l'inizio della regular season.")
    altro = [t for t in TIPI if t != tipo and t not in usati(team["id"])]
    righe += ["", "<i>Non è ancora fatto: conferma per rinnovare. "
                  + (f"Il rinnovo da {TIPI[altro[0]][0]} resta libero, anche per dopo." if altro else "")
                  + f" Si annulla entro {ORE_ANNULLA} ore.</i>"]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma", callback_data=_cb(admin_team, "ok", str(gid), tipo, str(anni))),
        InlineKeyboardButton("← Indietro", callback_data=_cb(admin_team, "g", str(gid)))]])
    return "\n".join(righe), kb


async def _annuncia(bot, testo: str):
    ch = settings.load_globals().get("main_channel_id")
    if ch:
        try:
            await bot.send_message(chat_id=ch, text=testo, parse_mode="HTML")
        except Exception as e:
            logger.warning("Annuncio rinnovo: %s", e)


# ── comandi e bottoni ──────────────────────────────────────────────────────────

@solo_privato
async def cmd_rinnovo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team = tm.get_team_by_gm(update.effective_user.id)
    if not team:
        await update.effective_message.reply_text("⛔ Non sei registrato come GM.")
        return
    if settings.fase() != FASE_RINNOVI:
        await update.effective_message.reply_text("❌ I rinnovi si fanno nella fase dei rinnovi.")
        return
    testo, kb = testo_lista(team, None)
    await update.effective_message.reply_text(testo, parse_mode="HTML", reply_markup=kb)


async def cb_rinnovi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parti = query.data.split(":")
    user = query.from_user
    if parti[0] == "rna":
        if not settings.is_admin(user.id):
            await query.answer("⛔ Solo admin.", show_alert=True)
            return
        if settings.fase() not in FASI_ADMIN_RINNOVI:
            await query.answer("❌ Solo nelle fasi rinnovi e draft.", show_alert=True)
            return
        if parti[1] == "scegli":
            await query.answer()
            bottoni = [InlineKeyboardButton(t["nome"], callback_data=f"rna:{t['id']}:l") for t in tm.get_all_teams()]
            kb = [bottoni[i:i + 2] for i in range(0, len(bottoni), 2)]
            kb.append([InlineKeyboardButton("← Menu admin", callback_data="adm:home")])
            await query.edit_message_text("📝 Rinnovi: scegli la squadra", reply_markup=InlineKeyboardMarkup(kb))
            return
        admin_team, azione, resto = parti[1], parti[2], parti[3:]
        team = tm.get_team_by_id(admin_team)
        chi = f"un admin ({user.first_name or user.username})"
    else:
        admin_team, azione, resto = None, parti[1], parti[2:]
        team = tm.get_team_by_gm(user.id)
        if not team:
            await query.answer("⛔ Non sei registrato come GM.", show_alert=True)
            return
        if settings.fase() != FASE_RINNOVI:
            await query.answer("❌ Solo nella fase dei rinnovi.", show_alert=True)
            return
        chi = None
    await query.answer()
    bot = query.get_bot()
    veste = "admin" if admin_team else "gm"
    per_conto = " per conto della squadra" if admin_team else ""
    gm_nome = html.escape(team.get("gm_nome") or team["nome"])
    from handlers.registro import segna
    from handlers.stagione import _sync, _avvisa_gm

    try:
        if azione == "l":
            testo, kb = testo_lista(team, admin_team)
            await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
        elif azione == "g":
            gid = int(resto[0])
            c = next((x for x in candidati(team["id"]) if x["giocatore_id"] == gid), None)
            if not c:
                raise StagioneErrore("❌ Giocatore non più rinnovabile.")
            testo, kb = testo_anteprima(team, c, admin_team)
            await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
        elif azione == "s":                           # v7.32.1 (Luca, 26/11): prima la simulazione, poi la conferma
            gid, tipo, anni = int(resto[0]), resto[1], int(resto[2])
            testo, kb = testo_simulazione(team, gid, tipo, anni, admin_team)
            await query.edit_message_text(testo, parse_mode="HTML", reply_markup=kb)
        elif azione == "ok":
            gid, tipo, anni = int(resto[0]), resto[1], int(resto[2])
            r = esegui(team["id"], gid, tipo, anni, chi or f"GM {user.id}")
            await segna(bot, user, veste, f"rinnovo da {r['simbolo']}{per_conto}", squadre=team["id"],
                        giocatore_id=gid, oggetto=r["nome_common"], prima=r["prima"], dopo=r["dopo"],
                        nota="minimo da tabella" if r["da_tabella"] else None)
            avviso = (f"\n⚠️ Cap a {r['cap_dopo']}M: sopra {settings.cap_massimo()}M, va rientrato entro l'inizio "
                      f"della regular season." if r["cap_dopo"] > settings.cap_massimo() else "")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 Rinnovi", callback_data=_cb(admin_team, "l"))]])
            await query.edit_message_text(f"✅ <b>{html.escape(r['nome_common'])}</b> rinnovato: {r['prima']} → "
                                          f"<b>{r['dopo']}</b> (da {r['simbolo']}).{avviso}\n<i>Si annulla entro "
                                          f"{ORE_ANNULLA} ore da 📝 Rinnovi.</i>", parse_mode="HTML", reply_markup=kb)
            await _annuncia(bot, f"📝 <b>{gm_nome}</b> rinnova <b>{html.escape(r['nome_common'])}</b>: "
                                 f"{r['prima']} → <b>{r['dopo']}</b> <i>(rinnovo da {r['simbolo']}"
                                 + (", minimo da tabella" if r["da_tabella"] else "") + ")</i>"
                                 + (f"\n<i>Registrato da {chi}</i>" if chi else ""))
            if chi:
                await _avvisa_gm(bot, team, f"🛠 {chi} ha rinnovato <b>{html.escape(r['nome_common'])}</b>: "
                                            f"{r['prima']} → {r['dopo']} (da {r['simbolo']}).")
            _sync(team["id"])
        elif azione == "u":
            rid = int(resto[0])
            r = next((x for x in usati(team["id"]).values() if x["id"] == rid), None)
            if not r:
                raise StagioneErrore("❌ Rinnovo non trovato o già annullato.")
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ Annulla il rinnovo", callback_data=_cb(admin_team, "uok", str(rid))),
                InlineKeyboardButton("← Indietro", callback_data=_cb(admin_team, "l"))]])
            await query.edit_message_text(
                f"↩️ Annulli il rinnovo di <b>{html.escape(r['nome_common'])}</b> ({r['prima']} → {r['dopo']})?\n"
                f"Torna {r['prima']} e il rinnovo da {TIPI[r['tipo']][0]} torna libero.", parse_mode="HTML", reply_markup=kb)
        elif azione == "uok":
            r = annulla(team["id"], int(resto[0]))
            simbolo = TIPI[r["tipo"]][0]
            await segna(bot, user, veste, f"rinnovo da {simbolo} annullato{per_conto}", squadre=team["id"],
                        giocatore_id=r["giocatore_id"], oggetto=r["nome_common"], prima=r["dopo"], dopo=r["prima"])
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 Rinnovi", callback_data=_cb(admin_team, "l"))]])
            await query.edit_message_text(f"↩️ Rinnovo di <b>{html.escape(r['nome_common'])}</b> annullato: torna "
                                          f"{r['prima']}. Il rinnovo da {simbolo} è di nuovo libero.",
                                          parse_mode="HTML", reply_markup=kb)
            await _annuncia(bot, f"↩️ <b>{gm_nome}</b> annulla il rinnovo di <b>{html.escape(r['nome_common'])}</b>: "
                                 f"torna {r['prima']}" + (f"\n<i>Registrato da {chi}</i>" if chi else ""))
            if chi:
                await _avvisa_gm(bot, team, f"🛠 {chi} ha annullato il rinnovo di <b>{html.escape(r['nome_common'])}</b>: "
                                            f"torna {r['prima']}.")
            _sync(team["id"])
    except StagioneErrore as e:
        await query.edit_message_text(str(e), reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📝 Rinnovi", callback_data=_cb(admin_team, "l"))]]))


def get_handlers() -> list:
    return [
        CommandHandler("rinnovo", cmd_rinnovo),
        CallbackQueryHandler(cb_rinnovi, pattern=r"^rna?:"),
    ]

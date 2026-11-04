"""
Comandi di klra (mockup approvati da Luca il 04/11). Per GM, admin e dev (shared/solo_lega).

/sistemi                      la lista; ogni sistema ha la sua scheda (cosa cambia rispetto all'Ufficiale) coi
                              bottoni Usa questo, Copia e modifica, Modifica (solo chi l'ha creato), Classifica,
                              Confronta, Risultati; l'editor in editor.py
/usa NOME                     il sistema attivo (di default l'Ufficiale)
/classifica [NOME]            immagine, col sistema attivo o con quello indicato
/giornata [N] [NOME]          tabellone della giornata (default l'ultima convalidata)
/partita [SQUADRA] [N] [NOME] una sfida in dettaglio, coi bonus del sistema
/risultati [N] [NOME]         in testo, con 🔄 dove finisce diversamente dalla realtà
/confronta [NOME]             classifica e partite: Ufficiale contro il sistema
/top [N|DA A] [firmati] [NOME] i migliori per fantamedia col sistema (come /top di loucabot), con quella della lega
/klra_verifica (dev)          l'Ufficiale di klra contro i risultati convalidati della lega
Si calcolano solo le giornate convalidate dalla lega.
"""
import asyncio
import html
import logging
import re

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

import config
import db
from klra import editor as ED
from klra import motore as M
from klra import regole as KR
from klra import sistemi as SI
from klra import viste as V

logger = logging.getLogger(__name__)
TEMPI = {"read_timeout": 60, "write_timeout": 60, "connect_timeout": 30}


def e(x) -> str:
    return html.escape(str(x), quote=False)


PUBBLICI = [("sistemi", "I sistemi di punteggio: scegli, copia, modifica"),
            ("classifica", "La classifica col tuo sistema [NOME]"),
            ("giornata", "Una giornata col tuo sistema [N] [NOME]"),
            ("partita", "Una sfida col tuo sistema [SQUADRA] [N] [NOME]"),
            ("risultati", "I risultati in testo [N] [NOME]"),
            ("confronta", "Ufficiale contro un sistema [NOME]"),
            ("top", "Migliori per fantamedia col tuo sistema [N] o [DA A] [firmati] [NOME]"),
            ("usa", "Scegli il tuo sistema: /usa NOME"),
            ("start", "Cos'è klra")]
DEV = [("klra_verifica", "L'Ufficiale di klra contro i risultati convalidati della lega")]


def comandi_pubblici() -> set[str]:
    return {c for c, _ in PUBBLICI} | {"aiuto"}


async def registra(bot) -> None:
    try:
        await bot.set_my_commands([BotCommand(c, d) for c, d in PUBBLICI], scope=BotCommandScopeAllPrivateChats())
        if config.dev_id():
            await bot.set_my_commands([BotCommand(c, d) for c, d in PUBBLICI + DEV], scope=BotCommandScopeChat(config.dev_id()))
    except Exception as err:
        logger.warning("Comandi: %s", err)


def _quando(x) -> str:
    from zoneinfo import ZoneInfo
    return f"{x.astimezone(ZoneInfo('Europe/Rome')):%d/%m}" if x else ""


# ── lista e scheda ───────────────────────────────────────────────────────────────

def lista(uid: int) -> tuple[str, K]:
    att = SI.attivo(uid)
    tutti = SI.tutti()
    righe = [f"🧪 <b>Sistemi di punteggio</b> · {e(V._anno(config.stagione()))}",
             "<b>⚠️ NON UFFICIALE</b>: niente di quello che vedi in klra conta per la lega; i risultati veri sono quelli di loucabot.",
             "", f"Il tuo attivo: <b>{e(att['nome'])}</b>", ""]
    for s in tutti:
        segno = "⭐" if s["id"] == att["id"] else ("🏛" if s["ufficiale"] else "📊" if s.get("predefinito") else "▫️")
        autore = "" if s["ufficiale"] or s.get("predefinito") else f" · {e(s.get('autore_nome') or '?')}"
        righe.append(f"{segno} <b>{e(s['nome'])}</b>{autore} · <i>{e(V.riassunto(s, 2))}</i>")
    bot = [B(("⭐ " if s["id"] == att["id"] else "") + s["nome"], callback_data=f"ks:v:{s['id']}") for s in tutti]
    kb = [bot[i:i + 2] for i in range(0, len(bot), 2)]
    if SI.bozza(uid):
        kb.append([B("✏️ Riprendi la bozza", callback_data="ks:e")])
    righe += ["", "Tocca un sistema per la sua scheda. Un sistema nuovo si fa copiandone un altro."]
    return "\n".join(righe), K(kb)


def scheda(s: dict, uid: int) -> tuple[str, K]:
    att = SI.attivo(uid)
    righe = [f"{'⭐ ' if s['id'] == att['id'] else ''}<b>{e(s['nome'])}</b>"
             + ("" if s["ufficiale"] or s.get("predefinito") else f" · di {e(s.get('autore_nome') or '?')} · {_quando(s['creato'])}")
             + (f" · modificato il {_quando(s['modificato'])}" if s.get("modificato") else "")]
    if s.get("base_id"):
        b = SI.per_id(s["base_id"])
        if b:
            righe.append(f"<i>copia di {e(b['nome'])}</i>")
    if s["ufficiale"]:
        righe.append("Le regole della lega (si aggiornano se cambia il regolamento).")
    elif s.get("predefinito") == "fantamedie":
        righe.append("Predefinito: a ogni giornata chi ha giocato prende la sua media della stagione fino al giorno prima "
                     "(non i punti delle partite); se quest'anno non ha ancora giocato, la fantamedia dell'anno prima, "
                     "se c'è, se no 0. Chi non ha giocato come nella lega (media se la sua squadra NBA non ha partite, "
                     "se no 0). Il resto come la lega. Nessuno lo modifica; si può copiare.")
    else:
        d = KR.differenze(SI.parametri(s))
        righe += ["", "Cosa cambia rispetto all'Ufficiale:"] + ([f"• {e(x)}" for x in d] if d else ["• niente: è uguale"])
    if s["id"] == att["id"]:
        righe += ["", "È il tuo sistema attivo."]
    kb = []
    r1 = [] if s["id"] == att["id"] else [B("✅ Usa questo", callback_data=f"ks:u:{s['id']}")]
    r1.append(B("📋 Copia e modifica", callback_data=f"ks:c:{s['id']}"))
    kb.append(r1)
    if SI.puo_modificare(s, uid):
        kb.append([B("✏️ Modifica", callback_data=f"ks:m:{s['id']}")])
    kb.append([B("🏆 Classifica", callback_data=f"ks:cl:{s['id']}"), B("⚖️ Confronta", callback_data=f"ks:cf:{s['id']}"),
               B("📅 Risultati", callback_data=f"ks:r:{s['id']}")])
    kb.append([B("← Sistemi", callback_data="ks:l")])
    return "\n".join(righe), K(kb)


# ── editor ───────────────────────────────────────────────────────────────────────

def editor_home(uid: int) -> tuple[str, K]:
    bz = SI.bozza(uid)
    base = SI.per_id(bz["base_id"]) if bz else None
    if not bz or not base:
        return "Nessuna bozza aperta: da /sistemi scegli un sistema e «Copia e modifica».", K([[B("← Sistemi", callback_data="ks:l")]])
    P = KR.completa(bz["parametri"])
    titolo = f"✏️ <b>Modifica di {e(base['nome'])}</b>" if bz.get("modifica_id") else f"✏️ <b>Nuovo sistema</b> · copia di {e(base['nome'])}"
    d = KR.differenze(P, SI.parametri(base))
    righe = [titolo, "", "Modifiche finora:" if d else "Nessuna modifica ancora.", *[f"• {e(x)}" for x in d], "",
             "Scegli una sezione."]
    sez = [B(n, callback_data=f"ks:s:{k}") for k, n in ED.SEZIONI.items()]
    kb = [sez[i:i + 2] for i in range(0, len(sez), 2)]
    kb.append([B("💾 Salva" if bz.get("modifica_id") else "💾 Salva e dai un nome", callback_data="ks:sv"),
               B("🗑 Butta", callback_data="ks:x")])
    return "\n".join(righe), K(kb)


def editor_sezione(uid: int, sez: str) -> tuple[str, K]:
    bz = SI.bozza(uid)
    base = SI.per_id(bz["base_id"])
    P, PB = KR.completa(bz["parametri"]), SI.parametri(base)
    bot = []
    for voce, (lab, tipo, _lim) in ED.VOCI[sez].items():
        if not ED.visibile(P, sez, voce):
            continue
        segno = "✏️ " if P[sez][voce] != PB[sez][voce] else ""
        bot.append(B(f"{segno}{lab}: {ED.mostra(P[sez][voce])}", callback_data=f"ks:t:{sez}:{voce}"))
    kb = [bot[i:i + 2] for i in range(0, len(bot), 2)] + [[B("← Sezioni", callback_data="ks:e")]]
    spieg = {"pesi": "Punti per ogni statistica in una partita.",
             "giocatore": "Bonus (o malus, col meno) di una partita del giocatore; 0 = spento. Doppia, tripla e quadrupla "
                          "doppia non si sommano: vale la più alta.",
             "squadra": "Si sommano al totale della squadra nella giornata.",
             "partita": "Le voci a scelta cambiano a ogni tocco.",
             "classifica": "A vittorie come la lega, o a punti."}[sez]
    return f"{ED.SEZIONI[sez]}\n<i>{e(spieg)}</i>\n\n✏️ = diverso da {e(base['nome'])}", K(kb)


# ── comandi ──────────────────────────────────────────────────────────────────────

async def cmd_start(update, context):
    await update.effective_message.reply_text(
        "🧪 <b>klra</b>: la lega con altri sistemi di punteggio.\n"
        "<b>⚠️ È tutto NON UFFICIALE</b>: niente di quello che vedi qui conta per la lega.\n"
        "Stesse formazioni e stessi tabellini, regole diverse: fantapunti, bonus, supplementari, classifica. "
        "I risultati veri restano quelli di loucabot: qui si guarda come sarebbe andata.\n\n"
        "/sistemi per scegliere o creare un sistema; poi /classifica, /giornata, /partita, /risultati e /confronta "
        "usano il tuo (o quello che scrivi dopo il comando). Si calcolano le giornate convalidate dalla lega.",
        parse_mode="HTML")


async def cmd_sistemi(update, context):
    t, kb = await asyncio.to_thread(lista, update.effective_user.id)
    await update.effective_message.reply_text(t, parse_mode="HTML", reply_markup=kb)


async def cmd_usa(update, context):
    s, _ = SI.trova_in_args(list(context.args or []))
    if not s:
        await update.effective_message.reply_text("Uso: /usa NOME (i nomi sono in /sistemi).")
        return
    SI.scegli(update.effective_user.id, s["id"])
    await update.effective_message.reply_text(f"⭐ Ora usi <b>{e(s['nome'])}</b>.", parse_mode="HTML")


def _sistema_e_resto(update, context) -> tuple[dict, list[str]]:
    s, resto = SI.trova_in_args(list(context.args or []))
    return (s or SI.attivo(update.effective_user.id)), resto


def _giornata(resto: list[str]) -> tuple[int | None, str | None]:
    """(giornata, errore): un numero («5» o «G5») negli argomenti, se no l'ultima convalidata."""
    conv = M.giornate_convalidate(config.stagione())
    n = next((int(m.group(1)) for a in resto for m in [re.fullmatch(r"[Gg]?(\d{1,2})", a)] if m), None)
    if n is None:
        return (max(conv) if conv else None), (None if conv else "Nessuna giornata convalidata dalla lega, per ora.")
    if n not in conv:
        return None, f"La giornata {n} non è ancora convalidata dalla lega: klra calcola solo quelle convalidate."
    return n, None


async def _attesa(msg, testo="⏳ Calcolo col sistema…"):
    try:
        return await msg.reply_text(testo)
    except Exception:
        return None


async def _cancella(m):
    if m:
        try:
            await m.delete()
        except Exception:
            pass


async def manda_classifica(msg, s):
    w = await _attesa(msg)
    try:
        png = await asyncio.to_thread(V.img_classifica, s, config.stagione())
        if not png:
            await msg.reply_text("Nessuna giornata convalidata dalla lega, per ora.")
            return
        await msg.reply_photo(png, caption=f"🧪 NON UFFICIALE · 🏆 Classifica col sistema {s['nome']}", **TEMPI)
    finally:
        await _cancella(w)


async def manda_confronta(msg, s):
    w = await _attesa(msg)
    try:
        png = await asyncio.to_thread(V.img_confronta, s, config.stagione())
        if not png:
            await msg.reply_text("Nessuna giornata convalidata dalla lega, per ora.")
            return
        await msg.reply_photo(png, caption=f"🧪 NON UFFICIALE · ⚖️ Ufficiale contro {s['nome']}", **TEMPI)
    finally:
        await _cancella(w)


async def manda_risultati(msg, s, n):
    t = await asyncio.to_thread(V.testo_risultati, s, config.stagione(), n)
    await msg.reply_text(t, parse_mode="HTML")


async def _errore(msg, err, cosa):
    logger.exception(cosa)
    await msg.reply_text(f"❌ {cosa} non riuscito: {e(str(err))[:200]}")


async def cmd_classifica(update, context):
    s, _ = _sistema_e_resto(update, context)
    try:
        await manda_classifica(update.effective_message, s)
    except Exception as err:
        await _errore(update.effective_message, err, "Classifica")


async def cmd_confronta(update, context):
    s, _ = _sistema_e_resto(update, context)
    if s["ufficiale"]:
        await update.effective_message.reply_text("Confrontare l'Ufficiale con sé stesso non dice molto: /confronta NOME "
                                                  "(i nomi sono in /sistemi), o scegli un altro sistema con /usa.")
        return
    try:
        await manda_confronta(update.effective_message, s)
    except Exception as err:
        await _errore(update.effective_message, err, "Confronto")


async def cmd_risultati(update, context):
    s, resto = _sistema_e_resto(update, context)
    n, err = _giornata(resto)
    if err:
        await update.effective_message.reply_text(err)
        return
    try:
        await manda_risultati(update.effective_message, s, n)
    except Exception as er:
        await _errore(update.effective_message, er, "Risultati")


async def cmd_giornata(update, context):
    s, resto = _sistema_e_resto(update, context)
    n, err = _giornata(resto)
    if err:
        await update.effective_message.reply_text(err)
        return
    w = await _attesa(update.effective_message)
    try:
        png = await asyncio.to_thread(V.img_giornata, s, config.stagione(), n)
        await update.effective_message.reply_photo(png, caption=f"🧪 NON UFFICIALE · 📅 Giornata {n} col sistema {s['nome']}", **TEMPI)
    except Exception as er:
        await _errore(update.effective_message, er, "Giornata")
    finally:
        await _cancella(w)


async def _manda_partita(msg, s, n, casa, tr):
    w = await _attesa(msg)
    try:
        png, d = await asyncio.to_thread(V.img_partita, s, config.stagione(), n, casa, tr)
        sq = d["squadre"]
        await msg.reply_photo(png, caption=f"🧪 NON UFFICIALE · 🏀 Giornata {n} · {sq[0]['nome']} {sq[0]['punti']} – {sq[1]['punti']} {sq[1]['nome']} col sistema {s['nome']}",
                              **TEMPI)
    finally:
        await _cancella(w)


async def cmd_partita(update, context):
    import partita
    msg = update.effective_message
    s, resto = _sistema_e_resto(update, context)
    st = config.stagione()
    sq, n, err = partita.leggi_argomenti(resto, config.squadre())
    if err:
        await msg.reply_text(f"❌ {err}\nUso: /partita [SQUADRA] [N] [SISTEMA] oppure /partita SQUADRA - SQUADRA")
        return
    if not sq:
        mia = config.squadra_del_gm(update.effective_user.id)
        if not mia:
            await msg.reply_text("Uso: /partita SQUADRA [N] [SISTEMA] (es. /partita Alfa 3 Hockey).")
            return
        sq = [mia]
    conv = M.giornate_convalidate(st)
    if len(sq) == 2:
        lista_ = [x for x in partita.sfide(st, sq[0]["id"], sq[1]["id"]) if x["giornata"] in conv and (not n or x["giornata"] == n)]
        if not lista_:
            await msg.reply_text("Nessuna loro sfida in una giornata convalidata.")
            return
        if len(lista_) > 1:
            kb = [[B(f"G{x['giornata']}: {config.nome(x['casa'])} – {config.nome(x['trasferta'])}",
                     callback_data=f"ks:pt:{s['id']}:{x['giornata']}:{x['casa']}:{x['trasferta']}")] for x in lista_]
            await msg.reply_text("Quale partita?", reply_markup=K(kb))
            return
        x = lista_[0]
    else:
        n, err = _giornata([str(n)] if n else [])
        if err:
            await msg.reply_text(err)
            return
        p = db.partita_squadra(st, n, sq[0]["id"])
        if not p:
            await msg.reply_text(f"{sq[0]['nome']} non gioca nella giornata {n}.")
            return
        x = {"giornata": n, "casa": p["casa"], "trasferta": p["trasferta"]}
    try:
        await _manda_partita(msg, s, x["giornata"], x["casa"], x["trasferta"])
    except Exception as er:
        await _errore(msg, er, "Partita")


async def cmd_top(update, context):
    import io
    import top_giocatori as TG
    msg = update.effective_message
    s, resto = _sistema_e_resto(update, context)
    da, a, firmati, err = TG.leggi_argomenti(resto)
    if err:
        await msg.reply_text(err)
        return
    w = await _attesa(msg)
    try:
        t = await asyncio.to_thread(V.testo_top, s, config.stagione(), da, a, firmati)
    except Exception as er:
        await _cancella(w)
        await _errore(msg, er, "Top")
        return
    await _cancella(w)
    if len(t) <= TG.LIMITE:
        await msg.reply_text(t)
        return
    await msg.reply_document(document=io.BytesIO(t.encode("utf-8")), filename=f"klra_top_{da}-{a}.md",
                             caption=f"🧪 NON UFFICIALE · 📄 Top {da}–{a} col sistema {s['nome']}: troppo lunga per un messaggio")


async def cmd_verifica(update, context):
    if update.effective_user.id != config.dev_id():
        return
    msg = await update.effective_message.reply_text("⏳ Confronto l'Ufficiale di klra coi risultati convalidati…")
    try:
        d = await asyncio.to_thread(M.verifica, config.stagione())
    except Exception as err:
        logger.exception("verifica")
        await msg.edit_text(f"❌ {e(err)[:300]}")
        return
    await msg.edit_text("✅ L'Ufficiale di klra dà esattamente i risultati della lega." if not d else
                        "⚠️ Differenze:\n" + "\n".join(e(x) for x in d[:40]))


# ── bottoni ──────────────────────────────────────────────────────────────────────

async def cb(update, context):
    q = update.callback_query
    uid = q.from_user.id
    p = q.data.split(":")
    az = p[1]
    privato = q.message and q.message.chat.type == "private"

    async def mostra(t, kb):
        await q.edit_message_text(t, parse_mode="HTML", reply_markup=kb)

    if az in ("c", "m", "e", "s", "t", "sv", "x") and not privato:
        await q.answer("L'editor funziona in privato: scrivimi /sistemi in chat.", show_alert=True)
        return
    if az == "l":
        await q.answer()
        await mostra(*lista(uid))
    elif az == "v":
        s = SI.per_id(p[2])
        await q.answer()
        if s:
            await mostra(*scheda(s, uid))
    elif az == "u":
        s = SI.per_id(p[2])
        if s:
            SI.scegli(uid, s["id"])
            await q.answer(f"Ora usi {s['nome']}")
            await mostra(*scheda(s, uid))
    elif az in ("c", "m"):
        s = SI.per_id(p[2])
        if not s:
            await q.answer()
            return
        if az == "m" and not SI.puo_modificare(s, uid):
            await q.answer("Lo modifica solo chi l'ha creato: fanne una copia.", show_alert=True)
            return
        context.user_data.pop("klra_attesa", None)
        SI.apri_bozza(uid, s, modifica=(az == "m"))
        await q.answer()
        await mostra(*editor_home(uid))
    elif az == "e":
        context.user_data.pop("klra_attesa", None)
        await q.answer()
        await mostra(*editor_home(uid))
    elif az == "s":
        context.user_data.pop("klra_attesa", None)
        if not SI.bozza(uid):
            await q.answer()
            await mostra(*editor_home(uid))
            return
        await q.answer()
        await mostra(*editor_sezione(uid, p[2]))
    elif az == "t":
        sez, voce = p[2], p[3]
        bz = SI.bozza(uid)
        if not bz or sez not in ED.VOCI or voce not in ED.VOCI[sez]:
            await q.answer()
            await mostra(*editor_home(uid))
            return
        P = KR.completa(bz["parametri"])
        if ED.tocca(P, sez, voce):
            SI.salva_bozza(uid, P)
            await q.answer(f"{ED.VOCI[sez][voce][0]}: {ED.mostra(P[sez][voce])}")
            await mostra(*editor_sezione(uid, sez))
            return
        context.user_data["klra_attesa"] = ("valore", sez, voce)
        lab = ED.VOCI[sez][voce][0]
        await q.answer()
        extra = " (o «nessuno»)" if ED.VOCI[sez][voce][1] == "num_o_niente" else ""
        await mostra(f"✏️ <b>{e(lab)}</b>: adesso {e(ED.mostra(P[sez][voce]))}.\nScrivi il nuovo valore{extra}.",
                     K([[B("← Indietro", callback_data=f"ks:s:{sez}")]]))
    elif az == "sv":
        bz = SI.bozza(uid)
        if not bz:
            await q.answer()
            await mostra(*editor_home(uid))
            return
        if bz.get("modifica_id"):
            if SI.aggiorna(bz["modifica_id"], uid, KR.completa(bz["parametri"])):
                SI.butta_bozza(uid)
                await q.answer("Salvato")
                await mostra(*scheda(SI.per_id(bz["modifica_id"]), uid))
            else:
                await q.answer("Lo modifica solo chi l'ha creato.", show_alert=True)
            return
        context.user_data["klra_attesa"] = ("nome",)
        await q.answer()
        await mostra("💾 <b>Come lo chiami?</b> Scrivi il nome (da 2 a 30 caratteri).\n"
                     "<i>Potrai modificarlo solo tu; gli altri potranno usarlo o copiarlo.</i>",
                     K([[B("← Indietro", callback_data="ks:e")]]))
    elif az == "x":
        SI.butta_bozza(uid)
        context.user_data.pop("klra_attesa", None)
        await q.answer("Bozza buttata")
        await mostra(*lista(uid))
    elif az in ("cl", "cf", "r"):
        s = SI.per_id(p[2])
        await q.answer()
        if not s:
            return
        try:
            if az == "cl":
                await manda_classifica(q.message, s)
            elif az == "cf":
                if s["ufficiale"]:
                    await q.message.reply_text("È l'Ufficiale: non c'è niente da confrontare.")
                else:
                    await manda_confronta(q.message, s)
            else:
                n, err = _giornata([])
                if err:
                    await q.message.reply_text(err)
                else:
                    await manda_risultati(q.message, s, n)
        except Exception as er:
            await _errore(q.message, er, {"cl": "Classifica", "cf": "Confronto", "r": "Risultati"}[az])
    elif az == "pt":
        s = SI.per_id(p[2])
        await q.answer()
        if s:
            try:
                await _manda_partita(q.message, s, int(p[3]), p[4], p[5])
            except Exception as er:
                await _errore(q.message, er, "Partita")
    else:
        await q.answer()


async def testo_libero(update, context):
    """Il valore o il nome che l'editor ha chiesto (solo in privato)."""
    att = context.user_data.get("klra_attesa")
    if not att:
        return
    uid = update.effective_user.id
    msg = update.effective_message
    bz = SI.bozza(uid)
    if not bz:
        context.user_data.pop("klra_attesa", None)
        return
    if att[0] == "valore":
        _, sez, voce = att
        v, err = ED.leggi_valore(sez, voce, msg.text)
        if err:
            await msg.reply_text(f"❌ {err} Riprova, o torna indietro coi bottoni.")
            return
        P = KR.completa(bz["parametri"])
        P[sez][voce] = v
        SI.salva_bozza(uid, P)
        context.user_data.pop("klra_attesa", None)
        t, kb = editor_sezione(uid, sez)
        await msg.reply_text(f"✅ {e(ED.VOCI[sez][voce][0])}: {e(ED.mostra(v))}\n\n" + t, parse_mode="HTML", reply_markup=kb)
    elif att[0] == "nome":
        nome = (msg.text or "").strip()
        err = SI.nome_valido(nome)
        if err:
            await msg.reply_text(f"❌ {err} Scrivi un altro nome.")
            return
        u = update.effective_user
        s = SI.crea(nome, uid, u.full_name or str(uid), KR.completa(bz["parametri"]), bz["base_id"])
        SI.scegli(uid, s["id"])
        SI.butta_bozza(uid)
        context.user_data.pop("klra_attesa", None)
        t, kb = scheda(s, uid)
        await msg.reply_text(f"✅ Creato <b>{e(nome)}</b>, ed è il tuo sistema attivo.\n\n" + t, parse_mode="HTML", reply_markup=kb)


def handlers() -> list:
    return [CommandHandler(["start", "aiuto"], cmd_start), CommandHandler("sistemi", cmd_sistemi), CommandHandler("usa", cmd_usa),
            CommandHandler("classifica", cmd_classifica), CommandHandler("confronta", cmd_confronta),
            CommandHandler("risultati", cmd_risultati), CommandHandler("giornata", cmd_giornata),
            CommandHandler("partita", cmd_partita), CommandHandler("top", cmd_top), CommandHandler("klra_verifica", cmd_verifica),
            CallbackQueryHandler(cb, pattern=r"^ks:"),
            MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, testo_libero)]

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
import json
import logging
import re

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

import config
import db
from klra import conference as CO
from klra import editor as ED
from klra import motore as M
from klra import regole as KR
from klra import sistemi as SI
from klra import viste as V

logger = logging.getLogger(__name__)
TEMPI = {"read_timeout": 60, "write_timeout": 60, "connect_timeout": 30}


def e(x) -> str:
    return html.escape(str(x), quote=False)


def con_conference(f):
    """Il comando gira con le conference attive di chi lo usa (calendario permutato): tutto il resto di klra lo segue."""
    import functools

    @functools.wraps(f)
    async def g(update, context):
        u = getattr(update, "effective_user", None) or update.callback_query.from_user
        uid = u.id
        with M.in_conference(CO.attiva(uid)):
            return await f(update, context)
    return g


PUBBLICI = [("sistemi", "I sistemi di punteggio: scegli, copia, modifica"),
            ("classifica", "La classifica col tuo sistema [NOME]"),
            ("giornata", "Una giornata col tuo sistema [N] [NOME]"),
            ("partita", "Una sfida col tuo sistema [SQUADRA] [N] [NOME]"),
            ("risultati", "I risultati in testo [N] [NOME]"),
            ("confronta", "Ufficiale contro un sistema [NOME]"),
            ("top", "Migliori per fantamedia col tuo sistema [N] o [DA A] [firmati] [NOME]"),
            ("calendario", "La giornata tua o di una squadra col sistema [N] [SQUADRA] [NOME]"),
            ("calendario_full", "Il calendario di una squadra coi risultati del sistema [SQUADRA] [NOME]"),
            ("classifica_full", "La classifica completa col sistema [NOME]"),
            ("classifica_conference", "La classifica per conference col sistema [NOME]"),
            ("pdf_giornata", "La giornata col sistema in PDF [N] [NOME]"),
            ("pdf_partite", "Le partite di una squadra col sistema in PDF [SQUADRA] [NOME]"),
            ("usa", "Scegli il tuo sistema: /usa NOME"),
            ("conference", "Conference alternative: scegli, crea, confronta"),
            ("player", "Un giocatore, con la fantamedia del tuo sistema [NOME SISTEMA]"),
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
    elif s.get("predefinito") in KR.PREDEFINITI:
        righe.append(f"Predefinito: {e(KR.PREDEFINITI[s['predefinito']]['descrizione'])}. Nessuno lo modifica; si può copiare.")
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
        "usano il tuo (o quello che scrivi dopo il comando). Con /conference puoi anche rimescolare le conference: "
        "ognuno sceglie le sue, e valgono insieme al sistema. Si calcolano le giornate convalidate dalla lega.",
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
        await msg.reply_photo(png, caption=f"🧪 NON UFFICIALE · 🏆 Classifica col sistema {M.nome_contesto(s)}", **TEMPI)
    finally:
        await _cancella(w)


async def manda_confronta(msg, s):
    w = await _attesa(msg)
    try:
        png = await asyncio.to_thread(V.img_confronta, s, config.stagione())
        if not png:
            await msg.reply_text("Nessuna giornata convalidata dalla lega, per ora.")
            return
        await msg.reply_photo(png, caption=f"🧪 NON UFFICIALE · ⚖️ Ufficiale contro {M.nome_contesto(s)}", **TEMPI)
    finally:
        await _cancella(w)


async def manda_risultati(msg, s, n):
    t = await asyncio.to_thread(V.testo_risultati, s, config.stagione(), n)
    await msg.reply_text(t, parse_mode="HTML")


async def _errore(msg, err, cosa):
    logger.exception(cosa)
    await msg.reply_text(f"❌ {cosa} non riuscito: {e(str(err))[:200]}")


@con_conference
async def cmd_classifica(update, context):
    s, _ = _sistema_e_resto(update, context)
    try:
        await manda_classifica(update.effective_message, s)
    except Exception as err:
        await _errore(update.effective_message, err, "Classifica")


@con_conference
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


@con_conference
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


@con_conference
async def cmd_giornata(update, context):
    s, resto = _sistema_e_resto(update, context)
    n, err = _giornata(resto)
    if err:
        await update.effective_message.reply_text(err)
        return
    w = await _attesa(update.effective_message)
    try:
        png = await asyncio.to_thread(V.img_giornata, s, config.stagione(), n)
        await update.effective_message.reply_photo(png, caption=f"🧪 NON UFFICIALE · 📅 Giornata {n} col sistema {M.nome_contesto(s)}", **TEMPI)
    except Exception as er:
        await _errore(update.effective_message, er, "Giornata")
    finally:
        await _cancella(w)


async def _manda_partita(msg, s, n, casa, tr):
    w = await _attesa(msg)
    try:
        png, d = await asyncio.to_thread(V.img_partita, s, config.stagione(), n, casa, tr)
        sq = d["squadre"]
        await msg.reply_photo(png, caption=f"🧪 NON UFFICIALE · 🏀 Giornata {n} · {sq[0]['nome']} {sq[0]['punti']} – {sq[1]['punti']} {sq[1]['nome']} col sistema {M.nome_contesto(s)}",
                              **TEMPI)
    finally:
        await _cancella(w)


@con_conference
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


# ── comandi di loucabot, col sistema (v7.1.0, Luca: «uguale a loucabot») ──

class _NonUfficiale:
    """Il messaggio passato ai comandi di loucabot: ogni risposta comincia con NON UFFICIALE e il sistema."""
    def __init__(self, msg, s: dict):
        self._m, self._s = msg, s
        self._bc = SI.parametri(s)["partita"]["bonus_casa"]

    def _testo(self, t: str, html_: bool) -> str:
        t = (t or "").replace("in casa (+3)", f"in casa (+{self._bc:g})")
        nome = M.nome_contesto(self._s)
        return (f"🧪 <b>NON UFFICIALE</b> · sistema <b>{e(nome)}</b>\n" if html_ else
                f"🧪 NON UFFICIALE · sistema {nome}\n") + t

    async def reply_text(self, t, **k):
        return await self._m.reply_text(self._testo(t, k.get("parse_mode") == "HTML"), **k)

    async def reply_photo(self, photo=None, caption=None, **k):
        c = self._testo(caption or "", k.get("parse_mode") == "HTML")
        if len(c) > 1024:                                  # col prefisso non sta più in una didascalia: foto, poi il testo
            await self._m.reply_photo(photo, caption=self._testo("", False).strip(), **TEMPI)
            return await self._m.reply_text(c, parse_mode=k.get("parse_mode"))
        return await self._m.reply_photo(photo, caption=c, **{**TEMPI, **k})

    async def reply_document(self, document=None, caption=None, **k):
        return await self._m.reply_document(document=document, caption=self._testo(caption or "", k.get("parse_mode") == "HTML"),
                                            **{**TEMPI, **k})

    def __getattr__(self, nome):
        return getattr(self._m, nome)


async def _di_loucabot(update, context, funzione):
    """Un comando di loucabot (stessi argomenti, stesso testo e immagini) dentro il contesto del sistema."""
    s, resto = _sistema_e_resto(update, context)
    await _di_loucabot_su(update.effective_message, update.effective_user, context, s, funzione, resto)


async def _di_loucabot_su(messaggio, utente, context, s, funzione, args):
    import types
    msg = _NonUfficiale(messaggio, s)
    u = types.SimpleNamespace(effective_message=msg, message=msg, effective_user=utente,
                              effective_chat=getattr(messaggio, "chat", None), callback_query=None)
    c = types.SimpleNamespace(args=args, bot=context.bot, user_data=getattr(context, "user_data", {}), bot_data={})
    w = await _attesa(messaggio)
    try:
        M.installa()
        righe = await asyncio.to_thread(M.righe_lega, s, config.stagione())
        with M.contesto(s, righe=righe):          # le ContextVar valgono per questo task e per i to_thread che apre
            await funzione(u, c)
    except Exception as er:
        await _errore(messaggio, er, "Comando")
    finally:
        await _cancella(w)


@con_conference
async def cmd_calendario(update, context):
    import handlers as LH
    await _di_loucabot(update, context, LH.cmd_calendario)


@con_conference
async def cmd_calendario_full(update, context):
    import handlers as LH
    await _di_loucabot(update, context, LH.cmd_calendario_full)


async def cmd_player(update, context):
    import player
    await _di_loucabot(update, context, player.cmd_player)


async def cb_player(update, context):
    """I bottoni «Quale?» di /player (pl:<id>), col sistema attivo."""
    import player
    q = update.callback_query
    await q.answer()
    gid = int(q.data.split(":")[1])
    s = SI.attivo(q.from_user.id)
    righe = await asyncio.to_thread(M.righe_lega, s, config.stagione())
    with M.contesto(s, righe=righe):
        if player._foto(gid):
            await q.edit_message_text("🏀 ⬇️")
            await player.manda(_NonUfficiale(q.message, s), gid)
        else:
            t = await asyncio.to_thread(player.scheda, gid)
            await q.edit_message_text(_NonUfficiale(q.message, s)._testo(t, True), parse_mode="HTML")


@con_conference
async def cmd_classifica_full(update, context):
    import classifica as CL
    await _di_loucabot(update, context, CL.cmd_classifica_full)


@con_conference
async def cmd_classifica_conference(update, context):
    import classifica as CL
    await _di_loucabot(update, context, CL.cmd_classifica_conference)


async def _manda_pdf(msg, pdfs, nome, didascalia):
    import io
    for i, b in enumerate(pdfs, 1):
        parte = f" ({i}/{len(pdfs)})" if len(pdfs) > 1 else ""
        await msg.reply_document(document=io.BytesIO(b), filename=f"klra_{nome}{'_' + str(i) if len(pdfs) > 1 else ''}.pdf",
                                 caption=f"🧪 NON UFFICIALE · {didascalia}{parte}", **TEMPI)


_PDF = {"in_corso": False}


@con_conference
async def cmd_pdf_giornata(update, context):
    msg = update.effective_message
    s, resto = _sistema_e_resto(update, context)
    n, err = _giornata(resto)
    if err:
        await msg.reply_text(err)
        return
    if _PDF["in_corso"]:
        await msg.reply_text("⏳ Sto già preparando un PDF: riprova tra un minuto.")
        return
    _PDF["in_corso"] = True
    try:
        await msg.reply_text(f"⏳ Preparo il PDF della giornata {n} col sistema {s['nome']}: ci vuole un po'…")
        pdfs = await asyncio.to_thread(V.pdf_giornata, s, config.stagione(), n)
        await _manda_pdf(msg, pdfs, f"giornata_{n}", f"📄 Giornata {n} col sistema {s['nome']}: risultati e partite")
    except Exception as er:
        await _errore(msg, er, "PDF")
    finally:
        _PDF["in_corso"] = False


@con_conference
async def cmd_pdf_partite(update, context):
    from shared.squadre import cerca_squadra
    msg = update.effective_message
    s, resto = _sistema_e_resto(update, context)
    testo = " ".join(resto).strip()
    sq = cerca_squadra(testo, config.squadre()) if testo else config.squadra_del_gm(update.effective_user.id)
    if not sq:
        await msg.reply_text(f"Squadra non trovata: «{e(testo)}»." if testo else "Uso: /pdf_partite [SQUADRA] [SISTEMA]")
        return
    if _PDF["in_corso"]:
        await msg.reply_text("⏳ Sto già preparando un PDF: riprova tra un minuto.")
        return
    _PDF["in_corso"] = True
    try:
        await msg.reply_text(f"⏳ Preparo il PDF delle partite di {sq['nome']} col sistema {s['nome']}: ci vuole un po'…")
        pdfs, n = await asyncio.to_thread(V.pdf_partite, s, config.stagione(), sq["id"])
        if not pdfs:
            await msg.reply_text(f"{sq['nome']} non ha partite in giornate convalidate, per ora.")
            return
        await _manda_pdf(msg, pdfs, f"partite_{sq['id']}", f"📄 {sq['nome']}: {n} partite col sistema {s['nome']}")
    except Exception as er:
        await _errore(msg, er, "PDF")
    finally:
        _PDF["in_corso"] = False


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
    t = ("✅ <b>Motore</b>: l'Ufficiale di klra dà esattamente il ricalcolo di oggi di loucabot." if not d["motore"] else
         "❌ <b>Motore</b>: klra e loucabot non danno gli stessi numeri (va guardato):\n" + "\n".join(e(x) for x in d["motore"][:30]))
    if d["dati"]:
        t += ("\n\nℹ️ <b>Dati cambiati dopo la convalida</b> (correzioni di ESPN o decisioni prese dopo; i risultati "
              "ufficiali restano quelli convalidati). Ricalcolando oggi:\n" + "\n".join(d["dati"][:30]))
    else:
        t += "\n\n✅ E il ricalcolo di oggi coincide coi risultati convalidati."
    await msg.edit_text(t, parse_mode="HTML")


# ── conference alternative (v2, mockup approvato da Luca il 06/11) ───────────────

def lista_conference(uid: int) -> tuple[str, K]:
    att = CO.attiva(uid)
    u = CO.ufficiali()
    righe = ["🗺 <b>Conference</b> · " + e(V._anno(config.stagione())),
             "<b>⚠️ NON UFFICIALE</b>: le conference alternative cambiano solo i conti di klra.", "",
             f"Le tue attive: <b>{e(att['nome']) if att else 'Ufficiali'}</b>", "",
             f"{'⭐' if not att else '🏛'} <b>Ufficiali</b> · quelle della lega"]
    for c in CO.tutte():
        a = c["squadre_a"] if isinstance(c["squadre_a"], list) else json.loads(c["squadre_a"])
        righe.append(f"{'⭐' if att and att['id'] == c['id'] else '▫️'} <b>{e(c['nome'])}</b> · {e(c.get('autore_nome') or '?')} · "
                     f"<i>{e(', '.join(config.nome(t) for t in a[:3]))}…</i>")
    bot = [B(("⭐ " if not att else "") + "Ufficiali", callback_data="kc:v:0")] + \
          [B(("⭐ " if att and att["id"] == c["id"] else "") + c["nome"], callback_data=f"kc:v:{c['id']}") for c in CO.tutte()]
    kb = [bot[i:i + 2] for i in range(0, len(bot), 2)] + [[B("➕ Nuove conference", callback_data="kc:n")]]
    if not u:
        righe.append("\n<i>Le conference della lega non sono configurate (config/divisions.json).</i>")
    return "\n".join(righe), K(kb)


def scheda_conference(cid: int, uid: int) -> tuple[str, K]:
    att = CO.attiva(uid)
    if not cid:
        gruppi = CO.ufficiali()
        titolo, attive = "🏛 <b>Ufficiali</b> · quelle della lega", not att
        kb = [] if attive else [[B("✅ Usa queste", callback_data="kc:u:0")]]
    else:
        c = CO.per_id(cid)
        mappa = c["mappa"] if isinstance(c["mappa"], dict) else json.loads(c["mappa"])
        na, nb = CO.nomi()
        a = set(c["squadre_a"] if isinstance(c["squadre_a"], list) else json.loads(c["squadre_a"]))
        gruppi = {na: sorted(a), nb: sorted(t for t in mappa if t not in a)}
        titolo = f"🗺 <b>{e(c['nome'])}</b> · di {e(c.get('autore_nome') or '?')}" + \
                 (f" · modificate il {_quando(c['modificato'])}" if c.get("modificato") else "")
        attive = att and att["id"] == c["id"]
        kb = [] if attive else [[B("✅ Usa queste", callback_data=f"kc:u:{cid}")]]
        if CO.puo_modificare(c, uid):
            kb.append([B("✏️ Modifica", callback_data=f"kc:m:{cid}")])
    righe = [titolo, ""]
    for nome, sq in gruppi.items():
        righe.append(f"<b>{e(nome)}</b>: " + ", ".join(e(config.nome(t)) for t in sq))
    if cid:
        mappa = c["mappa"] if isinstance(c["mappa"], dict) else json.loads(c["mappa"])
        righe += ["", "<i>Nel calendario: " + ", ".join(f"{e(config.nome(t))} al posto di {e(config.nome(p))}"
                                                      for t, p in sorted(mappa.items()) if t != p)[:900] + "</i>"]
    if attive:
        righe += ["", "Sono le tue attive."]
    kb.append([B("🏆 Classifica per conference", callback_data=f"kc:cl:{cid}"), B("⚖️ Confronta", callback_data=f"kc:cf:{cid}")])
    kb.append([B("← Conference", callback_data="kc:l")])
    return "\n".join(righe), K(kb)


def scelta_squadre(scelte: set, modifica: int | None) -> tuple[str, K]:
    u = CO.ufficiali()
    na = CO.nomi()[0]
    n = len(u[na])
    tutte = sorted((t for x in u.values() for t in x), key=config.nome)
    bot = [B(("✅ " if t in scelte else "") + config.nome(t), callback_data=f"kc:t:{t}") for t in tutte]
    kb = [bot[i:i + 3] for i in range(0, len(bot), 3)]
    kb.append([B("🔀 Squadre a caso", callback_data="kc:caso")])
    kb.append([B(f"🎲 Accoppia e salva ({len(scelte)}/{n})", callback_data="kc:ok"), B("❌ Annulla", callback_data="kc:l")])
    t = (f"{'✏️ Modifica' if modifica else '➕ Nuove conference'} · scegli le {n} squadre della <b>{e(na)}</b> "
         f"({len(scelte)}/{n}).\nLe altre vanno nella {e(CO.nomi()[1])}. Con «Accoppia e salva» ogni squadra prende a caso il "
         f"posto di una della sua conference nel calendario vero.")
    return t, K(kb)


async def cmd_conference(update, context):
    if not CO.configurate():
        await update.effective_message.reply_text("Le conference della lega non sono configurate (config/divisions.json): "
                                                  "chiedi al dev.")
        return
    t, kb = await asyncio.to_thread(lista_conference, update.effective_user.id)
    await update.effective_message.reply_text(t, parse_mode="HTML", reply_markup=kb)


async def cb_conference(update, context):
    q = update.callback_query
    uid = q.from_user.id
    p = q.data.split(":")
    az = p[1]

    async def mostra(t, kb):
        await q.edit_message_text(t, parse_mode="HTML", reply_markup=kb)

    if az in ("n", "m", "t", "ok", "caso") and not (q.message and q.message.chat.type == "private"):
        await q.answer("Le conference si creano in privato: scrivimi /conference in chat.", show_alert=True)
        return
    if az == "l":
        context.user_data.pop("klra_conf", None)
        await q.answer()
        await mostra(*lista_conference(uid))
    elif az == "v":
        await q.answer()
        await mostra(*scheda_conference(int(p[2]), uid))
    elif az == "u":
        cid = int(p[2]) or None
        CO.scegli(uid, cid)
        await q.answer("Ora usi " + (CO.per_id(cid)["nome"] if cid else "le conference ufficiali"))
        await mostra(*scheda_conference(int(p[2]), uid))
    elif az in ("n", "m"):
        if az == "m":
            c = CO.per_id(p[2])
            if not CO.puo_modificare(c, uid):
                await q.answer("Le modifica solo chi le ha create: fanne di nuove.", show_alert=True)
                return
            a = c["squadre_a"] if isinstance(c["squadre_a"], list) else json.loads(c["squadre_a"])
            context.user_data["klra_conf"] = {"a": set(a), "modifica": c["id"]}
        else:
            context.user_data["klra_conf"] = {"a": set(), "modifica": None}
        await q.answer()
        st = context.user_data["klra_conf"]
        await mostra(*scelta_squadre(st["a"], st["modifica"]))
    elif az == "t":
        st = context.user_data.setdefault("klra_conf", {"a": set(), "modifica": None})
        n = len(CO.ufficiali()[CO.nomi()[0]])
        t = p[2]
        if t in st["a"]:
            st["a"].discard(t)
        elif len(st["a"]) >= n:
            await q.answer(f"Sono già {n}: togline una prima.", show_alert=True)
            return
        else:
            st["a"].add(t)
        await q.answer()
        await mostra(*scelta_squadre(st["a"], st["modifica"]))
    elif az == "caso":                                     # estrazione casuale delle squadre (Luca, 06/11)
        import random
        st = context.user_data.setdefault("klra_conf", {"a": set(), "modifica": None})
        u = CO.ufficiali()
        n = len(u[CO.nomi()[0]])
        st["a"] = set(random.SystemRandom().sample(sorted(t for x in u.values() for t in x), n))
        await q.answer("Estratte: puoi cambiarle o salvare")
        await mostra(*scelta_squadre(st["a"], st["modifica"]))
    elif az == "ok":
        st = context.user_data.get("klra_conf")
        n = len(CO.ufficiali()[CO.nomi()[0]])
        if not st or len(st["a"]) != n:
            await q.answer(f"Servono esattamente {n} squadre.", show_alert=True)
            return
        if st["modifica"]:
            if CO.aggiorna(st["modifica"], uid, sorted(st["a"])):
                context.user_data.pop("klra_conf", None)
                await q.answer("Salvate, con un nuovo accoppiamento")
                await mostra(*scheda_conference(st["modifica"], uid))
            else:
                await q.answer("Le modifica solo chi le ha create.", show_alert=True)
            return
        context.user_data["klra_attesa"] = ("conf_nome",)
        await q.answer()
        await mostra("💾 <b>Come le chiami?</b> Scrivi il nome (da 2 a 30 caratteri).", K([[B("❌ Annulla", callback_data="kc:l")]]))
    elif az in ("cl", "cf"):
        await q.answer()
        cid = int(p[2]) or None
        conf = CO.per_id(cid) if cid else None
        s = SI.attivo(uid)
        with M.in_conference(conf):
            try:
                if az == "cl":
                    await _di_loucabot_su(q.message, q.from_user, context, s, __import__("classifica").cmd_classifica_conference, [])
                elif s["ufficiale"] and not conf:
                    await q.message.reply_text("Ufficiale con le conference ufficiali: non c'è niente da confrontare.")
                else:
                    await manda_confronta(q.message, s)
            except Exception as er:
                await _errore(q.message, er, "Conference")
    else:
        await q.answer()


# ── bottoni ──────────────────────────────────────────────────────────────────────

@con_conference
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
    if att[0] == "conf_nome":
        st = context.user_data.get("klra_conf")
        nome = (msg.text or "").strip()
        err = CO.nome_valido(nome)
        if err:
            await msg.reply_text(f"❌ {err} Scrivi un altro nome.")
            return
        if not st:
            context.user_data.pop("klra_attesa", None)
            return
        c = CO.crea(nome, uid, update.effective_user.full_name or str(uid), sorted(st["a"]))
        CO.scegli(uid, c["id"])
        context.user_data.pop("klra_conf", None)
        context.user_data.pop("klra_attesa", None)
        t, kb = scheda_conference(c["id"], uid)
        await msg.reply_text(f"✅ Create <b>{e(nome)}</b> (accoppiamento estratto), e sono le tue attive.\n\n" + t,
                             parse_mode="HTML", reply_markup=kb)
        return
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
            CommandHandler("calendario", cmd_calendario), CommandHandler("calendario_full", cmd_calendario_full),
            CommandHandler("classifica_full", cmd_classifica_full), CommandHandler("classifica_conference", cmd_classifica_conference),
            CommandHandler("pdf_giornata", cmd_pdf_giornata), CommandHandler("pdf_partite", cmd_pdf_partite),
            CommandHandler("conference", cmd_conference), CommandHandler("player", cmd_player),
            CallbackQueryHandler(cb_player, pattern=r"^pl:\d+$"),
            CallbackQueryHandler(cb, pattern=r"^ks:"), CallbackQueryHandler(cb_conference, pattern=r"^kc:"),
            MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, testo_libero)]

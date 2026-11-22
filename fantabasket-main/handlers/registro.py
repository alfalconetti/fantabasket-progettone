"""
Registro delle azioni nel bot principale (v6.0.0): `segna` per i flussi del bot e `/registro` per
consultarlo (anche dal pannello admin, «📜 Registro»). Il registro è unico per tutti i bot
(`shared/azioni.py`, tabella registro_azioni): da qui si vedono anche bot aste, loucabot e IPanchinari.

/registro [filtri] (admin: tutto; GM: solo le righe della sua squadra). v7.13.0: filtri come /giocatori
(chiavi, «o» con la virgola, «-» per negare, «|» tra gruppi, date): vedi AIUTO e leggi(). Il risultato è un file
Markdown, coi filtri capiti in cima.
"""
import io
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db
import settings
import teams as tm
from settings import solo_privato
from shared import azioni as A

logger = logging.getLogger(__name__)
ROMA = ZoneInfo("Europe/Rome")
BOT_ALIAS = {"principale": "main", "main": "main", "aste": "aste", "loucabot": "louca", "louca": "louca",
             "ipanchinari": "ipa", "ipa": "ipa", "panchinari": "ipa"}


def _nome(team_id: str) -> str:
    t = tm.get_team_by_id(team_id)
    return t["nome"] if t else team_id


async def segna(bot, user, veste: str, azione: str, **campi) -> dict | None:
    """Registra l'azione (e, se admin o dev, la riga sul canale log del bot principale). Non solleva."""
    try:
        chat = settings.load_globals().get("log_channel_id_main")
    except Exception:
        chat = None
    return await A.azione(db._q, bot, chat, "main", user, veste, azione, nomi_squadre=_nome, **campi)


async def solo_log(bot, user, veste: str, azione: str, **campi) -> None:
    """Solo la riga sul canale log (admin e dev): il riassunto di un'azione in blocco, le cui righe sono
    già nel registro una per una (segna_sync)."""
    try:
        chat = settings.load_globals().get("log_channel_id_main")
    except Exception:
        chat = None
    await A.azione(db._q, bot, chat, "main", user, veste, azione, nomi_squadre=_nome, nel_registro=False, **campi)


def segna_sync(user, veste: str, azione: str, **campi) -> dict | None:
    """Solo il registro (per funzioni non async o job senza bot): niente canale log."""
    return A.registra(db._q, "main", user, veste, azione, **campi)


# ── /registro ──────────────────────────────────────────────────────────────────
# v7.13.0 (Luca, 15/11): filtri come /giocatori. Chiavi: squadra: giocatore: chi: bot: veste: azione: testo:
# giorni: dal: al:. Senza chiave, quando non c'è dubbio: un numero sono i giorni, admin/gm/dev/sistema la veste,
# principale/aste/loucabot/ipanchinari il bot, @utente chi; le altre parole insieme sono una squadra, un giocatore
# (se è uno solo) o un pezzo di azione; se sono sia una squadra sia un giocatore il bot chiede la chiave. Più
# valori con la virgola in «o»; filtri diversi in «e»; «|» o «oppure» tra gruppi alternativi; «-» davanti nega.
# giorni, dal e al valgono per tutti i gruppi. I GM vedono sempre e solo la loro squadra.

AIUTO = ("📜 <b>/registro</b> [filtri] — le azioni di tutti i bot, in un file. Filtri in qualsiasi ordine:\n"
         "• <code>7</code> o <code>giorni:7</code> · <code>dal:01/11</code> · <code>al:15/11/2026</code>\n"
         "• <code>squadra:§A§,§B§</code> · <code>giocatore:\"Jalen Brunson\"</code> · <code>chi:@luca</code> (o solo <code>@luca</code>)\n"
         "• <code>admin</code> <code>gm</code> <code>dev</code> <code>sistema</code> (o <code>veste:</code>) · "
         "<code>principale</code> <code>aste</code> <code>loucabot</code> <code>ipanchinari</code> (o <code>bot:</code>)\n"
         "• <code>azione:taglio</code> · <code>testo:G12</code> (cerca in oggetto, prima → dopo e nota)\n"
         "• senza chiave: una squadra, un giocatore o un pezzo di azione (se è ambiguo il bot chiede la chiave)\n"
         "• più valori con la virgola valgono in «o»; <code>-</code> davanti nega (<code>-sistema</code>, <code>-bot:aste</code>); "
         "<code>|</code> (o <code>oppure</code>) separa gruppi alternativi: <code>squadra:§A§ taglio | squadra:§B§ trade</code>\n"
         "Con spazi nel valore, tra virgolette. I GM vedono solo la loro squadra.")


def aiuto() -> str:
    """AIUTO con due squadre vere a caso negli esempi (v7.20.4)."""
    from shared import esempi as ES
    a, b = ES.due()
    return AIUTO.replace("§A§", ES.filtro(a)).replace("§B§", ES.filtro(b))


class Errore(ValueError):
    """Un filtro scritto male: il messaggio va a chi ha scritto il comando."""


class Scegli(Errore):
    """v7.25.0 (Luca, 22/11): un nome ambiguo nei filtri si sceglie coi bottoni. `chiave` è il pezzo da scegliere
    («g:<nome>» un giocatore, «sg:<testo>» squadra o giocatore), `voci` [(etichetta, valore)], `domanda` il testo."""
    def __init__(self, chiave: str, domanda: str, voci: list):
        super().__init__(domanda)
        self.chiave, self.domanda, self.voci = chiave, domanda, voci


def _data(chiave: str, v: str):
    from datetime import date
    pz = v.replace("-", "/").replace(".", "/").split("/")
    try:
        g, m = int(pz[0]), int(pz[1])
        a = int(pz[2]) if len(pz) > 2 else datetime.now(ROMA).year
        a = a + 2000 if a < 100 else a
        return date(a, m, g)
    except (ValueError, IndexError):
        raise Errore(f"«{chiave}:{v}»: la data va scritta GG/MM o GG/MM/AAAA.")


def _squadra(v: str) -> str:
    t = tm.get_team_by_query(v)
    if not t:
        raise Errore(f"Nessuna squadra trovata con «{v}».")
    return t["id"]


def _giocatore(v: str, scelte: dict | None = None) -> tuple[int, str]:
    from utils import normalizza
    k = "g:" + normalizza(v)
    if scelte and k in scelte:                         # già scelto coi bottoni
        return tuple(scelte[k])
    gioc = db.cerca_giocatori(normalizza(v)) or []
    esatti = [x for x in gioc if normalizza(x["nome_common"]) == normalizza(v)]
    if len(esatti) == 1:
        gioc = esatti
    if not gioc:
        raise Errore(f"Nessun giocatore trovato con «{v}».")
    if len(gioc) > 1:                                  # v7.25.0: si sceglie coi bottoni
        raise Scegli(k, f"«{v}»: quale giocatore?", [(x["nome_common"], (x["id"], x["nome_common"])) for x in gioc])
    return gioc[0]["id"], gioc[0]["nome_common"]


def _valori(chiave: str, v: str, scelte: dict | None = None) -> tuple[str, list, str]:
    """(campo, valori, descrizione) di un filtro con la chiave."""
    vv = [x.strip() for x in v.split(",") if x.strip()]
    if not vv:
        raise Errore(f"«{chiave}:»: manca il valore dopo i due punti.")
    if chiave in ("squadra", "team"):
        ids = [_squadra(x) for x in vv]
        return "squadra", ids, "squadra " + " o ".join(_nome(i) for i in ids)
    if chiave == "giocatore":
        gg = [_giocatore(x, scelte) for x in vv]
        return "giocatore", [g[0] for g in gg], "giocatore " + " o ".join(g[1] for g in gg)
    if chiave == "chi":
        return "chi", [x.lstrip("@") for x in vv], "chi " + " o ".join(vv)
    if chiave == "bot":
        bad = [x for x in vv if x.lower() not in BOT_ALIAS]
        if bad:
            raise Errore(f"«bot:{bad[0]}»: i bot sono principale, aste, loucabot, ipanchinari.")
        ids = list(dict.fromkeys(BOT_ALIAS[x.lower()] for x in vv))
        return "bot", ids, " o ".join(A.NOMI_BOT[i] for i in ids)
    if chiave == "veste":
        bad = [x for x in vv if x.lower() not in A.VESTI]
        if bad:
            raise Errore(f"«veste:{bad[0]}»: le vesti sono admin, gm, dev, sistema.")
        return "veste", [x.lower() for x in vv], "veste " + " o ".join(x.lower() for x in vv)
    if chiave == "azione":
        return "azione", vv, "azione «" + "» o «".join(vv) + "»"
    if chiave == "testo":
        return "testo", vv, "testo «" + "» o «".join(vv) + "»"
    raise Errore(f"«{chiave}:»: chiave sconosciuta. /registro aiuto per l'elenco.")


def _senza_chiave(testo: str, scelte: dict | None = None) -> tuple[str, list, str]:
    """Parole senza chiave: squadra, giocatore unico o azione; se sono sia squadra sia giocatore, si chiede (v7.25.0:
    coi bottoni «squadra / giocatore»; il giocatore, se sono più d'uno, poi coi bottoni)."""
    from utils import normalizza
    t = tm.get_team_by_query(testo)
    gioc = db.cerca_giocatori(normalizza(testo)) or []
    k = "sg:" + normalizza(testo)
    if t and gioc and scelte and k in scelte:
        if scelte[k] == "squadra":
            return "squadra", [t["id"]], f"squadra {t['nome']}"
        g = _giocatore(testo, scelte)
        return "giocatore", [g[0]], f"giocatore {g[1]}"
    if t and gioc:
        raise Scegli(k, f"«{testo}» è sia una squadra sia un giocatore: quale?",
                     [(f"🏀 squadra {t['nome']}", "squadra"), ("👤 giocatore", "giocatore")])
    if t:
        return "squadra", [t["id"]], f"squadra {t['nome']}"
    if len(gioc) == 1:
        return "giocatore", [gioc[0]["id"]], f"giocatore {gioc[0]['nome_common']}"
    return "azione", [testo], f"azione «{testo}»"


def leggi(args: list[str], scelte: dict | None = None) -> dict:
    """I filtri: {"gruppi": [{"si", "no", "desc"}], "giorni", "dal", "al", "desc": [globali], "aiuto"}."""
    import shlex
    try:
        parti = shlex.split(" ".join(args))
    except ValueError:
        parti = list(args)
    out = {"gruppi": [], "giorni": None, "dal": None, "al": None, "desc": [], "aiuto": False}
    blocchi, cur = [], []
    for p in parti:
        if p in ("|", "||") or p.lower() == "oppure":
            blocchi.append(cur); cur = []
        else:
            cur.append(p)
    blocchi.append(cur)
    if len(blocchi) > 1 and not all(blocchi):
        from shared import esempi as ES
        a, b = ES.due()
        raise Errore(f"Un «|» (oppure) va tra due gruppi di filtri, es. /registro squadra:{ES.filtro(a)} | squadra:{ES.filtro(b)}.")
    for b in blocchi:
        g = {"si": [], "no": [], "desc": []}
        parole = {False: [], True: []}
        for p in b:
            neg = p.startswith("-") and len(p) > 1
            x = p[1:] if neg else p
            k, sep, v = x.partition(":")
            k = k.lower()
            if sep and k in ("giorni", "dal", "al"):
                if neg:
                    raise Errore(f"«{p}»: giorni e date non si negano.")
                if k == "giorni":
                    if not v.isdigit():
                        raise Errore(f"«{p}»: serve un numero di giorni.")
                    out["giorni"] = int(v)
                else:
                    out[k] = _data(k, v)
                continue
            if sep:
                campo, vals, d = _valori(k, v, scelte)
            elif x.lower() in ("aiuto", "help", "?"):
                out["aiuto"] = True
                continue
            elif x.isdigit() and int(x) <= 3650 and not neg:
                out["giorni"] = int(x)
                continue
            elif x.lower() in A.VESTI:
                campo, vals, d = "veste", [x.lower()], f"veste {x.lower()}"
            elif x.lower() in BOT_ALIAS:
                campo, vals, d = "bot", [BOT_ALIAS[x.lower()]], A.NOMI_BOT[BOT_ALIAS[x.lower()]]
            elif x.startswith("@") and len(x) > 1:
                campo, vals, d = "chi", [x[1:]], f"chi {x}"
            else:
                parole[neg].append(x)
                continue
            (g["no"] if neg else g["si"]).append((campo, vals))
            g["desc"].append(("non " if neg else "") + d)
        for neg, pp in parole.items():
            if pp:
                campo, vals, d = _senza_chiave(" ".join(pp), scelte)
                (g["no"] if neg else g["si"]).append((campo, vals))
                g["desc"].append(("non " if neg else "") + d)
        out["gruppi"].append(g)
    if out["giorni"]:
        out["desc"].append(f"ultimi {out['giorni']} giorni")
    if out["dal"]:
        out["desc"].append(f"dal {out['dal']:%d/%m/%Y}")
    if out["al"]:
        out["desc"].append(f"al {out['al']:%d/%m/%Y}")
    if out["dal"] and out["al"] and out["dal"] > out["al"]:
        raise Errore("La data «dal» viene dopo quella «al».")
    return out


def descrizione(f: dict) -> list[str]:
    """I filtri capiti, per la testata del file e la didascalia."""
    gg = [g for g in f["gruppi"] if g["desc"]]
    if len(gg) > 1:
        alt = " oppure ".join("(" + ", ".join(g["desc"]) + ")" for g in gg)
        return f["desc"] + [alt]
    return f["desc"] + (gg[0]["desc"] if gg else [])


def filtri(args: list[str]) -> tuple[dict, list[str]]:
    """Compatibilità (prima della v7.13.0): un gruppo solo → ({filtri per azioni.cerca}, [descrizione])."""
    f = leggi(args)
    piatto = {}
    if f["giorni"]:
        piatto["giorni"] = f["giorni"]
    g = f["gruppi"][0] if f["gruppi"] else {"si": []}
    nomi = {"squadra": "squadra", "giocatore": "giocatore_id", "chi": "chi_testo", "bot": "bot", "veste": "veste", "azione": "azione_"}
    for campo, vals in g["si"]:
        if campo in nomi:
            piatto[nomi[campo]] = ("@" + vals[0]) if campo == "chi" else vals[0]
    return piatto, descrizione(f)


def testo_md(righe: list[dict], desc: list[str], limite: int) -> str:
    e = lambda x: str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")
    out = [f"# Registro delle azioni", "",
           f"Filtri: {', '.join(desc) or 'nessuno'} · {len(righe)} righe"
           + (f" (le ultime {limite})" if len(righe) >= limite else "") + "  ",
           f"Estratto il {datetime.now(timezone.utc).astimezone(ROMA):%d/%m/%Y %H:%M} (ora italiana). "
           "Le azioni prima della v6.0.0 non sono nel registro.", "",
           "| Quando | Bot | Chi | Veste | Azione | Squadre | Oggetto | Prima → dopo | Nota |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in righe:
        pd = "" if r.get("prima") is None and r.get("dopo") is None else f"{e(r.get('prima') or '—')} → {e(r.get('dopo') or '—')}"
        out.append(f"| {r['quando'].astimezone(ROMA):%d/%m/%Y %H:%M} | {A.NOMI_BOT.get(r['bot'], r['bot'])} | "
                   f"{e(r.get('chi_nome') or '—')} | {r['veste']} | {e(r['azione'])} | "
                   f"{e(', '.join(_nome(s) for s in (r.get('squadre') or [])))} | {e(r.get('oggetto') or '')} | {pd} | "
                   f"{e(r.get('nota') or '')} |")
    return "\n".join(out) + "\n"


async def _manda(bot, chat_id: int, user, args: list[str], scelte: dict | None = None) -> "str | Scegli | None":
    """Manda il file; None se va bene, Scegli se un nome va scelto coi bottoni, altrimenti il motivo del rifiuto (o
    l'aiuto)."""
    admin = settings.is_admin(user.id)
    try:
        f = leggi(args, scelte)
    except Scegli as sc:
        return sc
    except Errore as err:
        return f"❌ {err}"
    if f["aiuto"]:
        return aiuto()
    fissa = None
    if not admin:
        t = tm.get_team_by_gm(user.id)
        if not t:
            return "⛔ Il registro lo vedono gli admin e i GM (solo per la loro squadra)."
        altre = {v for g in f["gruppi"] for c, vv in g["si"] if c == "squadra" for v in vv} - {t["id"]}
        if altre:
            return "⛔ Puoi vedere solo il registro della tua squadra."
        fissa = t["id"]
    desc = descrizione(f) + ([f"squadra {_nome(fissa)} (la tua)"] if fissa else [])
    limite = 500
    import asyncio
    righe = await asyncio.to_thread(A.cerca_filtri, db._q, f["gruppi"], giorni=f["giorni"], dal=f["dal"], al=f["al"],
                                    squadra_fissa=fissa, limite=limite)
    testo = testo_md(righe, desc, limite)
    adesso = datetime.now(timezone.utc).astimezone(ROMA)
    await bot.send_document(chat_id=chat_id, document=io.BytesIO(testo.encode("utf-8")),
                            filename=f"registro-{adesso:%Y%m%d-%H%M}.md",
                            caption=(f"📜 Registro delle azioni ({len(righe)} righe)" + (f" — {', '.join(desc)}" if desc else ""))[:1000])
    return None


async def _rispondi(context, motivo, st: dict, msg=None, q=None) -> None:
    """Dopo _manda: i bottoni se c'è da scegliere (stesso messaggio se viene da un bottone), se no il motivo."""
    from shared import pagine as PG
    if isinstance(motivo, Scegli):
        st.update(chiave=motivo.chiave, valori=[v for _, v in motivo.voci])
        voci = [(e, f"rg:{i}") for i, (e, _) in enumerate(motivo.voci)]
        if q:
            await PG.modifica(q, context, voci, motivo.domanda)
        else:
            await PG.manda(msg, context, voci, motivo.domanda)
        return
    if q:
        await q.edit_message_text(motivo or "📜 ⬇️")
    elif motivo:
        await msg.reply_text(motivo, parse_mode="HTML" if motivo.startswith("📜 <b>/registro</b>") else None)


@solo_privato
async def cmd_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    args = list(context.args or [])
    st = {"args": args, "scelte": {}}
    motivo = await _manda(context.bot, update.effective_chat.id, u, args, st["scelte"])
    if isinstance(motivo, Scegli) and getattr(context, "user_data", None) is not None:
        context.user_data["registro"] = st
    await _rispondi(context, motivo, st, msg=update.effective_message)


async def cb_scelta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """rg:<i>: un nome ambiguo dei filtri scelto coi bottoni (v7.25.0); poi si rilegge tutto con la scelta."""
    q = update.callback_query
    st = (getattr(context, "user_data", None) or {}).get("registro")
    i = int(q.data.split(":")[1])
    if not st or "chiave" not in st or i >= len(st.get("valori", [])):
        await q.answer("Ricerca scaduta: rifai /registro.", show_alert=True)
        return
    await q.answer()
    st["scelte"][st.pop("chiave")] = st.pop("valori")[i]
    motivo = await _manda(context.bot, q.message.chat_id, q.from_user, st["args"], st["scelte"])
    await _rispondi(context, motivo, st, q=q)


async def cb_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pannello admin → 📜 Registro: gli ultimi 7 giorni."""
    q = update.callback_query
    if not settings.is_admin(q.from_user.id):
        await q.answer("⛔ Solo admin.", show_alert=True)
        return
    await q.answer("Preparo il registro…")
    await _manda(context.bot, q.message.chat_id, q.from_user, ["7"])


def get_handlers() -> list:
    return [CommandHandler("registro", cmd_registro), CallbackQueryHandler(cb_registro, pattern=r"^reg:7$"),
            CallbackQueryHandler(cb_scelta, pattern=r"^rg:\d+$")]

"""
/giocatori_build (v7.42.0, Luca 28/11): la ricerca di /giocatori costruita coi bottoni, un passo alla volta, in tutti
i bot che hanno /giocatori (principale, loucabot, klra). Un solo messaggio che si aggiorna: in cima la ricerca fin qui
(la stessa sintassi di /giocatori, da ricopiare), sotto le categorie. Niente testo da scrivere (ogni bot ha già i suoi
gestori dei messaggi): i valori numerici sono soglie già pronte e, accanto, «🎚 Altro valore» che parte da 10 e si cambia con le frecce (v7.42.3); il nome (nome:REGEX) si
scrive a mano ricopiando la ricerca.

I connettori sono quelli di /giocatori: dentro un gruppo i filtri sono in «e», più valori dello stesso filtro in «o»
(due squadre NBA, due posizioni), «➕ Oppure» apre un gruppo alternativo (`|`), «🚫 Nega» mette un `-` davanti al
filtro dopo. Le parentesi non servono: «(A o B) e C» si scrive come «A C | B C».

Lo stato è in context.user_data["gb"] (di chi l'ha aperto: nei gruppi gli altri non lo toccano), i bottoni sono gb:…
`gestori(esegui)`: il comando e i bottoni, che ogni bot registra; `esegui(update, context, testo)` fa la ricerca (di base risposta + manda di
shared/elenco_giocatori; klra la fa nel contesto del sistema).
"""
import asyncio
import html

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup

from shared import elenco_giocatori as EG
from shared import lettura as L
from shared.squadre_nba import NBA

CHIAVE = "gb"
POSIZIONI = ("PG", "SG", "SF", "PF", "C", "G", "F")
SITUAZIONI = (("fa", "FA"), ("firmati", "Firmati"), ("diritti", "Diritti"), ("rookie", "Rookie"), ("watch", "👁 Watchlist"))
# filtro: (titolo, chiave nella ricerca, soglie già pronte, modo). v7.42.3 (Luca, 28/11): accanto alle soglie
# «🎚 Altro valore», un numero che parte da PARTENZA e si alza o abbassa con le frecce. Gli anni di contratto sono 1, 2, 3.
NUMERI = {"media": ("Media", "media", (10, 15, 20, 25, 30, 35, 40), "due"),
          "minuti": ("Minuti a partita", "minuti", (10, 15, 20, 25, 30, 35), "due"),
          "partite": ("Partite giocate", "min_g", (1, 5, 10, 20, 30, 40, 50), "almeno"),
          "costo": ("Costo del contratto (M)", "costo", (1, 5, 10, 20, 30, 40), "due"),
          "anni": ("Anni di contratto rimasti (questa stagione compresa)", "anni", (), "anni")}
PARTENZA = 10
PASSI = (-5, -1, 1, 5)
ANNI = (1, 2, 3)                   # il contratto più lungo è di 3 anni
ORDINI = (("media", "Media"), ("costo", "Costo"), ("partite", "Partite"), ("ultime5", "Ultime 5"), ("minuti", "Minuti"),
          ("nome", "Nome"))
TOP = (10, 20, 50, 100)
STAGIONI = 6                       # la stagione in corso e le 5 prima


def e(x) -> str:
    return html.escape(str(x), quote=False)


def nuovo(uid: int | None) -> dict:
    return {"uid": uid, "gruppi": [[]], "nega": False, "ordina": None, "top": None, "anno": None, "val": {}}


def testo(st: dict) -> str:
    """La ricerca fin qui, nella sintassi di /giocatori."""
    pezzi = [" ".join(EG._quota(t) for t in g) for g in st["gruppi"] if g]
    q = " | ".join(pezzi)
    opz = [x for x in (f"ordina:{st['ordina']}" if st["ordina"] else "", f"top:{st['top']}" if st["top"] else "",
                       f"anno:{st['anno']}" if st["anno"] else "") if x]
    return " ".join(x for x in [q] + opz if x)


def _chiave(t: str) -> str:
    return t.lstrip("-").partition(":")[0].lower() if ":" in t else ""


def aggiungi(st: dict, t: str, sostituisci: str | None = None) -> None:
    """Un filtro nel gruppo in corso, col `-` se «Nega» è acceso. `sostituisci`: toglie prima lo stesso filtro
    (i valori singoli: min_g, anni, infortunati; per media e minuti la stessa direzione)."""
    g = st["gruppi"][-1]
    if sostituisci:
        g[:] = [x for x in g if not (x.lstrip("-").lower().startswith(sostituisci))]
    if st["nega"]:
        t, st["nega"] = "-" + t, False
    if t not in g:
        g.append(t)


def togli(st: dict) -> None:
    if st["gruppi"][-1]:
        st["gruppi"][-1].pop()
    elif len(st["gruppi"]) > 1:
        st["gruppi"].pop()
    elif st["anno"] or st["top"] or st["ordina"]:     # niente filtri: le opzioni, dall'ultima
        k = "anno" if st["anno"] else "top" if st["top"] else "ordina"
        st[k] = None


def oppure(st: dict) -> bool:
    if not st["gruppi"][-1]:
        return False
    st["gruppi"].append([])
    return True


# ── le schermate ───────────────────────────────────────────────────────────────

def _righe(bottoni: list, n: int) -> list:
    return [bottoni[i:i + n] for i in range(0, len(bottoni), n)]


def _indietro() -> list:
    return [[B("⬅️ Indietro", callback_data="gb:home")]]


def schermata(st: dict, vista: str = "home", arg: str = "") -> tuple[str, InlineKeyboardMarkup]:
    q = testo(st)
    n = len(st["gruppi"])
    intesta = ("🧩 <b>Costruisci la ricerca</b>\n"
               + (f"<code>{e(EG.query(q))}</code>" if q else "<i>nessun filtro: tutti i giocatori</i>")
               + (f"\n➕ gruppo {n} (in «oppure» coi precedenti)" if n > 1 else "")
               + ("\n🚫 il prossimo filtro è negato" if st["nega"] else ""))
    if vista == "pos":
        return intesta + "\n\n<b>Posizione</b> (più posizioni valgono in «o»)", InlineKeyboardMarkup(
            _righe([B(p, callback_data=f"gb:a:{p}") for p in POSIZIONI], 5) + _indietro())
    if vista == "sit":
        return intesta + "\n\n<b>Situazione nel fantabasket</b>", InlineKeyboardMarkup(
            _righe([B(l, callback_data=f"gb:a:{t}") for t, l in SITUAZIONI], 3) + _indietro())
    if vista == "nba":
        b = [B(s, callback_data=f"gb:a:nba:{s}") for s in sorted(NBA)] + [B("Senza squadra", callback_data="gb:a:nba:no")]
        return intesta + "\n\n<b>Squadra NBA</b> (più squadre valgono in «o»)", InlineKeyboardMarkup(_righe(b, 5) + _indietro())
    if vista == "sq":
        sq = sorted(L.squadre(), key=lambda t: t["nome"].lower())
        b = [B(t["nome"][:30], callback_data=f"gb:sq:{i}") for i, t in enumerate(sq)]
        return intesta + "\n\n<b>Squadra del fantabasket</b>", InlineKeyboardMarkup(_righe(b, 2) + _indietro())
    if vista == "num":
        titolo, k, soglie, modo = NUMERI[arg]
        if modo == "anni":
            righe = [[B(f"{a}", callback_data=f"gb:n:{arg}:{a}") for a in ANNI], [B("almeno 2", callback_data=f"gb:n:{arg}:>=2")]]
            return intesta + f"\n\n<b>{titolo}</b>", InlineKeyboardMarkup(righe + _indietro())
        righe = [[B(f"≥ {x}", callback_data=f"gb:n:{arg}:{x}+") for x in soglie[i:i + 4]] for i in range(0, len(soglie), 4)]
        if modo == "due":
            righe += [[B(f"≤ {x}", callback_data=f"gb:n:{arg}:{x}-") for x in soglie[i:i + 4]] for i in range(0, len(soglie), 4)]
        righe.append([B("🎚 Altro valore", callback_data=f"gb:c:{arg}")])
        nota = "\n≥ almeno, ≤ al massimo: tutti e due fanno un intervallo." if modo == "due" else "\n≥ almeno."
        return intesta + f"\n\n<b>{titolo}</b>{nota}", InlineKeyboardMarkup(righe + _indietro())
    if vista == "numc":
        titolo, k, _, modo = NUMERI[arg]
        v = st.setdefault("val", {}).get(arg, PARTENZA)
        frecce = [B(("⏪ " if d < -1 else "◀️ " if d < 0 else "") + f"{d:+d}" + (" ▶️" if d == 1 else " ⏩" if d > 1 else ""),
                    callback_data=f"gb:s:{arg}:{d}") for d in PASSI]
        scelta = [B(f"≥ almeno {v}", callback_data=f"gb:n:{arg}:{v}+")]
        if modo == "due":
            scelta.append(B(f"≤ al massimo {v}", callback_data=f"gb:n:{arg}:{v}-"))
        return (intesta + f"\n\n<b>{titolo}</b>: <b>{v}</b> (con le frecce si cambia)",
                InlineKeyboardMarkup([frecce, scelta, [B("⬅️ Indietro", callback_data=f"gb:num:{arg}")]]))
    if vista == "inf":
        return intesta + "\n\n<b>Infortunati</b>", InlineKeyboardMarkup(
            [[B("Senza infortunati", callback_data="gb:a:infortunati:no"), B("Solo infortunati", callback_data="gb:a:infortunati:si")]]
            + _indietro())
    if vista == "ord":
        return intesta + "\n\n<b>Ordina per</b>", InlineKeyboardMarkup(
            _righe([B(l, callback_data=f"gb:o:{k}") for k, l in ORDINI], 3) + _indietro())
    if vista == "verso":
        nome = dict(ORDINI)[arg]
        su, giu = ("A → Z", "Z → A") if arg == "nome" else ("▲ dal più basso", "▼ dal più alto")
        return intesta + f"\n\n<b>Ordina per {e(nome)}</b>", InlineKeyboardMarkup(
            [[B(giu, callback_data=f"gb:v:{arg}:-"), B(su, callback_data=f"gb:v:{arg}:+")]] + _indietro())
    if vista == "top":
        return intesta + "\n\n<b>Quanti</b>", InlineKeyboardMarkup(
            [[B(f"{t}", callback_data=f"gb:t:{t}") for t in TOP] + [B("Tutti", callback_data="gb:t:0")]] + _indietro())
    if vista == "anno":
        oggi = int(L.stagione())
        b = [B(f"{EG.lbl(a)}" + (" (in corso)" if a == oggi else ""), callback_data=f"gb:y:{a}") for a in range(oggi, oggi - STAGIONI, -1)]
        return intesta + "\n\n<b>Stagione</b> (le passate da Basketball-Reference)", InlineKeyboardMarkup(_righe(b, 3) + _indietro())
    kb = [[B("📍 Posizione", callback_data="gb:pos"), B("📋 Situazione", callback_data="gb:sit")],
          [B("🏀 Squadra NBA", callback_data="gb:nba"), B("🏆 Squadra", callback_data="gb:sq")],
          [B("📈 Media", callback_data="gb:num:media"), B("⏱ Minuti", callback_data="gb:num:minuti")],
          [B("🔢 Partite", callback_data="gb:num:partite"), B("💰 Costo", callback_data="gb:num:costo")],
          [B("📆 Anni", callback_data="gb:num:anni"), B("🩹 Infortunati", callback_data="gb:inf")],
          [B("🚫 Nega il prossimo: " + ("sì" if st["nega"] else "no"), callback_data="gb:neg")],
          [B("➕ Oppure", callback_data="gb:or"), B("✖️ Togli l'ultimo", callback_data="gb:del")],
          [B("↕️ Ordina", callback_data="gb:ord"), B("🔝 Quanti", callback_data="gb:top"), B("📅 Stagione", callback_data="gb:anno")],
          [B("🔎 Cerca", callback_data="gb:go"), B("🗑 Ricomincia", callback_data="gb:new")]]
    return intesta, InlineKeyboardMarkup(kb)


def premi(st: dict, data: str) -> tuple[str, str, str | None]:
    """Un bottone sullo stato: (vista, argomento, avviso). vista «go» = cerca."""
    p = data.split(":")[1:]
    a = p[0] if p else "home"
    if a in ("home", "pos", "sit", "nba", "sq", "inf", "ord", "top", "anno") and len(p) == 1:
        return a, "", None
    if a == "num":
        return "num", p[1], None
    if a == "x":
        return "", "", None                                 # le etichette «almeno» / «al massimo»
    if a == "a":
        t = ":".join(p[1:])
        aggiungi(st, t, "infortunati:" if t.startswith("infortunati:") else None)
        return "home", "", None
    if a == "sq":
        sq = sorted(L.squadre(), key=lambda t: t["nome"].lower())
        i = int(p[1])
        if i >= len(sq):
            return "home", "", "Squadra non trovata."
        aggiungi(st, "squadra:" + sq[i]["nome"])
        return "home", "", None
    if a == "s":                                          # le frecce: il valore, mai sotto 0
        val = st.setdefault("val", {})
        val[p[1]] = max(0, val.get(p[1], PARTENZA) + int(p[2]))
        return "numc", p[1], None
    if a == "c":
        return "numc", p[1], None
    if a == "n":
        _, k, _, modo = NUMERI[p[1]]
        v = ":".join(p[2:])
        g = st["gruppi"][-1]
        if modo == "anni" or modo == "almeno":
            aggiungi(st, f"{k}:{v.rstrip('+')}", f"{k}:")
        elif k == "costo":                                 # costo è un filtro solo: almeno e al massimo fanno A-B
            n, su = v[:-1], v.endswith("+")
            altro = next((x for x in g if x.lstrip("-").lower().startswith("costo:")), "")
            vecchio = altro.partition(":")[2]
            if su and vecchio.startswith("<="):
                v = f"{n}-{vecchio[2:]}"
            elif not su and vecchio.startswith(">="):
                v = f"{vecchio[2:]}-{n}"
            else:
                v = (">=" if su else "<=") + n
            aggiungi(st, f"costo:{v}", "costo:")
        else:
            g[:] = [x for x in g if not (x.lstrip("-").lower().startswith(f"{k}:") and x.endswith(v[-1]))]
            aggiungi(st, f"{k}:{v}")
        return "home", "", None
    if a == "neg":
        st["nega"] = not st["nega"]
        return "home", "", None
    if a == "or":
        return "home", "", None if oppure(st) else "Prima metti almeno un filtro in questo gruppo."
    if a == "del":
        togli(st)
        return "home", "", None
    if a == "o":
        return "verso", p[1], None
    if a == "v":
        st["ordina"] = p[1] + ("" if (p[2] == "-" and p[1] != "nome") or (p[2] == "+" and p[1] == "nome") else p[2])
        if st["ordina"] == "media":
            st["ordina"] = None                            # il default
        return "home", "", None
    if a == "t":
        st["top"] = int(p[1]) or None
        return "home", "", None
    if a == "y":
        st["anno"] = None if int(p[1]) == int(L.stagione()) else int(p[1])
        return "home", "", None
    if a == "new":
        st.update(nuovo(st["uid"]))
        return "home", "", None
    if a == "go":
        return "go", "", None
    return "home", "", None


# ── i gestori ──────────────────────────────────────────────────────────────────

async def esegui_base(update, context, q: str) -> None:
    privato = getattr(getattr(update, "effective_chat", None), "type", "private") == "private"
    r = await asyncio.to_thread(EG.risposta, q, update.effective_user.id, privato)
    await EG.manda(update.effective_message, r)


PATTERN = r"^gb:"


def gestori(esegui=None, solo_privato: bool = False) -> tuple:
    """(comando, bottoni): ogni bot li registra lui (CommandHandler("giocatori_build", …) e CallbackQueryHandler col
    PATTERN), così le prove delle guide li trovano. solo_privato: il bot principale (segnato per il menu admin)."""
    esegui = esegui or esegui_base

    async def cmd(update, context):
        uid = getattr(update.effective_user, "id", None)
        st = context.user_data[CHIAVE] = nuovo(uid)
        t, kb = schermata(st)
        m = await update.effective_message.reply_text(t, parse_mode="HTML", reply_markup=kb, disable_notification=True)
        st["msg"] = getattr(m, "message_id", None)

    async def cb(update, context):
        import types
        q = update.callback_query
        st = context.user_data.get(CHIAVE)
        if not st or (st.get("msg") and getattr(q.message, "message_id", None) != st["msg"]):
            await q.answer("Questa ricerca è scaduta (o è di un altro): /giocatori_build per una nuova.", show_alert=True)
            return
        vista, arg, avviso = premi(st, q.data)
        await q.answer(avviso or None, show_alert=bool(avviso))
        if not vista:
            return
        if vista == "go":
            u = types.SimpleNamespace(effective_message=q.message, effective_user=q.from_user,
                                      effective_chat=getattr(q.message, "chat", None), callback_query=q, message=q.message)
            await esegui(u, context, testo(st))
            return
        t, kb = schermata(st, vista, arg)
        try:
            await q.edit_message_text(t, parse_mode="HTML", reply_markup=kb)
        except Exception as err:                         # «message is not modified»: lo stesso bottone due volte
            if "not modified" not in str(err).lower():
                raise

    if solo_privato:
        cmd._solo_privato = True
    return cmd, cb

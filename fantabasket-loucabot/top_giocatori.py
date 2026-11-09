"""
/top (v6.22.0, Luca 04/11): la classifica dei giocatori NBA per fantamedia della stagione in corso.

- Tutti i giocatori NBA (con «firmati» solo quelli sotto contratto nella lega).
- Fantamedia come nel calcolo: tabellini ESPN, regular season e play-in, uno 0 con 0 minuti non conta.
- Minimo di partite: almeno il 40% (MINIMO) delle partite finite della sua squadra NBA (quella di adesso, se no
  quella dell'ultimo tabellino); lo dice l'intestazione.
- Per ognuno: fantamedia, partite, squadra NBA, squadra del fanta o «libero», posizioni eleggibili.
- Argomenti: niente → 1–20; un numero N → 1–N; due numeri → da A a B («/top 50 80», anche «50-80»); «firmati».
  Se il testo non sta in un messaggio, arriva come file .md, e lo si dice.
"""
import io
import math
import re

import config
import db
from numeri import testo as tp

MINIMO = 0.40
LIMITE = 4000
DEFAULT = 20


def leggi_argomenti(args: list[str]) -> tuple[int, int, bool, str | None]:
    """(da, a, solo firmati, errore)."""
    firmati = any(a.lower() in ("firmati", "firmato", "f") for a in args)
    numeri = [int(x) for a in args for x in re.findall(r"\d+", a)]
    if not numeri:
        return 1, DEFAULT, firmati, None
    if len(numeri) == 1:
        return 1, numeri[0], firmati, (None if numeri[0] >= 1 else "Il numero deve essere almeno 1.")
    da, a = sorted(numeri[:2])
    return max(1, da), a, firmati, None


def classifica(s: str, solo_firmati: bool = False) -> list[dict]:
    """Tutti i giocatori sopra il minimo di partite, dalla fantamedia più alta."""
    righe = db.q("""WITH g AS (
                        SELECT t.atleta, MAX(t.nome) AS nome, AVG(t.fp)::float AS media, COUNT(*) AS partite,
                               (ARRAY_AGG(t.squadra ORDER BY p.inizio DESC))[1] AS ultima
                        FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                        WHERE p.stagione = %s AND p.tipo = ANY(%s) AND t.giocato AND NOT (t.fp = 0 AND t.minuti = 0)
                        GROUP BY t.atleta)
                    SELECT g.*, a.squadra, gi.id AS gid, c.team_id
                    FROM g LEFT JOIN nba_atleti a ON a.atleta = g.atleta
                    LEFT JOIN giocatori gi ON gi.espn_id = g.atleta
                    LEFT JOIN contratti c ON c.giocatore_id = gi.id AND c.attivo""", (s, [2, 5]), many=True) or []
    squadre = {r["sq"]: r["n"] for r in db.q(
        """SELECT sq, COUNT(*) AS n FROM (SELECT casa AS sq FROM nba_partite WHERE stagione = %s AND tipo = ANY(%s) AND stato = 'STATUS_FINAL'
               UNION ALL SELECT trasferta FROM nba_partite WHERE stagione = %s AND tipo = ANY(%s) AND stato = 'STATUS_FINAL') x
           GROUP BY sq""", (s, [2, 5], s, [2, 5]), many=True) or []}
    try:
        pos = {r["giocatore_id"]: r["posizioni"] for r in db.q("SELECT giocatore_id, posizioni FROM posizioni_attuali",
                                                                 many=True) or []}
    except Exception:
        pos = {}
    out, visti = [], set()
    for r in righe:
        if r["atleta"] in visti:
            continue
        visti.add(r["atleta"])
        if solo_firmati and not r["team_id"]:
            continue
        sq = r["squadra"] or r["ultima"]
        tot = squadre.get(sq, 0)
        if tot and r["partite"] < math.ceil(MINIMO * tot):
            continue
        out.append({"nome": r["nome"], "media": r["media"], "partite": r["partite"], "squadra": sq or "—",
                    "fanta": config.nome(r["team_id"]) if r["team_id"] else "libero",
                    "pos": (pos.get(r["gid"]) or "").replace(",", "/")})
    out.sort(key=lambda x: (-x["media"], x["nome"]))
    return out


def testo(s: str, da: int, a: int, solo_firmati: bool) -> tuple[str, int]:
    tutti = classifica(s, solo_firmati)
    scelti = tutti[da - 1:a]
    anno = f"{s}-{str(int(s) + 1)[-2:]}"
    righe = [f"🏆 Top {da}–{min(a, da - 1 + len(scelti))} per fantamedia · stagione {anno}"
             + (" · solo firmati" if solo_firmati else ""),
             f"Con almeno il {int(MINIMO * 100)}% delle partite della propria squadra NBA · fantapunti dai tabellini "
             f"ESPN, regular season e play-in ({len(tutti)} giocatori in classifica)", ""]
    for i, x in enumerate(scelti, da):
        righe.append(f"{i}. {x['nome']} {tp(x['media'])} · {x['partite']} G · {x['squadra']} · {x['fanta']}"
                     + (f" · {x['pos']}" if x["pos"] else ""))
    if not scelti:
        righe.append("Nessun giocatore in questo intervallo.")
    return "\n".join(righe), len(scelti)


async def cmd_top(update, context):
    msg = update.effective_message
    da, a, firmati, errore = leggi_argomenti(context.args or [])
    if errore:
        await msg.reply_text(errore)
        return
    import asyncio
    t, _n = await asyncio.to_thread(testo, config.stagione(), da, a, firmati)
    if len(t) <= LIMITE:
        await msg.reply_text(t)
        return
    await msg.reply_document(document=io.BytesIO(t.encode("utf-8")), filename=f"top_{da}-{a}.md",
                             caption=f"📄 Top {da}–{a}: troppo lunga per un messaggio, eccola in un file.")


# ── /top_storica ANNO [N | DA A] (v7.4.0, Luca 09/11) ─────────────────────────
# La classifica per fantamedia di una stagione passata dalle medie di Basketball-Reference (regular season, dati dal
# 2002-03). L'anno come nel resto della lega: la stagione che comincia quell'anno (2014 = 2014-15); vanno bene anche
# «2014-15» e «14-15». Minimo di partite: il 40% (MINIMO) delle partite giocate da chi ne ha giocate di più quell'anno
# (bref non ha le partite delle squadre: così vale anche per le stagioni corte, come 2011-12 e 2019-20). Chi ha
# cambiato squadra: la riga del totale e le squadre in ordine. La stagione in corso è /top (tabellini ESPN).

def leggi_storica(args: list[str], s_ora: str) -> tuple[str | None, int, int, str | None]:
    """(stagione della lega, da, a, errore)."""
    testo = " ".join(args)
    m = re.search(r"\b(\d{2}|\d{4})\s*[-/]\s*(\d{2}|\d{4})\b", testo)
    if m:
        inizio = int(m.group(1))
        inizio = inizio + (2000 if inizio < 50 else 1900) if inizio < 100 else inizio
        resto = testo[:m.start()] + " " + testo[m.end():]
    else:
        anni = [int(x) for x in re.findall(r"\b(\d{4})\b", testo)]
        if not anni:
            return None, 1, DEFAULT, "Uso: /top_storica ANNO [N] o [DA A], es. /top_storica 2014 (= 2014-15), /top_storica 2009-10 50"
        inizio = anni[0]
        resto = testo.replace(str(inizio), " ", 1)
    if inizio >= int(s_ora):
        return None, 1, DEFAULT, f"Per la stagione in corso c'è /top (tabellini ESPN). /top_storica arriva fino al {int(s_ora) - 1}-{str(s_ora)[-2:]}."
    da, a, _f, errore = leggi_argomenti(re.findall(r"\d+", resto))
    return str(inizio), da, a, errore


def classifica_storica(s: str) -> list[dict]:
    """Per ogni giocatore della stagione (bref: anno di fine = s + 1) l'ultima istantanea di ogni riga; totale e squadre."""
    righe = db.q("""SELECT DISTINCT ON (nome_bref, team) nome_bref, team, g, mp, fantamedia,
                           MIN(id) OVER (PARTITION BY nome_bref, team) AS primo
                    FROM bref_stats WHERE stagione = %s ORDER BY nome_bref, team, timestamp DESC, id DESC""",
                 (str(int(s) + 1),), many=True) or []
    per = {}
    for r in righe:
        per.setdefault(r["nome_bref"], []).append(r)
    out = []
    for nome, rr in per.items():
        tot = [r for r in rr if (r["team"] or "").upper() == "TOT" or (r["team"] or "").upper().endswith("TM")]
        base = tot[0] if tot else max(rr, key=lambda r: r["g"] or 0)
        squadre = [r["team"] for r in sorted([r for r in rr if r not in tot], key=lambda r: r["primo"]) if r["team"]]
        out.append({"nome": nome, "media": float(base["fantamedia"] or 0), "partite": int(base["g"] or 0),
                    "minuti": float(base["mp"] or 0), "squadra": "·".join(squadre) or (base["team"] or "—")})
    massimo = max((x["partite"] for x in out), default=0)
    minimo = math.ceil(MINIMO * massimo)
    out = [x for x in out if x["partite"] >= minimo]
    out.sort(key=lambda x: (-x["media"], x["nome"]))
    return out


def testo_storica(s: str, da: int, a: int) -> tuple[str, int]:
    tutti = classifica_storica(s)
    anno = f"{s}-{str(int(s) + 1)[-2:]}"
    if not tutti:
        return f"Nessun dato di Basketball-Reference per il {anno} (ci sono dal 2002-03).", 0
    scelti = tutti[da - 1:a]
    righe = [f"🏛️ Top {da}–{min(a, da - 1 + len(scelti))} per fantamedia · stagione {anno}",
             f"Medie di Basketball-Reference, regular season · almeno il {int(MINIMO * 100)}% delle partite "
             f"({len(tutti)} giocatori in classifica)", ""]
    for i, x in enumerate(scelti, da):
        righe.append(f"{i}. {x['nome']} {tp(x['media'])} · {x['partite']} G · " + f"{x['minuti']:.1f}".replace(".", ",") + f"′ · {x['squadra']}")
    if not scelti:
        righe.append("Nessun giocatore in questo intervallo.")
    return "\n".join(righe), len(scelti)


async def cmd_top_storica(update, context):
    msg = update.effective_message
    s, da, a, errore = leggi_storica(list(context.args or []), config.stagione())
    if errore:
        await msg.reply_text(errore)
        return
    import asyncio
    t, _n = await asyncio.to_thread(testo_storica, s, da, a)
    if len(t) <= LIMITE:
        await msg.reply_text(t)
        return
    await msg.reply_document(document=io.BytesIO(t.encode("utf-8")), filename=f"top_storica_{s}_{da}-{a}.md",
                             caption=f"📄 Top {da}–{a} del {s}-{str(int(s) + 1)[-2:]}: troppo lunga per un messaggio, eccola in un file.")

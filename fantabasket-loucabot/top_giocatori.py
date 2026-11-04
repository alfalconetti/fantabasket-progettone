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

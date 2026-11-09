"""
/status [SQUADRA] (v7.1.0 in loucabot, Luca 06/11; v7.3.0 in shared/, anche nel bot principale): gli injury status
dei giocatori sotto contratto di una squadra (di default la propria) dall'ultimo snapshot ESPN già nel database
(niente richieste a ESPN). Per ognuno: stato, da quando (giorni consecutivi con lo stesso stato negli snapshot
tenuti), squadra NBA e dettaglio. Chi non c'è nello snapshot è sano.
"""
import html
from zoneinfo import ZoneInfo

from shared import lettura as L

ROMA = ZoneInfo("Europe/Rome")
ORDINE = {"Out": 0, "Doubtful": 1, "Questionable": 2, "Day-To-Day": 3, "Probable": 4}


def e(x) -> str:
    return html.escape(str(x), quote=False)


def dati(team_id: str) -> dict:
    gioc = L.q("""SELECT g.id, g.nome_common, g.espn_id FROM contratti c JOIN giocatori g ON g.id = c.giocatore_id
                   WHERE c.team_id = %s AND c.attivo ORDER BY g.nome_common""", (team_id,), many=True) or []
    ultimo = (L.q("SELECT MAX(preso) AS p FROM nba_infortuni", one=True) or {}).get("p")
    atleti = [g["espn_id"] for g in gioc if g.get("espn_id")]
    voci = {}
    if ultimo and atleti:
        storia = L.q("""SELECT atleta, giorno, preso, stato, dettaglio, squadra FROM nba_infortuni
                         WHERE atleta = ANY(%s) ORDER BY atleta, preso DESC""", (atleti,), many=True) or []
        snap = sorted({r["preso"] for r in L.q("SELECT DISTINCT preso FROM nba_infortuni", many=True) or []}, reverse=True)
        per = {}
        for r in storia:
            per.setdefault(r["atleta"], {})[r["preso"]] = r
        for a, righe in per.items():
            if ultimo not in righe:
                continue                                   # non è nell'ultimo snapshot: sano
            ora = righe[ultimo]
            dal = ora["giorno"]
            for p in snap:                                 # indietro finché ogni snapshot lo dà con lo stesso stato
                r = righe.get(p)
                if not r or r["stato"] != ora["stato"]:
                    break
                dal = r["giorno"]
            voci[a] = {**ora, "dal": dal}
    return {"giocatori": gioc, "voci": voci, "ultimo": ultimo}


def testo(team_id: str) -> str:
    d = dati(team_id)
    nome = L.nome(team_id)
    if not d["ultimo"]:
        return f"🩹 <b>{e(nome)}</b>: nessuno snapshot degli infortunati nel database, per ora."
    righe = [f"🩹 <b>Status di {e(nome)}</b>", f"<i>snapshot ESPN del {d['ultimo'].astimezone(ROMA):%d/%m alle %H:%M}</i>", ""]
    con = [(g, d["voci"][g["espn_id"]]) for g in d["giocatori"] if g.get("espn_id") in d["voci"]]
    con.sort(key=lambda x: (ORDINE.get(x[1]["stato"], 9), x[0]["nome_common"]))
    for g, v in con:
        det = (v.get("dettaglio") or "").strip()
        righe.append(f"• <b>{e(g['nome_common'])}</b>" + (f" ({e(v['squadra'])})" if v.get("squadra") else "")
                     + f": <b>{e(v['stato'])}</b> dal {v['dal']:%d/%m}" + (f"\n   <i>{e(det[:160])}</i>" if det else ""))
    if not con:
        righe.append("✅ Nessuno nella lista degli infortunati.")
    sani = [g for g in d["giocatori"] if g.get("espn_id") and g["espn_id"] not in d["voci"]]
    senza = [g for g in d["giocatori"] if not g.get("espn_id")]
    if sani and con:
        righe += ["", f"✅ Gli altri {len(sani)}: nessuna voce (disponibili)."]
    if senza:
        righe.append("⚪ Non abbinati a ESPN (status sconosciuto): " + ", ".join(e(g["nome_common"]) for g in senza))
    righe += ["", "<i>«dal» = da quando gli snapshot tenuti lo danno così (quelli più vecchi di una settimana sono uno al giorno)</i>"]
    return "\n".join(righe)


async def cmd_status(update, context):
    from shared.squadre import cerca_squadra
    msg = update.effective_message
    q = " ".join(context.args or []).strip()
    sq = cerca_squadra(q, L.squadre()) if q else L.squadra_del_gm(update.effective_user.id)
    if not sq:
        await msg.reply_text(f"Squadra non trovata: «{q}»." if q else "Uso: /status SQUADRA (senza, la tua squadra).")
        return
    await msg.reply_text(testo(sq["id"]), parse_mode="HTML")

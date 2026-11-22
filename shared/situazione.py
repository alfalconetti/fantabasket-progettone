"""/rendimento_situazione NOME [periodo] (loucabot, v7.20.0; Luca 21/11, mockup approvato): la fantamedia di un
giocatore divisa per dov'era nella giornata del fantabasket di ogni partita, come la query fatta a mano per
Hezonja il 19/11.

Per ogni partita NBA di regular season **giocata** (le DNP non contano) dentro una giornata di regular season:
- squadra del fantabasket = quella dell'ultimo movimento prima dell'inizio della partita (`movimenti_giocatori`),
  nessuna = **free agent**;
- **quintetto** se è nella formazione di quella giornata di quella squadra (`ipa_formazioni`), **panchina** se è
  nella sua panchina (`ipa_panchine`), se no **tribuna** (in squadra ma né quintetto né panchina).

Risposta (v7.20.2: solo immagine): i riquadri (media totale e per situazione) e la tabella a doppia entrata squadra ×
quintetto/panchina/tribuna come immagine (`situazione.typ`), con i totali di riga e di colonna e la casella migliore
in oro; l'immagine sempre, anche con una squadra sola (v7.20.1, Luca 21/11: «con immagine a prescindere»).
Periodo: shared.periodo (stagione, da una data, tra due date, ultime N giocate).
"""
import asyncio
import json
import os

from shared import lettura as L
from shared import non_ufficiale as NU
from shared import periodo as PER

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "situazione.typ")
COLONNE = (("quintetto", "Quintetto"), ("panchina", "Panchina"), ("tribuna", "Tribuna"))
FA = "free agent"
GRIGIO_FA = "#9CA3AF"
EMOJI = {"quintetto": "🏀", "panchina": "🪑", "tribuna": "🎟", FA: "🆓"}


def _tabella(nome: str) -> bool:
    return bool(L.q("SELECT to_regclass(%s) AS t", (nome,), one=True)["t"])


def partite(gid: int, periodo: PER.Periodo, stagione: str | None = None) -> list[dict]:
    """[{fp, data, giornata, team, dove}] dalla più vecchia, già filtrate per periodo."""
    stagione = stagione or L.stagione()
    g = L.q("SELECT espn_id FROM giocatori WHERE id = %s", (gid,), one=True) or {}
    if not g.get("espn_id"):
        return []
    # v7.20.2 (Luca, 21/11): col periodo anche a cavallo di due stagioni (ogni partita con la sua stagione e le sue giornate)
    col_periodo = bool(periodo.dal or periodo.al or periodo.ultime)
    filtri, par = ("", [g["espn_id"]]) if col_periodo else (" AND p.stagione = %s", [g["espn_id"], stagione])
    if periodo.dal:
        filtri += " AND p.data_et >= %s"
        par.append(periodo.dal)
    if periodo.al:
        filtri += " AND p.data_et <= %s"
        par.append(periodo.al)
    righe = L.q(f"""SELECT t.*, p.data_et AS data, p.inizio, p.stagione, gg.numero AS giornata,
                           (SELECT m.team_id_a FROM movimenti_giocatori m
                            WHERE m.giocatore_id = %s AND m.timestamp <= p.inizio
                            ORDER BY m.timestamp DESC, m.id DESC LIMIT 1) AS team
                    FROM nba_tabellini t
                    JOIN nba_partite p ON p.espn_id = t.partita AND p.tipo = 2
                    JOIN lega_giornate gg ON gg.stagione = p.stagione AND gg.tipo = 'regular'
                                         AND p.data_et BETWEEN gg.dal AND gg.al
                    WHERE t.atleta = %s AND t.giocato{filtri}
                    ORDER BY p.inizio""", [gid] + par, many=True) or []
    if periodo.ultime:
        righe = righe[-periodo.ultime:]
    tab = {"form": _tabella("ipa_formazioni"), "panche": _tabella("ipa_panchine")}
    for r in righe:
        r["fp"] = NU.fp(r)
        r["dove"] = _dove(gid, r["stagione"], r["giornata"], r["team"], tab)
    return righe


def _dove(gid: int, stagione: str, giornata: int, team: str | None, tab: dict) -> str:
    """quintetto / panchina / tribuna / free agent nella giornata, per la squadra che lo aveva."""
    if not team:
        return FA
    chiave = (stagione, giornata, team, gid)
    if tab["form"] and L.q("""SELECT 1 FROM ipa_formazioni WHERE stagione = %s AND giornata = %s AND team_id = %s
                               AND giocatore_id = %s""", chiave, one=True):
        return "quintetto"
    if tab["panche"] and L.q("""SELECT 1 FROM ipa_panchine WHERE stagione = %s AND giornata = %s AND team_id = %s
                                 AND righe @> jsonb_build_array(jsonb_build_object('giocatore_id', %s::int))""",
                             chiave, one=True):
        return "panchina"
    return "tribuna"


ETICHETTE_PLAYER = {"quintetto": "quintetto", "panchina": "panca", "tribuna": "tribuna", FA: "fa"}


def per_partita(gid: int, partite: list[str], stagione: str | None = None) -> dict[str, dict]:
    """v7.20.1 (Luca, 21/11, mockup approvato): per /player, la giornata del fantabasket e dov'era in ogni partita
    (anche saltate o DNP): {partita: {"giornata": n, "dove": quintetto/panca/tribuna/fa}}. Solo partite dentro una
    giornata di regular season."""
    stagione = stagione or L.stagione()
    if not partite:
        return {}
    righe = L.q("""SELECT p.espn_id, gg.numero AS giornata,
                          (SELECT m.team_id_a FROM movimenti_giocatori m
                           WHERE m.giocatore_id = %s AND m.timestamp <= p.inizio
                           ORDER BY m.timestamp DESC, m.id DESC LIMIT 1) AS team
                   FROM nba_partite p
                   JOIN lega_giornate gg ON gg.stagione = p.stagione AND gg.tipo = 'regular'
                                        AND p.data_et BETWEEN gg.dal AND gg.al
                   WHERE p.espn_id = ANY(%s) AND p.stagione = %s""", (gid, list(partite), stagione), many=True) or []
    tab = {"form": _tabella("ipa_formazioni"), "panche": _tabella("ipa_panchine")}
    return {r["espn_id"]: {"giornata": r["giornata"],
                           "dove": ETICHETTE_PLAYER[_dove(gid, stagione, r["giornata"], r["team"], tab)]} for r in righe}


def _num(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _cella(fps: list[float]) -> dict | None:
    return {"media": _num(sum(fps) / len(fps)), "g": len(fps), "v": sum(fps) / len(fps)} if fps else None


def _quando(date_: list) -> str:
    a, b = min(date_), max(date_)
    return f"{a:%d/%m}" if a == b else f"{a:%d/%m} – {b:%d/%m}"


def dati(gid: int, periodo: PER.Periodo, stagione: str | None = None) -> dict | None:
    """Tutto per testo e immagine; None se nel periodo non ha partite giocate."""
    from shared.rendimento import colore_squadra
    stagione = stagione or L.stagione()
    gare = partite(gid, periodo, stagione)
    if not gare:
        return None
    nome = (L.q("SELECT nome_common FROM giocatori WHERE id = %s", (gid,), one=True) or {}).get("nome_common", "?")
    stagioni = PER.stagioni_txt([r["stagione"] for r in gare])
    if periodo.dal or periodo.al or periodo.ultime:      # v7.20.2: il periodo com'è davvero nei dati
        from shared.rendimento import primo_dato
        quando_txt = f"{stagioni} · {PER.descrizione_vera(periodo, len(gare), primo_dato())}"
    else:
        quando_txt = stagioni
    per_dove = {k: [r["fp"] for r in gare if r["dove"] == k] for k in ("quintetto", "panchina", "tribuna", FA)}
    squadre = list(dict.fromkeys(r["team"] or FA for r in gare))
    squadre.sort(key=lambda t: (t == FA, min(r["data"] for r in gare if (r["team"] or FA) == t)))
    righe = []
    for t in squadre:
        sue = [r for r in gare if (r["team"] or FA) == t]
        if t == FA:
            info = {"nome": "Free agent", "colore": GRIGIO_FA}
        else:
            sq = L.squadra(t) or {"id": t, "nome": t}
            info = {"nome": sq.get("nome", t), "colore": colore_squadra(sq)}
        righe.append({**info, "id": t, "quando": _quando([r["data"] for r in sue]),
                      "celle": [None if t == FA else _cella([r["fp"] for r in sue if r["dove"] == k]) for k, _l in COLONNE],
                      "totale": _cella([r["fp"] for r in sue])})
    celle = [c for r in righe for c in r["celle"] if c]
    if len(celle) > 1:
        max(celle, key=lambda c: c["v"])["migliore"] = True
    tot = _cella([r["fp"] for r in gare])
    riquadri = [{"t": "Media", "v": tot["media"], "s": f"{tot['g']} {'partita' if tot['g'] == 1 else 'partite'}"}]
    for k, titolo in (("quintetto", "In quintetto"), ("panchina", "In panchina"), ("tribuna", "In tribuna"), (FA, "Free agent")):
        c = _cella(per_dove[k])
        riquadri.append({"t": titolo, "v": c["media"] if c else "—",
                         "s": f"{c['g']} {'partita' if c['g'] == 1 else 'partite'}" if c else "nessuna"})
    return {"nome": nome, "gid": gid, "periodo": f"{quando_txt} · {tot['g']} partite giocate",
            "riquadri": riquadri, "colonne": [l for _k, l in COLONNE], "righe": righe,
            "totali": [_cella(per_dove[k]) for k, _l in COLONNE], "totale": tot, "per_dove": per_dove,
            "nota": ("Per ogni partita NBA: dov'era nella giornata del fantabasket di quella partita (squadra dall'ultimo "
                     "movimento prima dell'inizio; quintetto e panchina quelli consegnati per la giornata; tribuna = in "
                     "squadra ma né in quintetto né in panchina). Solo partite giocate di regular season (le DNP non "
                     "contano). In oro la casella migliore.")}


def testo(d: dict) -> str:
    righe = [f"📊 <b>{d['nome']}</b> · media per situazione", d["periodo"], "",
             f"Media <b>{d['totale']['media']}</b> ({d['totale']['g']})"]
    for k, titolo in (("quintetto", "In quintetto"), ("panchina", "In panchina"), ("tribuna", "In tribuna"), (FA, "Free agent")):
        c = _cella(d["per_dove"][k])
        if c:
            righe.append(f"{EMOJI[k]} {titolo} <b>{c['media']}</b> ({c['g']})")
    return "\n".join(righe)


def immagine(d: dict) -> bytes:
    import typst
    fonts = [f for f in ("/usr/share/fonts",) if os.path.isdir(f)]
    pulito = {k: v for k, v in d.items() if k != "per_dove"}
    png = typst.compile(TEMPLATE, root="/", format="png", ppi=170, font_paths=fonts,
                        sys_inputs={"dati": json.dumps(NU.marca(pulito), ensure_ascii=False, default=str)})
    return png[0] if isinstance(png, list) else png


USO = ("Uso: /rendimento_situazione NOME [periodo]: la fantamedia divisa per quintetto, panchina, tribuna e free "
       "agent (e per squadra, se è stato in più squadre). Periodo: niente = la stagione; una data = da lì a oggi; due "
       "date = l'intervallo; un numero N (più di 5) = le ultime N partite giocate.\n"
       "Es. /rendimento_situazione Hezonja · /rendimento_situazione Hezonja 01-11-26 · /rendimento_situazione Hezonja 10")


async def rispondi(msg, gid: int, periodo: PER.Periodo) -> None:
    d = await asyncio.to_thread(dati, gid, periodo)
    if not d:
        await msg.reply_text("Nessuna partita giocata in questo periodo dentro una giornata di regular season.")
        return
    await msg.reply_photo(await asyncio.to_thread(immagine, d))     # v7.20.2 (Luca, 21/11): solo l'immagine, niente testo


async def cmd_rendimento_situazione(update, context):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as K
    from shared import giocatore as G
    msg = update.effective_message
    try:
        nome, periodo = PER.leggi(context.args or [])
    except PER.Errore as e:
        await msg.reply_text(str(e))
        return
    if not nome:
        await msg.reply_text(USO)
        return
    trovati = G.cerca(nome)
    if not trovati:
        await msg.reply_text(f"Nessun giocatore si chiama «{nome}».")
        return
    from shared.parole_nome import senza_apici
    if len(trovati) > 1 and L.norm(trovati[0]["nome_common"]) != L.norm(senza_apici(nome)):
        context.user_data["situazione_periodo"] = periodo
        from shared import pagine as PG                # v7.25.0: a pagine
        await PG.manda(msg, context, [(x["nome_common"] + (" ✅" if x["a_roster"] else ""), f"sit:{x['id']}") for x in trovati])
        return
    await rispondi(msg, trovati[0]["id"], periodo)


async def cb_rendimento_situazione(update, context):
    q = update.callback_query
    await q.answer()
    periodo = context.user_data.pop("situazione_periodo", None) or PER.Periodo()
    await q.edit_message_text("📊 ⬇️")
    await rispondi(q.message, int(q.data.split(":")[1]), periodo)

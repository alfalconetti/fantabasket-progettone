"""
/rendimento_team [SQUADRA] (v7.14.0, Luca 15/11; mockup approvato): come /rendimento ma per una squadra del
fantabasket, sul viola. Senza squadra quella del GM che scrive; per nome, id o GM.

- In testa: record della regular season, posizione in classifica, record in casa e in trasferta (e nei playoff, se
  ci sono); quattro riquadri: media punti (con la posizione nella lega), ultime 5 (▲/▼ sulla media, vinte e perse),
  giornata migliore e peggiore con l'avversario.
- Grafico: una barra per giornata convalidata coi punti fatti (regolamentari col bonus casa, come la classifica),
  piena se vinta, chiara se persa, oro la migliore; un trattino coi punti dell'avversario; C/T sotto l'asse; linea
  spessa = media delle ultime 5, tratteggiata = media della stagione (regular season); fascia gialla sulle giornate
  dei nostri playoff.
- Panchina (Luca, 15/11: «una riga per il rendimento della panchina»): una linea arancio coi fantapunti dei
  panchinari a ogni giornata (la somma dei fantapunti, calcolati come nel calcolo: risultati.calcola) e una riga
  con media (e posizione nella lega), panchina migliore e supplementari decisi. Il ricalcolo delle panchine di
  tutte le giornate costa: si tiene in memoria per (stagione, giornata, versione del calcolo).
"""
import asyncio
import io
import json
import logging
import os

import classifica as C
import config
import db
from numeri import testo as tp
from shared import codici_giornata as CG

logger = logging.getLogger(__name__)
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rendimento_team.typ")
MIN_GIORNATE = 3
_cache: dict[tuple, dict[str, float | None]] = {}       # (stagione, giornata, versione) → {team: punti della panchina}


def _risultati(s: str) -> list[dict]:
    """Tutti i risultati convalidati, playoff compresi, col tipo della giornata."""
    return db.q("""SELECT r.*, g.tipo FROM lega_risultati r JOIN lega_giornate g ON g.stagione = r.stagione AND g.numero = r.giornata
                   WHERE r.stagione = %s AND r.convalidato IS NOT NULL ORDER BY r.giornata""", (s,), many=True) or []


def panchine(s: str, n: int) -> dict[str, float | None]:
    """{team: fantapunti della panchina} nella giornata n (None: panchina non mandata)."""
    v = db.q("SELECT versione FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (s, n), one=True)
    chiave = (s, n, v["versione"] if v else 0)
    if chiave in _cache:
        return _cache[chiave]
    import risultati as R
    out = {}
    try:
        c = R.calcola(s, n)
        for r in c["risultati"]:
            for t, sq in ((r["casa"], r["sc"]), (r["trasferta"], r["st"])):
                pan = sq.get("panchina")
                out[t] = round(sum(float(x.get("fp") or 0) for x in pan if not x.get("doppio")), 2) if pan else None
    except Exception as err:
        logger.info("Rendimento team: panchine della G%s non calcolate (%s)", n, err)
    _cache[chiave] = out
    return out


def _sigla(nome: str) -> str:
    p = [x for x in nome.replace("-", " ").split() if x]
    return (p[0][0] + p[1][0]).upper() if len(p) > 1 else nome[:2].upper()


def _rec(pp: list[dict]) -> str:
    w = sum(1 for x in pp if x["v"])
    return f"{w}-{len(pp) - w}"


def dati(team: str, s: str | None = None) -> dict | None:
    """Il JSON per rendimento_team.typ; None con meno di MIN_GIORNATE giornate convalidate."""
    s = s or config.stagione()
    ris = _risultati(s)
    u = CG.ultima_rs(s) or 0
    gg = []
    for r in ris:
        if team not in (r["casa"], r["trasferta"]):
            continue
        casa = r["casa"] == team
        fatti, subiti = (float(r["punti_casa"]), float(r["punti_trasferta"])) if casa else (float(r["punti_trasferta"]), float(r["punti_casa"]))
        po = r["tipo"] == "playoff"
        gg.append({"n": r["giornata"], "cod": f"P{r['giornata'] - u}" if po else f"G{r['giornata']}", "po": po,
                   "fatti": fatti, "subiti": subiti, "v": r["vince"] == ("casa" if casa else "trasferta"), "casa": casa,
                   "avv": r["trasferta"] if casa else r["casa"], "supp": r["supp_casa"] is not None})
    if len(gg) < MIN_GIORNATE:
        return None
    rs = [x for x in gg if not x["po"]]
    # panchine: di tutte le squadre, per la posizione nella lega
    medie_pan: dict[str, list[float]] = {}
    for n in sorted({r["giornata"] for r in ris}):
        for t, v in panchine(s, n).items():
            if v is not None:
                medie_pan.setdefault(t, []).append(v)
    for x in gg:
        x["panchina"] = panchine(s, x["n"]).get(team)
    for i, x in enumerate(gg):
        w = gg[max(0, i - 4):i + 1]
        x["mobile"] = round(sum(y["fatti"] for y in w) / len(w), 2) if i >= 4 else None
    base = rs or gg
    media = sum(x["fatti"] for x in base) / len(base)
    righe, _ = C.calcola(s)
    pos = next((r["pos"] for r in righe if r["team"] == team), None)
    rango_media = sorted(((float(r["media"]) for r in righe if r.get("media") is not None)), reverse=True)
    # v7.18.2 (Luca, 19/11: «25ª della lega» con 24 squadre): la classifica arrotonda la media agli ottavi
    # (classifica.ottavi), quindi la si confronta con la media della squadra presa dalla stessa classifica,
    # non con quella esatta calcolata qui (100,08 contro il suo 100,125: tutte e 24 «più alte»)
    mia = next((float(r["media"]) for r in righe if r["team"] == team and r.get("media") is not None), media)
    pos_media = 1 + sum(1 for m in rango_media if m > mia + 1e-9)
    ult = gg[-5:]
    m5 = sum(x["fatti"] for x in ult) / len(ult)
    best = max(range(len(gg)), key=lambda i: gg[i]["fatti"])
    worst = min(range(len(gg)), key=lambda i: gg[i]["fatti"])
    nome = config.nome(team)
    from shared import quasi_cup as QC
    info = QC._squadra(team)
    po = [x for x in gg if x["po"]]
    sotto = (f"Stagione {s}-{(int(s) + 1) % 100:02d} · {_rec(rs)}" + (f" · {pos}ª in classifica" if pos else "")
             + f" · in casa {_rec([x for x in rs if x['casa']])}, in trasferta {_rec([x for x in rs if not x['casa']])}"
             + (f" · playoff {_rec(po)}" if po else ""))
    pan_team = [x["panchina"] for x in gg if x["panchina"] is not None]
    if pan_team:
        mp = sum(pan_team) / len(pan_team)
        tutte = sorted((sum(v) / len(v) for v in medie_pan.values() if v), reverse=True)
        pos_p = 1 + sum(1 for m in tutte if m > mp + 1e-9)
        bp = max((x for x in gg if x["panchina"] is not None), key=lambda x: x["panchina"])
        sup = [x for x in gg if x["supp"]]
        riga_pan = (f"media {tp(mp)} a giornata ({pos_p}ª della lega) · migliore {tp(bp['panchina'])} in {bp['cod']}"
                    + (f" · {len(sup)} supplementar{'e' if len(sup) == 1 else 'i'} (vint{'o' if len(sup) == 1 else 'i'} "
                       f"{sum(1 for x in sup if x['v'])})" if sup else " · nessun supplementare"))
        senza = sum(1 for x in gg if x["panchina"] is None)
        if senza:
            riga_pan += f" · {senza} giornat{'a' if senza == 1 else 'e'} senza panchina"
    else:
        riga_pan = "nessuna panchina calcolata"
    valori = [x["fatti"] for x in gg] + [x["subiti"] for x in gg] + pan_team
    lo = int(min(valori) // 50 * 50)
    hi = int(-(-max(valori) // 50) * 50)
    passo = 50 if hi - lo <= 400 else 100
    lo = lo // passo * passo
    ipo = [i for i, x in enumerate(gg) if x["po"]]
    return {"nome": nome, "sigla": _sigla(nome), "colore": info["colore"], "logo": info.get("logo") or "",
            "sotto": sotto,
            "riquadri": [
                {"t": "Media punti", "v": tp(media), "s": f"{pos_media}ª della lega" + (" · regular season" if po else "")},
                {"t": "Ultime 5", "v": tp(m5) + (" ▲" if m5 > media else " ▼" if m5 < media else ""),
                 "s": f"{sum(1 for x in ult if x['v'])} vint{'a' if sum(1 for x in ult if x['v']) == 1 else 'e'}, "
                      f"{sum(1 for x in ult if not x['v'])} pers{'a' if sum(1 for x in ult if not x['v']) == 1 else 'e'}"},
                {"t": "Migliore", "v": tp(gg[best]["fatti"]), "s": f"{gg[best]['cod']} vs {config.nome(gg[best]['avv'])}"},
                {"t": "Peggiore", "v": tp(gg[worst]["fatti"]), "s": f"{gg[worst]['cod']} vs {config.nome(gg[worst]['avv'])}"}],
            "giornate": [{k: x[k] for k in ("cod", "fatti", "subiti", "v", "casa", "panchina", "mobile")} for x in gg],
            "media": round(media, 2), "migliore": best, "y_min": lo, "y_max": hi, "passo": passo,
            "ogni": 5 if len(gg) > 12 else 2 if len(gg) > 6 else 1,
            "fanta": {"da": ipo[0], "a": ipo[-1]} if ipo else None, "panchina": riga_pan}


def immagine(d: dict) -> bytes:
    import typst
    fonts = [x for x in ("/usr/share/fonts",) if os.path.isdir(x)]
    return typst.compile(TEMPLATE, root="/", format="png", ppi=150, font_paths=fonts,
                         sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})


async def cmd_rendimento_team(update, context):
    from shared.squadre import cerca_squadra
    msg = update.effective_message
    args = list(context.args or [])
    team = cerca_squadra(" ".join(args), config.squadre()) if args else config.squadra_del_gm(update.effective_user.id)
    if not team:
        await msg.reply_text("Uso: /rendimento_team [SQUADRA o GM] — senza squadra la tua. Es: /rendimento_team Alfa")
        return
    try:
        d = await asyncio.to_thread(dati, team["id"])
        if not d:
            await msg.reply_text(f"{team['nome']}: servono almeno {MIN_GIORNATE} giornate convalidate.")
            return
        png = await asyncio.to_thread(immagine, d)
    except Exception as err:
        logger.exception("Rendimento team")
        await msg.reply_text(f"⚠️ Rendimento non disponibile: {err}")
        return
    await msg.reply_photo(photo=io.BytesIO(png), caption=f"📈 Rendimento di {team['nome']} · {d['sotto']}")


def get_handlers() -> list:
    from telegram.ext import CommandHandler
    return [CommandHandler("rendimento_team", cmd_rendimento_team, block=False)]

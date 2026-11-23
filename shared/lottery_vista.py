"""
Lottery: la classifica finale, le odds, l'ordine del draft (v7.27.1, Luca 23/11). Lettura condivisa tra loucabot
(che a fine regular season salva la classifica e pubblica le odds) e il bot principale (estrazione, draft).

- `lega_classifica_finale` (la scrive loucabot al blocco del tabellone dei playoff): stagione, squadra, posto
  generale (1 = la migliore), se è ai playoff, W e L.
- Seed della lottery: le 12 fuori dai playoff dall'ultima in su (seed 1 = l'ultima). Dalla 13ª alla 24ª le squadre
  dei playoff in ordine inverso della classifica. Secondo giro: tutte e 24 in ordine inverso della classifica.
"""
import json
import os

from shared import lettura as L
from shared import lottery as LT

TABELLA = """CREATE TABLE IF NOT EXISTS lega_classifica_finale (
                 stagione  TEXT NOT NULL,
                 team      TEXT NOT NULL,
                 posto     INT NOT NULL,
                 playoff   BOOLEAN NOT NULL,
                 w         INT NOT NULL DEFAULT 0,
                 l         INT NOT NULL DEFAULT 0,
                 salvata   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                 PRIMARY KEY (stagione, team))"""


def classifica(stagione: str) -> list[dict]:
    try:
        return L.q("SELECT * FROM lega_classifica_finale WHERE stagione = %s ORDER BY posto", (str(stagione),), many=True) or []
    except Exception:
        return []


def seed_lottery(stagione: str) -> list[str]:
    """Le 12 fuori dai playoff, dall'ultima (seed 1) in su."""
    return [r["team"] for r in reversed(classifica(stagione)) if not r["playoff"]]


def fisse(stagione: str) -> list[str]:
    """Dalla 13ª alla 24ª: le squadre dei playoff, dalla peggiore."""
    return [r["team"] for r in reversed(classifica(stagione)) if r["playoff"]]


def secondo_giro(stagione: str) -> list[str]:
    return [r["team"] for r in reversed(classifica(stagione))]


def chi_ha(anno: int | str, giro: int) -> dict[str, str]:
    """{squadra di partenza: chi ha la pick adesso} per le pick del draft `anno`."""
    rr = L.q("SELECT proprietario_orig, proprietario_att FROM pick WHERE anno = %s AND round = %s", (str(anno), giro), many=True) or []
    return {r["proprietario_orig"]: r["proprietario_att"] for r in rr}


def dati_odds(stagione: str) -> dict | None:
    """L'immagine delle odds (lottery_odds.typ, mockup approvato il 18/11). Il draft è quello dell'anno dopo."""
    cl = {r["team"]: r for r in classifica(stagione)}
    if len(cl) != 24:
        return None
    anno = int(stagione) + 1
    ha = chi_ha(anno, 1)
    sq = lambda t: L.squadra(t) or {"nome": t}
    lot = []
    for i, t in enumerate(seed_lottery(stagione)):
        di = ha.get(t, t)
        lot.append({"seed": i + 1, "squadra": sq(t)["nome"], "colore": L.colore(sq(t)), "wl": f"{cl[t]['w']}-{cl[t]['l']}",
                    "odds": [round(p * 100, 2) for p in LT.ODDS[i]],
                    "di": sq(di)["nome"] if di != t else "", "di_colore": L.colore(sq(di))})
    fx = []
    for k, t in enumerate(fisse(stagione)):
        di = ha.get(t, t)
        fx.append({"pick": f"{13 + k}ª", "squadra": sq(t)["nome"], "colore": L.colore(sq(t)), "wl": f"{cl[t]['w']}-{cl[t]['l']}",
                   "di": sq(di)["nome"] if di != t else "", "di_colore": L.colore(sq(di)), "nota": ""})
    s2 = str(int(stagione) + 1)[-2:]
    return {"anno": str(anno), "sotto": f"Fine regular season {stagione}-{s2} · estrazione verificabile con drand, nella fase draft",
            "quando": "classifica finale", "lottery": lot, "fisse": fx,
            "note": "Le percentuali sono la matrice delle odds del regolamento (righe: seed, colonne: pick; seed 1 = l'ultima in "
                    "classifica). Dalla 13ª alla 24ª le squadre dei playoff, in ordine inverso della classifica. Le discese per "
                    "le penalità si applicano all'estrazione: queste posizioni possono ancora cambiare. «Pick in mano a»: la "
                    "pick è stata scambiata, la sceglie quella squadra (protezioni a parte)."}


def immagine_odds(d: dict) -> bytes:
    import typst
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lottery_odds.typ")
    fonts = [x for x in ("/usr/share/fonts",) if os.path.isdir(x)]
    return typst.compile(tpl, root="/", format="png", ppi=170, font_paths=fonts,
                         sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})

"""
Watchlist (v7.8.0, Luca 13–14/11): ogni GM segue dei giocatori e riceve in privato quello che li riguarda.
Privata (nessuno sa chi segue chi), senza limite. Qui i dati, sul database del bot principale (shared/lettura.q):
li usano il bot principale (comandi, avvisi, report: handlers/watchlist.py) e /giocatori (filtro `watch`).

Tabelle (le crea il bot principale, database.migrate_db → crea):
- watchlist (user_id, giocatore_id, da): chi segue chi, da quando (gli avvisi valgono solo per quello che succede dopo);
- watch_soglie (user_id, sopra, assoluta): la grande prestazione, se diversa dal default (media +15 o 50 fantapunti);
- watch_avvisi (user_id, chiave, quando): gli avvisi già mandati, così non arrivano due volte.
"""
from shared import lettura as L

SOPRA = 15.0          # grande prestazione: almeno la fantamedia +15 …
ASSOLUTA = 50.0       # … o almeno 50 fantapunti (Luca, 14/11: default, ogni GM può cambiarli)


def crea(q) -> None:
    q("""CREATE TABLE IF NOT EXISTS watchlist (
            user_id      BIGINT NOT NULL,
            giocatore_id INT NOT NULL REFERENCES giocatori(id) ON DELETE CASCADE,
            da           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, giocatore_id))""")
    q("CREATE INDEX IF NOT EXISTS idx_watchlist_giocatore ON watchlist (giocatore_id)")
    q("""CREATE TABLE IF NOT EXISTS watch_soglie (
            user_id  BIGINT PRIMARY KEY,
            sopra    NUMERIC,
            assoluta NUMERIC)""")
    q("""CREATE TABLE IF NOT EXISTS watch_avvisi (
            user_id BIGINT NOT NULL,
            chiave  TEXT NOT NULL,
            quando  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, chiave))""")


def _q(sql, params=None, **k):
    try:
        return L.q(sql, params, **k)
    except Exception:                       # tabelle che non ci sono ancora (loucabot prima del bot principale)
        return None


def seguiti(uid: int) -> set[int]:
    return {r["giocatore_id"] for r in _q("SELECT giocatore_id FROM watchlist WHERE user_id = %s", (uid,), many=True) or []}


def segue(uid: int, gid: int) -> bool:
    return bool(_q("SELECT 1 AS x FROM watchlist WHERE user_id = %s AND giocatore_id = %s", (uid, gid), one=True))


def aggiungi(uid: int, gid: int) -> bool:
    """True se non lo seguiva già."""
    r = L.q("INSERT INTO watchlist (user_id, giocatore_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING giocatore_id",
            (uid, gid), one=True)
    return bool(r)


def togli(uid: int, gid: int) -> bool:
    r = L.q("DELETE FROM watchlist WHERE user_id = %s AND giocatore_id = %s RETURNING giocatore_id", (uid, gid), one=True)
    return bool(r)


def tutti() -> dict[int, dict[int, object]]:
    """{giocatore_id: {user_id: da}} di tutte le watchlist."""
    out: dict[int, dict[int, object]] = {}
    for r in _q("SELECT user_id, giocatore_id, da FROM watchlist", many=True) or []:
        out.setdefault(r["giocatore_id"], {})[r["user_id"]] = r["da"]
    return out


def utenti() -> list[int]:
    return [r["user_id"] for r in _q("SELECT DISTINCT user_id FROM watchlist ORDER BY user_id", many=True) or []]


def soglia(uid: int) -> tuple[float, float]:
    """(sopra la media, assoluta) della grande prestazione."""
    r = _q("SELECT sopra, assoluta FROM watch_soglie WHERE user_id = %s", (uid,), one=True) or {}
    return (float(r["sopra"]) if r.get("sopra") is not None else SOPRA,
            float(r["assoluta"]) if r.get("assoluta") is not None else ASSOLUTA)


def imposta_soglia(uid: int, sopra: float | None, assoluta: float | None) -> None:
    """None = il default."""
    L.q("""INSERT INTO watch_soglie (user_id, sopra, assoluta) VALUES (%s, %s, %s)
           ON CONFLICT (user_id) DO UPDATE SET sopra = EXCLUDED.sopra, assoluta = EXCLUDED.assoluta""", (uid, sopra, assoluta))


def grande(fp: float, media: float | None, s: tuple[float, float]) -> bool:
    return fp >= s[1] or (media is not None and fp >= media + s[0])


def nuovo_avviso(uid: int, chiave: str) -> bool:
    """Segna l'avviso: True solo la prima volta (gli avvisi non arrivano due volte)."""
    r = L.q("INSERT INTO watch_avvisi (user_id, chiave) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING chiave",
            (uid, chiave), one=True)
    return bool(r)


def immagine(d: dict) -> bytes:
    """Il report della notte (watchlist.typ, accanto a questo file)."""
    import json
    import os
    import typst
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.typ")
    fonts = [x for x in ("/usr/share/fonts",) if os.path.isdir(x)]
    return typst.compile(tpl, root="/", format="png", ppi=170, font_paths=fonts,
                         sys_inputs={"dati": json.dumps(d, ensure_ascii=False, default=str)})

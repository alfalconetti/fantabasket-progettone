"""
bref_scraper.py — Scraping giornaliero Basketball Reference
Aggiunge una riga per ogni giocatore che ha aumentato G rispetto all'ultima snapshot.
Gira ogni mattina alle 10 via scheduler del bot-main (run_giornaliero): stessa
richiesta per bref_stats, foglio BrefRaw, cambi squadra e giocatori nuovi.

Uso standalone:
    python3 bref_scraper.py              # scraping normale
    python3 bref_scraper.py --migrate    # inserisce dati finali stagione precedente
"""
import argparse
import logging
import os
import sys
import unicodedata
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

BREF_BASE = "https://www.basketball-reference.com/leagues/NBA_{anno}_per_game.html"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
}


# ── DB ────────────────────────────────────────────────────────────────────────

def _get_conn():
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        pw_file = os.environ.get("PG_PASSWORD_FILE", "/run/secrets/pg_password")
        if os.path.exists(pw_file):
            os.environ["PGPASSWORD"] = open(pw_file).read().strip()
        dsn = "postgresql://fantabasket@postgres:5432/fantabasket"
    return psycopg2.connect(dsn)


def _get_ultima_g(conn, stagione: str) -> dict[str, int]:
    """Restituisce {nome_bref: g} dell'ultima snapshot per ogni giocatore."""
    return {n: v[0] for n, v in _get_ultima(conn, stagione).items()}


def _get_ultima(conn, stagione: str) -> dict[str, tuple]:
    """{nome_bref: (g, team)} dell'ultima snapshot per ogni giocatore."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT ON (nome_bref) nome_bref, g, team
            FROM bref_stats
            WHERE stagione = %s
            ORDER BY nome_bref, timestamp DESC
        """, (stagione,))
        return {r["nome_bref"]: (r["g"], r["team"]) for r in cur.fetchall()}


def _inserisci_righe(conn, stagione: str, righe: list[dict]):
    if not righe:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO bref_stats
                (stagione, nome_bref, team, g, mp,
                 fgm, fga, fg_pct, fg3m, fg3a, fg3_pct,
                 ftm, fta, ft_pct,
                 orb, drb, trb, ast, stl, blk, tov, pf, pts)
            VALUES
                (%(stagione)s, %(nome_bref)s, %(team)s, %(g)s, %(mp)s,
                 %(fgm)s, %(fga)s, %(fg_pct)s, %(fg3m)s, %(fg3a)s, %(fg3_pct)s,
                 %(ftm)s, %(fta)s, %(ft_pct)s,
                 %(orb)s, %(drb)s, %(trb)s, %(ast)s, %(stl)s, %(blk)s,
                 %(tov)s, %(pf)s, %(pts)s)
        """, righe)
    conn.commit()
    return len(righe)


# ── scraping ──────────────────────────────────────────────────────────────────

def _normalizza(s: str) -> str:
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower().strip()


def _safe_float(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def scrape_bref(anno: str) -> list[dict]:
    """Scarica e pulisce la tabella per_game da basketball-reference."""
    return _righe_da_df(scrape_bref_df(anno))


def scrape_bref_df(anno: str):
    """Scarica la tabella per_game e la pulisce come il vecchio script del foglio
    (BrefRaw): niente header ripetuti, per gli scambiati solo la riga dei totali con
    l'ultima squadra reale al posto di 2TM/3TM. Tutte le colonne originali."""
    import pandas as pd
    url = BREF_BASE.format(anno=anno)
    logger.info("Scraping %s", url)
    dfs = pd.read_html(url, storage_options=HEADERS)
    df = dfs[0]

    # Rimuovi header ripetuti
    df = df[df["Rk"] != "Rk"].copy()

    # Gestione 2TM/3TM — mappa giocatore → team reale (ultima squadra)
    real_teams = df[~df["Team"].str.contains("TM", na=False)]
    team_mapping = dict(zip(real_teams["Player"], real_teams["Team"]))

    # Tieni solo la riga totale (first) per i giocatori scambiati
    df = df.drop_duplicates(subset=["Player"], keep="first")
    df["Team"] = df.apply(
        lambda x: team_mapping.get(x["Player"], x["Team"])
        if "TM" in str(x["Team"]) else x["Team"],
        axis=1
    )
    return df


def _righe_da_df(df) -> list[dict]:
    righe = []
    for _, row in df.iterrows():
        nome = str(row.get("Player", "")).strip()
        if not nome or nome.lower() in ("nan", "league average", "player"):
            continue
        righe.append({
            "nome_bref": nome,
            "team":      str(row.get("Team", "")).strip() or None,
            "g":         _safe_int(row.get("G")),
            "mp":        _safe_float(row.get("MP")),
            "fgm":       _safe_float(row.get("FG")),
            "fga":       _safe_float(row.get("FGA")),
            "fg_pct":    _safe_float(row.get("FG%")),
            "fg3m":      _safe_float(row.get("3P")),
            "fg3a":      _safe_float(row.get("3PA")),
            "fg3_pct":   _safe_float(row.get("3P%")),
            "ftm":       _safe_float(row.get("FT")),
            "fta":       _safe_float(row.get("FTA")),
            "ft_pct":    _safe_float(row.get("FT%")),
            "orb":       _safe_float(row.get("ORB")),
            "drb":       _safe_float(row.get("DRB")),
            "trb":       _safe_float(row.get("TRB")),
            "ast":       _safe_float(row.get("AST")),
            "stl":       _safe_float(row.get("STL")),
            "blk":       _safe_float(row.get("BLK")),
            "tov":       _safe_float(row.get("TOV")),
            "pf":        _safe_float(row.get("PF")),
            "pts":       _safe_float(row.get("PTS")),
        })
    return righe


# ── logica principale ─────────────────────────────────────────────────────────

def run_scraper(stagione: str, migrate: bool = False):
    """
    Scarica i dati e inserisce le righe nuove.
    Se migrate=True, inserisce tutti i giocatori indipendentemente da G.
    """
    conn = _get_conn()
    try:
        dati = scrape_bref(stagione)
        if not dati:
            logger.warning("Nessun dato ricevuto da bref")
            return 0

        if migrate:
            # Migrazione: inserisce tutto come snapshot finale
            righe = [{**r, "stagione": stagione} for r in dati if r["g"]]
            n = _inserisci_righe(conn, stagione, righe)
            logger.info("Migrazione: inserite %d righe per stagione %s", n, stagione)
            return n

        # Normale: inserisce solo chi ha G aumentato
        ultima_g = _get_ultima_g(conn, stagione)
        righe = []
        for r in dati:
            g_nuovo = r.get("g") or 0
            g_vecchio = ultima_g.get(r["nome_bref"], 0)
            if g_nuovo > g_vecchio:
                righe.append({**r, "stagione": stagione})

        n = _inserisci_righe(conn, stagione, righe)
        logger.info("Scraper: inserite %d righe (di %d giocatori)", n, len(dati))
        return n
    finally:
        conn.close()


def run_giornaliero(stagione: str) -> dict:
    """Job giornaliero (bot main): una sola richiesta a bref, poi
    - append in bref_stats per chi ha giocato (G aumentate dall'ultima rilevazione);
    - cambi squadra (squadra della riga nuova diversa dalla precedente);
    - giocatori di bref che non sono in anagrafica (per la proposta al dev);
    - CSV della tabella per il foglio BrefRaw.
    """
    df = scrape_bref_df(stagione)
    dati = _righe_da_df(df)
    out = {"inseriti": 0, "cambi": [], "nuovi": [], "csv": df.to_csv(index=False), "giocatori": len(dati)}
    if not dati:
        return out
    conn = _get_conn()
    try:
        ultima = _get_ultima(conn, stagione)
        righe = []
        for r in dati:
            g_vecchio, team_vecchio = ultima.get(r["nome_bref"], (0, None))
            if (r.get("g") or 0) > (g_vecchio or 0):
                righe.append({**r, "stagione": stagione})
                if team_vecchio and r.get("team") and r["team"] != team_vecchio:
                    out["cambi"].append((r["nome_bref"], team_vecchio, r["team"]))
        out["inseriti"] = _inserisci_righe(conn, stagione, righe)
        with conn.cursor() as cur:
            cur.execute("SELECT nome_bref FROM giocatori")
            noti = {x[0] for x in cur.fetchall()}
        out["nuovi"] = [(r["nome_bref"], r.get("team"), r.get("g")) for r in dati if r["nome_bref"] not in noti]
    finally:
        conn.close()
    return out


# ── entry point standalone ────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrate", action="store_true",
                        help="Inserisce tutti i dati come snapshot finale (migrazione)")
    parser.add_argument("--stagione", type=str, default=None,
                        help="Stagione (es. 2026). Default: stagione_corrente da globals.json")
    args = parser.parse_args()

    if args.stagione:
        stagione = args.stagione
    else:
        import json
        globals_path = os.environ.get("GLOBALS_PATH", "/config/globals.json")
        g = json.load(open(globals_path))
        stagione_corrente = int(g.get("stagione_corrente", 2026))
        # bref usa l'anno di fine stagione
        stagione = str(stagione_corrente + 1) if not args.migrate else str(stagione_corrente)

    n = run_scraper(stagione, migrate=args.migrate)
    print(f"Inserite {n} righe.")

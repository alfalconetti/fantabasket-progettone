"""
FANTABASKET MAIN DB — Script di migrazione definitivo

Prerequisiti:
    pip install psycopg2-binary --break-system-packages

CSV attesi nella stessa cartella dello script:
    - giocatori.csv      : colonne vedi README
    - pick.csv           : proprietario_orig, proprietario_att, anno, round, protezioni
    - impatto_taglio.csv : team_id, nome_giocatore, stagione_taglio, stagione, importo

Uso:
    PG_PASS=$(cat secrets/pg_password.txt)
    python3 fantabasket_migrazione.py \\
        --db "postgresql://fantabasket:${PG_PASS}@localhost:5432/fantabasket" \\
        --stagione 2025 \\
        --giocatori config/giocatori.csv \\
        --pick config/pick.csv
    # aggiungere --impatto config/impatto_taglio.csv se esiste
"""

import argparse
import csv
import unicodedata
from datetime import datetime, timezone, date

import psycopg2
import psycopg2.extras


# ── helpers ───────────────────────────────────────────────────────────────────

def normalizza(s: str) -> str:
    return unicodedata.normalize("NFD", (s or "")).encode("ascii", "ignore").decode().lower().strip()


def val(r: dict, campo: str) -> str:
    """Legge un campo trattando 'null', 'NULL', '', None come stringa vuota."""
    v = (r.get(campo) or "").strip()
    return "" if v.lower() == "null" else v


def converti_data(s: str):
    """Converte M/D/YYYY, M/D/YY o YYYY-MM-DD → YYYY-MM-DD. Restituisce None se non parsabile."""
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def leggi_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


# ── migrazione ────────────────────────────────────────────────────────────────

def migra(conn, stagione: str, path_giocatori: str, path_pick: str, path_impatto: str | None):
    cur = conn.cursor()
    ts  = datetime.now(timezone.utc)

    # ── 1. Giocatori e contratti ────────────────────────────────────────────
    print("=== 1. Giocatori e contratti ===")
    rows = leggi_csv(path_giocatori)
    giocatore_id_map: dict[str, int] = {}
    firmati = diritti_count = fa_count = warn_count = 0

    for r in rows:
        nome_common = val(r, "nome_common")
        nome_bref   = val(r, "nome_bref") or nome_common
        nome_yahoo  = val(r, "nome_yahoo") or None
        nome_norm   = normalizza(nome_bref)
        data_nasc   = converti_data(val(r, "data_nascita"))

        if not nome_common:
            continue

        cur.execute("""
            INSERT INTO giocatori (nome_bref, nome_yahoo, nome_common, nome_norm, data_nascita)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id
        """, (nome_bref, nome_yahoo, nome_common, nome_norm, data_nasc))

        row = cur.fetchone()
        if row:
            gid = row[0]
        else:
            cur.execute("SELECT id FROM giocatori WHERE nome_norm = %s", (nome_norm,))
            found = cur.fetchone()
            if not found:
                print(f"  ⚠️  Impossibile trovare/inserire: {nome_common}")
                warn_count += 1
                continue
            gid = found[0]

        giocatore_id_map[nome_norm] = gid

        team_id = val(r, "team_id")

        # FA: nessun contratto né transazione
        if not team_id:
            fa_count += 1
            continue

        importo_raw = val(r, "importo")

        # Diritti 2nd pick: team_id presente ma importo vuoto + è_rookie=true
        if not importo_raw:
            if val(r, "è_rookie").lower() == "true":
                pick_s = val(r, "pick_numero")
                anno_s = val(r, "anno_draft")
                if not pick_s or not anno_s:
                    print(f"  ⚠️  {nome_common}: diritti senza pick/anno — skip")
                    warn_count += 1
                    continue
                pick_num   = int(pick_s)
                round_pick = 1 if pick_num <= 24 else 2
                try:
                    scadenza = date(int(anno_s) + 2, 6, 20).isoformat()
                except Exception:
                    scadenza = None
                cur.execute("""
                    INSERT INTO rookie
                        (giocatore_id, team_id, round, pick_numero, anno_draft,
                         scadenza_diritti, firmato, diritti_scaduti)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE, FALSE)
                """, (gid, team_id, round_pick, pick_num, anno_s, scadenza))
                diritti_count += 1
                print(f"  🔑 {nome_common} → diritti {team_id} (#{pick_num} {anno_s})")
            else:
                fa_count += 1
            continue

        # Contratto normale
        try:
            importo      = int(importo_raw)
            anni_residui = int(val(r, "anni_residui"))
        except ValueError:
            print(f"  ⚠️  {nome_common}: importo/anni non validi — skip")
            warn_count += 1
            continue

        tipo           = val(r, "tipo_contratto") or "normale"
        stagione_firma = val(r, "stagione_firma") or stagione
        e_rookie       = val(r, "è_rookie").lower() == "true"

        cur.execute("""
            INSERT INTO contratti
                (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id
        """, (gid, team_id, importo, anni_residui, stagione_firma, tipo))
        contratto_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO transazioni
                (timestamp, tipo, giocatore_id, team_id_da, team_id_a,
                 stagione, contratto_id, rookie_scale, note)
            VALUES (%s, 'signed', %s, NULL, %s, %s, %s, %s, %s)
        """, (ts, gid, team_id, stagione, contratto_id, e_rookie,
              "migrazione iniziale"))

        # Record rookie se firmato su scala
        if e_rookie:
            pick_s = val(r, "pick_numero")
            anno_s = val(r, "anno_draft")
            anni_s = val(r, "anni_scala")
            if pick_s and anno_s:
                pick_num   = int(pick_s)
                round_pick = 1 if pick_num <= 24 else 2
                anni_scala = int(anni_s) if anni_s else 0
                cur.execute("""
                    INSERT INTO rookie
                        (giocatore_id, team_id, round, pick_numero, anno_draft,
                         anno_firma, anni_scala, firmato, diritti_scaduti)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, FALSE)
                    ON CONFLICT DO NOTHING
                """, (gid, team_id, round_pick, pick_num, anno_s,
                      stagione_firma, anni_scala))

        firmati += 1

    conn.commit()
    print(f"\n  Firmati: {firmati} | Diritti: {diritti_count} | FA: {fa_count} | Avvisi: {warn_count}")

    # ── 2. Pick ────────────────────────────────────────────────────────────
    print("\n=== 2. Pick ===")
    pick_rows = leggi_csv(path_pick)
    pick_count = 0
    for r in pick_rows:
        orig  = val(r, "proprietario_orig")
        att   = val(r, "proprietario_att")
        anno  = val(r, "anno")
        rnd   = val(r, "round")
        prot  = val(r, "protezioni") or None
        if not (orig and att and anno and rnd):
            continue
        cur.execute("""
            INSERT INTO pick (proprietario_orig, proprietario_att, anno, round, protezioni, scattata)
            VALUES (%s, %s, %s, %s, %s, FALSE)
        """, (orig, att, anno, int(rnd), prot))
        pick_count += 1
    conn.commit()
    print(f"  Pick inserite: {pick_count}")

    # ── 3. Impatto taglio ──────────────────────────────────────────────────
    if path_impatto:
        print("\n=== 3. Impatto taglio ===")
        try:
            imp_rows = leggi_csv(path_impatto)
            imp_count = 0
            for r in imp_rows:
                team_id    = val(r, "team_id")
                nome_g     = val(r, "nome_giocatore")
                st_taglio  = val(r, "stagione_taglio")
                stagione_r = val(r, "stagione")
                importo_r  = val(r, "importo")
                if not all([team_id, nome_g, st_taglio, stagione_r, importo_r]):
                    continue
                gid = giocatore_id_map.get(normalizza(nome_g))
                if not gid:
                    cur.execute("SELECT id FROM giocatori WHERE nome_norm = %s",
                                (normalizza(nome_g),))
                    found = cur.fetchone()
                    if not found:
                        print(f"  ⚠️  {nome_g} non trovato nel DB — skip")
                        continue
                    gid = found[0]
                cur.execute("""
                    INSERT INTO impatto_taglio
                        (team_id, giocatore_id, stagione_taglio, stagione, importo)
                    VALUES (%s, %s, %s, %s, %s)
                """, (team_id, gid, st_taglio, stagione_r, int(importo_r)))
                imp_count += 1
                print(f"  ✅ {nome_g} → {team_id} {stagione_r}: {importo_r}M")
            conn.commit()
            print(f"  Rate impatto taglio inserite: {imp_count}")
        except FileNotFoundError:
            print("  ℹ️  impatto_taglio.csv non trovato — skip")

    print("\n✅ Migrazione completata.")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",       required=True)
    parser.add_argument("--stagione", required=True)
    parser.add_argument("--giocatori", default="config/giocatori.csv")
    parser.add_argument("--pick",      default="config/pick.csv")
    parser.add_argument("--impatto",   default=None)
    args = parser.parse_args()

    conn = psycopg2.connect(args.db)
    try:
        migra(conn, args.stagione, args.giocatori, args.pick, args.impatto)
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Errore: {e}")
        raise
    finally:
        conn.close()

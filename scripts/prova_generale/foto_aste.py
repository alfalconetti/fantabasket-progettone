"""Foto del bot aste sulla COPIA: python3 foto_aste.py out.json (cwd = fantabasket-aste-beta)."""
import sys, json
sys.path.insert(0, "..")
import pg_client as pg, database as db, teams as tm, utils, settings
from handlers import offerte
pg.init_pg(); db.init_db()
st = utils.get_stagione_corrente()
out = {}
for t in tm.get_all_teams():
    tid = t["id"]
    out[tid] = {"roster_count": pg.get_roster_count(tid, st), "roster_count_senza_stagione": pg.get_roster_count(tid),
                "slot_totale": pg.get_slot_totale(tid, st), "cap_contratti": pg.get_cap_contratti(tid, st),
                "cap_totale": pg.get_cap_totale(tid, st), "impatto": pg.get_impatto_taglio(tid, st),
                "cap_slot_display": list(utils.cap_slot_display(t, st)), "cap_libero_offerte": offerte._cap_libero(tid),
                "slot_ok": tm.check_slot_virtuale(tid, 0)}
nomi = [r["nome_common"] for r in pg.q("""SELECT DISTINCT g.nome_common FROM transazioni x JOIN giocatori g ON g.id=x.giocatore_id
                                          WHERE x.tipo IN ('cut','decadimento') OR x.team_id_a IS NULL""", many=True) or []]
nomi += [r["nome"] for r in pg.get_fa_rows_pg()[:40]]
out["_lega"] = {"30_giorni": {n: sorted(pg.squadre_regola_30_giorni(n)) for n in sorted(set(nomi))},
                "cam_thomas": {f"{n}|{t['id']}": pg.minimo_cam_thomas(n, t["id"]) for n in sorted(set(nomi)) for t in tm.get_all_teams()},
                "fa": sorted(r["nome"] for r in pg.get_fa_rows_pg())}
out["_lega"]["cam_thomas"] = {k: v for k, v in out["_lega"]["cam_thomas"].items() if v is not None}
json.dump(out, open(sys.argv[1], "w"), indent=1, ensure_ascii=False, default=str, sort_keys=True)
print("foto aste:", len(out) - 1, "squadre,", len(out["_lega"]["fa"]), "FA")

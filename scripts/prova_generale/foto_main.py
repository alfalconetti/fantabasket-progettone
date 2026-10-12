"""Foto del bot principale sulla COPIA: python3 foto_main.py out.json (cwd = fantabasket-main)."""
import sys, json, datetime as dt
sys.path.insert(0, "..")
import database as db, settings, teams as tm
from handlers import team_diff as td
from validators import trade as vt
from shared import ruoli_core as core
db.init_db()
Z = dt.timezone.utc
DATE = [dt.datetime(2026,7,26,12,tzinfo=Z), dt.datetime(2026,8,15,tzinfo=Z), dt.datetime(2026,9,1,tzinfo=Z),
        dt.datetime(2026,9,20,tzinfo=Z), dt.datetime(2026,9,30,13,50,tzinfo=Z), dt.datetime(2026,10,1,tzinfo=Z),
        dt.datetime(2026,10,5,7,45,tzinfo=Z), dt.datetime(2026,10,9,12,tzinfo=Z), dt.datetime(2026,10,11,23,tzinfo=Z)]
st = settings.stagione_corrente()
def pulisci(x):
    if isinstance(x, dict): return {str(k): pulisci(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple, set)):
        l = [pulisci(v) for v in x]
        try: return sorted(l, key=lambda v: json.dumps(v, sort_keys=True, default=str))
        except Exception: return l
    if isinstance(x, (dt.date, dt.datetime)): return x.isoformat()
    if hasattr(x, "__float__") and not isinstance(x, (int, float, bool)): return float(x)
    return x
out = {}
for t in tm.get_all_teams():
    tid = t["id"]; s = {}
    s["roster"] = [{k: r[k] for k in ("giocatore_id","nome_common","importo","importo_originale","anni_originali","stagione_firma","tipo_contratto","anni_scala","ha_dpe")} for r in db.get_roster_team(tid)]
    s["cap_occupato"] = db.cap_occupato_team(tid, st)
    s["pick"] = [p["id"] for p in db.get_pick_team(tid)]
    s["diritti"] = [r["giocatore_id"] for r in db.get_diritti_2nd_team(tid)]
    s["tagli_gratuiti"] = db.get_tagli_gratuiti_usati(tid, st)
    s["stepien"] = sorted(vt.anni_coperti_stepien(tid))
    s["a_data"] = {d.isoformat(): {"contratti": td._snapshot_contratti(tid, d),
                                   "pick": sorted(td._snapshot_pick(tid, d)),
                                   "diritti": sorted(td._snapshot_diritti(tid, d))} for d in DATE}
    s["riacquisto"] = {r["giocatore_id"]: core.ruolo_riacquisto(db._q, r["giocatore_id"], tid) for r in db.get_roster_team(tid)}
    out[tid] = s
out["_lega"] = {"fantamedia_stagione": {d.isoformat(): db.stagione_fantamedia(d) for d in DATE},
                "cam_thomas": {f"{r['giocatore_id']}|{r['team_id_da']}": db.minimo_cam_thomas(r["giocatore_id"], r["team_id_da"])
                               for r in db._q("SELECT DISTINCT giocatore_id, team_id_da FROM transazioni WHERE tipo='decadimento'", many=True) or []}}
from handlers import spalmature
out["_lega"]["report_spalmature"] = spalmature.testi_report()
json.dump(pulisci(out), open(sys.argv[1], "w"), indent=1, ensure_ascii=False, default=str)
print("foto main:", len(out) - 1, "squadre")

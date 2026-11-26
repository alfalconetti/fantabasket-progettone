import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.35.4: il registro (event sourcing) ricostruisce lo stato a ogni momento. Una sequenza con tutte le operazioni
che scrivono movimenti (firma, trade con giocatori, pick e diritti, taglio e annullamento, DPE, 10-day, decadimento,
annullamento di firma e di trade, cambio di stagione con rookie scale e Doncic, rinnovo e annullamento, RFA, scadenza
degli x0); dopo ognuna si fotografa lo stato di oggi (roster, contratti, pick, diritti, cap). Poi, alla fine, ogni
fotografia dev'essere ricostruita uguale dal registro a quel momento (get_roster_team_at, get_pick_at, get_diritti_at,
cap_at); quelle cancellate da un annullamento tornano come se l'operazione non ci fosse stata."""
import asyncio, time, types
from datetime import datetime, timezone
import database as db
import settings
db.init_db(); db.migrate_db()
db._q("DELETE FROM inizi_stagione")
db._q("TRUNCATE giocatori, contratti, pick, rookie, transazioni, dpe, impatto_taglio, rfa_dichiarati, messaggi_fissi, "
      "rinnovi_normali, trade, cambi_ruolo, inizi_stagione RESTART IDENTITY CASCADE")
db._q("DELETE FROM bref_stats")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
TEAMS = ["team01", "team02", "team03", "team04"]


def fase(f, stagione=None):
    g = settings.load_globals(); g["fase"] = f
    if stagione:
        g["stagione_corrente"] = str(stagione)
    settings.save_globals(g)


def gioc(n, team=None, imp=None, anni=None, sf=None, tipo="normale", pick=None, anno_firma=None):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    if pick:
        db._q("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft,anno_firma,firmato) "
              "VALUES (%s,%s,1,%s,%s,%s,TRUE)", (gid, team, pick, str(anno_firma), str(anno_firma)))
    if team:
        firma(gid, team, imp, anni, sf, tipo)
    return gid


def firma(gid, team, imp, anni, sf, tipo="normale"):
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                 "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (gid, team, imp, anni, str(sf), tipo))
    return db._qval("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,%s,%s) "
                    "RETURNING id", (gid, team, str(sf), c))


def fm(n, stagione_lega, valore):
    db._q("""INSERT INTO bref_stats (stagione,nome_bref,team,g,fga,fgm,ftm,fta,fg3m,pts,orb,drb,ast,stl,blk,tov)
             VALUES (%s,%s,'X',50,0,0,0,0,0,%s,0,0,0,0,0,0)""", (str(stagione_lega + 1), n, valore * 2))


# ── fotografie ─────────────────────────────────────────────────────────────────

def stato_oggi() -> dict:
    s = settings.stagione_corrente()
    out = {"roster": {}, "pick": {}, "diritti": {}, "cap": {}}
    for t in TEAMS:
        out["roster"][t] = {r["giocatore_id"]: (r["contratto_id"], int(r["anni_residui"]), bool(r.get("rfa")))
                            for r in db.get_roster_team(t)}
        out["cap"][t] = db.cap_occupato_team(t, s)
    out["pick"] = {r["id"]: r["proprietario_att"] for r in db._q("SELECT id, proprietario_att FROM pick", many=True) or []}
    out["diritti"] = {r["giocatore_id"]: r["team_id"] for r in db._q(
        "SELECT giocatore_id, team_id FROM rookie WHERE round = 2 AND NOT firmato AND NOT diritti_scaduti", many=True) or []}
    return out


def stato_al(iso: str) -> dict:
    out = {"roster": {}, "pick": {}, "diritti": {}, "cap": {}}
    for t in TEAMS:
        out["roster"][t] = {r["giocatore_id"]: (r["contratto_id"], int(r["anni_residui"]), bool(r.get("rfa")))
                            for r in db.get_roster_team_at(t, iso)}
        out["cap"][t] = db.cap_at(t, iso)
        out["pick"].update({r["id"]: t for r in db.get_pick_at(t, iso)})
        out["diritti"].update({r["giocatore_id"]: t for r in db.get_diritti_at(t, iso)})
    return out


foto = []          # (descrizione, iso, stato)


def passo(descr):
    time.sleep(0.02)
    iso = datetime.now(timezone.utc).isoformat()
    st = stato_oggi()
    foto.append([descr, iso, st])
    al = stato_al(iso)
    diff = [k for k in st if st[k] != al[k]]
    ok(not diff, f"{descr}: il registro ricostruisce lo stato di adesso" + (f" — diverso: {diff} {[(st[k], al[k]) for k in diff]}" if diff else ""))
    coer = db.controlli_coerenza()
    ok(not [p for p in coer if "storico" not in p], f"{descr}: controllo di coerenza pulito {coer}")
    time.sleep(0.02)


def annullata(i_op, gid=None, pick_id=None):
    """L'operazione della foto i_op è stata annullata: nelle foto da i_op in poi il giocatore (o la pick) torna com'era
    nella foto prima, e il cap delle squadre coinvolte pure."""
    prima = foto[i_op - 1][2]
    for f in foto[i_op:]:
        st = f[2]
        if gid is not None:
            for t in TEAMS:
                st["roster"][t].pop(gid, None)
                if gid in prima["roster"][t]:
                    st["roster"][t][gid] = prima["roster"][t][gid]
        if pick_id is not None:
            st["pick"][pick_id] = prima["pick"][pick_id]
        for t in TEAMS:
            st["cap"][t] = None          # ricontrollato a parte: dipende da tutto il resto


class Bot:
    async def send_message(self, *a, **k): return types.SimpleNamespace(message_id=1)
    async def edit_message_text(self, *a, **k): pass


import teams as tm
import handlers.stagione as S
import handlers.rinnovi as R
import handlers.trade_esegui as TE
import handlers.dieci_giorni as DG
from handlers.tagli import esegui_taglio
from handlers.decadimento import applica_decadimento


def trade(items, stagione="2026"):
    squadre = sorted({x for it in items for x in (it[1], it[2])})
    t = db.crea_trade_bozza(squadre[0], len(squadre), stagione)
    for i, sq in enumerate(squadre, 1):
        db.aggiungi_squadra_trade(t, sq, i)
    for tipo, da, a, chiave in items:
        if tipo == "pick":
            db.aggiungi_item_trade(t, "pick", da, a, pick_id=chiave)
        else:
            db.aggiungi_item_trade(t, tipo, da, a, giocatore_id=chiave)
    db._q("UPDATE trade SET stato='in_approvazione' WHERE id=%s", (t,))
    ref = f"TRADE-{stagione}-{t:03d}"
    TE._scrivi_trade(t, ref, "adm")
    return t


# ══ stagione 2026 (offseason-fa: mercato e trade aperti, niente minimi di roster) ══
fase("offseason-fa", 2026)
a = gioc("Alfa Uno", "team01", 20, 3, 2026)
b = gioc("Beta Uno", "team01", 8, 2, 2026)
c = gioc("Gamma Due", "team02", 12, 2, 2026); fm("Gamma Due", 2026, 21)
d = gioc("Delta Due", "team02", 6, 1, 2026)
r4 = gioc("Rookie Quarto", "team03", 8, 1, 2026, "rookie", pick=6, anno_firma=2023)
fm("Rookie Quarto", 2025, 22); fm("Rookie Quarto", 2026, 24.3)
e = gioc("Epsilon Tre", "team03", 10, 3, 2026)
dir2 = gioc("Diritti Secondo"); db._q("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft) VALUES (%s,'team04',2,40,'2026')", (dir2,))
for t in TEAMS:
    for rnd in (1, 2):
        db._q("INSERT INTO pick (proprietario_orig, proprietario_att, anno, round) VALUES (%s,%s,'2028',%s)", (t, t, rnd))
db.crea_storico_pick_diritti(forza=True)
p_t1 = db._qval("SELECT id FROM pick WHERE proprietario_orig='team01' AND round=1")
passo("partenza")

trade([("giocatore", "team01", "team02", b), ("pick", "team01", "team02", p_t1), ("diritti", "team04", "team01", dir2),
       ("giocatore", "team02", "team01", d)])
passo("trade a due con giocatori, pick e diritti")

taglio_a = esegui_taglio(tm.get_team_by_id("team01"), a)
passo("taglio 20x3")
tid = db._qval("SELECT max(id) FROM movimenti_giocatori WHERE tipo = 'cut' AND giocatore_id = %s", (a,))
db.annulla_taglio(tid)
annullata(len(foto) - 1, gid=a)
passo("taglio annullato")
esegui_taglio(tm.get_team_by_id("team03"), e)
passo("taglio 10x3 (resta)")

db.inserisci_dpe(c, "team02", "2026", 12, 6, True, "prova")
passo("DPE")

dd = gioc("Dieci Giorni")
DG.registra("team04", dd, "G", "prova")
passo("10-day")
DG.chiudi(db.get_contratto_attivo(dd)["id"], "Fine del 10-day")
passo("10-day chiuso")

z = gioc("Zeta Firmato")
ftid = firma(z, "team04", 4, 2, 2026)
db._q("UPDATE transazioni SET note = 'firma registrata' WHERE id = %s", (ftid,))      # come /registra_firma
passo("firma")
db.annulla_firma(ftid)
annullata(len(foto) - 1, gid=z)
passo("firma annullata")

ret = gioc("Ritirato", "team04", 5, 2, 2026)
passo("firma del futuro ritirato")
asyncio.run(applica_decadimento(Bot(), "team04", ret, "ritiro", "prova"))
passo("decadimento (ritiro)")

t_inv = trade([("giocatore", "team03", "team04", r4)])
passo("trade da annullare")
TE._scrivi_trade(t_inv, db._qval("SELECT trade_ref FROM trade WHERE id=%s", (t_inv,)), None, inverti=True)
passo("trade annullata (movimento inverso, non cancellato)")

# ══ stagione 2027 ══
fase("offseason-rinnovi", 2027)
db.segna_inizio_stagione(2027)                 # come fa il pannello entrando nei rinnovi
S.applica_stagione(2027)
S.crea_pick_anno(2033)
passo("cambio di stagione: rookie scale, Doncic, pick nuove")
rin = R.esegui("team02", c, "quarto", 2, "prova")
passo("rinnovo")
R.annulla("team02", rin["id"])
annullata(len(foto) - 1, gid=c)
passo("rinnovo annullato")
R.esegui("team02", c, "mezzo", 3, "prova")
passo("rinnovo da ½")
S.dichiara_rfa("team01", d, "prova")
passo("RFA dichiarato")
fase("offseason-fa", 2027)
S.scadenza_x0(2027)
passo("inizio FA: x0 scaduti")

# la stagione di una data: dagli inizi registrati, non dal 1° luglio
from datetime import timedelta
_ini = db._q("SELECT inizio FROM inizi_stagione WHERE stagione = '2027'", one=True)["inizio"]
ok(db.stagione_al(_ini - timedelta(minutes=1)) == 2026 and db.stagione_al(_ini + timedelta(minutes=1)) == 2027
   and db.stagione_al(datetime(2025, 9, 1, tzinfo=timezone.utc)) == 2025,
   "stagione di una data: prima dell'inizio dei rinnovi la vecchia, dopo la nuova, senza inizi la regola di luglio")
db.segna_inizio_stagione(2027)
ok(db._q("SELECT inizio FROM inizi_stagione WHERE stagione = '2027'", one=True)["inizio"] == _ini,
   "tornare ai rinnovi non sposta l'inizio della stagione")

# ── alla fine: ogni fotografia dal registro ──────────────────────────────────────
sbagliate = []
for descr, iso, st in foto:
    al = stato_al(iso)
    for k in ("roster", "pick", "diritti"):
        if st[k] != al[k]:
            sbagliate.append((descr, k, st[k], al[k]))
    for t in TEAMS:
        if st["cap"][t] is not None and st["cap"][t] != al["cap"][t]:
            sbagliate.append((descr, "cap", t, st["cap"][t], al["cap"][t]))
ok(not sbagliate, f"tutte le {len(foto)} fotografie ricostruite dal registro, a fine giro {sbagliate[:3]}")
fase("offseason-fa", 2026)
db._q("DELETE FROM inizi_stagione")   # v7.35.4: gli inizi di stagione di prova non restano per le altre prove

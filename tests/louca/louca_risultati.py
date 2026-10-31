import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""loucabot v13: calcolo definitivo di una giornata dai quintetti congelati e dalle panchine di
IPanchinari, foglio "Calcolo GN" (le formule devono dare gli stessi numeri del bot: il foglio si
ricalcola con LibreOffice e si confronta), proposta, convalida, risultati sul Calendario."""
import asyncio, csv, importlib.util, io, json, os, shutil, subprocess, tempfile, types
from datetime import date, datetime, timedelta, timezone
import db, config, calcolo, risultati as R

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
spec = importlib.util.spec_from_file_location("ipadb", os.path.join(ROOT, "fantabasket-ipanchinari", "db.py"))

ipadb = importlib.util.module_from_spec(spec); spec.loader.exec_module(ipadb)
db.init_db(); ipadb.init_db()
db.q("TRUNCATE nba_tabellini, nba_infortuni, nba_atleti, lega_giornate, lega_partite, nba_partite, lega_risultati, "
     "lega_calcoli, lega_calcoli_storico, lega_status_validi")
db.q("TRUNCATE ipa_formazioni, ipa_panchine, ipa_stato_giornata")
import congelamento as _CGm; _CGm.migra(); db.q("TRUNCATE lega_controlli_notte")
S = config.stagione()
N = 7
DAL, AL = date(2026, 11, 10), date(2026, 11, 12)

# giocatori dell'anagrafica con id ESPN (r1…r40); i ruoli della panchina sono quelli congelati
db.q("DELETE FROM giocatori WHERE espn_id LIKE 'r%%' AND nome_common LIKE 'Prova %%'")   # avanzi di una prova interrotta
gid = {}
for i in range(1, 41):
    gid[i] = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id",
                  (f"Prova {i}", f"Prova {i}", f"prova {i}", f"r{i}"), one=True)["id"]

def partita(pid, giorno, casa, trasf, stato="STATUS_FINAL"):
    db.salva_partite_nba([{"espn_id": pid, "stagione": S, "tipo": 2, "data_et": giorno, "casa": casa, "trasferta": trasf,
                           "inizio": datetime(giorno.year, giorno.month, giorno.day, 23, 0, tzinfo=timezone.utc), "stato": stato}])

def tab(pid, righe):
    db.salva_tabellino(pid, [{"partita": pid, "atleta": a, "nome": a, "squadra": sq, "titolare": True, "giocato": minuti is not None,
                              "minuti": minuti or 0, "pts": 0, "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0, "oreb": 0,
                              "dreb": 0, "ast": 0, "stl": 0, "blk": 0, "tov": 0, "pf": 0, "fp": fp or 0} for a, sq, fp, minuti in righe])

# stagione prima della giornata (per le medie)
partita("v1", date(2026, 11, 1), "IND", "NOP"); tab("v1", [("r5", "IND", 40, 30), ("r15", "NOP", 20, 30), ("r30", "NOP", 18, 30)])
partita("v2", date(2026, 11, 3), "IND", "MIA"); tab("v2", [("r5", "IND", 36, 30), ("r16", "IND", 22, 30)])
# la giornata: tre notti; IND e NOP non giocano (a media)
partita("g1", DAL, "NYK", "BOS"); partita("g2", DAL + timedelta(days=1), "NYK", "PHX"); partita("g3", AL, "BOS", "PHX")
partita("g4", DAL, "MEM", "UTA")
partita("g5", AL, "NYK", "MIA")   # r1: tre notti, 30 20 21 → media 23,67 → all'ottavo 23,625
tab("g1", [("r1", "NYK", 30, 30), ("r2", "NYK", 25, 30), ("r3", "BOS", 18, 30), ("r11", "NYK", 24, 30), ("r12", "BOS", 21, 30),
           ("r13", "BOS", 0, 22), ("r6", "NYK", 12, 20), ("r21", "NYK", 27, 30), ("r22", "BOS", 33, 30)])
tab("g2", [("r1", "NYK", 20, 30), ("r4", "PHX", 35, 30), ("r11", "NYK", 14, 30), ("r14", "PHX", 28, 30),
           ("r6", "NYK", 0, 0), ("r21", "NYK", 31, 30), ("r24", "PHX", 15, 30), ("r7", "PHX", 9, 15)])
tab("g3", [("r3", "BOS", 22, 30), ("r4", "PHX", 15, 30), ("r12", "BOS", 19, 30), ("r14", "PHX", 30, 30), ("r13", "BOS", 10, 25),
           ("r22", "BOS", 29, 30), ("r24", "PHX", 17, 30), ("r8", "BOS", 6, 12)])
tab("g5", [("r1", "NYK", 21, 30)])
tab("g4", [("r9", "UTA", 11, 25), ("r10", "MEM", None, None), ("r23", "UTA", 26, 30), ("r25", "MEM", 12, 30), ("r26", "UTA", 8, 18)])
# snapshot: r10 (MEM, gioca) Out tutta la giornata → FADD; r5 (IND, a media) Out tutta la giornata → FADD; r16 sano
for d in (DAL, DAL + timedelta(days=1), AL):
    db.q("INSERT INTO nba_infortuni (giorno, atleta, nome, stato, preso) VALUES (%s, 'r10', 'r10', 'Out', %s), (%s, 'r5', 'r5', 'Out', %s)",
         (d, datetime(d.year, d.month, d.day, 18, 0, tzinfo=timezone.utc), d, datetime(d.year, d.month, d.day, 18, 0, tzinfo=timezone.utc)))

db.q("INSERT INTO lega_giornate (stagione, numero, dal, al) VALUES (%s, %s, %s, %s)", (S, N, DAL, AL))
db.q("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES (%s, %s, 'team01', 'team02'), (%s, %s, 'team03', 'team04')",
     (S, N, S, N))

def schiera(team, q, panca):
    for ruolo, i in zip(R.RUOLI, q):
        db.q("INSERT INTO ipa_formazioni (stagione, giornata, team_id, ruolo, giocatore_id) VALUES (%s, %s, %s, %s, %s)",
             (S, N, team, ruolo, gid[i] if i else None))
    if panca is not None:
        ipadb.salva_panchina(S, N, team, None, [{"giocatore_id": gid[i], "testo": f"P{i}", "ruolo": r} for i, r in panca])

# Alfa: r10 PG (MEM) Out → FADD con r6 (PG); r6 ha uno 0 con 0 minuti il 11/11 (non conta)
schiera("team01", [10, 2, 3, 4, 9], [(7, "SF"), (6, "PG"), (8, "C"), (16, "PF"), (15, "SG")])
# Beta: tutti giocano; r13 ha uno 0 con dei minuti (conta)
schiera("team02", [11, 12, 13, 14, 1], [(21, "PG"), (22, "SG"), (24, "SF"), (23, "PF"), (25, "C")])
# Gamma: r5 PG (IND, a media) Out tutta la giornata → FADD anche se IND non gioca; r30 (NOP) a media
# in fondo alla panchina r21, che è anche titolare (quintetto copiato da Yahoo): esce dalla panchina
schiera("team03", [5, 21, 22, 24, 23], [(30, "SG"), (16, "PG"), (26, "C"), (21, "PG")])
# Delta: niente panchina (avviso), un ruolo vuoto
schiera("team04", [25, 26, None, 9, 12], None)
db.q("INSERT INTO ipa_stato_giornata (stagione, giornata, chiusa) VALUES (%s, %s, NOW())", (S, N))

ok(R.giornata_chiusa(S, N), "giornata chiusa su IPanchinari: si può calcolare")
# ── formazioni sul foglio di controllo appena congelate (prima del calcolo) ──
import formazioni_foglio as FF
FF.migra(); db.q("TRUNCATE lega_foglio_formazioni")
_t0 = datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)
db.q("UPDATE lega_giornate SET prima_partita = %s WHERE stagione = %s AND numero = %s", (_t0, S, N))
_inviati = []
async def _gas_ff(payload):
    _inviati.append(payload); return {"ok": True}
ff = asyncio.run(FF.aggiorna(ora=_t0 + timedelta(hours=1), manda=_gas_ff))
_tab = _inviati[0]["righe"] if _inviati else []
_cel = [c for r in _tab for c in r]
ok(len(ff) == 1 and _inviati[0]["nome"] == f"Calcolo G{N}" and "Q-PG" in _cel and "P1" in _cel and "panchina non mandata" in _cel
   and any("questa posizione vale 0" in str(x) for x in _cel) and not any(str(x).startswith("=") for x in _cel),
   "alla scadenza: tab «Calcolo GN» coi soli schierati (quintetti, panchine in ordine), niente formule")
ok(asyncio.run(FF.aggiorna(ora=_t0 + timedelta(hours=1), manda=_gas_ff)) == [] and len(_inviati) == 1, "niente cambi: non riscrive")
db.q("UPDATE ipa_formazioni SET giocatore_id = %s WHERE stagione = %s AND giornata = %s AND team_id = 'team01' AND ruolo = 'C'",
     (gid[16], S, N))
ff2 = asyncio.run(FF.aggiorna(ora=_t0 + timedelta(hours=2), manda=_gas_ff))
ok(len(ff2) == 1 and "aggiornate" in ff2[0] and len(_inviati) == 2, "un admin corregge una formazione: il tab si riscrive")
db.q("UPDATE ipa_formazioni SET giocatore_id = %s WHERE stagione = %s AND giornata = %s AND team_id = 'team01' AND ruolo = 'C'",
     (gid[9], S, N))
# ── foglio provvisorio a metà giornata (alle 10 dei giorni in mezzo; Luca, 23/10) ──
import calcolo as _CA
_oggi_vero = _CA.oggi_et
_CA.oggi_et = lambda: DAL                                  # primo giorno: nessuna notte finita
ok(asyncio.run(FF.parziali(ora=_t0 + timedelta(hours=3), manda=_gas_ff, scarica=False)) == [], "prima notte non ancora finita: niente foglio provvisorio")
_CA.oggi_et = lambda: DAL + timedelta(days=1)              # finita la prima notte
_n0 = len(_inviati)
_fp = asyncio.run(FF.parziali(ora=_t0 + timedelta(hours=3), manda=_gas_ff, scarica=False))
_tp = _inviati[-1]["righe"] if len(_inviati) > _n0 else []
ok(len(_fp) == 1 and f"fino al {DAL:%d/%m}" in _fp[0] and "PROVVISORIO" in str(_tp[0][0]) and f"notti fino al {DAL:%d/%m}" in str(_tp[0][0])
   and any(str(x).startswith("=") for r in _tp for x in r),
   "dopo la prima notte: tab col calcolo (formule) e PROVVISORIO nel titolo, notti fino a ieri")
ok(asyncio.run(FF.aggiorna(ora=_t0 + timedelta(hours=3), manda=_gas_ff)) == [], "dopo il provvisorio il job delle formazioni non lo sovrascrive")
db.q("UPDATE ipa_formazioni SET giocatore_id = %s WHERE stagione = %s AND giornata = %s AND team_id = 'team01' AND ruolo = 'C'",
     (gid[16], S, N))
_ff3 = asyncio.run(FF.aggiorna(ora=_t0 + timedelta(hours=4), manda=_gas_ff))
ok(len(_ff3) == 1 and "provvisorio" in _ff3[0] and "PROVVISORIO" in str(_inviati[-1]["righe"][0][0]),
   "correzione di un admin a giornata iniziata: il tab si riscrive col calcolo provvisorio, non con le sole formazioni")
db.q("UPDATE ipa_formazioni SET giocatore_id = %s WHERE stagione = %s AND giornata = %s AND team_id = 'team01' AND ruolo = 'C'",
     (gid[9], S, N))
_CA.oggi_et = _oggi_vero
db.q("UPDATE lega_giornate SET prima_partita = NULL WHERE stagione = %s AND numero = %s", (S, N))

# ── panchinario ceduto prima della scadenza: esce dalla panchina, gli altri scalano (v34) ──
_scad = datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)
db.q("UPDATE lega_giornate SET prima_partita = %s WHERE stagione = %s AND numero = %s", (_scad, S, N))
db.q("DELETE FROM transazioni WHERE note = 'prova ceduti'")
for _g, _mov in [(gid[7], [("signed", None, "team01", 30), ("trade", "team01", "team02", 1)]),     # ceduto prima
                 (gid[6], [("signed", None, "team01", 30), ("trade", "team01", "team02", -1)]),    # ceduto dopo la scadenza
                 (gid[2], [("signed", None, "team01", 30), ("cut", "team01", None, 2)])]:         # titolare tagliato prima
    for _tipo, _da, _a, _ore_prima in _mov:
        db.q("INSERT INTO transazioni (tipo, oggetto, giocatore_id, team_id_da, team_id_a, stagione, timestamp, note) "
             "VALUES (%s, 'giocatore', %s, %s, %s, %s, %s, 'prova ceduti')", (_tipo, _g, _da, _a, S, _scad - timedelta(hours=_ore_prima)))
_c = R.calcola(S, N)
_alfa = next(r for r in _c["risultati"] if "team01" in (r["casa"], r["trasferta"]))
_sa = _alfa["sc"] if _alfa["casa"] == "team01" else _alfa["st"]
_nomi = R._giocatori([gid[7], gid[6], gid[2]], S)
_at = {x["atleta"] for x in _sa["panchina"] + _sa["titolari"]}   # r6 entra con la FADD
ok(_nomi[gid[7]]["espn_id"] not in _at and _nomi[gid[6]]["espn_id"] in _at,
   "panchinario ceduto prima della scadenza: fuori dalla panchina; ceduto dopo: conta per la vecchia squadra")
ok(any("ceduto prima della scadenza" in a and _nomi[gid[7]]["nome_common"] in a and "penalità" in a for a in _c["avvisi"]),
   "avviso agli admin: ceduto in panchina (penalità)")
ok(any("titolare non più in squadra alla scadenza" in a and _nomi[gid[2]]["nome_common"] in a for a in _c["avvisi"]),
   "titolare tagliato prima della scadenza: avviso (si corregge da Yahoo)")
_gr = R.griglia(_c)
_rig = [r for r in _gr["righe"] if len(r) > 3 and r[3] == _nomi[gid[7]]["nome_common"]]
ok(_rig and "ceduto prima della scadenza" in str(_rig[0][-1]), "foglio di controllo: riga del ceduto con la nota")
_ff = FF.griglia(S, N)
ok(any("ceduto prima della scadenza" in str(c) for r in _ff["righe"] for c in r)
   and any("non più in squadra alla scadenza" in str(c) for r in _ff["righe"] for c in r),
   "tab delle formazioni: ceduti segnati")
db.q("DELETE FROM transazioni WHERE note = 'prova ceduti'")
db.q("UPDATE lega_giornate SET prima_partita = NULL WHERE stagione = %s AND numero = %s", (S, N))
c = R.calcola(S, N)
r1, r2 = c["risultati"]
ok(r1["sc"]["fadd"] and r1["sc"]["fadd"]["esce"]["atleta"] == "r10" and r1["sc"]["fadd"]["entra"]["atleta"] == "r6",
   "FADD: titolare Out tutta la giornata mentre la sua squadra gioca")
ok(c["punti"]["r6"]["fp"] == 12, "uno 0 con 0 minuti non fa media (r6: 12 e 0 senza minuti → 12)")
ok(c["punti"]["r13"]["fp"] == 5, f"uno 0 con dei minuti fa media (r13: 0 in 22 minuti e 10 → {c['punti']['r13']['fp']})")
ok(r2["sc"]["fadd"] and r2["sc"]["fadd"]["esce"]["atleta"] == "r5" and r2["sc"]["fadd"]["entra"]["atleta"] == "r16",
   "FADD anche se la squadra del titolare non gioca (a media) e lui è indisponibile")
ok(c["punti"]["r30"]["come"] == "media" and c["punti"]["r30"]["fp"] == 18, "squadra a media, disponibile: media della stagione")
ok(any("Delta: panchina non mandata" in a for a in c["avvisi"]) and any("Delta: quintetto incompleto (Q-SF)" in a for a in c["avvisi"]),
   "avvisi: panchina mancante e quintetto incompleto")
ok([x["atleta"] for x in r2["sc"]["panchina"]] == ["r30", "r26", "r21"] and r2["sc"]["panchina"][2]["fp"] == 0
   and any("Gamma: titolare e anche in panchina: Prova 21" in a for a in c["avvisi"]),
   "dopo la FADD la panchina di Gamma scala; r21, titolare e anche in panchina, resta al suo posto e vale 0 (con l'avviso)")
ok(r1["supplementari"] == 1 and r1["supp_casa"] == 9 and r1["supp_trasferta"] == 29,
   f"partita 1 ai supplementari: soli punti dei supplementari {r1['punti_casa']} {r1['punti_trasferta']} {r1['supp_casa']} {r1['supp_trasferta']}")

# ── il foglio rifà i conti del bot ──
from numeri import ottavi, testo as tp
ok([ottavi(x) for x in (0.01, 0.26, 10 / 3, -0.0625, 0.4375)] == [0.0, 0.25, 3.375, -0.125, 0.5]
   and [tp(x) for x in (0.125, 0.375, 0.625, 0.875, -3.375)] == ["0,13", "0,38", "0,63", "0,88", "-3,38"],
   "all'ottavo: solo ,00 ,13 ,25 ,38 ,50 ,63 ,75 ,88 (la metà per eccesso, come ROUND dei fogli)")
ok(c["punti"]["r1"]["fp"] == 23.625, f"tre notti: media all'ottavo ({c['punti']['r1']['fp']})")
ok(all(float(v) * 8 == int(float(v) * 8) for v in [p["fp"] for p in c["punti"].values()] + [r1["punti_casa"], r1["punti_trasferta"]]),
   "punteggi e totali del calcolo: multipli di 0,125")
gr = R.griglia(c)
ok(R.payload_foglio(gr)["congela"] == {"righe": 0, "colonne": 0}, "niente righe né colonne bloccate (e si sbloccano quelle dei tab vecchi)")
ok(all(len(x) == len(gr["righe"][0]) for k in ("righe", "sfondi", "testi", "pesi", "formati") for x in gr[k])
   and len(gr["righe"]) == len(gr["sfondi"]) == len(gr["formati"]), "matrici della stessa forma per il gas")
if shutil.which("soffice"):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    for i, riga in enumerate(gr["righe"], 1):
        for j, v in enumerate(riga, 1):
            if v != "":
                ws.cell(row=i, column=j, value=v)
    d = tempfile.mkdtemp()
    wb.save(os.path.join(d, "c.xlsx"))
    subprocess.run(["soffice", "--headless", "--convert-to", "csv", "--outdir", d, os.path.join(d, "c.xlsx")],
                   capture_output=True, timeout=180)
    foglio = list(csv.reader(io.open(os.path.join(d, "c.csv"), encoding="utf-8", errors="replace")))
    shutil.rmtree(d, ignore_errors=True)
    num = lambda x: round(float(x), 6) if x not in ("", None) else None
    ris_foglio = [foglio[i] for i in range(4, 4 + len(c["risultati"]))]
    for k, (rb, rf) in enumerate(zip(c["risultati"], ris_foglio), 1):
        vince_bot = config.nome(rb["casa"]) if rb["vince"] == "casa" else config.nome(rb["trasferta"])
        ok((num(rf[2]), num(rf[4]), int(float(rf[5])), rf[8]) == (rb["punti_casa"], rb["punti_trasferta"], rb["supplementari"], vince_bot)
           and (num(rf[6]), num(rf[7])) == (rb["supp_casa"], rb["supp_trasferta"]),
           f"partita {k}: il foglio dà gli stessi risultati del bot {rf[:9]} / {rb['punti_casa']} {rb['punti_trasferta']} "
           f"{rb['supplementari']} {rb['supp_casa']} {rb['supp_trasferta']} {vince_bot}")
    ip = gr["colonne"]["punteggio"]
    nomi = {f"Prova {i}": f"r{i}" for i in range(1, 41)}
    doppio = lambda r: r[1].startswith("P") and ("tolto dalla panchina" in r[-1] or "questa posizione vale 0" in r[-1])
    diversi = [(r[3], r[ip], c["punti"][nomi[r[3]]]["fp"]) for r in foglio if len(r) > ip and r[3] in nomi and not doppio(r)
               and num(r[ip]) != c["punti"][nomi[r[3]]]["fp"]]
    ok(not diversi, f"punteggio di ogni giocatore: foglio = bot {diversi[:3]}")
    dd = [r for r in foglio if len(r) > ip and r[3] == "Prova 21" and doppio(r)]
    ok(len(dd) == 1 and num(dd[0][ip]) == 0, f"foglio: il titolare che è anche in panchina, lì vale 0 (e tiene la sua posizione) {dd}")
else:
    print("⚠️ LibreOffice non c'è: confronto col foglio saltato")

async def _gas(payload):
    return {"ok": True, "tab": payload["nome"], "righe": len(payload["righe"]), "errori": 3, "sintassi": "punto e virgola"}
ok("3 formule danno #ERROR!" in asyncio.run(R.scrivi_foglio(c, manda=_gas)), "se il gas trova formule in errore, il bot lo dice")
async def _gas_ok(payload):
    ok(payload["action"] == "calcolo" and payload["nome"] == "Calcolo G7" and payload["formati"]
       and all(f["range"][0].isalpha() for f in payload["formati"]), "payload per il gas: tab, formati come intervalli")
    return {"ok": True, "tab": payload["nome"], "righe": len(payload["righe"]), "errori": 0, "sintassi": "virgole"}
ok(asyncio.run(R.scrivi_foglio(c, manda=_gas_ok)).startswith("tab «Calcolo G7» scritto"), "tab scritto senza errori")

# ── proposta e convalida ──
v = R.salva_calcolo(c)
ok(v == 1 and db.q("SELECT stato FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (S, N), one=True)["stato"] == "da_convalidare",
   "proposta salvata, da convalidare")
ok(R.salva_calcolo(c) == 2, "ricalcolo: versione 2")
R.convalida(S, N, 900)
lr = db.q("SELECT * FROM lega_risultati WHERE stagione = %s AND giornata = %s ORDER BY casa", (S, N), many=True)
ok(len(lr) == 2 and all(x["convalidato"] for x in lr) and float(lr[0]["punti_casa"]) == r1["punti_casa"],
   "convalida: risultati in lega_risultati (quelli che vanno sul Calendario)")
# storico del calcolo (v6.9.0): ogni versione resta, con la convalida e cosa cambia tra una e l'altra
_st = R.storico(S, N)
ok([x["versione"] for x in _st] == [1, 2] and _st[1]["convalidato"] and not _st[0]["convalidato"],
   "storico del calcolo: tutte le versioni, segnata quella convalidata")
import copy as _cp
_c99 = _cp.deepcopy(c); _c99["giornata"] = dict(c["giornata"], numero=99)
R.salva_calcolo(_c99)
R.salva_calcolo(_c99)
_c99["risultati"][0]["punti_casa"] = float(_c99["risultati"][0]["punti_casa"]) + 10
R.salva_calcolo(_c99)
_ts = R.testo_storico(S, 99)
ok("<b>v1</b>" in _ts and "prima versione" in _ts and "stessi risultati della versione prima" in _ts
   and "<b>v3</b>" in _ts and _ts.count("punti ") == 1 and "→ <b>" in _ts,
   "/storico_calcolo: per ogni versione cosa cambia rispetto alla precedente\n" + _ts)
_rs = []
class _MsgS:
    async def reply_text(self, t, **k): _rs.append(t)
import handlers_risultati as HR
asyncio.run(HR.cmd_storico_calcolo(types.SimpleNamespace(effective_message=_MsgS(), effective_user=types.SimpleNamespace(id=config.admin_ids()[0])),
                                   types.SimpleNamespace(args=["G99"])))
ok(_rs and "Storico del calcolo · giornata 99" in _rs[0], "/storico_calcolo G99 (admin)")
db.q("DELETE FROM lega_calcoli WHERE giornata = 99"); db.q("DELETE FROM lega_calcoli_storico WHERE giornata = 99")
import handlers as _H
_risp = []
class _Msg:
    async def reply_text(self, t, **k): _risp.append(t)
_upd = types.SimpleNamespace(effective_message=_Msg(), effective_user=types.SimpleNamespace(id=1))
asyncio.run(_H._mostra_giornata(_upd, db.giornata(S, N)))
from numeri import testo as _tp
ok(f"{_tp(lr[0]['punti_casa'])} – {_tp(lr[0]['punti_trasferta'])}" in _risp[0] and "<b>" in _risp[0].split("\n\n", 1)[1]
   and "supp." in _risp[0], "/giornata: risultati convalidati, vincente in grassetto, supplementari " + _risp[0][-300:])
ok(_H._argomenti(["7", "Beta"]) == (7, "Beta") and _H._argomenti(["buffalo", "brownies"]) == (None, "buffalo brownies"),
   "/calendario: numero e squadra in qualsiasi ordine")
t_beta = _H._squadra(_upd, "team02")[0]
ok(t_beta and t_beta["id"] == "team02" and _H._squadra(_upd, "GA")[0]["id"] == "team01"
   and _H._squadra(_upd, "zzzz")[1], "squadra per id, per nome del GM; non trovata: lo dice")
tf = _H.testo_calendario_full(S, t_beta)
rb = lr[0] if lr[0]["trasferta"] == "team02" or lr[0]["casa"] == "team02" else lr[1]
mio = rb["punti_trasferta"] if rb["trasferta"] == "team02" else rb["punti_casa"]
ok(f"G{N} ·" in tf and _tp(mio) in tf and ("✅ V" in tf or "❌ S" in tf) and "Calendario di Beta" in tf,
   "/calendario_full: tutte le giornate della squadra, col risultato (i suoi punti prima) " + tf)
t = R.testo(c, 2)
ok("Giornata 7 calcolata</b> (ricalcolo 1)" in t and "FADD: esce Prova 10, entra Prova 6" in t and "Delta: panchina non mandata" in t,
   "messaggio per il gruppo admin: risultati, FADD, avvisi")

# ── proposta al gruppo admin, convalida coi bottoni, controllo delle 10 ──
import json as _json, handlers_risultati as HR
G = _json.load(open(config.GLOBALS_PATH)); G["admin_group_id"] = -2; G["log_channel_id_louca"] = -3
_json.dump(G, open(config.GLOBALS_PATH, "w"))
db.q("DELETE FROM lega_calcoli"); db.q("DELETE FROM lega_calcoli_storico"); db.q("DELETE FROM lega_risultati")
from shared import azioni as _A; _A.migra(db.q); db.q("DELETE FROM registro_azioni WHERE bot = 'louca'")
class Bot:
    def __init__(s): s.mandati, s.n = [], 100
    async def send_message(s, chat_id, text, **k):
        s.n += 1; s.mandati.append({"chat_id": chat_id, "text": text, "id": s.n, **k}); return types.SimpleNamespace(message_id=s.n)
    async def edit_message_reply_markup(s, **k): s.mandati.append({"tolti_bottoni": k.get("message_id")})
BOT = Bot()
asyncio.run(HR.esegui(BOT, S, N))
prop = [x for x in BOT.mandati if x.get("chat_id") == -2]
ok(len(prop) == 1 and "Giornata 7 calcolata" in prop[0]["text"] and "non configurato" in prop[0]["text"]
   and [b.callback_data for r in prop[0]["reply_markup"].inline_keyboard for b in r] == [f"rc:ok:{N}:1", f"rc:re:{N}"],
   "alle 7:45: proposta al gruppo admin con Convalida e Ricalcola (foglio non configurato: lo dice)")
asyncio.run(HR.esegui(BOT, S, N, "prova"))
# /giornata e /risultati di una giornata calcolata e non convalidata: i risultati calcolati, in attesa della convalida
import handlers as _HGx, nba as _NBx
_vo = _NBx.oggi_et; _NBx.oggi_et = lambda: db.giornata(S, N)["al"] + timedelta(days=1)
_vg2 = []
class _MsgG2:
    async def reply_text(self, t, **k): _vg2.append(t)
asyncio.run(_HGx.cmd_giornata(types.SimpleNamespace(effective_message=_MsgG2(), effective_user=types.SimpleNamespace(id=900)),
                              types.SimpleNamespace(args=[str(N)], bot=None)))
_NBx.oggi_et = _vo
ok(_vg2 and "risultati calcolati, in attesa della convalida di un admin" in _vg2[0] and "ufficiali quando un admin li convalida" in _vg2[-1],
   "/giornata di una giornata calcolata e non convalidata: i risultati calcolati, detto chiaramente")
ok({"tolti_bottoni": prop[0]["id"]} in BOT.mandati and any("Superata dal ricalcolo" in x.get("text", "") for x in BOT.mandati),
   "ricalcolo: la proposta vecchia perde i bottoni e rimanda alla nuova")
class Q:
    def __init__(s, data): s.data, s.risposte, s.message = data, [], types.SimpleNamespace(chat_id=-2, message_id=1)
    async def answer(s, t=None, show_alert=False): s.risposte.append(t)
    async def edit_message_reply_markup(s, **k): pass
def premi(uid, data):
    q = Q(data); u = types.SimpleNamespace(callback_query=q, effective_user=types.SimpleNamespace(id=uid, full_name="Admin"))
    asyncio.run(HR.cb_risultati(u, types.SimpleNamespace(bot=BOT, application=None))); return q
ok(premi(101, f"rc:ok:{N}:2").risposte == ["Solo admin."], "convalida: solo admin")
ok("non è più valida" in premi(900, f"rc:ok:{N}:1").risposte[-1], "il bottone di una proposta superata non convalida")
premi(900, f"rc:ok:{N}:2")
ok(db.q("SELECT COUNT(*) AS n FROM lega_risultati WHERE stagione = %s AND giornata = %s AND convalidato IS NOT NULL", (S, N), one=True)["n"] == 2
   and any("convalidata da Admin" in x.get("text", "") for x in BOT.mandati), "convalida: risultati salvati, conferma nel gruppo")
ok("non è più valida" in premi(900, f"rc:ok:{N}:2").risposte[-1], "una seconda convalida dello stesso bottone non fa niente")
# ricalcolo di una giornata convalidata: cosa cambia rispetto ai risultati convalidati (Luca, 26/10)
_lc = db.q("SELECT risultati FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (S, N), one=True)["risultati"]
_ris = _lc if isinstance(_lc, list) else json.loads(_lc)
ok(R.differenze(S, N, _ris) == [] and "Stessi risultati della convalida" in R.testo_differenze(R.differenze(S, N, _ris)),
   "ricalcolo uguale alla convalida: «stessi risultati»")
_mod = [dict(x) for x in _ris]
_mod[0]["supp_casa"], _mod[0]["supp_trasferta"] = 12.5, 14.0
_mod[0]["vince"] = "trasferta" if _mod[0]["vince"] == "casa" else "casa"
_d = R.differenze(S, N, _mod)
ok(len(_d) == 1 and "supplementari" in _d[0] and "⚠️ <b>vince" in _d[0] and "cambiano 1 partita" in R.testo_differenze(_d),
   f"ricalcolo diverso: la partita cambiata, coi supplementari e il vincitore nuovo {_d}")
ok(R.differenze(S, 999, _ris) is None and R.testo_differenze(None) == "", "giornata mai convalidata: niente confronto")
_reg = db.q("SELECT veste, azione, chi_id, dopo FROM registro_azioni WHERE bot = 'louca' ORDER BY id", many=True)
ok([(r["veste"], r["azione"]) for r in _reg] == [("sistema", "giornata calcolata"), ("sistema", "giornata ricalcolata"),
                                                  ("admin", "giornata convalidata")] and _reg[-1]["chi_id"] == 900,
   f"registro: calcolo e ricalcolo del job (sistema), convalida dell'admin {[(r['veste'], r['azione']) for r in _reg]}")
# ── controllo finale delle 20 (v58, Luca 30/10): ESPN corregge r12 (schierato), si chiede la verifica su Yahoo ──
import congelamento as CG
_d1 = db.q("SELECT data_et FROM nba_partite WHERE espn_id = 'g1'", one=True)["data_et"]
_r12_prima = dict(db.q("SELECT * FROM nba_tabellini WHERE atleta = 'r12' AND partita = 'g1'", one=True))
async def finto_scarica(ids, **k):
    if k.get("salva", True):
        db.q("UPDATE nba_tabellini SET fp = 25, ast = ast + 2 WHERE atleta = 'r12' AND partita = 'g1'")
    return {"partite": len(ids), "giocatori": 0, "errori": [], "letti": {}}
_vero = HR.nba.scarica_tabellini; HR.nba.scarica_tabellini = finto_scarica
BOT.mandati.clear()
_es = asyncio.run(HR.controllo_notte(BOT, _d1))
HR.nba.scarica_tabellini = _vero
avv = [x for x in BOT.mandati if x.get("chat_id") == -2]
_cb = [b.callback_data for r in avv[0]["reply_markup"].inline_keyboard for b in r] if avv else []
ok(len(avv) == 1 and "Controllo finale, notte del" in avv[0]["text"] and "Yahoo" in avv[0]["text"]
   and "21,00 → <b>25,00</b>" in avv[0]["text"] and "assist" in avv[0]["text"] and "1 tabellino di" in avv[0]["text"]
   and _cb[:2] == [x for x in _cb if x.startswith("cn:")] and len([x for x in _cb if x.startswith("cn:")]) == 2 and f"rc:re:{N}" in _cb,
   f"controllo finale delle 20: cambio di uno schierato col dettaglio delle statistiche, ✅/❌ Yahoo e Ricalcola {avv[0]['text'] if avv else ''}")
# ❌ non corrisponde a Yahoo: tornano i valori di prima
class QY(Q):
    def __init__(s, data):
        super().__init__(data); s.message = types.SimpleNamespace(chat_id=-2, message_id=888, text_html="🔎 controllo")
    async def edit_message_text(s, t, **k): s.testo, s.k = t, k
_cid = [x for x in _cb if x.startswith("cn:no:")][0]
_qy = QY(_cid)
asyncio.run(HR.cb_controllo(types.SimpleNamespace(callback_query=_qy, effective_user=types.SimpleNamespace(id=900, full_name="Admin")),
                            types.SimpleNamespace(bot=BOT, application=None)))
_r12_ora = db.q("SELECT * FROM nba_tabellini WHERE atleta = 'r12' AND partita = 'g1'", one=True)
ok(float(_r12_ora["fp"]) == float(_r12_prima["fp"]) and _r12_ora["ast"] == _r12_prima["ast"] and "Non corrisponde a Yahoo" in _qy.testo
   and [b.callback_data for r in _qy.k["reply_markup"].inline_keyboard for b in r] == [f"rc:re:{N}"],
   "❌ non corrisponde a Yahoo: rimessi i valori di prima (anche le statistiche), resta il bottone Ricalcola")
_qy2 = QY(_cid.replace(":no:", ":ok:"))
asyncio.run(HR.cb_controllo(types.SimpleNamespace(callback_query=_qy2, effective_user=types.SimpleNamespace(id=900, full_name="Admin")),
                            types.SimpleNamespace(bot=BOT, application=None)))
ok(_qy2.risposte == ["Già deciso."], "una volta deciso, l'altro bottone non fa niente")
# primo controllo delle 11:05 a giornata convalidata (live chiuso): log col dettaglio e admin con Ricalcola (v60)
async def finto3(ids, **k):
    db.q("UPDATE nba_tabellini SET fp = fp + 1, stl = stl + 1 WHERE atleta = 'r12' AND partita = 'g1'")
    return {"partite": len(ids), "giocatori": 0, "errori": [], "letti": {}}
HR.nba.scarica_tabellini = finto3
BOT.mandati.clear()
_ep = asyncio.run(HR.primo_controllo(BOT, _d1))
HR.nba.scarica_tabellini = _vero
_adm = [x for x in BOT.mandati if x.get("chat_id") == -2]
ok(_ep == "1 cambi" and any("Primo controllo (11:05)" in x.get("text", "") and "recuperi" in x.get("text", "") for x in BOT.mandati if x.get("chat_id") == -3)
   and _adm and [b.callback_data for r in _adm[0]["reply_markup"].inline_keyboard for b in r] == [f"rc:re:{N}"],
   f"primo controllo delle 11:05 a giornata calcolata: dettaglio sul log e agli admin con Ricalcola {_adm[0]['text'] if _adm else ''}")
db.q("UPDATE nba_tabellini SET fp = fp - 1, stl = stl - 1 WHERE atleta = 'r12' AND partita = 'g1'")
# le altre notti della giornata: solo informazione sul log, niente salvato (Luca, 30/10)
_d2 = _d1 + timedelta(days=1)
_r12 = dict(db.q("SELECT * FROM nba_tabellini WHERE atleta = 'r12' AND partita = 'g1'", one=True))
async def finto2(ids, **k):
    if k.get("salva", True) is False:
        return {"partite": 0, "giocatori": 0, "errori": [], "letti": {"g1": [{**_r12, "fp": 99, "pts": int(_r12["pts"]) + 30}]}}
    return {"partite": len(ids), "giocatori": 0, "errori": [], "letti": {}}
HR.nba.scarica_tabellini = finto2
BOT.mandati.clear()
if [p for p in db.partite_nba(_d2, _d2) if p["stato"] == "STATUS_FINAL"]:
    asyncio.run(HR.controllo_notte(BOT, _d2))
    # (Luca, 30/10) agli admin col dettaglio e coi bottoni ✅ aggiorna come Yahoo / ❌ lascia com'è; niente salvato finché non si preme
    _info = [x for x in BOT.mandati if x.get("chat_id") == -2 and "Niente è stato salvato" in x.get("text", "")]
    _cbi = [b.callback_data for r in _info[0]["reply_markup"].inline_keyboard for b in r] if _info else []
    ok(_info and "r12" in _info[0]["text"] and "punti" in _info[0]["text"] and "Niente è stato salvato" in _info[0]["text"]
       and [x.split(":")[1] for x in _cbi] == ["ag", "la"]
       and any(x.get("chat_id") == -3 and "da verificare su Yahoo" in x.get("text", "") for x in BOT.mandati)
       and float(db.q("SELECT fp FROM nba_tabellini WHERE atleta = 'r12' AND partita = 'g1'", one=True)["fp"]) == float(_r12["fp"]),
       f"le notti prima della stessa giornata: agli admin col dettaglio e i bottoni Yahoo, niente salvato {_info[0]['text'] if _info else ''}")
    _tutte_g1 = [dict(x) for x in db.q("SELECT * FROM nba_tabellini WHERE partita = 'g1'", many=True)]
    _qa = QY(_cbi[0])
    asyncio.run(HR.cb_controllo(types.SimpleNamespace(callback_query=_qa, effective_user=types.SimpleNamespace(id=900, full_name="Admin")),
                                types.SimpleNamespace(bot=BOT, application=None)))
    ok(float(db.q("SELECT fp FROM nba_tabellini WHERE atleta = 'r12' AND partita = 'g1'", one=True)["fp"]) == 99
       and "valori nuovi salvati" in _qa.testo and [b.callback_data for r in _qa.k["reply_markup"].inline_keyboard for b in r] == [f"rc:re:{N}"],
       "✅ su Yahoo è così: salvati i valori di ESPN della notte congelata, resta Ricalcola")
    _ql = QY(_cbi[1])
    asyncio.run(HR.cb_controllo(types.SimpleNamespace(callback_query=_ql, effective_user=types.SimpleNamespace(id=900, full_name="Admin")),
                                types.SimpleNamespace(bot=BOT, application=None)))
    ok(_ql.risposte == ["Già deciso."], "notte congelata: deciso una volta, l'altro bottone non fa niente")
    db.q("DELETE FROM nba_tabellini WHERE partita = 'g1'")
    from db import _COLONNE_TAB as _CT
    for _x in _tutte_g1:
        db.q(f"INSERT INTO nba_tabellini ({', '.join(_CT)}) VALUES ({', '.join('%(' + k + ')s' for k in _CT)})", {k: _x[k] for k in _CT})
    # ❌ lascia com'è: niente cambia
    BOT.mandati.clear()
    asyncio.run(HR.controllo_notte(BOT, _d2))
    _cbi = [b.callback_data for x in BOT.mandati if x.get("chat_id") == -2 and "Niente è stato salvato" in x.get("text", "")
            for r in x["reply_markup"].inline_keyboard for b in r]
    _ql = QY(_cbi[1])
    asyncio.run(HR.cb_controllo(types.SimpleNamespace(callback_query=_ql, effective_user=types.SimpleNamespace(id=900, full_name="Admin")),
                                types.SimpleNamespace(bot=BOT, application=None)))
    ok(float(db.q("SELECT fp FROM nba_tabellini WHERE atleta = 'r12' AND partita = 'g1'", one=True)["fp"]) == float(_r12["fp"])
       and "Lasciata com'era" in _ql.testo and _ql.k.get("reply_markup") is None, "❌ lascia com'è: niente cambia, niente bottoni")
    # la sera dopo ESPN la dà ancora uguale a prima: non si ripete agli admin, solo una riga sul log
    BOT.mandati.clear()
    asyncio.run(HR.controllo_notte(BOT, _d2))
    ok(not any(x.get("chat_id") == -2 and "Niente è stato salvato" in x.get("text", "") for x in BOT.mandati)
       and any(x.get("chat_id") == -3 and "come già segnalato" in x.get("text", "") for x in BOT.mandati),
       "stessa differenza già lasciata com'era: la sera dopo non si ripete agli admin")
else:
    ok(False, "manca una partita finita nella seconda notte della giornata di prova")
HR.nba.scarica_tabellini = _vero
# premuto 🔄 Ricalcola sull'avviso: il bottone sparisce e resta scritto chi l'ha avviato (Luca, 24/10)
_modifiche = []
class QC(Q):
    def __init__(s, data):
        super().__init__(data); s.message = types.SimpleNamespace(chat_id=-2, message_id=777, text_html="🔎 avviso")
    async def edit_message_text(s, t, **k): _modifiche.append((t, k))
async def _no_avvia(context, coro): coro.close()
_avvia_vero = HR._avvia; HR._avvia = _no_avvia
_qc = QC(f"rc:re:{N}")
asyncio.run(HR.cb_risultati(types.SimpleNamespace(callback_query=_qc, effective_user=types.SimpleNamespace(id=900, full_name="Admin")),
                            types.SimpleNamespace(bot=BOT, application=None)))
HR._avvia = _avvia_vero
ok(_modifiche and _modifiche[-1][1].get("reply_markup") is None and "Ricalcolo avviato da Admin" in _modifiche[-1][0]
   and _modifiche[-1][0].startswith("🔎 avviso"), "🔄 Ricalcola premuto sull'avviso: il bottone sparisce, sotto chi l'ha avviato")
_lcm = db.q("SELECT messaggio FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (S, N), one=True)["messaggio"]
class QP(QC):
    def __init__(s, data):
        super().__init__(data); s.message = types.SimpleNamespace(chat_id=-2, message_id=_lcm, text_html="📊 proposta")
_modifiche.clear()
HR._avvia = _no_avvia
asyncio.run(HR.cb_risultati(types.SimpleNamespace(callback_query=QP(f"rc:re:{N}"), effective_user=types.SimpleNamespace(id=900, full_name="Admin")),
                            types.SimpleNamespace(bot=BOT, application=None)))
HR._avvia = _avvia_vero
ok(_modifiche and _modifiche[-1][1].get("reply_markup") is None and "Ricalcolo avviato" in _modifiche[-1][0],
   "🔄 Ricalcola premuto sulla proposta: anche lì i bottoni spariscono subito (risposta unica)")

# ── /dev_prova_calcolo: la prova prima che si giochi (quintetti di adesso, panchine mandate, notti NBA indicate) ──
db.q("DELETE FROM ipa_quintetto")
db.q("INSERT INTO ipa_quintetto (team_id, ruolo, giocatore_id, fonte) SELECT team_id, ruolo, giocatore_id, 'import' "
     "FROM ipa_formazioni WHERE stagione = %s AND giornata = %s AND giocatore_id IS NOT NULL", (S, N))
async def _niente(*a, **k): return {"giorni": 0, "partite": 0, "errori": [], "giocatori": 0, "abbinamento": {}}
import handlers_calcolo as HC2
_s, _t = HR.nba.sincronizza, HC2.aggiorna_tabellini
HR.nba.sincronizza, HC2.aggiorna_tabellini = _niente, _niente
class Msg2:
    def __init__(s): s.risposte = []
    async def reply_text(s, t, **k): s.risposte.append(t)
BOT.mandati.clear(); m2 = Msg2()
u = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=config.dev_id()), effective_message=m2,
                          effective_chat=types.SimpleNamespace(id=config.dev_id()))
asyncio.run(HR.cmd_dev_prova_calcolo(u, types.SimpleNamespace(bot=BOT, args=[f"{DAL:%d/%m/%Y}", f"{AL:%d/%m/%Y}"], application=None)))
HR.nba.sincronizza, HC2.aggiorna_tabellini = _s, _t
prova = [x for x in BOT.mandati if x.get("chat_id") == config.dev_id()]
ok(prova and "PROVA" in prova[0]["text"] and "Giornata 0 calcolata" in prova[0]["text"] and "reply_markup" not in prova[0]
   and f"{r1['punti_casa']:.2f}".replace(".", ",") in prova[0]["text"],
   "/dev_prova_calcolo: stessi conti con i quintetti di adesso e le panchine mandate, solo al dev, senza bottoni")
ok(db.q("SELECT COUNT(*) AS n FROM lega_calcoli WHERE giornata = 0", one=True)["n"] == 0, "la prova non salva niente")
db.q("DELETE FROM ipa_quintetto")

db.q("UPDATE nba_partite SET stato = 'STATUS_SCHEDULED' WHERE espn_id = 'g4'")
c_s = R.calcola(S, N)
ok(c_s["risultati"][0]["sc"]["fadd"] is None and not any("r10" in x or "Prova 10" in x for x in c_s["avvisi"] if "snapshot" in x),
   "la squadra del titolare deve ancora giocare (live): niente FADD e niente avviso, si decide dopo")
db.q("UPDATE nba_partite SET stato = 'STATUS_FINAL' WHERE espn_id = 'g4'")

# ── squadra NBA dai roster ESPN di adesso (cambi di squadra d'estate) ──
gN = db.giornata(S, N)
ok(calcolo.punteggio_giocatori(S, gN, ["r30"])["r30"]["come"] == "media", "r30: ultimo tabellino coi NOP, che non giocano: media")
db.salva_atleti([{"atleta": "r30", "nome": "r30", "squadra": "NYK"}])
p30 = calcolo.punteggio_giocatori(S, gN, ["r30"])["r30"]
ok(p30["squadra"] == "NYK" and p30["come"] == "zero", "passato ai Knicks (roster ESPN), che giocano: non prende la media")
db.salva_atleti([{"atleta": f"x{i}", "nome": "x", "squadra": sq} for i, sq in enumerate(sorted(__import__("nba").NBA))])
ok(calcolo.punteggio_giocatori(S, gN, ["r30"])["r30"]["squadra"] == "NOP", "non più in nessun roster: vale l'ultimo tabellino")
import nba as _nba
_ro = _nba.leggi_roster({"athletes": [{"id": 1, "displayName": "Esordiente", "experience": {"years": 0}},
                                      {"id": 2, "displayName": "Veterano", "experience": {"years": 9}},
                                      {"id": 3, "displayName": "Senza Dato"}]}, "BOS")
ok([a["esperienza"] for a in _ro] == [0, 9, None], "roster ESPN: anni di esperienza (0 = esordiente), se ci sono")
db.salva_atleti(_ro)
db.salva_atleti([{"atleta": "1", "nome": "Esordiente", "squadra": "BOS"}])
ok(db.q("SELECT esperienza FROM nba_atleti WHERE atleta = '1'", one=True)["esperienza"] == 0, "esperienza: un roster senza il dato non la cancella")
db.q("TRUNCATE nba_atleti")

# ── punteggi live (v18) ──
import live as LV
from zoneinfo import ZoneInfo
ROMA = ZoneInfo("Europe/Rome")
LV.migra(); db.q("TRUNCATE lega_live")
G = _json.load(open(config.GLOBALS_PATH)); G["main_channel_id"] = -1; _json.dump(G, open(config.GLOBALS_PATH, "w"))
g7 = {**db.giornata(S, N), "stagione": S}
nn = LV.notti(g7)
ok([d for d, _, _ in nn] == [DAL, DAL + timedelta(days=1), AL] and nn[0][1] == datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)
   and nn[0][2] == datetime(2026, 11, 11, 8, 0, tzinfo=ROMA), "notti: dalla prima partita alle 8 del mattino dopo")
t0 = nn[0][1]
ok(LV.cosa_fare(g7, t0 - timedelta(minutes=1), None) == (None, None), "prima della palla a due: niente")
ok(LV.cosa_fare(g7, t0, None) == ("live", DAL), "alla palla a due: si pubblica")
st_ = {"message_id": 5, "aggiornato": t0}
ok(LV.cosa_fare(g7, t0 + timedelta(minutes=5), st_) == (None, None) and LV.cosa_fare(g7, t0 + timedelta(minutes=10), st_) == ("live", DAL),
   "poi ogni 10 minuti")
ok(LV.cosa_fare(g7, datetime(2026, 11, 11, 9, 0, tzinfo=ROMA), {**st_, "aggiornato": datetime(2026, 11, 11, 7, 55, tzinfo=ROMA)}) == (None, None),
   "dalle 8 alle 11 niente")
ok(LV.cosa_fare(g7, datetime(2026, 11, 11, 11, 6, tzinfo=ROMA), {**st_, "aggiornato": datetime(2026, 11, 11, 7, 55, tzinfo=ROMA)})
   == ("controllo", DAL), "alle 11:05 il primo controllo della notte")
ok(LV.cosa_fare(g7, t0 + timedelta(minutes=30), {**st_, "prossimo": t0 + timedelta(minutes=40)}) == (None, None), "dopo un errore si aspetta")

class BotL(Bot):
    async def edit_message_text(s, chat_id, message_id, text, **k):
        s.mandati.append({"chat_id": chat_id, "id": message_id, "text": text, "modifica": True})
    async def send_photo(s, chat_id, photo, caption=None, **k):
        s.n += 1; s.mandati.append({"chat_id": chat_id, "foto": photo, "text": caption or "", "id": s.n}); return types.SimpleNamespace(message_id=s.n)
    async def edit_message_media(s, chat_id, message_id, media, **k):
        s.mandati.append({"chat_id": chat_id, "id": message_id, "text": media.caption, "modifica": True, "foto": media.media})
BL = BotL()
scaricate = []
async def finta(g, d, controllo=False):
    scaricate.append((d, controllo))
db.q("UPDATE lega_giornate SET prima_partita = %s WHERE stagione = %s AND numero = %s", (t0, S, N))
fatti = asyncio.run(LV.tick(BL, ora=t0 + timedelta(seconds=30), scarica_fn=finta))
pub = [x for x in BL.mandati if x.get("chat_id") == -1]
c_ora = LV.calcolo(S, N)
r0 = c_ora["risultati"][0]
_tx = LV.testo(c_ora, t0 + timedelta(seconds=30))
ok(len(pub) == 1 and pub[0]["foto"][:8] == b"\x89PNG\r\n\x1a\n" and f"Giornata {N} · live" in pub[0]["text"]
   and "aggiornato alle 00:00" in pub[0]["text"] and "/live_results" in pub[0]["text"] and scaricate == [(DAL, False)],
   "tipoff: sul canale principale l'immagine del tabellone (Typst), didascalia con l'ora e /live_results")
ok("punteggi live" in _tx and "provvisori" in _tx and "convalida un admin" in _tx and "Ultimo aggiornamento: 11/11 alle 00:00" in _tx
   and f"{LV.tp(r0['punti_casa'])} – {LV.tp(r0['punti_trasferta'])}" in _tx, "il testo del live (per /live_results): calcolo, provvisorio, ora")
asyncio.run(LV.tick(BL, ora=t0 + timedelta(minutes=4), scarica_fn=finta))
ok(len([x for x in BL.mandati if x.get("chat_id") == -1]) == 1 and len(scaricate) == 1, "4 minuti dopo: niente")
asyncio.run(LV.tick(BL, ora=t0 + timedelta(minutes=11), scarica_fn=finta))
mod = [x for x in BL.mandati if x.get("modifica")]
ok(len(mod) == 1 and mod[0]["id"] == pub[0]["id"] and len(scaricate) == 2 and mod[0]["foto"],
   "10 minuti dopo: si sostituisce la foto dello stesso messaggio")
# un live di prima (messaggio di testo): la foto non si può mettere al suo posto → cancellato e foto nuova
class BotT(BotL):
    async def edit_message_media(s, **k): raise RuntimeError("Bad Request: there is no media in the message to edit")
    async def delete_message(s, chat_id, message_id): s.mandati.append({"cancellato": message_id})
BT = BotT()
asyncio.run(LV.aggiorna(BT, {**LV.db.giornata(S, N), "stagione": S}, None, t0 + timedelta(minutes=15)))
ok({"cancellato": pub[0]["id"]} in BT.mandati and any(x.get("foto") and x.get("chat_id") == -1 for x in BT.mandati)
   and LV.stato(S, N)["message_id"] == BT.n, "live di testo di prima: cancellato e sostituito da una foto nuova")
# timeout di Telegram sulla sostituzione: niente cancellazione, niente foto nuova, giro saltato (Luca, 26/10)
from telegram.error import TimedOut as _TO
class BotTO(BotL):
    async def edit_message_media(s, **k): raise _TO()
    async def delete_message(s, chat_id, message_id): s.mandati.append({"cancellato": message_id})
BTO = BotTO()
_id_prima = LV.stato(S, N)["message_id"]
try:
    asyncio.run(LV.aggiorna(BTO, {**LV.db.giornata(S, N), "stagione": S}, None, t0 + timedelta(minutes=16)))
    _errore = False
except _TO:
    _errore = True
ok(_errore and not any("cancellato" in x for x in BTO.mandati) and not any(x.get("foto") for x in BTO.mandati)
   and LV.stato(S, N)["message_id"] == _id_prima, "timeout di Telegram: il live NON si cancella e non se ne manda un altro, si salta il giro")
class BotAltro(BotL):
    async def edit_message_media(s, **k): raise RuntimeError("Forbidden: bot is not a member of the channel chat")
    async def delete_message(s, chat_id, message_id): s.mandati.append({"cancellato": message_id})
BA_ = BotAltro()
try:
    asyncio.run(LV.aggiorna(BA_, {**LV.db.giornata(S, N), "stagione": S}, None, t0 + timedelta(minutes=16)))
    _errore = False
except RuntimeError:
    _errore = True
ok(_errore and not BA_.mandati, "altri errori di Telegram: niente cancellazione né messaggi nuovi, si salta il giro")
LV._salva(S, N, aggiornato=t0 + timedelta(minutes=11))      # come se non fosse successo: i giri dopo restano quelli
async def rotta(g, d, controllo=False):
    raise RuntimeError("429 Too Many Requests")
BL.mandati.clear()
asyncio.run(LV.tick(BL, ora=t0 + timedelta(minutes=22), scarica_fn=rotta))
stl = LV.stato(S, N)
ok(stl["prossimo"] == t0 + timedelta(minutes=32) and any("aggiornamento saltato" in x["text"] for x in BL.mandati if x["chat_id"] == -3)
   and not any(x.get("modifica") for x in BL.mandati), "ESPN in errore: giro saltato, si riprova fra 10 minuti, una riga sul log")
asyncio.run(LV.tick(BL, ora=t0 + timedelta(minutes=30), scarica_fn=finta))
ok(len(scaricate) == 2, "prima dei 10 minuti non riprova")
BL.mandati.clear()
asyncio.run(LV.tick(BL, ora=t0 + timedelta(minutes=33), scarica_fn=rotta))
ok(any("aggiornamento saltato" in x["text"] for x in BL.mandati if x["chat_id"] == -3),
   "secondo giro saltato di fila: la riga sul log c'è di nuovo (v57: prima una all'ora, i salti dopo non si vedevano)")
db.q("UPDATE lega_live SET prossimo = NULL WHERE stagione = %s AND giornata = %s", (S, N))
# una partita che non risponde non blocca il giro: tabellone aggiornato, riga sul log
async def una_rotta(g, d, controllo=False):
    return {"errori": ["401909871: Expecting value: line 1 column 1 (char 0)"]}
BL.mandati.clear()
_agg = asyncio.run(LV.aggiorna(BL, {**LV.db.giornata(S, N), "stagione": S}, DAL, t0 + timedelta(minutes=44), scarica_fn=una_rotta))
ok(any(x.get("modifica") or x.get("foto") for x in BL.mandati if x.get("chat_id") == -1)
   and any("1 tabellini non scaricati" in x["text"] for x in BL.mandati if x["chat_id"] == -3),
   "una partita senza risposta da ESPN: il tabellone si aggiorna con le altre, riga sul log")
# ESPN che risponde vuoto: si riprova (v57)
import nba as _NB
class _R:
    def __init__(s, ok_): s.ok_ = ok_; s.status_code = 200
    def raise_for_status(s): pass
    def json(s):
        if not s.ok_: raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return {"ok": 1}
class _Cl:
    def __init__(s, seq): s.seq = list(seq); s.n = 0
    async def get(s, url, params=None):
        s.n += 1; return _R(s.seq.pop(0))
_vsl = _NB.asyncio.sleep
async def _nosleep(x): pass
_NB.asyncio.sleep = _nosleep
_c1 = _Cl([False, True])
_ok1 = asyncio.run(_NB._json(_c1, "u")) == {"ok": 1} and _c1.n == 2
_c2 = _Cl([False, False, False])
try:
    asyncio.run(_NB._json(_c2, "u")); _ok2 = False
except ValueError:
    _ok2 = _c2.n == 3
_NB.asyncio.sleep = _vsl
ok(_ok1 and _ok2, "ESPN risponde vuoto: riprova fino a 3 volte, poi l'errore")
asyncio.run(LV.tick(BL, ora=datetime(2026, 11, 11, 11, 6, tzinfo=ROMA), scarica_fn=finta))
ok(scaricate[-1] == (DAL, True), "alle 11:05 riscarica i tabellini della notte")
_rg = lambda nome, fp, mi, ast: {"nome": nome, "fp": fp, "minuti": mi, "ast": ast}
async def con_cambi(g, d, controllo=False):
    return {"cambi": {("g1", "r1"): (_rg("Prova 1", 30.0, 30, 2), _rg("Prova 1", 32.5, 31, 3)),
                      ("g1", "r99"): (_rg("Nessuno", 5.0, 10, 0), _rg("Nessuno", 6.0, 10, 0))}}
db.q("UPDATE lega_live SET aggiornato = %s WHERE stagione = %s AND giornata = %s", (datetime(2026, 11, 12, 7, 55, tzinfo=ROMA), S, N))
BL.mandati.clear()
asyncio.run(LV.tick(BL, ora=datetime(2026, 11, 12, 11, 6, tzinfo=ROMA), scarica_fn=con_cambi))
righe_log = [x["text"] for x in BL.mandati if x.get("chat_id") == -3 and "primo controllo (11:05)" in x.get("text", "")]
ok(len(righe_log) == 1 and "Prova 1: 30,00 → <b>32,50</b> (minuti 30 → 31, assist 2 → 3)" in righe_log[0] and "Nessuno" not in righe_log[0]
   and "notte del 11/11" in righe_log[0], "11:05: tabellini cambiati di giocatori schierati sul canale log (gli altri no)")
# tabellino parziale: la partita resta senza tabellino (il definitivo si riscarica a partita finita)
db.salva_tabellino("g5", [{"partita": "g5", "atleta": "r1", "nome": "r1", "squadra": "NYK", "titolare": True, "giocato": True,
                           "minuti": 10, "pts": 0, "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0, "oreb": 0,
                           "dreb": 0, "ast": 0, "stl": 0, "blk": 0, "tov": 0, "pf": 0, "fp": 21}], finale=False)
ok(db.q("SELECT tabellino FROM nba_partite WHERE espn_id = 'g5'", one=True)["tabellino"] is None and "g5" in db.partite_senza_tabellino(),
   "tabellino live: partita ancora da riscaricare")
db.q("UPDATE nba_partite SET stato = 'STATUS_IN_PROGRESS' WHERE espn_id = 'g5'")
c_ora = LV.calcolo(S, N)
r_b = next(r for r in c_ora["risultati"] if r["trasferta"] == "team02" or r["casa"] == "team02")
lato = r_b["st"] if r_b["trasferta"] == "team02" else r_b["sc"]
tl = LV.testo(c_ora, t0)
ok(LV._da_giocare(c_ora, lato["titolari"])[0] >= 1 and "🏀 in campo" in tl, "partita in corso: giocatori in campo")
ok("▶ al momento vince" in tl, "pochi giocatori ancora da giocare (al massimo 4 su 10): l'esito, al momento")
_stati = db.q("SELECT espn_id, stato FROM nba_partite", many=True)
db.q("UPDATE nba_partite SET stato = 'STATUS_SCHEDULED'")
tl0 = LV.testo(LV.calcolo(S, N), t0)
ok("▶" not in tl0 and "devono giocare" in tl0, "più di 4 dei 10 ancora da giocare: nessun esito, solo chi deve giocare")
_di0 = LV.dati_immagine(LV.calcolo(S, N), t0)
ok(all(p["avanti"] == "" for p in _di0["partite"]) and any(p["nota"] == "HANNO GIOCATO IN MENO DI 6" for p in _di0["partite"])
   and all(p["casa"]["giocare"] + p["casa"]["media"] + p["tras"]["giocare"] + p["tras"]["media"] >= 1 for p in _di0["partite"]
           if p["nota"].startswith("HANNO")), "tabellone: nessuno avanti e «HANNO GIOCATO IN MENO DI 6» finché mancano più di 4 su 10")
import re as _re
_m = _re.search(r"devono giocare (\d+) · devono rigiocare (\d+)", tl0)
ok(_m and int(_m.group(1)) + int(_m.group(2)) >= 1 and "⏳ da giocare" not in tl0,
   f"live, per squadra e per esteso: devono giocare, devono rigiocare (Luca, 23/10) {_m and _m.group(0)}")
_cc = LV.calcolo(S, N); _rr = _cc["risultati"][0]
_dg, _dr, _ballo = LV.ancora_in_ballo(_cc, _rr["sc"]["titolari"])
ok(_dr > 0 or _ballo == 0, f"finora: solo i punti di chi deve rigiocare ({_dg}, {_dr}, {_ballo})")
_vp = LV.db.partite_nba
from datetime import date as _d
LV.db.partite_nba = lambda dal, al: [
    {"casa": "AAA", "trasferta": "BBB", "stato": "STATUS_FINAL", "data_et": _d(2026, 11, 10)},
    {"casa": "AAA", "trasferta": "CCC", "stato": "STATUS_SCHEDULED", "data_et": _d(2026, 11, 11)},
    {"casa": "DDD", "trasferta": "EEE", "stato": "STATUS_SCHEDULED", "data_et": _d(2026, 11, 11)}]
_cf = {"giornata": {"dal": _d(2026, 11, 10), "al": _d(2026, 11, 11)},
       "punti": {"x": {"squadra": "AAA"}, "y": {"squadra": "AAA"}, "z": {"squadra": "DDD"}, "w": {"squadra": "BBB"}},
       "dettaglio": {"notti": {"x": {_d(2026, 11, 10): 30.5}, "y": {_d(2026, 11, 10): 30.0}, "w": {_d(2026, 11, 10): 12.0}}, "medie": {}}}
ok(LV.ancora_in_ballo(_cf, [{"atleta": a} for a in "xyzw"]) == (1, 2, 60.5),
   "2 devono rigiocare (finora 30,5 + 30), 1 deve giocare, chi ha finito non conta")
LV.db.partite_nba = _vp
for _x in _stati:
    db.q("UPDATE nba_partite SET stato = %s WHERE espn_id = %s", (_x["stato"], _x["espn_id"]))
db.q("UPDATE nba_partite SET stato = 'STATUS_FINAL' WHERE espn_id = 'g5'")
tl = LV.testo(LV.calcolo(S, N), t0)
ok("▶ al momento vince Beta ai supplementari (1): " in tl and "▶ al momento vince Gamma" in tl,
   "tutti hanno finito: l'esito, supplementari compresi")
_cf2 = LV.calcolo(S, N); _di = LV.dati_immagine(_cf2, t0)
_pb = next(p for p in _di["partite"] if "SUPPL." in p["nota"])
_png = LV.immagine(_di)
ok(_pb["avanti"] in ("casa", "trasferta") and any(p["avanti"] for p in _di["partite"]) and _png[:8] == b"\x89PNG\r\n\x1a\n"
   and _di["soglia"] == 6 and _di["notte"] == f"del {DAL:%d/%m}", f"tabellone a partite finite: chi è avanti, supplementari ({_pb['nota']}), immagine")
_nm = sum(LV.a_media(_cf2, r[k]["titolari"]) for r in _cf2["risultati"] for k in ("sc", "st"))
ok(sum(p[x]["media"] for p in _di["partite"] for x in ("casa", "tras")) == _nm
   and ((_nm == 0) or "📈 prendono media" in LV.testo(_cf2, t0)), f"chi prende la media: nel tabellone e nel testo ({_nm})")
# /live_results: il testo completo, anche in più messaggi
_rl = []
class _MsgL:
    async def reply_text(self, t, **k): _rl.append(t)
asyncio.run(LV.cmd_live_results(types.SimpleNamespace(effective_message=_MsgL()), types.SimpleNamespace(args=[str(N)])))
ok(_rl and "punteggi live" in _rl[0] and all(len(x) <= 4096 for x in _rl), "/live_results N: il testo completo del live")
_dock = open(os.path.join(os.path.dirname(LV.TEMPLATE), "Dockerfile")).read()
ok("fonts-noto-color-emoji" in _dock and '"Noto Color Emoji"' in open(LV.TEMPLATE).read() and LV.font_emoji(),
   "emoji del tabellone: il font nel Dockerfile di loucabot e nel template (e c'è qui, dove girano le prove)")
ok(LV._pezzi("a" * 3000 + "\n\n" + "b" * 3000) == ["a" * 3000, "b" * 3000], "/live_results lungo: più messaggi, tagliati tra una partita e l'altra")
av = LV.avvisi_brevi(LV.calcolo(S, N))
ok(any(x.startswith("• Delta: ") and "manca SF" in x and "senza panchina" in x for x in av), f"anteprima: avvisi brevi per squadra {av}")
class BotD(BotL):
    async def send_document(s, chat_id, document, filename, caption=None, **k):
        s.mandati.append({"chat_id": chat_id, "file": filename, "contenuto": document.read().decode()})
BD = BotD()
c_ant = LV.calcolo(S, N)
asyncio.run(LV.manda_anteprima(BD, 900, c_ant, t0))
ok(len(BD.mandati) == 1 and "Avvisi del calcolo" in BD.mandati[0]["text"] and "Delta: manca SF" in BD.mandati[0]["text"],
   "anteprima: avvisi nello stesso messaggio se ci stanno")
c_ant["avvisi"] = [f"Squadra {i}: senza id ESPN, contano 0: {'Nome Lunghissimo ' * 8}" for i in range(60)]
BD.mandati.clear(); asyncio.run(LV.manda_anteprima(BD, 900, c_ant, t0))
msg_a = [x for x in BD.mandati if x.get("chat_id") == 900]
fil = [x for x in BD.mandati if x.get("file")]
ok(len(msg_a) == 1 and len(msg_a[0]["text"]) <= 4096 and "file sul canale log" in msg_a[0]["text"]
   and fil and fil[0]["chat_id"] == -3 and fil[0]["file"] == f"avvisi-G{N}.md" and "Squadra 59" in fil[0]["contenuto"],
   "avvisi troppo lunghi: messaggio senza avvisi, file .md sul canale log")
c_v = LV.calcolo(S, N)
for x in c_v["risultati"][1]["st"]["titolari"]:
    x["atleta"] = None
ok("⚠️ quintetto vuoto: Delta" in LV.testo(c_v, t0) and "▶ al momento vince Gamma" not in LV.testo(c_v, t0),
   "quintetto vuoto: nessun esito (non c'è niente da stimare)")
rr = {"punti_casa": 3.0, "punti_trasferta": 0.0, "vince": "trasferta", "supplementari": 5, "esito": {"casa": 3.0, "trasferta": 0.0},
      "sc": {"panchina": []}, "st": {"panchina": []}}
ok(LV.esito_live(rr, "A", "B") == "al momento vince B (nessuna delle due ha la panchina: niente supplementari)", "senza panchine: niente supplementari nel testo")

# ── /dev_prova_live: il live su notti vere (preseason), solo al dev, niente nel database ──
import prova_live as PL
db.q("TRUNCATE ipa_quintetto")
db.q("INSERT INTO ipa_quintetto (team_id, ruolo, giocatore_id, fonte) SELECT team_id, ruolo, giocatore_id, 'prova' FROM ipa_formazioni "
     "WHERE stagione = %s AND giornata = %s AND giocatore_id IS NOT NULL", (S, N))
DP = date(2026, 10, 14)
inizio_p = datetime(2026, 10, 14, 23, 30, tzinfo=timezone.utc)
async def giorno_finto(d):
    return {"events": [{"id": "pre1", "date": inizio_p.isoformat().replace("+00:00", "Z"), "season": {"year": 2027, "type": 1},
                        "competitions": [{"competitors": [{"homeAway": "home", "team": {"abbreviation": "NYK"}},
                                                          {"homeAway": "away", "team": {"abbreviation": "BOS"}}],
                                          "status": {"type": {"name": "STATUS_IN_PROGRESS"}}}]}]}
async def partita_finta(pid):
    return {"boxscore": {"players": [{"team": {"abbreviation": "NYK"}, "statistics": [{"keys": ["minutes", "points"],
            "athletes": [{"athlete": {"id": "r1", "displayName": "Prova 1"}, "starter": True, "stats": ["20", "40"]}]}]}]}}
conta = lambda: (db.q("SELECT count(*) AS n FROM nba_tabellini", one=True)["n"], db.q("SELECT count(*) AS n FROM nba_partite", one=True)["n"],
                 db.q("SELECT count(*) AS n FROM lega_live", one=True)["n"])
prima_db = conta()
import calendario as _cal
stp = {"giorni": [DP], "chat": 900, "vera": _cal.corrente(S), "accoppiamenti": db.partite_giornata(S, N),
       "partite": [], "tabellini": [], "finite": set(), "fatti_10": set(), "message_id": None, "aggiornato": None}
orig = (db.partite_nba, db.tabellini_atleti)
BP = BotL()
asyncio.run(PL.giro(BP, stp, inizio_p + timedelta(minutes=2), forza=True, scarica_giorno=giorno_finto, scarica_partita=partita_finta))
txt = BP.mandati[0]["text"] if BP.mandati else ""
ok(len(BP.mandati) == 1 and BP.mandati[0]["chat_id"] == 900 and "preseason, solo a te" in txt and "🏀 in campo" in txt,
   "prova del live: messaggio solo al dev, con le partite in corso " + txt[:300])
ok(conta() == prima_db and (db.partite_nba, db.tabellini_atleti) == orig, "prova del live: niente scritto nel database, funzioni rimesse a posto")
ok(PL.cosa_fare(stp, inizio_p + timedelta(minutes=5)) is None and PL.cosa_fare(stp, inizio_p + timedelta(minutes=13)) == "live"
   and PL.cosa_fare(stp, datetime(2026, 10, 15, 11, 6, tzinfo=ROMA)) == "controllo", "prova del live: stessi orari del live")
ok(not PL.finita(stp, datetime(2026, 10, 15, 11, 6, tzinfo=ROMA)) and PL.finita(stp, datetime(2026, 10, 15, 11, 20, tzinfo=ROMA)),
   "prova del live: finisce dopo le 11:05 dell'ultimo giorno")
db.q("TRUNCATE ipa_quintetto")

# ── convalida (Luca, 23/10): risultati definitivi sul canale, il live si cancella e non si aggiorna più ──
class BotC(BotL):
    async def delete_message(s, chat_id, message_id): s.mandati.append({"cancellato": message_id, "chat_id": chat_id})
BC = BotC()
LV._salva(S, N, chat_id=-1, message_id=555, chiuso=None, definitivo_id=None)
es = asyncio.run(LV.pubblica_definitivo(BC, S, N, "Admin"))
dfn = [x for x in BC.mandati if x.get("chat_id") == -1 and "risultati definitivi" in x.get("text", "")]
ok(len(dfn) == 1 and "Giornata 7 · risultati definitivi" in dfn[0]["text"] and "Convalidati da Admin" in dfn[0]["text"]
   and {"cancellato": 555, "chat_id": -1} in BC.mandati and "live cancellato" in es, "convalida: risultati definitivi sul canale e live cancellato " + es)
ok("📊 <b>In questa giornata</b>" in dfn[0]["text"] and "🔝 Miglior punteggio" in dfn[0]["text"] and "⭐" in dfn[0]["text"],
   "risultati definitivi: in fondo miglior e peggior punteggio e la prestazione migliore " + dfn[0]["text"][-400:])
ok(LV.stato(S, N)["chiuso"] is not None and LV.stato(S, N)["definitivo_id"] == dfn[0]["id"], "il live risulta chiuso, col messaggio definitivo")
BC.mandati.clear()
asyncio.run(LV.tick(BC, ora=t0 + timedelta(minutes=20), scarica_fn=finta))
ok(not BC.mandati, "live chiuso: il job non lo ripubblica né lo aggiorna")
ok(N not in [g["numero"] for g in LV.giornate_attive(S, t0 + timedelta(minutes=20))],
   "giornata convalidata: fuori dalle giornate attive, quindi anche /live non la ripubblica (Luca, 26/10)")
asyncio.run(LV.pubblica_definitivo(BC, S, N, "Admin"))
ok([x for x in BC.mandati if x.get("modifica") and x.get("id") == dfn[0]["id"]] and not any("cancellato" in x for x in BC.mandati),
   "nuova convalida (dopo un ricalcolo): si modifica lo stesso messaggio definitivo")
ok(not any("cambia un risultato" in x.get("text", "") for x in BC.mandati), "stessi esiti: niente messaggio in più")
_r1 = db.q("SELECT casa, vince FROM lega_risultati WHERE stagione = %s AND giornata = %s AND convalidato IS NOT NULL LIMIT 1", (S, N), one=True)
db.q("UPDATE lega_risultati SET vince = %s WHERE stagione = %s AND giornata = %s AND casa = %s",
     ("trasferta" if _r1["vince"] == "casa" else "casa", S, N, _r1["casa"]))
BC.mandati.clear()
_es = asyncio.run(LV.pubblica_definitivo(BC, S, N, "Admin"))
_avv = [x for x in BC.mandati if "cambia un risultato" in x.get("text", "")]
ok(len(_avv) == 1 and "Ora vince" in _avv[0]["text"] and _avv[0].get("reply_to_message_id") == dfn[0]["id"]
   and any(x.get("modifica") and "Aggiornati dopo il ricontrollo" in x["text"] for x in BC.mandati),
   "cambia chi vince: messaggio definitivo modificato e un avviso in più, in risposta " + _es)
db.q("UPDATE lega_risultati SET vince = %s WHERE stagione = %s AND giornata = %s AND casa = %s", (_r1["vince"], S, N, _r1["casa"]))

# ── /notte (Luca, 21/10) ──
import notte as NT
from datetime import date as _date
ok(NT.notte_di_default(datetime(2026, 11, 11, 10, 0, tzinfo=ROMA)) == _date(2026, 11, 10)
   and NT.notte_di_default(datetime(2026, 11, 11, 20, 0, tzinfo=ROMA)) == _date(2026, 11, 11),
   "notte di default: la mattina quella appena passata, la sera quella di stasera")
_tn = NT.testo_notte(S, config.squadra("team01"), DAL)
ok("notte del 10/11" in _tn and "giornata 7" in _tn and "<b>Quintetto</b>" in _tn and "Titolari stanotte" in _tn
   and ("vs " in _tn or "@ " in _tn),
   "/notte: quintetto e panchina della squadra in quella notte\n" + _tn)

# ── /partita (Luca, 21 e 23/10) ──
import partita as PA
from numeri import testo as tp
_c7 = LV.calcolo(S, N); _r7 = _c7["risultati"][0]
_d7 = PA.dati(S, N, _r7["casa"], _r7["trasferta"])
_s0 = _d7["squadre"][0]
ok(len(_d7["notti"]) == 3 and _d7["notti"][0].endswith(f"{DAL:%d/%m}") and len(_s0["righe"]) >= 5
   and all(len(x["celle"]) == 3 for x in _s0["righe"]) and _s0["lato"] == "casa",
   f"/partita: una colonna per notte (con la data), quintetto e panchina {_d7['notti']}")
_k = {c["k"] for x in _d7["squadre"][0]["righe"] + _d7["squadre"][1]["righe"] for c in x["celle"]}
ok(_k <= {"fp", "dnp", "prossima", "live", "rinviata", "vuota"} and "fp" in _k, f"/partita: celle fp / DNP / vs @ / vuote {_k}")
_png = PA.immagine(_d7)
if _os_pa := __import__("os").environ.get("PARTITA_PNG"): open(_os_pa, "wb").write(_png)
ok(_png[:8] == b"\x89PNG\r\n\x1a\n" and len(_png) > 20000, "/partita: immagine Typst")
_sl = db.q("SELECT * FROM lega_risultati WHERE stagione = %s AND giornata = %s AND casa = %s", (S, N, _r7["casa"]), one=True)
if _sl and _sl.get("convalidato"):
    db.q("UPDATE lega_risultati SET punti_casa = punti_casa + 1 WHERE stagione = %s AND giornata = %s AND casa = %s", (S, N, _r7["casa"]))
    _d8 = PA.dati(S, N, _r7["casa"], _r7["trasferta"])
    ok(_d8["squadre"][0]["punti"] == tp(float(_sl["punti_casa"]) + 1) and "risultato convalidato" in _d8["note"][0],
       "giornata convalidata: in testa il risultato salvato; se il ricalcolo di oggi differisce lo dice")
    db.q("UPDATE lega_risultati SET punti_casa = punti_casa - 1 WHERE stagione = %s AND giornata = %s AND casa = %s", (S, N, _r7["casa"]))
_sq = config.squadre()
ok(PA.leggi_argomenti(["Alfa", "G3"], _sq)[:2] == ([config.squadra("team01")], 3), "/partita Alfa G3")
ok([t["id"] for t in PA.leggi_argomenti(["Alfa", "-", "Beta"], _sq)[0]] == ["team01", "team02"]
   and [t["id"] for t in PA.leggi_argomenti(["Alfa", "Beta"], _sq)[0]] == ["team01", "team02"], "/partita Alfa - Beta e Alfa Beta")
ok(PA.leggi_argomenti(["Nessunaaa", "Zzzz"], _sq)[2], "squadra che non c'è: errore")
_conv = {x["giornata"] for x in db.q("SELECT giornata FROM lega_calcoli WHERE stagione = %s AND stato = 'convalidata'", (S,), many=True) or []}
_aperte = [g["numero"] for g in db.giornate(S) if g["numero"] not in _conv]
ok(PA.giornata_di_default(S)["numero"] == (min(_aperte) if _aperte else max(g["numero"] for g in db.giornate(S))),
   "giornata di default: la prima non convalidata (la stessa fino alla convalida)")
from datetime import date as _dd
_vg, _vq = PA.db.giornate, PA.db.q
PA.db.giornate = lambda s_: [{"numero": 1, "dal": _dd(2026, 10, 20), "al": _dd(2026, 10, 22)},
                             {"numero": 2, "dal": _dd(2026, 10, 23), "al": _dd(2026, 10, 25)}]
PA.db.q = lambda sql, params=None, **k: [{"giornata": 1}] if "stato = 'convalidata'" in sql else _vq(sql, params, **k)
ok(PA.giornata_di_default(S, datetime(2026, 10, 23, 15, 59, tzinfo=ROMA))["numero"] == 1
   and PA.giornata_di_default(S, datetime(2026, 10, 23, 16, 0, tzinfo=ROMA))["numero"] == 2,
   "G1 convalidata: la G2 solo dalle 16 del suo primo giorno, prima ancora la G1")
PA.db.q = lambda sql, params=None, **k: [] if "stato = 'convalidata'" in sql else _vq(sql, params, **k)
ok(PA.giornata_di_default(S, datetime(2026, 10, 24, 12, 0, tzinfo=ROMA))["numero"] == 1, "G1 non ancora convalidata: resta la G1")
# /giornata e /risultati senza numero: la stessa giornata di /partita (Luca, 25/10)
import calendario as _CAL, handlers as _HG
_vista = []
class _MsgG:
    async def reply_text(self, t, **k): _vista.append(t)
_vero_dm = _CAL.da_mostrare
_CAL.da_mostrare = lambda s_, ora=None: db.giornate(s_)[0]
import nba as _NBg
_vog = _NBg.oggi_et; _NBg.oggi_et = lambda: _dd(2026, 10, 1)   # giornata non ancora iniziata: l'elenco delle partite
asyncio.run(_HG.cmd_giornata(types.SimpleNamespace(effective_message=_MsgG(), effective_user=types.SimpleNamespace(id=900)),
                             types.SimpleNamespace(args=[], bot=None)))
_CAL.da_mostrare = _vero_dm
_NBg.oggi_et = _vog
ok(_vista and f"iornata {db.giornate(S)[0]['numero']}" in _vista[0] and PA.giornata_di_default(S) == _CAL.da_mostrare(S),
   "/giornata e /risultati senza numero: stessa regola di /partita (la finita resta fino alle 16 del primo giorno della nuova)")
PA.db.giornate, PA.db.q = _vg, _vq
ok(PA.sfide(S, _r7["casa"], _r7["trasferta"]) and all(x["giornata"] for x in PA.sfide(S, _r7["casa"])), "sfide tra due squadre")

# ── /player ──
import player as PLY
gid1 = next(v for k, v in gid.items() if db.q("SELECT espn_id FROM giocatori WHERE id = %s", (v,), one=True)["espn_id"] == "r1")
sc = PLY.scheda(gid1)
ok("🇺🇸 NBA:" in sc and "🏆 Fantabasket: <b>" in sc and "media <b>" in sc and "Ultime partite" in sc and "fantapunti" in sc,
   "/player: NBA, fantabasket, media e ultime partite\n" + sc)
# data di nascita ed età; partite saltate di fila in una riga sola (Luca, 25/10)
from datetime import date as _dd
ok(PLY.eta(_dd(2004, 1, 4), _dd(2026, 1, 3)) == 21 and PLY.eta(_dd(2004, 1, 4), _dd(2026, 1, 4)) == 22, "/player: età giusta il giorno prima e il giorno del compleanno")
db.q("UPDATE giocatori SET data_nascita = '2004-01-04' WHERE id = %s", (gid1,))
ok("🎂 04/01/2004 (" in PLY.scheda(gid1), "/player: data di nascita con l'età")
db.q("UPDATE giocatori SET data_nascita = NULL WHERE id = %s", (gid1,))
_P = lambda i, d: {"espn_id": f"x{i}", "data_et": d, "casa": "NYK", "trasferta": "BOS", "squadra": "NYK"}
_parts = [_P(i, _dd(2026, 11, i)) for i in range(1, 15)]
_tb = [{"partita": "x1", "data_et": _dd(2026, 11, 1), "squadra": "NYK", "casa": "NYK", "trasferta": "BOS", "minuti": 30, "pts": 20,
        "oreb": 1, "dreb": 4, "ast": 3, "fp": 30.5, "giocato": True},
       {"partita": "x12", "data_et": _dd(2026, 11, 12), "squadra": "NYK", "casa": "NYK", "trasferta": "BOS", "minuti": 0, "pts": 0,
        "oreb": 0, "dreb": 0, "ast": 0, "fp": 0, "giocato": False},
       {"partita": "x14", "data_et": _dd(2026, 11, 14), "squadra": "NYK", "casa": "NYK", "trasferta": "BOS", "minuti": 25, "pts": 10,
        "oreb": 0, "dreb": 3, "ast": 2, "fp": 18.0, "giocato": True}]
_ul = PLY.ultime(_tb, _parts)
ok(any("dal 02/11 al 11/11: <i>10 partite saltate</i>" in x for x in _ul) and any("13/11 vs BOS: <i>saltata</i>" in x for x in _ul)
   and any("12/11" in x and "non è entrato" in x for x in _ul) and len(_ul) == 5,
   f"/player: 10 saltate di fila in una riga, una sola «saltata», «non è entrato» a parte {_ul}")
ok(PLY.testo_su(_parts) == " su 14 della squadra"
   and PLY.testo_su([{**x, "arrivato": _dd(2026, 11, 1)} for x in _parts]) == " su 14 da quando è a NYK (dal 01/11)"
   and PLY.testo_su(_parts[:3] + [{**x, "squadra": "BOS"} for x in _parts[3:5]]) == " su 5 (NYK poi BOS)",
   "/player: partite giocate su quelle della squadra, da quando è arrivato, o con lo scambio")
# media della stagione prima, da Basketball-Reference (Luca, 26/10): bref numera col secondo anno
_nb = db.q("SELECT nome_common FROM giocatori WHERE id = %s", (gid1,), one=True)["nome_common"]
_tabb = db.q("SELECT to_regclass('bref_stats') AS t", one=True)["t"]
if _tabb:
    db.q("""INSERT INTO bref_stats (timestamp, stagione, nome_bref, g, pts, fga, fgm, ftm, fta, fg3m, orb, drb, ast, stl, blk, tov)
            VALUES (NOW(), %s, %s, 70, 20, 15, 7, 4, 5, 2, 1, 5, 4, 1, 1, 2)""", (str(int(S)), _nb))
    db.q("""INSERT INTO bref_stats (timestamp, stagione, nome_bref, g, pts, fga, fgm, ftm, fta, fg3m, orb, drb, ast, stl, blk, tov)
            VALUES (NOW(), %s, %s, 10, 40, 15, 7, 4, 5, 2, 1, 5, 4, 1, 1, 2)""", (str(int(S) + 1), _nb))
    _ap = PLY.anno_prima(gid1, S)
    ok(_ap and f"Stagione {int(S) - 1}-{str(S)[-2:]}" in _ap and "in 70 partite" in _ap and _ap in PLY.scheda(gid1),
       f"/player: media della stagione prima (la riga di bref di quella stagione, non di quella in corso) {_ap}")
    db.q("DELETE FROM bref_stats WHERE nome_bref = %s", (_nb,))
else:
    ok(PLY.anno_prima(gid1, S) is None, "/player: senza bref_stats niente media della stagione prima (e niente errori)")
ok(PLY.cerca("prova 1") and PLY.cerca("prova 1")[0]["id"] == gid1, "/player: ricerca per nome")
db.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s, 'team01', 12, 3, %s, 'normale')",
     (gid1, S))
sc = PLY.scheda(gid1)
ok("🏆 Fantabasket: <b>Alfa</b>" in sc and "12M × 3 anni rimasti" in sc and "📋 Posizioni eleggibili" in sc and "🎽 Ruolo" in sc,
   "/player: posizioni eleggibili, squadra, ruolo e stato del contratto\n" + sc)
db.q("UPDATE contratti SET stagione_firma = %s WHERE giocatore_id = %s", (str(int(S) - 3), gid1))
ok((PLY.NOTA_FIRMA in sc) == (str(S) == PLY.ANNO_BOT), "/player: firmato nella prima stagione del bot → nota in corsivo sull'anno di firma")
ok(PLY.NOTA_FIRMA not in PLY.scheda(gid1) and "contratto finito (x0)" in PLY.scheda(gid1), "/player: contratto x0 e RFA (firmato prima: niente nota)")
db.q("DELETE FROM contratti WHERE giocatore_id = %s", (gid1,))
ok("svincolato</b> (free agent)" in PLY.scheda(gid1), "/player: svincolato")
# diritti di una 2nd non firmata: la scadenza dalla regola (10 giorni prima della deadline della stagione dopo il draft)
_Sx = int(S)
ok(PLY.scadenza_diritti({"round": 2, "anno_draft": str(_Sx)}, S) == f"scadono 10 giorni prima della trade deadline del {_Sx + 1}-{str(_Sx + 2)[-2:]}"
   and PLY.scadenza_diritti({"round": 1, "anno_draft": str(_Sx)}, S) == "",
   "/player: diritti del draft di quest'anno, scadono nella stagione dopo; le prime scelte niente scadenza")
_G = json.load(open(os.environ["GLOBALS_PATH"])); _dl = _G.get("trade_deadline"); _G["trade_deadline"] = f"{_Sx + 1}-02-05"; json.dump(_G, open(os.environ["GLOBALS_PATH"], "w"))
ok(PLY.scadenza_diritti({"round": 2, "anno_draft": str(_Sx - 1)}, S) == f"scadono il 26/01/{_Sx + 1}, 10 giorni prima della trade deadline",
   "/player: diritti al secondo anno, con la deadline fissata: la data (deadline − 10 giorni)")
_G.pop("trade_deadline") if _dl is None else _G.update(trade_deadline=_dl); json.dump(_G, open(os.environ["GLOBALS_PATH"], "w"))
# ── foto ESPN (Luca, 23/10): di notte una alla volta, poi /player con la foto ──
import foto as FO, tempfile, os
FO.CARTELLA = tempfile.mkdtemp(); FO.INDICE = os.path.join(FO.CARTELLA, "indice.json")
db.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s, 'team01', 5, 2, %s, 'normale')", (gid1, S))
ok("r1" in FO.da_scaricare(), "foto: il giocatore a roster senza foto è in coda")
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 3000
class _Risp:
    def __init__(s, c, b): s.status_code, s.content = c, b
class _Cli:
    def __init__(s, codici): s.codici, s.url = list(codici), []
    async def get(s, url): s.url.append(url); c = s.codici.pop(0); return _Risp(c, PNG if c == 200 else b"")
    async def aclose(s): pass
_c = _Cli([404, 200])
ok(asyncio.run(FO.scarica("r1", _c)) and FO.percorso("r1") and "combiner" in _c.url[0] and "w=520" in _c.url[0] and "full/r1.png" in _c.url[1],
   "foto: prima la piccola (combiner), se non c'è l'intera; salvata in cartella")
ok("r1" not in FO.da_scaricare(), "foto presa: esce dalla coda")
ok(not asyncio.run(FO.scarica("r2", _Cli([404, 404]))) and FO._indice()["r2"].get("mancante"), "foto che ESPN non ha: segnata mancante")
import base64 as _b64                      # una PNG vera (1×1 trasparente) per comporre la foto con Typst
open(os.path.join(FO.CARTELLA, "r1.png"), "wb").write(_b64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="))
_im = PLY.immagine(gid1, FO.percorso("r1"))
ok(_im[:8] == b"\x89PNG\r\n\x1a\n" and len(_im) > 5000, "/player: la foto composta su sfondo viola (Typst)")
_inviate = []
class _MsgF:
    async def reply_photo(s, f, caption=None, **k): _inviate.append(("foto", caption))
    async def reply_text(s, t, **k): _inviate.append(("testo", t))
asyncio.run(PLY.manda(_MsgF(), gid1))
ok(_inviate and _inviate[0][0] == "foto" and (_inviate[0][1] or (len(_inviate) > 1 and "Prova 1" in _inviate[1][1])),
   "/player con la foto (didascalia, o foto e testo sotto se lungo)")
ok(asyncio.run(FO.job_foto(types.SimpleNamespace())) is None, "job delle foto: fuori dalla notte americana non fa niente (o una sola foto)")
db.q("DELETE FROM contratti WHERE giocatore_id = %s", (gid1,))
# 7:45: prima del calcolo riscarica TUTTI i tabellini della giornata, anche quelli presi nella notte (Luca, 24/10)
import handlers_calcolo as _HC3
_ord, _logs = [], []
async def _sinc(*a, **k): _ord.append("sincronizza")
async def _agg(*a, **k): _ord.append("mancanti")
async def _risc(g): _ord.append("riscarica"); return {("p", "a"): ((10.0, 30, "X"), (12.0, 30, "X"))}
async def _es(bot, s_, n_, *a, **k): _ord.append("calcolo")
async def _lg(bot, t): _logs.append(t)
import handlers as _HH
_salva = (HR.nba.sincronizza, _HC3.aggiorna_tabellini, HR._riscarica, HR.pronta, HR.esegui, HR.db.giornate, HR.nba.oggi_et, _HH.log)
HR.nba.sincronizza, _HC3.aggiorna_tabellini, HR._riscarica, HR.esegui, _HH.log = _sinc, _agg, _risc, _es, _lg
HR.pronta = lambda s_, g: None
HR.db.giornate = lambda s_: [{"numero": 99, "dal": date(2030, 1, 1), "al": date(2030, 1, 2), "stagione": s_}]
HR.nba.oggi_et = lambda: date(2030, 1, 3)
asyncio.run(HR.job_calcolo(types.SimpleNamespace(bot=BOT)))
(HR.nba.sincronizza, _HC3.aggiorna_tabellini, HR._riscarica, HR.pronta, HR.esegui, HR.db.giornate, HR.nba.oggi_et, _HH.log) = _salva
ok(_ord == ["sincronizza", "mancanti", "riscarica", "calcolo"] and any("1 righe di tabellino corrette" in t for t in _logs),
   f"calcolo delle 7:45: riscarica tutti i tabellini della giornata prima di calcolare, e dice se ESPN ne ha corretti {_ord}")
# ── congelamento per notte (v58, Luca 30/10, come Yahoo): ogni notte si ricontrolla fino alle 20 del giorno dopo ──
from datetime import date as _dg
_GG = [{"numero": i, "dal": _dg(2026, 10, 20) + timedelta(days=3 * (i - 1)), "al": _dg(2026, 10, 21) + timedelta(days=3 * (i - 1))}
       for i in range(1, 7)]                      # G4: notti del 29 e del 30/10
_vgg = CG.db.giornate
CG.db.giornate = lambda s_: _GG
db.q("DELETE FROM lega_congelamento"); CG.migra(); db.q("DELETE FROM lega_notti_congelate")
_R = lambda g, m, h, mi=0: datetime(2026, m, g, h, mi, tzinfo=ROMA)
ok(not CG.notte_congelata(_dg(2026, 10, 29), S, _R(30, 10, 19, 59)) and CG.notte_congelata(_dg(2026, 10, 29), S, _R(30, 10, 20)),
   "la notte del 29/10 si congela alle 20 del 30/10")
_st = CG.stati(S, _R(31, 10, 12))
ok(_st[4]["stato"] == "aperta" and _st[3]["stato"] == "congelata" and _st[5]["stato"] in ("in corso", "da giocare"),
   "giornata finita: aperta finché l'ultima notte non è congelata, le precedenti congelate")
ok(CG.stati(S, _R(31, 10, 20, 1))[4]["stato"] == "congelata", "alle 20 del giorno dopo l'ultima notte: la giornata è congelata")
CG.adesso = lambda: _R(31, 10, 12)
CG.oggi_et = lambda: _dg(2026, 10, 31)
class _MsgC:
    def __init__(s): s.t = []
    async def reply_text(s, t, **k): s.t.append(t)
class _BotC:
    def __init__(s): s.m = []
    async def send_message(s, chat_id, text, **k): s.m.append((chat_id, text))
def _cmd(f, args, uid=900):
    m, b = _MsgC(), _BotC()
    asyncio.run(f(types.SimpleNamespace(effective_message=m, effective_user=types.SimpleNamespace(id=uid, full_name="Admin")),
                  types.SimpleNamespace(args=args, bot=b)))
    return m.t, b.m
_t, _m = _cmd(CG.cmd_congela, ["4"])
ok(CG.congelata(S, 4) and CG.stati(S)[4]["a_mano"] and CG.notte_congelata(_dg(2026, 10, 30), S)
   and any(c == -1 and "Giornata 4 congelata" in x for c, x in _m) and any(c == -3 for c, x in _m),
   "/congela 4: tutte le sue notti congelate (anche quella ancora aperta), sul canale principale e sul log")
_t, _m = _cmd(CG.cmd_scongela, ["G1"])
ok(not CG.congelata(S, 1) and not CG.notte_congelata(_dg(2026, 10, 20), S) and any("Giornata 1 scongelata" in x for c, x in _m if c == -1),
   "/scongela G1: le notti della vecchia si riaprono")
db.q("DELETE FROM lega_congelamento")
_t, _m = _cmd(CG.cmd_scongela_notte, ["27/10"])
ok(not CG.notte_congelata(_dg(2026, 10, 27), S) and CG.stati(S)[3]["stato"] == "aperta" and any("Notte del 27/10 scongelata" in x for c, x in _m if c == -1),
   "/scongela_notte 27/10: quella notte si riapre (e la sua giornata torna aperta)")
_t, _m = _cmd(CG.cmd_congela_notte, ["30/10"])
ok(CG.notte_congelata(_dg(2026, 10, 30), S) and CG.stati(S)[4]["stato"] == "congelata", "/congela_notte 30/10: congelata prima delle 20")
ok(_cmd(CG.cmd_congela_notte, ["31/10"])[0][0].startswith("La notte del 31/10 non è ancora finita")
   and _cmd(CG.cmd_congela_notte, ["29/10"], uid=101)[0] == ["⛔ Solo admin."], "/congela_notte: solo notti finite, solo admin")
_tn = CG.testo_notti(S, _R(31, 10, 12))
ok("🧊 30/10 (G4): congelata <i>(a mano)</i>" in _tn and "🧊 29/10 (G4): congelata" in _tn and "🔄 27/10" in _tn,
   f"/congelamento_notti: le notti delle ultime giornate, con le scelte a mano {_tn}")
_reg = [r["azione"] for r in db.q("SELECT azione FROM registro_azioni WHERE bot = 'louca' ORDER BY id", many=True)]
ok("giornata congelata" in _reg and "notte scongelata" in _reg and "notte congelata" in _reg, "congela e scongela (giornate e notti) nel registro")
CG.db.giornate = _vgg
db.q("DELETE FROM lega_congelamento"); db.q("DELETE FROM lega_notti_congelate")
CG.adesso = lambda: datetime(2026, 11, 1, tzinfo=timezone.utc)      # le notti della giornata N (novembre) ancora aperte
# una notte congelata non si riscarica (v58): la partita g1 col tabellino, a notte congelata, si tiene
db.q("INSERT INTO lega_notti_congelate (data_et, congelata) VALUES (%s, TRUE)", (_d1,))
ok(CG.da_tenere(["g1"]) == {"g1"}, "notte congelata: la partita col tabellino non si riscarica")
db.q("DELETE FROM lega_notti_congelate")
ok(CG.da_tenere(["g1"]) == set(), "notte aperta: si riscarica")
# /correggi_tabellino: i fantapunti di una partita, senza riscaricare; registro, canale log, canale principale
ok(CG.leggi_correzione(["Norman", "Powell", "G1", "16"]) == ("Norman Powell", 1, 16.0, None)
   and CG.leggi_correzione(["Powell", "1", "16,5", "24/10"]) == ("Powell", 1, 16.5, (24, 10)) and CG.leggi_correzione(["Powell", "16"]) is None,
   "/correggi_tabellino: lettura di nome, giornata, valore e data")
CG.oggi_et = lambda: db.giornata(S, N)["al"] + timedelta(days=1)
_fp_prima = db.q("SELECT partita, atleta, fp FROM nba_tabellini", many=True)
_nome12 = db.q("SELECT nome_common FROM giocatori WHERE espn_id = 'r1'", one=True)["nome_common"]
_d12 = db.q("""SELECT p.data_et FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
               WHERE t.atleta = 'r1' ORDER BY p.inizio LIMIT 1""", one=True)["data_et"]
_t, _m = _cmd(CG.cmd_correggi, _nome12.split() + [f"G{N}", "33"])
ok(_m == [] and "aggiungi la data" in _t[0],
   "/correggi_tabellino: più partite nella giornata → chiede la data, coi comandi già scritti")
_t, _m = _cmd(CG.cmd_correggi, _nome12.split() + [f"G{N}", "33", f"{_d12:%d/%m}"])
ok(float(db.q("""SELECT t.fp FROM nba_tabellini t JOIN nba_partite p ON p.espn_id = t.partita
                 WHERE t.atleta = 'r1' AND p.data_et = %s""", (_d12,), one=True)["fp"]) == 33.0
   and any(c == -1 and "Correzione G" in x and "→ <b>33,00</b>" in x for c, x in _m) and any(c == -3 for c, x in _m)
   and "/ricalcola" in _t[0] and "/congela" in _t[0],
   f"/correggi_tabellino: corretto, sul canale principale e sul log; giornata aperta: avviso che ESPN può rimetterlo {_t}")
for _x in _fp_prima:
    db.q("UPDATE nba_tabellini SET fp = %s WHERE partita = %s AND atleta = %s", (_x["fp"], _x["partita"], _x["atleta"]))
# una giornata congelata non si riscarica, nemmeno con /ricalcola o alle 7:45 (v58: il filtro è in scarica_tabellini)
db.q("INSERT INTO lega_congelamento (stagione, giornata, congelata) VALUES (%s, %s, TRUE)", (S, N))
_scar = []
async def _fs(pid):
    _scar.append(pid); return {}
_rr = asyncio.run(HR.nba.scarica_tabellini(["g1"], scarica=_fs, pausa=0))
ok(not _scar and _rr["congelate"] == 1, "giornata congelata: i tabellini già presi non si riscaricano")
_rr = asyncio.run(HR.nba.scarica_tabellini(["g1"], scarica=_fs, pausa=0, forza=True))
ok(_scar == ["g1"], "il controllo finale (forza) riscarica anche a notte congelata")
db.q("DELETE FROM lega_congelamento")
# Top 20 della notte (Luca, 30/10): schierati in classifica, sotto i firmati non schierati che sarebbero entrati
import top as TOP
for _g in gid.values():
    db.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s, 'team01', 5, 2, %s, 'normale')", (_g, S))
_tt = TOP.testo(S, _d1)
_sch = TOP.schierati(S, db.giornata(S, N))
_tutte = TOP.righe_notte(_d1)
ok(_tt and f"Top 20 della notte</b> · {_d1:%d/%m} (G{N})" in _tt and "1. <b>" in _tt and "non ancora ricontrollati" in _tt
   and "Prestazioni notevoli" not in _tt and _sch and all(r["giocatore_id"] in _sch for r in _tutte),
   "top 20 della notte: schierati, coi fantapunti; tutti schierati → niente prestazioni notevoli\n" + (_tt or ""))
_primo = _tutte[0]
_vs = TOP.schierati
TOP.schierati = lambda s_, g_: {k: v for k, v in _vs(s_, g_).items() if k != _primo["giocatore_id"]}
_tt2 = TOP.testo(S, _d1)
TOP.schierati = _vs
ok("👀 <b>Prestazioni notevoli di giocatori firmati non schierati</b>" in _tt2
   and _tt2.index(_primo["nome"]) > _tt2.index("Prestazioni notevoli"),
   "top 20: un firmato non schierato da top 20 va sotto, nelle prestazioni notevoli")
ok(TOP.testo(S, _d1 - timedelta(days=400)) is None, "top 20: notte fuori dalle giornate, niente messaggio")
_inv = []
class _BotT:
    async def send_message(self, chat, t, **k): _inv.append((chat, t))
_vg = config.globali
config.globali = lambda: dict(_vg(), gruppo_lega_id=-100777)
_vieri = TOP.ieri
TOP.ieri = lambda: _d1
asyncio.run(TOP.job_top_notte(types.SimpleNamespace(bot=_BotT())))
config.globali = _vg
asyncio.run(TOP.job_top_notte(types.SimpleNamespace(bot=_BotT())))
TOP.ieri = _vieri
ok(len(_inv) == 1 and _inv[0][0] == -100777 and "Top 20" in _inv[0][1], "top 20: alle 9 nel gruppo della lega; senza gruppo_lega_id non pubblica")
# controllo del tanking, parte 1 (Luca, 25/10 e 30/10): indizi al gruppo admin il mattino dopo la prima notte
import tanking as TK
ok(TK.nettamente_meglio(20, 12) and TK.nettamente_meglio(13.5, 10) and not TK.nettamente_meglio(12, 10)
   and not TK.nettamente_meglio(5, 0) and TK.nettamente_meglio(8, 0), "tanking: soglia +8 di media oppure +30%")
_G = lambda gid_, nome, media, partite, stato=None, pos=("SF",): {"gid": gid_, "nome": nome, "media": media, "partite": partite,
                                                               "stato": stato, "posizioni": set(pos)}
_sq = {"quintetto": {"PG": 1, "SG": 2, "SF": 3, "PF": 4, "C": None},
       "panchina": None,
       "giocatori": {1: _G(1, "Titolare Out", 25, 2, "Out", ("PG",)), 2: _G(2, "Titolare Senza Partite", 10, 0, None, ("SG",)),
                     3: _G(3, "Titolare Scarso", 10, 2), 4: _G(4, "Titolare Ok", 30, 2, None, ("PF",)),
                     5: _G(5, "Escluso Forte", 24, 2, None, ("SF", "PG")), 6: _G(6, "Escluso Out", 50, 2, "Out", ("SF", "PF")),
                     7: _G(7, "Escluso Senza Partite", 60, 0, None, ("SG", "SF"))}}
_ind = TK.indizi(_sq)
_j = "\n".join(_ind)
ok(any(x.startswith("• PG: titolare <b>indisponibile</b> Titolare Out") and "Escluso Forte" in x for x in _ind)
   and any(x.startswith("• SF: Titolare Scarso") and "fuori Escluso Forte" in x and "+14,00" in x for x in _ind)
   and "C: <b>posto vuoto</b>" in _j and "panchina non mandata" in _j
   and "SG:" not in _j and "PF:" not in _j and "Escluso Out" not in _j and "Escluso Senza Partite" not in _j,
   "tanking: titolare indisponibile con un sano in rosa, escluso nettamente migliore, posto vuoto, panchina; "
   "niente per chi non ha partite (prende la media) né per gli esclusi infortunati o senza partite\n" + _j)
# escluso che adesso ha un altro ruolo: si segnala che servirebbe un cambio ruolo (Luca, 31/10)
_sqr = {**_sq, "giocatori": {**_sq["giocatori"], 5: {**_sq["giocatori"][5], "ruolo": "PG"}}}
_indr = TK.indizi(_sqr)
ok(any(x.startswith("• SF:") and "ora è PG: servirebbe un cambio ruolo" in x for x in _indr)
   and not any(x.startswith("• PG:") and "cambio ruolo" in x for x in _indr),
   "tanking: escluso di un altro ruolo → segnalato che servirebbe un cambio ruolo (nel suo ruolo no)")
_ok2 = TK.indizi({"quintetto": {"PG": 5, "SG": 2, "SF": 3, "PF": 4, "C": 8}, "panchina": [{"giocatore_id": 7}],
                  "giocatori": {5: _G(5, "A", 24, 2, None, ("PG",)), 2: _G(2, "B", 10, 0, None, ("SG",)), 3: _G(3, "C", 21, 2),
                                4: _G(4, "D", 30, 2, None, ("PF",)), 8: _G(8, "E", 15, 2, None, ("C",)), 7: _G(7, "F", 60, 0, None, ("C",))}})
ok(_ok2 == [], f"tanking: formazione plausibile, nessun indizio {_ok2}")
_tk = TK.testo(S, db.giornata(S, N))
ok(f"Controllo tanking · giornata {N}" in _tk and "Delta" in _tk and "posto vuoto" in _tk and "panchina non mandata" in _tk
   and "Solo per gli admin" in _tk, "tanking: il report della giornata (Delta senza panchina e con un posto vuoto)\n" + _tk[:600])
# lo stato è quello alla scadenza: uno status deciso da un admin (per la FADD) non conta qui (Luca, 31/10)
db.set_status_valido(S, N, "r25", "Out", 900)
_d0 = TK.dati(S, db.giornata(S, N))
db.togli_status_valido(S, N, "r25")
ok(next(x for x in _d0["team01"]["giocatori"].values() if x["atleta"] == "r25")["stato"] is None,
   "tanking: lo status deciso da un admin per la FADD non conta, vale l'injury report alla scadenza")
_vgo = TK.giornata_di_oggi
TK.giornata_di_oggi = lambda s_: db.giornata(S, N)
_mt = []
class _BotK:
    async def send_message(self, chat_id, text, **k): _mt.append((chat_id, text))
asyncio.run(TK.job_tanking(types.SimpleNamespace(bot=_BotK())))
TK.giornata_di_oggi = _vgo
ok(_mt and _mt[0][0] == config.gruppo_admin() and "Controllo tanking" in _mt[0][1], "tanking: il mattino dopo la prima notte, solo al gruppo admin")
# /dev_foto (v6.9.0): quante foto dei giocatori a roster, quali mancano
import foto as FT, tempfile as _tf
_cart = _tf.mkdtemp()
FT.CARTELLA, FT.INDICE = _cart, os.path.join(_cart, "indice.json")
open(os.path.join(_cart, "r1.png"), "wb").write(b"\x89PNG\r\n\x1a\n" + b"0" * 2000)
FT._salva_indice({"r1": {"preso": datetime.now(timezone.utc).isoformat(), "squadra": "NYK"},
                  "r2": {"preso": datetime.now(timezone.utc).isoformat(), "squadra": "NYK", "mancante": True}})
_sf = FT.stato_foto()
ok(_sf["roster"] >= len(gid) and _sf["con_foto"] == 1 and [x["espn_id"] for x in _sf["espn_non_ha"]] == ["r2"]
   and len(_sf["da_prendere"]) + len(_sf["senza_espn"]) == _sf["roster"] - 2 and _sf["in_cartella"] == 1, f"/dev_foto: presenti, ESPN non ce l'ha, da prendere {_sf['roster']}")
# tutti i giocatori attivi in NBA (Luca, 30/10), dopo quelli a roster
db.q("INSERT INTO nba_atleti (atleta, nome, squadra) VALUES ('zz9', 'Attivo Non Firmato', 'NYK'), ('zz8', 'Fuori Roster', NULL) ON CONFLICT DO NOTHING")
_coda = FT.da_scaricare()
_rost = [a for a in _coda if a.startswith("r")]
ok("zz9" in _coda and "zz8" in _coda and "r1" not in _coda and _coda.index("zz9") > max(_coda.index(a) for a in _rost)
   and _coda.index("zz8") > _coda.index("zz9") and FT.stato_foto()["attivi"] >= 1 and FT.stato_foto()["tutti"] >= len(gid) + 2,
   "foto: dopo quelli a roster tutti gli attivi in NBA, poi tutti gli altri del database")
# chi non gioca: foto rinnovata dopo 90 giorni (non 14), mancante riprovata dopo 30 (non 3)
_vi = FT._indice()
_vi["zz8"] = {"preso": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(), "squadra": None}
_vi["zz9"] = {"preso": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(), "squadra": "NYK"}
FT._salva_indice(_vi)
open(os.path.join(_cart, "zz8.png"), "wb").write(b"x"); open(os.path.join(_cart, "zz9.png"), "wb").write(b"x")
_coda = FT.da_scaricare()
ok("zz9" in _coda and "zz8" not in _coda, "foto vecchia di 20 giorni: si rinnova per chi gioca, non per chi è fuori dalla NBA")
for _x in ("zz8", "zz9"):
    os.remove(os.path.join(_cart, f"{_x}.png"))
db.q("DELETE FROM nba_atleti WHERE atleta IN ('zz9', 'zz8')")
_rf = []
class _MsgF:
    async def reply_text(self, t, **k): _rf.append(t)
asyncio.run(FT.cmd_dev_foto(types.SimpleNamespace(effective_user=types.SimpleNamespace(id=config.dev_id()), effective_message=_MsgF()), None))
ok(_rf and "1 su " in _rf[0] and "ESPN non ce l'ha" in _rf[0], "/dev_foto: il messaggio al dev")
db.q("DELETE FROM contratti WHERE giocatore_id = ANY(%s)", (list(gid.values()),))
# pulizia
db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (list(gid.values()),))
db.q("TRUNCATE nba_tabellini, nba_infortuni, lega_giornate, lega_partite, nba_partite, lega_risultati, lega_calcoli, lega_calcoli_storico, lega_live")
db.q("TRUNCATE ipa_formazioni, ipa_panchine, ipa_stato_giornata")
_ = (asyncio, json, types)

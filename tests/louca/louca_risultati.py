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
     "lega_calcoli, lega_status_validi")
db.q("TRUNCATE ipa_formazioni, ipa_panchine, ipa_stato_giornata")
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
   and any("tolto dalla panchina" in str(x) for x in _cel) and not any(str(x).startswith("=") for x in _cel),
   "alla scadenza: tab «Calcolo GN» coi soli schierati (quintetti, panchine in ordine), niente formule")
ok(asyncio.run(FF.aggiorna(ora=_t0 + timedelta(hours=1), manda=_gas_ff)) == [] and len(_inviati) == 1, "niente cambi: non riscrive")
db.q("UPDATE ipa_formazioni SET giocatore_id = %s WHERE stagione = %s AND giornata = %s AND team_id = 'team01' AND ruolo = 'C'",
     (gid[16], S, N))
ff2 = asyncio.run(FF.aggiorna(ora=_t0 + timedelta(hours=2), manda=_gas_ff))
ok(len(ff2) == 1 and "aggiornate" in ff2[0] and len(_inviati) == 2, "un admin corregge una formazione: il tab si riscrive")
db.q("UPDATE ipa_formazioni SET giocatore_id = %s WHERE stagione = %s AND giornata = %s AND team_id = 'team01' AND ruolo = 'C'",
     (gid[9], S, N))
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
ok(len(r2["sc"]["panchina"]) == 2 and "r21" not in [x["atleta"] for x in r2["sc"]["panchina"]]
   and any("Gamma: titolare e anche in panchina: Prova 21" in a for a in c["avvisi"]),
   "dopo la FADD la panchina di Gamma scala; r21, titolare e anche in panchina, esce dalla panchina (con l'avviso)")
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
    doppio = lambda r: r[1].startswith("P") and "tolto dalla panchina" in r[-1]
    diversi = [(r[3], r[ip], c["punti"][nomi[r[3]]]["fp"]) for r in foglio if len(r) > ip and r[3] in nomi and not doppio(r)
               and num(r[ip]) != c["punti"][nomi[r[3]]]["fp"]]
    ok(not diversi, f"punteggio di ogni giocatore: foglio = bot {diversi[:3]}")
    dd = [r for r in foglio if len(r) > ip and r[3] == "Prova 21" and doppio(r)]
    ok(len(dd) == 1 and num(dd[0][ip]) == 0, f"foglio: il titolare che è anche in panchina, lì vale 0 e senza ordine {dd}")
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
db.q("DELETE FROM lega_calcoli"); db.q("DELETE FROM lega_risultati")
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
_reg = db.q("SELECT veste, azione, chi_id, dopo FROM registro_azioni WHERE bot = 'louca' ORDER BY id", many=True)
ok([(r["veste"], r["azione"]) for r in _reg] == [("sistema", "giornata calcolata"), ("sistema", "giornata ricalcolata"),
                                                  ("admin", "giornata convalidata")] and _reg[-1]["chi_id"] == 900,
   f"registro: calcolo e ricalcolo del job (sistema), convalida dell'admin {[(r['veste'], r['azione']) for r in _reg]}")
# controllo delle 10: ESPN corregge il tabellino di un giocatore schierato (r12) e di uno no (r40)
async def finto_scarica(ids, **k):
    db.q("UPDATE nba_tabellini SET fp = 25 WHERE atleta = 'r12' AND partita = 'g1'")
    return {"partite": len(ids), "giocatori": 0, "errori": []}
_vero = HR.nba.scarica_tabellini; HR.nba.scarica_tabellini = finto_scarica
BOT.mandati.clear()
asyncio.run(HR.job_controllo(types.SimpleNamespace(bot=BOT)))
HR.nba.scarica_tabellini = _vero
avv = [x for x in BOT.mandati if x.get("chat_id") == -2]
ok(len(avv) == 1 and "Prova 12" not in avv[0]["text"] and "r12: 21.0 → 25.0" in avv[0]["text"] and "già convalidata" in avv[0]["text"]
   and [b.callback_data for r in avv[0]["reply_markup"].inline_keyboard for b in r] == [f"rc:re:{N}"],
   f"controllo delle 10: tabellino cambiato di uno schierato → avviso col bottone Ricalcola {avv[0]['text'] if avv else ''}")

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
   "dalle 8 alle 10 niente")
ok(LV.cosa_fare(g7, datetime(2026, 11, 11, 10, 6, tzinfo=ROMA), {**st_, "aggiornato": datetime(2026, 11, 11, 7, 55, tzinfo=ROMA)})
   == ("controllo", DAL), "alle 10:05 un aggiornamento (dopo il controllo dei tabellini)")
ok(LV.cosa_fare(g7, t0 + timedelta(minutes=30), {**st_, "prossimo": t0 + timedelta(minutes=40)}) == (None, None), "dopo un errore si aspetta")

class BotL(Bot):
    async def edit_message_text(s, chat_id, message_id, text, **k):
        s.mandati.append({"chat_id": chat_id, "id": message_id, "text": text, "modifica": True})
BL = BotL()
scaricate = []
async def finta(g, d, controllo=False):
    scaricate.append((d, controllo))
db.q("UPDATE lega_giornate SET prima_partita = %s WHERE stagione = %s AND numero = %s", (t0, S, N))
fatti = asyncio.run(LV.tick(BL, ora=t0 + timedelta(seconds=30), scarica_fn=finta))
pub = [x for x in BL.mandati if x.get("chat_id") == -1]
c_ora = LV.calcolo(S, N)
r0 = c_ora["risultati"][0]
ok(len(pub) == 1 and "punteggi live" in pub[0]["text"] and "provvisori" in pub[0]["text"] and "convalida un admin" in pub[0]["text"]
   and "Ultimo aggiornamento: 11/11 alle 00:00" in pub[0]["text"]
   and f"{LV.tp(r0['punti_casa'])} – {LV.tp(r0['punti_trasferta'])}" in pub[0]["text"] and scaricate == [(DAL, False)],
   "tipoff: messaggio sul canale principale col calcolo, provvisorio, ora dell'aggiornamento")
asyncio.run(LV.tick(BL, ora=t0 + timedelta(minutes=4), scarica_fn=finta))
ok(len([x for x in BL.mandati if x.get("chat_id") == -1]) == 1 and len(scaricate) == 1, "4 minuti dopo: niente")
asyncio.run(LV.tick(BL, ora=t0 + timedelta(minutes=11), scarica_fn=finta))
mod = [x for x in BL.mandati if x.get("modifica")]
ok(len(mod) == 1 and mod[0]["id"] == pub[0]["id"] and len(scaricate) == 2, "10 minuti dopo: si modifica lo stesso messaggio")
async def rotta(g, d, controllo=False):
    raise RuntimeError("429 Too Many Requests")
BL.mandati.clear()
asyncio.run(LV.tick(BL, ora=t0 + timedelta(minutes=22), scarica_fn=rotta))
stl = LV.stato(S, N)
ok(stl["prossimo"] == t0 + timedelta(minutes=42) and any("aggiornamento saltato" in x["text"] for x in BL.mandati if x["chat_id"] == -3)
   and not any(x.get("modifica") for x in BL.mandati), "ESPN in errore: giro saltato, si riprova fra 20 minuti, una riga sul log")
asyncio.run(LV.tick(BL, ora=t0 + timedelta(minutes=32), scarica_fn=finta))
ok(len(scaricate) == 2, "prima dei 20 minuti non riprova")
asyncio.run(LV.tick(BL, ora=datetime(2026, 11, 11, 10, 6, tzinfo=ROMA), scarica_fn=finta))
ok(scaricate[-1] == (DAL, True), "alle 10:05 riscarica i tabellini della notte")
async def con_cambi(g, d, controllo=False):
    return {"cambi": {("g1", "r1"): ((30.0, 30, "Prova 1"), (32.5, 31, "Prova 1")), ("g1", "r99"): ((5.0, 10, "Nessuno"), (6.0, 10, "Nessuno"))}}
db.q("UPDATE lega_live SET aggiornato = %s WHERE stagione = %s AND giornata = %s", (datetime(2026, 11, 12, 7, 55, tzinfo=ROMA), S, N))
BL.mandati.clear()
asyncio.run(LV.tick(BL, ora=datetime(2026, 11, 12, 10, 6, tzinfo=ROMA), scarica_fn=con_cambi))
righe_log = [x["text"] for x in BL.mandati if x.get("chat_id") == -3 and "controllo delle 10:05" in x.get("text", "")]
ok(len(righe_log) == 1 and "Prova 1: 30,00 → 32,50 fantapunti (minuti 30 → 31)" in righe_log[0] and "Nessuno" not in righe_log[0]
   and "notte del 11/11" in righe_log[0], "10:05: tabellini cambiati di giocatori schierati sul canale log (gli altri no)")
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
ok("▶" not in tl0 and "⏳ da giocare" in tl0, "più di 4 dei 10 ancora da giocare: nessun esito, solo chi deve giocare")
for _x in _stati:
    db.q("UPDATE nba_partite SET stato = %s WHERE espn_id = %s", (_x["stato"], _x["espn_id"]))
db.q("UPDATE nba_partite SET stato = 'STATUS_FINAL' WHERE espn_id = 'g5'")
tl = LV.testo(LV.calcolo(S, N), t0)
ok("▶ al momento vince Beta ai supplementari (1): " in tl and "▶ al momento vince Gamma" in tl,
   "tutti hanno finito: l'esito, supplementari compresi")
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
   and PL.cosa_fare(stp, datetime(2026, 10, 15, 10, 6, tzinfo=ROMA)) == "controllo", "prova del live: stessi orari del live")
ok(not PL.finita(stp, datetime(2026, 10, 15, 10, 6, tzinfo=ROMA)) and PL.finita(stp, datetime(2026, 10, 15, 10, 20, tzinfo=ROMA)),
   "prova del live: finisce dopo le 10:05 dell'ultimo giorno")
db.q("TRUNCATE ipa_quintetto")

# ── /player ──
import player as PLY
gid1 = next(v for k, v in gid.items() if db.q("SELECT espn_id FROM giocatori WHERE id = %s", (v,), one=True)["espn_id"] == "r1")
sc = PLY.scheda(gid1)
ok("🇺🇸 NBA:" in sc and "🏆 Fantabasket: <b>" in sc and "media <b>" in sc and "Ultime partite" in sc and "fantapunti" in sc,
   "/player: NBA, fantabasket, media e ultime partite\n" + sc)
ok(PLY.cerca("prova 1") and PLY.cerca("prova 1")[0]["id"] == gid1, "/player: ricerca per nome")
db.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s, 'team01', 12, 3, %s, 'normale')",
     (gid1, S))
sc = PLY.scheda(gid1)
ok("🏆 Fantabasket: <b>Alfa</b>" in sc and "12 × 3 anni" in sc, "/player: squadra e contratto " + sc.split("\n")[3])
db.q("DELETE FROM contratti WHERE giocatore_id = %s", (gid1,))
# pulizia
db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (list(gid.values()),))
db.q("TRUNCATE nba_tabellini, nba_infortuni, lega_giornate, lega_partite, nba_partite, lega_risultati, lega_calcoli, lega_live")
db.q("TRUNCATE ipa_formazioni, ipa_panchine, ipa_stato_giornata")
_ = (asyncio, json, types)

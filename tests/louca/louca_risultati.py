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
tab("g1", [("r1", "NYK", 30, 30), ("r2", "NYK", 25, 30), ("r3", "BOS", 18, 30), ("r11", "NYK", 24, 30), ("r12", "BOS", 21, 30),
           ("r13", "BOS", 0, 22), ("r6", "NYK", 12, 20), ("r21", "NYK", 27, 30), ("r22", "BOS", 33, 30)])
tab("g2", [("r1", "NYK", 20, 30), ("r4", "PHX", 35, 30), ("r11", "NYK", 14, 30), ("r14", "PHX", 28, 30),
           ("r6", "NYK", 0, 0), ("r21", "NYK", 31, 30), ("r24", "PHX", 15, 30), ("r7", "PHX", 9, 15)])
tab("g3", [("r3", "BOS", 22, 30), ("r4", "PHX", 15, 30), ("r12", "BOS", 19, 30), ("r14", "PHX", 30, 30), ("r13", "BOS", 10, 25),
           ("r22", "BOS", 29, 30), ("r24", "PHX", 17, 30), ("r8", "BOS", 6, 12)])
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
schiera("team03", [5, 21, 22, 24, 23], [(30, "SG"), (16, "PG"), (26, "C")])
# Delta: niente panchina (avviso), un ruolo vuoto
schiera("team04", [25, 26, None, 9, 12], None)
db.q("INSERT INTO ipa_stato_giornata (stagione, giornata, chiusa) VALUES (%s, %s, NOW())", (S, N))

ok(R.giornata_chiusa(S, N), "giornata chiusa su IPanchinari: si può calcolare")
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
ok(len(r2["sc"]["panchina"]) == 2, "dopo la FADD la panchina di Gamma scala")
ok(r1["supplementari"] == 1 and r1["supp_casa"] == 9 and r1["supp_trasferta"] == 29,
   f"partita 1 ai supplementari: soli punti dei supplementari {r1['punti_casa']} {r1['punti_trasferta']} {r1['supp_casa']} {r1['supp_trasferta']}")

# ── il foglio rifà i conti del bot ──
gr = R.griglia(c)
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
    num = lambda x: round(float(x), 2) if x not in ("", None) else None
    ris_foglio = [foglio[i] for i in range(4, 4 + len(c["risultati"]))]
    for k, (rb, rf) in enumerate(zip(c["risultati"], ris_foglio), 1):
        vince_bot = config.nome(rb["casa"]) if rb["vince"] == "casa" else config.nome(rb["trasferta"])
        ok((num(rf[2]), num(rf[4]), int(float(rf[5])), rf[8]) == (rb["punti_casa"], rb["punti_trasferta"], rb["supplementari"], vince_bot)
           and (num(rf[6]), num(rf[7])) == (rb["supp_casa"], rb["supp_trasferta"]),
           f"partita {k}: il foglio dà gli stessi risultati del bot {rf[:9]} / {rb['punti_casa']} {rb['punti_trasferta']} "
           f"{rb['supplementari']} {rb['supp_casa']} {rb['supp_trasferta']} {vince_bot}")
    ip = gr["colonne"]["punteggio"]
    nomi = {f"Prova {i}": f"r{i}" for i in range(1, 41)}
    diversi = [(r[3], r[ip], c["punti"][nomi[r[3]]]["fp"]) for r in foglio if len(r) > ip and r[3] in nomi
               and num(r[ip]) != c["punti"][nomi[r[3]]]["fp"]]
    ok(not diversi, f"punteggio di ogni giocatore: foglio = bot {diversi[:3]}")
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
t = R.testo(c, 2)
ok("Giornata 7 calcolata</b> (ricalcolo 1)" in t and "FADD: esce Prova 10, entra Prova 6" in t and "Delta: panchina non mandata" in t,
   "messaggio per il gruppo admin: risultati, FADD, avvisi")

# ── proposta al gruppo admin, convalida coi bottoni, controllo delle 10 ──
import json as _json, handlers_risultati as HR
G = _json.load(open(config.GLOBALS_PATH)); G["admin_group_id"] = -2; G["log_channel_id_louca"] = -3
_json.dump(G, open(config.GLOBALS_PATH, "w"))
db.q("DELETE FROM lega_calcoli"); db.q("DELETE FROM lega_risultati")
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

# pulizia
db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (list(gid.values()),))
db.q("TRUNCATE nba_tabellini, nba_infortuni, lega_giornate, lega_partite, nba_partite, lega_risultati, lega_calcoli")
db.q("TRUNCATE ipa_formazioni, ipa_panchine, ipa_stato_giornata")
_ = (asyncio, json, types)

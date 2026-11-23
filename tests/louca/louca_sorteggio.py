import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.28.0 (Luca, 15/11 e 23/11): sorteggio del calendario con drand. Lo schema a posti rispetta la struttura di Henry
e mai più di 2 di fila nello stesso campo; ogni sorteggio la rispetta ed è quello dello script allegato; annuncio con
allegati, sorteggio all'ora del round, date dal CSV unite al sorteggio nel calendario della stagione."""
import asyncio
import hashlib
import json
import subprocess
import shutil
import tempfile
import types
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import db, config
from shared import calendario_sorteggio as CS
from shared import lottery as LT
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
run = asyncio.run

# ── la libreria ──
A, B = CS.posti("A"), CS.posti("B")
CS.valida(CS.schema(), A, B)
ok(True, "lo schema a posti supera i controlli di Henry e i nostri")
ok(all(CS.di_fila(CS.campi(CS.schema(), t)) <= 2 for t in A + B), "nello schema mai più di 2 di fila, su 38 giornate")
semi = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(300)]
peggio, primi = 0, Counter()
for s in semi:
    gg = CS.genera(A, B, s)                                   # genera chiama valida: un errore fermerebbe la prova
    peggio = max(peggio, max(CS.di_fila(CS.campi(gg, t)) for t in A + B))
    primi[CS.assegna(A, B, s)["A1"]] += 1
ok(peggio <= 2, f"300 sorteggi: tutti validi, al massimo {peggio} di fila")
ok(len(primi) == 12 and min(primi.values()) >= 10, f"il primo posto va a tutte le squadre ({dict(primi)})")
ok(CS.genera(A, B, semi[0]) == CS.genera(A, B, semi[0]) and CS.genera(A, B, semi[0]) != CS.genera(A, B, semi[1]),
   "stesso seme stesso calendario, seme diverso calendario diverso")
_rotto = CS.schema()
_rotto[34], _rotto[35] = _rotto[35], _rotto[34]
_rotto[0], _rotto[1] = _rotto[1], _rotto[0]
try:
    CS.valida(_rotto, A, B); _e = ""
except CS.ErroreCalendario as er:
    _e = str(er)
ok("di fila" in _e or "trasferta" in _e or "casa" in _e, f"un calendario con le giornate spostate non passa ({_e[:60]})")
try:
    CS.assegna(A[:11], B, semi[0]); _e = ""
except CS.ErroreCalendario as er:
    _e = str(er)
ok("12 squadre" in _e, "servono 12 squadre per conference")

# ── 24 squadre in due conference: file temporanei, rimessi a posto alla fine ──
CFG = _os.path.dirname(config.TEAMS_PATH)
_teams = open(config.TEAMS_PATH, encoding="utf-8").read()
T = [f"sc{i:02d}" for i in range(1, 25)]
json.dump({"teams": [{"id": t, "nome": f"Squadra {t[-2:]}", "gm_ids": [], "gm_nome": t} for t in T]},
          open(config.TEAMS_PATH, "w", encoding="utf-8"))
json.dump({"conference": {"Ovest": ["O"], "Est": ["E"]}, "team_div": {t: ("O" if i < 12 else "E") for i, t in enumerate(T)}},
          open(_os.path.join(CFG, "divisions.json"), "w", encoding="utf-8"))
try:
    db.init_db()
    import sorteggio_calendario as SC
    SC.migra()
    for t in ("lega_giornate", "lega_partite", "lega_calendario_sorteggio"):
        db.q(f"TRUNCATE {t}")
    S = config.stagione()
    ok(SC.stagione() == S, "senza calendario: la stagione corrente")
    cc = SC.conference()
    ok([c["nome"] for c in cc] == ["Ovest", "Est"] and cc[0]["squadre"] == T[:12] and cc[1]["squadre"] == T[12:],
       "conference da divisions.json, squadre in ordine alfabetico")

    inviati = []

    class Bot:
        async def send_message(self, chat_id, text, **k):
            inviati.append((chat_id, text, None))
        async def send_media_group(self, chat_id, media, **k):
            inviati.append((chat_id, "ALLEGATI", [m.media.filename for m in media]))
        async def send_document(self, chat_id, document, filename=None, **k):
            inviati.append((chat_id, "FILE", (filename, document.getvalue())))
    bot = Bot()
    risposte = []

    class M:
        async def reply_text(s, t, **k): risposte.append(t)
    def upd(uid): return types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid, full_name="Admin"), effective_message=M())
    ctx = lambda *a: types.SimpleNamespace(bot=bot, args=list(a))

    run(SC.cmd_calendario_quando(upd(5), ctx("01/01", "10:00")))
    ok(risposte[-1].startswith("⛔") and not SC.stato(S), "solo admin")
    run(SC.cmd_calendario_quando(upd(900), ctx()))
    ok("non ancora fissato" in risposte[-1], "senza argomenti: lo stato")
    LT.info = lambda: {"genesis_time": 1692803367, "period": 3}
    quando = (datetime.now(timezone.utc) + timedelta(hours=2)).astimezone(SC.ROMA)
    run(SC.cmd_calendario_quando(upd(900), ctx(f"{quando:%d/%m/%Y}", f"{quando:%H:%M}")))
    r = SC.stato(S)
    ok(r and r["stato"] == "annunciato" and r["impronta"] == CS.impronta() and risposte[-1].startswith("✅"),
       f"sorteggio fissato {risposte[-1:]}")
    ok(any(c == -1 and "Sorteggio del calendario" in tx and r["impronta"] in tx and LT.link_round(r["round"]) in tx
           and "Squadra 01" in tx and "mai più di 2 di fila" in tx and f"--round {r['round']}" in tx for c, tx, _ in inviati),
       "annuncio sul canale: round, conference, impronta, link, comando")
    ok(any(c == -1 and tx == "ALLEGATI" and kb == ["calendario_sorteggio.py", "lottery.py", "LEGGIMI.txt"] for c, tx, kb in inviati),
       "allegati il codice e le istruzioni")
    _lg = SC.leggimi(r)
    ok(r["impronta"] in _lg and SC.comando(r) in _lg and "sha256sum calendario_sorteggio.py" in _lg, "LEGGIMI: impronta, comando")
    quando2 = quando + timedelta(hours=1)
    run(SC.cmd_calendario_quando(upd(900), ctx(f"{quando2:%d/%m/%Y}", f"{quando2:%H:%M}")))
    ok(SC.stato(S)["round"] == r["round"] + 1200, "si può rifissare prima del sorteggio (un'ora dopo: 1200 round)")
    r = SC.stato(S)

    ok(run(SC.passo(bot, ora=datetime.now(timezone.utc))) is None, "prima dell'ora: niente")
    def _non_ancora(rnd, servono=2):
        raise LT.LotteryError("non ancora")
    LT.randomness = _non_ancora
    ok("non ancora" in run(SC.passo(bot, ora=quando2 + timedelta(seconds=5))) and SC.stato(S)["stato"] == "annunciato",
       "round non ancora uscito: si riprova, vale sempre quello annunciato")
    SEME = "5e" * 32
    LT.randomness = lambda rnd, servono=2: SEME if rnd == r["round"] else "00" * 32
    inviati.clear()
    esito = run(SC.passo(bot, ora=quando2 + timedelta(seconds=5)))
    r = SC.stato(S)
    gg = SC._j(r["giornate"])
    ok(r["stato"] == "estratto" and r["randomness"] == SEME and len(gg) == 38 and "sorteggiato" in esito, "sorteggio all'ora del round")
    ok(gg == [[list(p) for p in g] for g in CS.genera(T[:12], T[12:], SEME)], "il calendario è quello di genera col seme del round")
    ok(any(c == -1 and "sorteggiato" in tx and SEME in tx for c, tx, _ in inviati)
       and any(c == -1 and tx == "FILE" and kb[0].startswith("calendario_") and kb[1].count(b"\n") == 1 + 38 * 12 for c, tx, kb in inviati)
       and any(c == -2 and "/importa_date" in tx for c, tx, _ in inviati), "canale: risultato e CSV; admin: promemoria delle date")
    ok(run(SC.passo(bot, ora=quando2 + timedelta(minutes=5))) is None, "una volta sola")
    run(SC.cmd_calendario_quando(upd(900), ctx(f"{quando2:%d/%m/%Y}", f"{quando2:%H:%M}")))
    ok("già sorteggiato" in risposte[-1], "dopo il sorteggio non si rifissa")

    # lo script da solo, coi due file in una cartella qualsiasi, coi nomi delle squadre
    _dir = tempfile.mkdtemp()
    for _f in ("calendario_sorteggio.py", "lottery.py"):
        shutil.copy(_os.path.join(LT.CARTELLA, _f), _dir)
    _a, _b = SC._j(r["conf_a"]), SC._j(r["conf_b"])
    _out = subprocess.run([_sys.executable, "calendario_sorteggio.py", "genera", "--randomness", SEME, "--a", SC._nomi(_a["squadre"]),
                           "--b", SC._nomi(_b["squadre"]), "--csv", "c.csv"], cwd=_dir, capture_output=True, text=True,
                          env={"PATH": _os.environ.get("PATH", "")})
    _csv = open(_os.path.join(_dir, "c.csv"), encoding="utf-8").read().replace("\r", "")
    ok(r["impronta"] in _out.stdout and "Calendario valido" in _out.stdout and _csv == SC.csv_sorteggio(gg).decode(),
       f"lo script allegato rifà lo stesso calendario, con la stessa impronta {_out.stderr[-200:]}")

    # le date
    def errore(t):
        try:
            SC.importa_date(t, S); return ""
        except ValueError as er:
            return str(er)
    Y = int(S)
    giorni = [date(Y, 10, 20) + timedelta(days=2 * i) for i in range(38)]
    righe = ["giornata,giorno1,giorno2"] + [f"G{i + 1},{d:%d/%m/%Y},{d + timedelta(days=1):%d/%m/%Y}" for i, d in enumerate(giorni)]
    ok("da G1 a G38" in errore("\n".join(righe[:-1])), "mancano giornate")
    ok("non sono consecutivi" in errore("G1,20/10/2026,22/10/2026"), "giorni non consecutivi")
    ok("da 1 a 4" in errore("G1,20/10,21/10,22/10,23/10,24/10"), "più di 4 giorni")
    righe[2] += ",okc nop"
    esito = SC.importa_date("\n".join(righe), S)
    ok(esito["giornate"] == 38 and esito["partite"] == 456 and SC.stato(S)["stato"] == "date", "date importate: 38 giornate, 456 partite")
    _p = db.q("SELECT giornata, casa, trasferta FROM lega_partite WHERE stagione = %s ORDER BY giornata, id", (S,), many=True)
    ok([[p["casa"], p["trasferta"]] for p in _p] == [list(x) for g in gg for x in g], "in calendario le partite del sorteggio")
    _g2 = db.giornata(S, 2)
    ok(_g2["dal"] == date(Y, 10, 22) and _g2["al"] == date(Y, 10, 23) and list(_g2["media_file"]) == ["NOP", "OKC"], "date e squadre a media")
    ok(SC.stagione() == str(Y + 1), "col calendario della stagione corrente il prossimo sorteggio è per la stagione dopo")
    ok("date importate" in SC.testo_stato(S), "stato: date importate")
    try:
        SC.importa_date("G1,20/10/2027", str(Y + 1)); _e = ""
    except ValueError as er:
        _e = str(er)
    ok("prima il sorteggio" in _e, "senza sorteggio le date non si importano")
finally:
    open(config.TEAMS_PATH, "w", encoding="utf-8").write(_teams)
    try:
        _os.remove(_os.path.join(CFG, "divisions.json"))
    except FileNotFoundError:
        pass
    for t in ("lega_giornate", "lega_partite", "lega_calendario_sorteggio", "lega_calendario_csv"):
        try:
            db.q(f"TRUNCATE {t}")
        except Exception:
            pass

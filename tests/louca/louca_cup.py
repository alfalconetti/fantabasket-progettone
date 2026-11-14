import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.9.0: Quasi NBA Cup (shared/quasi_cup.py, loucabot cup.py): giornate della qualificazione (anche quella a cavallo
del 27/11), classifica col miglior punteggio di giornata e spareggio col secondo, abbinamenti (in casa la meglio
classificata), esiti dai punteggi di squadra del calcolo della G con bonus casa e supplementari, convalida con la
giornata, finale tra le vincenti, campione, fasi dell'immagine, messaggio live sul canale che resta alla convalida."""
import asyncio
import json
from datetime import date, datetime, timezone

import db, config, cup
import risultati as R
from shared import quasi_cup as QC
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
db.init_db()
S = config.stagione()
Y = int(S)
for t in ("lega_cup", "lega_cup_live", "lega_risultati", "lega_giornate", "lega_calcoli", "lega_calcoli_storico"):
    db.q(f"TRUNCATE {t}")
T = [t["id"] for t in config.squadre()]          # 4 squadre nella config di prova
a, b, c, d = T
GG = [(0, date(Y, 10, 20), date(Y, 10, 26)), (1, date(Y, 10, 27), date(Y, 11, 2)), (2, date(Y, 11, 3), date(Y, 11, 9)),
      (3, date(Y, 11, 24), date(Y, 11, 30)),        # a cavallo del 27/11: conta
      (4, date(Y, 12, 1), date(Y, 12, 7)), (5, date(Y, 12, 8), date(Y, 12, 14)), (6, date(Y, 12, 15), date(Y, 12, 21))]
for n, dal, al in GG:
    db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES (%s, %s, 'regular', %s, %s)", (S, n, dal, al))
info = QC.giornate(S)
ok([g["numero"] for g in info["qual"]] == [1, 2, 3] and info["q1"]["numero"] == 4 and info["q2"]["numero"] == 5,
   f"qualificazione G1–G3 (anche quella a cavallo del 27/11, non la G0); Q1 nella G4, Q2 nella G5 {[g['numero'] for g in info['qual']]}")
ok(QC.turno_di(S, 4, info) == 1 and QC.turno_di(S, 5, info) == 2 and QC.turno_di(S, 3, info) is None, "turno della giornata")


def ris(n, casa, tr, pc, pt, conv=True):
    db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince, convalidato)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", (S, n, casa, tr, pc, pt, "casa" if pc - pt >= 5 else "trasferta",
                                                        datetime.now(timezone.utc) if conv else None))


ris(0, a, b, 900, 100)                                # G0: prima della finestra, non conta
ris(1, a, b, 600, 500); ris(1, c, d, 580, 590)
ris(2, b, a, 610, 400); ris(2, d, c, 550, 600)
ris(3, a, d, 590, 300, conv=False); ris(3, b, c, 500, 300, conv=False)
cl = QC.classifica(S)
ok([x["team"] for x in cl] == [b, c, a, d] and cl[0]["punteggi"][0] == (610.0, 2),
   f"classifica sul miglior punteggio (solo convalidate, niente G0): {[x['team'] for x in cl]}")
ok(not QC.qualificazione_chiusa(S), "qualificazione aperta finché la giornata a cavallo non è convalidata")
ok(cup.esiti(S, 4, []) == [], "semifinali non calcolate con la qualificazione aperta")
db.q("UPDATE lega_risultati SET convalidato = NOW() WHERE giornata = 3")
db.q("UPDATE lega_risultati SET punti_casa = 600 WHERE giornata = 3 AND casa = %s", (a,))
# a: 600, 600 (G1, G3) · c: 600, 580 · b: 610 · d: 590 → a e c a 600: passa a, che ha anche il secondo a 600
cl = QC.classifica(S)
ok([x["team"] for x in cl] == [b, a, c, d], f"a pari miglior punteggio conta il secondo {[x['team'] for x in cl]}")
ok(QC.qualificazione_chiusa(S), "qualificazione chiusa con tutte le giornate convalidate")
ok(QC.abbinamenti(S, 1) == [(b, d), (a, c)], "semifinali 1ª–4ª e 2ª–3ª, in casa la meglio classificata")
ok(QC.abbinamenti(S, 2) == [], "finale: nessuna squadra prima delle semifinali convalidate")


def sq(tot, panca=()):
    return {"totale": float(tot), "panchina": [{"fp": float(x)} for x in panca], "titolari": [], "fadd": None, "avvisi": []}


# la G4 di regular season: b–a, c–d (abbinamenti diversi da quelli della Cup)
partite_g4 = [{"casa": b, "trasferta": a, "sc": sq(300, [10]), "st": sq(320, [5])},
              {"casa": c, "trasferta": d, "sc": sq(290, [20, 0]), "st": sq(291, [4, 30])}]
es = cup.esiti(S, 4, partite_g4)
e1 = next(x for x in es if x["casa"] == b)
e2 = next(x for x in es if x["casa"] == a)
ok(e1["trasferta"] == d and float(e1["punti_casa"]) == 303 and float(e1["punti_trasferta"]) == 291 and e1["vince"] == "casa",
   f"SF1: b in casa col bonus (300+3) contro d (291) {e1}")
ok(float(e2["punti_casa"]) == 323 and float(e2["punti_trasferta"]) == 290 and e2["vince"] == "casa" and e2["supplementari"] == 0,
   "SF2: a 320+3 su c 290, punti della squadra presi dalla sua partita di G4")
es2 = cup.esiti(S, 4, [{"casa": b, "trasferta": a, "sc": sq(300, [10]), "st": sq(301, [5])},
                       {"casa": c, "trasferta": d, "sc": sq(299, [1]), "st": sq(301, [1])}])
x = next(x for x in es2 if x["casa"] == b)
ok(x["supplementari"] == 1 and x["vince"] == "casa" and float(x["supp_casa"]) == 10, f"supplementari con la panchina {x}")
ok(cup.esiti(S, 3, partite_g4) == [], "nessuna Cup nelle altre giornate")
txt = cup.testo_admin(es)
ok("Q1" in txt and "semifinali" in txt and config.nome(b) in txt, "nella proposta agli admin")

# calcolo salvato e convalida con la giornata
c4 = {"stagione": S, "giornata": {"numero": 4}, "avvisi": [], "cup": es,
      "risultati": [{"casa": b, "trasferta": a, "punti_casa": 303, "punti_trasferta": 320, "supp_casa": None, "supp_trasferta": None,
                     "supplementari": 0, "vince": "trasferta"}]}
R.salva_calcolo(c4)
R.convalida(S, 4, 900)
ok(len(QC.risultati_cup(S, 1)) == 2, "alla convalida della G4 anche le semifinali in lega_cup")
ok(QC.abbinamenti(S, 2) == [(b, a)], f"finale tra le vincenti, in casa la meglio classificata {QC.abbinamenti(S, 2)}")
R.salva_calcolo(c4)                                  # ricalcolo e nuova convalida: si riscrivono, niente doppioni
R.convalida(S, 4, 900)
ok(len(QC.risultati_cup(S, 1)) == 2, "nuova convalida: stesse due semifinali")
ok(QC.campione(S) is None, "nessuna campionessa prima della finale")
fin = cup.esiti(S, 5, [{"casa": a, "trasferta": c, "sc": sq(250), "st": sq(240)},
                       {"casa": d, "trasferta": b, "sc": sq(260), "st": sq(280)}])
ok(len(fin) == 1 and fin[0]["casa"] == b and fin[0]["vince"] == "casa", f"finale: b 280+3 su a 250 {fin}")
R.salva_calcolo({**c4, "giornata": {"numero": 5}, "cup": fin})
R.convalida(S, 5, 900)
ok(QC.campione(S) == b, "campionessa dopo la finale convalidata")

# fasi dell'immagine
fasi = []
for k, ora in enumerate((datetime(Y, 10, 25, 12, tzinfo=timezone.utc), datetime(Y, 11, 14, 12, tzinfo=timezone.utc))):
    db.q("TRUNCATE lega_cup")
    if k == 1:
        db.q("UPDATE lega_risultati SET convalidato = NULL WHERE giornata = 3")
    fasi.append(QC.dati(S, ora))
ok("inizia il 30/10" in fasi[0]["fase"], f"prima della qualificazione: {fasi[0]['fase']}")
ok("mancano 13 giorni" in fasi[1]["fase"] and fasi[1]["tab_nota"] == "se finisse oggi" and fasi[1]["q_titoli"][1] == "Inseguono",
   f"durante la qualificazione: {fasi[1]['fase']}")
db.q("UPDATE lega_risultati SET convalidato = NOW() WHERE giornata = 3")
dopo = datetime(Y, 11, 29, 12, tzinfo=timezone.utc)
dq = QC.dati(S, dopo)
ok("Qualificate" in dq["fase"] and dq["tab_nota"] == "le qualificate" and len(dq["semi"]) == 2
   and dq["semi"][0]["righe"][0]["id"] == b and dq["semi"][0]["righe"][0]["seed"] == "1ª", f"qualificate: {dq['fase']}")
ok(dq["chip"]["v"].startswith(config.nome(b)) and "610" in dq["chip"]["v"], f"record della Cup {dq['chip']}")


# live: messaggio del turno sul canale, stesso giro del live; alla convalida resta e diventa definitivo
class Bot:
    def __init__(self):
        self.mandati, self.modificati, self.testi = [], [], []

    async def send_photo(self, chat_id, photo, caption, parse_mode, **k):
        self.mandati.append(caption)
        return type("M", (), {"message_id": 77})()

    async def edit_message_media(self, chat_id, message_id, media, **k):
        self.modificati.append(media.caption)

    async def send_message(self, chat_id, text, parse_mode=None, **k):
        self.testi.append(text)


bot = Bot()
semi_live = datetime(Y, 12, 2, 1, tzinfo=timezone.utc)
db.q("UPDATE lega_giornate SET prima_partita = %s WHERE numero = 4", (datetime(Y, 12, 2, 0, tzinfo=timezone.utc),))
r1 = asyncio.run(cup.aggiorna_live(bot, S, 4, {"risultati": partite_g4}, semi_live))
r2 = asyncio.run(cup.aggiorna_live(bot, S, 4, {"risultati": partite_g4}, semi_live))
ok(r1 == "Cup Q1 pubblicata" and r2 == "Cup Q1 aggiornata" and len(bot.mandati) == 1 and len(bot.modificati) == 1,
   f"live: pubblicata una volta, poi sostituita {r1}, {r2}")
dl = QC.dati(S, semi_live)
ok("Semifinali in corso" in dl["fase"] and dl["semi"][0]["badge"] == "LIVE" and dl["semi"][0]["righe"][0]["punti"] == "303,00",
   f"immagine live: {dl['fase']} {dl['semi'][0]['righe'][0]['punti']}")
ok(asyncio.run(cup.aggiorna_live(bot, S, 3, {"risultati": partite_g4}, semi_live)) is None, "nessun messaggio nelle altre giornate")
R.salva_calcolo(c4)
R.convalida(S, 4, 900)
r3 = asyncio.run(cup.dopo_convalida(bot, S, 4))
ok("definitiva" in r3 and len(bot.modificati) == 2 and len(bot.mandati) == 1 and QC.live(S, 1)["chiuso"],
   f"alla convalida il messaggio resta (modificato, non cancellato) {r3}")
ok(asyncio.run(cup.aggiorna_live(bot, S, 4, {"risultati": partite_g4}, semi_live)) is None, "dopo la convalida il live della Cup è fermo")
dd = QC.dati(S, semi_live)
ok(dd["semi"][0]["badge"] == "FINITA" and len(dd["finale"]["righe"]) == 2 and "Finaliste" in dd["fase"],
   f"semifinali definitive, finaliste nella finale: {dd['fase']}")
R.salva_calcolo({**c4, "giornata": {"numero": 5}, "cup": fin})
R.convalida(S, 5, 900)
r4 = asyncio.run(cup.dopo_convalida(bot, S, 5))
r5 = asyncio.run(cup.dopo_convalida(bot, S, 5))
ok("vincitrice" in r4 and "vincitrice" not in r5 and len(bot.testi) == 1 and "cambio ruolo Cup" in bot.testi[0],
   "dopo la finale il messaggio della vincitrice, una volta sola")
dc = QC.dati(S, semi_live)
ok(dc["finale"]["campione"]["id"] == b and "vince la Quasi NBA Cup" in dc["fase"], f"campione nell'immagine: {dc['fase']}")
try:
    import typst  # noqa: F401
    pngs = [QC.immagine(x) for x in (fasi[0], fasi[1], dq, dl, dd, dc)]
    ok(all(p[:8] == b"\x89PNG\r\n\x1a\n" for p in pngs), "immagini di tutte le fasi")
    if _os.environ.get("CUP_PNG"):                   # per guardarle: CUP_PNG=cartella
        for i, p in enumerate(pngs):
            open(_os.path.join(_os.environ["CUP_PNG"], f"cup{i}.png"), "wb").write(p)
except ImportError:
    print("(typst non installato: immagini non provate)")
# ── v7.9.1: Q1 e Q2 nei comandi, date in settings.json ──
ok(cup.leggi_turno(["Alfa", "q2"]) == (2, ["Alfa"]) and cup.leggi_turno(["G3"]) == (None, ["G3"]) and cup.leggi_turno(["Q3"])[0] is None,
   "Q1/Q2 tra gli argomenti (non G3, non Q3)")
t1 = cup.testo_turno(S, 1)
ok("Q1 (semifinali)" in t1 and "Semifinale 1" in t1 and "303,00" in t1 and "convalidati" in t1, "/risultati Q1: semifinali convalidate")
import live as LV, partita as PA
_vc = LV.calcolo


def finto(s_, n_):
    sqd = {t: {"quintetto": [], "panchina": []} for t in T}
    return {"risultati": partite_g4, "squadre": sqd, "punti": {}, "avvisi": [], "dettaglio": {}, "bonus": 3.0,
            "giornata": db.giornata(S, n_)}


LV.calcolo = finto
dp = PA.dati(S, 4, b, d, turno=1)
ok(dp["cup"]["fase"] == "Semifinale 1" and dp["titolo"] == "Q1 · Giornata 4" and dp["stato"] == "convalidata"
   and dp["squadre"][0]["record"] == "1ª QUALIFICATA" and dp["squadre"][1]["record"] == "4ª QUALIFICATA"
   and dp["squadre"][0]["punti"] == "303,00" and "Quasi NBA Cup" in dp["note"][0],
   f"/partita Q1: fascia, titolo, piazzamenti, risultato salvato {dp['titolo']} {dp['squadre'][0]['record']}")
try:
    PA.dati(S, 4, b, a, turno=1); _err = False
except ValueError:
    _err = True
ok(_err, "/partita Q1 con una coppia che non è della Cup: errore")
tb = LV.dati_tabellone(S, db.giornata(S, 4), semi_live, 1)
ok(tb["titolo"] == "Q1 · Giornata 4" and tb["cup"] == "Semifinali" and len(tb["partite"]) == 2 and tb.get("modo") == "finale",
   "/giornata Q1: le due semifinali, convalidate, con la fascia")
try:
    import typst  # noqa: F401
    ok(PA.immagine(dp)[:4] == b"\x89PNG" and LV.immagine(tb)[:4] == b"\x89PNG", "immagini di /partita Q1 e /giornata Q1")
    if _os.environ.get("CUP_PNG"):
        open(_os.path.join(_os.environ["CUP_PNG"], "partita_q1.png"), "wb").write(PA.immagine(dp))
        open(_os.path.join(_os.environ["CUP_PNG"], "giornata_q1.png"), "wb").write(LV.immagine(tb))
except ImportError:
    pass
LV.calcolo = _vc
ok("Finale" in cup.testo_turno(S, 2), "/risultati Q2")
from shared import regole as RG
_sp = RG.SETTINGS_PATH
_cfg = json.load(open(_sp))
json.dump({**_cfg, "cup_fine_giorno": 5, "cup_fine_mese": 11}, open(_sp, "w")); _os.utime(_sp, (1, 1))
ok(QC.finestra(S) == (date(Y, 10, 30), date(Y, 11, 5)) and [g["numero"] for g in QC.giornate(S)["qual"]] == [1, 2],
   "date da settings.json: fine il 5/11 → qualificazione G1–G2, Q1 la G3")
json.dump({**_cfg, "cup_fine_giorno": 31, "cup_fine_mese": 11}, open(_sp, "w")); _os.utime(_sp, (2, 2))
ok(QC.finestra(S) == (date(Y, 10, 30), date(Y, 11, 27)), "data impossibile (31/11): i default")
json.dump(_cfg, open(_sp, "w")); _os.utime(_sp, (3, 3))

for t in ("lega_cup", "lega_cup_live", "lega_risultati", "lega_giornate", "lega_calcoli", "lega_calcoli_storico"):
    db.q(f"TRUNCATE {t}")                            # pulizia: le altre prove non si aspettano queste giornate

import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.10.0 (Luca, 15/11): playoff, passo 1. Fine della regular season (avviso agli admin una volta), cosa manca per
il cambio di fase, passaggio (congelamento della regular season tranne l'ultima, seed 6 per conference, bozza agli
admin), /set_seed (scambio, scelte a mano che restano), conferma (canale, «soggetto a cambiamenti»), blocco alle 15
(ultima giornata congelata, primo turno e P1 in calendario con le gare 1 in casa della meglio classificata), le
giornate P fuori dalla classifica, il tabellone /playoff in tutti gli stati."""
import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import db, config
import classifica as C
import playoff as PO
from shared import codici_giornata as CG
from shared import playoff_base as PB
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)

# 14 squadre in due conference (la config delle prove ne ha 4): file temporanei, rimessi a posto alla fine
CFG = _os.path.dirname(config.TEAMS_PATH)
_teams = open(config.TEAMS_PATH, encoding="utf-8").read()
_glob = open(config.GLOBALS_PATH, encoding="utf-8").read()
T = [f"po{i:02d}" for i in range(1, 15)]
json.dump({"teams": [{"id": t, "nome": f"Squadra {t[-2:]}", "gm_ids": [], "gm_nome": t} for t in T]},
          open(config.TEAMS_PATH, "w", encoding="utf-8"))
json.dump({"conference": {"Ovest": ["O"], "Est": ["E"]}, "team_div": {t: ("O" if i < 7 else "E") for i, t in enumerate(T)}},
          open(_os.path.join(CFG, "divisions.json"), "w", encoding="utf-8"))
try:
    db.init_db()
    import calendario_playoff as CP
    CP.migra(); PO.migra()
    S = config.stagione()
    Y = int(S) + 1
    for t in ("lega_giornate", "lega_giornate_playoff", "lega_risultati", "lega_partite", "lega_playoff", "lega_seed",
              "lega_serie", "lega_avvisi_playoff", "lega_congelamento", "lega_cup", "lega_calcoli"):
        db.q(f"TRUNCATE {t}")
    for n, dal, al in ((1, date(Y, 3, 1), date(Y, 3, 7)), (2, date(Y, 3, 8), date(Y, 3, 14)), (3, date(Y, 3, 15), date(Y, 3, 21))):
        db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES (%s, %s, 'regular', %s, %s)", (S, n, dal, al))
    coppie = {1: [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14)],
              2: [(1, 14), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13)],
              3: [(1, 13), (2, 14), (3, 5), (4, 6), (7, 9), (8, 10), (11, 12)]}

    def gioca(n, conv=True):
        for a, b in coppie[n]:
            pa, pb = 500 - a * 5, 500 - b * 5
            db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince, convalidato)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                 (S, n, T[a - 1], T[b - 1], pa, pb, "casa" if pa - pb >= 5 else "trasferta", datetime.now(timezone.utc) if conv else None))
    gioca(1); gioca(2)
    ok(any("non è ancora convalidata" in x for x in PB.problemi_passaggio(S)) and any("importa_playoff" in x for x in PB.problemi_passaggio(S)),
       f"prima: manca l'ultima giornata e il calendario dei playoff {PB.problemi_passaggio(S)}")
    gioca(3)
    for k in (1, 2, 3):
        d0 = date(Y, 3, 22) + timedelta(days=2 * (k - 1))
        db.q("INSERT INTO lega_giornate_playoff (stagione, numero_p, giorni, dal, al) VALUES (%s, %s, %s, %s, %s)",
             (S, k, [d0, d0 + timedelta(days=1)], d0, d0 + timedelta(days=1)))
    ok(PB.problemi_passaggio(S) == [], "regular season finita e calendario dei playoff importato: si può passare")

    class Bot:
        def __init__(self):
            self.msg, self.foto, self.mod = [], [], []

        async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **k):
            self.msg.append((chat_id, text, reply_markup))
            return type("M", (), {"message_id": 500 + len(self.msg)})()

        async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, **k):
            self.foto.append((chat_id, caption, photo[:4]))
            return type("M", (), {"message_id": 700 + len(self.foto)})()

        async def edit_message_media(self, chat_id, message_id, media, **k):
            self.mod.append((chat_id, message_id, media.caption))

        async def edit_message_reply_markup(self, **k):
            pass

    bot = Bot()
    ok(asyncio.run(PO.fine_regular_season(bot, S, 2)) == "", "convalida di una giornata che non è l'ultima: niente")
    r = asyncio.run(PO.fine_regular_season(bot, S, 3))
    asyncio.run(PO.fine_regular_season(bot, S, 3))
    ok(r and len(bot.msg) == 1 and bot.msg[0][0] == -2 and "Regular season finita" in bot.msg[0][1] and "/set_fase" in bot.msg[0][1],
       "convalida dell'ultima: avviso al gruppo admin, una volta sola")

    # prima del cambio di fase: /playoff «se finisse oggi»
    dp = PO.dati_tabellone(S)
    ok(dp["conf_sopra"] == "Ovest" and dp["conf_sotto"] == "Est", "nomi delle conference da divisions.json, anche nel riquadro della finale")
    ok(dp["adesso"] == "Proiezione" and "finisse oggi" in dp["fase"] and dp["ovest"]["nome"] == "Conference Ovest"
       and dp["ovest"]["r1"][0]["a"]["seed"] == "4", "/playoff prima dei playoff: proiezione dalla classifica")
    cc = PO.classifica_conference(S)
    atteso = {c: [r["team"] for r in rr[:6]] for c, rr in cc.items()}
    ok(PO.seed_calcolati(S) == atteso and all(len(v) == 6 for v in atteso.values()), "6 seed per conference, nell'ordine della classifica")

    # cambio di fase → passaggio
    json.dump({**json.loads(_glob), "fase": "playoff"}, open(config.GLOBALS_PATH, "w"))
    ctx = type("C", (), {"bot": bot})()
    asyncio.run(PO.job_passaggio(ctx))
    st = PO.stato(S)
    cong = {r["giornata"]: r["congelata"] for r in db.q("SELECT * FROM lega_congelamento WHERE stagione = %s", (S,), many=True)}
    ok(st and st["stato"] == "bozza" and cong == {1: True, 2: True}, f"passaggio: bozza, congelate tutte tranne l'ultima {cong}")
    ok(PO.seed(S) == atteso and len(bot.foto) == 1 and any("bozza del tabellone" in m[1] and "set_seed" in m[1] for m in bot.msg)
       and bot.msg[-1][2] is not None, "bozza al gruppo admin: tabellone, posizioni, come cambiarle, bottone di conferma")
    asyncio.run(PO.job_passaggio(ctx))
    ok(len(bot.foto) == 1, "il passaggio si fa una volta sola")

    # /set_seed
    sett = cc["Ovest"][6]["team"]
    terza = atteso["Ovest"][2]
    es = PO.imposta_seed(S, sett, 3)
    sv = PO.seed_salvati(S)["Ovest"]
    ok(sv[3]["team"] == sett and sv[3]["manuale"] and terza not in [v["team"] for v in sv.values()] and "fuori dai playoff" in es,
       f"/set_seed con una squadra fuori: entra al 3, chi c'era esce ({es})")
    es2 = PO.imposta_seed(S, atteso["Ovest"][0], 2)
    sv = PO.seed_salvati(S)["Ovest"]
    ok(sv[2]["team"] == atteso["Ovest"][0] and sv[1]["team"] == atteso["Ovest"][1], f"/set_seed dentro: scambio ({es2})")
    PO.aggiorna_seed(S)
    sv = PO.seed_salvati(S)["Ovest"]
    ok(sv[3]["team"] == sett and sv[2]["team"] == atteso["Ovest"][0], "un ricalcolo tiene le scelte a mano")
    try:
        PO.imposta_seed(S, sett, 7); _err = False
    except ValueError:
        _err = True
    ok(_err, "seed oltre il 6: errore")

    # conferma
    esito = asyncio.run(PO.conferma(bot, S, None))
    st = PO.stato(S)
    ok(st["stato"] == "confermato" and bot.foto[-1][0] == -1 and "Soggetto a cambiamenti fino alle 15:00" in bot.foto[-1][1],
       f"conferma: sul canale, soggetto a cambiamenti fino alle 15 ({esito})")
    ok(PO.ora_blocco(S) == datetime(Y, 3, 22, 15, 0, tzinfo=PO.ROMA), "il blocco: alle 15 del giorno dopo l'ultima notte")
    asyncio.run(PO.job_passaggio(ctx))
    ok(PO.stato(S)["stato"] == "confermato", "prima delle 15 non si blocca")

    # alle 15: blocco
    _ob = PO.ora_blocco
    PO.ora_blocco = lambda s: datetime.now(timezone.utc) - timedelta(minutes=1)
    asyncio.run(PO.job_passaggio(ctx))
    PO.ora_blocco = _ob
    st = PO.stato(S)
    g4 = db.giornata(S, 4)
    pp = db.q("SELECT casa, trasferta FROM lega_partite WHERE stagione = %s AND giornata = 4 ORDER BY casa", (S,), many=True)
    ser = db.q("SELECT * FROM lega_serie WHERE stagione = %s ORDER BY conference, slot", (S,), many=True)
    sd = PO.seed(S)
    ok(st["stato"] == "bloccato" and g4 and g4["tipo"] == "playoff" and g4["dal"] == date(Y, 3, 22) and len(pp) == 4 and len(ser) == 4,
       "blocco: P1 = G4 in calendario coi giorni importati, 4 serie, 4 gare 1")
    ok({(p["casa"], p["trasferta"]) for p in pp} == {(sd[c][a - 1], sd[c][b - 1]) for c in sd for _s, a, b in PO.PRIMO_TURNO}
       and all(x["al_meglio"] == 5 and x["inizio"] == 4 for x in ser), "gara 1: 4–5 e 3–6, in casa la meglio classificata; al meglio delle 5")
    ok(db.q("SELECT congelata FROM lega_congelamento WHERE stagione = %s AND giornata = 3", (S,), one=True)["congelata"],
       "blocco: anche l'ultima giornata di regular season congelata")
    ok(any("bloccato" in m[1] for m in bot.msg) and bot.mod and "definitivo" in bot.mod[-1][2], "agli admin e il tabellone definitivo sul canale")
    # v7.27.1 (Luca, 23/11): al blocco la classifica finale per la lottery e il draft
    _cf = db.q("SELECT team, posto, playoff FROM lega_classifica_finale WHERE stagione = %s ORDER BY posto", (S,), many=True) or []
    _ai = {t for tt in PO.seed(S).values() for t in tt}
    ok(len(_cf) == len(config.squadre()) and [r["posto"] for r in _cf] == list(range(1, len(_cf) + 1))
       and {r["team"] for r in _cf if r["playoff"]} == _ai, f"classifica finale salvata per la lottery {_cf}")
    ok(CG.numero("P1", S) == 4 and PB.in_gioco(db.q, S, g4) == {x for p in pp for x in (p["casa"], p["trasferta"])}
       and PB.in_gioco(db.q, S, db.giornata(S, 3)) is None, "P1 = G4; nella P1 giocano solo le 8 squadre del primo turno")
    prima = [(r["team"], r["w"]) for r in C.calcola(S)[0]]
    db.q("INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince, convalidato) VALUES (%s, 4, %s, %s, 1, 900, 'trasferta', NOW())",
         (S, pp[0]["casa"], pp[0]["trasferta"]))
    ok([(r["team"], r["w"]) for r in C.calcola(S)[0]] == prima, "i risultati delle giornate P non contano in classifica")
    try:
        PO.imposta_seed(S, sett, 1); _bl = False
    except ValueError:
        _bl = True
    ok(_bl, "a tabellone bloccato i seed non si cambiano")
    dfin = PO.dati_tabellone(S)
    ok(dfin["adesso"] == "Primo turno" and "P1 (G4)" in dfin["fase"], f"/playoff dopo il blocco: {dfin['fase']}")
    try:
        import typst  # noqa: F401
        png = PO.immagine(dfin); png0 = PO.immagine(dp)
        ok(png[:4] == b"\x89PNG" and png0[:4] == b"\x89PNG", "immagini del tabellone (proiezione e primo turno)")
        if _os.environ.get("PO_PNG"):
            open(_os.environ["PO_PNG"], "wb").write(png)
            open(_os.environ["PO_PNG"].replace(".png", "_proiezione.png"), "wb").write(png0)
    except ImportError:
        pass

    # ── passo 2 (v7.11.0): serie, turni, una giornata P alla volta, campione ──
    for k in range(4, 23):
        d0 = date(Y, 3, 22) + timedelta(days=2 * (k - 1))
        db.q("INSERT INTO lega_giornate_playoff (stagione, numero_p, giorni, dal, al) VALUES (%s, %s, %s, %s, %s)",
             (S, k, [d0, d0 + timedelta(days=1)], d0, d0 + timedelta(days=1)))
    perde_alta = {(4, pp[0]["casa"])}                  # gara 1 della prima serie: l'ha vinta la bassa (sopra)

    def convalida_p(n, eccezioni=(), rifai=False):
        """Risultati della giornata n: vince la meglio classificata della serie, tranne le partite (n, casa) in eccezioni."""
        if rifai:
            db.q("DELETE FROM lega_risultati WHERE stagione = %s AND giornata = %s", (S, n))
        gia = {r["casa"] for r in db.q("SELECT casa FROM lega_risultati WHERE stagione = %s AND giornata = %s", (S, n), many=True) or []}
        for p in db.q("SELECT casa, trasferta FROM lega_partite WHERE stagione = %s AND giornata = %s", (S, n), many=True):
            if p["casa"] in gia:
                continue
            x = next(y for y in PO.serie(S) if {y["alta"], y["bassa"]} == {p["casa"], p["trasferta"]} and not (y["inizio"] or 0) > n)
            vince_alta = (n, p["casa"]) not in eccezioni
            chi = x["alta"] if vince_alta else x["bassa"]
            db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince, convalidato)
                    VALUES (%s, %s, %s, %s, 500, 480, %s, NOW())""",
                 (S, n, p["casa"], p["trasferta"], "casa" if chi == p["casa"] else "trasferta"))
        db.q("""INSERT INTO lega_calcoli (stagione, giornata, stato, risultati) VALUES (%s, %s, 'convalidata', '[]')
                ON CONFLICT (stagione, giornata) DO UPDATE SET stato = 'convalidata'""", (S, n))
        return asyncio.run(PO.dopo_convalida(bot, S, n))

    def partite(n):
        return [(r["casa"], r["trasferta"]) for r in
                db.q("SELECT casa, trasferta FROM lega_partite WHERE stagione = %s AND giornata = %s ORDER BY casa", (S, n), many=True) or []]

    s0 = next(x for x in PO.serie(S) if x["alta"] == pp[0]["casa"] or x["bassa"] == pp[0]["casa"])
    e4 = convalida_p(4)
    ok(PO.serie(S) and next(x for x in PO.serie(S) if x["id"] == s0["id"])["vinte_bassa"] == 1 and len(partite(5)) == 4
       and (s0["bassa"], s0["alta"]) in partite(5) and db.giornata(S, 5)["tipo"] == "playoff", f"P1 convalidata: serie 0-1, P2 con le gare 2 (in casa la bassa) ({e4})")
    ok(any("P2 (G5)" in m[1] and "gara 2" in m[1] for m in bot.msg), "agli admin: la P2 e le sue partite")
    ok(convalida_p(4).endswith("tabellone già aggiornato sul canale") or "P2 già in calendario" in convalida_p(4),
       "convalida rifatta uguale: la P2 resta com'è")
    convalida_p(5); convalida_p(6)
    ss = PO.serie(S)
    ok(sum(1 for x in ss if x["vincente"]) == 3 and partite(7) == [(s0["bassa"], s0["alta"])],
       f"dopo la P3: tre serie 3-0, nella P4 solo la gara 4 della serie ancora aperta ({partite(7)})")
    e7 = convalida_p(7)
    sd = PO.seed(S)
    t2 = [x for x in PO.serie(S) if x["turno"] == 2]
    ok(len(t2) == 4 and all(x["inizio"] == 8 and x["alta"] in (sd[x["conference"]][0], sd[x["conference"]][1]) for x in t2)
       and sorted(partite(8)) == sorted((x["alta"], x["bassa"]) for x in t2), f"serie finita 3-1: semifinali di conference dalla P5, 1 e 2 in casa ({e7})")
    ok(any("Si apre il turno" in m[1] and "semifinali" in m[1] for m in bot.msg), "agli admin: si apre il turno")
    # una convalida rifatta della P4 cambia il vincitore: la serie non è finita, la P5 cambia
    convalida_p(7, eccezioni={(7, s0["bassa"])}, rifai=True)
    ok(partite(8) == [(s0["alta"], s0["bassa"])] and not [x for x in PO.serie(S) if x["turno"] == 2],
       f"convalida rifatta (2-2): la P5 diventa la gara 5, via le semifinali ({partite(8)})")
    ok(db.q("SELECT 1 FROM registro_azioni WHERE azione = 'playoff: giornata in calendario (partite cambiate)' AND oggetto = 'P5 (G8)'", one=True),
       "registro: la P5 rifatta, «partite cambiate»")
    convalida_p(7, rifai=True)
    ok(len(partite(8)) == 4, "rimessa a posto: di nuovo le semifinali nella P5")
    db.q("UPDATE lega_giornate SET prima_partita = NOW() - INTERVAL '1 hour' WHERE stagione = %s AND numero = 8", (S,))
    prima7 = __import__("live")._esiti(S, 7)
    db.q("UPDATE lega_risultati SET vince = CASE vince WHEN 'casa' THEN 'trasferta' ELSE 'casa' END WHERE stagione = %s AND giornata = 7", (S,))
    n_msg = len(bot.msg)
    e7b = asyncio.run(PO.dopo_convalida(bot, S, 7, prima=prima7))
    ok(len(partite(8)) == 4 and len(bot.msg) == n_msg + 1 and "già iniziata" in bot.msg[-1][1],
       f"P5 già iniziata: non si tocca, avviso agli admin ({e7b})")
    ok(db.q("SELECT 1 FROM registro_azioni WHERE azione = 'playoff: giornata già iniziata non cambiata'", one=True),
       "registro: la giornata già iniziata non toccata")
    db.q("UPDATE lega_risultati SET vince = CASE vince WHEN 'casa' THEN 'trasferta' ELSE 'casa' END WHERE stagione = %s AND giornata = 7", (S,))
    PO.aggiorna_serie(S)
    for n in (8, 9, 10):
        convalida_p(n)
    t3 = [x for x in PO.serie(S) if x["turno"] == 3]
    ok(len(t3) == 2 and all(x["slot"] == "cf" and x["inizio"] == 11 for x in t3), "finali di conference dalla P8")
    for n in (11, 12, 13):
        convalida_p(n)
    f = next((x for x in PO.serie(S) if x["turno"] == 4), None)
    posto = PO.posto_generale(S)
    ok(f and f["al_meglio"] == 7 and f["conference"] == "" and posto[f["alta"]] < posto[f["bassa"]] and partite(14) == [(f["alta"], f["bassa"])],
       "finale al meglio delle 7, in casa la meglio classificata nella classifica generale")
    d_f = PO.dati_tabellone(S)
    ok(d_f["finale"] and d_f["finale"]["a"]["nome"] == config.nome(f["alta"]) and d_f["adesso"] == "Finale"
       and d_f["ovest"]["r3"]["tipo"] == "serie" and d_f["ovest"]["r3"]["fine"], f"/playoff in finale: {d_f['fase']}")
    g14 = dict(db.giornata(S, 14)); dl = {"partite": [{}]}
    PO.titoli_live(g14, dl, [{"casa": f["alta"], "trasferta": f["bassa"]}])
    ok(dl["titolo"] == "P11 · Giornata 14" and dl["partite"][0]["titolo"] == "GARA 1 · FINALE", f"live: {dl}")
    for n in (14, 15, 16):
        convalida_p(n)
    ecamp = convalida_p(17)
    st = PO.stato(S)
    ok(st["campione"] == f["alta"] and db.giornata(S, 18) is None and any("vince i playoff" in m[1] and m[0] == -1 for m in bot.msg),
       f"finale 4-0: campione, sul canale, nessuna P15 ({ecamp})")
    d_c = PO.dati_tabellone(S)
    if _os.environ.get("PO_PNG"):
        open(_os.environ["PO_PNG"].replace(".png", "_campione.png"), "wb").write(PO.immagine(d_c))
    ok(d_f["finale"]["a"]["conf"].endswith("Ovest") or d_f["finale"]["a"]["conf"].endswith("Est"), "in finale sotto il nome il piazzamento nella conference")
    ok(d_c["adesso"] == "Campione" and d_c["campione"]["nome"] == config.nome(f["alta"]) and "campione" in bot.mod[-1][2],
       "tabellone: campione, anche sul canale")
    ok(asyncio.run(PO.dopo_convalida(bot, S, 3)) == "", "convalida di regular season: niente playoff")
    # v7.15.0 (Luca, 15/11): i tab del foglio di calcolo si chiamano P nei playoff; i playoff in un foglio a parte
    import risultati as R_, foglio as F_
    ok(R_.nome_tab(db.giornata(S, 5), S) == "Calcolo P2" and R_.nome_tab(db.giornata(S, 3), S) == "Calcolo G3" and R_.nome_tab(7, S) == "Calcolo P4",
       "tab del foglio di calcolo: «Calcolo P2» nei playoff, «Calcolo G3» in regular season")
    gp = F_.griglia_playoff(S)
    if _os.environ.get("PO_CSV"):
        import csv as _csv
        _csv.writer(open(_os.environ["PO_CSV"], "w", newline="")).writerows(gp)
    ok(all(len(r) == 23 for r in gp) and gp[1][1] == f"PLAYOFF QUASI FRIENDS {S}/{int(S) + 1}" and gp[3][7] == "OVEST" and gp[3][16] == "EST"
       and gp[4][2] == "Teste di Serie" and gp[6][7] == "Primo Turno" and gp[6][13] == "FINALS" and gp[6][21] == "Primo Turno",
       "foglio dei playoff: titolo, conference, intestazioni del tabellone, colonne A–W come il vecchio foglio")
    sd_ = PO.seed(S)
    ok([gp[10 + i][2] for i in range(6)] == [config.nome(t) for t in sd_["Ovest"]] and gp[10][1] == 1 and gp[15][5] == config.nome(sd_["Est"][5]),
       "foglio dei playoff: le teste di serie delle due conference")
    s36 = next(x for x in PO.serie(S) if x["turno"] == 1 and x["conference"] == "Ovest" and x["slot"] == "3-6")
    ok(gp[8][7] == config.nome(s36["alta"]) and gp[8][8] == s36["vinte_alta"] and gp[9][7] == config.nome(s36["bassa"]),
       "foglio dei playoff: primo turno nel tabellone con le vittorie")
    ok(gp[12][13] and gp[12][16] and {gp[12][14], gp[12][15]} == {4, 0}, "foglio dei playoff: le finals al centro")
    i_pt = next(i for i, r in enumerate(gp) if r[2] == "PRIMO TURNO")
    ok(gp[i_pt][6] == "SERIE" and gp[i_pt + 3][0] == "DATA" and "/" in gp[i_pt + 4][0] and gp[i_pt + 3][3] != "" and "-" in gp[i_pt + 3][6],
       "foglio dei playoff: le giornate (DATA, giorni, partite coi punti e la serie)")
    ok(any(r[2] == "FINALS" for r in gp) and F_.nome_foglio_playoff(S) == f"Playoff {int(S) % 100:02d}-{(int(S) + 1) % 100:02d}",
       "foglio dei playoff: «Playoff 26-27»")
    gp2, stili_ = F_.dati_playoff(S)
    ok(gp2 == gp and any(x["range"] == "B2:W2" and x.get("unisci") and x.get("dimensione") == 18 for x in stili_)
       and any(x["range"] == "N13:Q13" for x in stili_) and any(x.get("formato") == "0.00" for x in stili_)
       and any(x.get("unisci") and x["range"].startswith("N14") for x in stili_),
       "foglio dei playoff: la formattazione (titolo, finals, punteggi, campione)")
    if _os.environ.get("PO_CSV"):
        import json as _json
        open(_os.environ["PO_CSV"] + ".stili.json", "w").write(_json.dumps(stili_))
    mandati_f = []
    async def manda_f(payload):
        mandati_f.append(payload); return {"ok": True, "righe": len(payload["righe"])}
    ef = asyncio.run(F_.aggiorna_playoff(S, manda_f))
    ok(mandati_f and mandati_f[0]["stili"] and mandati_f[0]["larghezze"][3] == 170, "foglio dei playoff: stili e larghezze al gas")
    ok(mandati_f and mandati_f[0]["foglio"] == F_.nome_foglio_playoff(S) and mandati_f[0]["action"] == "calendario" and "ricaricato" in ef,
       "foglio dei playoff: stessa azione del Calendario, col suo foglio")
    ok(F_.griglia_playoff("1998") == [], "senza giornate P: niente foglio dei playoff")
    try:
        import typst  # noqa: F401
        png = PO.immagine(d_f)
        ok(png[:4] == b"\x89PNG", "immagine del tabellone in finale")
        if _os.environ.get("PO_PNG"):
            open(_os.environ["PO_PNG"].replace(".png", "_finale.png"), "wb").write(png)
    except ImportError:
        pass
finally:
    open(config.TEAMS_PATH, "w", encoding="utf-8").write(_teams)
    open(config.GLOBALS_PATH, "w", encoding="utf-8").write(_glob)
    try:
        _os.remove(_os.path.join(CFG, "divisions.json"))
    except FileNotFoundError:
        pass
    for t in ("lega_giornate", "lega_giornate_playoff", "lega_risultati", "lega_partite", "lega_playoff", "lega_seed",
              "lega_serie", "lega_avvisi_playoff", "lega_congelamento", "lega_calcoli", "lega_classifica_finale"):
        db.q(f"TRUNCATE {t}")

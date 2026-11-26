import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.35.5: prova generale dei playoff col calcolo vero. 14 squadre, regular season finita, passaggio (bozza, conferma,
blocco), poi ogni giornata P come nella realtà: partite NBA e tabellini dei giocatori delle squadre in campo,
formazioni e panchine congelate, calcolo di loucabot (handlers_risultati.esegui), convalida col bottone dell'admin
(cb_risultati: risultati, live, foglio, playoff.dopo_convalida), fino alla campione. Controlla a ogni giornata: niente
pareggi, il bonus casa dei playoff, le serie contate come i risultati, nel calendario solo chi gioca, una sorpresa
(la bassa che vince una serie al primo turno), le eliminate fuori; alla fine la campione e il via libera ai rinnovi
del bot principale (playoff_base.problemi_fine_stagione)."""
import asyncio
import json
import types
from datetime import date, datetime, timedelta, timezone

import db, config
import playoff as PO
import calendario_playoff as CP
import handlers_risultati as HR
import risultati as R
from shared import codici_giornata as CG
from shared import playoff_base as PB
from shared import regole
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)

CFG = _os.path.dirname(config.TEAMS_PATH)
_teams = open(config.TEAMS_PATH, encoding="utf-8").read()
_glob = open(config.GLOBALS_PATH, encoding="utf-8").read()
_div_path = _os.path.join(CFG, "divisions.json")
_div = open(_div_path, encoding="utf-8").read() if _os.path.exists(_div_path) else None
T = [f"po{i:02d}" for i in range(1, 15)]
NBA = ["ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU", "IND", "LAC", "LAL"]
SQ_NBA = dict(zip(T, NBA))
json.dump({"teams": [{"id": t, "nome": f"Squadra {t[-2:]}", "gm_ids": [], "gm_nome": t} for t in T]},
          open(config.TEAMS_PATH, "w", encoding="utf-8"))
json.dump({"conference": {"Ovest": ["O"], "Est": ["E"]}, "team_div": {t: ("O" if i < 7 else "E") for i, t in enumerate(T)}},
          open(_div_path, "w", encoding="utf-8"))
try:
    db.init_db()
    CP.migra(); PO.migra()
    import live as _LV; _LV.migra()
    import congelamento as _CG; _CG.migra()
    S = config.stagione()
    Y = int(S) + 1
    for t in ("lega_giornate", "lega_giornate_playoff", "lega_risultati", "lega_partite", "lega_playoff", "lega_seed",
              "lega_serie", "lega_avvisi_playoff", "lega_congelamento", "lega_calcoli", "lega_calcoli_storico",
              "nba_tabellini", "nba_partite", "nba_infortuni", "ipa_formazioni", "ipa_panchine", "ipa_stato_giornata"):
        try:
            db.q(f"TRUNCATE {t}")
        except Exception:
            pass
    db.q("DELETE FROM giocatori WHERE espn_id LIKE 'pp%%'")

    # ── regular season: tre giornate convalidate, classifica netta (po01 la migliore, po14 la peggiore) ──
    coppie = {1: [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14)],
              2: [(1, 14), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13)],
              3: [(1, 13), (2, 14), (3, 5), (4, 6), (7, 9), (8, 10), (11, 12)]}
    for n, dal in ((1, date(Y, 3, 1)), (2, date(Y, 3, 8)), (3, date(Y, 3, 15))):
        db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES (%s, %s, 'regular', %s, %s)",
             (S, n, dal, dal + timedelta(days=6)))
        for a, b in coppie[n]:
            pa, pb = 500 - a * 5, 500 - b * 5
            db.q("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES (%s, %s, %s, %s)", (S, n, T[a - 1], T[b - 1]))
            db.q("""INSERT INTO lega_risultati (stagione, giornata, casa, trasferta, punti_casa, punti_trasferta, vince, convalidato)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())""", (S, n, T[a - 1], T[b - 1], pa, pb, "casa" if pa > pb else "trasferta"))
    # calendario dei playoff: 20 giornate P di due notti
    for k in range(1, 21):
        d0 = date(Y, 3, 22) + timedelta(days=2 * (k - 1))
        db.q("INSERT INTO lega_giornate_playoff (stagione, numero_p, giorni, dal, al) VALUES (%s, %s, %s, %s, %s)",
             (S, k, [d0, d0 + timedelta(days=1)], d0, d0 + timedelta(days=1)))
    ok(PB.problemi_passaggio(S) == [], "regular season finita e calendario dei playoff: il bot principale lascia passare")
    ok(PB.problemi_fine_stagione(S) and "nessun tabellone" in PB.problemi_fine_stagione(S)[0],
       "ai rinnovi non ancora: i playoff non sono giocati")

    class Bot:
        def __init__(self):
            self.msg, self.foto = [], []

        async def send_message(self, chat_id=None, text=None, **k):
            self.msg.append((chat_id, text))
            return types.SimpleNamespace(message_id=500 + len(self.msg))

        async def send_photo(self, chat_id=None, photo=None, caption=None, **k):
            self.foto.append((chat_id, caption))
            return types.SimpleNamespace(message_id=700 + len(self.foto))

        def __getattr__(self, nome):                      # edit_*, delete_*, pin_*…: niente
            async def _f(*a, **k):
                return types.SimpleNamespace(message_id=1)
            return _f

    bot = Bot()
    ctx = types.SimpleNamespace(bot=bot, application=None)

    # ── passaggio: fase playoff, bozza, conferma, blocco ──
    json.dump({**json.loads(_glob), "fase": "playoff"}, open(config.GLOBALS_PATH, "w"))
    asyncio.run(PO.job_passaggio(ctx))
    asyncio.run(PO.conferma(bot, S, None))
    _ob = PO.ora_blocco
    PO.ora_blocco = lambda s: datetime.now(timezone.utc) - timedelta(minutes=1)
    asyncio.run(PO.job_passaggio(ctx))
    PO.ora_blocco = _ob
    ok(PO.stato(S)["stato"] == "bloccato" and CG.ultima_rs(S) == 3 and db.giornata(S, 4)["tipo"] == "playoff",
       "passaggio: bozza, conferma, blocco; P1 = G4 in calendario")
    posto = PO.posto_generale(S)
    sd = PO.seed(S)
    in_playoff = {t for v in sd.values() for t in v}
    ok(len(in_playoff) == 12 and posto[T[0]] == 1, "12 squadre ai playoff, po01 prima di tutte")

    # ── giocatori: 5 titolari e 3 in panchina per squadra, tutti della squadra NBA della squadra ──
    gid = {}
    for t in T:
        for k in range(8):
            a = f"pp{t[-2:]}{k}"
            gid[(t, k)] = db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id",
                               (f"Prova {a}", f"Prova {a}", f"prova {a}", a), one=True)["id"]
    # la sorpresa: al primo turno la bassa della prima serie dell'Ovest vince tutte le sue gare
    s_sorpresa = next(x for x in PO.serie(S) if x["conference"] == "Ovest")
    sorpresa = s_sorpresa["bassa"]
    BONUS = regole.bonus_casa(playoff=True)

    spenta = set()                                       # giornate in cui la sorpresa non c'è (il ricalcolo che ribalta)

    def forza(t, n):
        """Fantapunti di ogni titolare di t nella giornata n: la meglio classificata è più forte (3 a posto),
        tranne la sorpresa nelle giornate del primo turno."""
        base = 60 - 3 * posto[t]
        if t == sorpresa and n not in spenta and any(x["id"] == s_sorpresa["id"] and not x["vincente"] for x in PO.serie(S)):
            base += 40
        return base

    def gioca(n):
        """Partite NBA e tabellini delle notti della giornata n, formazioni e panchine congelate delle squadre in campo."""
        g = db.giornata(S, n)
        partite = db.q("SELECT casa, trasferta FROM lega_partite WHERE stagione = %s AND giornata = %s", (S, n), many=True)
        giorni = [g["dal"] + timedelta(days=i) for i in range((g["al"] - g["dal"]).days + 1)]
        for i, d in enumerate(giorni):
            for p in partite:
                pid = f"pp{n}-{i}-{p['casa']}"
                db.salva_partite_nba([{"espn_id": pid, "stagione": S, "tipo": 3, "data_et": d, "casa": SQ_NBA[p["casa"]],
                                       "trasferta": SQ_NBA[p["trasferta"]], "stato": "STATUS_FINAL",
                                       "inizio": datetime(d.year, d.month, d.day, 23, 0, tzinfo=timezone.utc)}])
                righe = []
                for t in (p["casa"], p["trasferta"]):
                    for k in range(8):
                        righe.append({"partita": pid, "atleta": f"pp{t[-2:]}{k}", "nome": "x", "squadra": SQ_NBA[t],
                                      "titolare": k < 5, "giocato": True, "minuti": 30, "pts": 0, "fgm": 0, "fga": 0,
                                      "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0, "oreb": 0, "dreb": 0, "ast": 0, "stl": 0,
                                      "blk": 0, "tov": 0, "pf": 0, "fp": forza(t, n) if k < 5 else 10 + k})
                db.salva_tabellino(pid, righe)
        db.q("DELETE FROM ipa_formazioni WHERE stagione = %s AND giornata = %s", (S, n))
        for p in partite:
            for t in (p["casa"], p["trasferta"]):
                for ruolo, k in zip(R.RUOLI, range(5)):
                    db.q("INSERT INTO ipa_formazioni (stagione, giornata, team_id, ruolo, giocatore_id) VALUES (%s, %s, %s, %s, %s)",
                         (S, n, t, ruolo, gid[(t, k)]))
                db.q("""INSERT INTO ipa_panchine (stagione, giornata, team_id, righe) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (stagione, giornata, team_id) DO NOTHING""",
                     (S, n, t, json.dumps([{"giocatore_id": gid[(t, k)], "testo": f"P{k}", "ruolo": r}
                                           for k, r in zip(range(5, 8), ("PG", "SF", "C"))])))
        db.q("INSERT INTO ipa_stato_giornata (stagione, giornata, chiusa) VALUES (%s, %s, NOW()) ON CONFLICT DO NOTHING", (S, n))
        return [(p["casa"], p["trasferta"]) for p in partite]

    def convalida(n):
        asyncio.run(HR.esegui(bot, S, n, "prova"))
        v = db.q("SELECT versione FROM lega_calcoli WHERE stagione = %s AND giornata = %s", (S, n), one=True)["versione"]
        q = types.SimpleNamespace(data=f"rc:ok:{n}:{v}", message=types.SimpleNamespace(chat_id=-2, message_id=1), risposte=[])

        async def _ans(t=None, show_alert=False):
            q.risposte.append(t)
        q.answer = _ans

        async def _nulla(*a, **k):
            pass
        q.edit_message_reply_markup = _nulla
        q.edit_message_text = _nulla
        u = types.SimpleNamespace(callback_query=q, effective_user=types.SimpleNamespace(id=900, full_name="Admin", first_name="Admin"))
        asyncio.run(HR.cb_risultati(u, ctx))
        return q.risposte

    # ── le giornate P, una alla volta, fino alla campione ──
    problemi, giocate, eliminate_in_campo = [], [], []
    ribalta = {}
    n = 4
    while n < 30 and not (PO.stato(S) or {}).get("campione"):
        if not db.giornata(S, n):
            problemi.append(f"G{n} non in calendario e campione non ancora decisa"); break
        partite = gioca(n)
        fuori = {t for x in PO.serie(S) if x["vincente"] for t in (x["alta"], x["bassa"]) if t != x["vincente"]}
        eliminate_in_campo += [t for p in partite for t in p if t in fuori or t not in in_playoff]
        forze = {t: forza(t, n) for p in partite for t in p}          # prima della convalida, che può chiudere la serie
        risp = convalida(n)
        ris = db.q("SELECT * FROM lega_risultati WHERE stagione = %s AND giornata = %s", (S, n), many=True) or []
        if len(ris) != len(partite) or not all(r["convalidato"] for r in ris):
            problemi.append(f"G{n}: {len(ris)} risultati convalidati su {len(partite)} partite ({risp})")
        for r in ris:
            if r["punti_casa"] == r["punti_trasferta"] and not r["supplementari"]:
                problemi.append(f"G{n}: pareggio {r['casa']}-{r['trasferta']}")
            atteso = "casa" if forze[r["casa"]] * 5 + BONUS > forze[r["trasferta"]] * 5 else "trasferta"
            if r["vince"] != atteso:
                problemi.append(f"G{n}: {r['casa']}-{r['trasferta']} vince {r['vince']}, atteso {atteso} "
                                f"({r['punti_casa']}-{r['punti_trasferta']})")
        giocate.append(n)
        # il ricalcolo che ribalta: la gara che ha chiuso la serie della sorpresa, corretta, la vince l'alta. La serie si
        # riapre e la giornata dopo torna ad avere la sua gara
        x = next(y for y in PO.serie(S) if y["id"] == s_sorpresa["id"])
        if x["vincente"] and not ribalta:
            spenta.add(n)
            gioca(n)
            convalida(n)
            x2 = next(y for y in PO.serie(S) if y["id"] == s_sorpresa["id"])
            dopo = db.q("SELECT casa, trasferta FROM lega_partite WHERE stagione = %s AND giornata = %s", (S, n + 1), many=True) or []
            ribalta = {"giornata": n, "riaperta": not x2["vincente"] and x2["vinte_alta"] + x2["vinte_bassa"] == x["vinte_alta"] + x["vinte_bassa"],
                       "gara_dopo": any({p["casa"], p["trasferta"]} == {x2["alta"], x2["bassa"]} for p in dopo)}
        n += 1
    st = PO.stato(S)
    ok(not problemi, f"{len(giocate)} giornate P calcolate e convalidate col calcolo vero, risultati come le forze {problemi[:4]}")
    ok(not eliminate_in_campo, f"in calendario solo chi è ancora in corsa {eliminate_in_campo[:4]}")

    # le serie contate dai risultati convalidati
    sbagliate = []
    for x in PO.serie(S):
        vinte = {x["alta"]: 0, x["bassa"]: 0}
        for r in db.q("SELECT * FROM lega_risultati WHERE stagione = %s AND giornata >= %s", (S, x["inizio"]), many=True) or []:
            if {r["casa"], r["trasferta"]} == {x["alta"], x["bassa"]}:
                vinte[r["casa"] if r["vince"] == "casa" else r["trasferta"]] += 1
        if (vinte[x["alta"]], vinte[x["bassa"]]) != (x["vinte_alta"], x["vinte_bassa"]):
            sbagliate.append((x["turno"], x["alta"], x["bassa"], vinte, x["vinte_alta"], x["vinte_bassa"]))
        if x["vincente"] and max(vinte.values()) != PO.vinte_per_passare(x["al_meglio"]):
            sbagliate.append(("vinte", x["turno"], vinte))
    ok(not sbagliate, f"ogni serie: vittorie come i risultati convalidati, chiusa alla vittoria giusta {sbagliate[:3]}")
    ok(ribalta.get("riaperta") and ribalta.get("gara_dopo"),
       f"ricalcolo che ribalta la gara decisiva: la serie si riapre e la gara dopo torna in calendario {ribalta}")
    ok(next(x for x in PO.serie(S) if x["id"] == s_sorpresa["id"])["vincente"] == sorpresa,
       "la sorpresa: la bassa passa il primo turno (alla gara dopo)")
    turni = sorted({x["turno"] for x in PO.serie(S)})
    finale = next((x for x in PO.serie(S) if x["turno"] == max(turni)), None)
    ok(turni == [1, 2, 3, 4] and finale and finale["al_meglio"] == 7, f"quattro turni, finale al meglio delle 7 {turni}")
    ok(st and st["campione"] == T[0] and any("vince i playoff" in (m[1] or "") for m in bot.msg),
       f"campione la più forte, annunciata ({st and st['campione']})")
    ok(PB.problemi_fine_stagione(S) == [], "con la finale convalidata il bot principale lascia passare ai rinnovi")
    ok(not db.giornata(S, giocate[-1] + 1) or not db.q("SELECT 1 FROM lega_partite WHERE stagione = %s AND giornata = %s",
                                                     (S, giocate[-1] + 1), one=True),
       "dopo la finale niente altre partite in calendario")
    ok(any(m[0] == -1 for m in bot.msg) or bot.foto, "risultati e tabellone sul canale")
finally:
    open(config.TEAMS_PATH, "w", encoding="utf-8").write(_teams)
    open(config.GLOBALS_PATH, "w", encoding="utf-8").write(_glob)
    if _div is None:
        _os.remove(_div_path)
    else:
        open(_div_path, "w", encoding="utf-8").write(_div)
    for t in ("lega_giornate", "lega_giornate_playoff", "lega_risultati", "lega_partite", "lega_playoff", "lega_seed",
              "lega_serie", "lega_avvisi_playoff", "lega_congelamento", "lega_calcoli", "ipa_formazioni", "ipa_panchine",
              "ipa_stato_giornata"):
        try:
            db.q(f"TRUNCATE {t}")
        except Exception:
            pass

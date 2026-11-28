import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""klra v1: separazione dal database ufficiale (utente di sola lettura da setup_db.sql: niente scritture, niente
tabelle fuori elenco), motore coi sistemi (l'Ufficiale e la sua copia danno esattamente i risultati convalidati
della lega; pesi, bonus del giocatore e di squadra, chi non gioca, FADD, supplementari, pareggio, classifica a
punti), cache rifatta alla riconvalida, nessun effetto sui calcoli di loucabot."""
import importlib.util, json, os, random, subprocess, sys, tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "fantabasket-loucabot"))
import db, config, calcolo, nba, risultati as R          # noqa: E402
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)

spec = importlib.util.spec_from_file_location("ipadb", os.path.join(ROOT, "fantabasket-ipanchinari", "db.py"))
ipadb = importlib.util.module_from_spec(spec); spec.loader.exec_module(ipadb)
db.init_db(); ipadb.init_db()
db.q("TRUNCATE nba_tabellini, nba_infortuni, nba_atleti, lega_giornate, lega_partite, nba_partite, lega_risultati, "
     "lega_calcoli, lega_calcoli_storico, lega_status_validi")
db.q("TRUNCATE ipa_formazioni, ipa_panchine, ipa_stato_giornata")
S = config.stagione()
calcolo.oggi_et = lambda: date(2026, 12, 31)
db.q("DELETE FROM giocatori WHERE espn_id LIKE 'k%%' AND nome_common LIKE 'Klra %%'")
gid = {i: db.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id",
               (f"Klra {i}", f"Klra {i}", f"klra {i}", f"k{i}"), one=True)["id"] for i in range(1, 33)}
SQ_NBA = {i: ["NYK", "BOS", "PHX", "MIA"][i % 4] for i in range(1, 33)}
SQ_NBA[5] = "IND"                                          # IND non gioca nelle giornate: a media
rnd = random.Random(7)


def partita(pid, giorno, casa, trasf, pc=110, pt=100):
    db.salva_partite_nba([{"espn_id": pid, "stagione": S, "tipo": 2, "data_et": giorno, "casa": casa, "trasferta": trasf,
                           "inizio": datetime(giorno.year, giorno.month, giorno.day, 23, 0, tzinfo=timezone.utc),
                           "stato": "STATUS_FINAL", "punti_casa": pc, "punti_trasferta": pt}])


def stats(**x):
    base = {k: 0 for k in ("pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf")}
    base.update(x)
    return base


def casuali():
    fga = rnd.randint(4, 20); fgm = rnd.randint(1, fga); tpm = rnd.randint(0, min(fgm, 5)); fta = rnd.randint(0, 8); ftm = rnd.randint(0, fta)
    return stats(pts=2 * fgm + tpm + ftm, fgm=fgm, fga=fga, tpm=tpm, tpa=tpm + rnd.randint(0, 4), ftm=ftm, fta=fta,
                 oreb=rnd.randint(0, 4), dreb=rnd.randint(0, 9), ast=rnd.randint(0, 9), stl=rnd.randint(0, 3),
                 blk=rnd.randint(0, 3), tov=rnd.randint(0, 5), pf=rnd.randint(0, 6))


def tab(pid, righe):
    out = []
    for i, st, minuti in righe:
        st = st or stats()
        out.append({"partita": pid, "atleta": f"k{i}", "nome": f"Klra {i}", "squadra": SQ_NBA[i], "titolare": True,
                    "giocato": minuti is not None, "minuti": minuti or 0, **st, "fp": nba.fantapunti(st) if minuti is not None else 0})
    db.salva_tabellino(pid, out)


# prima della stagione delle giornate: medie (k5 di IND compreso)
partita("p0", date(2026, 11, 1), "IND", "NYK")
tab("p0", [(5, casuali(), 30)] + [(i, casuali(), 25) for i in range(6, 33, 4)])
# due giornate: NYK-BOS e PHX-MIA ogni notte, due notti per giornata
GIORNATE = {1: (date(2026, 11, 10), date(2026, 11, 11)), 2: (date(2026, 11, 17), date(2026, 11, 18))}
TD = stats(pts=24, fgm=9, fga=16, tpm=2, tpa=5, ftm=4, fta=5, oreb=2, dreb=9, ast=11, stl=1, blk=1, tov=3, pf=2)   # 24-11-11
for n, (dal, al) in GIORNATE.items():
    for d, (dd) in enumerate((dal, al)):
        partita(f"a{n}{d}", dd, "NYK", "BOS", 101 + d, 99); partita(f"b{n}{d}", dd, "PHX", "MIA", 95, 120)
        righe_a = [(i, TD if (i == 4 and n == 1 and d == 0) else casuali(), rnd.randint(18, 38)) for i in range(1, 33) if SQ_NBA[i] in ("NYK", "BOS")]
        righe_b = [(i, casuali(), rnd.randint(18, 38)) for i in range(1, 33) if SQ_NBA[i] in ("PHX", "MIA")]
        righe_a = [(i, s, None if i == 8 else m) for i, s, m in righe_a]        # k8 a referto senza entrare: 0
        tab(f"a{n}{d}", righe_a); tab(f"b{n}{d}", righe_b)
    db.q("INSERT INTO lega_giornate (stagione, numero, dal, al, prima_partita) VALUES (%s, %s, %s, %s, %s)",
         (S, n, dal, al, datetime(dal.year, dal.month, dal.day, 23, 0, tzinfo=timezone.utc)))
    casa = [("team01", "team02"), ("team03", "team04")] if n == 1 else [("team01", "team03"), ("team02", "team04")]
    for c, t in casa:
        db.q("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES (%s, %s, %s, %s)", (S, n, c, t))
    for k, team in enumerate(("team01", "team02", "team03", "team04")):
        ids = list(range(1 + 8 * k, 9 + 8 * k))
        for ruolo, i in zip(R.RUOLI, ids[:5]):
            db.q("INSERT INTO ipa_formazioni (stagione, giornata, team_id, ruolo, giocatore_id) VALUES (%s, %s, %s, %s, %s)",
                 (S, n, team, ruolo, gid[i]))
        ipadb.salva_panchina(S, n, team, None, [{"giocatore_id": gid[i], "testo": f"P{i}", "ruolo": r}
                                                for i, r in zip(ids[5:], ("PG", "SF", "C"))])
    db.q("INSERT INTO ipa_stato_giornata (stagione, giornata, chiusa) VALUES (%s, %s, NOW())", (S, n))
    R.salva_calcolo(R.calcola(S, n))
    R.convalida(S, n, 900)
ufficiali = db.q("SELECT * FROM lega_risultati ORDER BY giornata, casa", many=True)
ok(len(ufficiali) == 4, f"due giornate convalidate dalla lega ({len(ufficiali)} partite)")

# ── l'utente klra (setup_db.sql, come deploy.sh) ──
RUOLO = "klra_prova"
PG = os.environ["DATABASE_URL"]
def psql(sql_o_file, *, file=False, db_url=PG):
    args = ["psql", db_url, "-v", "ON_ERROR_STOP=1", "-q"]
    return subprocess.run(args, input=sql_o_file, capture_output=True, text=True)
psql(f"DROP DATABASE IF EXISTS {RUOLO}")
setup = open(os.path.join(ROOT, "fantabasket-klra", "setup_db.sql")).read()
for volta in (1, 2):                                        # rilanciabile
    r = psql(f"\\set pw 'segreta'\n\\set ruolo {RUOLO}\n\\set dbklra {RUOLO}\n" + setup)
    ok(r.returncode == 0, f"setup_db.sql, volta {volta} {r.stderr.strip()[-300:]}")
pw = tempfile.NamedTemporaryFile("w", delete=False); pw.write("segreta\n"); pw.close()
host = PG.split("@")[1]
os.environ.update(DATABASE_URL=f"postgresql://{RUOLO}@{host}", PG_PASSWORD_FILE=pw.name,
                  KLRA_DATABASE_URL=f"postgresql://{RUOLO}@{host.split('/')[0]}/{RUOLO}")
pool_lega = db._pool
from klra import basi, motore as M, regole as KR       # noqa: E402
basi.apri_ufficiale(); basi.apri_klra()


def rifiutato(sql):
    try:
        db.q(sql)
        return False
    except Exception:
        return True

ok(db.q("SELECT COUNT(*) AS n FROM lega_risultati", one=True)["n"] == 4, "klra legge le tabelle della lega in elenco")
ok(rifiutato("INSERT INTO lega_risultati (stagione, giornata, casa, trasferta) VALUES ('x', 99, 'a', 'b')"), "INSERT su lega_risultati: rifiutato")
ok(rifiutato("UPDATE giocatori SET nome_common = 'x' WHERE id = %d" % gid[1]), "UPDATE su giocatori: rifiutato")
ok(rifiutato("DELETE FROM nba_tabellini"), "DELETE su nba_tabellini: rifiutato")
ok(rifiutato("CREATE TABLE klra_furba (x int)"), "creare tabelle nel database della lega: rifiutato")
ok(rifiutato("SELECT * FROM lega_calcoli"), "tabella fuori elenco (lega_calcoli): non si legge nemmeno")
ok(rifiutato("SET default_transaction_read_only = off; INSERT INTO lega_risultati (stagione, giornata, casa, trasferta) VALUES ('x', 99, 'a', 'b')"),
   "anche togliendo la sola lettura della sessione: rifiutato (permessi del ruolo)")
db._pool, _k = pool_lega, db._pool
ok(db.q("SELECT COUNT(*) AS n FROM lega_risultati WHERE stagione = 'x'", one=True)["n"] == 0, "niente è stato scritto nella lega")
db._pool = _k
ok(basi.q("SELECT nome FROM klra_sistemi WHERE ufficiale", one=True)["nome"] == "Ufficiale", "database klra: sistema Ufficiale creato")
uff = basi.q("SELECT * FROM klra_sistemi WHERE ufficiale", one=True)

# ── l'Ufficiale di klra = i risultati convalidati, al centesimo ──
d = M.verifica(S)
ok(d["motore"] == [] and d["dati"] == [], f"Ufficiale di klra identico al ricalcolo di loucabot e ai risultati convalidati {d}")
copia = basi.q("INSERT INTO klra_sistemi (nome, autore, parametri, base_id) VALUES ('Copia', 900, %s, %s) RETURNING *",
               (json.dumps(KR.ufficiale()), uff["id"]), one=True)
rc = {(r["giornata"], r["casa"]): r for r in M.risultati_stagione(copia, S)}
ok(all(float(u["punti_casa"]) == M.centesimi(rc[(u["giornata"], u["casa"])]["punti_casa"]) and u["vince"] == rc[(u["giornata"], u["casa"])]["vince"]
       for u in ufficiali), "la copia dell'Ufficiale (parametri congelati, stesso motore) dà gli stessi risultati")
ok(M.classifica(copia, S)[0]["team"] == __import__("classifica").calcola(S)[0][0]["team"], "e la stessa classifica")

# ── nessun effetto su loucabot: fuori dal calcolo di klra le funzioni danno i fantapunti della lega ──
_righe = db.tabellini_atleti(["k4"], *GIORNATE[1])
ok(all("fp_lega" not in r for r in _righe) and float(_righe[0]["fp"]) == nba.fantapunti(TD), "fuori da klra: fantapunti della lega, niente toccato")

# ── pesi e bonus del giocatore ──
P = KR.ufficiale(); P["pesi"]["blk"] = 10; P["giocatore"]["tripla_doppia"] = 5; P["giocatore"]["doppia_doppia"] = 2
ok(M.fp_riga({**TD, "giocato": True, "minuti": 34}, P) == round(nba.fantapunti(TD) + 8 + 5, 2),
   "pesi del sistema (stoppata 10) e tripla doppia +5 (prende il posto della doppia doppia)")
ok([b[0] for b in M.bonus_riga({**TD, "giocato": True}, P)] == ["TD"], "solo la tripla doppia, non anche la doppia")
P2 = KR.ufficiale(); P2["giocatore"].update(punti_40=3, mano_calda=2, custode=1, sei_falli=-2, tetto=20)
r40 = {**stats(pts=41, fgm=15, fga=20, ftm=8, fta=9, tov=0, pf=6), "giocato": True, "minuti": 36}
ok({b[0] for b in M.bonus_riga(r40, P2)} == {"40", "🔥", "🔒", "6F"} and M.fp_riga(r40, P2) == 20,
   "40 punti, mano calda, custode, 6 falli; tetto a 20")
ok(M.bonus_riga({**stats(pts=40), "giocato": False}, P2) == [], "chi non entra non prende bonus")
P3 = KR.ufficiale(); P3["giocatore"]["vittoria_nba"] = 4
ok([b[0] for b in M.bonus_riga({**stats(), "giocato": True, "partita": "a10", "squadra": "NYK"}, P3, {"a10": {"vince": "NYK"}})] == ["W"],
   "vittoria della squadra NBA")
sid = lambda nome, p: basi.q("INSERT INTO klra_sistemi (nome, autore, parametri) VALUES (%s, 900, %s) RETURNING *", (nome, json.dumps(p)), one=True)
sp = sid("Stoppate", P)
g1 = M.risultati_giornata(sp, S, 1)
k4 = next(x for r in g1["risultati"] for s in (r["sc"], r["st"]) for x in s["titolari"] if x["atleta"] == "k4")
ok(["TD", 5] in k4["bonus"], "nella giornata il bonus resta segnato accanto al giocatore")
ok(k4["fp"] > float(calcolo.punteggio_giocatori(S, db.giornata(S, 1), ["k4"])["k4"]["fp"]), "e i suoi fantapunti sono più alti di quelli della lega")
# medie col sistema: k5 (IND) a media, coi pesi del sistema
m_lega = __import__("db").q("SELECT fp FROM nba_tabellini WHERE atleta = 'k5'", one=True)["fp"]
k5 = next(x for r in g1["risultati"] for s in (r["sc"], r["st"]) for x in s["titolari"] if x["atleta"] == "k5")
row5 = db.q("SELECT * FROM nba_tabellini WHERE atleta = 'k5'", one=True)
ok(k5["come"] == "media" and k5["fp"] == M.fp_riga({**row5, "giocato": True}, M.KR.completa(P)), "media della stagione rifatta coi pesi del sistema")
pz = KR.ufficiale(); pz["partita"]["assenti"] = "zero"
k5z = next(x for r in M.risultati_giornata(sid("Assenti zero", pz), S, 1)["risultati"] for s in (r["sc"], r["st"]) for x in s["titolari"] if x["atleta"] == "k5")
ok(k5z["fp"] == 0 and k5z["come"] == "media", "chi non gioca e la squadra non ha partite: 0 se il sistema lo dice")
pp = KR.ufficiale(); pp["partita"].update(assenti="percentuale", assenti_pct=50)
k5p = next(x for r in M.risultati_giornata(sid("Metà", pp), S, 1)["risultati"] for s in (r["sc"], r["st"]) for x in s["titolari"] if x["atleta"] == "k5")
ok(abs(k5p["fp"] - float(row5["fp"]) / 2) <= 0.125, "o il 50% della media")

pf = KR.ufficiale(); pf["partita"]["fadd"] = False
M.installa(); _t = M._ATTIVO.set(KR.completa(pf))
_sost = M._fadd("k1", {"come": "zero", "squadra": "NYK"}, db.giornata(S, 1))
M._ATTIVO.reset(_t)
ok(_sost == (False, ""), "FADD spenta: nessuna sostituzione")

# ── Fantamedie (predefinito): chi gioca prende la media prima della giornata ──
# anno prima: k1 solo su bref (22,4), k3 coi tabellini della stagione precedente
db._pool = pool_lega
db.q("DELETE FROM bref_stats WHERE nome_bref LIKE 'Klra %%'")
# la fantamedia di bref la calcola un trigger dalle statistiche: 20 punti, 5 assist, 2 rimbalzi difensivi = 22,5
db.q("""INSERT INTO bref_stats (stagione, nome_bref, pts, ast, orb, drb, fg3m, fga, fgm, fta, ftm, stl, blk, tov)
        VALUES (%s, 'Klra 1', 20, 5, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0), (%s, 'Klra 3', 40, 10, 0, 10, 0, 0, 0, 0, 0, 0, 0, 0)""", (S, S))
db.salva_partite_nba([{"espn_id": "prec1", "stagione": str(int(S) - 1), "tipo": 2, "data_et": date(2026, 3, 1), "casa": "MIA",
                       "trasferta": "BOS", "inizio": datetime(2026, 3, 1, 23, 0, tzinfo=timezone.utc), "stato": "STATUS_FINAL"}])
_prec3 = stats(pts=20, fgm=8, fga=15, ast=4, dreb=6)
db.salva_tabellino("prec1", [{"partita": "prec1", "atleta": "k3", "nome": "Klra 3", "squadra": "MIA", "titolare": True, "giocato": True,
                              "minuti": 30, **_prec3, "fp": nba.fantapunti(_prec3)}])
db._pool = _k
fm = basi.q("SELECT * FROM klra_sistemi WHERE predefinito = 'fantamedie'", one=True)
from klra import sistemi as _SI
ok(fm and fm["nome"] == "Fantamedie" and not _SI.puo_modificare(fm, 900) and _SI.parametri(fm)["partita"]["fantapunti"] == "media",
   "Fantamedie: sistema predefinito, nessuno lo modifica")
gf = M.risultati_giornata(fm, S, 1)
_tutti_f = {x["atleta"]: x for r in gf["risultati"] for sd in (r["sc"], r["st"]) for x in sd["titolari"] + sd["panchina"]}
_p0 = {r["atleta"]: float(r["fp"]) for r in db.q("SELECT atleta, fp FROM nba_tabellini WHERE partita = 'p0'", many=True)}
ok(_tutti_f["k6"]["fp"] == _p0["k6"] and "fantamedie" in _tutti_f["k6"]["nota"], "chi ha giocato prende la media di prima (k6: la sua unica partita prima)")
ok(_tutti_f["k1"]["fp"] == 22.5 and "basketball-reference" in _tutti_f["k1"]["nota"],
   "nessuna partita quest'anno: la fantamedia dell'anno prima da bref (22,5)")
ok(_tutti_f["k2"]["fp"] == 0 and "né l'anno prima" in _tutti_f["k2"]["nota"], "né quest'anno né l'anno prima: 0")
ok(_tutti_f["k3"]["fp"] == M.fp_riga({**_prec3, "giocato": True}, KR.ufficiale()) and "media del" in _tutti_f["k3"]["nota"],
   "anno prima dai tabellini ESPN, se ci sono, prima di bref")
ok(_tutti_f["k5"]["come"] == "media" and _tutti_f["k5"]["fp"] == _p0["k5"], "chi non ha partite nella giornata: media come nella lega")
ok(_tutti_f["k8"]["fp"] == 0 and _tutti_f["k8"]["come"] == "zero", "chi era a referto senza entrare: 0 come nella lega")
gu1 = M.risultati_giornata(uff, S, 1)
ok(gf["risultati"][0]["punti_casa"] != gu1["risultati"][0]["punti_casa"], "i risultati cambiano rispetto all'Ufficiale")

# ── Fantapanchine (predefinito, v2): il totale è la somma dei panchinari, vince chi fa di più ──
fp_ = basi.q("SELECT * FROM klra_sistemi WHERE predefinito = 'fantapanchine'", one=True)
gp = M.risultati_giornata(fp_, S, 1)
_r0 = gp["risultati"][0]
_pan = round(sum(x["fp"] for x in _r0["sc"]["panchina"]) * 8) / 8
ok(fp_ and _r0["sc"]["totale"] == _pan and _r0["punti_casa"] == _pan + gp["bonus_casa"] and _r0["supplementari"] == 0,
   f"Fantapanchine: totale = somma dei panchinari (+ bonus casa), niente supplementari ({_r0['sc']['totale']} vs {_pan})")
ok(_r0["vince"] == ("casa" if _r0["punti_casa"] > _r0["punti_trasferta"] else "trasferta"), "vince chi fa di più")
pt_ = KR.ufficiale(); pt_["partita"]["chi_conta"] = "tutti"
gt_ = M.calcola_giornata(pt_, S, 1)["risultati"][0]
_gu1 = M.risultati_giornata(uff, S, 1)
ok(gt_["sc"]["totale"] == round((_gu1["risultati"][0]["sc"]["totale"] + _pan) * 8) / 8, "«tutti»: titolari più panchinari")
ok(any("solo i panchinari, sommati" in x for x in KR.differenze(KR.predefinito("fantapanchine"))), "differenze a parole")
# v16 (Luca, 28/11): Fanta P36, fantapunti riportati a 36 minuti netti; il minimo come opzione, spento nel predefinito
_p36 = KR.predefinito("p36")
_r18 = {"pts": 10, "ast": 2, "giocato": True, "minuti": 18}
_base = M.fp_riga(_r18, KR.ufficiale())
ok(_p36["giocatore"]["per36"] and _p36["giocatore"]["per36_minimo"] is None and M.fp_riga(_r18, _p36) == round(_base * 2, 2),
   f"P36: 18 minuti, fantapunti raddoppiati ({_base} → {M.fp_riga(_r18, _p36)})")
_r4 = {**_r18, "minuti": 4}
ok(M.fp_riga(_r4, _p36) == round(_base * 9, 2), "P36 netti: 4 minuti × 9, nessun limite")
_pm = KR.completa({"giocatore": {"per36": True, "per36_minimo": 12}})
ok(M.fp_riga(_r4, _pm) == round(_base * 3, 2) and M.fp_riga(_r18, _pm) == round(_base * 2, 2), "col minimo di 12: sotto si divide per 12")
ok(M.fp_riga({**_r18, "minuti": 0}, _p36) == _base and M.fp_riga({"giocato": False, "minuti": 0}, _p36) == 0,
   "senza minuti non si riporta (chi non entra resta a 0)")
_pb = KR.completa({"giocatore": {"per36": True, "doppia_doppia": 5}})
_dd = {"pts": 10, "dreb": 10, "giocato": True, "minuti": 18}
ok(M.fp_riga(_dd, _pb) == round(M.fp_riga(_dd, KR.ufficiale()) * 2 + 5, 2), "i bonus dopo il riporto, non riportati")
ok(M.fm_bref_sistema(_p36)({"pts": 20, "mp": 24}) == round(M.fm_bref_sistema(KR.ufficiale())({"pts": 20, "mp": 24}) * 1.5, 2),
   "media di Basketball-Reference: × 36 / minuti a partita")
ok(KR.firma(KR.ufficiale()) == KR.firma({}) and KR.firma(_p36) != KR.firma(KR.ufficiale()), "firma: il P36 spento non cambia le cache di prima")
ok(any("riportati a 36 minuti" in x for x in KR.differenze(_p36)) and any("almeno 12 minuti" in x for x in KR.differenze(_pm)),
   "differenze a parole, col minimo se c'è")
import klra.editor as ED
ok(not ED.visibile(KR.ufficiale(), "giocatore", "per36_minimo") and ED.visibile(_p36, "giocatore", "per36_minimo")
   and ED.leggi_valore("giocatore", "per36_minimo", "12") == (12, None) and ED.leggi_valore("giocatore", "per36_minimo", "nessuno") == (None, None),
   "editor: il minimo si vede col P36 acceso, si scrive o si toglie")

# ── squadra: quintetto completo, MVP, sotto zero ──
psq = KR.ufficiale(); psq["squadra"].update(mvp_bonus=7, quintetto_bonus=4, quintetto_soglia=-100, negativo_malus=-1)
gs = M.risultati_giornata(sid("Squadra", psq), S, 1)
gu = M.risultati_giornata(uff, S, 1)
tutti = [(r, s) for r in gs["risultati"] for s in (r["sc"], r["st"])]
mvp = [s for _, s in tutti if any(b[0] == "MVP di giornata" for b in s["bonus_squadra"])]
ok(len(mvp) >= 1 and all(any(b[0] == "Quintetto completo" for b in s["bonus_squadra"]) for _, s in tutti), "MVP di giornata e quintetto completo (soglia bassa: tutte)")
ok(gs["risultati"][0]["sc"]["totale"] == round((gu["risultati"][0]["sc"]["totale"] + sum(b[1] for b in gs["risultati"][0]["sc"]["bonus_squadra"])) * 8) / 8,
   "i bonus di squadra si sommano al totale")

# ── partita: esito coi modi del sistema ──
pan = [{"fp": 3}, {"fp": 1}]
E = lambda **x: M.esito(100, 103, pan, [{"fp": 0}, {"fp": 0}], {**KR.ufficiale(), "partita": {**KR.ufficiale()["partita"], **x}}, 0)
ok(E()["vince"] == "trasferta" and E()["supplementari"] == KR.ufficiale()["partita"]["panchina"] and E(panchina=2)["supplementari"] == 2,
   "Ufficiale: supplementari fino all'ultimo panchinaro, pari sotto lo scarto → trasferta; panchina 2: due")
ok(E(pari_finale="pareggio")["vince"] == "pari", "pari finale: pareggio")
ok(E(supplementari="pareggio")["vince"] == "pari" and E(supplementari="pareggio")["supplementari"] == 0, "sotto lo scarto: pareggio, niente supplementari")
ok(E(supplementari="nessuno")["vince"] == "trasferta" and E(supplementari="nessuno", scarto=50)["vince"] == "trasferta", "chi fa di più")
ok(E(scarto=2)["vince"] == "trasferta" and E(scarto=2)["supplementari"] == 0, "scarto 2: vince subito")
ok(M.esito(100, 100, [], [], KR.ufficiale(), 3)["regolamentari"] == (103, 100), "bonus casa")

# ── classifica a punti ──
ris = [{"giornata": 1, "casa": "team01", "trasferta": "team02", "punti_casa": 100, "punti_trasferta": 90, "vince": "casa", "supplementari": 0},
       {"giornata": 1, "casa": "team03", "trasferta": "team04", "punti_casa": 100, "punti_trasferta": 98, "vince": "pari", "supplementari": 0},
       {"giornata": 2, "casa": "team02", "trasferta": "team03", "punti_casa": 100, "punti_trasferta": 99, "vince": "casa", "supplementari": 2}]
Pc = KR.ufficiale(); Pc["classifica"]["modo"] = "punti"
tb = {r["team"]: r for r in M.tabella(ris, Pc)}
ok(tb["team01"]["pt"] == 3 and tb["team02"]["pt"] == 2 and tb["team03"]["pt"] == 2 and tb["team04"]["pt"] == 1 and tb["team03"]["p"] == 1,
   "a punti: vittoria 3, ai supplementari 2 e 1, pareggio 1")
ok(tb["team01"]["pos"] == 1 and tb["team02"]["pos"] < tb["team03"]["pos"], "ordine per punti, a parità lo scontro diretto")

# ── classifica cumulativa (v2): punti fatti in totale, senza bonus casa né supplementari ──
from klra import sistemi as SI, viste as V
risc = [{"giornata": 1, "casa": "team01", "trasferta": "team02", "punti_casa": 103, "punti_trasferta": 120, "vince": "trasferta", "supplementari": 0,
         "sc": {"totale": 100}, "st": {"totale": 120}},
        {"giornata": 2, "casa": "team02", "trasferta": "team01", "punti_casa": 93, "punti_trasferta": 140, "vince": "trasferta", "supplementari": 0,
         "sc": {"totale": 90}, "st": {"totale": 140}}]
Pcu = KR.ufficiale(); Pcu["classifica"]["modo"] = "cumulativa"
tcu = {r["team"]: r for r in M.tabella(risc, Pcu)}
ok(tcu["team01"]["cumulati"] == 240 and tcu["team02"]["cumulati"] == 210 and tcu["team01"]["pos"] == 1 and tcu["team01"]["pt"] == 240,
   "cumulativa: somma dei totali senza bonus casa (team01 240 prima di team02 210, anche se team02 ha più punti col bonus)")
ok(KR.predefinito("fantapanchine")["classifica"]["modo"] == "cumulativa", "Fantapanchine usa la classifica cumulativa")
ok(V.dati_classifica(basi.q("SELECT * FROM klra_sistemi WHERE predefinito = 'fantapanchine'", one=True), S)["cumulativa"],
   "immagine della classifica cumulativa")
_pngc = V.img_classifica(basi.q("SELECT * FROM klra_sistemi WHERE predefinito = 'fantapanchine'", one=True), S)
ok(_pngc[:4] == b"\x89PNG", "immagine della classifica cumulativa disegnata")
if os.environ.get("KLRA_IMMAGINI"):
    open(os.path.join(os.environ["KLRA_IMMAGINI"], "klra_cumulativa.png"), "wb").write(_pngc)

# ── cache ──
c1 = basi.q("SELECT calcolato FROM klra_risultati WHERE sistema_id = %s AND giornata = 1", (sp["id"],), one=True)["calcolato"]
M.risultati_giornata(sp, S, 1)
ok(basi.q("SELECT calcolato FROM klra_risultati WHERE sistema_id = %s AND giornata = 1", (sp["id"],), one=True)["calcolato"] == c1, "seconda volta: dalla cache")
db._pool = pool_lega
db.q("UPDATE lega_risultati SET convalidato = NOW() + INTERVAL '1 minute' WHERE giornata = 1")
db._pool = _k
M.risultati_giornata(sp, S, 1)
ok(basi.q("SELECT calcolato FROM klra_risultati WHERE sistema_id = %s AND giornata = 1", (sp["id"],), one=True)["calcolato"] != c1, "giornata riconvalidata: si rifà")

# ── confronto ──
cf = M.confronta(sid("Pareggi", {**KR.ufficiale(), "partita": {**KR.ufficiale()["partita"], "supplementari": "pareggio", "scarto": 1000}}), S)
ok(cf["giornate"] == 2 and len(cf["righe"]) == len(config.squadre()) and all(c["dopo"] == "pari" for c in cf["cambiano"]) and len(cf["cambiano"]) == 4,
   "confronta: con lo scarto a 1000 tutte e 4 le partite diventano pareggi")
ok(any("Sotto lo scarto: pareggio" in x for x in KR.differenze(cf and {**KR.ufficiale(), "partita": {**KR.ufficiale()["partita"], "supplementari": "pareggio"}})),
   "differenze rispetto all'Ufficiale a parole")
ok(KR.differenze(KR.ufficiale()) == [] and "Stoppata: 2 → 10" in KR.differenze(P), "l'Ufficiale non ha differenze; la stoppata sì")

# ── sistemi, editor, comandi e immagini (v1) ──
import asyncio, types
from klra import sistemi as SI, editor as ED, viste as V, comandi as CM
OUT = os.environ.get("KLRA_IMMAGINI")                     # per guardarle: KLRA_IMMAGINI=/cartella
ok(SI.trova_in_args(["3", "assenti", "zero"])[0]["nome"] == "Assenti zero" and SI.trova_in_args(["3", "assenti", "zero"])[1] == ["3"],
   "nome di sistema di più parole dentro gli argomenti")
ok(SI.nome_valido("copia") and SI.nome_valido("5") and SI.nome_valido("/x") and SI.nome_valido("Nuovo bello") is None, "nomi: doppioni, numeri, «/» rifiutati")
ok(SI.puo_modificare(sp, 900) and not SI.puo_modificare(sp, 101) and not SI.puo_modificare(uff, 900), "modifica solo chi l'ha creato, l'Ufficiale nessuno")
ok(not SI.aggiorna(sp["id"], 101, KR.ufficiale()), "un altro non può modificare")
Pm = SI.parametri(sp); Pm["pesi"]["blk"] = 3
ok(SI.aggiorna(sp["id"], 900, Pm) and SI.per_id(sp["id"])["modificato"] and SI.parametri(SI.per_id(sp["id"]))["pesi"]["blk"] == 3,
   "il creatore modifica: salvato con la data")
g1b = M.risultati_giornata(SI.per_id(sp["id"]), S, 1)
ok(g1b != g1, "dopo la modifica i risultati si rifanno (cache per firma)")
Pe = KR.ufficiale()
ok(ED.tocca(Pe, "partita", "supplementari") and Pe["partita"]["supplementari"] == "pareggio" and ED.tocca(Pe, "partita", "fadd") and Pe["partita"]["fadd"] is False
   and not ED.tocca(Pe, "pesi", "blk"), "editor: le scelte girano a ogni tocco, i numeri no")
ok(ED.leggi_valore("pesi", "blk", "2,5") == (2.5, None) and ED.leggi_valore("pesi", "blk", "−1") == (-1, None) and ED.leggi_valore("pesi", "blk", "x")[1]
   and ED.leggi_valore("pesi", "blk", "0,1")[1] and ED.leggi_valore("partita", "panchina", "7")[1] and ED.leggi_valore("giocatore", "tetto", "nessuno") == (None, None),
   "editor: valori scritti (virgola, meno, limiti, multipli di 0,25, «nessuno»)")

class Msg:
    def __init__(s): s.testi, s.foto, s.chat = [], [], types.SimpleNamespace(type="private")
    async def reply_text(s, t, **k): s.testi.append((t, k.get("reply_markup"))); return types.SimpleNamespace(delete=lambda: asyncio.sleep(0))
    async def reply_photo(s, p, **k): s.foto.append((p, k.get("caption")))
    async def reply_document(s, document=None, **k): s.foto.append((document, k.get("caption")))
class Q:
    def __init__(s, uid, data, msg): s.from_user, s.data, s.message, s.testo, s.kb, s.alert = types.SimpleNamespace(id=uid), data, msg, None, None, None
    async def answer(s, t=None, show_alert=False): s.alert = t
    async def edit_message_text(s, t, **k): s.testo, s.kb = t, k.get("reply_markup")
UD = {}
def ctx(args=None): return types.SimpleNamespace(args=args or [], user_data=UD, bot=None)
def upd(uid, msg, testo=None): return types.SimpleNamespace(effective_user=types.SimpleNamespace(id=uid, full_name="Luca"), effective_message=msg,
                                                            effective_chat=types.SimpleNamespace(type="private"))
def bottoni(kb): return [b.callback_data for r in kb.inline_keyboard for b in r] if kb else []
m = Msg(); asyncio.run(CM.cmd_sistemi(upd(901, m), ctx()))
ok("Ufficiale" in m.testi[0][0] and "Stoppate" in m.testi[0][0] and f"ks:v:{sp['id']}" in bottoni(m.testi[0][1]), "/sistemi: la lista coi bottoni")
def cb(uid, data):
    msg = Msg(); q = Q(uid, data, msg)
    asyncio.run(CM.cb(types.SimpleNamespace(callback_query=q), ctx()))
    return q, msg
q, _ = cb(901, f"ks:v:{sp['id']}")
ok("Stoppata: 2 → 3" in q.testo and f"ks:c:{sp['id']}" in bottoni(q.kb) and f"ks:m:{sp['id']}" not in bottoni(q.kb), "scheda: cosa cambia; un altro non ha «Modifica»")
q, _ = cb(901, f"ks:m:{sp['id']}")
ok("solo chi l'ha creato" in (q.alert or ""), "Modifica premuto da un altro: no")
q, _ = cb(901, f"ks:c:{sp['id']}")
ok("Nuovo sistema" in q.testo and "copia di Stoppate" in q.testo, "copia di un sistema non ufficiale: editor")
q, _ = cb(901, "ks:t:partita:supplementari")
ok(q.alert == "Sotto lo scarto: pareggio", "tocco su una scelta: cambia e lo dice")
q, _ = cb(901, "ks:t:pesi:blk")
ok("Scrivi il nuovo valore" in q.testo and UD.get("klra_attesa") == ("valore", "pesi", "blk"), "voce numerica: chiede il valore")
m = Msg(); m.text = "6"; asyncio.run(CM.testo_libero(upd(901, m), ctx()))
ok("Stoppata: 6" in m.testi[0][0] and SI.bozza(901)["parametri"]["pesi"]["blk"] == 6, "valore scritto: salvato nella bozza")
q, _ = cb(901, "ks:e")
ok("Stoppata: 3 → 6" in q.testo and "pareggio" in q.testo, "home dell'editor: le modifiche rispetto al sistema copiato")
q, _ = cb(901, "ks:sv")
ok("Come lo chiami" in q.testo, "salva: chiede il nome")
m = Msg(); m.text = "Stoppate"; asyncio.run(CM.testo_libero(upd(901, m), ctx()))
ok("C'è già" in m.testi[0][0], "nome già usato")
m = Msg(); m.text = "Muro"; asyncio.run(CM.testo_libero(upd(901, m), ctx()))
muro = SI.per_nome("Muro")
ok(muro and muro["autore"] == 901 and muro["base_id"] == sp["id"] and SI.attivo(901)["id"] == muro["id"] and not SI.bozza(901),
   "creato, copia di Stoppate, attivo per chi l'ha fatto, bozza chiusa")
q, _ = cb(901, f"ks:m:{muro['id']}")
q, _ = cb(901, "ks:t:pesi:pts")
m = Msg(); m.text = "1"; asyncio.run(CM.testo_libero(upd(901, m), ctx()))
q, _ = cb(901, "ks:sv")
ok("Salvato" == q.alert and SI.parametri(SI.per_id(muro["id"]))["pesi"]["pts"] == 1, "il creatore modifica il suo: salva senza nome")
q, _ = cb(902, f"ks:u:{muro['id']}")
ok(SI.attivo(902)["id"] == muro["id"] and SI.attivo(903)["ufficiale"], "/usa dal bottone; chi non ha scelto usa l'Ufficiale")
grp = Msg(); grp.chat = types.SimpleNamespace(type="supergroup"); qg = Q(901, f"ks:c:{muro['id']}", grp)
asyncio.run(CM.cb(types.SimpleNamespace(callback_query=qg), ctx()))
ok("in privato" in (qg.alert or ""), "l'editor nei gruppi no")

# /top col sistema
_tp = V.classifica_top(SI.per_nome("Stoppate"), S)
_tu = V.classifica_top(uff, S)
ok(_tu and all(x["media"] == x["lega"] for x in _tu), "/top con l'Ufficiale: fantamedie uguali a quelle della lega")
ok(_tp and any(x["media"] != x["lega"] for x in _tp), "/top con un altro sistema: fantamedie rifatte, diverse da quelle della lega")
_tt = V.testo_top(SI.per_nome("Stoppate"), S, 1, 5, False)
ok(_tt.startswith("🧪 NON UFFICIALE") and "(lega " in _tt, "/top: NON UFFICIALE in testa, accanto la fantamedia della lega")
m = Msg(); asyncio.run(CM.cmd_top(upd(900, m), ctx(["3", "Stoppate"])))
ok(m.testi and "sistema Stoppate" in m.testi[-1][0] and m.testi[-1][0].count("\n") >= 5, "/top N NOME")

# immagini e testo
pc = KR.ufficiale(); pc["classifica"]["modo"] = "punti"; pc["partita"]["supplementari"] = "pareggio"; pc["giocatore"]["tripla_doppia"] = 5
hk = SI.crea("Hockey", 900, "Luca", pc, uff["id"])
for nome, f in (("classifica", lambda: V.img_classifica(hk, S)), ("confronta", lambda: V.img_confronta(hk, S)),
                ("giornata", lambda: V.img_giornata(hk, S, 1)), ("partita", lambda: V.img_partita(hk, S, 1, "team01", "team02")[0])):
    try:
        png = f()
        ok(png[:4] == b"\x89PNG", f"immagine {nome}")
        if OUT:
            open(os.path.join(OUT, f"klra_{nome}.png"), "wb").write(png)
    except Exception as err:
        ok(False, f"immagine {nome}: {err}")
dp = V.dati_partita(hk, S, 1, "team01", "team02")
import partita as _PAk
_rk = json.loads(M.righe_lega(hk, S))
ok(all(sq["record"] == _PAk.record(_rk, sq["id"], 1)["record"] for sq in dp["squadre"]),
   f"/partita: il record W-L coi risultati del sistema {[(sq['id'], sq['record'], sq['record_prima']) for sq in dp['squadre']]}")
ok(dp["sistema"] == "Hockey" and any(r.get("bonus") == "+5 TD" for sq in dp["squadre"] for r in sq["righe"]), "/partita: il nome del sistema e il bonus accanto (+5 TD)")
t = V.testo_risultati(hk, S, 1)
ok("Hockey" in t and "Giornata 1" in t and t.startswith("🧪 <b>NON UFFICIALE</b>"), "/risultati in testo, NON UFFICIALE in testa")
ok(dp["filigrana"] == "NON UFFICIALE" and "NON UFFICIALE" in dp["striscia"] and V.dati_giornata(hk, S, 1)["filigrana"] and V.dati_classifica(hk, S)["filigrana"]
   and V.dati_confronta(hk, S)["filigrana"], "tutte le immagini: filigrana e striscia NON UFFICIALE")
m = Msg(); asyncio.run(CM.cmd_giornata(upd(900, m), ctx(["9"])))
ok("non è ancora convalidata" in m.testi[-1][0], "giornata non convalidata: lo dice")
m = Msg(); asyncio.run(CM.cmd_classifica(upd(900, m), ctx(["Hockey"])))
ok(m.foto and "Hockey" in m.foto[0][1] and m.foto[0][1].startswith("🧪 NON UFFICIALE"), "/classifica NOME, didascalia NON UFFICIALE")
m = Msg(); asyncio.run(CM.cmd_partita(upd(900, m), ctx(["Alfa", "1", "Hockey"])))
ok(m.foto and "Hockey" in m.foto[0][1], "/partita SQUADRA N NOME " + str(m.testi[-1:] if not m.foto else ""))

# ── v7.1.0: i comandi di loucabot dentro il contesto del sistema ──
import classifica as CLL
par = SI.per_nome("Pareggi")
with M.contesto(par):
    _rc = CLL.risultati(S)
ok(len(_rc) == 4 and all(r["vince"] == "pari" for r in _rc), "dentro il contesto loucabot legge i risultati del sistema (tutti pareggi)")
ok(all(r["vince"] != "pari" for r in CLL.risultati(S)), "fuori dal contesto i risultati veri: niente è stato toccato")
with M.contesto(hk):
    _cl = [r["team"] for r in CLL.calcola(S)[0]]
ok(_cl == [r["team"] for r in M.classifica(hk, S)], "la classifica di loucabot col sistema ha l'ordine del sistema (a punti)")
m = Msg(); asyncio.run(CM.cmd_calendario_full(upd(900, m), ctx(["Alfa", "Pareggi"])))
ok(m.testi and m.testi[-1][0].startswith("🧪 <b>NON UFFICIALE</b> · sistema <b>Pareggi</b>"), "/calendario_full SQUADRA NOME: il testo di loucabot, NON UFFICIALE in testa " + (m.testi[-1][0][:200] if m.testi else ""))
m = Msg(); asyncio.run(CM.cmd_classifica_full(upd(900, m), ctx(["Hockey"])))
ok(m.foto and m.foto[-1][1].startswith("🧪 NON UFFICIALE"), "/classifica_full NOME: immagine di loucabot, didascalia NON UFFICIALE")
with M.contesto(hk):
    _dt = CLL.dati_typst(CLL.calcola(S, True)[0], 2, True)
ok(_dt.get("filigrana") == "NON UFFICIALE" and "Hockey" in _dt.get("striscia", ""), "e con filigrana e striscia")
ok("filigrana" not in CLL.dati_typst(CLL.calcola(S, True)[0], 2, True), "fuori dal contesto la classifica di loucabot è quella di sempre")
_pg = V.pdf_giornata(hk, S, 1)
ok(_pg and _pg[0][:4] == b"%PDF", "/pdf_giornata col sistema")
_pp, _np = V.pdf_partite(hk, S, "team01")
ok(_pp and _pp[0][:4] == b"%PDF" and _np == 2, "/pdf_partite col sistema: le partite delle giornate convalidate")
m = Msg(); asyncio.run(CM.cmd_pdf_giornata(upd(900, m), ctx(["1", "Hockey"])))
ok(m.foto and m.foto[-1][1].startswith("🧪 NON UFFICIALE"), "/pdf_giornata N NOME")

# ── conference alternative (v2) ──
from klra import conference as CO
_div = os.path.join(os.path.dirname(os.environ.get("TEAMS_PATH", "")), "divisions.json")
json.dump({"conference": {"Est": ["E"], "Ovest": ["O"]}, "team_div": {"team01": "E", "team02": "E", "team03": "O", "team04": "O"}},
          open(_div, "w"))
ok(CO.configurate() and CO.nomi() == ["Est", "Ovest"], "conference della lega lette da divisions.json")
inc = CO.crea("Incrocio", 900, "Luca", ["team01", "team03"])
_map = inc["mappa"] if isinstance(inc["mappa"], dict) else json.loads(inc["mappa"])
ok(sorted(_map) == ["team01", "team02", "team03", "team04"] and {_map["team01"], _map["team03"]} == {"team01", "team02"}
   and {_map["team02"], _map["team04"]} == {"team03", "team04"}, f"accoppiamento a caso, ognuno al posto di uno della sua conference {_map}")
_vere = {(p["casa"], p["trasferta"]) for p in db.partite_giornata(S, 1)}
with M.in_conference(inc):
    _perm = [(p["casa"], p["trasferta"]) for p in db.partite_giornata(S, 1)]
    _conf = CLL.conference()
    gc = M.risultati_giornata(uff, S, 1)
ok(all(_conf[a] == _conf[b] for a, b in _perm) and _conf["team01"] == _conf["team03"] == "Est", "G1 intra conference resta intra con le nuove conference")
ok({(p["casa"], p["trasferta"]) for p in db.partite_giornata(S, 1)} == _vere, "fuori: il calendario vero, niente toccato")
_tot_v = {t: s_["totale"] for r in gu1["risultati"] for t, s_ in ((r["casa"], r["sc"]), (r["trasferta"], r["st"]))}
_tot_c = {t: s_["totale"] for r in gc["risultati"] for t, s_ in ((r["casa"], r["sc"]), (r["trasferta"], r["st"]))}
ok(_tot_v == _tot_c and {(r["casa"], r["trasferta"]) for r in gc["risultati"]} == set(_perm),
   "i punti delle squadre non cambiano, cambiano le sfide (ricalcolate col motore di loucabot)")
ok(basi.q("SELECT COUNT(DISTINCT firma) AS n FROM klra_risultati WHERE sistema_id = %s AND giornata = 1", (uff["id"],), one=True)["n"] >= 2,
   "in cache a parte: ogni conference la sua firma")
with M.in_conference(inc):
    _cfc = M.confronta(hk, S)
ok(_cfc["righe"] and len(_cfc["righe"]) == len(config.squadre()), "/confronta con le conference alternative contro l'Ufficiale vero")
# interfaccia
UD.clear()
q, _ = None, None
def cbc(uid, data):
    msg = Msg(); q_ = Q(uid, data, msg)
    asyncio.run(CM.cb_conference(types.SimpleNamespace(callback_query=q_), ctx()))
    return q_
q = cbc(905, "kc:n")
ok("scegli le 2 squadre della <b>Est</b>" in q.testo, "nuove conference: scelta delle squadre della prima")
cbc(905, "kc:t:team02"); cbc(905, "kc:t:team04")
q = cbc(905, "kc:t:team01")
ok("Sono già 2" in (q.alert or ""), "non più di quante ne servono")
q = cbc(905, "kc:ok")
ok("Come le chiami" in q.testo, "accoppia e salva: chiede il nome")
m = Msg(); m.text = "Pari e dispari"; asyncio.run(CM.testo_libero(upd(905, m), ctx()))
pd = CO.per_nome("Pari e dispari")
ok(pd and CO.attiva(905)["id"] == pd["id"] and "sono le tue attive" in m.testi[-1][0], "create e attive per chi le ha fatte")
q = cbc(906, f"kc:m:{pd['id']}")
ok("solo chi le ha create" in (q.alert or ""), "un altro non le modifica")
m = Msg(); asyncio.run(CM.cmd_classifica(upd(905, m), ctx([])))
ok(m.foto and "conference Pari e dispari" in m.foto[-1][1], "/classifica con le conference attive: lo dice")
q = cbc(907, "kc:n"); q = cbc(907, "kc:caso")
ok(len(UD["klra_conf"]["a"]) == 2 and "Accoppia e salva (2/2)" in str([b.text for r in q.kb.inline_keyboard for b in r]), "squadre estratte a caso")
q = cbc(905, "kc:u:0")
ok(CO.attiva(905) is None, "si torna alle ufficiali")

# ── v7.36.0: calendari alternativi (lo schema della lega estratto di nuovo, sulle giornate di regular season) ──
from shared import calendario_sorteggio as _CS
_d4 = open(_div, encoding="utf-8").read()
_T24 = [f"k{i:02d}" for i in range(1, 25)]
json.dump({"conference": {"Est": ["E"], "Ovest": ["O"]}, "team_div": {t: ("E" if i < 12 else "O") for i, t in enumerate(_T24)}},
          open(_div, "w", encoding="utf-8"))
db._pool, _k = pool_lega, db._pool                         # scrittura sui dati della lega (la prova, non klra)
db.q("DELETE FROM lega_giornate WHERE stagione = '2098'"); db.q("DELETE FROM lega_partite WHERE stagione = '2098'")
for _n in range(1, 39):
    db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES ('2098', %s, 'regular', '2098-11-01', '2098-11-02')", (_n,))
db.q("INSERT INTO lega_giornate (stagione, numero, tipo, dal, al) VALUES ('2098', 39, 'playoff', '2099-03-01', '2099-03-02')")
db.q("INSERT INTO lega_partite (stagione, giornata, casa, trasferta) VALUES ('2098', 39, 'k01', 'k13')")
db._pool = _k
_cal = CO.crea_calendario("Calendario Bis", 905, "Luca", _T24[:12])
_pj = json.loads(CO.partite_json(_cal, "2098"))
_reg = [r for r in _pj if r["giornata"] <= 38]
_gg = [[(r["casa"], r["trasferta"]) for r in _reg if r["giornata"] == n] for n in range(1, 39)]
_CS.valida(_gg, _T24[:12], _T24[12:])
ok(len(_reg) == 38 * 12 and all(len(g) == 12 for g in _gg) and max(_CS.di_fila(_CS.campi(_gg, t)) for t in _T24) <= 2,
   "calendario alternativo: 38 giornate da 12 partite, i controlli di Henry, mai più di 2 di fila")
ok([(r["casa"], r["trasferta"]) for r in _pj if r["giornata"] == 39] == [("k01", "k13")], "le giornate dei playoff restano quelle vere")
ok(json.loads(CO.partite_json(_cal, "2098")) == _pj, "stesso seme, stesso calendario")
_vero = [(r["casa"], r["trasferta"]) for r in _reg]
ok(CO.riestrai(_cal["id"], 905) and [(r["casa"], r["trasferta"]) for r in json.loads(CO.partite_json(CO.per_id(_cal["id"]), "2098"))
                                     if r["giornata"] <= 38] != _vero, "riestrai: un altro calendario")
ok(not CO.riestrai(_cal["id"], 906), "lo riestrae solo chi l'ha creato")
with M.in_conference(CO.per_id(_cal["id"])):
    _f1 = M.firma_cache({})
CO.riestrai(_cal["id"], 905)
with M.in_conference(CO.per_id(_cal["id"])):
    _f2 = M.firma_cache({})
ok(_f1 != _f2, "cache: ogni calendario estratto la sua firma")
_sc = scheda_cal = CM.scheda_conference(_cal["id"], 905)
ok("Calendario estratto di nuovo" in _sc[0] and "kc:re:" in str([b.callback_data for r in _sc[1].inline_keyboard for b in r]),
   "scheda: lo dice, e chi l'ha creato può riestrarlo")
q = cbc(908, "kc:cal:0")
ok("Come lo chiami" in q.testo and UD["klra_conf"]["calendario"], "📅 calendario nuovo con le conference ufficiali: chiede il nome")
m = Msg(); m.text = "Altro Giro"; asyncio.run(CM.testo_libero(upd(908, m), ctx()))
_ag = CO.per_nome("Altro Giro")
ok(_ag and _ag["seme"] and CO.attiva(908)["id"] == _ag["id"] and "calendario estratto" in m.testi[-1][0],
   "creato col seme e attivo per chi l'ha fatto")
basi.q("DELETE FROM klra_scelte WHERE conference_id IN (%s, %s)", (_cal["id"], _ag["id"]))
basi.q("DELETE FROM klra_conference WHERE id IN (%s, %s)", (_cal["id"], _ag["id"]))
db._pool, _k = pool_lega, db._pool
db.q("DELETE FROM lega_giornate WHERE stagione = '2098'"); db.q("DELETE FROM lega_partite WHERE stagione = '2098'")
db._pool = _k
open(_div, "w", encoding="utf-8").write(_d4)
os.unlink(_div)

# /player col sistema: v7.41.0 (Luca, 28/11: «klra è loucabot, cambia solo il punteggio») la stessa immagine di loucabot,
# coi fantapunti del sistema dentro, niente testo in più
from shared import giocatore as _G, rendimento as _REx
_RE_partite = lambda a: _REx.partite(a, S)
_spP = KR.completa(SI.parametri(sp))
_dl = _G.dati_scheda(gid[4])
with M.contesto(sp):
    _ds = _G.dati_scheda(gid[4])
_fm = lambda d: next(x["v"] for x in d["riquadri"] if x["t"] == "Fantamedia")
ok(_fm(_ds) != _fm(_dl) and all(u["fpt"] == __import__("shared.numeri", fromlist=["x"]).testo(M.fp_riga(r, _spP, {}))
                               for u, r in zip([u for u in _ds["ultime"] if u.get("fp") is not None],
                                               [r for r in _RE_partite("k4") if r["giocato"]][-len([u for u in _ds["ultime"] if u.get("fp") is not None]):])),
   f"/player in klra: fantamedia e ultime partite col sistema ({_fm(_dl)} → {_fm(_ds)})")
m = Msg(); asyncio.run(CM.cmd_player(upd(900, m), ctx(["Klra", "4", "Stoppate"])))
_altri = [t for t, _ in m.testi if not t.startswith("⏳")]
ok(m.foto and "NON UFFICIALE" in (m.foto[-1][1] or "") and not _altri, f"/player NOME SISTEMA: solo l'immagine, NON UFFICIALE, niente testo sotto {_altri}")
import player as _PL
ok(_PL.extra(gid[4]) == "" and _fm(_G.dati_scheda(gid[4])) == _fm(_dl), "fuori da klra: /player com'era")
# /giocatori, /prestazione, /notte di loucabot in klra (v7.41.0), coi fantapunti del sistema
from shared import elenco_giocatori as _EG, prestazione as _PR
_el = {x["id"]: x for x in _EG.dati(int(S), int(S))}
with M.contesto(sp):
    _es = {x["id"]: x for x in _EG.dati(int(S), int(S))}
ok(_el[gid[4]]["media"] != _es[gid[4]]["media"], f"/giocatori: la fantamedia col sistema ({_el[gid[4]]['media']} → {_es[gid[4]]['media']})")
m = Msg(); m.text = "/giocatori Stoppate"
asyncio.run(CM.cmd_giocatori(upd(900, m), ctx(["Stoppate"])))
ok((m.foto or m.testi) and "NON UFFICIALE" in str(m.foto[-1][1] if m.foto else m.testi[-1][0]), "/giocatori in klra: NON UFFICIALE")
# v18 (v7.42.0): /giocatori_build, il 🔎 Cerca nel contesto del sistema attivo
_gbh = [h for h in CM.handlers() if getattr(h, "pattern", None) is not None and h.pattern.pattern == "^gb:"]
_gbc = [h for h in CM.handlers() if "giocatori_build" in getattr(h, "commands", ())]
m = Msg(); _c = ctx()
asyncio.run(_gbc[0].callback(upd(900, m), _c))
ok(_gbh and "Costruisci la ricerca" in m.testi[-1][0], "/giocatori_build in klra: il messaggio coi bottoni")
for _d in ("gb:a:Stoppate", "gb:go"):
    _qq = Q(900, _d, Msg())
    asyncio.run(_gbh[0].callback(types.SimpleNamespace(callback_query=_qq), _c))
ok((_qq.message.foto or _qq.message.testi) and "NON UFFICIALE" in str(_qq.message.foto[-1][1] if _qq.message.foto else _qq.message.testi[-1][0])
   and "🔁" in str(_qq.message.foto[-1][1] if _qq.message.foto else _qq.message.testi[-1][0]), "/giocatori_build in klra: cerca col sistema, NON UFFICIALE")
m = Msg(); asyncio.run(CM.cmd_prestazione(upd(900, m), ctx(["Klra", "4", "Stoppate"])))
ok(m.foto and "NON UFFICIALE" in str(m.foto[-1][1]), "/prestazione in klra: l'immagine, NON UFFICIALE " + str([t for t, _ in m.testi])[:200])
m = Msg(); asyncio.run(CM.cmd_notte(upd(900, m), ctx(["Stoppate"])))
ok(m.testi and "NON UFFICIALE" in m.testi[-1][0], "/notte in klra: NON UFFICIALE " + (m.testi[-1][0][:150] if m.testi else ""))

# ── v8 (v7.20.1): copia quasi speculare di loucabot: i comandi in comune col sistema, sempre NON UFFICIALE ──
from shared import rendimento as _RE, non_ufficiale as _NU, quasi_cup as _QC
_muro = SI.per_nome("Muro")
_Pm = KR.completa(SI.parametri(_muro))
_ds_f = _RE.dati_stagione(gid[4], S)
with M.contesto(hk):
    _ds_h = _RE.dati_stagione(gid[4], S)
    _tab4 = [r for r in _RE.partite("k4", S) if r["giocato"]]
    _att = [M.fp_riga(r, KR.completa(SI.parametri(hk)), {}) for r in _tab4]
ok(not _NU.attivo() and _NU.fp({"fp": 7}) == 7.0, "fuori da klra: shared/non_ufficiale spento, i fantapunti della lega")
_fp_h = [x["fp"] for x in _ds_h["partite"] if x["fp"] is not None]
ok(sorted(_fp_h) == sorted(_att) and sorted(_fp_h) != sorted(x["fp"] for x in _ds_f["partite"] if x["fp"] is not None),
   f"/rendimento col sistema Hockey: fantapunti rifatti (tripla doppia +5) {_fp_h[:3]}")
with M.contesto(_muro):
    _b1 = _RE.stagioni_bref("Klra 1") if hasattr(_RE, "stagioni_bref") else None
    _nota_m = _NU.nota_bref()
    _fm1 = _NU.fm_bref({"pts": 20, "ast": 5, "orb": 0, "drb": 2, "mp": 30})
ok(abs(_fm1 - (20 * _Pm["pesi"]["pts"] + 5 * _Pm["pesi"]["ast"] + 2 * _Pm["pesi"]["dreb"] + 30 * _Pm["pesi"]["minuti"])) < 0.01,
   f"medie di Basketball-Reference coi pesi del sistema Muro ({_fm1})")
ok(_nota_m == "" if not any(_Pm["giocatore"][k] for k in KR.BONUS_GIOCATORE) and _Pm["giocatore"]["tetto"] is None else bool(_nota_m),
   f"nota sulle medie storiche solo se il sistema ha bonus o tetto: {_nota_m!r}")
with M.contesto(hk):
    _nota_h = _NU.nota_bref()
ok("tripla doppia" in _nota_h and "non si calcolano" in _nota_h, f"Hockey (tripla doppia +5): la nota lo dice {_nota_h!r}")
ok(M.nota_bref({"giocatore": {**{k: 0 for k in KR.BONUS_GIOCATORE}, "tetto": 60}}).endswith("il tetto non si calcola dalle medie di Basketball-Reference"),
   "solo il tetto: «il tetto non si calcola»")

# Quasi Cup col sistema: qualificazione sulla G1, semifinali nella G2 (calendario della Cup finto)
_g = {g["numero"]: g for g in db.q("SELECT * FROM lega_giornate WHERE stagione = %s", (S,), many=True)}
_QCg, _QCq = _QC.giornate, _QC.qualificazione_chiusa
_QC.giornate = lambda s: {"qual": [_g[1]], "q1": _g[2], "q2": None}
_QC.qualificazione_chiusa = lambda s, info=None: True
try:
    with M.contesto(par):
        _sf = _QC.risultati_cup(S, 1)
        _lv = _QC.live(S, 1)
        _cl1 = [x["team"] for x in _QC.classifica(S)]
    _r2 = {r["casa"]: r for r in M.risultati_giornata(par, S, 2)["risultati"]}
    _sq2 = {}
    for r in _r2.values():
        _sq2[r["casa"]], _sq2[r["trasferta"]] = r["sc"], r["st"]
    _Pp = KR.completa(SI.parametri(par))
    _e = [M.esito(_sq2[x["casa"]]["totale"], _sq2[x["trasferta"]]["totale"], _sq2[x["casa"]]["panchina"], _sq2[x["trasferta"]]["panchina"], _Pp,
                  float(M.risultati_giornata(par, S, 2)["bonus_casa"])) for x in _sf]
    ok(len(_sf) == 2 and {(x["casa"], x["trasferta"]) for x in _sf} == {(_cl1[0], _cl1[3]), (_cl1[1], _cl1[2])},
       f"Cup col sistema: semifinali 1ª-4ª e 2ª-3ª della qualificazione del sistema {[(x['casa'], x['trasferta']) for x in _sf]}")
    ok(all(float(x["punti_casa"]) == M.centesimi(e["regolamentari"][0]) and x["vince"] in ("casa", "trasferta") for x, e in zip(_sf, _e)),
       "Cup: punti del sistema nella G del turno (bonus casa, regole di partita), un pari va a chi è in casa")
    ok(_lv is None, "Cup col sistema: niente live (quello vero non si vede)")
    m = Msg(); asyncio.run(CM.cmd_quasi_cup(upd(900, m), ctx(["Pareggi"])))
    ok(m.foto and m.foto[-1][1].startswith("🧪 <b>NON UFFICIALE</b> · sistema <b>Pareggi</b>"), "/quasi_cup NOME: immagine, NON UFFICIALE " + str(m.testi[-1:]))
finally:
    _QC.giornate, _QC.qualificazione_chiusa = _QCg, _QCq
db._pool, _k = pool_lega, db._pool
ok(_QC.risultati_cup(S, 1) == [], "fuori dal contesto: lega_cup quella vera (vuota)")
db._pool = _k

# i comandi: tutti rispondono NON UFFICIALE, nessun errore (permessi del ruolo klra compresi)
db._pool, _k = pool_lega, db._pool                         # nomi senza numeri (un numero in fondo è il periodo)
for _i, _n in ((1, "Klra Uno"), (2, "Klra Due"), (3, "Klra Tre"), (4, "Klra Quattro")):
    db.q("UPDATE giocatori SET nome_common = %s, nome_bref = %s, nome_norm = lower(%s) WHERE id = %s", (_n, _n, _n, gid[_i]))
    db.q("UPDATE bref_stats SET nome_bref = %s WHERE nome_bref = %s", (_n, f"Klra {_i}"))
db._pool = _k
for _cmd, _args, _img in ((CM.cmd_rendimento, ["Klra", "Quattro"], False), (CM.cmd_rendimento_carriera, ["Klra", "Tre"], True),
                          (CM.cmd_confronto, ["Klra", "Quattro,", "Klra", "Due"], True), (CM.cmd_confronto_carriera, ["Klra", "Uno,", "Klra", "Tre"], True),
                          (CM.cmd_rendimento_situazione, ["Klra", "Quattro"], True), (CM.cmd_rendimento_team, ["Alfa", "Hockey"], False),
                          (CM.cmd_classifica_home_away, ["Hockey"], True), (CM.cmd_top_storica, [S], False), (CM.cmd_playoff, ["Hockey"], True)):
    m = Msg()
    asyncio.run(_cmd(upd(900, m), ctx(list(_args))))
    _tt = [t for t, _ in m.testi if not t.startswith("⏳")] + [c or "" for _, c in m.foto]
    _err = [t for t in _tt if "non riuscito" in t or "❌" in t or "Uso:" in t or "può essere" in t]
    ok(_tt and not _err and all(t.startswith("🧪") for t in _tt) and (m.foto or not _img),
       f"/{_cmd.__name__[4:]}: NON UFFICIALE, nessun errore {(_err or _tt)[:2]!r}"[:400])
    if OUT and m.foto:
        _f = m.foto[-1][0]
        open(os.path.join(OUT, f"klra_{_cmd.__name__[4:]}.png"), "wb").write(_f.getvalue() if hasattr(_f, "getvalue") else _f)
m = Msg(); q = Q(900, f"rs:{gid[4]}", m)
asyncio.run(CM.cb_rendimento(types.SimpleNamespace(callback_query=q), ctx()))
_tt = [t for t, _ in m.testi] + [c or "" for _, c in m.foto]
ok(_tt and all(t.startswith("🧪") for t in _tt) and q.testo == "📈 ⬇️", f"bottone «Quale?» di /rendimento: col sistema attivo, NON UFFICIALE {_tt[:1]}")
m = Msg(); q = Q(900, f"sit:{gid[4]}", m)
asyncio.run(CM.cb_rendimento_situazione(types.SimpleNamespace(callback_query=q), ctx()))
ok(m.foto and all(t.startswith("🧪") for t, _ in m.testi), "bottone di /rendimento_situazione: NON UFFICIALE")
with M.contesto(hk):
    import playoff as _PO
    _dp = _PO.dati_tabellone(S)
ok(_dp["filigrana"] == "NON UFFICIALE" and "classifica del sistema" in _dp["fase"], "/playoff col sistema: seed dalla classifica del sistema, filigrana")
db._pool, _k = pool_lega, db._pool
ok("filigrana" not in _PO.dati_tabellone(S), "/playoff fuori da klra: com'era")
db._pool = _k
ok({c for c, _ in CM.PUBBLICI} >= {"rendimento", "rendimento_carriera", "confronto", "confronto_carriera", "rendimento_situazione",
                                   "rendimento_team", "classifica_home_away", "quasi_cup", "top_storica", "playoff"},
   "i comandi nuovi nel menu di klra")
_h = {c for h in CM.handlers() for c in getattr(h, "commands", ())}
ok(not _h & {"status", "live"} and {"giocatori", "giocatori_build", "prestazione", "notte"} <= _h,
   "niente /status e /live; /giocatori, /prestazione e /notte sì (v7.41.0)")

# verifica: dati cambiati dopo la convalida (un tabellino corretto) → motore uguale, differenza nei dati
db._pool = pool_lega
db.q("UPDATE nba_tabellini SET fp = fp + 10, pts = pts + 20 WHERE atleta = 'k2' AND partita = 'b10'")
db._pool = _k
d = M.verifica(S)
ok(d["motore"] == [] and d["dati"] and d["dati"][0].startswith("G1"), f"verifica: motore uguale a loucabot, i dati cambiati a parte {d}")

# pulizia (lega con l'utente della prova)
db._pool = pool_lega
db.q("TRUNCATE nba_tabellini, nba_infortuni, lega_giornate, lega_partite, nba_partite, lega_risultati, lega_calcoli, "
     "lega_calcoli_storico, ipa_formazioni, ipa_panchine, ipa_stato_giornata")   # le altre prove non devono trovarle
db.q("DELETE FROM bref_stats WHERE nome_bref LIKE 'Klra %%'")
db.q("DELETE FROM giocatori WHERE id = ANY(%s)", (list(gid.values()),))
basi._pool.closeall()
psql(f"DROP DATABASE IF EXISTS {RUOLO}")
os.unlink(pw.name)

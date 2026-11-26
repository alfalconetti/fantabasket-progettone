import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.33.0: prospetto dei rinnovi (shared/prospetto_rinnovi.py): stima in regular season, numeri veri ai rinnovi
(gli stessi di handlers/rinnovi.py), solo l'elenco nelle fasi in mezzo."""
import asyncio, types
import database as db
import settings
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, transazioni, dpe, impatto_taglio, rfa_dichiarati, messaggi_fissi, "
      "rinnovi_normali RESTART IDENTITY CASCADE")
db._q("DELETE FROM bref_stats")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)


def fase(f, stagione=None):
    g = settings.load_globals(); g["fase"] = f
    if stagione:
        g["stagione_corrente"] = str(stagione)
    settings.save_globals(g)


def gioc(n, team, imp, anni, sf, tipo="normale", pick=None, anno_firma=None):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    if pick:
        db._q("INSERT INTO rookie (giocatore_id,team_id,round,pick_numero,anno_draft,anno_firma,firmato) "
              "VALUES (%s,%s,1,%s,%s,%s,TRUE)", (gid, team, pick, str(anno_firma), str(anno_firma)))
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                 "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (gid, team, imp, anni, str(sf), tipo))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id,timestamp) "
          "VALUES ('signed',%s,%s,%s,%s,NOW() - INTERVAL '1 day')", (gid, team, str(sf), c))
    return gid


def fm(n, stagione_lega, valore):
    db._q("""INSERT INTO bref_stats (stagione,nome_bref,team,g,fga,fgm,ftm,fta,fg3m,pts,orb,drb,ast,stl,blk,tov)
             VALUES (%s,%s,'X',50,0,0,0,0,0,%s,0,0,0,0,0,0)""", (str(stagione_lega + 1), n, valore * 2))


from shared import prospetto_rinnovi as P
import handlers.stagione as S
import handlers.rinnovi as R
team = {"id": "team01", "nome": "Alfa"}

# le regole copiate in shared danno gli stessi numeri del bot principale
ok(all(P.doncic(x) == S.doncic(x) for x in (None, 19.99, 20, 22.4, 24.99, 25, 27.9, 33, 41)), "Doncic come handlers/stagione")
ok(all(P.minimo(x) == settings.minimo_contratto_per_media(x) for x in (0, 10.99, 10.995, 14.995, 21.4, 27, 50)),
   "minimo da tabella come settings")
ok(all(P.aumento(b, t) == R.aumento(b, t) for b in range(1, 40) for t in P.TIPI), "¼ e ½ come handlers/rinnovi")

# ── regular season 2026: la stima dell'offseason 2027 ─────────────────────────
fase("regular-season-fa", 2026)
vet = gioc("Veterano", "team01", 18, 2, 2026); fm("Veterano", 2026, 21.4)
r4 = gioc("Rookie Quarto", "team01", 8, 1, 2026, "rookie", pick=6, anno_firma=2023)
fm("Rookie Quarto", 2025, 22); fm("Rookie Quarto", 2026, 24.3)
r2 = gioc("Rookie Secondo", "team01", 13, 1, 2026, "rookie", pick=1, anno_firma=2025); fm("Rookie Secondo", 2026, 26.1)
gioc("Lungo", "team01", 10, 3, 2026)
gioc("Scade", "team01", 5, 1, 2026)
gioc("Dieci Giorni", "team01", 1, 1, 2025, "10day")
d = P.dati(team, giornate=3)
g = {x["nome"]: x for x in d["giocatori"]}
ok(set(g) == {"Veterano", "Rookie Quarto"}, "rinnovabili alla prossima offseason: chi diventa x1 e il rookie che esce dal IV anno")
ok(g["Veterano"]["base"] == "18x1" and (g["Veterano"]["q"]["imp"], g["Veterano"]["m"]["imp"], g["Veterano"]["min"]) == (23, 27, 10),
   "x1: 18 → 23 da ¼ e 27 da ½ (minimo 10 per 21,4)")
ok(g["Rookie Quarto"]["base"] == "15x0" and "= 14,4 → 15" in g["Rookie Quarto"]["doncic"]
   and (g["Rookie Quarto"]["q"]["imp"], g["Rookie Quarto"]["m"]["imp"]) == (19, 23),
   "rookie al IV anno: prima la Doncic d'ufficio (24,3 → 15), poi 19 e 23")
ok(d["rookie"] == [{"nome": "Rookie Secondo", "come": d["rookie"][0]["come"], "nuovo": "16x2"}] and "Doncic" in d["rookie"][0]["come"],
   "rookie a fine II anno: Doncic 16x2 sopra la scala III (14)")
ok(d["riquadri"][2]["v"] == "28M" and d["riquadri"][3]["v"] == "122M / 137M", "cap 2027-28 senza rinnovi: 28M (in corso lì)")
ok("solo 3 giornate" in d["striscia"] and d["modo"] == "stima", "avviso nelle prime 10 giornate")
ok("STIMA" in P.dati(team, giornate=12)["striscia"] and "solo" not in P.dati(team, giornate=12)["striscia"], "dopo 10 giornate solo «STIMA»")
ok("finali" in P.dati(team, fase="offseason-break")["striscia"], "nel break: fantamedie finali")
ok(P.immagine(d)[:4] == b"\x89PNG", "immagine")

# ── fasi in mezzo: solo l'elenco ───────────────────────────────────────────────
d = P.dati(team, fase="offseason-fa", stagione=2026)
ok(d["modo"] == "senza" and "Mancano le fantamedie" in d["striscia"] and all(x["q"] is None for x in d["giocatori"]),
   "fasi in mezzo: i rinnovabili senza importi, e il perché")
ok(P.immagine(d)[:4] == b"\x89PNG", "immagine senza dati")

# ── ai rinnovi: i numeri veri, gli stessi di /rinnovo ──────────────────────────
fase("offseason-rinnovi", 2027)
S.applica_stagione(2027)
d = P.dati(team)
g = {x["nome"]: x for x in d["giocatori"]}
cand = {c["nome_common"]: c for c in R.candidati("team01")}
ok(set(g) == set(cand) == {"Veterano", "Rookie Quarto"}, "ai rinnovi: gli stessi rinnovabili di /rinnovo")
ok(all(g[n]["q"]["imp"] == R.opzione(cand[n], "quarto")["importo"] and g[n]["m"]["imp"] == R.opzione(cand[n], "mezzo")["importo"]
       for n in cand), "ai rinnovi: gli stessi importi di /rinnovo")
ok(g["Rookie Quarto"]["base"] == "15x0" and "Doncic" in (g["Rookie Quarto"]["doncic"] or ""), "ex rookie: la Doncic già applicata")
ok(d["rookie"] and d["rookie"][0]["nuovo"] == "16x2", "rookie a fine II anno anche ai rinnovi")
R.esegui("team01", vet, "quarto", 2, "prova")
d = P.dati(team)
ok("✓" in d["riquadri"][1]["v"] and "Veterano" in d["riquadri"][1]["s"] and {x["nome"] for x in d["giocatori"]} == {"Rookie Quarto"},
   "ai rinnovi: il rinnovo usato nel riquadro, il rinnovato non è più in elenco")
ok(d["riquadri"][2]["v"] == f"{db.cap_occupato_team('team01', '2027')}M", "ai rinnovi: il cap vero")

# ── comando ────────────────────────────────────────────────────────────────────
foto = []
msg = types.SimpleNamespace(reply_photo=lambda b: foto.append(b) or asyncio.sleep(0),
                            reply_text=lambda t, **k: foto.append(t) or asyncio.sleep(0))
asyncio.run(P.cmd_prospetto_rinnovi(types.SimpleNamespace(effective_message=msg, effective_user=types.SimpleNamespace(id=101)),
                                    types.SimpleNamespace(args=[])))
asyncio.run(P.cmd_prospetto_rinnovi(types.SimpleNamespace(effective_message=msg, effective_user=types.SimpleNamespace(id=5)),
                                    types.SimpleNamespace(args=["Beta"])))
ok(isinstance(foto[0], bytes) and isinstance(foto[1], bytes), "/prospetto_rinnovi: la propria squadra e un'altra per nome")
fase("offseason-fa", 2026)

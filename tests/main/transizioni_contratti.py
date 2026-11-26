import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v7.35.3: contratti a cavallo della stagione: impatto dei tagli negli anni dopo (cap, rinnovi, prospetto), DPE
che vale solo nella sua stagione, decadimento (ritiro: via le spalmature future di tutti; Cam Thomas: restano)
anche di un RFA dichiarato, 10-day che non attraversa il cambio di stagione."""
import asyncio, types
import database as db
import settings
db.init_db(); db.migrate_db()
db._q("TRUNCATE giocatori, contratti, pick, rookie, transazioni, dpe, impatto_taglio, rfa_dichiarati, messaggi_fissi, "
      "rinnovi_normali, trade RESTART IDENTITY CASCADE")
db._q("DELETE FROM bref_stats")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)


def fase(f, stagione=None):
    g = settings.load_globals(); g["fase"] = f
    if stagione:
        g["stagione_corrente"] = str(stagione)
    settings.save_globals(g)


def gioc(n, team, imp, anni, sf, tipo="normale"):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                 "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (gid, team, imp, anni, str(sf), tipo))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id,timestamp) "
          "VALUES ('signed',%s,%s,%s,%s,NOW() - INTERVAL '2 days')", (gid, team, str(sf), c))
    return gid


def firma(gid, team, imp, anni, sf):
    c = db._qval("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) "
                 "VALUES (%s,%s,%s,%s,%s,'normale') RETURNING id", (gid, team, imp, anni, str(sf)))
    db._q("INSERT INTO transazioni (tipo,giocatore_id,team_id_a,stagione,contratto_id) VALUES ('signed',%s,%s,%s,%s)",
          (gid, team, str(sf), c))


def fm(n, stagione_lega, valore):
    db._q("""INSERT INTO bref_stats (stagione,nome_bref,team,g,fga,fgm,ftm,fta,fg3m,pts,orb,drb,ast,stl,blk,tov)
             VALUES (%s,%s,'X',50,0,0,0,0,0,%s,0,0,0,0,0,0)""", (str(stagione_lega + 1), n, valore * 2))


class Bot:
    async def send_message(self, *a, **k): return types.SimpleNamespace(message_id=1)
    async def edit_message_text(self, *a, **k): pass


import teams as tm
import handlers.stagione as S
import handlers.rinnovi as R
from handlers.tagli import esegui_taglio
from handlers.decadimento import applica_decadimento
rate = lambda gid, team: {r["stagione"]: r["importo"] for r in db._q(
    "SELECT stagione, importo FROM impatto_taglio WHERE giocatore_id = %s AND team_id = %s", (gid, team), many=True) or []}
cap = lambda team, s: db.cap_occupato_team(team, str(s))

# ── 2026: tagli, DPE ───────────────────────────────────────────────────────────
fase("offseason-fa", 2026)                  # tagli fuori dai minimi di roster della RS
grosso = gioc("Grosso Tagliato", "team01", 20, 3, 2026)            # tagliato: 20x3 spalmato
esegui_taglio(tm.get_team_by_id("team01"), grosso)
r_g = rate(grosso, "team01")
ok(min(r_g) == "2026" and "2027" in r_g and sum(r_g.values()) == 60, f"taglio 20x3: 60M spalmati dal 2026 {r_g}")
firma(grosso, "team02", 3, 2, 2026)                                # lo firma un'altra squadra
dpe = gioc("Con Dpe", "team01", 12, 2, 2026)
db.inserisci_dpe(dpe, "team01", "2026", 12, 6, True, "prova")
x1 = gioc("Da Rinnovare", "team01", 10, 2, 2026); fm("Da Rinnovare", 2026, 12)
gioc("Stipendio", "team01", 110, 3, 2026)
cap26 = cap("team01", 2026)
ok(cap26 == r_g["2026"] + 6 + 10 + 110, f"cap 2026: rata del taglio + DPE (6, non 12) + contratti ({cap26})")

# ── 2027: la stagione nuova ────────────────────────────────────────────────────
fase("offseason-rinnovi", 2027)
S.applica_stagione(2027)
cap27 = cap("team01", 2027)
ok(cap27 == r_g["2027"] + 12 + 10 + 110, f"cap 2027: la rata 2027 del taglio, la DPE del 2026 non vale più (12 pieno) ({cap27})")
c = next(c for c in R.candidati("team01") if c["giocatore_id"] == x1)
ok(R.cap_dopo(tm.get_team_by_id("team01"), c, 13) == cap27 + 3, "rinnovo: il cap dopo conta anche la rata del taglio")
from shared import prospetto_rinnovi as P
d = P.dati({"id": "team01", "nome": "x"})
ok(d["riquadri"][2]["v"] == f"{cap27}M", "prospetto ai rinnovi: lo stesso cap, con la rata del taglio")
fase("offseason-break", 2026)
d = P.dati({"id": "team01", "nome": "x"})
ok(d["riquadri"][2]["v"] == f"{r_g['2027'] + 12 + 10 + 110}M", f"prospetto nel break: il cap 2027 stimato ha la rata 2027 {d['riquadri'][2]}")
fase("offseason-rinnovi", 2027)

# ── decadimento: ritiro toglie le spalmature future di tutti, Cam Thomas no ─────
err = asyncio.run(applica_decadimento(Bot(), "team02", grosso, "ritiro", "prova"))
r_dopo = rate(grosso, "team01")
ok(err is None and r_dopo == {"2026": r_g["2026"]}, f"ritiro nel 2027: a chi l'aveva tagliato resta solo la rata 2026 {r_dopo}")
ok(cap("team01", 2027) == 12 + 10 + 110, "cap 2027 senza più la rata")
ct = gioc("Tagliato Ct", "team03", 15, 3, 2026)
fase("offseason-fa", 2026); esegui_taglio(tm.get_team_by_id("team03"), ct); fase("offseason-rinnovi", 2027)
r_ct = rate(ct, "team03")
firma(ct, "team04", 2, 1, 2027)
err = asyncio.run(applica_decadimento(Bot(), "team04", ct, "cam_thomas", "prova"))
ok(err is None and rate(ct, "team03") == r_ct, "Cam Thomas: le spalmature di chi l'aveva tagliato restano tutte")

# ── decadimento di un RFA dichiarato: la dichiarazione decade, se ne può fare un'altra ──
r1 = gioc("Rfa Ritirato", "team03", 7, 1, 2026)
r2 = gioc("Altro X0", "team03", 5, 1, 2026)
S.dichiara_rfa("team03", r1, "prova")
err = asyncio.run(applica_decadimento(Bot(), "team03", r1, "ritiro", "prova"))
ok(err is None and db.rfa_squadra("team03", "2027") is None and db.rfa_usata("team03", "2027") is None,
   "RFA dichiarato e poi ritirato: la dichiarazione non resta in vigore né «usata»")
S.dichiara_rfa("team03", r2, "prova")
ok(db.rfa_squadra("team03", "2027")["giocatore_id"] == r2, "la squadra dichiara un altro RFA")

# ── 10-day: non passa l'estate (chiuso entrando nel break) e non si dichiara RFA ──
fase("playoff", 2026)
dd = gioc("Dieci Giorni", "team04", 1, 1, 2026, "10day")
ok(not any(x["giocatore_id"] == dd for x in S.candidati_rfa("team04")), "un 10-day non è mai un candidato RFA")
from handlers.stagione import dopo_cambio_fase
nota = asyncio.run(dopo_cambio_fase(Bot(), "playoff", "offseason-break"))
ok(db._q("SELECT 1 FROM contratti WHERE giocatore_id = %s AND attivo", (dd,), one=True) is None and "Dieci Giorni" in nota,
   f"entrando nel break il 10-day si chiude ({nota[-120:]!r})")
ok(db._qval("SELECT count(*) FROM transazioni WHERE giocatore_id = %s AND tipo = '10day_scadenza'", (dd,)) == 1,
   "con il suo movimento di fine 10-day")
fase("offseason-fa", 2026)

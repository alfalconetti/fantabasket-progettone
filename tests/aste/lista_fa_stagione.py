import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v72 (Luca, 24/10): quando almeno il 70% dei giocatori firmati ha giocato nella stagione in corso si passa
d'anno: /lista_fa non mostra più la stagione prima, quindi chi non ha ancora giocato quest'anno sparisce;
l'asta per lui si apre lo stesso, con un avviso sotto «Quanto offri?» (dati aggiornati al…). Prima dello
switch ognuno coi dati più recenti."""
import asyncio, json, os, types
import database as db, pg_client as pg, utils
pg.init_pg(); db.init_db()
pg.q("TRUNCATE giocatori, contratti, transazioni, dpe, impatto_taglio, rookie RESTART IDENTITY CASCADE")
pg.q(open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "fantabasket-main", "bref_schema.sql")).read())
pg.q("TRUNCATE bref_stats")
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
g = json.load(open(os.environ["GLOBALS_PATH"])); g["stagione_corrente"] = "2026"; json.dump(g, open(os.environ["GLOBALS_PATH"], "w"))
def gioc(common, bref=None):
    pg.q("INSERT INTO giocatori (nome_bref, nome_common, nome_norm) VALUES (%s, %s, %s)", (bref or common, common, common.lower()))
def riga(bref, stagione, fm=20, ts="2026-10-24 12:00+02"):
    pg.q("""INSERT INTO bref_stats (timestamp, stagione, nome_bref, g, pts, fga, fgm, ftm, fta, fg3m, orb, drb, ast, stl, blk, tov)
            VALUES (%s, %s, %s, 1, %s, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)""", (ts, stagione, bref, fm * 2))
# free agent: Uno ha giocato nel 2026-27; Jokic (bref «Jokić») e Due solo l'anno prima; Senza Storico mai
for n in ("Uno Giocato", "Due Fermo"):
    gioc(n)
gioc("Nikola Jokic", "Nikola Jokić")
gioc("Senza Storico")
gioc("Vecchio Ritirato")                   # ultima stagione: 2024-25 (bref «2025»)
for n in ("Uno Giocato", "Due Fermo", "Nikola Jokić"):
    riga(n, "2026", ts="2026-04-10 12:00+02")
riga("Vecchio Ritirato", "2025", ts="2025-04-10 12:00+02")
riga("Uno Giocato", "2027")
# 10 firmati: 6 hanno giocato nel 2026-27 (60%: sotto il 70%)
firmati = []
for i in range(10):
    n = f"Firmato {i}"
    gioc(n)
    gid = pg.q("SELECT id FROM giocatori WHERE nome_common = %s", (n,), one=True)["id"]
    pg.q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo) VALUES (%s, 'team01', 5, 2, '2026', 'normale')", (gid,))
    firmati.append(n)
for n in firmati[:6]:
    riga(n, "2027")
import handlers.user as U, handlers.offerte as O
st = pg.stato_stagione(["Uno Giocato", "Due Fermo", "Nikola Jokic", "Senza Storico", "Vecchio Ritirato"])
ok(not st["attivo"] and abs(st["quota"] - 0.6) < 1e-9 and st["giocato"] == {"uno giocato"}, f"6 firmati su 10 hanno giocato: niente switch {st['quota']}")
righe, nascosti = U.righe_lista_fa()
fa = {r["nome"]: r for r in righe}
ok(nascosti == 2 and set(fa) == {"Uno Giocato", "Due Fermo", "Nikola Jokic"}
   and fa["Uno Giocato"]["stagione_bref"] is None and fa["Due Fermo"]["stagione_bref"] == "2025" and fa["Nikola Jokic"]["stagione_bref"] == "2025"
   and fa["Nikola Jokic"].get("fantamedia") is not None,
   "prima dello switch: chi ha giocato quest'anno o l'anno prima, coi dati più recenti (con l'anno; Jokic col nome di bref); "
   "mai chi non gioca da più di una stagione o non ha mai giocato")
ok(pg.avviso_non_ha_giocato("Due Fermo") == "" and "non gioca in NBA dal 2024-25" in pg.avviso_non_ha_giocato("Vecchio Ritirato")
   and "mai giocato in NBA" in pg.avviso_non_ha_giocato("Senza Storico"),
   "prima dello switch: avviso solo per chi la lista non mostra, con l'ultima stagione giocata (o mai)")
riga(firmati[6], "2027", ts="2026-10-23 12:00+02")
st = pg.stato_stagione(["Uno Giocato", "Due Fermo", "Nikola Jokic"])
ok(st["attivo"] and abs(st["quota"] - 0.7) < 1e-9, "7 firmati su 10 (70%): si passa alla stagione in corso")
riga("Nikola Jokić", "2027", ts="2026-10-23 12:00+02")
righe, nascosti = U.righe_lista_fa()
ok({r["nome"] for r in righe} == {"Uno Giocato", "Nikola Jokic"} and nascosti == 3,
   f"dopo lo switch: solo chi ha giocato quest'anno (anche Jokic, nome diverso su bref) {[r['nome'] for r in righe]}")
av = pg.avviso_non_ha_giocato("Due Fermo")
ok("non gioca in NBA dal 2025-26" in av and "aggiornati al 24/10" in av and pg.avviso_non_ha_giocato("Uno Giocato") == "",
   f"avviso solo per chi non ha giocato, con la data dei dati: {av!r}")
out = []
class M:
    async def reply_text(s, t, **k): out.append(t)
asyncio.run(U.cmd_lista_fa(types.SimpleNamespace(effective_message=M(), effective_user=types.SimpleNamespace(id=101)),
                           types.SimpleNamespace(bot=types.SimpleNamespace(username="bot"), args=[])))
ok(out and "Non ci sono 3 free agent" in out[-1] and "in questa stagione" in out[-1] and "/nuova_fa" in out[-1], "/lista_fa: dice quanti ne nasconde e come aprire l'asta lo stesso")

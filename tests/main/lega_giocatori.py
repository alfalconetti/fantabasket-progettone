import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# v7.5.0 (Luca, 10/11): /giocatori, la ricerca coi filtri (shared/elenco_giocatori.py), in loucabot e nel bot principale.
# Gira dopo le prove di loucabot (le tabelle nba_*): giocatori «Elenco *», atleti «eg*».
import asyncio, re, types
from datetime import datetime, timedelta, timezone
import database as db
import settings
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
from shared import elenco_giocatori as EG
import handlers.lega as LG
import comandi

S = settings.stagione_corrente()
SB = str(int(S) + 1)


def pulizia():
    db._q("DELETE FROM nba_infortuni WHERE atleta LIKE 'eg%%'"); db._q("DELETE FROM nba_tabellini WHERE atleta LIKE 'eg%%'")
    db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'eg%%'"); db._q("DELETE FROM nba_atleti WHERE atleta LIKE 'eg%%'")
    db._q("DELETE FROM bref_stats WHERE nome_bref LIKE 'Elenco %%'")
    for r in db._q("SELECT id FROM giocatori WHERE nome_common LIKE 'Elenco %%'", many=True) or []:
        for t in ("cambi_ruolo", "posizioni_eleggibili", "rookie", "transazioni", "contratti"):
            db._q(f"DELETE FROM {t} WHERE giocatore_id = %s", (r["id"],))
        db._q("DELETE FROM giocatori WHERE id = %s", (r["id"],))


pulizia()
# tutti gli altri giocatori delle prove non devono disturbare: si filtra sempre per nome «Elenco»
gid = {}
for nome, espn, nba in (("Elenco Centro Firmato", "eg1", "DEN"), ("Elenco Guardia Fa", "eg2", "LAL"),
                        ("Elenco Ala Diritti", "eg3", "BOS"), ("Elenco Fa Panchina", "eg4", None),
                        ("Elenco Fa Mai Giocato", "eg5", "LAL"), ("Elenco Senza Espn", None, None),
                        ("Elenco Jokić Accento", "eg7", "DEN")):
    gid[nome] = db._qval("INSERT INTO giocatori (nome_bref, nome_common, nome_norm, espn_id) VALUES (%s, %s, %s, %s) RETURNING id",
                         (nome, nome, nome.lower(), espn))
    if nba:
        db._q("INSERT INTO nba_atleti (atleta, nome, squadra) VALUES (%s, %s, %s)", (espn, nome, nba))
for nome, pos in (("Elenco Centro Firmato", "C,PF"), ("Elenco Guardia Fa", "PG,SG"), ("Elenco Ala Diritti", "SF"),
                  ("Elenco Fa Panchina", "C"), ("Elenco Jokić Accento", "C")):
    db._q("INSERT INTO posizioni_eleggibili (giocatore_id, posizioni, fonte) VALUES (%s, %s, 'prova')", (gid[nome], pos))
db._q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) VALUES (%s, 'team01', 30, 3, %s, 'normale', TRUE)",
      (gid["Elenco Centro Firmato"], S))
db._q("INSERT INTO contratti (giocatore_id, team_id, importo, anni_originali, stagione_firma, tipo, attivo) VALUES (%s, 'team02', 4, 1, %s, 'rookie', TRUE)",
      (gid["Elenco Jokić Accento"], S))
db._q("INSERT INTO cambi_ruolo (giocatore_id, team_id, ruolo_da, ruolo_a, stagione, tipo) VALUES (%s, 'team01', NULL, 'C', %s, 'iniziale')",
      (gid["Elenco Centro Firmato"], S))
db._q("INSERT INTO rookie (giocatore_id, team_id, round, pick_numero, anno_draft) VALUES (%s, 'team03', 1, 5, %s)", (gid["Elenco Ala Diritti"], S))

# tabellini della stagione: firmato 7 partite (le ultime 5 più alte), guardia FA 3, ala 2, panchina 1 (e uno 0 con 0 minuti, che non conta)
ora = datetime.now(timezone.utc)
for i in range(7):
    db._q("INSERT INTO nba_partite (espn_id, stagione, tipo, data_et, inizio, casa, trasferta, stato) VALUES (%s, %s, 2, %s, %s, 'DEN', 'LAL', 'STATUS_FINAL')",
          (f"eg_p{i}", S, (ora - timedelta(days=10 - i)).date(), ora - timedelta(days=10 - i)))
fp = {"eg1": [20, 20, 40, 40, 40, 40, 40], "eg2": [30, 31, 32], "eg3": [10, 12], "eg4": [5, 0], "eg7": [25, 25, 25]}
for a, punti in fp.items():
    for i, p in enumerate(punti):
        db._q("INSERT INTO nba_tabellini (partita, atleta, nome, squadra, giocato, minuti, pts, fp) VALUES (%s, %s, %s, 'DEN', TRUE, %s, 10, %s)",
              (f"eg_p{i}", a, a, 0 if (a == "eg4" and i == 1) else 20, p))
db._q("INSERT INTO nba_infortuni (giorno, atleta, nome, squadra, stato, dettaglio, preso) VALUES (%s, 'eg2', 'x', 'LAL', 'Out', 'Caviglia', %s)",
      (ora.date(), ora + timedelta(days=3650)))
# Basketball-Reference: chi non è su ESPN (stagione in corso) e una stagione passata
z = ", fga, fgm, ftm, fta, fg3m, orb, drb, ast, stl, blk, tov"
db._q(f"INSERT INTO bref_stats (stagione, nome_bref, team, g, pts{z}) VALUES (%s, 'Elenco Senza Espn', 'MIA', 12, 36, 0,0,0,0,0,0,0,0,0,0,0)", (SB,))
db._q(f"INSERT INTO bref_stats (stagione, nome_bref, team, g, pts{z}) VALUES ('2025', 'Elenco Centro Firmato', 'DEN', 70, 60, 0,0,0,0,0,0,0,0,0,0,0)")
db._q(f"INSERT INTO bref_stats (stagione, nome_bref, team, g, pts{z}) VALUES ('2025', 'Elenco Fa Panchina', 'DEN', 10, 8, 0,0,0,0,0,0,0,0,0,0,0)")
# la stessa stagione scaricata due volte: vale l'ultima
db._q(f"INSERT INTO bref_stats (timestamp, stagione, nome_bref, team, g, pts{z}) VALUES (NOW() - INTERVAL '1 day', '2025', 'Elenco Guardia Fa', 'LAL', 30, 20, 0,0,0,0,0,0,0,0,0,0,0)")
db._q(f"INSERT INTO bref_stats (stagione, nome_bref, team, g, pts{z}) VALUES ('2025', 'Elenco Guardia Fa', 'LAL', 60, 50, 0,0,0,0,0,0,0,0,0,0,0)")


def nomi(testo):
    m, md, _ = EG.risposta("nome:^Elenco " + testo)
    return re.findall(r"<b>(Elenco [^<]+)</b>", m), m, md


# tutti: firmati e diritti sempre, i FA solo se hanno giocato; ordine per media
n, m, _ = nomi("")
ok(n == ["Elenco Centro Firmato", "Elenco Guardia Fa", "Elenco Jokić Accento", "Elenco Senza Espn", "Elenco Ala Diritti", "Elenco Fa Panchina"],
   "tutti, per media; il FA che non ha mai giocato no\n" + m)
ok("Elenco Centro Firmato</b> · DEN · <b>34,25</b> (7 G, ult. 5: 40,00)" in m, "media ESPN, partite e ultime 5")
ok("📝 Alfa · 30M × 3 anni · ruolo C" in m and "📝 Beta · 4M × 1 anno (rookie)" in m, "contratto: squadra, importo, anni, rookie, ruolo")
ok("🔒 diritti di " in m and "🆓 FA" in m, "diritti e FA")
ok("Elenco Fa Panchina</b> · — · <b>5,00</b> (1 G)" in m, "uno 0 con 0 minuti non conta; senza squadra NBA il trattino")
ok("Elenco Senza Espn</b> · — · <b>18,00</b> (12 G)" in m, "chi non è su ESPN: la media di Basketball-Reference")
ok("🩹 Out" in m, "l'infortunio dell'ultimo snapshot")

# i filtri
ok(nomi("fa")[0] == ["Elenco Guardia Fa", "Elenco Senza Espn", "Elenco Fa Panchina"], "fa")
ok(nomi("stato:firmati")[0] == ["Elenco Centro Firmato", "Elenco Jokić Accento"], "stato:firmati")
ok(nomi("diritti")[0] == ["Elenco Ala Diritti"], "diritti")
ok(nomi("C")[0] == ["Elenco Centro Firmato", "Elenco Jokić Accento", "Elenco Fa Panchina"], "un ruolo scritto da solo")
ok(nomi("g sf")[0] == ["Elenco Guardia Fa", "Elenco Ala Diritti"], "G = PG o SG, più ruoli insieme")
ok(nomi("ruolo:PF")[0] == ["Elenco Centro Firmato"], "ruolo:")
ok(nomi("nba:lal")[0] == ["Elenco Guardia Fa"], "nba:")
ok(nomi("nba:no")[0] == ["Elenco Senza Espn", "Elenco Fa Panchina"], "nba:no")
ok(nomi("squadra:Gamma")[0] == ["Elenco Ala Diritti"], "squadra: anche i diritti")
ok(nomi("ruolo_squadra:C")[0] == ["Elenco Centro Firmato"], "ruolo_squadra:")
ok(nomi("top:2")[0] == ["Elenco Centro Firmato", "Elenco Guardia Fa"], "top:")
ok(nomi("min_g:3")[0] == ["Elenco Centro Firmato", "Elenco Guardia Fa", "Elenco Jokić Accento", "Elenco Senza Espn"], "min_g:")
ok(nomi("costo:>10")[0] == ["Elenco Centro Firmato"] and nomi("costo:1-5")[0] == ["Elenco Jokić Accento"], "costo: confronto e fascia")
ok(nomi("anni:1")[0] == ["Elenco Jokić Accento"], "anni:")
ok(nomi("infortunati:no")[0] == ["Elenco Centro Firmato", "Elenco Jokić Accento", "Elenco Senza Espn", "Elenco Ala Diritti", "Elenco Fa Panchina"],
   "infortunati:no")
ok(nomi("ordina:costo")[0][:2] == ["Elenco Centro Firmato", "Elenco Jokić Accento"], "ordina:costo")
ok(nomi("ordina:ultime5")[0][0] == "Elenco Centro Firmato", "ordina:ultime5 (chi non ne ha 5: la media)")
ok(EG.risposta("nome:jokic")[0].count("Elenco Jokić") == 1, "regex: accenti indifferenti")
ok(EG.risposta("nome:^ELENCO.*panchina$")[0].count("<b>Elenco") == 1, "regex: maiuscole indifferenti")
ok(nomi("guardia")[0] == ["Elenco Guardia Fa"], "le parole da sole cercano nel nome")
ok(nomi("C fa top:1")[0] == ["Elenco Fa Panchina"], "i filtri si combinano")

# stagione passata: solo chi ha giocato, dalla riga più recente di bref; il contratto è quello di oggi
n, m, _ = nomi("anno:2024")
ok(n == ["Elenco Centro Firmato", "Elenco Guardia Fa", "Elenco Fa Panchina"] and "2024-25" in m
   and "Elenco Guardia Fa</b> · LAL · <b>25,00</b> (60 G)" in m and "📝 Alfa" in m and "ult. 5" not in m,
   "anno:2024: Basketball-Reference, la riga più recente, contratto di oggi\n" + m)

# errori e aiuto
ok(EG.risposta("pippo:1")[0].startswith("⚠️ Filtro sconosciuto"), "filtro sconosciuto")
ok("non valida" in EG.risposta("nome:(")[0], "regex non valida")
ok("PG, SG, SF, PF, C" in EG.risposta("ruolo:X")[0], "ruolo sbagliato")
ok("dal 1979" in EG.risposta("anno:1900")[0], "anno fuori dai limiti")
ok("costo:&lt;10" in EG.risposta("aiuto")[0], "aiuto")
ok("Nessun giocatore" in EG.risposta("nome:^Nessunoconquestonome$")[0], "nessun risultato")
ok(EG.leggi('squadra:"Alfa" nome:"^Elenco C"', int(S))["squadra"]["id"] == "team01", "valori tra virgolette")

# troppi per un messaggio: i primi 10 e il file .md
_max = EG.MAX_MESSAGGIO
EG.MAX_MESSAGGIO = 300
m, md, nome_f = EG.risposta("nome:^Elenco")
EG.MAX_MESSAGGIO = _max
ok(md and nome_f.endswith(".md") and "| # | Giocatore | NBA | Pos. |" in md and "| Elenco Fa Panchina | — | C | 5,00 | 1 |" in md
   and "i primi 10" in m, "oltre il messaggio: il file markdown con tutti\n" + (md or "")[:600])

# il comando: messaggio e file
out = []
class M:
    text = "/giocatori nome:^Elenco fa"
    async def reply_text(s, t, **k): out.append(("t", t))
    async def reply_document(s, document=None, filename=None, **k): out.append(("d", filename))
asyncio.run(EG.cmd_giocatori(types.SimpleNamespace(effective_message=M()), types.SimpleNamespace(args=[])))
ok(out and out[0][0] == "t" and "Elenco Guardia Fa" in out[0][1] and len(out) == 1, "/giocatori: un messaggio")

# nel bot principale solo in privato, nel menu in privato e non nei gruppi
hs = {next(iter(h.commands)): h for h in LG.get_handlers() if hasattr(h, "commands")}
ok("giocatori" in hs and "PRIVATE" in str(hs["giocatori"].filters).upper(), "bot principale: /giocatori solo in privato")
li = comandi.liste_comandi(settings.fase())
ok("giocatori" in {c.command for c in li["gm"]} and "giocatori" not in {c.command for c in li["group"]}, "menu: in privato sì, nei gruppi no")

pulizia()
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'eg_%%'")

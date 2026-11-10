import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
# v7.5.0 (Luca, 10/11): /giocatori, la ricerca coi filtri (shared/elenco_giocatori.py), in loucabot e nel bot principale.
# Gira dopo le prove di loucabot (le tabelle nba_*): giocatori «Elenco *», atleti «eg*».
import asyncio, types
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


def risp(testo):
    return EG.risposta("nome:^Elenco " + testo)


def righe(testo):
    r = risp(testo)
    return [x for p in r.get("pagine", []) for x in p["righe"]]


def nomi(testo):
    return [x["nome"] for x in righe(testo)]


def riga(testo, nome):
    return next(x for x in righe(testo) if x["nome"] == nome)


# la foto ESPN di uno (le scarica loucabot): nell'immagine il percorso, gli altri le iniziali
import tempfile
from PIL import Image
_os.environ["FOTO_DIR"] = tempfile.mkdtemp()
Image.new("RGBA", (350, 254), (120, 80, 200, 255)).save(_os.path.join(_os.environ["FOTO_DIR"], "eg1.png"))

# tutti: firmati e diritti sempre, i FA solo se hanno giocato; ordine per media
n = nomi("")
ok(n == ["Elenco Centro Firmato", "Elenco Guardia Fa", "Elenco Jokić Accento", "Elenco Senza Espn", "Elenco Ala Diritti", "Elenco Fa Panchina"],
   "tutti, per media; il FA che non ha mai giocato no: " + str(n))
c = riga("", "Elenco Centro Firmato")
ok(c["nba"] == "DEN" and c["media"] == "34,25" and c["sotto_media"] == "7 G · ult. 5: 40,00" and c["pos"] == "PF,C",
   "media ESPN, partite, ultime 5, posizioni " + str(c))
ok(c["stato"] == "firmati" and c["squadra"] == "Alfa" and c["contratto"] == "30M × 3 anni · ruolo C" and c["colore"].startswith("#"),
   "firmato: squadra col suo colore, contratto e ruolo")
ok(c["foto"] and c["foto"].endswith("eg1.png") and riga("", "Elenco Guardia Fa")["foto"] is None
   and riga("", "Elenco Guardia Fa")["iniziali"] == "EG", "la foto ESPN, se no le iniziali")
ok(riga("", "Elenco Jokić Accento")["contratto"] == "4M × 1 anno (rookie)", "contratto rookie")
d = riga("", "Elenco Ala Diritti")
ok(d["stato"] == "diritti" and d["squadra"] == "diritti · Gamma", "diritti")
fa = riga("", "Elenco Fa Panchina")
ok(fa["stato"] == "fa" and fa["squadra"] == "FA" and fa["nba"] == "—" and fa["media"] == "5,00" and fa["sotto_media"] == "1 G",
   "FA; uno 0 con 0 minuti non conta; senza squadra NBA il trattino")
ok(riga("", "Elenco Senza Espn")["media"] == "18,00", "chi non è su ESPN: la media di Basketball-Reference")
ok(riga("", "Elenco Guardia Fa")["inf"] == "Out", "l'infortunio dell'ultimo snapshot")

# i filtri
ok(nomi("fa") == ["Elenco Guardia Fa", "Elenco Senza Espn", "Elenco Fa Panchina"], "fa")
ok(nomi("stato:firmati") == ["Elenco Centro Firmato", "Elenco Jokić Accento"], "stato:firmati")
ok(nomi("diritti") == ["Elenco Ala Diritti"], "diritti")
ok(nomi("C") == ["Elenco Centro Firmato", "Elenco Jokić Accento", "Elenco Fa Panchina"], "un ruolo scritto da solo")
ok(nomi("g sf") == ["Elenco Guardia Fa", "Elenco Ala Diritti"], "G = PG o SG, più ruoli insieme")
ok(nomi("ruolo:PF") == ["Elenco Centro Firmato"], "ruolo:")
ok(nomi("nba:lal") == ["Elenco Guardia Fa"], "nba:")
ok(nomi("nba:no") == ["Elenco Senza Espn", "Elenco Fa Panchina"], "nba:no")
ok(nomi("squadra:Gamma") == ["Elenco Ala Diritti"], "squadra: anche i diritti")
ok(nomi("squadra:gamm") == ["Elenco Ala Diritti"], "squadra: anche scritta a metà")
ok(nomi("ruolo_squadra:C") == ["Elenco Centro Firmato"], "ruolo_squadra:")
ok(nomi("top:2") == ["Elenco Centro Firmato", "Elenco Guardia Fa"], "top:")
ok(nomi("min_g:3") == ["Elenco Centro Firmato", "Elenco Guardia Fa", "Elenco Jokić Accento", "Elenco Senza Espn"], "min_g:")
ok(nomi("costo:>10") == ["Elenco Centro Firmato"] and nomi("costo:1-5") == ["Elenco Jokić Accento"], "costo: confronto e fascia")
ok(nomi("anni:1") == ["Elenco Jokić Accento"], "anni:")
ok(nomi("infortunati:no") == ["Elenco Centro Firmato", "Elenco Jokić Accento", "Elenco Senza Espn", "Elenco Ala Diritti", "Elenco Fa Panchina"],
   "infortunati:no")
ok(nomi("ordina:costo")[:2] == ["Elenco Centro Firmato", "Elenco Jokić Accento"], "ordina:costo")
ok(nomi("ordina:ultime5")[0] == "Elenco Centro Firmato", "ordina:ultime5 (chi non ne ha 5: la media)")
_n = lambda t: [x["nome"] for p in EG.risposta(t).get("pagine", []) for x in p["righe"]]
ok(_n("nome:jokic") == ["Elenco Jokić Accento"], "regex: accenti indifferenti")
ok(_n("nome:^ELENCO.*panchina$") == ["Elenco Fa Panchina"], "regex: maiuscole indifferenti")
ok(nomi("guardia") == ["Elenco Guardia Fa"], "le parole da sole cercano nel nome")
ok(nomi("C fa top:1") == ["Elenco Fa Panchina"], "i filtri si combinano")

# stagione passata: solo chi ha giocato, dalla riga più recente di bref; il contratto è quello di oggi
r = risp("anno:2024")
g = riga("anno:2024", "Elenco Guardia Fa")
ok(nomi("anno:2024") == ["Elenco Centro Firmato", "Elenco Guardia Fa", "Elenco Fa Panchina"] and r["pagine"][0]["stagione"] == "2024-25"
   and g["media"] == "25,00" and g["sotto_media"] == "60 G" and riga("anno:2024", "Elenco Centro Firmato")["squadra"] == "Alfa"
   and "Basketball-Reference" in r["pagine"][0]["fonte"], "anno:2024: Basketball-Reference, la riga più recente, contratto di oggi")

# errori e aiuto: testo
ok(EG.risposta("pippo:1")["testo"].startswith("⚠️ Filtro sconosciuto"), "filtro sconosciuto")
ok("non valida" in EG.risposta("nome:(")["testo"], "regex non valida")
ok("PG, SG, SF, PF, C" in EG.risposta("ruolo:X")["testo"], "ruolo sbagliato")
ok("dal 1979" in EG.risposta("anno:1900")["testo"], "anno fuori dai limiti")
ok("costo:&lt;10" in EG.risposta("aiuto")["testo"], "aiuto")
ok("Nessun giocatore" in EG.risposta("nome:^Nessunoconquestonome$")["testo"], "nessun risultato")
ok(EG.leggi('squadra:"Alfa" nome:"^Elenco C"', int(S))["squadra"]["id"] == "team01", "valori tra virgolette")

# l'immagine, la didascalia e il file .md con tutti
r = risp("")
p0 = r["pagine"][0]
ok(len(r["pagine"]) == 1 and p0["da"] == 1 and p0["a"] == 6 and p0["tot"] == 6 and p0["pagine"] == 1
   and r["didascalia"].startswith("🏀 Giocatori · ") and r["didascalia"].endswith(" · 6"), "una pagina, didascalia " + r["didascalia"])
png = EG.immagine(p0)
ok(png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 20000, "l'immagine (Typst)")
ok(r["nome"].endswith(".md") and "| # | Giocatore | NBA | Pos. | Media | G | Ult. 5 | Fantabasket | Status |" in r["md"]
   and "| Elenco Fa Panchina | — | C | 5,00 | 1 | — | FA |" in r["md"] and "| Alfa · 30M × 3 anni · ruolo C |" in r["md"]
   and "diritti di Gamma" in r["md"], "il file markdown\n" + r["md"][:500])
# più di 25: un album; oltre le 10 immagini solo nel file
_pi, _mi = EG.PER_IMMAGINE, EG.MAX_IMMAGINI
EG.PER_IMMAGINE, EG.MAX_IMMAGINI = 2, 2
r = risp("")
EG.PER_IMMAGINE, EG.MAX_IMMAGINI = _pi, _mi
ok(len(r["pagine"]) == 2 and [p["da"] for p in r["pagine"]] == [1, 3] and r["pagine"][1]["a"] == 4 and r["pagine"][1]["pagine"] == 2
   and r["pagine"][1]["righe"][0]["n"] == 3 and "nelle immagini i primi 4" in r["didascalia"] and r["md"].count("| Elenco") == 6,
   "album: le immagini a gruppi, oltre il limite solo nel file")

# il comando: immagine (o album) e sotto il file; errori in testo
out = []
class M:
    text = "/giocatori nome:^Elenco fa"
    async def reply_text(s, t, **k): out.append(("t", t))
    async def reply_photo(s, photo=None, caption=None, **k): out.append(("f", caption))
    async def reply_media_group(s, media, **k): out.append(("a", len(media)))
    async def reply_document(s, document=None, filename=None, **k): out.append(("d", filename))
asyncio.run(EG.cmd_giocatori(types.SimpleNamespace(effective_message=M()), types.SimpleNamespace(args=[])))
ok([k for k, _ in out] == ["f", "d"] and "FA" in out[0][1] and out[1][1].endswith(".md"), "/giocatori: l'immagine e il file " + str(out))
out.clear()
EG.PER_IMMAGINE = 2
asyncio.run(EG.cmd_giocatori(types.SimpleNamespace(effective_message=M()), types.SimpleNamespace(args=[])))
EG.PER_IMMAGINE = _pi
ok([k for k, _ in out] == ["a", "d"] and out[0][1] == 2, "/giocatori: l'album e il file " + str(out))
out.clear()
M.text = "/giocatori pippo:1"
asyncio.run(EG.cmd_giocatori(types.SimpleNamespace(effective_message=M()), types.SimpleNamespace(args=[])))
ok([k for k, _ in out] == ["t"], "/giocatori: gli errori in testo")

# nel bot principale solo in privato, nel menu in privato e non nei gruppi
hs = {next(iter(h.commands)): h for h in LG.get_handlers() if hasattr(h, "commands")}
ok("giocatori" in hs and "PRIVATE" in str(hs["giocatori"].filters).upper(), "bot principale: /giocatori solo in privato")
li = comandi.liste_comandi(settings.fase())
ok("giocatori" in {c.command for c in li["gm"]} and "giocatori" not in {c.command for c in li["group"]}, "menu: in privato sì, nei gruppi no")

pulizia()
db._q("DELETE FROM nba_partite WHERE espn_id LIKE 'eg_%%'")

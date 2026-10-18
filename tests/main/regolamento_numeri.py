import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v3.13.0: i numeri del regolamento (FANTA NBA – REGOLAMENTO UFFICIALE, versione dell'11/10/2026)
scritti qui a mano, confrontati con quelli che usa il bot. Se cambia il regolamento si cambia
prima questa prova, poi settings.json o il codice. Lo specchietto completo regola → codice →
prova è in docs/regolamento_e_codice.md."""
import math
import database as db, settings
from shared import regole, ruoli_core
from handlers import stagione as S, tagli as T, dpe as D
db.init_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
s = settings.get()

# Roster, cap, floor (capitoli Roster, Mercato, Luxury e salary floor, Lega)
ok((s["roster_min_regular"], s["roster_max"]) == (10, 15), "roster da 10 a 15 giocatori")
ok(regole.minimi_ruolo() == {"G": 4, "F": 4, "C": 2}
   and (s["roster_min_guardie"], s["roster_min_ali"], s["roster_min_centri"]) == (4, 4, 2),
   "almeno 4 guardie, 4 ali, 2 centri (letti da settings.json da shared/regole)")
ok((s["cap_regular"], s["cap_offseason"], s["salary_floor"]) == (150, 165, 115), "cap 150, luxury 165 in preseason, floor 115")
ok(s["numero_teams"] == 24, "24 franchigie")

# Mercato
ok(s["durata_asta_ore"] == 18, "l'asta chiude 18 ore dopo l'ultimo rilancio")
ok(s["timeout_firma_fa_ore"] == 48 and s["ore_comunicazione_ruolo"] == 48, "48 ore per anni e ruolo dopo un'asta FA, e per il ruolo dopo una trade")
ok([settings.anni_minimi_contratto(x) for x in (1, 19, 20, 34, 35, 60)] == [1, 1, 2, 2, 3, 3],
   "da 20M almeno x2, da 35M x3")
ok(s["stepien_anni"] == 4, "Stepien: finestra di 4 anni contigui (il capitolo Stepien; nel Mercato c'è scritto 3)")

# Ruoli e cambi ruolo
DM = ruoli_core.deficit_minimo
base = ["PG", "SG", "PG", "SG", "SF", "PF", "SF", "PF", "C", "C"]
ok(DM(base, []) == 0 and DM(base[:-1], []) == 1 and DM(["PG"] * 10, []) == 6,
   "minimi dei ruoli: 4 G (PG/SG), 4 F (SF/PF), 2 C; le guardie in più non coprono altro")
ok(DM(base[:-1], [{"PF", "C"}]) == 0 and DM(base[:-1], [{"PF", "SF"}]) == 1
   and DM(base[:-2], [{"C", "PF"}, {"C", "SG"}]) == 0,
   "minimi dei ruoli: chi arriva copre il buco con una delle sue posizioni eleggibili")
from handlers import cambi_ruolo as CR
ok(regole.giorni_riacquisto_ruolo() == 60, "ripreso entro 60 giorni: torna nel vecchio ruolo")
ok((regole.max_cambi_ordinari(), regole.giorni_erminio(), regole.giorni_saedro()) == (2, 14, 10),
   "2 cambi ruolo a stagione, Erminio entro due settimane, Saedro di 10 giorni")

# Tabella dei compensi minimi per fantapunti (draft iniziale, minimi dei rinnovi)
TABELLA = [(0, 1), (10.99, 1), (11, 2), (14.99, 2), (15, 5), (19.99, 5), (20, 10), (24.99, 10), (25, 15),
           (29.99, 15), (30, 20), (34.99, 20), (35, 25), (39.99, 25), (40, 30), (44.99, 30), (45, 35), (70, 35)]
ok(all(settings.minimo_contratto_per_media(fp) == m for fp, m in TABELLA), "tabella dei compensi minimi per fantapunti")

# Tagli
ok(regole.max_tagli_gratuiti() == 3 and T._e_taglio_gratuito(1, 1) and not T._e_taglio_gratuito(2, 1)
   and not T._e_taglio_gratuito(1, 2), "3 tagli gratuiti a stagione, solo 1x1")
BASSI = {(1, 1): [1], (2, 1): [1, 1], (3, 1): [1, 1, 1], (4, 1): [2, 1, 1],
         (1, 2): [1, 1], (2, 2): [1, 1, 1, 1], (3, 2): [2, 2, 1, 1], (4, 2): [2, 2, 2, 2],
         (1, 3): [1, 1, 1], (2, 3): [2, 1, 1, 1, 1], (3, 3): [2, 2, 2, 2, 1], (4, 3): [3, 3, 2, 2, 2],
         (5, 1): [2, 2, 1], (5, 2): [3, 3, 2, 2], (5, 3): [4, 3, 3, 3, 2]}
rate = lambda imp, anni: [r["importo"] for r in T.calcola_impatto_taglio(imp, anni, "2026")]
diversi = {k: rate(*k) for k, v in BASSI.items() if rate(*k) != v}
ok(not diversi, f"tabella dei tagli fino a 5M, voce per voce{': ' + str(diversi) if diversi else ''}")
PERC = {1: [50, 30, 20], 2: [60, 50, 50, 40], 3: [70, 70, 60, 50, 50]}
storti = []
for imp in range(6, 61):
    for anni, p in PERC.items():
        r = rate(imp, anni)
        if sum(r) != imp * anni or len(r) != len(p) or r[0] != math.ceil(imp * p[0] / 100) or min(r) < 1:
            storti.append((imp, anni, r))
ok(not storti, f"sopra 5M: rate 50-30-20 / 60-50-50-40 / 70-70-60-50-50, somma uguale al contratto{': ' + str(storti[:3]) if storti else ''}")

# DPE
ok(D._importo_dpe(5) == 3 and all(D._importo_dpe(i) == i - math.ceil(i * 0.25) for i in range(1, 60)),
   "DPE: −25% arrotondato per eccesso (Klay 5 → 3)")

# Rookie scale
SCALA = {1: [12, 13, 14, 15], 2: [10, 11, 12, 13], 3: [10, 11, 12, 13], 4: [8, 9, 10, 11], 5: [8, 9, 10, 11],
         6: [5, 6, 7, 8], 10: [5, 6, 7, 8], 11: [3, 3, 4, 4], 24: [3, 3, 4, 4], 25: [2, 2, 3, 3], 30: [2, 2, 3, 3],
         31: [1, 1, 2, 2], 48: [1, 1, 2, 2]}
ok(all([S.importo_scala(p, i) for i in range(4)] == v for p, v in SCALA.items())
   and all([x["anni"] for x in S.scala(p)] == [2, 1, 2, 1] for p in SCALA), "rookie scale: importi per pick e durate x2, x1, x2, x1")

# Doncic: X per difetto all'intero, risultato per eccesso
atteso = lambda x: None if x < 20 else (12 + math.ceil(round(0.6 * (x - 20), 6)) if x < 25 else 15 + math.ceil(round(0.4 * (x - 25), 6)))
ok(all(S.doncic(x + d) == atteso(x) for x in range(15, 60) for d in (0, 0.5, 0.99)), "Doncic: 12 + 0,6·(X−20) e 15 + 0,4·(X−25)")
ok((S.doncic(19.99), S.doncic(20), S.doncic(24.99), S.doncic(25), S.doncic(27), S.doncic(30)) == (None, 12, 15, 15, 16, 17),
   "Doncic, esempi: 19,99 niente, 20 → 12, 24,99 → 15, 25 → 15, 27 → 16, 30 → 17")

# Fantapunti (capitolo Partita): la fantamedia di bref usa gli stessi pesi
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Prova Regolamento'")
riga = dict(pts=20, ast=5, orb=2, drb=6, fg3m=2, fga=15, fgm=8, fta=5, ftm=4, stl=1, blk=1, tov=3)
db._q("""INSERT INTO bref_stats (stagione, nome_bref, pts, ast, orb, drb, fg3m, fga, fgm, fta, ftm, stl, blk, tov)
         VALUES ('2099', 'Prova Regolamento', %(pts)s, %(ast)s, %(orb)s, %(drb)s, %(fg3m)s, %(fga)s, %(fgm)s,
                 %(fta)s, %(ftm)s, %(stl)s, %(blk)s, %(tov)s)""", riga)
fm = float(db._qval("SELECT fantamedia FROM bref_stats WHERE nome_bref = 'Prova Regolamento'"))
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Prova Regolamento'")
pesi = dict(pts=0.5, ast=2, orb=2, drb=1.25, fg3m=1.5, fga=-0.5, fgm=1, fta=-0.75, ftm=1, stl=2, blk=2, tov=-2)
ok(abs(fm - sum(riga[k] * p for k, p in pesi.items())) < 0.01, f"fantapunti: pesi del regolamento ({fm})")

# Stepien (capitolo Mercato): in ogni finestra di 4 anni contigui almeno una PROPRIA 1st;
# le 2nd non contano, gli anni fino al 2026 sono coperti d'ufficio (prima del bot)
from validators import trade as VT
db._q("TRUNCATE pick RESTART IDENTITY CASCADE")
for anno in range(2027, 2034):
    for rnd in (1, 2):
        db._q("INSERT INTO pick (proprietario_orig, proprietario_att, anno, round) VALUES ('team01','team01',%s,%s)",
              (str(anno), rnd))
prima = {int(r["anno"]): r["id"] for r in db.get_proprie_1st_pick_storico("team01")}
fuori = lambda *anni: VT.finestra_scoperta(VT.anni_coperti_stepien("team01", out_ids=[prima[a] for a in anni]))
ok(fuori(2027, 2028, 2029) is None, "Stepien: cedere 3 prime scelte di fila si può")
ok(fuori(2027, 2028, 2029, 2030) == (2027, 2030), "Stepien: 4 di fila no (finestra 2027–2030)")
ok(fuori(2027, 2028, 2030, 2031) is None, "Stepien: 4 non contigue sì")
db._q("UPDATE pick SET proprietario_att = 'team02' WHERE round = 2")
ok(fuori(2027, 2028, 2029, 2030) == (2027, 2030), "Stepien: tenere le 2nd non basta")
db._q("UPDATE pick SET proprietario_att = 'team02' WHERE round = 1 AND anno IN ('2027','2028','2029')")
ok(VT.anni_1st_bloccate_stepien("team01") == {2030}, "Stepien: dopo averne cedute 3, la quarta è bloccata (tag S su /assets)")

# Salary floor nelle trade in stagione (Luca, 12/10/2026): bloccata la trade che porta o lascia una
# squadra sotto i 115M facendole scendere il cap; chi è già sotto può fare trade che lo avvicinano
import json, os
g = json.load(open(os.environ["GLOBALS_PATH"])); g["fase"] = "regular-season-fa"; json.dump(g, open(os.environ["GLOBALS_PATH"], "w"))
db._q("TRUNCATE giocatori, contratti, trade, trade_items, trade_squadre, trade_voti, transazioni, dpe, impatto_taglio, "
      "rfa_dichiarati RESTART IDENTITY CASCADE")
def gioc(n, team, imp):
    gid = db._qval("INSERT INTO giocatori (nome_bref,nome_common,nome_norm) VALUES (%s,%s,%s) RETURNING id", (n, n, n.lower()))
    db._q("INSERT INTO contratti (giocatore_id,team_id,importo,anni_originali,stagione_firma,tipo) VALUES (%s,%s,%s,2,'2026','normale')",
          (gid, team, imp))
    return gid
grosso = gioc("Grosso", "team01", 26); [gioc(f"a{i}", "team01", 10) for i in range(9)]       # team01: 116
b = [gioc(f"b{i}", "team02", 10) for i in range(10)]                                          # team02: 100, sotto
c12 = gioc("Dodici", "team03", 12); [gioc(f"c{i}", "team03", 14) for i in range(9)]          # team03: 138
def floor(da, a, gid_da, gid_a=None):
    t = db.crea_trade_bozza(da, 2, "2026"); db.aggiungi_squadra_trade(t, da, 1); db.aggiungi_squadra_trade(t, a, 2)
    db.aggiungi_item_trade(t, "giocatore", da, a, giocatore_id=gid_da)
    if gid_a:
        db.aggiungi_item_trade(t, "giocatore", a, da, giocatore_id=gid_a)
    return sorted(e.split(":")[0] for e in VT.valida_trade(t)[1] if "salary floor" in e)
ok(floor("team01", "team02", grosso, b[0]) == ["❌ Alfa"], "floor: da 116 a 100 no; chi sale da 100 a 116 sì")
ok(floor("team02", "team03", b[1], c12) == [], "floor: chi è sotto può avvicinarsi (100 → 102)")
ok(floor("team02", "team03", b[2]) == ["❌ Beta"], "floor: chi è sotto non può scendere ancora (100 → 90)")

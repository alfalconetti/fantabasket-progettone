import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v5.8.0: i numeri del regolamento in config/settings.json (shared/regole.py). Ogni chiave si legge
davvero: cambiata nel file, cambia il comportamento del bot (senza riavvio); se manca, vale il default.
La fantamedia di basketball-reference segue i pesi dei fantapunti (trigger)."""
import json, os, time
import database as db, settings
from shared import regole, ruoli_core
from handlers import tagli as T, dpe as D, cambi_ruolo as CR, ruoli_rs as RS, dieci_giorni as DG
db.init_db(); db.migrate_db()
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
P = os.environ["SETTINGS_PATH"]
originale = json.load(open(P))


_giro = [0]


def scrivi(**k):
    d = {x: v for x, v in originale.items() if x not in regole.DEFAULT}
    d.update(k)
    json.dump(d, open(P, "w"))
    _giro[0] += 1
    os.utime(P, (time.time() + 10 * _giro[0],) * 2)   # mtime sempre nuovo, anche nello stesso secondo


# senza le chiavi nuove: i default del regolamento 2026-27
scrivi()
ok({k: regole.valore(k) for k in regole.DEFAULT} == regole.DEFAULT, "chiavi mancanti in settings.json: valgono i default (regolamento 2026-27)")
base = ["PG", "SG", "PG", "SG", "SF", "PF", "SF", "PF", "C", "C"]
ok(ruoli_core.deficit_minimo(base, []) == 0 and D._importo_dpe(5) == 3, "default: minimi 4/4/2, DPE −25% (Klay 5 → 3)")

# tutte cambiate
scrivi(roster_min_guardie=5, roster_min_ali=3, roster_min_centri=1, ore_comunicazione_ruolo=24,
       giorni_riacquisto_ruolo=30, max_cambi_ruolo_ordinari=3, giorni_erminio=7, giorni_saedro=5,
       max_tagli_gratuiti=1, giorni_10day=7, riduzione_dpe_percento=50, giocatori_panchina=4,
       bonus_casa=2, bonus_casa_playoff=4, scarto_minimo=3, pesi_fantapunti={"pts": 1})
ok(ruoli_core.deficit_minimo(base, []) == 1 and ruoli_core.deficit_minimo(["PG", "SG", "PG", "SG", "SG", "SF", "PF", "PF", "C"], []) == 0,
   "minimi per ruolo letti da settings.json (5 G, 3 F, 1 C), prima erano fissi nel codice")
ok((settings.min_guardie(), settings.min_ali(), settings.min_centri(), settings.ore_comunicazione_ruolo()) == (5, 3, 1, 24),
   "settings.py legge gli stessi valori")
ok((regole.ore_dichiarazione_ruolo(), regole.giorni_riacquisto_ruolo()) == (24, 30), "ore per dichiarare il ruolo e giorni del riacquisto")
ok((regole.max_cambi_ordinari(), regole.giorni_erminio(), regole.giorni_saedro()) == (3, 7, 5), "cambi ruolo, Erminio, Saedro")
ok(regole.max_tagli_gratuiti() == 1 and regole.giorni_10day() == 7, "tagli gratuiti e durata del 10-day")
ok(D._importo_dpe(5) == 2 and D._importo_dpe(10) == 5, "riduzione della DPE (50%: 5 → 2, arrotondata per eccesso)")
ok((regole.giocatori_panchina(), regole.bonus_casa(), regole.bonus_casa(playoff=True), regole.scarto_minimo()) == (4, 2, 4, 3),
   "panchina, bonus casa, scarto minimo")
ok(regole.pesi_fantapunti()["pts"] == 1 and regole.pesi_fantapunti()["ast"] == 2, "pesi: quelli scritti cambiano, gli altri restano ai default")

# conversione del DB di produzione: fantamedia colonna generata coi pesi fissi (bref_schema.sql) → trigger
db._q("DROP TRIGGER IF EXISTS bref_fantamedia ON bref_stats")
db._q("ALTER TABLE bref_stats DROP COLUMN fantamedia")
db._q("""ALTER TABLE bref_stats ADD COLUMN fantamedia NUMERIC(6,2) GENERATED ALWAYS AS (
           fga*(-0.5) + fgm*1 + ftm*1 + fta*(-0.75) + fg3m*1.5 + pts*0.5 + orb*2 + drb*1.25 + ast*2 + stl*2 + blk*2 + tov*(-2)) STORED""")
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Prova Vecchia'")
db._q("INSERT INTO bref_stats (stagione, nome_bref, pts, ast, orb, drb, fg3m, fga, fgm, fta, ftm, stl, blk, tov) "
      "VALUES ('2099', 'Prova Vecchia', 20, 5, 2, 6, 2, 15, 8, 5, 4, 1, 1, 3)")
scrivi()
db.migrate_db()
col = db._q("SELECT is_generated FROM information_schema.columns WHERE table_name = 'bref_stats' AND column_name = 'fantamedia'", one=True)
ok(col["is_generated"] == "NEVER" and float(db._qval("SELECT fantamedia FROM bref_stats WHERE nome_bref = 'Prova Vecchia'")) == 33.25,
   "avvio del bot: colonna generata convertita, valori già presenti invariati (33,25)")
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Prova Vecchia'")
scrivi(roster_min_guardie=5, roster_min_ali=3, roster_min_centri=1, ore_comunicazione_ruolo=24,
       giorni_riacquisto_ruolo=30, max_cambi_ruolo_ordinari=3, giorni_erminio=7, giorni_saedro=5,
       max_tagli_gratuiti=1, giorni_10day=7, riduzione_dpe_percento=50, giocatori_panchina=4,
       bonus_casa=2, bonus_casa_playoff=4, scarto_minimo=3, pesi_fantapunti={"pts": 1})

# valori storti nel file: mai un errore, il default (e un avviso nel log)
scrivi(bonus_casa="4,5", scarto_minimo="boh", max_tagli_gratuiti=True, giorni_10day="inf",
       pesi_fantapunti={"pts": "1", "xyz": 3, "ast": "a"})
ok((regole.bonus_casa(), regole.scarto_minimo(), regole.max_tagli_gratuiti(), regole.giorni_10day()) == (4.5, 5, 3, 10)
   and regole.pesi_fantapunti()["pts"] == 1 and regole.pesi_fantapunti()["ast"] == 2 and "xyz" not in regole.pesi_fantapunti(),
   "valori storti nel file: numeri come testo letti, il resto ai default, statistiche sconosciute ignorate")
open(P, "w").write("{rotto")
_giro[0] += 1; os.utime(P, (time.time() + 10 * _giro[0],) * 2)
ok(regole.bonus_casa() == 4.5, "file illeggibile: l'ultima lettura buona, non i default")
scrivi(roster_min_guardie=5, roster_min_ali=3, roster_min_centri=1, ore_comunicazione_ruolo=24,
       giorni_riacquisto_ruolo=30, max_cambi_ruolo_ordinari=3, giorni_erminio=7, giorni_saedro=5,
       max_tagli_gratuiti=1, giorni_10day=7, riduzione_dpe_percento=50, giocatori_panchina=4,
       bonus_casa=2, bonus_casa_playoff=4, scarto_minimo=3, pesi_fantapunti={"pts": 1})

# fantamedia di basketball-reference coi pesi nuovi (trigger)
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Prova Pesi'")
riga = dict(pts=20, ast=5, orb=2, drb=6, fg3m=2, fga=15, fgm=8, fta=5, ftm=4, stl=1, blk=1, tov=3)
ins = """INSERT INTO bref_stats (stagione, nome_bref, pts, ast, orb, drb, fg3m, fga, fgm, fta, ftm, stl, blk, tov)
         VALUES ('2099', 'Prova Pesi', %(pts)s, %(ast)s, %(orb)s, %(drb)s, %(fg3m)s, %(fga)s, %(fgm)s, %(fta)s, %(ftm)s, %(stl)s, %(blk)s, %(tov)s)"""
fm = lambda: float(db._qval("SELECT fantamedia FROM bref_stats WHERE nome_bref = 'Prova Pesi'"))
db._q(ins, riga)
vecchia = fm()
ok(abs(vecchia - 33.25) < 0.01, f"bref: fantamedia coi pesi dell'avvio del bot ({vecchia})")
regole.allinea_bref(db._q)
db._q("UPDATE bref_stats SET stagione = stagione WHERE stagione = '2099'")
ok(abs(fm() - 43.25) < 0.01, f"bref: trigger riscritto coi pesi nuovi e righe ricalcolate (punto +1: {fm()})")
col = db._q("SELECT is_generated FROM information_schema.columns WHERE table_name = 'bref_stats' AND column_name = 'fantamedia'", one=True)
ok(col["is_generated"] == "NEVER", "bref_stats.fantamedia non è più una colonna generata coi pesi fissi")
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Prova Pesi'")

# di nuovo i default
scrivi()
regole.allinea_bref(db._q)
db._q(ins, riga)
ok(abs(fm() - 33.25) < 0.01, "di nuovo i default: fantamedia come il regolamento")
db._q("DELETE FROM bref_stats WHERE nome_bref = 'Prova Pesi'")
json.dump(originale, open(P, "w"))

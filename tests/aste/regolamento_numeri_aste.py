import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v3.13.0 / aste v63: i numeri del regolamento (versione dell'11/10/2026) che usa il bot aste,
scritti qui a mano: anni minimi, tempi, soglie del pareggio RFA. Lo specchietto completo è in
docs/regolamento_e_codice.md."""
import settings
from handlers import firma_comune as F
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
s = settings.get()

ok(s["durata_asta_ore"] == 18 and s["rilancio_minimo"] == 1, "l'asta chiude 18 ore dopo l'ultimo rilancio, rilanci di almeno 1M (niente decimali)")
ok(s["timeout_firma_fa_ore"] == 48, "FA: 48 ore per scegliere anni e ruolo, poi 3 anni e ruolo a caso")
ok(s["timeout_firma_rfa_ore"] == 12 and s["timeout_pareggio_ore"] == 24,
   "RFA: 12 ore al vincitore per gli anni, 24 ore dalla fine dell'asta al proprietario per pareggiare")
ok([F.anni_minimi(x) for x in (1, 19, 20, 34, 35, 50)] == [1, 1, 2, 2, 3, 3],
   "anni minimi: da 20M x2, da 35M x3 (anche gli anni d'ufficio dell'RFA: 1, 2, 3)")
ok([F.soglia_pareggio(v) for v in (1, 20, 21, 30, 34, 35, 50, 71)] == [1, 1, 7, 10, 11, 17, 25, 35],
   "pareggio RFA: fino a 20M qualsiasi offerta; 21–34M almeno ⌊1/3⌋ del vecchio; da 35M almeno ⌊1/2⌋")
ok(F.importo_minimo_pareggio(5, 30) == 10 and F.importo_minimo_pareggio(15, 30) == 15 and F.importo_minimo_pareggio(3, 12) == 3,
   "per pareggiare: l'offerta del vincitore, ma mai sotto la soglia della fascia")
valido = lambda importo, anni: F._valida_anni(importo, anni) is None     # None = va bene, se no il messaggio d'errore
ok(valido(20, 2) and not valido(20, 1) and valido(35, 3) and not valido(35, 2) and valido(1, 3) and not valido(1, 4),
   "anni da 1 a 3, con i minimi per importo")

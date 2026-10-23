import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))); import guardia  # noqa: E402,F401  — blocca le prove sul server (TRUNCATE)
"""v6.2.1 (Luca, 20/10): le date nei comandi in un formato solo e tollerante (shared/date_comandi):
- / . come separatori, anno a 4 o a 2 cifre (con 2 cifre sempre GG/MM/AA), oppure AAAA-MM-GG."""
from datetime import date, datetime, time
from shared.date_comandi import leggi_data as L, leggi_data_ora as LO
ok = lambda c, m: print(("✅" if c else "❌ FAIL"), m)
D = date(2026, 10, 20)
ok(all(L(x) == D for x in ("2026-10-20", "2026/10/20", "2026.10.20", "20/10/2026", "20-10-2026", "20.10.2026", "20/10/26", "20-10-26")),
   "tutti i formati della stessa data")
ok(L("1/2/27") == date(2027, 2, 1) and L("31/02/2026") is None and L("20/10") is None and L("ciao") is None,
   "giorno e mese a una cifra; date impossibili o incomplete: None")
ok(LO("2026-11-15T20:00") == datetime(2026, 11, 15, 20, 0) and LO("15/11/26 20:00") == datetime(2026, 11, 15, 20, 0)
   and LO("15/11/26", time(23, 59)) == datetime(2026, 11, 15, 23, 59) and LO("15/11/26") is None, "data e ora")
from handlers import nascite as N
ok(N._parse_riga("Ja Morant 10/08/99") == ("Ja Morant", date(1999, 8, 10)) and N._parse_riga("Ja Morant 1999-08-10")[1] == date(1999, 8, 10)
   and N._parse_riga("Ja Morant 10.08.1999")[1] == date(1999, 8, 10), "date di nascita: tutti i formati, l'anno a 2 cifre nel Novecento")

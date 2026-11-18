# Mockup da fare (cartella temporanea)

Mockup approvati o in bozza per cose non ancora fatte, tenuti qui per non perderli. Si cancella quando sono
diventati codice (`shared/` o il bot che li usa). I dati sono finti; il disegno è Typst come le altre immagini.

| Cartella | Cosa | Stato |
|---|---|---|
| `lottery/` | Odds della lottery a fine regular season: le 12 della lottery con la % di ogni pick, le 13ª–24ª già decise, chi ha le pick scambiate | approvato il 18/11 |
| `draft/` | Tabellone del draft in stile NBA, in verticale, un'immagine per giro (due colonne da 12 o tre da 8) | bozza del 18/11: da decidere colonne e regole delle chiamate |

Per rifare le anteprime: `python3 lottery/dati.py lottery/anteprima.png` e `python3 draft/dati.py` (serve il
pacchetto `typst` di Python, come per i bot). Le decisioni prese su questi mockup sono in MIGRATION.md, sezione Da fare
(draft e lottery).

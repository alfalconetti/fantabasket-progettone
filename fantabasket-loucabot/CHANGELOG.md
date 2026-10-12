# Changelog — loucabot

## v1 (2026-10-12)

Primo rilascio: il calendario.

- Import del calendario della stagione da CSV (`/importa_calendario`, admin): giornate con le date, partite con casa e trasferta, squadre riconosciute per nome, squadre a media scritte nel file
- Partite NBA da ESPN (fonte pubblica, senza chiave): tutta la stagione con `/nba_sync`, poi ogni mattina i giorni vicini per accorgersi di rinvii e spostamenti
- Per ogni giornata: scadenza della formazione (la prima partita NBA), squadre NBA senza partite (a media), confronto con le note del file; avviso al gruppo admin se cambia qualcosa nelle giornate dei prossimi giorni
- `/calendario` (la tua giornata, l'avversario, casa o trasferta, la scadenza, le prossime), `/giornata [N]`, `/calendario_check` (admin)

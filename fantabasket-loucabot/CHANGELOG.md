# Changelog — loucabot

## v1 (2026-10-12)

Primo rilascio: il calendario.

- Import del calendario della stagione da CSV (`/importa_calendario`, admin): giornate con le date, partite con casa e trasferta, squadre riconosciute per nome, squadre a media scritte nel file
- Partite NBA da ESPN (fonte pubblica, senza chiave): tutta la stagione con `/nba_sync`, poi ogni mattina i giorni vicini per accorgersi di rinvii e spostamenti
- Per ogni giornata: scadenza della formazione (la prima partita NBA), squadre NBA senza partite (a media), confronto con le note del file; avviso al gruppo admin se cambia qualcosa nelle giornate dei prossimi giorni
- `/calendario` (la tua giornata, l'avversario, casa o trasferta, la scadenza, le prossime), `/giornata [N]`, `/calendario_check` (admin)

## v2 (2026-10-12)

- Le partite della NBA Cup con le squadre ancora da decidere (su ESPN "TBD") non contano più come una 31ª squadra: TBD non finiva più tra le squadre a media di ogni giornata. Le partite restano e contano per la scadenza della formazione. Contano solo le 30 squadre NBA; una sigla sconosciuta diventa TBD

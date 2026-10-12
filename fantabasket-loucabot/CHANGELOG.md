# Changelog — loucabot

## v1 (2026-10-12)

Primo rilascio: il calendario.

- Import del calendario della stagione da CSV (`/importa_calendario`, admin): giornate con le date, partite con casa e trasferta, squadre riconosciute per nome, squadre a media scritte nel file
- Partite NBA da ESPN (fonte pubblica, senza chiave): tutta la stagione con `/nba_sync`, poi ogni mattina i giorni vicini per accorgersi di rinvii e spostamenti
- Per ogni giornata: scadenza della formazione (la prima partita NBA), squadre NBA senza partite (a media), confronto con le note del file; avviso al gruppo admin se cambia qualcosa nelle giornate dei prossimi giorni
- `/calendario` (la tua giornata, l'avversario, casa o trasferta, la scadenza, le prossime), `/giornata [N]`, `/calendario_check` (admin)

## v2 (2026-10-12)

- Le partite della NBA Cup con le squadre ancora da decidere (su ESPN "TBD") non contano più come una 31ª squadra: TBD non finiva più tra le squadre a media di ogni giornata. Le partite restano e contano per la scadenza della formazione. Contano solo le 30 squadre NBA; una sigla sconosciuta diventa TBD

## v3 (2026-10-12)

- Canale log suo: `log_channel_id_louca` in `globals.json` (senza, quello del bot principale). Ci vanno avvio, errori, ogni import del calendario (chi, quante giornate e partite, differenze con le partite NBA), ogni `/nba_sync` (chi, giorni, partite, giorni non scaricati, cambi) e la sincronizzazione delle 8:30 (anche quando non cambia niente, così si vede che gira). Al gruppo admin restano solo i cambi di scadenze e squadre a media

## v4 (2026-10-12)

Il calcolo dei fantapunti.
- Tabellini da ESPN a partita finita (sync delle 8:30 e `/tabellini`), con statistiche e fantapunti del regolamento per giocatore (`nba_tabellini`). Formula verificata sul vecchio foglio (17/01/2026: 141 righe su 141 uguali; l'unica differenza era un errore del foglio, che aveva dato i punti di Jaylen Brown a Mamukelashvili)
- Foto degli infortunati alle 8:30, 17:30 e 23:30 (`nba_infortuni`)
- Abbinamento dei giocatori con l'id ESPN (`lega_espn`): automatico sui nomi, `/espn_giocatori`, `/espn_mancanti`, `/espn_abbina`
- `calcolo.py`: punteggio del giocatore nella giornata (partite, media, zero), della squadra con la FADD, esito con bonus casa e supplementari
- `/fantapunti [N]`: i fantapunti della giornata dei giocatori a roster, per squadra

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

## v5 (2026-10-12)

- Id e nome ESPN nell'anagrafica (`giocatori.espn_id`, `nome_espn`, deciso con Luca) invece della tabella `lega_espn`: all'avvio gli abbinamenti già fatti vengono copiati e la tabella eliminata. È l'unica cosa che loucabot scrive fuori dalle sue tabelle

## v6 (2026-10-12)

- Menu `/` per scope come negli altri bot (`comandi.py`): nei gruppi calendario e giornata, in privato anche la guida, agli admin (in privato e nel gruppo admin) i comandi admin, al dev quelli dev
- Documentazione a più livelli: `docs/guida_gm.md`, `guida_admin.md`, `guida_dev.md`, inviate come file da `/guida`, `/guida_admin`, `/guida_dev`; `/start` con i comandi in breve
- Comandi dev: `/dev`, `/dev_version`, `/job_status`

## v7 (2026-10-13)

- Il calendario sul foglio Google Calendario (stesso file del Roster), tramite gas-router (`/gas/calendario`) e la nuova azione `calendario` dello script (`gas/calendario.gs`): all'import il CSV si conserva tale e quale (`lega_calendario_csv`) come mappa delle righe del foglio; il bot scrive le intestazioni con le squadre a media calcolate e i punteggi in B e D (regolamentari, supplementari subito sotto) da `lega_risultati` (nuova, si riempirà con la convalida delle giornate). Lo script trova ogni giornata da "Week N" nella colonna A e scrive solo le celle che cambiano: formattazione, celle unite, nomi e valori scritti a mano senza risultato non si toccano (provato con node su un foglio simulato)
- Quando: all'import, quando cambiano le squadre a media (sync delle 8:30), `/calendario_foglio`

## v8 (2026-10-13)

- Foglio Calendario: a ogni aggiornamento si ricarica tutta la pagina, colonne A:E (richiesta di Luca), invece di scrivere solo le celle che cambiano: lo script svuota i valori di A:E (formattazione, celle unite e altre colonne restano) e scrive il calendario con le squadre a media calcolate e i punteggi. Da sincronizzare anche dopo ogni giornata convalidata

## v9 (2026-10-13)

- Nei log niente chiamate all'API di Telegram (anche `httpcore` a WARNING, oltre a `httpx`)

## v10 (2026-10-13)

- Comandi dev: `/dev_giornata [N]` (stato di una giornata: date, scadenza, squadre a media, partite NBA e tabellini scaricati, foto infortuni, risultati), `/dev_log` (ultime righe di log del bot), `/dev_pg` (versione e risposta di PostgreSQL), `/reboot` (riavvio del container). Menu dev e `/dev` aggiornati
- Guide: sezione "Comandi dev" nella guida dev, `/start` e `/guida` nella guida GM; tolti i riferimenti superati a "quintetti e panchine in un bot a parte"

## v11 (2026-10-13)

- Error handler comune con IPanchinari (`shared/dev_comune.py`): "Message is not modified" non arriva più sul canale log, gli errori di rete sì (non al dev), gli errori veri dicono chi e quale bottone o comando

## v12 (2026-10-13)

- **Snapshot** degli infortunati ESPN (prima "foto"): ogni 4 ore anche di notte (0:30, 4:30, 8:30, 12:30, 16:30, 20:30) e 30 minuti prima della prima partita NBA del giorno, per prendere i report che escono subito prima delle partite. Non si sostituiscono più: si tengono tutti quelli dell'ultima settimana; per i giorni più vecchi resta solo quello che conta per il calcolo (l'ultimo prima della prima partita del giorno). Il più recente è lo stato che IPanchinari mostra accanto ai giocatori
- `/dev_giornata` conta gli snapshot di ogni giorno
- Snapshot solo dai ruoli dell'offseason ai playoff (`offseason-ruoli`, `regular-season-fa`, `regular-season-deadline`, `playoff`); nelle altre fasi i job non scaricano niente
- **`/set_valid_status GIOCATORE N`** (admin): lo status di un giocatore che vale per il calcolo della giornata N, scelto coi bottoni tra quelli catturati dagli snapshot (con ★ quello che conterebbe); vince sugli snapshot per la media a 0 e per la FADD, "↩️ Torna agli snapshot" annulla, tutto sul canale log
- Calcolo (deciso con Luca il 13/10): uno 0 con 0 minuti non fa media, uno 0 con dei minuti sì (anche nella media della stagione); FADD anche per il titolare indisponibile tutta la giornata la cui squadra non gioca; sul foglio Calendario e in `lega_risultati.supp_*` i soli punti dei supplementari

## v13 (2026-10-13)

- **Calcolo definitivo delle giornate** (`risultati.py`, `handlers_risultati.py`): alle 7:45 del giorno dopo l'ultima notte, coi tabellini definitivi, dai quintetti congelati e dalle panchine di IPanchinari. Proposta al gruppo admin (risultati, FADD, avvisi: panchina mancante → senza supplementari, quintetto incompleto, giocatori senza id ESPN) con ✅ Convalida e 🔄 Ricalcola
- **Tab «Calcolo GN»** sul foglio di controllo del calcolo (via gas-router `/gas/calcolo`, `gas/calcolo.gs`): una riga per giocatore coi fantapunti di ogni notte, media, status, punteggio, in campo, ordine dei supplementari; totali, supplementari e vincitore come formule che rifanno i conti del bot (provato: il foglio ricalcolato dà gli stessi numeri). Riquadro dei risultati in cima
- **Convalida**: risultati in `lega_risultati` e foglio Calendario aggiornato (sotto la partita i soli punti dei supplementari). **`/ricalcola N`** e 🔄: riscarica i tabellini della giornata, ricalcola, riscrive il tab, proposta nuova (quella vecchia perde i bottoni)
- **Controllo delle 10:00**: riscarica i tabellini delle giornate calcolate da poco o da convalidare; se ESPN ne ha cambiato uno di un giocatore schierato, avviso al gruppo admin con le differenze e 🔄 Ricalcola

## v14 (2026-10-13)

- `/dev_prova_calcolo GG/MM/AAAA GG/MM/AAAA` (dev): prova del calcolo prima dell'inizio della stagione, con gli accoppiamenti della prossima giornata, i quintetti di adesso e le panchine già mandate, sulle partite NBA vere di giorni già giocati; scrive il tab «Calcolo G0» e manda la proposta solo al dev, senza salvare niente

## v15 (2026-10-13)

- Tab «Calcolo GN»: le formule si scrivono con `setFormulas` e non più con `setValues` (che le leggeva nella lingua del foglio: in italiano il separatore è ";" e davano tutte #ERROR!). Dopo la scrittura il gas controlla le celle: se una formula dà #ERROR! le riscrive col ";" e ricontrolla; se restano errori, la proposta al gruppo admin lo dice

## v16 (2026-10-13)

- Tab «Calcolo GN»: niente più righe e colonne bloccate in alto e a sinistra (il foglio era inusabile); si sbloccano anche i tab già scritti, alla prossima scrittura

## v17 (2026-10-13)

- Medie arrotondate all'ottavo: la media delle notti della giornata e la media della stagione valgono solo ,00 ,13 ,25 ,38 ,50 ,63 ,75 ,88 dopo la virgola (prima a due decimali: uscivano 0,01 o 0,26). Lo stesso per totali e supplementari. Sul foglio di calcolo il punteggio è `ROUND(AVERAGE(notti)*8;0)/8`, provato con LibreOffice contro il bot. Nei messaggi la metà si scrive per eccesso (0,125 → 0,13)

## v18 (2026-10-14)

- **Punteggi live** sul canale principale: alla palla a due della prima partita della giornata un messaggio con tutte le partite (punteggi col bonus casa, chi è avanti, supplementari, giocatori in campo e da giocare), il calcolo vero sui tabellini live di ESPN; sotto "provvisori, li valuta e convalida un admin" e l'ora dell'ultimo aggiornamento. Si modifica ogni 10 minuti dalla prima partita di ogni notte fino alle 8 di mattina, poi una volta alle 10:05 dopo il controllo dei tabellini. ESPN in errore: giro saltato, nuovo tentativo dopo 20 minuti, riga sul canale log
- Alle 10:05, a giornata in corso, il controllo della notte appena finita: riscarica tutte le sue partite e, se ESPN ha cambiato il tabellino di un giocatore schierato, una riga sul canale log con le differenze
- `/live` (admin) aggiorna subito; `/dev_prova_calcolo` manda anche l'anteprima del messaggio live
- I tabellini delle partite in corso si salvano senza segnare la partita come scaricata: il tabellino definitivo si riscarica sempre a partita finita
- Serve che loucabot sia amministratore del canale principale

## v19 (2026-10-14)

- Live: finché qualcuno (titolari o panchina) deve ancora giocare, il messaggio dice chi è avanti e di quanto, non più l'esito e i supplementari ipotetici (prima della prima partita usciva "ai supplementari (5)" con tutti a zero); quando hanno finito tutti, chi vince, supplementari compresi. L'anteprima di `/live` mostra anche i primi avvisi del calcolo (quintetti incompleti, panchine mancanti)
- **Squadra NBA di adesso dai roster ESPN**, aggiornati ogni mattina alle 8:30: per chi non ha ancora giocato nella giornata la squadra non è più quella del suo ultimo tabellino (per chi ha cambiato squadra d'estate o con una trade era quella vecchia). Conta per la media (squadra che non gioca), per la FADD e per il ⏳ del live

## v20 (2026-10-14)

- Anteprima di `/live`: tutti gli avvisi del calcolo, una riga per squadra ("quintetto vuoto", "manca SF", "senza panchina", giocatori senza id ESPN)
- Live: l'esito si scrive solo quando dei 10 in campo ne restano al massimo 4 da giocare (o in campo), sempre come "al momento vince …" (supplementari compresi); prima nessun esito, solo 🏀 e ⏳
- Live: se nessuna delle due squadre ha la panchina, "vince (nessuna delle due ha la panchina: niente supplementari)" invece di "ai supplementari (5)"

## v21 (2026-10-14)

- Anteprima del live (`/live` fuori giornata, `/dev_prova_calcolo`): se con gli avvisi del calcolo il messaggio supera il limite di Telegram, l'anteprima esce senza avvisi e gli avvisi vanno in un file `avvisi-GN.md` sul canale log (prima: "Message is too long")

## v22 (2026-10-14)

- Live: con il quintetto di una squadra vuoto (nessun giocatore) niente esito, ma "⚠️ quintetto vuoto: SQUADRA" (prima, con tutti a zero, il regolamento dava vinta la trasferta: scarto sotto 5, niente panchine)


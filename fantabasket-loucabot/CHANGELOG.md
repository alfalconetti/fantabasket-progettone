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

## v23 (2026-10-14)

- FADD durante la giornata (live, anteprime): un titolare a zero la cui squadra NBA deve ancora giocare non si valuta finché non ha giocato (prima si guardava tutta la giornata come se non giocasse); e l'avviso "manca lo snapshot degli infortunati" vale solo per i giorni passati: per oggi e i prossimi giorni lo snapshot arriverà (prima usciva per ogni giocatore nell'anteprima prima della giornata). Il calcolo delle 7:45, a giornata finita, è come prima

## v24 (2026-10-14)

- **`/dev_prova_live [GG/MM/AAAA …]`** (dev): il live vero su notti vere, anche di preseason (che il calcolo ignora), con gli accoppiamenti della prossima giornata e i quintetti e le panchine di adesso: stessi orari (ogni 10 minuti dalla prima partita alle 8, poi alle 10:05), stesso calcolo e stesso messaggio, ma **solo al dev** e **niente nel database** (partite e tabellini restano in memoria). `/dev_prova_live stop` la ferma; finisce da sola dopo le 10:05 dell'ultimo giorno; un riavvio la ferma

## v25 (2026-10-14)

- I tabellini che mancano si ritentano solo per le partite della **stagione in corso** (ogni mattina alle 8:30, alle 7:45, `/tabellini`, `/ricalcola`): una partita vecchia senza tabellino su ESPN (es. Bulls–Hornets del 3/1/2026) non torna più ogni giorno. `/dev_prova_calcolo` scarica quelli dei giorni indicati
- Se un tabellino non si scarica, il log dice quale partita e perché ("NYK–SAS del 01/03/2026 (id: tabellino vuoto)")

## v26 (2026-10-16)

- **`/player NOME`** (tutti): squadra NBA di adesso e status degli infortunati, squadra del fantabasket con ruolo e contratto (o svincolato), partite e media dei fantapunti della stagione (la stessa del calcolo), medie per partita e percentuali al tiro, ultime 5 partite
- `/giornata` (e `/calendario` per la propria partita): i risultati delle giornate convalidate, vincente in grassetto e supplementari; "in attesa della convalida" se calcolata ma non convalidata
- Sincronizzazione delle 8:30: il log dice **chi** è stato abbinato a ESPN (nome dell'anagrafica = nome ESPN); se un giocatore a roster non ha l'id ESPN (i suoi punti non contano), avviso ogni mattina al gruppo admin con /espn_mancanti

## v27 (2026-10-16)

- **`/classifica`** (immagine verticale): vittorie, sconfitte, punti fatti e subiti col bonus casa, media punti, striscia; solo giornate convalidate. Ordine: vittorie, poi scontri diretti tra le squadre a pari (classifica avulsa ricorsiva, solo V/S), poi media punti, poi differenza
- **`/classifica_full`** (immagine orizzontale, come file): in più media delle ultime 10, migliori di giornata, massimo e minimo, età media, record positivi e negativi subiti, coefficiente di variazione, fantapunti medi e % di partite giocate di roster e quintetto, età del quintetto, vantaggio e svantaggio medio senza supplementari, supplementari (vinti-persi)
- Immagini con Typst (pacchetto `typst` e font Liberation nell'immagine Docker di loucabot)

## v28 (2026-10-16)

- **`/classifica_conference`**: la generale filtrata per conference (ex aequo risolti sulla generale), con la posizione nella conference e quella generale. Le conference vengono da `config/divisions.json`, chiave nuova `"conference": {"Nome": ["A", "B", "C"], ...}` (le division di `team_div`)
- `/classifica_full`: record positivi/negativi subiti = volte in cui l'avversario ha fatto contro di te il **suo** massimo/minimo della stagione; le statistiche del quintetto sono sul **quintetto migliore possibile** per fantapunti (uno per ruolo dal roster di adesso), non su quello schierato

## v29 (2026-10-17)

- Un titolare messo anche in panchina (es. quintetto corretto dall'admin copiando Yahoo, con un giocatore che il GM aveva in panchina): in panchina conta **0**, tiene il suo posto (i supplementari non scalano) e non entra con la FADD. Avviso nel calcolo («titolare e anche in panchina»); sul foglio di controllo la sua riga di panchina è senza notti, quindi la formula dà 0 come il bot. Vale anche per il live

## v30 (2026-10-18)

- Titolare anche in panchina: **esce dalla panchina e gli altri scalano** (Luca, 18/10; nella v29 restava al suo posto con 0). Sul foglio di controllo la riga resta, senza notti né ordine dei supplementari
- `/calendario [N] [SQUADRA]`: anche per un'altra squadra (id, nome o inizio del nome, nome del GM, come /roster), numero e squadra in qualsiasi ordine
- **`/calendario_full [SQUADRA]`**: tutto il calendario di una squadra in un messaggio, coi risultati delle giornate convalidate (V/S, i suoi punti prima, supplementari) e il record

## v31 (2026-10-18)

- **Formazioni sul foglio di controllo alla scadenza**: quando IPanchinari congela la giornata, il tab «Calcolo GN» mostra subito gli schierati (per partita e squadra: quintetto, panchina in ordine, ruolo, squadra NBA; panchina non mandata, posti vuoti e titolari anche in panchina segnati), senza punteggi né formule. Si riscrive entro 5 minuti se un admin corregge formazioni o panchine (riga sul canale log); il calcolo della mattina lo sostituisce con quello completo. Tabella nuova `lega_foglio_formazioni` (creata all'avvio)

## v32 (2026-10-18)

- **Numeri del regolamento in `config/settings.json`** (`shared/regole.py`, chiave mancante = valore di oggi): pesi dei fantapunti (`pesi_fantapunti`), bonus casa (`bonus_casa`, `bonus_casa_playoff`), scarto minimo (`scarto_minimo`), giocatori in panchina e quindi supplementari (`giocatori_panchina`). Sul foglio di controllo le righe dei supplementari seguono `giocatori_panchina`
- **`/dev_ricalcola_fp [STAGIONE]`** (dev): dopo un cambio dei pesi (di solito alla riunione di giugno), ricalcola i fantapunti della stagione dalle statistiche già salvate (tabellini ESPN e medie di basketball-reference), senza riscaricare niente. I risultati già convalidati restano come sono (Luca, 18/10)

## v33 (2026-10-18)

- Dai roster ESPN delle 8:30 si salvano anche gli anni di esperienza NBA di ogni giocatore (`nba_atleti.esperienza`, 0 = esordiente; colonna nuova, creata all'avvio). Li usa il controllo dei dati del bot principale per riconoscere gli esordienti mai visti su basketball-reference

## v34 (2026-10-18)

- **Panchinario ceduto prima della scadenza** (trade, taglio, 10-day finito: dal registro dei movimenti del bot principale, `shared/rosa.py`): esce dalla panchina e gli altri scalano (Luca, 18/10), con l'avviso nella proposta di convalida («penalità: decidono gli admin»). Prima contava come se fosse ancora suo. Un **titolare** non più in squadra alla scadenza resta nel calcolo (fa fede Yahoo) ma c'è l'avviso per correggerlo con /quintetto_admin. Chi è ceduto dopo la scadenza conta per la vecchia squadra fino a fine giornata, come prima. Vale anche per il live; sul foglio di controllo e nel tab delle formazioni le righe hanno la nota

## v35 (2026-10-19)

- **Registro delle azioni** (main v6.0.0, `registro.py`): calendario importato, foglio Calendario riscritto, partite NBA risincronizzate, tabellini riscaricati, giocatori ESPN scaricati, abbinamenti ESPN, status validi messi e tolti, giornate calcolate e ricalcolate (dal job: sistema; da /ricalcola o 🔄: admin), giornate convalidate, fantapunti ricalcolati (dev) lasciano una riga nel registro condiviso con gli altri bot, con chi, veste e prima → dopo; si consulta dal bot principale. Sul canale log restano le righe di sempre, che avevano già il nome di chi (niente doppioni)
- Prova: controlli del registro in `louca_risultati`

## v36 (2026-10-20)

- Messaggio live: una riga vuota tra una partita e l'altra (Luca, 20/10)

## v37 (2026-10-23)

- **Dopo la convalida** (Luca, 23/10): sul canale principale il messaggio dei risultati definitivi (a una nuova convalida, dopo un ricalcolo, si modifica lo stesso) e il messaggio live si cancella; il live di quella giornata non si aggiorna più (`lega_live.chiuso`, `definitivo_id`)
- **Live, chi manca**: al posto di «⏳ da giocare 5–5», sotto ogni partita una riga per squadra «devono giocare N · devono rigiocare N (in ballo X)»: titolari che non hanno ancora una partita finita, titolari che ne hanno finita una e ne hanno un'altra, e le loro medie fantapunti per le partite che restano (`live.ancora_in_ballo`)
- `/risultati` come `/giornata`; una riga vuota tra una partita e l'altra in `/giornata` e nel report del calcolo al gruppo admin
- **Foglio di calcolo leggibile col tema scuro**: tutte le celle con lo sfondo bianco esplicito (prima le celle «normali» erano senza sfondo e nell'app col tema scuro diventavano scure, col testo blu e nero illeggibile)
- Orari dei job (calcolo, sync NBA, controllo dei tabellini, fine del live) da `orari` in settings.json

## v38 (2026-10-23)

- Live: «devono rigiocare N (finora X)», i punti già fatti da chi deve rigiocare al posto delle medie; date dei comandi dev da `shared/date_comandi`
- **`/notte [SQUADRA o GM] [DATA]`** (Luca, 21/10): gli schierati di una squadra (la propria di default) in una notte NBA (di default quella in corso o appena passata): partita, orario, fantapunti, in campo, DNP, infortuni; la formazione congelata della giornata, o il quintetto di adesso se non è ancora iniziata (`notte.py`)
- **Nuova convalida dopo un ricalcolo** (Luca, 23/10): si modifica il messaggio dei definitivi sul canale («aggiornati dopo il ricontrollo»); un messaggio in più, in risposta, solo se cambia chi vince una partita (`lega_live.esiti`)

## v39 (2026-10-23)

- **`/partita`** (Luca, 21 e 23/10): una sfida come immagine Typst verticale in tinte viola (`partita.py`, `partita.typ`): tabellone coi loghi, punteggi, supplementari e stato (da giocare, in corso, calcolata, convalidata); per ogni squadra quintetto e panchina, una colonna per notte con la data (fantapunti, DNP, «vs/@» se deve giocare, vuota se non gioca) e la colonna «Conta» (media delle partite della giornata, MEDIA, ↓/↑ FADD, S1… supplementari); in fondo FADD, medie, supplementari e avvisi del calcolo. Argomenti: niente (la propria squadra e la giornata in corso, la stessa fino alla convalida), SQUADRA [GN], SQUADRA - SQUADRA (più sfide: bottoni)
- `/partita` (Luca, 23/10): colonna **Media** (media fantapunti della stagione all'inizio della giornata, quella che vale se la squadra NBA non gioca); supplementari più grandi, centrati sotto il punteggio regolamentare; chi vince (giornata calcolata o convalidata) in grassetto, l'altra squadra no
- `/partita` su una giornata convalidata: in testa il risultato salvato (quello ufficiale); se il ricalcolo di oggi darebbe altro, la prima nota lo dice. **Squadra NBA nelle giornate vecchie**: per una giornata finita da più di una settimana il calcolo (e quindi un ricalcolo o `/partita` mesi dopo) non usa più i roster ESPN di adesso per chi non ha giocato, ma l'ultimo tabellino prima della fine della giornata (dopo una trade NBA avrebbe preso la squadra nuova)
- `/partita` senza argomenti: dopo la convalida passa alla giornata nuova solo dalle 16 (`orari.partita_nuova`) del suo primo giorno, fino ad allora mostra quella appena finita (Luca, 23/10)
- `/partita`: i totali di ogni squadra in fondo alla tabella, sotto la colonna «Conta» (titolari, bonus casa, totale, supplementari), invece che in alto a destra (Luca, 23/10)
- `/partita`: le squadre NBA a media nella giornata in una fascia subito sotto il tabellone, invece che tra le note (Luca, 23/10)

## v40 (2026-10-23)

- **Titolare anche in panchina** (Luca, 23/10: «ricordavo male»): in panchina quella posizione vale 0 e gli altri **non** scalano (prima usciva dalla panchina e gli altri scalavano); niente FADD con lui e, nei supplementari, a quel giro la squadra prende 0. Lo stesso sul foglio di calcolo (la riga tiene il suo numero d'ordine, vale 0) e negli avvisi. I panchinari ceduti prima della scadenza restano come prima (fuori, gli altri scalano)
- `/partita`: il ruolo dei panchinari tra parentesi (quello della giornata), e il titolare anche in panchina con «0 ANCHE TITOLARE»

## v41 (2026-10-23)

- **`/player`** (Luca, 23/10): le posizioni eleggibili sempre; se firmato squadra, ruolo della stagione (o la dichiarazione aperta con la scadenza) e lo stato del contratto su una riga sua: importo × anni rimasti e fino a quale stagione (firmato quando, per quanti anni), rookie, 10-day, DPE di quest'anno, x0 (contratto finito: dichiarato RFA o dichiarabile); se svincolato, free agent o diritti rookie di quale squadra

## v42 (2026-10-23)

- **Foto dei giocatori da ESPN** (Luca, 23/10, `foto.py`): scaricate piano, solo nella notte americana (2–6 a New York), una al minuto, per i giocatori a roster (prima le mancanti, poi chi ha cambiato squadra, poi le più vecchie di 14 giorni); versione piccola dal combiner di ESPN; un 429 ferma tutto per 20 ore. In `config/foto` sul server: nel docker-compose una cartella in scrittura `./config/foto:/foto` (`FOTO_DIR`)
- **`/player` con la foto** quando c'è (didascalia; se il testo è lungo, foto e testo sotto); senza foto come prima, `/player` non scarica mai niente
- `/player`: la foto (520×380 dal combiner di ESPN, nitida sul telefono) composta con Typst su uno sfondo viola 640×420 col nome, la squadra NBA e quella del fantabasket (`foto_player.typ`): una PNG trasparente su Telegram può uscire su fondo nero e una foto piccola si vede sgranata

## v43 (2026-10-23)

- `/partita`: la foto ESPN di ogni giocatore in un tondo accanto al nome (ritagliata sulla faccia; senza foto le iniziali)
- Parole più chiare (Luca, 23/10): la colonna «Conta» di `/partita` è **«Punti effettivi»**; «a media» è **«prendono la media»** (`/partita`, `/calendario`, avvisi del calendario agli admin)

## v44 (2026-10-23)

- Injury report ogni mezz'ora nella prima sera di ogni giornata, dalle 19 (`orari.injury_fitti`) alla prima partita (`handlers_calcolo.job_injury_fitti`): IPanchinari avvisa i GM dei cambi. Una sola richiesta a ESPN ogni volta
- Ricerca delle squadre per una parola sola anche in `/partita`, `/notte`, `/calendario` (`shared/squadre.per_parole`)

## v45 (2026-10-23)

- **Foglio di controllo provvisorio** (`formazioni_foglio.job_parziale`, alle `orari.foglio_parziale`, 10:00): nelle giornate chiuse e non ancora calcolate, dopo almeno una notte, il tab «Calcolo GN» col calcolo fino alla notte appena finita (lo stesso del live: chi deve ancora giocare conta 0, la FADD a giornata finita), formule comprese, titolo PROVVISORIO su sfondo arancio chiaro. Prima scarica partite e tabellini delle notti passate. Il job delle formazioni, se un admin corregge dopo la prima notte, riscrive col calcolo provvisorio invece che con le sole formazioni

## v46 (2026-10-23)

- `/player`: sotto un contratto firmato nella prima stagione del bot (2026-27) la nota in corsivo che i contratti firmati prima risultano firmati quell'anno (`NOTA_FIRMA`, fino al 2028: `NOTA_FIRMA_FINO_AL`)

## v47 (2026-10-23)

- **Cambi di squadra NBA salvati** (`nba_movimenti`, per `/carriera` del bot principale): `db.salva_atleti` confronta i roster ESPN delle 8:30 con quelli del giorno prima e segna ogni cambio col giorno (da una squadra all'altra, di nuovo in un roster, fuori da tutti i roster)

## v48 (2026-10-23)

- `/player`: scadenza dei diritti rookie di una 2nd dalla regola (`player.scadenza_diritti`: 10 giorni prima della trade deadline della stagione dopo il draft, `trade_deadline` in globals), non più da `rookie.scadenza_diritti`

## v49 (2026-10-24)

- `/partita`: foto nel tondo meno ingrandita e un filo più in alto (altezza 24pt invece di 30); tondo e nome in una griglia centrata in verticale, uguale con la foto e con le iniziali

## v50 (2026-10-24)

- Controllo delle 10: premuto 🔄 Ricalcola sull'avviso, il bottone si toglie e il messaggio dice chi ha avviato il ricalcolo e quando (la proposta del calcolo no: quella la segna già superata il ricalcolo); «1 tabellino» e fantapunti formattati come altrove


## v51 (2026-10-24)

- **Calcolo delle 7:45**: prima di calcolare riscarica tutti i tabellini della giornata, anche quelli già presi dal live nella notte, come fanno già `/ricalcola` e il controllo delle 10. Una correzione di ESPN arrivata tra la fine della notte e le 7:45 entra subito nella proposta; se ce ne sono, una riga nel canale log (Luca, 24/10)

## v52 (2026-10-25)

- `/giornata` e `/risultati` senza numero seguono la regola di `/partita` (Luca, 25/10): la giornata finita resta fino alla convalida e poi fino alle 16 (`orari.partita_nuova`) del primo giorno della successiva, così la mattina si vedono i risultati appena convalidati invece delle partite della giornata nuova. La regola è in un posto solo (`calendario.da_mostrare`). `/calendario` resta com'era (la tua giornata in corso o la prossima)

## v53 (2026-10-25)

- **Live come immagine** (Luca, 23/10, mockup approvato; per la giornata 3): sul canale principale il tabellone Typst (`live.typ`) al posto del messaggio di testo, una scheda per partita in due colonne con loghi e punteggi, grassetto a chi è avanti, etichette con emoji e numero di titolari (🏀 in campo · ⏳ devono giocare · 🔁 devono rigiocare coi punti già fatti · ✅ finito · 📉 prendono media), «HANNO GIOCATO IN MENO DI 6» quando l'esito non si dà, «SI VA AI SUPPL.» coi punti dei supplementari, **legenda evidente** in fondo, sempre al plurale (Luca, 25/10). La foto si sostituisce ogni 10 minuti nello stesso messaggio (didascalia con giornata e ora); un live di testo di prima si cancella e lo rimpiazza una foto nuova
- Emoji dal font **Noto Color Emoji**, ora installato nel container (`fonts-noto-color-emoji` nel Dockerfile): se manca, una riga nel canale log
- **`/live_results [N]`**: il testo completo del live, anche in più messaggi; ora nel testo anche «📉 prendono media N–M»
- Anteprima agli admin, `/dev_prova_live` e proposta delle 7:45 restano in testo

## v54 (2026-10-26)

- **`/live` ripubblicava anche la giornata appena convalidata** (Luca, 26/10: aggiornata la G2, già convalidata, insieme alla G3 in corso). Le giornate col live chiuso dalla convalida ora restano fuori da `live.giornate_attive`, che usano sia `/live` sia il job. Prova in `louca_risultati`
- **`/player`** (Luca, 25/10): data di nascita con l'età; partite **saltate** nelle ultime partite (la squadra NBA ha giocato e lui non era nel tabellino), quelle di fila in una riga sola («dal 02/11 al 11/11: 10 partite saltate»), «non è entrato» resta a parte; nella stagione «N partite su M della squadra», «su M da quando è a NYK (dal 12/12)» per chi è arrivato a stagione in corso, «su M (BOS poi NYK)» per chi è stato scambiato. Per chi cambia squadra o firma a stagione in corso contano solo le partite da quando c'era (tabellini e movimenti dei roster ESPN)
- Chi prende la media: 📈 al posto di 📉, nel tabellone, nella legenda e nei testi (Luca, 26/10)
- `/player`: la **media della stagione prima** da Basketball-Reference, con le partite giocate (Luca, 26/10)
- **Live, timeout di Telegram** (Luca, 26/10, notte della G3): alle 2:15 la sostituzione della foto è andata in timeout e il bot ha cancellato il live e ne ha mandato uno nuovo, andato anch'esso in timeout (pubblicato ma senza saperne l'id: rimasto orfano); alle 2:35 un terzo. Ora un messaggio nuovo si fa solo se Telegram dice che quello di prima non si può modificare (testo di prima della v53, cancellato); con timeout o altri errori il messaggio resta e si salta il giro. Tempi più larghi per mandare la foto (60 s)

## v55 (2026-10-26)

- **Ricalcolo di una giornata già convalidata: si vede cosa cambia** (Luca, 26/10: un ricalcolo aveva cambiato una partita ai supplementari e nessun messaggio l'aveva detto). La proposta nuova ha in fondo «🔁 Rispetto ai risultati convalidati cambiano N partite» con punti, supplementari e ⚠️ vincitore di prima e di adesso, oppure «✅ Stessi risultati della convalida»; lo stesso nel messaggio di conferma della convalida. L'avviso sul canale quando cambia chi vince ora funziona anche per le giornate convalidate prima che il bot salvasse gli esiti

## v56 (2026-10-26)

- **Congelamento delle giornate** (regola votata dai GM il 26/10, proposta di Luca): il controllo delle 10 ricontrolla solo le **ultime 3 giornate finite** (con la 4 in corso la 1, la 2 e la 3; finita la 4, la 2, la 3 e la 4), convalidate o no; le più vecchie sono congelate e `/ricalcola` non le riscarica (ricalcola coi tabellini che hanno). Prima: le giornate da convalidare o calcolate negli ultimi 2 giorni, e ogni ricalcolo rimetteva la giornata nel controllo. Le correzioni fatte finora restano
- **`/congela N`**, **`/scongela N`** (la scelta a mano vale più della regola) e **`/congelamento`** (lo stato di tutte), admin
- **`/correggi_tabellino GIOCATORE GN VALORE [GG/MM]`** (admin): i fantapunti di una partita senza riscaricare; con più partite nella giornata chiede la data coi comandi già scritti; poi `/ricalcola N` e la convalida
- `/congela`, `/scongela` e le correzioni nel registro, nel canale log e sul canale principale

## v57 (2026-10-27)

- **Live più robusto con ESPN** (Luca, notte del 27/10: il live si fermava senza dire niente). ESPN ogni tanto risponde vuoto («Expecting value»): ora ogni richiesta si riprova fino a 3 volte (`nba._json`). Se il tabellone della notte non arriva lo stesso, giro saltato e nuovo tentativo dopo **10 minuti** (era 20), con una riga sul canale log **a ogni giro saltato** (prima una all'ora: i salti dopo il primo non si vedevano). Se manca il tabellino di una sola partita il tabellone si aggiorna con le altre e quella si riprova al giro dopo

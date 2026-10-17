# Guida admin — loucabot

Da admin in loucabot gestisci il calendario della stagione e controlli i punteggi. I comandi admin funzionano in privato e nel gruppo admin, e compaiono nel menu `/` solo lì.

Gli admin sono quelli di `admin_ids` in `globals.json`, gli stessi degli altri bot.

---

## Canali

- **Gruppo admin** (`admin_group_id`): qui arrivano solo i cambi che contano per la lega, cioè una scadenza che si sposta o le squadre a media di una giornata che cambiano. loucabot deve essere nel gruppo.
- **Canale principale** (`main_channel_id`, lo stesso del bot principale): il messaggio dei punteggi live di ogni giornata. **loucabot deve essere amministratore del canale** (con il permesso di pubblicare e modificare i messaggi).
- **Canale log** (`log_channel_id_louca` in `globals.json`; senza, quello del bot principale): la parte tecnica. Ci vanno avvio ed errori, ogni import del calendario, ogni `/nba_sync`, `/tabellini`, `/espn_giocatori`, ogni abbinamento a mano e la sincronizzazione delle 8:30, anche quando non cambia niente (così si vede che gira).

---

## Il calendario

**A inizio stagione:**

1. Manda il CSV del calendario come file, con didascalia `/importa_calendario`. Va bene anche rispondere con `/importa_calendario` al messaggio che contiene il file. Un nuovo import sostituisce il calendario di regular season della stagione, senza doppioni.
2. `/nba_sync`: scarica da ESPN tutte le partite NBA della stagione (qualche minuto).
3. `/calendario_check`: scadenza di ogni giornata e squadre a media, con il confronto tra quelle scritte nel CSV e quelle calcolate dalle partite NBA.

**Il CSV** è quello degli admin: per ogni giornata una riga `Week N gg/mm - gg/mm (media XXX,YYY)` e sotto le partite `Casa,,V,,Trasferta`. Le squadre si riconoscono solo per nome esatto (senza maiuscole e accenti) o per id, come in `teams.json`. Se un nome non c'è, il bot propone il più simile ma non importa niente. Controlli: giornate da 1 in ordine e senza sovrapposizioni, ogni squadra una volta per giornata.

**Squadre a media.** Vale il calcolo dalle partite NBA, che è quello che vedono i GM. Se `/calendario_check` mostra differenze, correggi le note nel CSV e reimportalo, così anche il calendario pubblicato torna giusto.

**Il foglio Google Calendario** (stesso file del Roster) lo ricarica il bot, tutto, nelle colonne A:E: all'import, quando cambiano le squadre a media, con `/calendario_foglio` e dopo ogni giornata convalidata. Scrive il calendario come nel CSV, con le squadre a media calcolate nelle intestazioni e i punteggi in B e D (regolamentari nella riga delle squadre, supplementari subito sotto). La formattazione, le celle unite e le altre colonne non si toccano; i valori di A:E invece sì: quello che si scrive lì a mano sparisce al primo aggiornamento.

**Ogni mattina alle 8:30** il bot riscarica le partite dei giorni vicini (da 3 giorni fa a 2 settimane avanti) e ricalcola. Se in una giornata non ancora finita cambiano la prima partita o le squadre a media, arriva un avviso al gruppo admin.

---

## Il calcolo della giornata

**Alla scadenza**, appena IPanchinari congela quintetti e panchine, nel tab **«Calcolo GN»** del foglio di controllo esce l'elenco degli schierati, per trasparenza verso i GM: per ogni partita, per ogni squadra, i 5 del quintetto e la panchina in ordine, col ruolo e la squadra NBA (panchina non mandata, posti vuoti e doppioni sono segnati). Niente punteggi né formule. Se un admin corregge una formazione o una panchina, il tab si riscrive entro 5 minuti (riga sul canale log). Il calcolo della mattina riscrive lo stesso tab per intero.

**Alle 7:45** del giorno dopo l'ultima notte della giornata il bot calcola da solo, coi tabellini definitivi: riscarica partite e tabellini, prende i quintetti congelati alla scadenza e le panchine da IPanchinari e applica le regole qui sotto. Poi:
- scrive il tab **«Calcolo GN»** del foglio di controllo del calcolo: una riga per giocatore coi fantapunti di ogni notte, la media della stagione, lo status di ogni notte, il punteggio, chi è in campo (FADD), l'ordine dei supplementari, e in cima il riquadro dei risultati. Punteggi, totali, supplementari e vincitore sono **formule** che rifanno i conti del bot: se tutto quadra sul foglio, quadra anche nel bot. I dati scritti dal bot sono in blu, le formule in nero, le righe della FADD in arancione;
- manda al gruppo admin la proposta: risultati, FADD, avvisi (panchina mancante → senza supplementari, quintetto incompleto, giocatori senza id ESPN), con **✅ Convalida** e **🔄 Ricalcola**.

Se a quell'ora la giornata non si può ancora calcolare (una partita non finita, un tabellino che manca, quintetti non congelati) lo dice sul canale log: quando è pronta, `/ricalcola N`.

**Controlli e correzioni.** Si correggono sempre dal bot, mai a mano sul foglio (il bot riscrive il tab a ogni ricalcolo):
- status di un giocatore: `/set_valid_status GIOCATORE N` (qui);
- quintetto della giornata: `/quintetto_admin SQUADRA GN` (IPanchinari);
- panchina della giornata: `/panchina_admin SQUADRA GN` (IPanchinari);
- fantapunti sbagliati (ESPN corregge un tabellino): il ricalcolo li riscarica.

Poi **🔄 Ricalcola** (o `/ricalcola N`): il bot riscarica i tabellini della giornata, ricalcola, riscrive il tab e manda una proposta nuova; quella vecchia perde i bottoni.

**✅ Convalida**: solo allora i risultati si salvano e il foglio **Calendario** si aggiorna (punti col bonus casa nella riga della partita, i soli punti dei supplementari nella riga sotto). Il bottone di una proposta superata non convalida niente.

**Alle 10:00** il bot riscarica i tabellini delle giornate calcolate da poco o ancora da convalidare: se ESPN ne ha corretto qualcuno di un giocatore schierato, avvisa il gruppo admin con le differenze e il bottone 🔄 Ricalcola. Vale anche per una giornata già convalidata: si ricalcola e si riconvalida.

**Dopo la convalida**, se scopri un errore: correggi e `/ricalcola N`; alla nuova convalida il Calendario si riscrive.

Il foglio di controllo è un file Google a parte (`CALCOLO_SPREADSHEET_ID` in `gas/globals.gs`; senza, il tab va nel file del Roster).

---

## I punteggi live

Alla palla a due della prima partita della giornata il bot pubblica sul canale principale un messaggio con tutte le partite della giornata: punteggio di casa e trasferta (bonus casa compreso) e, quando dei 10 in campo ne restano al massimo 4 da giocare, l'esito "al momento" (chi vince, coi supplementari se servono); con più di 4 ancora da giocare nessun esito. Accanto, tra i 5 in campo, quanti stanno giocando adesso (🏀) e quanti hanno ancora una partita della giornata, stanotte o nelle notti dopo (⏳). È il calcolo vero (medie, media della stagione, FADD, supplementari) sui tabellini live di ESPN. Sotto c'è scritto che sono **risultati provvisori, da valutare e convalidare da un admin**, e l'ora dell'ultimo aggiornamento.

- Si aggiorna (modificando lo stesso messaggio) **ogni 10 minuti** dalla prima partita di ogni notte della giornata **fino alle 8 di mattina**, poi **una volta alle 10:05**: è il controllo della notte appena finita a giornata in corso. Riscarica tutte le partite di quella notte (ESPN a volte riassegna le statistiche) e aggiorna il messaggio; se è cambiato il tabellino di un giocatore schierato, sul canale log arriva una riga con le differenze. Dopo l'ultima notte non riscarica: l'ha appena fatto il controllo del calcolo delle 10:00, che avvisa il gruppo admin.
- Formazioni: quelle congelate da IPanchinari alla scadenza (nei primi minuti, finché IPanchinari non chiude la giornata, i quintetti di quel momento).
- Se ESPN non risponde si salta il giro e si riprova dopo 20 minuti; sul canale log una riga (al massimo una all'ora).
- **`/live`**: aggiorna subito, senza aspettare i 10 minuti (se nessuna giornata è in corso, ti manda l'anteprima della prossima). Anche `/dev_prova_calcolo` manda l'anteprima del messaggio live.
- Fa fede sempre il calcolo delle 7:45 convalidato: il live è solo una stima.

---

## I punteggi

**Tabellini.** A partita finita il bot scarica da ESPN il tabellino e salva statistiche e fantapunti di ogni giocatore NBA. Lo fa alle 8:30; `/tabellini` lo fa subito, per le partite finite che ancora non ce l'hanno.

**Infortunati.** ESPN dà solo lo stato di adesso, quindi il bot ne salva uno snapshot (dai ruoli dell'offseason fino ai playoff; nelle altre fasi no) ogni 4 ore, anche di notte (0:30, 4:30, 8:30, 12:30, 16:30, 20:30), più uno 30 minuti prima della prima partita NBA del giorno (il report subito prima delle partite). Per il calcolo, di ogni giorno conta lo snapshot subito prima della prima partita; il più recente è lo stato che IPanchinari mostra accanto ai giocatori. Si tengono tutti gli snapshot dell'ultima settimana; per i giorni più vecchi resta solo quello che conta. Anche `/tabellini` ne salva uno. Servono per due regole:
- chi è in una squadra a media prende 0 invece della media se nello snapshot che conta di ogni giorno della giornata risulta indisponibile (stato diverso da Probable);
- la FADD (il panchinaro che entra al posto del titolare che non ha giocato): il titolare deve avere il tag in tutti i giorni in cui la sua squadra ha giocato, o in tutta la giornata se la sua squadra non ha giocato. La panchina scala e resta di 4: al quinto supplementare quella squadra aggiunge 0. Se manca lo snapshot di uno di quei giorni il bot non sostituisce e lo segnala: decide un admin.

**Giocatori e id ESPN.** Il calcolo collega i giocatori dell'anagrafica a ESPN con l'id ESPN, non col nome. L'abbinamento è automatico quando il nome è uguale (senza accenti, punteggiatura, Jr./III) e corrisponde a un solo giocatore.
- `/espn_giocatori` scarica i roster delle 30 squadre e abbina. Si rifà ogni tanto, per esempio dopo il mercato NBA.
- `/espn_mancanti` elenca i giocatori a roster nella lega senza id ESPN, con i nomi ESPN più simili.
- `/espn_abbina ID_GIOCATORE ID_ESPN` abbina a mano. L'id del giocatore è quello di `/espn_mancanti`; l'id ESPN è il numero nell'indirizzo della pagina del giocatore su espn.com (`…/player/_/id/4432174/cam-thomas`). Attenzione ai suggerimenti: sono solo nomi simili, non per forza giusti.

**`/set_valid_status GIOCATORE N`**: quando gli snapshot non tornano (un report arrivato tardi, un giocatore segnato Out che poi ha giocato, uno sparito dalla lista per sbaglio) decidi tu lo status che vale per il calcolo della giornata N. Il bot mostra tutti gli snapshot del giocatore in quella giornata, giorno per giorno, con ★ quello che conta, e un bottone per ogni stato catturato (Out, Questionable, sano…): quello che scegli vale per tutta la giornata, sia per la media a 0 sia per la FADD, al posto degli snapshot. "↩️ Torna agli snapshot" annulla. Ogni scelta finisce sul canale log. Gli snapshot dei giorni più vecchi di una settimana si riducono a uno per giorno: le correzioni conviene farle prima.

**`/fantapunti [N]`** mostra i fantapunti della giornata di tutti i giocatori a roster, divisi per squadra (📉 = ha preso la media). Serve per controllare il calcolo. Se è lungo arriva come file.

**Come si calcola** (regolamento, capitolo Partita):
- chi ha giocato una o più partite della giornata → media delle partite giocate (uno 0 con 0 minuti non conta, uno 0 con dei minuti sì), arrotondata all'ottavo: dopo la virgola solo ,00 ,13 ,25 ,38 ,50 ,63 ,75 ,88 (sul foglio `ROUND(media*8)/8`; lo stesso per la media della stagione);
- chi non ha giocato, se la sua squadra NBA non aveva partite (o solo partite rinviate) → la sua media della stagione, 0 se indisponibile;
- chi non ha giocato mentre la sua squadra sì → 0;
- squadra: somma dei 5 titolari, con la FADD; vince chi ha almeno 5 punti di scarto, bonus casa compreso (3, nei playoff 5); altrimenti supplementari con i panchinari in ordine; pari fino al decimo uomo → vince la trasferta. Sul Calendario: punti col bonus casa, e sotto i soli punti dei supplementari.

Restano agli admin le 72 ore di attesa per le partite rinviate e le penalità.

---

## Comandi

| Comando | Cosa fa |
|---|---|
| `/importa_calendario` | importa il CSV (didascalia del file, o in risposta al file) |
| `/calendario_check` | scadenze e squadre a media, confronto col CSV |
| `/nba_sync` | riscarica le partite NBA della stagione |
| `/calendario_foglio` | ricarica il foglio Google Calendario (A:E) |
| `/tabellini` | tabellini mancanti e snapshot degli infortunati |
| `/espn_giocatori` | roster NBA da ESPN e abbinamento automatico |
| `/espn_mancanti` | giocatori a roster senza id ESPN |
| `/espn_abbina ID_GIOCATORE ID_ESPN` | abbinamento a mano |
| `/ricalcola N` | riscarica i tabellini della giornata N, ricalcola, riscrive il tab «Calcolo GN» e ripropone la convalida |
| `/live` | aggiorna subito il messaggio live della giornata in corso (o l'anteprima, se non è iniziata) |
| `/fantapunti [N]` | fantapunti della giornata, per squadra |
| `/set_valid_status GIOCATORE N` | lo status di un giocatore che vale per il calcolo della giornata N, scelto tra quelli degli snapshot |
| `/calendario [N]`, `/giornata [N]` | come i GM |
| `/guida_admin` | questa guida |

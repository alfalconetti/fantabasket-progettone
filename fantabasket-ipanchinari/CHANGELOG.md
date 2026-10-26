# Changelog — IPanchinari

## v1 (2026-10-13)

Primo rilascio: panchine e quintetti.
- **Panchine da messaggio**: il GM manda al bot, in privato, il messaggio di sempre (righe dei panchinari in ordine, soprannomi compresi, titolo facoltativo sopra separato da una riga vuota). Abbinamento tollerante con i giocatori della squadra (parole del nome, cognome che vale doppio, errori di battitura, nomi col trattino, iniziali come SGA o KAT, solo nome di battesimo se è di uno solo); le righe dubbie si scelgono coi bottoni e diventano alias della squadra. Anteprima al GM coi nomi veri, poi sul canale Panchinari solo le righe come le ha scritte lui. Vale per la prossima giornata aperta; rimandata esce come aggiornamento in risposta alla precedente. Bloccano: giocatori non della squadra, doppioni, scadenza (anche se passa durante la conferma). Un panchinaro che nel quintetto del bot è titolare è solo segnalato (al GM e sul canale log): per il quintetto fa fede Yahoo
- **Quintetti**: uno per squadra, un giocatore per ruolo nel suo ruolo di roster, restano finché si cambiano. `/quintetto_admin SQUADRA` con 5 righe (anche a giornata in corso: aggiorna anche la formazione della giornata; con `G5` corregge solo quella della giornata 5), `/quintetti_import` per tutte le squadre (nomi esatti), `/quintetto` per i GM coi bottoni
- **Promemoria** alle 8 (Roma) dell'ultimo giorno prima della prima partita: quintetto, partite di ogni titolare nella giornata, Confermo / Modifico validi fino alla scadenza. **Riepilogo** agli admin 2 ore prima (conferme, panchine, incompatibilità; `/stato` quando si vuole). **Chiusura** alla scadenza: quintetti congelati in `ipa_formazioni` per il calcolo, panchine mancanti al gruppo admin
- `/panchina_admin` per conto di una squadra; menu per scope e guide GM, admin e dev come gli altri bot; nei log niente chiamate all'API di Telegram

## v2 (2026-10-13)

- `/build_panchina`: la panchina anche coi bottoni, un panchinaro alla volta in ordine, proponendo solo i giocatori della squadra non nel quintetto e non già scelti; poi la stessa anteprima con Pubblica (sul canale i nomi dei giocatori)

## v3 (2026-10-13)

- 😎 CAI mode nel builder: dall'anteprima di `/build_panchina` il bot chiede il titolo e il soprannome di ogni panchinaro, uno alla volta (salta, fine); sul canale escono titolo e soprannomi, che diventano alias. Un messaggio di 3 o più righe durante la CAI mode è una panchina nuova; la CAI mode lasciata a metà scade dopo 6 ore

## v4 (2026-10-13)

- Admin coi bottoni sulle altre squadre: `/quintetto_admin SQUADRA` senza righe apre il quintetto di quella squadra coi bottoni (parte da quello attuale; anche a giornata in corso aggiorna la formazione della giornata), `/panchina_admin SQUADRA` senza righe apre il builder della panchina con la CAI mode. I bottoni del quintetto portano la squadra (un GM non tocca quelle degli altri)

## v5 (2026-10-13)

- Riconosce il nome di battesimo da solo anche scritto male o accorciato ("Herbet", "Herb" → Herbert Jones), se è di un solo giocatore della squadra
- Sul canale Panchinari niente più emoji 🪑 nell'intestazione della panchina
- Righe dubbie risolte con un tocco: nell'anteprima i candidati di ogni riga dubbia sono già bottoni ("2: Jalen Williams"), più "📋 altri" per tutta la rosa

## v6 (2026-10-13)

- Comandi dev: `/dev_promemoria [SQUADRA]` (ti manda in privato il promemoria del quintetto come lo riceverebbe la squadra, per provarlo), `/dev_log`, `/dev_pg`, `/reboot`. Menu dev e `/dev` aggiornati
- Guide: sezione "Comandi dev" nella guida dev, `/start` e `/guida` nella guida GM

## v7 (2026-10-13)

- Panchina rimandata: sul canale Panchinari si **modifica il messaggio di prima** (con "🔁 aggiornata" nell'intestazione) invece di mandarne uno nuovo in risposta. Un messaggio nuovo solo se il vecchio è stato cancellato a mano; da lì il bot modifica quello nuovo

## v8 (2026-10-13)

- "Message is not modified" (bottone premuto due volte, il messaggio resterebbe uguale) non arriva più sul canale log come errore: è innocuo, come già nel bot principale e nel bot aste. Gli errori di rete restano sul canale log (non al dev). Gli errori veri dicono anche chi e quale bottone o comando. Error handler comune in `shared/dev_comune.py`

## v9 (2026-10-13)

- **Panchina sempre di 5 giocatori**, mai meno: un messaggio con meno righe viene rifiutato (con la spiegazione), il builder passa all'anteprima e a Pubblica solo al quinto (i titolari, segnati ⭐, si possono scegliere solo se non restano abbastanza giocatori)
- **`/soprannomi`**: i soprannomi che il bot riconosce per i giocatori della squadra, giocatore per giocatore, con 🗑 per cancellare quelli sbagliati o vecchi; gli admin `/soprannomi SQUADRA`. Il nome vero del giocatore non diventa più un soprannome
- **I soprannomi seguono il giocatore**: dopo una trade valgono per la squadra nuova (in `/soprannomi` con chi li ha scritti) e non più per la vecchia
- **Trade e tagli**: ogni 5 minuti il bot controlla se un giocatore schierato non è più in squadra (quintetto, panchina della prossima giornata, formazione o panchina della giornata in corso) e avvisa i GM della squadra e il canale log, una volta sola: la panchina va rimandata, il quintetto si aggiorna se si vuole, per la giornata in corso decidono gli admin. `/panchina` segna il giocatore fuori squadra
- Ovunque si parla del quintetto (`/start`, `/quintetto`, promemoria, avvisi, guide, menu) il bot ripete che aggiornarlo **non è obbligatorio**: fa fede Yahoo, è un favore agli admin

## v10 (2026-10-13)

- Sul canale Panchinari, in fondo a ogni panchina: chi l'ha inserita (**✍️ GM** o **✍️ admin** col nome) e giorno e ora (ora italiana) dell'inserimento o dell'ultima modifica

## v11 (2026-10-13)

- `/soprannomi`: nei bottoni 🗑 il nome intero del giocatore, non solo il cognome (con gli omonimi, Grant e Mark Williams, non si capiva quale)

## v12 (2026-10-13)

- `/quintetti` (admin): tutti i quintetti attuali, una riga per squadra (PG · SG · SF · PF · C, nomi interi; ⚠️ chi non è più in squadra, — ruolo vuoto). `/quintetti N`: le formazioni congelate della giornata N, quelle del calcolo

## v13 (2026-10-13)

- Righe uguali nella stessa panchina ("prova" cinque volte): non usano i soprannomi e alla pubblicazione non diventano un soprannome

## v14 (2026-10-13)

- **Righe duplicate**: una panchina con la stessa riga scritta più volte ("prova" cinque volte, anche con maiuscole o punteggiatura diverse) viene rifiutata con "Righe duplicate"; anche due soprannomi uguali nella CAI mode bloccano Pubblica. Al posto della v13, che le accettava facendo scegliere i giocatori coi bottoni

## v15 (2026-10-13)

- **`/ripubblica_panchine [N]`** (admin): tutte le panchine già mandate della prossima giornata (o della N) di nuovo sul canale Panchinari, con chi e quando, una ogni 3,5 secondi (limite di Telegram), senza bloccare il bot; avviso a fine lavoro e sul log. Serve per passare dal canale di prova a quello vero
- Le modifiche di una panchina vanno sul suo messaggio solo se è nel canale di oggi (`ipa_panchine.canale_id`): dopo un cambio di canale il bot non rischia più di modificare, con lo stesso numero di messaggio, la panchina di un'altra squadra. Le panchine salvate prima di questa versione, alla prossima modifica, escono come messaggio nuovo
- Salvati anche il nome di chi ha inserito la panchina e quante volte è stata mandata, per ripubblicarla com'era

## v16 (2026-10-13)

- Panchina aggiornata sul canale: niente più "· 🔁 aggiornata" accanto al nome della squadra; basta la riga in fondo, "✍️ GM · 🔁 ultima modifica 13/10 alle 16:00"
- `/soprannomi SQUADRA` anche per i GM: i soprannomi di un'altra squadra, solo da guardare (senza bottoni); cancellarli resta al GM di quella squadra e agli admin
- Stato infortunati di ESPN accanto ai giocatori nel builder della panchina, nella scelta del quintetto, nell'anteprima e nel promemoria (🔴 Out, 🟠 Doubtful, 🟡 Questionable/Day-To-Day, 🟢 Probable), con l'ora dell'aggiornamento: è l'ultimo snapshot degli infortunati di loucabot (ogni 4 ore e prima delle partite)

## v17 (2026-10-13)

- Per il calcolo di loucabot: alla scadenza si congela anche il **ruolo di ogni panchinaro** nella panchina della giornata (la FADD usa quello). `/panchina_admin SQUADRA GN` corregge la panchina di una giornata già chiusa (anche col builder): si pubblica a scadenza passata, i ruoli si ricongelano, invito a `/ricalcola N` su loucabot

## v18 (2026-10-14)

- L'admin può **confermare il quintetto** di una squadra prima della scadenza: nell'editor di `/quintetto_admin SQUADRA` c'è ✅ Conferma per la giornata N (admin); la squadra risulta ✅ in `/stato` e nel riepilogo
- **`/controlli [N]`**: dopo la scadenza, le formazioni congelate della giornata, una per squadra, con ☑️ controllata (chi e quando) o ⬜ da controllare su Yahoo e lo stato del GM; un bottone per squadra segna (o toglie) il controllo. Una correzione dell'admin alla formazione di una giornata chiusa la segna controllata da sola. Il segno c'è anche nell'editor admin e in `/stato N` (tabella `ipa_controlli`)

## v19 (2026-10-16)

- **`/soprannomi tutti`** (admin): tutti i soprannomi della lega in un file .md, dal più sospetto (somiglianza col nome del giocatore da 0 a 1: sotto 0,5 «sospetti», cioè col nome non c'entrano), e i sospetti nel messaggio; si cancellano con /soprannomi SQUADRA

## v20 (2026-10-18)

- Il numero di giocatori della panchina viene da `config/settings.json` (`giocatori_panchina`, default 5) invece che dal codice

## v21 (2026-10-18)

- **`/report_formazioni [N]`** (admin): quintetti e panchine di tutte le squadre per la prossima giornata (o la N) in un file Markdown, da usare prima della scadenza. Riepilogo (avversaria, quintetto confermato o no, panchina mandata, in ritardo o mancante, quanti titolari e panchinari con problemi) e una tabella per squadra con squadra NBA, partite della giornata, stato degli infortunati e note: posto vuoto, panchina non mandata, Out/Doubtful/Questionable, squadra NBA senza partite, senza id ESPN, non più in squadra, ruolo cambiato, titolare anche in panchina, non abbinato, panchina di lunghezza sbagliata. A giornata chiusa le formazioni congelate. Solo lettura

## v22 (2026-10-18)

- `/report_formazioni` prepara il file in un thread: il bot non si blocca mentre lo scrive

## v23 (2026-10-18)

- Alla chiusura della giornata, nel gruppo admin, anche le **panchine con giocatori non più in squadra alla scadenza** (penalità: decidono gli admin; nel calcolo escono e gli altri scalano) e i **titolari non più in squadra** (da correggere da Yahoo). Dal registro dei movimenti del bot principale: chi è ceduto dopo la scadenza non viene segnalato

## v24 (2026-10-19)

- **Registro delle azioni** (main v6.0.0, `registro.py`): panchine mandate e corrette (GM, o admin per conto), quintetti cambiati e confermati (GM, o admin per conto), quintetto e formazione corretti da /quintetto_admin, quintetti importati, formazioni controllate ☑️ e controlli tolti, panchine ripubblicate, soprannomi cancellati, chiusura della giornata (sistema) lasciano una riga nel registro condiviso con gli altri bot, con chi, veste e prima → dopo; si consulta dal bot principale. Sul canale log restano le righe di sempre, che avevano già il nome di chi (niente doppioni)
- Prova: controlli del registro in `ipa_panchine`

## v25 (2026-10-19)

- **Quintetto**: dopo ✅ Confermo il messaggio si chiude e resta il riepilogo, con scritto che si cambia in qualsiasi momento con /quintetto (prima restava aperto l'editor coi bottoni e non si capiva se era fatta). Nel promemoria la stessa frase. L'editor ha ✖️ Chiudi
- **Titolare anche in panchina, visto da un admin** (editor di /quintetto_admin): non più «se vuoi aggiorna il quintetto» (pensato per il GM) ma cosa fare: prima della scadenza avvisare il GM di cambiare la panchina; a giornata iniziata è un errore del GM (nel calcolo il titolare conta, in panchina gli altri scalano, penalità agli admin). Guarda anche la panchina della giornata in corso. Negli elenchi (/stato, riepilogo) la versione breve
- **`/stato`** manda anche un file Markdown con la tabella (squadra, quintetto, panchina, formazione controllata, problemi)
- **Niente panchine durante la giornata in corso** (Luca, 19/10): dalla scadenza alle 6:00 del giorno dopo l'ultimo giorno NBA della giornata (quello in cui comincia la successiva) il bot risponde che c'è una giornata in corso, anche a /build_panchina e a /panchina_admin senza GN. Prima una panchina arrivata a giornata iniziata valeva in silenzio per la giornata dopo. /panchina in quelle ore mostra quella della giornata in corso
- Prove: controlli nuovi in `ipa_panchine`

## v26 (2026-10-20)

- **`/edit`** (Luca, 20/10): la panchina già mandata per la prossima giornata, una riga per giocatore. Il bottone del giocatore cambia il soprannome (scritto in chat, ♻️ nome vero); ⬆️ ⬇️ spostano; 🔄 cambia: con un altro già in panchina i due si scambiano il posto e ognuno tiene il suo soprannome, con uno fuori panchina entra al suo posto col nome vero. Il titolo resta; ✅ Pubblica aggiorna il messaggio sul canale. Lo stesso editor anche dall'anteprima di una panchina nuova (🛠). Admin: `/edit SQUADRA`. A giornata in corso è bloccato come le panchine nuove
- Guide GM, admin e dev; prove nuove in `ipa_panchine`

## v27 (2026-10-20)

- **`/quintetto_admin SQUADRA GN` senza righe** (Luca, 20/10): con il GN della giornata in corso apre l'editor coi bottoni (ogni cambio vale anche per la sua formazione), invece di «manca PG, SG, SF, PF, C». Con il GN di una giornata chiusa ma non più in corso spiega come scrivere i 5 titolari sotto
- **Fino alle 6 i comandi restano sulla giornata in corso** (Luca, 20/10), come già le panchine: dalla scadenza alle 6:00 del giorno dopo l'ultimo giorno NBA della giornata `/quintetto` mostra il quintetto senza bottoni e dice da quando si cambia; i bottoni vecchi del GM (cambio, Confermo, Modifico) sono bloccati. L'admin con `/quintetto_admin` continua a correggere la formazione della giornata in corso, senza il Conferma della giornata dopo. `/stato` e i report senza numero mostrano la giornata in corso
- **Admin a giornata in corso** (Luca, 20/10): `/edit SQUADRA` e `/panchina_admin SQUADRA` (anche senza GN) correggono la panchina della giornata in corso, invece di «non accetto panchine» (che resta per i GM)

## v28 (2026-10-23)

- **Media fantapunti nei builder** (Luca, 23/10): accanto ai giocatori nei bottoni di `/build_panchina`, `/edit` (anche nel testo dell'editor e nella lista di 🔄) e del quintetto, la media fantapunti della stagione in corso (0 senza partite), dai tabellini di loucabot (`db.medie_fp`, `comune.medie`)
- Orari di fine blocco delle panchine (6:00) e del promemoria dei quintetti (8:00) da `orari` in settings.json

## v29 (2026-10-23)

- Testi degli avvisi sul titolare anche in panchina allineati alla regola giusta: in panchina quella posizione vale 0, gli altri non scalano

## v30 (2026-10-23)

- «a media» diventa «prendono la media» (Luca, 23/10): nei builder «nessuna partita (prende la media)», nel report delle formazioni

## v31 (2026-10-23)

- **Avvisi dell'injury report** (Luca, 23/10; `infortuni.py`): quando ESPN cambia lo stato di un giocatore della squadra (anche uscito dalla lista = di nuovo disponibile) il bot lo scrive in privato ai GM, col dettaglio e il ruolo se è nel quintetto; tutti i giocatori della rosa, a qualsiasi ora. Nessun cambio si perde se loucabot prende più snapshot tra un giro e l'altro; uno snapshot incompleto (meno della metà dei giocatori) non manda avvisi
- **`/toggle_injures`**: spegne e riaccende gli avvisi, ricordato sotto ogni avviso
- Ricerca delle squadre per una parola sola (`/soprannomi`, `/quintetto_admin`, `/panchina_admin`…)

## v32 (2026-10-26)

- `/quintetti`: una riga vuota tra una squadra e l'altra; chi prende la media con 📈 (Luca, 26/10)

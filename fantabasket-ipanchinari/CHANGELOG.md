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


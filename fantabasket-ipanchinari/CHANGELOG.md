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

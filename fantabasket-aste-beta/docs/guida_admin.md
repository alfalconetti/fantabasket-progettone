# Guida admin — bot aste

Il bot aste lavora quasi tutto da solo. Le aste si aprono, scadono, vanno in firma e annunciano il risultato senza bisogno di nessuno. Da admin intervieni in tre casi:

- quando una squadra non può fare da sé;
- quando un'asta va corretta;
- quando qualcosa si inceppa.

`/admin` ti dà l'elenco dei comandi in breve; questa guida li spiega con calma.

---

## Cosa NON si fa da qui

**La fase.** La cambia solo il bot principale (`/set_fase`). Il bot aste se ne accorge entro 5 minuti: aggiorna i menu e apre o chiude il mercato FA da solo. Il `/set_fase` di questo bot non fa più niente e rimanda all'altro.

**La stagione.** Anche questa la porta avanti il bot principale, entrando in *offseason-rinnovi*. Con la stagione nuova ogni squadra può di nuovo aprire una RFA. `/reset_rfa` non serve più.

**Cap e slot.** Vengono dai contratti nel database del bot principale. Se un numero è sbagliato, va corretto lì (una firma o un taglio mancante), non qui. `/set_cap`, `/add_cap`, `/set_slot` e `/add_slot` non fanno più niente.

Anche la **penalità** sul cap si imposta dal bot principale: `/set_cap_penalizzato team07 5`.

---

## Guardare la situazione

- **`/list`** — nome, id e GM di tutte le squadre. Serve soprattutto per trovare un id.
- **`/listteams`** — una riga per squadra: cap occupato su tetto, cap libero, giocatori su 15, ed eventuali offerte in corso. I segnali:
  - ⚠️ in offseason, chi sta sopra il cap che avrà in regular season;
  - ⚠️ in regular season, chi sta sotto il salary floor;
  - 🔴 cap o slot liberi negativi.
- **`/team team07`** (o `/team Rossi`, `/team buf`: id, nome della squadra o del GM, come il roster nel bot principale) — una squadra nel dettaglio: la stessa vista che il GM ha con `/me`.
- **`/aste`** — le aste aperte, con il loro numero (l'id).
- **`/all_aste`** — anche quelle finite (le ultime 30). Si può filtrare per stato: `/all_aste chiusa`, `pareggio`, `conclusa`, `annullata`. Serve per ritrovare l'id di un'asta che non è più in `/aste`.
- **`/firme`** — le ultime 10 firme (`/firme 30` per vederne di più).
- **`/stato_asta 42`** — tutto quello che c'è nel database su un'asta, offerte comprese.

---

## Agire per conto di una squadra

**Aprire un'asta FA.** Esempio: il GM di team07 ti scrive che non riesce ad aprire l'asta per LeBron a 5.

```
/apri_asta team07 5 LeBron James
```

Valgono gli stessi controlli del GM: mercato aperto, cap e slot della squadra, giocatore non già all'asta, regola dei 30 giorni e minimo Cam Thomas. Se il nome è ambiguo il bot ti propone i comandi già scritti coi nomi giusti, da ricopiare.

L'asta compare sul canale con la scritta "aperta da admin per conto di", e i GM della squadra vengono avvisati e la seguono.

**Fare un'offerta.** Per esempio 7 di team07 sull'asta 42:

```
/crea_offerta team07 42 7
```

Stessi controlli di un'offerta normale. L'azione finisce sul canale log col tuo nome.

**Le RFA si aprono da sole.** I GM dichiarano il loro RFA nel bot principale durante i rinnovi (menu → 🔒 Dichiara RFA, o un admin dal pannello → 🔒 RFA squadre). Quando la fase diventa RFA, entro 5 minuti questo bot apre l'asta di ogni giocatore dichiarato, col vecchio contratto preso dal database, e i GM proprietari la seguono in automatico. Se un RFA viene scambiato durante l'asta, il bot passa i diritti alla nuova squadra e lo scrive sul canale log.

**Aprire una RFA a mano** (solo se serve, per esempio per un giocatore non dichiarato):

```
/nuova_rfa Doncic team12 28
```

Cioè: giocatore, squadra proprietaria, vecchio contratto.

- Il giocatore viene cercato nel roster di quella squadra, quindi gli accenti non servono e basta il cognome; se il nome non torna, il bot suggerisce quello giusto.
- Ogni squadra ha **una sola RFA a stagione**.

---

## Correggere un'asta

Tutte queste azioni avvisano chi è coinvolto (GM in testa, proprietario RFA, chi segue l'asta) e riportano il tuo nome sul canale log.

**`/annulla_offerta 42`** toglie l'ultima offerta e rimette in testa quella prima. Se così chi torna in testa finirebbe con il cap in negativo, il bot chiede conferma nel gruppo admin prima di procedere.

**`/chiudi_asta 42`** chiude subito l'asta:

- se c'è un vincitore parte la firma;
- se è una RFA senza offerte, il proprietario riceve i bottoni per firmarlo o lasciarlo andare.

**`/annulla_asta 42`** annulla l'asta senza vincitore.

**`/riapri_asta 42`** riporta ad aperta un'asta chiusa, in pareggio o annullata, con 18 ore di tempo (`/riapri_asta 42 6` per darne 6). Il bot:

- ferma firme e pareggi in sospeso;
- aggiorna il messaggio nel canale;
- avvisa chi segue l'asta.

Chiede conferma nel gruppo se l'asta era annullata, o se qualcuno finirebbe col cap in negativo.

**Cambiare la scadenza:**

- `/estendi_asta 42 6` → 6 ore in più;
- `/estendi_asta 42 -3` → 3 ore in meno;
- `/sposta_asta 42 2026-11-15T20:00` → scadenza precisa, in ora di Roma.

---

## Se qualcosa si inceppa

**Un GM dice che non gli è arrivato il messaggio per firmare o pareggiare.** Per esempio aveva bloccato il bot.

```
/force_esito 42
```

Rimanda il messaggio e riattiva le scadenze automatiche. Non cambia niente nel database. Funziona sulle aste chiuse o in pareggio.

**Il messaggio dell'asta nel canale è rimasto indietro**, per esempio non mostra l'ultima offerta: `/forza_aggiornamento 42` lo riscrive con i dati giusti.

**Il messaggio nel canale è stato cancellato**: `/ripubblica_asta 42` ne pubblica uno nuovo e lo collega all'asta. Senza, ogni rilancio darebbe errore sul canale log.

**Un GM ha usato `/autocap` o `/autoslot`.** Arriva una segnalazione nel gruppo. Il cap o lo slot anticipato dura 48 ore; se la richiesta non è giustificata c'è il bottone per azzerarlo.

**Il mercato FA va aperto o chiuso fuori fase:** `/apri_mercato` e `/chiudi_mercato`. Solo per emergenze: di norma il mercato segue la fase del bot principale, e il cambio di fase successivo lo rimette com'era previsto. Le RFA non dipendono dal mercato.

**Backup subito del database delle aste:** `/backup_ora`. I backup completi automatici li fa il bot principale.

---

## Da sapere

- Un'asta che una squadra sta vincendo **impegna cap e slot** dal primo rilancio fino alla firma. Questo vale anche dopo la chiusura, mentre il GM sceglie anni e ruolo, e durante il pareggio di una RFA.
- **Un RFA** occupa cap ma non slot del proprietario, finché la sua asta non è conclusa.
- **I contratti finiti (x0)**, dai rinnovi all'inizio della FA, non pesano né sul cap né sugli slot (tranne l'RFA dichiarato, sul cap). Cap e slot li calcola il bot principale allo stesso modo.
- **L'offerta massima** su una singola asta si calcola da sola: il cap di regular season meno 1M per ognuno degli altri 9 giocatori che servono ad arrivare al minimo di 10 (oggi 150 − 9 = 141M). Chi la offre chiude l'asta all'istante.
- **Se il bot si riavvia**, firme e pareggi in sospeso ripartono da soli dopo pochi secondi.
- **Gli avvisi importanti** finiscono sul canale log: cap negativi, errori nei job automatici, messaggi del canale che non si aggiornano. Gli errori arrivano anche in privato al dev.
- **Registro delle azioni** (aste v68): ogni azione che cambia qualcosa (aste aperte, offerte, chiusure, annullamenti, riaperture, scadenze spostate, firme, pareggi, preimpostazioni, mercato, cap e slot anticipati) lascia una riga nel registro unico di tutti i bot, con chi, in che veste, prima → dopo. Le azioni da admin vanno anche sul canale log di questo bot in un formato unico (`🛠 admin Nome · azione · squadra`, sotto `giocatore (asta FA #42): prima → dopo`). Si consulta dal bot principale (comando registro, o pannello admin → 📜 Registro); il filtro «aste» mostra solo questo bot.
- **Per la diagnostica più tecnica** il dev ha `/dev`.

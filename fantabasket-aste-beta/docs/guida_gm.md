# Guida GM — bot aste

Qui si fanno le aste: free agent (FA) e restricted free agent (RFA). Roster, trade e tagli sono nel bot principale.

**La prima volta** manda `/start` al bot in privato, altrimenti non può scriverti (e ti perdi le notifiche delle aste).

Il menu dei comandi (il tasto `/`) segue la fase. A mercato chiuso, per esempio, non vedi `/nuova_fa`. Se qualcosa non compare, probabilmente adesso non si può fare.

---

## Quanto posso spendere?

**`/me`** ti dà la tua situazione:

- **cap libero**, già al netto delle aste che stai vincendo in questo momento;
- **slot liberi** (massimo 15 giocatori);
- le **offerte** con cui sei in testa.

In offseason ti mostra anche come saresti messo col cap di regular season, e quanto pesa il tuo eventuale RFA.

Per vedere un'altra squadra: **`/team team07`**, con l'id della squadra. Gli id li trovi in `/listteams`, che mostra anche cap e slot di tutti in una riga a testa.

Il bot fa sempre questi conti prima di accettare un'offerta. Se non hai cap o slot te lo dice subito e l'offerta non parte.

---

## Aprire un'asta

Due modi:

**Dalla lista.** `/lista_fa` mostra i free agent. Tocchi un nome e il bot ti chiede quanto offri. Il pallino 🟡 vuol dire che per quel giocatore c'è già un'asta aperta.

**Scrivendo il nome.** `/nuova_fa Jalen Williams`. Basta anche il cognome, e qualche errore di battitura viene perdonato (`/nuova_fa Currry` trova Curry). Se ci sono omonimi il bot ti fa scegliere.

L'offerta con cui apri è la prima offerta dell'asta, e da lì parte il timer di **18 ore**.

---

## Rilanciare

**`/offri`** elenca le aste aperte, ognuna con offerta attuale e tempo che manca (per esempio `3h` o `47min`). Tocchi quella che ti interessa e scrivi la cifra.

I bottoni non scadono: puoi usarli anche ore dopo. Se intanto l'asta è finita, il bot te lo dice.

**`/offerta asta 42 15`** fa la stessa cosa in un colpo solo: offre 15 sull'asta 42. È comodo con i **messaggi programmati** di Telegram. Scrivi il comando, tieni premuto invio, scegli "Programma messaggio" e il bot eseguirà l'offerta all'ora che hai deciso. Se in quel momento l'offerta non è valida, ti risponde col motivo.

Regole del rilancio:

- devi superare l'offerta attuale di almeno 1;
- non puoi rilanciare su te stesso;
- **ogni offerta fa ripartire il timer da 18 ore**;
- chi offre il **massimo consentito** (oggi 141M: 150 meno 1M per ognuno degli altri 9 giocatori del minimo di 10) chiude l'asta all'istante e se lo prende.

---

## Seguire le aste

Quando fai un'offerta inizi a seguire l'asta in automatico. Puoi seguirne altre:

- dal bottone 🔔 nel canale;
- con **`/watch`**, che ti mostra la lista (✅ = già seguita);
- con `/watch 42`.

Per ogni asta che segui ricevi un messaggio:

- a ogni rilancio;
- 15 minuti prima della fine;
- alla firma.

**`/watched`** elenca le aste che segui, con un link per offrire direttamente su quelle ancora aperte.

Per smettere di ricevere notifiche di un'asta: **`/silenzia 42`** (il comando lo trovi già pronto in ogni notifica).

---

## Ho vinto: la firma

Quando l'asta finisce e sei in testa, ti arriva un messaggio con i bottoni per scegliere gli **anni**. In regular season, dopo gli anni scegli anche il **ruolo** tra quelli eleggibili del giocatore.

Gli anni dipendono dalla cifra:

| Cifra | Anni |
|---|---|
| sotto 20M | 1, 2 o 3, scegli tu |
| da 20M a 34M | 2 o 3 |
| da 35M | 3, obbligatori |

Hai **48 ore**. Se non rispondi, il contratto viene firmato per **3 anni** come penale (e in regular season il ruolo viene estratto a caso).

Finché non firmi, quel giocatore **conta già** sul tuo cap e sui tuoi slot, anche ad asta chiusa. Quindi non puoi usare quei soldi per un'altra asta nel frattempo.

---

## Le regole che il bot controlla da solo

**Regola dei 30 giorni.** Se un giocatore è stato tagliato e tu l'hai avuto in squadra negli ultimi 30 giorni, non puoi aprirgli l'asta né rilanciare. Esempio: lo tagli il 1° marzo, finisce in FA e tu vorresti riprenderlo a meno. Fino al 31 marzo non puoi.

**Cam Thomas exception.** Se hai fatto decadere un giocatore con la Cam Thomas exception, per un anno puoi riprenderlo solo ad almeno il contratto che aveva prima. Esempio: era 15 → la tua prima offerta (o il tuo rilancio) deve essere almeno 15.

**DPE.** Un giocatore con la DPE pesa sul tuo cap con lo stipendio ridotto, e il bot conta quello.

**Il tuo RFA.** Occupa cap ma **non** uno slot, finché la sua asta non è finita. E non puoi fare offerte sul tuo stesso RFA.

---

## Le aste RFA (offseason)

Nella fase RFA ogni squadra può mettere all'asta un suo giocatore in scadenza. Gli altri fanno offerte; alla fine il proprietario decide se **pareggiare** e tenerselo, o lasciarlo andare.

### Se vinci l'asta di un RFA altrui

Scegli gli anni come in FA, ma hai solo **12 ore**. Se non rispondi ti vengono dati gli anni minimi per la cifra:

- 1 anno sotto i 20M;
- 2 anni da 20M;
- 3 anni da 35M.

Da 35M in su gli anni sono 3 per forza, quindi non ti viene chiesto niente.

Poi aspetti: il proprietario ha **24 ore dalla fine dell'asta** per decidere se pareggiare.

### Se il RFA è tuo

Alla fine dell'asta ti arriva l'offerta vincente con la scadenza esatta per decidere. Quando il vincitore ha scelto gli anni ricevi tutti i dettagli e i bottoni per pareggiare o lasciarlo andare.

**Quanto devi offrire per pareggiare** dipende da quanto guadagnava prima:

- **vecchio contratto fino a 20M:** pareggi la cifra offerta, qualunque sia;
- **vecchio contratto da 21M a 34M:** devi offrire almeno **1/3** del vecchio contratto, anche se l'offerta vincente è più bassa;
- **vecchio contratto da 35M:** devi offrire almeno **la metà** del vecchio contratto.

Esempio: il tuo RFA prendeva 30M e l'asta si chiude a 6M. Un terzo di 30 è 10, quindi per tenerlo devi dargli **almeno 10M**. Visto che stai sopra l'offerta "per obbligo", gli anni li scegli tu.

Se invece l'asta si chiude a 14M (sopra la soglia di 10), pareggi a 14M e devi dargli **almeno gli stessi anni** del vincitore.

**Nessuno ha offerto?** Puoi firmarlo tu con le stesse soglie, oppure lasciarlo andare in free agency.

### Decidere in anticipo (facoltativo)

Se non vuoi aspettare che il vincitore scelga gli anni, puoi impostare la tua decisione subito dopo la fine dell'asta:

- **⚡ Pre-pareggio ≤N anni.** Pareggi in automatico se il vincitore sceglie al massimo N anni.
- **❌ Rifiuto assoluto.** Lo lasci andare comunque.
- **❌ Rifiuto se >N anni.** Lo lasci andare solo se il vincitore sceglie più di N anni.

Si possono combinare. Esempio: "pareggio se ≤2 anni" più "rifiuto se >2 anni" copre tutti i casi, e non devi più fare niente. Il bot blocca le combinazioni contraddittorie (pareggio e rifiuto assoluto insieme, oppure pareggio ≤2 con rifiuto >1, che si sovrappongono sui 2 anni).

Puoi cambiare idea finché il vincitore non ha scelto gli anni.

---

## Emergenze

**`/autocap 10`** e **`/autoslot 1`** servono quando ti manca cap o uno slot per una cosa già successa che il bot non vede ancora. Esempio: una trade approvata di notte con gli admin che dormono. Il cap o lo slot ti vengono dati subito, valgono **48 ore** (il tempo che la trade venga registrata), e gli admin ricevono la segnalazione per controllare.

Usali solo se serve davvero: le dichiarazioni false si pagano con una penalità.

Se il bot sembra bloccato ad aspettare una tua risposta: **`/annulla`**.

---

## In breve

| Voglio… | Comando |
|---|---|
| sapere quanto posso spendere | `/me` |
| vedere un'altra squadra | `/team team07` |
| vedere i free agent | `/lista_fa` |
| aprire un'asta | `/nuova_fa Nome` |
| rilanciare | `/offri` oppure `/offerta asta 42 15` |
| seguire o smettere di seguire | `/watch`, `/watched`, `/silenzia 42` |
| ricevere questa guida | `/guida` |

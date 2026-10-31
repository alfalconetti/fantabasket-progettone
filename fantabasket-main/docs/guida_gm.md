# Guida GM — bot principale

Questo è il bot dove vive la tua squadra: roster, trade, tagli, rookie, ruoli.

Gli altri bot della lega: **bot aste** (aste FA e RFA), **loucabot** (calendario, scadenze, squadre a media, punteggi), **IPanchinari** (panchine e quintetti). Ognuno ha la sua guida (`/guida`).

Si usa tutto in **chat privata**. Se qualcosa non torna, o non sai come fare, scrivi a un admin: può fare qualsiasi operazione al posto tuo.

---

## Da dove si parte

Scrivi `/menu`. Ti compare un messaggio con dei bottoni e, in alto, la fase in cui siamo (per esempio *regular-season-fa* o *offseason-draft*).

I bottoni cambiano con la fase: se le trade sono chiuse il bottone Trade non c'è, se non siamo in regular season non c'è il cambio ruolo. Quindi se cerchi una cosa e non la trovi, probabilmente in questo momento non si può fare. Roster e Assets invece ci sono sempre.

Anche il menu dei comandi di Telegram (il tasto `/` vicino alla tastiera) segue la fase. Se dopo un cambio di fase non vedi un comando nuovo, chiudi e riapri la chat.

Due cose da sapere:

- Se lasci un'operazione a metà, dopo qualche minuto il bot la chiude da solo.
- Se il bot sembra bloccato ad aspettare una tua risposta, scrivi `/annulla` ed esci da qualsiasi cosa.

---

## Guardare la squadra

**`/roster`** ti manda un'immagine del tuo roster. In alto il logo, il salary cap (con contratti e impatto dei tagli) e quanti posti sono occupati su 15. Per ogni giocatore vedi:

- il ruolo a sinistra, in un'etichetta;
- le posizioni eleggibili accanto al nome;
- la fantamedia;
- il contratto: i rookie hanno il colore del loro anno di scala (dal I al IV), RFA, DPE e 10-day il loro colore, con una barretta colorata davanti al nome. Se il colore non si leggerebbe sullo sfondo della riga, il nome ha un riquadro chiaro dietro.

I posti liberi sono righe basse con scritto «posto libero». Chi sta fuori dai 15 (il 10-day, la DPE che libera lo slot) è in fondo, sotto una riga più spessa e l'etichetta «FUORI DAI 15». In fondo, tre riquadri: età media, tagli senza impatto usati e cambi ruolo usati.

Dalla fase dei rinnovi all'inizio della free agency i contratti finiti compaiono con durata **0** (per esempio 10x0) e non entrano nel cap. L'RFA dichiarato è segnato con la sigla **A** e invece nel cap c'è.

Il comando funziona anche in altri modi:

- `/roster team07` oppure `/roster Rossi` → il roster di un'altra squadra (basta una parte del nome della squadra o del GM)
- `/roster 15-01-26` → il tuo roster com'era il 15 gennaio 2026

**`/assets`** è il roster più tutto il resto: le pick anno per anno (una scheda per anno: piene quelle tue, col solo bordo e «da …» quelle prese da altri) e i diritti sui rookie. Se vedi il tag rosso **STEPIEN** su una tua prima scelta, vuol dire che non puoi cederla senza violare la Stepien Rule.

**`/carriera GIOCATORE`** manda un'immagine con la carriera del giocatore dal 25 luglio 2026, quando è nato il bot: a sinistra i movimenti nel fantabasket (in rosa all'avvio o il draft, firme, trade, tagli, DPE, 10-day), a destra le squadre NBA vere, con le date al centro e una barra col colore della squadra di ogni periodo. Le trade poi annullate non compaiono. I cambi di squadra NBA vengono dai roster ESPN e da Basketball-Reference: per quelli visti solo lì la data è quella della prima partita con la squadra nuova. Funziona anche nei gruppi.

**`/team_diff`** ti dice cosa è cambiato nell'ultima settimana: chi è arrivato, chi è uscito e chi ha cambiato contratto (per esempio per una DPE, un rinnovo o un rookie che passa al II anno, 12x2 → 13x1). Esempio di risposta:

```
🟢 IN
  • Jalen Williams 12x2 (Trade)
🔴 OUT
  • Kevin Durant 30x1 (Tagliato)
🔁 CONTRATTO CAMBIATO
  • Joel Embiid 40x2 → 30x2 (DPE, era 40)
```

Funziona anche per un'altra squadra (`/team_diff team07`) o tra due date a scelta (`/team_diff team07 01-10-26 15-10-26`).

`/roster`, `/assets`, `/team_diff` e `/carriera` funzionano anche nei gruppi della lega, e li trovi nel menu dei comandi del gruppo.

**`/my_team`** serve a cambiare nome squadra e nome GM. **`/palette`** personalizza i colori delle immagini di roster e assets: tocchi un colore (intestazione, righe pari e dispari, leggenda e cap, pick, diritti), scrivi il colore in esadecimale (`#1A237E`, anche senza #) o scegli ♻️ Automatico (ricavato dal colore dell'intestazione), vedi l'anteprima e alla fine 💾 Salva. Qualsiasi colore scegli, il testo sopra diventa chiaro o scuro da solo, così resta sempre leggibile.

In tutti i menu a bottoni c'è un modo per uscire: ← per tornare alla schermata di prima, 🏠 Menu, oppure ✖️ Chiudi.

---

## Le trade

### Costruirla coi bottoni

Menu → **Trade → Build** (oppure `/build_trade`).

1. Scegli le squadre coinvolte: la tua più una, due o tre altre.
2. Per ogni squadra tocchi cosa cede: giocatori, pick, diritti.
3. Se le squadre sono più di due, il bot ti chiede anche **a chi va** ogni pezzo.

Alla fine vedi il riepilogo con il controllo automatico. Il bot verifica:

- il cap di ogni squadra;
- che nessuno superi i 15 giocatori;
- la Stepien Rule;
- in regular season, i ruoli minimi (4 guardie, 4 ali, 2 centri).

Se c'è un problema te lo dice e non ti fa inviare.

Se è tutto a posto hai tre scelte:

- **proporla agli altri GM**;
- **mandarla direttamente agli admin**;
- **tenerla in bozza** per dopo.

### Scriverla come testo

Menu → **Trade → Import** (oppure `/import_trade`) e incolli la trade nel formato della lega. Per una trade a due basta scrivere cosa cede ognuno:

```
Rossi cede:
LeBron James 25x2
1st round pick 2027 by Bianchi

Bianchi cede:
Jalen Williams 12x2
2nd round pick 2028 Rossi
Diritti di Mario Rookie
```

Per una trade a **tre o più squadre** serve anche cosa **riceve** ognuno, altrimenti il bot non sa dove mandare i pezzi:

```
Rossi cede:
LeBron James 25x2

Bianchi cede:
Jalen Williams 12x2

Verdi cede:
1st round pick 2027 by Verdi

Rossi riceve:
Jalen Williams 12x2

Bianchi riceve:
1st round pick 2027 by Verdi

Verdi riceve:
LeBron James 25x2
```

Qualche regola:

- **I GM.** Puoi indicarli col cognome o col nome della squadra, purché non ci siano ambiguità.
- **Il "by" delle pick.** Indica la squadra di **origine** della pick, anche se nel frattempo è passata di mano. Scriverlo è facoltativo: "2nd round pick 2028 Rossi" va bene uguale.
- **Cosa puoi cedere.** Il bot controlla che pick e diritti che cedi siano davvero tuoi oggi. Se trova errori non salva niente e ti dice cosa correggere.

### Il voto

Quando proponi una trade, tutte le squadre coinvolte la ricevono e votano ✅ o ❌; chi rifiuta può aggiungere una motivazione.

- Tu vedi l'avanzamento dei voti man mano che arrivano.
- Se tutti accettano, la trade passa agli admin per l'approvazione finale.
- Ogni esito arriva a **tutte** le squadre coinvolte, non solo a chi l'ha proposta: rifiuto di un GM, rifiuto degli admin, approvazione o annullamento.

### Tenere traccia

**`/my_trades`** (o Trade → 📂 Le mie trade) elenca tutte le trade che ti riguardano, con lo stato:

- 📝 bozza
- 🗳 in voto (con chi ha già risposto)
- ⏳ dagli admin
- ✅ approvata
- ❌ rifiutata da un GM (con la motivazione)
- 🚫 rifiutata dagli admin

Dal dettaglio puoi votare, ritirare una tua proposta ancora in voto, oppure **riprendere come bozza** una trade rifiutata, sistemarla e rimandarla.

**`/bozze_trade`** mostra solo le bozze. **`/edit_trade 3`** apre la bozza numero 3.

Nell'editor puoi aggiungere o togliere giocatori, pick e diritti, cambiare la nota e i destinatari. In una trade a tre, quando premi **✅ Fatto** il bot ti chiede a chi va ogni pezzo nuovo che non ha ancora un destinatario.

Le bozze si modificano solo finché sono bozze: una trade già in voto o dagli admin non si tocca più. Se va cambiata, la ritiri e la riprendi come bozza.

### La DPE segue il giocatore

Se cedi un giocatore con la DPE attiva, la DPE va con lui. Chi lo riceve lo paga ridotto e non gli occupa uno slot, esattamente come succedeva a te.

---

## Tagliare un giocatore

Menu → **Tagli** → scegli il giocatore. Prima di confermare vedi quanto peserà il taglio sul tuo cap, anno per anno.

**Contratti 1x1.** Ogni stagione hai **3 tagli gratuiti**. Dal quarto in poi puoi tagliare lo stesso, ma quel giocatore ti pesa 1M sul cap per la stagione.

**Gli altri contratti** si spalmano secondo la tabella del regolamento. Esempio: tagli un 20x3 e per un paio di stagioni ti resta una parte del suo stipendio sul cap. L'anteprima ti dice quanto, prima di decidere.

**In regular season** il bot blocca il taglio se:

- ti lascerebbe sotto i **10 giocatori**;
- ti lascerebbe scoperto un ruolo, cioè meno di 4 guardie, 4 ali o 2 centri.

Esempio: hai esattamente 2 centri e provi a tagliarne uno → il bot ti ferma.

---

## DPE — giocatore fuori per la stagione

`/dpe` (o menu → DPE), poi scegli il giocatore. La richiesta va agli admin.

Se viene approvata, per la stagione in corso il suo contratto scende del 25%, arrotondando la riduzione per eccesso:

- 10M → 7M
- 9M → 6M
- 5M → 3M

Conta il momento in cui l'admin approva:

- **prima della trade deadline**: il giocatore smette di occuparti uno slot;
- **dopo la deadline**: lo slot no, ma ricevi un **cambio ruolo gratuito** verso il ruolo dell'infortunato. Lo trovi in `/cambio_ruolo` come 🏥 Extra DPE.

Puoi avere una sola richiesta aperta per giocatore.

---

## Rookie: attivare i diritti

Menu → **Rookie** (o `/attiva_diritti`), poi scegli il giocatore. Il contratto è già scritto dalla rookie scale in base alla pick: devi solo confermare. Serve uno slot libero.

Attenzione: i diritti delle seconde scelte al secondo anno **scadono 10 giorni prima della trade deadline**. Dopo quella data il giocatore torna free agent.

---

## Cambio di stagione: contratti finiti, rookie e RFA

Quando inizia la fase dei rinnovi parte la stagione nuova e tutti i contratti scalano di un anno: un 10x3 diventa 10x2, un 10x1 diventa **10x0**.

**Un x0 è un contratto finito.** Il giocatore resta nella tua squadra fino all'inizio della free agency, ma **non pesa né sul cap né sugli slot**. Lo vedi nel roster con la durata a 0. Nel frattempo puoi:

- dichiararlo RFA (vedi sotto);
- scambiarlo: per esempio lo cedi a una squadra che vuole dichiararlo RFA lei;
- lasciarlo andare: all'inizio della free agency scade da solo e torna free agent.

**La rookie scale la aggiorna il bot.** Al II e al IV anno l'importo passa a quello della tabella (per esempio la pick 1 va da 12 a 13), a meno che il giocatore non abbia già una Doncic più alta. Alla fine del IV anno il bot applica la Doncic, se spetta, e il contratto diventa un x0 normale: da lì si rinnova come tutti gli altri.

### Rinnovare un rookie a fine II anno

`/rinnovo_rookie` (o 🔁 Rinnovi rookie nel menu). Il bot ti propone già il contratto per il III e il IV anno, x2:

- l'importo della rookie scale del III anno;
- oppure la **Doncic**, se è più alta.

La Doncic si calcola sulla fantamedia migliore delle ultime due stagioni, presa per difetto (24,99 conta 24):

- da 20 a 24: 12 + 0,6 per ogni punto sopra 20;
- da 25 in su: 15 + 0,4 per ogni punto sopra 25;
- il risultato si arrotonda per eccesso.

Esempio: fantamedia 24,95 → conta 24 → 12 + 2,4 = 14,4 → **15**. Se la scala del III anno è 14, il rinnovo è 15x2.

I rinnovi dei rookie non hanno limite e non contano nei 2 rinnovi normali. Servono cap e uno slot liberi.

### Dichiarare l'RFA

`/dichiara_rfa` (o 🔒 Dichiara RFA nel menu), dalla fase dei rinnovi fino all'inizio delle aste RFA (quindi anche nel draft). Puoi scegliere **un solo** giocatore tra i tuoi contratti finiti (x0); fino a quel momento lo cambi o lo togli quante volte vuoi. Sul canale principale un messaggio unico, aggiornato dal bot, mostra gli RFA dichiarati di tutte le squadre.

- L'RFA **pesa sul cap** con il suo vecchio contratto, ma **non occupa uno slot**.
- Nella fase RFA il bot delle aste apre da solo la sua asta. Alla fine puoi pareggiare l'offerta vincente.
- **Scambiarlo prima delle aste RFA** (rinnovi e draft): perde la dichiarazione. Chi lo riceve ha un x0 qualsiasi, che non pesa sul cap; tu puoi dichiarare un altro RFA con `/dichiara_rfa`. Il riepilogo della trade te lo ricorda.
- **Scambiarlo con le aste aperte** (dalla fase RFA): la dichiarazione segue il giocatore e chi lo riceve decide sul pareggio. Si può solo se dopo la trade ogni squadra ha al massimo un RFA: RFA contro RFA, oppure verso una squadra che non ne ha dichiarati (anche insieme ad altri giocatori o pick).

---

## 10-day contract

In regular season, prima della chiusura della free agency, puoi prendere **un free agent per 10 giorni**, senza asta. **Una volta a stagione.**

- Non pesa sul cap e non occupa uno slot.
- Si chiede solo se nel ruolo da coprire **non hai nessun giocatore disponibile** (OUT o fuori dalle rotazioni). Decidono gli admin.
- Dura 10 giorni dall'ora della firma, ma decade solo **all'ufficialità (convalida) dell'ultima giornata in cui era in squadra**: chi inizia una giornata con te la finisce con te, e resta tuo finché quella giornata non è convalidata.
- Ogni free agent può essere firmato con un 10-day al massimo da **due squadre** a stagione.
- Alla scadenza torna free agent: per riprenderlo serve un'asta normale.
- Non si taglia, non si scambia e non va in DPE.

Come si chiede: menu → ⏱ 10-day → ✍️ e scrivi il nome (oppure `/firma_10day NOME`), poi scegli il giocatore e il ruolo che deve coprire. Il bot ti mostra i tuoi giocatori in quel ruolo con lo status ESPN, poi manda la richiesta agli admin. Quando approvano lo trovi nel roster (in fondo, sotto una riga più spessa, in verde petrolio, con la scadenza nella legenda), nel foglio Roster (sotto, riga 10-DAY) e su IPanchinari, dove lo puoi schierare come gli altri.

---

## Decadimento: il contratto si chiude senza contare come taglio

`/decadimento` (o menu → Decadimento), poi scegli il giocatore e il motivo. Decidono gli admin.

**Si è ritirato, o è andato a giocare in un altro campionato.** Il contratto si chiude. In più smettono di pesare anche le vecchie spalmature: se l'avevi tagliato in passato, i soldi che ti restavano sul cap per lui spariscono. Questo vale per tutte le squadre che l'avevano tagliato.

**Cam Thomas exception.** Il giocatore è stato tagliato in NBA ed è senza squadra da almeno un mese, con il mercato NBA aperto. Il contratto decade gratis, ma le spalmature che avevi già restano. Gli admin verificano le condizioni quando arriva la tua richiesta.

Se poi lo rifirmi entro un anno devi dargli **almeno il contratto che aveva prima**. Esempio: era un 15x2, lo fai decadere a novembre e a febbraio firma con un'altra squadra NBA. Se lo vuoi riprendere all'asta, non puoi offrire meno di 15.

---

## Ruoli

Ogni giocatore in rosa ha un ruolo: PG, SG, SF, PF o C, sempre scelto tra le sue **posizioni eleggibili** su Yahoo. Il roster deve avere sempre almeno **4 guardie** (PG/SG), **4 ali** (SF/PF) e **2 centri**.

### A inizio stagione: la dichiarazione

Nella fase *offseason-ruoli* scrivi `/dichiarazione_ruoli` (o 🎽 nel menu). Ogni stagione si riparte da zero. Ci sono due modi per farla.

**Coi bottoni.** Tocchi un giocatore e scegli il ruolo. Chi ha una sola posizione è già a posto (🔒).

**Col testo.** Premi 📥 Importa da testo e mandi un messaggio con una riga per giocatore:

```
LeBron SF
Curry PG
Jokic C
```

Basta nome o cognome. Se un nome è dubbio il bot ti chiede conferma, e ti dice chi hai dimenticato.

Le scelte restano in bozza finché non premi **✅ Conferma**. Puoi anche confermarne una parte e finire dopo, purché entro la deadline. Il giorno prima, se non hai finito, ti arriva un promemoria.

### Giocatori nuovi durante la stagione

**Dall'asta.** Il bot aste ti chiede prima gli anni e poi il ruolo.

**Da trade, firma registrata da un admin o attivazione diritti.** Ti arriva un messaggio privato con i bottoni dei ruoli possibili; lo ritrovi anche nel menu, in 🎽 Ruoli da dichiarare.

- Hai **48 ore**. Dopo, il ruolo viene estratto a caso tra quelli possibili (🎲).
- Dopo una **trade** sul canale c'è un messaggio solo con i ruoli di tutti i giocatori della trade, che si aggiorna man mano: chi è ancora da dichiarare (⏳ e fino a quando), chi è stato dichiarato, chi ha avuto il ruolo in automatico (una sola posizione, regola dei 60 giorni) e chi è stato estratto. Per le firme resta un annuncio per giocatore.
- Se il giocatore ha una sola posizione eleggibile, il ruolo è automatico e non c'è niente da fare.
- Se riprendi un giocatore che avevi negli ultimi **60 giorni**, torna col suo vecchio ruolo.
- Il ruolo non viaggia con il giocatore: chi lo riceve in trade dichiara il suo.

### Cambiare ruolo (regular season e playoff)

`/cambio_ruolo` (o 🔁 nel menu), poi giocatore e nuovo ruolo. Il bot ti mostra solo i tipi di cambio che puoi usare in quel momento:

- **Ordinario.** Al massimo 2 a stagione; il contatore è su `/roster`.
- **Erminio.** Gratuito, quando Yahoo ha aggiunto quella posizione al giocatore negli ultimi 14 giorni (lo vedi segnato con ✨). Quando c'è, l'ordinario non viene proposto, così non lo sprechi.
- **Saedro (10 giorni).** Cambio temporaneo, una volta a stagione, quando in un ruolo non hai nessuno disponibile. Lo approvano gli admin; dopo 10 giorni il giocatore torna da solo nel ruolo di prima.
- **🏥 Extra DPE.** Gratuito, uno per ogni DPE approvata dopo la deadline, verso il ruolo dell'infortunato.

Esempio: Yahoo ieri ha aggiunto "C" a un tuo PF. Apri `/cambio_ruolo`, scegli il giocatore e vedi l'opzione ✨ Erminio verso C, gratis.

I cambi che ti lascerebbero sotto i minimi (4 G, 4 F, 2 C) vengono bloccati. Ogni cambio viene annunciato sul canale.

---

## Penalità

Gli admin possono dare una penalità alla squadra (panchina in ritardo, formazioni sbagliate e così via): arriva sul canale principale e ti arriva un messaggio con la motivazione. Si sommano nella stagione e ripartono da zero con quella nuova. `/penalita` (o /menu → ⚠️ Penalità) mostra quelle della tua squadra, `/penalita SQUADRA` quelle di un'altra.

## Il registro della tua squadra

**`/registro`** ti manda un file con tutto quello che è stato fatto sulla tua squadra, in tutti i bot (questo, aste, loucabot, IPanchinari): chi, quando, cosa, com'era prima e com'è dopo. Ci sono le tue operazioni e quelle degli admin sulla tua squadra (una trade compare per tutte le squadre coinvolte). Puoi restringere: `/registro 7` (ultimi 7 giorni), `/registro taglio`, `/registro LeBron`, `/registro aste`. Le azioni prima di questa funzione non ci sono.

## In breve

| Voglio… | Comando |
|---|---|
| vedere la mia squadra | `/roster`, `/assets` |
| vedere cosa è cambiato | `/team_diff` |
| fare una trade | `/build_trade` o `/import_trade` |
| vedere le mie trade | `/my_trades` |
| tagliare | menu → Tagli (`/taglia`) |
| chiedere una DPE | `/dpe` |
| attivare un rookie | `/attiva_diritti` |
| rinnovare un rookie a fine II anno | `/rinnovo_rookie` |
| dichiarare l'RFA | `/dichiara_rfa` |
| chiudere un contratto (ritiro, altra lega, Cam Thomas) | `/decadimento` |
| prendere un free agent per 10 giorni | `/firma_10day` |
| dichiarare o cambiare ruoli | `/dichiarazione_ruoli`, `/cambio_ruolo` |
| vedere chi ha fatto cosa sulla mia squadra | `/registro` |
| uscire da un'operazione bloccata | `/annulla` |
| ricevere questa guida | `/guida` |

**Nomi dei giocatori.** Dove scrivi il nome di un giocatore puoi metterlo in qualsiasi ordine («Clowney Noah» o «Noah Clowney»), senza accenti e con qualche errore di battitura: il bot propone il più simile.

## Da dove vengono i dati

- **ESPN** (le pagine pubbliche delle partite NBA): calendario e risultati NBA, i **tabellini** da cui il bot calcola i fantapunti (anche quelli live), la lista degli **infortunati**, la squadra NBA di ogni giocatore e le foto. I tabellini si ricontrollano alle 11:05 e alle 20 del giorno dopo: fino ad allora possono cambiare.
- **Basketball-Reference**: le statistiche della stagione di ogni giocatore (medie a partita), aggiornate ogni giorno alle 12. Da lì la **fantamedia** del roster, della lista dei free agent e del foglio Roster.
- **Yahoo**: la lega dove si schierano i quintetti (per il regolamento fa fede Yahoo) e le **posizioni eleggibili** dei giocatori, che decidono i ruoli.
- Tutto il resto (contratti, trade, aste, panchine, risultati, classifica) è della lega e sta nel database dei bot.

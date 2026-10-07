# Guida GM — Fantabasket Main Bot

Tutto si fa in **chat privata** col bot. In qualsiasi momento puoi anche scrivere a un admin, che può fare per te qualsiasi operazione.

## Menu principale

`/menu` apre il menu con i bottoni. Mostra **solo le azioni disponibili nella fase corrente** e indica in che fase siamo. A seconda della fase trovi Trade, Tagli, Rookie, DPE, Decadimento, Dichiarazione ruoli, Cambio ruolo; Roster e Assets ci sono sempre.

I flussi si chiudono dopo qualche minuto di inattività. `/annulla` (o `/annulla_trade`) esce da un'operazione in corso.

---

## Roster e Assets

- `/roster` — immagine del tuo roster: ruolo di ogni giocatore a sinistra, posizioni eleggibili in corsivo accanto al nome, contratti, cap, tagli gratuiti e cambi ruolo usati. Quando tutti i ruoli sono dichiarati i giocatori sono ordinati per ruolo (PG, SG, SF, PF, C), poi per contratto.
- `/roster <squadra>` — roster di qualsiasi squadra (nome squadra, nome del GM, anche parziale).
- `/roster <GG-MM-AA>` — il tuo roster a una data passata, con i ruoli di quella data.
- `/assets` — roster + pick per anno (★ proprie, ○ altrui) + diritti rookie. Il tag rosso **STEPIEN** indica una tua 1st che non puoi cedere senza violare la Stepien Rule.
- `/team_diff` — movimenti dell'ultima settimana (accetta squadra e date).
- `/palette` — personalizza i colori delle immagini.

---

## Trade

**Build** (menu → Trade → Build, o `/build_trade`): scegli le squadre e per ognuna cosa cede (giocatori, pick, diritti). Il riepilogo mostra la validazione: cap, roster, Stepien Rule e — in regular season — i **ruoli minimi** (4 guardie, 4 ali, 2 centri: deve esistere un modo di assegnare i ruoli eleggibili ai nuovi arrivati che li rispetti). Poi puoi proporla ai GM, mandarla agli admin o salvarla in bozza.

**Import** (menu → Trade → Import, o `/import_trade`): incolla il testo nel formato della lega:

```
Nome GM cede:
Giocatore 25x2
1st round pick 2027 by AltroGM
2nd round pick 2028 AltroGM
Diritti di Nome Rookie

Altro GM cede:
Giocatore 10x1
```

- Il `by` prima del GM è facoltativo; il GM si può indicare anche solo col cognome o col nome della squadra, se non è ambiguo.
- "by GM" indica il **proprietario originale** della pick: va scritta così anche se nel frattempo è passata di mano.
- Il bot controlla che pick e diritti che cedi siano **tuoi oggi**; se ci sono errori la bozza non viene salvata e ti dice cosa correggere.

`/bozze_trade` elenca le tue bozze; quando ricevi una proposta voti con ✅/❌.

---

## Tagli

Menu → Tagli → giocatore: vedi l'anteprima dell'impatto sul cap prima di confermare. 3 tagli gratuiti a stagione per i contratti 1x1; gli altri contratti vengono spalmati secondo la tabella del regolamento.

---

## DPE — Disabled Player Exception

`/dpe` (o menu → DPE) per un giocatore out for the season: per la stagione corrente il contratto scende del 25%, con la riduzione arrotondata per eccesso (5 → 3, 9 → 6, 10 → 7). Prima della deadline libera uno slot. Serve l'approvazione di un admin.

---

## Rookie

Menu → Rookie (o `/attiva_diritti`) → scegli il giocatore: il contratto è quello della rookie scale (colonna I anno, in base alla pick), devi solo confermare. I diritti delle seconde al secondo anno scadono 10 giorni prima della trade deadline.

---

## Decadimento

`/decadimento` (o menu → Decadimento) per un giocatore ritirato o andato in un altro campionato: il contratto viene annullato senza contare tra i tagli. Serve l'approvazione di un admin.

---

## Ruoli

I ruoli possibili sono PG, SG, SF, PF, C, sempre tra le **posizioni eleggibili** del giocatore su Yahoo. Ogni roster deve avere almeno 4 guardie (PG/SG), 4 ali (SF/PF) e 2 centri.

### Dichiarazione a inizio stagione (fase "Dichiarazione ruoli")

`/dichiarazione_ruoli` o 🎽 nel menu. Ogni stagione si dichiara tutto da capo.

- Tocca un giocatore e scegli il ruolo; chi ha una sola posizione è già impostato (🔒).
- Oppure **📥 Importa da testo**: un messaggio con una riga per giocatore (`LeBron SF`, `Curry PG`...). Basta nome o cognome; se il nome è incerto il bot chiede conferma, e ti segnala chi hai saltato.
- Le scelte restano in bozza finché non premi **✅ Conferma**. Puoi confermare anche una parte e completare dopo, entro la deadline.
- Il giorno prima della deadline, se non hai completato, ricevi un promemoria.
- Se ricevi o firmi un giocatore durante questa fase, comparirà da dichiarare.

### Nuovi giocatori in regular season

**Free agency:** quando vinci un'asta il bot aste ti chiede prima gli anni e poi il ruolo, tra quelli eleggibili; la conferma li mostra insieme. Se non rispondi entro 48 ore il giocatore viene firmato per 3 anni (penale) con un ruolo estratto a caso. Il ruolo compare nell'annuncio della firma.

**Trade, firme registrate dagli admin, attivazione diritti:** dopo una trade, una firma o l'attivazione dei diritti ricevi in privato un messaggio con i bottoni dei ruoli eleggibili (o solo la conferma, se ne ha uno). Lo ritrovi anche nel menu, in **🎽 Ruoli da dichiarare**.

- Hai **48 ore**, poi il ruolo viene estratto a caso tra quelli eleggibili.
- Se riprendi un giocatore che hai avuto negli ultimi **60 giorni**, torna automaticamente col suo vecchio ruolo.
- I ruoli non passano da una squadra all'altra: chi riceve il giocatore dichiara il suo.

### Cambi ruolo (regular season e playoff)

`/cambio_ruolo` o 🔁 nel menu → giocatore → nuovo ruolo. Il bot mostra solo i tipi possibili:

- **Ordinario** — massimo 2 a stagione (contatore su `/roster` e sul foglio); chiede una conferma.
- **Erminio (ruolo aggiunto)** — gratuito, se Yahoo ha aggiunto quel ruolo al giocatore negli ultimi 14 giorni (lo vedi segnato con ✨). Quando è disponibile, l'ordinario non viene proposto.
- **Saedro (10 day)** — cambio temporaneo di 10 giorni, una volta a stagione, quando non hai giocatori disponibili in quel ruolo: la richiedi e la approvano gli admin. Alla scadenza il giocatore torna nel ruolo originale da solo.

I cambi che farebbero scendere il roster sotto i minimi (4G/4F/2C) vengono bloccati. Ogni cambio viene annunciato sul canale.

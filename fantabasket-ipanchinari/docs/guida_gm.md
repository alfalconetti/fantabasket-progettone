# Guida GM — IPanchinari

IPanchinari è il bot delle panchine e dei quintetti. Si usa in **chat privata**: scrivigli `/start` una volta, così può mandarti i promemoria.

---

## La panchina

Mandala al bot **come l'hai sempre scritta**: un panchinaro per riga, in ordine, soprannomi compresi. Se vuoi un titolo, mettilo sopra e lascia una riga vuota:

```
No Buffalo Brownies

Ja the sniper Morant
Dominik Arcade Boy Barlow
Walter White Clayton jr
Nique il califfo Clifford
Kevon the champ Looney
```

Il bot ti risponde con l'anteprima: accanto a ogni riga il giocatore che ha capito.

- Se una riga non l'ha capita (❓), sotto l'anteprima trovi già i bottoni con i giocatori possibili per quella riga ("2: Jalen Williams", "2: Jalen Brunson"): un tocco e la riga è a posto. Se non c'è quello giusto, "📋 altri" ti mostra tutta la rosa. La volta dopo quel soprannome lo riconosce da solo.
- Se ha capito male, tocca ✏️ e il numero della riga per correggerla.
- Quando è tutto giusto tocca **✅ Pubblica**: sul canale Panchinari escono **le tue righe come le hai scritte** (e il titolo), senza i nomi veri.

La panchina vale per **la prossima giornata**, quella la cui scadenza (la prima partita NBA) non è ancora passata. Fino alla scadenza puoi rimandarla quante volte vuoi: vale l'ultima, e sul canale il bot modifica il messaggio della tua panchina (con la scritta 🔁 aggiornata) invece di mandarne uno nuovo.

Il bot non pubblica se un giocatore non è della tua squadra, se c'è due volte o se la scadenza è passata (anche mentre stavi confermando). Se un panchinaro risulta titolare nel quintetto del bot, te lo segnala ma pubblica lo stesso: per il quintetto fa fede Yahoo, quindi puoi aggiornarlo con `/quintetto` oppure lasciare che se ne occupi un admin.

**Coi bottoni.** Se preferisci, `/build_panchina`: scegli i panchinari uno alla volta, in ordine. Ti propone solo i giocatori della tua squadra che non sono nel quintetto e non hai già scelto; ↩️ toglie l'ultimo, ➡️ Anteprima ti porta all'anteprima con Pubblica. Sul canale escono i nomi dei giocatori, a meno che non usi la CAI mode.

**😎 CAI mode.** Nell'anteprima del builder c'è il bottone 😎 CAI mode: il bot ti chiede il titolo e poi il soprannome di ogni panchinaro, uno alla volta. Scrivili come messaggio; ⏭️ Salta lascia quello che c'è, ✅ Fine torna subito all'anteprima. Sul canale escono titolo e soprannomi, e il bot se li ricorda anche per quando mandi la panchina come messaggio. Se a metà ci ripensi e mandi una panchina intera come messaggio, vale quella.

`/panchina` ti mostra la panchina che hai mandato, coi nomi veri.

---

## Il quintetto

Il quintetto **non va rimandato ogni giornata**: resta quello finché non lo cambi. È un giocatore per ruolo (PG, SG, SF, PF, C), ognuno nel suo ruolo di roster.

**Il promemoria.** Alle 8 di mattina dell'ultimo giorno prima della giornata (se si gioca di notte, la mattina prima) il bot ti manda il tuo quintetto con le partite di ogni titolare nella giornata, e due bottoni:

- **✅ Confermo**: va bene così;
- **✏️ Modifico**: si apre il quintetto e cambi chi vuoi.

I bottoni valgono fino alla scadenza della giornata. Se non fai niente, gli admin controllano il tuo quintetto su Yahoo.

**`/quintetto`** te lo mostra quando vuoi: tocca il ruolo da cambiare e scegli il giocatore (ti propone solo quelli di quel ruolo).

Se qualcosa non torna (un titolare che non è più in squadra, che hai messo anche in panchina, un ruolo vuoto) il bot te lo segnala. Non sei obbligato a sistemarlo nel bot: per il quintetto fa fede Yahoo, e se non lo fai tu ci pensa un admin.

---

`/start` ti ricorda come si usa, `/guida` ti manda questa guida.

Se qualcosa non va, scrivi a un admin: può mettere panchina e quintetto al posto tuo.

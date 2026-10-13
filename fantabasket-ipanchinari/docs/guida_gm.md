# Guida GM — IPanchinari

IPanchinari è il bot delle panchine e dei quintetti. Si usa in **chat privata**: scrivigli `/start` una volta, così può mandarti i promemoria.

In breve: **la panchina è obbligatoria** (sempre 5 giocatori, mai meno). **Il quintetto nel bot no**: per il regolamento fa fede Yahoo, e tenerlo aggiornato qui è un favore che fai agli admin.

---

## La panchina

Mandala al bot **come l'hai sempre scritta**: un panchinaro per riga, in ordine, soprannomi compresi. **Sempre 5 giocatori, mai meno**: con meno righe il bot non la prende. Se vuoi un titolo, mettilo sopra e lascia una riga vuota:

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
- Quando è tutto giusto tocca **✅ Pubblica**: sul canale Panchinari escono **le tue righe come le hai scritte** (e il titolo), senza i nomi veri. In fondo al messaggio c'è chi l'ha inserita (GM, o quale admin) e il giorno e l'ora dell'ultima modifica.

La panchina vale per **la prossima giornata**, quella la cui scadenza (la prima partita NBA) non è ancora passata. Fino alla scadenza puoi rimandarla quante volte vuoi: vale l'ultima, e sul canale il bot modifica il messaggio della tua panchina (in fondo "🔁 ultima modifica" con l'ora) invece di mandarne uno nuovo.

Il bot non prende una panchina con **righe duplicate** (la stessa riga scritta due volte, anche con maiuscole diverse): ogni panchinaro va scritto in modo diverso. Non pubblica se i giocatori non sono 5, se uno non è della tua squadra, se c'è due volte o se la scadenza è passata (anche mentre stavi confermando). Se un panchinaro risulta titolare nel quintetto del bot, te lo segnala ma pubblica lo stesso: per il quintetto fa fede Yahoo, quindi puoi aggiornarlo con `/quintetto` (non sei obbligato: è un favore agli admin) oppure lasciare che se ne occupi un admin.

**Coi bottoni.** Se preferisci, `/build_panchina`: scegli i panchinari uno alla volta, in ordine. Ti propone solo i giocatori della tua squadra che non sono nel quintetto e non hai già scelto (i titolari, segnati ⭐, solo se non ne restano abbastanza); ↩️ toglie l'ultimo. Al quinto passa da solo all'anteprima con Pubblica. Sul canale escono i nomi dei giocatori, a meno che non usi la CAI mode.

**😎 CAI mode.** Nell'anteprima del builder c'è il bottone 😎 CAI mode: il bot ti chiede il titolo e poi il soprannome di ogni panchinaro, uno alla volta. Scrivili come messaggio; ⏭️ Salta lascia quello che c'è, ✅ Fine torna subito all'anteprima. Sul canale escono titolo e soprannomi, e il bot se li ricorda anche per quando mandi la panchina come messaggio. Se a metà ci ripensi e mandi una panchina intera come messaggio, vale quella.

**Infortunati.** Nei bottoni del builder, nella scelta del quintetto, nell'anteprima e nel promemoria accanto a ogni giocatore c'è il suo stato sulla lista infortunati di ESPN (🔴 Out, 🟠 Doubtful, 🟡 Questionable o Day-To-Day, 🟢 Probable; niente se è sano), con l'ora dell'ultimo aggiornamento (ogni 4 ore, e mezz'ora prima della prima partita del giorno). È solo un aiuto: per il calcolo valgono le regole del regolamento.

`/panchina` ti mostra la panchina che hai mandato, coi nomi veri.

**I soprannomi.** Ogni riga che confermi diventa un soprannome che il bot riconosce da solo la volta dopo. `/soprannomi` te li mostra, giocatore per giocatore; con 🗑 cancelli quelli sbagliati o che non usi più. `/soprannomi SQUADRA` ti fa vedere quelli di un'altra squadra, solo da guardare. I soprannomi **seguono il giocatore**: se lo cedi valgono per la sua squadra nuova (accanto c'è scritto chi li ha inventati), se lo prendi tu valgono quelli che gli aveva dato il vecchio GM.

**Se cedi o tagli un giocatore** che avevi in panchina o nel quintetto del bot, il bot ti avvisa (e lo segna sul canale log):
- era nella panchina della prossima giornata → **rimandala** con 5 giocatori della tua squadra prima della scadenza;
- era nel quintetto → se vuoi aggiornalo con `/quintetto` (non è obbligatorio, fa fede Yahoo: è un favore agli admin);
- era nella giornata in corso → ne tiene conto un admin.

---

## Il quintetto

**Aggiornare il quintetto nel bot non è obbligatorio**: per il regolamento fa fede Yahoo. Se lo tieni aggiornato qui fai un favore agli admin, che altrimenti lo controllano su Yahoo.

Il quintetto **non va rimandato ogni giornata**: resta quello finché non lo cambi. È un giocatore per ruolo (PG, SG, SF, PF, C), ognuno nel suo ruolo di roster.

**Il promemoria.** Alle 8 di mattina dell'ultimo giorno prima della giornata (se si gioca di notte, la mattina prima) il bot ti manda il tuo quintetto con le partite di ogni titolare nella giornata, e due bottoni:

- **✅ Confermo**: va bene così;
- **✏️ Modifico**: si apre il quintetto e cambi chi vuoi.

I bottoni valgono fino alla scadenza della giornata. Se non fai niente non succede niente di male: gli admin controllano il tuo quintetto su Yahoo.

**`/quintetto`** te lo mostra quando vuoi: tocca il ruolo da cambiare e scegli il giocatore (ti propone solo quelli di quel ruolo).

Se qualcosa non torna (un titolare che non è più in squadra, che hai messo anche in panchina, un ruolo vuoto) il bot te lo segnala. Non sei obbligato a sistemarlo nel bot: per il quintetto fa fede Yahoo, e se non lo fai tu ci pensa un admin.

---

`/start` ti ricorda come si usa, `/guida` ti manda questa guida.

Se qualcosa non va, scrivi a un admin: può mettere panchina e quintetto al posto tuo.

# Guida admin — IPanchinari

Da admin carichi i quintetti, controlli conferme e panchine prima della scadenza e puoi mettere panchina e quintetto per conto di una squadra. I comandi admin funzionano in privato e nel gruppo admin.

---

## Canali

- **Canale Panchinari** (`canale_panchinari_id` in `globals.json`): il bot deve esserne amministratore e poter pubblicare. Ci escono le panchine come le scrivono i GM.

  **Cambiare canale** (per esempio dal canale di prova a quello vero): metti il nuovo id in `globals.json` (vale subito, senza riavvio), aggiungi il bot come amministratore del canale nuovo e lancia **`/ripubblica_panchine`**: tutte le panchine già mandate per la prossima giornata escono sul canale nuovo, ognuna con chi l'ha inserita e l'ora dell'ultima modifica (`/ripubblica_panchine N` per la giornata N). Il bot ne manda una ogni 3,5 secondi per il limite di Telegram (24 panchine ≈ un minuto e mezzo) e ti avvisa quando ha finito. Da lì le modifiche vanno sui messaggi nuovi; quelli del canale vecchio non li tocca più.
- **Gruppo admin** (`admin_group_id`): riepilogo 2 ore prima della scadenza e avviso di chiusura con le panchine mancanti. Il bot deve essere nel gruppo.
- **Canale log** (`log_channel_id_ipa`; senza, quello del bot principale): avvio, errori, ogni panchina (coi nomi veri), conferme e cambi di quintetto, import, promemoria, chiusure.

---

## I quintetti

**A inizio stagione** si caricano tutti:

```
/quintetti_import
Buffalo Brownies
PG Jalen Brunson
SG Devin Booker
SF Mikal Bridges
PF Grant Williams
C Mark Williams

Alfa
...
```

Per ogni squadra il nome esatto (o l'id) nella prima riga, poi i 5 titolari, con o senza il ruolo davanti; squadre separate da una riga vuota. Va bene anche un file .txt con didascalia `/quintetti_import`. Il nome della squadra deve essere esatto: in un import di tante squadre una ricerca tollerante potrebbe sbagliare squadra. Le squadre con un errore non si salvano, le altre sì, e il bot dice quali.

**Una squadra alla volta**: `/quintetto_admin SQUADRA` e sotto i 5 titolari (qui il nome della squadra può essere approssimativo: il bot risponde col nome giusto). **Senza righe si apre il quintetto della squadra coi bottoni**, partendo da quello attuale: tocchi il ruolo e scegli il giocatore (solo quelli di quel ruolo). Vale come le righe: anche a giornata in corso aggiorna la formazione della giornata.

Il ruolo di ogni titolare è quello di roster: un giocatore scritto in un ruolo diverso, due giocatori nello stesso ruolo o un ruolo mancante bloccano il salvataggio.

**Durante la stagione**: alle 8 dell'ultimo giorno prima della giornata i GM ricevono il promemoria e confermano o modificano. **2 ore prima della scadenza** nel gruppo admin arriva il riepilogo:

- ✅ confermato · ✏️ modificato · — niente: le squadre con "—" sono quelle di cui controllare il quintetto su Yahoo (con `/quintetto_admin`). Se lo controlli tu prima della scadenza, nell'editor di `/quintetto_admin SQUADRA` c'è **✅ Conferma per la giornata N (admin)**: la squadra passa a ✅ come se avesse confermato il GM;
- 🪑 panchina mandata · ❌ mancante;
- ⚠️ incompatibilità (titolare non più in squadra o in un altro ruolo, anche in panchina, ruolo vuoto).

`/stato` (o `/stato N`) lo mostra quando vuoi.

**`/report_formazioni`** (o `/report_formazioni N`) manda un file Markdown con quintetti e panchine di tutte le squadre per la prossima giornata (o la N; quella in corso se non ce n'è una aperta), da usare prima della scadenza per sollecitare i GM. Prima della scadenza mostra i quintetti di adesso, a giornata chiusa le formazioni congelate. In cima: panchine mancanti, quintetti non confermati e una riga per squadra con l'avversaria e quanti titolari e panchinari hanno problemi. Poi, squadra per squadra, ogni giocatore con squadra NBA, partite della giornata, stato degli infortunati (ultimo snapshot ESPN) e le note che contano per il calcolo: posto vuoto, panchina non mandata, Out/Doubtful/Questionable, squadra NBA senza partite (media), senza id ESPN (0 punti), non più in squadra, ruolo cambiato, titolare anche in panchina, panchinario non abbinato, panchina di lunghezza sbagliata. Non cambia niente.

**`/quintetti`** mostra tutti i quintetti attuali, una riga per squadra (`PG … · SG … · SF … · PF … · C …`; ⚠️ accanto a un giocatore non più in squadra, — per un ruolo vuoto). **`/quintetti N`** mostra invece le formazioni congelate della giornata N, quelle che usa il calcolo.

**Alla scadenza** i quintetti si congelano: sono quelli della giornata per il calcolo. Nel gruppo admin arriva l'elenco delle squadre senza panchina (penalità) e, se ci sono, le **panchine con giocatori non più in squadra** alla scadenza (ceduti o tagliati prima, secondo il registro del bot principale: penalità, decidete voi; nel calcolo escono dalla panchina e gli altri scalano) e i **titolari non più in squadra** (nel calcolo contano finché non correggete il quintetto da Yahoo). Chi viene ceduto dopo la scadenza conta per la vecchia squadra fino a fine giornata.

**Dopo la scadenza: tenere il segno dei controlli.** **`/controlli`** (o `/controlli N`) mostra le formazioni congelate della giornata in corso (o della N), una per squadra, con ☑️ controllata (chi e quando) o ⬜ da controllare, e accanto lo stato del GM (✅ ✏️ —). Sotto c'è un bottone per squadra: lo tocchi quando hai controllato quella formazione su Yahoo (un altro tocco toglie il segno), 🔄 aggiorna. Se correggi una formazione (`/quintetto_admin SQUADRA`, anche coi bottoni, o `/quintetto_admin SQUADRA G5`) si segna controllata da sola. Lo stesso segno c'è nell'editor di `/quintetto_admin SQUADRA` (☑️ Segna controllata) e in `/stato N` a giornata chiusa.

**Non serve fare tutto prima della scadenza.** I quintetti si correggono anche a giornata in corso:
- `/quintetto_admin SQUADRA` con i 5 titolari cambia il quintetto e, se c'è una giornata in corso, anche la sua formazione (quella del calcolo);
- `/quintetto_admin SQUADRA G5` con i 5 titolari corregge solo la formazione della giornata 5 (già chiusa), senza toccare il quintetto attuale.

Per il quintetto fa fede Yahoo: i GM non sono obbligati a tenerlo aggiornato nel bot (il bot lo ripete ovunque: è un favore agli admin). Se un GM mette in panchina un giocatore che nel bot è titolare, la panchina si pubblica lo stesso; il GM riceve un avviso e a te arriva una riga ⚠️ sul canale log.

---

## Le panchine

I GM le mandano al bot in privato come le hanno sempre scritte (vedi la guida GM); il bot le pubblica sul canale con le loro righe. Per conto di una squadra:

```
/panchina_admin Buffalo Brownies
Ja the sniper Morant
Dominik Arcade Boy Barlow
...
```

Stessa anteprima e stessi bottoni del GM; sul canale, in fondo al messaggio, c'è scritto "✍️ admin" col tuo nome e l'ora (per le panchine dei GM "✍️ GM"), e nel log risulta fatta da te. **Senza righe** (`/panchina_admin SQUADRA`) si apre il builder coi bottoni di quella squadra, con la 😎 CAI mode.

La panchina è sempre di 5 giocatori: con meno righe il bot non la prende, il builder pubblica solo al quinto.

Una panchina che arriva dopo la scadenza vale per la giornata successiva: per quella appena chiusa decidono gli admin.

**Correggere la panchina di una giornata già chiusa** (per il calcolo): `/panchina_admin SQUADRA G5` e sotto le righe (o senza righe, col builder). Si pubblica anche a scadenza passata (sul canale si aggiorna il messaggio), i ruoli dei panchinari si congelano di nuovo, e il bot ricorda di lanciare `/ricalcola 5` su loucabot.

Alla scadenza, insieme ai quintetti, si congela anche il **ruolo di ogni panchinaro** (quello di quel momento): la FADD della giornata usa quello, anche se poi il ruolo cambia.

---

## Trade e tagli

Ogni 5 minuti il bot confronta quintetti e panchine con le rose. Un giocatore che non è più in squadra (trade o taglio nel bot principale) ed era schierato fa partire un avviso ai GM della squadra e una riga 🔁 sul canale log, una volta sola:
- **panchina della prossima giornata**: il GM la deve rimandare (finché non lo fa, nell'anteprima e in `/panchina` il giocatore risulta fuori squadra);
- **quintetto del bot**: aggiornarlo non è obbligatorio, il riepilogo lo segna tra le incompatibilità;
- **formazione o panchina della giornata in corso**: decidete voi (`/quintetto_admin SQUADRA G N` per la formazione).

## Soprannomi

`/soprannomi SQUADRA` mostra i soprannomi che il bot riconosce per i giocatori di una squadra e permette di cancellarli (i GM con lo stesso comando li possono solo guardare). Seguono il giocatore: dopo una trade valgono per la squadra nuova.

---

## Comandi

| Comando | Cosa fa |
|---|---|
| `/stato [N]` | conferme dei quintetti e panchine della giornata |
| `/report_formazioni [N]` | file .md con quintetti e panchine di tutte le squadre e i problemi (vedi sopra) |
| `/quintetti [N]` | tutti i quintetti attuali, una riga per squadra; con N le formazioni della giornata N |
| `/quintetto_admin SQUADRA [GN]` | quintetto di una squadra: senza righe coi bottoni, o 5 righe sotto (anche a giornata in corso); con GN corregge la formazione della giornata N |
| `/quintetti_import` | quintetti di tutte le squadre |
| `/panchina_admin SQUADRA [GN]` | panchina per conto di una squadra: senza righe col builder, o le righe sotto; con GN corregge quella della giornata N, già chiusa |
| `/soprannomi SQUADRA` | soprannomi di una squadra, da vedere o cancellare |
| `/ripubblica_panchine [N]` | tutte le panchine della prossima giornata (o della N) di nuovo sul canale, per esempio dopo un cambio di canale |
| `/guida_admin` | questa guida |

## Registro delle azioni

Le azioni che cambiano qualcosa (panchine e quintetti mandati, confermati, cambiati o corretti, anche per conto di una squadra, formazioni controllate, import, panchine ripubblicate, soprannomi cancellati, chiusura della giornata) lasciano una riga nel registro unico di tutti i bot: chi, in che veste (gm, admin, dev, sistema), cosa, prima → dopo. Sul canale log restano le righe di sempre, col nome di chi. Il registro si consulta dal bot principale (comando registro, o pannello admin → 📜 Registro); i GM vedono le righe della loro squadra.

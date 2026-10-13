# Guida admin — IPanchinari

Da admin carichi i quintetti, controlli conferme e panchine prima della scadenza e puoi mettere panchina e quintetto per conto di una squadra. I comandi admin funzionano in privato e nel gruppo admin.

---

## Canali

- **Canale Panchinari** (`canale_panchinari_id` in `globals.json`): il bot deve esserne amministratore e poter pubblicare. Ci escono le panchine come le scrivono i GM.
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

- ✅ confermato · ✏️ modificato · — niente: le squadre con "—" sono quelle di cui controllare il quintetto su Yahoo (con `/quintetto_admin`);
- 🪑 panchina mandata · ❌ mancante;
- ⚠️ incompatibilità (titolare non più in squadra o in un altro ruolo, anche in panchina, ruolo vuoto).

`/stato` (o `/stato N`) lo mostra quando vuoi.

**Alla scadenza** i quintetti si congelano: sono quelli della giornata per il calcolo. Nel gruppo admin arriva l'elenco delle squadre senza panchina (penalità).

**Non serve fare tutto prima della scadenza.** I quintetti si correggono anche a giornata in corso:
- `/quintetto_admin SQUADRA` con i 5 titolari cambia il quintetto e, se c'è una giornata in corso, anche la sua formazione (quella del calcolo);
- `/quintetto_admin SQUADRA G5` con i 5 titolari corregge solo la formazione della giornata 5 (già chiusa), senza toccare il quintetto attuale.

Per il quintetto fa fede Yahoo: i GM non sono obbligati a tenerlo aggiornato nel bot. Se un GM mette in panchina un giocatore che nel bot è titolare, la panchina si pubblica lo stesso; il GM riceve un avviso e a te arriva una riga ⚠️ sul canale log.

---

## Le panchine

I GM le mandano al bot in privato come le hanno sempre scritte (vedi la guida GM); il bot le pubblica sul canale con le loro righe. Per conto di una squadra:

```
/panchina_admin Buffalo Brownies
Ja the sniper Morant
Dominik Arcade Boy Barlow
...
```

Stessa anteprima e stessi bottoni del GM; sul canale esce come se l'avesse mandata lui (nel log risulta fatta da un admin). **Senza righe** (`/panchina_admin SQUADRA`) si apre il builder coi bottoni di quella squadra, con la 😎 CAI mode.

Una panchina che arriva dopo la scadenza vale per la giornata successiva: per quella appena chiusa decidono gli admin.

---

## Comandi

| Comando | Cosa fa |
|---|---|
| `/stato [N]` | conferme dei quintetti e panchine della giornata |
| `/quintetto_admin SQUADRA [GN]` | quintetto di una squadra: senza righe coi bottoni, o 5 righe sotto (anche a giornata in corso); con GN corregge la formazione della giornata N |
| `/quintetti_import` | quintetti di tutte le squadre |
| `/panchina_admin SQUADRA` | panchina per conto di una squadra: senza righe col builder, o le righe sotto |
| `/guida_admin` | questa guida |

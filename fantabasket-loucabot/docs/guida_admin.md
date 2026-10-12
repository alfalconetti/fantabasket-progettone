# Guida admin — loucabot

Da admin in loucabot gestisci il calendario della stagione e controlli i punteggi. I comandi admin funzionano in privato e nel gruppo admin, e compaiono nel menu `/` solo lì.

Gli admin sono quelli di `admin_ids` in `globals.json`, gli stessi degli altri bot.

---

## Canali

- **Gruppo admin** (`admin_group_id`): qui arrivano solo i cambi che contano per la lega, cioè una scadenza che si sposta o le squadre a media di una giornata che cambiano. loucabot deve essere nel gruppo.
- **Canale log** (`log_channel_id_louca` in `globals.json`; senza, quello del bot principale): la parte tecnica. Ci vanno avvio ed errori, ogni import del calendario, ogni `/nba_sync`, `/tabellini`, `/espn_giocatori`, ogni abbinamento a mano e la sincronizzazione delle 8:30, anche quando non cambia niente (così si vede che gira).

---

## Il calendario

**A inizio stagione:**

1. Manda il CSV del calendario come file, con didascalia `/importa_calendario`. Va bene anche rispondere con `/importa_calendario` al messaggio che contiene il file. Un nuovo import sostituisce il calendario di regular season della stagione, senza doppioni.
2. `/nba_sync`: scarica da ESPN tutte le partite NBA della stagione (qualche minuto).
3. `/calendario_check`: scadenza di ogni giornata e squadre a media, con il confronto tra quelle scritte nel CSV e quelle calcolate dalle partite NBA.

**Il CSV** è quello degli admin: per ogni giornata una riga `Week N gg/mm - gg/mm (media XXX,YYY)` e sotto le partite `Casa,,V,,Trasferta`. Le squadre si riconoscono solo per nome esatto (senza maiuscole e accenti) o per id, come in `teams.json`. Se un nome non c'è, il bot propone il più simile ma non importa niente. Controlli: giornate da 1 in ordine e senza sovrapposizioni, ogni squadra una volta per giornata.

**Squadre a media.** Vale il calcolo dalle partite NBA, che è quello che vedono i GM. Se `/calendario_check` mostra differenze, correggi le note nel CSV e reimportalo, così anche il calendario pubblicato torna giusto.

**Ogni mattina alle 8:30** il bot riscarica le partite dei giorni vicini (da 3 giorni fa a 2 settimane avanti) e ricalcola. Se in una giornata non ancora finita cambiano la prima partita o le squadre a media, arriva un avviso al gruppo admin.

---

## I punteggi

**Tabellini.** A partita finita il bot scarica da ESPN il tabellino e salva statistiche e fantapunti di ogni giocatore NBA. Lo fa alle 8:30; `/tabellini` lo fa subito, per le partite finite che ancora non ce l'hanno.

**Infortunati.** ESPN dà solo lo stato di adesso, quindi il bot ne salva una foto alle 8:30, alle 17:30 e alle 23:30 (anche con `/tabellini`). Servono per due regole:
- chi è in una squadra a media prende 0 invece della media se in tutte le foto della giornata risulta indisponibile (stato diverso da Probable);
- la FADD (il panchinaro che entra al posto del titolare che non ha giocato): il titolare deve avere il tag in tutti i giorni in cui la sua squadra ha giocato. Se manca la foto di uno di quei giorni il bot non sostituisce e lo segnala: decide un admin.

**Giocatori e id ESPN.** Il calcolo collega i giocatori dell'anagrafica a ESPN con l'id ESPN, non col nome. L'abbinamento è automatico quando il nome è uguale (senza accenti, punteggiatura, Jr./III) e corrisponde a un solo giocatore.
- `/espn_giocatori` scarica i roster delle 30 squadre e abbina. Si rifà ogni tanto, per esempio dopo il mercato NBA.
- `/espn_mancanti` elenca i giocatori a roster nella lega senza id ESPN, con i nomi ESPN più simili.
- `/espn_abbina ID_GIOCATORE ID_ESPN` abbina a mano. L'id del giocatore è quello di `/espn_mancanti`; l'id ESPN è il numero nell'indirizzo della pagina del giocatore su espn.com (`…/player/_/id/4432174/cam-thomas`). Attenzione ai suggerimenti: sono solo nomi simili, non per forza giusti.

**`/fantapunti [N]`** mostra i fantapunti della giornata di tutti i giocatori a roster, divisi per squadra (📉 = ha preso la media). Serve per controllare il calcolo. Se è lungo arriva come file.

**Come si calcola** (regolamento, capitolo Partita):
- chi ha giocato una o più partite della giornata → media delle partite giocate;
- chi non ha giocato, se la sua squadra NBA non aveva partite (o solo partite rinviate) → la sua media della stagione, 0 se indisponibile;
- chi non ha giocato mentre la sua squadra sì → 0;
- squadra: somma dei 5 titolari, con la FADD; vince chi ha almeno 5 punti di scarto, bonus casa compreso (3, nei playoff 5); altrimenti supplementari con i panchinari in ordine; pari fino al decimo uomo → vince la trasferta.

Restano agli admin le 72 ore di attesa per le partite rinviate e le penalità.

---

## Comandi

| Comando | Cosa fa |
|---|---|
| `/importa_calendario` | importa il CSV (didascalia del file, o in risposta al file) |
| `/calendario_check` | scadenze e squadre a media, confronto col CSV |
| `/nba_sync` | riscarica le partite NBA della stagione |
| `/tabellini` | tabellini mancanti e foto degli infortunati |
| `/espn_giocatori` | roster NBA da ESPN e abbinamento automatico |
| `/espn_mancanti` | giocatori a roster senza id ESPN |
| `/espn_abbina ID_GIOCATORE ID_ESPN` | abbinamento a mano |
| `/fantapunti [N]` | fantapunti della giornata, per squadra |
| `/calendario [N]`, `/giornata [N]` | come i GM |
| `/guida_admin` | questa guida |

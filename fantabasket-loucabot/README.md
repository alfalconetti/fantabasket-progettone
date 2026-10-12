# loucabot

Il bot del campionato: il **calendario** (giornate e partite della lega, sincronizzate con il
calendario NBA) e il **calcolo dei fantapunti** dai tabellini di ESPN. Poi classifica, calendario
dei playoff dalla classifica e risultati automatici, quando ci saranno quintetti e panchine. Le formazioni e le panchine saranno in un bot a parte.

Fa parte del progettone: stesso PostgreSQL e stessa `config/` dei due bot (in sola lettura),
moduli condivisi in `../shared/`. Legge le tabelle degli altri bot, scrive solo le sue
(`lega_giornate`, `lega_partite`, `nba_partite`, `nba_tabellini`, `nba_infortuni`, `nba_atleti`), più id e nome ESPN nell'anagrafica
(`giocatori.espn_id`, `nome_espn`).

Sviluppato con [Claude](https://claude.ai) (Anthropic).

## Messa in funzione (una volta)

1. Su Telegram, da @BotFather crea un bot nuovo (comando newbot), con nome e username a piacere, e copia il token.
2. Sul server, dalla cartella del progettone:
   ```bash
   printf '%s' 'IL_TOKEN' > secrets/bot_token_loucabot.txt && chmod 600 secrets/bot_token_loucabot.txt
   bash scripts/cifra_secrets.sh          # così il token finisce nel backup cifrato
   ```
   Il token va creato **prima** del deploy della v4.0.0: `deploy.sh` controlla che ci siano tutti
   i file di `secrets/` richiesti dal `docker-compose.yml` e si ferma se ne manca uno.
3. Canali, in `config/globals.json` (si rilegge a ogni messaggio, non serve riavviare):
   - aggiungi loucabot al **gruppo admin** (`admin_group_id`): lì arrivano solo i cambi di
     scadenze e squadre a media;
   - crea un **canale log** per loucabot, aggiungi il bot come amministratore che può pubblicare e
     metti l'id in `"log_channel_id_louca"`. Lì vanno avvio, errori, import del calendario, ogni
     `/nba_sync` e la sincronizzazione delle 8:30. Finché la chiave non c'è, usa il canale log del
     bot principale (`log_channel_id_main`).
4. Dopo il deploy, a un admin:
   - manda il CSV del calendario con didascalia `/importa_calendario`;
   - `/nba_sync` scarica da ESPN le partite NBA della stagione (qualche minuto);
   - `/calendario_check` mostra scadenze e squadre a media e le confronta con il calendario.

## Il calendario

**Il file** è il CSV pubblicato dagli admin: una riga `Week N gg/mm - gg/mm (media XXX,YYY)` per
giornata e sotto le partite `Casa,,V,,Trasferta`. Le squadre si riconoscono per nome esatto (senza
maiuscole e accenti) come in `teams.json`; se un nome non c'è il bot propone il più simile e
non importa niente. Controlli: giornate da 1 in ordine e senza sovrapposizioni, ogni squadra una
volta per giornata. Un nuovo import sostituisce il calendario di regular season della stagione.

**Le partite NBA** vengono da ESPN (`site.api.espn.com`, pubblico, senza chiave): giorno (ora
della costa est, come nei calendari NBA), ora d'inizio, squadre, stato. Una risposta contiene
anche l'elenco dei giorni con partite della stagione, quindi `/nba_sync` sa cosa scaricare. Ogni
mattina alle 8:30 il bot riscarica i giorni vicini (da 3 giorni fa a 2 settimane avanti). NBA.com
dal server risponde 403; Basketball-Reference ha le stesse informazioni in HTML ed è la riserva.

**Per ogni giornata** il bot calcola:
- la **scadenza della formazione**: l'ora della prima partita NBA della giornata;
- le **squadre a media**: quelle senza partite nella giornata (regolamento: prendono la media);
  le partite rinviate non contano. Contano solo le 30 squadre NBA: le partite della NBA Cup con
  le squadre ancora da decidere ("TBD" su ESPN) valgono per la scadenza ma TBD non è una squadra.

Se il calendario e il calcolo non coincidono vale il calcolo, che è quello che vedono i GM.

Se in una giornata non ancora finita cambia la prima partita o cambiano le squadre a media, il
gruppo admin riceve un avviso. `/calendario_check` confronta le squadre a media calcolate con
quelle scritte nel calendario.

## Il calcolo

**Tabellini.** A partita finita (sincronizzazione delle 8:30, o `/tabellini`) il bot scarica da ESPN
il tabellino (`summary?event=ID`) e salva per ogni giocatore statistiche e fantapunti. Ogni
partita si scarica una volta sola. Formula del regolamento: punto +0,5, assist +2, rimbalzo
offensivo +2, difensivo +1,25, tripla +1,5, tiro dal campo tentato −0,5 e segnato +1, libero
tentato −0,75 e segnato +1, recupero +2, stoppata +2, palla persa −2. Verificata il 12/10/2026
sul vecchio foglio: tutte le 141 righe del 17/01/2026 uguali al centesimo.

**Infortunati.** ESPN dà solo lo stato di adesso, quindi il bot ne fa una foto alle 8:30, alle
17:30 e alle 23:30 (prima delle partite della sera); per ogni giorno vale l'ultima.

**Giocatore nella giornata** (`calcolo.punteggio_giocatori`):
- ha giocato → media matematica delle partite giocate nella giornata;
- non ha giocato, la sua squadra NBA non ha partite (squadre a media) o ha solo partite rinviate →
  media della stagione, ma 0 se era indisponibile (stato diverso da Probable in tutte le foto
  della giornata); senza foto prende la media, con un avviso;
- non ha giocato e la sua squadra sì → 0.

**Squadra** (`calcolo.punteggio_squadra`): somma dei 5 titolari, con la FADD: il primo panchinaro
dello stesso ruolo prende il posto di un titolare che non ha giocato e aveva il tag in tutti i
giorni in cui la sua squadra ha giocato; una sola sostituzione, la panchina scala. Se manca una
foto, decide un admin. **Partita** (`calcolo.esito`): vince chi ha almeno 5 punti di scarto, bonus
casa compreso (3, playoff 5); altrimenti supplementari con i panchinari in ordine; pari fino al
decimo uomo → vince la trasferta. Restano agli admin le 72 ore delle partite rinviate e le penalità.

**Abbinamento con l'anagrafica.** Il calcolo lavora con l'id ESPN dei giocatori, in anagrafica
(`giocatori.espn_id` e `nome_espn`):
niente errori da nomi simili. `/espn_giocatori` scarica i roster delle 30 squadre e abbina da
solo i nomi uguali (senza accenti, punteggiatura e Jr./III) quando il nome è di un solo
giocatore; ogni giorno lo stesso con i giocatori nuovi dei tabellini. Gli altri: `/espn_mancanti`
(con i nomi ESPN più simili) e `/espn_abbina ID_GIOCATORE ID_ESPN`.

## Comandi

| Comando | Chi | Cosa |
|---|---|---|
| `/calendario [N]` | GM | la tua giornata (avversario, casa o trasferta, scadenza, squadre a media) e le prossime |
| `/giornata [N]` | tutti | le partite di una giornata |
| `/guida` | tutti | l'elenco dei comandi |
| `/importa_calendario` | admin | con il CSV allegato, o in risposta al messaggio con il CSV |
| `/calendario_check` | admin | scadenze, squadre a media, confronto con il calendario |
| `/nba_sync` | admin | riscarica tutte le partite NBA della stagione |
| `/fantapunti [N]` | admin | fantapunti della giornata dei giocatori a roster, per squadra |
| `/tabellini` | admin | scarica i tabellini delle partite finite che mancano e fa una foto degli infortunati |
| `/espn_giocatori` | admin | roster NBA da ESPN e abbinamento automatico con l'anagrafica |
| `/espn_mancanti` | admin | giocatori a roster senza id ESPN, con i nomi più simili |
| `/espn_abbina ID_GIOCATORE ID_ESPN` | admin | abbinamento a mano |

## File

| File | Contenuto |
|---|---|
| `bot.py` | avvio, comandi del menu, job (8:30; infortunati 17:30 e 23:30), errori al canale log e al dev |
| `handlers.py` | i comandi del calendario, il canale log, la sincronizzazione delle 8:30 |
| `handlers_calcolo.py` | i comandi del calcolo e la foto degli infortunati |
| `calcolo.py` | punteggio del giocatore, della squadra (FADD), esito con supplementari, abbinamento ESPN |
| `calendario.py` | lettura del CSV, controlli, import, scadenze e squadre a media |
| `nba.py` | ESPN: partite, tabellini e fantapunti, infortunati, roster |
| `db.py` | PostgreSQL: tabelle di loucabot e query |
| `config.py` | `globals.json` e `teams.json` in sola lettura |

Prove: `tests/run.sh louca_calendario louca_calcolo` (calendario; tabellino vero ridotto di
NYK-SAS del 1/3/2026, formula, infortunati, partite/media/zero, FADD, supplementari, abbinamento).

## Da fare

- quintetti e panchine (bot a parte): poi risultati delle partite con `calcolo.esito`;
- classifica e risultati, con i criteri di parità del regolamento (scontri diretti, media punti,
  differenza punti: da decidere se col bonus casa);
- calendario dei playoff generato dalla classifica;
- lottery (c'è già il codice di un admin da portare qui).

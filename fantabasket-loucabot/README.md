# loucabot

Il bot del campionato. Per ora (v1) il **calendario**: giornate e partite della lega,
sincronizzate con il calendario NBA. Poi classifica, calendario dei playoff dalla classifica e
calcolo automatico dei punteggi. Le formazioni e le panchine saranno in un bot a parte.

Fa parte del progettone: stesso PostgreSQL e stessa `config/` dei due bot (in sola lettura),
moduli condivisi in `../shared/`. Legge le tabelle degli altri bot, scrive solo le sue
(`lega_giornate`, `lega_partite`, `nba_partite`).

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

## Comandi

| Comando | Chi | Cosa |
|---|---|---|
| `/calendario [N]` | GM | la tua giornata (avversario, casa o trasferta, scadenza, squadre a media) e le prossime |
| `/giornata [N]` | tutti | le partite di una giornata |
| `/guida` | tutti | l'elenco dei comandi |
| `/importa_calendario` | admin | con il CSV allegato, o in risposta al messaggio con il CSV |
| `/calendario_check` | admin | scadenze, squadre a media, confronto con il calendario |
| `/nba_sync` | admin | riscarica tutte le partite NBA della stagione |

## File

| File | Contenuto |
|---|---|
| `bot.py` | avvio, comandi del menu, job delle 8:30, errori al canale log e al dev |
| `handlers.py` | i comandi |
| `calendario.py` | lettura del CSV, controlli, import, scadenze e squadre a media |
| `nba.py` | ESPN: lettura delle risposte e sincronizzazione |
| `db.py` | PostgreSQL: tabelle di loucabot e query |
| `config.py` | `globals.json` e `teams.json` in sola lettura |

Prova: `tests/run.sh louca_calendario` (CSV, import, risposta vera di ESPN ridotta, squadre a
media, cambi, comandi).

## Da fare

- classifica e risultati, con i criteri di parità del regolamento;
- calendario dei playoff generato dalla classifica;
- calcolo automatico dei punteggi;
- lottery (c'è già il codice di un admin da portare qui).

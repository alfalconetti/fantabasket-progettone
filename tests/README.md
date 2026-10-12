# Prove dei bot

Prove "di flusso" dei due bot: girano il codice vero (handler, validatori, query) contro
un **PostgreSQL 16 locale di prova** e una **configurazione finta**, con Telegram simulato
(oggetti finti al posto di bot, messaggi e bottoni: nessuna rete, nessun token).

> ⚠️ Le prove **svuotano le tabelle** (`TRUNCATE`). Mai puntarle al database vero:
> `PGURL` deve essere un database di prova su localhost.

## Preparazione (una volta)

```bash
sudo apt install postgresql-16          # oppure qualsiasi PostgreSQL 16 locale
pip install psycopg2-binary "python-telegram-bot[job-queue]==22.*"
sudo pg_ctlcluster 16 main start
sudo -u postgres psql -c "CREATE ROLE fb LOGIN SUPERUSER PASSWORD 'fb'" \
                      -c "CREATE DATABASE fbt OWNER fb"
PGPASSWORD=fb psql -h localhost -U fb -d fbt -q -f fantabasket-main/schema.sql
PGPASSWORD=fb psql -h localhost -U fb -d fbt -q -f fantabasket-main/bref_schema.sql
```

Le tabelle aggiunte nel tempo (dpe, richieste_admin, cap_anticipato, …) le crea
`migrate_db()`, chiamato dalle prove del bot principale: per questo `run.sh` le esegue per prime.

## Esecuzione

```bash
tests/run.sh                                  # tutte
tests/run.sh trade_3_squadre cap_asta_chiusa  # solo alcune
PGURL=postgresql://utente:pw@localhost/altro_db tests/run.sh   # altro database di prova
```

Ogni prova parte da una copia pulita di `tests/config/` (alcune cambiano la fase) e da un
`aste.db` SQLite nuovo. Esito: righe ✅ / ❌ FAIL e riepilogo finale.

## Configurazione finta (`tests/config/`)

- `settings.json`: **gli stessi valori di produzione** (cap, soglie, timeout, rookie scale,
  tabella minimi) — se cambiano in produzione vanno aggiornati anche qui.
- `globals.json`: fase `offseason-fa`, stagione 2026, mercato aperto, admin `900`, chat fittizie
  (canale aste `-10`, canale principale `-1`, gruppo admin `-2`, log `-3`/`-30`).
- `teams.json`: 4 squadre `team01`–`team04` (Alfa, Beta, Gamma, Delta); GM `101`+`111`
  (due GM su team01, per le prove "secondo GM"), `102`, `103`, `104`. I campi
  `cap_disponibile`/`slot_disponibili` servono solo alle prove del bot aste in modalità isolata.
- `fa_players.csv`: lista FA per le prove senza PostgreSQL (LeBron James, Jalen/Jaylin
  Williams per gli omonimi, Kevin Durant).

## Le prove

| Prova | Bot | Cosa verifica |
|---|---|---|
| `trade_3_squadre` | main | builder a 3 squadre (destinatari, diritti multipli, doppio tap), editor con `?`, bottoni vecchi, voti e notifiche a tutte le squadre, ripresa come bozza, approvazione ed esecuzione, `/annulla_trade_admin`, parser testo a 3+ |
| `revisione_regolamento` | main | tagli 1x1 (3 gratuiti, 4° con spalmatura, minimo 10 in RS), decadimento ritiro vs altro, `/ritiro_fa`, slot all'attivazione diritti, anni in `/registra_firma` |
| `dpe_trade_tagli` | main | DPE che segue il giocatore in trade (validazione = cap reale, annullamento), taglio bloccato se scopre i ruoli in RS |
| `report_spalmature` | main | report mensile: free agent con spalmature, ultima partita bref, Cam Thomas, esclusi i sotto contratto e le stagioni passate |
| `penalita_cap` | main | `/set_cap_penalizzato`: solo admin, scrive teams.json, tetto RS ridotto e offseason a 165 |
| `sync_fogli` | main | il foglio Roster si aggiorna sempre per tutte le squadre |
| `registro_unico` | main | migrazione al registro unico (tagli pre-bot, trade rimesse approvate, storico di pick e diritti con trade annullate e pre-bot), movimenti scritti da trade/annullamento/attivazione/scadenza, `roster_attuale`, controllo di coerenza, ricostruzione che si ferma su dati incoerenti |
| `taglio_admin` | main | il taglio dal pannello admin usa lo stesso codice dei GM: anteprima, minimi di regular season, scrittura atomica, avviso al GM |
| `team_diff` | main | contratti nei due momenti, DPE, cambio contratto, niente falsi cambi tra stagioni |
| `stagione` | main | cambio di stagione: Doncic (arrotondamenti), migrazione dei contratti rookie, anteprima completa (anche chi resta uguale, stima del rinnovo), II e IV anno, fine scala con Doncic d'ufficio, x0 fuori da cap e slot, rinnovo rookie, RFA dichiarati (cap sì, slot no, uno per squadra), regola delle trade RFA, pick dell'anno +6 ai rinnovi, scadenza degli x0 a inizio FA, report di inizio RS, coerenza a ogni passo, report lunghi come file `.md` |
| `cap_condiviso` | main | `shared/cap.py`: peso sul cap e slot per in corso, x0, RFA dichiarato, DPE prima e dopo la deadline; cap con le spalmature; il bot principale dà gli stessi numeri |
| `stagione_ui` | main | bottoni di rinnovo rookie e RFA (GM e admin, fuori fase, permessi), conferma con anteprima del cambio fase, doppio tap, ritorno ai rinnovi senza far avanzare la stagione |
| `pg_rfa_30giorni_dpe` | aste + PG | RFA: cap sì slot no, lascio andare con movimento; regola dei 30 giorni; DPE nel cap per offrire; rifirma dopo taglio |
| `rfa_lascio_andare` | aste + PG | "Lascio andare": solo proprietario, una volta sola |
| `apri_asta_admin` | aste (isolato) | `/apri_asta`: nome esatto/omonimi/fuzzy, cap, squadra, importo, mercato chiuso |
| `apertura_gm` | aste (isolato) | apertura del GM passata dalla funzione comune |
| `cap_asta_chiusa` | aste (isolato) | un'asta chiusa e non firmata impegna ancora cap e slot |
| `rfa_proprietario` | aste (isolato) | il proprietario non offre sul proprio RFA neanche con `/offerta` |
| `menu_e_listteams` | aste + PG | menu "/" per fase e ruolo, `/listteams` compatto, `/reset_rfa` disattivato |
| `autoslot` | aste + PG | `/autoslot` e `/autocap` contano davvero negli slot e nel cap |
| `giocatore_id` | aste + PG | l'asta ricorda l'id del giocatore: la firma non crea doppioni se il nome cambia |
| `rfa_dichiarati` | aste + PG | x0 fuori da cap e slot, RFA dichiarato sul cap; aste RFA aperte da sole nella fase RFA, una volta sola; proprietario allineato dopo una trade; il contratto nuovo di chi vince non cambia il proprietario; DPE prima e dopo la deadline |
| `guide_e_menu` | — | ogni comando citato in guide, `/admin`, `/dev` e menu "/" esiste nel suo bot (nessun database) |
| `letture_transazioni` | — | nessuno legge `transazioni` fuori dalle funzioni ammesse (i roster si ricostruiscono da `movimenti_giocatori`) |

"Isolato" = bot aste senza PostgreSQL (`PG_URL` vuoto): cap e slot dal JSON.

## Script della dashboard

`tests/dashboard/docker_finto` simula `docker compose exec -T postgres …` girando i comandi
sul PostgreSQL locale. Per provare `scripts/setup_dashboard.sh` senza Docker:

```bash
sudo -u postgres psql -c "CREATE ROLE fantabasket LOGIN SUPERUSER PASSWORD 'x'" \
                      -c "CREATE DATABASE fantabasket OWNER fantabasket"
mkdir -p /tmp/dash/scripts /tmp/dash/secrets && cp scripts/setup_dashboard.sh /tmp/dash/scripts/
mkdir -p /tmp/shim && cp tests/dashboard/docker_finto /tmp/shim/docker && chmod +x /tmp/shim/docker
cd /tmp/dash && PATH=/tmp/shim:$PATH PGPASSWORD=x bash scripts/setup_dashboard.sh   # due volte: deve restare uguale
```

## Scrivere una prova nuova

Lo schema è sempre lo stesso: si parte dal DB svuotato, si inseriscono giocatori/contratti/
transazioni con SQL, si chiamano gli handler con oggetti finti (`types.SimpleNamespace` per
update/context, una classe `Q` con `answer` / `edit_message_text` per i bottoni, un `Bot` con
`send_message` che salva i messaggi) e si controlla il risultato con `ok(condizione, "descrizione")`.
Vedi `main/trade_3_squadre.py` come esempio completo.

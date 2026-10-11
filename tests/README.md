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
| `team_diff` | main | contratti nei due momenti, DPE, cambio contratto, niente falsi cambi tra stagioni |
| `pg_rfa_30giorni_dpe` | aste + PG | RFA: cap sì slot no, lascio andare con movimento; regola dei 30 giorni; DPE nel cap per offrire; rifirma dopo taglio |
| `rfa_lascio_andare` | aste + PG | "Lascio andare": solo proprietario, una volta sola |
| `apri_asta_admin` | aste (isolato) | `/apri_asta`: nome esatto/omonimi/fuzzy, cap, squadra, importo, mercato chiuso |
| `apertura_gm` | aste (isolato) | apertura del GM passata dalla funzione comune |
| `cap_asta_chiusa` | aste (isolato) | un'asta chiusa e non firmata impegna ancora cap e slot |
| `rfa_proprietario` | aste (isolato) | il proprietario non offre sul proprio RFA neanche con `/offerta` |
| `menu_e_listteams` | aste + PG | menu "/" per fase e ruolo, `/listteams` compatto, `/reset_rfa` disattivato |
| `guide_e_menu` | — | ogni comando citato in guide, `/admin`, `/dev` e menu "/" esiste nel suo bot (nessun database) |

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

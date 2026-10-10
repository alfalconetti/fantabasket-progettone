# 🆘 Backup e ripristino — Fantabasket Progettone

Guida unica per tutto il sistema (bot principale, bot aste, database, fogli).
Sostituisce le vecchie `DEV_RECOVERY.md`, `emergency_recovery_progettone.md` e la
guida di emergenza del bot aste.

- **Sezione 1–2**: cosa c'è nel backup e i problemi comuni sul server (dev).
- **Sezione 3**: ripristino completo, sullo stesso server o su un altro computer.
- **Sezione 4**: emergenza quando il dev non è raggiungibile (admin).

---

## 1. Il backup

C'è **un solo tipo di backup**, sempre completo, generato dal bot principale:

| Quando | Dove |
|---|---|
| Ogni giorno alle 00:00 e alle 12:00 | canale log |
| Domenica alle 00:30 | gruppo admin |
| Allo spegnimento del bot (`docker compose down`, riavvii) | canale log |
| `/backup` (solo dev) | canale log |

File `backup_progettone_AAAAMMGG_HHMM.zip`:

```
db/fantabasket.sql     database principale (contratti, trade, roster, pick, ruoli, tutto)
db/aste.db             database del bot aste (aste, offerte, firme), copia verificata e completa
config/                tutta la cartella config: globals.json, teams.json, settings.json,
                       divisions.json, tabelle/, loghi/, csv
secrets.tar.gpg        i secrets CIFRATI (se il dev li ha preparati, vedi sezione 5)
MANIFEST.txt           data, versione del bot, contenuto
```

La didascalia del backup dice se i secrets sono inclusi e di che data sono.

Il bot aste non fa più backup suoi: `/backup_ora` (bot aste) resta solo come copia
d'emergenza del suo database.

**Cosa non c'è nel backup, e non serve:**
- il codice → è su GitHub;
- il token Yahoo (`yahoo_data`) → si rifà con `docker compose exec -it yahoo-router python3 cli.py auth`;
- gli script Google Apps Script → stanno su Google e non cambiano: per riattaccarli bastano
  gli URL delle web app e il token, che sono tra i secrets.

---

## 2. Problemi comuni sul server (dev)

```bash
cd ~/bots/fantabasket-progettone
docker compose ps                         # stato dei container
docker compose logs --tail=50 bot-main    # ultimi errori (o bot-aste-beta, postgres, gas-router)
docker compose restart bot-main           # riavvio di un servizio
docker compose up -d --build              # riavvio completo con rebuild
```

- **Il mini-PC si è riavviato**: i container hanno `restart: unless-stopped` e ripartono da soli.
  Se non ripartono: `docker compose up -d`.
- **PostgreSQL non risponde**: `docker compose restart postgres` (i bot si riconnettono).
  Console: `docker compose exec postgres psql -U fantabasket -d fantabasket`.
- **Secrets modificati**: `docker compose up -d --force-recreate <servizio>` (i secrets sono
  montati per file: alcuni editor creano un file nuovo e il container vede ancora il vecchio).
  Poi rilancia `scripts/cifra_secrets.sh` (sezione 5).
- **Healthcheck**: il bot main pinga l'URL in `secrets/bot_main.env` ogni 5 minuti; se smette
  arriva la notifica.
- **Backup subito**: `/backup` dal bot main.

---

## 3. Ripristino completo

Vale sia per rimettere in piedi il server sia per partire da un altro computer.

**Serve:** Docker (su Windows e Mac: Docker Desktop), git, l'ultimo zip di backup
(canale log o gruppo admin) e — per i secrets — la passphrase (sezione 5).

### 3.1 Codice e backup

```bash
git clone <indirizzo del repo GitHub, fissato nel gruppo admin> fantabasket-progettone
cd fantabasket-progettone
unzip ~/Downloads/backup_progettone_AAAAMMGG_HHMM.zip -d restore/
cp -r restore/config ./config
```

### 3.2 Secrets

**Con la passphrase** (backup con `secrets.tar.gpg`; su Windows serve Gpg4win):
```bash
mkdir -p secrets
gpg -d restore/secrets.tar.gpg | tar -xz -C secrets/
```

**Senza passphrase**: vanno ricreati a mano nella cartella `secrets/` (un valore per file,
senza a capo in più). Nomi esatti, come in `docker-compose.yml`:

| File | Cosa contiene | Dove si recupera |
|---|---|---|
| `bot_token_main.txt` | token del bot principale | @BotFather → il bot → API Token |
| `bot_token_aste_beta.txt` | token del bot aste | @BotFather |
| `pg_password.txt` | password del database | si può inventare: su un database nuovo vale quella che scrivi qui |
| `gas_roster_url`, `gas_scelte_url` | URL delle web app dei fogli | Apps Script → Esegui il deployment → Gestisci deployment |
| `gas_token` | token che le web app controllano | Apps Script → Impostazioni progetto → Proprietà script → `AUTH_TOKEN` |
| `gas_router_token` | token interno tra bot main e gas-router | si può inventare (una stringa qualsiasi) |
| `yahoo_client_id`, `yahoo_client_secret`, `yahoo_router_token` | Yahoo | portale developer Yahoo (dev); non necessari per i bot |
| `bot_main.env` | `HEALTHCHECK_URL=...` | healthchecks.io; può restare vuoto |
| `yahoo_router.env` | `YAHOO_LEAGUE_IDS=...` | dev; può restare vuoto |

Se i token dei bot non sono recuperabili, vedi **Bot di emergenza** nella sezione 4.

### 3.3 Database principale

Sul server già avviato ferma prima i bot: `docker compose stop bot-main bot-aste-beta`
(lo spegnimento manda anche un backup dello stato attuale: tienilo, non si sa mai).

```bash
mkdir -p secrets/cifrati
docker compose up -d postgres
# database vuoto, poi il dump (vale anche per i backup vecchi, con nomi tipo fantabasket_AAAAMMGG_HHMM.sql)
docker compose exec -T postgres psql -U fantabasket -d postgres \
  -c "DROP DATABASE IF EXISTS fantabasket WITH (FORCE)" -c "CREATE DATABASE fantabasket OWNER fantabasket"
cat restore/db/fantabasket*.sql | docker compose exec -T postgres psql -q -U fantabasket -d fantabasket
```
Un eventuale `unrecognized configuration parameter "transaction_timeout"` all'inizio è
innocuo (dump fatto con un client PostgreSQL più recente del server).

Su Windows (PowerShell) l'ultima riga diventa:
`Get-Content (Get-Item restore/db/fantabasket*.sql).FullName | docker compose exec -T postgres psql -q -U fantabasket -d fantabasket`

### 3.4 Database del bot aste

Va copiato nel volume **a bot aste fermo**, togliendo prima i file `-wal`/`-shm` del database
vecchio (se restassero, SQLite li applicherebbe al file nuovo rovinandolo):
```bash
docker compose create --build bot-aste-beta
docker compose run --rm --no-deps --entrypoint sh bot-aste-beta -c "rm -f /data/aste.db-wal /data/aste.db-shm"
docker compose cp restore/db/aste.db bot-aste-beta:/data/aste.db
```

### 3.5 Avvio e verifica

```bash
docker compose up -d --build
docker compose logs -f bot-main bot-aste-beta     # Ctrl+C per uscire
```
- bot principale: `/menu` risponde e `/roster` mostra le squadre;
- bot aste: `/aste` mostra le aste in corso (le aste chiuse o in pareggio vengono
  riprese da sole pochi secondi dopo l'avvio);
- canale log: arriva il messaggio di avvio con la versione.

---

## 4. Emergenza senza il dev (admin)

**Prima scrivi al dev.** Se non risponde entro qualche ora, segui la sezione 3 su un
computer con Docker, con queste differenze.

### Bot di emergenza (token non disponibili)
1. Su Telegram apri `@BotFather` → `/newbot` → salva il token. Ripeti per il secondo bot.
2. Bot principale: amministratore del canale principale, del gruppo admin e del canale log.
   Bot aste: amministratore del canale aste e del gruppo admin.
3. Metti i token in `secrets/bot_token_main.txt` e `secrets/bot_token_aste_beta.txt`.
4. Se hai ricreato canali o gruppi, aggiorna gli ID in `config/globals.json`.
5. In `config/globals.json` metti il tuo ID Telegram come `dev_id`: così puoi usare `/backup`.
6. Avvisa i GM del cambio di bot.

⚠️ **Mai due istanze con lo stesso token insieme**: si bloccano a vicenda. Con token
diversi non ci sono conflitti tecnici, ma i database sono separati.

### Quando il dev torna
1. Dal bot di emergenza: `/backup` (con il tuo `dev_id`) e gira lo zip al dev.
   In alternativa, dal computer di emergenza:
   ```bash
   docker compose exec -T postgres pg_dump --clean --if-exists --no-owner -U fantabasket fantabasket > db_aggiornato.sql
   docker compose cp bot-aste-beta:/data/aste.db aste_aggiornato.db
   ```
2. Il dev lo ripristina sul server con la sezione 3.3–3.4.
3. Spegni l'emergenza (`docker compose down`) **solo dopo** che il dev conferma che il
   server è tornato operativo.

---

## 5. Secrets nel backup (dev)

I secrets entrano nel backup **solo cifrati**, e la cifratura avviene sul server, fuori
dai bot: il bot main vede solo il file già cifrato (`secrets/cifrati/`, montato in sola
lettura) e lo allega allo zip.

```bash
cd ~/bots/fantabasket-progettone && ./scripts/cifra_secrets.sh
```
- chiede la passphrase due volte, poi la richiede per verificare che il file si decifri;
- **va rilanciato ogni volta che cambi un file in `secrets/`** (la didascalia del backup
  mostra la data dei secrets inclusi: se è vecchia, rilancia);
- la passphrase sta nel password manager, mai sul server né su Telegram;
- se vuoi che un admin di fiducia possa ripristinare tutto anche senza di te, dagli la
  passphrase: con quella il ripristino usa i bot veri e i GM non si accorgono di niente.

Senza `secrets/cifrati/secrets.tar.gpg` il backup funziona lo stesso, con l'avviso
"secrets non inclusi" nella didascalia.

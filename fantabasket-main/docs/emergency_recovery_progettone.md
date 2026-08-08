# 🆘 Guida di Emergenza — Fantabasket Progettone

Questa guida serve se i bot smettono di funzionare e il dev non è raggiungibile.
È scritta per essere seguita anche senza esperienza tecnica.

**Prima di tutto:** scrivi al dev su Telegram. Se non risponde entro qualche ora, procedi con questa guida.

---

## Il sistema è composto da due bot

1. **Bot principale** — gestisce trade, tagli, roster, assets, DPE e tutto il mercato
2. **Bot aste** — gestisce le aste per i free agent

Entrambi devono funzionare. Il backup settimanale (ogni notte tra venerdì e sabato, nel gruppo admin) contiene tutto il necessario per ripristinarli entrambi.

---

## Cosa può essere successo

Il sistema gira su un mini-PC casalingo sempre acceso. Può smettere di rispondere per:

1. **Il mini-PC si è spento** (corrente mancante, riavvio)
2. **Uno o entrambi i bot si sono crashati** (errore software)

Senza accesso diretto alla macchina del dev, l'unica opzione è il ripristino su un altro computer tramite backup.

---

## Cosa contiene il backup

- `db/fantabasket_YYYYMMDD_HHMM.sql` — database principale (contratti, trade, roster, pick, tutto)
- `db/aste.db` — database del bot aste (aste in corso, offerte, firme)
- `config/globals.json` — impostazioni lega (fase corrente, canali, admin)
- `config/teams.json` — dati squadre e GM (cap, slot, colori)
- `config/settings_main.json` — impostazioni bot principale
- `config/settings_aste.json` — impostazioni bot aste
- `config/tabelle/` — tabelle di riferimento
- `config/loghi/` — loghi squadre

---

## Procedura di ripristino

### Cosa ti serve
- Un computer con Docker installato — funziona su Windows, Mac e Linux
  - Windows: installa [Docker Desktop](https://docs.docker.com/desktop/install/windows-install/)
  - Mac: installa [Docker Desktop](https://docs.docker.com/desktop/install/mac-install/)
  - Linux: segui la [guida ufficiale](https://docs.docker.com/engine/install/)
- Il file di backup `.zip` dal gruppo admin su Telegram
- I token dei bot e la password del database — li ha solo il dev. Senza questi, vedi la sezione "Bot di emergenza"

### Passi

**1. Scarica il codice**
```
git clone https://github.com/alfalconetti/fantabasket-progettone.git
cd fantabasket-progettone
```

**2. Estrai il backup**

Fai doppio clic sul file `.zip` e trascinane il contenuto in una cartella chiamata `restore/` dentro la cartella `fantabasket-progettone`.

Poi crea la cartella `config/` con le sottocartelle `tabelle/` e `loghi/`, e copia lì dentro tutti i file dalla cartella `restore/config/`.

Su **Mac/Linux** puoi farlo da terminale:
```
unzip backup_progettone_YYYYMMDD_HHMM.zip -d restore/
mkdir -p config/tabelle config/loghi
cp restore/config/globals.json config/
cp restore/config/teams.json config/
cp restore/config/settings_main.json config/
cp restore/config/settings_aste.json config/
cp restore/config/tabelle/* config/tabelle/ 2>/dev/null || true
cp restore/config/loghi/* config/loghi/ 2>/dev/null || true
```

**3. Crea i file segreti**

Su **Mac/Linux**:
```
mkdir -p secrets
echo "TOKEN_BOT_MAIN" > secrets/bot_token_main
echo "TOKEN_BOT_ASTE" > secrets/bot_token_aste_beta
echo "PASSWORD_DATABASE" > secrets/postgres_password
```

Su **Windows**: crea una cartella chiamata `secrets` dentro `fantabasket-progettone`, poi crea tre file di testo (senza estensione) con questi nomi e contenuti:
- `bot_token_main` → scrivi dentro il token del bot principale
- `bot_token_aste_beta` → scrivi dentro il token del bot aste
- `postgres_password` → scrivi dentro la password del database

⚠️ I token e la password li ha solo il dev. Senza di essi, vedi la sezione "Bot di emergenza".

**4. Avvia tutti i container**
```
docker compose up -d --build
```
Aspetta circa un minuto. Questo avvia sia il bot principale che il bot aste.

**5. Ripristina il database principale**

Su **Mac/Linux**:
```
cat restore/db/fantabasket_*.sql | docker exec -i fantabasket-progettone-postgres-1 psql -U fantabasket -d fantabasket
```

Su **Windows** (PowerShell):
```
Get-Content (Get-Item restore/db/fantabasket_*.sql).FullName | docker exec -i fantabasket-progettone-postgres-1 psql -U fantabasket -d fantabasket
```

**6. Ripristina il database del bot aste**
```
docker cp restore/db/aste.db fantabasket-progettone-bot-aste-beta-1:/data_aste/aste.db
docker compose restart bot-aste-beta
```

**7. Verifica entrambi i bot**

Bot principale: manda `/start` su Telegram — deve rispondere con il menu.
Bot aste: manda `/aste` su Telegram — deve mostrare le aste in corso.

Se entrambi rispondono, il ripristino è riuscito.

---

## Bot di emergenza (token non disponibili)

Se non hai i token, puoi creare due bot temporanei:

**Bot principale di emergenza:**
1. Apri Telegram e cerca `@BotFather`
2. Manda `/newbot` e segui le istruzioni
3. Aggiungi il nuovo bot come amministratore al canale principale, al gruppo admin e al canale log
4. Usa il token ottenuto al posto di `TOKEN_BOT_MAIN`

**Bot aste di emergenza:**
1. Ripeti la procedura per un secondo bot
2. Aggiungi questo bot come amministratore al canale aste e al gruppo admin
3. Usa il token al posto di `TOKEN_BOT_ASTE`

⚠️ Aggiorna `config/globals.json` se i channel_id sono cambiati.
⚠️ Comunica ai GM il cambio di bot.

---

## Note importanti

- **Non avviare mai due bot con lo stesso token contemporaneamente** — si bloccano a vicenda
- **Il backup del venerdì notte è completo** — contiene tutto il necessario per ripristinare entrambi i bot
- Se ci sono aste in corso al momento del ripristino, il bot aste le riprende automaticamente dal database

---

## Quando il dev torna disponibile

Quando il dev è di nuovo raggiungibile, bisogna trasferirgli i dati aggiornati accumulati durante l'emergenza, poi spegnere il bot di emergenza.

**1. Esporta i database aggiornati dal computer di emergenza**

Su **Mac/Linux**:
```
docker exec fantabasket-progettone-postgres-1 pg_dump -U fantabasket fantabasket > db_aggiornato.sql
docker cp fantabasket-progettone-bot-aste-beta-1:/data_aste/aste.db aste_aggiornato.db
```

Su **Windows** (PowerShell):
```
docker exec fantabasket-progettone-postgres-1 pg_dump -U fantabasket fantabasket | Out-File -Encoding utf8 db_aggiornato.sql
docker cp fantabasket-progettone-bot-aste-beta-1:/data_aste/aste.db aste_aggiornato.db
```

**2. Manda i due file al dev** — `db_aggiornato.sql` e `aste_aggiornato.db`. Li importerà sul server principale.

**3. Spegni il bot di emergenza** solo dopo conferma del dev che tutto funziona:
```
docker compose down
```

⚠️ Non spegnere il bot di emergenza prima che il dev confermi che il server principale è tornato operativo.

---

## Contatti

- **Dev:** [contatto Telegram del dev]
- **Repo:** https://github.com/alfalconetti/fantabasket-progettone
- **Backup:** gruppo admin su Telegram, ogni notte tra venerdì e sabato

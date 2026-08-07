# Changelog — Fantabasket Main Bot

## v1.1 (2026-08-07)

### Bug fix
- **`get_roster_team_at`**: fix event sourcing — la query ora prende l'ultima transazione per ogni giocatore (qualsiasi tipo, inclusi tagli) e filtra su `team_id_a = team_id` tramite subquery SQL. Prima non filtrava per team e restituiva giocatori di tutti i team.
- **`/roster <data>`**: aggiunto guard per roster vuoto prima di invocare Typst — evita crash "invalid dimensions" / "Photo_invalid_dimensions".
- **`/roster <data>`**: aggiunto supporto formato data `DD-MM-YYYY` oltre a `DD-MM-YY`.
- **`/roster <data>`**: aggiunto safeguard su date future e date precedenti alla prima transazione nel DB.
- **`/edit_trade`**: rimosso `CommandHandler("edit_trade")` duplicato dalla lista handler globale (era già entry point di `conv_edit`).
- **`/bozze_trade`**: l'elenco bozze ora mostra `bozza_num` invece di `trade_id`.
- **`_testo_riepilogo`**: il titolo "Bozza trade #N" ora usa `bozza_num` invece di `trade_id`.
- **Validatore trade**: aggiunto check ownership giocatori — verifica che ogni giocatore ceduto appartenga effettivamente al roster del team cedente.
- **Keyboard trade non valida**: trade con errori di validazione mostrano solo "Modifica" ed "Elimina", non i bottoni per proporre/ufficializzare.
- **Età media roster**: calcolata su anni interi compiuti invece di anni decimali.

### Nuove feature
- **`/assets [team_id]`**: nuovo comando (pubblica anche nei gruppi) che genera un PNG con roster completo, pick divise per anno in griglia 3 colonne (★ proprie, ○ altrui), e diritti rookie con numero pick e anno draft. Usa `assets.typ`.
- **Backup automatico**: `scheduler.py` con pg_dump + zip config — giornaliero (00:00 e 12:00) al `log_channel_id_main`, settimanale (domenica 00:30) all'admin group, shutdown automatico.
- **Error handler**: errori non gestiti loggati su `log_channel_id_main` e in privato al dev.
- **`/backup`** (solo dev): invia backup manuale al canale log.
- **`/reboot`** (solo dev): riavvia il bot.
- **Notifica avvio**: messaggio su `log_channel_id_main` ad ogni avvio con versione e orario.
- **Scope comandi Telegram**: gruppi vedono solo `roster` e `assets`; privato aggiunge `menu`; admin e dev hanno tutti i comandi.
- **Ordinamento roster**: uniformato tra roster attuale e storico — importo DESC, cognome ASC.

### Aggiornamenti tecnici
- `python-telegram-bot` aggiornato da 21.6 a 22.8 con `[job-queue]`.
- `log_channel_id_main` in `globals.json` per canale log separato dal bot aste.

## v1.2 (2026-08-07)

### Refactor
- **`utils.py`** nuovo: centralizza `ROME`, `format_dt`, `format_dt_short`, `normalizza`, `cognome`. Tutti i file usano da qui invece di definire `ZoneInfo("Europe/Rome")` inline.
- **`log_buffer.py`** nuovo: buffer in memoria (maxlen=200) per `/dev_log`. Installato all'avvio in `bot.py`.
- **`handlers/dev.py`** nuovo: tutti i comandi dev unificati — `/dev`, `/dev_version`, `/dev_log`, `/dev_trade`, `/dev_pg`, `/dev_roster`, `/job_status`, `/broadcast`.
- **`database.py`**: aggiunte `ping()` e `get_ultime_trade_approvate()`.
- **`handlers/dev_player.py`**: `/dev_pg` e `/dev_roster` spostati in `handlers/dev.py`.

### Nuove feature
- **Healthchecks.io**: ping ogni 5 minuti se `HEALTHCHECK_URL` è configurato nel docker-compose.
- **`/broadcast`** (solo dev): invia messaggio in privato a tutti i GM con riepilogo successi/falliti sul canale log.
- **`/dev_log [N]`**: ultime N righe di log in memoria (default 30, max 100).
- **`/dev_trade [N]`**: ultime N trade approvate dal DB (default 10).
- **`/job_status`**: lista dei job attivi nella JobQueue con prossima esecuzione.

### Aggiornamenti tecnici
- `aiohttp` aggiunto ai requirements (necessario per healthcheck ping).
- Scope comandi Telegram aggiornato con tutti i nuovi comandi dev.

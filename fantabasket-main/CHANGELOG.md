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

## v1.3 (2026-08-07)

### Nuove feature
- **`/palette`**: nuovo comando per personalizzare i colori del roster/assets PNG — `colore_header`, `colore_riga1`, `colore_riga2`, `colore_sezione`, `colore_pick`, `colore_diritti`. Anteprima live via Typst prima di salvare.
- **`/set_fase`**: passaggio a `offseason-rinnovi` incrementa automaticamente `stagione_corrente`; `mercato_aperto` si aggiorna automaticamente in base alla fase.
- **`richiede_fase` decorator**: blocca comandi fuori dalla fase corretta con messaggio configurabile.
- **`FASI_TRADE_APERTE`**: costante in `settings.py` condivisa da trade, tagli, DPE e attiva_diritti.

## v1.4 (2026-08-07)

### Nuove feature
- **`/attiva_diritti`** (`handlers/rookie.py`): attivazione diritti 2nd pick con selezione giocatore, scelta importo/anni, conferma. Annuncio sul canale principale al completamento.
- **`/taglia`** (`handlers/tagli.py`): taglio giocatori con preview impatto cap, conferma, scrittura DB. Tagli 1x1 gratuiti (max 3/stagione); se esauriti il taglio è bloccato. Annuncio sul canale principale.
- **`/dpe`** (`handlers/dpe.py`): Disabled Player Exception — flusso GM → approvazione admin (gruppo admin) → scrittura tabella `dpe` in PostgreSQL → annuncio canale. Pre-deadline libera slot; post-deadline nessuno slot liberato.
- **`handlers/helpers.py`** (nuovo): `log_job_error` e `log_warn` per loggare eccezioni dei job schedulati su `log_channel_id_main` e in privato al dev.
- **Migrazione DB automatica**: `migrate_db()` chiamata all'avvio — crea tabella `dpe` se non esiste.

### Bug fix
- **Bot aste beta — `/me`**: cap occupato ora calcolato correttamente in offseason (165M di riferimento invece di 150M fisso). Fix in `pg_client.get_cap_totale` — usa `cap_limite()` invece di `cap_massimo()`.
- **Bot aste beta — `settings_aste.json`**: aggiunto `cap_offseason: 165` e `cap_massimo_offseason: 165`.
- **`/attiva_diritti`**: aperto a tutte le `FASI_TRADE_APERTE` invece di solo `offseason-rinnovi`.
- **Tagli 1x1**: rimossa opzione "taglia con impatto" quando i tagli gratuiti sono esauriti — il taglio è semplicemente bloccato.
- **Scheduler job**: errori in `backup_giornaliero`, `backup_settimanale`, `_bref_scraper_job` ora loggati via `log_job_error` invece di sparire silenziosamente.
- **Annunci canale trade**: nome admin nel formato "Nome (@tag)" per accountability.

### Aggiornamenti tecnici
- `cap_occupato_team` in `database.py` aggiornato per includere DPE nel calcolo del cap.

## v1.4.10 (2026-08-08)

### Bug fix
- **`roster.typ` / `assets.typ`**: fix font Liberation Sans mancante nel container — aggiunto `fonts-liberation` al Dockerfile.
- **Testo adattivo WCAG**: colori testo su sfondo personalizzabile ora calcolati in Python (`roster.py`) con luminanza WCAG (soglia 0.179) e passati a Typst come parametri. Eliminato calcolo in Typst che causava errori di tipo.
- **Footer**: usa `c_dark` quando `colore_sezione` non è impostato; usa `c_sezione` se personalizzato. Testo footer calcolato sul colore effettivo del footer (non su `c_sezione` che potrebbe differire).
- **`/palette` — Riprova**: fix crash su messaggio foto — usa `reply_text` + disabilita bottoni vecchio messaggio.
- **`/palette` — Indietro**: disabilita bottoni messaggio precedente prima di mandare il menu.
- **`/palette` — timeout**: `conversation_timeout=300` ora gestisce correttamente la scadenza via fallback.
- **`/palette` — `/annulla`**: `CommandHandler("annulla")` aggiunto ai fallbacks del ConversationHandler.
- **Annunci canale admin**: accountability in tutti i messaggi canale generati da azioni admin — formato "Nome (@tag)".

## v1.4.11 (2026-08-08)

### Bug fix / miglioramenti
- **`/dpe`**: aggiunto ai `BotCommand` nello scope GM.
- **`/annulla` globale**: nuovo handler con `group=-1` che pulisce `user_data` e termina qualsiasi conversazione attiva. Aggiunto a `cmd_gm` con descrizione "Esci da qualsiasi conversazione bloccata".

## v1.4.12 (2026-08-08)

### Nuove feature
- **`/menu` dinamico per fase**: mostra solo i bottoni disponibili nella fase corrente — Trade/Tagli/Rookie solo in `FASI_TRADE_APERTE`, DPE solo in `regular-season-fa/deadline`, Roster/Assets sempre visibili.
- **Assets via menu**: aggiunto bottone 📋 Assets nel menu principale con selezione squadra via bottoni (analogo a Roster).
- **DPE via menu**: aggiunto bottone 🏥 DPE nel menu principale quando disponibile.
- **Riepilogo cap admin**: il bottone "Cap" nel pannello admin mostra ora riepilogo completo per tutte le squadre — contratti, tagli, penalità, DPE, totale vs limite, stato ✅/🔴.

## v1.4.13 (2026-08-08)

### Bug fix
- **Trade builder da menu**: i bottoni Build e Import nel menu trade ora usano callback_data dedicati (`menu_trade_build`, `menu_trade_import`) registrati come entry_point nei rispettivi ConversationHandler — evita il bypass di PTB che impediva l'avvio della conversazione.

## v1.4.14 (2026-08-08)

### Miglioramenti
- **`/bozze_trade`**: riscritta con bottoni InlineKeyboard — ogni bozza mostra i GM coinvolti (`GM1 ↔ GM2`), cliccando si apre il riepilogo con i bottoni azione (Modifica/Elimina/Proponi). Stessa visualizzazione per trade in attesa di voto.

## v1.4.15 (2026-08-08)

### Bug fix
- **Admin panel — situazione cap**: fix `settings.cap_limite()` → `settings.luxury_cap()` (la funzione corretta nel bot main).

### Miglioramenti
- **Menu admin**: aggiunto bottoni DPE, Attiva diritti, Cambia fase, Annulla trade — non solo Trade/Tagli/Cap.

## v1.4.16 (2026-08-08)

### Miglioramenti
- **DPE admin**: dal menu admin la DPE viene applicata direttamente (admin già autorizza), senza passare per il gruppo admin. Flusso: seleziona team → seleziona giocatore con preview importo → conferma → DB + annuncio canale con tag admin.

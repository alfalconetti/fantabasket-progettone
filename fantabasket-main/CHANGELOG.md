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

## v1.4.17 (2026-08-08)

### Bug fix
- **`admin_panel`**: fix `NameError cb_adm_dpe_team` — funzioni DPE admin mancanti inserite correttamente.
- **`check_cap_stagionale`**: fix logica errata — ora confronta cap occupato totale vs `n_teams × cap_regular` invece di calcolare margine su delta offseason/RS. Mostra anche i singoli team già oltre il limite RS.

### Miglioramenti
- **Annulla trade da menu admin**: ora mostra lista delle ultime 15 trade approvate con bottoni, riepilogo e conferma prima del rollback.

## v1.4.18 (2026-08-08)

### Bug fix
- **Set fase da menu admin**: fix — ora chiama `cmd_set_fase` direttamente invece di mostrare una keyboard i cui callback non venivano intercettati dopo `ConversationHandler.END`.

## v1.4.19 (2026-08-08)

### Miglioramenti
- **Riepilogo cap admin**: header mostra esplicitamente il limite per squadra con nota "(offseason)" quando applicabile.

## v1.5.0 (2026-08-08)

### Nuove feature
- **Autocap/Autoslot anticipato**: GM può richiedere cap/slot temporaneo (+48h) in caso di trade notturna non ancora ufficializzata. Il cap anticipato viene sommato al cap libero reale per permettere offerte. Notifica al gruppo admin con bottone Reset.
- **Reset con check**: al Reset l'admin riceve avviso se il team andrebbe in negativo senza il cap anticipato (trade non ancora ufficializzata). Il reset è bloccato in quel caso.
- **Pulizia automatica**: job alle 3:00 pulisce cap/slot anticipati scaduti e notifica admin. Se il team è in negativo dopo la pulizia, avviso urgente.
- **Display cap anticipato**: `/me` e dettaglio team mostrano cap/slot anticipato attivo con nota scadenza.

### Bug fix
- **`_cap_libero`**: ora usa `cap_limite()` (165M offseason, 150M RS) invece di `cap_massimo()` fisso — un GM in offseason aveva 15M in meno di cap disponibile per le offerte.

## v1.5.3 (2026-08-09)

### Bug fix
- **DPE — slot**: ora libera sempre uno slot indipendentemente dalla fase (pre/post deadline). Lo slot viene escluso da `get_roster_count` tramite la tabella `dpe`.
- **DPE — cap**: `get_cap_contratti` ora usa `importo_dpe` quando disponibile per quella stagione, sia nel bot aste che nel calcolo cap.
- **`get_slot_totale`**: accetta `stagione` per escludere giocatori con DPE attiva dal conteggio roster.

## v2.0.2 (2026-08-09)

### Nuove feature
- **GAS Client** (`gas_client.py`): modulo per inviare aggiornamenti roster al GAS Router dopo ogni transazione. Chiamate automatiche dopo trade, taglio, firma rookie, DPE.
- **`/sync_sheets`**: comando dev per sincronizzazione manuale completa di tutti i 24 team su Google Sheets.

## v2.0.12 (2026-08-11)

### Nuove feature
- **Decadimento contratti**: nuovo comando `/decadimento` per segnalare contratti decaduti (ritiro, firma in altra lega, ecc.). Flusso GM → approvazione admin → DB + annuncio canale. Contratto disattivato, impatti tagli futuri cancellati, slot roster liberato. Disponibile anche da menu admin (diretto senza approvazione).
- `registra_decadimento()` in `database.py`: inserisce transazione `tipo='decadimento'` con `team_id_a=NULL` per l'event sourcing, disattiva contratto, cancella impatti tagli futuri.

## v2.0.15 (2026-08-15)

### Nuove feature
- **Settings unificato**: `settings_main.json` e `settings_aste.json` sostituiti da un unico `settings.json` con nomi chiari e senza duplicazioni. Chiavi rinominate: `luxury_cap`→`cap_offseason`, `cap_massimo`→`cap_regular`, `max_roster`→`roster_max`, `min_roster`→`roster_min_regular`, ecc.
- **`/settings`**: comando admin per visualizzare e modificare le settings dal bot. Log automatico su canale log. Uso: `/settings` per visualizzare, `/settings chiave valore` per modificare.
- **BotCommand bot aste**: comandi registrati su Telegram con scope corretto (GM e admin).
- **Scadenza diritti 2nd round**: job giornaliero che avvisa 10 giorni prima della trade deadline + bottone conferma admin. Parametro `trade_deadline` in `globals.json`.

## v2.0.16 (2026-09-18)

### Nuove feature
- **`/settings [chiave] [valore]`**: comando admin per visualizzare e modificare le settings dal bot. Log automatico su canale log.
- **BotCommand bot aste con scope**: comandi registrati su Telegram con scope corretto — GM, admin, dev.
- **`/annulla_trade`** aggiunto ai comandi GM nel bot main.

### Bug fix
- **BotCommand bot aste**: corretti nomi comandi reali (rimosso `fa`, aggiunto `lista_fa`, `offri`, `nuova_fa`).
- **`guida_gm.md` bot aste**: rimosso `/aste` e `/listteams` dai comandi GM (sono admin-only).

## v2.0.17 (2026-09-18)

### Nuove feature
- **BotCommand bot aste**: scope corretti verificati dal codice reale — `offri` e `nuova_fa` aggiunto ai GM, `aste` spostato in admin.

### Fix
- **`guida_gm.md` bot aste**: aggiornata con comandi corretti.

## v2.0.18 (2026-09-18)

### Fix
- **BotCommand bot aste**: rimosso `fa` (non esiste), aggiunto `lista_fa` verificato dal codice.

## v2.0.19 (2026-09-18)

### Bug fix
- **`_notifica_proponente`**: funzione non definita in `trade.py` — aggiunta.
- **`trade_ref` None nel flusso voto GM**: aggiunta funzione `_trade_label()` che usa label `{AAA}-B{N}` (prime 3 lettere nome team + numero bozza) quando `trade_ref` è NULL.

## v2.0.20 (2026-09-18)

### Bug fix
- **Label trade pre-approvazione**: formato `{AAA}-B{N}` — prime 3 lettere del nome del team proponente + numero bozza.

## v2.0.21 (2026-09-18)

### Nuove feature
- **`/registra_firma`** (admin): registra firma avvenuta fuori dal bot. Parametri: `team_id importo anni nome giocatore`. Ricerca fuzzy, selezione con bottoni se più risultati, check contratto attivo, sync GAS automatico, log su canale.
- **`/nuovo_giocatore`** (dev): inserisce anagrafica giocatore nel DB. Formato: `nome_common | nome_bref [YYYY-MM-DD]`.

## v2.0.22 (2026-09-19)

### Bug fix
- **Lista FA bot aste — paginazione**: `lista_fa_page_callback` non ordinava per fantamedia — aggiunto `rows.sort()` dopo il fetch.
- **`get_fa_rows_pg()`**: aggiunto JOIN con `bref_stats` (LATERAL, ultima riga per timestamp) — la fantamedia arriva già dal DB invece di essere fetchata separatamente. Ordine `fantamedia DESC NULLS LAST` direttamente in SQL.

## v2.0.23 (2026-09-19)

### Bug fix
- **Trade builder dal menu**: bottone "🔨 Build" ora avvia correttamente il ConversationHandler (aggiunto come entry_point).
- **`/annulla` nella trade**: aggiunto ai fallback del ConversationHandler — prima solo `/annulla_trade` funzionava.
- **Bottoni riepilogo post-errore**: `cb_send_trade` registrato come handler globale fuori dalla conversazione.
- **Import dal menu**: `menu_trade_import` gestito prima del `split(":")` in `cb_menu` per evitare IndexError.

## v2.0.24 (2026-09-19)

### Nuove feature
- **Bottone "💾 Salva bozza"**: aggiunto al riepilogo trade — salva e termina la conversazione senza inviare.
- **Re-validazione su invio**: `cb_send_trade` rivalida la trade al momento dell'invio invece di fidarsi del valore `validazione_ok` nel DB (poteva essere obsoleto dopo modifiche).

### Bug fix
- **`cb_salva_bozza`**: definizione mancante aggiunta.
- **Fix menu import IndexError**: rimosso pattern `menu_trade_import` dal `CallbackQueryHandler` di `cb_menu`.

## v2.0.25 (2026-09-20)

### Nuove feature
- **Nota trade**: bottone "📝 Aggiungi nota" / "📝 Modifica nota" nel riepilogo. Apre stato `TRADE_NOTA` — GM scrive testo (max 300 caratteri), `/salta` rimuove nota. Nota salvata in colonna `nota_gm` della tabella `trade`.

⚠️ **Operazione manuale richiesta:**
```sql
ALTER TABLE trade ADD COLUMN IF NOT EXISTS nota_gm TEXT;
```

## v2.0.26 (2026-09-20)

### Nuove feature
- **Nota ai riceventi**: nota trade mostrata ai GM riceventi come "💬 Messaggio da {GM proponente}" nel messaggio di proposta.
- **Nota rifiuto**: quando GM rifiuta, chiede conferma con bottoni "❌ Rifiuto secco" / "📝 Rifiuto con nota". Nota mostrata al proponente sotto il messaggio di rifiuto.
- **`conv_rifiuto`**: nuovo ConversationHandler separato per il flusso rifiuto con nota (timeout 120s).

### Bug fix
- **Import dal menu** (`menu_trade_import`): aggiunto come entry_point di `conv_import` — prima non avviava il ConversationHandler.
- **Import**: dopo il parsing rimane in `TRADE_RIEPILOGO` con bottoni funzionanti (nota, proponi, salva bozza).

## v2.0.27 (2026-09-20)

### Bug fix
- **`menu_trade_import` IndexError**: gestito prima del `split(":")` in `cb_menu`.
- **None concatenation in `cb_nota_ricevi`**: `validazione_note` può essere `None` — fix con `or ""`.

## v2.0.28 (2026-09-20)

### Bug fix
- **`menu_trade_import` IndexError** (ripetuto): rimosso pattern `^menu_trade_import$` dal `CallbackQueryHandler` di `cb_menu` — ora gestito esclusivamente da `conv_import`.
- **`cb_nota_ricevi`**: `validazione_note` ora gestito con `or ""` per evitare `TypeError`.

## v2.0.29 (2026-09-21)

### Nuove feature e fix
- **GAS sync fire and forget**: `sync_teams()` ora lancia il sync in un thread daemon — non blocca il bot. Retry automatico dopo 30s se fallisce.
- **`/sync_sheets` sincrono**: usa `sync_teams_sync()` con timeout 60s e feedback reale.

## v2.0.30 (2026-09-28)

### Nuove feature
- **Sync periodico GAS**: job `sync_sheets_periodico` ogni 2 ore (first=600s) — recovery automatico in caso di sync persi. Fire and forget, nessun feedback all'utente.

## v2.0.31 (2026-10-01)

### Nuove feature
- **DPE: fasi estese**: disponibile in tutte e 6 le fasi (`offseason-rinnovi` → `regular-season-deadline`), non solo in regular season. `FASI_DPE` aggiornata.
- **`pre_deadline`**: logica aggiornata — `fase != "regular-season-deadline"` (libera slot in tutte le fasi tranne post-deadline).
- **DPE admin diretta**: aggiunta voce "🏥 DPE" nel pannello admin (`/admin_menu`). Flusso: team → giocatore (con preview importo) → conferma → DB + notifica GM + annuncio canale + GAS sync. Senza approvazione.

## v2.0.32 (2026-10-01)

### Nuove feature
- **Roster/Assets PNG — DPE barrato**: giocatori con DPE attiva mostrano nome in rosso scuro (`#C62828`) e importo come `~~originale~~ nuovo`. Leggenda con `■ DPE` se presente.
- **Roster sempre 15 righe**: padding con righe vuote (`flag=VUOTO`) per slot non occupati.

### Bug fix
- **`get_roster_team()`**: joina tabella `dpe` per la stagione corrente — restituisce `importo` DPE-adjusted, `importo_originale`, `ha_dpe`.
- **Annuncio canale DPE**: testo `effetto` in `cb_approva_dpe` ora usa `pre_deadline` invece di essere hardcoded.

## v2.0.33 (2026-10-01)

### Bug fix
- **Import trade — pick**: lookup per `proprietario_orig` invece di `proprietario_att` — trovava solo le pick ancora in mano al proprietario originale. Aggiunta `get_pick_by_orig_anno_round()` in `database.py`.
- **Roster 15 righe**: `has_rookie`, `has_rfa`, `has_dpe` escludono le righe `VUOTO` dal check leggenda.

## v2.0.34 (2026-10-01)

### Bug fix
- **Bot aste — slot DPE**: `check_slot_virtuale()` in `teams.py` passava `get_roster_count()` senza `stagione` — giocatori con DPE venivano contati nel roster e lo slot risultava 0.

## v2.0.35 (2026-10-01)

### Bug fix
- **Annuncio canale import trade**: `cb_ufficializza` in `admin_panel.py` usava `_testo_riepilogo()` (formato bozza con bullet) invece di `_formatta_annuncio_canale()` (formato standard con importi).

## v2.0.36 (2026-10-01)

### Nuove feature
- **Label bozze unificate**: nuova funzione `_label_bozza(trade)` — formato `BUF03-3` (prime 3 lettere prima parola nome team + numero team zero-padded + bozza_num) o `ADM-4` per bozze admin.
- **Rimossi ID interni**: eliminati tutti i punti dove `trade_id` PK PostgreSQL o `proposta_da` grezzo apparivano all'utente.
- **Invio gruppo admin**: mostra nome squadra invece di `team_id` grezzo.

## v2.0.37 (2026-10-01)

### Nuove feature
- **`/bozze_trade` con bottoni inline**: bottone `✏️ BUF03-3` apre l'editor direttamente; bottone `👀 TRADE-2026-022` apre riepilogo con voto per le trade pending. Nuovo handler `cb_trade_vedi`.
- **Notifica ruoli post-trade condizionale**: messaggio "comunica i ruoli entro 48h" inviato ai GM solo in `regular-season-fa` (pronto per `offseason-ruoli`).
- **Comandi bot aggiornati**: aggiunti `edit_trade` (GM), `registra_firma`, `annulla_admin` (admin), `sync_sheets` (dev).

### Bug fix
- **`trade_ref` NULL in transazioni e notifiche GM**: `_esegui_trade()` ora riceve `trade_ref` come parametro — `db.approva_trade()` viene chiamata prima di `_esegui_trade()`. Prima le transazioni venivano registrate con `trade_ref = NULL`.

## v2.0.38 (2026-10-01)

### Nuove feature
- **Fuzzy match team**: aggiunta `get_team_by_query()` in `teams.py` — match su team_id (esatto), nome squadra (esatto → prefix → fuzzy difflib 0.6), gm_nome. `/roster`, `/assets`, `/team_diff` accettano nome GM o nome squadra oltre a team_id.

## v2.0.39 (2026-10-01)

### Bug fix
- **Palette assets**: `_genera_assets_png()` usava `team.get('colore', '#1A237E')` (campo obsoleto) per il calcolo del colore testo footer — sostituito con `team.get('colore_header', '#1A237E')`. Il footer di `/assets` ignorava la palette e usava sempre il colore di default.

### Documentazione
- Aggiornate `guida_gm.md` e `guida_admin.md` con tutte le novità v2.0.31–v2.0.39.
- Aggiornato `MIGRATION.md` a v2.0.39.

## v2.0.40 (2026-10-01)

### Bug fix
- **Pick assets inline**: squadra originaria della pick ora mostrata sulla stessa riga (`○ 1st (Buffalo Brownies)`) invece di a capo.
- **Palette assets**: `assets.typ` leggeva `colore` (campo obsoleto) invece di `colore_header` per il colore principale — fix definitivo con allineamento completo campi Python ↔ Typst.
- **Stroke rimosso**: rimosso stroke su testi colorati (rookie/RFA/DPE) — in Typst lo stroke va sopra il fill, rendendo il testo illeggibile.

## v2.0.41 (2026-10-01)

### Nuove feature
- **Badge bianco selettivo**: per rookie/RFA/DPE con contrasto insufficiente contro lo sfondo riga, il nome viene wrappato in un `box(fill: white.transparentize(25%))`. Il badge viene calcolato giocatore per giocatore, confrontando il colore speciale del tipo con lo sfondo della riga esatta su cui finisce il giocatore (alternanza Python allineata a `calc.odd(i)` di Typst).
- **`_lum()`, `_contrasto()`, `_needs_badge()`**: funzioni WCAG in `roster.py` per calcolo contrasto runtime.

### Bug fix
- **Alternanza riga badge**: Python usava `idx % 2 == 0 → riga1` mentre Typst usa `calc.odd(i) → riga1` per i dispari — fix inversione.

## v2.0.41a (2026-10-01)

### Bug fix
- **`_text_on_muted()`**: ora scorre una scala di grigi garantendo ratio WCAG ≥ 2.5 contro lo sfondo invece di usare `#bbbbbb`/`#555555` fissi.

## v2.0.42 (2026-10-01)

### Bug fix
- **`tagli_usati` da DB**: roster e assets calcolano i tagli gratuiti usati in tempo reale da PostgreSQL (`get_tagli_gratuiti_usati()`) invece di leggerlo da `teams.json`. `cambi_usati` resta da `teams.json` finché non viene tracciato nel DB.
- **`tagli_usati`/`cambi_usati` passati ad assets**: mancavano nel cmd Typst di `_genera_assets_png`.
- **Default rimossi da `sys.inputs`**: `roster.typ` e `assets.typ` non hanno più valori hardcodati nei `default:` di `sys.inputs.at()` — se un campo non arriva da Python, Typst fallisce esplicitamente invece di usare valori fasulli.

## v2.1.0 (2026-10-03)

### Nuove feature
- **Foglio Scelte GAS**: ricostruzione completa ad ogni sync — pick proprie (1st in riga 1, 2nd in riga 2), pick altrui per anno, diritti 2nd pick, numeri draft corrente con suffisso ordinale (25th, 2nd...), flag `[STEPIEN]` sulle pick proprie la cui cessione violerebbe la Stepien Rule
- **`globals.gs`**: CONFIG, DIV_COLORS, TEAM_MAP centralizzati
- **`divisions.json`**: mapping team_id → division e ordine fisso, in `config/` (non nel repo)
- **`gas-router`**: endpoint `POST /gas/scelte`, secret `GAS_SCELTE_URL_FILE`
- **`database.py`**: `get_all_picks_by_orig()`, `get_stepien_anni()`
- **`sync_scelte()`** in `gas_client.py`: fire-and-forget, incluso in `sync_all()`

## v2.1.1 (2026-10-03)

### Fix
- `globals.gs` rimosso da `.gitignore` → pushato via clasp; nomi sensibili rimossi da GAS, spostati in `divisions.json`
- `docker-compose.yml`: aggiunto secret `gas_scelte_url`

## v2.1.2 (2026-10-03)

### Fix
- Pick proprie: mostrate solo se ancora in possesso del team (`proprietario_att == team_id`)
- Nomi GM in colonna B e label pick usano mapping `team_pick_nome` da `divisions.json`
- Suffisso ordinale corretto (1st, 2nd, 3rd, 25th...) per numeri draft e diritti
- Stile celle: nome squadra bold nero centrato, GM normale centrato, "Altre pick" bold centrato
- Minimo 4 righe per team (2 righe "Altre pick" sempre presenti)
- Reset esplicito alignment/fontColor dopo `clearFormat()`

## v2.1.3 (2026-10-03)

### Fix
- **Trade validator — slot**: giocatori con DPE pre-deadline esclusi dal conteggio roster
- **Trade validator — cap**: `cap_out`/`cap_in` usano `importo_dpe` se attiva, altrimenti importo contratto

## v2.1.4 (2026-10-03)

### Fix
- `cmd_annulla_trade_admin`: `NameError: trade_id not defined` — sostituito con `trade["id"]` già disponibile

## v2.1.5 (2026-10-03)

### Fix
- `scelte.gs`: reset esplicito `setHorizontalAlignment("left")` e `setFontColor` dopo `clearFormat()` per evitare che formattazione residua sovrascriva quella nuova

## v2.1.6 (2026-10-03)

### Fix
- Diritti 2nd pick: formato ordinale (25th 2026) invece di (#25 2026)
- Nomi GM colonna B usano `team_pick_nome` (Klra, Hanry, Delfino...) invece di `gm_nome` da teams.json

## v2.1.7 (2026-10-03)

### Nuove feature
- `sync_scelte()` aggiunto in tutte le funzioni `sync_after_*` (taglio, firma, dpe, rookie)
- Sync GAS roster + scelte dopo rollback trade

### Fix
- `cmd_annulla_trade_admin`: `NameError: trade_id` → usa `trade["id"]`

## v2.1.8 (2026-10-03)

### Fix
- `_esegui_trade`: aggiunto `sync_after_trade()` — mancava completamente, nessun sync avveniva dopo l'esecuzione di una trade

## v2.1.9 (2026-10-03)

### Fix
- Versione rinominata 2.1.10

## v2.1.10 (2026-10-03)

### Nuove feature
- **Foglio Roster GAS — SALARY CAP**: label aggiornata con penalità cap se presente (`SALARY CAP [-1]`)
- **Foglio Roster GAS — DPE**: riga rossa sotto i tagliati con formato `DIS. Nome 9x1   7x1`
- **`gas_client.py`**: `cap_penalizzato` e `dpe` aggiunti al payload roster
- **`database.py`**: aggiunta `get_dpe_attive_team(team_id, stagione)`
- **`trade.py`**: sync GAS (roster + scelte) alla fine di `_esegui_trade`

### Da fare (roadmap)
- Cambi ruolo: tracciamento nel DB (attualmente sempre 0/2 — v5.x)
- `offseason-ruoli`: fase tra `offseason-fa` e `regular-season-fa`, dichiarazione ruoli post-trade entro 48h

## v2.1.11 (2026-10-04)

### Nuove feature
- `/guida` (tutti i GM) — invia `guida_gm.md` in privato
- `/guida_admin` (solo admin) — invia `guida_admin.md` in privato
- Comandi suggeriti con scope corretto in `bot.py`

## v2.1.12 (2026-10-04)

### Bug fix
- `NameError: name 'tm' is not defined` in `_build_team_payload` — aggiunto `import teams as tm`
- `NameError: name 'team' is not defined` — aggiunto `team = tm.get_team_by_id(team_id)`

## v2.1.13 (2026-10-04)

### Bug fix
- `globals.gs` riscritto con struttura corretta (`CONFERENCE_ROW_BASES: [3, 30]`, `conference: 0/1`, `SPREADSHEET_ID` inline)
- Giocatori con DPE esclusi dalle 15 righe nel payload roster GAS

## v2.1.14 (2026-10-04)

### Nuove feature
- **Rookie scale colonne AX-BA** nel foglio Roster GAS: 4 colonne (ring buffer modulo 4), 24 pick con gap, `#` se fuori scala, riga 26 vuota, righe 27+ diritti 2nd attivati per quell'anno
- `get_rookie_scale_per_anno()` in `database.py`
- `_q_rookie_scale()` in `gas_client.py`

## v2.1.15 (2026-10-04)

### Bug fix
- Anni rookie scale: `range(stagione_int - 3, stagione_int + 1)` — usa stagione corrente inclusa

## v2.1.16 (2026-10-04)

### Bug fix
- `--root /` aggiunto al comando Typst per `roster.py` e `assets.py` — i loghi in `/config/loghi/` erano inaccessibili

## v2.1.17 (2026-10-04)

### Bug fix
- `decadimento.py`: `query.message.bot` → `context.bot` per notifica al gruppo admin
- `roster.gs`: SALARY CAP con penalità sempre negativo (`[-1]` non `[+1]`)

## v2.1.18 (2026-10-04)

### Nuove feature
- **Coda `gas_sync_queue`** su PostgreSQL: il bot aste accoda una riga dopo ogni firma FA/RFA
- `migrate_db()` crea la tabella automaticamente all'avvio del bot main
- `gas_queue_max_id()` e `gas_queue_svuota_fino()` in `database.py`
- Job `processa_coda_gas` ogni 60s in `scheduler.py`: se la coda non è vuota lancia `sync_all` e svuota fino all'id letto
- `accoda_sync_gas()` in `fantabasket-aste-beta/pg_client.py`
- Chiamata in `handlers/firma.py` del bot aste dopo firma finale

## v2.1.19 (2026-10-04)

### Bug fix
- `/attiva_diritti`: il contratto viene preso dalla rookie scale (colonna "I anno", `anno_idx = 0`) e si chiede solo conferma, invece di un importo libero; check cap spostato alla conferma; fallback a importo manuale solo se la pick non rientra in nessuna fascia

## v3.0.0 (2026-10-04)

### Nuove feature
- **`yahoo-router`**: nuovo microservizio FastAPI per le Yahoo Fantasy API — OAuth2 flusso `oob`, refresh automatico con lock, retry su 401, `game_key` risolto da `/game/nba`; endpoint `/health`, `/yahoo/game`, `/yahoo/teams`; CLI `cli.py auth|teams`; token in volume `yahoo_data`, credenziali in Docker secrets
- ⚠️ Le API rispondono 403 finché Yahoo non approva l'accesso (nuova policy da luglio 2026)

## v3.0.0a (2026-10-05)
- README del repository (in inglese): progetto hobbistico, architettura, uso dei dati Yahoo, contenuto del foglio Google

## v3.0.1 (2026-10-05)

### Bug fix
- **Trade parser** (`handlers/trade_parser.py`): le pick ora si cercano per proprietario originale. Il fix di v2.0.33 era finito sulla copia in radice, mai importata
- Controllo che la pick ceduta sia posseduta oggi dal cedente, con errore esplicito
- `by` facoltativo nelle righe pick
- GM riconosciuto anche da una singola parola di `gm_nome`/nome squadra, solo se univoca ("Birra" → "Alex Birra")
- Errori non più duplicati nelle trade a 2 squadre

## v3.0.2 (2026-10-05)

### Bug fix
- `admin_panel.py`: `db` non importato in 4 funzioni (import trade, `/registra_firma`) → `import database as db` a livello di modulo
- `admin_panel.py`: `calcola_impatto_taglio` non importata (taglio admin con impatto)
- `gas_client.py`: `_ordinal` definita dentro il ciclo dopo il primo uso → spostata a livello di modulo

## v3.0.3 (2026-10-05)

### Bug fix
- `cb_ufficializza`: rimossa una chiamata residua a `_esegui_trade` senza `trade_ref` (crashava; con i parametri giusti avrebbe eseguito la trade due volte)

## v3.0.4 (2026-10-05)

### Bug fix
- **Diritti nelle trade**: `_esegui_trade` non spostava gli item `diritti`; ora li assegna al destinatario (solo diritti attivi posseduti dal cedente)
- `_rollback_trade`: i diritti venivano riassegnati confrontando `rookie.id` con `giocatore_id` (riga sbagliata); corretto
- Parser: verifica che i diritti ceduti siano attivi e posseduti dal cedente
- Dati corretti a mano: TRADE-2026-019 (Dillon Mitchell → team10), TRADE-2026-029 (Drake Powell → team04, Baba Miller → team18)

## v3.0.5 (2026-10-06)

### Bug fix
- **DPE**: importo = contratto − ceil(25%) (5→3 come da regolamento), era ceil(75%) (5→4). Funzione unica `_importo_dpe()` usata anche dall'admin panel
- Dati: DPE di Mark Williams corretta da 7 a 6

## v3.0.6 (2026-10-06)

### Bug fix
- **Stepien Rule**: contava anche le 1st già cedute in trade precedenti. Ora un anno è coperto se la propria 1st è posseduta oggi o, se già scattata, usata dalla squadra; considera pick in entrata e in uscita della trade
- **Scadenza diritti 2nd**: il bottone di conferma non aveva handler (i diritti non scadevano mai) → nuovo `cb_scadi_diritti` in `handlers/rookie.py` (solo admin, non prima della data), annuncio in gruppo admin e canale main, sync scelte
- Scadenza calcolata su `stagione − 1` (era `− 2`) e alla data `deadline − 10 giorni` (era alla deadline)
- Avvisi: informativo nei 3 giorni prima, con bottone dal giorno della scadenza fino a conferma
- `scadi_diritti_anno()` restituisce i diritti scaduti; nuove `info_scadenza_diritti()` e `conta_diritti_attivi_anno()`

## v3.0.7 (2026-10-06)

### Bug fix
- **Cap**: in offseason tetto 165M per tutti, la penalità vale solo in regular season (150 − penalità). Validatore trade e bot aste (`settings.penalita_cap()`, usata in offerte, admin, scheduler, utils)
- Validatore trade: in stagione blocca le trade che portano sotto il salary floor (o fanno scendere ancora)
- Tagli: spalmatura 7x1 → 4-2-1 (era 4-3); unico importo che cambiava
- Bot aste: `/autoslot` andava sempre in errore per codice morto in fondo (che avrebbe anche raddoppiato slot e notifiche); riga "Cap libero in Regular Season" mostrata in tutte le fasi `offseason-*` (confronto con `== "offseason"` mai vero)
- Rimosse copie morte in radice: `trade_parser.py`, `admin_panel.py`, `dpe.py`
- README: Yahoo resta la piattaforma usata dai GM per i quintetti; nome servizio `bot-aste-beta`

## v3.0.8 (2026-10-06)

### Sicurezza
- ID delle leghe Yahoo tolti dal `docker-compose.yml`: lo yahoo-router li legge da `secrets/yahoo_router.env` (`env_file`, fuori da git). Cronologia git ripulita con `git filter-repo` + force push

## v3.0.9 (2026-10-06)

### Miglioramenti
- **Versione automatica**: `BOT_VERSION` letta dall'ultima voce `## vX.Y.Z` di questo CHANGELOG (era fissa a "v1" nel messaggio di avvio). Ogni patch deve aggiornare il CHANGELOG
- **Stepien unificata**: una sola logica in `validators/trade.py` (`anni_coperti_stepien`, `finestra_scoperta`, `anni_1st_bloccate_stepien`) usata da validazione trade, foglio Scelte e `/assets`. Il foglio prima ignorava le pick già usate al draft e partiva da `stagione + 1`: dal prossimo draft avrebbe dato risultati diversi dal validatore
- **`/assets`**: tag STEPIEN (rosso) sulle proprie 1st che non si possono cedere

### Pulizia
- Rimosso `fantabasket-main/roster.py` (copia morta di `handlers/roster.py`, ultimo doppione in radice)

## v3.1.0 (2026-10-07)

### Nuove feature
- **Posizioni eleggibili** (base per i ruoli): tabella `posizioni_eleggibili` come event log (nuova riga solo quando il set di posizioni di un giocatore cambia), vista `posizioni_attuali`; colonna `giocatori.yahoo_id` (indice unico)
- **`/import_posizioni`** (admin, privato): import da CSV `yahoo_id;nome;team;posizioni` esportato dalle pagine giocatori Yahoo. Abbinamento per yahoo_id → nome → nome senza suffisso → iniziale+cognome (solo se univoco). Anteprima con posizioni cambiate (Erminio rule), sotto contratto senza posizioni, ambigui, conflitti, righe scartate e file dei non abbinati; salvataggio solo dopo conferma, in un'unica transazione. Salva anche `yahoo_id` e `nome_yahoo`

### Dati
- Corretti i nomi di tre rookie in base a Yahoo: Cameron Boozer, Dailyn Swain, Jayden Quaintance

## v3.1.1 (2026-10-07)

### Bug fix
- `/import_posizioni`: i nomi accorciati della lista giocatori Yahoo ("K. Caldwell-Pope") non vengono più salvati in `giocatori.nome_yahoo`; si mantiene il nome già salvato o il nome comune
- Dati: `nome_yahoo` dei 6 giocatori importati in forma accorciata riportato al nome completo

## v3.2.0 (2026-10-07)

### Nuove feature
- **Fase `offseason-ruoli`** ("🎽 Offseason — Dichiarazione ruoli") tra `offseason-fa` e `regular-season-fa`: mercato aperto (trade, FA, DPE), `mercato_aperto` calcolato da `FASI_MERCATO_APERTO`
- **Dichiarazione ruoli** (`handlers/ruoli.py`): `/dichiarazione_ruoli` e bottone "🎽 Dichiara ruoli" nel `/menu` (solo in fase). Un bottone per giocatore con le posizioni eleggibili; giocatori con una sola posizione già impostati; scelte in bozza (tabella `ruoli_bozze`, persistente) e ufficiali solo con Conferma (eventi `cambi_ruolo`, tipo `iniziale`; `forzato_admin` se un admin cambia un ruolo già ufficiale). Conferma anche parziale, segnalata; vincoli 4G/4F/2C solo come avviso
- **Import ruoli da testo**: righe "Nome RUOLO", match solo sul proprio roster (esatto → parole del nome → fuzzy con conferma Sì/No), controllo eleggibilità, segnalazione di ambigui, errori e giocatori non indicati
- **Admin**: "🎽 Ruoli squadre" nel `/admin_menu` (stato di tutte le squadre, impostazione per qualsiasi squadra in qualsiasi fase); `/deadline_ruoli AAAA-MM-GG [HH:MM]`; dopo la deadline i GM non possono più confermare
- **Job**: promemoria privato ai GM incompleti il giorno prima della deadline (10:00); report giornaliero sul canale log alle 17:00 durante la fase; elenco dei giocatori senza ruolo al gruppo admin all'uscita dalla fase
- **Foglio Google**: colonna ruolo del roster riempita coi ruoli ufficiali della stagione
- **`/set_posizioni_eleggibili <nome> <PG,SG>`** (admin): correzione puntuale delle posizioni (event log, fonte `manuale`), con scelta tra candidati se il nome non è univoco
- `/import_posizioni` rinominato **`/import_posizioni_eleggibili`**
- Notifica post-trade in `offseason-ruoli`: invito a dichiarare i ruoli dei nuovi giocatori

## v3.2.1 (2026-10-07)

### Nuove feature
- **Annuncio di fase sul canale principale**: a ogni cambio fase il bot pubblica cosa si può fare (trade, FA e DPE calcolati dalle stesse costanti dei comandi, più indicazioni specifiche della fase in `FASI_INDICAZIONI` di `admin_panel.py`)

### Sicurezza / bug fix
- `HEALTHCHECK_URL` tolto dal `docker-compose.yml`: ora in `secrets/bot_main.env` (`env_file`, fuori da git); URL di ping rigenerato su healthchecks.io
- Sync periodico del foglio (2h) e coda di sync GAS avviati sempre: prima partivano solo se `HEALTHCHECK_URL` era impostato

## v3.2.2 (2026-10-07)

### Nuove feature
- **Ruoli nelle immagini**: colonna RUOLO a sinistra del giocatore in `/roster` e `/assets`; in `/roster` le posizioni eleggibili in corsivo accanto al nome. Per il roster a una data passata, ruoli e posizioni sono quelli in vigore a quella data (event log)
- **Ordinamento per ruolo**: quando tutti i giocatori hanno un ruolo ufficiale, roster ordinato per ruolo (PG, SG, SF, PF, C), poi contratto; altrimenti per contratto come prima

## v3.2.3 (2026-10-07)

### Miglioramenti
- **Menu principale dinamico per fase**: azioni dichiarate in `AZIONI_FASE` (`handlers/menu.py`) con le fasi prese dalle stesse costanti dei comandi; la fase corrente è indicata nel menu. Predisposte (commentate) le azioni future: rinnovi, dichiarazione RFA, cambio ruolo
- Il bottone DPE ora segue `FASI_DPE` (prima compariva solo in regular season, anche se `/dpe` funzionava anche in offseason)
- **Foglio Google**: roster ordinato per ruolo quando tutti i ruoli sono dichiarati, come `/roster`
- Documentazione ripulita da dettagli non necessari

## v3.2.4 (2026-10-07)

### Bug fix
- Bottone 🏀 Rookie del `/menu`: la scelta del giocatore non faceva nulla (la conversazione partiva solo da `/attiva_diritti`). Ora la scelta è anche un punto d'ingresso; aggiunto controllo che i diritti siano della squadra del GM, attivi e non firmati

### Miglioramenti
- **🏁 Decadimento nel `/menu`** nelle fasi di mercato aperto (il comando `/decadimento` resta disponibile in ogni fase)

## v3.2.5 (2026-10-07)

### Bug fix
- `query.bot` → `query.get_bot()` (python-telegram-bot ≥ 20): non partivano l'annuncio di fase sul canale principale, il messaggio di cambio fase sul canale log, il report di fine dichiarazione ruoli, e la notifica al GM + annuncio sul canale della DPE attivata da admin. Gli errori venivano ignorati in silenzio
- DPE da admin: i messaggi contenevano `\n` letterali al posto degli a capo

## v3.2.6 (2026-10-07)

### Miglioramenti
- Dopo la conferma dei ruoli il foglio Google aggiorna il roster di tutte le squadre (prima solo quella confermata), in un'unica chiamata; foglio Scelte escluso

## v3.3.0 (2026-10-07)

### Nuove feature — ruoli in regular season (fasi `FASI_RUOLI_RS`: regular-season-fa, regular-season-deadline, playoff)
- **Dichiarazioni post-trade / post-firma** (`handlers/ruoli_rs.py`, tabella `ruoli_pendenti`): per ogni giocatore ricevuto con una trade, con l'attivazione dei diritti o con `/registra_firma` si apre una dichiarazione con scadenza 48h. Il GM riceve in privato un bottone per ogni ruolo eleggibile (solo conferma se ce n'è uno); nel `/menu` compare "🎽 Ruoli da dichiarare (N)". Gli admin possono dichiarare al posto del GM da `/admin_menu` → "⏳ Ruoli in sospeso"
- Scelte che renderebbero impossibili i minimi 4G/4F/2C vengono rifiutate
- **Estrazione casuale** dopo 48h tra le eleggibili (preferendo quelle compatibili coi vincoli), job ogni 15 minuti; senza posizioni registrate → avviso agli admin
- **Regola dei 60 giorni**: giocatore riacquistato entro 60 giorni → vecchio ruolo assegnato subito
- Annunci sul canale principale per dichiarazioni, estrazioni e ruoli imposti; sync dei roster sul foglio
- **Trade in regular season**: il validatore verifica che esista un'assegnazione dei ruoli eleggibili che rispetti 4G/4F/2C (`validators/ruoli.py`); se la squadra è già fuori regola, la trade non deve peggiorare la situazione

### Bug fix
- `/registra_firma`: la transazione era registrata con tipo `'firma'`, non ammesso dalla tabella → il contratto veniva creato ma la transazione falliva ("Errore DB"). Ora tipo `'signed'`, con contratto e transazione in un'unica transazione DB

## v3.3.1 (2026-10-07)

### Nuove feature — cambi ruolo (regular season e playoff)
- **`/cambio_ruolo`** e "🔁 Cambio ruolo" nel `/menu` (`handlers/cambi_ruolo.py`): giocatore → nuovo ruolo tra le eleggibili → tipo di cambio, con l'esito dei controlli per ogni tipo
  - **ordinario**: max 2 a stagione; contatore "cambi ruolo usati" su `/roster` e sul foglio Google
  - **Erminio** (gratuito): verso una posizione aggiunta negli ultimi 14 giorni (data Yahoo se inserita con `/data_erminio`, altrimenti data di rilevazione dell'import); le posizioni nuove sono segnate con ✨
  - **Saedro** (10 giorni, una volta a stagione): il GM la richiede, gli admin approvano dal gruppo con l'elenco dei giocatori della squadra in quel ruolo; ritorno automatico al ruolo originale (job ogni 15 minuti)
- **Admin**: `/admin_menu` → "🔁 Cambi ruolo" → qualsiasi squadra: ordinario per conto del GM, Erminio, Saedro diretta e **forzato admin** (non conta nel contatore; vincoli solo come avviso)
- Vincoli 4G/4F/2C bloccanti per i cambi (passano quelli che non peggiorano); giocatori con Saedro in corso non modificabili
- Annunci sul canale principale, avviso al GM per i cambi fatti dagli admin, sync dei roster di tutte le squadre
- **`/data_erminio <nome> <AAAA-MM-GG>`** (admin): data in cui Yahoo ha aggiunto l'ultima posizione (colonna `posizioni_eleggibili.data_yahoo`)

## v3.3.2 (2026-10-07)

### Miglioramenti
- Cambio ruolo: se per il nuovo ruolo è disponibile l'Erminio vengono proposti solo Erminio e Saedro (l'ordinario non è ammesso); altrimenti Ordinario e Saedro. Gli admin hanno sempre anche il Forzato
- Passaggio di conferma prima del cambio ordinario ("Userai il cambio n/2")

## v3.3.3 (2026-10-07)

### Miglioramenti
- Cambio ruolo: etichette "Erminio (ruolo aggiunto)" e "Saedro (10 day)" in bottoni, riepiloghi e annunci

## v3.3.4 (2026-10-07)

### Documentazione
- `docs/guida_gm.md` e `docs/guida_admin.md` riscritte (menu per fase, ruoli, posizioni, cambi ruolo, Stepien, DPE, parser trade, fasi)
- Indicazioni dell'annuncio di fase aggiornate: dichiarazioni post-trade e cambi ruolo in regular season, deadline e playoff; dichiarazione ruoli con import da testo e possibilità di passare da un admin
- MIGRATION aggiornato allo stato v3.3.4

## v3.3.5 (2026-10-07)

### Miglioramenti
- Annuncio trade sul canale: in ogni sezione prima i giocatori, poi le pick, i diritti in fondo

## v3.4.0 (2026-10-07)

### Nuove feature
- **Modulo condiviso `shared/ruoli_core.py`** (cartella `shared/` montata in sola lettura in bot main e bot aste): unica implementazione delle regole dei ruoli (eleggibili, vincoli 4G/4F/2C, regola dei 60 giorni, estrazione, registrazione evento). Ogni funzione riceve la funzione di query del bot chiamante. Il main la usa in `validators/ruoli.py`, `ruoli_rs.py`, `cambi_ruolo.py`; `FASI_RUOLI_RS` definita lì
- **Bot aste — ruolo insieme agli anni** (FA in regular season): dopo gli anni il vincitore sceglie il ruolo tra le eleggibili (esclusi quelli che violerebbero i minimi, con spiegazione); con la regola dei 60 giorni il ruolo è già fissato; la conferma mostra contratto e ruolo. Senza risposta in 48h: 3 anni (penale) e ruolo estratto, con avviso al GM. Il ruolo compare nell'annuncio della firma sul canale principale ed entra nell'event log condiviso (foglio, /roster, cambi ruolo). Senza posizioni eleggibili: firma senza ruolo e avviso agli admin. RFA e offseason invariati
- Guide GM e admin: ruolo nelle firme di free agency

## v3.4.1 (2026-10-07)

### Nuove feature
- Al passaggio a `regular-season-fa`: report nel gruppo admin delle squadre che non rispettano i minimi dei ruoli (4 G, 4 F, 2 C), con i conteggi per categoria dei ruoli ufficiali e i giocatori ancora senza ruolo

## v3.4.2 (2026-10-07)

### Bug fix — robustezza trade
- **Esecuzione e annullamento atomici**: approvazione, spostamento di giocatori/pick/diritti, transazioni e stato della trade avvengono in un'unica transazione DB (`_scrivi_trade`). Prima ogni scrittura faceva il proprio commit: un errore a metà lasciava una trade parzialmente eseguita
- Ogni asset viene verificato al momento dell'esecuzione (contratto ancora attivo e nella squadra che cede, pick e diritti ancora suoi): se qualcosa non torna la trade non viene toccata e l'admin riceve il motivo (`TradeNonEseguibile`); la trade resta da approvare
- Protezione dal doppio clic: una trade già approvata non viene rieseguita
- Il messaggio nel gruppo admin non dice più "approvata" prima che l'esecuzione sia riuscita
- `_valida_rollback`: controlla solo i diritti attivi (prima guardava anche diritti già firmati o scaduti)

## v3.4.3 (2026-10-07)

### Bug fix
- `/edit_trade` senza argomenti: il messaggio d'uso conteneva `<numero_bozza>` in un testo HTML e Telegram lo rifiutava ("Can't parse entities"); ora `&lt;numero_bozza&gt;`. Stesso problema corretto in `/reset_rfa` del bot aste

## v3.4.4 (2026-10-07)

### Miglioramenti — trade builder
- Selezione giocatori: ogni giocatore mostra il contratto nel formato `importo x anni` (es. `Josh Hart 20x2`)
- Riepilogo della bozza/proposta (builder, proposta ai GM, invio agli admin, modifica): contratti accanto ai giocatori
- In offseason: avviso non bloccante se una squadra dopo la trade supera i 150M (meno eventuali penalità) della regular season; resta bloccante il limite di 165M
- Validatore: calcolo del cap post-trade in una funzione unica (`_cap_post_team`), usata anche dagli avvisi

## v3.4.5 (2026-10-07)

### Miglioramenti
- `/attiva_diritti` e 🏀 Rookie nel menu: ogni bottone mostra il contratto della rookie scale (es. `Dailyn Swain (#40 2026) — 1x2`); calcolo della scala in una funzione unica usata anche dalla conferma
- Bot aste: versione mostrata al riavvio letta dal suo CHANGELOG (era fissa a "beta-1")

## v3.4.6 (2026-10-09)

### Bug fix
- Trade builder admin (/admin_menu → Trade → Build): selezionando i diritti il bot si bloccava, perché la conversazione admin non aveva lo stato dei diritti. Aggiunti tutti gli stati del builder GM che mancavano: diritti, destinazioni nelle trade a 3-4 squadre, nota, salva bozza, elimina, modifica

## v3.5.0 (2026-10-09)

### Cambi ruolo: GM e admin separati
- Due modalità distinte dal callback: `cr:` (GM sulla propria squadra) e `ca:` (admin per conto di una squadra, da /admin_menu)
- Dal /menu e da `/cambio_ruolo` anche chi è admin agisce come GM: niente "Forzato admin", Saedro sempre come richiesta. Il forzato e la Saedro diretta solo dal pannello admin
- Fasi: i cambi ruolo (GM e admin) solo in regular season e playoff; prima un admin poteva entrarci in qualsiasi fase, e così compariva anche in `offseason-ruoli`

### Menu dei comandi di Telegram per fase
- Nuovo `comandi.py`: le voci GM legate a una fase (`build_trade`, `import_trade`, `taglia`, `attiva_diritti`, `decadimento`, `dpe`, `dichiarazione_ruoli`, `cambio_ruolo`) compaiono solo quando la fase le permette, con le stesse costanti dei comandi
- Registrazione all'avvio e a ogni cambio di fase

### Pannello admin: tutto quello che fa un GM, per conto di una squadra
- Menu dinamico per fase (DPE, Ruoli in sospeso e Cambi ruolo solo quando servono), con la fase nel titolo
- 🏀 **Attiva diritti**: squadra → diritto → conferma, contratto dalla rookie scale, in qualsiasi fase; avviso al GM, annuncio, ruolo da dichiarare in RS, sync
- 🏁 **Decadimento** diretto: squadra → giocatore → motivo → conferma; avviso al GM e annuncio
- 📊 **Situazione cap** (era "da implementare"): cap occupato / tetto attuale e giocatori a roster di tutte le squadre

### Bug fix
- **CHECK di `transazioni.tipo`**: il DB di produzione era nato da uno schema più vecchio di `schema.sql` e ammetteva solo `signed, traded, firma, taglio, cut, trade, rookie, dpe, decadimento`. L'attivazione dei diritti scrive `rookie_firma` e veniva rifiutata (fino a v3.4.5 il contratto restava creato e il rookie segnato firmato, senza transazione). `migrate_db()` ora ricrea il CHECK con l'unione dei due elenchi a ogni avvio; `schema.sql` allineato
- Decadimento: transazione (tipo `decadimento`, quello ammesso in produzione) + disattivazione contratto + impatti taglio in un'unica transazione DB; `/team_diff` mostra "Decaduto"
- Approva/Rifiuta decadimento: controllo admin (prima chiunque nel gruppo poteva premere); messaggio riscritto con `text_html`; il GM riceve l'esito (prima non sapeva nulla)
- `/attiva_diritti`: il controllo cap usava sempre 150M; ora il tetto della fase (165M in offseason, 150M − penalità in RS, `settings.cap_limite_team`). Contratto, rookie e transazione in un'unica transazione DB, con i diritti bloccati (`FOR UPDATE`) e ricontrollati

### Backup unico
- Un solo backup, sempre completo, dal bot main: `pg_dump --clean --if-exists --no-owner` (ripristinabile su DB vuoto o esistente), `aste.db` come copia verificata (`integrity_check`) con il WAL già consolidato (prima veniva copiato solo il file principale e le scritture ancora nel WAL andavano perse), **tutta** la cartella config (prima `settings.json` e `divisions.json` mancavano: cercava i vecchi `settings_main/aste.json`), `secrets.tar.gpg` se presente, `MANIFEST.txt`
- Secrets: `scripts/cifra_secrets.sh` li cifra sul server (gpg AES256, passphrase) in `secrets/cifrati/`, montata in sola lettura nel bot main: il bot allega solo il file cifrato
- Didascalia con data dei secrets inclusi (o avviso se mancano) e rimando a `docs/RECOVERY.md`; tolto il link al branch `master` inesistente
- Il bot aste non manda più backup suoi (doppioni); `/backup_ora` resta come copia d'emergenza del solo DB aste
- 📊 Situazione cap: 🔴 sopra il tetto, 🟠 in offseason sopra 150M − penalità, 🔵 in RS sotto il salary floor
- Nuova guida unica `docs/RECOVERY.md` (radice del repo); eliminate `DEV_RECOVERY.md`, `emergency_recovery_progettone.md` e la guida del bot aste (nomi dei secrets, percorso di `aste.db` e file di config erano sbagliati)

## v3.5.0a (2026-10-10)

### Bug fix
- `scripts/cifra_secrets.sh`: via SSH gpg falliva con "problem with the agent: A locale function failed" (pinentry di gpg-agent). Ora lo script chiede la passphrase da sé (due volte, con controllo) e la passa a gpg con `--pinentry-mode loopback --passphrase-fd`, senza agent; verifica di decifratura con la stessa passphrase
- `docs/RECOVERY.md`: decifratura con `--pinentry-mode loopback`

## v3.5.0b (2026-10-10)

### Miglioramenti
- Backup: link "📖 Guida di ripristino" nella didascalia (e nel MANIFEST) di ogni backup, costruito da `repo_url` in `config/globals.json` (fuori da git, così l'URL non sta nel codice). Senza `repo_url` resta il testo `docs/RECOVERY.md`

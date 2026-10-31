# Changelog — Fantabasket Aste Bot

## v48 — Backup shutdown + /backup_ora + chunking messaggi lunghi

### Novità
- **Backup automatico al `docker compose down`**: hook `post_shutdown` su `ApplicationBuilder` chiama `backup_shutdown` in `scheduler.py`, che invia il backup al canale log prima che il processo si spenga. Garantisce sempre un backup aggiornato prima di ogni deploy.
- **`/backup_ora`** (admin): invia immediatamente un backup manuale al canale log con feedback esplicito su successo o errore.
- **Chunking messaggi lunghi** su `/aste`, `/all_aste`, `/firme` (admin) e `dev_rfa`, `dev_firme`, `dev_cap`, `job_status` (dev). Stesso pattern già usato per `dev_watched` e `cmd_watched`.
- **Limite `/firme`** alzato da 50 → 100. Stessa modifica in `dev_firme`.
- `BOT_VERSION` aggiornato a v48.

## v47 — Conferma offerta + conferma anni + backup ore tonde

### Novità
- **Conferma prima di ogni offerta**: sia all'apertura di una nuova asta FA che al rilancio, dopo aver inserito l'importo appare un messaggio con bottoni ✅ Conferma / ❌ Annulla che mostra giocatore, offerta attuale e importo scelto. Nuovo stato `CONFERMA_OFFERTA` nel ConversationHandler. Tutta la validazione (min, max, cap, slot) avviene prima della conferma; in caso di race condition tra conferma e pressione, `_esegui_offerta` rileva e segnala l'errore.
- **Conferma anni contratto**: dopo aver premuto "X anni" nella firma appare riepilogo (giocatore, contratto) con ✅ Conferma e ← Indietro. Helper `_anni_kb_e_testo` condiviso tra `chiedi_anni` e `firma_indietro_callback`.
- **Backup a ore tonde**: `bot.py` ora schedula `backup_giornaliero` con `run_daily` sugli orari calcolati da `range(0, 24, backup_intervallo_ore)`. Con 6h: 00:00, 06:00, 12:00, 18:00. Con 4h: 00:00, 04:00, ..., 20:00.
- `BOT_VERSION` aggiornato a v47.

## v46 — Tempo mancante in /offri, /watch, link Offri in /watched

### Novità
- `/offri`: ogni bottone mostra ora il tempo mancante alla scadenza (es. `3h` o `47min`) tramite helper `_tempo_mancante()` in `offerte.py`.
- `/watch` (nuovo comando in `user.py`): senza args mostra lista aste aperte con bottoni per seguire (✅ se già seguita, 🔔 se no); con `/watch <asta_id>` aggiunge il watch direttamente. Riutilizza il `watch_callback` esistente.
- `/watched`: per le aste in stato APERTA compare un link inline "Offri" con deep link `offri_<asta_id>`. `disable_web_page_preview=True` per evitare anteprime.
- Backup periodico ora configurabile via `backup_intervallo_ore` in `settings.json` (default 6h se non presente). Sostituisce i due `run_daily` fissi (00:00 e 12:00) con un `run_repeating` parametrico. In offseason consigliato 4-6h, in regular season 12h.
- `BOT_VERSION` aggiornato a v46.

## v1 — Base
Prima versione funzionante. Struttura iniziale del progetto con bot.py, database.py, teams.py, utils.py, scheduler.py. Flusso offerte FA e RFA base. Cap e slot dal JSON. Messaggi nel canale. Deep link dal canale per offrire.

## v2 — Cap virtuale e Watch
- Cap virtuale: somma offerte vincenti su aste aperte, controlla prima di ogni offerta
- Slot virtuale: come il cap, conta aste vincenti aperte
- Sistema watch: 🔔 nel canale, watch automatico per chi offre, notifiche push ad ogni rilancio
- Prima offerta contestuale in `/nuova_fa`
- `/me` con situazione cap e slot live
- Annuncio firma separato nel canale

## v3 — Notifica 15 minuti
- Notifica push ai watcher 15 minuti prima della scadenza con vincitore attuale
- Flag `notifica_15min` nel DB per non mandare duplicati

## v4 — Flusso RFA completo
- Logica RFA completa: 12h anni vincitore, PAREGGIO 24h
- Soglie pareggio per fascia (≤20, 21-34, ≥35) con vecchio compenso
- Anni liberi nel pareggio quando offerta sotto soglia
- Firma proprietario senza offerte
- Bottone ← Indietro nel pareggio
- Check cap e slot proprietario prima del pareggio
- `libera_cap` chiamato solo in `_registra_firma_finale` e `lascia_callback`
- Scala cap/slot anche per RFA alla firma (il giocatore RFA non occupava slot)
- Vecchio compenso liberato alla chiusura in tutti i casi
- Max 1 RFA per team per stagione

## v5 — Match giocatori e comandi admin
- Normalizzazione diacritici: Doncic = Dončić
- Sistema "intendevi?": fuzzy matching sul nome completo
- Match per cognome esatto
- `/listteams` con ID cliccabile per admin
- `/set_cap` e `/set_slot` admin live (modifica JSON senza restart)
- `/apri_mercato` e `/chiudi_mercato`

## v6 — Comandi pubblici e gestione aste
- `/aste` pubblico con lista aste in corso e ID
- `/chiudi_asta` admin con conferma
- `/annulla_asta` admin con conferma
- `/annulla` nei fallback ConversationHandler
- `conversation_timeout=300` (5 minuti)

## v7 — Timezone e messaggi canale
- Timezone Roma con `zoneinfo` (gestione automatica ora legale/solare)
- Proprietario RFA visibile nel messaggio canale e in `/aste`
- Bold nome squadra in `/listteams`
- Guida utenti nello `/start`

## v8 — Lista FA e watch avanzato
- `/lista_fa` con paginazione, fantamedia, pallino 🟡 per aste in corso, cliccabile
- Match per cognome con gestione omonimi (bottoni per scegliere)
- `/watched` con lista aste seguite
- `/listteams` e `/aste` pubblici
- Feedback privato quando inizi a seguire un'asta
- Notifica 15 minuti include vincitore e importo
- Messaggio pareggio include nome squadra vincitrice
- Ogni stato in attesa mostra "Per annullare: /annulla"
- CSV con colonne `nome`, `fantamedia`, `firmato`; giocatori FA firmati automaticamente
- Giocatori firmati spariscono dalla lista FA

## v9 — Fix critici cap/slot RFA
- Bug critico: cap e slot ora scalano correttamente alla firma RFA
- Vecchio compenso liberato dal cap proprietario alla chiusura in tutti i casi
- Check cap e slot prima del pareggio con formula `+ vecchio_compenso`
- Check slot prima del pareggio (il giocatore RFA non occupava slot)
- `scala_cap` e `libera_cap` in teams.py

## v10 — Fase offseason/regular e fix vari
- `/set_fase offseason|regular` scala cap di tutte le squadre con `cap_penalizzato`
- `"fase"` in globals.json, `"cap_penalizzato"` in teams.json
- `/me` mostra cap RS previsto in offseason con penalità
- Pallino 🟡 in `/lista_fa` anche per aste CHIUSE
- Notifica GM vincitore + messaggio canale su annullamento asta
- Check cap nel pareggio usa `+ vecchio_compenso`
- Check slot nel pareggio e nella firma proprietario senza offerte

## v11 — Refactoring architettura e messaggi ricchi
- Stato ANNULLATA nel DB (distinto da CONCLUSA)
- Migrazioni DB automatiche in `_migrate()`
- Refactoring cap RFA centralizzato: `_registra_firma_finale` gestisce sempre `libera_cap`
- `_concludi_rfa_senza_contratto` per chiusura senza firma
- Messaggi canale ricchi: timestamp offerte, chi deve fare cosa, orari firma
- Notifiche admin group quando impossibile contattare GM
- `admin_group_id` in globals.json
- Testi più esplicativi ovunque
- Fix annullamento RFA: il cap non viene mai toccato

## v12 — Settings e refactoring struttura
- `settings.json` con tutte le costanti di business modificabili live senza restart
- `settings.py` con shortcut per tutte le costanti
- `handlers/helpers.py` con funzioni condivise (aggiorna_canale, notifica_watchers, notifica_admin_group)
- `handlers/user.py` con /me, /watched, /lista_fa, watch_callback
- `handlers/offerte.py` solo flusso offerte
- `handlers/me.py` eliminato
- Import circolari rimossi
- Notifica watcher alla firma
- Vecchio compenso RFA visibile nel messaggio canale

## v13 — Nuovi comandi e miglioramenti
- Notifica proprietario RFA ad ogni nuova offerta sul suo giocatore
- `/reset_rfa` con anteprima e conferma
- `/set_cap_penalizzato` admin
- `/admin` con lista comandi admin
- Error handler globale: errori non gestiti in privato al dev
- `"dev_id"` in globals.json
- `cap_penalizzato` invece di `penalita` nel JSON

## v14 — Fix e fuzzy cognome
- Fix crash `update.message` → `update.effective_message` in `nuova_fa`
- Slot esauriti → esce dalla conversazione invece di restare in attesa
- Fuzzy cognome con gestione omonimi: `Corry` trova tutti i Curry con bottoni
- "Message is not modified" ignorato silenziosamente
- Cap/slot virtuali in `/listteams`
- Info utente nel messaggio di errore al dev
- README.md e .gitignore

## v15 — Autocap, autoslot e add_cap
- `/autocap` per GM: aggiunge cap con notifica admin e dev per verifica
- `/autoslot` per GM: aggiunge slot con notifica admin e dev
- `/add_cap` admin: aggiunge/sottrae cap (accetta negativi)
- `/add_slot` admin: aggiunge/sottrae slot (accetta negativi)
- Notifica GM quando admin tocca cap/slot
- `/annulla_offerta` admin: elimina ultima offerta, ripristina precedente, aggiorna canale

## v16 — Canale log e fix critici
- Canale log (`log_channel_id` in globals.json) per tutti i warning critici
- `log_warn()` in helpers usata ovunque
- Network errors sul canale log invece che ignorati
- Orario in tutti i messaggi del canale log
- Fix recupero stati pendenti al restart: aste CHIUSE e PAREGGIO ripristinate 5s dopo avvio
- Fix ordine operazioni `firma_callback` RFA: prima DB, poi proprietario, poi canale
- Fix cap/slot virtuali includono stato PAREGGIO
- Fix `reset_rfa` FOREIGN KEY: elimina record collegati prima delle aste
- `/add_slot` e `/autoslot` completi
- `TimedOut`/`NetworkError` sul canale log non in privato

## v17 — Stagioni e /reboot
- `/reboot` solo dev_id: invia SIGTERM e Docker riavvia
- Colonna `stagione` nelle aste e `stagione_corrente` in globals.json
- `team_ha_rfa_stagione` filtra per stagione corrente
- `/reset_rfa <nuova_stagione>` aggiorna stagione invece di eliminare aste (storico conservato)
- Nome admin e orario nelle notifiche cap/slot ai GM
- Fix nota anni in `chiedi_anni` usa settings invece di valori hardcodati
- Fix formattazione PAREGGIO nel canale (nome squadra non più ripetuto)
- Check cap virtuale negativo dopo `annulla_offerta` con warning all'admin
- Fix tag HTML non validi (`<importo>` → `&lt;importo&gt;`) nei messaggi di help
- Fix `/autoslot` CommandHandler allineato al nome corretto
- Notifica sul canale log quando il bot si riavvia con aste recuperate

## v18 — Notifiche, silenzia e documentazione
- Warning cap virtuale negativo al gruppo admin dopo modifiche cap admin (set_cap, add_cap)
- Notifica watcher quando asta viene annullata
- Notifica GM + watcher quando offerta viene annullata con /annulla_offerta
- Fix AUTOCAP → Autocap e AUTO_SLOT → Autoslot nel testo notifiche
- Fuzzy cognome con omonimi: prima chiede conferma del cognome, poi mostra lista giocatori
- /silenzia <asta_id> — smette di seguire un'asta specifica
- Hint "Per silenziare: /silenzia <id>" in ogni notifica di rilancio
- README.md aggiornato con struttura completa e credito a Claude
- docs/guida_gm.md e docs/guida_admin.md creati
- CHANGELOG.md aggiornato

## v19 — Backup, healthcheck e main channel
- Backup zip automatico (DB + config) 2x/giorno sul canale log, 1x/settimana sul gruppo admin
- Healthchecks.io ping ogni 5 minuti (`HEALTHCHECK_URL` in `.env`)
- `gm_nome` in teams.json — annuncio firma nel canale lega: "GM firma Giocatore con Squadra"
- `main_channel_id` in globals.json — annunci firma separati nel canale principale lega
- `aiohttp` nei requirements per il ping healthcheck

## v20 — /team e formula offerta massima

### Nuove funzionalità
- `/team <team_id>` solo admin — mostra cap, slot, offerte vincenti e stima cap RS di qualsiasi squadra (identico a `/me` dal punto di vista delle informazioni, ma accessibile per tutti i team)
- Formula `offerta_massima` derivata: `cap_regular - (slot_minimi_rs - 1) * minimo_contrattuale`
  - Rimossa la chiave `"offerta_massima"` da settings.json (ora è un calcolo)
  - Tre nuove chiavi in settings.json: `"cap_regular"`, `"slot_minimi_rs"`, `"minimo_contrattuale"`
  - Il valore si aggiorna automaticamente se cambiano i parametri, senza restart

### Roadmap (prossime versioni)
- **Rich messages Bot API 10.1** — messaggi canale con formattazione avanzata (bold/italic nativo, link inline, anteprime giocatore) non appena python-telegram-bot aggiornerà il supporto
- **Storico contratti per squadra** — comando `/contratti <team_id>` con lista firme della stagione corrente

## v21 — Error handling sui job periodici
- **Bug fix critico**: gli errori dentro i job di `JobQueue` (`check_scadenze`, `firma_automatica`, `pareggio_automatico`, `recupera_stati_pendenti`, `backup_giornaliero`, `backup_settimanale`) non passavano mai per `app.add_error_handler`, che copre solo gli update handler. Un'eccezione in uno di questi job restava visibile solo nei log del container, mai sul canale Telegram né al dev — causa probabile di notifiche di scadenza mancate senza alcun avviso visibile
- Nuova funzione `log_job_error()` in `handlers/helpers.py`: cattura l'eccezione, logga il traceback completo, lo invia al canale log e in privato al dev
- Tutti i job periodici ora sono avvolti in try/except che chiama `log_job_error`, senza alcuna modifica alla logica esistente all'interno
- Un'eccezione su una singola asta dentro `check_scadenze` non resta più invisibile: viene notificata su Telegram. Il giro corrente del job si interrompe comunque al punto dell'errore (comportamento invariato), ma il giro successivo (60s dopo) riprende regolarmente da capo

## v22 — Comandi di recupero emergenza
- `/ripubblica_asta <asta_id>` solo admin — pubblica un nuovo messaggio nel canale per un'asta esistente e aggiorna `canale_msg_id` nel DB. Utile se il messaggio originale viene cancellato per errore: senza questo comando `aggiorna_canale` continua a fallire ad ogni rilancio finché non si sistema manualmente il DB
- `/force_esito <asta_id>` solo admin — rimanda il messaggio di firma/pareggio appropriato al GM senza dover reboottare il bot. In base allo stato dell'asta: CHIUSA con vincitore → rimanda `chiedi_anni`; CHIUSA RFA senza offerte → rimanda il messaggio al proprietario; PAREGGIO → rimanda `_chiedi_pareggio`. Non modifica il DB, si limita a reinviare i messaggi e rischedulare i timeout

## v23 — Comandi admin avanzati e comandi dev

### Fix
- Rimosso annuncio firma duplicato su `channel_id`: ora viene mandato solo su `main_channel_id`. Il messaggio dell'asta nel canale viene già aggiornato con ✅ CONTRATTO FIRMATO da `aggiorna_canale`, l'annuncio separato era ridondante

### Nuovi comandi admin
- `/estendi_asta <asta_id> <ore>` — sposta la scadenza di un'asta in avanti di N ore, aggiorna il messaggio nel canale
- `/sposta_asta <asta_id> <YYYY-MM-DDTHH:MM>` — imposta una scadenza precisa (ora di Roma), utile per allineare più aste che scadono la stessa sera
- `/stato_asta <asta_id>` — dump completo di tutti i campi DB di un'asta con storico offerte, per debug rapido senza aprire sqlite3
- `/job_status` — lista tutti i job attivi nella JobQueue con nome e prossima esecuzione prevista, utile per verificare che i timeout automatici siano ancora schedulati dopo un recovery

### Nuovo file handlers/dev.py
Comandi riservati al solo `dev_id` (non visibili in /admin), per osservare lo stato del sistema senza aprire sqlite3:
- `/dev_aste_stato` — tutte le aste raggruppate per stato (APERTA, CHIUSA, PAREGGIO, CONCLUSA, ANNULLATA) con conteggio
- `/dev_watched` — tutti i watcher attivi raggruppati per asta con user_id
- `/dev_rfa` — tutte le aste RFA della stagione corrente con stato e team proprietario
- `/dev_firme [N]` — ultime N firme concluse con importo, anni e team (default 10, max 50)

## v24 — Robustezza input admin e nome admin nelle notifiche

### Fix
- Sostituito `update.message` con `update.effective_message` in tutti i comandi di `admin.py` — `update.message` può essere `None` in alcuni contesti (reply a messaggi forwarded, callback, ecc.) causando crash; `effective_message` funziona in qualsiasi contesto
- Messaggi di errore per argomenti non validi resi descrittivi: "❌ Serve l'ID numerico dell'asta. Usa /aste per vedere gli ID in corso." invece del generico "❌ ID non valido."

### Miglioramenti notifiche
- Aggiunto helper `_admin_label(user)` — costruisce uniformemente "Nome (@username)" o "Nome" se l'username manca
- Il nome dell'admin che ha eseguito il comando compare ora in tutte le notifiche rilevanti:
  - Annullamento asta → GM vincitore, proprietario RFA, watcher, canale
  - Annullamento offerta → GM, watcher, canale
  - Apertura/chiusura mercato FA → canale log
  - Estensione/spostamento scadenza asta → canale log

## v25 — Trasparenza azioni admin nel canale

- Chiusura asta anticipata da admin → annuncio nel canale aste con nome admin + notifica ai watcher (escluso il GM vincitore che viene già contattato per la firma)
- Apertura nuova RFA da admin → annuncio separato nel canale aste con nome admin (oltre al messaggio dell'asta già pubblicato)
- Estensione scadenza asta → annuncio nel canale aste con ore aggiunte e nuova scadenza, oltre al canale log
- Spostamento scadenza asta → annuncio nel canale aste con nuova scadenza, oltre al canale log

## v26 — /all_aste, /riapri_asta e notifica GM vincitore

- `/all_aste [stato]` solo admin — lista tutte le aste con filtro opzionale per stato (aperta, chiusa, pareggio, conclusa, annullata). Senza argomenti mostra le ultime 30. Utile per trovare l'ID di un'asta non più visibile in `/aste`
- `/riapri_asta <asta_id> [ore]` solo admin — riporta un'asta da CHIUSA o PAREGGIO ad APERTA con nuova scadenza (default 18h). Cancella i job pendenti di firma/pareggio, notifica nel canale e avvisa i watcher
- Chiusura anticipata da admin: il GM vincitore riceve un messaggio in privata che lo avvisa della chiusura anticipata prima della richiesta di firma; il proprietario RFA (se presente) viene avvisato che riceverà a breve la richiesta di pareggio

## v27 — Avviso riavvio, stagione FA, apertura RFA nel messaggio

- Avviso riavvio incondizionato sul canale log ad ogni restart, con versione e orario — prima arrivava solo se c'erano aste pendenti da recuperare
- Aggiunta costante `BOT_VERSION` in `bot.py` — compare nel messaggio di riavvio
- Stagione corrente ora salvata anche nelle aste FA (prima era `None`)
- "Aperta da X" integrato direttamente nel messaggio dell'asta RFA nel canale, invece di un secondo messaggio separato; rimosso il `send_message` ridondante

## v28 — Comandi dev, robustezza input e miglioramenti

### Fix input
- `update.message.reply_text` → `update.effective_message.reply_text` in `offerte.py` e `user.py` — stesso fix già fatto in `admin.py` in v24
- Guard su `update.message.text` in `nuova_fa_importo` (riga 230): se il GM manda uno sticker/foto/vocale durante l'inserimento importo, il bot risponde con messaggio chiaro e resta nello stato di attesa invece di crashare
- Stesso guard in `inserisci_importo` (già fixato in v27, ora allineato)

### /estendi_asta
- Accetta valori negativi per accorciare la scadenza (es. `/estendi_asta 42 -3`)
- Check che la nuova scadenza non sia nel passato
- Messaggio canale aggiornato: "estesa di Xh" o "accorciata di Xh" a seconda del segno

### handlers/dev.py — nuovi comandi dev
- `/dev` — lista tutti i comandi dev disponibili
- `/dev_cap` — cap e slot virtuali di tutte le squadre con dettaglio delle aste che li occupano (ID asta, giocatore, importo, stato)
- `/dev_log [N]` — ultime N righe di log in memoria (default 30, max 100) senza dover fare `docker compose logs` dal server
- `/dev_watched` aggiornato: mostra nome GM/team invece degli user_id numerici
- `/job_status` spostato da `admin.py` a `dev.py` — è diagnostica da dev, non serve agli altri admin

### Fix limiti autocap/autoslot
- `/autocap` e `/autoslot` ora controllano `cap_massimo` e `slot_massimo` da settings.json prima di applicare la modifica — se il risultato supererebbe il limite, la richiesta viene bloccata con messaggio descrittivo al GM

### Infrastruttura
- Aggiunto `_DequeHandler` in `bot.py`: buffer in memoria delle ultime 200 righe di log, usato da `/dev_log`
- `BOT_VERSION` aggiornato a v28

## v29 — Bug fix e /riapri_asta su aste ANNULLATE

### Bug fix
- `firma_automatica`: aggiunto `return` dopo `_registra_firma_finale` per aste FA — senza di esso veniva chiamata anche `_chiedi_pareggio` su un'asta già firmata (nessun danno pratico grazie al check su `squadra_proprietaria=None`, ma comportamento scorretto)
- `database.py`: rimossa definizione duplicata di `set_canale_msg_id` (quella senza type hints dalla v18)
- `utils.py`: cast esplicito `int(anni)` in `build_canale_message` per stato PAREGGIO — evita confronti inattesi se `anni_offerti` fosse una stringa

### /riapri_asta
- Accetta ora anche aste in stato ANNULLATA (prima dava errore)
- Per aste ANNULLATE mostra un bottone di conferma prima di procedere, per evitare riaperture accidentali
- Logica di notifica canale e watcher estratta in helper `_notifica_riapertura` per evitare duplicazione tra comando e callback

## v30 — /dev_log fix, chiusura immediata a offerta massima, check cap negativo

### /dev_log fix
- Creato `log_buffer.py` — modulo separato condiviso tra `bot.py` e `dev.py`. Prima `from bot import _log_buffer` creava un reimport che restituiva sempre una deque vuota; ora entrambi i moduli importano da `log_buffer.py` e Python garantisce la stessa istanza

### /dev_version
- Nuovo comando dev che mostra la versione corrente del bot (`BOT_VERSION` da `bot.py`)

### Chiusura immediata a offerta massima
- Se un GM offre esattamente `offerta_massima()`, l'asta si chiude immediatamente invece di far ripartire il timer di 18h. Il vincitore viene contattato subito per la scelta degli anni

### Check cap virtuale negativo con conferma dal gruppo admin
- `/riapri_asta` e `/annulla_offerta` ora controllano preventivamente se l'operazione porterebbe il cap virtuale di una squadra in negativo
- Se sì: il comando viene bloccato, il gruppo admin riceve un warning con bottoni "✅ Confermo, procedi" / "❌ Annulla". L'admin che ha dato il comando riceve conferma che la richiesta è in attesa di approvazione
- `admin_group_id` diventa obbligatorio per queste operazioni quando il cap è a rischio: se non configurato, il comando viene bloccato con messaggio esplicito
- Aggiunta `preview_annulla_ultima_offerta` in `database.py`: simula l'annullamento senza modificare il DB, usata per il check preventivo
- `BOT_VERSION` aggiornato a v30

## v31 — /lista_fa con apertura diretta asta

- `/lista_fa` ora usa bottoni con deep link diretti invece di callback — cliccando un giocatore si apre subito il flusso di offerta in privata col bot senza dover scrivere nulla
- Aggiunto ramo `nuova_fa_<nome>` in `start_deep_link`: il nome viene decodificato (underscore → spazio), verificato nella lista FA e usato direttamente come entry point per `NUOVA_FA_IMPORTO`
- I controlli esistenti (mercato aperto, asta già in corso, GM registrato) vengono eseguiti nel deep link
- `lista_fa_avvia_callback` mantenuto come fallback per vecchi messaggi già inviati prima dell'aggiornamento
- `BOT_VERSION` aggiornato a v31

## v32 — Check cap insufficiente all'avvio conversazione

- Aggiunto check cap all'avvio di tutti i flussi di offerta: se il cap libero è inferiore al minimo necessario, il bot esce subito con messaggio chiaro invece di avviare una conversazione destinata a fallire
- Nuova FA (`/nuova_fa`, deep link da `/lista_fa`, callback omonimo, callback conferma fuzzy): se cap libero < rilancio minimo → messaggio e fine conversazione
- Rilancio su asta esistente (deep link da bottone 🏀 nel canale): se cap libero < offerta corrente + rilancio minimo → messaggio con cap disponibile e minimo necessario, e fine conversazione
- Aggiunto helper `_cap_libero(team_id)` in `offerte.py` per calcolo pulito del cap effettivo
- `BOT_VERSION` aggiornato a v32

## v33 — Check cap ex ante su /offri e uscita immediata se cap insufficiente

- Aggiunto check cap in `asta_scelta_callback` (/offri): se il cap libero è inferiore al minimo necessario per rilanciare, il bot esce subito con messaggio chiaro invece di chiedere l'importo (lo stesso check già presente per il bottone 🏀 nel canale)
- Fix `inserisci_importo`: se l'errore è "cap insufficiente" e il GM non ha cap sufficiente per fare nemmeno l'offerta minima su quell'asta, il bot esce con `ConversationHandler.END` invece di restare in `INSERISCI_IMPORTO` chiedendo di reinserire
- Aggiunto check slot in `asta_scelta_callback` e in `start_deep_link`: se non ci sono slot liberi il bot esce subito con messaggio chiaro
- `BOT_VERSION` aggiornato a v33

## v34 — Refactoring /offri: no timeout, bottoni deep link

- `/offri` rimosso dal ConversationHandler — diventa un semplice comando che manda la lista aste con bottoni deep link. I bottoni non scadono mai (erano soggetti al timeout di 5 minuti del ConversationHandler)
- Paginazione di `/offri` gestita da `offri_pagina_callback`, handler globale con pattern `offri_page:N` — non scade mai
- I bottoni delle aste in `/offri` usano ora deep link `start=offri_<asta_id>` come il bottone 🏀 nel canale — il flusso di offerta passa sempre da `start_deep_link` che ha già tutti i check
- Aggiunto `_check_partecipazione(team, asta)` — helper condiviso che unifica i check cap+slot+RFA sia per `/offri` che per il deep link canale, evitando duplicazioni
- `asta_scelta_callback` rimosso (non più necessario — i bottoni sono deep link)
- Testo di `/start` ripristinato identico alla v33 (era stato modificato per errore)
- `BOT_VERSION` aggiornato a v34

## v35 — /guida, /guida_admin, /broadcast

- `/guida` — manda `docs/guida_gm.md` in privata come documento, disponibile a tutti i GM
- `/guida_admin` solo admin — manda `docs/guida_admin.md` in privata come documento
- `/broadcast <testo>` solo dev — manda un messaggio in privata a tutti i gm_ids di tutti i team. Logga i falliti sul canale log (chi non ha mai avviato il bot). Utile prima della FA per assicurarsi che tutti abbiano attivato il bot
- `BOT_VERSION` aggiornato a v35

## v36 — Recovery robusto, nuovi comandi e check cap stagionale

### Bug fix critici
- `recupera_stati_pendenti`: ora rischedulia `firma_automatica` e `pareggio_automatico` con il tempo residuo corretto dopo un riavvio — se mancano 10h alla firma automatica, viene schedulato tra 10h, non tra 48h dall'inizio. Se il timeout è già scaduto durante il downtime, viene eseguito entro 5 secondi dal riavvio
- `dev_firme`: usa `anni_contratto` invece di `anni_offerti` — il campo corretto che contiene gli anni effettivamente firmati

### Nuovi comandi dev
- `/offerta asta <asta_id> <importo>` — offerta one-shot senza ConversationHandler. Tutti i check applicati (cap, slot, stato asta, offerta minima/massima). Nessun retry: se va male, messaggio di errore e fine. Utile per offerte programmate con lo scheduling messaggi Telegram
- `/offerta` aggiunto al testo di `/dev`

### Nuovi comandi admin
- `/crea_offerta <team_id> <asta_id> <importo>` — stessa logica di `/offerta` ma per conto di un team specifico. Logga l'azione sul canale log con nome admin
- `/firme [N]` — ultime N firme concluse con nome squadra (invece di team_id) e anni_contratto (default 10, max 50)

### Job giornaliero check cap stagionale (ore 13:00)
- Ogni giorno alle 13 controlla che `Σ cap_liberi ≥ numero_teams × (cap_offseason - cap_regular) + Σ cap_penalizzati`
- Manda il risultato sul canale log con margine positivo ✅ o avviso ⚠️ se insufficiente
- Nuova chiave `numero_teams` in `settings.json` (aggiungere: 24 per questa lega)
- Validazione all'avvio: se `numero_teams` in settings non corrisponde al numero di squadre in `teams.json`, viene loggato un warning

### Fix vari
- "Message is not modified" → `ℹ️ Messaggio canale già aggiornato` invece di "⚠️ Errore di rete"
- `/guida_admin` spostata nella sezione 🏟️ Lega in `/admin`
- `&lt;testo&gt;` escaped correttamente nel testo di `/dev`
- `/admin` aggiunto al testo di `/start` (per non-admin dice non autorizzato)
- `/dev` aggiunto al testo di `/admin` (per non-dev dice non autorizzato)
- Nome repo GitHub corretto: `fantabasket_aste` (underscore) in scheduler.py, docs, README
- `BOT_VERSION` aggiornato a v36

## v37 — Fix job duplicati al riavvio e annuncio crea_offerta

### Fix job duplicati
- `chiedi_anni` e `_chiedi_pareggio` ora accettano parametro `schedula_job=True`. Nel recovery (`recupera_stati_pendenti`) vengono chiamati con `schedula_job=False` — mandano solo il messaggio al GM senza schedulare un secondo job. Il recovery schedula già il job con il tempo residuo corretto. Risultato: nessun job duplicato dopo il riavvio
- Rimosso `return` doppio in `firma_automatica` (residuo di un edit precedente, innocuo ma brutto)

### /crea_offerta
- Aggiunto annuncio nel canale aste con nome admin e dettagli dell'offerta: "🔧 Offerta registrata da X per conto di Team: YM su Giocatore"
- `BOT_VERSION` aggiornato a v37

## v38 — Pre-pareggio RFA e fix timer pareggio

### Fix timer pareggio
- Il timer `pareggio_automatico` ora parte da `conclusa_at + 24h` invece che dall'ora in cui il vincitore sceglie gli anni. Questo rispetta le regole: il proprietario ha 24h dalla fine dell'asta, non dal momento in cui riceve l'offerta completa

### Notifica proprietario alla chiusura RFA
- Alla chiusura dell'asta il proprietario riceve subito un messaggio con: importo del vincitore, scadenza esatta del pareggio (conclusa_at + 24h), avviso fascia se l'offerta è sotto soglia (min_importo da pareggiare), informazione che il vincitore ha 12h per scegliere gli anni

### Pre-pareggio RFA
- Nuova colonna DB `pareggio_preimpostato` (JSON) — migrazione automatica
- Il proprietario può pre-impostare il pareggio mentre aspetta la scelta anni del vincitore, tramite bottone "⚡ Pre-imposta pareggio" nel messaggio di chiusura
- Il bot calcola automaticamente l'importo corretto (offrire la soglia minima se sotto fascia)
- Dopo l'impostazione: bottoni "✏️ Modifica" e "❌ Annulla" fino a quando il vincitore non sceglie
- Quando il vincitore sceglie gli anni (o dopo 12h automatiche): se anni vincitore ≤ anni pre-impostati → pareggio automatico istantaneo; altrimenti chiede normalmente al proprietario
- `BOT_VERSION` aggiornato a v38

## v39 — /listteams per tutti, /list admin, /team per tutti

- `/listteams` ora disponibile a tutti i GM con formato migliorato: cap disponibile, cap libero (al netto delle aste in corso), slot occupati/totali/liberi, spazio tra le squadre
- `/list` nuovo comando solo admin — specchio del teams.json con ID, GM, gm_ids, cap, slot, penalità
- `/team <team_id>` ora disponibile a tutti i GM (non più solo admin) — rimosso testo "vista admin"
- `/team` e `/listteams` aggiunti al testo di `/start`
- `BOT_VERSION` aggiornato a v39

## v40 — Fix pareggio con cap insufficiente

- `pareggio_anni_callback`: se cap o slot insufficienti, ora mostra un popup (`show_alert=True`) invece di editare il messaggio. I bottoni per scegliere gli anni restano attivi — il proprietario può riprovare in qualsiasi momento entro le 24h, ad esempio dopo che una sua offerta su un'altra asta viene superata e il cap si libera
- `BOT_VERSION` aggiornato a v40

## v41 — RFA ≥35M: anni automatici e pareggio immediato

- Per aste RFA con offerta ≥35M (anni minimi obbligatori = 3), il flusso di scelta anni viene saltato completamente
- Il vincitore riceve un messaggio descrittivo che conferma l'offerta a 3 anni automatici
- Il proprietario riceve subito il messaggio di notifica chiusura con importo, anni (3, obbligatori) e scadenza pareggio — senza dover aspettare le 12h del vincitore
- Il timer del pareggio (24h dalla chiusura) parte immediatamente
- Il pre-pareggio non viene proposto per ≥35M (inutile — il pareggio parte subito)
- Recovery al riavvio gestisce tutto normalmente tramite i job rischedulati
- `BOT_VERSION` aggiornato a v41

## v42 — Pre-rifiuto pareggio RFA

- Nuovo bottone "❌ Non pareggerò" nel messaggio di chiusura RFA (solo per offerte <35M — per ≥35M il proprietario decide direttamente con i bottoni Pareggia/Rinuncio)
- Il proprietario può pre-impostare il rifiuto mentre aspetta la scelta anni del vincitore — appena il vincitore sceglie, il giocatore passa automaticamente senza aspettare le 24h
- Il proprietario riceve notifica che il rifiuto è stato eseguito automaticamente
- Bottone "↩️ Annulla rifiuto" per cambiare idea fino alla scelta anni del vincitore
- Se c'era un pre-pareggio impostato e si clicca "Non pareggerò", il pre-pareggio viene cancellato automaticamente
- Nuova colonna DB `rifiuto_preimpostato` — migrazione automatica
- `BOT_VERSION` aggiornato a v42

## v43 — Pre-impostazioni RFA complete e annunci canale

### Pre-rifiuto condizionale
- `rifiuto_preimpostato` ora è un intero: 0=nessuno, -1=assoluto, N=condizionale (passa al vincitore se offre >N anni)
- Rifiuto assoluto incompatibile con pre-pareggio — il bot lo impedisce con alert
- Rifiuto condizionale compatibile con pre-pareggio se i valori non si sovrappongono (es. pareggio ≤2 + rifiuto >2)
- Il bot blocca combinazioni contraddittorie con alert descrittivo

### UI pre-impostazioni
- Nuovo pannello di riepilogo pre-impostazioni con helper `_testo_stato_preimpostazioni` e `_kb_preimpostazioni` — mostra sempre lo stato di entrambe le pre-impostazioni
- Testo del messaggio di chiusura RFA <35M riscritto con spiegazione chiara delle opzioni (opzionale, risparmia l'attesa delle Xh del vincitore)
- Pre-pareggio e rifiuto ora si vedono sempre insieme nel pannello di riepilogo

### Annunci canale RFA
- Alla chiusura asta RFA <35M: annuncio nel canale con importo offerto, ore del vincitore per scegliere anni, scadenza pareggio del proprietario
- Alla chiusura asta RFA ≥35M: annuncio nel canale con importo × 3 anni e scadenza pareggio

### Logica rifiuto automatico
- `_esegui_pre_pareggio_se_compatibile` controlla prima il rifiuto (assoluto o condizionale) poi il pre-pareggio
- Notifica al proprietario descrive il motivo del rifiuto automatico con gli anni effettivamente offerti
- `BOT_VERSION` aggiornato a v43

## v44 — UX miglioramenti e annunci canale RFA

### /start
- Struttura a categorie: Azioni aste, La tua situazione, Situazione lega, Altro
- Rimossi /autocap e /autoslot dalla lista (esistono ma sono comandi rari)

### Flusso offerta
- Nel messaggio di richiesta importo per il rilancio aggiunto "Cap libero: XM"

### Conferme pareggio/rifiuto
- Prima di rinunciare al pareggio ("No, rinuncio") ora appare un messaggio di conferma con bottone "Confermo" e "← Indietro"
- Prima di confermare il pareggio ora appare un riepilogo con importo e anni e bottone "Confermo" e "← Indietro"

### Annunci canale RFA
- Messaggio 2 sul canale quando il vincitore sceglie gli anni: "Team Y offre ZM × N anni"
- Se gli anni vengono assegnati automaticamente (timeout 12h): messaggio con nota "anni minimi per fascia — nessuna risposta entro il termine"
- `BOT_VERSION` aggiornato a v44

## v45 — Fix suffissi cognome e notifica RFA proprietario

### Fix
- `trova_giocatore_fa()` (`utils.py`): i giocatori con suffisso "Jr.", "Sr.", "II", "III", "IV" venivano cercati per il suffisso invece che per il cognome reale (es. "Wendell Carter Jr." → cercava "Jr."). Introdotto helper `_cognome()` che ignora i suffissi in tutti i punti di matching (esatto, fuzzy, omonimi).
- Reintrodotta notifica al proprietario RFA ad ogni nuova offerta in `_esegui_offerta()` (`handlers/offerte.py`), persa nel refactoring v34. Il proprietario riceve un push con importo, offerente e scadenza; skippato se è già watcher dell'asta o è lui stesso l'offerente.
- `/lista_fa` (`handlers/user.py`): i bottoni deep link di giocatori con accenti o apostrofi nel nome (es. "Nikola Jokić", "D'Angelo Russell", "Wendell Carter Jr.", "Royce O'Neale") non aprivano l'asta perché il parametro `start` Telegram accetta solo `A-Za-z0-9_-`. Fix lato encoding: il nome viene normalizzato (`normalizza()`) e i caratteri non consentiti rimossi prima di costruire l'URL. Fix lato decoding (`start_deep_link`, `handlers/offerte.py`): se `trova_giocatore_fa()` non restituisce un match esatto ma ha un suggerimento non ambiguo (es. "oneale" → "O'Neale"), viene usato direttamente senza chiedere conferma — il link proviene da un bottone generato dal bot stesso.
- Aggiunto `/forza_aggiornamento <asta_id>` (admin): riedita forzatamente il messaggio canale di un'asta, con feedback esplicito su successo o errore. Utile quando `aggiorna_canale` è andato in timeout silenzioso. Se il messaggio risulta cancellato suggerisce `/ripubblica_asta`.
- Aggiunto `/team_detail` (tutti): keyboard inline con tutte le 24 squadre (2 per riga); premendo una squadra mostra cap/slot (identico a `/team`) + sezione "Offerte ultime 24h" con stato per offerta (✅ vincente con scadenza se asta APERTA, ✅ vincente senza scadenza se chiusa/conclusa, ❌ superata). Bottone "← Torna alla lista" per navigare.
- Apertura asta FA (`/nuova_fa` e deep link da `/lista_fa`): aggiunta visualizzazione cap libero e, se fase offseason, cap in Regular Season stimato (come in `/team`). Allineato al messaggio di rilancio che già mostrava il cap.
- `BOT_VERSION` aggiornato a v45

## v46 — Ruolo insieme agli anni (regular season)

- FA in regular season: dopo la scelta degli anni il vincitore sceglie il ruolo tra le posizioni eleggibili (regole nel modulo condiviso `shared/ruoli_core.py`, le stesse del bot main): esclusi i ruoli che violerebbero i minimi 4G/4F/2C, ruolo imposto dalla regola dei 60 giorni, conferma con contratto e ruolo
- Firma automatica dopo 48h: 3 anni (penale) + ruolo estratto tra le eleggibili; messaggio al GM
- Ruolo nell'annuncio della firma sul canale principale e nel contratto del DB aste (campo `ruolo`)
- Dopo la conferma il messaggio del GM mostra l'esito della firma
- `pg_client.q()`: query generica usata dal modulo condiviso
- RFA e fasi di offseason invariate

## v47 — Fix messaggio d'uso /reset_rfa

- Il segnaposto `<nuova_stagione>` in un messaggio HTML veniva rifiutato da Telegram; ora `&lt;nuova_stagione&gt;`

## v48 — Versione automatica

- La versione mostrata al riavvio è l'ultima voce di questo CHANGELOG (prima era fissa a "beta-1")

## v49 — Backup unico

- Niente più backup periodici e allo spegnimento: il backup completo (PostgreSQL + aste.db + config + secrets cifrati) lo fa il bot principale
- `/backup_ora` resta come copia d'emergenza del solo DB aste, con didascalia che rimanda a `docs/RECOVERY.md`; la copia ora usa l'API di backup di sqlite (prima il file veniva copiato così com'era e le scritture ancora nel WAL mancavano)
- Rimossa `docs/emergency_recovery.md` (si riferiva al vecchio repo separato)

## v50 — Ruolo automatico per chi ha una sola posizione

- Firma in regular season: se il giocatore ha una sola posizione eleggibile non c'è la scelta del ruolo, la conferma lo mostra già ("unica posizione eleggibile")

## v51 — Admin: apertura aste per conto di una squadra

- **`/apri_asta <team_id> <importo> <nome giocatore>`** (admin): apre un'asta FA per conto di una squadra con la sua offerta iniziale. Prima gli admin potevano solo rilanciare per altri con `/crea_offerta`. Stessa ricerca del nome di `/nuova_fa`; se il nome non è esatto il bot propone i comandi con i nomi giusti da ricopiare. Annuncio sul canale ("aperta da admin per conto di"), avviso ai GM della squadra, che seguono l'asta, e riga sul canale log
- Apertura delle aste FA in un'unica funzione (`offerte.apri_asta_fa`) usata da GM e admin: mercato, importo, cap, slot e "asta già aperta" vengono ricontrollati al momento dell'apertura (prima, per il GM, solo prima del bottone di conferma)

## v52 — Revisione contro il regolamento

- **Cap e slot impegnati anche ad asta chiusa**: tra la chiusura e la firma (fino a 48h per scegliere anni e ruolo) l'offerta vincente non contava più nel cap e negli slot virtuali, e con lo stesso cap si potevano aprire o vincere altre aste. Ora contano le aste APERTA, CHIUSA e PAREGGIO (`database.STATI_IMPEGNO`). `/riapri_asta` non conta più due volte l'asta stessa
- **RFA: il proprietario non può offrire** sul proprio RFA neanche con `/offerta` o `/crea_offerta` (il blocco c'era solo dal canale)
- **RFA occupa cap ma non slot** (regolamento): slot totali = 15 − roster + RFA in corso della squadra, per offerte, `/me`, pareggio e firma del proprietario (prima chi aveva 14 giocatori + l'RFA non poteva offrire né rifirmarlo)
- **Lascio andare**: solo il proprietario, solo su un RFA chiuso senza offerte; il contratto viene davvero chiuso su PostgreSQL con un movimento di uscita (prima la funzione veniva chiamata senza il nome del giocatore e su PG non succedeva niente: il giocatore restava in squadra). Con due GM il secondo poteva annullare una firma appena fatta dal primo
- **Regola dei 30 giorni**: chi ha avuto negli ultimi 30 giorni un giocatore poi tagliato non può aprire l'asta né rilanciare (`pg_client.squadre_regola_30_giorni`)
- **DPE nel cap per offrire**: il cap delle offerte ora usa l'importo ridotto, come `/me`
- **Rifirma dopo un taglio**: il contratto è quello firmato e la spalmatura resta com'è (prima veniva sommato tutto lo spalmato residuo all'importo annuo)
- **`/nuova_rfa`**: il giocatore va scelto dal roster della squadra proprietaria (con suggerimento se il nome non è esatto); durata da `settings` invece che 18 fisso
- Pareggio: gli avvisi di cap o slot insufficienti ora compaiono (doppia `answer()`)
- `/me`, `/team_detail`, `/listteams`: cap impegnato calcolato davvero (contratti con DPE + tagli; prima 165 − disponibile, gonfiato di 15M in regular season) ed etichetta in base alla fase
- Config: `fascia_bassa_max` va a **20** (regolamento: "≤ 20 milioni si può pareggiare qualsiasi offerta")
- **Cam Thomas exception**: la squadra che ha fatto decadere un giocatore con questa regola nell'ultimo anno può riaprirne l'asta o rilanciare solo ad almeno il contratto precedente (`pg_client.minimo_cam_thomas`)

## v53 — Menu comandi per fase e /listteams compatto

- **Menu dei comandi per ruolo e per fase** (`comandi.py`): GM in privato, admin, dev, gruppi (solo `/team` e `/listteams`). I comandi FA (`/lista_fa`, `/nuova_fa`, `/apri_asta`) compaiono solo a mercato FA aperto; quelli per offrire (`/offri`, `/offerta`, `/watch`, `/autocap`, `/autoslot`, `/crea_offerta`) anche in fase RFA o finché ci sono aste aperte; `/nuova_rfa` e `/reset_rfa` solo in offseason. La fase la cambia il bot principale: il bot aste la ricontrolla ogni 5 minuti e aggiorna il menu se cambia. Tolti dal menu `/set_cap` e `/set_slot` (non fanno più niente); `/list` descritto correttamente (squadre, non aste)
- **`/set_fase` del bot aste disattivato**: scriveva "offseason"/"regular" nel globals.json condiviso, mandando fuori fase tutti i controlli del bot principale. Ora rimanda al `/set_fase` del bot principale
- **`/listteams` compatto**: una riga per squadra, `cap occupato/tetto · liberi · roster/15`, offerte in corso solo se ci sono; avvisi ⚠️ per chi in offseason sta sopra il cap di regular season (150 meno penalità) e in regular season sotto il floor; 🔴 se cap o slot liberi sono negativi


## v54 — Guide e aiuti

- **Guide riscritte** (`docs/guida_gm.md`, `docs/guida_admin.md`) in modo discorsivo e con esempi; la guida admin spiega cosa non si fa più da qui (fase, stagione, cap e slot) e i comandi per conto delle squadre
- **`/admin`** riscritto per gruppi d'uso: tolti `/set_fase`, `/set_cap`, `/set_slot`, `/add_cap`, `/add_slot` (non fanno più niente) e `/reset_rfa`; aggiunti `/list`, `/stato_asta`, `/estendi_asta`, `/sposta_asta`, `/apri_asta` con esempi
- **`/reset_rfa` disattivato**: la stagione la porta avanti il bot principale entrando in offseason-rinnovi (e con lei si azzera la RFA di ogni squadra); scriverla da qui con il formato dell'esempio ("2025-26") rompeva i conti del bot principale. Tolto dal menu
- `/dev`: aggiunti `/backup_ora` e `/reboot`

## v55 — /autoslot che conta, guida dev

- **`/autoslot` non contava**: lo slot anticipato compariva in `/me` ma non entrava nel conteggio degli slot, quindi chi lo chiedeva restava comunque bloccato. Ora `pg_client.get_slot_totale` lo somma (come già faceva il cap per `/autocap`); il reset dal gruppo admin controlla gli slot senza l'anticipato. Tolte le prime definizioni duplicate di `get_cap_anticipato`/`get_slot_anticipato` (codice morto)
- **`/set_cap_penalizzato`** rimanda al bot principale: qui config è in sola lettura e il comando andava in errore. Tolto da `/admin`
- **Benvenuto (`/start`)** riscritto: diceva 24 ore per le RFA (sono 12) e citava comandi admin
- **Offerta massima**: documentato che chiude subito l'asta
- Nuova `docs/guida_dev.md` e `/guida_dev` (solo dev)
- `/admin` ed esempi: id squadra nel formato vero (`team07`)

## v56 — Offerta massima 141

- **Offerta massima di nuovo 141** (150 − 9, per arrivare al minimo di 10 giocatori a 1M): `settings.offerta_massima` usava `roster_max` (15) e dava 136, quindi rifiutava le offerte da 137 a 141 e chiudeva subito l'asta già a 136. Guide e README corretti

## v57 — Roster dai contratti attivi, id del giocatore nelle aste

- **Roster = contratti attivi** (`pg_client.get_roster_count`), come nel bot principale: prima si contava dall'ultimo movimento in `transazioni` e un movimento sbagliato faceva divergere i due bot (team21 aveva uno slot fantasma per un taglio pre-bot agganciato a Jokić)
- **`aste.giocatore_id`** (colonna SQLite nuova, additiva): l'id su PostgreSQL deciso all'apertura (FA dalla lista, RFA dal roster della squadra). Firma, rilascio e chiusura del vecchio contratto RFA usano l'id invece di riabbinare per nome: con un nome cambiato in anagrafica o un omonimo veniva creato un giocatore doppione. Le aste vecchie senza id cercano per nome senza mai creare
- Regola dei 30 giorni e Cam Thomas leggono la vista `movimenti_giocatori` (registro unico del bot principale v3.10.0)
- Tolto codice irraggiungibile in `database.py` (resto di un copia-incolla dopo `get_rifiuto_preimpostato`)


## v58 — Contratti finiti, RFA dichiarati

Insieme al bot principale v3.11.0.

- **Cap e slot con i contratti finiti (x0)**: `get_cap_contratti` conta i contratti in corso più gli RFA dichiarati nel bot principale (tabella `rfa_dichiarati`), `get_roster_count` solo quelli in corso. Senza stagione usano quella corrente (prima alcuni conti la saltavano e ignoravano le DPE)
- **Aste RFA aperte da sole** (`handlers/rfa.py`, ogni 5 minuti): nella fase RFA il bot apre l'asta di ogni giocatore dichiarato RFA, col vecchio contratto preso dal database; i GM del proprietario la seguono e vengono avvisati. `/nuova_rfa` resta per i casi a mano e usa lo stesso codice
- **RFA scambiato durante l'asta**: i diritti passano alla squadra che ha il contratto x0, con il messaggio del canale aggiornato e un avviso nel log

## v59 — Elenchi lunghi come file

- `/all_aste`, `/firme`, `/dev_aste_stato`, `/dev_watched`, `/dev_rfa`, `/dev_firme`, `/dev_cap` e `/job_status`: se non stanno in un messaggio arrivano come riassunto più file `.md` col testo completo (`shared/messaggi.py`, in comune col bot principale), invece di più messaggi spezzati. `/aste` e `/listteams`, che usano anche i GM, restano messaggi

## v60 — Documentazione

- README riscritto (stack, i due database, struttura, configurazione condivisa e in sola lettura, guide); guida dev con le RFA dichiarate, la diagnosi delle aste RFA che non si aprono e la regola "cap e slot uguali nei due bot"
- `/admin` e menu "/": `/nuova_rfa` è per le RFA a mano, quelle dichiarate si aprono da sole
- Tolta `docs/emergency_recovery.md`, sostituita da tempo da `docs/RECOVERY.md` del progettone

## v61 — Cap e slot condivisi col bot principale

- `get_cap_contratti`, `get_impatto_taglio` e `get_roster_count` chiamano `shared/cap.py`, la stessa implementazione del bot principale: i due bot fanno per forza gli stessi conti
- La DPE libera lo slot solo se approvata prima della deadline (come da regolamento; prima bastava una DPE qualsiasi della stagione)

## v62 — /team come /roster

- `/team` trova la squadra con la stessa ricerca di `/roster` del bot principale (`shared/squadre.py`): id, nome della squadra o del GM, anche solo l'inizio o con un errore di battitura (`/team team07`, `/team Rossi`, `/team buf`). Senza argomento mostra la propria squadra. Prima accettava solo l'id esatto

## v63 — File divisi

Niente cambia per chi usa il bot: codice spostato senza modifiche.

- `handlers/admin.py` (2.400 righe): restano `/admin`, `/guida_admin`, `/backup_ora`, mercato, i comandi che rimandano al bot principale e la registrazione; il resto in `admin_comune.py` (`is_admin`, conferma per cap negativo), `admin_squadre.py` (`/list`, `/listteams`, `/team`, `/firme`, `/autocap`, `/autoslot`), `admin_aste.py` (guardare e correggere le aste), `admin_riapri.py` (`/riapri_asta`, `/estendi_asta`, `/sposta_asta`), `admin_offerte.py` (`/apri_asta`, `/crea_offerta`, `/nuova_rfa`, `/annulla_offerta`)
- `handlers/firma.py` (1.750 righe): restano la scelta degli anni e del ruolo, la firma automatica e la registrazione dei bottoni; il resto in `firma_comune.py` (soglie, validazione, `_registra_firma_finale`, `_concludi_rfa_senza_contratto`), `firma_preimpostazioni.py`, `firma_pareggio.py` (pareggio, RFA senza offerte, lascia andare)
- Tolte `_check_cap_virtuale_negativo` e `_notifica_gm_cap_slot`, che nessuno chiamava
- Prova `regolamento_numeri_aste`: durata dell'asta, tempi di firma e pareggio, anni minimi, soglie del pareggio RFA come nel regolamento

## v64 — Log senza token

- Nei log niente più una riga per ogni chiamata all'API di Telegram (`httpx` e `httpcore` a WARNING): l'URL conteneva il token del bot e con quattro bot i log erano illeggibili. Avvisi ed errori restano

## v65 — ⏰ Tempo scaduto sul canale

- Quando una cosa si decide d'ufficio perché è scaduto il tempo, l'annuncio della firma sul canale principale lo dice con una riga **⏰ Tempo scaduto**: FA con gli anni non scelti (3 anni di penale), RFA con gli anni minimi assegnati d'ufficio (nuova colonna `anni_automatici` delle aste) o con il pareggio non deciso dal proprietario. Il ruolo estratto in regular season dice "⏰ tempo scaduto: estratto tra le posizioni eleggibili"
- Anche il **messaggio dell'asta sul canale aste** lo dice: "anni d'ufficio" già nello stato in attesa di pareggio, e tutte le note a contratto firmato (colonna `note_tempo`)
- Corretto: a contratto firmato il messaggio dell'asta diceva sempre il vincitore e la sua offerta, anche quando il proprietario aveva pareggiato (a volte a un importo diverso). Ora dice chi ha firmato davvero e a quanto, con "(pareggio)" (colonne `team_firma`, `importo_firma`; le aste vecchie restano come prima)
- Corretto: un RFA senza offerte rifirmato dal proprietario usciva sul canale principale come "pareggia"; ora "rifirma (RFA senza offerte)"
- Prova `tempo_scaduto`

## v66 — 10-day contract

- Il 10-day contract del bot principale (contratto `10day`) non pesa sul cap e non occupa uno slot anche qui (`shared/cap.py`); durante il 10-day il giocatore non è un free agent, alla scadenza torna nella lista

## v67 — numeri del regolamento in settings.json

- Tolta la costante `DURATA_ASTA_H` (18), mai usata: la durata delle aste è da sempre `durata_asta_ore` di settings.json. I minimi per ruolo usati dai controlli dei ruoli (`shared/ruoli_core`) ora vengono da settings.json

## v68 — registro delle azioni

- Ogni azione che cambia qualcosa lascia una riga nel registro delle azioni condiviso con gli altri bot (`registro.py`, main v6.0.0): aste aperte (GM, admin per conto, RFA dichiarate dal job, RFA a mano), offerte (GM; per conto con `/crea_offerta`, una sola riga in veste admin), offerte annullate, aste chiuse in anticipo, annullate, riaperte, estese o accorciate, scadenze spostate, ripubblicate, esiti rimandati, firme dopo l'asta e pareggi (GM, o sistema se è scaduto il tempo o vale una preimpostazione), RFA lasciato andare, preimpostazioni di pareggio e rifiuto, diritti RFA passati con una trade, mercato aperto/chiuso, cap e slot anticipati (e tolti), broadcast
- Le azioni da admin vanno anche sul canale log di questo bot (`log_channel_id`) nel formato unico; dove c'era già una riga (mercato, estendi/sposta, offerta per conto) ora c'è quella, non due
- Senza PostgreSQL il bot funziona come prima: la riga nel registro manca (avviso nel log del processo), quella sul canale log arriva
- Prova: `registro_aste`

## v69 (2026-10-20)

- **`/firma_per_conto [asta_id]`** (admin, Luca 20/10): scegliere anni (e ruolo in regular season) al posto del GM vincitore entro le 48 ore, con gli stessi bottoni e controlli del GM (callback `pc_firma*`). Senza id l'elenco delle aste che aspettano gli anni. Annuncio sul canale principale di sempre, i GM della squadra avvisati in privato, nel registro e sul canale log come admin «per conto della squadra». Anche per gli anni del vincitore di una RFA; il pareggio resta al proprietario (`/force_esito`)
- Anche la scelta degli anni di una RFA da parte del GM finisce nel registro
- Prova `firma_per_conto`

## v70 (2026-10-23)

- Orario del controllo del cap stagionale da `orari` in settings.json (default 13:00, come prima)

## v71 (2026-10-23)

- `/sposta_asta`: la data in tutti i formati di `shared/date_comandi` (GG/MM/AA HH:MM, GG/MM/AAAA HH:MM, AAAA-MM-GGTHH:MM)

## v72 (2026-10-24)

- **`/lista_fa` senza chi non ha giocato** (Luca, 24/10): fino a quando almeno il 70% dei giocatori **firmati** nella lega non ha giocato nella stagione in corso, ognuno coi dati più recenti (quest'anno o l'anno prima, con l'anno); poi si passa d'anno: la stagione prima non si mostra più e chi non ha ancora giocato quest'anno sparisce (la lista dice quanti). L'asta per gli altri si apre lo stesso con `/nuova_fa`: sotto «Quanto offri?» l'avviso «Stai aprendo un'asta per un giocatore che non ha giocato nella stagione in corso (dati di Basketball-Reference aggiornati al …)». I nomi della lista si collegano a quelli di bref passando dall'anagrafica (prima un «Jokic» non trovava «Jokić»). Prova `lista_fa_stagione`

## v73 (2026-10-24)

- `/lista_fa` mostra **sempre al massimo i dati dell'anno prima** (Luca, 24/10): chi non gioca in NBA da più di una stagione (ritirati, all'estero) o non ci ha mai giocato non compare mai; dopo lo switch (70% dei firmati) solo la stagione in corso. In cima quanti free agent non compaiono
- `/nuova_fa` apre l'asta per chiunque: per chi la lista non mostra, l'avviso sotto «Quanto offri?» dice **da quando non gioca in NBA** («non gioca in NBA dal 2024-25»), o che non ci ha mai giocato, con la data dei dati di Basketball-Reference

## v74 (2026-10-24)

- `/lista_fa`: accanto alla fantamedia le **partite giocate su quelle della sua squadra NBA** nella stessa stagione, es. «FM: 23.4 · 3/4 G» (Luca, 24/10): partite e squadra dall'ultima riga di Basketball-Reference, partite finite della squadra da loucabot (`nba_partite`); per la stagione prima su 82

## v75 (2026-10-24)

- `/lista_fa`: le **posizioni eleggibili** accanto al nome, es. «Jalen Esempio (SG/SF) — FM: 23.4 · 3/4 G» (Luca, 24/10)

## v76 (2026-10-24)

- `/lista_fa`: fantamedia, partite, squadra e stagione **dalla stessa riga** di Basketball-Reference, la più recente (`pg_client.dati_fa`). Prima la fantamedia veniva da una ricerca diversa e, per chi su bref ha cambiato grafia del nome tra un anno e l'altro (es. «Cissé» → «Cisse»), usciva quella dell'anno prima, «(2025)», anche dopo lo switch (Luca, 24/10)
- «FM» diventa **«FP»**, come negli altri bot


## v77 (2026-10-24)

- **Asta aperta per un giocatore senza posizioni eleggibili**: subito un messaggio al gruppo admin col comando già scritto (`/set_posizioni_eleggibili Nome PG,SG`) da usare nel bot principale prima che l'asta finisca (Luca, 24/10)
- Lo switch della lista FA (70% dei firmati) si calcola in `shared/lista_fa.py`, lo stesso usato dal report posizioni del bot principale

## v78 (2026-10-30)

- **Menu admin nel gruppo admin** (prima lì si vedeva quello dei GM) e menu dei gruppi anche per gli amministratori dei gruppi Telegram (Luca, 30/10)
- Asta aperta per un giocatore senza posizioni: l'avviso dice di scrivere `/set_posizioni_eleggibili` **in privato** al bot principale (nel gruppo non funziona)

## v79 (2026-10-30)

- Guida dei GM: «Da dove vengono i dati» (ESPN, Basketball-Reference, Yahoo)

## v80 (2026-10-31)

- Offerte e lista FA: il nome del giocatore anche con cognome e nome invertiti («Clowney Noah»), anche nelle proposte per somiglianza (`shared/parole_nome.py`; Luca, 31/10)

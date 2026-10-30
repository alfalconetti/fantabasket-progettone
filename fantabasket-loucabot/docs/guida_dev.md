# Guida dev — loucabot

Promemoria tecnico di loucabot: cosa c'è, dove sta, come funziona. Panoramica e messa in funzione nel `README.md` della cartella; storia nel `CHANGELOG.md`. Da Telegram questa guida si riceve con `/guida_dev` (solo dev).

---

## 1. Dove sta

Servizio `loucabot` del `docker-compose.yml` del progettone, cartella `fantabasket-loucabot/`:

| File | Contenuto |
|---|---|
| `bot.py` | avvio: handler, error handler (canale log e dev), job, comandi del menu |
| `comandi.py` | menu `/` per scope: gruppi, privato, admin (privato e gruppo admin), dev |
| `handlers.py` | comandi del calendario, guide, dev; `log()` al canale log; `job_sync` delle 8:30 |
| `handlers_calcolo.py` | comandi del calcolo (`/tabellini`, `/espn_giocatori`, `/espn_mancanti`, `/espn_abbina`, `/fantapunti`), snapshot degli infortunati |
| `calendario.py` | CSV della lega: lettura, controlli, import; scadenze e squadre a media; `ora()` |
| `foglio.py` | foglio Google Calendario: `griglia()` (tutta la pagina A:E) dal CSV importato e da `lega_risultati`, `aggiorna()` via gas-router |
| `calcolo.py` | punteggio del giocatore, della squadra (FADD), `esito` con supplementari; abbinamento ESPN |
| `nba.py` | ESPN: scoreboard, tabellini e `fantapunti()`, infortunati, roster; sigle; `NBA` (le 30) |
| `db.py` | PostgreSQL: `migra()` e query |
| `config.py` | `globals.json` e `teams.json` in sola lettura, riletti a ogni chiamata; `versione()` |
| `docs/` | guide GM, admin, dev |

Ambiente: `GAS_ROUTER_URL` + `GAS_ROUTER_TOKEN_FILE` (secret `gas_router_token`, lo stesso del bot principale) per il foglio; `BOT_TOKEN_FILE` (`secrets/bot_token_loucabot.txt`), `DATABASE_URL` + `PG_PASSWORD_FILE`, `GLOBALS_PATH`, `TEAMS_PATH`; per le prove `ESPN_BASE` / `ESPN_URL` sostituiscono gli indirizzi di ESPN. `config/` montata in sola lettura, `shared/` in `/app/shared` (usa `shared.squadre` e `shared.messaggi.manda_lungo`).

**globals.json** (lo scrive il bot principale): `stagione_corrente`, `admin_ids`, `dev_id`, `admin_group_id`, `log_channel_id_louca` (senza: `log_channel_id_main`).

---

## 2. Database

Stesso PostgreSQL degli altri bot. loucabot legge tutto e scrive solo le sue tabelle, **più `giocatori.espn_id` e `nome_espn`** (decisione di Luca, v5: l'id ESPN è un dato del giocatore). `migra()` è idempotente e gira all'avvio.

| Tabella | Chiave | Cosa |
|---|---|---|
| `lega_giornate` | stagione, numero | date (giorni ET), `tipo` regular/playoff, `media_file` (dal CSV), `prima_partita` e `media` (calcolate), `calcolato` |
| `lega_partite` | id; unici stagione+giornata+casa/trasferta | calendario della lega (team_id) |
| `lega_calendario_csv` | stagione | il CSV importato tale e quale: la mappa delle righe del foglio Calendario |
| `lega_risultati` | stagione, giornata, casa | punteggi regolamentari (bonus casa compreso) e dopo i supplementari, vincitore, convalida (si riempirà con la convalida delle giornate) |
| `nba_partite` | `espn_id` | partite NBA: stagione della lega (ESPN 2027 = 2026), tipo (1 pre, 2 RS, 3 playoff, 5 play-in), `data_et`, `inizio`, sigle, `stato`, `tabellino` (quando scaricato) |
| `nba_tabellini` | partita, atleta | una riga per giocatore a referto: squadra, titolare, `giocato` (FALSE = DNP), minuti, statistiche della formula, `fp` |
| `nba_infortuni` | atleta, preso | snapshot ESPN degli infortunati (uno snapshot = le righe con lo stesso `preso`; `giorno` = giorno ET): stato, dettaglio. Per il calcolo conta, per ogni giorno, `db.snapshot_del_giorno`: l'ultimo preso prima dell'inizio della prima partita del giorno (senza partite, l'ultimo del giorno). `db.pulisci_snapshot` (alle 8:30) tiene tutto per `GIORNI_SNAPSHOT` = 7 giorni, poi solo quello che conta. IPanchinari legge il più recente |
| `lega_status_validi` | stagione, giornata, atleta | status deciso da un admin con `/set_valid_status` (NULL = sano): vale per tutta la giornata e vince sugli snapshot in `punteggio_giocatori` e `_fadd_possibile`. `_fadd_possibile` non valuta chi ha ancora partite non finite nella giornata, e l'avviso "manca lo snapshot" solo per giorni prima di `calcolo.oggi_et()` |
| `lega_live` | stagione, giornata | il messaggio live sul canale principale (`chat_id`, `message_id`), `aggiornato`, `prossimo` (dopo un errore di ESPN: non prima di), `errore_log` |
| `nba_atleti` | atleta | giocatori dai roster ESPN (abbinamento prima dei tabellini, e la squadra NBA di adesso: `db.squadre_roster`, che in `punteggio_giocatori` vince sull'ultimo tabellino per chi non ha giocato nella giornata). Si aggiornano ogni mattina in `job_sync`; con tutte e 30 le squadre, chi non è in nessun roster resta senza squadra |
| `giocatori.espn_id`, `nome_espn` | indice unico su espn_id | abbinamento con l'anagrafica (anche il bot principale crea le colonne) |

`nba_tabellini.partita` → `nba_partite`: chi svuota `nba_partite` nelle prove svuota anche i tabellini.

---

## 3. ESPN

Tutto da `site.api.espn.com/apis/site/v2/sports/basketball/nba/` (pubblico, senza chiave; NBA.com dal server dà 403; bref resta riserva, limite circa 20 richieste al minuto):

| Endpoint | Uso | Lettura |
|---|---|---|
| `scoreboard?dates=AAAAMMGG` | partite del giorno; `leagues[0].calendar` = tutti i giorni della stagione | `nba.leggi_giorno`, `giorni_stagione` |
| `summary?event=ID` | tabellino | `nba.leggi_tabellino` (`boxscore.players[].statistics[0]`, `keys` + `stats`) |
| `injuries` | infortunati di adesso | `nba.leggi_infortuni` (cerca ovunque voci con `athlete` e `status`; id dal campo o dal link `/id/NNN/`) |
| `teams/gsw/roster` (sigla ESPN in minuscolo) | giocatori di una squadra | `nba.leggi_roster` |

Date ESPN in UTC → giorno della costa est (`ET`). Sigle ESPN → NBA (`SIGLE`: GS→GSW, NO→NOP, NY→NYK, SA→SAS, UTAH→UTA, WSH→WAS). Tutto quello che non è una delle 30 (`nba.NBA`), come le partite della NBA Cup da decidere, diventa `TBD`: conta per la scadenza, non come squadra.

**Fantapunti** (`nba.fantapunti`): 0,5·PTS + 2·AST + 2·OREB + 1,25·DREB + 1,5·3PM − 0,5·FGA + FGM − 0,75·FTA + FTM + 2·STL + 2·BLK − 2·TOV. Verificata sul vecchio foglio: 17/01/2026, 141 righe su 141.

---

## 3b. Foglio Calendario

`foglio.griglia(stagione)` rilegge il CSV importato (`lega_calendario_csv`) e costruisce tutta la pagina, 5 colonne: intestazioni con il testo intero in A (`foglio.intestazione`: `(media …)` sostituito con quelle calcolate, anche se nel CSV le virgole spezzavano la riga) e B:E vuote; partite come nel CSV, con i punteggi da `lega_risultati` in B e D (regolamentari nella riga delle squadre, supplementari nella riga sotto); righe vuote finali tolte. `foglio.aggiorna` → POST `gas-router/gas/calendario` (stessa web app del Roster, timeout 170 s) → `gas/calendario.gs` `handleCalendario`: trova il foglio (`CONFIG.CALENDARIO_SHEET_NAME` o "Calendario", maiuscole libere), `clearContent()` di A:E fino all'ultima riga (formattazione e celle unite restano) e `setValues` della griglia; rifiuta righe senza 5 colonne e griglie vuote. Risponde `{ok, righe}`. Lo script si prova con node simulando il foglio. Modifiche a `gas/`: `clasp push` e Nuova versione della web app.

## 4. Job

| Ora (Roma) | Job | Cosa |
|---|---|---|
| 7:45 (`orari.calcolo`) | `handlers_risultati.job_calcolo` | giornate finite (ultima notte passata, non più di 7 giorni fa), chiuse su IPanchinari e non calcolate: `nba.sincronizza` dei giorni, tabellini mancanti, `_riscarica` (le notti non congelate, cioè in pratica l'ultima, come `/ricalcola`; i cambi degli schierati col dettaglio nel canale log), `pronta` (partite chiuse, tabellini), `esegui` (calcolo, `lega_calcoli`, tab «Calcolo GN», proposta al gruppo admin) |
| 11:05 / 11:06 (`orari.primo_controllo`) | `live.job_live` («controllo») / `handlers_risultati.job_primo_controllo` | primo controllo dell'ultima notte (v60): col live aperto lo fa il live (riscarica la notte, `testo_cambi` sul log e, a giornata calcolata, agli admin con Ricalcola); col live chiuso (convalidata) un minuto dopo `primo_controllo(bot, d)`, stessa cosa senza canale. Il controllo delle 10 sulle giornate (`job_controllo`) non c'è più dalla v58 |
| 20:00 (`orari.controllo_notte`) | `handlers_risultati.job_controllo_finale` | controllo finale della notte prima (`controllo_notte`): riscarica con `forza`, cambi degli schierati agli admin con ✅/❌ Yahoo e Ricalcola, poi la notte è congelata; le notti prima della giornata lette senza salvare: se cambiano schierati, agli admin in `lega_controlli_notte` con stato «da applicare» e bottoni `cn:ag:<id>` (scrive le righe `dopo`) / `cn:la:<id>` (niente), v66 |
| 9:00 (`orari.top_notte`) | `top.job_top_notte` | top 20 della notte prima nel gruppo della lega (`globals.gruppo_lega_id`; senza, solo una riga nel log): scarica i tabellini mancanti di quella notte, poi `top.testo` (schierati della giornata da `notte.schieramento`, quintetto e panchina; prestazioni da `nba_tabellini` dei giocatori sotto contratto con `calcolo.conta`, la migliore per giocatore; sotto i firmati non schierati che stanno nella top 20 di tutti). Notte fuori da una giornata: niente |
| 8:30 (`orari.sync_nba`) | `handlers.job_sync` | partite dei giorni vicini (−3, +14), ricalcolo di scadenze e squadre a media (cambi → gruppo admin), roster ESPN delle 30 squadre (30 richieste; `db.salva_atleti` segna in `nba_movimenti` ogni cambio di squadra, anche l'uscita da tutti i roster, per la carriera dei giocatori nel bot principale), tabellini delle partite finite della stagione in corso (`handlers_calcolo.da_scaricare`: le vecchie non si ritentano; nel log quali non si scaricano e perché), abbinamento automatico dei giocatori nuovi, snapshot degli infortunati; riga sul canale log |
| 0:30, 4:30, 12:30, 16:30, 20:30 | `handlers_calcolo.job_infortuni` (`bot.ORE_SNAPSHOT`) | snapshot degli infortunati, solo nelle fasi `config.FASI_SNAPSHOT` (offseason-ruoli, regular season, playoff): con quello delle 8:30 uno ogni 4 ore; sul canale log solo se fallisce |
| ogni minuto | `live.job_live` | punteggi live: `cosa_fare` decide se aggiornare (ogni 10 minuti dalla prima partita di ogni notte alle 8:00 del mattino dopo; una volta alle 11:05, `orari.primo_controllo`, riscaricando le partite finite della notte anche a giornata calcolata, e con `testo_cambi` una riga sul canale log per i tabellini cambiati di giocatori schierati, col dettaglio delle statistiche; a giornata calcolata anche agli admin con Ricalcola). `scarica`: tabellone della notte, tabellini delle partite in corso con `finale=False` (la partita resta senza tabellino e il definitivo si riscarica a partita finita: qui, alle 7:45 o alle 8:30), quelli delle finite senza tabellino. Poi `risultati.calcola` (formazioni congelate, o `schieramenti_attuali` se IPanchinari non ha ancora chiuso) e il messaggio (`testo`) pubblicato o modificato. Errore → `prossimo` = +20 minuti, una riga sul log all'ora |
| ogni 5 minuti | `formazioni_foglio.job_formazioni` | giornate chiuse su IPanchinari, iniziate da meno di 14 giorni e non in `lega_calcoli`: tab «Calcolo GN» coi soli schierati (`griglia`: quintetti e panchine, ruolo, squadra NBA, note), solo se l'impronta delle formazioni (`firma`, sha1 di `risultati.schieramenti`) è diversa da quella in `lega_foglio_formazioni`; riga sul canale log. Dopo il calcolo non tocca più la giornata |
| ogni 10 minuti | `handlers_calcolo.job_prepartita` | uno snapshot 30-40 minuti prima della prima partita NBA del giorno, se non ce n'è già uno da 45 minuti prima |
| 10:00 (`orari.foglio_parziale`) | `formazioni_foglio.job_parziale` | giornate chiuse, non calcolate, con almeno una notte finita (`notti_passate`: `dal` < oggi ET): sincronizza partite e tabellini delle notti passate, poi `scrivi_parziale` (`R.calcola` come il live, `c["provvisorio"]` → titolo PROVVISORIO su `SF_PROVVISORIO`) e aggiorna l'impronta in `lega_foglio_formazioni`; anche `aggiorna` (ogni 5 minuti) usa `scrivi_parziale` se le formazioni cambiano dopo la prima notte |
| ogni 5 minuti | `handlers_calcolo.job_injury_fitti` | prima sera di una giornata (`finestra_fitta`: dalle `orari.injury_fitti`, 19:00 a Roma del giorno `dal`, alla prima partita): uno snapshot se l'ultimo ha più di 29 minuti, cioè uno ogni mezz'ora; IPanchinari avvisa i GM dei cambi |

Errori dei job: canale log e dev.

---

## 5. Calcolo (`calcolo.py`)

- `punteggio_giocatori(stagione, giornata, atleti)` → `{atleta: {fp, come, partite, squadra, nota}}`, con `come` ∈ partite / media / zero. Squadra NBA del giocatore: quella dei suoi tabellini nella giornata, se no l'ultima prima (`db.ultima_squadra`). Media della stagione: partite giocate di RS e play-in prima della giornata (`db.medie_stagione`). Una riga conta (`calcolo.conta`) se è entrato, e uno 0 con 0 minuti no (vale anche per la media della stagione). Indisponibile: stato diverso da Probable/Active in tutti gli snapshot dei giorni della giornata; senza snapshot prende la media con un avviso.
- `punteggio_squadra(giornata, quintetto, panchina, punteggi)`: quintetto e panchina sono `[{atleta, ruolo, nome}]`, panchina in ordine. FADD (`_fadd_possibile`): titolare a 0 per "non ha giocato", tag in tutti i giorni in cui la sua squadra ha giocato, o in tutti i giorni della giornata se non ha giocato (manca uno snapshot → avviso, decide l'admin); entra il primo panchinaro dello stesso ruolo; una sola sostituzione; la panchina scala.
- Titolare anche in panchina (v40, Luca 23/10): in `punteggio_squadra` resta nella panchina al suo posto con `fp` 0 e `doppio: True` (non scala, non entra per la FADD, ai supplementari vale 0); i ceduti (`ceduto`) invece escono e gli altri scalano. Squadra NBA di chi non ha giocato: per le giornate finite da più di 7 giorni solo l'ultimo tabellino (`oggi_et`), non i roster ESPN di adesso.
- `esito(casa, trasferta, bonus)`: scarto minimo `scarto_minimo` (5), supplementari con i panchinari (`giocatori_panchina`, 5, poi 0), bonus casa `bonus_casa`/`bonus_casa_playoff` (3/5): numeri di `config/settings.json` via `shared/regole.py`, pari → trasferta. `punti_supplementari`: i soli punti dei supplementari, quelli che vanno in `lega_risultati.supp_*` e sul foglio Calendario sotto i regolamentari.
- `abbina_auto({atleta: nome})`: `norm()` (senza accenti, Đ/ø/ł…, punteggiatura, Jr./Sr./II–V) uguale a uno e un solo giocatore dell'anagrafica (nome_common, nome_bref, nome_yahoo) e a un solo atleta ESPN; i già abbinati non si toccano.

Orari dei job: `shared/regole.orario(...)` (`"orari"` in settings.json, default in `shared/regole.ORARI`): `calcolo`, `sync_nba`, `top_notte`, `primo_controllo`, `controllo_notte`, `controllo_tabellini` (non più usato), `fine_live_notte`, `partita_nuova`, `injury_fitti`, `foglio_parziale`; letti all'avvio (`injury_fitti` a ogni giro).

---

## 5a. Calcolo della giornata (`risultati.py`, `handlers_risultati.py`)

- `risultati.calcola(stagione, n)`: giornata, `lega_partite`, schieramenti di IPanchinari (`ipa_formazioni`: un giocatore per ruolo; `ipa_panchine.righe`: `giocatore_id`, testo e `ruolo` congelato alla scadenza; senza ruolo quello di `ruolo_attuale`), giocatore → `espn_id` → `calcolo.punteggio_giocatori`, `punteggio_squadra`, `esito` (bonus 3, 5 se `lega_giornate.tipo` = playoff). Avvisi: quintetto incompleto, panchina mancante (senza supplementari), giocatori senza id ESPN, avvisi della FADD. `_dettaglio`: fantapunti per notte (solo le righe che `calcolo.conta`), medie, status per notte (snapshot che conta o `lega_status_validi`).
- `risultati.griglia(c)`: il tab «Calcolo GN» come matrici (righe, sfondi, testi, pesi, formati) della stessa forma; formule in inglese con le virgole (`SUMIFS`, `INDEX/MATCH`, `IFERROR`, `COUNTIF`, `ROUND`), come le vuole Apps Script. Punteggio = `IF(COUNT(notti)>0, ROUND(AVERAGE(notti)*8,0)/8, IF(AND(a media="sì", indisponibile="no"), media, 0))`: le colonne «a media» e «indisponibile» sono quelle che ha usato il bot. **Deve dare gli stessi numeri del bot**: `tests/louca/louca_risultati.py` lo verifica ricalcolando il foglio con LibreOffice.
- `payload_foglio` / `scrivi_foglio` → `foglio.manda_gas("calcolo", …)` → gas-router `/gas/calcolo` → `gas/calcolo.gs` `handleCalcolo`: file `CONFIG.CALCOLO_SPREADSHEET_ID` (o quello del Roster), tab `Calcolo GN` creato se manca, `clear()`, valori (`setValues` senza le formule), formule con `setFormulas` colonna per colonna (con `setValues` verrebbero lette nella lingua del foglio: in italiano #ERROR!), controllo degli #ERROR! con `getDisplayValues` e, se ce ne sono, riscrittura col ";" (`sintassi` ed `errori` nella risposta), sfondi, colori, grassetti, formati (`[{range, formato}]`), righe e colonne bloccate (il bot manda 0: niente blocchi); rifiuta nomi diversi da `Calcolo GN`.
- `lega_calcoli_storico` (stagione, giornata, versione; v6.9.0): ogni versione salvata da `salva_calcolo` (risultati, avvisi, quando) e, alla convalida, `convalidato` su quella convalidata; al primo avvio ci copia le righe di `lega_calcoli`. `risultati.testo_storico` (`/storico_calcolo N`) confronta ogni versione con la precedente (`risultati.confronta`, lo stesso confronto di `differenze`).
- `lega_calcoli` (stagione, giornata): la proposta (`risultati` JSON, avvisi), `versione` (+1 a ogni ricalcolo), `stato` da_convalidare / convalidata, `messaggio` nel gruppo admin. `risultati.convalida`: `lega_risultati` (con `convalidato`) dalla proposta, poi `foglio.aggiorna` del Calendario. `lega_risultati.supp_*` = i soli punti dei supplementari.
- Callback `rc:ok:<N>:<versione>` (convalida, solo se la versione è quella di adesso e da convalidare) e `rc:re:<N>` (ricalcola); `/ricalcola N`. Ricalcolo e riscaricamento girano in un task (`application.create_task`).

## 5c. Live, convalida, /notte, /partita

- **Congelamento per notte e controllo finale** (v58): `congelamento.notte_congelata(d)` = scelta a mano della notte (`lega_notti_congelate`), poi della giornata (`lega_congelamento`), poi la regola `adesso() >= fine_notte(d)` (20:00 Roma del giorno dopo, `orari.controllo_notte`); `stati` per giornata (congelata = tutte le notti); `da_tenere(partite)` usato da `nba.scarica_tabellini` (salta le partite con tabellino di notti congelate, salvo `forza`; `salva=False` legge e basta, in `letti`); `righe`/`cambi`/`dettaglio`/`riga_cambio` per i cambi col dettaglio delle statistiche (`STATISTICHE`). `handlers_risultati.job_controllo_finale` (20:00) → `controllo_notte(bot, d)`: riscarica con `forza`, cambi degli schierati al gruppo admin con ✅/❌ Yahoo (`cb_controllo`, `cn:ok|no:<id>`, `lega_controlli_notte` con le righe di prima e dopo; ❌ le rimette) e Ricalcola; poi le notti prima della giornata lette senza salvare, sul log. `/controllo_notte`, `/congela_notte`, `/scongela_notte`, `/congelamento_notti`. Il primo controllo alle 11:05 (v60) riscarica sempre l'ultima notte: lo fa il live se è aperto, se no `job_primo_controllo` (anche a giornata convalidata).
- **Congelamento** (v56, `congelamento.py`, regola delle ultime 3 giornate superata dalla v58): `stati(s)` → per giornata da giocare / in corso / aperta / congelata (ultime `FINESTRA` = 3 finite aperte, `al < oggi` ET; `lega_congelamento` per le scelte a mano, che valgono più della regola); `congelata(s, n)` decide se `/ricalcola` riscarica; `/congela`, `/scongela`, `/congelamento`, `/correggi_tabellino` (aggiorna `nba_tabellini.fp` di una partita) con registro, canale log e canale principale (`_annuncia`). `oggi_et` sostituibile nelle prove.
- **Ricalcolo di una giornata convalidata** (v55): `risultati.differenze(stagione, n, risultati)` confronta coi `lega_risultati` convalidati (tolleranza 0,01: lì 2 decimali, nel calcolo gli ottavi) e `testo_differenze` lo scrive; in `esegui` (proposta) e nella conferma della convalida (letto prima di `convalida`, che sovrascrive). `live.pubblica_definitivo(..., prima=)`: chi vinceva nella convalida di prima quando `lega_live.esiti` non c'è.
- **Live come immagine** (v53, Luca 23/10): `aggiorna` manda sul canale `immagine(dati_immagine(c, ora))` (`live.typ`, typst della libreria, ppi 170) con `didascalia`, e ai giri dopo `edit_message_media` sullo stesso messaggio; se fallisce (messaggio di testo di prima della v53, o cancellato) lo cancella e ne manda uno nuovo. `dati_immagine`: per partita `avanti` (vuoto con più di `MAX_DA_GIOCARE` ancora da giocare o con un quintetto vuoto), `nota` (HANNO GIOCATO IN MENO DI 6, SI VA AI SUPPL., QUINTETTO VUOTO), per squadra `stato_titolari` (campo, giocare, rigiocare con `finora`, media = `come == "media"`, finito; etichette al plurale), logo da `partita._logo`, colore `colore_header` di teams.json o viola. Emoji dal font Noto Color Emoji (`fonts-noto-color-emoji` nel Dockerfile, `font: ("Liberation Sans", "Noto Color Emoji")` nel template); `font_emoji()` controlla che ci sia e, se manca, una riga nel canale log una volta per avvio. `/live_results [N]` (`cmd_live_results`): `testo` dai tabellini già scaricati, a pezzi con `_pezzi` (tagli tra una partita e l'altra); giornata da `giornata_live` (live aperto più recente, se no `calendario.da_mostrare`).
- **`/giornata` e `/risultati`** (`handlers._mostra_giornata`, v62): giornata iniziata (`dal` ≤ `nba.oggi_et()`) e non convalidata → `live.calcolo` e `live.testo(quale="live" | "calcolata")` a pezzi (titolo diverso a seconda di `_stato_calcolo`); se il calcolo fallisce, log e l'elenco delle partite.
- **Classifica a colori** (`classifica.colori`, v62): `DIREZIONI` (e `DIREZIONI_FULL`) dicono per colonna se il migliore è il più alto (+) o il più basso (−); W/L e supplementari esclusi; nei dati Typst `col` per riga {colonna: best/worst}, `col()` in `classifica.typ` colora.
- **Live** (`live.py`): `testo` con una riga vuota tra le partite e, per squadra, `ancora_in_ballo(c, titolari)` → (devono giocare, devono rigiocare, fantapunti già fatti da chi deve rigiocare). `lega_live.chiuso` (giornata convalidata: `tick` la salta), `definitivo_id` (il messaggio dei definitivi), `esiti` (chi vinceva alla convalida).
- **Convalida** (`handlers_risultati.cb_risultati` → `live.pubblica_definitivo`): messaggio dei risultati definitivi sul canale principale (`testo_definitivo`, in fondo `statistiche_giornata`: 🔝/🔻 da `lega_risultati`, ⭐ il più alto valore contato tra titolari e supplementari usati, 💥 la miglior singola partita da `dettaglio.notti`, 👀 il migliore tra i giocatori a roster con `calcolo.conta`; chi prende media escluso; v62; a una nuova convalida si modifica lo stesso), cancellazione del live; se rispetto alla convalida precedente cambia chi vince una partita, un messaggio in più in risposta.
- **`/notte`** (`notte.py`): `notte_di_default` (giorno ET, prima di mezzogiorno a New York quello prima), `schieramento` (formazione congelata della giornata o quintetto di adesso), `testo_notte`.
- **`/partita`** (`partita.py` + `partita.typ`, Typst come la classifica): `leggi_argomenti` (squadra, GN, due squadre con «-»/«vs» o due nomi attaccati), `giornata_di_default` (→ `calendario.da_mostrare`, la stessa di `/giornata` e `/risultati` dalla v52: prima giornata non convalidata, ma la nuova solo dalle `orari.partita_nuova` del suo primo giorno), `sfide`, `dati` (dal calcolo di `live.calcolo`; celle per notte `_cella`: fp, live, dnp, prossima «vs/@», rinviata, vuota; «Punti effettivi» (campo `conta`), media della stagione da `dettaglio.medie`, foto da `foto.percorso` (tondo ritagliato sulla faccia in `partita.typ`, iniziali se manca), tag esce/entra/media/S1…/doppio/ceduto; per una giornata convalidata in testa `lega_risultati`, con una nota se il ricalcolo di oggi dà altro), `immagine`. Callback `pt:<N>:<casa>:<trasferta>`.

**`/player`, partite saltate** (v54): `player.partite_squadra(tab, squadra_attuale, stagione, atleta)` = partite finite delle sue squadre NBA mentre c'era (tratti dai tabellini; la prima dall'inizio della stagione, le altre dal giorno dopo l'ultima con la squadra prima, mai prima dell'arrivo in `nba_movimenti`; quella di adesso, da `squadre_roster`, fino a oggi); `ultime(tab, partite)` mette insieme giocate, «non è entrato» e saltate, quelle di fila in una voce sola, le ultime 5 voci. `eta(nato)` per la data di nascita (`giocatori.data_nascita`). `anno_prima(gid, stagione)`: ultima riga di `bref_stats` della stagione prima (bref numera col secondo anno: la stagione `stagione` della lega è la `stagione+1` di bref, quella prima la `stagione`), dal nome di bref o comune.

**Foto ESPN** (`foto.py`, v42): cartella del container in `FOTO_DIR`, montata da `config/foto` sul server (l’unica di config/ in scrittura), `indice.json` con quando e con quale squadra NBA. `job_foto` ogni minuto, solo dalle 2 alle 6 di New York, **una foto per giro**: prima quelle che mancano ai giocatori a roster, poi a tutti gli altri attivi in NBA (`nba_atleti.squadra` non vuota, cioè in un roster ESPN; v64), poi a tutti gli altri del database con un id ESPN (`nba_atleti` e `giocatori.espn_id`; v65, Luca 30/10), poi chi ha cambiato squadra NBA, poi le più vecchie (14 giorni, 90 per chi non è a roster né in un roster NBA: `VECCHIA_ALTRI`), poi le «mancanti» (ESPN non le ha) dopo 3 giorni (30 per chi non gioca). Prima la 520×380 dal combiner, se no l'intera. In `/player` la foto si compone con Typst (`foto_player.typ`, `player.immagine`) su uno sfondo viola col nome: le PNG di ESPN sono trasparenti e su Telegram uscirebbero su fondo nero. Un 429 ferma il job per 20 ore. `/player` (`player.manda`) non scarica mai: foto se c'è (didascalia fino a 1024 caratteri, oltre foto e testo sotto), se no solo testo.

## 5b. Comandi dev

Solo per `dev_id`, nel menu `/` del dev.

| Comando | Cosa fa |
|---|---|
| `/dev` | l'elenco dei comandi dev |
| `/guida_dev` | questa guida, come file |
| `/dev_version` | versione (ultima voce del CHANGELOG) |
| `/job_status` | job programmati e prossima esecuzione |
| `/dev_prova_calcolo GG/MM/AAAA GG/MM/AAAA` | prova del calcolo prima che si giochi: gli accoppiamenti della giornata corrente o prossima, i quintetti di adesso (`ipa_quintetto`) e le panchine già mandate, sulle partite NBA vere dei giorni indicati (1-5, già giocati: li scarica con i tabellini). Scrive il tab «Calcolo G0» sul foglio e manda la proposta solo al dev, senza bottoni; non salva niente in `lega_calcoli` né in `lega_risultati`. Le medie sono quelle della stagione NBA di quei giorni, sulle sole partite nel database |
| `/dev_ricalcola_fp [STAGIONE]` | dopo un cambio di `pesi_fantapunti` in `config/settings.json` (`shared/regole.py`): `handlers_calcolo.ricalcola_fp` riscrive `nba_tabellini.fp` delle partite della stagione con l'espressione SQL dei pesi (`regole.espressione_sql`) e, se c'è `bref_stats`, riscrive il trigger (`regole.allinea_bref`) e ricalcola la fantamedia di quella stagione. Niente richieste a ESPN né a basketball-reference; `lega_risultati` non si tocca. Riga sul canale log |
| `/dev_prova_live [GG/MM/AAAA …]` · `stop` | prova del live (`prova_live.py`) su notti vere, anche di preseason (tipo 1, che il calcolo ignora): giornata finta coi giorni indicati (al massimo 5, senza date oggi ET), accoppiamenti della giornata corrente o prossima, quintetti e panchine di adesso. Stessi orari del live (ogni 10 minuti dalla prima partita alle 8, poi alle 11:05), stesso calcolo e messaggio, **solo al dev**. **Niente nel database**: partite e tabellini restano in memoria (`STATO`), e durante il calcolo (sincrono) `db.partite_nba` e `db.tabellini_atleti` sono sostituite coi dati in memoria (`dati_in_memoria`). Job `dev_prova_live` ogni minuto, si toglie da solo dopo le 11:05 dell'ultimo giorno; un riavvio la ferma |
| `/dev_giornata [N]` | tutto su una giornata (la corrente senza N): date, scadenza, squadre a media calcolate e del calendario, partite NBA per stato con quante hanno il tabellino, snapshot degli infortunati per giorno, risultati salvati e convalidati |
| `/dev_log [N]` | ultime N righe di log in memoria (30, massimo 100) |
| `/dev_pg` | connessione a PostgreSQL (versione) |
| `/dev_foto` | foto ESPN dei giocatori a roster, degli attivi in NBA e di tutti quelli del database (`foto.stato_foto`): quante ci sono, quante in cartella e in coda per il job notturno, chi manca (da prendere, ESPN non ce l'ha, senza id ESPN) |
| `/reboot` | riavvia il bot (il processo esce, Docker lo fa ripartire) |

`/dev_log`, `/dev_pg` e `/reboot` sono in `shared/dev_comune.py`, uguali in IPanchinari.

**Errori non gestiti** (`dev_comune.error_handler`): log del container, poi canale log e dev col tipo di errore, chi e quale bottone o comando. "Message is not modified" (un bottone premuto due volte, stesso testo) non si segnala; gli errori di rete vanno solo sul canale log, per accorgersi se il bot non raggiunge Telegram.

## 6. Prove

`tests/run.sh louca_calendario louca_calcolo louca_foglio` (mai sul server: svuotano tabelle). Dati veri ridotti in `tests/louca/`: `espn-20261022.json` (scoreboard), `espn-summary-20260301.json` (tabellino NYK-SAS con infortunati). `tests/docs/guide_e_menu.py` controlla che i comandi citati in README, guide, `/start` e menu esistano.

## 7. Rilascio

Come gli altri bot: zip cumulativo con `deploy.sh`; `rilascio-X.json` con `"loucabot"` in `riavvia`. Un secret nuovo nel compose va creato prima del deploy (`deploy.sh` controlla e si ferma).

**Menu dei comandi** (`comandi.py`): privato (GM), admin e dev in privato, gruppo admin (menu admin), tutti i gruppi e anche gli **amministratori dei gruppi** (`BotCommandScopeAllChatAdministrators`, stesso menu dei gruppi; v61, Luca 30/10: diventato admin del gruppo della lega non vedeva più /partita e /classifica).

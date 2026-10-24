# Guida dev — bot aste

Promemoria tecnico del bot delle aste FA e RFA. Struttura generale del progetto, database PostgreSQL, fogli, backup e deploy sono nella guida dev del bot principale (`fantabasket-main/docs/guida_dev.md`). Qui c'è quello che è specifico delle aste. Da Telegram: `/guida_dev`.

---

## 1. Come sta in piedi

Il bot lavora su **due database**.

**SQLite (`/data/aste.db`, volume `aste_beta_data`).** È il suo database: aste, offerte, chi le segue. Resta SQLite per scelta, così si può sempre tornare al vecchio bot aste standalone (v48). Le modifiche allo schema sono **solo additive**: colonne nuove con default, mai rinominare o togliere.

**PostgreSQL** (lo stesso del bot principale, via `pg_client.py`). Da qui legge contratti, tagli, DPE e roster, cioè cap e slot, e gli RFA dichiarati (`rfa_dichiarati`) per aprire le aste RFA. Ci scrive:

- le firme (`contratti` + transazione `signed`);
- i rilasci RFA (`expired`);
- cap e slot anticipati;
- la coda dei fogli (`gas_sync_queue`, che poi svuota il bot principale).

**Config.** `config/` è montata **in sola lettura**: globals, teams, settings, fa_players.csv. Fase, stagione, mercato, penalità e squadre li decide il bot principale. Il bot aste li legge e basta: `/set_fase`, `/reset_rfa`, `/set_cap`, `/add_cap`, `/set_slot`, `/add_slot` e `/set_cap_penalizzato` qui rispondono soltanto rimandando all'altro bot.

**Modalità isolata.** Se `PG_URL` è vuoto, `pg_client` restituisce valori neutri e cap e slot vengono da `cap_disponibile`/`slot_disponibili` di teams.json, mentre la lista FA viene da `fa_players.csv`. Serve solo per emergenze e per alcune prove; in produzione non dovrebbe mai succedere.

**Variabili d'ambiente:**

| Variabile | Uso |
|---|---|
| `BOT_TOKEN_FILE` | token |
| `GLOBALS_PATH`, `SETTINGS_PATH`, `TEAMS_PATH`, `FA_CSV_PATH` | config |
| `DB_PATH` | aste.db |
| `PG_URL` + `PG_PASSWORD_FILE` | PostgreSQL |
| `HEALTHCHECK_URL` | facoltativa |

**Chat** (da globals.json):

| Chiave | Uso |
|---|---|
| `channel_id` | canale aste, con un messaggio per asta che si aggiorna |
| `log_channel_id` | log del bot aste |
| `main_channel_id` | annuncio delle firme |
| `admin_group_id` | conferme e avvisi |

**Versione.** È l'ultima voce `## vNN` del suo `CHANGELOG.md`.

---

## 2. SQLite

| Tabella | Contenuto |
|---|---|
| `aste` | `tipo` (FA/RFA), `giocatore` (nome, per messaggi e ricerca), `giocatore_id` (id su PostgreSQL deciso all'apertura, v57), `squadra_proprietaria` e `vecchio_compenso` (RFA), `stato`, `offerta_corrente`, `offerente_team_id`, `anni_offerti`/`anni_contratto`, `creata_at`/`scade_at`/`conclusa_at`/`firmato_at` (ISO UTC), `stagione`, `canale_msg_id`, `notifica_15min`, `pareggio_preimpostato` (JSON), `rifiuto_preimpostato` |
| `offerte` | storico: `asta_id`, `team_id`, `importo`, `timestamp` |
| `aste_watch` | chi segue cosa: `asta_id`, `gm_id` |
| `contratti` | copia locale delle firme (eredità dello standalone; la verità è su PostgreSQL) |

**Stati dell'asta:**

```
APERTA ──scade──▶ CHIUSA ──anni scelti (FA)──────────────▶ CONCLUSA
   │                │
   │                └─anni scelti (RFA)─▶ PAREGGIO ──decisione/timeout──▶ CONCLUSA
   │
   └──senza offerte──▶ CONCLUSA  (RFA senza offerte: decide il proprietario)

qualsiasi ──/annulla_asta──▶ ANNULLATA      CHIUSA/PAREGGIO/ANNULLATA ──/riapri_asta──▶ APERTA
```

**Cap e slot virtuali.** `database.STATI_IMPEGNO = ("APERTA","CHIUSA","PAREGGIO")`: un'asta in cui la squadra è in testa impegna cap (`get_cap_virtuale`) e uno slot (`get_slot_virtuali`) fino alla firma.

---

## 3. I conti di cap e slot

Tutto passa da qui: `/me`, `/team`, `/listteams`, apertura, offerte, firma, pareggio.

**Tetto** (`settings.py`):

- `cap_limite()` = 165 in offseason, 150 in regular season;
- `penalita_cap(team)` = 0 in offseason, `cap_penalizzato` di teams.json in regular season.

**Cap libero per offrire** (`offerte._cap_libero`):

```
cap_limite − contratti (con DPE ridotta) − spalmature della stagione − penalità + cap anticipato
          − cap virtuale (aste APERTA/CHIUSA/PAREGGIO in cui la squadra è in testa)
```

`pg_client.get_cap_totale` è la stessa cosa senza la parte virtuale (la usa `/me`).

**Cap e slot da `shared/cap.py` (v61).** `get_cap_contratti`, `get_impatto_taglio` e `get_roster_count` chiamano le stesse funzioni del bot principale, quindi i due bot fanno per forza gli stessi conti. Regole: anni residui = `anni_originali − (stagione − stagione_firma)`; un x0 non pesa né su cap né su slot, tranne l'RFA dichiarato nel bot principale (`rfa_dichiarati`), che pesa sul cap; la DPE riduce l'importo e libera lo slot solo se approvata prima della deadline. Senza `stagione` usano quella corrente.

**Slot** (`pg_client.get_slot_totale` → `teams.check_slot_virtuale`):

```
roster_max − roster (contratti attivi in corso, esclusi i DPE approvati prima della deadline)
          + RFA con asta in corso e contratto non finito  (aste aperte a mano: l'RFA occupa cap ma non slot;
                                                            gli x0 sono già fuori dal roster)
          + slot anticipato                           (/autoslot, 48 ore)
          − slot virtuali
```

**Altri limiti:**

- **Offerta massima:** `settings.offerta_massima()` = `cap_regular − (roster_min_regular − 1)`, oggi 150 − 9 = 141.
- **Rilancio:** almeno `rilancio_minimo` sopra l'offerta corrente, mai su te stesso.

**Check aggregato** (job delle 13, solo offseason). Somma il cap occupato di tutte le squadre e lo confronta con 24 × 150, per capire se al passaggio in regular season qualcuno andrà in negativo. Il risultato va sul canale log.

---

## 4. I flussi

Quale regola del regolamento sta dove (anche nel bot principale) e quale prova la controlla: [`docs/regolamento_e_codice.md`](../../docs/regolamento_e_codice.md).

### Apertura FA

- **Dal GM:** `/nuova_fa` oppure il bottone di `/lista_fa` (`fa_avvia:`). La lista (`user.righe_lista_fa`, v72) col filtro della stagione: `pg_client.stato_stagione` (righe di `bref_stats` della stagione in corso, dal nome comune al nome di bref passando da `giocatori`), switch quando almeno `QUOTA_GIOCATO` (0,7) dei giocatori **firmati** (contratti attivi) ha giocato nella stagione in corso; `mostrabili`: sempre al massimo l'anno prima, dopo lo switch solo la stagione in corso; `avviso_non_ha_giocato` per chi non è mostrabile, con l'ultima stagione giocata (`ultima`) o «mai»; nell'etichetta «FP: x · g/tot G» (`dati_fa`: fantamedia, partite, squadra e stagione dalla stessa riga di bref, la più recente, v76; `partite_squadre`: partite di regular season finite della squadra in `nba_partite` di loucabot, sigle bref → ESPN con `SIGLE_BREF_ESPN`; 82 per la stagione prima se loucabot non le ha); posizioni eleggibili accanto al nome (`posizioni_fa`, vista `posizioni_attuali` del bot principale) e sotto «Quanto offri?» (4 punti in `offerte.py`) esce `pg_client.avviso_non_ha_giocato`. Dal canale c'è il deep link `/start offri_…` o `nuova_fa_…`.
- **Dall'admin:** `/apri_asta`.

Tutte e due finiscono in `offerte.apri_asta_fa(context, team, giocatore, importo, watcher_ids)` → `(asta_id, errore)`, che ricontrolla:

- mercato aperto;
- importo (minimo, massimo);
- cap e slot;
- asta già aperta;
- regola dei 30 giorni;
- minimo Cam Thomas.

Poi crea l'asta, pubblica il messaggio nel canale, avvisa il canale log e mette tutti i GM della squadra in watch.

**La lista FA.** `get_fa_rows_pg()` prende dall'anagrafica i giocatori senza contratto attivo, esclude i diritti 2nd non firmati e ordina per fantamedia bref. La ricerca per nome è `utils.trova_giocatore_fa`: esatto → cognome → fuzzy, con gli omonimi da scegliere (`fa_omonimo:`).

### Offerta

Tre ingressi, che finiscono tutti in `offerte._esegui_offerta(context, team, asta_id, importo, gm_id)`:

- conversazione `/offri` → asta → importo;
- deep link dal canale;
- `/offerta asta <id> <importo>`, senza conversazione e quindi programmabile.

`_esegui_offerta` controlla:

- stato APERTA;
- che la squadra non sia la proprietaria dell'RFA;
- che non sia già in testa;
- rilancio minimo e offerta massima;
- 30 giorni e Cam Thomas;
- cap e slot.

Se va bene registra l'offerta, porta `scade_at` a ora + `durata_asta_ore` (18), mette chi offre in watch, aggiorna il canale e avvisa i watcher (e il proprietario, se è una RFA).

**Offerta uguale all'offerta massima:** l'asta si chiude subito e parte la firma.

`/crea_offerta` (admin) passa dallo stesso punto.

### Chiusura

`scheduler.check_scadenze`, ogni 60 secondi:

- asta scaduta con offerte → CHIUSA e `firma.chiedi_anni`;
- asta scaduta senza offerte → CONCLUSA (o flusso del proprietario, se è RFA);
- a 15 minuti dalla scadenza → avviso ai watcher (una volta sola, `notifica_15min`).

### Firma FA (`handlers/firma.py`)

1. **Anni.** Bottoni `firma:` → in regular season scelta del ruolo `firma_ruolo:` (regole in `shared/ruoli_core`, regola dei 60 giorni) → conferma `firma_confirm:`.
2. **Timeout di 48 ore.** `firma_automatica` (job `run_once`) firma 3 anni di penale e, in regular season, estrae il ruolo.
3. **Registrazione.** `_registra_firma_finale` (`firma_comune.py`) è l'unico punto che chiude:
   - `pg_client.registra_firma` (contratto + `signed` in un'unica transazione), sul `giocatore_id` dell'asta: niente più riabbinamento per nome, che con un nome cambiato creava un giocatore doppione (`pg_client.id_giocatore_asta`; le aste vecchie senza id cercano per nome senza mai creare);
   - ruolo su PostgreSQL;
   - copia nel `contratti` locale;
   - asta CONCLUSA;
   - annuncio sul canale principale;
   - `accoda_sync_gas`.

**Anni minimi** (`anni_minimi`): da 20 almeno 2, da 35 obbligatori 3.

### RFA

**Apertura automatica (v58).** I GM dichiarano l'RFA nel bot principale (`rfa_dichiarati`). `handlers/rfa.job_rfa`, ogni 5 minuti:

1. per ogni asta RFA in corso, il proprietario è la squadra del contratto **x0** del giocatore (`pg_client.squadra_x0`): se è stato scambiato, `set_squadra_proprietaria` + canale aggiornato + avviso nel log. Il contratto nuovo di chi vince è in corso e non conta mai;
2. nella fase `offseason-rfa`, apre con `pubblica_asta_rfa` l'asta di ogni dichiarato in vigore (`pg_client.rfa_dichiarati`) che non l'ha ancora avuta in questa stagione (`rfa_giocatore_stagione`), con il vecchio compenso dal contratto. I GM del proprietario seguono l'asta e vengono avvisati.

La dichiarazione smette di pesare quando l'asta chiude il contratto x0 (firma, pareggio o rilascio): il bot aste non deve toccarla.

**Apertura a mano.** `/nuova_rfa <giocatore> <team_id> <vecchio_compenso>` (admin), con il giocatore cercato nel roster della squadra (`pg_client.nomi_roster`). Usa la stessa `pubblica_asta_rfa`.

- Una sola RFA per squadra per stagione (`team_ha_rfa_stagione`, sulla `stagione_corrente` condivisa).
- Durante l'asta il proprietario non può offrire (`_check_partecipazione` + `_esegui_offerta`).

**Il vincitore sceglie gli anni.** Ha 12 ore; al timeout prende gli anni minimi. Da 35 anni = 3, e si salta direttamente al pareggio.

**Pareggio** (`firma_pareggio.py`). Dopo la scelta l'asta va in PAREGGIO: il proprietario ha 24 ore **dalla chiusura** (`_chiedi_pareggio`, `pareggio:` / `pareggio_anni:` / `pareggio_confirm:`; timeout → `pareggio_automatico` = passa al vincitore).

- `soglia_pareggio(vecchio)`: fino a `fascia_bassa_max` (20) basta 1, fino a 34 ⌊vecchio/3⌋, oltre ⌊vecchio/2⌋.
- `importo_minimo_pareggio = max(offerta, soglia)`.
- Anni: sopra soglia ≥ quelli del vincitore; sotto soglia liberi.

**Pre-impostazioni del proprietario** (`firma_preimpostazioni.py`). Bottoni `pre_par_*` / `pre_rifiuto_*`, salvati in `pareggio_preimpostato` / `rifiuto_preimpostato`. Quando il vincitore sceglie gli anni, `_esegui_pre_pareggio_se_compatibile` decide da solo.

**Senza offerte.** Il proprietario può:

- firmarlo (`firma_prop:`, stesse soglie);
- lasciarlo andare (`lascia:`, solo il proprietario, una volta). Qui `_concludi_rfa_senza_contratto` → `pg_client.rilascia_rfa` disattiva il contratto e scrive il movimento `expired`.

**Il vecchio contratto.** Quando il giocatore passa al vincitore o viene rifirmato, `teams.libera_cap` → `pg_client.deattiva_contratto` disattiva quello del proprietario. Il movimento lo dà la `signed` della firma nuova.

### Regole extra

**Regola dei 30 giorni** (`pg_client.squadre_regola_30_giorni`). Se l'ultimo movimento del giocatore è un taglio, sono bloccate le squadre che l'hanno avuto negli ultimi 30 giorni.

**Cam Thomas** (`pg_client.minimo_cam_thomas`). Se c'è un decadimento con nota "Cam Thomas" della stessa squadra nell'ultimo anno, l'offerta minima è il vecchio contratto.

**Cap e slot anticipati** (`/autocap`, `/autoslot`). Una riga in `cap_anticipato`/`slot_anticipato` con scadenza a 48 ore, più una segnalazione al gruppo admin con il bottone di reset (`reset_cap_ant:` / `reset_slot_ant:`). Il reset è rifiutato se la squadra finirebbe in negativo.

### Riavvio

`recupera_stati_pendenti` gira 5 secondi dopo l'avvio. Ripesca le aste CHIUSA e PAREGGIO e rischedula firma e pareggio automatici **con il tempo che mancava**, non da capo. `/force_esito` fa la stessa cosa a mano per un'asta.

---

## 5. Job

| Quando | Job | Cosa fa |
|---|---|---|
| ogni 60 s | `check_scadenze` | chiusure e avvisi a 15 minuti |
| 5 s dopo l'avvio | `recupera_stati_pendenti` | riprende firme e pareggi |
| ogni 5 min | `job_aggiorna_comandi` | se cambiano fase, mercato o presenza di aste aperte, ri-registra il menu "/" |
| ogni 5 min | `rfa.job_rfa` | proprietario delle aste RFA allineato alle trade; in fase RFA apre le aste dei dichiarati |
| ogni 5 min | `ping_healthcheck` | solo con `HEALTHCHECK_URL` |
| 13:00 | `check_cap_stagionale` | solo offseason |
| una tantum | `firma_automatica`, `pareggio_automatico` | `run_once` alle scadenze di firma e pareggio |

Gli errori dei job vanno a `helpers.log_job_error`: canale log e privato del dev.

**Codice presente ma non schedulato:**

- `scheduler.backup_*`: il backup lo fa il bot principale; qui resta solo `/backup_ora`.
- `scheduler.pulizia_anticipati_scaduti`: non serve, perché le query filtrano già `scade_at > NOW()`. Restano solo righe vecchie nella tabella.

---

## 6. Menu "/" e comandi

**Menu** (`comandi.py`). `liste_comandi(fase, mercato_fa, offerte)` costruisce le liste per scope:

- GM in privato;
- ogni admin;
- dev;
- gruppi: solo `/team` e `/listteams`.

Visibilità:

- i comandi FA (`/lista_fa`, `/nuova_fa`, `/apri_asta`) solo a mercato aperto;
- quelli per offrire (`/offri`, `/offerta`, `/watch`, `/autocap`, `/autoslot`, `/crea_offerta`) anche in fase RFA o finché ci sono aste aperte;
- `/nuova_rfa` solo in offseason.

`registra_comandi(bot, forza)` ricorda l'ultimo stato e non rifà le chiamate se non è cambiato niente.

**Dev:**

| Comando | Cosa fa |
|---|---|
| `/dev` | elenco |
| `/guida_dev` | questa guida |
| `/dev_version` | versione |
| `/dev_aste_stato` | aste raggruppate per stato |
| `/dev_watched` | tutti i watcher, con nome |
| `/dev_rfa` | RFA della stagione |
| `/dev_firme [N]` | ultime firme in dettaglio |
| `/dev_cap` | cap e slot virtuali di ogni squadra, con le aste che li occupano |
| `/dev_log [N]` | ultime righe di log |
| `/job_status` | job e prossima esecuzione |
| `/broadcast <testo>` | messaggio a tutti i GM |
| `/backup_ora` | copia di aste.db sul canale log |
| `/reboot` | riavvio |

**Admin:**

| Area | Comandi |
|---|---|
| guardare | `/list`, `/listteams`, `/team`, `/aste`, `/all_aste`, `/firme`, `/stato_asta` |
| per conto di una squadra | `/apri_asta`, `/crea_offerta`, `/nuova_rfa` |
| correggere | `/annulla_offerta`, `/chiudi_asta`, `/annulla_asta`, `/riapri_asta`, `/estendi_asta`, `/sposta_asta` |
| recupero | `/force_esito`, `/forza_aggiornamento`, `/ripubblica_asta`, `/firma_per_conto` (v69: callback `pc_firma*`, stessi handler di `firma*` con `_squadra_che_firma` che per conto accetta solo admin; `_registra_firma_finale(per_conto=True)`) |
| mercato | `/apri_mercato`, `/chiudi_mercato` (emergenza) |
| aiuto | `/admin`, `/guida_admin` |

**GM:**

| Area | Comandi |
|---|---|
| situazione | `/me`, `/team`, `/team_detail` (tastiera con tutte le squadre), `/listteams`, `/aste` |
| aste | `/lista_fa`, `/nuova_fa`, `/offri`, `/offerta` |
| seguire | `/watch`, `/watched`, `/silenzia` |
| emergenze | `/autocap`, `/autoslot` |
| varie | `/guida`, `/annulla`, `/start` (benvenuto o deep link) |

---

## 7. I file

| File | Contenuto |
|---|---|
| `bot.py` | avvio, handler, job, error handler, `recupera_stati_pendenti`, `/reboot` |
| `database.py` | SQLite: schema, `_migrate()` additivo, query su aste, offerte e watch, `STATI_IMPEGNO` |
| `pg_client.py` | PostgreSQL: cap, roster, firme, RFA, 30 giorni, Cam Thomas, anticipati, lista FA, coda GAS |
| `teams.py` | teams.json (lettura), `check_slot_virtuale`, `libera_cap`/`scala_cap_slot` (no-op su JSON con PostgreSQL attivo) |
| `settings.py` | settings e regole di cap (`cap_limite`, `penalita_cap`, `offerta_massima`) |
| `utils.py` | globals, ricerca giocatori, formattazione, messaggio del canale (`build_canale_message`), `cap_slot_display`, `cap_impegnato_display` |
| `comandi.py` | menu "/" |
| `scheduler.py` | `check_scadenze`, `check_cap_stagionale`, healthcheck |
| `handlers/offerte.py` | apertura, offerta, deep link, `/offri` |
| `handlers/firma.py` | scelta degli anni del vincitore (e del ruolo in regular season), firma automatica allo scadere, registrazione dei bottoni di tutta la firma; in testa il flusso e l'indice dei moduli `firma_*` |
| `handlers/firma_comune.py` | anni minimi e soglie RFA, validazione degli anni, ruolo da scegliere, `_registra_firma_finale`, `_concludi_rfa_senza_contratto` |
| `handlers/firma_preimpostazioni.py` | pre-impostazioni del proprietario di un RFA alla chiusura dell'asta e loro applicazione |
| `handlers/firma_pareggio.py` | pareggio (24 ore, `pareggio_automatico`), RFA senza offerte: il proprietario firma o lascia andare |
| `handlers/user.py` | `/me`, `/watch`, `/watched`, `/lista_fa`, `/silenzia`, `/offerta`, `/team_detail`, `/guida` |
| `handlers/admin.py` | `/admin`, `/guida_admin`, `/backup_ora`, `/apri_mercato`, `/chiudi_mercato`, i comandi che rimandano al bot principale, registrazione dei comandi admin; in testa l'indice dei moduli `admin_*` |
| `handlers/admin_comune.py` | `is_admin`, `_admin_label`, conferma degli admin quando un'operazione manda il cap in negativo |
| `handlers/admin_squadre.py` | `/list`, `/listteams`, `/team`, `/firme`, `/autocap`, `/autoslot` (questi tre registrati in `user.py`) |
| `handlers/admin_aste.py` | `/aste`, `/all_aste`, `/stato_asta`, `/chiudi_asta`, `/annulla_asta`, `/ripubblica_asta`, `/forza_aggiornamento`, `/force_esito` |
| `handlers/admin_riapri.py` | `/riapri_asta`, `/estendi_asta`, `/sposta_asta` |
| `handlers/admin_offerte.py` | `/apri_asta`, `/crea_offerta`, `/nuova_rfa`, `/annulla_offerta` |
| `handlers/rfa.py` | `pubblica_asta_rfa`, `job_rfa` (RFA dichiarati nel bot principale) |
| `../shared/cap.py` | cap e slot, gli stessi del bot principale |
| `../shared/squadre.py` | ricerca di una squadra da testo (`teams.get_team_by_query`, per `/team`), la stessa di `/roster` nel bot principale |
| `../shared/messaggi.py` | `manda_lungo`: elenchi admin e dev (`/all_aste`, `/firme`, comandi dev) che, se non stanno in un messaggio, arrivano come file `.md` |
| `handlers/helpers.py` | `aggiorna_canale`, `notifica_watchers`, `notifica_admin_group`, `log_warn`, `log_job_error` |
| `handlers/dev.py` | comandi dev |
| `flowchart.mermaid` | schema dei flussi GM (può essere indietro rispetto al codice) |

### Prefissi dei bottoni

| File | Prefissi |
|---|---|
| `offerte.py` | `conferma_offerta:`, `fa_conferma:`, `fa_omonimo:`, `offri_page:`, `annulla` |
| `firma.py` | `firma:`, `firma_ruolo:`, `firma_confirm:`, `firma_indietro:` |
| `firma_pareggio.py` | `pareggio*`, `firma_prop*`, `lascia:` |
| `firma_preimpostazioni.py` | `pre_par_*`, `pre_rifiuto*` |
| `user.py` | `watch:`, `fa_page:`, `fa_avvia:`, `td:`, `td_back` |
| `admin_aste.py` | `admin_annulla:`, `admin_chiudi:`, `admin_noop` |
| `admin_riapri.py` | `riapri_cap:`, `riapri_annullata:` |
| `admin_offerte.py` | `annulla_off_cap:` |
| `admin_squadre.py` | `reset_cap_ant:`, `reset_slot_ant:` |
| `admin.py` | `reset_rfa:` (disattivato) |

I bottoni di `firma_*` e `admin_*` sono registrati in `firma.py` e `admin.py` (`get_handlers`).

---

## 8. Diagnosi rapida

**Un'asta è "bloccata":**

1. `/stato_asta <id>` per vedere stato, scadenze e offerte.
2. Se è CHIUSA o PAREGGIO e il GM non ha il messaggio: `/force_esito <id>`.
3. Se il canale non si aggiorna: `/forza_aggiornamento`, poi `/ripubblica_asta`.

**Cap o slot sbagliati in `/me`:**

1. `/dev_cap` per vedere quali aste stanno impegnando cap e slot.
2. Poi guarda i contratti attivi su PostgreSQL: dalla v57 il bot aste conta il roster dai **contratti attivi**, come il bot principale. `/dev_coerenza` del bot principale dice se contratti e movimenti sono d'accordo.

```sql
-- roster secondo entrambi i bot
SELECT g.nome_common, c.importo, c.anni_originali FROM contratti c
JOIN giocatori g ON g.id = c.giocatore_id
WHERE c.team_id = 'team07' AND c.attivo ORDER BY c.importo DESC;
```

**Firma non arrivata su PostgreSQL.** Nei log c'è `Firma PG fallita per …`: registrala con `/registra_firma` dal bot principale.

**Un'asta RFA non si è aperta da sola.** Il job gira ogni 5 minuti solo in fase `offseason-rfa` e apre le aste dei dichiarati il cui contratto x0 è ancora attivo, una per giocatore e stagione. Controlla la dichiarazione nel bot principale (pannello → 🔒 RFA squadre → 📋 RFA dichiarati) e i log (`job_rfa`). In ultima istanza: `/nuova_rfa`.

**Elenchi lunghi** (`/all_aste`, `/firme`, comandi dev): se non stanno in un messaggio arrivano come file `.md` (`shared/messaggi.manda_lungo`).

**Leggere il database delle aste:**

```bash
docker compose exec bot-aste-beta python3 -c "import sqlite3; c=sqlite3.connect('/data/aste.db'); print(c.execute('SELECT id,giocatore,stato,offerta_corrente,offerente_team_id,scade_at FROM aste ORDER BY id DESC LIMIT 10').fetchall())"
```

---

## 9. Sviluppare e provare

- Le prove del bot aste stanno in `tests/aste/`:
  - quelle "isolate" girano senza PostgreSQL (`PG_URL` vuoto);
  - le altre usano il PostgreSQL locale di prova.
- Lancio: `tests/run.sh` dalla radice del progetto, in locale, mai sul server.
- Schema SQLite: solo `ALTER TABLE … ADD COLUMN` in `_migrate()`, con default.
- Ogni rilascio che tocca questo bot aggiunge una voce `## vNN — titolo` al suo CHANGELOG (nello zip `CHANGELOG_aste.md`).
- Rebuild: `docker compose up --build -d bot-aste-beta`. Se cambia `shared/` (`ruoli_core.py`, `cap.py`, `messaggi.py`), anche `bot-main`.
- Cap e slot stanno in `shared/cap.py`: una regola nuova su cosa pesa (x0, RFA, DPE) si cambia lì e vale per tutti e due i bot. Prove: `cap_condiviso` (bot principale) e `rfa_dichiarati` (qui).

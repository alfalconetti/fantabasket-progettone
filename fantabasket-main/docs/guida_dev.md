# Guida dev — bot principale

Promemoria tecnico: cosa c'è nel bot, dove sta e come funziona. Il bot aste ha la sua (`fantabasket-aste-beta/docs/guida_dev.md`). Per backup e ripristino la guida è `docs/RECOVERY.md`. Da Telegram questa guida si riceve con `/guida_dev`.

---

## 1. Mappa

```
fantabasket-progettone/
├── docker-compose.yml
├── config/             globals.json, teams.json, settings.json, divisions.json, loghi/ …  (NON in git)
├── secrets/            token, password, URL dei fogli, *.env                            (NON in git)
│   └── cifrati/        secrets.tar.gpg per il backup (scripts/cifra_secrets.sh)
├── shared/ruoli_core.py   regole dei ruoli, usate da entrambi i bot
├── fantabasket-main/      ← questo bot
├── fantabasket-aste-beta/ bot aste
├── gas-router/            ponte verso Google Apps Script (fogli)
├── gas/                   codice Apps Script (clasp)
├── yahoo-router/          OAuth Yahoo (in attesa di abilitazione)
├── scripts/               cifra_secrets.sh, setup_dashboard.sh
├── tests/                 prove locali (MAI sul server)
└── docs/RECOVERY.md
```

**Servizi Docker:**

| Servizio | Cosa fa |
|---|---|
| `postgres` | PostgreSQL 16, database `fantabasket`, utente `fantabasket` |
| `bot-main` | questo bot |
| `bot-aste-beta` | bot aste |
| `gas-router` | riceve i dati dal bot e li gira alla web app Apps Script |
| `yahoo-router` | OAuth e chiamate Yahoo (per ora inutilizzato) |
| `nocodb` | dashboard in LAN sulla 8090, di solito spenta |

**Chi possiede cosa:**

- **PostgreSQL** è la fonte di verità di contratti, trade, pick, tagli e ruoli. Ci scrivono entrambi i bot; il bot aste scrive solo firme, rilasci RFA, cap/slot anticipati e coda dei fogli.
- **globals.json** è condiviso. Lo scrive solo questo bot (fase, stagione, mercato, deadline); il bot aste lo monta in sola lettura.
- **teams.json** è condiviso. Lo scrive solo questo bot (`/my_team`, `/palette`, `/set_cap_penalizzato`).
- **aste.db** (SQLite) è del bot aste. Questo bot lo legge solo per il backup (`/data_aste/aste.db`, in sola lettura).

---

## 2. Configurazione

**Variabili d'ambiente** (dal compose):

| Variabile | Valore |
|---|---|
| `BOT_TOKEN_FILE` | file del token |
| `DATABASE_URL` + `PG_PASSWORD_FILE` | connessione a PostgreSQL |
| `GLOBALS_PATH`, `SETTINGS_PATH`, `TEAMS_PATH` | file di config |
| `CONFIG_DIR`, `LOGHI_DIR` | cartelle di config e loghi |
| `ASTE_DB_PATH` | aste.db per il backup |
| `GAS_ROUTER_URL`, `GAS_ROUTER_TOKEN_FILE` | gas-router |
| `HEALTHCHECK_URL` | da `secrets/bot_main.env`; senza, niente ping |

**globals.json:**

| Chiave | Uso |
|---|---|
| `fase` | fase corrente, sempre con i trattini |
| `stagione_corrente` | stringa, `"2026"` = stagione 2026-27 |
| `mercato_aperto` | FA aperta; si aggiorna da sola a ogni cambio fase |
| `admin_ids`, `dev_id` | permessi |
| `admin_group_id` | gruppo admin: approvazioni, report |
| `main_channel_id` | canale principale: annunci |
| `log_channel_id_main` | log del bot e backup |
| `log_channel_id` | log del bot aste |
| `channel_id` | canale aste (usato dal bot aste) |
| `trade_deadline` | data; i diritti 2nd scadono 10 giorni prima |
| `deadline_ruoli` | scadenza della dichiarazione ruoli (`/deadline_ruoli`) |
| `repo_url` | link alla guida di ripristino nella didascalia dei backup |

**settings.json** (condiviso, si legge a ogni chiamata, `/settings chiave valore` per cambiarlo):

- **cap:** `cap_regular` 150, `cap_offseason` 165, `salary_floor` 115;
- **roster:** `roster_max` 15, `roster_min_regular` 10, `roster_min_guardie`/`ali`/`centri` 4/4/2;
- **anni minimi:** `soglia_anni_2` 20, `soglia_anni_3` 35;
- **pareggio RFA:** `fascia_bassa_max` 20, `fascia_media_max` 34;
- **regole varie:** `stepien_anni` 4, `ore_comunicazione_ruolo` 48;
- **tabelle:** `rookie_scale` (per pick, anno per anno), `tabella_minimo_contratto` (per i rinnovi, non ancora usata);
- **tempi del bot aste:** `durata_asta_ore`, `timeout_*`, `rilancio_minimo`.

`tests/config/settings.json` ha gli stessi valori: se cambi uno, cambia l'altro.

**teams.json:** per squadra `id` (`teamXX`), `nome`, `gm_nome`, `gm_ids` (anche più di uno), `colore`/`colore2`, i colori della palette (`colore_header`, `colore_riga1`, …) e `cap_penalizzato`.

**secrets/:**

- `bot_token_*.txt`, `pg_password.txt`;
- `gas_token`, `gas_router_token`, `gas_roster_url`, `gas_scelte_url`;
- `yahoo_*`;
- `bot_main.env`, `yahoo_router.env`, `nocodb.env`.

Sono bind-mount per file: dopo una modifica serve `docker compose up -d --force-recreate <servizio>`, e poi `scripts/cifra_secrets.sh` perché il backup li includa.

---

## 3. Fasi e stagione

```
regular-season-fa → regular-season-deadline → playoff →
offseason-break → offseason-rinnovi → offseason-draft →
offseason-rfa → offseason-fa → offseason-ruoli → (ricomincia)
```

Costanti in `settings.py`, da usare sempre (non scrivere liste di fasi a mano):

| Costante | Fasi |
|---|---|
| `FASI_TRADE_APERTE` | `regular-season-fa` + tutte le offseason tranne `offseason-break` |
| `FASI_FA_APERTA` / `FASI_MERCATO_APERTO` | `regular-season-fa`, `offseason-fa`, `offseason-ruoli` |
| `FASI_DPE` (in `dpe.py`) | da `offseason-rinnovi` a `regular-season-deadline` |
| `FASI_RUOLI_RS` (in `shared/ruoli_core.py`) | regular season e playoff: cambi ruolo, dichiarazioni post-trade |

**Cambio fase.** `admin_panel._esegui_cambio_fase`:

1. scrive `fase` e `mercato_aperto`;
2. entrando in `offseason-rinnovi` incrementa `stagione_corrente`;
3. ri-registra i comandi (`comandi.registra_comandi`);
4. annuncia sul canale (`testo_annuncio_fase()` + `FASI_INDICAZIONI`, da tenere allineate al regolamento);
5. lancia i report di fine fase (ruoli mancanti, vincoli ruoli all'ingresso in RS).

Il bot aste vede la fase nuova entro 5 minuti.

**Cap per fase:**

- `settings.cap_limite_team(team)`: in offseason 165 per tutti, in regular season 150 − `cap_penalizzato`;
- `luxury_cap()` / `cap_limite()`: il tetto senza penalità.

---

## 4. Database

### Tabelle

**Anagrafica e contratti**

| Tabella | Contenuto |
|---|---|
| `giocatori` | anagrafica: `nome_common`, `nome_bref`, `nome_yahoo`, `nome_norm`, `yahoo_id`, `data_nascita` |
| `contratti` | `importo`, `anni_originali`, `stagione_firma`, `tipo` (normale/rookie/10day), `attivo` |
| `transazioni` | **event log** di ogni movimento (vedi sotto) |
| `impatto_taglio` | rate delle spalmature: una riga per squadra, giocatore e stagione |
| `dpe` | DPE approvate: `importo_originale`, `importo_dpe`, `pre_deadline`, `stagione`, `team_id` (segue il giocatore in trade) |

**Trade, pick e rookie**

| Tabella | Contenuto |
|---|---|
| `trade` | trade e bozze: `stato`, `trade_ref` `TRADE-AAAA-NNN`, `bozza_num`, `proposta_da`, `note`/`nota_gm` |
| `trade_squadre`, `trade_items`, `trade_voti` | squadre, pezzi (`team_id_a = '?'` = destinatario da assegnare) e voti |
| `pick` | `proprietario_orig`, `proprietario_att`, `anno`, `round`, `protezioni`, `scattata` |
| `rookie` | diritti e rookie scale: `pick_numero`, `anno_draft`, `anni_scala`, `firmato`, `diritti_scaduti` |

**Ruoli e posizioni**

| Tabella | Contenuto |
|---|---|
| `cambi_ruolo` + vista `ruolo_attuale` | event log dei ruoli (`iniziale`, `ordinario`, `erminio`, `saedro`, `forzato_admin`, `post_trade`, `post_firma`, `dpe_extra`, …) |
| `posizioni_eleggibili` + vista `posizioni_attuali` | event log delle posizioni Yahoo (una riga solo se il set cambia; `data_yahoo` per Erminio) |
| `ruoli_bozze` | dichiarazione di inizio stagione non ancora confermata |
| `ruoli_pendenti` | dichiarazioni post-trade/firma in RS (48 ore) |

**Richieste, code e dati esterni**

| Tabella | Contenuto |
|---|---|
| `richieste_admin` | richieste aperte (DPE, Saedro, decadimento): una per giocatore, decisione unica |
| `cap_anticipato`, `slot_anticipato` | `/autocap` e `/autoslot` del bot aste (48 ore) |
| `gas_sync_queue` | il bot aste ci accoda le firme, questo bot sincronizza i fogli |
| `bref_stats` | snapshot Basketball-Reference: una riga quando G aumenta (`bref_schema.sql`) |
| `bref_nuovi` | giocatori bref non in anagrafica, con decisione del dev |
| `penalita` | nello schema, non usata (la penalità è in teams.json) |

**Viste:** `roster_attuale`, `firme`.

### Tre cose da ricordare

**1. Roster = contratti attivi, ma il bot aste conta i movimenti.** Il bot aste conta il roster dall'**ultimo movimento** in `transazioni` (`team_id_a`). Quindi ogni chiusura di contratto (taglio, decadimento, scadenza, rilascio RFA) deve avere anche la sua transazione, altrimenti i due bot non sono d'accordo.

**2. I CHECK dei tipi.** `migrate_db()` (all'avvio) ricrea i CHECK di `transazioni` e `cambi_ruolo` con `_allinea_check` come **unione** dei valori. Un tipo nuovo va aggiunto lì **e** in `schema.sql`.

**3. Lo schema cresce da solo.** `schema.sql` crea il DB solo la prima volta (initdb del container). Le tabelle e colonne successive le crea `migrate_db()` a ogni avvio, sempre con `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`.

### Accesso a mano

```bash
docker compose exec postgres psql -U fantabasket -d fantabasket -c "SELECT ..."
```

Da uno script Python nel container, chiama `db.init_db()` prima di usare il DB.

Esempio: tutti i movimenti di un giocatore.

```sql
SELECT t.timestamp, t.tipo, t.team_id_da, t.team_id_a, t.note
FROM transazioni t JOIN giocatori g ON g.id = t.giocatore_id
WHERE g.nome_common ILIKE '%durant%' ORDER BY t.timestamp;
```

---

## 5. I file

**Radice**

| File | Contenuto |
|---|---|
| `bot.py` | avvio: registra gli handler, i job, l'error handler (errori al canale log e al dev), la versione dal CHANGELOG |
| `settings.py` | lettura config, costanti di fase, `is_admin`, decoratori `@solo_privato` e `@richiede_fase` |
| `database.py` | tutte le query (`_q(sql, params, one=, many=)`), `migrate_db()`, transazioni atomiche (trade, tagli, decadimenti) |
| `teams.py` | `get_team_by_id`, `get_team_by_gm`, `get_team_by_query` (fuzzy: id → nome esatto → prefisso → difflib 0.6), `set_campo_team` |
| `comandi.py` | menu "/" di Telegram per scope e fase (`_fasi_comando`) |
| `scheduler.py` | backup, sync fogli, coda GAS, scadenza diritti |
| `gas_client.py` | payload dei fogli Roster e Scelte, `sync_after_*`, `sync_bref_raw` |
| `bref_scraper.py` | scraping per_game di Basketball-Reference (anche standalone con `--migrate`) |
| `nomi.py` | abbinamento nomi severo (`/set_nascita`, giocatori bref nuovi) |
| `utils.py`, `log_buffer.py` | fuso `ROME`, formattazione date, normalizzazione; buffer per `/dev_log` |
| `roster.typ`, `assets.typ` | template Typst delle immagini |
| `validators/trade.py` | validazione trade: cap, roster, floor, Stepien, ruoli, struttura a 3+ |
| `validators/ruoli.py` | involucro di `shared/ruoli_core.py` |

**handlers/**

| File | Cosa contiene |
|---|---|
| `menu.py` | `/menu` per fase (`AZIONI_FASE`, `AZIONI_SEMPRE`), `/guida`, `/guida_admin` |
| `trade.py` | builder, import, editor, bozze, voto, invio, esecuzione e rollback (`_scrivi_trade`), `/my_trades` |
| `trade_parser.py` | parser del testo delle trade |
| `tagli.py` | `/taglia`: anteprima, spalmature, limiti |
| `dpe.py` | `/dpe` e `_importo_dpe()` |
| `rookie.py` | `/attiva_diritti`, scadenza diritti |
| `decadimento.py` | `/decadimento`, motivi, `/ritiro_fa` |
| `spalmature.py` | report mensile e `/report_spalmature` |
| `ruoli.py` | dichiarazione di inizio stagione, `/deadline_ruoli` |
| `ruoli_rs.py` | dichiarazioni post-trade/firma in RS |
| `cambi_ruolo.py` | `/cambio_ruolo`: ordinario, Erminio, Saedro, forzato, Extra DPE |
| `posizioni.py` | import e correzione delle posizioni eleggibili, `/data_erminio` |
| `roster.py` | `/roster`, `/assets` (Typst) |
| `team_diff.py` | `/team_diff` |
| `palette.py`, `myteam.py` | colori e dati squadra |
| `admin_panel.py` | `/admin_menu`, fasi, DPE e tagli admin, `/registra_firma`, `/list`, `/set_cap_penalizzato`, situazione cap |
| `bref.py` | job Basketball-Reference e conferma dei giocatori nuovi |
| `nascite.py` | `/set_nascita`, `/nascite_mancanti` |
| `dev.py`, `dev_player.py` | comandi dev |
| `helpers.py` | `log_job_error`, `log_warn` |

### Prefissi dei bottoni (callback_data)

Utile per capire chi risponde a un bottone. In grassetto quelli citati più spesso.

| File | Prefissi |
|---|---|
| `trade.py` | `trade_*`, `edit_*`, `menu_trade_*`, `mt:` (solo `mt:l` e `mt:v/r/c:<id>`) |
| `admin_panel.py` | `adm*`, `fase_*`, `rfirma:` |
| `rookie.py` | `att_r*`, **`attadm:`**, `scadi_diritti:` |
| `decadimento.py` | `dec_*`, **`decadm:`** |
| `dpe.py` | `dpe_*` |
| `tagli.py` | `taglia_*` |
| `cambi_ruolo.py` | **`cr:`** (GM), **`ca:`**/`cradm:` (admin), `sae:` (Saedro) |
| `ruoli.py` | `rl:`, `rladm:`, `rli:` |
| `ruoli_rs.py` | `rp:`, `rpadm:` |
| `posizioni.py` | `pos_imp_`, `spe:` |
| `myteam.py` | `mt:<campo>:<team>` |
| `palette.py` | `pal_*` |
| `bref.py` | `brefn:` |
| `nascite.py` | `nasc:` |
| `dev_player.py` | `dp:` |
| `menu.py` | `menu:`, `roster_sq:`, `assets_sq:` |

Attenzione: `mt:` è usato da due file. Funziona perché gli handler di `trade.py` sono registrati prima e hanno un pattern più stretto. Se aggiungi un `mt:` nuovo, controlla che non si pestino.

---

## 6. Le regole, dove stanno

### Trade

**Stati.** Tutti i passaggi passano da `db.cambia_stato_trade(id, da=(...), a=...)`, che è atomico:

- percorso normale: `bozza → proposta → in_approvazione → approvata`;
- uscite: `rifiutata_gm`, `rifiutata_admin`, `annullata`.

**Esecuzione e rollback.** `_scrivi_trade` fa tutto in un'unica transazione DB: approvazione, spostamento di giocatori, pick e diritti, transazioni, `dpe.team_id`, stato. Se un pezzo non torna solleva `TradeNonEseguibile` e non scrive niente. `trade_ref` viene assegnato prima dell'esecuzione.

**Validazione** (`validators/trade.valida_trade`):

- struttura (niente `?`, niente pezzi doppi, ogni squadra cede o riceve qualcosa);
- possesso dei pezzi;
- cap post-trade per squadra, con la DPE ridotta;
- roster ≤ 15 (i giocatori con DPE non contano);
- salary floor in stagione;
- Stepien (`anni_coperti_stepien`, finestre di `stepien_anni`; gli anni ≤ 2026 sono coperti d'ufficio);
- in RS, i ruoli (`deficit_minimo`).

**Notifiche.** `_notifica_squadre(context, trade_id, testo, escludi=())` scrive a tutte le squadre (e al gruppo admin se la trade è degli admin). `_notifica_proponente` solo per l'avanzamento dei voti.

**Bozze.** `_bozza_non_modificabile` / `_puo_gestire_bozza`: si toccano solo in stato `bozza`, solo dal proponente o da un admin.

**Etichette delle bozze.** `BUF03-3` = prime 3 lettere del nome squadra + numero squadra + `bozza_num`; `ADM-4` per le bozze degli admin.

### Tagli e spalmature (`tagli.py`)

- **Gratuito:** 1M x1 con meno di 3 tagli gratuiti già fatti nella stagione (`MAX_TAGLI_GRATUITI`). Dal quarto, spalmatura 1x1.
- **Sopra i 5M:** percentuali per anni residui (x1: 50-30-20; x2: 60-50-50-40; x3: 70-70-60-50-50), arrotondate per eccesso, con l'eccedenza tolta dal fondo senza scendere sotto 1 (7x1 → 4-2-1).
- **Fino a 5M:** tabella fissa `_TABELLA_SPALMATA_BASSA`.
- **Controlli e scrittura:** `_valuta_taglio` / `TaglioNonEseguibile` bloccano in RS sotto i 10 e se si scopre un ruolo. Contratto, transazione e rate vengono scritti in un'unica transazione.

### DPE (`dpe.py`)

- `_importo_dpe`: contratto − ceil(25%).
- `pre_deadline = fase != "regular-season-deadline"`, valutato **all'approvazione**.
- Pre-deadline: il giocatore non occupa slot. Post-deadline: niente slot, ma un cambio ruolo `dpe_extra` gratuito.
- La DPE vale per la stagione corrente e segue il giocatore in trade.

### Decadimento (`decadimento.py`)

- Motivi in `MOTIVI`: `ritiro`, `altra_lega`, `cam_thomas`, `altro`.
- `registra_decadimento(..., tutte_le_squadre)`:
  - con ritiro e altra lega cancella le spalmature future di **tutte** le squadre e restituisce quali squadre ha toccato;
  - con gli altri motivi solo quelle della squadra.
- `/ritiro_fa` fa lo stesso per un free agent (`db.cancella_spalmate_ritirato`).
- Cam Thomas: la nota della transazione contiene "Cam Thomas". `db.minimo_cam_thomas` (e il gemello nel bot aste) impone il vecchio contratto alla stessa squadra per un anno; lo controlla anche `/registra_firma`.

### Rookie (`rookie.py`)

- `esegui_attivazione()`: una transazione con `FOR UPDATE`, contratto dalla colonna "I anno" della rookie scale (`_slot_scala`), controllo di cap e slot.
- Scadenza diritti delle 2nd del draft `stagione − 1`: il giorno `trade_deadline − 10`. Prima un avviso 3 giorni prima, poi il bottone `scadi_diritti:<anno>` ogni giorno finché un admin non conferma.

### Ruoli (`shared/ruoli_core.py`, unica implementazione)

- **Funzioni:** `RUOLI`, `deficit_minimo` (0 se esiste un'assegnazione valida), `deficit_team`, `eleggibili`, `scelta_valida`, `ruolo_riacquisto` (regola dei 60 giorni), `estrai_ruolo`, `registra_ruolo`. Ognuna riceve la funzione di query `q` del bot che la chiama.
- **Modifiche:** una modifica a `shared/` richiede il riavvio di **entrambi** i bot.
- **Erminio:** finestra di 14 giorni da `COALESCE(data_yahoo, timestamp)` dell'ultima riga di posizioni.
- **Saedro:** evento con `scadenza` e `ruolo_ripristino`; il ritorno lo fa `job_fine_saedro`.
- **Ordinari:** contatore = eventi `ordinario` della squadra nella stagione (max 2).

### Richieste agli admin

1. Il GM chiede: `db.apri_richiesta`.
2. Il bottone Approva/Rifiuta chiama `db.chiudi_richiesta`, che risponde:
   - `'ok'` → procedi;
   - `'gestita'` → già decisa, non fare niente;
   - `'nessuna'` → bottone vecchio, procedi.

Le richieste nuove vanno fatte così.

### Fantamedia nel roster

- `db.stagione_fantamedia()`: la stagione bref è `stagione_corrente + 1`, se almeno metà dei giocatori sotto contratto ha dati; altrimenti la precedente.
- `db.fantamedie(gids, stagione)`. Tutte e due accettano `as_of` per il roster a una data.

---

## 7. Job automatici

| Quando | Job | Cosa fa |
|---|---|---|
| ogni 60 s | `processa_coda_gas` | svuota `gas_sync_queue` (firme del bot aste) → fogli |
| ogni 5 min | `_ping_healthcheck` | solo con `HEALTHCHECK_URL` |
| ogni 15 min | `ruoli_rs.job_scadenze` | estrae il ruolo delle dichiarazioni oltre le 48 ore |
| ogni 15 min | `cambi_ruolo.job_fine_saedro` | chiude le Saedro scadute |
| ogni 2 ore | `sync_sheets_periodico` | sync completo dei fogli |
| 00:00 e 12:00 | `backup_giornaliero` | backup completo al canale log |
| sabato 00:30 | `backup_settimanale` | backup al gruppo admin (PTB: `days=(6,)` = sabato, 0 = domenica) |
| 09:00 | `check_scadenza_diritti` | avvisi e bottone di scadenza dei diritti 2nd |
| lunedì 09:30 | `job_report_nascite` | date di nascita mancanti → dev |
| 1° del mese 09:45 | `job_report_spalmature` | free agent con spalmature → gruppo admin |
| 10:00 | `_bref_scraper_job` | Basketball-Reference (solo RS e playoff) |
| 10:00 | `ruoli.job_promemoria_deadline` | promemoria ai GM il giorno prima della deadline ruoli |
| 17:00 | `ruoli.job_report_giornaliero` | stato dichiarazioni sul canale log (in `offseason-ruoli`) |
| spegnimento | `backup_shutdown` | backup al `docker compose down` |

Gli errori dei job vanno a `log_job_error`: canale log e privato del dev. `/job_status` mostra i prossimi orari.

---

## 8. Comandi

**Dev** (solo `dev_id`):

| Comando | Cosa fa |
|---|---|
| `/dev` | elenco |
| `/guida_dev` | questa guida |
| `/dev_version` | versione (ultima voce `## vX.Y.Z` del CHANGELOG) |
| `/dev_log [N]` | ultime righe di log in memoria |
| `/dev_trade [N]` | ultime trade approvate |
| `/dev_pg` | stato della connessione |
| `/dev_roster <team_id>` | roster grezzo dal DB |
| `/dev_player <nome>` | anagrafica e contratto con bottoni per modificare ogni campo (i campi contrattuali loggano un avviso); `/annulla_dev` per uscire |
| `/nuovo_giocatore <nome> \| <nome_bref> [AAAA-MM-GG]` | crea un giocatore |
| `/job_status` | job e prossima esecuzione |
| `/broadcast <testo>` | messaggio a tutti i GM |
| `/sync_sheets` | sync completo dei fogli |
| `/backup` | backup subito |
| `/reboot` | riavvia (Docker lo rialza) |

**Admin:**

| Area | Comandi |
|---|---|
| pannello e squadre | `/admin_menu`, `/list` |
| fasi | `/set_fase` |
| trade e firme | `/annulla_trade_admin`, `/registra_firma` |
| spalmature | `/ritiro_fa`, `/report_spalmature` |
| cap e config | `/set_cap_penalizzato`, `/settings` |
| posizioni e ruoli | `/import_posizioni_eleggibili`, `/set_posizioni_eleggibili`, `/data_erminio`, `/deadline_ruoli` |
| nascite | `/set_nascita`, `/nascite_mancanti` |
| varie | `/annulla_admin`, `/guida_admin` |

**GM:**

| Area | Comandi |
|---|---|
| menu e squadra | `/menu` (anche `/start`), `/roster`, `/assets`, `/team_diff`, `/palette`, `/my_team` |
| trade | `/build_trade`, `/import_trade`, `/bozze_trade`, `/my_trades` (alias `/mie_trade`), `/edit_trade` |
| roster | `/taglia`, `/dpe`, `/attiva_diritti`, `/decadimento` |
| ruoli | `/dichiarazione_ruoli`, `/cambio_ruolo` |
| varie | `/guida`, `/annulla`, `/annulla_trade` (`/salta` dentro i flussi per saltare la nota) |

**Menu "/".** Lo costruisce `comandi.liste_comandi(fase)` per scope:

- gruppi: solo `/roster` e `/assets`;
- privato: GM;
- chat dei singoli admin e gruppo admin: admin;
- dev: tutto.

I comandi legati a una fase sono in `_fasi_comando`.

---

## 9. Integrazioni

**Google Sheets.**

- **Percorso:** il bot manda a `gas-router` (POST `/gas/roster`, `/gas/scelte`, `/gas/bref`) e il router gira alla web app Apps Script con il suo token.
- **Fogli:** Roster (per squadra), Scelte (pick, diritti, Stepien, colori delle division da `config/divisions.json`), BrefRaw.
- **Quando sincronizza:** `gas_client.sync_after_*` dopo ogni operazione, il periodico ogni 2 ore, la coda per le firme del bot aste.
- **Deploy Apps Script:** `clasp push` dalla cartella `gas/` (escluso `globals.gs`, che ha la config vera e non va mai nello zip). La nuova versione si pubblica da Gestisci deployment → matita → Nuova versione. Un "Nuovo deployment" cambia l'URL: vanno aggiornati i secrets.
- **Il foglio dice "Sync fallito":** chiama la web app dal container gas-router; se risponde HTML, il `<title>` dice l'errore.

**Basketball-Reference** (`bref_scraper.py` + `handlers/bref.py`). Ogni mattina alle 10, una sola richiesta per_game, che serve a:

- aggiungere righe a `bref_stats` per chi ha giocato;
- aggiornare il foglio BrefRaw;
- scrivere sul log aggiornati e cambi squadra NBA;
- proporre al dev i giocatori nuovi (`bref_nuovi`, bottoni `brefn:`).

**Yahoo** (`yahoo-router`). Pronto ma bloccato: serve l'approvazione separata della Fantasy API, senza la quale ogni chiamata dà 403.

- `docker compose exec -it yahoo-router python3 cli.py auth` per il primo token;
- `cli.py teams` per verificare se l'accesso è arrivato.

**NocoDB.** `docker compose start|stop nocodb`. Utente PostgreSQL `lettore` in sola lettura con timeout di 30 secondi; dati interni nel database `nocodb`. `scripts/setup_dashboard.sh` è rilanciabile e va rilanciato dopo un ripristino del DB.

---

## 10. Backup

`scheduler._crea_backup_zip`, sempre completo:

- `db/fantabasket.sql` (pg_dump);
- `db/aste.db`: copia coerente con `integrity_check`;
- tutta `config/`;
- `secrets.tar.gpg` se presente;
- `MANIFEST.txt`.

Va al canale log alle 00 e alle 12 e allo spegnimento, al gruppo admin il sabato 00:30, e su richiesta con `/backup`. Il bot non vede mai i secrets in chiaro: solo il file cifrato in `/secrets_cifrati/`. Ripristino: `docs/RECOVERY.md`.

---

## 11. Sviluppare

**Aggiungere un comando GM legato a una fase:**

1. l'handler, con `@solo_privato` e `@richiede_fase(...)`;
2. la voce in `AZIONI_FASE` di `menu.py`;
3. il comando in `comandi.py` (e in `_fasi_comando` se dipende dalla fase);
4. **l'equivalente "per conto di" nel pannello admin** (parità GM/admin);
5. la riga nella guida GM.

La prova `tests/docs/guide_e_menu.py` si accorge se una guida o il menu cita un comando che non esiste.

**Regole di casa:**

- `update.effective_message` ovunque. Nei callback, `query.get_bot()` per mandare messaggi altrove.
- ConversationHandler con `per_message=False`. `/annulla` globale (group −1) pulisce `user_data` e chiude tutto.
- Le scritture che toccano più tabelle vanno in un'unica transazione: vedi `_scrivi_trade`, i tagli, `registra_decadimento`.
- Un solo file per modulo, import sempre `handlers.xxx`. In passato si sono corretti bug sulla copia morta.
- Fasi sempre con i trattini.
- Testi con `parse_mode="HTML"`: passare i nomi in `html.escape`.

**Prove** (in locale, mai sul server):

```bash
tests/run.sh                         # tutte
tests/run.sh trade_3_squadre         # una
```

PostgreSQL 16 locale, database `fbt` (fb/fb), config finta in `tests/config/`. `tests/guardia.py` le blocca se vede `secrets/`, `/run/secrets/`, un DB non locale o il DB `fantabasket`; sul server `run.sh` non è eseguibile. Prima di ogni rilascio devono passare tutte. Dettagli in `tests/README.md`.

**Rilascio:**

1. voce `## vX.Y.Z (data)` nel CHANGELOG (la versione del bot si legge da lì);
2. voce `## vNN` nel CHANGELOG del bot aste, se lo tocchi;
3. riga in `MIGRATION.md`;
4. zip senza `config/`, `secrets/`, `.db`, `gas/globals.gs`.

Deploy da `~/bots`:

```bash
docker compose up --build -d bot-main                 # solo questo bot
docker compose up --build -d bot-main bot-aste-beta   # entrambi (sempre se cambia shared/)
docker compose logs -f --tail 100 bot-main            # log
```

---

## 12. Cose da sapere

**Non ancora automatizzato: il cambio di stagione.** Va fatto prima di giugno 2027:

- scadenza dei contratti (oggi un contratto finito resta x1);
- rinnovi con `tabella_minimo_contratto`;
- dichiarazione RFA in una fase nuova prima di `offseason-rfa`, con apertura automatica delle aste RFA;
- avanzamento della rookie scale (`anni_scala`) e Doncic rule;
- draft;
- penalità salary floor a inizio RS.

**10-day contract.** Non c'è: si gestisce a mano. Non va registrato con `/registra_firma`, perché peserebbe sul cap.

**Limiti noti:**

- `/team_diff` per i rookie usa `anni_scala` di oggi.
- La tabella `penalita` non è usata.

**Doppio account admin/GM:** dal `/menu` si agisce sempre come GM. I poteri admin (`ca:`, `attadm:`, `decadm:`) stanno solo nel pannello.

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
├── shared/              in comune ai bot: ruoli_core.py (ruoli), cap.py (cap e slot), squadre.py (ricerca squadra), lista_fa.py (stagioni della lista FA e switch al 70% dei firmati, per aste e report posizioni), messaggi.py (report lunghi), dev_comune.py (/dev_log, /dev_pg, /reboot ed error handler di loucabot e IPanchinari)
├── fantabasket-main/      ← questo bot
├── fantabasket-aste-beta/ bot aste
├── fantabasket-loucabot/  loucabot: calendario e calcolo dei fantapunti, README e docs/ suoi
├── fantabasket-ipanchinari/ IPanchinari: panchine (messaggi dei GM) e quintetti, README e docs/ suoi
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
| `loucabot` | calendario della lega sincronizzato con quello NBA, tabellini ESPN e fantapunti; tabelle sue `lega_*`, `nba_*`, più `giocatori.espn_id`; guida tecnica in `fantabasket-loucabot/docs/guida_dev.md` |
| `ipanchinari` | panchine dai messaggi dei GM (soprannomi) pubblicate sul canale Panchinari, quintetti con promemoria e conferma; tabelle sue `ipa_*`; guida tecnica in `fantabasket-ipanchinari/docs/guida_dev.md` |
| `gas-router` | riceve i dati dal bot e li gira alla web app Apps Script |
| `yahoo-router` | OAuth e chiamate Yahoo (per ora inutilizzato) |
| `nocodb` | dashboard in LAN sulla 8090, di solito spenta |

**Chi possiede cosa:**

- **PostgreSQL** è la fonte di verità di contratti, trade, pick, tagli, ruoli e RFA dichiarati. Ci scrivono il bot principale e il bot aste (loucabot e IPanchinari hanno tabelle loro, `lega_*`/`nba_*` e `ipa_*`); il bot aste scrive solo firme, rilasci RFA, cap/slot anticipati e coda dei fogli, e legge `rfa_dichiarati` per aprire le aste RFA.
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
| `log_channel_id_louca` | log di loucabot (senza: usa `log_channel_id_main`) |
| `gruppo_lega_id` | gruppo della lega (GM): la top 20 della notte di loucabot alle 9 (senza: non la pubblica) |
| `log_channel_id_ipa` | log di IPanchinari (senza: usa `log_channel_id_main`) |
| `canale_panchinari_id` | canale Panchinari: ci pubblica IPanchinari |
| `channel_id` | canale aste (usato dal bot aste) |
| `trade_deadline` | data; i diritti 2nd scadono 10 giorni prima. Ogni stagione con `/trade_deadline AAAA-MM-GG` (admin, controlla che cada nella stagione); entrando nei rinnovi, se è vecchia, promemoria al gruppo admin |
| `deadline_ruoli` | scadenza della dichiarazione ruoli (`/deadline_ruoli`) |
| `repo_url` | link alla guida di ripristino nella didascalia dei backup |

**settings.json** (condiviso, si legge a ogni chiamata; si cambia con `/settings`, `handlers/impostazioni.py`: catalogo `GRUPPI` con nome, tipo, limiti e unità di ogni chiave, chiavi sconosciute in «Altre», tabelle in sola lettura; anteprima e conferma, scrittura atomica di una sola chiave rileggendo il file, messaggio sul canale principale e sul log; un peso dei fantapunti riscrive subito il trigger di `bref_stats`). **Una chiave nuova di settings.json va aggiunta a `GRUPPI`** (la prova `impostazioni` controlla che ogni chiave del file e di `regole.DEFAULT` abbia una voce):

- **cap:** `cap_regular` 150, `cap_offseason` 165, `salary_floor` 115;
- **roster:** `roster_max` 15, `roster_min_regular` 10, `roster_min_guardie`/`ali`/`centri` 4/4/2;
- **anni minimi:** `soglia_anni_2` 20, `soglia_anni_3` 35;
- **pareggio RFA:** `fascia_bassa_max` 20, `fascia_media_max` 34;
- **regole varie:** `stepien_anni` 4, `ore_comunicazione_ruolo` 48;
- **Doncic:** `doncic_soglia_1` 20 e `doncic_soglia_2` 25 (le due fasce della formula, `stagione.doncic`);
- **tabelle:** `rookie_scale` (per fascia di pick, anno per anno: importo e anni; la usano attivazione diritti e cambio di stagione), `tabella_minimo_contratto` (per i rinnovi normali, non ancora usata);
- **tempi del bot aste:** `durata_asta_ore`, `timeout_*`, `rilancio_minimo`;
- **numeri del regolamento** (v5.8.0, letti da `shared/regole.py` per tutti i bot; chiave mancante = default, tra parentesi): `pesi_fantapunti` (dizionario `pts`, `ast`, `oreb`, `dreb`, `tpm`, `fga`, `fgm`, `fta`, `ftm`, `stl`, `blk`, `tov`: 0,5 2 2 1,25 1,5 −0,5 1 −0,75 1 2 2 −2; una statistica che manca vale il default), `bonus_casa` (3), `bonus_casa_playoff` (5), `scarto_minimo` (5), `giocatori_panchina` (5: anche il numero massimo di supplementari), `roster_min_guardie`/`_ali`/`_centri` (4/4/2), `ore_comunicazione_ruolo` (48), `giorni_riacquisto_ruolo` (60), `max_cambi_ruolo_ordinari` (2), `giorni_erminio` (14), `giorni_saedro` (10), `max_tagli_gratuiti` (3), `giorni_10day` (10), `riduzione_dpe_percento` (25). Si rileggono quando il file cambia, senza riavvio.
- **pesi dei fantapunti:** i fantapunti si salvano quando si scarica un tabellino (`nba_tabellini.fp`, loucabot) e la fantamedia di basketball-reference la scrive un trigger su `bref_stats` (`regole.allinea_bref`, all'avvio del bot principale: fino alla v5.7 era una colonna generata coi pesi nello schema). Dopo un cambio di `pesi_fantapunti`: **`/dev_ricalcola_fp [STAGIONE]` su loucabot** (riscrive il trigger e ricalcola tabellini e bref della stagione dalle statistiche salvate; i risultati convalidati restano).

`tests/config/settings.json` ha gli stessi valori: se cambi uno, cambia l'altro.

**Orari dei job** (v6.2.0): `"orari"` in settings.json, `{"nome": "HH:MM"}`; `shared/regole.orario(nome)` → `datetime.time` (senza fuso: chi lo usa mette Roma), default ed elenco in `shared/regole.ORARI`; un valore storto vale il default con un avviso nel log. Non è in `regole.DEFAULT` (non è un numero): in `/settings` compare tra le tabelle in sola lettura.

**Date nei comandi** (v6.2.1): `shared/date_comandi.leggi_data` (GG/MM/AAAA, GG/MM/AA, AAAA-MM-GG, con - / .), `leggi_ora`, `leggi_data_ora` (data e ora con uno spazio o una T). Ogni comando nuovo con una data usa questi.

**teams.json:** per squadra `id` (`teamXX`), `nome`, `gm_nome`, `gm_ids` (anche più di uno), `colore`/`colore2` (vecchi, non li legge nessuno), i colori della palette (`colore_header`, `colore_riga1`, …) `cap_penalizzato` e `alias` (lista; v6.8.0: con nome e `gm_nome` sono i campi della ricerca, `shared/squadre.campi_ricerca`; conflitti con `alias_in_conflitto`; li scrive «🏷️ Alias» di `/edit_team`).

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

**Cambio fase.** `admin_panel.cb_fase_set` → `_esegui_cambio_fase`:

0. se il passaggio tocca i contratti (`stagione.anteprima_fase`: stagione nuova, inizio FA) mostra l'anteprima e aspetta `fase_conferma:`;
1. scrive `fase` e `mercato_aperto`;
2. incrementa `stagione_corrente` solo se `stagione.nuova_stagione(vecchia, nuova)`: si entra in `offseason-rinnovi` da RS, playoff o break (tornando indietro da draft/RFA/FA/ruoli no);
3. `stagione.dopo_cambio_fase()`: i passaggi automatici sui contratti (sezione 4, "Stagioni e contratti finiti"). Se falliscono la fase resta cambiata, l'errore va nel messaggio e nel log, e `/dev_stagione rifai` li ripete;
4. ri-registra i comandi (`comandi.registra_comandi`);
5. annuncia sul canale (`testo_annuncio_fase()` + `FASI_INDICAZIONI`, da tenere allineate al regolamento);
6. lancia i report di fine fase (ruoli mancanti, vincoli ruoli all'ingresso in RS).

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
| `giocatori` | anagrafica: `nome_common`, `nome_bref`, `nome_yahoo`, `nome_norm`, `yahoo_id`, `espn_id` e `nome_espn` (scritti da loucabot, per tabellini e calcolo), `data_nascita` |
| `contratti` | `importo`, `anni_originali`, `stagione_firma` (da quando parte il contratto, o il pezzo di rookie scale), `tipo` (normale/rookie/10day), `attivo`. Mai cancellati: un contratto chiuso ha `attivo = FALSE` |
| `transazioni` | **registro unico** di tutto quello che si muove in lega: giocatori, diritti, pick (vedi sotto) |
| `registro_azioni` | **registro delle azioni** (v6.0.0): chi ha fatto cosa, in tutti i bot (vedi sotto). Non sostituisce `transazioni` |
| `impatto_taglio` | rate delle spalmature: una riga per squadra, giocatore e stagione |
| `dpe` | DPE approvate: `importo_originale`, `importo_dpe`, `pre_deadline`, `stagione`, `team_id` (segue il giocatore in trade) |
| `messaggi_fissi` | messaggi sul canale che il bot modifica invece di riscriverli: `chiave` (es. `riepilogo_rfa:2027`), `chat_id`, `message_id` (v3.13.3) |
| `rfa_dichiarati` | RFA dichiarati nella fase dei rinnovi: `stagione`, `team_id` (segue il giocatore nelle trade con le aste aperte), `giocatore_id`, `contratto_id` (l'x0), `stato` attiva/revocata, `da`, `nota` (`trade <id>` se decaduta con una trade prima delle aste) |
| `migrazioni` | migrazioni una tantum già fatte (`_migrazione_fatta(nome)`) |

**Trade, pick e rookie**

| Tabella | Contenuto |
|---|---|
| `trade` | trade e bozze: `stato`, `trade_ref` `TRADE-AAAA-NNN`, `bozza_num`, `proposta_da`, `note`/`nota_gm` |
| `trade_squadre`, `trade_items`, `trade_voti` | squadre, pezzi (`team_id_a = '?'` = destinatario da assegnare) e voti |
| `pick` | `proprietario_orig`, `proprietario_att`, `anno`, `round`, `protezioni`, `scattata` |
| `rookie` | diritti e rookie scale: `pick_numero`, `anno_draft`, `anno_firma` (inizio della scala: da qui l'anno di scala e il colore R0–R3), `anni_scala` (solo informativa, aggiornata al cambio di stagione), `firmato`, `diritti_scaduti` |

**Ruoli e posizioni**

| Tabella | Contenuto |
|---|---|
| `cambi_ruolo` + vista `ruolo_attuale` | event log dei ruoli (`iniziale`, `ordinario`, `erminio`, `saedro`, `forzato_admin`, `post_trade`, `post_firma`, `dpe_extra`, …) |
| `posizioni_eleggibili` + vista `posizioni_attuali` | event log delle posizioni Yahoo (una riga solo se il set cambia; `data_yahoo` per Erminio) |
| `ruoli_bozze` | dichiarazione di inizio stagione non ancora confermata |
| `ruoli_pendenti` | dichiarazioni post-trade/firma in RS (48 ore); anche i ruoli assegnati in automatico (stato `assegnata`, `nota` col perché) |
| `ruoli_messaggi` | il messaggio unico dei ruoli di una trade sul canale (riferimento → chat, messaggio), v6.2.0 |

**Richieste, code e dati esterni**

| Tabella | Contenuto |
|---|---|
| `richieste_admin` | richieste aperte (DPE, Saedro, decadimento): una per giocatore, decisione unica |
| `cap_anticipato`, `slot_anticipato` | `/autocap` e `/autoslot` del bot aste (48 ore) |
| `gas_sync_queue` | il bot aste ci accoda le firme, questo bot sincronizza i fogli |
| `bref_stats` | snapshot Basketball-Reference: una riga quando G aumenta (`bref_schema.sql`) |
| `bref_nuovi` | giocatori bref non in anagrafica, con decisione del dev |
| `penalita` | nello schema, non usata (la penalità è in teams.json) |

**Viste:**

| Vista | Contenuto |
|---|---|
| `movimenti_giocatori` | le righe di `transazioni` con `oggetto = 'giocatore'`: è da qui che si ricostruisce qualsiasi roster |
| `roster_attuale` | contratti attivi con l'ultimo movimento del giocatore (usata dai ruoli) |
| `firme` | firme dei giocatori, per la dashboard |

### Il registro unico (`transazioni`, v3.10.0)

Ogni riga ha un `oggetto` che dice di cosa parla:

| `oggetto` | Colonne | Esempi di `tipo` |
|---|---|---|
| `giocatore` | `giocatore_id` (+ `contratto_id`) | `signed`, `traded`, `cut`, `decadimento`, `rookie_firma`, `expired`, `renewed`, `rookie_scala`, `rookie_fine_scala` |
| `diritti` | `giocatore_id` (diritti di una 2nd non firmata) | `iniziale`, `traded`, `rookie_firma` (attivati), `rookie_diritti_scaduti` |
| `pick` | `pick_id` | `iniziale`, `traded`, `creata` (pick dell'anno +6, v3.11) |
| `squadra` | nessuna delle due | `cut` gratuito pre-bot (conta nei tagli gratuiti, non sposta nessuno) |

Il controllo `transazioni_oggetto_check` impedisce combinazioni sbagliate (una pick senza `pick_id`, un giocatore senza `giocatore_id`).

**Le quattro regole:**

1. **Lo stato di oggi** sta nelle tabelle: `contratti` attivi (roster e cap di entrambi i bot), `pick.proprietario_att`, `rookie.team_id`.
2. **Il registro** dice come ci si è arrivati. Ogni operazione scrive tutte e due le cose nella stessa transazione DB: trade, tagli, firme, attivazioni, scadenze, rilasci RFA.
3. **Chi ricostruisce un roster** (a una data, 30 giorni, 60 giorni, fantamedie) legge `movimenti_giocatori`, mai `transazioni`. La prova `tests/docs/letture_transazioni.py` fallisce se qualcuno legge `transazioni` fuori dalle funzioni ammesse.
4. **"Ultimo movimento"** = `ORDER BY timestamp DESC, id DESC`: a parità di orario vince l'ultima riga scritta.

**Lo storico di pick e diritti** l'ha creato `crea_storico_pick_diritti()` la prima volta, rigiocando all'indietro le trade e verificando che tutto tornasse con lo stato di oggi:
- una riga `iniziale` alla data della prima transazione, cioè l'avvio del bot;
- poi una riga per ogni trade e annullamento.

Finché lo storico non esiste (`storico_pick_diritti_presente()`), trade e attivazioni non scrivono righe di pick e diritti: lo storico nasce tutto insieme o niente.

**Controllo notturno** (`handlers/coerenza.py`, all'01:00, o `/dev_coerenza`). Confronta stato e registro:
- per ogni giocatore, la squadra del contratto attivo con quella dell'ultimo movimento;
- per ogni pick e diritto, il proprietario di oggi con l'ultimo movimento;
- nessun giocatore con due contratti attivi;
- nessun x0 attivo (non RFA) fuori da rinnovi, draft e RFA, nessun contratto `rookie` oltre il IV anno (v3.11).

Se trova qualcosa scrive al dev. Di solito è una modifica fatta a mano sul DB: si sistema **aggiungendo il movimento mancante**, non cancellando righe.

### Il registro delle azioni (`registro_azioni`, v6.0.0, `shared/azioni.py`)

`transazioni` dice **cosa** si è mosso; `registro_azioni` dice **chi** ha fatto **cosa**, in tutti e quattro i bot, anche le azioni che non muovono giocatori (impostazioni, fasi, penalità, ruoli, aste, panchine, convalide). Una riga: `quando`, `bot` (main/aste/louca/ipa), `chi_id` e `chi_nome`, `veste`, `azione`, `squadre` (array: una trade conta per tutte), `giocatore_id`, `oggetto`, `prima`, `dopo`, `nota`, `dettagli` (JSONB, es. `trade_id`, `asta_id`). La tabella si crea in `migrate_db` (e, se un altro bot parte prima, al primo uso).

- **Veste**: `gm`, `admin`, `dev`, `sistema`. La decide il flusso che chiama (prefisso del bottone, pannello o comando admin), mai un «è admin?»: dal menu normale un admin è `gm`.
- **Dove va**: sempre nel registro; le vesti `admin` e `dev` anche sul canale log del bot che le fa, nel formato unico (`azioni.riga_log`). `gm` e `sistema` solo nel registro, tranne le righe di log che c'erano già (dichiarazione ruoli, RFA, 10-day scaduti).
- **Mai bloccante**: si scrive dopo che l'azione è riuscita; `registra` e `azione` non sollevano mai (un errore finisce nel log del processo).
- **Per bot**: qui `handlers/registro.py` (`segna` = registro + log, `segna_sync` = solo registro, `solo_log` = solo la riga di riassunto di un'azione in blocco, le cui righe sono già nel registro una per una); nel bot aste `registro.py` (`segna`, `segna_asta` che prende squadre, giocatore e oggetto dall'asta); in loucabot e IPanchinari `registro.py` (lì le azioni admin avevano già la riga di log col nome, quindi `segna_sync`). Per le trade `trade_comune.segna_trade` (squadre e contenuto della trade).
- **Consultazione**: `/registro` (`handlers/registro.py`, filtri in `filtri()`, ricerca in `azioni.cerca`). Admin: tutto; GM: solo le righe con la sua squadra.
- Le bozze delle trade non hanno una riga per ogni bottone: c'è la riga quando si crea con un import, quando si manda (col contenuto di quel momento) e quando si elimina.

### Stagioni e contratti finiti (v3.11.0, `handlers/stagione.py`)

**Anni residui, sempre calcolati:** `db.anni_residui(c, stagione) = anni_originali − (stagione − stagione_firma)`, anche per i rookie, senza minimo. In SQL: `db.SQL_IN_CORSO` (≥ 1) e `db.SQL_RFA` (dichiarazione attiva sul contratto), parametri `(stagione, stagione)`.

- **x0** (≤ 0) = contratto finito: resta attivo e in squadra fino all'inizio della FA, si può scambiare, ma **non pesa su cap né slot**. Unica eccezione l'RFA dichiarato: cap sì, slot no.
- Cap e slot: **un'implementazione sola in `shared/cap.py`** (v3.12.0), usata dai due bot con la loro funzione di query. Qui `cap_occupato_team`, `peso_cap_giocatore`, `occupa_slot` la chiamano; `get_roster_team` ha per ogni riga `pesa_cap` e `occupa_slot` calcolati da lì, e `slot_occupati(roster)` / `cap_roster(roster)` li sommano. Nel bot aste `pg_client.get_cap_contratti`, `get_impatto_taglio`, `get_roster_count`. Una regola nuova su cosa pesa si cambia solo lì.
- `get_roster_team` dà per ogni riga `anni_residui`, `x0`, `rfa`, `contratto_id`, `anni_scala` (= stagione − `rookie.anno_firma`: 0 = I anno … 3 = IV anno). `get_roster_team_at` li calcola sulla stagione di quella data.

**Ogni cambio di importo è un contratto nuovo:** il vecchio va a `attivo = FALSE` e si scrive il movimento. I contratti non si cancellano mai.

**Rookie scale** (`rookie_scale` di settings, per fascia di pick: I x2, II x1, III x2, IV x1). Entrando nella stagione S (`applica_stagione(S)`, in un'unica transazione, rilanciabile), con k = S − `anno_firma`:

| k | Condizione | Cosa fa | Movimento |
|---|---|---|---|
| 1 | contratto del I anno (`stagione_firma = anno_firma`) e importo del II diverso | contratto nuovo II anno x1 | `rookie_scala` |
| 2 | x0 | niente: attende rinnovo rookie, RFA o scadenza | — |
| 3 | rinnovo III-IV (x2 firmato in S−1) con importo sotto la scala del IV anno | contratto nuovo IV anno x1 (una Doncic è già più alta e resta) | `rookie_scala` |
| 4 | x0 | contratto `normale` x0, importo max(attuale, Doncic sul III-IV) | `rookie_fine_scala` |

Rinnovo rookie a fine II anno (`esegui_rinnovo_rookie`): `tipo = 'rookie'` x2, importo max(scala III, Doncic), movimento `renewed` con `rookie_scale = TRUE`. Doncic: `doncic(fm)` con X = ⌊max fantamedia delle due stagioni⌋ e risultato per eccesso in aritmetica intera; `fantamedia_max(gid, stagioni_lega)` legge bref alla stagione + 1.

**La migrazione `rookie_pezzi_v3_11`** (una volta sola, tabella `migrazioni`): fino alla v3.10 i pezzi II, III e IV avevano `stagione_firma = anno_firma`; li ha portati alla stagione in corso.

**Passaggi automatici** (`dopo_cambio_fase`, tutti rilanciabili, ognuno a sé: se uno fallisce gli altri vanno avanti):

| Entrando in | Cosa |
|---|---|
| `offseason-rinnovi` | `applica_stagione`, dettaglio nel gruppo admin (`testo_piano` via `manda_lungo`); `crea_pick_anno(S + 6)` con movimento `creata` (fino al draft di S le annate sono 7: le pick di S diventeranno posizioni al draft) |
| `offseason-rfa` | niente qui: le aste RFA le apre il bot aste (`handlers/rfa.py`) |
| `offseason-fa` | `scadenza_x0`: gli x0 non RFA → `attivo = FALSE` + `expired`, elenco sul canale |
| `regular-season-fa` | `testo_report_inizio_rs`: sotto il floor (con `/set_cap_penalizzato` già scritto, 2M per milione) o sopra il tetto → gruppo admin |

**Il piano** (`_calcola_piano`, la stessa funzione per l'anteprima e per il passaggio vero) elenca tutti i rookie che cambiano anno di scala: `secondo_anno` / `quarto_anno` (importo nuovo), `secondo_anno_uguali` / `quarto_anno_uguali` (restano, con il `motivo`: stesso importo in tabella o Doncic sopra la tabella), `fine_scala`, `da_rinnovare` (con la `proposta` del rinnovo rookie, stima con le fantamedie del momento), `anomalie` (contratti rookie con una forma che non torna col loro anno: finiscono in "Da controllare", non vengono toccati), `x0` per squadra. Nel passaggio vero si scrivono solo `secondo_anno`, `quarto_anno` e `fine_scala`.

**RFA dichiarati.** Uno per squadra e stagione (indici unici parziali). La dichiarazione vale finché il suo contratto x0 è attivo: quando l'asta si conclude il bot aste chiude quel contratto e lei smette di pesare da sola (`rfa_squadra`, `rfa_dichiarato`; `rfa_usata` la vede anche dopo). **RFA e trade** (deciso con Luca il 12/10/2026, v3.13.1), in `_scrivi_trade`: prima delle aste RFA (`settings.FASI_RFA_PRIMA_DELLE_ASTE`: rinnovi e draft) la dichiarazione decade (`db.revoca_rfa_trade`: resta revocata alla squadra che l'aveva fatta, con `nota = 'trade <id>'`), chi lo cede può dichiararne un altro, per chi lo riceve è un x0 che non pesa (`_cap_post_team`), nessun limite sul numero; riepilogo (`avvisi_trade`) e notifiche lo dicono. Dalla fase RFA in poi la dichiarazione segue il giocatore (`db.sposta_rfa_trade`, il bot aste allinea il proprietario dell'asta) e vale `validators.trade._errori_rfa`: dopo la trade ogni squadra ha al massimo un RFA. L'annullamento di una trade rimette la dichiarazione dov'era (`db.ripristina_rfa_trade`, se intanto la squadra non ne ha dichiarato un altro). Si dichiara e si cambia fino all'inizio delle aste (`/dichiara_rfa` nei rinnovi e nel draft). **Canali** (v3.13.3): ogni dichiarazione, cambio, ritiro e trade di un RFA è una riga sul canale log (`stagione.log_rfa`); sul canale principale c'è un solo riepilogo per stagione (`stagione.aggiorna_riepilogo_rfa`, `db.rfa_stagione`), modificato a ogni cambio e ritrovato tramite `messaggi_fissi`: se non si può più modificare (cancellato) ne manda uno nuovo.

### Due cose da ricordare

**1. I CHECK dei tipi.** `migrate_db()` (all'avvio) ricrea i CHECK di `transazioni` e `cambi_ruolo` con `_allinea_check` come **unione** dei valori. Un tipo nuovo va aggiunto lì **e** in `schema.sql`.

**2. Lo schema cresce da solo.** `schema.sql` crea il DB solo la prima volta (initdb del container). Le tabelle e colonne successive le crea `migrate_db()` a ogni avvio, sempre con `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`.

### Accesso a mano

```bash
docker compose exec postgres psql -U fantabasket -d fantabasket -c "SELECT ..."
```

Da uno script Python nel container, chiama `db.init_db()` prima di usare il DB.

Esempio: tutti i movimenti di un giocatore.

```sql
SELECT t.timestamp, t.tipo, t.team_id_da, t.team_id_a, t.note
FROM movimenti_giocatori t JOIN giocatori g ON g.id = t.giocatore_id
WHERE g.nome_common ILIKE '%durant%' ORDER BY t.timestamp, t.id;
```

Esempio: la storia di una pick.

```sql
SELECT t.timestamp, t.tipo, t.team_id_da, t.team_id_a, t.note
FROM transazioni t JOIN pick p ON p.id = t.pick_id
WHERE p.proprietario_orig = 'team04' AND p.anno = '2031' AND p.round = 1
ORDER BY t.timestamp, t.id;
```

---

## 5. I file

**Radice**

| File | Contenuto |
|---|---|
| `bot.py` | avvio: registra gli handler, i job, l'error handler (errori al canale log e al dev), la versione dal CHANGELOG |
| `settings.py` | lettura config, costanti di fase, `is_admin`, decoratori `@solo_privato` e `@richiede_fase` |
| `database.py` | tutte le query (`_q(sql, params, one=, many=)`), `migrate_db()`, transazioni atomiche (trade, tagli, decadimenti) |
| `teams.py` | `get_team_by_id`, `get_team_by_gm`, `get_team_by_query` (fuzzy: id → nome esatto → prefisso → difflib 0.6, in `shared/squadre.py`, la stessa di `/team` nel bot aste), `set_campo_team` |
| `comandi.py` | menu "/" di Telegram per scope e fase (`_fasi_comando`). Scope: privato (GM), ogni admin e il dev in privato, tutti i gruppi **e gli amministratori dei gruppi** (`BotCommandScopeAllChatAdministrators`, stesso menu dei gruppi: senza, chi diventa admin del gruppo della lega non vedeva più i comandi; v6.7.8), il gruppo admin col menu admin **meno i comandi solo privati** (`SOLO_PRIVATO`, trovati da `bot.post_init` con `trova_solo_privato` dagli handler col decoratore `settings.solo_privato`). `solo_privato` nel gruppo admin risponde «↪️ (il comando) funziona solo in privato» col bottone per aprire la chat; negli altri gruppi silenzio |
| `scheduler.py` | backup, sync fogli, coda GAS, scadenza diritti |
| `gas_client.py` | payload dei fogli Roster e Scelte, `sync_after_*`, `sync_bref_raw`; sul Roster i nomi di Basketball-Reference (`nomi_foglio`, v6.5.4: le formule si agganciano a BrefRaw per nome) |
| `bref_scraper.py` | scraping per_game di Basketball-Reference (anche standalone con `--migrate`) |
| `nomi.py` | abbinamento nomi severo (`/set_nascita`, giocatori bref nuovi) |
| `utils.py`, `log_buffer.py` | fuso `ROME`, formattazione date, normalizzazione; buffer per `/dev_log` |
| `carriera.typ` | template Typst di `/carriera` (toni blu, due timeline; v6.5.0) |
| `roster.typ`, `assets.typ` | template Typst delle immagini (v6.4.2: stessi input di sempre; `#set block(spacing: 0pt)`, righe vuote basse, etichetta «FUORI DAI 15» sopra chi sta sotto la riga spessa, il riquadro `badge` quando il colore del contratto non contrasta, footer a riquadri col colore `_ton_ftr` in trasparenza; risoluzione in `handlers/roster.py`: `PPI_ROSTER` 288, `PPI_ASSETS` 240, cioè 1200 e 1400 pixel di larghezza) |
| `validators/trade.py` | validazione trade: cap, roster, floor, Stepien, ruoli, struttura a 3+ |
| `validators/ruoli.py` | involucro di `shared/ruoli_core.py` |

**handlers/**

| File | Cosa contiene |
|---|---|
| `carriera.py` | `/carriera` (v6.5.0): `eventi_fanta` (`database.movimenti_carriera` dal 25/07/2026, più `dpe`; trade annullate tolte con l'annullamento, stesso `trade_id`), `eventi_nba` (squadra al 25/07, `nba_movimenti` di loucabot, cambi nelle righe di `bref_stats`; un cambio di bref già visto da ESPN nei 30 giorni prima non si ripete), `righe_timeline`, `dati`, `genera_png` (Typst a 220 dpi); `NBA` = nomi e colori delle 30 squadre; loghi NBA da `config/loghi/nba/<SIGLA>.png`; callback `car:<id>` |
| `menu.py` | `/menu` per fase (`AZIONI_FASE`, `AZIONI_SEMPRE`), `/guida`, `/guida_admin` |
| `trade.py` | registrazione di comandi, bottoni e conversazioni delle trade (`get_handlers`), `/annulla_trade`; in testa l'indice dei moduli `trade_*` |
| `trade_comune.py` | stati delle conversazioni, `_STATI`, testo del riepilogo, tastiere, chi può toccare una bozza, annuncio sul canale, notifiche alle squadre |
| `trade_crea.py` | `/build_trade` e `/import_trade`: squadre, asset, destinazioni a 3+ squadre, riepilogo, nota, invio, salva bozza |
| `trade_modifica.py` | `/edit_trade` e "Modifica" dal riepilogo |
| `trade_voto.py` | proposta ai GM, voti, rifiuto con nota, approvazione degli admin |
| `trade_esegui.py` | `_scrivi_trade` (l'unico punto che sposta gli asset; `inverti=True` per annullare), `_esegui_trade`, `/annulla_trade_admin` |
| `trade_liste.py` | `/my_trades` (= `/mie_trade`), `/bozze_trade` |
| `trade_parser.py` | parser del testo delle trade |
| `tagli.py` | `/taglia`: anteprima, spalmature, limiti |
| `dpe.py` | `/dpe` e `_importo_dpe()` |
| `rookie.py` | `/attiva_diritti`, scadenza diritti |
| `stagione.py` | cambio di stagione (rookie scale, Doncic, x0), `/rinnovo_rookie`, `/dichiara_rfa`, passaggi di fase, `/dev_stagione`, `/trade_deadline` |

| `decadimento.py` | `/decadimento`, motivi, `/ritiro_fa` |
| `spalmature.py` | report mensile e `/report_spalmature` |
| `coerenza.py` | controllo notturno contratti/pick/diritti contro il registro, `/dev_coerenza` |
| `registro.py` | registro delle azioni: `segna`, `segna_sync`, `solo_log`, `/registro` |
| `ruoli.py` | dichiarazione di inizio stagione, `/deadline_ruoli` |
| `ruoli_rs.py` | dichiarazioni post-trade/firma in RS; per le trade un messaggio unico sul canale (`testo_trade`, `aggiorna_messaggio_trade`) aggiornato a ogni dichiarazione, assegnazione ed estrazione |
| `cambi_ruolo.py` | `/cambio_ruolo`: ordinario, Erminio, Saedro, forzato, Extra DPE |
| `dieci_giorni.py` | `/firma_10day` (GM, richiesta), `/firma_10day_admin`, approvazione, pannello, scadenza |
| `posizioni.py` | import e correzione delle posizioni eleggibili, `/data_erminio`; `/posizioni_mancanti` e `job_report_posizioni` (`mancanti`: sotto contratto e free agent con righe di `bref_stats` nelle stagioni di `shared/lista_fa.stagioni_valide`, le stesse di `/lista_fa` (quest'anno e l'anno prima, dopo lo switch al 70% dei firmati solo quest'anno); ogni mattina in privato al dev (`dev_id`) con `manda_lungo` se l'elenco cambia, impronta in `report_posizioni_inviato`; il lunedì comunque) |
| `roster.py` | `/roster`, `/assets` (Typst) |
| `team_diff.py` | `/team_diff` |
| `palette.py`, `myteam.py` | colori e dati squadra (colori effettivi e testo leggibile: `roster.colori_effettivi`, `roster.input_colori`) |
| `nav.py` | navigazione dei menu: ✖️ Chiudi (`nav:x`), 🏠 Menu, ←, `mostra()` (da un bottone modifica il messaggio invece di mandarne uno nuovo) |
| `admin_panel.py` | `/admin_menu`, fasi, DPE e tagli admin, `/registra_firma`, `/list`, `/set_cap_penalizzato`, situazione cap |
| `trova_trade.py` | `/trova_trade` (v6.12.0): `per_numero` / `per_giocatore` (solo `stato` approvata o annullata, con `trade_ref`), `dati` (asset dal movimento della trade: contratto di allora da `transazioni.contratto_id`; `_cap_roster` a un istante: roster a una data, DPE a una data, spalmature con la transazione fino ad allora; `_percorso` da `trade`, `trade_voti` e `registro_azioni`), `trova_trade.typ` (in verde) col Typst del container, emoji dal font Noto Color Emoji (`fonts-noto-color-emoji` nel Dockerfile, come loucabot); trade a due solo «riceve» |
| (shared) `parole_nome.py` | nomi dei giocatori in qualsiasi ordine (v6.11.1): `nomi.esatti`/`simili`, `db.cerca_giocatori` (ogni parola, se il pezzo intero non c'è), `posizioni._cerca_giocatori` (anche `/carriera`), `dieci_giorni.cerca` |
| `bref.py` | job Basketball-Reference e conferma dei giocatori nuovi; dopo ogni abbinamento (`abbina_auto`, bottone 🔗) `aggiorna_foglio` risincronizza il foglio Roster se il giocatore è sotto contratto (v6.9.0) |
| `nascite.py` | `/set_nascita`, `/nascite_mancanti` |
| `dev.py`, `dev_player.py` | comandi dev |
| `helpers.py` | `log_job_error`, `log_warn` |

**shared/** (montata in sola lettura in tutti e due i container: una modifica richiede il riavvio di entrambi)

| File | Contenuto |
|---|---|
| `ruoli_core.py` | regole dei ruoli (sezione 6) |
| `cap.py` | cap e slot di una squadra (v3.12.0): `cap_occupato`, `cap_contratti`, `impatto_taglio`, `giocatori_in_slot`, `peso_cap`, `occupa_slot`, i frammenti SQL (`SQL_IN_CORSO`, `sql_rfa`, `SQL_OCCUPA_SLOT`) e `anni_residui`. Prova: `tests/main/cap_condiviso.py` |
| `squadre.py` | `cerca_squadra(query, squadre)`: la ricerca di /roster, /assets, /team_diff e di /team nel bot aste |
| `messaggi.py` | `manda_lungo(bot, chat_id, testo_html, nome_file, riassunto=None)`: messaggio se sta in Telegram, altrimenti riassunto + file `.md` generato in memoria (`html_a_markdown`). Da usare per ogni report o elenco amministrativo che può crescere |

### Prefissi dei bottoni (callback_data)

Utile per capire chi risponde a un bottone. In grassetto quelli citati più spesso.

| File | Prefissi |
|---|---|
| `trade_crea.py` | `menu_trade_build`, `menu_trade_import`, `trade_n:`, `trade_sq:`, `trade_am:`, `trade_gi:`, `trade_pi:`, `trade_di:`, `trade_dest:`, `trade_send:`, `trade_nota:`, `trade_salva:`, `trade_del:` |
| `trade_modifica.py` | `edit_*` (`edit_back:` dal riepilogo è di `trade_crea.py`) |
| `trade_voto.py` | `trade_vedi:`, `trade_voto:`, `trade_rifiuta_conf:`, `trade_admin:` |
| `trade_liste.py` | `mt:` (solo `mt:l` e `mt:v/r/c:<id>`) |
| `admin_panel.py` | `adm*`, `fase_*`, `rfirma:` |
| `rookie.py` | `att_r*`, **`attadm:`**, `scadi_diritti:` |
| `decadimento.py` | `dec_*`, **`decadm:`** |
| `dpe.py` | `dpe_*` |
| `tagli.py` | `taglia_*` |
| `cambi_ruolo.py` | **`cr:`** (GM), **`ca:`**/`cradm:` (admin), `sae:` (Saedro) |
| `dieci_giorni.py` | `td:` (GM), `tda:` (admin che firma), `tdq:` (richiesta), `tdadm:` (pannello) |
| `registro.py` | `reg:7` (pannello admin → 📜 Registro) |
| `ruoli.py` | `rl:`, `rladm:`, `rli:` |
| `ruoli_rs.py` | `rp:`, `rpadm:` |
| `posizioni.py` | `pos_imp_`, `spe:` |
| `myteam.py` | `mt:<campo>:<team>` |
| `palette.py` | `pal_*` |
| `myteam.py` | `myt:` (prima `mt:`, che è di `trade_liste.py`) |
| `nav.py` | `nav:x` (✖️ Chiudi, ovunque) |
| `trade_comune.py` | `trade_x` (✖️ Annulla nel builder), `trade_x:menu` (← Trade) |
| `bref.py` | `brefn:` |
| `nascite.py` | `nasc:` |
| `dev_player.py` | `dp:` |
| `menu.py` | `menu:`, `roster_sq:`, `assets_sq:` |
| `stagione.py` | **`sg:`** (GM: `rr`, `rrg`, `rrok`, `rfa`, `rfag`, `rfaok`, `rfano`), **`sga:<team>:`** (admin, stesse azioni), `sga:scegli:`, `sga:elenco` |

Tutti i bottoni delle trade sono registrati in `trade.py` (`get_handlers`), anche quelli dei moduli `trade_*`.

Attenzione: `mt:` è usato da due file. Funziona perché gli handler delle trade sono registrati prima e hanno un pattern più stretto. Se aggiungi un `mt:` nuovo, controlla che non si pestino.

---

## 6. Le regole, dove stanno

Lo specchietto completo, regola per regola del regolamento con il codice e la prova che la controlla (e le differenze da decidere), è in [`docs/regolamento_e_codice.md`](../../docs/regolamento_e_codice.md). Qui i dettagli di come funzionano.

### Trade

**Stati.** Tutti i passaggi passano da `db.cambia_stato_trade(id, da=(...), a=...)`, che è atomico:

- percorso normale: `bozza → proposta → in_approvazione → approvata`;
- uscite: `rifiutata_gm`, `rifiutata_admin`, `annullata`.

**Esecuzione e rollback.** `_scrivi_trade` (`trade_esegui.py`) fa tutto in un'unica transazione DB: approvazione, spostamento di giocatori, pick e diritti, transazioni, `dpe.team_id`, stato. Se un pezzo non torna solleva `TradeNonEseguibile` e non scrive niente. `trade_ref` viene assegnato prima dell'esecuzione.

**Validazione** (`validators/trade.valida_trade`):

- struttura (niente `?`, niente pezzi doppi, ogni squadra cede o riceve qualcosa);
- possesso dei pezzi;
- cap post-trade per squadra, con la DPE ridotta;
- roster ≤ 15 (i giocatori con DPE non contano);
- salary floor in stagione;
- Stepien (`anni_coperti_stepien`, finestre di `stepien_anni`; gli anni ≤ 2026 sono coperti d'ufficio);
- in RS, i ruoli (`deficit_minimo`);
- RFA dichiarati: prima delle aste RFA nessun limite (la dichiarazione decade), con le aste aperte al massimo uno per squadra dopo la trade (`_errori_rfa`). Cap e slot usano `peso_cap_giocatore` e `occupa_slot`: un x0 non pesa, l'RFA dichiarato pesa sul cap.

**Notifiche** (`trade_comune.py`). `_notifica_squadre(context, trade_id, testo, escludi=())` scrive a tutte le squadre (e al gruppo admin se la trade è degli admin). `_notifica_proponente` solo per l'avanzamento dei voti.

**Bozze.** `_bozza_non_modificabile` / `_puo_gestire_bozza`: si toccano solo in stato `bozza`, solo dal proponente o da un admin.

**Etichette delle bozze.** `BUF03-3` = prime 3 lettere del nome squadra + numero squadra + `bozza_num`; `ADM-4` per le bozze degli admin.

### Tagli e spalmature (`tagli.py`)

- **Gratuito:** 1M x1 con meno di 3 tagli gratuiti già fatti nella stagione (`max_tagli_gratuiti` in settings.json). Dal quarto, spalmatura 1x1.
- **Sopra i 5M:** percentuali per anni residui (x1: 50-30-20; x2: 60-50-50-40; x3: 70-70-60-50-50), arrotondate per eccesso, con l'eccedenza tolta dal fondo senza scendere sotto 1 (7x1 → 4-2-1).
- **Fino a 5M:** tabella fissa `_TABELLA_SPALMATA_BASSA`.
- **Controlli e scrittura:** `_valuta_taglio` / `TaglioNonEseguibile` bloccano in RS sotto i 10 e se si scopre un ruolo, e un contratto finito (x0: non pesa e scade da solo). `esegui_taglio` scrive contratto, transazione e rate in un'unica transazione; `dopo_taglio` annuncia e sincronizza. GM e pannello admin passano entrambi da qui (v3.10.0).

### DPE (`dpe.py`)

- `_importo_dpe`: contratto − ceil(25%).
- `pre_deadline = fase != "regular-season-deadline"`, valutato **all'approvazione**.
- Approvata prima della deadline: il giocatore non occupa slot. Approvata dopo: lo slot resta occupato, ma c'è un cambio ruolo `dpe_extra` gratuito. Conta `dpe.pre_deadline` (il momento dell'approvazione), non la fase di oggi (`shared/cap.py`).
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
- Rinnovo rookie a fine II anno e passaggi della scala: `stagione.py` (sezione 4, "Stagioni e contratti finiti").
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
| 01:00 | `coerenza.job_coerenza` | contratti, pick e diritti contro il registro → dev, solo se trova qualcosa |
| ogni 5 min | `_ping_healthcheck` | solo con `HEALTHCHECK_URL` |
| ogni 15 min | `ruoli_rs.job_scadenze` | estrae il ruolo delle dichiarazioni oltre le 48 ore |
| ogni 15 min | `cambi_ruolo.job_fine_saedro` | chiude le Saedro scadute |
| ogni 15 min | `dieci_giorni.job_scadenza` | chiude i 10-day scaduti (fine giornata compresa) |
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
| `/dev_coerenza` | controllo di coerenza contratti/pick/diritti contro il registro, subito |
| `/dev_stagione` | anteprima del prossimo cambio di stagione (sola lettura); `/dev_stagione rifai` ripete i passaggi automatici della fase in corso |
| `/job_status` | job e prossima esecuzione |
| `/broadcast <testo>` | messaggio a tutti i GM |
| `/sync_sheets` | sync completo dei fogli |
| `/backup` | backup subito |
| `/reboot` | riavvia (Docker lo rialza) |

**Admin:**

| Area | Comandi |
|---|---|
| pannello e squadre | `/admin_menu`, `/list` |
| fasi e date | `/set_fase`, `/trade_deadline` |
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
| rinnovi (fase rinnovi) | `/rinnovo_rookie`, `/dichiara_rfa` |
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

- **Percorso:** il bot manda a `gas-router` (POST `/gas/roster`, `/gas/scelte`, `/gas/bref`; loucabot `/gas/calendario` → `gas/calendario.gs`, foglio Calendario ricaricato tutto in A:E) e il router gira alla web app Apps Script con il suo token.
- **Fogli:** Roster (per squadra), Scelte (pick, diritti, Stepien, colori delle division da `config/divisions.json`), BrefRaw.
- **Quando sincronizza:** `gas_client.sync_after_*` dopo ogni operazione, il periodico ogni 2 ore, la coda per le firme del bot aste. Il foglio Roster si manda **sempre per tutte le 24 squadre**: `sync_teams` ignora l'elenco che riceve, quindi non serve preoccuparsi di quali squadre passare.
- **Deploy Apps Script:** `clasp push` dalla cartella `gas/` (escluso `globals.gs`, che ha la config vera e non va mai nello zip). La nuova versione si pubblica da Gestisci deployment → matita → Nuova versione. Un "Nuovo deployment" cambia l'URL: vanno aggiornati i secrets.
- **Il foglio dice "Sync fallito":** chiama la web app dal container gas-router; se risponde HTML, il `<title>` dice l'errore.

**Basketball-Reference** (`bref_scraper.py` + `handlers/bref.py`). Ogni giorno alle 12 (`orari.bref` in settings.json; prima alle 10, ma bref aggiorna in tarda mattinata), una sola richiesta per_game, che serve a:

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
5. **una via d'uscita in ogni schermata coi bottoni** (← verso la schermata di prima, 🏠 Menu o ✖️ Chiudi, `handlers/nav.py`; v6.1.0);
6. **la riga nel registro delle azioni**: `segna(bot, user, "gm"|"admin", azione, squadre=…, giocatore_id=…, prima=…, dopo=…)` dopo che l'azione è riuscita, con la veste del flusso (v6.0.0);
7. la riga nella guida GM.

La prova `tests/docs/guide_e_menu.py` si accorge se una guida o il menu cita un comando che non esiste.

**Regole di casa:**

- Report ed elenchi amministrativi che possono crescere: `shared.messaggi.manda_lungo`, non messaggi spezzati a mano (sopra i 4096 caratteri Telegram rifiuta il messaggio).
- I contratti non si cancellano mai: chiusura = `attivo = FALSE` + movimento; cambio di importo = contratto nuovo + movimento; cambio di squadra (trade) = `team_id` aggiornato + movimento. Ogni cosa che sposta o chiude un contratto scrive il suo movimento nella stessa transazione DB, se no il controllo notturno lo segnala.
- `update.effective_message` ovunque. Nei callback, `query.get_bot()` per mandare messaggi altrove.
- ConversationHandler con `per_message=False`. `/annulla` globale (group −1) pulisce `user_data` e chiude tutto.
- Le scritture che toccano più tabelle vanno in un'unica transazione: vedi `_scrivi_trade`, i tagli, `registra_decadimento`.
- Un solo file per modulo, import sempre `handlers.xxx`. In passato si sono corretti bug sulla copia morta.
- Un file che passa le mille righe si divide per argomento, come `trade_*.py` qui e `admin_*.py`/`firma_*.py` nel bot aste: un modulo `*_comune.py` con quello che serve a tutti, i moduli per fase, e il file originale che tiene la registrazione degli handler e in testa l'indice. Si sposta il codice senza cambiarlo, nello stesso rilascio niente altro.
- Gli import dentro le funzioni (`from handlers.x import y`) pyflakes non li controlla: lo fa `tests/docs/nomi_importati.py`, che verifica anche `db.funzione` e le sostituzioni fatte dalle prove.
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
3. `MIGRATION.md` aggiornato dove cambia lo stato (decisioni, architettura, operazioni, da fare): niente righe per versione, la storia sta nei CHANGELOG;
4. zip con i percorsi del repo, senza `config/`, `secrets/`, `.db`, `gas/globals.gs`, più alla radice `deploy.sh` (copia di `scripts/deploy.sh`) e `rilascio.json` (`versione`, `messaggio` di commit, `elimina`, `riavvia`, `ferma_aste_prima`, `attesa_main`, `log_attesi`).

Deploy di uno zip, da `~/bots`: `Z=fantabasket-progettone-vX.Y.Z.zip; bash <(unzip -p $Z deploy.sh) $Z`. Controlla zip e versione, chiede conferma, fa il dump del database in `archivio/backup-deploy/`, scompatta, cancella i file tolti, riavvia controllando i log, fa commit e push e archivia gli zip oltre gli ultimi 5. Se un bot non parte non fa il commit e stampa come tornare indietro.

Per le modifiche strutturali (schema, migrazioni, conti di cap e roster) prima la prova generale su una copia del database di produzione: `scripts/prova_generale/README.md`.

Deploy da `~/bots`:

```bash
docker compose up --build -d bot-main                 # solo questo bot
docker compose up --build -d bot-main bot-aste-beta   # entrambi (sempre se cambia shared/)
docker compose logs -f --tail 100 bot-main            # log
```

---

## 12. Cose da sapere

**Da fare prima di giugno 2027:**

- **rinnovi normali**: sui contratti x1 e sugli ex rookie x0 a fine scala, max 2 a stagione, +¼ e +½ per eccesso, minimi da `tabella_minimo_contratto`;
- **draft**: le pick dell'anno diventano posizioni al draft (pick `scattata`, riga `draft` nel registro), righe `rookie` importate dagli admin, firma obbligatoria delle 1st.

**Ogni stagione:** `/trade_deadline` (scadenza dei diritti 2nd); il bot lo ricorda entrando nei rinnovi.

**10-day contract** (v5.2.0, `handlers/dieci_giorni.py`): contratto `tipo = '10day'`, importo 0, x1 della stagione, `scadenza_10day` = firma + 10 giorni; movimenti `10day_firma` e `10day_scadenza`; ruolo in `cambi_ruolo` (`post_firma`). `shared/cap.py` lo esclude da cap e slot (`SQL_NON_10DAY`), `ruoli_core.deficit_team` dai minimi; `get_roster_team(senza_10day=True)` per le liste di tagli, DPE, decadimenti e trade, e i controlli sul contratto lo rifiutano. Scadenza (`scaduto`, deciso con Luca il 14/10): passati i 10 giorni e convalidate (`lega_calcoli.stato = 'convalidata'`) tutte le giornate di `lega_giornate` iniziate durante il contratto (`giornate_aperte`); senza `lega_calcoli` vale il giorno dopo `al` alle 12 (Roma). Roster Typst: decimo campo `x` per chi sta fuori dai 15 (10-day, DPE che libera lo slot), sotto una `table.hline` più spessa. Foglio Roster: `dieci_giorni` nel payload, riga `10-DAY` sotto le DIS. (`gas/roster.gs`, righe sotto gli impatti pulite a ogni sync: `RIGHE_EXTRA_SOTTO`, default 2). Richieste in `richieste_admin` (tipo `10day`).

**Limiti noti:**

- La tabella `penalita` non è usata.
- `rookie.team_id` dei firmati non segue le trade (per loro conta il contratto); `rookie.pick_numero` e `pick.numero_scelta` non sono collegati.

**Doppio account admin/GM:** dal `/menu` si agisce sempre come GM. I poteri admin (`ca:`, `attadm:`, `decadm:`) stanno solo nel pannello.

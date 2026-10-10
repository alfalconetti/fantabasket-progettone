# Messaggio di migrazione — Fantabasket Progettone (stato v3.6.0, bot aste v50)

---

Ecosistema Fantabasket su server domestico Ubuntu. Bot aste v48 standalone SPENTO — bot-aste-beta del progettone è ora in produzione con token reale. Tutto gira su Docker Compose unificato.

**Stack:** Python 3.12 + python-telegram-bot 22.8 [job-queue] + PostgreSQL 16 + SQLite (bot aste beta) + Typst + aiohttp + pandas + lxml + html5lib

**Struttura:**
```
~/bots/
├── fantabasket-aste/          ← PRODUZIONE v48, congelato
└── fantabasket-progettone/
    ├── docker-compose.yml
    ├── config/                ← NON incluso nello zip, gestito sul server
    │   ├── globals.json
    │   ├── teams.json
    │   ├── settings.json
    │   ├── tabelle/
    │   └── loghi/
    ├── secrets/               ← anche yahoo_client_id, yahoo_client_secret, yahoo_router_token
    │   └── cifrati/           ← secrets.tar.gpg da scripts/cifra_secrets.sh (montata :ro nel bot main)
    ├── README.md              ← in inglese, linkato nella richiesta di accesso a Yahoo
    ├── docs/RECOVERY.md       ← guida UNICA backup e ripristino (dev + emergenza admin)
    ├── scripts/cifra_secrets.sh ← cifra secrets/ per il backup (da rilanciare a ogni modifica dei secrets)
    ├── shared/                ← regole condivise (ruoli), montata in entrambi i bot
    ├── fantabasket-aste-beta/
    ├── fantabasket-main/
    ├── gas-router/
    └── yahoo-router/          ← v3.0.0, OAuth2 Yahoo (in attesa di abilitazione)
```

**Regola assoluta:** zip mai include `config/`, `fantabasket-main/config/`, `.db`, `.db-shm`, `.db-wal`, `.env`. Gestiti solo sul server.

---

**globals.json — campi principali:**
```json
{
  "admin_ids": [ID_ADMIN_1, ID_ADMIN_2, ...],
  "channel_id": ID_CANALE_ASTE,
  "mercato_aperto": true,
  "fase": "offseason-fa",
  "admin_group_id": ID_GRUPPO_ADMIN,
  "log_channel_id": ID_CANALE_LOG_ASTE,
  "log_channel_id_main": ID_CANALE_LOG_MAIN,
  "stagione_corrente": "2026",
  "dev_id": ID_DEV,
  "main_channel_id": ID_CANALE_PRINCIPALE
}
```

**settings.json — valori critici:**
```json
{
  "cap_offseason": 165,
  "cap_regular":   150,
  "salary_floor":  115,
  "roster_max":    15,
  "roster_min_regular": 10,
  ...
}
```
⚠️ `cap_offseason` deve essere 165, `cap_regular` 150. File unico condiviso tra entrambi i bot.
⚠️ `settings_main.json` e `settings_aste.json` non esistono più — sostituiti da `settings.json`.

---

**Fasi della stagione** (con trattini, mai underscore):
```
regular-season-fa → regular-season-deadline → playoff →
offseason-break → offseason-rinnovi → offseason-draft →
offseason-rfa → offseason-fa → offseason-ruoli → (ricomincia)
```
Cambio fase via `/set_fase` (solo admin). Passaggio a `offseason-rinnovi` incrementa automaticamente `stagione_corrente`. `mercato_aperto` si aggiorna automaticamente al cambio fase.

**Comportamento per fase:**
- Trade aperte: `regular-season-fa`, `offseason-rinnovi`, `offseason-draft`, `offseason-rfa`, `offseason-fa`, `offseason-ruoli`
- FA aperta: `regular-season-fa`, `offseason-fa`, `offseason-ruoli`
- DPE disponibile: `offseason-rinnovi`, `offseason-draft`, `offseason-rfa`, `offseason-fa`, `offseason-ruoli`, `regular-season-fa`, `regular-season-deadline`
- DPE libera slot: tutte le fasi tranne `regular-season-deadline`
- Bref scraper: `regular-season-fa`, `regular-season-deadline`, `playoff`
- Check cap stagionale bot aste: solo fasi `offseason-*`
- Cap massimo consentito: 165M in `offseason-*` per tutti, 150M − `cap_penalizzato` altrimenti (`luxury_cap()` in settings main, `cap_limite()` + `penalita_cap()` in settings aste)
- Notifica ruoli post-trade: `regular-season-fa` (entro 48h) e `offseason-ruoli` (invito a /dichiarazione_ruoli)
- `offseason-ruoli`: dichiarazione ruoli aperta ai GM fino a `deadline_ruoli` (globals, impostata con /deadline_ruoli)
- A ogni cambio fase: annuncio sul canale principale (`testo_annuncio_fase()` in `admin_panel.py`); i testi specifici sono in `FASI_INDICAZIONI`, da tenere allineati al regolamento

---

**Bot aste beta** — v50 + pg_client.py. Cap/slot da PostgreSQL. FA list da PostgreSQL (esclude diritti 2nd non firmati, ordinata per fantamedia bref desc). Versione = ultima voce `## vNN` del suo `CHANGELOG.md` (v48). Niente backup propri da v49 (solo `/backup_ora` d'emergenza del DB aste). Config montata `:ro`. `cap_massimo()` alias di `cap_regular` (150M fisso), `cap_limite()` dinamico (165M offseason, 150M RS).

**Il DB del bot aste resta su SQLite per scelta** (decisione del 09/10/2026): così si può sempre tornare al bot aste standalone v48. Modifiche allo schema SQLite solo additive (nuove colonne con default, mai rinominare o togliere), così il DB resta leggibile dallo standalone.

`cap_slot_display()` in `utils.py` è PG-first — se PG non disponibile cade su fallback JSON (non dovrebbe mai succedere in produzione).

`check_slot_virtuale()` in `teams.py` passa sempre `stagione` a `get_roster_count()` per escludere giocatori con DPE attiva dal conteggio slot.

---

**Bot main (v1.4.17)**

**Principi critici:**
- Modifiche chirurgiche con `str_replace`, mai riscrivere file interi
- `update.effective_message` ovunque
- `@solo_privato` decorator su tutti i cmd tranne `/roster`, `/assets`, `/team_diff`
- `@richiede_fase(*fasi, msg=...)` per bloccare comandi fuori fase
- `allowed_updates` in `run_polling`: `["message","callback_query","edited_message","my_chat_member","chat_member","guest_message"]`
- `per_message=False` su tutti i ConversationHandler (NON usare `per_message=True`)
- `config/` montata `:rw` per bot-main (scrittura teams.json da `/my_team` e `/palette`)
- `config/` montata `:ro` per bot-aste-beta
- Fasi sempre con trattini
- Zip sempre senza config/ e file sensibili
- Syntax check `ast.parse` prima di ogni zip
- Versioning: patch con suffisso incrementale (v1.4.17, v1.4.18...), feature bump minor (v1.5.0), nuovo servizio bump major (v2.0.0); `vX.Y.Za` per docs/hotfix della stessa patch
- Ogni zip include comando deploy + git commit + git push origin main (vedi sezione deploy: si parte SEMPRE da `cd ~/bots`)
- **Ogni zip aggiorna SEMPRE `fantabasket-main/CHANGELOG.md`** con la voce `## vX.Y.Z (data)`: la versione mostrata dal bot all'avvio e in `/dev_version` è letta dall'ultima voce del CHANGELOG (v3.0.9). Senza voce nuova il bot mostra la versione precedente
- **Ogni patch che tocca il bot aste aggiorna ANCHE `fantabasket-aste-beta/CHANGELOG.md`** con una voce `## vNN — titolo` (numero successivo): da v48 la versione del bot aste è l'ultima voce del suo CHANGELOG. Nello zip il file si chiama `CHANGELOG_aste.md`
- **Parità GM/admin**: ogni azione che può fare un GM deve avere l'equivalente "per conto di" una squadra nel pannello admin (`_kb_admin_home`). Chi aggiunge un'azione GM aggiunge anche la voce admin
- **Admin che è anche GM**: nei flussi GM (/menu, comandi) agisce come GM, con le regole dei GM (es. `cambi_ruolo` modalità `cr:`); i poteri admin solo dal pannello (`ca:`, `attadm:`, `decadm:`)
- **Comandi di Telegram per fase**: `comandi.py` (`_fasi_comando`). Un nuovo comando GM legato a una fase va aggiunto lì, oltre che in `AZIONI_FASE` del menu
- Prima di ogni zip: `ast.parse` + `pyflakes` (cerca "undefined name"): i bug v3.0.2/v3.0.3 erano tutti nomi non definiti in rami poco usati
- Un solo file per modulo: niente copie con lo stesso nome in radice e in `handlers/` (in passato fix finiti sulla copia morta, v3.0.1). Gli import usano sempre `handlers.xxx`
- Prima di discutere → poi codice → poi zip: niente deploy di patch non discusse
- `/annulla` globale con `group=-1` pulisce `user_data` e termina qualsiasi ConversationHandler

**Handlers bot-main:**
- `menu.py` — `/menu` dinamico per fase con InlineKeyboard; Trade/Tagli/Rookie/DPE solo nelle fasi corrette; Assets sempre visibile; entry point `menu_trade_build` e `menu_trade_import` registrati nei ConversationHandler del trade
- `trade.py` — builder (2-4 squadre), import, bozze con bottoni inline, edit, annulla, rollback; `/bozze_trade` mostra InlineKeyboard con bottoni diretti all'edit per bozze e al riepilogo-voto per pending; label bozze: `BUF03-3` (prime 3 lettere nome + num team + bozza_num) o `ADM-4` per admin; `trade_ref` (`TRADE-2026-001`) assegnato prima di `_esegui_trade` per evitare NULL nelle transazioni; notifica GM post-trade include "comunica i ruoli" solo in `regular-season-fa`
- `trade_parser.py` — parser deterministico testo trade; lookup pick per `proprietario_orig` via `get_pick_by_orig_anno_round()` (davvero attivo solo da v3.0.1: prima il fix era sulla copia morta in radice); `by` facoltativo (`1st round pick 2028 Birra`); GM trovati anche per singola parola di `gm_nome`/nome squadra se univoca; verifica che pick e diritti ceduti siano posseduti OGGI dal cedente; errori non duplicati nelle trade a 2
- `tagli.py` — taglio con preview impatto, conferma, scrittura DB, annuncio canale; tagli 1x1 gratuiti bloccati quando esauriti
- `rookie.py` — attivazione diritti 2nd pick, GM in `FASI_TRADE_APERTE`, admin (`attadm:`) in qualsiasi fase; contratto SEMPRE dalla colonna "I anno" della rookie scale (`_slot_scala`, la scala parte dall'anno di firma), solo conferma; `esegui_attivazione()` unica transazione DB con `FOR UPDATE` e cap con `settings.cap_limite_team`; `_dopo_attivazione()` annuncio/avviso GM/ruolo RS/sync; bottone `scadi_diritti:<anno>` per la scadenza diritti (v3.0.6)
- `decadimento.py` — GM: richiesta → gruppo admin (Approva/Rifiuta, solo admin); admin diretto `decadm:`; `applica_decadimento()` comune; transazione tipo `decadimento`, scrittura atomica in `db.registra_decadimento`
- **Tipi di `transazioni`**: il CHECK in produzione NON coincideva con `schema.sql` (DB nato da uno schema più vecchio). Da v3.5.0 `migrate_db()` lo ricrea a ogni avvio con l'unione: `signed, traded, cut, renewed, expired, decadimento, decaduto, dpe_attivata, 10day_firma, 10day_scadenza, rookie_firma, rookie_diritti_scaduti, firma, taglio, trade, rookie, dpe`. Un tipo nuovo va aggiunto lì E in `schema.sql`. Verifica: `SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname LIKE 'transazioni_tipo%'`
- `comandi.py` (radice bot-main) — liste comandi Telegram per scope, filtrate per fase; `registra_comandi(bot)` all'avvio e in `_esegui_cambio_fase`
- `roster.py` — PNG via Typst subprocess per `/roster` e `/assets`; fuzzy match team via `get_team_by_query()`; roster sempre 15 righe (padding con righe vuote); giocatori con DPE mostrano importo barrato in rosso
- `palette.py` — `/palette` con anteprima PNG live
- `myteam.py` — modifica nome/colori team
- `team_diff.py` — variazioni roster tra date; fuzzy match team via `get_team_by_query()`
- `admin_panel.py` — pannello admin dinamico per fase (`_kb_admin_home`: Trade, Taglia, Attiva diritti, Decadimento, DPE, Ruoli squadre, Ruoli in sospeso, Cambi ruolo, Situazione cap); DPE admin diretta (team→giocatore→conferma→DB+canale); annuncio canale usa `_formatta_annuncio_canale()` (non `_testo_riepilogo`)
- `dpe.py` — `/dpe` GM: flusso richiesta→approvazione admin gruppo→DB+canale; `pre_deadline = (fase != "regular-season-deadline")`; DPE legata alla stagione corrente; `_importo_dpe()` unica funzione usata anche da `admin_panel.py`
- `tagli.py` — spalmatura >5M: rate per eccesso, eccedenza tolta dal fondo senza scendere sotto 1 (7x1 → 4-2-1)
- `posizioni.py` — posizioni eleggibili: `/import_posizioni_eleggibili` (CSV, anteprima, transazione unica), `/set_posizioni_eleggibili`, `/data_erminio`
- `ruoli.py` — dichiarazione ruoli in `offseason-ruoli` (bozze `ruoli_bozze`, import da testo, admin per altre squadre, `/deadline_ruoli`, job 10:00 e 17:00, report a fine fase)
- `ruoli_rs.py` — dichiarazioni post-trade/firma in RS (`ruoli_pendenti`, 48h, estrazione, regola 60 giorni)
- `cambi_ruolo.py` — `/cambio_ruolo`: ordinario (2/stagione), Erminio, Saedro (richiesta → gruppo admin, `job_fine_saedro`), forzato admin. Callback `cr:` = GM sulla propria squadra (anche se admin: niente forzato, Saedro su richiesta), `ca:` = admin da pannello. Tutto solo in `FASI_RUOLI_RS`
- `menu.py` — menu per fase: `AZIONI_FASE` (etichetta, callback, fasi) + `AZIONI_SEMPRE`
- `validators/ruoli.py` — involucro di `shared/ruoli_core.py` (`deficit_team` col `db._q` del main)
- **`shared/ruoli_core.py`** (radice del progetto, montato in `/app/shared` in bot main e bot aste) — UNICA implementazione delle regole dei ruoli: `RUOLI`, `FASI_RUOLI_RS`, `deficit_minimo`, `deficit_team`, `eleggibili`, `scelta_valida`, `ruolo_riacquisto`, `estrai_ruolo`, `registra_ruolo`. Ogni funzione riceve `q` (main: `database._q`, aste: `pg_client.q`). **Una modifica a `shared/` richiede il riavvio di entrambi i bot**
- `dev_player.py`, `dev.py`, `helpers.py` — invariati

**File principali bot-main:**
- `bot.py` — entry point; comandi GM: `build_trade`, `import_trade`, `bozze_trade`, `edit_trade`, `taglia`, `dpe`, `attiva_diritti`, `decadimento`, `my_team`, `palette`, `team_diff`, `annulla_trade`, `annulla`; comandi admin aggiuntivi: `admin_menu`, `set_fase`, `approva_trade`, `annulla_trade_admin`, `registra_firma`, `annulla_admin`, `settings`; comandi dev aggiuntivi: `dev*`, `job_status`, `broadcast`, `sync_sheets`, `backup`, `reboot`
- `teams.py` — `get_team_by_id`, `get_team_by_gm`, `get_all_teams`, `get_team_by_query` (fuzzy match su team_id → nome esatto → gm_nome esatto → prefix → difflib 0.6)
- `database.py` — `get_pick_by_orig_anno_round(proprietario_orig, anno, round)` per lookup pick nel trade parser; `get_roster_team()` joina tabella `dpe` e restituisce `importo` (DPE-adjusted), `importo_originale`, `ha_dpe`
- `scheduler.py` — backup UNICO e completo (vedi sezione Backup)
- `bref_scraper.py`, `utils.py`, `log_buffer.py` — invariati; `settings.py` + `cap_limite_team(team)`
- `assets.typ` / `roster.typ` — 15 righe fisse con padding vuoto; flag `VUOTO` per righe empty; DPE: nome in rosso scuro (`#C62828`), cella importo `~~orig~~ nuovo`; leggenda include `■ DPE` se presente

**Trade — architettura:**

Stati ConversationHandler:
`TRADE_N_SQUADRE, TRADE_SELEZIONA_SQUADRE, TRADE_ASSET_MENU, TRADE_ASSET_GIOCATORI, TRADE_ASSET_PICK, TRADE_ASSET_DIRITTI, TRADE_ASSEGNA_DEST, TRADE_RIEPILOGO, EDIT_MENU, EDIT_AGGIUNGI_TIPO, EDIT_AGGIUNGI_ITEM = range(11)`
`TRADE_NOTA = 11`, `TRADE_RIFIUTO_NOTA = 12`, `IMPORT_ATTENDI_TESTO = 20`

- `trade_ref` (`TRADE-2026-001`) assegnato PRIMA di chiamare `_esegui_trade()` — evita NULL nelle transazioni e notifiche GM
- Label bozze: `BUF03-3` = prime 3 lettere prima parola nome team + numero team zero-padded + bozza_num; `ADM-4` per bozze admin
- `/edit_trade N` — N è il bozza_num del GM (relativo al proprio team), non l'ID PG
- `/bozze_trade` — bottoni `✏️ BUF03-3` → edit diretto, `👀 TRADE-2026-022` → riepilogo con voto
- Annuncio canale: sempre via `_formatta_annuncio_canale()` (formato TRADE + importi), mai `_testo_riepilogo()` (formato bozza con bullet)
- Pick nel parser: lookup per `proprietario_orig` non per `proprietario_att`
- `_esegui_trade` e `_rollback_trade` gestiscono giocatori, pick E diritti (diritti fino a v3.0.4 non si spostavano). I diritti si spostano solo se attivi e posseduti dal cedente
- `_valida_rollback` controlla anche i diritti: se non sono nella squadra che li ha ricevuti, l'annullamento è bloccato
- Esecuzione e rollback **atomici** (v3.4.2, `_scrivi_trade`): approvazione + spostamenti + transazioni + stato in un'unica transazione DB, con verifica di ogni asset; se qualcosa non torna → `TradeNonEseguibile`, nessuna modifica

**DPE:**
- Fasi disponibili: `offseason-rinnovi` → `regular-season-deadline` (tutte e 6)
- `pre_deadline = (fase != "regular-season-deadline")` — libera slot in tutte le fasi tranne post-deadline
- Post-deadline: decurtazione 25% + nessuno slot liberato + cambio ruolo `dpe_extra` gratuito verso il ruolo dell'infortunato (v3.6.0). Pre/post si decide all'approvazione
- `get_roster_count()` nel bot aste riceve sempre `stagione` per escludere giocatori con DPE dal conteggio slot
- Tabella `dpe`: `(id, giocatore_id, team_id, stagione, importo_originale, importo_dpe, pre_deadline, approvata_da, timestamp)`

**Roster/Assets PNG (Typst):**
- Flag: `N`=normale, `A`=RFA, `R0-R3`=rookie anno I-IV, `VUOTO`=riga padding
- Sempre 15 righe: padding con flag `VUOTO` per slot vuoti
- DPE: nome in rosso scuro, cella importo con originale barrato e nuovo importo
- Leggenda: rookie, RFA, DPE (mostrate solo se presenti)
- `/roster` e `/assets` accettano nome GM o nome squadra (fuzzy) oltre a team_id

**Regole del regolamento verificate/decise (v3.0.x):**
- DPE: contratto − ceil(25%) → 5→3, 9→6, 10→7 (esempio Klay del regolamento). Fino a v3.0.4 era ceil(75%); Mark Williams corretto a mano (9→6)
- Stepien: finestre di **4** anni (`stepien_anni`, modifica votata). Anno coperto se la propria 1st di quell'anno è posseduta oggi o, se già scattata, usata dalla squadra stessa. Pick protette cedute = cedute. Anni ≤2026 coperti d'ufficio (nessun dato). Al deploy v3.0.6 tutte le 24 squadre erano in regola
- Cap: offseason 165 per TUTTI (penalità ignorata); regular season 150 − `cap_penalizzato`. Bot aste: `settings.penalita_cap(team)` vale 0 in offseason. `check_cap_stagionale` invece conta la penalità (proietta la RS)
- Salary floor 115: in stagione le trade non possono portare sotto il floor (o farci scendere ancora)
- Diritti 2nd: scadono quelli del draft `stagione_corrente − 1` il giorno `trade_deadline − 10`. Avviso informativo 3 giorni prima, poi avviso con bottone ogni giorno fino a conferma admin; conferma → `diritti_scaduti`, annuncio gruppo admin + canale main, sync scelte
- `stagione_corrente = "2026"` = stagione 2026-27; `anno_draft` = anno del draft (giugno)

**PostgreSQL schema — novità:**
```sql
-- pick lookup per proprietario originale (v2.0.33)
-- get_pick_by_orig_anno_round(proprietario_orig, anno, round) in database.py

-- tagli gratuiti fittizi pre-bot (inserimento manuale):
INSERT INTO transazioni (tipo, giocatore_id, team_id_da, stagione, gratuito, note)
SELECT 'cut', MIN(id), 'teamXX', '2026', TRUE, 'Taglio gratuito registrato manualmente — avvenuto pre-bot'
FROM giocatori;
-- giocatore_id NOT NULL — usare MIN(id) come placeholder
```

**Operazioni manuali sul DB:**
```sql
-- nota trade (v2.0.25)
ALTER TABLE trade ADD COLUMN IF NOT EXISTS nota_gm TEXT;
```

**deploy:** gli zip vengono scaricati in `~/bots/`; il comando parte SEMPRE da `cd ~/bots`. Nello zip i file stanno alla radice; nomi ambigui con prefisso (`validators_trade.py`, `aste_admin.py`, ...)
```bash
cd ~/bots && \
unzip -p ~/bots/fantabasket-progettone-vX.Y.Z.zip NOMEFILE.py > ~/bots/fantabasket-progettone/fantabasket-main/handlers/NOMEFILE.py && \
unzip -p ~/bots/fantabasket-progettone-vX.Y.Z.zip ALTRO.py > ~/bots/fantabasket-progettone/fantabasket-main/ALTRO.py && \
cd ~/bots/fantabasket-progettone && docker compose up --build -d bot-main && \
git add -A && git commit -m "vX.Y.Z: descrizione" && git push origin main
```
- Nuove cartelle/servizi: `unzip -o ~/bots/zip -d ~/bots/fantabasket-progettone/`
- Bot aste: rebuild `bot-aste-beta`; entrambi: `docker compose up --build -d bot-main bot-aste-beta`
- File in `shared/`: `unzip -p ... > ~/bots/fantabasket-progettone/shared/...` e poi riavvio di ENTRAMBI i bot (`docker compose up --build -d bot-main bot-aste-beta`)
- Variabili sensibili non-secret (URL, ID) in `secrets/*.env` via `env_file`: `yahoo_router.env` (ID leghe), `bot_main.env` (HEALTHCHECK_URL). Mai valori sensibili nel compose o nei .md
- Secrets modificati: `docker compose up -d --force-recreate <servizio>` (i secrets sono bind-mount per file: editor come vi creano un file nuovo e il container continua a vedere il vecchio)
- Script Python nel container: chiamare `db.init_db()` prima di usare il DB (il pool non è inizializzato fuori dal bot)
- psql: `docker compose exec postgres psql -U fantabasket -d fantabasket -c "..."`

**Richieste agli admin e trade (v3.6.0):**
- `richieste_admin (tipo, chiave=giocatore_id, team_id, stato)`, indice unico sulle aperte. `db.apri_richiesta` alla richiesta del GM; `db.chiudi_richiesta` in Approva/Rifiuta → `'ok'` (procedi), `'gestita'` (già decisa: non fare niente), `'nessuna'` (bottoni di prima della v3.6.0: procedi). Nuove richieste agli admin vanno fatte così
- Trade: ogni cambio di stato passa da `db.cambia_stato_trade(id, da=(...), a=...)` (atomico). Stati: bozza → proposta → in_approvazione → approvata, oppure rifiutata_gm / rifiutata_admin / annullata. Etichette in `_STATI` (trade.py)
- `/my_trades`: `db.get_trade_team`, `db.clona_trade_in_bozza`, callback `mt:l`, `mt:v|r|c:<id>`
- CHECK dei tipi: `_allinea_check(tabella, valori)` in `migrate_db()` per `transazioni` e `cambi_ruolo`. Un tipo nuovo va aggiunto lì e in `schema.sql`
- Fantamedia nel roster: `db.stagione_fantamedia()` (stagione bref = anno di fine, cioè `stagione_corrente + 1`, se ≥50% dei giocatori sotto contratto ce l'ha) e `db.fantamedie(gids, stagione)`; 9° campo del payload Typst, `fm_label` in input

**Backup (v3.5.0):**
- Un solo backup, generato dal bot main, sempre completo: `db/fantabasket.sql` (`pg_dump --clean --if-exists --no-owner`), `db/aste.db` (copia coerente: `_snapshot_aste` copia -wal e DB, `integrity_check`, API di backup sqlite → un solo file; fino a 3 tentativi), tutta `config/`, `secrets.tar.gpg` se presente, `MANIFEST.txt`. Canale log 00:00 e 12:00 e allo spegnimento, gruppo admin domenica 00:30, `/backup` (dev)
- Secrets: `./scripts/cifra_secrets.sh` (gpg AES256 simmetrico, passphrase nel password manager) → `secrets/cifrati/secrets.tar.gpg`, montata `:ro` nel bot main come `/secrets_cifrati`. Il bot non vede mai i secrets in chiaro. **Rilanciare lo script dopo ogni modifica a `secrets/`**: la didascalia del backup mostra la data dei secrets inclusi
- Link alla guida nella didascalia di ogni backup: chiave `repo_url` in `config/globals.json` (v3.5.0b)
- Ripristino e emergenza: `docs/RECOVERY.md` (unica guida; le vecchie DEV_RECOVERY/emergency_recovery eliminate)
- Il bot aste non manda più backup periodici (v49)

**Bug noti aperti:**
- Votazione GM non testata end-to-end
- Guest mode in attesa supporto completo ptb per `InputRichMessageContent`

---

**Yahoo Fantasy API (stato al 06/10/2026):**
- Da luglio 2026 Yahoo richiede un'approvazione separata (contratto DocuSign) per la Fantasy API: senza, ogni chiamata dà 403 "This application is not authorized to perform this action", anche con app e token validi
- `yahoo-router` (v3.0.0) pronto: FastAPI interno, OAuth2 flusso `oob`, refresh automatico, token in volume `yahoo_data:/data`, leghe in `YAHOO_LEAGUE_IDS` (24 squadre su due leghe, la seconda contiene anche account admin da escludere nel mapping)
- `docker compose exec -it yahoo-router python3 cli.py auth` → bootstrap OAuth; `cli.py teams` → collaudo + elenco squadre per il mapping `teamXX ↔ lega/team Yahoo`
- Sul portale developer ci sono due app: in uso quella NUOVA (creata il 05/10/2026), la vecchia va tenuta (non cancellare). Credenziali solo in `secrets/`
- Richiesta di accesso inviata su sports.yahoo.com/developer/access/ (Client ID della nuova app, README linkato). Tempi riportati: da 1 settimana a 2 mesi. Le email non sono affidabili: verificare con `cli.py teams`. Prima di firmare il contratto leggere le clausole su conservazione/visualizzazione dati
- NBA.com (cdn.nba.com) bloccato da Akamai sulla rete di casa (403 anche da browser)

**Fonti dati senza Yahoo (piano B):**
- Statistiche di giornata (Loucabot): box score Basketball-Reference `/boxscores/YYYYMMDD0HOME.html`, tabella `box-<TEAM>-game-basic` (titolari/riserve, DNP). Testato dal server. Niente live
- Posizioni eleggibili (ruoli): import manuale da testo copiato dalle pagine Yahoo (lista giocatori `status=T`, pagine da 25 con `count=` offset)
- Titolari: oggi solo su Yahoo → proposta da portare in riunione di lega (dichiararli anche su Telegram)
- Status infortuni: Yahoo fa fede; eventuale supporto dal report infortuni NBA

---

**Roadmap:**

**v2.x — GAS Router + Google Sheets** ✅ completata (foglio scelte in v2.1.0)

**v3.x — Yahoo router + Ruoli (anticipati rispetto a Loucabot)**
- `yahoo-router` ✅ (v3.0.0, in attesa di abilitazione Yahoo)
- Colonna `posizioni` su `giocatori` + import manuale `/import_posizioni` da testo Yahoo (poi fetch giornaliero se Yahoo si sblocca)
- Tabella `cambi_ruolo` e vista `ruolo_attuale` già presenti nello schema
- Dichiarazione ruoli post-trade/post-firma entro 48h (GM dichiara, admin approva), cambi ordinari 2/stagione, Saedro, forzati admin, Erminio, regola 60 giorni, minimi 4G/4F/2C
- Fase `offseason-ruoli`; DPE post-deadline: cambio ruolo aggiuntivo gratuito

**v4.x — Loucabot**
- Calcolo punteggi partite + penalità automatiche (fonte: Yahoo se abilitato, altrimenti Basketball-Reference)

**v5.x — IPanchinariBot**

**Pending fuori roadmap:**
- Rinnovo rookie (offseason, flusso separato dall'attivazione diritti)

**Posizioni e ruoli (v3.1.0):**
- `posizioni_eleggibili` = event log delle posizioni Yahoo (set completo, es. `PG,SG`), nuova riga solo se il set cambia → vista `posizioni_attuali`. Le aggiunte segnalate nell'anteprima servono per la Erminio rule (2 settimane dalla data della riga)
- `cambi_ruolo` + vista `ruolo_attuale` = event log dei ruoli dichiarati (già nello schema)
- Import: CSV `yahoo_id;nome;team;posizioni` esportato dalle pagine giocatori Yahoo, poi `/import_posizioni_eleggibili`; correzioni puntuali con `/set_posizioni_eleggibili` (fonte `manuale`). Primo import: 713 righe, 628 abbinate, tutti i sotto contratto coperti
- `giocatori.yahoo_id` + `nome_yahoo` salvati dall'import: dai successivi l'abbinamento è per ID (i nomi accorciati della lista Yahoo, "K. Caldwell-Pope", non vengono salvati)
- **Dichiarazione ruoli (v3.2.0, `handlers/ruoli.py`)**: ogni stagione da capo, solo PG/SG/SF/PF/C tra le eleggibili; bozze in `ruoli_bozze`, ufficiali con Conferma → `cambi_ruolo` (`iniziale` / `forzato_admin`). Conferma parziale permessa. Vincoli 4G/4F/2C: avviso in offseason, BLOCCO previsto per i cambi ruolo in regular season (da implementare). Import da testo con match sul proprio roster. Admin: /admin_menu → Ruoli squadre. Job 10:00 promemoria deadline, 17:00 report canale log, report mancanti al gruppo admin a fine fase
- **Ruoli in RS (v3.3.0, `handlers/ruoli_rs.py`)**: dichiarazioni in sospeso (`ruoli_pendenti`) aperte da trade, attivazione diritti e /registra_firma solo in `FASI_RUOLI_RS`; 48h poi estrazione (job ogni 15'); regola dei 60 giorni; admin dichiarano da /admin_menu → ⏳ Ruoli in sospeso; annunci sul canale principale. Vincoli 4G/4F/2C: `validators/ruoli.py` (`deficit_minimo` = 0 se esiste un'assegnazione valida; fissi = ruoli ufficiali, flessibili = senza ruolo), usati da trade (RS) e dichiarazioni
- **Cambi ruolo (v3.3.1, `handlers/cambi_ruolo.py`)**: ordinari max 2/stagione (contatore = eventi `ordinario` della squadra nella stagione, su /roster e foglio); Erminio gratuito entro 14 giorni da `COALESCE(data_yahoo, timestamp)` dell'ultima riga posizioni (data_yahoo con /data_erminio); Saedro 10 giorni una volta a stagione (evento con `scadenza` + `ruolo_ripristino`, ritorno via job `job_fine_saedro`), richiesta GM → approvazione nel gruppo admin, admin anche diretta; forzato_admin non conta. Vincoli bloccanti tranne per i forzati
- **Bot aste (v3.4.0 / aste v46)**: FA in RS → anni, poi ruolo (stesse regole via `shared/`); 48h senza risposta → 3 anni + ruolo estratto; ruolo nell'annuncio sul canale principale
- Prossimi passi: v3.7 Basketball-Reference (nuovi giocatori, date di nascita, medie sul foglio), Mini App

**@qf_bot (vX.x — dipende da guest mode PTB)**
- Bot pubblico per roster e info lega

---

**Stato attuale: v3.6.0**

Novità v2.1.19–v3.0.7 (sessione 04-06/10/2026):
- **v2.1.19** — `/attiva_diritti` propone il contratto della rookie scale (anno I) e chiede solo conferma
- **v3.0.0** — nuovo servizio `yahoo-router` (OAuth2, `/yahoo/teams`)
- **v3.0.0a** — README del repo (in inglese, per la richiesta di accesso Yahoo)
- **v3.0.1** — trade parser: pick per proprietario originale (davvero), `by` facoltativo, GM per singola parola, controllo possesso pick
- **v3.0.2** — fix nomi non definiti: `db` in admin_panel (import trade, `/registra_firma`), `calcola_impatto_taglio`, `_ordinal` in gas_client
- **v3.0.3** — rimossa chiamata doppia/errata a `_esegui_trade` in `cb_ufficializza`
- **v3.0.4** — i diritti si scambiano davvero; fix rollback diritti (confrontava `rookie.id` con `giocatore_id`); controllo possesso diritti nel parser. Dati corretti a mano: TRADE-2026-019 (Mitchell) e 029 (Powell/Miller)
- **v3.0.5** — DPE = contratto − ceil(25%), calcolo centralizzato
- **v3.0.6** — Stepien riscritta; scadenza diritti 2nd funzionante (`stagione − 1`, deadline − 10, bottone con handler)
- **v3.0.7** — penalità cap solo in RS (165 per tutti in offseason) in entrambi i bot; salary floor nelle trade; spalmatura 7x1; `/autoslot` senza crash; riga "Cap libero in RS" del bot aste; rimosse copie morte `trade_parser.py`/`admin_panel.py`/`dpe.py` in radice; README aggiornato
- **v3.0.8** — ID leghe Yahoo fuori dal compose (`secrets/yahoo_router.env`), cronologia git ripulita
- **v3.0.9** — versione letta dal CHANGELOG; Stepien unificata (trade, foglio, /assets con tag STEPIEN); rimosso `roster.py` doppio
- **v3.1.0–v3.1.1** — posizioni eleggibili (event log `posizioni_eleggibili`, `giocatori.yahoo_id`), import da CSV
- **v3.2.0** — fase `offseason-ruoli`, dichiarazione ruoli (bozze, import da testo, admin, deadline, report), `/set_posizioni_eleggibili`
- **v3.2.1** — annuncio di fase sul canale principale; healthcheck in `secrets/bot_main.env`; job GAS sempre attivi
- **v3.2.2** — ruoli e posizioni in /roster e /assets, ordinamento per ruolo
- **v3.2.3–v3.2.4** — menu dinamico per fase (`AZIONI_FASE`), foglio ordinato per ruolo, decadimento nel menu, fix bottone Rookie
- **v3.2.5** — `query.get_bot()` (annunci di fase, log, DPE admin non partivano); a capo nei messaggi DPE admin
- **v3.2.6** — sync di tutti i roster dopo la conferma ruoli
- **v3.3.0** — ruoli in RS: dichiarazioni post-trade/firma (48h, estrazione, regola 60 giorni), vincoli ruoli nelle trade; fix `/registra_firma`
- **v3.3.1–v3.3.3** — cambi ruolo (ordinari con contatore, Erminio, Saedro, forzati admin), `/data_erminio`; Erminio esclusivo, conferma per l'ordinario
- **v3.3.4** — guide GM e admin riscritte; indicazioni di fase aggiornate
- **v3.3.5** — diritti in fondo nell'annuncio trade
- **v3.4.0** — modulo condiviso `shared/ruoli_core.py`; bot aste: ruolo insieme agli anni per le FA in RS (aste v46)
- **v3.4.1** — report vincoli ruoli al passaggio in regular season
- **v3.4.2** — trade: esecuzione e rollback atomici, verifica degli asset, diritti attivi nel rollback
- **v3.4.3** — fix `&lt;numero_bozza&gt;` in /edit_trade e /reset_rfa
- **v3.4.4** — trade builder: contratti `impxanni` nella selezione e nei riepiloghi, avviso offseason sopra i 150M
- **v3.4.5** — contratto della rookie scale nei bottoni dei diritti; versione del bot aste dal suo CHANGELOG (v48)
- **v3.4.6** — hotfix: trade builder admin con tutti gli stati del builder GM (diritti, destinazioni, nota, modifica)
- **v3.5.0** — cambi ruolo GM/admin separati (`cr:`/`ca:`) e solo in RS/playoff; comandi Telegram per fase (`comandi.py`); pannello admin per fase con Attiva diritti, Decadimento diretto e Situazione cap; fix decadimento (tipo `decaduto`, atomico, solo admin approvano); cap per fase in /attiva_diritti; backup unico con secrets cifrati e `docs/RECOVERY.md` (aste v49)
- **v3.5.0a/b** — `cifra_secrets.sh` senza gpg-agent; link alla guida di ripristino nei backup (`repo_url` in globals.json)
- **v3.6.0** — `/my_trades`; stati delle trade atomici; `richieste_admin` (DPE, Saedro, decadimento: una richiesta aperta, decisione unica); DPE valutata all'approvazione + cambio ruolo Extra DPE post-deadline; ruolo automatico per i monoruolo (main e aste v50); colonna FM nel roster; CHECK dei tipi allineati per unione; penalità col meno nel foglio

Novità v2.0.31–v2.0.38:
- **v2.0.31** — DPE disponibile in tutte e 6 le fasi (da offseason-rinnovi a regular-season-deadline); admin menu DPE diretta; `pre_deadline = (fase != "regular-season-deadline")`
- **v2.0.32** — annuncio canale DPE con effetto corretto; `get_roster_team()` joina tabella dpe; roster/assets PNG con importo DPE barrato in rosso; `_build_giocatori_str` aggiunge 5° campo `importo_orig`
- **v2.0.33** — roster/assets: sempre 15 righe fisse con padding; fix lookup pick per `proprietario_orig` in trade_parser; `get_pick_by_orig_anno_round()` in database.py
- **v2.0.34** — bot aste: `check_slot_virtuale()` passa `stagione` a `get_roster_count()` — fix DPE slot
- **v2.0.35** — fix annuncio canale import trade: usa `_formatta_annuncio_canale()` invece di `_testo_riepilogo()`
- **v2.0.36** — label bozza unificata `BUF03-3`/`ADM-4`; rimossi ID interni visibili all'utente; `proposta_da` mostra nome squadra
- **v2.0.37** — `trade_ref` passato a `_esegui_trade()` (fix NULL in transazioni/notifiche); `/bozze_trade` con bottoni inline edit+voto; notifica ruoli post-trade solo in `regular-season-fa`; comandi bot completi (`edit_trade`, `registra_firma`, `annulla_admin`, `sync_sheets`)
- **v2.0.38** — `get_team_by_query()` in teams.py (fuzzy match su team_id/nome/gm_nome); `/roster`, `/assets`, `/team_diff` accettano nome GM o squadra
- **v2.0.39** — fix palette assets: `_genera_assets_png` usava `colore` (campo obsoleto) invece di `colore_header` per il calcolo del footer color
- **v2.0.40** — pick assets inline (squadra originaria sulla stessa riga); fix definitivo palette assets; rimosso stroke (illeggibile in Typst)
- **v2.0.41** — badge bianco selettivo su rookie/RFA/DPE con contrasto WCAG insufficiente; calcolo per riga specifica del giocatore
- **v2.0.41a** — `_text_on_muted()` con scala di grigi garantendo ratio ≥ 2.5
- **v2.0.42** — `tagli_usati` da DB in tempo reale; `tagli_usati`/`cambi_usati` passati ad assets; rimossi default hardcodati da `sys.inputs` in Typst
- **v2.1.0** — foglio Scelte GAS: pick + diritti + Stepien + colori division; `globals.gs`; `divisions.json` in config/; endpoint `/gas/scelte`
- **v2.1.1** — `docker-compose.yml` con `gas_scelte_url`; nomi sensibili fuori da GAS
- **v2.1.2** — fix picks proprie, ordinale diritti, stile celle Scelte, minimo 4 righe per team
- **v2.1.3** — fix DPE in trade validator: slot e cap entrambi corretti
- **v2.1.4** — fix `NameError: trade_id` in `cmd_annulla_trade_admin`
- **v2.1.5** — fix reset alignment dopo clearFormat in scelte.gs
- **v2.1.6** — fix nomi GM colonna B e formato ordinale diritti
- **v2.1.7** — `sync_scelte()` in tutti i `sync_after_*`, sync dopo rollback trade
- **v2.1.8** — fix sync mancante dopo esecuzione trade (`_esegui_trade`)
- **v2.1.10** — SALARY CAP con penalità in roster GAS, DPE in rosso sotto tagliati, `get_dpe_attive_team()`
- **v2.1.11** — `/guida` e `/guida_admin`, comandi suggeriti con scope corretto
- **v2.1.12** — fix `NameError tm/team` in `_build_team_payload`
- **v2.1.13** — fix `globals.gs` struttura corretta; DPE escluse dalle 15 righe GAS
- **v2.1.14** — rookie scale colonne AX-BA in foglio Roster GAS
- **v2.1.15** — fix anni rookie scale usa stagione corrente
- **v2.1.16** — `--root /` in Typst per accesso loghi
- **v2.1.17** — fix notifica decadimento al gruppo admin; SALARY CAP penalità sempre negativa
- **v2.1.18** — coda `gas_sync_queue` PG: bot aste accoda firme, bot main sincronizza fogli ogni 60s

---

## Esportazione per nuova sessione

```bash
cd ~/bots/fantabasket-progettone && \
zip -r ~/fantabasket-progettone-export-$(date +%Y%m%d).zip \
  fantabasket-main/ \
  fantabasket-aste-beta/ \
  gas/ \
  gas-router/ \
  yahoo-router/ \
  shared/ \
  docs/ \
  scripts/ \
  docker-compose.yml \
  README.md \
  --exclude "**/__pycache__/*" \
  --exclude "**/*.pyc" \
  --exclude "**/*.db" \
  --exclude "secrets/*" \
  --exclude "config/*" \
  --exclude "gas/globals.gs" \
  --exclude "gas/.clasp.json" \
  --exclude "fantabasket-main/config/*" \
  --exclude "fantabasket-aste-beta/config/*"
```

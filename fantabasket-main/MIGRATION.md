# Messaggio di migrazione — Fantabasket Progettone (stato v1.4.17)

---

Ecosistema Fantabasket su M910q Ubuntu (alfalconetti@ubuntum910q). Bot aste v48 in produzione standalone, mai toccare. Progettone in testing attivo su Docker Compose separato.

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
    │   ├── settings_main.json
    │   ├── settings_aste.json
    │   ├── tabelle/
    │   └── loghi/
    ├── secrets/
    ├── fantabasket-aste-beta/
    └── fantabasket-main/
```

**Regola assoluta:** zip mai include `config/`, `fantabasket-main/config/`, `.db`, `.db-shm`, `.db-wal`, `.env`. Gestiti solo sul server.

---

**globals.json attuale:**
```json
{
  "admin_ids": [ID_ADMIN,ID_ADMIN,ID_ADMIN,ID_ADMIN,ID_ADMIN],
  "channel_id": -ID_CANALE,
  "mercato_aperto": true,
  "fase": "offseason-fa",
  "admin_group_id": -ID_CANALE,
  "log_channel_id": -ID_CANALE,
  "log_channel_id_main": -100XXXXXXXXXX,
  "stagione_corrente": "2026",
  "dev_id": ID_ADMIN,
  "main_channel_id": -ID_CANALE
}
```

**settings_aste.json — valori critici:**
```json
{
  "cap_offseason": 165,
  "cap_massimo_offseason": 165,
  "cap_regular": 150,
  ...
}
```
⚠️ `cap_offseason` e `cap_massimo_offseason` devono essere 165, non 150.

---

**Fasi della stagione** (con trattini, mai underscore):
```
regular-season-fa → regular-season-deadline → playoff →
offseason-break → offseason-rinnovi → offseason-draft →
offseason-rfa → offseason-fa → (ricomincia)
```
Cambio fase via `/set_fase` (solo admin). Passaggio a `offseason-rinnovi` incrementa automaticamente `stagione_corrente`. `mercato_aperto` si aggiorna automaticamente al cambio fase.

**Comportamento per fase:**
- Trade aperte: `regular-season-fa`, `offseason-rinnovi`, `offseason-draft`, `offseason-rfa`, `offseason-fa`
- FA aperta: `regular-season-fa`, `offseason-fa`
- DPE disponibile: `regular-season-fa`, `regular-season-deadline`
- Bref scraper: `regular-season-fa`, `regular-season-deadline`, `playoff`
- Check cap stagionale bot aste: solo fasi `offseason-*`
- Cap massimo consentito: 165M in `offseason-*`, 150M altrimenti (`luxury_cap()` in settings main, `cap_limite()` in settings aste)

---

**Bot aste beta** — v48 + pg_client.py. Cap/slot da PostgreSQL. FA list da PostgreSQL (esclude diritti 2nd non firmati, ordinata per fantamedia bref desc). `BOT_VERSION = "beta-1"`. Config montata `:ro`. `cap_massimo()` sempre 150M (fisso per calcoli interni), `cap_limite()` dinamico 165M in offseason.

`cap_slot_display()` in `utils.py` è PG-first — se PG non disponibile cade su fallback JSON (non dovrebbe mai succedere in produzione).

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
- Versioning: patch con suffisso incrementale (v1.4.17, v1.4.18...), feature bump minor (v1.5.0), nuovo servizio bump major (v2.0.0)
- Ogni zip include comando deploy + git commit + git push origin main
- Zip sempre cumulativi con tutti i file modificati dall'inizio sessione
- `/annulla` globale con `group=-1` pulisce `user_data` e termina qualsiasi ConversationHandler

**Handlers bot-main:**
- `menu.py` — `/menu` dinamico per fase con InlineKeyboard; Trade/Tagli/Rookie/DPE solo nelle fasi corrette; Assets sempre visibile; entry point `menu_trade_build` e `menu_trade_import` registrati nei ConversationHandler del trade
- `trade.py` — builder (2-4 squadre), import, bozze con bottoni (GM ↔ GM), edit, annulla, rollback; `/bozze_trade` mostra InlineKeyboard con GM coinvolti
- `trade_parser.py` — parser deterministico testo trade
- `tagli.py` — taglio con preview impatto, conferma, scrittura DB, annuncio canale; tagli 1x1 gratuiti bloccati quando esauriti (no forzato)
- `rookie.py` — attivazione diritti 2nd pick, aperto a tutte `FASI_TRADE_APERTE`, annuncio canale
- `roster.py` — PNG via Typst subprocess per `/roster` e `/assets`; colori testo calcolati in Python (WCAG luminanza) e passati come `--input`; `_footer_color()` simula `darken(20%)` quando `colore_sezione` non impostato
- `palette.py` — `/palette` con anteprima PNG live; `cb_pal_riprova` e `cb_pal_back` disabilitano bottoni vecchio messaggio; `/annulla` e timeout gestiti; warning colori scuri WCAG
- `myteam.py` — modifica nome/colori team
- `team_diff.py` — variazioni roster tra date
- `admin_panel.py` — pannello admin con `/set_fase` keyboard fasi inline; controllo cap con riepilogo per team; DPE admin diretta (team→giocatore→conferma→DB+canale); annulla trade con lista bottoni+conferma; accountability admin "Nome (@tag)" su tutti i messaggi canale
- `dpe.py` — `/dpe` GM: flusso richiesta→approvazione admin gruppo→DB+canale; `pre_deadline` libera slot; DPE legata alla stagione corrente (torna normale alla successiva)
- `dev_player.py` — `/dev_player <nome>` con edit bottoni
- `dev.py` — `/dev`, `/dev_version`, `/dev_log`, `/dev_trade`, `/dev_pg`, `/dev_roster`, `/job_status`, `/broadcast`
- `helpers.py` — `log_job_error(context, job_name, exc)` logga eccezioni job su `log_channel_id_main` + dev; `log_warn()` per warning espliciti

**File principali bot-main:**
- `bot.py` — entry point, `post_stop`, `post_init`, `post_shutdown` (backup), job queue; `migrate_db()` chiamata all'avvio; `/annulla` globale con `group=-1`; Healthcheck via `HEALTHCHECK_URL` env var (ping ogni 5 min)
- `scheduler.py` — backup pg_dump+SQLite giornaliero/settimanale/shutdown, bref scraper job; errori wrappati con `log_job_error`
- `bref_scraper.py` — scraping basketball-reference, append su `bref_stats`; gira solo in `regular-season-fa`, `regular-season-deadline`, `playoff`
- `utils.py` — ROME, format_dt, normalizza, cognome
- `log_buffer.py` — buffer in memoria per `/dev_log`
- `settings.py` — get(), load_globals(), fase(), `luxury_cap()` (165M offseason, 150M altrimenti), `cap_massimo()`, richiede_fase(), solo_privato, FASI_TRADE_APERTE
- `database.py` — tutte le query PG; `migrate_db()` crea tabella `dpe` se non esiste; `get_dpe_team()`, `get_dpe_attiva()`, `inserisci_dpe()`; `cap_occupato_team()` include DPE
- `teams.py` — get_team_by_id, get_team_by_gm, get_all_teams
- `assets.typ` / `roster.typ` — template Typst; colori testo adattivi via parametri `--input` (`text_on_riga1/2`, `text_on_sezione`, `text_on_footer`, `text_on_pick`, `text_on_dir`); footer usa `c_dark` se `colore_sezione` non impostato, `c_sezione` se personalizzato; leggenda: bullet colorato + label con `text_on(c_sezione)`
- `Dockerfile` — include `fonts-liberation` per Liberation Sans

**Trade — architettura:**

Stati ConversationHandler (range 11):
`TRADE_N_SQUADRE, TRADE_SELEZIONA_SQUADRE, TRADE_ASSET_MENU, TRADE_ASSET_GIOCATORI, TRADE_ASSET_PICK, TRADE_ASSET_DIRITTI, TRADE_ASSEGNA_DEST, TRADE_RIEPILOGO, EDIT_MENU, EDIT_AGGIUNGI_TIPO, EDIT_AGGIUNGI_ITEM`
`IMPORT_ATTENDI_TESTO = 20`
`PAL_MENU, PAL_ATTENDI_HEX, PAL_ANTEPRIMA = range(30, 33)`

Entry points aggiuntivi: `CallbackQueryHandler(cmd_trade, pattern=r"^menu_trade_build$")` e `CallbackQueryHandler(cmd_import, pattern=r"^menu_trade_import$")`

- `trade_ref` (TRADE-2026-001) assegnato SOLO all'approvazione admin, mai prima
- Trade 2 squadre: assegnazione automatica destinatari
- Trade 3+ squadre: flusso item per item `TRADE_ASSEGNA_DEST`
- Elimina/Modifica bozza funzionanti incluso post-modifica (flag `edit_from_riepilogo`)
- Admin può importare qualsiasi trade (check "non ti coinvolge" saltato per admin)
- `get_trade_count_approvate` usa MAX(SPLIT_PART) per evitare UniqueViolation
- Annuncio canale: 2 squadre solo "cede", 3+ squadre "cede" + "riceve"; accountability "Nome (@tag)"
- `/annulla_trade_admin TRADE-2026-XXX` con validazione compatibilità roster prima del rollback
- `/bozze_trade` mostra InlineKeyboard con label "GM1 ↔ GM2", click apre riepilogo con bottoni azione
- Keyboard trade non valida mostra solo "Modifica" ed "Elimina" — mai "Proponi/Ufficializza"

**Tagli:**
- Impatto taglio: tabella fissa ≤5M, percentuali sopra cappate a max 3 anni
- Tagli 1Mx1 gratuiti: max 3/stagione, `gratuito=TRUE` in transazioni; se esauriti taglio bloccato (nessuna opzione forzato)
- Annuncio canale: con impatto mostra rate per stagione; gratuito mostra rimasti/3
- Admin può tagliare da menu admin con accountability

**DPE:**
- Fasi disponibili: `regular-season-fa` (pre-deadline), `regular-season-deadline` (post-deadline)
- Pre-deadline: decurtazione 25% arrotondato per eccesso + libera slot roster
- Post-deadline: decurtazione 25% + nessuno slot liberato (cambio ruolo aggiuntivo — da implementare con i ruoli)
- Tabella `dpe`: `(id, giocatore_id, team_id, stagione, importo_originale, importo_dpe, pre_deadline, approvata_da, timestamp)`
- La DPE è legata alla stagione corrente — alla stagione successiva il contratto torna all'importo originale automaticamente (la riga dpe non esiste per la nuova stagione)
- Flusso GM: richiesta → notifica gruppo admin → Approva/Rifiuta → DB + notifica GM + annuncio canale
- Flusso admin da menu: diretto senza approvazione (team→giocatore→conferma→DB+canale)

**Roster/Assets PNG (Typst):**
- Flag: `N`=normale, `A`=RFA, `R0-R3`=rookie anno I-IV
- Cap = contratti attivi + rate impatto taglio stagione corrente + DPE (riduce importo contratto)
- Età media su anni interi compiuti, un decimale
- `/roster [team_id] [DD-MM-YY o DD-MM-YYYY]` — storico via event sourcing
- `/assets [team_id]` — roster + pick per anno (★ proprie, ○ altrui) + diritti con #pick e anno draft
- Palette colori personalizzabile via `/palette`: `colore_header`, `colore_riga1`, `colore_riga2`, `colore_sezione`, `colore_pick`, `colore_diritti`
- Campi palette in `teams.json`, stringa vuota = default calcolato da `colore` principale
- Testo adattivo: colori calcolati in Python con luminanza WCAG (soglia 0.179), passati a Typst come `--input`; footer usa `c_dark` di default
- Warning colori scuri in `/palette` per campi sfondo

**Menu principale `/menu`:**
- Dinamico per fase: Trade/Tagli/Rookie mostrati solo in `FASI_TRADE_APERTE`, DPE solo in `regular-season-fa/deadline`, Roster/Assets sempre
- Assets con selezione squadra via bottoni (analogo a Roster)
- Trade builder avviato via `menu_trade_build` callback (entry point ConversationHandler)

**Menu admin `/admin_menu`:**
- Trade (con approvazione/rifiuto/rollback)
- Taglia giocatore (con selezione team+giocatore)
- DPE (diretta, con selezione team+giocatore+conferma)
- Attiva diritti (con selezione team)
- Situazione cap (riepilogo per team: contratti+tagli+penalità+DPE, stato ✅/🔴)
- Cambia fase (keyboard fasi inline)
- Annulla trade (lista ultime 15 approvate con bottoni+conferma+rollback)

**Validatori trade:**
- Cap post-trade vs `luxury_cap()` (dinamico: 165M offseason, 150M regular)
- Roster size: max 15 sempre, min 10 SOLO in regular season
- Stepien: `ANNO_STORICO_LIMITE = 2026` hardcoded
- Ownership giocatori: contratto attivo deve appartenere al team cedente
- Corrispondenza importo/anni contratto vs DB (warning se divergono)

**PostgreSQL schema:**
Tabelle: `giocatori`, `contratti`, `transazioni` (con `gratuito BOOLEAN`), `trade/trade_items/trade_squadre/trade_voti`, `pick`, `rookie`, `impatto_taglio`, `cambi_ruolo`, `penalita`, `bref_stats`, `dpe`

**dpe:**
```sql
(id SERIAL PRIMARY KEY,
 giocatore_id INTEGER REFERENCES giocatori(id),
 team_id TEXT, stagione TEXT,
 importo_originale INTEGER, importo_dpe INTEGER,
 pre_deadline BOOLEAN DEFAULT TRUE,
 approvata_da TEXT,
 timestamp TIMESTAMPTZ DEFAULT NOW(),
 UNIQUE (giocatore_id, stagione))
```

**bref_stats:**
```sql
(id, timestamp, stagione, nome_bref, team, g, mp,
 fgm, fga, fg_pct, fg3m, fg3a, fg3_pct, ftm, fta, ft_pct,
 orb, drb, trb, ast, stl, blk, tov, pf, pts,
 fantamedia NUMERIC GENERATED ALWAYS AS (...) STORED)
```
Stagione bref = stagione_corrente + 1 (es. stagione 2026 → bref 2027).
Scraper gira ogni mattina alle 10 solo in `regular-season-fa`, `regular-season-deadline`, `playoff`.

**Backup:**
- Giornaliero 00:00 e 12:00 → `log_channel_id_main` (solo PG)
- Settimanale domenica 00:30 → `admin_group_id` (PG + SQLite aste beta)
- On stop e shutdown → `log_channel_id_main` (PG + SQLite aste beta)
- `/backup` manuale → dev only, canale log

**Healthcheck:**
- Variabile env `HEALTHCHECK_URL` nel `docker-compose.yml` del bot main
- Ping ogni 5 minuti su healthchecks.io
- Job registrato solo se `HEALTHCHECK_URL` è presente

**deploy:**
```bash
cd ~/bots && unzip -o fantabasket-progettone-vX.Y.Z-completo.zip && \
cd fantabasket-progettone && docker compose up --build -d && \
git add -A && git commit -m "vX.Y.Z: descrizione" && \
git push origin main
```

**Bug noti aperti:**
- Votazione GM non testata end-to-end
- Guest mode in attesa supporto completo ptb per `InputRichMessageContent`

---

**Roadmap:**

**v1.5.x — bot main + aste (in corso)**
- Colorazione rossa giocatori con DPE attiva in roster/assets PNG
- Penalità: tabella, `/penalita` con motivazione, log canale; automatiche con Loucabot
- RFA in offseason-rinnovi (selezione contratti x0) + aste offseason-rfa
- Rinnovi: rookie vs non-rookie, +¼/+½ arrotondato per eccesso, Doncic Rule (soglie 20 e 25), max 2 standard per stagione
- 10-day contract: una volta per squadra, non pesa su cap/slot, max 2 squadre per FA, scade a fine turno
- Bref scraper: import automatico nuovi giocatori non in DB, check giornaliero alle 14 firmati senza nome_bref con suggerimento match, `/match_bref` dev, check alle 15 firmati senza data di nascita

**v2.x — GAS Router**
- Microservizio router nel Docker Compose
- Integrazione Google Sheets: foglio roster (ruolo/nome/$/Y per squadra) e foglio scelte (pick e diritti)
- Sync bulk dopo ogni transazione via POST a Web App GAS
- Account Google dedicato con email recovery Henry

**v3.x — Loucabot**
- Calcolo punteggi partite (refactor da versione esistente artigianale)
- Penalità automatiche: mancate panchine, giocatori fuori ruolo su Yahoo

**v4.x — IPanchinariBot**
- Gestione panchine giornaliere

**v5.x — Ruoli (feature trasversale)**
- Fase `offseason-ruoli` tra `offseason-fa` e `regular-season-fa`
- Tabella ruoli con event sourcing (label: inizializzazione/cambio normale/10-day/post-DPE/post-trade)
- In offseason-ruoli: dichiarazione iniziale in-place, nessuno storico
- In RS: 2 cambi normali + casi speciali tracciati
- Post-trade: notifica GM in privato per dichiarazione entro 48h, altrimenti ruolo casuale tra disponibili
- Fetch Yahoo giornaliero nuovi ruoli + notifica canale + Erminio rule automatica
- Cambio ruolo forzato admin (Vassell rule)
- Saedro rule: cambio ruolo temporaneo 10-day
- DPE post-deadline: cambio ruolo aggiuntivo gratuito

**@qf_bot (vX.x — dipende da guest mode PTB)**
- Bot pubblico per roster e info lega

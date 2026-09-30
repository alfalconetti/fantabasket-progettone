# Messaggio di migrazione — Fantabasket Progettone (stato v2.0.39)

---

Ecosistema Fantabasket su M910q Ubuntu (alfalconetti@ubuntum910q). Bot aste v48 standalone SPENTO — bot-aste-beta del progettone è ora in produzione con token reale. Tutto gira su Docker Compose unificato.

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
    ├── secrets/
    ├── fantabasket-aste-beta/
    └── fantabasket-main/
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
offseason-rfa → offseason-fa → (ricomincia)
```
Cambio fase via `/set_fase` (solo admin). Passaggio a `offseason-rinnovi` incrementa automaticamente `stagione_corrente`. `mercato_aperto` si aggiorna automaticamente al cambio fase.

**Comportamento per fase:**
- Trade aperte: `regular-season-fa`, `offseason-rinnovi`, `offseason-draft`, `offseason-rfa`, `offseason-fa`
- FA aperta: `regular-season-fa`, `offseason-fa`
- DPE disponibile: `offseason-rinnovi`, `offseason-draft`, `offseason-rfa`, `offseason-fa`, `regular-season-fa`, `regular-season-deadline`
- DPE libera slot: tutte le fasi tranne `regular-season-deadline`
- Bref scraper: `regular-season-fa`, `regular-season-deadline`, `playoff`
- Check cap stagionale bot aste: solo fasi `offseason-*`
- Cap massimo consentito: 165M in `offseason-*`, 150M altrimenti (`luxury_cap()` in settings main, `cap_limite()` in settings aste)
- Notifica ruoli post-trade: solo `regular-season-fa` (in futuro anche `offseason-ruoli`)

---

**Bot aste beta** — v48 + pg_client.py. Cap/slot da PostgreSQL. FA list da PostgreSQL (esclude diritti 2nd non firmati, ordinata per fantamedia bref desc). `BOT_VERSION = "beta-1"`. Config montata `:ro`. `cap_massimo()` alias di `cap_regular` (150M fisso), `cap_limite()` dinamico (165M offseason, 150M RS).

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
- Versioning: patch con suffisso incrementale (v1.4.17, v1.4.18...), feature bump minor (v1.5.0), nuovo servizio bump major (v2.0.0)
- Ogni zip include comando deploy + git commit + git push origin main
- `/annulla` globale con `group=-1` pulisce `user_data` e termina qualsiasi ConversationHandler

**Handlers bot-main:**
- `menu.py` — `/menu` dinamico per fase con InlineKeyboard; Trade/Tagli/Rookie/DPE solo nelle fasi corrette; Assets sempre visibile; entry point `menu_trade_build` e `menu_trade_import` registrati nei ConversationHandler del trade
- `trade.py` — builder (2-4 squadre), import, bozze con bottoni inline, edit, annulla, rollback; `/bozze_trade` mostra InlineKeyboard con bottoni diretti all'edit per bozze e al riepilogo-voto per pending; label bozze: `BUF03-3` (prime 3 lettere nome + num team + bozza_num) o `ADM-4` per admin; `trade_ref` (`TRADE-2026-001`) assegnato prima di `_esegui_trade` per evitare NULL nelle transazioni; notifica GM post-trade include "comunica i ruoli" solo in `regular-season-fa`
- `trade_parser.py` — parser deterministico testo trade; lookup pick per `proprietario_orig` (non per detentore attuale) via `get_pick_by_orig_anno_round()`
- `tagli.py` — taglio con preview impatto, conferma, scrittura DB, annuncio canale; tagli 1x1 gratuiti bloccati quando esauriti
- `rookie.py` — attivazione diritti 2nd pick, aperto a tutte `FASI_TRADE_APERTE`, annuncio canale
- `roster.py` — PNG via Typst subprocess per `/roster` e `/assets`; fuzzy match team via `get_team_by_query()`; roster sempre 15 righe (padding con righe vuote); giocatori con DPE mostrano importo barrato in rosso
- `palette.py` — `/palette` con anteprima PNG live
- `myteam.py` — modifica nome/colori team
- `team_diff.py` — variazioni roster tra date; fuzzy match team via `get_team_by_query()`
- `admin_panel.py` — pannello admin; DPE admin diretta (team→giocatore→conferma→DB+canale); annuncio canale usa `_formatta_annuncio_canale()` (non `_testo_riepilogo`)
- `dpe.py` — `/dpe` GM: flusso richiesta→approvazione admin gruppo→DB+canale; `pre_deadline = (fase != "regular-season-deadline")`; DPE legata alla stagione corrente
- `dev_player.py`, `dev.py`, `helpers.py` — invariati

**File principali bot-main:**
- `bot.py` — entry point; comandi GM: `build_trade`, `import_trade`, `bozze_trade`, `edit_trade`, `taglia`, `dpe`, `attiva_diritti`, `decadimento`, `my_team`, `palette`, `team_diff`, `annulla_trade`, `annulla`; comandi admin aggiuntivi: `admin_menu`, `set_fase`, `approva_trade`, `annulla_trade_admin`, `registra_firma`, `annulla_admin`, `settings`; comandi dev aggiuntivi: `dev*`, `job_status`, `broadcast`, `sync_sheets`, `backup`, `reboot`
- `teams.py` — `get_team_by_id`, `get_team_by_gm`, `get_all_teams`, `get_team_by_query` (fuzzy match su team_id → nome esatto → gm_nome esatto → prefix → difflib 0.6)
- `database.py` — `get_pick_by_orig_anno_round(proprietario_orig, anno, round)` per lookup pick nel trade parser; `get_roster_team()` joina tabella `dpe` e restituisce `importo` (DPE-adjusted), `importo_originale`, `ha_dpe`
- `scheduler.py`, `bref_scraper.py`, `utils.py`, `log_buffer.py`, `settings.py` — invariati
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

**DPE:**
- Fasi disponibili: `offseason-rinnovi` → `regular-season-deadline` (tutte e 6)
- `pre_deadline = (fase != "regular-season-deadline")` — libera slot in tutte le fasi tranne post-deadline
- Post-deadline: decurtazione 25% + nessuno slot liberato (cambio ruolo aggiuntivo — da implementare con i ruoli v5.x)
- `get_roster_count()` nel bot aste riceve sempre `stagione` per escludere giocatori con DPE dal conteggio slot
- Tabella `dpe`: `(id, giocatore_id, team_id, stagione, importo_originale, importo_dpe, pre_deadline, approvata_da, timestamp)`

**Roster/Assets PNG (Typst):**
- Flag: `N`=normale, `A`=RFA, `R0-R3`=rookie anno I-IV, `VUOTO`=riga padding
- Sempre 15 righe: padding con flag `VUOTO` per slot vuoti
- DPE: nome in rosso scuro, cella importo con originale barrato e nuovo importo
- Leggenda: rookie, RFA, DPE (mostrate solo se presenti)
- `/roster` e `/assets` accettano nome GM o nome squadra (fuzzy) oltre a team_id

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

**deploy:**
```bash
# File in handlers/:
unzip -p fantabasket-progettone-vX.Y.Z.zip NOMEFILE.py > ~/bots/fantabasket-progettone/fantabasket-main/handlers/NOMEFILE.py
# File in fantabasket-main/:
unzip -p fantabasket-progettone-vX.Y.Z.zip NOMEFILE.py > ~/bots/fantabasket-progettone/fantabasket-main/NOMEFILE.py
# Poi:
cd ~/bots/fantabasket-progettone && docker compose up --build -d bot-main && \
git add -A && git commit -m "vX.Y.Z: descrizione" && git push origin main
```

**Bug noti aperti:**
- Votazione GM non testata end-to-end
- Guest mode in attesa supporto completo ptb per `InputRichMessageContent`

---

**Roadmap:**

**v2.x — GAS Router + Google Sheets**
- GAS Router microservizio FastAPI ✅
- Foglio roster ✅ — foglio scelte (pick e diritti) ❌ da fare
- Sync automatico + periodico ogni 2h ✅
- `/sync_sheets` sincrono ✅

**v3.x — Loucabot**
- Calcolo punteggi partite + penalità automatiche

**v4.x — IPanchinariBot**

**v5.x — Ruoli (feature trasversale)**
- Fase `offseason-ruoli` tra `offseason-fa` e `regular-season-fa`
- Post-trade: notifica GM per dichiarazione ruoli entro 48h
- DPE post-deadline: cambio ruolo aggiuntivo gratuito
- Fetch Yahoo giornaliero

**@qf_bot (vX.x — dipende da guest mode PTB)**
- Bot pubblico per roster e info lega

---

**Stato attuale: v2.0.39**

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

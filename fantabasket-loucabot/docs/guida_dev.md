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
| `handlers_calcolo.py` | comandi del calcolo (`/tabellini`, `/espn_giocatori`, `/espn_mancanti`, `/espn_abbina`, `/fantapunti`), foto degli infortunati |
| `calendario.py` | CSV della lega: lettura, controlli, import; scadenze e squadre a media; `ora()` |
| `foglio.py` | foglio Google Calendario: `blocchi()` dal CSV importato e da `lega_risultati`, `aggiorna()` via gas-router |
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
| `nba_infortuni` | giorno, atleta | foto ESPN degli infortunati: stato, dettaglio; vale l'ultima foto del giorno |
| `nba_atleti` | atleta | giocatori dai roster ESPN (per l'abbinamento prima dei tabellini) |
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

`foglio.blocchi(stagione)` rilegge il CSV importato riga per riga: per ogni giornata un blocco `{numero, righe}` con la prima riga = intestazione (testo originale con `(media …)` sostituito da quelle calcolate, `foglio.intestazione`), poi le righe del CSV con `None` dappertutto tranne B e D: punteggi regolamentari nella riga delle squadre, supplementari nella riga sotto. Righe finali tutte `None` tolte. `foglio.aggiorna` → POST `gas-router/gas/calendario` (timeout 170 s) → `gas/calendario.gs` `handleCalendario`: trova il foglio (`CONFIG.CALENDARIO_SHEET_NAME` o "Calendario", maiuscole libere), cerca `^(week|giornata)\s+N\b` nella colonna A, legge il blocco e scrive cella per cella solo dove il valore cambia (intestazione: solo A, celle unite A:E). Risponde `{ok, celle, non_trovate}`. Lo script si prova con node simulando il foglio (vedi la storia della v7 nel CHANGELOG). Modifiche a `gas/`: `clasp push` e Nuova versione della web app.

## 4. Job

| Ora (Roma) | Job | Cosa |
|---|---|---|
| 8:30 | `handlers.job_sync` | partite dei giorni vicini (−3, +14), ricalcolo di scadenze e squadre a media (cambi → gruppo admin), tabellini delle partite finite, abbinamento automatico dei giocatori nuovi, foto degli infortunati; riga sul canale log |
| 17:30, 23:30 | `handlers_calcolo.job_infortuni` | foto degli infortunati (prima delle partite); sul canale log solo se fallisce |

Errori dei job: canale log e dev.

---

## 5. Calcolo (`calcolo.py`)

- `punteggio_giocatori(stagione, giornata, atleti)` → `{atleta: {fp, come, partite, squadra, nota}}`, con `come` ∈ partite / media / zero. Squadra NBA del giocatore: quella dei suoi tabellini nella giornata, se no l'ultima prima (`db.ultima_squadra`). Media della stagione: partite giocate di RS e play-in prima della giornata (`db.medie_stagione`). Indisponibile: stato diverso da Probable/Active in tutte le foto dei giorni della giornata; senza foto prende la media con un avviso.
- `punteggio_squadra(giornata, quintetto, panchina, punteggi)`: quintetto e panchina sono `[{atleta, ruolo, nome}]`, panchina in ordine. FADD (`_fadd_possibile`): titolare a 0 per "non ha giocato", tag in tutti i giorni in cui la sua squadra ha giocato (manca una foto → avviso, decide l'admin); entra il primo panchinaro dello stesso ruolo; una sola sostituzione; la panchina scala.
- `esito(casa, trasferta, bonus=3)`: scarto minimo `SCARTO` = 5, supplementari con i panchinari (5, poi 0), pari → trasferta.
- `abbina_auto({atleta: nome})`: `norm()` (senza accenti, Đ/ø/ł…, punteggiatura, Jr./Sr./II–V) uguale a uno e un solo giocatore dell'anagrafica (nome_common, nome_bref, nome_yahoo) e a un solo atleta ESPN; i già abbinati non si toccano.

Non ancora: quintetti e panchine (bot a parte), risultati congelati (`lega_punteggi`, `lega_risultati`, da scrivere alla convalida della giornata), classifica (parità: scontri diretti, media punti, differenza punti), playoff dalla classifica, 72 ore delle partite rinviate.

---

## 6. Prove

`tests/run.sh louca_calendario louca_calcolo louca_foglio` (mai sul server: svuotano tabelle). Dati veri ridotti in `tests/louca/`: `espn-20261022.json` (scoreboard), `espn-summary-20260301.json` (tabellino NYK-SAS con infortunati). `tests/docs/guide_e_menu.py` controlla che i comandi citati in README, guide, `/start` e menu esistano.

## 7. Rilascio

Come gli altri bot: zip cumulativo con `deploy.sh`; `rilascio-X.json` con `"loucabot"` in `riavvia`. Un secret nuovo nel compose va creato prima del deploy (`deploy.sh` controlla e si ferma).

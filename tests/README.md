# Prove dei bot

Prove "di flusso" dei bot (principale, aste, loucabot, IPanchinari): girano il codice vero (handler, validatori, query) contro
un **PostgreSQL 16 locale di prova** e una **configurazione finta**, con Telegram simulato
(oggetti finti al posto di bot, messaggi e bottoni: nessuna rete, nessun token).

> ⚠️ Le prove **svuotano le tabelle** (`TRUNCATE`). Mai puntarle al database vero:
> `PGURL` deve essere un database di prova su localhost.

## Preparazione (una volta)

```bash
sudo apt install postgresql-16          # oppure qualsiasi PostgreSQL 16 locale
pip install psycopg2-binary "python-telegram-bot[job-queue]==22.*"
sudo pg_ctlcluster 16 main start
sudo -u postgres psql -c "CREATE ROLE fb LOGIN SUPERUSER PASSWORD 'fb'" \
                      -c "CREATE DATABASE fbt OWNER fb"
PGPASSWORD=fb psql -h localhost -U fb -d fbt -q -f fantabasket-main/schema.sql
PGPASSWORD=fb psql -h localhost -U fb -d fbt -q -f fantabasket-main/bref_schema.sql
```

Le tabelle aggiunte nel tempo (dpe, richieste_admin, cap_anticipato, …) le crea
`migrate_db()`, chiamato dalle prove del bot principale: per questo `run.sh` le esegue per prime.

## Esecuzione

```bash
tests/run.sh                                  # tutte
tests/run.sh trade_3_squadre cap_asta_chiusa  # solo alcune
PGURL=postgresql://utente:pw@localhost/altro_db tests/run.sh   # altro database di prova
```

Ogni prova parte da una copia pulita di `tests/config/` (alcune cambiano la fase) e da un
`aste.db` SQLite nuovo. Esito: righe ✅ / ❌ FAIL e riepilogo finale.

## Configurazione finta (`tests/config/`)

- `settings.json`: **gli stessi valori di produzione** (cap, soglie, timeout, rookie scale,
  tabella minimi) — se cambiano in produzione vanno aggiornati anche qui.
- `globals.json`: fase `offseason-fa`, stagione 2026, mercato aperto, admin `900`, chat fittizie
  (canale aste `-10`, canale principale `-1`, gruppo admin `-2`, log `-3`/`-30`).
- `teams.json`: 4 squadre `team01`–`team04` (Alfa, Beta, Gamma, Delta); GM `101`+`111`
  (due GM su team01, per le prove "secondo GM"), `102`, `103`, `104`. I campi
  `cap_disponibile`/`slot_disponibili` servono solo alle prove del bot aste in modalità isolata.
- `fa_players.csv`: lista FA per le prove senza PostgreSQL (LeBron James, Jalen/Jaylin
  Williams per gli omonimi, Kevin Durant).

## Le prove

| Prova | Bot | Cosa verifica |
|---|---|---|
| `trade_3_squadre` | main | builder a 3 squadre (destinatari, diritti multipli, doppio tap), editor con `?`, bottoni vecchi, voti e notifiche a tutte le squadre, ripresa come bozza, approvazione ed esecuzione, `/annulla_trade_admin`, parser testo a 3+ |
| `revisione_regolamento` | main | tagli 1x1 (3 gratuiti, 4° con spalmatura, minimo 10 in RS), decadimento ritiro vs altro, `/ritiro_fa`, slot all'attivazione diritti, anni in `/registra_firma` |
| `dpe_trade_tagli` | main | DPE che segue il giocatore in trade (validazione = cap reale, annullamento), taglio bloccato se scopre i ruoli in RS |
| `report_spalmature` | main | report mensile: free agent con spalmature, ultima partita bref, Cam Thomas, esclusi i sotto contratto e le stagioni passate |
| `penalita_cap` | main | `/set_cap_penalizzato`: solo admin, scrive teams.json, tetto RS ridotto e offseason a 165 |
| `sync_fogli` | main | il foglio Roster si aggiorna sempre per tutte le squadre |
| `registro_unico` | main | migrazione al registro unico (tagli pre-bot, trade rimesse approvate, storico di pick e diritti con trade annullate e pre-bot), movimenti scritti da trade/annullamento/attivazione/scadenza, `roster_attuale`, controllo di coerenza, ricostruzione che si ferma su dati incoerenti |
| `taglio_admin` | main | il taglio dal pannello admin usa lo stesso codice dei GM: scelta della squadra, anteprima, minimi di regular season, scrittura atomica, avviso al GM |
| `team_diff` | main | contratti nei due momenti, DPE, cambio contratto, niente falsi cambi tra stagioni |
| `stagione` | main | cambio di stagione: Doncic (arrotondamenti), migrazione dei contratti rookie, anteprima completa (anche chi resta uguale, stima del rinnovo), II e IV anno, fine scala con Doncic d'ufficio, x0 fuori da cap e slot, rinnovo rookie, RFA dichiarati (cap sì, slot no, uno per squadra), RFA in trade (prima delle aste la dichiarazione decade, chi lo cede ne dichiara un altro, notifiche ai GM; con le aste aperte lo segue, al massimo uno per squadra; annullamento), pick dell'anno +6 ai rinnovi, scadenza degli x0 a inizio FA, report di inizio RS, coerenza a ogni passo, report lunghi come file `.md` |
| `regolamento_numeri` | main | i numeri del regolamento ricopiati a mano contro quelli del bot: roster, cap, floor, tempi, anni minimi, Stepien (anche la logica), tabella dei minimi, tagli (tabella fino a 5M e percentuali), DPE, rookie scale, Doncic, fantapunti, minimi e costanti dei ruoli, salary floor nelle trade in stagione. Lo specchietto completo è in `docs/regolamento_e_codice.md` |
| `cap_condiviso` | main | `shared/cap.py`: peso sul cap e slot per in corso, x0, RFA dichiarato, DPE prima e dopo la deadline; cap con le spalmature; il bot principale dà gli stessi numeri |
| `stagione_ui` | main | bottoni di rinnovo rookie e RFA (GM e admin, fuori fase, permessi), conferma con anteprima del cambio fase, doppio tap, ritorno ai rinnovi senza far avanzare la stagione |
| `pg_rfa_30giorni_dpe` | aste + PG | RFA: cap sì slot no, lascio andare con movimento; regola dei 30 giorni; DPE nel cap per offrire; rifirma dopo taglio |
| `rfa_lascio_andare` | aste + PG | "Lascio andare": solo proprietario, una volta sola |
| `apri_asta_admin` | aste (isolato) | `/apri_asta`: nome esatto/omonimi/fuzzy, cap, squadra, importo, mercato chiuso |
| `apertura_gm` | aste (isolato) | apertura del GM passata dalla funzione comune |
| `cap_asta_chiusa` | aste (isolato) | un'asta chiusa e non firmata impegna ancora cap e slot |
| `team_ricerca` | aste (isolato) | `/team` trova la squadra come `/roster` (id, nome, GM, inizio, una parola sola del nome della squadra o del GM, errore di battitura; ambigua → nessuna), senza argomento la propria |
| `regolamento_numeri_aste` | aste (isolato) | i numeri del regolamento nel bot aste: durata dell'asta, tempi di firma e pareggio, anni minimi, soglie del pareggio RFA |
| `rfa_proprietario` | aste (isolato) | il proprietario non offre sul proprio RFA neanche con `/offerta` |
| `menu_e_listteams` | aste + PG | menu "/" per fase e ruolo, `/listteams` compatto, `/reset_rfa` disattivato |
| `autoslot` | aste + PG | `/autoslot` e `/autocap` contano davvero negli slot e nel cap |
| `ruoli_trade` | main | ruoli dopo una trade in un messaggio unico sul canale: automatici, dichiarati, estratti, «tutti ufficiali»; le firme restano a parte |
| `date_comandi` | main | `shared/date_comandi`: tutti i formati di data, date impossibili, data e ora, date di nascita a 2 cifre |
| `firma_per_conto` | aste + PG | `/firma_per_conto`: elenco, solo admin, stessi bottoni del GM, annuncio sul canale, GM avvisati, registro «per conto» |
| `registro_azioni` | main | registro delle azioni: una riga per azione (chi, veste, cosa, squadre, prima → dopo), admin e dev anche sul canale log, `/registro` (admin tutto, GM la sua squadra), il registro non fa mai fallire un'azione |
| `menu_palette` | main | menu a bottoni sempre con ← o ✖️ Chiudi, `/palette` (colori veri, automatico, anteprime, testo leggibile), `/my_team`, `/team_diff` nei gruppi, DPE su un 1x1 normale ; `/edit_team` e «✏️ Nomi squadre e GM» (solo admin, nome squadra e GM di un'altra squadra, registro) |
| `admin_poteri` | main | dal menu normale un admin che è anche GM ha le regole dei GM; i poteri da admin solo dal pannello e dai comandi admin |
| `regole_config` | main | i numeri del regolamento in settings.json (`shared/regole.py`) si leggono davvero, senza riavvio; default se mancano; fantamedia bref coi pesi |
| `impostazioni` | main | `/settings`: argomenti coi bottoni, anteprima e conferma, canali; ogni chiave del file e di `regole.DEFAULT` ha una voce |
| `report_ruoli` | main | `/report_ruoli`: i ruoli di tutte le squadre in Markdown (riepilogo, minimi, note) |
| `report_dati` | main | `/report_dati`: la salute dei dati in Markdown |
| `bref_abbina` | main | abbinamento dei nomi di Basketball-Reference (automatico senza accenti, bottoni per i simili, log); stagione non ancora iniziata su bref: ⏳, foglio BrefRaw non toccato |
| `penalita` | main | penalità degli admin (motivazione, canale, GM, log, foglio Scelte), revoca, conteggio per stagione |
| `dieci_giorni` | main | 10-day contract: richiesta, approvazione, firma dell'admin, regole, niente cap né slot, scadenza a fine giornata; `roster.typ` e `assets.typ` compilano (pick, diritti, chi è fuori dai 15 sotto) e con la risoluzione giusta (`PPI_ROSTER`, `PPI_ASSETS`) |
| `registro_aste` | aste + PG | registro delle azioni dal bot aste: squadre e giocatore dall'asta, azioni admin sul canale log del bot aste, offerte dei GM solo nel registro |
| `tempo_scaduto` | aste + PG | decisioni d'ufficio a tempo scaduto (3 anni di penale, anni minimi RFA, pareggio non deciso) dette nell'annuncio sul canale |
| `louca_risultati` | loucabot | calcolo definitivo dalle formazioni di IPanchinari (FADD, medie, supplementari, titolare anche in panchina a 0), foglio «Calcolo GN» confrontato con LibreOffice, proposta, convalida, risultati definitivi sul canale e live cancellato, avviso se cambia un esito, live (riga per squadra «devono giocare / rigiocare (finora)»), `/notte`, `/partita` (dati, immagine, argomenti, giornata di default) ; foglio provvisorio a metà giornata (niente prima della prima notte, PROVVISORIO con le formule, non sovrascritto dalle formazioni, correzione dopo la prima notte riscritta col calcolo) |
| `louca_foglio` | loucabot | il foglio Calendario costruito dal CSV: intestazioni con le squadre a media, punteggi regolamentari e supplementari |
| `louca_classifica` | loucabot | classifica (avulsa, `/classifica`, `/classifica_full`, immagini Typst) dai risultati convalidati |
| `ipa_panchine` | IPanchinari | panchine da messaggio e coi bottoni, `/edit`, soprannomi, quintetti, promemoria, riepilogo, chiusura, giornata in corso fino alle 6 (GM bloccati, admin correggono), medie nei builder |
| `ipa_errori` | IPanchinari | error handler comune: «not modified» ignorato, errori di rete solo sul canale log, gli altri anche al dev |
| `ipa_injury` | IPanchinari | avvisi dell'injury report: punto di partenza senza avvisi, confronto con l'ultimo visto (più snapshot nel frattempo), un messaggio per GM con prima → dopo, dettaglio e ruolo nel quintetto, uscito dalla lista = disponibile, GM che non ha avviato il bot saltato, `/toggle_injures` (spegne, riaccende, solo GM e in privato), snapshot incompleto senza avvisi; loucabot: finestra delle 19 → prima partita della prima sera |
| `router_health` | router | le richieste a /health dei router non finiscono nei log |
| `gas_node` | GAS | gli script `gas/*.gs` provati con node e finti oggetti di Google (senza node si saltano) |
| `backup_foto` | main | il backup contiene tutta config/ tranne le foto dei giocatori (config/foto) |
| `louca_calendario` | loucabot | CSV del calendario, import, partite NBA da ESPN (risposta vera ridotta), TBD, squadre a media e scadenze, cambi, `/calendario`, canale log |
| `louca_calcolo` | loucabot | tabellino ESPN vero ridotto (NYK-SAS 1/3/2026) e formula dei fantapunti, infortunati, punteggio nella giornata (partite, media, zero, rinviate), FADD, supplementari e bonus casa, abbinamento ESPN |
| `giocatore_id` | aste + PG | l'asta ricorda l'id del giocatore: la firma non crea doppioni se il nome cambia |
| `rfa_dichiarati` | aste + PG | x0 fuori da cap e slot, RFA dichiarato sul cap; aste RFA aperte da sole nella fase RFA, una volta sola; proprietario allineato dopo una trade; il contratto nuovo di chi vince non cambia il proprietario; DPE prima e dopo la deadline |
| `guide_e_menu` | — | ogni comando citato in guide, `/admin`, `/dev` e menu "/" esiste nel suo bot (nessun database) |
| `letture_transazioni` | — | nessuno legge `transazioni` fuori dalle funzioni ammesse (i roster si ricostruiscono da `movimenti_giocatori`) |
| `nomi_importati` | — | ogni nome preso da un altro modulo esiste: `from x import y` anche dentro le funzioni (pyflakes non li guarda), `db.funzione`, le sostituzioni delle prove (`modulo.f = ...` vale solo dove `f` è definita). Legge i sorgenti, non li esegue |

"Isolato" = bot aste senza PostgreSQL (`PG_URL` vuoto): cap e slot dal JSON.

## Script della dashboard

`tests/dashboard/docker_finto` simula `docker compose exec -T postgres …` girando i comandi
sul PostgreSQL locale. Per provare `scripts/setup_dashboard.sh` senza Docker:

```bash
sudo -u postgres psql -c "CREATE ROLE fantabasket LOGIN SUPERUSER PASSWORD 'x'" \
                      -c "CREATE DATABASE fantabasket OWNER fantabasket"
mkdir -p /tmp/dash/scripts /tmp/dash/secrets && cp scripts/setup_dashboard.sh /tmp/dash/scripts/
mkdir -p /tmp/shim && cp tests/dashboard/docker_finto /tmp/shim/docker && chmod +x /tmp/shim/docker
cd /tmp/dash && PATH=/tmp/shim:$PATH PGPASSWORD=x bash scripts/setup_dashboard.sh   # due volte: deve restare uguale
```

## Scrivere una prova nuova

Lo schema è sempre lo stesso: si parte dal DB svuotato, si inseriscono giocatori/contratti/
transazioni con SQL, si chiamano gli handler con oggetti finti (`types.SimpleNamespace` per
update/context, una classe `Q` con `answer` / `edit_message_text` per i bottoni, un `Bot` con
`send_message` che salva i messaggi) e si controlla il risultato con `ok(condizione, "descrizione")`.
Vedi `main/trade_3_squadre.py` come esempio completo.

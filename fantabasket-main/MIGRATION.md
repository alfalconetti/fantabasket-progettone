# Messaggio di migrazione — Fantabasket Progettone

**Stato: v5.9.1 · bot aste v67 · loucabot v32 · IPanchinari v20** (13/10/2026)

Il punto da cui ripartire in una sessione nuova: com'è fatto il progettone oggi, come si lavora, cosa è stato deciso e cosa resta da fare. Solo cose valide adesso; la storia versione per versione è nei CHANGELOG (`fantabasket-main/CHANGELOG.md`, `fantabasket-aste-beta/CHANGELOG.md`, `fantabasket-loucabot/CHANGELOG.md`, `fantabasket-ipanchinari/CHANGELOG.md`). Le guide dei bot (`docs/guida_gm.md`, `guida_admin.md`, `guida_dev.md` di ognuno) e `docs/RECOVERY.md` sono il riferimento di dettaglio.

---

## 1. Panorama

Lega fantasy NBA a 24 squadre (due conference da 12) gestita su Telegram da quattro bot, su un server domestico Ubuntu con Docker Compose, in `~/bots/fantabasket-progettone` (repo git, push su `origin main`). Il vecchio bot aste standalone (`~/bots/fantabasket-aste`, v48) è spento e congelato.

**Stack:** Python 3.12, python-telegram-bot 22.8 [job-queue], PostgreSQL 16, SQLite (solo bot aste), Typst (PNG di roster e assets), FastAPI (router), Google Apps Script (fogli), httpx/aiohttp, pandas + lxml (bref).

| Servizio | Cosa fa |
|---|---|
| `postgres` | database unico `fantabasket` (+ `nocodb` per i dati interni della dashboard) |
| `bot-main` | bot principale: roster, trade, tagli, DPE, rookie, ruoli, stagione, backup, fogli |
| `bot-aste-beta` | bot delle aste FA e RFA (SQLite per le aste, PostgreSQL per cap e slot) |
| `loucabot` | il campionato: calendario, tabellini ESPN e fantapunti, foglio Calendario |
| `ipanchinari` | panchine (dai messaggi dei GM, soprannomi compresi) e quintetti |
| `gas-router` | ponte FastAPI verso la web app Apps Script (fogli Roster, Scelte, BrefRaw, Calendario) |
| `yahoo-router` | OAuth2 Yahoo, pronto ma in attesa dell'abilitazione di Yahoo |
| `nocodb` | dashboard in LAN/Tailscale, di solito spenta |

```
fantabasket-progettone/
├── docker-compose.yml
├── config/        globals.json, teams.json, settings.json, divisions.json, tabelle/, loghi/   (solo sul server)
├── secrets/       token, password, URL dei fogli, *.env; cifrati/secrets.tar.gpg               (solo sul server)
├── shared/        in comune ai bot: ruoli_core.py, cap.py, squadre.py, messaggi.py, dev_comune.py (/dev_log, /dev_pg, /reboot ed error handler di loucabot e IPanchinari) (montata :ro)
├── fantabasket-main/ · fantabasket-aste-beta/ · fantabasket-loucabot/ · fantabasket-ipanchinari/
├── gas/           Apps Script (clasp); globals.gs solo in locale
├── gas-router/ · yahoo-router/
├── scripts/       deploy.sh, cifra_secrets.sh, setup_dashboard.sh, prova_generale/
├── tests/         prove locali (mai sul server)
└── docs/          RECOVERY.md (backup e ripristino), regolamento_e_codice.md (regolamento ↔ codice)
```

---

## 2. Regole di lavoro

**Consegna**
- Le versioni si consegnano come zip **cumulativo** (differenza dall'albero v3.10.0) con `deploy.sh` e `rilascio.json` dentro. Deploy, sempre da `~/bots`:
  ```bash
  cd ~/bots && Z=fantabasket-progettone-vX.Y.Z.zip; bash <(unzip -p $Z deploy.sh) $Z
  ```
  `deploy.sh` controlla lo zip (niente `config/`, `secrets/`, `.db`, `globals.gs`) e che esistano i file di `secrets/` richiesti dal compose, fa il dump del DB, scompatta, riavvia i servizi di `riavvia` e controlla i log, poi commit e push (togliendo comunque dal commit `secrets/`, `config/`, `.db`, `globals.gs`). Se un bot non parte non committa e dice come tornare indietro.
- `rilascio.json`: `versione`, `messaggio` (commit), `elimina`, `riavvia`, `ferma_aste_prima`, `attesa_main`, `log_attesi`.
- Niente accesso a GitHub: niente permessi chiesti né usati. Si consegna solo lo zip.
- Ogni versione aggiorna il CHANGELOG del bot toccato: la versione mostrata dai bot è l'ultima voce `## v…` del loro CHANGELOG. Numerazione: progettone `vX.Y.Z` (patch per correzioni, minor per funzioni, major per un servizio nuovo); bot aste `vNN`; loucabot e IPanchinari `vN`.
- Prima di discutere, poi codice, poi zip: niente rilasci di cose non decise.
- Questo file si tiene aggiornato **per argomento** a ogni rilascio che cambia lo stato (decisioni, architettura, operazioni, da fare), togliendo quello che non vale più: niente elenchi di versioni.

**Sicurezza**
- Nel repo pubblico e nei documenti niente ID di leghe, client ID, nomi di app, utente o host del server, link di sessione. Dati sensibili non segreti (URL, ID) in `secrets/*.env` via `env_file`.
- Mai scrivere da nessuna parte che si sono presi dati dalla console.
- `config/`, `secrets/`, database e `gas/globals.gs` mai negli zip (`tests/config` sì: è finta).
- Le copie del DB vero (`prodcopia` e simili) restano solo nell'ambiente di lavoro.
- Nelle prove niente nomi veri delle squadre: si usano quelli di `tests/config` (Alfa, Beta, Gamma, Delta).
- Dopo ogni modifica a `secrets/`: `bash scripts/cifra_secrets.sh` (finisce nel backup) e `docker compose up -d --force-recreate <servizio>` (vi crea un file nuovo e il container continua a vedere il vecchio).

**Codice**
- Modifiche chirurgiche; `update.effective_message` ovunque; fasi sempre con i trattini.
- Bot principale: `@solo_privato` su tutto tranne `/roster`, `/assets`, `/team_diff`; `@richiede_fase` per i comandi di fase; `per_message=False` nei ConversationHandler; `/annulla` globale (`group=-1`).
- Parità GM/admin: ogni azione GM ha l'equivalente "per conto di" nel pannello admin. L'admin che è anche GM, nei flussi GM, agisce con le regole dei GM.
- Un comando GM legato a una fase va in `comandi.py` (`_fasi_comando`) e in `AZIONI_FASE` del menu.
- Un tipo nuovo di `transazioni` o `cambi_ruolo` va in `_allinea_check` (`migrate_db`) e in `schema.sql`.
- Schema SQLite del bot aste solo additivo (deve restare leggibile dal v48).
- Una modifica a `shared/` richiede il riavvio di tutti i bot che la usano.
- Log: in ogni bot `httpx` e `httpcore` a WARNING, così le chiamate all'API di Telegram (col token nell'URL) non finiscono nei log. Un bot nuovo fa lo stesso.
- Log: in ogni bot `httpx` e `httpcore` a WARNING (niente riga per ogni chiamata a Telegram, che conterrebbe anche il token nell'URL); nei router (`gas-router`, `yahoo-router`) un filtro su `uvicorn.access` toglie le richieste a `/health` dell'healthcheck di Docker (prova `tests/docs/router_health.py`). Un bot o un router nuovo fa lo stesso.
- Prima di ogni zip: `pyflakes` e `tests/run.sh` con "Tutte le prove passate." (comprende `nomi_importati`, che trova gli import rotti dentro le funzioni).
- Modifiche strutturali: prova generale su una copia del DB vero (`scripts/prova_generale/`: foto di tutte le squadre prima e dopo, confronto; differenze solo volute).

---

## 3. Operazioni

- psql: `docker compose exec -T postgres psql -U fantabasket -d fantabasket -c "…"`.
- Script Python nel container: `db.init_db()` prima di usare il DB.
- **Apps Script** (`gas/`): `cd ~/bots/fantabasket-progettone/gas && clasp push`, poi dal browser Gestisci deployment → matita → **Nuova versione** (un "Nuovo deployment" cambia l'URL: andrebbero aggiornati `secrets/gas_roster_url` e `gas_scelte_url`, `--force-recreate gas-router` e `cifra_secrets.sh`). `gas/.claspignore` esclude `globals_sample.gs` (sennò `CONFIG` è dichiarato due volte e la web app risponde con una pagina d'errore). Se `clasp push` chiede di sovrascrivere il manifest: **No**, prima riallineare `appsscript.json` con un `clasp pull` in una cartella a parte. Diagnosi: chiamata diretta dal container gas-router; se risponde HTML, il titolo dice l'errore (login = accesso non "Chiunque").
- Una web app sola per Roster, BrefRaw e Calendario (`gas_roster_url`, smista per `action`), una per Scelte (`gas_scelte_url`).
- Backup: un solo backup, dal bot principale, completo (`pg_dump`, `aste.db` coerente, `config/`, `secrets.tar.gpg`, `MANIFEST.txt`): canale log alle 00 e 12 e allo spegnimento, gruppo admin il sabato alle 00:30, `/backup`. Ripristino: `docs/RECOVERY.md`. Il database `nocodb` non è nel backup (`scripts/setup_dashboard.sh` dopo un ripristino).
- Dashboard NocoDB: `docker compose stop|start nocodb`; utente PostgreSQL `lettore` in sola lettura con timeout di 30 s (non può bloccare le migrazioni dei bot).

---

## 4. Configurazione e fasi

**globals.json** (lo scrive il bot principale; gli altri lo leggono): `fase`, `stagione_corrente` (`"2026"` = 2026-27), `mercato_aperto`, `admin_ids`, `dev_id`, `admin_group_id`, `main_channel_id`, `channel_id` (aste), `log_channel_id` (aste), `log_channel_id_main`, `log_channel_id_louca`, `log_channel_id_ipa`, `canale_panchinari_id`, `trade_deadline`, `deadline_ruoli`, `repo_url`.

**settings.json** (condiviso, `/settings chiave valore`): `cap_offseason` 165, `cap_regular` 150, `salary_floor` 115, `roster_max` 15, `roster_min_regular` 10, … Dalla v5.8.0 anche i numeri del regolamento sparsi nel codice (pesi dei fantapunti, bonus casa, scarto, panchina, minimi dei ruoli, cambi ruolo, tagli gratuiti, 10-day, DPE, riacquisto), letti da `shared/regole.py` con i default di oggi: elenco in `fantabasket-main/docs/guida_dev.md`. Restano nel codice solo valori tecnici (limiti di Telegram, soglie di somiglianza, paginazioni).

**Fasi** (cambio con `/set_fase`, con anteprima e conferma; il bot aste non cambia fase):
```
regular-season-fa → regular-season-deadline → playoff →
offseason-break → offseason-rinnovi → offseason-draft →
offseason-rfa → offseason-fa → offseason-ruoli → (ricomincia)
```
- Entrando in `offseason-rinnovi` la stagione avanza e partono i passaggi automatici (vedi §6). A ogni cambio: annuncio sul canale principale (`FASI_INDICAZIONI`, da tenere allineate al regolamento), menu e comandi Telegram aggiornati, `mercato_aperto` ricalcolato.
- Trade aperte: `regular-season-fa` e tutte le `offseason-*` tranne `break`. FA aperta: `regular-season-fa`, `offseason-fa`, `offseason-ruoli`. DPE: da `offseason-rinnovi` a `regular-season-deadline`. Ruoli dichiarati in `offseason-ruoli`, cambi ruolo in RS e playoff. Bref: RS, deadline, playoff.

---

## 5. Decisioni sul regolamento

Lo specchietto completo regolamento ↔ codice ↔ prove, con i testi proposti per le correzioni, è `docs/regolamento_e_codice.md`; le prove `regolamento_numeri` e `regolamento_numeri_aste` ricopiano i numeri a mano.

- **Cap**: offseason 165 per tutti, anche per i penalizzati (il testo del regolamento va corretto); RS 150 − `cap_penalizzato`. Floor 115: in stagione le trade non possono portare o lasciare sotto.
- **Stepien**: finestre di 4 anni sulle proprie 1st (testo da correggere). Anni ≤2026 coperti d'ufficio.
- **Offerta massima 141** = conseguenza di cap e minimo giocatori, non una regola.
- **DPE**: contratto − ceil(25%); segue il giocatore in trade; libera lo slot solo se approvata prima della deadline; dopo la deadline cambio ruolo extra gratuito.
- **Tagli**: 1x1 gratuiti (3), spalmatura oltre 5M per eccesso; in RS niente tagli sotto 10 giocatori o che scoprono i minimi dei ruoli. Rifirma dopo taglio: spalmatura invariata + contratto nuovo. Cam Thomas exception: motivo del decadimento, rifirma entro un anno ≥ contratto precedente.
- **Aste**: nessun minimo per fantamedia nelle FA; aste aperte, chiuse e in pareggio impegnano cap e slot; regola dei 30 giorni dopo un taglio.
- **Rookie e x0**: anni residui sempre calcolati; x0 = contratto finito, resta fino all'inizio FA e non pesa, tranne l'RFA dichiarato (cap sì, slot no). Doncic: max fantamedia delle ultime due stagioni per difetto, importo per eccesso, solo sopra la tabella; al IV anno il contratto non scende sotto la tabella. Tra rinnovi e draft le annate di pick sono 7.
- **RFA**: si dichiara e si cambia quante volte si vuole fino all'inizio delle aste RFA (anche nel draft). In trade prima delle aste la dichiarazione decade (chi lo cede ne dichiara un altro, per chi lo riceve è un x0 che non pesa); dalle aste in poi segue il giocatore, massimo uno per squadra. Sui canali: una riga per evento sul log, un riepilogo unico aggiornato sul canale principale.
- **Ruoli**: PG/SG/SF/PF/C tra le posizioni eleggibili; minimi 4G/4F/2C; dichiarazione a inizio stagione, in RS dichiarazioni post-trade/firma entro 48 h (poi estrazione) e regola dei 60 giorni; cambi ordinari 2 a stagione, Erminio (14 giorni dall'aggiunta della posizione), Saedro (10 giorni, una volta), forzati admin che non contano.
- **Partita** (loucabot): fantapunti = punto +0,5, assist +2, rimb. off. +2, dif. +1,25, tripla +1,5, tiro tentato −0,5 e segnato +1, libero tentato −0,75 e segnato +1, recupero +2, stoppata +2, palla persa −2. Più partite nella giornata → media (uno 0 con 0 minuti non conta, uno 0 con dei minuti sì), arrotondata all'ottavo come la media della stagione (Luca, 13/10: solo ,00 ,13 ,25 ,38 ,50 ,63 ,75 ,88; la metà per eccesso, come ROUND dei fogli; `loucabot/numeri.py`); squadre NBA senza partite → media della stagione, 0 se indisponibile; FADD anche quando la squadra del titolare non gioca (deciso con Luca il 13/10), poi la panchina scala e resta di 4; supplementari sul Calendario come soli punti dei supplementari; vince chi ha 5 o più punti di scarto bonus casa compreso (3, playoff 5), poi supplementari con la panchina, pari fino al decimo uomo → trasferta. Vale il calcolo delle squadre a media dalle partite NBA, non le note del calendario.
- **Cambi dei numeri del regolamento** (Luca, 18/10): si decidono alla riunione di lega di giugno e si cambiano in `settings.json`. Se cambiano i pesi dei fantapunti: `/dev_ricalcola_fp` su loucabot per la stagione nuova; le giornate già convalidate non si ricalcolano mai.

---

## 6. Bot principale (`fantabasket-main`)

Guida tecnica completa: `fantabasket-main/docs/guida_dev.md`.

- **Registro unico**: `transazioni` registra giocatori, pick, diritti ed eventi di squadra (`oggetto`); vista `movimenti_giocatori` per ricostruire i roster a una data; storico di pick e diritti; ogni chiusura di contratto ha il suo movimento; controllo di coerenza notturno (01:00, `/dev_coerenza`). Ogni cambio di importo = contratto nuovo.
- **Trade** (`handlers/trade*.py`, divisi nella v3.13.0): builder 2-4 squadre, import da testo (`trade_parser.py`: pick per proprietario originale, possesso verificato), bozze, voti, approvazione; stati cambiati solo con `db.cambia_stato_trade`; esecuzione e annullamento atomici in `_scrivi_trade` (verifica di ogni asset, `TradeNonEseguibile`); `trade_ref` (`TRADE-AAAA-NNN`) assegnato prima dell'esecuzione; annuncio sempre con `_formatta_annuncio_canale`.
- **Richieste agli admin** (DPE, Saedro, decadimento): `richieste_admin`, una richiesta aperta per giocatore, decisione unica (`db.apri_richiesta` / `chiudi_richiesta`).
- **Cambio di stagione** (`handlers/stagione.py`): ai rinnovi rookie scale, Doncic d'ufficio a fine IV anno, pick dell'anno +6, `/rinnovo_rookie`, `/dichiara_rfa`; all'inizio FA x0 scaduti; all'inizio RS report di floor e tetto. `/dev_stagione` per l'anteprima, `/trade_deadline` ogni stagione. Report lunghi come file `.md` (`shared/messaggi.py`).
- **Cap e slot**: `shared/cap.py`, un'implementazione per il bot principale e il bot aste.
- **Ruoli**: `shared/ruoli_core.py` (regole uniche), `handlers/ruoli.py`, `ruoli_rs.py`, `cambi_ruolo.py`, posizioni eleggibili importate da CSV Yahoo (`/import_posizioni_eleggibili`, event log `posizioni_eleggibili`).
- **Fogli Google** (`gas_client.py` → gas-router): Roster sempre per tutte le 24 squadre, Scelte, BrefRaw; il bot aste accoda le firme in `gas_sync_queue`, il principale sincronizza ogni 60 s.
- **Basketball-Reference**: job giornaliero alle 10:00 (per_game → `bref_stats`, fantamedie, cambi squadra NBA). L'aggancio all'anagrafica è per `giocatori.nome_bref` uguale al nome di bref: un nome nuovo uguale senza accenti a uno e un solo giocatore mai visto su bref si abbina da solo (v5.4.1), gli altri vanno al dev (🔗 abbina a un simile, 🆕 crea, ✅ crea quelli senza simili); nel log chi è abbinato e chi a roster su bref non c'è.
- **Anagrafica** `giocatori`: `nome_common`, `nome_bref`, `nome_yahoo`, `yahoo_id`, `espn_id` e `nome_espn` (questi due li scrive loucabot), `data_nascita`.

## 7. Bot aste (`fantabasket-aste-beta`, v64)

Guida tecnica: `fantabasket-aste-beta/docs/guida_dev.md`. Aste in SQLite per scelta (si può sempre tornare al v48), cap e slot da PostgreSQL (`pg_client.py`, `shared/cap.py`); `config/` in sola lettura. FA e RFA (aste RFA aperte da sole all'inizio della fase), `/apri_asta` per conto di una squadra, menu comandi per ruolo e fase, nessun backup suo (lo fa il principale), file grandi divisi nella v3.13.0 (`admin_*`, `firma_*`).

## 8. loucabot (`fantabasket-loucabot`, v9)

README e guide in `fantabasket-loucabot/` e `docs/`. Legge tutto, scrive solo le sue tabelle (`lega_*`, `nba_*`) più `giocatori.espn_id`/`nome_espn`. Canale log suo (`log_channel_id_louca`), gruppo admin solo per i cambi del calendario; menu per scope e guide come gli altri bot.

- **Calendario**: CSV degli admin importato con `/importa_calendario` (nomi esatti di teams.json; conservato tale e quale in `lega_calendario_csv`). 2026-27: 38 giornate, verificato; le note sulle squadre a media del CSV originale erano incomplete (corrette nel CSV mandato a Luca).
- **Partite NBA da ESPN** (`site.api.espn.com`, pubblico; NBA.com dal server dà 403; bref è la riserva, circa 20 richieste al minuto al massimo): per ogni giornata scadenza (prima partita) e squadre a media; ogni mattina alle 8:30 sincronizzazione dei giorni vicini, avviso agli admin se cambia qualcosa. TBD (NBA Cup da decidere) non è una squadra.
- **Tabellini e fantapunti**: box score ESPN (`summary?event=ID`) di ogni partita finita, una volta sola, in `nba_tabellini` con le statistiche e `fp`. Formula verificata sul vecchio foglio (17/01/2026: 141 righe su 141; l'unica differenza era un errore del foglio). Snapshot degli infortunati ESPN (`nba_infortuni`) ogni 4 ore, anche di notte, più uno 30 minuti prima della prima partita del giorno (deciso con Luca il 13/10: molti report arrivano subito prima della partita). Si tengono tutti per una settimana, poi resta solo quello che conta per il calcolo: di ogni giorno, l'ultimo prima della prima partita. Il più recente è lo stato mostrato da IPanchinari. Solo dai ruoli dell'offseason ai playoff. In caso di dubbio un admin decide lo status che vale per la giornata con `/set_valid_status GIOCATORE N`, tra quelli catturati: è l'unica cosa del calcolo che si corregge a mano. Abbinamento giocatori per id ESPN (automatico sui nomi, `/espn_mancanti`, `/espn_abbina`); i 99 dell'anagrafica non abbinati al 12/10 sono fuori dai roster NBA.
- **Calcolo** (`calcolo.py`): punteggio del giocatore nella giornata, della squadra con FADD, esito con supplementari, tutto provato. `/fantapunti N` per controllo.
- **Foglio Calendario** (stesso file del Roster, oggi un foglio parallelo di test): a ogni aggiornamento si ricarica tutta la pagina, colonne A:E (formattazione e celle unite restano), con le squadre a media calcolate e i punteggi in B e D (regolamentari nella riga delle squadre, supplementari sotto) da `lega_risultati`. All'import, quando cambiano le squadre a media, con `/calendario_foglio`; da fare anche dopo ogni giornata ufficializzata. La classifica sul foglio ha le sue formule.

## 8b. IPanchinari (`fantabasket-ipanchinari`, v5)

README e guide in `fantabasket-ipanchinari/`. Scrive solo `ipa_*`; legge roster e ruoli (bot principale), giornate e partite NBA (loucabot). Deciso con Luca (13/10/2026), per venire incontro alle abitudini dei GM:
- **Panchine come sempre, da messaggio**: il GM manda al bot in privato le righe dei panchinari (soprannomi "High CAI" compresi, titolo facoltativo sopra separato da una riga vuota); il bot le abbina ai giocatori della squadra (tollerante; dubbi coi bottoni; soprannomi ricordati, che seguono il giocatore nelle trade; `/soprannomi` per vederli e cancellarli), chiede conferma e pubblica sul **canale Panchinari solo le righe come le ha scritte il GM**, mai i nomi veri. **Sempre 5 giocatori, mai meno.** Vale per la prossima giornata aperta; rimandata, il messaggio sul canale si modifica. Chi vuole la compone coi bottoni (`/build_panchina`: solo giocatori non nel quintetto; con il bottone 😎 CAI mode titolo e soprannomi).
- **Quintetti non reinseriti ogni giornata**: Luca li carica (da Yahoo, `/quintetti_import`; script da console da fare), poi restano. Promemoria alle 8 (Roma) dell'ultimo giorno prima della giornata con le partite di ogni titolare e Confermo/Modifico validi fino alla scadenza; `/quintetto` per i cambi; incompatibilità segnalate. Agli admin il riepilogo 2 ore prima: l'unico lavoro di Luca è controllare su Yahoo i quintetti di chi non ha risposto.
- Alla scadenza i quintetti si congelano in `ipa_formazioni`: sono quelli che userà il calcolo, insieme a `ipa_panchine`. Gli admin li correggono anche a giornata in corso (`/quintetto_admin SQUADRA [GN]`, senza righe coi bottoni partendo dal quintetto attuale; `/panchina_admin SQUADRA` senza righe apre il builder): il lavoro su Yahoo non va fatto per forza prima della scadenza.
- Per il quintetto fa fede Yahoo (regolamento): i GM non sono obbligati ad aggiornarlo nel bot; un panchinaro titolare nel bot è solo segnalato (al GM e sul canale log), non blocca. Il bot lo ripete ovunque inviti ad aggiornare il quintetto: "non è obbligatorio, è un favore agli admin" (`comune.FAVORE`).
- **Trade e tagli**: un giocatore schierato (quintetto, panchina della prossima giornata, giornata in corso) che esce dalla squadra fa partire un avviso ai GM e al canale log, una volta sola (job ogni 5 minuti).

## 9. Fonti esterne

- **Yahoo**: dal luglio 2026 la Fantasy API richiede un'approvazione separata (contratto); senza, 403. Richiesta inviata; `yahoo-router` pronto (`docker compose exec -it yahoo-router python3 cli.py auth`, poi `cli.py teams`). Sul portale developer ci sono due app: in uso la nuova, la vecchia non va cancellata. Se arriva, servirebbe solo per i quintetti: i punteggi si calcolano già da ESPN.
- **ESPN**: partite, tabellini, infortunati, roster (loucabot).
- **Basketball-Reference**: per_game giornaliero (bot principale), riserva per i tabellini.
- **NBA.com**: bloccato dal server (403).

---

## 9b. Dettagli tecnici e lezioni imparate

Cose che non stanno nelle guide e che servono quando qualcosa va storto.

**Database**
- I tipi ammessi in `transazioni` (e `cambi_ruolo`) li riallinea `migrate_db()` a ogni avvio con l'unione dei valori (`_allinea_check`): il DB di produzione era nato da uno schema più vecchio di `schema.sql`. Verifica: `SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname LIKE 'transazioni_tipo%'`.
- Registro unico (v3.10.0): per tornare indietro a un codice precedente bisogna prima `DELETE FROM transazioni WHERE oggetto IN ('pick','diritti')`. Al deploy di quella versione il bot aste andava fermato prima di avviare il principale (le righe nuove sarebbero state lette come giocatori).
- Migrazioni una tantum segnate nella tabella `migrazioni` (per esempio `rookie_pezzi_v3_11`: `stagione_firma` dei 66 contratti rookie dal II al IV anno portata alla stagione in corso).
- Dati corretti a mano o dalle migrazioni, da non "riscoprire" come anomalie: 2 tagli pre-bot staccati da Jokić (id 1, era usato come segnaposto); TRADE-2026-021 rimessa approvata; TRADE-2026-019 (Mitchell) e 029 (Powell/Miller), coi diritti che fino alla v3.0.4 non si spostavano; DPE di Mark Williams 9→6. I tagli gratuiti pre-bot sono transazioni `cut` con `gratuito = TRUE` e nota "avvenuto pre-bot".
- `giocatori.nome_common` è `TEXT`: in NocoDB è testo lungo e non fa da display value (si usa `yahoo_id`).

**Roster e assets PNG (Typst)**
- Sempre 15 righe, riempite con il flag `VUOTO`; flag `N` normale, `A` RFA, `R0`–`R3` rookie dal I al IV anno. DPE: nome in rosso scuro e importo originale barrato accanto al nuovo; leggenda solo per le cose presenti. Fantamedia nella colonna FM (`db.fantamedie`, con `as_of` per il roster a una data; `fm_label` in input). Badge bianchi sui colori con contrasto insufficiente (`_text_on_muted`). Typst gira con `--root /` per vedere i loghi.

**Dashboard NocoDB**
- Senza `NC_ALLOW_LOCAL_EXTERNAL_DBS=true` rifiuta gli host interni. Con SQLite come database interno la versione in uso va in timeout creando l'admin: per questo i suoi dati stanno nel database PostgreSQL `nocodb` (utente `nocodb`, niente CONNECT su `fantabasket`). Niente `NC_ADMIN_EMAIL/PASSWORD`: il primo che si registra è admin; nella CE un solo workspace, dentro una base con sorgente esterna PostgreSQL (utente `lettore`). Porta su tutte le interfacce ma nessun port forwarding (Docker scavalca ufw): LAN e Tailscale. `scripts/setup_dashboard.sh` è rilanciabile.

**Fogli Google**
- Una "Nuova versione" della web app tiene l'URL; un "Nuovo deployment" no. Il foglio Roster si sincronizza sempre per tutte le 24 squadre (decisione di Luca). Il bot aste non chiama il gas-router: accoda in `gas_sync_queue`.

**Yahoo e NBA**
- Yahoo: approvazione della Fantasy API con contratto (DocuSign), tempi riportati da una settimana a due mesi, email non affidabili: si verifica con `cli.py teams`. Prima di firmare leggere le clausole su conservazione e visualizzazione dei dati. Le leghe Yahoo sono due (la seconda contiene anche account admin da escludere nel mapping); i loro ID solo in `secrets/yahoo_router.env`.
- Posizioni eleggibili: CSV dalle pagine giocatori Yahoo (`yahoo_id;nome;team;posizioni`); dal secondo import l'abbinamento è per `yahoo_id` (i nomi accorciati di Yahoo non si salvano). Erminio conta da `data_yahoo` se impostata con `/data_erminio`, altrimenti dalla data della riga.
- NBA.com (cdn.nba.com) è bloccato da Akamai anche dalla rete di casa, browser compreso.

**Telegram**
- Il backup settimanale è il sabato alle 00:30: in PTB `days=(6,)` è sabato, 0 è domenica.
- I menu `/` degli admin compaiono solo per chi ha scritto almeno una volta al bot; quello del gruppo admin solo se il bot è nel gruppo.

---

## 10. Prove

PostgreSQL 16 locale, database `fbt` (utente `fb`), configurazione finta in `tests/config/` (4 squadre, admin 900), Telegram simulato. `tests/run.sh` lancia le 31 prove (bot principale, bot aste con e senza PG, loucabot, documentazione); `tests/run.sh nome` solo quelle. Le prove fanno `TRUNCATE`: `tests/guardia.py` le blocca sul server o su un database non locale, e sul server `run.sh` non è eseguibile. Dettagli: `tests/README.md`. Lo script Apps Script si prova simulando il foglio con node.

---

## 11. Da fare

**Prima dell'inizio della stagione (20/10/2026)**, in quest'ordine:
1. **IPanchinari in produzione**: token, canale, quintetti di partenza (script da console sulla pagina Yahoo: serve una pagina di esempio), qualche giro di prova con 2-3 GM prima del 20.
2. ~~Regole di calcolo complete~~ **fatto nella v5.1.0**: calcolo alle 7:45 coi definitivi dai quintetti congelati e dalle panchine, tab «Calcolo GN» sul foglio di controllo (formule che rifanno i conti del bot), proposta al gruppo admin con Convalida/Ricalcola, correzioni dal bot (`/set_valid_status`, `/quintetto_admin SQUADRA GN`, `/panchina_admin SQUADRA GN`, `/ricalcola N`), controllo dei tabellini alle 10:00, alla convalida `lega_risultati` e foglio Calendario. Deciso con Luca il 13/10: il foglio di controllo è un file a parte (`CALCOLO_SPREADSHEET_ID` in `gas/globals.gs`); le correzioni si fanno sempre dal bot, mai sul foglio; nella classifica media e differenza punti col bonus casa; sul Calendario punti col bonus casa e sotto i soli punti dei supplementari; senza panchina si gioca senza supplementari (avviso agli admin); il giocatore ceduto a giornata in corso conta per la vecchia squadra fino a fine giornata.
   - Deciso con Luca il 13/10: la media vale solo sulla stagione in corso; chi non ha ancora partite quando serve la media prende 0, mai la media della stagione prima (alla prima giornata non si prende nessuna media). È già così in `calcolo.punteggio_giocatori`.
3. ~~Classifica~~ **fatto nella v5.5.0** (`/classifica`, `/classifica_full`; Luca 16/10: colonne e statistiche). Classifica nel bot, `/classifica` come immagine Typst (parità: prima gli scontri diretti, se le squadre si sono già incontrate, poi i punti fatti (media) e la differenza punti, col bonus casa; ribadito da Luca il 13/10; con tre o più squadre a pari la classifica avulsa, cioè solo gli scontri diretti tra loro, e negli scontri diretti contano solo vittorie e sconfitte, mai lo scarto (Luca, 13/10); fa fede quella dei fogli). Da confermare: "indisponibile" = stato diverso da Probable nello snapshot che conta di ogni giorno della giornata (l'ultimo prima della prima partita).

**Dopo** (ordine deciso con Luca il 13/10: live e classifica, 10-day il prima possibile, poi playoff, draft e rinnovi)
- ~~Foglio Google pubblico di calcolo automatico~~: è il foglio di controllo del calcolo (tab «Calcolo GN»), per trasparenza verso i GM (Luca, 13/10). A fine stagione se ne fa un backup e si azzera.
- ~~Punteggio live~~ **fatto nella v5.3.0** (loucabot v18, `live.py`; deciso con Luca il 14/10: messaggio al tipoff della prima partita, ogni 10 minuti fino alle 8 del mattino, poi alle 10 — fatto alle 10:05, dopo il controllo dei tabellini; sotto provvisorio e ora dell'ultimo aggiornamento). Specifica di partenza (13/10): ESPN dà anche il live (scoreboard con stato e punteggio, `summary?event=ID` aggiornato durante la partita); con quintetti e panchine, fantapunti live delle squadre. Deciso con Luca il 13/10: **ogni 10 minuti**, **un solo messaggio sul canale principale modificato** ogni volta, con scritto l'ora dell'ultimo aggiornamento; si riscaricano solo lo scoreboard e i tabellini delle partite in corso (stima: una ventina di richieste ogni 10 minuti nelle notti piene, qualche centinaio a notte). Per non farsi limitare da ESPN: una richiesta alla volta con una pausa, mai le partite finite (quelle le scarica il job delle 8:30), e se ESPN risponde 429/403 si salta un giro e si allunga l'intervallo, con avviso sul canale log. I numeri live sono provvisori: fa fede il calcolo a partita finita e convalidato. Dopo i risultati ufficiali.
- Playoff: calendario generato dalla classifica; 72 ore delle partite rinviate.
- **Fonte dati di riserva** (se ESPN bloccasse o cambiasse gli indirizzi; Luca, 14/10: da tenere presente, per ora si resta su ESPN). Servono calendario con stato e orari, tabellini live per giocatore (tutte le voci della formula), status degli infortunati, id stabili dei giocatori. Uso stimato: qualche centinaio di richieste a notte. Candidati (prezzi da verificare sui siti): BALLDONTLIE (ALL-STAR ~10 $/mese con statistiche dei giocatori e infortuni, GOAT ~40 $/mese con i box score), API-NBA di API-Sports (Pro ~15 $/mese, 7.500 richieste al giorno, statistiche per partita, niente infortuni), MySportsFeeds (piano personale non commerciale economico, dati live nei piani alti), SportsDataIO e Sportradar (contratti B2B da centinaia di $/mese: fuori scala). Cambiare fonte = un modulo nuovo al posto di `loucabot/nba.py` e un abbinamento degli id come quello di ESPN (`giocatori.espn_id`).
- **Cambio di stagione di loucabot e IPanchinari** (verificato il 13/10: i dati sono già per stagione e niente cancella le stagioni passate; `lega_giornate`, `lega_partite`, `lega_risultati`, `lega_calendario_csv`, `ipa_panchine`, `ipa_formazioni`, `ipa_conferme` per `stagione`; `nba_partite` con la stagione da ESPN, 2027 → 2026; tabellini e snapshot degli infortuni per partita e giorno). Da fare: una procedura scritta (quando `stagione_corrente` cambia ai rinnovi: import del CSV della stagione nuova, `/nba_sync` quando ESPN pubblica il calendario, `/espn_mancanti` per rookie e nuovi, quintetti da ricaricare con `/quintetti_import`), una prova completa del passaggio sulla copia del database, e fogli (deciso con Luca il 13/10): **il foglio Calendario resta sempre lo stesso** e si riscrive col calendario nuovo (è il comportamento di oggi); **il foglio di controllo del calcolo** a fine stagione si salva (backup) e si azzera (da fare: comando o passo della procedura).
- Draft, con la lottery dallo script di Henry (`Lottery.py` del suo repo), e **rinnovi normali** (x1 ed ex rookie x0: max 2, +¼ e +½ per eccesso, minimo da `tabella_minimo_contratto`, x2/x3): entro giugno 2027.
- ~~10-day contract~~ **fatto nella v5.2.0** (`handlers/dieci_giorni.py`). Deciso con Luca il 13/10: il GM chiede e l'admin approva (nel messaggio le regole), l'admin può firmarlo direttamente per qualsiasi squadra; solo in `regular-season-fa`, quelli già firmati finiscono anche dopo; decade all'ufficialità (convalida) dell'ultima giornata in cui era in squadra (Luca, 14/10); su IPanchinari e nel calcolo come gli altri; nel foglio Roster e su Typst con un colore suo. Scelte mie, approvate da Luca il 14/10: durante il 10-day il giocatore non è un free agent (niente aste su di lui) e non si firma con un'asta aperta; non si taglia, non si scambia, niente DPE (un admin lo può chiudere prima dal pannello); non conta per i minimi dei ruoli; nel roster Typst il 10-day e le DPE che liberano lo slot stanno sotto le 15 righe, dopo una riga più spessa; nel foglio Roster il 10-day va sotto le DIS.
- Rookie: `rookie.team_id` dei firmati non segue le trade, `rookie.pick_numero` senza legame con le pick (proposta `rookie.pick_id`), campo mai usato `rookie.scadenza_diritti` (`contratti.scadenza_10day` e il tipo `10day` li usa il 10-day dalla v5.2.0). Da sistemare insieme al draft.
- Votazione GM delle trade da provare dall'inizio alla fine; guest mode in attesa del supporto di python-telegram-bot.
- Luca aggiorna il testo del regolamento (luxury, Stepien, RFA in trade, floor: testi in `docs/regolamento_e_codice.md`).
- Una stagione intera di prova.

**Futuro lontano** (idee di Luca, 14/10: nessuna fretta)
- **Assistente `/chiedi`**: risponde a domande su regolamento e bot e indirizza al comando o al bot giusto. Base: ricerca locale nelle sezioni di regolamento e guide (gira sul M910q senza consumare, risponde sempre con la fonte). Sopra, se gratis: un'API gratuita (Groq o Cerebras: limiti giornalieri ampi per una lega, niente addestramento sui dati; **non** Gemini gratis, che usa i dati e per gli utenti UE consente solo il piano a pagamento) che riscrive la risposta solo dai pezzi trovati; se l'API non risponde, la sola ricerca. Modellino locale (Ollama, 2-4B) solo come ultima spiaggia: sul M910q lento e impreciso sui dettagli. Per le decisioni rimanda sempre agli admin.
- **Bot delle statistiche**: ora che nel database ci sono tabellini, fantapunti, formazioni, panchine, risultati e movimenti, statistiche per giocatore, squadra e stagione (migliori e peggiori, rendimento dei panchinari e delle FADD, scontri diretti, andamento, quanto rende un contratto per milione, eccetera), magari con immagini Typst come il roster.
  - **`/carriera GIOCATORE`** (il pallino di Luca): la grafica in stile Transfermarkt ma coi loghi delle squadre del fantabasket. La carriera nella lega: squadre, contratti (importo e anni), firme, trade, tagli, rinnovi, DPE, 10-day, rookie, con le date; dai movimenti del registro (`transazioni`), che dal 25 luglio sono dati veri. Accanto, la carriera NBA reale. Immagine Typst come roster e asset, loghi da `assets/`.
- **Dashboard in LAN per Luca** (solo LAN/Tailscale, nessuna porta aperta sul router): interfacce comode e curate per le cose che coi bot sono macchinose (quintetti e controlli, correzioni di formazioni e panchine, status validi, convalida e ricalcolo, 10-day, situazione cap e roster, stato dei job e dei rilasci). Oggi c'è NocoDB in sola lettura (`nocodb`, di solito spenta): la dashboard nuova sarebbe una web app sua, che scrive passando dalle stesse funzioni dei bot (stesse regole e controlli, log sul canale).

---

## Esportazione per una sessione nuova

```bash
cd ~/bots/fantabasket-progettone && \
zip -r ~/fantabasket-progettone-export-$(date +%Y%m%d).zip \
  fantabasket-main/ fantabasket-aste-beta/ fantabasket-loucabot/ fantabasket-ipanchinari/ \
  gas/ gas-router/ yahoo-router/ shared/ tests/ docs/ scripts/ \
  docker-compose.yml README.md \
  --exclude "**/__pycache__/*" --exclude "**/*.pyc" --exclude "**/*.db" \
  --exclude "secrets/*" --exclude "config/*" \
  --exclude "gas/globals.gs" --exclude "gas/.clasp.json" \
  --exclude "fantabasket-main/config/*" --exclude "fantabasket-aste-beta/config/*"
```

# Guida dev — IPanchinari

Promemoria tecnico di IPanchinari. Panoramica e messa in funzione nel `README.md` della cartella, storia nel `CHANGELOG.md`. Da Telegram: `/guida_dev` (solo dev).

---

## 1. Dove sta

Servizio `ipanchinari` del `docker-compose.yml`, cartella `fantabasket-ipanchinari/`. Ambiente: `BOT_TOKEN_FILE` (`secrets/bot_token_ipanchinari.txt`), `DATABASE_URL` + `PG_PASSWORD_FILE`, `GLOBALS_PATH`, `TEAMS_PATH`; `config/` in sola lettura, `shared/` in `/app/shared` (`shared.squadre`, `shared.messaggi.manda_lungo`). Chiavi di `globals.json`: `canale_panchinari_id`, `log_channel_id_ipa`, più quelle comuni (`stagione_corrente`, `admin_ids`, `dev_id`, `admin_group_id`).

Moduli: `abbina.py` (testo → righe → giocatori), `panchine.py` (flusso della panchina), `quintetti.py` (quintetti, job), `soprannomi.py` (`/soprannomi`), `cessioni.py` (avvisi di trade e tagli), `comune.py`, `handlers.py`, `comandi.py`, `db.py`, `config.py`.

## 2. Database

Legge: `contratti`, `giocatori` (anche `espn_id`), `ruolo_attuale` (bot principale); `lega_giornate` (scadenza = `prima_partita`, squadre a media), `nba_partite`, `nba_tabellini`, `nba_atleti` (loucabot). Scrive solo `ipa_*`:

| Tabella | Chiave | Cosa |
|---|---|---|
| `ipa_quintetto` | team_id, ruolo | il quintetto attuale, `fonte` gm/admin/import |
| `ipa_formazioni` | stagione, giornata, team_id, ruolo | il quintetto congelato alla scadenza: **è quello che usa il calcolo** |
| `ipa_panchine` | stagione, giornata, team_id | titolo, `righe` JSON `[{giocatore_id, testo}]` in ordine, chi, fonte, messaggio sul canale |
| `ipa_alias` | team_id, alias (+ `id` per i bottoni) | riga normalizzata → giocatore (si impara alla pubblicazione, tranne il nome vero). `team_id` = chi l'ha scritto: l'abbinamento usa i soprannomi dei giocatori della rosa di oggi chiunque li abbia scritti (seguono il giocatore), a parità vincono quelli della squadra |
| (`ipa_panchine`) | | in più `canale_id` (il canale del messaggio: si modifica solo se è quello di oggi, perché gli id dei messaggi sono per canale), `da_nome`, `versioni` |
| `ipa_cessioni` | team_id, giocatore_id, dove | avvisi di cessione già mandati (`quintetto`, `panchina GN`, `formazione GN`); si cancellano se il giocatore torna |
| `ipa_bozze` | id | panchine in attesa di conferma (sopravvivono ai riavvii; i bottoni portano l'id) |
| `ipa_conferme` | stagione, giornata, team_id | confermato / modificato (anche dall'admin, `da` = chi) |
| `ipa_controlli` | stagione, giornata, team_id | formazione congelata controllata su Yahoo da un admin: `da`, `da_nome`, `quando` (v18) |
| `ipa_stato_giornata` | stagione, giornata | quando sono partiti promemoria, riepilogo e chiusura (una volta sola) |

## 3. Abbinamento (`abbina.py`)

`leggi_messaggio`: blocchi separati da righe vuote; l'ultimo è la panchina (massimo 5 righe: se di più, le prime sono titolo), quelli prima sono il titolo; numerazione (`1.`, `2)`, `-`, `•`) tolta. `parole`: minuscole senza accenti (anche Đ, ø, ł), senza apostrofi e punti. Punteggio di un giocatore per una riga: parole del nome separate da spazi (un nome col trattino è una parola sola, riconosciuta da uno dei suoi pezzi), cognome peso 2, somiglianza per parola 1 uguale, 0,85 difflib ≥ 0,8, 0,7 prefisso di almeno 3 lettere, 0,4 iniziale; iniziali di tutto il nome (SGA) → 0,9; si prova su `nome_common`, `nome_bref`, `nome_yahoo`, `nome_espn`. Certo se ≥ `SOGLIA` (0,55) e stacca il secondo di `STACCO` (0,15); senza candidati, il solo nome di battesimo di un giocatore, anche scritto male o accorciato (somiglianza ≥ 0,7: "Herbet", "Herb"). Un alias (`db.alias(team, ids rosa)`) vince su tutto. `abbina_panchina` toglie dai candidati delle righe dubbie i giocatori già presi. Righe ripetute nella stessa panchina (`abbina.ripetute`, confronto sulle righe normalizzate): `crea_bozza` rifiuta il messaggio ("Righe duplicate"), `problemi` blocca la pubblicazione (soprannomi uguali in CAI mode); per sicurezza non usano e non creano alias.

## 4. Flussi

**Panchina** (`panchine.py`): messaggio privato di testo di un GM con almeno 2 righe → `crea_bozza` (meno di 5 righe: rifiutata, la panchina è sempre di `MAX_PANCHINA` = 5) (giornata = `comune.prossima_giornata`: la prima con `prima_partita` futura) → anteprima con bottoni `pb:*` → `pubblica`: ricontrolla scadenza e `problemi` (bloccano: righe diverse da 5, non a roster, doppioni); `avvisi` (titolare nel quintetto del bot: fa fede Yahoo) non bloccano, vanno al GM e al log; scrive sul canale (`testo_canale`: righe del GM e in fondo "✍️ GM" o "✍️ admin Nome" con data e ora, "inserita" o "🔁 ultima modifica"; `_scrivi_canale`: se la squadra ha già la panchina della giornata modifica quel messaggio, `messaggio_canale`; uno nuovo solo se il vecchio non si può modificare), salva panchina e alias, chiude la bozza, riga sul log.

**Correzione a giornata chiusa** (`/panchina_admin SQUADRA GN`): `crea_bozza`/`apri_builder` con `numero` (`_giornata_correzione`: la giornata deve essere chiusa), `dati.correzione` = True: `pubblica` salta il controllo della scadenza e dopo il salvataggio `db.congela_ruoli_panchine` per quella squadra; riga sul log con l'invito a `/ricalcola N` su loucabot. Alla chiusura (`job_giornate`) `db.congela_ruoli_panchine` scrive in ogni riga delle panchine della giornata il `ruolo` di `ruolo_attuale` di quel momento (lo usa la FADD del calcolo).

**Builder** (`/build_panchina`, `panchine.builder`): bozza con `righe` vuote e `builder: True`; `pb:b` aggiunge (solo roster meno titolari meno già scelti; i titolari, ⭐, solo se non ne restano abbastanza per arrivare a 5), `pb:u` toglie l'ultimo, al quinto si passa all'anteprima normale (non c'è un'anteprima prima: `pb:bv` resta solo per i bottoni vecchi); il testo di ogni riga è il nome del giocatore. **CAI mode** (`pb:cai`, dall'anteprima del builder): `dati.cai_passo` 0 = titolo, i = soprannome della riga i; le risposte arrivano come messaggi (`msg_panchina` → `risposta_cai` se `db.bozza_cai` trova una bozza in CAI mode delle ultime 6 ore e il messaggio ha meno di 3 righe; altrimenti la chiude ed è una panchina nuova); `pb:cs` salta, `pb:cf` finisce. I soprannomi diventano alias alla pubblicazione.

**Quintetto coi bottoni** (`/quintetto`, `/quintetto_admin SQUADRA` senza righe): callback con la squadra `q:<azione>:<team>:…`; il GM agisce sulla sua, un admin su tutte (fonte admin, e se c'è una giornata in corso già chiusa aggiorna anche la sua formazione). `/panchina_admin SQUADRA` senza righe → `apri_builder` con `fonte = admin`.

**Quintetto** (`quintetti.py`): `leggi_quintetto` (admin e import: righe con o senza ruolo, ruolo = quello di roster), `/quintetto` con bottoni `q:*` (solo giocatori del ruolo), conferma `q:ok:N` valida fino alla scadenza della giornata N. `incompatibilita`: ruoli vuoti, titolari non a roster o in altro ruolo, titolari nella panchina della prossima giornata. `/quintetto_admin` anche a giornata in corso: aggiorna il quintetto e la formazione della `comune.giornata_in_corso` (se già chiusa); con `GN` solo `db.salva_formazione` della giornata N (deve essere chiusa). Le correzioni a giornata chiusa segnano la formazione controllata (`db.segna_controllo`). `/controlli [N]` (`testo_controlli`, callback `ck:<N>:<team>` e `ck:<N>:-`; giornata di default `giornata_da_controllare`: quella in corso se chiusa, se no l'ultima chiusa); nell'editor admin `q:ok` (conferma per conto del GM) e `q:ck:<team>:<N>`.

**`/ripubblica_panchine [N]`** (`panchine.ripubblica`, in un task per non bloccare il bot): manda di nuovo tutte le panchine salvate della giornata sul canale di oggi (`testo_da_salvata`: chi, quando, "🔁 ultima modifica" se `versioni` > 1), una ogni `PAUSA_CANALE` secondi (RetryAfter: aspetta e riprova), e segna `messaggio_canale`/`canale_id` (`db.segna_messaggio`).

**`/quintetti [N]`** (`quintetti.testo_quintetti`): una riga per squadra da `ipa_quintetto`, o con N da `ipa_formazioni` (solo giornate chiuse); ⚠️ se il giocatore non è più a roster.

**Soprannomi** (`soprannomi.py`): `/soprannomi` (la propria squadra) o `/soprannomi SQUADRA` (GM: solo testo, `schermata(modifica=False)`; admin: coi bottoni), elenco per giocatore della rosa con chi li ha scritti, bottoni `so:d:<team>:<id>:<pagina>` per cancellare (10 per pagina, `so:p`), riga sul log.

**Cessioni** (`cessioni.py`, `job_cessioni` ogni 5 minuti): per ogni squadra confronta con la rosa il quintetto, la panchina della prossima giornata e formazione e panchina della giornata in corso (se chiusa); per ogni giocatore uscito avviso ai GM (con la squadra nuova, `db.squadra_attuale`) e riga sul log, una volta sola (`ipa_cessioni`).

**Stato ESPN** (`comune.stati`, `db.stati_espn`): dall'ultimo snapshot di `nba_infortuni` di loucabot (ogni 4 ore e prima delle partite) via `giocatori.espn_id`; bottoni del builder e di `pb:r`/`pb:t`, anteprima, scelta del ruolo nel quintetto, `testo_quintetto` (promemoria). Senza snapshot non mostra niente.

Il testo "non è obbligatorio, fa fede Yahoo, è un favore agli admin" sta in `comune.FAVORE`: va in ogni messaggio che invita ad aggiornare il quintetto.

**Job** `job_giornate` ogni 5 minuti, per ogni giornata con scadenza: scaduta e non chiusa → `congela_quintetti` + avviso al gruppo admin; altrimenti promemoria a `comune.ora_promemoria` (le 8:00 Roma dell'ultimo giorno prima della scadenza) e riepilogo 2 ore prima, ognuno una volta sola (`ipa_stato_giornata`).

## 4b. Comandi dev

Solo per `dev_id`, nel menu `/` del dev.

| Comando | Cosa fa |
|---|---|
| `/dev` | l'elenco dei comandi dev |
| `/guida_dev` | questa guida, come file |
| `/dev_version` | versione (ultima voce del CHANGELOG) |
| `/job_status` | job programmati (giornate e cessioni, ogni 5 minuti) |
| `/dev_promemoria [SQUADRA]` | il promemoria della prossima giornata mandato solo a te, con quando partirà davvero e a quanti GM; i bottoni funzionano (per provarlo prima del giorno vero) |
| `/dev_log [N]` | ultime N righe di log in memoria (30, massimo 100) |
| `/dev_pg` | connessione a PostgreSQL (versione) |
| `/reboot` | riavvia il bot (il processo esce, Docker lo fa ripartire) |

`/dev_log`, `/dev_pg` e `/reboot` sono in `shared/dev_comune.py`, uguali in loucabot.

**Errori non gestiti** (`dev_comune.error_handler`): log del container, poi canale log e dev col tipo di errore, chi e quale bottone o comando. "Message is not modified" (un bottone premuto due volte, stesso testo) non si segnala; gli errori di rete vanno solo sul canale log, per accorgersi se il bot non raggiunge Telegram.

## 5. Prove

`tests/run.sh ipa_panchine` (mai sul server). Crea le tabelle di loucabot col suo `db.py`, giocatori e contratti di prova (puliti alla fine), Telegram finto. Copre messaggio coi soprannomi, canale senza nomi veri, alias, panchina di 5 obbligatoria, `/soprannomi` e cancellazione, soprannomi che seguono il giocatore, avvisi di cessione, aggiornamento, controlli, quintetti (admin, import, bottoni, conferma), promemoria, riepilogo, chiusura, scadenza durante la conferma.

## 6. Da fare

Script da console per i quintetti Yahoo (serve una pagina di esempio); calcolo dei risultati in loucabot da `ipa_formazioni` e `ipa_panchine`.

# Guida dev — IPanchinari

Promemoria tecnico di IPanchinari. Panoramica e messa in funzione nel `README.md` della cartella, storia nel `CHANGELOG.md`. Da Telegram: `/guida_dev` (solo dev).

---

## 1. Dove sta

Servizio `ipanchinari` del `docker-compose.yml`, cartella `fantabasket-ipanchinari/`. Ambiente: `BOT_TOKEN_FILE` (`secrets/bot_token_ipanchinari.txt`), `DATABASE_URL` + `PG_PASSWORD_FILE`, `GLOBALS_PATH`, `TEAMS_PATH`; `config/` in sola lettura, `shared/` in `/app/shared` (`shared.squadre`, `shared.messaggi.manda_lungo`). Chiavi di `globals.json`: `canale_panchinari_id`, `log_channel_id_ipa`, più quelle comuni (`stagione_corrente`, `admin_ids`, `dev_id`, `admin_group_id`).

Moduli: `abbina.py` (testo → righe → giocatori), `panchine.py` (flusso della panchina), `quintetti.py` (quintetti, job), `comune.py`, `handlers.py`, `comandi.py`, `db.py`, `config.py`.

## 2. Database

Legge: `contratti`, `giocatori` (anche `espn_id`), `ruolo_attuale` (bot principale); `lega_giornate` (scadenza = `prima_partita`, squadre a media), `nba_partite`, `nba_tabellini`, `nba_atleti` (loucabot). Scrive solo `ipa_*`:

| Tabella | Chiave | Cosa |
|---|---|---|
| `ipa_quintetto` | team_id, ruolo | il quintetto attuale, `fonte` gm/admin/import |
| `ipa_formazioni` | stagione, giornata, team_id, ruolo | il quintetto congelato alla scadenza: **è quello che usa il calcolo** |
| `ipa_panchine` | stagione, giornata, team_id | titolo, `righe` JSON `[{giocatore_id, testo}]` in ordine, chi, fonte, messaggio sul canale |
| `ipa_alias` | team_id, alias | riga normalizzata → giocatore (si impara alla pubblicazione) |
| `ipa_bozze` | id | panchine in attesa di conferma (sopravvivono ai riavvii; i bottoni portano l'id) |
| `ipa_conferme` | stagione, giornata, team_id | confermato / modificato |
| `ipa_stato_giornata` | stagione, giornata | quando sono partiti promemoria, riepilogo e chiusura (una volta sola) |

## 3. Abbinamento (`abbina.py`)

`leggi_messaggio`: blocchi separati da righe vuote; l'ultimo è la panchina (massimo 5 righe: se di più, le prime sono titolo), quelli prima sono il titolo; numerazione (`1.`, `2)`, `-`, `•`) tolta. `parole`: minuscole senza accenti (anche Đ, ø, ł), senza apostrofi e punti. Punteggio di un giocatore per una riga: parole del nome separate da spazi (un nome col trattino è una parola sola, riconosciuta da uno dei suoi pezzi), cognome peso 2, somiglianza per parola 1 uguale, 0,85 difflib ≥ 0,8, 0,7 prefisso di almeno 3 lettere, 0,4 iniziale; iniziali di tutto il nome (SGA) → 0,9; si prova su `nome_common`, `nome_bref`, `nome_yahoo`, `nome_espn`. Certo se ≥ `SOGLIA` (0,55) e stacca il secondo di `STACCO` (0,15); senza candidati, il solo nome di battesimo di un giocatore, anche scritto male o accorciato (somiglianza ≥ 0,7: "Herbet", "Herb"). Un alias della squadra vince su tutto. `abbina_panchina` toglie dai candidati delle righe dubbie i giocatori già presi.

## 4. Flussi

**Panchina** (`panchine.py`): messaggio privato di testo di un GM con almeno 2 righe → `crea_bozza` (giornata = `comune.prossima_giornata`: la prima con `prima_partita` futura) → anteprima con bottoni `pb:*` → `pubblica`: ricontrolla scadenza e `problemi` (bloccano: non a roster, doppioni); `avvisi` (titolare nel quintetto del bot: fa fede Yahoo) non bloccano, vanno al GM e al log; manda sul canale (in risposta alla precedente se c'era), salva panchina e alias, chiude la bozza, riga sul log.

**Builder** (`/build_panchina`, `panchine.builder`): bozza con `righe` vuote e `builder: True`; `pb:b` aggiunge (solo roster meno titolari meno già scelti, massimo 5), `pb:u` toglie l'ultimo, `pb:bv` (o al quinto) passa all'anteprima normale; il testo di ogni riga è il nome del giocatore. **CAI mode** (`pb:cai`, dall'anteprima del builder): `dati.cai_passo` 0 = titolo, i = soprannome della riga i; le risposte arrivano come messaggi (`msg_panchina` → `risposta_cai` se `db.bozza_cai` trova una bozza in CAI mode delle ultime 6 ore e il messaggio ha meno di 3 righe; altrimenti la chiude ed è una panchina nuova); `pb:cs` salta, `pb:cf` finisce. I soprannomi diventano alias alla pubblicazione.

**Quintetto coi bottoni** (`/quintetto`, `/quintetto_admin SQUADRA` senza righe): callback con la squadra `q:<azione>:<team>:…`; il GM agisce sulla sua, un admin su tutte (fonte admin, e se c'è una giornata in corso già chiusa aggiorna anche la sua formazione). `/panchina_admin SQUADRA` senza righe → `apri_builder` con `fonte = admin`.

**Quintetto** (`quintetti.py`): `leggi_quintetto` (admin e import: righe con o senza ruolo, ruolo = quello di roster), `/quintetto` con bottoni `q:*` (solo giocatori del ruolo), conferma `q:ok:N` valida fino alla scadenza della giornata N. `incompatibilita`: ruoli vuoti, titolari non a roster o in altro ruolo, titolari nella panchina della prossima giornata. `/quintetto_admin` anche a giornata in corso: aggiorna il quintetto e la formazione della `comune.giornata_in_corso` (se già chiusa); con `GN` solo `db.salva_formazione` della giornata N (deve essere chiusa).

**Job** `job_giornate` ogni 5 minuti, per ogni giornata con scadenza: scaduta e non chiusa → `congela_quintetti` + avviso al gruppo admin; altrimenti promemoria a `comune.ora_promemoria` (le 8:00 Roma dell'ultimo giorno prima della scadenza) e riepilogo 2 ore prima, ognuno una volta sola (`ipa_stato_giornata`).

## 5. Prove

`tests/run.sh ipa_panchine` (mai sul server). Crea le tabelle di loucabot col suo `db.py`, giocatori e contratti di prova (puliti alla fine), Telegram finto. Copre messaggio coi soprannomi, canale senza nomi veri, alias, aggiornamento, controlli, quintetti (admin, import, bottoni, conferma), promemoria, riepilogo, chiusura, scadenza durante la conferma.

## 6. Da fare

Script da console per i quintetti Yahoo (serve una pagina di esempio); calcolo dei risultati in loucabot da `ipa_formazioni` e `ipa_panchine`.

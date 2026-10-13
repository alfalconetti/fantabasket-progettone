# IPanchinari

Il bot delle **panchine** e dei **quintetti** della lega. Le panchine si scrivono come sempre,
soprannomi compresi: il bot capisce chi sono e le pubblica sul canale Panchinari così come le ha
scritte il GM. I quintetti non si reinseriscono a ogni giornata: restano, e si confermano dal
promemoria. Il calcolo dei punteggi (loucabot) userà quintetti e panchine da qui.

Fa parte del progettone: stesso PostgreSQL e stessa `config/` degli altri bot (in sola lettura),
moduli condivisi in `../shared/`. Legge roster e ruoli del bot principale e giornate e partite NBA
di loucabot; scrive solo le sue tabelle (`ipa_*`).

Sviluppato con [Claude](https://claude.ai) (Anthropic).

## Messa in funzione (una volta)

1. Su Telegram, da @BotFather crea il bot (comando newbot) e copia il token.
2. Sul server, dalla cartella del progettone, **prima del deploy**:
   ```bash
   read -rs T && printf '%s' "$T" > secrets/bot_token_ipanchinari.txt; unset T
   chmod 600 secrets/bot_token_ipanchinari.txt && bash scripts/cifra_secrets.sh
   ```
   `deploy.sh` controlla che ci siano i file di `secrets/` richiesti dal compose e si ferma se ne manca uno.
3. In `config/globals.json`:
   - `"canale_panchinari_id"`: il canale Panchinari, con il bot amministratore che può pubblicare;
   - `"log_channel_id_ipa"` (facoltativo): canale log suo; senza, quello del bot principale.
   Il bot va anche nel gruppo admin (riepiloghi e chiusure).
4. I quintetti di partenza: `/quintetti_import` (tutte le squadre) o `/quintetto_admin` squadra per squadra.
5. Ogni GM deve scrivere una volta al bot (`/start`), sennò il bot non può mandargli il promemoria.

## Come funziona

**Panchina.** Il GM manda in privato le righe dei panchinari, una per riga, in ordine; un titolo,
se vuole, sopra, separato da una riga vuota (se le righe sono più di 5, le prime sono il titolo).
Esempio:

```
No Buffalo Brownies

Ja the sniper Morant
Dominik Arcade Boy Barlow
Walter White Clayton jr
Nique il califfo Clifford
Kevon the champ Looney
```

Il bot cerca solo tra i giocatori della squadra: conta le parole del nome che compaiono nella riga
(il cognome vale doppio), tollera errori di battitura, nomi col trattino, iniziali (SGA, KAT) e il
solo nome di battesimo se è di un giocatore solo. Mostra al GM l'anteprima coi nomi veri; le righe
dubbie si scelgono coi bottoni e il bot se le ricorda per quella squadra. Alla conferma, sul canale
escono **solo le righe come le ha scritte il GM** e il titolo. Vale per la prossima giornata la
cui scadenza (prima partita NBA) non è passata; si può rimandare fino alla scadenza, e sul canale
si modifica il messaggio di prima. Non si pubblica se: un giocatore non è della squadra, è due volte, o la
scadenza è passata. Un panchinaro che nel bot è titolare non blocca (per il quintetto fa fede
Yahoo): avviso al GM e riga sul canale log.

**Quintetto.** Un giocatore per ruolo (PG, SG, SF, PF, C), nel suo ruolo di roster. Lo caricano gli
admin; i GM lo cambiano con `/quintetto`. **Alle 8:00** (ora italiana) dell'ultimo giorno prima della
prima partita della giornata (la mattina prima se si gioca di notte) ogni GM riceve il quintetto,
le partite di ogni titolare nella giornata e i bottoni **Confermo** / **Modifico**, validi fino
alla scadenza. Incompatibilità (titolare non più in squadra, in un altro ruolo, anche in panchina,
ruolo vuoto) segnalate al GM e agli admin.

**Admin.** 2 ore prima della scadenza il gruppo admin riceve il riepilogo: chi ha confermato, chi ha
modificato, chi niente (quintetti da controllare su Yahoo), chi non ha mandato la panchina.
`/stato` lo mostra quando si vuole. Alla scadenza i quintetti si congelano (sono quelli della
giornata per il calcolo) e al gruppo admin va l'elenco delle panchine mancanti.

## Comandi

| Comando | Chi | Cosa |
|---|---|---|
| (messaggio con le righe) | GM | la panchina della prossima giornata |
| `/build_panchina` | GM | la panchina coi bottoni: un panchinaro alla volta, solo giocatori non nel quintetto; con 😎 CAI mode titolo e soprannomi, sennò sul canale i nomi |
| `/panchina` | GM | la panchina mandata, coi nomi veri |
| `/quintetto` | GM | il quintetto: cambialo o confermalo |
| `/start`, `/guida` | tutti | come si usa, la guida (file) |
| `/stato [N]` | admin | conferme e panchine di una giornata |
| `/quintetto_admin SQUADRA [GN]` | admin | senza righe il quintetto coi bottoni (parte dall'attuale), o sotto i 5 titolari (con o senza ruolo davanti); anche a giornata in corso; con GN corregge la formazione della giornata N |
| `/quintetti_import` | admin | tutte le squadre: nome esatto o id, poi 5 titolari; squadre separate da una riga vuota (anche file .txt) |
| `/panchina_admin SQUADRA` | admin | la panchina per conto di una squadra: senza righe col builder (e CAI mode), o le righe sotto |
| `/guida_admin` | admin | la guida admin (file) |
| `/dev`, `/guida_dev`, `/dev_version`, `/job_status` | dev | comandi dev |

## File

| File | Contenuto |
|---|---|
| `bot.py` | avvio, handler, job ogni 5 minuti, errori al canale log e al dev |
| `comandi.py` | menu `/` per scope: privato, admin, dev |
| `abbina.py` | lettura del messaggio e abbinamento delle righe ai giocatori |
| `panchine.py` | messaggio del GM, anteprima, bottoni, pubblicazione sul canale |
| `quintetti.py` | quintetti (admin, import, `/quintetto`), promemoria, riepilogo, chiusura |
| `comune.py` | giornata di riferimento, orari, partite dei giocatori, canale log |
| `handlers.py` | `/start`, guide, comandi dev |
| `db.py` | PostgreSQL: tabelle `ipa_*` e letture dagli altri bot |
| `config.py` | `globals.json` e `teams.json` in sola lettura, versione dal CHANGELOG |
| `docs/` | `guida_gm.md`, `guida_admin.md`, `guida_dev.md` |

Prova: `tests/run.sh ipa_panchine`.

## Da fare

- script da console per scaricare i quintetti da Yahoo nel formato di `/quintetti_import`;
- calcolo dei risultati in loucabot con `ipa_formazioni` e `ipa_panchine`.

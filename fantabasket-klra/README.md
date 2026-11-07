# klra

loucabot coi sistemi di punteggio alternativi (Luca, 04/11/2026). Stesso calendario, stesse formazioni congelate e
panchine di IPanchinari, stessi tabellini ESPN; regole diverse. I risultati ufficiali restano quelli di loucabot.

## Separazione dai dati della lega

È la regola numero uno (Luca: «la separazione deve essere assoluta e non rischiare mai»), garantita da PostgreSQL:

- **database `klra`** suo, proprietario l'utente `klra`: tabelle `klra_sistemi`, `klra_scelte`, `klra_bozze`, `klra_risultati`;
- **sul database della lega** l'utente `klra` ha solo `SELECT` sulle tabelle elencate in `setup_db.sql`, nessun altro
  permesso (non può scrivere né creare tabelle), e `default_transaction_read_only` acceso; in più il bot apre ogni
  sessione in sola lettura (`klra/basi.py`). Una tabella nuova della lega klra non la vede finché non la si aggiunge
  all'elenco;
- **due connessioni distinte** nel codice (`basi.apri_ufficiale`, `basi.apri_klra`), container, token e canale log
  suoi; non scrive sul foglio Calendario né sui canali della lega.

`setup_db.sql` lo esegue `deploy.sh` come superutente prima di ogni avvio di klra (si può rilanciare). La prova
`tests/klra/klra_motore.py` controlla che INSERT, UPDATE, DELETE, CREATE e le tabelle fuori elenco siano rifiutati.

## Come calcola

`klra/motore.py` usa il codice di calcolo di loucabot (montato in sola lettura in `/louca`): stessi quintetti, panchine,
medie, snapshot, decisioni degli admin, ceduti e FADD. Quattro funzioni di loucabot sono sostituite da versioni che
guardano il sistema del calcolo in corso (una ContextVar: senza sistema si comportano come in loucabot). Si calcolano
solo le giornate **convalidate** dalla lega; i risultati vanno in cache per firma dei parametri e si rifanno se la
giornata viene riconvalidata. Un job ogni ora porta avanti la cache di tutti i sistemi.

Il sistema **Ufficiale** legge le regole di adesso da `config/settings.json`. C'è anche un predefinito, **Fantamedie** (Luca, 04/11): chi ha giocato nella giornata prende la sua media della stagione fino al giorno prima, invece dei punti delle partite (se quest'anno non ha ancora giocato, la fantamedia dell'anno prima: dai tabellini ESPN se ci sono, se no da basketball-reference, `bref_stats`; se no 0); chi non ha giocato come nella lega; il resto come l'Ufficiale (voce «Chi gioca prende» della sezione Partita, che si può usare in ogni sistema). I predefiniti non li modifica nessuno, si copiano. Dalla v2 c'è anche **Fantapanchine** (Luca, 05/11): il totale della squadra è la somma dei punti effettivi dei panchinari, vince chi fa di più, niente supplementari (voce «Nel totale contano: titolari / panchina / tutti»). I predefiniti stanno in `regole.PREDEFINITI` (nome, modifiche alle regole della lega, descrizione) e `basi.migra` li crea. Un sistema nuovo nasce sempre come copia
di un altro, qualsiasi; **solo chi l'ha creato** lo modifica, gli altri lo modificano facendone una copia (Luca, 04/11);
nessun limite di numero. Se cambia, i risultati si rifanno da soli (cache per firma dei parametri). `/klra_verifica` (dev) controlla che l'Ufficiale
di klra dia esattamente i risultati convalidati.

Cosa si può cambiare: `klra/regole.py` (pesi di 14 statistiche, 13 bonus del giocatore e il tetto, 3 bonus di squadra,
bonus casa, scarto, supplementari / pareggio / chi fa di più, pari finale, FADD, chi non gioca, panchinari, classifica
a vittorie o a punti).

## Comandi (per GM, admin e dev)

| Comando | Cosa fa |
|---|---|
| `/sistemi` | la lista; la scheda di ogni sistema (cosa cambia rispetto all'Ufficiale) con Usa questo, Copia e modifica, Modifica (solo chi l'ha creato), Classifica, Confronta, Risultati |
| `/usa NOME` | il tuo sistema attivo (di default l'Ufficiale) |
| `/classifica [NOME]` | immagine, con P (pareggi) e PT (classifica a punti) se servono |
| `/giornata [N] [NOME]` | il tabellone (live.typ di loucabot, etichetta KLRA) |
| `/partita [SQUADRA] [N] [NOME]` | la sfida (partita.typ di loucabot) coi bonus accanto ai punti (es. +5 TD) e i bonus di squadra nelle note |
| `/risultati [N] [NOME]` | in testo, 🔄 dove finisce diversamente dalla realtà |
| `/confronta [NOME]` | classifica col sistema accanto all'ufficiale (▲▼) e le partite che cambiano esito |
| `/top [N] [DA A] [firmati] [NOME]` | come /top di loucabot (minimo 40% delle partite) con la fantamedia del sistema; tra parentesi quella della lega e la posizione nella top vera |
| `/calendario`, `/calendario_full`, `/classifica_full`, `/classifica_conference` | quelli di loucabot, uguali, coi risultati del sistema (v2: dentro `motore.contesto` ogni lettura di `lega_risultati` del codice di loucabot diventa una tabella coi risultati del sistema, e l'ordine della classifica è quello del sistema); risposte che cominciano con NON UFFICIALE |
| `/pdf_giornata [N] [NOME]`, `/pdf_partite [SQUADRA] [NOME]` | come loucabot, col sistema, con striscia e filigrana |
| `/conference` | conference alternative (v2, Luca 06/11): lista, scheda (squadre e posti nel calendario), Usa queste, Classifica per conference, Confronta; «➕ Nuove conference»: si scelgono le squadre della prima conference coi bottoni, «🔀 Squadre a caso» le estrae (poi si possono cambiare), «🎲 Accoppia e salva» estrae a caso il posto di ognuna nel calendario vero (tabella `klra_conference`, `mappa` salvata), poi il nome. Le modifica solo chi le ha create (nuovo accoppiamento); attive per utente (`klra_scelte.conference_id`) e valgono in tutti i comandi insieme al sistema |
| `/klra_verifica` (dev) | il motore: l'Ufficiale di klra contro il ricalcolo di oggi di loucabot (deve essere identico); a parte le partite in cui il ricalcolo di oggi è diverso dalla convalida (dati cambiati dopo) |

**Tutto è segnato NON UFFICIALE** (Luca, 04/11): striscia rossa in cima e filigrana in diagonale su ogni immagine (campi `striscia` e `filigrana`, letti anche da `partita.typ` e `live.typ` di loucabot), etichetta rossa al posto dello stato, didascalie e testi che iniziano con «🧪 NON UFFICIALE», avviso in `/start` e `/sistemi`.

**Conference alternative** (`klra/conference.py`, `motore.in_conference`): dentro, ogni lettura di `lega_partite` del codice di loucabot diventa il calendario permutato (chi ha preso il posto di X gioca le partite di X) e `classifica.conference` le nuove conference; le sfide si ricalcolano da zero (bonus casa e supplementari dipendono dall'avversario); in cache con firma a parte. `/confronta` confronta sempre con l'Ufficiale sul calendario vero.

**Classifica cumulativa** (v2): terza modalità oltre a vittorie e punti, i punti fatti in tutte le giornate senza bonus casa né supplementari (immagine con PUNTI, media e giornate); Fantapanchine la usa.

`/confronta` e il 🔄 di `/risultati` partono dall'**Ufficiale ricalcolato coi dati di oggi**, non dai risultati convalidati: così le differenze vengono solo dalle regole del sistema. La cache dei risultati è per firma dei parametri più `VERSIONE_MOTORE` (si alza quando cambia il modo di calcolare: all'avvio la cache vecchia si cancella).

`/player NOME [SISTEMA]` è quello di loucabot con in fondo la stagione col sistema (fantamedia e ultime 5 partite coi fantapunti e i bonus del sistema, accanto quelli della lega); `/live`, `/live_results` e `/notte` non ci sono: klra lavora solo sulle giornate convalidate (per il live c'è loucabot).

Senza NOME vale il tuo sistema attivo; N di default è l'ultima giornata convalidata. Editor (`klra/editor.py`, solo in
privato): cinque sezioni, un bottone per voce col valore; le voci a scelta cambiano a ogni tocco, quelle numeriche
chiedono il valore (multipli di 0,25, con limiti); la bozza resta se si chiude a metà.

## Avvio (una volta)

1. Token da BotFather in `secrets/bot_token_klra.txt`.
2. Password dell'utente PostgreSQL: `openssl rand -hex 24 > secrets/pg_password_klra.txt` (solo lettere e cifre).
3. Il deploy della versione che porta klra nel `docker-compose.yml` esegue `setup_db.sql` e lo avvia.
4. Facoltativo: `"log_channel_id_klra"` in `globals.json` (se no l'avviso di avvio va al dev).

Il codice di loucabot è montato: **quando cambia loucabot, si riavvia anche klra** (nel `riavvia` del rilascio).

Backup: il backup del bot principale include `db/klra.sql` se il database esiste; ripristino in `docs/RECOVERY.md`.

## Servizio nel docker-compose.yml (dalla v7.0.0)

```yaml
  klra:
    build: ./fantabasket-klra
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      BOT_TOKEN_FILE: /run/secrets/bot_token_klra
      GLOBALS_PATH: /config/globals.json
      TEAMS_PATH: /config/teams.json
      DATABASE_URL: postgresql://klra@postgres/fantabasket       # sola lettura (setup_db.sql)
      KLRA_DATABASE_URL: postgresql://klra@postgres/klra
      PG_PASSWORD_FILE: /run/secrets/pg_password_klra
    secrets:
      - bot_token_klra
      - pg_password_klra
    volumes:
      - ./config:/config:ro
      - ./shared:/app/shared:ro
      - ./fantabasket-loucabot:/louca:ro
```

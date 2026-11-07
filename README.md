# Fantabasket Progettone

Un progetto **hobbistico**: un gruppo di bot Telegram che gestisce **una lega fantasy NBA
giocata tra amici** (24 squadre). Lo usano solo i membri della lega e gira su un piccolo
server di casa.

## Perché esiste

Le formazioni si schierano su Yahoo Fantasy Basketball, ma la lega ha regole sue che Yahoo
non gestisce: contratti pluriennali, salary cap, aste per i free agent, trade con scelte al
draft, contratti da rookie, panchine e un calendario proprio con punteggi calcolati da noi.
Per anni tutto questo si è fatto a mano su un foglio condiviso. I bot automatizzano i conti e
le procedure e tengono il foglio aggiornato.

## Cosa fanno

- **Contratti e cap**: contratti pluriennali, tetto salariale e minimo, dead money dei tagli,
  eccezioni per infortunio.
- **Aste**: aste a tempo in un canale Telegram per i free agent, anche ristrette (RFA) con
  diritto di pareggio.
- **Trade**: proposta, controlli (cap, roster, regole sulle scelte), approvazione; registro di
  tutti i movimenti.
- **Draft e rookie**: scelte, diritti e contratti da rookie; cambio di stagione automatico.
- **Campionato**: calendario della lega allineato a quello NBA, fantapunti dai tabellini delle
  partite (anche in diretta), risultati convalidati da un admin, classifiche e immagini.
- **Formazioni**: panchine mandate dai GM come messaggio, quintetti, avvisi su infortuni e
  giocatori ceduti.
- **What-if**: le stesse giornate rigiocate con sistemi di punteggio inventati dai GM, sempre
  segnate come **non ufficiali** e separate dai dati veri.
- **Foglio della lega**: il Google Sheet condiviso resta aggiornato in automatico.

## Architettura

Tutto gira con Docker Compose. I bot non si chiamano tra loro: condividono un database
PostgreSQL, ognuno scrive solo le sue tabelle.

```
 FONTI                            I BOT                              TELEGRAM
                               ┌────────────────────┐
 Basketball-Reference ───────► │ bot-main           │ ──┐
   medie stagionali            │ contratti, cap,    │   │            chat private
                               │ trade, ruoli       │   │            canale principale
                               └────────────────────┘   │            gruppo della lega
                               ┌────────────────────┐   │            gruppo admin
                               │ bot-aste-beta      │ ──┤            canale aste
                               │ aste FA e RFA      │   ├──────────► canale panchine
                               └────────────────────┘   │            canali di log
 ESPN (dati pubblici) ───────► ┌────────────────────┐   │
   calendario NBA, tabellini,  │ loucabot           │ ──┤
   infortuni, roster           │ calendario, punti, │   │
                               │ risultati          │   │
                               └────────────────────┘   │
                               ┌────────────────────┐   │
                               │ ipanchinari        │ ──┤
                               │ panchine, quintetti│   │
                               └────────────────────┘   │
                               ┌────────────────────┐   │
                               │ klra (what-if)     │ ──┘
                               │ sola lettura       │
                               └────────────────────┘
                                         │
                                         ▼
     ┌───────────────────────────────────────────────┐   aste.db (SQLite, aste)
     │ PostgreSQL: database della lega               │   config/, secrets/ (solo sul server)
     │ + database separato per klra                  │   NocoDB (sola lettura, rete di casa)
     └───────────────────────────────────────────────┘

 Google Sheets ◄── gas-router ◄── bot-main  (roster, scelte, statistiche)
 (foglio lega)   (Apps Script) ◄── loucabot  (calendario, risultati)
```

| Servizio        | Ruolo                                                                      |
|-----------------|----------------------------------------------------------------------------|
| `bot-main`      | Bot principale: contratti, cap, trade, tagli, draft, ruoli, stagione, backup |
| `bot-aste-beta` | Aste dei free agent (FA e RFA)                                             |
| `loucabot`      | Il campionato: calendario, tabellini e fantapunti, risultati, classifiche  |
| `ipanchinari`   | Panchine dai messaggi dei GM e quintetti                                   |
| `klra`          | What-if coi sistemi di punteggio alternativi; database suo, sola lettura su quello della lega |
| `gas-router`    | Ponte interno verso Google Apps Script                                     |
| `postgres`      | Database                                                                   |
| `nocodb`        | Consultazione delle tabelle in sola lettura, solo dalla rete di casa       |

Una giornata tipo: i quintetti si bloccano alla prima partita NBA, loucabot segue le partite
dai tabellini ESPN, la mattina dopo l'ultima notte calcola i risultati e un admin li convalida
prima che finiscano sul foglio e sul canale.

## Dati

- **ESPN** (pagine pubbliche delle partite): calendario NBA, risultati, tabellini, infortuni,
  squadre dei giocatori.
- **Basketball-Reference**: medie stagionali, da cui si calcola la fantamedia di ogni
  giocatore con la formula della lega.
- **Yahoo**: solo le posizioni in cui ogni giocatore può essere schierato, importate a mano.
  Nessuna statistica, punteggio o classifica di Yahoo viene salvata o mostrata.

Credenziali, ID e configurazione della lega stanno solo sul server (Docker secrets e file
esclusi dal repo).

## Documentazione

- `MIGRATION.md`: stato del progetto, regole di lavoro, decisioni e cose da fare.
- Ogni bot ha README, CHANGELOG e guide (`docs/guida_gm.md`, `guida_admin.md`, `guida_dev.md`).
- `docs/RECOVERY.md`: backup e ripristino. `docs/regolamento_e_codice.md`: dove il regolamento
  sta nel codice.
- `tests/README.md`: le prove, che girano solo in locale.

## Tecnologie

Python 3.12 · python-telegram-bot · PostgreSQL 16 · SQLite · FastAPI · Typst ·
Google Apps Script · Docker Compose

## Note

Non affiliato a Yahoo, alla NBA, a ESPN o a
Basketball-Reference, né approvato da loro. I marchi appartengono ai rispettivi proprietari.

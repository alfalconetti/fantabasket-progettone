# Fantabasket Aste Bot

Bot Telegram delle aste della lega: free agency (FA) e restricted free agency (RFA), con
offerte, rilanci, firma, pareggio dell'RFA e annunci sul canale delle aste.

Fa parte del progettone insieme al bot principale (roster, trade, tagli, rookie, ruoli,
cambio di stagione), con cui condivide PostgreSQL e la configurazione.

Sviluppato con [Claude](https://claude.ai) (Anthropic).

## Stack

- Python 3.12, python-telegram-bot 21.6 (con job-queue)
- **SQLite** (`/data/aste.db`): aste, offerte, chi le segue. Schema solo additivo
- **PostgreSQL** (quello del bot principale, via `pg_client.py`): contratti, cap, slot, DPE,
  tagli, RFA dichiarati; qui il bot scrive firme, rilasci RFA, cap e slot anticipati e la coda
  dei fogli
- Docker Compose (servizio `bot-aste-beta` del progettone)

## Struttura

```
fantabasket-aste-beta/
├── bot.py            avvio, handler, job, recupero di firme e pareggi dopo un riavvio
├── database.py       SQLite: aste, offerte, watch
├── pg_client.py      PostgreSQL: cap e slot (x0 e RFA dichiarati come nel bot principale), firme, RFA, regole
├── comandi.py        menu "/" per ruolo e per fase
├── scheduler.py      scadenze delle aste, check del cap in offseason, healthcheck
├── settings.py       regole di cap (tetto, penalità, offerta massima)
├── teams.py          lettura di teams.json
├── utils.py          globals, ricerca giocatori, messaggi del canale
├── handlers/
│   ├── offerte.py    apertura FA, offerte, deep link
│   ├── firma.py      firma del vincitore (anni, ruolo, firma automatica); firma_comune.py,
│   │                 firma_preimpostazioni.py, firma_pareggio.py: soglie e scrittura, pre-impostazioni,
│   │                 pareggio e lascio andare
│   ├── rfa.py        aste RFA aperte da sole per i dichiarati, proprietario allineato alle trade
│   ├── user.py       /me, /watch, /lista_fa, /team_detail, /autocap, /autoslot…
│   ├── admin.py      /admin e registrazione; admin_squadre.py (/listteams, /team, /autocap…),
│   │                 admin_aste.py (guardare e correggere), admin_riapri.py, admin_offerte.py, admin_comune.py
│   ├── dev.py        comandi dev
│   └── helpers.py    canale, notifiche, log
└── docs/             guide (GM, admin, dev)
```

Usa anche `../shared/` (montata in sola lettura): `ruoli_core.py` per i ruoli e `messaggi.py`
per gli elenchi lunghi mandati come file.

## Configurazione

`config/` è quella del progettone, montata **in sola lettura**: `globals.json`, `teams.json`,
`settings.json`, `fa_players.csv`. Fase, stagione, mercato, penalità e squadre li decide il bot
principale; i comandi che li cambiavano da qui ora rimandano a lui. Le chiavi sono descritte
nella guida dev del bot principale (`../fantabasket-main/docs/guida_dev.md`, sezione 2).

Segreti (token, password di PostgreSQL) solo in `secrets/` del progettone, mai in git.

## Avvio

Dalla cartella del progettone:

```bash
docker compose up --build -d bot-aste-beta
docker compose logs -f --tail 100 bot-aste-beta
```

## Documentazione

- [Guida GM](docs/guida_gm.md): aprire un'asta, offrire, firmare, pareggiare un RFA
- [Guida admin](docs/guida_admin.md): agire per conto di una squadra, correggere un'asta, cosa fare se qualcosa si inceppa
- [Guida dev](docs/guida_dev.md): stati delle aste, conti di cap e slot, job, comandi, diagnosi
- [Backup e ripristino](../docs/RECOVERY.md): guida unica del progettone
- [Changelog](CHANGELOG.md)

I comandi sono elencati nelle guide (e da Telegram con `/start`, `/admin` e `/dev`): una prova
automatica controlla che ogni comando citato esista davvero.

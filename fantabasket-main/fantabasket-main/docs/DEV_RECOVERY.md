# 🔧 Dev Recovery — Fantabasket Progettone

Guida personale per il ripristino rapido del sistema.

---

## Il bot non risponde — checklist rapida

```bash
# Stato container
docker ps

# Log ultimi errori
cd ~/bots/fantabasket-progettone
docker compose logs --tail=50

# Riavvio rapido
docker compose restart

# Riavvio completo con rebuild
docker compose up --build -d
```

---

## Il mini-PC si è riavviato

Docker è configurato con `restart: unless-stopped` — i container ripartono da soli.
Se non ripartono:

```bash
cd ~/bots/fantabasket-progettone
docker compose up -d
```

---

## Errore nel bot main

```bash
# Log in tempo reale
docker compose logs -f bot-main

# Riavvia solo il bot main
docker compose restart bot-main
```

---

## Errore nel bot aste beta

```bash
docker compose logs -f bot-aste-beta
docker compose restart bot-aste-beta
```

---

## Database PostgreSQL non risponde

```bash
# Stato postgres
docker compose logs postgres

# Riavvia postgres (i bot si riconnettono da soli)
docker compose restart postgres

# Connessione diretta al DB
docker exec -it fantabasket-progettone-postgres-1 psql -U fantabasket -d fantabasket
```

---

## Backup manuale immediato

Dal bot: `/backup` (solo dev)

Oppure da shell:
```bash
docker exec fantabasket-progettone-postgres-1 pg_dump -U fantabasket fantabasket > ~/backup_emergency_$(date +%Y%m%d_%H%M).sql
```

---

## Ripristino da backup

```bash
# Estrai backup dal gruppo admin
unzip backup_progettone_YYYYMMDD_HHMM.zip -d restore/

# Ripristina config (se necessario)
cp restore/config/* ~/bots/fantabasket-progettone/config/

# Ripristina DB PostgreSQL
cat restore/db/fantabasket_*.sql | docker exec -i fantabasket-progettone-postgres-1 psql -U fantabasket -d fantabasket

# Ripristina DB aste beta
docker cp restore/db/aste.db fantabasket-progettone-bot-aste-beta-1:/data_aste/aste.db
docker compose restart bot-aste-beta
```

---

## Deploy nuovo codice

```bash
cd ~/bots
unzip -o fantabasket-progettone-vX.Y.Z-completo.zip
cd fantabasket-progettone
docker compose up --build -d
git add -A && git commit -m "vX.Y.Z: descrizione"
git push origin main
```

---

## Secrets e config

```
~/bots/fantabasket-progettone/
├── secrets/
│   ├── bot_token_main
│   ├── bot_token_aste_beta
│   └── postgres_password
└── config/
    ├── globals.json        ← fase, stagione, admin_ids, channel_ids
    ├── teams.json          ← cap, slot, colori, palette GM
    ├── settings_main.json  ← costanti business bot main
    └── settings_aste.json  ← costanti business bot aste (cap_offseason=165!)
```

⚠️ `settings_aste.json`: `cap_offseason` e `cap_massimo_offseason` devono essere **165**, non 150.

---

## Healthcheck

Il bot pinga healthchecks.io ogni 5 minuti. Se smette di pingare ricevi una notifica.
URL configurato in `docker-compose.yml` come variabile env `HEALTHCHECK_URL`.

---

## Accesso remoto

```bash
# Via Tailscale
ssh [username]@[nome-macchina]

# Porta SSH standard
ssh [username]@[indirizzo-tailscale]
```

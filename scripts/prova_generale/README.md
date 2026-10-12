# Prova generale sui dati veri

Per le modifiche strutturali (schema, query dei roster, migrazioni): prima di andare in
produzione si prova tutto su una **copia** del database, ripristinata dal backup, e si
confronta una "foto" di tutte le squadre prima e dopo. Gli script **leggono soltanto**.

Mai sul server: si lavora in locale (o in una sessione di Claude) con i file del backup
(`db/fantabasket.sql`, `db/aste.db`), su un database separato con un nome diverso da
`fantabasket`.

```bash
# 1. copia del DB (il dump è di pg_dump 17: via le due righe che psql 16 non capisce)
grep -v '^\\restrict\|^\\unrestrict\|^SET transaction_timeout' fantabasket.sql > dump.sql
createdb prodcopia && psql -d prodcopia -f dump.sql
cp aste.db /tmp/aste_copia.db

# 2. ambiente: config finta con le 24 squadre, settings veri, DB della copia
export DATABASE_URL=postgresql://utente:pw@localhost/prodcopia PG_URL=$DATABASE_URL PG_PASSWORD_FILE=/nonesiste
export SETTINGS_PATH=… GLOBALS_PATH=… TEAMS_PATH=… FA_CSV_PATH=… DB_PATH=/tmp/aste_copia.db

# 3. foto PRIMA, col codice in produzione
(cd fantabasket-main && PYTHONPATH=.:.. python3 ../scripts/prova_generale/foto_main.py /tmp/prima_main.json)
(cd fantabasket-aste-beta && PYTHONPATH=.:.. python3 ../scripts/prova_generale/foto_aste.py /tmp/prima_aste.json)

# 4. codice nuovo: migrazione (migrate_db) sulla copia, poi foto DOPO con gli stessi comandi
#    (dopo_main.json, dopo_aste.json)

# 5. confronto: ogni differenza deve essere voluta
python3 scripts/prova_generale/confronta.py /tmp
```

`foto_main.py`: roster, cap, pick, diritti, tagli gratuiti, Stepien, roster/pick/diritti a
varie date, regola dei 60 giorni, fantamedie, Cam Thomas, report spalmature.
`foto_aste.py`: roster, slot, cap (come li vede il bot aste), regola dei 30 giorni, Cam
Thomas, lista FA.

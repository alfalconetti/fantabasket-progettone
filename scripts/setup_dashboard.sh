#!/usr/bin/env bash
# Prepara la dashboard NocoDB. Rilanciabile senza danni (anche dopo un ripristino):
#  1. secrets/nocodb.env: segreto JWT, database interno di NocoDB su PostgreSQL (NC_DB),
#     connessione al PostgreSQL interno consentita (NC_ALLOW_LOCAL_EXTERNAL_DBS)
#  2. utente/database PostgreSQL `nocodb` per i dati interni di NocoDB (account, viste):
#     max 10 connessioni, nessun accesso al database della lega
#  3. utente PostgreSQL `lettore` in SOLA LETTURA sul database della lega, con timeout
#     (una query di NocoDB non può bloccare i bot, es. le ALTER TABLE di migrate_db all'avvio)
#  4. stampa i dati da inserire in NocoDB
#
# Perché non SQLite (il default di NocoDB): con la 2026.09.1 la creazione dell'utente
# admin va in timeout su SQLite ("Failed to ensure org user") e l'account resta senza
# workspace. Niente NC_ADMIN_EMAIL/PASSWORD: l'account si crea con la registrazione
# (/#/signup) al primo accesso, il primo utente diventa admin.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d secrets ] || { echo "❌ cartella secrets/ non trovata"; exit 1; }
genera() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c "$1"; }
psql_pg() { docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U fantabasket "$@"; }

docker compose up -d postgres >/dev/null
for _ in $(seq 1 30); do
  docker compose exec -T postgres pg_isready -U fantabasket -q && break
  sleep 1
done

# ── 1. secrets/nocodb.env ──────────────────────────────────────────────────────
ENV=secrets/nocodb.env
touch "$ENV" && chmod 600 "$ENV"
imposta() {   # aggiunge KEY=valore solo se KEY manca (non tocca i valori esistenti)
  grep -q "^$1=" "$ENV" || echo "$1=$2" >> "$ENV"
}
imposta NC_AUTH_JWT_SECRET "$(genera 48)"
imposta NC_ALLOW_LOCAL_EXTERNAL_DBS true
if grep -q '^NC_DB=' "$ENV"; then
  NCPW=$(sed -n 's/^NC_DB=.*[?&]p=\([^&]*\).*/\1/p' "$ENV")
else
  NCPW=$(genera 32)
  echo "NC_DB=pg://postgres:5432?u=nocodb&p=${NCPW}&d=nocodb" >> "$ENV"
fi
[ -n "$NCPW" ] || { echo "❌ password di NC_DB non leggibile in $ENV"; exit 1; }
if grep -q '^NC_ADMIN_' "$ENV"; then
  sed -i '/^NC_ADMIN_EMAIL=/d;/^NC_ADMIN_PASSWORD=/d' "$ENV"
  echo "ℹ️  tolte NC_ADMIN_EMAIL/NC_ADMIN_PASSWORD (l'account si crea con la registrazione)"
fi
echo "✅ $ENV pronto."

# ── 2. utente e database `nocodb` (dati interni di NocoDB) ─────────────────────
psql_pg -d postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nocodb') THEN
    CREATE ROLE nocodb LOGIN PASSWORD '${NCPW}' CONNECTION LIMIT 10;
  ELSE
    ALTER ROLE nocodb LOGIN PASSWORD '${NCPW}' CONNECTION LIMIT 10;
  END IF;
END \$\$;
SQL
if [ "$(psql_pg -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'nocodb'")" != "1" ]; then
  psql_pg -d postgres -c "CREATE DATABASE nocodb OWNER nocodb"
fi
psql_pg -d postgres -c "REVOKE CONNECT ON DATABASE nocodb FROM PUBLIC" \
                    -c "GRANT CONNECT ON DATABASE nocodb TO nocodb"
echo "✅ Database 'nocodb' pronto (dati interni di NocoDB)."

# ── 3. utente `lettore` (sola lettura sul database della lega) ─────────────────
if [ ! -f secrets/pg_lettore_password.txt ]; then
  genera 32 > secrets/pg_lettore_password.txt
  chmod 600 secrets/pg_lettore_password.txt
fi
PW=$(cat secrets/pg_lettore_password.txt)

psql_pg -d fantabasket <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lettore') THEN
    CREATE ROLE lettore LOGIN PASSWORD '${PW}';
  ELSE
    ALTER ROLE lettore LOGIN PASSWORD '${PW}';
  END IF;
END \$\$;
ALTER ROLE lettore CONNECTION LIMIT 5;
ALTER ROLE lettore SET default_transaction_read_only = on;
ALTER ROLE lettore SET statement_timeout = '30s';
ALTER ROLE lettore SET idle_in_transaction_session_timeout = '30s';
REVOKE CONNECT ON DATABASE fantabasket FROM PUBLIC;
GRANT CONNECT ON DATABASE fantabasket TO lettore;
GRANT USAGE ON SCHEMA public TO lettore;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lettore;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO lettore;
ALTER DEFAULT PRIVILEGES FOR ROLE fantabasket IN SCHEMA public GRANT SELECT ON TABLES TO lettore;
SQL
echo "✅ Utente PostgreSQL 'lettore' pronto (sola lettura, timeout 30s, max 5 connessioni)."

# ── 4. istruzioni ──────────────────────────────────────────────────────────────
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
cat <<TXT

Avvio:      docker compose up -d nocodb     (stop: docker compose stop nocodb)
Primo accesso: http://${IP:-<IP-del-server>}:${NOCODB_PORT:-8090}/#/signup → il primo utente registrato è l'admin
Poi nel workspace: nuova base → sorgente esterna PostgreSQL:
   Host: postgres   Porta: 5432   Database: fantabasket   Schema: public
   Utente: lettore  Password: in secrets/pg_lettore_password.txt
   (modifiche ai dati disattivate)

Ricordati di rilanciare ./scripts/cifra_secrets.sh se sono cambiati i secrets.
TXT

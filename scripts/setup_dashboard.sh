#!/usr/bin/env bash
# Prepara la dashboard NocoDB (una volta sola; rilanciabile senza danni):
#  1. secrets/nocodb.env con l'account admin di NocoDB e il segreto JWT
#  2. secrets/pg_lettore_password.txt e l'utente PostgreSQL `lettore` in SOLA LETTURA
#     (SELECT su tutte le tabelle e viste, anche quelle create in futuro)
#  3. stampa i dati da inserire in NocoDB per collegare il database
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d secrets ] || { echo "❌ cartella secrets/ non trovata"; exit 1; }
genera() { openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c "$1"; }

if [ ! -f secrets/nocodb.env ]; then
  read -rp "📧 Email per l'account admin di NocoDB: " email
  pw=$(genera 20)
  printf 'NC_ADMIN_EMAIL=%s\nNC_ADMIN_PASSWORD=%s\nNC_AUTH_JWT_SECRET=%s\n' "$email" "$pw" "$(genera 48)" > secrets/nocodb.env
  chmod 600 secrets/nocodb.env
  echo "✅ secrets/nocodb.env creato. Password admin di NocoDB (salvala nel password manager):"
  echo "   $pw"
else
  echo "ℹ️  secrets/nocodb.env c'è già: lo lascio com'è."
fi

if [ ! -f secrets/pg_lettore_password.txt ]; then
  genera 32 > secrets/pg_lettore_password.txt
  chmod 600 secrets/pg_lettore_password.txt
fi
PW=$(cat secrets/pg_lettore_password.txt)

docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U fantabasket -d fantabasket <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lettore') THEN
    CREATE ROLE lettore LOGIN PASSWORD '${PW}';
  ELSE
    ALTER ROLE lettore LOGIN PASSWORD '${PW}';
  END IF;
END \$\$;
ALTER ROLE lettore SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE fantabasket TO lettore;
GRANT USAGE ON SCHEMA public TO lettore;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lettore;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO lettore;
ALTER DEFAULT PRIVILEGES FOR ROLE fantabasket IN SCHEMA public GRANT SELECT ON TABLES TO lettore;
SQL
echo "✅ Utente PostgreSQL 'lettore' pronto (sola lettura)."

echo
echo "Ora, in NocoDB → nuova base → 'Connect external data source' → PostgreSQL:"
echo "   Host: postgres   Porta: 5432   Database: fantabasket   Schema: public"
echo "   Utente: lettore   Password: $PW"
echo "   (togli 'Allow data edit' / spunta sola lettura se NocoDB la propone)"
echo
echo "Ricordati di rilanciare ./scripts/cifra_secrets.sh: ci sono secrets nuovi."

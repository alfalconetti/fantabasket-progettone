-- klra (Luca, 04/11/2026: separazione assoluta dalle tabelle ufficiali). Da eseguire come superutente
-- (l'utente fantabasket del container postgres), collegati al database ufficiale. Lo fa deploy.sh prima di
-- avviare klra, a ogni rilascio che lo riavvia; si può rilanciare quante volte si vuole.
--
-- Variabili psql: pw (password dell'utente klra, da secrets/pg_password_klra.txt), ruolo (default klra),
-- dbklra (default klra). Uso a mano:
--   { printf "\\set pw '%s'\n" "$(cat secrets/pg_password_klra.txt)"; cat fantabasket-klra/setup_db.sql; } \
--     | docker compose exec -T postgres psql -U fantabasket -d fantabasket -v ON_ERROR_STOP=1 -q
--
-- Cosa ottiene:
--   * utente klra, proprietario del SUO database klra (dove scrive le tabelle klra_*);
--   * sul database ufficiale: CONNECT e SELECT solo sulle tabelle elencate sotto, niente altro (né scrivere,
--     né creare tabelle: in PostgreSQL 16 lo schema public non lo permette a chi non è proprietario), e ogni
--     transazione in sola lettura per default;
--   * le tabelle nuove della lega non sono visibili a klra finché non si aggiungono qui.

\if :{?ruolo}
\else
  \set ruolo klra
\endif
\if :{?dbklra}
\else
  \set dbklra klra
\endif
\if :{?pw}
\else
  \echo 'Manca la password: \\set pw ...'
  \quit
\endif

SELECT format('CREATE ROLE %I LOGIN', :'ruolo') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'ruolo') \gexec
ALTER ROLE :"ruolo" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'pw';
SELECT format('CREATE DATABASE %I OWNER %I', :'dbklra', :'ruolo')
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'dbklra') \gexec

-- database ufficiale: solo lettura di queste tabelle
SELECT format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', :'ruolo') \gexec
SELECT format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', :'ruolo') \gexec
SELECT format('REVOKE CREATE ON SCHEMA public FROM %I', :'ruolo') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'ruolo') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'ruolo') \gexec
SELECT format('GRANT SELECT ON %I TO %I', c.relname, :'ruolo')
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm', 'p')
   AND c.relname IN ('giocatori', 'ruolo_attuale', 'posizioni_attuali', 'contratti', 'movimenti_giocatori',
                     'ipa_formazioni', 'ipa_panchine', 'ipa_stato_giornata', 'ipa_quintetto',
                     'nba_partite', 'nba_tabellini', 'nba_atleti', 'nba_infortuni',
                     'lega_giornate', 'lega_partite', 'lega_risultati', 'lega_status_validi', 'lega_live', 'bref_stats',
                     -- /player (v2): contratti e anagrafica del bot principale, movimenti NBA
                     'dpe', 'rookie', 'ruoli_pendenti', 'rfa_dichiarati', 'nba_movimenti') \gexec
SELECT format('ALTER ROLE %I IN DATABASE %I SET default_transaction_read_only = on', :'ruolo', current_database()) \gexec

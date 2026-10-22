#!/bin/sh
# Cria o usuário de login da API como membro de comex_app (sem UPDATE/DELETE no ledger).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'comex_api') THEN
    CREATE ROLE comex_api LOGIN PASSWORD '${API_DB_PASSWORD}' IN ROLE comex_app;
  END IF;
END \$\$;
SQL

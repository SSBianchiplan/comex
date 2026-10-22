#!/bin/sh
# Banco e usuário próprios do Keycloak (isolados do schema comex).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keycloak') THEN
    CREATE ROLE keycloak LOGIN PASSWORD '${KC_DB_PASSWORD}';
  END IF;
END \$\$;
SQL
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='keycloak'" | grep -q 1 \
  || psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE keycloak OWNER keycloak"

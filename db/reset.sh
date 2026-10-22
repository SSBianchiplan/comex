#!/bin/sh
# Recria o schema do zero (DESTRUTIVO — apaga todos os dados). Uso: DATABASE_URL=... ./reset.sh
set -e
psql "$DATABASE_URL" -q -c "DROP SCHEMA IF EXISTS comex CASCADE"
for f in 001_schema.sql 002_regras.sql 003_referencia.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$(dirname "$0")/$f"; done

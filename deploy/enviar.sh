#!/usr/bin/env bash
# Publica o GPlanSiS|COMEX no servidor (comex.gplansis.com), atrás do Caddy do host.
#   bash deploy/enviar.sh
# 1ª vez: gera /opt/gplansis-comex/.env com segredos aleatórios (fica só no servidor, chmod 600)
# e instala /etc/caddy/comex.caddy. Depois: só sincroniza o código e reconstrói.
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=${HOST:?defina HOST=<servidor ssh>}; DIR=/opt/gplansis-comex
rsync -az --delete --exclude .env --exclude '__pycache__' --exclude .pytest_cache --exclude .vscode --exclude .DS_Store ./ "$HOST:$DIR/"
ssh "$HOST" DIR="$DIR" bash -s <<'REMOTO'
set -euo pipefail
cd "$DIR"
if [ ! -f .env ]; then
  r(){ openssl rand -hex "$1"; }
  umask 077; cat > .env <<ENV
DB_USER=comex
DB_PASSWORD=$(r 24)
API_DB_PASSWORD=$(r 24)
KC_DB_PASSWORD=$(r 24)
KC_ADMIN_PASSWORD=$(r 16)
COMEX_SENHA_DEMO=Demo-$(r 8)
COMEX_SENHA_ADMIN=Cmx-$(r 6)-Adm
COMEX_ADMIN_EMAIL=contato@gplansis.com
KC_ADMIN_SECRET=$(r 32)
DOMINIO=comex.gplansis.com
COMEX_URL=https://comex.gplansis.com
ENV
  echo ".env criado (segredos só no servidor)"
fi
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
if [ ! -f /etc/caddy/comex.caddy ] || ! cmp -s deploy/comex.caddy /etc/caddy/comex.caddy; then
  cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak-comex-$(date +%Y%m%d-%H%M%S)"
  install -m 644 deploy/comex.caddy /etc/caddy/comex.caddy
  touch /var/log/caddy/comex.log && chown caddy:caddy /var/log/caddy/comex.log
  grep -q 'import /etc/caddy/comex.caddy' /etc/caddy/Caddyfile || printf '\n# GPlanSiS|COMEX\nimport /etc/caddy/comex.caddy\n' >> /etc/caddy/Caddyfile
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null && systemctl reload caddy && echo "Caddy recarregado"
fi
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps --format '{{.Service}} {{.Status}}'
REMOTO

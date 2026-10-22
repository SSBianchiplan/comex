FROM nginx:1.30.6-alpine
# O template recebe KEYCLOAK_ORIGIN (CSP) por envsubst na subida do contêiner
ENV NGINX_ENVSUBST_FILTER=^KEYCLOAK_ORIGIN$
COPY default.conf.template seguranca.inc.template /etc/nginx/templates/
COPY index.html app.html manifest.webmanifest sw.js /usr/share/nginx/html/
COPY icons /usr/share/nginx/html/icons

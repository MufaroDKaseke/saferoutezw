# Managed by infra/server/bootstrap.sh (rendered with the real domain). Edit the template in the
# repo and re-run bootstrap; changes made directly on the server are overwritten.

upstream saferoute_web {
    server 127.0.0.1:3000;
    keepalive 16;
}

upstream saferoute_api {
    server 127.0.0.1:8000;
    keepalive 16;
}

server {
    listen 80;
    listen [::]:80;
    server_name __DOMAIN__;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name __DOMAIN__;

    ssl_certificate     /etc/letsencrypt/live/__DOMAIN__/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/__DOMAIN__/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 2m;

    # Common proxy settings. X-Forwarded-For is OVERWRITTEN, not appended: the API's rate limiter
    # trusts the first address in that header, so a client must not be able to supply its own.
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 5s;
    proxy_read_timeout 60s;

    location ~ /\.(?!well-known) {
        deny all;
    }

    # Meta's WhatsApp webhook calls the API directly; the raw body is forwarded untouched so its
    # HMAC signature still verifies.
    location /api/v1/webhooks/ {
        proxy_pass http://saferoute_api;
    }

    # Everything else is the Next.js app, which proxies /backend/* to the API itself.
    location / {
        proxy_pass http://saferoute_web;
    }

    # While the app is down or restarting, show a plain page instead of nginx's raw 502.
    error_page 502 503 504 /maintenance.html;
    location = /maintenance.html {
        root /var/www/saferoute;
        internal;
    }
}

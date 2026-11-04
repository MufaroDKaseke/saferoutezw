# Managed by infra/server/bootstrap.sh. Used until a certificate exists; bootstrap swaps in
# site-https.conf.tpl as soon as Let's Encrypt has issued one.
server {
    listen 80;
    listen [::]:80;
    server_name __DOMAIN__;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 503;
    }

    error_page 503 /maintenance.html;
    location = /maintenance.html {
        root /var/www/saferoute;
        internal;
    }
}

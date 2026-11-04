# Production server

Provisioning for the single Ubuntu 24.04 droplet that hosts SafeRouteZW at
<https://saferoute.momo.co.zw>. `bootstrap.sh` is idempotent: re-run it to repair or update the
server. Existing secrets are never regenerated.

```bash
scp -r infra/server root@<server>:/root/saferoute-bootstrap
ssh root@<server> 'cd /root/saferoute-bootstrap && DOMAIN=saferoute.momo.co.zw ./bootstrap.sh'
```

## What it sets up

| Piece | Detail |
| --- | --- |
| Swap | 2 GB `/swapfile`, `vm.swappiness=10` (the host has 2 GB RAM, 1 vCPU). |
| Packages | nginx, certbot, PostgreSQL 16 + PostGIS 3, Python 3.12 + venv, Node 24 (NodeSource), pm2, ufw, fail2ban. |
| App user | `saferoute` (no password). Owns `/opt/saferoutezw`. pm2 runs as this user and restarts on boot (`pm2-saferoute.service`). |
| Layout | `/opt/saferoutezw/app` is where the code goes; `/opt/saferoutezw/app/.env` holds production settings (mode 600). |
| Database | Local only (`localhost:5432`). Database `saferoutezw`, owned by non-superuser role `saferoute`. PostGIS is pre-enabled by the superuser, so the Alembic migration finds it already present. |
| `.env` | Generated once with the DB password and subscriber encryption/digest keys. Third-party keys (`OPENAI_API_KEY`, `GEOAPIFY_API_KEY`, ...) are left blank for you to fill in. |
| nginx | HTTP redirects to HTTPS. `/api/v1/webhooks/` goes straight to the API on `127.0.0.1:8000` (Meta's WhatsApp webhook); everything else goes to Next.js on `127.0.0.1:3000`. While the app is down, a plain maintenance page is shown. Requests that don't name the domain get no answer. |
| TLS | Let's Encrypt via certbot (webroot), auto-renewed by certbot's systemd timer; nginx reloads after each renewal. Registered without an e-mail address; add one with `certbot update_account --email ...` to get expiry notices. |
| Firewall | ufw: only 22, 80 and 443 are open. fail2ban guards SSH. |
| Backups | `pg_dump` nightly at 02:30 UTC to `/var/backups/saferoutezw`, 14 days kept. These are on the same disk: enable droplet backups or copy them off-site too. |

## Deploying the app

[`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) does it on every push to `main`:

1. **Tests**: API (pytest against a PostGIS service) and web (typecheck + vitest). Pull requests stop here.
2. **Build** the Next.js app on the GitHub runner (the 2 GB server cannot build it).
3. **Sync** the repo plus the prebuilt `apps/web/.next` to `/opt/saferoutezw/app` with rsync, as the `saferoute`
   user. The server's `.env`, `data/` and `node_modules` are never touched.
4. **[`deploy.sh`](deploy.sh)** on the server: installs Python/web dependencies when their lock files changed,
   dumps the database and runs `alembic upgrade head` when the schema is behind, reloads the three pm2
   processes from [`ecosystem.config.cjs`](ecosystem.config.cjs), then health-checks API, web and the proxy.
5. **Smoke test** of `https://saferoute.momo.co.zw/backend/health` from the runner.

**GitHub secret (Settings > Secrets and variables > Actions):** one, `DEPLOY_SSH_KEY`, the private half of a key
that can only log in as the unprivileged `saferoute` user. The matching public key is in
`/home/saferoute/.ssh/authorized_keys` (installed by `DEPLOY_PUBLIC_KEY=... ./bootstrap.sh`). The server address,
user and host key are public and live in the workflow file. Production settings (`.env`) stay on the server only.

**Roll back:** re-run an earlier green workflow run. **Skip the tests in an emergency:** Actions > Run workflow
> tick "skip_tests".

| Process (pm2) | Listens on |
| --- | --- |
| `saferoute-web` (`next start`) | `127.0.0.1:3000` |
| `saferoute-api` (uvicorn, 1 worker) | `127.0.0.1:8000` |
| `saferoute-scheduler` (RSS, pipeline, social, WhatsApp dispatch) | nothing; set `RSS_SCHEDULER_ENABLED=false` in `.env` to pause it |

nginx overwrites `X-Forwarded-For` with the real client address, which is why `TRUST_FORWARDED_FOR=true`
is safe in the server's `.env`.

**First admin user** (after the first successful deploy; the password prompt is hidden):

```bash
ssh -t root@<server>
sudo -u saferoute -H bash -c 'cd /opt/saferoutezw/app/apps/api && /opt/saferoutezw/venv/bin/python scripts/create_user.py --email you@example.org --name "Your Name" --role admin'
```

## Useful commands

```bash
systemctl status nginx postgresql        # services
sudo -u saferoute pm2 status             # app processes (once deployed)
nginx -t && systemctl reload nginx       # after editing nginx config
saferoute-backup-db                      # take a backup now
certbot renew --dry-run                  # check certificate renewal
```

# DEPLOY — running the Noore Candles store in production

One small Linux server (Ubuntu 24.04) in an Indian region runs everything: Caddy (HTTPS),
gunicorn (the Django API), the background worker, and PostgreSQL. The built React storefront is
served from the same domain. This matches roadmap decision A7.

What has and has not been proven is stated at the end. Read that first if you are short of time.

Throughout: the code lives in `/srv/noore`, the service user is `noore`, the domain is
`shop.example.in`. Replace with your own.

## 0. Before you start (owner tasks)

- A domain, with an A record pointing at the server's IP address.
- Razorpay KYC complete; live key id, key secret.
- An email provider with your sending domain verified (SPF and DKIM). The project is wired for
  Mailgun through django-anymail; another provider means changing `DJANGO_EMAIL_BACKEND`.
- Somewhere off the server for backups (any storage `rclone` supports).
- Real catalogue data: photos, prices, MRP, weights, policy text, unit cost per batch.

## 1. First install

    sudo apt update && sudo apt install -y python3.11 python3.11-venv postgresql caddy git rclone
    # Node 20 LTS for building the storefront (from nodejs.org or your preferred method).

    sudo adduser --system --group --home /srv/noore noore
    sudo -u noore git clone <your repository url> /srv/noore
    sudo mkdir -p /var/backups/noore && sudo chown noore:noore /var/backups/noore

Database (choose your own password):

    sudo -u postgres psql -c "CREATE USER noore WITH PASSWORD 'CHANGE-ME' CREATEDB"
    sudo -u postgres psql -c "CREATE DATABASE noore OWNER noore"

Backend:

    cd /srv/noore/backend
    sudo -u noore python3.11 -m venv venv
    sudo -u noore venv/bin/pip install -r requirements.txt
    sudo -u noore cp ../deploy/env.production.example .env
    sudo -u noore nano .env          # fill in every value; see backend/.env.example for each one
    sudo chmod 600 .env

    sudo -u noore venv/bin/python manage.py migrate
    sudo -u noore venv/bin/python manage.py createcachetable     # shared rate-limit counters
    sudo -u noore venv/bin/python manage.py collectstatic --noinput
    sudo -u noore venv/bin/python manage.py check --deploy
    sudo -u noore venv/bin/python manage.py createsuperuser
    sudo -u noore venv/bin/python manage.py claim_shop --email you@example.in

The database starts empty: migrations only. `seed_noore` refuses to run here (DEBUG is off).
Add the real products through the dashboard, sizes in Django admin (Products, then the variants
table on the product), and stock by adding a Batch (Inventory, Batches).

Storefront (the API address is baked in at build time):

    cd /srv/noore/frontend
    sudo -u noore cp .env.example .env.production
    sudo -u noore nano .env.production
        VITE_API_BASE_URL=https://shop.example.in/api/v1/
        VITE_SERVER_URL=https://shop.example.in/
        VITE_SUPPORT_EMAIL=...   VITE_WHATSAPP_NUMBER=...
    sudo -u noore npm ci
    sudo -u noore npm run build

Services:

    sudo cp /srv/noore/deploy/noore-web.service /srv/noore/deploy/noore-worker.service \
            /srv/noore/deploy/noore-backup.service /srv/noore/deploy/noore-backup.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now noore-web noore-worker noore-backup.timer

Caddy:

    sudo cp /srv/noore/deploy/Caddyfile /etc/caddy/Caddyfile
    printf 'SITE_ADDRESS=shop.example.in\nAPP_ROOT=/srv/noore\n' | sudo tee /etc/caddy/noore.env
    sudo mkdir -p /etc/systemd/system/caddy.service.d
    printf '[Service]\nEnvironmentFile=/etc/caddy/noore.env\n' | sudo tee /etc/systemd/system/caddy.service.d/noore.conf
    sudo systemctl daemon-reload && sudo systemctl restart caddy

Caddy must be able to read `/srv/noore/frontend/dist`, `backend/staticfiles` and `backend/media`
(`sudo chmod o+rx /srv/noore` and those folders, or add the `caddy` user to the `noore` group).

Check:

    curl -s https://shop.example.in/api/v1/health/?strict=1
    # {"status":"ok","database":true,"cache":true,"worker":{"ok":true,...}}

Then, in the Razorpay dashboard (Live Mode), add the webhook
`https://shop.example.in/api/v1/payments/razorpay/webhook/` with event `payment.captured`, using
the same secret as `RAZORPAY_WEBHOOK_SECRET`.

## 2. Deploy a new version

    cd /srv/noore
    sudo -u noore deploy/backup.sh                       # always back up first (needs the env, see section 4)
    sudo -u noore git fetch && sudo -u noore git checkout <tag or commit>
    cd backend
    sudo -u noore venv/bin/pip install -r requirements.txt
    sudo -u noore venv/bin/python manage.py migrate
    sudo -u noore venv/bin/python manage.py collectstatic --noinput
    cd ../frontend && sudo -u noore npm ci && sudo -u noore npm run build
    sudo systemctl restart noore-web noore-worker
    curl -s https://shop.example.in/api/v1/health/?strict=1

Shoppers see the new storefront on their next page load (`index.html` is never cached).

## 3. Roll back

Code only (no migration in the bad release):

    cd /srv/noore && sudo -u noore git checkout <previous tag>
    cd frontend && sudo -u noore npm ci && sudo -u noore npm run build
    sudo systemctl restart noore-web noore-worker

If the bad release included a migration, roll the migration back **before** checking out the
older code, using the exact command recorded for that phase in `docs/BUILD_LOG.md`
(for example `python manage.py migrate store 0034`). Every migration in this project is
reversible and its rollback command is written there. If data was damaged, restore (section 5).

## 4. Backups

`deploy/backup.sh` runs nightly at 02:30 from `noore-backup.timer`. It writes a compressed
PostgreSQL dump and a tarball of `backend/media` to `/var/backups/noore`, checks the dump is
readable, keeps 14 days, and copies them off the server when `BACKUP_REMOTE` is set.

    sudo -u noore cp /srv/noore/deploy/backup.env.example /srv/noore/deploy/backup.env
    sudo -u noore nano /srv/noore/deploy/backup.env      # set BACKUP_REMOTE after `rclone config`
    sudo systemctl start noore-backup.service            # run one now
    systemctl status noore-backup.service                # must say it succeeded
    systemctl list-timers noore-backup.timer

To run it by hand outside systemd: `set -a; . backend/.env; . deploy/backup.env; set +a; deploy/backup.sh`

**Until `BACKUP_REMOTE` is set, backups exist only on the server and do not protect you if the
server is lost.** The script says so every time it runs.

## 5. Restore

Drill (safe, does not touch the live database). Do this once after launch and write the timings
into `docs/BUILD_LOG.md`; a backup that has never been restored does not count.

    export ADMIN_DATABASE_URL=postgres://noore:CHANGE-ME@127.0.0.1:5432/postgres
    deploy/restore.sh /var/backups/noore/db-<stamp>.dump
    # prints how long it took and row counts; compare them with the live site, then drop the scratch database

Real restore (replaces the live data):

    sudo systemctl stop noore-web noore-worker
    sudo -u postgres psql -c "ALTER DATABASE noore RENAME TO noore_broken"
    sudo -u postgres psql -c "CREATE DATABASE noore OWNER noore"
    pg_restore --no-owner --no-privileges --exit-on-error -d postgres://noore:CHANGE-ME@127.0.0.1:5432/noore /var/backups/noore/db-<stamp>.dump
    sudo -u noore tar -xzf /var/backups/noore/media-<stamp>.tar.gz -C /srv/noore/backend
    cd /srv/noore/backend && sudo -u noore venv/bin/python manage.py migrate
    sudo systemctl start noore-web noore-worker
    # when you are sure: sudo -u postgres psql -c "DROP DATABASE noore_broken"

Orders placed after the backup was taken are not in it. Check the Razorpay dashboard for payments
made in that gap.

## 6. Rotate a secret

Edit `/srv/noore/backend/.env`, then `sudo systemctl restart noore-web noore-worker`.

| Secret | Also change it at | Effect of rotating |
|---|---|---|
| `DJANGO_SECRET_KEY` | nowhere | Everyone is signed out. Unused "create your account" links stop working |
| `RAZORPAY_KEY_SECRET` (and key id) | Razorpay dashboard, API Keys, regenerate | Payments in progress during the swap may need to be retried |
| `RAZORPAY_WEBHOOK_SECRET` | Razorpay dashboard, Webhooks, edit the secret | Razorpay's retries of events sent with the old secret are refused; the reconcile job still confirms those payments |
| Database password | `ALTER USER noore WITH PASSWORD '...'`, then `DATABASE_URL` and `ADMIN_DATABASE_URL` | None after restart |
| `MAILGUN_API_KEY` | your email provider | None after restart |

If a secret was ever committed, pasted in a chat or shown on a screen share, rotate it.

## 7. Monitoring

- **Uptime.** Point any uptime service at `https://shop.example.in/api/v1/health/?strict=1`
  (expects HTTP 200) and at the home page. `?strict=1` also fails when the background worker has
  stopped, which would silently stop order emails and payment reconciliation.
- **Errors.** Set `ERROR_REPORT_EMAILS`. Every backend error is emailed there with personal data
  masked, at most once per distinct error every five minutes.
- **Logs.** `journalctl -u noore-web -f`, `journalctl -u noore-worker -f`, `journalctl -u caddy -f`.
- **Daily, in the Razorpay dashboard:** payments stuck in "authorized", failed webhooks, disputes.
- **Daily, in "Handle orders":** anything marked "Needs attention".

## 8. HSTS

`SECURE_HSTS_SECONDS` starts at 3600 (one hour). After a week of working HTTPS, set it to
`31536000`. Do not raise it earlier: browsers remember it and you cannot take it back quickly.

## 9. Go-live checklist

- [ ] `python manage.py check --deploy` is clean
- [ ] `python -m pytest -q` passes on the server's PostgreSQL (needs `requirements-dev.txt`; the `noore` user has CREATEDB)
- [ ] Health check returns ok with `?strict=1`
- [ ] HTTP redirects to HTTPS
- [ ] `sudo reboot`, then the health check is ok again without touching anything
- [ ] Backup ran, went off-site, and the restore drill is written up with timings
- [ ] Razorpay live webhook added; one real low-value order paid, shipped, delivered and refunded
- [ ] Order emails arrive in an inbox, not spam
- [ ] From your own computer: `$env:E2E_BASE_URL = "https://shop.example.in"; npx playwright test`, then cancel the smoke-test order in "Handle orders"
- [ ] Policy text is real and `PLACEHOLDER_COPY` is `false`; support email and WhatsApp number are real
- [ ] The CA or lawyer's answers on product declarations, published contact details and privacy are applied

## What has been proven, and what has not

Proven in the build session of 3 Oct 2026, on a local production-like stack (PostgreSQL 16.2,
gunicorn, the worker, Caddy 2.8.4, the built storefront, `DJANGO_DEBUG=False`):

- The `Caddyfile` validates and routes correctly: storefront, deep links, API, admin, static
  files, product link-preview pages, `robots.txt`, `sitemap.xml`; a missing asset is a 404.
- The full test suite passes on PostgreSQL: 179 passed, 0 skipped, including both concurrency tests.
- `check --deploy` passes at warning level.
- The deployed-site smoke test placed a Cash on Delivery order through Caddy.
- Stopping web and worker made the health check fail; starting them made it pass again.
- `backup.sh` then `restore.sh` round-tripped the database with matching row counts.

**Not proven**, because they need your server, domain and accounts: the systemd units as
installed (they were written, not run), automatic HTTPS, the off-site copy (`rclone`), real email
delivery, Razorpay live mode, a reboot, and the restore drill on production data. Each has a
checkbox above.

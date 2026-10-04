#!/usr/bin/env bash
# Restore a database backup into a SCRATCH database and check it, without touching the live one.
#
#   deploy/restore.sh /var/backups/noore/db-20261003-023000.dump  [scratch_db_name]
#
# Needs ADMIN_DATABASE_URL: a connection that may create databases (e.g. the postgres
# superuser's "postgres" database). Prints row counts of the main tables so the result can be
# compared with the live site. To actually replace the live database, see docs/DEPLOY.md.
set -euo pipefail

dump="${1:?usage: restore.sh <db dump file> [scratch database name]}"
scratch="${2:-noore_restore_check}"
: "${ADMIN_DATABASE_URL:?ADMIN_DATABASE_URL is not set (a connection allowed to create databases)}"

[ -f "$dump" ] || { echo "no such file: $dump" >&2; exit 1; }
case "$scratch" in *[!a-z0-9_]*) echo "scratch database name must be lowercase letters, digits and _" >&2; exit 1;; esac

started=$(date +%s)
psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -q -c "DROP DATABASE IF EXISTS $scratch" -c "CREATE DATABASE $scratch"

# The same server, the scratch database: swap the database name at the end of the URL.
scratch_url="$(printf '%s' "$ADMIN_DATABASE_URL" | sed -E "s#/[^/?]+(\?.*)?\$#/$scratch\1#")"

pg_restore --no-owner --no-privileges --exit-on-error --dbname="$scratch_url" "$dump"

echo "restored into database '$scratch' in $(( $(date +%s) - started )) seconds. Row counts:"
psql "$scratch_url" -v ON_ERROR_STOP=1 -At -F ' = ' <<'SQL'
SELECT 'products', count(*) FROM store_product
UNION ALL SELECT 'variants', count(*) FROM catalog_productvariant
UNION ALL SELECT 'orders', count(*) FROM store_cartorder
UNION ALL SELECT 'order lines', count(*) FROM store_cartorderitem
UNION ALL SELECT 'stock movements', count(*) FROM inventory_stockmovement
UNION ALL SELECT 'audit rows', count(*) FROM core_auditlog
UNION ALL SELECT 'users', count(*) FROM userauths_user
UNION ALL SELECT 'migrations applied', count(*) FROM django_migrations;
SQL
echo "Drop the scratch database when you are done:  psql \"\$ADMIN_DATABASE_URL\" -c 'DROP DATABASE $scratch'"

#!/usr/bin/env bash
# Daily PostgreSQL backup (cron: 0 2 * * * /opt/selfxtrack/deploy/backup.sh). Keeps 14 days.
# Copy the backups off the server too (e.g. to an S3 bucket in ap-south-1 / Mumbai).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U selfx selfx | gzip > "backups/selfx-$(date +%F).sql.gz"
find backups -name 'selfx-*.sql.gz' -mtime +14 -delete
echo "backup ok"

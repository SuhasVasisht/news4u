#!/bin/sh
set -eu

: "${INTERNAL_API_KEY:?INTERNAL_API_KEY is required}"
: "${DAILY_SYNC_CRON:=5 5 * * *}"
: "${APP_TIMEZONE:=America/Los_Angeles}"

export TZ="$APP_TIMEZONE"

mkdir -p /var/log/news-app

cat > /etc/cron.d/news-app-daily-sync <<EOF
${DAILY_SYNC_CRON} root /bin/sh -lc 'curl -fsS -X POST -H "Authorization: Bearer ${INTERNAL_API_KEY}" http://web:3000/api/internal/jobs/daily-sync >> /var/log/news-app/daily-sync.log 2>&1'
EOF
chmod 0644 /etc/cron.d/news-app-daily-sync

echo "scheduler configured for ${DAILY_SYNC_CRON} (${APP_TIMEZONE})"
exec cron -f

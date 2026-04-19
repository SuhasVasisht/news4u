#!/bin/sh
set -eu

: "${DAILY_SYNC_CRON:=5 5 * * *}"
: "${APP_TIMEZONE:=America/Los_Angeles}"

export TZ="$APP_TIMEZONE"

mkdir -p /var/log/news-app

if ! npm run startup:catchup >> /var/log/news-app/startup-catchup.log 2>&1; then
  echo "startup catch-up failed; scheduler will continue and retry on cron" >&2
fi

cat > /etc/cron.d/news-app-daily-sync <<EOF
${DAILY_SYNC_CRON} root /bin/sh -lc 'cd /app && npm run job:daily-sync >> /var/log/news-app/daily-sync.log 2>&1'
EOF
chmod 0644 /etc/cron.d/news-app-daily-sync

echo "scheduler configured for ${DAILY_SYNC_CRON} (${APP_TIMEZONE})"
exec cron -f

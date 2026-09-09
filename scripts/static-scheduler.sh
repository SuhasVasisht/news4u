#!/bin/sh
set -eu
cd /app
export PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"
export APP_TIMEZONE="${APP_TIMEZONE:-America/Los_Angeles}"
export TZ="$APP_TIMEZONE"
ln -snf "/usr/share/zoneinfo/$TZ" /etc/localtime
mkdir -p /var/log/news-app /app/data /app/out
umask 077
# Cron does not inherit the complete container environment. Keep credentials private.
node -e 'const fs=require("fs"); const quote=s=>"\x27"+s.replaceAll("\x27","\x27\\\x27\x27")+"\x27"; fs.writeFileSync("/run/news-app-env.sh",Object.entries(process.env).filter(([k])=>/^[A-Za-z_][A-Za-z0-9_]*$/.test(k)).map(([k,v])=>`export ${k}=${quote(v)}`).join("\n"));'
printf '%s root . /run/news-app-env.sh; cd /app && npm run build:daily >> /var/log/news-app/static-build.log 2>&1\n' "${DAILY_SYNC_CRON:-5 5 * * *}" > /etc/cron.d/news-app-static
chmod 0644 /etc/cron.d/news-app-static
if ! node -e 'const r=require("./out/build-review.json"); process.exit(r.editionDate===new Intl.DateTimeFormat("en-CA",{timeZone:process.env.APP_TIMEZONE}).format(new Date())?0:1)' 2>/dev/null; then
  npm run build:daily >> /var/log/news-app/static-build.log 2>&1 || echo 'Initial build failed; inspect static-build.log. Existing HTML is unchanged.' >&2
fi
exec cron -f

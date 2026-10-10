"""Private daily logs for every supported publisher command, with bounded retention."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo


def rotate_logs(directory, now=None):
    now = now or datetime.now(timezone.utc)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for file in directory.glob('publisher-????-??-??.log'):
        if file.is_file() and not file.is_symlink() and now.timestamp() - file.stat().st_mtime > 30 * 86400:
            file.unlink()


def redactor(root):
    secrets = [value for key, value in os.environ.items() if re.search('KEY|TOKEN|SECRET|PASSWORD', key, re.I) and len(value) >= 8]
    # Native service supplies .env through systemd; manual npm runs load it in Node.
    # Read only secret values here so both paths redact the same credentials.
    for name in ('.env', '.env.newsletters'):
        file = root / name
        if not file.exists():
            continue
        for line in file.read_text().splitlines():
            key, sep, value = line.partition('=')
            value = value.strip().strip('\"\'')
            if sep and re.search('KEY|TOKEN|SECRET|PASSWORD', key, re.I) and len(value) >= 8:
                secrets.append(value)
    def redact(text):
        for value in sorted(set(secrets), key=len, reverse=True):
            text = text.replace(value, '[REDACTED]')
        return re.sub(r'(?i)([?&](?:token|key|password|secret|signature)=)[^&\s]+', r'\1[REDACTED]', text)
    return redact


def open_log(root):
    directory = Path(os.environ.get('NEWS_PUBLISHER_LOG_DIR', root / 'data/publisher-logs'))
    rotate_logs(directory)
    date = datetime.now(ZoneInfo(os.environ.get('APP_TIMEZONE', 'America/Los_Angeles'))).date()
    path = directory / f'publisher-{date}.log'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    return os.fdopen(fd, 'a', buffering=1), redactor(root)


def record(log, redact, text):
    stamp = datetime.now(timezone.utc).isoformat()
    safe = redact(text.rstrip('\n'))
    log.write(f'{stamp} {safe}\n')
    print(safe, flush=True)

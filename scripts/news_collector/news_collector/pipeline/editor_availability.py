"""Persist hard account exhaustion separately from transient model capacity."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo


def quota_path(output):
    return Path(os.environ.get('NEWS_EDITOR_QUOTA_FILE', Path(output).parent / 'editor-quota.json'))


def active_quota_block(path, now=None):
    if not path.exists():
        return None
    block = json.loads(path.read_text())
    now = now or datetime.now(timezone.utc)
    if block.get('retryAfter') and datetime.fromisoformat(block['retryAfter']) <= now:
        return None
    return block


def record_quota_error(stderr, path, now=None):
    if not re.search(r'^ERROR:.*(?:hit your usage limit|insufficient_quota|exceeded your current quota)', stderr, re.I | re.M):
        return False
    now = now or datetime.now(timezone.utc)
    retry_after = None
    match = re.search(r'try again at ([A-Za-z]{3} \d{1,2})(?:st|nd|rd|th)?, (\d{4} \d{1,2}:\d{2} [AP]M)', stderr, re.I)
    if match:
        reset = datetime.strptime(f'{match[1]}, {match[2]}', '%b %d, %Y %I:%M %p')
        retry_after = reset.replace(tzinfo=ZoneInfo(os.environ.get('APP_TIMEZONE', 'America/Los_Angeles'))).isoformat()
    block = {'reason': 'editor_usage_limit', 'detectedAt': now.isoformat(), 'retryAfter': retry_after,
             'action': 'Fund or renew the editor account, then run publish:daily -- --retry-editor'}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(block, indent=2))
    temporary.replace(path)
    return True

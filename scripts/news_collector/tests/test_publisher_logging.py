from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import sys

MODULE = Path(__file__).resolve().parents[2] / 'lib/publisher_logging.py'
spec = importlib.util.spec_from_file_location('publisher_logging', MODULE)
logging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logging)


def test_retention_removes_only_publisher_logs_older_than_30_days(tmp_path):
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    for name, days in [('publisher-2026-09-09.log', 31), ('publisher-2026-09-10.log', 30),
                       ('publisher-2026-10-10.log', 0), ('other.log', 40)]:
        file = tmp_path / name
        file.write_text('test')
        stamp = now.timestamp() - days * 86400
        os.utime(file, (stamp, stamp))
    logging.rotate_logs(tmp_path, now)
    assert not (tmp_path / 'publisher-2026-09-09.log').exists()
    assert len(list(tmp_path.iterdir())) == 3


def test_file_credentials_and_environment_are_redacted(tmp_path, monkeypatch):
    (tmp_path / '.env').write_text('NEWS_MAIL_PASSWORD="private-email-password"\n')
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'private-cloud-token')
    redact = logging.redactor(tmp_path)
    assert redact('private-email-password private-cloud-token https://example.org/?token=secret&ok=1') == (
        '[REDACTED] [REDACTED] https://example.org/?token=[REDACTED]&ok=1')


def test_wrapper_records_child_progress_errors_and_exit(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setenv('NEWS_PUBLISHER_LOG_DIR', str(tmp_path))
    monkeypatch.setenv('TEST_SECRET_TOKEN', 'sensitive-log-secret')
    import shutil
    checkout = tmp_path / 'checkout'
    (checkout / 'scripts/lib').mkdir(parents=True)
    shutil.copyfile(MODULE, checkout / 'scripts/lib/publisher_logging.py')
    wrapper = checkout / 'scripts/with-publisher-lock.py'
    shutil.copyfile(MODULE.parents[1] / 'with-publisher-lock.py', wrapper)
    result = subprocess.run([sys.executable, str(wrapper), sys.executable, '-c',
        'import os,sys; print("progress " + os.environ["TEST_SECRET_TOKEN"]); print("failure",file=sys.stderr); sys.exit(7)'],
        capture_output=True, text=True)
    assert result.returncode == 7
    content = next(tmp_path.glob('publisher-*.log')).read_text()
    assert 'run_start' in content and 'progress [REDACTED]' in content and 'failure' in content and 'exit=7' in content
    assert 'sensitive-log-secret' not in content
    assert next(tmp_path.glob('publisher-*.log')).stat().st_mode & 0o777 == 0o600

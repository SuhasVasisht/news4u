"""Interactively store and verify newsletter credentials without echoing the password."""
from getpass import getpass
import imaplib
import os
from pathlib import Path
import ssl
import tempfile


def save_credentials(path: Path, values: dict[str, str]):
    if any('\n' in value or '\r' in value for value in values.values()):
        raise ValueError('Mailbox settings must be single-line values')
    existing = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                existing[key] = value
    values = {**existing, **values}
    fd, temporary = tempfile.mkstemp(prefix='.env.newsletters-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write('# Private newsletter mailbox settings. Do not commit or publish.\n')
            handle.write('\n'.join(f'{key}={value}' for key, value in values.items()) + '\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    host = input('IMAP host [imap.gmail.com]: ').strip() or 'imap.gmail.com'
    username = input('Dedicated newsletter email address: ').strip()
    folder = input('Mailbox folder [INBOX]: ').strip() or 'INBOX'
    password = getpass('Mailbox app password (hidden): ').strip()
    if host == 'imap.gmail.com':
        password = password.replace(' ', '')
    if not username or not password:
        raise SystemExit('No credentials saved: email address and app password are required.')
    try:
        with imaplib.IMAP4_SSL(host, 993, ssl_context=ssl.create_default_context(), timeout=20) as mailbox:
            mailbox.login(username, password)
            status, _ = mailbox.select(folder, readonly=True)
            if status != 'OK':
                raise ValueError('Folder unavailable')
    except Exception:
        raise SystemExit('Mailbox verification failed. Check the host, address, folder and app password; no credentials saved.') from None
    root = Path(__file__).resolve().parents[4]
    save_credentials(root / '.env.newsletters', {
        'NEWS_MAIL_ENABLED': '1', 'NEWS_MAIL_HOST': host, 'NEWS_MAIL_PORT': '993',
        'NEWS_MAIL_USERNAME': username, 'NEWS_MAIL_PASSWORD': password, 'NEWS_MAIL_FOLDER': folder,
    })
    print('Mailbox verified. Private credentials saved to .env.newsletters (owner-only permissions).')
    print('Email collectors enabled for the next daily collection. Website sources remain available.')


if __name__ == '__main__':
    main()

from dataclasses import replace
from email.message import EmailMessage
import imaplib
import ssl

import pytest

from news_collector.collectors.base import CollectorContext
from news_collector.collectors.newsletter_mail import NewsletterMailCollector, story_links, article_url
from news_collector.pipeline.normalize import normalize_item
from tests.test_collectors import make_settings, make_repository


def mail(body=None, sender='TLDR <dan@tldrnewsletter.com>'):
    msg = EmailMessage()
    msg['From'], msg['To'] = sender, 'private-inbox@example.com'
    msg['Date'] = 'Wed, 09 Sep 2026 10:00:00 +0000'
    msg['Subject'] = 'Private newsletter subject'
    msg.set_content('Plain alternative')
    msg.add_alternative(body or '''<p><a href="https://example.com/article?utm_source=tldr"><b>A new reasoning model (3 minute read)</b></a> A useful summary.</p>
        <a href="https://ads.example/">Try our product (Sponsor)</a>
        <a href="https://tldr.tech/unsubscribe?token=secret">Unsubscribe from this newsletter</a>
        <a href="https://tldr.tech/confirm?token=secret">Confirm your email address</a>
        <img src="https://tracking.example/pixel?recipient=secret">''', subtype='html')
    return msg.as_bytes()


def test_mime_sender_ads_and_subscription_filter():
    date, key, links = story_links(mail(), ['tldrnewsletter.com'])
    assert date.isoformat() == '2026-09-09T10:00:00+00:00'
    assert len(key) == 64
    assert len(links) == 1
    assert links[0][0] == 'A new reasoning model'
    assert story_links(mail(sender='Fake <news@tldrnewsletter.com.evil.test>'), ['tldrnewsletter.com']) is None
    with pytest.raises(ValueError):
        story_links(mail(body='<p>Welcome, confirm your subscription.</p>'), ['tldrnewsletter.com'])
    with pytest.raises(ValueError):
        article_url('https://mail.example/confirm?token=secret')


class Mailbox:
    validity = b'123'
    messages = {b'1': mail()}
    calls = []
    fail = False

    def __init__(self, host, port, ssl_context, timeout):
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert ssl_context.check_hostname
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def login(self, username, password):
        if self.fail:
            raise RuntimeError('password=supersecret private-inbox@example.com')
    def select(self, folder, readonly):
        assert readonly
        return 'OK', [b'1']
    def response(self, name): return name, [self.validity]
    def uid(self, action, *args):
        self.calls.append((action, args))
        if action == 'search': return 'OK', [b' '.join(self.messages)]
        assert action == 'fetch'
        assert args[1] == '(BODY.PEEK[]<0.2000001>)'
        return 'OK', [(b'1 BODY[]', self.messages[args[0].encode()])]


def setup(tmp_path, monkeypatch):
    settings = replace(make_settings(tmp_path), mail_host='imap.example.com',
        mail_username='private-inbox@example.com', mail_password='supersecret')
    c = NewsletterMailCollector(CollectorContext(name='tldr_email',
        config={'category': 'tech', 'sender_domains': ['tldrnewsletter.com'], 'link_delay_seconds': 0},
        defaults={}, settings=settings, repository=make_repository(tmp_path)))
    monkeypatch.setattr('news_collector.collectors.newsletter_mail.imaplib.IMAP4_SSL', Mailbox)
    monkeypatch.setattr('news_collector.collectors.newsletter_mail.download',
        lambda *args, **kwargs: (b'<article>A model announcement.</article>', 'https://example.com/article?utm_source=tldr'))
    Mailbox.calls = []
    monkeypatch.setattr(Mailbox, 'messages', {b'1': mail()})
    return c


def test_progress_only_after_persistence_and_repeat_runs(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    result = c.run(force=True)
    assert result.status == 'ok'
    assert len(result.items) == 1
    assert 'mail_done' not in c.get_state()
    # A crash before persistence/acknowledgement replays the message.
    assert len(c.run(force=True).items) == 1
    for item in result.items:
        c.repository.insert_raw_item(item)
        assert c.repository.insert_normalized_item(normalize_item(item))
        assert c.repository.insert_normalized_item(normalize_item(item)) is None
        assert item.url == 'https://example.com/article'
        assert 'private-inbox' not in item.model_dump_json()
        assert 'supersecret' not in item.model_dump_json()
    c.acknowledge()
    assert c.get_state()['mail_done'] == ['1']
    result = c.run(force=True)
    assert result.status == 'ok' and result.items == []
    # A replacement mailbox may reuse UIDs; UIDVALIDITY prevents lost mail.
    monkeypatch.setattr(Mailbox, 'validity', b'456')
    assert len(c.run(force=True).items) == 1


def test_partial_links_retry_and_auth_error_redaction(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    def unavailable(*args, **kwargs): raise RuntimeError('private url')
    monkeypatch.setattr('news_collector.collectors.newsletter_mail.download', unavailable)
    result = c.run(force=True)
    assert result.status == 'degraded'
    assert 'mail_done' not in c.get_state()
    monkeypatch.setattr(Mailbox, 'fail', True)
    result = c.run(force=True)
    assert result.status == 'degraded'
    assert 'supersecret' not in repr(result)
    assert 'private-inbox' not in repr(result)
    assert 'supersecret' not in repr(c.context.settings)


def test_plaintext_email():
    msg = EmailMessage()
    msg['From'] = 'news@alphasignal.ai'
    msg['Date'] = 'Wed, 09 Sep 2026 10:00:00 +0000'
    msg.set_content('New model research released\nhttps://example.com/research\n')
    assert story_links(msg.as_bytes(), ['alphasignal.ai'])[2][0][0] == 'New model research released'


def test_mail_authentication_rejection_has_actionable_redacted_reason(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    def rejected(*args):
        raise imaplib.IMAP4.error('Invalid credentials private-inbox@example.com supersecret')
    monkeypatch.setattr(Mailbox, 'login', rejected)
    result = c.run(force=True)
    assert result.status == 'degraded'
    assert 'authentication rejected' in result.reason
    assert 'mailbox/app password' in result.reason
    assert 'supersecret' not in repr(result)
    assert 'private-inbox' not in repr(result)
    assert 'mail_done' not in c.get_state()


def test_partial_mail_acknowledges_only_complete_messages(tmp_path, monkeypatch):
    c = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(Mailbox, 'messages', {
        b'1': mail(body='<a href="https://example.com/broken">A temporarily unavailable article</a>'),
        b'2': mail(),
    })
    def fetch(client, link, *args, **kwargs):
        if 'broken' in link:
            raise RuntimeError('Unavailable')
        return b'<article>News</article>', 'https://example.com/article'
    monkeypatch.setattr('news_collector.collectors.newsletter_mail.download', fetch)
    result = c.run(force=True)
    assert result.status == 'partial' and len(result.items) == 1
    assert 'mail_done' not in c.get_state()
    c.acknowledge()
    assert c.get_state()['mail_done'] == ['2']
    Mailbox.calls = []
    c.run(force=True)
    assert [args[0] for action, args in Mailbox.calls if action == 'fetch'] == ['1']


def test_rate_limit_stops_repeated_host_requests(tmp_path, monkeypatch):
    import httpx
    c = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(Mailbox, 'messages', {b'1': mail(body='''
        <a href="https://example.com/a">A new model released</a>
        <a href="https://example.com/b">Another story about AI</a>''')})
    calls = []
    def limited(client, link, *args, **kwargs):
        calls.append(link)
        response = httpx.Response(429, request=httpx.Request('GET', link))
        response.raise_for_status()
    monkeypatch.setattr('news_collector.collectors.newsletter_mail.download', limited)
    assert c.run(force=True).status == 'degraded'
    assert len(calls) == 1


def test_credentials_saved_privately_and_not_echoed(tmp_path):
    from news_collector.jobs.setup_mailbox import save_credentials
    path = tmp_path / '.env.newsletters'
    save_credentials(path, {'NEWS_MAIL_PASSWORD': 'test-secret', 'NEWS_MAIL_ENABLED': '1'})
    assert path.stat().st_mode & 0o777 == 0o600
    assert 'test-secret' in path.read_text()
    with pytest.raises(ValueError):
        save_credentials(path, {'NEWS_MAIL_PASSWORD': 'bad\nINJECTED=value'})
    assert 'test-secret' in path.read_text()


def test_collect_job_does_not_advance_mail_progress_on_storage_failure(tmp_path, monkeypatch):
    from news_collector.jobs import collect
    c = setup(tmp_path, monkeypatch)
    monkeypatch.setenv('NEWS_COLLECTOR_FORCE_RUN', '1')
    monkeypatch.delenv('NEWS_COLLECTOR_SOURCES', raising=False)
    monkeypatch.setattr(collect, 'build_runtime', lambda: (c.context.settings, {'trust_scores': {}}, c.repository, [c]))
    monkeypatch.setattr(collect, 'prepare_images', lambda *args: {})
    monkeypatch.setattr(collect, 'refresh_recent_images', lambda *args: {})
    original_insert = c.repository.insert_normalized_item
    def fail(*args): raise RuntimeError('Disk unavailable')
    monkeypatch.setattr(c.repository, 'insert_normalized_item', fail)
    with pytest.raises(RuntimeError, match='Disk unavailable'):
        collect.main()
    assert 'mail_done' not in c.get_state()
    monkeypatch.setattr(c.repository, 'insert_normalized_item', original_insert)
    collect.main()
    assert c.get_state()['mail_done'] == ['1']


def test_private_link_parameters_removed_and_actions_blocked_before_redirect(monkeypatch):
    import httpx
    from news_collector.pipeline import images
    from news_collector.collectors.newsletter_mail import public_story_url
    assert public_story_url('https://example.com/a?email=private%40example.com&token=secret&accessToken=gift-secret&utm_source=tldr&id=3') == 'https://example.com/a?id=3'
    monkeypatch.setattr(images, 'public_url', lambda url: url)
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'location': 'https://example.com/confirm?token=secret'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match='action'):
            images.download(client, 'https://example.com/track', 1000, validate_url=article_url)
    assert calls == ['https://example.com/track']


def test_confirmation_mail_is_ignored_without_following_links():
    message = EmailMessage()
    message['From'] = 'news@alphasignal.ai'
    message['Date'] = 'Wed, 09 Sep 2026 10:00:00 +0000'
    message['Subject'] = 'Confirm your subscription'
    message.set_content('Confirm your email address https://example.com/confirm?token=private')
    message.add_alternative('<a href="https://example.com/help">Please follow these instructions</a>', subtype='html')
    assert story_links(message.as_bytes(), ['alphasignal.ai']) is None


def test_tldr_template_uses_story_blocks_not_nested_ads_or_footer():
    body = '''<div class="text-block"><a href="https://example.com/story"><b>React 19.3 (23 minute read)</b></a>Release details.</div>
    <div class="text-block"><a href="https://ads.example"><b>A new product (Sponsor)</b></a><a href="https://ads.example/book">Get your copy</a></div>
    <div class="text-block"><a href="https://jobs.example"><b>create your own role</b></a></div>'''
    links = story_links(mail(body), ['tldrnewsletter.com'])[2]
    assert [link[0] for link in links] == ['React 19.3']
    assert 'Release details' in links[0][2]


def test_alphasignal_template_reads_main_articles_and_excludes_paid_signals():
    body = '''<table><tbody><tr><td class="h1">A new image model</td></tr><tr><td>Model details.</td></tr><tr><td><a href="https://example.com/model">READ MORE</a></td></tr></tbody></table>
    <table><tbody><tr><td><a class="h1" href="https://example.com/paper">An interesting research paper</a></td></tr><tr><td>42 Likes</td></tr></tbody></table>
    <table><tbody><tr><td><a class="h1" href="https://ads.example">A paid cloud announcement</a></td></tr><tr><td>Presented by Cloud</td></tr></tbody></table>
    <a href="https://ads.example">WORK WITH US</a>'''
    links = story_links(mail(body, 'news@alphasignal.ai'), ['alphasignal.ai'])[2]
    assert [link[0] for link in links] == ['A new image model', 'An interesting research paper']
    assert 'Model details' in links[0][2]


def test_historical_newsletter_urls_obey_current_privacy_rules(tmp_path):
    from datetime import datetime, timezone
    from news_collector.models import RawItem
    repository = make_repository(tmp_path)
    item = normalize_item(RawItem(source='tldr_email', source_type='scrape', category='tech',
        title='An article with a gifted link', url='https://example.com/news', published_at=datetime.now(timezone.utc)))
    # Simulate a row written by an older collector.
    item.url = item.canonical_url = 'https://example.com/news?accessToken=private-gift'
    repository.insert_normalized_item(item)
    row = repository.fetch_recent_items()[0]
    assert row['url'] == row['canonical_url'] == 'https://example.com/news'

"""Read-only newsletter IMAP ingestion with post-persistence acknowledgement."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import hashlib
import imaplib
import re
import ssl
import time
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import httpx
from selectolax.parser import HTMLParser

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.pipeline.extract import extract_text_from_html
from news_collector.pipeline.images import download
from news_collector.utils import canonicalize_url, entity_candidates, parse_datetime

# Never follow subscription, verification, preference, or account actions.
NON_STORY = re.compile(r'\b(unsubscribe|subscribe|preferences|sponsor(?:ed)?|advertise|sign[ -]?in|log[ -]?in|verify|confirm|password|view (?:this )?(?:email|in browser)|manage subscriptions?|track your referrals|work with us|follow on|privacy|terms|share (?:this|on)|refer a friend)\b', re.I)
ACTION_URL = re.compile(r'(unsubscribe|preferences|/subscribe|/verify|/confirm|/login|/signin|/auth/|/password|/referral)', re.I)


def article_url(url):
    if ACTION_URL.search(url):
        raise ValueError('Subscription/account action is not an article')
    return url


def public_story_url(url):
    parts = urlparse(canonicalize_url(url))
    private_keys = {'email', 'recipient', 'subscriber', 'subscriber_id', 'token', 'signature', 'access_token', 'accesstoken'}
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in private_keys and '@' not in v]
    return urlunparse(parts._replace(query=urlencode(query)))


def template_links(page, domain):
    """Extract editorial blocks, never nested sponsor calls to action or footers."""
    if domain in {'tldr.tech', 'tldrnewsletter.com'} and page.css('.text-block'):
        links = []
        for block in page.css('.text-block'):
            a = block.css_first('a[href]')
            if a is None or not a.css_first('strong,b'):
                continue
            title = ' '.join(a.text(separator=' ').split())
            if not re.search(r'\((?:\d+ minute (?:read|video)|GitHub Repo|Website)\)\s*$', title, re.I):
                continue
            links.append((title, a.attributes['href'], ' '.join(block.text(separator=' ').split())))
        return links
    if domain == 'alphasignal.ai' and page.css('td.h1'):
        links = []
        for heading in page.css('td.h1, a.h1'):
            block = heading.parent.parent
            if heading.tag == 'a':
                block = block.parent
            summary = ' '.join(block.text(separator=' ').split())
            if re.search(r'\b(presented by|sponsored)\b', summary, re.I):
                continue
            a = heading if heading.tag == 'a' else next(
                (a for a in block.css('a[href]') if a.text().strip() == 'READ MORE'), None)
            # Summary/navigation headings contain whole editions, not a single story.
            title = ' '.join(heading.text(separator=' ').split())
            if a is not None and title not in {'Summary', 'Signals'}:
                links.append((title, a.attributes['href'], summary))
        return links
    return None


def story_links(message_bytes: bytes, allowed_domains: list[str]):
    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    sender = parseaddr(str(message.get('From', '')))[1].lower()
    domain = sender.rsplit('@', 1)[-1]
    if not any(domain == d or domain.endswith('.' + d) for d in allowed_domains):
        return None
    subject = str(message.get('Subject', ''))
    if re.search(r'\b(confirm your|verify your|welcome to|subscription confirmed|verification code|sign-in code)\b', subject, re.I):
        return None
    date = parse_datetime(str(message.get('Date', '')))
    if not date:
        raise ValueError('Newsletter has no valid publication date')
    part = message.get_body(preferencelist=('html', 'plain'))
    if part is None:
        raise ValueError('Newsletter has no readable body')
    body = part.get_content()
    links = []
    if part.get_content_type() == 'text/html':
        page = HTMLParser(body)
        for node in page.css('script,style,footer'):
            node.decompose()
        structured = template_links(page, domain)
        for a in ([] if structured is not None else page.css('a[href]')):
            title = ' '.join(a.text(separator=' ').split())
            url = a.attributes['href']
            # The surrounding short paragraph often contains the newsletter synopsis.
            parent = a.parent
            summary = None
            for _ in range(3):
                if parent is None:
                    break
                text = ' '.join(parent.text(separator=' ').split())
                if len(title) < len(text) < 2000:
                    summary = text
                    break
                parent = parent.parent
            links.append((title, url, summary))
        if structured is not None:
            links = structured
    else:
        # Plain-text issues with descriptive link labels on the same/previous line.
        lines = body.splitlines()
        for i, line in enumerate(lines):
            match = re.search(r'https?://[^\s<>]+', line)
            if match:
                title = line[:match.start()].strip(' []():-') or (lines[i-1].strip() if i else '')
                links.append((title, match.group().rstrip(').,'), None))
    candidates = {}
    for title, url, summary in links:
        if (len(title.split()) < 3 or len(title) > 350 or NON_STORY.search(title)
                or ACTION_URL.search(url) or urlparse(url).scheme not in {'http', 'https'}
                or urlparse(url).username or not urlparse(url).hostname
                or urlparse(url).hostname in {'jobs.ashbyhq.com', 'jobs.tldr.tech'}):
            continue
        title = re.sub(r'\s*\((?:\d+ minute read|GitHub Repo)\)\s*$', '', title)
        candidates[canonicalize_url(url)] = (title, url, summary)
    if not candidates:
        raise ValueError('No newsletter story links recognized; inspect the email format')
    # Hash only: recipient, subject, headers and full email never enter public artifacts.
    message_key = hashlib.sha256(message_bytes).hexdigest()
    return date, message_key, list(candidates.values())


class NewsletterMailCollector(BaseCollector):
    source_type = 'scrape'  # Compatible with the retained app's source-type contract.

    def run(self, *args, **kwargs):
        self._pending = []
        self._empty_success = False
        result = super().run(*args, **kwargs)
        if self._empty_success and not result.items and result.status == 'degraded':
            result.status, result.reason = 'ok', None
            state = self.get_state()
            state.update(last_status='ok', last_reason=None, consecutive_zero_runs=0)
            self.set_state(state)
            result.stats = state
        return result

    def collect(self):
        self._pending = []
        self._rate_limited_hosts = set()
        settings = self.context.settings
        if not all((settings.mail_host, settings.mail_username, settings.mail_password)):
            raise CollectorDegraded('Newsletter mailbox is not configured')
        warnings, items = [], []
        state = self.get_state()
        state.pop('collection_warning', None)
        self.set_state(state)
        try:
            with imaplib.IMAP4_SSL(settings.mail_host, settings.mail_port,
                    ssl_context=ssl.create_default_context(), timeout=20) as mailbox:
                try:
                    mailbox.login(settings.mail_username, settings.mail_password)
                except imaplib.IMAP4.error:
                    raise CollectorDegraded(
                        'Newsletter mailbox authentication rejected; check the mailbox/app password and IMAP account access'
                    ) from None
                status, _ = mailbox.select(settings.mail_folder, readonly=True)
                if status != 'OK':
                    raise CollectorDegraded('Newsletter mailbox folder is unavailable')
                _, validity = mailbox.response('UIDVALIDITY')
                if not validity or not validity[0]:
                    raise CollectorDegraded('Mailbox did not provide UIDVALIDITY')
                identity = f'{settings.mail_host}|{settings.mail_username}|{settings.mail_folder}|{validity[0]!r}'
                self._mailbox_key = hashlib.sha256(identity.encode()).hexdigest()
                done = set(state.get('mail_done', [])) if state.get('mailbox_key') == self._mailbox_key else set()
                since = (datetime.now(timezone.utc) - timedelta(days=int(self.context.config.get('lookback_days', 30)))).strftime('%d-%b-%Y')
                # Server-side filter reduces downloads; parsed From domain is checked again.
                uids = set()
                for domain in self.context.config['sender_domains']:
                    status, data = mailbox.uid('search', None, 'SINCE', since, 'FROM', f'"{domain}"')
                    if status != 'OK':
                        raise CollectorDegraded('Newsletter mailbox search failed')
                    uids.update(uid.decode() for uid in (data[0] or b'').split())
                pending = sorted(uids - done, key=int)
                link_count = 0
                for uid in pending[:int(self.context.config.get('max_messages_per_run', 20))]:
                    status, data = mailbox.uid('fetch', uid, '(BODY.PEEK[]<0.2000001>)')
                    payload = next((d[1] for d in data if isinstance(d, tuple)), None)
                    if status != 'OK' or not payload or len(payload) > 2_000_000:
                        warnings.append('A newsletter could not be downloaded within the size limit')
                        continue
                    try:
                        parsed = story_links(payload, self.context.config['sender_domains'])
                        if parsed is None:
                            self._pending.append(uid)
                            continue
                        date, message_key, links = parsed
                        if len(links) > 100:
                            raise ValueError('Too many links')
                        if link_count + len(links) > 100:
                            warnings.append('Article request budget reached; remaining emails will be retried')
                            break
                        link_count += len(links)
                        message_items, failed = self._article_items(date, message_key, links)
                        items.extend(message_items)
                        if failed:
                            warnings.append('Some linked articles are unavailable; the email will be retried')
                        else:
                            self._pending.append(uid)
                    except (ValueError, TypeError, LookupError):
                        warnings.append('A newsletter format was not recognized; it will be retried')
                if len(pending) > int(self.context.config.get('max_messages_per_run', 20)):
                    warnings.append('Additional newsletter messages remain for the next run')
                # Retain only IDs still inside the server-side lookback window.
                self._done = done & uids
        except CollectorDegraded:
            raise
        except Exception:
            # IMAP errors may contain account identifiers/server responses; never log them.
            raise CollectorDegraded('Newsletter mailbox connection or authentication failed') from None
        if warnings:
            if not items:
                raise CollectorDegraded('; '.join(sorted(set(warnings))))
            state = self.get_state()
            state['collection_warning'] = '; '.join(sorted(set(warnings)))
            self.set_state(state)
        self._empty_success = not warnings and not items
        return items

    def _article_items(self, date, message_key, links):
        items, failed = [], False
        with httpx.Client(timeout=20, follow_redirects=False,
                headers={'User-Agent': self.context.settings.user_agent}) as client:
            for title, link, summary in links:
                if urlparse(link).hostname in self._rate_limited_hosts:
                    failed = True
                    continue
                try:
                    # Validates public destinations at every redirect; skips email tracking pixels.
                    body, final_url = download(client, link, 3_000_000, validate_url=self._validate_article_url)
                    url = public_story_url(final_url)
                    if ACTION_URL.search(url):
                        raise ValueError('Action link')
                    text = extract_text_from_html(body.decode('utf-8', errors='replace'), url)
                    items.append(RawItem(source=self.name, source_type=self.source_type,
                        category=self.category, external_id=f'{message_key}:{url}', title=title,
                        url=url, published_at=date, summary=summary or title, text=text or summary or title,
                        entities=entity_candidates(title, summary),
                        raw={'_ingestion': 'email', '_message_key': message_key,
                             '_editorial_type': 'reporting', '_date_basis': 'newsletter_sent_at'}))
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        self._rate_limited_hosts.update((urlparse(link).hostname, exc.request.url.host))
                    failed = True
                except Exception:
                    failed = True
                time.sleep(float(self.context.config.get('link_delay_seconds', .5)))
        return items, failed

    def _validate_article_url(self, url):
        article_url(url)
        if urlparse(url).hostname in self._rate_limited_hosts:
            raise ValueError('Host was rate limited earlier in this run')

    def acknowledge(self):
        if not hasattr(self, '_mailbox_key'):
            return
        state = self.get_state()
        state['mailbox_key'] = self._mailbox_key
        state['mail_done'] = sorted(self._done | set(self._pending), key=int)
        self.set_state(state)

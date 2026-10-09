"""Adapt URL/date/classification rules from market-pulse/src/normalize.js."""

from datetime import datetime, UTC, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import re
import unicodedata
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

from bs4 import BeautifulSoup


def fold(value: str) -> str:
    value = unicodedata.normalize('NFD', value.replace('đ', 'd').replace('Đ', 'D'))
    return ''.join(c for c in value if not unicodedata.combining(c)).lower()


def plain(value) -> str:
    soup = BeautifulSoup(str(value or ''), 'html.parser')
    for node in soup.select('script,style,noscript'):
        node.decompose()
    return re.sub(r'\s+', ' ', soup.get_text(' ', strip=True)).strip()


def canonical_url(value, base) -> str | None:
    try:
        url = urlsplit(urljoin(base, str(value or '')))
        if not value or url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
            return None
        query = sorted((k, v) for k, v in parse_qsl(url.query, keep_blank_values=True)
            if not re.match(r'^(utm_|at_campaign$|at_medium$|fbclid$|gclid$)', k, re.I))
        return urlunsplit((url.scheme, url.netloc.lower(), url.path or '/', urlencode(query), ''))
    except ValueError:
        return None


def date_iso(value) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    vn = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?', text)
    try:
        if vn:
            day, month, year, hour, minute = vn.groups()
            dt = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0),
                          tzinfo=timezone(timedelta(hours=7)))
        else:
            try:
                dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
            except ValueError:
                dt = parsedate_to_datetime(text)
        # Unknown timezone/date is not inferred from ingestion time.
        return dt.astimezone(UTC).isoformat() if dt.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def contains(text, keyword) -> bool:
    return bool(re.search(r'(?<!\w)' + re.escape(unicodedata.normalize('NFC', keyword)) + r'(?!\w)', text, re.I))


def normalize_article(raw, source, entities) -> dict | None:
    url = canonical_url(raw.get('url'), source['url'])
    title = plain(raw.get('title'))[:1000]
    if not url or len(title) < 8:
        return None
    excerpt = plain(raw.get('excerpt'))[:1600]
    text = unicodedata.normalize('NFC', f'{title} {excerpt}')
    companies = [symbol for symbol, aliases in entities['companies'].items()
                 if any(contains(text, alias) for alias in aliases)]
    sectors = [sector for sector, words in entities['sectors'].items()
               if any(contains(text, word) for word in words)]
    if source.get('sector') and source['sector'] not in sectors:
        sectors.append(source['sector'])
    categories = []
    category = raw.get('category') or source.get('category')
    if category == 'vimo' or any(contains(text, w) for w in entities['macro']):
        categories.append('vimo')
    if sectors or category == 'nganh':
        categories.append('nganh')
    if companies:
        categories.append('doanhnghiep')
    published_at = date_iso(raw.get('published_at'))
    return dict(url=url, title=title, excerpt=excerpt, published_at=published_at,
        source_id=source['id'], language=source.get('language'), region=source['region'],
        companies=companies, sectors=sectors, categories=categories or [category or 'khac'],
        search_text=fold(f'{title} {excerpt} {" ".join(companies)}'),
        content_hash=hashlib.sha256(json.dumps([title, excerpt, published_at], ensure_ascii=False).encode()).hexdigest())

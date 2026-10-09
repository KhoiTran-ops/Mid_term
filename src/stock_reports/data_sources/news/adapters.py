"""RSS/Atom and listing adapters ported from market-pulse/src/adapters.js."""

import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import httpx

from stock_reports.data_sources.news.normalize import canonical_url, date_iso


MAX_RESPONSE_BYTES = 6_000_000


def local_name(tag):
    return tag.rsplit('}', 1)[-1].split(':')[-1]


def parse_feed(body: bytes) -> list[dict]:
    if re.search(br'<!DOCTYPE|<!ENTITY', body.replace(b'\x00', b''), re.I):
        raise ValueError('XML declarations are not allowed')
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise ValueError('Invalid feed XML') from error
    if local_name(root.tag) not in ('rss', 'feed', 'RDF'):
        raise ValueError('Response is not an RSS/Atom feed')
    rows = []
    for entry in root.iter():
        if local_name(entry.tag) not in ('item', 'entry'):
            continue
        fields = {}
        links = []
        for child in entry:
            name = local_name(child.tag)
            # Preserve markup only until plain() strips it after parsing.
            value = (child.text or '') + ''.join(ET.tostring(c, encoding='unicode') for c in child)
            fields.setdefault(name, value)
            if name == 'link':
                links.append(child)
        alternate = next((l for l in links if l.get('rel') == 'alternate'), None)
        if alternate is None:
            alternate = next((l for l in links if not l.get('rel')), None)
        url = alternate.get('href') or alternate.text if alternate is not None else fields.get('guid')
        rows.append(dict(title=fields.get('title'), url=url,
            excerpt=fields.get('description') or fields.get('summary') or '',
            published_at=fields.get('pubDate') or fields.get('date') or fields.get('published') or fields.get('updated')))
    return rows


def parse_listing(body: str, source: dict) -> list[dict]:
    soup = BeautifulSoup(body, 'html.parser')
    for node in soup.select('script,style,nav,footer'):
        node.decompose()
    include = re.compile(source['include'])
    exclude = re.compile(source['exclude']) if source.get('exclude') else None
    seen, rows = set(), []
    for link in soup.select(source.get('selector') or 'a[href]'):
        if source['id'] == 'vneconomy' and not link.find_parent('article'):
            continue
        url = canonical_url(link.get('href'), source['url'])
        if not url or urlsplit(url).netloc != urlsplit(source['url']).netloc or url in seen:
            continue
        if not include.search(urlsplit(url).path) or (exclude and exclude.search(urlsplit(url).path)):
            continue
        scope = listing_scope(link, source, include)
        heading = scope.select_one('h2,h3,.title')
        title = link.get('title') or (heading.get('title') or heading.get_text(' ', strip=True) if heading else link.get_text(' ', strip=True))
        if not 20 <= len(title) <= 700:
            continue
        time = scope.select_one('time')
        explicit = scope.select_one('.archive-issue-date,.date')
        date_text = (explicit or scope).get_text(' ', strip=True)
        match = re.search(r'\b\d{2}/\d{2}/\d{4}\b', date_text)
        published_at = date_iso(time.get('datetime') if time else match.group() if match else None)
        category_text = link.select_one('.cate-name')
        category = None
        if category_text:
            text = category_text.get_text().lower()
            category = 'vimo' if 'vĩ mô' in text else 'doanhnghiep' if 'doanh nghiệp' in text else 'nganh' if 'ngành' in text else None
        rows.append(dict(title=title, url=url, excerpt='', published_at=published_at, category=category))
        seen.add(url)
    if not rows:
        raise ValueError('Listing structure changed or no links available')
    return rows[:100]


def listing_scope(link, source, include):
    # NSO currently publishes an empty link followed by its own report section.
    if source['id'] == 'nso' and not link.get_text(strip=True):
        sibling = link.parent.find_next_sibling()
        if sibling and sibling.name == 'section' and 'item' in sibling.get('class', []):
            return sibling
    candidate = link.find_parent(lambda node: node.name in ('article', 'li') or
        bool(set(node.get('class', [])) & {'item', 'post', 'news-item', 'report-item'})) or link
    siblings = set()
    for anchor in candidate.select('a[href]'):
        url = canonical_url(anchor.get('href'), source['url'])
        if url and include.search(urlsplit(url).path):
            siblings.add(url)
    return candidate if len(siblings) == 1 else link


def collect_source(source: dict, state: dict, archive=None) -> dict:
    headers = {'User-Agent': 'MidTermFinanceResearch/1.0',
               'Accept': 'application/rss+xml,application/atom+xml,text/html;q=0.9,*/*;q=0.5'}
    if state.get('etag'):
        headers['If-None-Match'] = state['etag']
    if state.get('last_modified'):
        headers['If-Modified-Since'] = state['last_modified']
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        with client.stream('GET', source['url'], headers=headers) as response:
            if response.status_code == 304:
                return dict(not_modified=True)
            response.raise_for_status()
            if int(response.headers.get('content-length') or 0) > MAX_RESPONSE_BYTES:
                raise ValueError('Response too large')
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError('Response too large')
                chunks.append(chunk)
            body = b''.join(chunks)
            encoding = response.encoding or 'utf-8'
            etag, last_modified = response.headers.get('etag'), response.headers.get('last-modified')
    if archive:
        archive.save('news', source['url'], body, '.xml' if source['kind'] == 'rss' else '.html')
    rows = parse_feed(body) if source['kind'] == 'rss' else parse_listing(body.decode(encoding, errors='replace'), source)
    return dict(articles=rows, etag=etag, last_modified=last_modified)

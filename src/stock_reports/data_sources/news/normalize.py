"""Adapt URL/date/classification rules from market-pulse/src/normalize.js."""

from datetime import datetime, UTC, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import re
import unicodedata
from functools import lru_cache
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


@lru_cache(maxsize=32768)
def keyword_pattern(keyword):
    return re.compile(r'(?<!\w)' + re.escape(unicodedata.normalize('NFC', keyword)) + r'(?!\w)', re.I)


def contains(text, keyword) -> bool:
    return bool(keyword_pattern(keyword).search(text))


def company_matches(text,symbol,aliases):
    for alias in aliases:
        if alias.upper()==symbol and re.fullmatch(r'[A-Z0-9]{2,12}',alias.upper()):
            # Do not tag BID from English 'bid', CEO from a job title, or API from software.
            if symbol in {'BID','CEO','API','CAP','GAS','DIG','ONE','ART','TIG','NET','ITQ',
                          'USD','VND','EUR','JPY','AUD','CAD','GBP','NZD','CHF','THB','KRW','CNY','SGD','HKD'}:
                if re.search(r'(?:cổ phiếu|mã|HOSE|HNX|UPCOM)\s*[:(\-]?\s*'+re.escape(symbol)+r'(?!\w)',text,re.I) or re.search(r'\('+re.escape(symbol)+r'\)',text):return True
            elif re.search(r'(?<!\w)'+re.escape(symbol)+r'(?!\w)',text):return True
        elif contains(text,alias):return True
    return False


class CompanyMatcher:
    """Use the headline's tokens to shortlist aliases, instead of scanning 1,500 issuers."""
    def __init__(self, companies):
        self.codes = {}; self.names = {}
        for symbol, aliases in companies.items():
            for alias in aliases:
                if alias.upper() == symbol and re.fullmatch(r'[A-Z0-9]{2,12}', alias.upper()):
                    self.codes[symbol] = [alias]
                else:
                    tokens = re.findall(r'\w+', unicodedata.normalize('NFC', alias).casefold())
                    if tokens:
                        self.names.setdefault(tokens[0], []).append((symbol, alias))

    def match(self, text):
        matched = set()
        for code in set(re.findall(r'(?<!\w)[A-Z0-9]{2,12}(?!\w)', text)):
            if code in self.codes and company_matches(text, code, self.codes[code]):
                matched.add(code)
        for token in set(re.findall(r'\w+', text.casefold())):
            for symbol, alias in self.names.get(token, ()):
                if symbol not in matched and contains(text, alias):
                    matched.add(symbol)
        return sorted(matched)


# A sector feed is not automatically financial news.  These vocabularies are
# deliberately cross-language because the configured feeds are Vietnamese and
# international.  Geopolitics is retained only when it has an economic/market
# transmission channel (trade, energy, sanctions, supply chains, ...).
FINANCE_TERMS = (
    'chứng khoán', 'cổ phiếu', 'trái phiếu', 'thị trường', 'đầu tư', 'nhà đầu tư',
    'tài chính', 'kinh tế', 'ngân hàng', 'tín dụng', 'lãi suất', 'tỷ giá', 'lợi suất',
    'doanh thu', 'lợi nhuận', 'kết quả kinh doanh', 'báo cáo tài chính', 'bctc',
    'cổ tức', 'vốn hóa', 'định giá', 'mua bán sáp nhập', 'huy động vốn',
    'giá vàng', 'giá dầu', 'hàng hóa', 'stock', 'share', 'equity', 'bond',
    'market', 'economy', 'economic', 'investor', 'investment', 'finance', 'financial', 'bank', 'credit',
    'yield', 'currency', 'exchange rate', 'earnings', 'revenue', 'profit',
    'dividend', 'valuation', 'ipo', 'merger', 'acquisition', 'fundraising',
    'commodity', 'oil price', 'gold price',
)
CORPORATE_TERMS = (
    'doanh nghiệp', 'công ty', 'tập đoàn', 'kinh doanh', 'sản xuất', 'sản lượng', 'đơn hàng',
    'xuất khẩu', 'nhập khẩu', 'thị phần', 'chi phí', 'biên lợi nhuận', 'company',
    'corporate', 'business', 'sales', 'production', 'output', 'orders', 'export', 'import',
    'market share', 'cost', 'margin',
)
GEOPOLITICAL_TERMS = (
    'địa chính trị', 'chiến tranh', 'xung đột', 'trừng phạt', 'cấm vận',
    'thuế quan', 'căng thẳng thương mại', 'biển đỏ', 'eo biển', 'geopolitic',
    'war', 'conflict', 'sanction', 'embargo', 'tariff', 'trade tension',
    'red sea', 'strait',
)
ECONOMIC_CHANNEL_TERMS = (
    'kinh tế', 'thương mại', 'chuỗi cung ứng', 'năng lượng', 'dầu', 'khí',
    'vận tải', 'logistics', 'lạm phát', 'tăng trưởng', 'economic', 'economy',
    'trade', 'supply chain', 'energy', 'oil', 'gas', 'shipping', 'inflation',
    'growth',
)


def _matches_any(text: str, terms) -> bool:
    return any(contains(text, term) for term in terms)


def normalize_article(raw, source, entities, *, company_matcher=None) -> dict | None:
    url = canonical_url(raw.get('url'), source['url'])
    title = plain(raw.get('title'))[:1000]
    if not url or len(title) < 8:
        return None
    excerpt = plain(raw.get('excerpt'))[:1600]
    text = unicodedata.normalize('NFC', f'{title} {excerpt}')
    companies = (company_matcher or CompanyMatcher(entities['companies'])).match(text)
    sectors = [sector for sector, words in entities['sectors'].items()
               if any(contains(text, word) for word in words)]
    if source.get('sector') and source['sector'] not in sectors:
        sectors.append(source['sector'])
    macro_hit = any(contains(text, word) for word in entities['macro'])
    finance_hit = _matches_any(text, FINANCE_TERMS)
    corporate_hit = _matches_any(text, CORPORATE_TERMS)
    geopolitical_hit = (_matches_any(text, GEOPOLITICAL_TERMS)
                         and _matches_any(text, ECONOMIC_CHANNEL_TERMS))
    category = raw.get('category') or source.get('category')
    trusted_research = source.get('id') == 'vietcap'
    trusted_macro = category == 'vimo'
    # Company and sector names can also appear in lifestyle/product stories;
    # require a business, market or macro signal unless the publisher is an
    # official macro/research source.
    if not (trusted_research or trusted_macro or macro_hit or finance_hit
            or geopolitical_hit or (companies and (corporate_hit or source.get('finance_only')))):
        return None
    categories = []
    if trusted_macro or macro_hit:
        categories.append('vimo')
    if finance_hit:
        categories.append('taichinh')
    if geopolitical_hit:
        categories.append('diachinhtri')
    if sectors and (finance_hit or corporate_hit or macro_hit or trusted_research):
        categories.append('nganh')
    if companies:
        categories.append('doanhnghiep')
    topics={'chungkhoan':('chứng khoán','cổ phiếu','VN-Index','HOSE','HNX','stock','equity','securities'),
            'nganhang':('ngân hàng','tín dụng','bank','banking','credit'),
            'kinhteso':('kinh tế số','chuyển đổi số','digital economy','fintech','trí tuệ nhân tạo','artificial intelligence'),
            'thitruong':('thị trường','market','giá vàng','giá dầu')}
    for topic,words in topics.items():
        if _matches_any(text,words) or category==topic:categories.append(topic)
    if corporate_hit:categories.append('kinhte')
    if source.get('region') != 'VN':
        categories.append('quocte')
    published_at = date_iso(raw.get('published_at'))
    return dict(url=url, title=title, excerpt=excerpt, published_at=published_at,
        source_id=source['id'], language=source.get('language'), region=source['region'],
        companies=companies, sectors=sectors, categories=list(dict.fromkeys(categories)) or [category or 'khac'],
        search_text=fold(f'{title} {excerpt} {" ".join(companies)}'),
        content_hash=hashlib.sha256(json.dumps([title, excerpt, published_at], ensure_ascii=False).encode()).hexdigest())

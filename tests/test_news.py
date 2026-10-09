from datetime import datetime, UTC, timedelta
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from stock_reports.data_sources.news.adapters import parse_feed, parse_listing
from stock_reports.data_sources.news.normalize import normalize_article
from stock_reports.storage.news import NewsStore
from stock_reports.pipeline.news import NewsCollector


SOURCE = dict(id='test', name='Nguồn thử', kind='rss', url='https://example.org/rss',
              region='VN', language='vi', intervalMinutes=10, enabled=True)
ENTITIES = dict(companies={'HPG': ['Hòa Phát', 'HPG']}, sectors={'Thép': ['thép', 'steel']}, macro=['GDP'])


def article(url='https://example.org/a?utm_source=rss', title='Hòa Phát tăng sản lượng thép'):
    return normalize_article(dict(title=title, url=url, excerpt='<p>Đoạn trích</p>'), SOURCE, ENTITIES)


def test_rss_atom_normalization_missing_dates_and_safe_urls():
    body = b'<rss><channel><item><title>HPG steel investment</title><link>https://example.org/a</link><pubDate>Fri, 09 Oct 2026 08:00:00 +0700</pubDate></item></channel></rss>'
    rows = parse_feed(body)
    item = normalize_article(rows[0], SOURCE, ENTITIES)
    assert item['published_at'] == '2026-10-09T01:00:00+00:00'
    assert item['companies'] == ['HPG']
    assert article()['published_at'] is None
    assert article()['url'] == 'https://example.org/a'
    assert article(url='javascript:alert(1)') is None
    assert article(url='https://user:password@example.org/a') is None
    assert parse_feed(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>HPG investment</title><link href="https://example.org/a" rel="alternate"/></entry></feed>')[0]['url'] == 'https://example.org/a'
    with pytest.raises(ValueError):
        parse_feed(b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///secret">]><rss/>')


def test_listing_dates_are_per_article_and_links_stay_on_source_domain():
    source = {**SOURCE, 'kind': 'listing', 'include': '/reports/'}
    body = '<div><a href="/reports/a">Báo cáo thị trường tháng thứ nhất <span class="date">03/10/2026</span></a><a href="/reports/b">Báo cáo thị trường tháng thứ hai <span class="date">03/09/2026</span></a><a href="https://evil.org/reports/a">External article not trusted</a></div>'
    rows = parse_listing(body, source)
    assert len(rows) == 2
    assert rows[0]['published_at'] != rows[1]['published_at']


def test_nso_adjacent_report_layout_uses_release_date_not_next_release():
    source = {**SOURCE, 'id': 'nso', 'kind': 'listing', 'include': '/reports/'}
    body = '<div class="archive-container"><p><a href="/reports/a"></a></p><section class="item"><h3>Báo cáo tình hình kinh tế tháng chín</h3><span class="archive-issue-date">Ngày đăng: 03/10/2026</span><span class="archive-next-release">03/11/2026</span></section><p><a href="/reports/b"></a></p><section class="item"><h3>Báo cáo tình hình kinh tế tháng tám</h3><span class="archive-issue-date">Ngày đăng: 03/09/2026</span></section></div>'
    rows = parse_listing(body, source)
    assert len(rows) == 2
    assert rows[0]['published_at'].startswith('2026-10-02T17:00:00')
    assert rows[1]['published_at'].startswith('2026-09-02T17:00:00')


def test_vneconomy_ignores_menu_links_with_article_like_paths():
    source = {**SOURCE, 'id': 'vneconomy', 'kind': 'listing', 'include': r'\.htm$'}
    body = '<div class="box-category-menu"><li><a href="/doanh-nghiep-niem-yet.htm">Doanh nghiệp niêm yết</a></li></div><article><h3><a href="/doanh-nghiep-tang-truong.htm">Doanh nghiệp tăng trưởng trong quý mới</a></h3></article>'
    rows = parse_listing(body, source)
    assert len(rows) == 1
    assert rows[0]['url'].endswith('/doanh-nghiep-tang-truong.htm')


def test_news_deduplicates_and_filters_region_company_and_accentless_query(tmp_path):
    store = NewsStore(tmp_path / 'news.db')
    store.sync_sources([SOURCE, {**SOURCE, 'id': 'foreign', 'region': 'Global'}])
    assert store.save_articles([article()])['added'] == 1
    assert store.save_articles([article()])['added'] == 0
    assert store.save_articles([article(title='Hòa Phát điều chỉnh sản lượng thép')])['updated'] == 1
    foreign = normalize_article(dict(title='Global economy news', url='https://example.org/b'),
        {**SOURCE, 'id': 'foreign', 'region': 'Global'}, ENTITIES)
    store.save_articles([foreign])
    assert store.list_news(region='VN')['total'] == 1
    assert store.list_news(region='international')['total'] == 1
    assert store.list_news(symbol='HPG', query='hoa phat')['total'] == 1
    assert store.revision_count() == 1


def test_collector_backoff_304_and_no_overlapping_runs(tmp_path):
    store = NewsStore(tmp_path / 'news.db')
    store.sync_sources([SOURCE])
    now = datetime(2026, 10, 9, tzinfo=UTC)
    calls = []

    def adapter(source, state):
        calls.append(state)
        return dict(articles=[dict(title='HPG steel investment', url='https://example.org/a')], etag='v1')

    collector = NewsCollector(store, ENTITIES, adapter=adapter, clock=lambda: now)
    assert collector.run()['added'] == 1
    assert collector.run()['sources'] == 0
    collector.adapter = lambda *args: dict(not_modified=True)
    now += timedelta(minutes=11)
    assert collector.run()['success'] == 1
    assert store.sources()[0]['etag'] == 'v1'
    assert store.list_news()['total'] == 1
    collector.adapter = lambda *args: (_ for _ in ()).throw(ConnectionError('secret URL'))
    now += timedelta(minutes=11)
    assert collector.run()['failed'] == 1
    assert store.sources()[0]['error'] == 'ConnectionError'
    assert collector.run()['sources'] == 0
    assert collector.lock.acquire(blocking=False)
    assert collector.run()['busy'] is True
    collector.lock.release()


def test_overlapping_source_feeds_can_save_same_article_concurrently(tmp_path):
    store = NewsStore(tmp_path / 'news.db')
    store.sync_sources([SOURCE])
    barrier = threading.Barrier(8)

    def save(_):
        barrier.wait(timeout=5)
        return store.save_articles([article()])

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(save, range(8)))
    assert sum(r['added'] for r in results) == 1
    assert store.list_news()['total'] == 1

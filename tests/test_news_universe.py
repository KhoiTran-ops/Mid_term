from datetime import date
from pathlib import Path
import json
import sqlite3
from types import SimpleNamespace

from stock_reports.core.files import atomic_json
from stock_reports.data_sources.news.entities import universe_entities
from stock_reports.data_sources.news.normalize import company_matches, normalize_article, CompanyMatcher
from stock_reports.data_sources.news.ranking import rank_company_news
from stock_reports.storage.news import NewsStore
from tests.test_news import SOURCE, ENTITIES


def test_all_local_issuers_extend_aliases_without_mutating_base(tmp_path):
    path = tmp_path / 'market.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE instruments(symbol TEXT, company_name TEXT)')
        db.execute('INSERT INTO instruments VALUES (?,?)', ('XYZ', 'CTCP Công nghiệp Mới'))
    result = universe_entities(SimpleNamespace(market_database=path), ENTITIES)
    assert 'XYZ' not in ENTITIES['companies']
    assert result['companies']['XYZ'] == ['XYZ', 'CTCP Công nghiệp Mới', 'Công nghiệp Mới']


def test_ambiguous_codes_need_stock_context():
    for code, text in [('BID', 'Investors bid for government bonds'), ('CEO', 'CEO announces earnings'), ('API', 'API for financial services'), ('USD','FPT mất 4,5 tỷ USD vốn hóa'), ('VND','Lợi nhuận 100 tỷ VND')]:
        assert not company_matches(text, code, [code])
        assert company_matches(f'Cổ phiếu {code} tăng giá', code, [code])
    assert company_matches('HPG công bố lợi nhuận', 'HPG', ['HPG'])
    assert not company_matches('hpg text in a software log', 'HPG', ['HPG'])


def test_indexed_matcher_has_same_issuer_rules_and_multilingual_aliases():
    companies={'HPG':['HPG','Hòa Phát'],'CEO':['CEO','Tập đoàn C.E.O'],'USD':['USD']}
    matcher=CompanyMatcher(companies)
    for text in ['Hòa Phát tăng doanh thu', 'FPT mất 4,5 tỷ USD vốn hóa', 'Cổ phiếu CEO tăng giá', 'Tập đoàn C.E.O tăng lợi nhuận']:
        expected=sorted(s for s,a in companies.items() if company_matches(text,s,a))
        assert matcher.match(text)==expected


def test_daily_ranking_rejects_future_and_does_not_promote_old_earnings():
    rows = [dict(title='HPG lợi nhuận', published_at='2026-10-09T01:00:00+00:00'),
            dict(title='HPG thông báo mới', published_at='2026-10-10T02:00:00+00:00'),
            dict(title='HPG tin mới hôm nay', published_at='2026-10-11T01:00:00+00:00'),
            dict(title='HPG future', published_at='2026-10-12T01:00:00+00:00'),
            dict(title='HPG unknown', published_at=None)]
    ranked = rank_company_news(rows, 'HPG', date(2026, 10, 11))
    assert [r['title'] for r in ranked] == [rows[2]['title'], rows[1]['title'], rows[0]['title'], rows[4]['title']]


def test_company_api_store_topics_dates_and_no_unrelated_substitution(tmp_path):
    store = NewsStore(tmp_path / 'news.db'); store.sync_sources([SOURCE])
    item = normalize_article(dict(title='HPG công bố lợi nhuận cổ phiếu', url='https://example.org/a', published_at='2026-10-10T20:00:00Z'), SOURCE, ENTITIES)
    store.save_articles([item])
    assert store.list_news(category='chungkhoan')['total'] == 1
    assert store.list_news(category='nganhang')['total'] == 0
    assert store.company_news('HPG', as_of=date(2026, 10, 11))['today_count'] == 1
    assert store.company_news('VCB', as_of=date(2026, 10, 11))['items'] == []


def test_atomic_json_retries_transient_windows_lock(tmp_path, monkeypatch):
    original = Path.replace; calls = []
    def replace(path, target):
        calls.append(path)
        if len(calls) < 3: raise PermissionError('locked')
        return original(path, target)
    monkeypatch.setattr(Path, 'replace', replace)
    monkeypatch.setattr('stock_reports.core.files.time.sleep', lambda seconds: None)
    output = tmp_path / 'progress.json'; atomic_json(output, {'status': 'running'})
    assert json.loads(output.read_text())['status'] == 'running'
    assert len(calls) == 3
    assert not list(tmp_path.glob('*.tmp'))

import sqlite3

from stock_reports.data_sources.cafef.sync import sync_financial_history, Instrument, STATEMENT_TYPES
from stock_reports.storage.market import MarketStore


def make_period(year, quarter):
    return dict(symbol='HPG', fiscal_year=year, fiscal_quarter=quarter,
                audit_status='', is_audited=False, report_code='HK')


def test_incremental_checks_newest_summary_without_redownloading_cached_eight_quarters(tmp_path):
    store = MarketStore(tmp_path / 'data.db')
    store.initialize()
    store.upsert_instruments([Instrument('HPG', 'HOSE', '')], source='dnse')
    periods = [make_period(2024 + i // 4, i % 4 + 1) for i in range(8)]
    store.upsert_financial_periods(periods, source='cafef')
    for statement in STATEMENT_TYPES:
        store.replace_financial_facts('HPG', statement, [dict(row_order=0, item_name='X',
            values={(p['fiscal_year'], p['fiscal_quarter']): ('1', 1) for p in periods})], source='cafef')

    class Client:
        def get_financial_summary(self, symbol, *, page):
            assert page == 1
            return dict(isSuccess=True, value=dict(count=8, data=[dict(data=[
                dict(symbol=symbol, year=2025, quater=q, content='', type='HK')
                for q in (4, 3, 2, 1)])]))

        def get_financial_html(self, *args):
            raise AssertionError('An unchanged complete block should be reused')

    result = sync_financial_history(Client(), store, max_quarters=8, incremental=True)
    assert result.requests == 1
    assert result.saved == result.rejected == 0
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT COUNT(*) FROM financial_periods').fetchone()[0] == 8


def test_quarter_window_discards_old_periods_but_retains_missing_as_missing(tmp_path):
    store = MarketStore(tmp_path / 'data.db')
    store.initialize()
    store.upsert_financial_periods([make_period(2024 + i // 4, i % 4 + 1)
                                    for i in range(9)], source='cafef')
    store.replace_financial_facts('HPG', 'IncSta', [dict(row_order=0, item_name='X',
        values={(2024, 1): ('5', 5), (2026, 1): ('', None)})], source='cafef')
    store.trim_financial_history('HPG', 8)
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT COUNT(*) FROM financial_periods').fetchone()[0] == 8
        assert db.execute('SELECT fiscal_year,fiscal_quarter,value_numeric FROM financial_facts').fetchall() == [(2026, 1, None)]

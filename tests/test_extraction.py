import sqlite3

from data.db.market_store import MarketStore
from scripts.import_legacy import import_database


def test_import_keeps_latest_eight_periods_per_symbol_and_no_chat_data(tmp_path):
    source = MarketStore(tmp_path / 'old.db')
    source.initialize()
    periods = []
    values = {}
    for index in range(10):
        year, quarter = 2024 + index // 4, index % 4 + 1
        periods.append(dict(symbol='HPG', fiscal_year=year, fiscal_quarter=quarter,
                            audit_status='', is_audited=False, report_code='HK'))
        values[year, quarter] = (str(index), index)
    source.upsert_financial_periods(periods, source='cafef')
    source.replace_financial_facts('HPG', 'IncSta', [
        dict(row_order=0, item_name='Doanh thu', values=values)
    ], source='cafef')
    source.upsert_ohlcv_bars([dict(symbol='HPG', timeframe='1D', timestamp=100,
        open=10, high=11, low=9, close=10, volume=100, is_closed=True)], source='dnse')
    with sqlite3.connect(source.path) as db:
        db.execute('CREATE TABLE notification_subscriptions (chat_id INTEGER)')
        db.execute('INSERT INTO notification_subscriptions VALUES (12345)')

    target = tmp_path / 'new.db'
    import_database(source.path, target, quarters=8)
    import_database(source.path, target, quarters=8)

    with sqlite3.connect(target) as db:
        assert db.execute('SELECT COUNT(*) FROM ohlcv_bars').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM financial_periods').fetchone()[0] == 8
        assert db.execute('SELECT COUNT(*),MIN(value_numeric) FROM financial_facts').fetchone() == (8, 2)
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='notification_subscriptions'").fetchone()

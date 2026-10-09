from datetime import datetime

from data.db.market_store import MarketStore
from data.dnse_market import DNSEInstrument, VIETNAM
from data.refresh import refresh_market


def test_refresh_overlaps_latest_daily_bar_and_continues_after_symbol_error(tmp_path):
    store = MarketStore(tmp_path / 'data.db')
    store.initialize()
    previous = int(datetime(2026, 10, 8, 9, tzinfo=VIETNAM).timestamp())
    store.upsert_ohlcv_bars([dict(symbol='HPG', timeframe='1D', timestamp=previous,
        open=10, high=12, low=9, close=10, volume=100, is_closed=True)], source='dnse')

    class Gateway:
        def list_stock_instruments(self):
            return [DNSEInstrument('AAA','HOSE','',1), DNSEInstrument('HPG','HOSE','',1)]

        def get_ohlc(self, symbol, resolution, start, end, *, asset_type='STOCK'):
            if symbol == 'AAA':
                raise ConnectionError('Source unavailable')
            if symbol == 'HPG':
                assert start == previous
                return dict(t=[previous], o=[10], h=[12], l=[9], c=[11], v=[100])
            assert asset_type == 'INDEX'
            return dict(t=[],o=[],h=[],l=[],c=[],v=[])

    result = refresh_market(Gateway(),store,timeframes=('1D',),
                           now=datetime(2026,10,9,10,tzinfo=VIETNAM))
    assert result['failures'] == [dict(symbol='AAA',timeframe='1D',error_type='ConnectionError')]
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*),MAX(close) FROM ohlcv_bars WHERE symbol='HPG'").fetchone() == (1,11)

from datetime import datetime

from stock_reports.storage.market import MarketStore
from stock_reports.data_sources.dnse.market import DNSEInstrument, VIETNAM
from stock_reports.pipeline.market_refresh import refresh_market


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


def test_weekend_refresh_uses_previous_weekday_for_minutes_and_foreign(tmp_path):
    store=MarketStore(tmp_path/'market.db'); store.initialize()
    start=int(datetime(2026,10,9,tzinfo=VIETNAM).timestamp())
    end=int(datetime(2026,10,10,tzinfo=VIETNAM).timestamp())-1
    class Gateway:
        def list_stock_instruments(self):
            return [DNSEInstrument('VCB','HOSE','',1)]
        def get_ohlc(self,symbol,resolution,since,until,**kwargs):
            assert (since,until)==(start,end)
            return dict(t=[],o=[],h=[],l=[],c=[],v=[])
        def get_foreign_trading(self,symbol,since,until):
            assert (since,until)==(start,end)
            return dict(foreigners=[])
    result=refresh_market(Gateway(),store,timeframes=('1m',),include_foreign=True,
        now=datetime(2026,10,10,11,tzinfo=VIETNAM))
    assert result['intraday_session']=='2026-10-09'
    assert not result['failures']


def test_foreign_gateway_follows_all_pages_and_rejects_repeated_tokens():
    import pytest
    from stock_reports.data_sources.dnse.market import DNSEGateway
    gateway=object.__new__(DNSEGateway)
    calls=[]
    def get(path,params):
        calls.append(params)
        return {'foreigners':[{'page':len(calls)}],
            'nextPageToken':'next' if len(calls)==1 else None}
    gateway._get=get
    assert len(gateway.get_foreign_trading('VCB',1,2)['foreigners'])==2
    assert calls[1]['nextPageToken']=='next'
    assert calls[0]['order']=='DESC'
    gateway._get=lambda *args:{'foreigners':[], 'nextPageToken':'same'}
    with pytest.raises(ValueError,match='did not advance'):
        gateway.get_foreign_trading('VCB',1,2)

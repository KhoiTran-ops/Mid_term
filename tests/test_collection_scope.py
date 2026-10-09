import pytest

from stock_reports.data_sources.dnse.market import DNSEInstrument
from stock_reports.pipeline.collection import select_symbols
from stock_reports.pipeline.market_refresh import refresh_market
from stock_reports.storage.market import MarketStore


def test_exchange_scope_intersects_symbols_and_rejects_mistakes():
    catalog = [DNSEInstrument('HPG', 'HOSE', '', 1), DNSEInstrument('SHS', 'HNX', '', 1)]
    assert select_symbols(catalog, exchanges=['HOSE'], symbols=None) == ['HPG']
    assert select_symbols(catalog, exchanges=None, symbols=['shs']) == ['SHS']
    with pytest.raises(ValueError):
        select_symbols(catalog, exchanges=['HOSE'], symbols=['SHS'])


def test_market_exchange_scope_keeps_full_catalog(tmp_path):
    store = MarketStore(tmp_path / 'market.db')
    store.initialize()
    catalog = [DNSEInstrument('HPG', 'HOSE', '', 1), DNSEInstrument('SHS', 'HNX', '', 1)]
    called = []

    class Gateway:
        def list_stock_instruments(self):
            return catalog

        def get_ohlc(self, symbol, *args, **kwargs):
            called.append(symbol)
            return dict(t=[], o=[], h=[], l=[], c=[], v=[])

    refresh_market(Gateway(), store, exchanges=['HOSE'], timeframes=('1D',))
    assert called == ['VNINDEX', 'HPG']
    assert len(store.list_instruments()) == 2

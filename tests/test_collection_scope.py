import pytest

from stock_reports.core.config import Settings
from stock_reports.data_sources.archive import ResponseArchive
from stock_reports.data_sources.dnse.market import DNSEInstrument
from stock_reports.pipeline.collection import build_parser, resolve_financial_catalog, select_symbols
from stock_reports.pipeline.market_refresh import refresh_market
from stock_reports.storage.industries import IndustryStore
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


def test_financial_catalog_uses_public_industry_companies_without_credentials(tmp_path):
    settings = Settings.from_root(tmp_path)
    industry_store = IndustryStore(settings.industries_database)
    industry_store.save_catalog(
        [dict(sectorId='12', slug='ngan-hang', name='Ngân hàng', level=2,
              classificationType='gics')],
        [dict(symbol='VCB', floor='HOSE', type='STOCK', isListed=True,
              gicsIndustryGroupId='12', companyName='Vietcombank')],
        retrieved_at='2026-10-09T00:00:00+00:00',
    )
    market_store = MarketStore(settings.market_database)
    market_store.initialize()

    catalog = resolve_financial_catalog(
        settings, market_store, ResponseArchive(tmp_path / 'raw')
    )

    assert [(row.symbol, row.exchange) for row in catalog] == [('VCB', 'HOSE')]
    assert market_store.list_instruments() == [('VCB', 'HOSE')]


def test_collection_parser_preserves_conservative_cafef_rate(tmp_path):
    settings = Settings.from_root(tmp_path)
    assert build_parser(settings).parse_args(
        ['financials', '--cafef-rate', '1']
    ).cafef_rate == 1
    assert build_parser(settings).parse_args(
        ['daily', '--date', '2026-10-09']
    ).date.isoformat() == '2026-10-09'

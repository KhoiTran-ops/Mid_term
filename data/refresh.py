"""Finite, resumable DNSE updates for the research database."""

from datetime import datetime
import logging

from data.dnse_market import BENCHMARK_SYMBOL, DNSESynchronizer, VIETNAM


logger = logging.getLogger(__name__)


def refresh_market(gateway, store, *, symbols=None, timeframes=('1D', '1m'),
                   now=None, include_foreign=False, on_progress=None, instruments=None):
    now = now or datetime.now(VIETNAM)
    end = int(now.timestamp())
    day_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    instruments = gateway.list_stock_instruments() if instruments is None else instruments
    if not instruments:
        raise ValueError('DNSE returned an empty instrument catalog')
    store.replace_instruments(instruments, source='dnse')
    if symbols:
        requested = set(symbols)
        instruments = [item for item in instruments if item.symbol in requested]
        unknown = requested - {item.symbol for item in instruments} - {BENCHMARK_SYMBOL}
        if unknown:
            raise ValueError('Unknown DNSE stock symbols: ' + ', '.join(sorted(unknown)))
    sync = DNSESynchronizer(gateway=gateway, store=store)
    saved, failures = 0, []
    targets = [(BENCHMARK_SYMBOL, 946684800, 'INDEX'),
               *[(i.symbol, i.listed_at or 946684800, 'STOCK') for i in instruments]]
    for index, (symbol, listed, asset) in enumerate(targets, 1):
        for timeframe in timeframes:
            latest = store.latest_bar_timestamp(symbol, timeframe)
            # Overlap the last bar so an intraday snapshot can become a completed bar.
            start = (latest if latest is not None else listed) if timeframe == '1D' else day_start
            try:
                saved += sync._sync_range(symbol, '1D' if timeframe == '1D' else '1',
                                          timeframe, start, end, asset_type=asset)
            except Exception as error:
                failures.append(dict(symbol=symbol, timeframe=timeframe,
                                     error_type=type(error).__name__))
                logger.warning('DNSE %s %s failed (%s)', symbol, timeframe, type(error).__name__)
        if include_foreign and asset == 'STOCK':
            from data.dnse_market import parse_foreign_trading
            try:
                rows = parse_foreign_trading(gateway.get_foreign_trading(symbol, day_start, end))
                store.upsert_foreign_snapshots(rows, source='dnse')
            except Exception as error:
                failures.append(dict(symbol=symbol, dataset='foreign', error_type=type(error).__name__))
        if on_progress:
            on_progress(symbol, index, len(targets))
    return dict(provider='dnse', requested_until=now.isoformat(),
                symbols=len(targets), saved=saved, failures=failures,
                timeframes=list(timeframes), foreign_refreshed=include_foreign)

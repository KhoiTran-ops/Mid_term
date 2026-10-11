"""Collect market data and eight-quarter financial statements; no Telegram dependency."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime
import json
import logging
from pathlib import Path
from stock_reports.core.config import Settings
from stock_reports.core.locking import ProcessLock

from stock_reports.data_sources.archive import ArchivedCafeFTransport, ArchivedDNSEGateway, ResponseArchive
from stock_reports.data_sources.cafef.client import CafeFClient
from stock_reports.data_sources.cafef.sync import CafeFSynchronizer, sync_financial_history
from stock_reports.storage.market import MarketStore
from stock_reports.data_sources.dnse.market import VIETNAM
from stock_reports.data_sources.dnse.market import DNSEInstrument
from stock_reports.data_sources.dnse.catalog import select_symbols
from stock_reports.pipeline.industries import public_company_instruments, refresh_public_catalog
from stock_reports.pipeline.market_refresh import refresh_market
from stock_reports.storage.industries import IndustryStore


def progress(provider, path=None):
    def notify(symbol, done, total):
        if path:
            path.write_text(json.dumps(dict(provider=provider, symbol=symbol, done=done,
                total=total, updated_at=datetime.now(VIETNAM).isoformat())), encoding='utf-8')
        if done == 1 or done % 25 == 0 or done == total:
            print(f'{provider}: {done}/{total} ({symbol})', flush=True)
    return notify


def resolve_financial_catalog(settings, store, archive):
    """Resolve a CafeF universe without requiring authenticated DNSE market data."""
    existing = [DNSEInstrument(symbol, exchange, name, 0)
                for symbol, exchange, name in store.list_instrument_details()]
    industry_store = IndustryStore(settings.industries_database)
    instruments = public_company_instruments(industry_store)
    if not instruments:
        if existing:
            return existing
        instruments = refresh_public_catalog(settings, archive)
    store.replace_instruments(instruments, source='dnse-public-catalog')
    return instruments


def build_parser(settings: Settings):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=settings.market_database)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('update', 'market', 'financials'):
        p = commands.add_parser(name)
        p.add_argument('--symbols', nargs='+', help='Default: full existing stock universe')
        p.add_argument('--exchanges', nargs='+', choices=['HOSE', 'HNX', 'UPCOM'],
                       help='Limit collection to these exchanges; preserve the complete catalog')
        p.add_argument('--quarters', type=int, default=8)
        p.add_argument('--timeframes', nargs='+', choices=['1D', '1m'], default=['1D', '1m'])
        p.add_argument('--foreign', action='store_true', help='Also fetch current-day foreign-trading snapshots')
        p.add_argument('--refresh-financials', action='store_true', help='Refetch existing financial blocks too')
        p.add_argument('--cafef-rate', type=float, default=1)
    commands.add_parser('status')
    export = commands.add_parser('export')
    export.add_argument('--symbols', nargs='+')
    export.add_argument('--output', type=Path, default=settings.outputs_directory)
    annual = commands.add_parser('import-annual')
    annual.add_argument('--xlsx', type=Path, required=True)
    annual.add_argument('--source-url', default=(
        'https://github.com/BuiHang-stp/Crawl-CafeF-Data/blob/main/'
        'indicators_all_firms_2010-2024.xlsx'
    ))
    daily = commands.add_parser('daily')
    daily.add_argument('--date', type=date.fromisoformat,
                       default=datetime.now(VIETNAM).date(),
                       help='Trading date in YYYY-MM-DD; default: today in Vietnam')
    daily.add_argument('--cafef-rate', type=float, default=1)
    return parser


def main(argv=None, settings: Settings | None = None):
    settings = settings or Settings.from_root(Path(__file__).resolve().parents[3])
    args = build_parser(settings).parse_args(argv)
    args.database = (settings.root / args.database).resolve()
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')
    store = MarketStore(args.database)
    store.initialize()
    if args.command == 'import-annual':
        from stock_reports.pipeline.annual_financials import import_annual_workbook
        result = import_annual_workbook(
            args.database, (settings.root / args.xlsx).resolve(),
            source_url=args.source_url,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == 'daily':
        if not 0 < args.cafef_rate <= 1:
            raise ValueError('--cafef-rate must be in (0, 1]')
        started = datetime.now(VIETNAM)
        run_dir = settings.runs_directory / started.strftime('%Y%m%dT%H%M%S%f')
        archive = ResponseArchive(run_dir / 'raw')
        client = CafeFClient(transport=ArchivedCafeFTransport(
            archive, requests_per_second=args.cafef_rate
        ))
        results = [asdict(result) for result in CafeFSynchronizer(
            client=client, store=store
        ).sync_daily(args.date)]
        manifest = dict(status='completed_with_issues' if any(
            result['rejected'] for result in results
        ) else 'completed', started_at=started.isoformat(),
            completed_at=datetime.now(VIETNAM).isoformat(), command='daily',
            requested_date=args.date.isoformat(), database=str(args.database),
            results=results)
        (run_dir / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
        from stock_reports.storage.inventory import write_inventory
        write_inventory(store, settings.outputs_directory)
        if any(result['rejected'] for result in results):
            raise SystemExit(2)
        return
    if args.command in ('status', 'export'):
        from stock_reports.storage.inventory import export_data, write_inventory
        result = write_inventory(store, settings.outputs_directory) if args.command == 'status' else export_data(
            store, (settings.root / args.output).resolve(), args.symbols)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.quarters < 1:
        raise ValueError('--quarters must be positive')
    if not 0 < args.cafef_rate <= 1:
        raise ValueError('--cafef-rate must be in (0, 1]')
    symbols = [s.strip().upper() for s in args.symbols] if args.symbols else None
    started = datetime.now(VIETNAM)
    run_dir = settings.runs_directory / started.strftime('%Y%m%dT%H%M%S%f')
    archive = ResponseArchive(run_dir / 'raw')
    (run_dir / 'manifest.json').write_text(json.dumps(dict(status='running',
        started_at=started.isoformat(), command=args.command, exchanges=args.exchanges,
        database=str(args.database), quarters=args.quarters)), encoding='utf-8')
    catalog = None

    def new_gateway():
        key, secret = settings.dnse_api_key, settings.dnse_api_secret
        if not key or not secret:
            raise ValueError('Configure both DNSE_API_KEY and DNSE_API_SECRET in .env')
        return ArchivedDNSEGateway(key, secret, archive)

    def market():
        gateway = new_gateway()
        try:
            return refresh_market(gateway, store, symbols=symbols,
                timeframes=tuple(args.timeframes), include_foreign=args.foreign,
                on_progress=progress('DNSE', run_dir / 'dnse-progress.json'),
                instruments=catalog, exchanges=args.exchanges)
        finally:
            gateway.close()

    def financials():
        lock = ProcessLock(settings.root/'var/cafef-collector.lock')
        if not lock.acquire():
            raise ValueError('A CafeF financial collector is already running')
        try:
            financial_catalog = catalog or resolve_financial_catalog(settings, store, archive)
            selected = select_symbols(financial_catalog, exchanges=args.exchanges, symbols=symbols)
            client = CafeFClient(transport=ArchivedCafeFTransport(archive,
                    requests_per_second=args.cafef_rate))
            result = sync_financial_history(client, store, max_quarters=args.quarters,
                    symbols=selected, incremental=not args.refresh_financials,
                    on_progress=progress('CafeF', run_dir / 'cafef-progress.json'))
            return dict(provider='cafef', **asdict(result), incremental=not args.refresh_financials,
                        symbols=len(selected), exchanges=args.exchanges)
        finally:
            lock.release()

    results = []
    try:
        if args.command == 'update':
            # Both collectors use the same current catalog, including newly listed stocks.
            gateway = new_gateway()
            try:
                catalog = gateway.list_stock_instruments()
                if not catalog:
                    raise ValueError('DNSE returned an empty instrument catalog')
                store.replace_instruments(catalog, source='dnse')
            finally:
                gateway.close()
            # Two providers; each retains its own conservative request pacing.
            with ThreadPoolExecutor(max_workers=2) as executor:
                tasks = [executor.submit(market), executor.submit(financials)]
                for task in tasks:
                    results.append(task.result())
        else:
            results.append(market() if args.command == 'market' else financials())
    except BaseException as error:
        failure = dict(status='cancelled' if isinstance(error, KeyboardInterrupt) else 'failed',
            started_at=started.isoformat(), completed_at=datetime.now(VIETNAM).isoformat(),
            command=args.command, symbols=symbols, exchanges=args.exchanges, quarters=args.quarters,
            database=str(args.database), error_type=type(error).__name__, results=results)
        (run_dir / 'manifest.json').write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding='utf-8')
        raise
    manifest = dict(status='completed_with_issues' if any(r.get('failures') or r.get('rejected') for r in results) else 'completed',
                    started_at=started.isoformat(), completed_at=datetime.now(VIETNAM).isoformat(),
                    command=args.command, quarters=args.quarters,
                    database=str(args.database), symbols=symbols, exchanges=args.exchanges, results=results)
    (run_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    from stock_reports.storage.inventory import write_inventory
    write_inventory(store, settings.outputs_directory)
    if any(result.get('failures') or result.get('rejected') for result in results):
        raise SystemExit(2)


if __name__ == '__main__':
    main()

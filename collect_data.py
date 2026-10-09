"""Collect market data and eight-quarter financial statements; no Telegram dependency."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from data.archive import ArchivedCafeFTransport, ArchivedDNSEGateway, ResponseArchive
from data.cafef.client import CafeFClient
from data.cafef.sync import sync_financial_history
from data.db.market_store import MarketStore
from data.dnse_market import VIETNAM
from data.refresh import refresh_market


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')


def progress(provider):
    def notify(symbol, done, total):
        if done == 1 or done % 25 == 0 or done == total:
            print(f'{provider}: {done}/{total} ({symbol})', flush=True)
    return notify


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT / os.getenv('DATABASE_PATH', 'var/market_data.db'))
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('update', 'market', 'financials'):
        p = commands.add_parser(name)
        p.add_argument('--symbols', nargs='+', help='Default: full existing stock universe')
        p.add_argument('--quarters', type=int, default=8)
        p.add_argument('--timeframes', nargs='+', choices=['1D', '1m'], default=['1D', '1m'])
        p.add_argument('--foreign', action='store_true', help='Also fetch current-day foreign-trading snapshots')
        p.add_argument('--refresh-financials', action='store_true', help='Refetch existing financial blocks too')
        p.add_argument('--cafef-rate', type=float, default=1)
    commands.add_parser('status')
    export = commands.add_parser('export')
    export.add_argument('--symbols', nargs='+')
    export.add_argument('--output', type=Path, default=ROOT / 'outputs')
    return parser


def main():
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')
    store = MarketStore(args.database)
    store.initialize()
    if args.command in ('status', 'export'):
        from data.inventory import export_data, write_inventory
        result = write_inventory(store, ROOT / 'outputs') if args.command == 'status' else export_data(
            store, args.output, args.symbols)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.quarters < 1:
        raise ValueError('--quarters must be positive')
    symbols = [s.strip().upper() for s in args.symbols] if args.symbols else None
    started = datetime.now(VIETNAM)
    run_dir = ROOT / 'var' / 'runs' / started.strftime('%Y%m%dT%H%M%S%f')
    archive = ResponseArchive(run_dir / 'raw')
    catalog = None

    def new_gateway():
        key, secret = os.getenv('DNSE_API_KEY'), os.getenv('DNSE_API_SECRET')
        if not key or not secret:
            raise ValueError('Configure both DNSE_API_KEY and DNSE_API_SECRET in .env')
        return ArchivedDNSEGateway(key, secret, archive)

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

    def market():
        gateway = new_gateway()
        try:
            return refresh_market(gateway, store, symbols=symbols,
                timeframes=tuple(args.timeframes), include_foreign=args.foreign,
                on_progress=progress('DNSE'), instruments=catalog)
        finally:
            gateway.close()

    def financials():
        client = CafeFClient(transport=ArchivedCafeFTransport(archive,
                requests_per_second=args.cafef_rate))
        result = sync_financial_history(client, store, max_quarters=args.quarters,
                symbols=symbols, incremental=not args.refresh_financials,
                on_progress=progress('CafeF'))
        return dict(provider='cafef', **asdict(result), incremental=not args.refresh_financials)

    results = []
    if args.command == 'update':
        # Two different providers; each retains its own conservative request pacing.
        with ThreadPoolExecutor(max_workers=2) as executor:
            tasks = [executor.submit(market), executor.submit(financials)]
            for task in tasks:
                results.append(task.result())
    else:
        results.append(market() if args.command == 'market' else financials())
    manifest = dict(started_at=started.isoformat(), completed_at=datetime.now(VIETNAM).isoformat(),
                    database=str(args.database), symbols=symbols, results=results)
    (run_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    from data.inventory import write_inventory
    write_inventory(store, ROOT / 'outputs')
    if any(result.get('failures') or result.get('rejected') for result in results):
        raise SystemExit(2)


if __name__ == '__main__':
    main()

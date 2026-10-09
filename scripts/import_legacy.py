"""Import only research data, opening the legacy database read-only."""

import argparse
from datetime import datetime, UTC
import json
from pathlib import Path
import sqlite3

from data.db.market_store import MarketStore


TABLES = ('instruments', 'ohlcv_bars', 'foreign_snapshots', 'eod_prices',
          'foreign_trading', 'data_anomalies')


def import_database(source: Path, target: Path, *, quarters: int = 8) -> dict:
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError('Source and destination must be different databases')
    if quarters < 1 or not source.is_file():
        raise ValueError('A readable source database and positive quarter count are required')
    MarketStore(target).initialize()
    counts = {}
    with sqlite3.connect(target, uri=True) as db:
        db.execute('ATTACH DATABASE ? AS legacy', (source.as_uri() + '?mode=ro',))
        for table in TABLES:
            db.execute(f'INSERT OR IGNORE INTO main.{table} SELECT * FROM legacy.{table}')
            counts[table] = db.execute(f'SELECT COUNT(*) FROM main.{table}').fetchone()[0]
            print(f'Imported {table}: {counts[table]:,}', flush=True)
        db.execute('''CREATE TEMP TABLE selected_periods AS
            SELECT symbol,fiscal_year,fiscal_quarter FROM (
                SELECT symbol,fiscal_year,fiscal_quarter,
                    ROW_NUMBER() OVER (PARTITION BY symbol
                    ORDER BY fiscal_year DESC,fiscal_quarter DESC) AS period_rank
                FROM legacy.financial_periods
            ) WHERE period_rank <= ?''', (quarters,))
        db.execute('CREATE INDEX selected_period_key ON selected_periods(symbol,fiscal_year,fiscal_quarter)')
        for table in ('financial_periods', 'financial_facts'):
            db.execute(f'''INSERT OR IGNORE INTO main.{table}
                SELECT f.* FROM legacy.{table} f JOIN selected_periods p
                USING(symbol,fiscal_year,fiscal_quarter)''')
            counts[table] = db.execute(f'SELECT COUNT(*) FROM main.{table}').fetchone()[0]
            print(f'Imported {table}: {counts[table]:,}', flush=True)
    return dict(source_database=str(source), imported_at=datetime.now(UTC).isoformat(),
                quarters=quarters, tables=counts,
                legacy_raw_documents_available=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--database', type=Path, default=Path('var/market_data.db'))
    parser.add_argument('--quarters', type=int, default=8)
    args = parser.parse_args()
    result = import_database(args.source, args.database, quarters=args.quarters)
    manifest = args.database.parent / 'legacy_import.json'
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()

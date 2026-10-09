"""Industry metadata and source-native snapshots, isolated from market history."""

from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3


class IndustryStore:
    def __init__(self, database: Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sectors (
                    classification TEXT NOT NULL, level INTEGER NOT NULL, sector_id TEXT NOT NULL,
                    slug TEXT NOT NULL, name TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                    source_url TEXT NOT NULL, raw_json TEXT NOT NULL,
                    PRIMARY KEY(classification,level,sector_id));
                CREATE TABLE IF NOT EXISTS companies (
                    symbol TEXT NOT NULL, exchange TEXT NOT NULL, company_name TEXT,
                    industry_id TEXT, retrieved_at TEXT NOT NULL, source_url TEXT NOT NULL, raw_json TEXT NOT NULL,
                    PRIMARY KEY(symbol,exchange));
                CREATE TABLE IF NOT EXISTS snapshots (
                    sector_id TEXT NOT NULL, source_time TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                    source_url TEXT NOT NULL, quality TEXT NOT NULL, raw_json TEXT NOT NULL,
                    PRIMARY KEY(sector_id,source_time));''')

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.database, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA journal_mode=WAL')
            with db:
                yield db

    def save_catalog(self, sectors, companies, *, retrieved_at):
        with self.connect() as db:
            for row in sectors:
                db.execute('INSERT OR REPLACE INTO sectors VALUES(?,?,?,?,?,?,?,?)', (
                    row['classificationType'], row['level'], str(row['sectorId']), row['slug'], row['name'],
                    retrieved_at, 'https://api.dnse.com.vn/market-api/sectors?classificationType=gics&level=2',
                    json.dumps(row, ensure_ascii=False)))
            for row in companies:
                if row.get('type') != 'STOCK' or not row.get('isListed') or row.get('floor') not in ('HOSE', 'HNX', 'UPCOM'):
                    continue
                db.execute('INSERT OR REPLACE INTO companies VALUES(?,?,?,?,?,?,?)', (
                    row['symbol'], row['floor'], row.get('companyName'), row.get('gicsIndustryGroupId'),
                    retrieved_at, 'https://api.dnse.com.vn/market-api/tickers', json.dumps(row, ensure_ascii=False)))

    def save_snapshot(self, rows, *, source_time, retrieved_at):
        with self.connect() as db:
            for row in rows:
                db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?,?)', (
                    str(row['id']), source_time, retrieved_at,
                    'wss://datafeed-krx.dnse.com.vn/wss#stats/sector/volatility', 'raw',
                    json.dumps(row, ensure_ascii=False)))

    def summary(self):
        with self.connect() as db:
            result = {key: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                      for key, table in [('sectors', 'sectors'), ('companies', 'companies'), ('snapshots', 'snapshots')]}
            result['latest_source_time'] = db.execute('SELECT MAX(source_time) FROM snapshots').fetchone()[0]
        return result

    def list_companies(self, *, exchange=None):
        with self.connect() as db:
            rows = db.execute('SELECT symbol,exchange,company_name,industry_id FROM companies' +
                (' WHERE exchange=?' if exchange else '') + ' ORDER BY symbol', [exchange] if exchange else []).fetchall()
        return [dict(row) for row in rows]

    def latest_snapshots(self):
        with self.connect() as db:
            rows = db.execute('''SELECT s.* FROM snapshots s JOIN (
                SELECT sector_id,MAX(source_time) AS latest FROM snapshots GROUP BY sector_id
                ) t ON t.sector_id=s.sector_id AND t.latest=s.source_time ORDER BY s.sector_id''').fetchall()
        return [dict(row) for row in rows]

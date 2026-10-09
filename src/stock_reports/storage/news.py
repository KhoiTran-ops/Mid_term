"""News storage adapted from market-pulse; separate from financial databases."""

from contextlib import closing, contextmanager
from datetime import datetime, UTC
import json
from pathlib import Path
import sqlite3

from stock_reports.data_sources.news.normalize import fold


class NewsStore:
    def __init__(self, database: Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, config TEXT NOT NULL, enabled INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', last_attempt TEXT, last_success TEXT,
                    next_run TEXT, error TEXT, failures INTEGER NOT NULL DEFAULT 0,
                    etag TEXT, last_modified TEXT, fetched_count INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, source_id TEXT NOT NULL,
                    title TEXT NOT NULL, excerpt TEXT NOT NULL, published_at TEXT,
                    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, language TEXT, region TEXT,
                    companies TEXT NOT NULL, sectors TEXT NOT NULL, categories TEXT NOT NULL,
                    search_text TEXT NOT NULL, content_hash TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_news_date ON articles(published_at DESC);
                CREATE TABLE IF NOT EXISTS article_sources (
                    article_id INTEGER NOT NULL, source_id TEXT NOT NULL,
                    PRIMARY KEY(article_id,source_id));
                CREATE TABLE IF NOT EXISTS revisions (
                    id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL, snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT,
                    summary TEXT);''')

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.database, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA journal_mode=WAL')
            with db:
                yield db

    def sync_sources(self, sources: list[dict]):
        with self.connect() as db:
            db.execute('UPDATE sources SET enabled=0')
            for source in sources:
                config = json.dumps(source, ensure_ascii=False, sort_keys=True)
                db.execute('''INSERT INTO sources(id,config,enabled) VALUES(?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                    next_run=CASE WHEN sources.config<>excluded.config THEN NULL ELSE sources.next_run END,
                    etag=CASE WHEN sources.config<>excluded.config THEN NULL ELSE sources.etag END,
                    last_modified=CASE WHEN sources.config<>excluded.config THEN NULL ELSE sources.last_modified END,
                    config=excluded.config,enabled=excluded.enabled''',
                    (source['id'], config, int(source.get('enabled', True))))

    def sources(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('SELECT * FROM sources ORDER BY id').fetchall()
        return [{**dict(row), 'config': json.loads(row['config'])} for row in rows]

    def source_state(self, source_id: str, **state):
        allowed = {'status', 'last_attempt', 'last_success', 'next_run', 'error',
                   'failures', 'etag', 'last_modified', 'fetched_count'}
        if not state or not state.keys() <= allowed:
            raise ValueError('Invalid source state')
        with self.connect() as db:
            db.execute('UPDATE sources SET ' + ','.join(f'{key}=?' for key in state) + ' WHERE id=?',
                       [*state.values(), source_id])

    def save_articles(self, items: list[dict]) -> dict:
        added = updated = 0
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            # Feeds overlap: serialize the lookup and insert as one transaction.
            db.execute('BEGIN IMMEDIATE')
            for item in items:
                existing = db.execute('SELECT * FROM articles WHERE url=?', (item['url'],)).fetchone()
                values = (item['title'], item['excerpt'], item['published_at'],
                    json.dumps(item['companies'], ensure_ascii=False), json.dumps(item['sectors'], ensure_ascii=False),
                    json.dumps(item['categories'], ensure_ascii=False), item['search_text'], item['content_hash'], now)
                if existing:
                    article_id = existing['id']
                    if item['content_hash'] != existing['content_hash']:
                        db.execute('INSERT INTO revisions(article_id,recorded_at,snapshot) VALUES(?,?,?)',
                                   (article_id, now, json.dumps(dict(existing), ensure_ascii=False)))
                        db.execute('''UPDATE articles SET title=?,excerpt=?,published_at=?,companies=?,sectors=?,
                            categories=?,search_text=?,content_hash=?,last_seen=? WHERE id=?''', (*values, article_id))
                        updated += 1
                    else:
                        db.execute('UPDATE articles SET last_seen=? WHERE id=?', (now, article_id))
                else:
                    article_id = db.execute('''INSERT INTO articles(title,excerpt,published_at,companies,sectors,
                        categories,search_text,content_hash,last_seen,url,source_id,first_seen,language,region)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (*values, item['url'], item['source_id'], now, item['language'], item['region'])).lastrowid
                    added += 1
                db.execute('INSERT OR IGNORE INTO article_sources VALUES(?,?)', (article_id, item['source_id']))
        return dict(added=added, updated=updated)

    def list_news(self, *, region=None, source_id=None, symbol=None, query=None, page=1, page_size=20) -> dict:
        if region not in (None, 'VN', 'international') or page < 1 or not 1 <= page_size <= 100:
            raise ValueError('Invalid news filters')
        conditions, values = [], []
        if region:
            conditions.append("a.region='VN'" if region == 'VN' else "a.region<>'VN'")
        if source_id:
            conditions.append('EXISTS(SELECT 1 FROM article_sources x WHERE x.article_id=a.id AND x.source_id=?)')
            values.append(source_id)
        if symbol:
            conditions.append('EXISTS(SELECT 1 FROM json_each(a.companies) WHERE value=?)')
            values.append(symbol.upper())
        if query:
            conditions.append('a.search_text LIKE ?')
            values.append('%' + fold(query) + '%')
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        with self.connect() as db:
            db.execute('BEGIN')
            total = db.execute('SELECT COUNT(*) FROM articles a' + where, values).fetchone()[0]
            rows = db.execute('''SELECT a.*,json_extract(s.config,'$.name') AS source_name
                FROM articles a JOIN sources s ON s.id=a.source_id''' + where +
                ' ORDER BY COALESCE(a.published_at,a.first_seen) DESC,a.id DESC LIMIT ? OFFSET ?',
                [*values, page_size, (page-1)*page_size]).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            for key in ('companies', 'sectors', 'categories'):
                item[key] = json.loads(item[key])
            item.pop('search_text')
            item.pop('content_hash')
            items.append(item)
        return dict(items=items, total=total, page=page, page_size=page_size)

    def start_run(self, now: str) -> int:
        with self.connect() as db:
            return db.execute('INSERT INTO runs(started_at) VALUES(?)', (now,)).lastrowid

    def finish_run(self, run_id: int, now: str, summary: dict):
        with self.connect() as db:
            db.execute('UPDATE runs SET completed_at=?,summary=? WHERE id=?',
                       (now, json.dumps(summary), run_id))

    def revision_count(self) -> int:
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0]

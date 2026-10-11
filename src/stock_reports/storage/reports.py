"""A separate report catalog; never open the market database here."""

from contextlib import closing
from datetime import date, datetime, UTC
import hashlib
from pathlib import Path
import re
import shutil
import sqlite3
from uuid import UUID, uuid4

from stock_reports.reports.models import ReportKind, ReportMetadata, ReportPage, StoredReport


class ReportCatalog:
    def __init__(self, database: Path, directory: Path):
        self.database = Path(database)
        self.directory = Path(directory).resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.directory.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript('''CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                as_of TEXT NOT NULL, symbol TEXT, company_name TEXT,
                industry_id TEXT, industry_name TEXT, created_at TEXT NOT NULL,
                sha256 TEXT NOT NULL, pdf_filename TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_reports_scope
                ON reports(kind,symbol,industry_id,as_of);
                CREATE TABLE IF NOT EXISTS report_generation_keys (
                generation_key TEXT PRIMARY KEY,
                report_id TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_report_generation_keys_report
                ON report_generation_keys(report_id);''')

    @staticmethod
    def _generation_key(value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r'[0-9a-f]{64}', value):
            raise ValueError('Invalid report generation key')
        return value

    def find_by_generation_key(self, generation_key: str) -> StoredReport | None:
        generation_key = self._generation_key(generation_key)
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('''SELECT r.* FROM reports r
                JOIN report_generation_keys k ON k.report_id=r.id
                WHERE k.generation_key=?''', (generation_key,)).fetchone()
        return self._record(row) if row else None

    def bind_generation_key(self, generation_key: str, report_id: str) -> StoredReport:
        """Attach a legacy sidecar fingerprint without creating another report."""
        generation_key = self._generation_key(generation_key)
        report_id = str(UUID(report_id))
        with closing(sqlite3.connect(self.database, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT r.* FROM reports r
                JOIN report_generation_keys k ON k.report_id=r.id
                WHERE k.generation_key=?''', (generation_key,)).fetchone()
            if row is None:
                row = db.execute('SELECT * FROM reports WHERE id=?', (report_id,)).fetchone()
                if row is None:
                    db.rollback()
                    raise ValueError('Report not found')
                db.execute('INSERT INTO report_generation_keys VALUES (?,?)',
                           (generation_key, report_id))
            db.commit()
        return self._record(row)

    def register(self, metadata: ReportMetadata, pdf: Path, *,
                 generation_key: str | None = None) -> StoredReport:
        pdf = Path(pdf)
        with pdf.open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                raise ValueError('The report file must have a PDF signature')
        generation_key = self._generation_key(generation_key)
        with pdf.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        identity = (metadata.kind.value, metadata.title, metadata.as_of.isoformat(),
                    metadata.symbol, metadata.company_name, metadata.industry_id,
                    metadata.industry_name)
        destination = None
        destination_created = False
        try:
            with closing(sqlite3.connect(self.database, timeout=30)) as db:
                db.row_factory = sqlite3.Row
                db.execute('BEGIN IMMEDIATE')
                row = None
                if generation_key:
                    row = db.execute('''SELECT r.* FROM reports r
                        JOIN report_generation_keys k ON k.report_id=r.id
                        WHERE k.generation_key=?''', (generation_key,)).fetchone()
                if row is None:
                    row = db.execute('''SELECT * FROM reports WHERE kind=? AND title=?
                        AND as_of=? AND symbol IS ? AND company_name IS ?
                        AND industry_id IS ? AND industry_name IS ? AND sha256=?
                        ORDER BY created_at DESC,id DESC LIMIT 1''', (*identity, digest)).fetchone()
                if row is not None:
                    destination = (self.directory / row['pdf_filename']).resolve()
                    if (not destination.is_relative_to(self.directory) or
                            destination.suffix.lower() != '.pdf'):
                        raise ValueError('Report file is outside the configured PDF directory')
                    if not destination.is_file():
                        shutil.copyfile(pdf, destination)
                        destination_created = True
                        if row['sha256'] != digest:
                            db.execute('UPDATE reports SET sha256=? WHERE id=?',
                                       (digest, row['id']))
                            row = db.execute('SELECT * FROM reports WHERE id=?',
                                             (row['id'],)).fetchone()
                    if generation_key:
                        db.execute('INSERT OR IGNORE INTO report_generation_keys VALUES (?,?)',
                                   (generation_key, row['id']))
                    db.commit()
                    return self._record(row)

                report_id = str(uuid4())
                destination = self.directory / f'{report_id}.pdf'
                shutil.copyfile(pdf, destination)
                destination_created = True
                record = StoredReport(**metadata.model_dump(), id=report_id,
                                      created_at=datetime.now(UTC), sha256=digest)
                db.execute('''INSERT INTO reports
                    (id,kind,title,as_of,symbol,company_name,industry_id,industry_name,
                     created_at,sha256,pdf_filename) VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
                    record.id, record.kind.value, record.title, record.as_of.isoformat(),
                    record.symbol, record.company_name, record.industry_id, record.industry_name,
                    record.created_at.isoformat(), record.sha256, destination.name))
                if generation_key:
                    db.execute('INSERT INTO report_generation_keys VALUES (?,?)',
                               (generation_key, record.id))
                db.commit()
                return record
        except Exception:
            if destination is not None and destination_created:
                destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def _record(row) -> StoredReport:
        values = dict(row)
        values.pop('pdf_filename')
        values.pop('duplicate_rank', None)
        return StoredReport.model_validate(values)

    def get(self, report_id: str) -> StoredReport | None:
        report_id = str(UUID(report_id))
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM reports WHERE id=?', (report_id,)).fetchone()
        return self._record(row) if row else None

    def pdf_path(self, report_id: str) -> Path:
        report_id = str(UUID(report_id))
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute('SELECT pdf_filename FROM reports WHERE id=?', (report_id,)).fetchone()
        if row is None:
            raise FileNotFoundError('Report not found')
        path = (self.directory / row[0]).resolve()
        if not path.is_relative_to(self.directory) or path.suffix.lower() != '.pdf':
            raise ValueError('Report file is outside the configured PDF directory')
        if not path.is_file():
            raise FileNotFoundError('Report PDF is unavailable')
        return path

    def list_reports(self, *, kind: ReportKind | None = None, symbol: str | None = None,
                     industry_id: str | None = None, query: str | None = None,
                     date_from: date | None = None, date_to: date | None = None,
                     page: int = 1, page_size: int = 20) -> ReportPage:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError('Invalid pagination')
        if date_from and date_to and date_from > date_to:
            raise ValueError('Invalid date range')
        conditions, values = [], []
        for column, value in [('kind', kind), ('symbol', symbol.upper() if symbol else None),
                              ('industry_id', industry_id)]:
            if value:
                conditions.append(f'{column}=?')
                values.append(str(value))
        if query:
            conditions.append('(title LIKE ? OR company_name LIKE ? OR symbol LIKE ?)')
            values.extend([f'%{query}%'] * 3)
        if date_from:
            conditions.append('as_of>=?')
            values.append(date_from.isoformat())
        if date_to:
            conditions.append('as_of<=?')
            values.append(date_to.isoformat())
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        ranked = '''WITH filtered AS (SELECT * FROM reports''' + where + '''),
            ranked AS (SELECT *,ROW_NUMBER() OVER (
                PARTITION BY kind,title,as_of,COALESCE(symbol,''),COALESCE(company_name,''),
                    COALESCE(industry_id,''),COALESCE(industry_name,'')
                ORDER BY created_at DESC,id DESC) AS duplicate_rank FROM filtered)'''
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            total = db.execute(ranked + ' SELECT COUNT(*) FROM ranked WHERE duplicate_rank=1',
                               values).fetchone()[0]
            rows = db.execute(ranked + ''' SELECT * FROM ranked WHERE duplicate_rank=1
                ORDER BY as_of DESC,created_at DESC,id DESC LIMIT ? OFFSET ?''',
                [*values, page_size, (page - 1) * page_size]).fetchall()
        return ReportPage(items=[self._record(r) for r in rows], total=total, page=page, page_size=page_size)

    def filter_options(self) -> dict:
        with closing(sqlite3.connect(self.database)) as db:
            symbols = db.execute('SELECT DISTINCT symbol FROM reports WHERE symbol IS NOT NULL ORDER BY symbol').fetchall()
            industries = db.execute('SELECT industry_id,MAX(industry_name) FROM reports '
                'WHERE industry_id IS NOT NULL GROUP BY industry_id ORDER BY industry_id').fetchall()
        return dict(symbols=[r[0] for r in symbols],
                    industries=[dict(id=r[0], name=r[1] or r[0]) for r in industries])

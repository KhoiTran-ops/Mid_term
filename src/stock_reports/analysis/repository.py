"""Read one consistent snapshot from each source store for report generation."""

from contextlib import closing
from copy import deepcopy
from datetime import datetime, time, UTC
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from stock_reports.domain.research import SourceReference


VIETNAM = ZoneInfo('Asia/Ho_Chi_Minh')


class ResearchRepository:
    def __init__(self, settings, as_of):
        self.settings, self.as_of = settings, as_of
        self.cutoff = datetime.combine(as_of,time.max,tzinfo=VIETNAM)
        self.now = datetime.now(UTC)
        self._reads = {}
        self._financials = {}
        self._macro = None

    def read(self, database, sql, args=()):
        key=(str(database),sql,tuple(args))
        if key in self._reads:
            return deepcopy(self._reads[key])
        if not Path(database).is_file():
            self._reads[key]=[]
            return []
        with closing(sqlite3.connect(database,timeout=30)) as db:
            db.row_factory=sqlite3.Row
            rows=[dict(r) for r in db.execute(sql,args)]
        self._reads[key]=rows
        return deepcopy(rows)

    def financials(self, symbol, *, period=None, review=None):
        from stock_reports.analysis.financials import load_financials
        key=(symbol,period,review.model_dump_json() if review else None)
        if key not in self._financials:
            self._financials[key]=load_financials(self.settings.market_database,symbol,period=period,review=review)
        return self._financials[key]

    def financial_inputs(self):
        rows={json.dumps(r,sort_keys=True):r for data in self._financials.values() for r in data.raw_rows}
        return list(rows.values())

    def industries(self):
        return self.read(self.settings.industries_database,
            "SELECT * FROM sectors WHERE classification='gics' AND level=2 ORDER BY name")

    def industry(self, value):
        row=next((r for r in self.industries() if value in (r['slug'],r['sector_id'])),None)
        if not row:
            raise ValueError('Ngành chưa có trong danh mục DNSE; chạy industries update trước')
        return row

    def companies(self, industry_id=None):
        return self.read(self.settings.industries_database,
            'SELECT * FROM companies'+(' WHERE industry_id=?' if industry_id else '')+' ORDER BY CASE exchange WHEN \'HOSE\' THEN 0 ELSE 1 END,symbol',
            [industry_id] if industry_id else [])

    def company(self, symbol):
        matches=[r for r in self.companies() if r['symbol']==symbol]
        if not matches:
            raise ValueError('Mã cổ phiếu chưa có trong danh mục doanh nghiệp DNSE')
        row=matches[0]
        row['industry']=self.industry(str(row['industry_id']))
        return row

    def bars(self, symbol):
        rows=self.read(self.settings.market_database,
            "SELECT * FROM ohlcv_bars WHERE symbol=? AND timeframe='1D' AND ts<=? AND is_closed=1 ORDER BY ts DESC LIMIT 252",
            (symbol,int(self.cutoff.timestamp())))
        return list(reversed([r for r in rows if r['low'] <= r['close'] <= r['high'] and r['volume']>=0]))

    def price_source(self, symbol, rows):
        return SourceReference(source_name='DNSE OHLCV',url=f'https://openapi.dnse.com.vn/price/ohlc?symbol={symbol}&resolution=1D',
            retrieved_at=max((r['updated_at'] for r in rows),default=self.now.isoformat()),
            locator=f'var/market_data.db, {symbol}, 1D; {len(rows)} nến đóng hợp lệ')

    def foreign(self,symbol):
        return self.read(self.settings.market_database,
            "SELECT * FROM foreign_snapshots WHERE symbol=? AND board_id='G1' AND ts<=? ORDER BY ts DESC LIMIT 1",
            (symbol,int(self.cutoff.timestamp()*1000)))

    def macro(self):
        if self._macro is not None:
            return deepcopy(self._macro)
        path=self.settings.root/'var/macro/worldbank.json'
        if not path.exists():
            self._macro=[]
            return []
        payload=json.loads(path.read_text(encoding='utf-8'))
        self._macro=[r for r in payload['observations'] if int(r['period']) < self.as_of.year and
                datetime.fromisoformat(r['source']['retrieved_at']).astimezone(UTC) <= self.now]
        return deepcopy(self._macro)

    def news(self, *, symbol=None, macro=False, limit=5):
        conditions=['COALESCE(published_at,first_seen)<=?']
        args=[self.cutoff.astimezone(UTC).isoformat()]
        if symbol:
            conditions.append('EXISTS(SELECT 1 FROM json_each(companies) WHERE value=?)')
            args.append(symbol)
        if macro:
            conditions.append("EXISTS(SELECT 1 FROM json_each(categories) WHERE value='vimo')")
        rows=self.read(self.settings.news_database,"SELECT a.*,json_extract(s.config,'$.name') AS source_name FROM articles a JOIN sources s ON s.id=a.source_id WHERE "+
            ' AND '.join(conditions)+' ORDER BY COALESCE(published_at,first_seen) DESC LIMIT 100',args)
        selected,publishers=[],set()
        for row in rows:
            publisher=row['source_name'].split(' · ')[0]
            if publisher in publishers:
                continue
            publishers.add(publisher)
            selected.append(row)
            if len(selected)==limit:
                break
        return selected

    def snapshots(self):
        return self.read(self.settings.industries_database,
            'SELECT s.* FROM snapshots s JOIN (SELECT sector_id,MAX(source_time) AS t FROM snapshots WHERE source_time<=? GROUP BY sector_id) x ON x.sector_id=s.sector_id AND x.t=s.source_time ORDER BY s.sector_id',
            (self.cutoff.astimezone(UTC).isoformat(),))

    def industry_source(self,industry):
        return SourceReference(source_name='DNSE GICS cấp 2',url=industry['source_url'],retrieved_at=industry['retrieved_at'],
            locator=f"GICS cấp 2, ID {industry['sector_id']}, {industry['name']}")

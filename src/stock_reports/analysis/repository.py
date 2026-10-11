"""Read one consistent snapshot from each source store for report generation."""

from contextlib import closing
from copy import deepcopy
from datetime import date, datetime, time, UTC
import json
import math
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
        valid=[r for r in rows if r['low'] <= r['close'] <= r['high'] and r['volume']>=0]
        if valid:
            return list(reversed(valid))
        fallback=self.read(self.settings.market_database,
            """SELECT symbol,trade_date,open_thousand_vnd,high_thousand_vnd,
                low_thousand_vnd,close_thousand_vnd,matched_volume,source,retrieved_at
                FROM eod_prices WHERE symbol=? AND trade_date<=?
                AND open_thousand_vnd IS NOT NULL AND high_thousand_vnd IS NOT NULL
                AND low_thousand_vnd IS NOT NULL AND close_thousand_vnd IS NOT NULL
                AND low_thousand_vnd<=close_thousand_vnd
                AND close_thousand_vnd<=high_thousand_vnd
                ORDER BY trade_date DESC LIMIT 252""",
            (symbol,self.as_of.isoformat()))
        converted=[]
        for row in reversed(fallback):
            trading_day=date.fromisoformat(row['trade_date'])
            converted.append(dict(symbol=row['symbol'],timeframe='1D',
                ts=int(datetime.combine(trading_day,time(15),tzinfo=VIETNAM).timestamp()),
                open=row['open_thousand_vnd'],high=row['high_thousand_vnd'],
                low=row['low_thousand_vnd'],close=row['close_thousand_vnd'],
                volume=int(row['matched_volume'] or 0),is_closed=1,
                source=row['source'],updated_at=row['retrieved_at'],
                trade_date=row['trade_date']))
        return converted

    def price_source(self, symbol, rows):
        if rows and rows[-1].get('trade_date'):
            return SourceReference(source_name='CafeF EOD',url='https://cafef.vn/du-lieu.chn',
                retrieved_at=max(r['updated_at'] for r in rows),
                locator=f"var/market_data.db, {symbol}, EOD; {len(rows)} phiên đến {rows[-1]['trade_date']}")
        return SourceReference(source_name='DNSE OHLCV',url=f'https://openapi.dnse.com.vn/price/ohlc?symbol={symbol}&resolution=1D',
            retrieved_at=max((r['updated_at'] for r in rows),default=self.now.isoformat()),
            locator=f'var/market_data.db, {symbol}, 1D; {len(rows)} nến đóng hợp lệ')

    def foreign(self,symbol):
        return self.read(self.settings.market_database,
            "SELECT * FROM foreign_snapshots WHERE symbol=? AND board_id='G1' AND ts<=? ORDER BY ts DESC LIMIT 1",
            (symbol,int(self.cutoff.timestamp()*1000)))

    def annual(self,symbol):
        tables={r['name'] for r in self.read(self.settings.market_database,
            "SELECT name FROM sqlite_master WHERE type='table'")}
        old=self.read(self.settings.market_database,
            'SELECT * FROM annual_financial_facts WHERE symbol=? AND fiscal_year<? ORDER BY fiscal_year,metric',
            (symbol,self.as_of.year)) if 'annual_financial_facts' in tables else []
        fresh=self.read(self.settings.market_database,
            'SELECT *,item_name AS metric,retrieved_at AS imported_at,'
            'response_sha256 AS workbook_sha256,statement_type AS sheet_name,'
            'row_order AS source_row FROM annual_statement_facts '
            'WHERE symbol=? AND fiscal_year<? ORDER BY fiscal_year,statement_type,row_order',
            (symbol,self.as_of.year)) if 'annual_statement_facts' in tables else []
        return fresh+old

    def macro(self):
        if self._macro is not None:
            return deepcopy(self._macro)
        path=self.settings.root/'var/macro/worldbank.json'
        if not path.exists():
            self._macro=[]
            return []
        payload=json.loads(path.read_text(encoding='utf-8'))
        self._macro=[r for r in payload['observations'] if r.get('country', 'VNM') == 'VNM' and
                int(r['period']) < self.as_of.year and
                datetime.fromisoformat(r['source']['retrieved_at']).astimezone(UTC) <= self.now]
        return deepcopy(self._macro)

    def news(self, *, symbol=None, macro=False, limit=5, distinct_publishers=True):
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
            if distinct_publishers and publisher in publishers:
                continue
            publishers.add(publisher)
            selected.append(row)
            if len(selected)==limit:
                break
        return selected

    def macro_context(self):
        """Dated official current-period facts, kept apart from annual WDI."""
        path=self.settings.root/'config/macro_observations.json'
        if not path.is_file():return []
        selected=[]
        for row in json.loads(path.read_text(encoding='utf-8'))['observations']:
            source=SourceReference.model_validate(row['source'])
            if not source.published_at:raise ValueError('Current macro observation requires publication date')
            if source.published_at>self.cutoff or date.fromisoformat(row['period_end'])>self.as_of or source.retrieved_at>self.now:continue
            if not isinstance(row['value'],(int,float)) or not math.isfinite(row['value']):raise ValueError('Invalid macro observation')
            selected.append(deepcopy(row))
        return selected

    def snapshots(self):
        return self.read(self.settings.industries_database,
            'SELECT s.* FROM snapshots s JOIN (SELECT sector_id,MAX(source_time) AS t FROM snapshots WHERE source_time<=? GROUP BY sector_id) x ON x.sector_id=s.sector_id AND x.t=s.source_time ORDER BY s.sector_id',
            (self.cutoff.astimezone(UTC).isoformat(),))

    def industry_source(self,industry):
        return SourceReference(source_name='DNSE GICS cấp 2',url=industry['source_url'],retrieved_at=industry['retrieved_at'],
            locator=f"GICS cấp 2, ID {industry['sector_id']}, {industry['name']}")

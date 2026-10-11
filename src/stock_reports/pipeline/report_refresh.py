"""Debounced refresh of watched reports while keeping immutable PDF snapshots."""
from datetime import datetime,UTC
import hashlib
import json
import sqlite3
import threading
import time

from stock_reports.core.files import atomic_json
from stock_reports.core.locking import ProcessLock
from stock_reports.pipeline.research_reports import GenerationRequest,generate_reports
from stock_reports.analysis.repository import VIETNAM


class ReportRefreshRunner:
    def __init__(self,settings):
        self.settings=settings;self.stop_event=threading.Event();self.thread=None
        path=settings.root/'config/report_refresh.json'
        self.config=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        self.lock=ProcessLock(settings.root/'var/report-auto-refresh.lock')
        self.seen={};self.attempted={};self.last_results={}

    def start(self):
        if not self.config.get('enabled') or not self.lock.acquire():return False
        self.thread=threading.Thread(target=self._loop,name='report-refresh',daemon=True);self.thread.start();return True

    def signature(self,symbol,day):
        values=[day]
        for database,queries in [(self.settings.news_database,[('SELECT url,title,excerpt,published_at FROM articles WHERE EXISTS(SELECT 1 FROM json_each(companies) WHERE value=?) ORDER BY published_at DESC LIMIT 20',(symbol,))]),
                (self.settings.market_database,[('SELECT MAX(retrieved_at),COUNT(*) FROM financial_facts WHERE symbol=?',(symbol,)),('SELECT MAX(retrieved_at),COUNT(*) FROM annual_statement_facts WHERE symbol=?',(symbol,))])]:
            with sqlite3.connect(database,timeout=30) as db:
                for sql,args in queries:values.append(db.execute(sql,args).fetchall())
        paths=[self.settings.root/'strategy_config.json']
        paths.extend(self.settings.root/'var'/folder/f'{symbol}.json' for folder in
                     ('financial_reviews','annual_reviews','stocklens_adjusted_prices','stocklens_prices','issuer_news','corporate_actions'))
        paths.extend((self.settings.root/'config/valuation'/f'{symbol}.json',
                      self.settings.root/'var/stocklens_adjusted_prices/VNINDEX.json'))
        for path in paths:
            values.append(hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
        return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()

    def run_once(self):
        day=datetime.now(VIETNAM).date();now=time.monotonic();results=[]
        with sqlite3.connect(self.settings.reports_database,timeout=30) as db:
            rows=db.execute("SELECT symbol,id FROM reports r WHERE kind='stock' AND symbol IS NOT NULL AND id=(SELECT id FROM reports x WHERE x.kind='stock' AND x.symbol=r.symbol ORDER BY created_at DESC LIMIT 1) ORDER BY symbol").fetchall()
        def publish(stage, symbol=None):
            self.last_results.update((r['symbol'],r) for r in results)
            atomic_json(self.settings.outputs_directory/'REPORT_REFRESH_STATUS.json',dict(enabled=True,
                updated_at=datetime.now(UTC).isoformat(),watched=len(rows),stage=stage,current_symbol=symbol,
                minimum_interval_seconds=self.config.get('minimum_interval_seconds',300),results=results,
                last_results=list(self.last_results.values())))
        publish('checking')
        for symbol,latest_id in rows:
            if self.stop_event.is_set():break
            if now-self.attempted.get(symbol,-1e10)<self.config.get('minimum_interval_seconds',300):continue
            try:
                signature=self.signature(symbol,day.isoformat())
                if self.seen.get(symbol)==signature:continue
                self.attempted[symbol]=now
                publish('generating',symbol)
                archive=self.settings.outputs_directory/'analysis'/f'{latest_id}.json'
                saved=json.loads(archive.read_text(encoding='utf-8')) if archive.is_file() else {}
                horizon=saved.get('request',{}).get('horizon')
                result=generate_reports(self.settings,GenerationRequest(kind='stock',symbol=symbol,as_of=day,horizon=horizon))[0]
                self.seen[symbol]=self.signature(symbol,day.isoformat())
                results.append(dict(symbol=symbol,report_id=result['report']['id'],reused=result['reused']))
            except Exception as error:
                results.append(dict(symbol=symbol,error_type=type(error).__name__))
            publish('checking')
        publish('idle')
        return results

    def _loop(self):
        try:
            while not self.stop_event.is_set():
                try:self.run_once()
                except Exception as error:
                    atomic_json(self.settings.outputs_directory/'REPORT_REFRESH_STATUS.json',dict(enabled=True,updated_at=datetime.now(UTC).isoformat(),error_type=type(error).__name__))
                self.stop_event.wait(self.config.get('tick_seconds',60))
        finally:self.lock.release()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=30)

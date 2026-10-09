"""Polling/cache/backoff behavior adapted from market-pulse/src/collector.js."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC, timedelta
import json
from pathlib import Path
import threading

from stock_reports.data_sources.news.adapters import collect_source
from stock_reports.data_sources.news.normalize import normalize_article


def load_news_config(root: Path):
    sources = json.loads((root / 'config/news_sources.json').read_text(encoding='utf-8'))
    ids = set()
    for source in sources:
        if source['id'] in ids or source['kind'] not in ('rss', 'listing'):
            raise ValueError('Duplicate or unsupported news source')
        if not source['url'].startswith('https://') or source['intervalMinutes'] < 1:
            raise ValueError('News sources require HTTPS and a positive polling interval')
        ids.add(source['id'])
    entities = json.loads((root / 'config/news_entities.json').read_text(encoding='utf-8'))
    return sources, entities


class NewsCollector:
    def __init__(self, store, entities, *, adapter=collect_source, clock=lambda: datetime.now(UTC),
                 concurrency=4):
        self.store, self.entities, self.adapter, self.clock = store, entities, adapter, clock
        self.concurrency = concurrency
        self.lock = threading.Lock()

    def run(self, *, force=False, stop=None) -> dict:
        if not self.lock.acquire(blocking=False):
            return dict(busy=True)
        run_id = None
        summary = dict(sources=0, success=0, failed=0, added=0, updated=0)
        try:
            now = self.clock()
            states = [s for s in self.store.sources() if s['enabled'] and
                (force or not s['next_run'] or datetime.fromisoformat(s['next_run']) <= now)]
            summary['sources'] = len(states)
            if not states:
                return summary
            run_id = self.store.start_run(now.isoformat())

            def collect(state):
                if stop and stop.is_set():
                    return dict(cancelled=True)
                config, source_id = state['config'], state['id']
                self.store.source_state(source_id, status='running', last_attempt=self.clock().isoformat())
                try:
                    result = self.adapter(config, state)
                    if not result.get('not_modified'):
                        rows = [normalize_article(r, config, self.entities) for r in result.get('articles', [])]
                        items = [r for r in rows if r]
                        if rows and not items:
                            raise ValueError('No valid article URLs or titles')
                        saved = self.store.save_articles(items)
                    else:
                        items, saved = [], dict(added=0, updated=0)
                    self.store.source_state(source_id, status='ok', error=None, failures=0,
                        last_success=self.clock().isoformat(),
                        next_run=(self.clock() + timedelta(minutes=config['intervalMinutes'])).isoformat(),
                        etag=state['etag'] if result.get('not_modified') else result.get('etag'),
                        last_modified=state['last_modified'] if result.get('not_modified') else result.get('last_modified'),
                        fetched_count=state['fetched_count'] if result.get('not_modified') else len(items))
                    return dict(success=1, **saved)
                except Exception as error:
                    failures = state['failures'] + 1
                    delay = min(21600, 60 * 2 ** min(failures, 8))
                    status = getattr(getattr(error, 'response', None), 'status_code', None)
                    # Never persist exception messages/URLs that might carry credentials.
                    self.store.source_state(source_id, status='error', failures=failures,
                        error=f'HTTP {status}' if status else type(error).__name__,
                        next_run=(self.clock() + timedelta(seconds=delay)).isoformat())
                    return dict(failed=1)

            with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                for result in executor.map(collect, states):
                    for key in ('success', 'failed', 'added', 'updated'):
                        summary[key] += result.get(key, 0)
            return summary
        finally:
            try:
                if run_id is not None:
                    self.store.finish_run(run_id, self.clock().isoformat(), summary)
            finally:
                self.lock.release()

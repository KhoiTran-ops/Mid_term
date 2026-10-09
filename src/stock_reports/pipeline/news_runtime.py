"""News lifecycle shared by the unified CLI and web process."""

from datetime import datetime, UTC
import logging
from pathlib import Path
import threading

from stock_reports.core.locking import ProcessLock
from stock_reports.data_sources.archive import ResponseArchive
from stock_reports.pipeline.news import NewsCollector, load_news_config
from stock_reports.storage.news import NewsStore


logger = logging.getLogger(__name__)


def configured_news(settings):
    store = NewsStore(settings.news_database)
    if not (settings.root / 'config/news_sources.json').is_file():
        return store, None
    sources, entities = load_news_config(settings.root)
    store.sync_sources(sources)

    def adapter(source, state):
        from stock_reports.data_sources.news.adapters import collect_source
        stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')
        archive = ResponseArchive(settings.runs_directory / ('news-' + stamp) / source['id'])
        return collect_source(source, state, archive)

    return store, NewsCollector(store, entities, adapter=adapter)


class NewsRunner:
    def __init__(self, settings, collector, *, tick_seconds=5):
        self.collector, self.tick_seconds = collector, tick_seconds
        self.process_lock = ProcessLock(settings.root / 'var/news-collector.lock')
        self.stop_event = threading.Event()
        self.thread = None
        self.last_error = None

    def start(self) -> bool:
        if not self.collector or not self.process_lock.acquire():
            return False
        self.thread = threading.Thread(target=self._loop, name='news-collector', daemon=True)
        self.thread.start()
        return True

    def _loop(self):
        try:
            while not self.stop_event.is_set():
                try:
                    result = self.collector.run(stop=self.stop_event)
                    self.last_error = None
                    if result.get('sources'):
                        logger.info('News: %s', result)
                except Exception as error:
                    self.last_error = type(error).__name__
                    logger.error('News collection failed (%s)', self.last_error)
                self.stop_event.wait(self.tick_seconds)
        finally:
            self.process_lock.release()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=30)

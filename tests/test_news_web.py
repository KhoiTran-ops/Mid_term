from dataclasses import replace

from fastapi.testclient import TestClient

from stock_reports.core.config import Settings
from stock_reports.storage.news import NewsStore
from stock_reports.web.app import create_app
from tests.test_news import SOURCE, article, ENTITIES
from stock_reports.data_sources.news.normalize import normalize_article


def test_news_page_and_separate_filters_do_not_expose_markup_or_private_files(tmp_path):
    settings = replace(Settings.from_root(tmp_path), news_auto_update=False)
    app = create_app(settings)
    store = NewsStore(settings.news_database)
    store.sync_sources([SOURCE, {**SOURCE, 'id': 'world', 'region': 'Global'}])
    store.save_articles([article(title='<script>alert(1)</script> Hòa Phát tăng sản lượng thép')])
    store.save_articles([normalize_article(dict(title='Global economy news', url='https://example.org/b'),
        {**SOURCE, 'id': 'world', 'region': 'Global'}, ENTITIES)])
    with TestClient(app) as client:
        assert client.get('/news').status_code == 200
        assert 'Việt Nam' in client.get('/news').text and 'Quốc tế' in client.get('/news').text
        assert '<script>alert(1)</script>' not in client.get('/news').text
        assert client.get('/api/news?region=VN').json()['total'] == 1
        assert client.get('/api/news?region=international').json()['total'] == 1
        assert client.get('/api/news?symbol=hpg&query=hoa%20phat').json()['total'] == 1
        assert client.get('/api/news?region=invalid').status_code == 422
        assert client.get('/api/news?page_size=101').status_code == 422
        assert client.get('/api/reports').json()['total'] == 0
        assert client.get('/var/news.db').status_code == 404
        assert 'Tin tức' in client.get('/').text

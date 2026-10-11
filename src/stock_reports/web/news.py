"""Read-only news UI and API, with filters independent from report filters."""

from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi import Path as ApiPath


def news_router(store, templates) -> APIRouter:
    router = APIRouter()

    @router.get('/api/news')
    def news(region: Literal['VN', 'international'] | None = None,
             source_id: str | None = Query(None, max_length=80),
             symbol: str | None = Query(None, max_length=12), query: str | None = Query(None, max_length=240),
             category: Literal['chungkhoan','doanhnghiep','nganhang','taichinh','quocte','vimo','kinhteso','thitruong','kinhte','nganh','diachinhtri'] | None = None,
             page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        return store.list_news(region=region, source_id=source_id, symbol=symbol,
                               query=query, category=category, page=page, page_size=page_size)

    @router.get('/api/companies/{symbol}/news')
    def company_news(symbol:str=ApiPath(pattern=r'^[A-Za-z0-9]{2,12}$')):
        return store.company_news(symbol.upper())

    @router.get('/api/news/sources')
    def sources():
        return {'items': [dict(id=s['id'], name=s['config']['name'], region=s['config']['region'],
            enabled=bool(s['enabled']), status=s['status'], last_attempt=s['last_attempt'],
            last_success=s['last_success'], next_run=s['next_run'], error=s['error'],
            interval_minutes=s['config']['intervalMinutes'], fetched_count=s['fetched_count']) for s in store.sources()]}

    @router.get('/news')
    def page_news(request: Request, region: Literal['', 'VN', 'international'] = '',
                  source_id: str = Query('', max_length=80), symbol: str = Query('', max_length=12),
                  query: str = Query('', max_length=240), page: int = Query(1, ge=1)):
        category=request.query_params.get('category') or None
        if category not in (None,'chungkhoan','doanhnghiep','nganhang','taichinh','quocte','vimo','kinhteso','thitruong','kinhte','nganh','diachinhtri'):
            from fastapi import HTTPException
            raise HTTPException(422,'Chủ đề tin tức không hợp lệ.')
        result = store.list_news(region=region or None, source_id=source_id or None,
            symbol=symbol or None, query=query or None, category=category, page=page)
        total_pages = max(1, (result['total'] + result['page_size'] - 1) // result['page_size'])
        states = [s for s in store.sources() if s['enabled']]
        return templates.TemplateResponse(request=request, name='news.html', context=dict(active='news',
            result=result, filters=dict(region=region, source_id=source_id, symbol=symbol.upper(), query=query,category=category or ''),
            sources=states, failed_sources=[s for s in states if s['status'] == 'error'],
            latest_success=max((s['last_success'] for s in states if s['last_success']), default=None),
            total_pages=total_pages,
            previous_url=str(request.url.include_query_params(page=page-1)) if page>1 else None,
            next_url=str(request.url.include_query_params(page=page+1)) if page<total_pages else None))

    return router

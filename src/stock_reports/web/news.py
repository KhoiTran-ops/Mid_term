"""Read-only news UI and API, with filters independent from report filters."""

from typing import Literal

from fastapi import APIRouter, Query, Request


def news_router(store, templates) -> APIRouter:
    router = APIRouter()

    @router.get('/api/news')
    def news(region: Literal['VN', 'international'] | None = None,
             source_id: str | None = Query(None, max_length=80),
             symbol: str | None = Query(None, max_length=12), query: str | None = Query(None, max_length=240),
             page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        return store.list_news(region=region, source_id=source_id, symbol=symbol,
                               query=query, page=page, page_size=page_size)

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
        result = store.list_news(region=region or None, source_id=source_id or None,
            symbol=symbol or None, query=query or None, page=page)
        total_pages = max(1, (result['total'] + result['page_size'] - 1) // result['page_size'])
        states = [s for s in store.sources() if s['enabled']]
        return templates.TemplateResponse(request=request, name='news.html', context=dict(active='news',
            result=result, filters=dict(region=region, source_id=source_id, symbol=symbol.upper(), query=query),
            sources=states, failed_sources=[s for s in states if s['status'] == 'error'],
            latest_success=max((s['last_success'] for s in states if s['last_success']), default=None),
            total_pages=total_pages,
            previous_url=str(request.url.include_query_params(page=page-1)) if page>1 else None,
            next_url=str(request.url.include_query_params(page=page+1)) if page<total_pages else None))

    return router

"""Public, archived market fundamentals; independent of analyst reviews."""
from datetime import datetime, UTC
import json
import re
from stock_reports.analysis.market_fundamentals import provider_number, provider_metrics
from stock_reports.core.locking import ProcessLock
from stock_reports.data_sources.archive import ArchivedCafeFTransport, ResponseArchive

UNIT_SOURCE = 'https://cafef.vn/du-lieu/hose/hpg-1673049600288.chn'


def refresh(settings, symbols):
    settings.outputs_directory.mkdir(parents=True,exist_ok=True)
    lock = ProcessLock(settings.root/'var/market-fundamentals.lock')
    if not lock.acquire(): raise ValueError('A fundamentals refresh is already running')
    try:
        transport = ArchivedCafeFTransport(ResponseArchive(settings.root/'var/source_archive'),requests_per_second=1, timeout_seconds=12, retries=1)
        html = transport.get(UNIT_SOURCE).decode('utf-8')
        if not re.search(r'Giá\s*\(nghìn đồng\)',html): raise ValueError('Price unit source no longer confirms thousand VND')
        output = settings.root/'var/market_fundamentals';output.mkdir(parents=True,exist_ok=True)
        results = []
        for symbol in symbols:
            try:
                if not re.fullmatch(r'[A-Z0-9]{2,12}',symbol):raise ValueError('Invalid symbol')
                sources=[];payloads={}
                for endpoint in ('ChiSoTaiChinh','PriceRealTimeHeader'):
                    url=f'https://cafef.vn/du-lieu/Ajax/PageNew/{endpoint}.ashx?Symbol={symbol}'
                    payload=json.loads(transport.get(url))
                    if payload.get('Success') is not True:raise ValueError('Provider did not return successful data')
                    payloads[endpoint]=payload
                    sources.append(dict(source_name='CafeF '+endpoint,url=url,retrieved_at=datetime.now(UTC).isoformat()))
                now=datetime.now(UTC).isoformat();data=payloads['PriceRealTimeHeader'].get('Data') or {}
                stamp=re.fullmatch(r'/Date\((\d+)\)/',data.get('ThoiGian') or '')
                price=provider_number(data.get('Gia'));quote=None
                sources.append(dict(source_name='CafeF đơn vị giá',url=UNIT_SOURCE,retrieved_at=now,
                    locator='Đơn vị: Giá (nghìn đồng); không xác nhận đơn vị DNSE'))
                if stamp and price is not None and price>0:
                    timestamp=datetime.fromtimestamp(int(stamp[1])/1000,UTC).isoformat()
                    quote=dict(price_vnd=str(price*1000),timestamp=timestamp,
                        source={**sources[1],'published_at':timestamp,'locator':'Giá thị trường CafeF; nghìn VND × 1000'})
                indicators=payloads['ChiSoTaiChinh'].get('Data')
                if not isinstance(indicators,list):raise ValueError('Invalid indicator list')
                snapshot=dict(symbol=symbol,retrieved_at=now,indicators=indicators,quote=quote,sources=sources,
                    fundamental_period=next((r.get('Value') for r in indicators if r.get('Code')=='ThoiGian'),None),
                    caveat='Ảnh chụp chỉ tiêu nguồn tại thời điểm tải; chưa có lịch sử công bố/điều chỉnh của từng chỉ tiêu.')
                tmp=output/f'{symbol}.json.tmp';tmp.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(output/f'{symbol}.json')
                results.append(dict(symbol=symbol,metrics=len(provider_metrics(snapshot)),quote=bool(quote)))
            except Exception as error:results.append(dict(symbol=symbol,error_type=type(error).__name__,message=str(error)[:180]))
            progress=dict(status='running',completed=len(results),total=len(symbols),results=results,updated_at=datetime.now(UTC).isoformat())
            (settings.outputs_directory/'MARKET_FUNDAMENTALS_PROGRESS.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding='utf-8')
        progress['status']='completed_with_gaps' if any('error_type' in r for r in results) else 'completed'
        (settings.outputs_directory/'MARKET_FUNDAMENTALS_PROGRESS.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding='utf-8')
        return results
    finally:lock.release()

"""Read-only adjusted-price refresh with explicit VCI → KBS fallback and archive."""
from datetime import date,datetime,UTC,timedelta
import json
import logging
import re


def ensure_adjusted_history(settings,symbol,as_of):
    if not re.fullmatch('[A-Z0-9]{2,12}',symbol):raise ValueError('Invalid ticker')
    config=settings.root/'config/stocklens.json'
    if not config.is_file() or not json.loads(config.read_text(encoding='utf-8')).get('auto_price_refresh',False):return False
    path=settings.root/'var/stocklens_adjusted_prices'/f'{symbol}.json'
    expected=as_of
    while expected.weekday()>4:expected-=timedelta(days=1)
    if path.is_file():
        cached=json.loads(path.read_text(encoding='utf-8'))
        days=[r['time'][:10] for r in cached.get('rows',[]) if r['time'][:10]<=expected.isoformat()]
        if cached.get('adjusted') is True and len(days)>=300 and max(days)>=expected.isoformat():return True
    attempts=[]
    try:from vnstock import Quote
    except ImportError:
        attempts.append(dict(source='vnstock',status='dependency_missing'))
    else:
        for provider in ('VCI','KBS'):
            try:
                df=Quote(symbol=symbol,source=provider).history(start=(as_of-timedelta(days=800)).isoformat(),end=expected.isoformat(),interval='1D')
                rows=json.loads(df.to_json(orient='records',date_format='iso'))
                if not rows:raise ValueError('Empty adjusted history')
                stamp=datetime.now(UTC).isoformat()
                payload=dict(symbol=symbol,unit='index points' if symbol=='VNINDEX' else 'thousand VND',adjusted=True,
                    volume_basis='provider total; not assumed split-adjusted',retrieved_at=stamp,rows=rows,source_attempts=attempts+[dict(source=provider,status='success')],
                    source=dict(item='Giá điều chỉnh '+symbol,source=provider+' via vnstock 4.0.9',url='https://trading.vietcap.com.vn' if provider=='VCI' else 'https://kbs.com.vn',
                        retrieved_at=stamp,published_at=None,locator='Quote.history 1D; đơn vị/giá adjusted: https://www.vnstocks.com/docs/vnstock-data/du-lieu-giao-dich'))
                path.parent.mkdir(parents=True,exist_ok=True)
                temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
                return True
            except Exception as exc:
                # Provider exceptions may contain request headers; never log or persist them.
                attempts.append(dict(source=provider,status=type(exc).__name__))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.with_suffix('.status.json').write_text(json.dumps(dict(symbol=symbol,attempts=attempts),ensure_ascii=False,indent=2),encoding='utf-8')
    logging.getLogger(__name__).warning('Adjusted history unavailable ticker=%s; previous archive preserved',symbol)
    return False

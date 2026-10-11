"""Read-only market API probe. Never emit credentials, headers or response bodies."""
from datetime import datetime, timedelta
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dotenv import dotenv_values
from dnse import DnseClient
from stock_reports.core.config import Settings
from stock_reports.data_sources.dnse.market import VIETNAM, CompatibleDNSEMarketStream, parse_ohlc, parse_foreign_trading


async def probe_stream(settings):
    stream=CompatibleDNSEMarketStream(settings.dnse_api_key,settings.dnse_api_secret)
    try:
        await asyncio.wait_for(stream._connect(),timeout=10)
        await asyncio.wait_for(stream._authenticate(),timeout=10)
        return {'status':'authenticated','market_events_tested':False}
    except Exception as error:
        return {'status':'authentication_error' if type(error).__name__=='DnseStreamAuthError' else 'connection_error',
            'error_type':type(error).__name__}
    finally:
        if stream._ws:
            await stream._ws.close()


def probe():
    settings=Settings.from_root(ROOT)
    file_config=dotenv_values(ROOT/'.env')
    result={'checked_at':datetime.now(VIETNAM).isoformat(),
        'credentials_present':settings.dnse_configured,
        'environment_overrides':{name:bool(name in os.environ and os.environ[name]!=file_config.get(name))
            for name in ('DNSE_API_KEY','DNSE_API_SECRET')},
        'scope':'read-only market data; no accounts, orders, OTP or trading calls',
        'checks':[]}
    if not settings.dnse_configured:
        result['status']='missing_credentials'
        return result
    now=datetime.now(VIETNAM)
    session=now.replace(hour=0,minute=0,second=0,microsecond=0)
    while session.weekday()>=5:
        session-=timedelta(days=1)
    session_end=min(now,session+timedelta(hours=23,minutes=59))
    checks=[
        ('instruments','/market/instruments',{'securityGroupId':'ST','limit':2,'page':1}),
        ('daily_stock','/price/ohlc',{'type':'STOCK','symbol':'VCB','resolution':'1D','from':int((session-timedelta(days=30)).timestamp()),'to':int(now.timestamp())}),
        ('daily_index','/price/ohlc',{'type':'INDEX','symbol':'VNINDEX','resolution':'1D','from':int((session-timedelta(days=30)).timestamp()),'to':int(now.timestamp())}),
        ('minute_stock','/price/ohlc',{'type':'STOCK','symbol':'VCB','resolution':'1','from':int(session.timestamp()),'to':int(session_end.timestamp())}),
        ('foreign_trading','/price/VCB/foreign-trading',{'from':int(session.timestamp()),'to':int(session_end.timestamp())}),
    ]
    client=DnseClient(api_key=settings.dnse_api_key,api_secret=settings.dnse_api_secret,timeout=20)
    try:
        for dataset,path,params in checks:
            item={'dataset':dataset,'path':path,'query':params}
            try:
                response=client.get(path,params=params)
                item['http_status']=response.status_code
                if not response.is_success:
                    item['status']='access_denied' if response.status_code in (401,403) else 'http_error'
                else:
                    payload=response.json()
                    item['schema_keys']=sorted(payload) if isinstance(payload,dict) else []
                    if dataset=='instruments':
                        rows=payload.get('data');item['rows']=len(rows) if isinstance(rows,list) else 0
                        item['total']=payload.get('total')
                        item['status']='available' if item['rows'] else 'empty'
                    elif dataset=='foreign_trading':
                        rows=parse_foreign_trading(payload);item['rows']=len(rows)
                        item['status']='available' if rows else 'empty'
                    else:
                        rows,_=parse_ohlc(payload,symbol=params['symbol'],timeframe='1D' if params['resolution']=='1D' else '1m')
                        item['rows']=len(rows);item['status']='available' if rows else 'empty'
                        item['latest_source_time']=datetime.fromtimestamp(max(r['timestamp'] for r in rows),VIETNAM).isoformat() if rows else None
            except Exception as error:
                item['status']='error';item['error_type']=type(error).__name__
                status=getattr(error,'status_code',None)
                if status:
                    item['http_status']=status
                    if status in (401,403):item['status']='access_denied'
                try:
                    body=json.loads(getattr(error,'body','{}'))
                    item['provider_code']=body.get('code')
                    if body.get('code')=='OA-400':item['status']='authentication_error'
                    message=body.get('message') or body.get('error') or body.get('code')
                    if isinstance(message,str):
                        for secret in (settings.dnse_api_key,settings.dnse_api_secret):
                            message=message.replace(secret,'[REDACTED]')
                        item['provider_message']=message[:200]
                except (ValueError,AttributeError):
                    pass
                response=getattr(error,'response',None)
                if response is not None:
                    item['http_status']=response.status_code
                    if response.status_code in (401,403):item['status']='access_denied'
            result['checks'].append(item)
            print(json.dumps(item,ensure_ascii=False),flush=True)
            time.sleep(.6)
    finally:
        client.close()
    result['websocket']=asyncio.run(probe_stream(settings))
    result['status']='authentication_failed' if all(c['status']=='authentication_error' for c in result['checks']) else 'completed'
    return result


if __name__=='__main__':
    target=ROOT/'outputs/dnse_capabilities.json'
    result=probe()
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False,indent=2))
    print(f'Result: {target}')

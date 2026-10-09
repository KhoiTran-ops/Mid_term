"""Annual World Bank data, archived with observation dates and release metadata."""

from datetime import datetime, UTC
import json
import math
from pathlib import Path

import httpx

from stock_reports.data_sources.archive import ResponseArchive
from stock_reports.core.locking import ProcessLock


INDICATORS = {
    'NY.GDP.MKTP.KD.ZG': ('Tăng trưởng GDP thực','%/năm'),
    'FP.CPI.TOTL.ZG': ('Lạm phát CPI','%/năm'),
    'NE.TRD.GNFS.ZS': ('Thương mại hàng hóa và dịch vụ','% GDP'),
    'BX.KLT.DINV.WD.GD.ZS': ('FDI ròng vào','% GDP'),
}


def update_macro(settings):
    lock=ProcessLock(settings.root/'var/macro-collector.lock')
    if not lock.acquire():
        raise ValueError('Đang có một lượt cập nhật vĩ mô khác')
    try:
        return _update_macro(settings)
    finally:
        lock.release()


def _update_macro(settings):
    started = datetime.now(UTC)
    archive = ResponseArchive(settings.runs_directory / ('macro-'+started.strftime('%Y%m%dT%H%M%S%f')) / 'raw')
    observations,issues = [],[]
    with httpx.Client(timeout=30,follow_redirects=True) as client:
        for code,(label,unit) in INDICATORS.items():
            url=f'https://api.worldbank.org/v2/country/VNM/indicator/{code}'
            try:
                response=client.get(url,params={'format':'json','date':f'{started.year-11}:{started.year-1}','per_page':100})
                response.raise_for_status()
                archive.save('worldbank',str(response.url),response.content,'.json')
                payload=response.json()
                if not isinstance(payload,list) or len(payload)!=2 or not isinstance(payload[1],list):
                    raise ValueError('World Bank schema changed')
                series=[]
                for row in payload[1]:
                    if row.get('value') is not None and row.get('countryiso3code')=='VNM':
                        value=float(row['value'])
                        if not math.isfinite(value) or not started.year-11 <= int(row['date']) < started.year:
                            raise ValueError('Invalid indicator value/year')
                        series.append(dict(metric=code,label=label,unit=unit,period=str(row['date']),
                            value=value,provider_updated=payload[0].get('lastupdated'),
                            source=dict(source_name='World Bank WDI',url=str(response.url),retrieved_at=started.isoformat(),locator=f"{code}, Việt Nam, năm {row['date']}")))
                if not series:
                    raise ValueError('No observations for this indicator')
                observations.extend(series)
            except (httpx.HTTPError,ValueError,KeyError,TypeError) as error:
                issues.append(dict(metric=code,error_type=type(error).__name__))
    folder=settings.root/'var/macro'
    folder.mkdir(parents=True,exist_ok=True)
    previous=folder/'worldbank.json'
    # Preserve prior series on partial outages; replace only successful indicator series.
    if previous.exists():
        old=json.loads(previous.read_text(encoding='utf-8'))['observations']
        failed={i['metric'] for i in issues}
        observations.extend(r for r in old if r['metric'] in failed)
    result=dict(country='VNM',updated_at=started.isoformat(),observations=observations,issues=issues)
    temporary=folder/'worldbank.json.tmp'
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(previous)
    return dict(observations=len(observations),issues=issues,path=str(previous))

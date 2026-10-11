"""Archive ticker EOD history with explicit CafeF units for StockLens charts."""
import argparse
from datetime import datetime, UTC,timedelta
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from stock_reports.data_sources.archive import ArchivedCafeFTransport,ResponseArchive
from stock_reports.core.locking import ProcessLock
from stock_reports.data_sources.cafef.fundamentals import UNIT_SOURCE


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--symbols',nargs='+',required=True);args=parser.parse_args()
    lock=ProcessLock(ROOT/'var/cafef-collector.lock')
    if not lock.acquire():raise ValueError('CafeF collector is already running; no parallel refresh started')
    try:
        transport=ArchivedCafeFTransport(ResponseArchive(ROOT/'var/source_archive'),requests_per_second=1,retries=1,timeout_seconds=15)
        html=transport.get(UNIT_SOURCE).decode('utf-8')
        if not re.search(r'Giá\s*\(nghìn đồng\)',html):raise ValueError('CafeF price unit not confirmed')
        folder=ROOT/'var/stocklens_prices';folder.mkdir(parents=True,exist_ok=True)
        for ticker in args.symbols:
            if not re.fullmatch('[A-Z0-9]{2,12}',ticker):raise ValueError('Invalid ticker')
            rows=[];sources=[]
            for age in (0,365):
                # Endpoint uses US mm/dd/YYYY and a rolling year from EndDate;
                # StartDate alone does not extend it. Fetch two windows, then deduplicate.
                end=datetime.now()-timedelta(days=age);window_count=0
                for page in range(1,31):
                    url='https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx?'+urlencode(dict(Symbol=ticker,PageIndex=page,PageSize=20,StartDate='01/01/2023',EndDate=end.strftime('%m/%d/%Y')))
                    payload=json.loads(transport.get(url));data=payload.get('Data') or {};batch=data.get('Data')
                    if not isinstance(batch,list):raise ValueError('History response shape changed')
                    if not batch:break
                    rows.extend(batch);window_count+=len(batch);sources.append(dict(item='Lịch sử giá EOD '+ticker,source='CafeF EOD',url=url,
                        retrieved_at=datetime.now(UTC).isoformat(),published_at=None,locator='Giá nghìn đồng; khối lượng cổ phiếu; giá trị giao dịch tỷ đồng; tham số ngày mm/dd/YYYY'))
                    if window_count>=data.get('TotalCount',600):break
            rows=list({r['Ngay']:r for r in rows}.values())
            old=folder/f'{ticker}.json'
            if old.exists():
                previous=json.loads(old.read_text(encoding='utf-8'))
                if len(rows)<len(previous['rows']):raise ValueError('Refreshed history is shorter; preserve existing archive')
            snapshot=dict(symbol=ticker,retrieved_at=datetime.now(UTC).isoformat(),unit='thousand VND' if ticker!='VNINDEX' else 'index points',rows=rows,sources=sources,
                unit_source=dict(item='Đơn vị giá',source='CafeF đơn vị giá',url=UNIT_SOURCE,retrieved_at=datetime.now(UTC).isoformat(),published_at=None,locator='Giá (nghìn đồng) | Giá trị (tỷ đồng) | Khối lượng (cổ phiếu)'))
            tmp=folder/f'{ticker}.json.tmp';tmp.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(folder/f'{ticker}.json')
            print(json.dumps(dict(symbol=ticker,rows=len(rows))),flush=True)
    finally:lock.release()


if __name__=='__main__':main()

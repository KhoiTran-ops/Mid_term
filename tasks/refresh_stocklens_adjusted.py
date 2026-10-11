"""Archive actual adjusted daily bars; do not apply unverified corporate-action ratios."""
import argparse
from datetime import datetime,UTC,timedelta,date
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbols',nargs='+',required=True)
    p.add_argument('--as-of',type=date.fromisoformat,default=date.today())
    args=p.parse_args()
    from vnstock import Quote
    for symbol in args.symbols:
        if not re.fullmatch('[A-Z0-9]{2,12}',symbol):raise ValueError('Invalid ticker')
        df=Quote(symbol=symbol,source='VCI').history(start=(args.as_of-timedelta(days=800)).isoformat(),end=args.as_of.isoformat(),interval='1D')
        rows=json.loads(df.to_json(orient='records',date_format='iso'))
        if not rows:raise ValueError('Empty adjusted history; keep existing archive')
        stamp=datetime.now(UTC).isoformat()
        payload=dict(symbol=symbol,unit='index points' if symbol=='VNINDEX' else 'thousand VND',adjusted=True,
            volume_basis='provider total; do not assume split-adjusted',retrieved_at=stamp,rows=rows,
            source=dict(item='Giá điều chỉnh '+symbol,source='VCI via vnstock 4.0.9',url='https://trading.vietcap.com.vn',
                retrieved_at=stamp,published_at=None,locator='Quote.history 1D; adjusted price and thousand VND documented: https://www.vnstocks.com/docs/vnstock-data/du-lieu-giao-dich'))
        folder=ROOT/'var/stocklens_adjusted_prices';folder.mkdir(parents=True,exist_ok=True)
        tmp=folder/f'{symbol}.json.tmp';tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(folder/f'{symbol}.json')
        print(json.dumps(dict(symbol=symbol,rows=len(rows),last_date=rows[-1]['time'][:10])))


if __name__=='__main__':main()

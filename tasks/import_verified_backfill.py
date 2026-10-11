"""Import manually reviewed issuer tables only where structured source is blank."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.core.config import Settings
from stock_reports.storage.market import MarketStore
from stock_reports.analysis.financials import parse_period
from stock_reports.data_sources.cafef.parsers import parse_financial_number


def import_backfill(store,path):
    payload=json.loads(path.read_text(encoding='utf-8'))
    if payload['currency']!='VND' or payload['money_multiplier']<=0 or not payload['verification']:
        raise ValueError('Missing verified currency/unit/review')
    selected=list(payload['periods']);prepared=[]
    for index,p in enumerate(selected):
        info=payload['periods'][p];pdf=(ROOT/info['pdf']).resolve()
        if not pdf.is_relative_to(ROOT/'var/issuer_disclosures'):
            raise ValueError('Source PDF outside issuer archive')
        if hashlib.sha256(pdf.read_bytes()).hexdigest()!=info['sha256']:
            raise ValueError('Source PDF checksum mismatch')
        year,quarter=parse_period(p)
        rows=[]
        for order,row in enumerate(payload['rows']):
            raw=row[index+1];number=parse_financial_number(raw)
            rows.append(dict(row_order=order,item_name=row[0],values={(year,quarter):
                (raw+' [triệu VND, BCTC gốc]',number*payload['money_multiplier'] if number is not None else None)}))
        with store._connect() as db:
            existing=db.execute('SELECT row_order,item_name,value_raw,value_numeric,source FROM financial_facts '
                'WHERE symbol=? AND statement_type=? AND fiscal_year=? AND fiscal_quarter=? AND value_numeric IS NOT NULL',
                (payload['symbol'],payload['statement_type'],year,quarter)).fetchall()
        if existing and any(r[4]!=info['url'] for r in existing):
            raise ValueError('Refusing to overwrite existing numeric data; resolve source conflict first')
        prepared.append((info,rows))
    count=0
    for info,rows in prepared:
        count+=store.replace_financial_facts(payload['symbol'],payload['statement_type'],rows,source=info['url'])
    return dict(symbol=payload['symbol'],saved=count,periods=selected,source='issuer PDF manually reviewed')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('path',type=Path);args=parser.parse_args()
    settings=Settings.from_root(ROOT);store=MarketStore(settings.market_database);store.initialize()
    print(json.dumps(import_backfill(store,args.path),ensure_ascii=False))


if __name__=='__main__':main()

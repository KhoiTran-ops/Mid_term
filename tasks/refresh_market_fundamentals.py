"""Refresh provider fundamentals for existing reports or the whole catalog."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from stock_reports.core.config import Settings
from stock_reports.data_sources.cafef.fundamentals import refresh

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--symbols',nargs='+');parser.add_argument('--all',action='store_true');args=parser.parse_args()
    settings=Settings.from_root(ROOT)
    with sqlite3.connect(settings.industries_database if args.all else settings.reports_database) as db:
        symbols=args.symbols or [r[0] for r in db.execute('SELECT symbol FROM companies ORDER BY symbol' if args.all else "SELECT DISTINCT symbol FROM reports WHERE kind='stock' AND symbol IS NOT NULL ORDER BY symbol")]
    print(json.dumps(refresh(settings,symbols),ensure_ascii=False))

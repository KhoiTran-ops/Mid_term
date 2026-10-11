import sqlite3

from stock_reports.data_sources.cafef.annual import sync_annual_financials
from stock_reports.data_sources.cafef.parsers import parse_annual_financial_statement, parse_financial_number
from stock_reports.data_sources.cafef.sync import sync_financial_history
from stock_reports.storage.market import MarketStore
from stock_reports.analysis.financials import normalized_name


def annual_html(year):
    cols=''.join(f'<td>{y}</td>' for y in range(year-3,year+1))
    return f'<table id="tblGridData"><tr><td>Chỉ tiêu</td>{cols}<td>Tăng trưởng</td></tr></table>' + (
        '<table id="tableContent"><tr><td>1. Chi tiết</td><td>1.000</td><td>-</td>'
        '<td>(2.000)</td><td>0</td><td>200</td></tr></table>')


def test_annual_parser_never_confuses_q4_or_growth_and_preserves_null_zero():
    facts=parse_annual_financial_statement(annual_html(2025))
    assert facts[0]['values']=={2022:('1.000',1000),2023:('-',None),2024:('(2.000)',-2000),2025:('0',0)}
    assert parse_annual_financial_statement('<table id="tblGridData"><tr><td>Quý 4-2025</td></tr></table>')==[]
    assert parse_financial_number('1.234,56')==1234.56
    assert normalized_name('B - VỐN CHỦ SỞ HỮU')=='von chu so huu'
    assert parse_financial_number('9'*400) is None


def test_annual_refresh_fetches_2021_2025_and_keeps_statement_provenance(tmp_path):
    store=MarketStore(tmp_path/'data.db');store.initialize()
    class Client:
        def get_annual_financial_html(self,symbol,statement,year):return annual_html(year)
    result=sync_annual_financials(Client(),store,'VCB')
    # The null 2023 column is supplied by the overlapping 2024 window.
    assert result['statement_years']['BSheet']==[2021,2022,2023,2024,2025]
    with sqlite3.connect(store.path) as db:
        rows=db.execute('SELECT fiscal_year,value_numeric,source_url,response_sha256 FROM annual_statement_facts '
                        "WHERE statement_type='BSheet' ORDER BY fiscal_year").fetchall()
    assert [r[0] for r in rows]==[2021,2022,2023,2024,2025]
    assert rows[2][1]==-2000
    assert rows[1][1]==1000  # retry windows do not overwrite already fetched years
    assert all('quarter=0' in r[2] and 'showtype=1' in r[2] and len(r[3])==64 for r in rows)
    old=store.replace_annual_statement('VCB','BSheet',[dict(row_order=0,item_name='Empty',values={2025:('',None)})],
        source_url='blank',response_sha256='blank')
    assert old==0
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT value_numeric FROM annual_statement_facts WHERE statement_type='BSheet' AND fiscal_year=2025").fetchone()==(0,)


def test_oldest_year_is_retrieved_from_overlapping_window_not_a_dead_own_year_route(tmp_path):
    store=MarketStore(tmp_path/'data.db');store.initialize();calls=[]
    class Client:
        def get_annual_financial_html(self,symbol,statement,year):
            calls.append(year)
            assert year!=2021, '2021 route unavailable; 2024 has the same published annual column'
            return annual_html(year).replace('<td>-</td>','<td>123</td>')
    result=sync_annual_financials(Client(),store,'FPT')
    assert result['statement_years']['BSheet']==[2021,2022,2023,2024,2025]
    assert 2024 in calls


def test_incremental_annual_refresh_skips_numeric_cached_years(tmp_path):
    store=MarketStore(tmp_path/'data.db');store.initialize()
    class Client:
        def get_annual_financial_html(self,symbol,statement,year):
            return annual_html(year).replace('<td>-</td>','<td>123</td>')
    sync_annual_financials(Client(),store,'FPT')
    class NoRequests:
        def get_annual_financial_html(self,*args):raise AssertionError('cached year requested')
    result=sync_annual_financials(NoRequests(),store,'FPT',incremental=True)
    assert result['requests']==0
    assert result['missing_years']=={'BSheet':[],'IncSta':[],'CashFlow':[]}


def test_blank_quarter_refresh_preserves_existing_numeric_and_is_not_complete(tmp_path):
    store=MarketStore(tmp_path/'data.db');store.initialize()
    store.replace_financial_facts('VCB','BSheet',[dict(row_order=0,item_name='Asset',values={(2025,1):('100',100)})],source='good')
    store.replace_financial_facts('VCB','BSheet',[dict(row_order=0,item_name='Asset',values={(2025,1):('',None),(2025,2):('',None)})],source='blank')
    assert store.financial_statement_periods('VCB','BSheet')=={(2025,1)}
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT value_numeric,source FROM financial_facts WHERE fiscal_quarter=1").fetchone()==(100,'good')


def test_partial_quarter_window_retries_empty_older_periods(tmp_path):
    store=MarketStore(tmp_path/'data.db');store.initialize()
    class Client:
        def get_financial_summary(self,symbol,*,page):
            return dict(isSuccess=True,value=dict(count=2,data=[dict(data=[dict(symbol=symbol,year=2025,quater=q,type='HK',content='') for q in (2,1)])]))
        def get_financial_html(self,symbol,statement,year,quarter):
            values='<td></td><td>200</td>' if quarter==2 else '<td>100</td><td></td>'
            return ('<table id="tblGridData"><tr><td>X</td><td>Quý 1-2025</td><td>Quý 2-2025</td></tr></table>'
                    f'<table id="tableContent"><tr><td>Asset</td>{values}</tr></table>')
    sync_financial_history(Client(),store,symbols=['VCB'],max_quarters=2)
    assert store.financial_statement_periods('VCB','BSheet')=={(2025,1),(2025,2)}

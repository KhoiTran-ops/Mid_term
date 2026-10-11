from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from fastapi.testclient import TestClient

from stock_reports.analysis.contracts import AnalysisSection, Finding, ReportBlock, SectionKind
from stock_reports.analysis.financials import FinancialData, FinancialReview
from stock_reports.analysis.valuation import Scenarios, evaluate_scenarios
from stock_reports.core.config import Settings
from stock_reports.pipeline.research_reports import GenerationRequest, generate_reports, report_analysis
from stock_reports.reports.documents import ReportDocument
from stock_reports.storage.reports import ReportCatalog
from stock_reports.web.app import create_app
from tests.test_research_financials import SOURCE


def scenarios(method='pb'):
    return Scenarios(method=method,horizon_months=12,cases=[dict(name=n,multiple=m,growth='0.1',rationale='Giả định kiểm thử có giải thích') for n,m in [('bear',1),('base',2),('bull',3)]])


def review():
    return FinancialReview(symbol='SSI',periods=['2026Q2'],scope='consolidated',currency='VND',money_multiplier=1,
        income_basis='quarter',source=SOURCE,notes_reviewed=True,price_multiplier=1000,
        shares_outstanding=100,parent_equity_vnd=1000000,eps_ttm_vnd=2000)


def test_report_does_not_start_competing_financial_collector(tmp_path,monkeypatch):
    from stock_reports.core.locking import ProcessLock
    from stock_reports.storage.market import MarketStore
    from stock_reports.data_sources.dnse.market import DNSEInstrument
    from stock_reports.pipeline.research_reports import ensure_financials
    settings=Settings.from_root(tmp_path)
    store=MarketStore(settings.market_database); store.initialize()
    store.replace_instruments([DNSEInstrument('VCB','HOSE','',1)],source='test')
    lock=ProcessLock(tmp_path/'var/cafef-collector.lock')
    assert lock.acquire()
    monkeypatch.setattr('stock_reports.pipeline.research_reports.sync_financial_history',
        lambda *a,**kw:pytest.fail('Concurrent collector must not be called'))
    try:
        with pytest.raises(ValueError,match='Đang tải lại BCTC'):
            ensure_financials(settings,['VCB'])
        store.replace_financial_facts('VCB','BSheet',[
            {'row_order':0,'item_name':'Tổng tài sản có','values':{(2026,2):('100',100)}}
        ],source=str(SOURCE.url))
        assert ensure_financials(settings,['VCB']) is None
    finally:
        lock.release()


def test_pb_has_consistent_currency_dilution_and_requires_notes():
    data=FinancialData('SSI',[(2026,2)],{},review(),[])
    result=evaluate_scenarios(data,'securities',20,scenarios())
    assert result['current']==20000
    base=next(r for r in result['rows'] if r['name']=='base')
    assert base['target']==22000 and base['upside']==10
    assert result['assessment']=='TRUNG LẬP'
    snapshot=evaluate_scenarios(data,'securities',20,None)
    assert {m['label'] for m in snapshot['metrics']}=={'Giá tham chiếu chuẩn hóa','P/B hiện tại','BVPS hiện tại','P/E hiện tại','EPS TTM'}
    assert snapshot['rows']==[] and snapshot['current']==20000
    data.review=data.review.model_copy(update={'notes_reviewed':False})
    unchecked=evaluate_scenarios(data,'securities',20,scenarios())
    assert unchecked['assessment']=='Chưa đủ cơ sở khuyến nghị' and 'Thuyết minh' in unchecked['reason']
    cases=scenarios().model_dump()
    cases['cases'][1]['forecast_shares']=200
    assert evaluate_scenarios(data,'securities',20,Scenarios.model_validate(cases))['rows'][1]['target']==11000


def test_missing_units_and_wrong_business_model_block_targets():
    data=FinancialData('SSI',[(2026,2)],{},None,[])
    assert evaluate_scenarios(data,'securities',20,scenarios())['rows']==[]
    data.review=review()
    with pytest.raises(ValueError,match='P/B'):
        evaluate_scenarios(data,'securities',20,scenarios('pe'))
    data.review=data.review.model_copy(update={'shares_outstanding':None})
    assert evaluate_scenarios(data,'securities',20,scenarios())['rows']==[]
    data.review=review().model_copy(update={'eps_ttm_vnd':Decimal('-10')})
    assert evaluate_scenarios(data,'manufacturing',20,scenarios('pe'))['rows']==[]


def test_scenario_duplicates_nonfinite_values_and_future_dates_rejected():
    data=scenarios().model_dump()
    data['cases'][1]['name']='bear'
    with pytest.raises(ValidationError):Scenarios.model_validate(data)
    with pytest.raises(ValidationError):ReportBlock(kind='chart',title='X',labels=['a'],values=[float('nan')])
    with pytest.raises(ValidationError):GenerationRequest(kind='macro',as_of=date(2999,1,1))
    with pytest.raises(ValidationError):GenerationRequest(kind='stock',symbol='../.env')


def macro_document():
    return ReportDocument(kind='macro',title='Tổng quan vĩ mô Việt Nam',as_of=date(2026,10,9),
        sections=(AnalysisSection(kind=SectionKind.MACRO,title='Vĩ mô',findings=(Finding(text='Tăng trưởng cần đối chiếu dữ liệu.',is_assumption=True),),
            blocks=(ReportBlock(kind='chart',title='Chuỗi có khoảng trống',labels=('2023','2024','2025'),values=(1,None,2)),)),
            AnalysisSection(kind=SectionKind.RISKS,title='Rủi ro',findings=(Finding(text='Thiếu chuỗi tháng hiện tại.',is_assumption=True),))))


def test_pdf_publication_reuses_identical_analysis_and_records_provenance(tmp_path,monkeypatch):
    settings=Settings.from_root(tmp_path)
    monkeypatch.setattr('stock_reports.pipeline.research_reports.build_document',lambda *a,**k:macro_document())
    monkeypatch.setattr('stock_reports.pipeline.research_reports.ResearchRepository.macro',lambda self:[])
    monkeypatch.setattr('stock_reports.pipeline.research_reports.ResearchRepository.snapshots',lambda self:[])
    request=GenerationRequest(kind='macro')
    first=generate_reports(settings,request)[0]
    second=generate_reports(settings,request)[0]
    assert second['reused'] and first['report']['id']==second['report']['id']
    catalog=ReportCatalog(settings.reports_database,settings.reports_directory)
    assert catalog.list_reports().total==1
    payload=report_analysis(settings,first['report']['id'],catalog)
    assert payload['document']['kind']=='macro' and payload['inputs']['macro']==[]
    reader=PdfReader(catalog.pdf_path(first['report']['id']))
    text=''.join(page.extract_text() for page in reader.pages)
    assert 'Tổng quan vĩ mô Việt Nam' in text and 'Rủi ro' in text and 'Trang 1' in text
    assert payload['page_count']==len(reader.pages)
    assert any('/FontFile2' in font.get_object().get('/FontDescriptor',{}).get_object() for page in reader.pages for font in page['/Resources']['/Font'].values() if font.get_object().get('/FontDescriptor'))


def test_generation_recovers_missing_analysis_without_duplicate_pdf(tmp_path,monkeypatch):
    settings=Settings.from_root(tmp_path)
    monkeypatch.setattr('stock_reports.pipeline.research_reports.build_document',lambda *a,**k:macro_document())
    monkeypatch.setattr('stock_reports.pipeline.research_reports.ResearchRepository.macro',lambda self:[])
    monkeypatch.setattr('stock_reports.pipeline.research_reports.ResearchRepository.snapshots',lambda self:[])
    request=GenerationRequest(kind='macro')
    first=generate_reports(settings,request)[0]
    (settings.outputs_directory/'analysis'/f"{first['report']['id']}.json").unlink()
    second=generate_reports(settings,request)[0]
    assert second['reused'] and second['report']['id']==first['report']['id']
    assert ReportCatalog(settings.reports_database,settings.reports_directory).list_reports().total==1
    assert report_analysis(settings,first['report']['id']) is not None


def test_four_macro_charts_are_split_two_per_page_and_formula_version_is_current(tmp_path):
    from stock_reports.reports.render import ResearchPdfRenderer
    from stock_reports.analysis.financials import FORMULA_VERSION
    doc=ReportDocument(kind='industry',title='Ngân hàng',industry_id='ngan-hang',industry_name='Ngân hàng',as_of=date(2026,10,9),
        sections=(AnalysisSection(kind=SectionKind.INDUSTRY,title='Ngành',findings=(Finding(text='Dữ liệu thử ngành',is_assumption=True),)),
            AnalysisSection(kind=SectionKind.MACRO,title='Vĩ mô',findings=(Finding(text='Dữ liệu thử biểu đồ',is_assumption=True),),blocks=tuple(
            ReportBlock(kind='chart',title=f'CHART_{i}',labels=('2024','2025'),values=(1,2))
                for i in range(4))),
            AnalysisSection(kind=SectionKind.RISKS,title='Rủi ro',findings=(Finding(text='Dữ liệu thử rủi ro',is_assumption=True),))))
    path=ResearchPdfRenderer().render(doc,tmp_path/'report.pdf')
    texts=[p.extract_text() for p in PdfReader(path).pages]
    chart_pages=[t for t in texts if 'CHART_' in t]
    assert len(chart_pages)==2
    assert all(sum(f'CHART_{i}' in t for i in range(4))==2 for t in chart_pages)
    assert FORMULA_VERSION in ''.join(texts)


def test_local_web_generation_rejects_foreign_origin_and_reports_errors(tmp_path,monkeypatch):
    monkeypatch.setenv('NEWS_AUTO_UPDATE','false')
    settings=Settings.from_root(tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.post('/api/report-jobs',json={'kind':'macro'},headers={'Origin':'https://evil.example'}).status_code==403
        assert client.post('/api/report-jobs',json={'kind':'stock'}).status_code==422
        assert client.get('/api/report-jobs/missing').status_code==404
        assert client.get('/reports/not-a-uuid').status_code==404
        assert client.get('/outputs/analysis/a.json').status_code==404
        assert client.get('/',headers={'host':'evil.example'}).status_code==400


def test_repository_freezes_source_rows_while_collectors_continue(tmp_path):
    import sqlite3
    from stock_reports.analysis.repository import ResearchRepository
    settings=Settings.from_root(tmp_path)
    settings.market_database.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(settings.market_database) as db:
        db.execute('CREATE TABLE sample (value INTEGER)')
        db.execute('INSERT INTO sample VALUES (1)')
    repo=ResearchRepository(settings,date(2026,10,9))
    first=repo.read(settings.market_database,'SELECT * FROM sample')
    first[0]['value']=999
    with sqlite3.connect(settings.market_database) as db:
        db.execute('UPDATE sample SET value=2')
    assert repo.read(settings.market_database,'SELECT * FROM sample')==[{'value':1}]
    assert ResearchRepository(settings,date(2026,10,9)).read(settings.market_database,'SELECT * FROM sample')==[{'value':2}]


def test_macro_partial_failure_preserves_old_series_without_partial_invalid_rows(tmp_path,monkeypatch):
    import httpx,json
    from stock_reports.pipeline.macro_data import update_macro, INDICATORS
    settings=Settings.from_root(tmp_path)
    folder=tmp_path/'var/macro';folder.mkdir(parents=True)
    old=[dict(metric=code,period='2024',value=5,source={}) for code in list(INDICATORS)[:2]]
    (folder/'worldbank.json').write_text(json.dumps({'observations':old}),encoding='utf-8')
    def respond(request):
        code=request.url.path.rsplit('/',1)[-1]
        if code=='NY.GDP.MKTP.KD.ZG':return httpx.Response(503)
        rows=[dict(value=2,countryiso3code='VNM',date='2025')]
        if code=='FP.CPI.TOTL.ZG':rows.append(dict(value=float('nan'),countryiso3code='VNM',date='2025'))
        return httpx.Response(200,text=json.dumps([{'lastupdated':'2026-09-01'},rows]))
    original=httpx.Client
    monkeypatch.setattr('stock_reports.pipeline.macro_data.httpx.Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    result=update_macro(settings)
    saved=json.loads((folder/'worldbank.json').read_text(encoding='utf-8'))
    assert len(result['issues'])==2 and result['observations']==4
    assert [r for r in saved['observations'] if r['metric'] in {old[0]['metric'],old[1]['metric']}]==old


def test_repository_uses_cafef_eod_when_dnse_daily_bars_are_missing(tmp_path):
    from stock_reports.analysis.repository import ResearchRepository
    from stock_reports.storage.market import MarketStore
    settings=Settings.from_root(tmp_path)
    store=MarketStore(settings.market_database);store.initialize()
    store.upsert_eod_rows('HOSE',[dict(Symbol='FPT',Ngay='09/10/2026',
        GiaMoCua=100,GiaCaoNhat=105,GiaThapNhat=99,GiaDongCua=104,
        KhoiLuongKhopLenh=1234)],source='cafef')

    repo=ResearchRepository(settings,date(2026,10,9))
    rows=repo.bars('FPT')

    assert rows[0]['close']==104 and rows[0]['trade_date']=='2026-10-09'
    assert repo.price_source('FPT',rows).source_name=='CafeF EOD'

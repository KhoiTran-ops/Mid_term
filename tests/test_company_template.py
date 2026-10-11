from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from stock_reports.analysis.financials import FinancialData,Fact
from stock_reports.analysis.company_template import CompanyFact,composition_chart,compress_warnings,build_company_document
from stock_reports.analysis.valuation import Scenarios,Sensitivity,calculate_method,evaluate_scenarios,Scenario
from stock_reports.reports.company import render_company
from stock_reports.core.config import Settings
from tests.test_research_reports import review,scenarios
from tests.test_research_financials import SOURCE


def justified(base_roe='.24',**extras):
    return Scenarios(method='justified_pb',horizon_months=12,cases=[dict(name=n,sustainable_roe=r,
        ke='.12',terminal_growth='.02',forecast_bvps_vnd=10000,
        rationale='Giả định kiểm thử, không phải dự báo thật',**extras)
        for n,r in [('bear','.08'),('base',base_roe),('bull','.30')]])


@pytest.mark.parametrize('roe,assessment',[('.25','KHẢ QUAN'),('.24','TRUNG LẬP'),('.20','KÉM KHẢ QUAN')])
def test_fair_bank_pb_reverse_check_and_exact_recommendation_thresholds(roe,assessment):
    data=FinancialData('SSI',[(2026,2)],{},review(),[])
    value=evaluate_scenarios(data,'banking',20,justified(roe))
    assert value['assessment']==assessment and value['target'] is not None
    assert value['methods'][0]['target_implied_roe']==Decimal(roe)
    assert value['methods'][0]['implied_roe']==Decimal('.22')
    assert value['rows'][0]['target']<value['current']


def test_unchecked_discretionary_bank_multiple_cannot_be_published():
    data=FinancialData('SSI',[(2026,2)],{},review(),[])
    value=evaluate_scenarios(data,'banking',20,scenarios())
    assert value['rows'] and value['target'] is None
    assert value['assessment']=='Chưa đủ cơ sở khuyến nghị'
    assert 'đảo ngược' in value['reason']


def test_fcff_fcfe_nav_currency_terminal_value_and_explicit_zero_inputs():
    case=Scenario(name='base',rationale='Dòng tiền giả định dùng cho kiểm thử',wacc='.10',ke='.12',
        terminal_growth='.02',cash_vnd=30,debt_vnd=20,
        projections=[dict(year=y,discount_years=t,fcff_vnd=f,fcfe_vnd=e,rationale='Số giả lập cho kiểm thử')
                     for y,t,f,e in [(2027,1,100,50),(2028,2,110,60)]])
    value=calculate_method('fcff',case,review())
    expected=(Decimal(100)/Decimal('1.10')+Decimal(110)/Decimal('1.10')**2+
        Decimal(110)*Decimal('1.02')/Decimal('.08')/Decimal('1.10')**2+30-20)/100
    assert value['target']==expected
    assert calculate_method('fcfe',case,review())['target']==(
        Decimal(50)/Decimal('1.12')+Decimal(60)/Decimal('1.12')**2+
        Decimal(60)*Decimal('1.02')/Decimal('.10')/Decimal('1.12')**2)/100
    with pytest.raises(ValueError,match='nhập rõ'):
        calculate_method('fcff',case.model_copy(update={'cash_vnd':None}),review())
    assert calculate_method('fcff',case.model_copy(update={'cash_vnd':Decimal(0),'debt_vnd':Decimal(0)}),review())['target']>0
    with pytest.raises(ValueError,match='lớn hơn g'):
        calculate_method('fcff',case.model_copy(update={'wacc':Decimal('.02')}),review())
    nav=Scenario(name='base',rationale='Tài sản dự án giả lập cho kiểm thử',nav_liabilities_vnd=100,
        nav_assets=[dict(name='A',value_vnd=1000,ownership='.5',rationale='Giả định kiểm thử có giải thích')])
    assert calculate_method('nav',nav,review())['target']==4


def test_missing_ordered_downside_horizon_and_share_checks_block_issuance():
    data=FinancialData('SSI',[(2026,2)],{},review(),[])
    cfg=justified().model_dump()
    cfg['cases'][0]['sustainable_roe']=Decimal('.40')
    value=evaluate_scenarios(data,'banking',20,Scenarios.model_validate(cfg))
    assert value['target'] is None and 'Bi quan' in value['reason']
    cfg=justified().model_copy(update={'horizon_months':24})
    assert evaluate_scenarios(data,'banking',20,cfg)['target'] is None
    data.review=review().model_copy(update={'shares_outstanding':None})
    value=evaluate_scenarios(data,'banking',20,justified())
    assert value['target'] is None and not value['checks'][0]['passed']


def test_explicit_sensitivity_probability_weight_and_capm_validation():
    data=FinancialData('SSI',[(2026,2)],{},review(),[])
    cfg=justified().model_copy(update={'sensitivity':Sensitivity(row_variable='roe',row_values=['.20','.24','.28'],
        column_variable='ke',column_values=['.10','.12','.14'],rationale='Trục nhập riêng cho kiểm thử')})
    result=evaluate_scenarios(data,'banking',20,cfg)
    assert len(result['sensitivity'])==3 and result['sensitivity'][1]['values'][1]==result['methods'][0]['target']
    assert evaluate_scenarios(data,'banking',20,justified())['sensitivity']==[]
    with pytest.raises(ValidationError,match='Xác suất'):
        Scenario(name='base',probability='.5',rationale='Giả định chưa có căn cứ xác suất')
    with pytest.raises(ValidationError,match='Trọng số'):
        Scenario(name='base',rationale='Giả định tổng hợp kiểm thử',components=[dict(method='pb',weight='.5',multiple=1,
            growth=0,rationale='Giả định thành phần kiểm thử')])
    case=Scenario(name='base',ke='.20',risk_free_rate='.04',market_risk_premium='.08',beta=1,
        sustainable_roe='.24',terminal_growth='.02',forecast_bvps_vnd=10000,rationale='CAPM không khớp dùng cho kiểm thử')
    with pytest.raises(ValueError,match='CAPM'):calculate_method('justified_pb',case,review())
    with pytest.raises(ValidationError,match='liên tiếp'):
        Scenario(name='base',rationale='Dự phóng kiểm thử có khoảng trống',projections=[
            dict(year=y,rationale='Giả định kiểm thử có giải thích') for y in (2027,2029)])


def test_warning_grouping_preserves_all_periods_without_duplicate_rows():
    result=compress_warnings(['Cho vay 2026Q2: ánh xạ không duy nhất.',
        'Cho vay 2026Q1: ánh xạ không duy nhất.','Đơn vị chưa kiểm chứng.'])
    assert len(result)==2 and '2026Q2, 2026Q1' in result[1]


def test_composition_chart_requires_complete_percentages_same_period_and_sources():
    facts=[CompanyFact(category='shareholders',label=name,value=str(v)+'%',numeric=v,unit='%',period='2026Q2',source=SOURCE)
        for name,v in [('Cổ đông A',60),('Cổ đông B',40)]]
    pie=composition_chart(facts,'shareholders','Cơ cấu đã công bố')
    assert pie.chart_type=='pie' and sum(pie.values)==100
    assert composition_chart(facts[:1],'shareholders','Cơ cấu thiếu') is None
    assert composition_chart([facts[0],facts[1].model_copy(update={'period':'2025Q2'})],'shareholders','Khác kỳ') is None
    assert composition_chart([facts[0],facts[1].model_copy(update={'numeric':Decimal(20)})],'shareholders','Thiếu phần còn lại') is None


def test_weighted_method_result_uses_only_supplied_weights_and_no_growth_default():
    cases=[]
    for name,pb,pe in [('bear',1,2),('base',2,4),('bull',3,6)]:
        cases.append(dict(name=name,rationale='Trọng số chỉ có trong dữ liệu kiểm thử',components=[
            dict(method='pb',weight='.25',multiple=pb,growth=0,rationale='Bội số PB giả lập có giải thích'),
            dict(method='pe',weight='.75',multiple=pe,growth=0,rationale='Bội số PE giả lập có giải thích')]))
    data=FinancialData('SSI',[(2026,2)],{},review(),[])
    value=evaluate_scenarios(data,'manufacturing',20,Scenarios(method='blended',horizon_months=12,cases=cases))
    assert value['rows'][1]['target']==Decimal(20000)*Decimal('.25')+Decimal(8000)*Decimal('.75')
    assert len(value['methods'])==2
    missing=scenarios().model_dump();missing['cases'][0]['growth']=None
    assert evaluate_scenarios(data,'securities',20,Scenarios.model_validate(missing))['rows']==[]


def test_dcf_without_explicit_discount_time_is_blocked():
    case=Scenario(name='base',rationale='Không được tự mặc định kỳ chiết khấu',wacc='.1',terminal_growth='.02',
        cash_vnd=0,debt_vnd=0,projections=[dict(year=2027,fcff_vnd=100,rationale='Dòng tiền giả lập để kiểm thử')])
    with pytest.raises(ValueError,match='thời điểm chiết khấu'):calculate_method('fcff',case,review())


class CompanyRepo:
    def __init__(self,settings):
        from stock_reports.analysis.repository import ResearchRepository
        self.settings=settings;self.as_of=date(2026,10,9)
        self.cutoff=ResearchRepository(settings,self.as_of).cutoff
    def annual(self,symbol):return []
    def snapshots(self):return []
    def companies(self,industry):return []
    def macro(self):return []
    def news(self,**kwargs):return []
    def bars(self,symbol):return []
    def industry_source(self,industry):return SOURCE


def test_complete_template_pdf_without_unverified_targets_or_unreplaced_placeholders(tmp_path):
    settings=Settings.from_root(tmp_path);repo=CompanyRepo(settings)
    p=(2026,2)
    data=FinancialData('VCB',[p,(2026,1)],{key:{p:Fact(Decimal(v),SOURCE,key)} for key,v in
        dict(assets=100,equity=20,liabilities=80,revenue=10,net_profit=2,loans_gross=50,deposits=40).items()},None,[])
    company=dict(company_name='Ngân hàng thử nghiệm',exchange='HOSE',source_url=str(SOURCE.url),
        retrieved_at=SOURCE.retrieved_at,industry=dict(name='Ngân hàng',sector_id='12',slug='ngan-hang'))
    value=evaluate_scenarios(data,'banking',None,None)
    doc=build_company_document(settings,repo,company,data,'banking',[],[],value,None,[])
    assert len(doc.sections)==11 and doc.template_version
    pdf=render_company(doc,tmp_path/'company.pdf')
    texts=[p.extract_text() for p in PdfReader(pdf).pages]
    text='\n'.join(texts)
    for roman in ('I. TỔNG QUAN','II. CẬP NHẬT','III. PHÂN TÍCH','IV. PHÂN TÍCH',
                  'V. TRIỂN VỌNG','VI. RỦI RO','VII. ĐỊNH GIÁ','VIII. PHỤ LỤC'):
        assert roman in text
    for i in range(1,11):assert f'7.{i}.' in text
    assert 'Chưa đủ cơ sở khuyến nghị' in text and 'Chưa đủ dữ liệu' in text
    assert '[giá]' not in text and 'None' not in text and 'Khuyến nghị [1]' not in text
    assert all(cell!='Thiếu' for part in doc.sections for b in part.blocks for row in b.rows for cell in row)
    assert '>= +15%' in text and '<= -10%' in text
    assert all(len(t)>200 for t in texts)


def test_filled_dcf_and_two_composition_charts_render_without_fake_sources(tmp_path,monkeypatch):
    settings=Settings.from_root(tmp_path);repo=CompanyRepo(settings)
    facts=[]
    for category,dimension in [('shareholders',None),('segments','product'),('segments','market')]:
        facts.extend(CompanyFact(category=category,dimension=dimension,label=name,value=str(number)+'%',
            numeric=number,unit='%',period='2026Q2',source=SOURCE) for name,number in [('A',60),('B',40)])
    monkeypatch.setattr('stock_reports.analysis.company_template.load_supplement',lambda *args:facts)
    cases=[]
    for name,factor in [('bear',Decimal('.5')),('base',Decimal(1)),('bull',Decimal('1.5'))]:
        components=[]
        for method in ('fcff','fcfe'):
            components.append(dict(method=method,weight='.5',rationale='Giả định kiểm thử, không dùng cho mã thực',
                wacc='.10',ke='.12',terminal_growth='.02',cash_vnd=0,debt_vnd=0,
                projections=[dict(year=2026+i,discount_years=i,fcff_vnd=Decimal(1000000)*factor,
                    fcfe_vnd=Decimal(500000)*factor,rationale='Dòng tiền giả lập dùng trong kiểm thử') for i in (1,2)]))
        cases.append(dict(name=name,rationale='Kịch bản giả lập để kiểm tra xuất PDF',components=components))
    cfg=Scenarios(method='blended',horizon_months=12,cases=cases)
    p=(2026,2)
    data=FinancialData('SSI',[p],{key:{p:Fact(Decimal(v),SOURCE,key)} for key,v in
        dict(assets=100,equity=20,liabilities=80,revenue=10,net_profit=2).items()},review(),[])
    company=dict(company_name='Công ty giả lập cho kiểm thử',exchange='HOSE',source_url=str(SOURCE.url),
        retrieved_at=SOURCE.retrieved_at,industry=dict(name='Sản xuất',sector_id='15',slug='san-xuat'))
    value=evaluate_scenarios(data,'manufacturing',20,cfg)
    assert len(value['methods'])==2
    doc=build_company_document(settings,repo,company,data,'manufacturing',[],[],value,cfg,[])
    pdf=render_company(doc,tmp_path/'filled.pdf')
    text=' '.join(' '.join(p.extract_text().split()) for p in PdfReader(pdf).pages)
    assert 'Dòng tiền và chiết khấu FCFF' in text and 'Dòng tiền và chiết khấu FCFE' in text
    assert 'Cơ cấu doanh thu theo sản phẩm' in text and 'Cơ cấu doanh thu theo thị trường' in text
    assert 'Giả định của người soạn' in text and 'None' not in text

"""Populate the user's company template from sourced inputs, not from placeholders."""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from stock_reports.analysis.contracts import AnalysisSection, Finding, ReportBlock, SectionKind
from stock_reports.analysis.financials import ALIASES, LABELS, financial_metrics, normalized_name
from stock_reports.analysis.profiles import PROFILES
from stock_reports.analysis.repository import VIETNAM
from stock_reports.analysis.valuation import cost_of_equity, load_scenarios
from stock_reports.domain.research import SourceReference
from stock_reports.reports.documents import ReportDocument

TEMPLATE_VERSION='company-template-1.6'
MISSING='Chưa đủ dữ liệu'
METHOD_NAMES={'pb':'P/B kịch bản','pe':'P/E kịch bản','justified_pb':'P/B hợp lý theo ROE',
              'fcff':'FCFF','fcfe':'FCFE','nav':'NAV','blended':'Tổng hợp có trọng số'}


class CompanyFact(BaseModel):
    model_config=ConfigDict(extra='forbid')
    category: Literal['overview','history','shareholders','subsidiaries','segments','operations','risks','forecast_assumptions']
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    numeric: Decimal | None = Field(default=None,allow_inf_nan=False)
    unit: str | None = None
    period: str | None = None
    dimension: Literal['product','market'] | None = None
    source: SourceReference


class CompanySupplement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    symbol: str
    facts: tuple[CompanyFact,...]


def load_supplement(settings,symbol,cutoff):
    path=settings.root/'config/company_profiles'/f'{symbol}.json'
    if not path.exists():return ()
    value=CompanySupplement.model_validate_json(path.read_text(encoding='utf-8-sig'))
    if value.symbol.upper()!=symbol:raise ValueError('Hồ sơ doanh nghiệp không khớp mã')
    return tuple(f for f in value.facts if not f.source.published_at or f.source.published_at<=cutoff)


def format_value(value,places=2):
    if value is None:return MISSING
    return f'{value:,.{places}f}'.replace(',','_').replace('.',',').replace('_','.')


def refs(*values):
    return tuple(dict.fromkeys(s for group in values for s in group if s))


def block(title,headers,rows,*,sources=(),note=''):
    return ReportBlock(kind='table',title=title,headers=tuple(headers),
        rows=tuple(tuple(str(v) if v is not None and v!='' else MISSING for v in row) for row in rows),
        sources=tuple(sources),note=note)


def note(text,sources=()):
    return Finding(text=text,sources=tuple(sources),is_assumption=not bool(sources))


def section(kind,title,findings,blocks=()):
    return AnalysisSection(kind=kind,title=title,findings=tuple(findings or [note(MISSING)]),blocks=tuple(blocks))


def supplement_table(facts,category,title):
    selected=[f for f in facts if f.category==category]
    return block(title,('Nội dung','Giá trị / mô tả','Kỳ'),
        [(f.label,f.value,f.period or MISSING) for f in selected] or [(MISSING,MISSING,MISSING)],
        sources=refs([f.source for f in selected]),note='Chỉ dùng công bố có nguồn; không tự ước tính phần chưa công bố.')


def composition_chart(facts,category,title,dimension=None):
    selected=[f for f in facts if f.category==category and f.dimension==dimension]
    # A partial share register or mixed periods must not be rendered as a complete pie.
    if len(selected)<2 or len({f.period for f in selected})!=1 or not selected[0].period:
        return None
    if any(f.numeric is None or f.numeric<0 or f.unit!='%' for f in selected):return None
    if abs(sum((f.numeric for f in selected),Decimal(0))-100)>Decimal('.01'):return None
    return ReportBlock(kind='chart',chart_type='pie',title=title,
        labels=tuple(f.label for f in selected),values=tuple(float(f.numeric) for f in selected),
        sources=refs([f.source for f in selected]),note='Tỷ trọng (%), kỳ '+selected[0].period+'. Không tự điền phần còn lại.')


def compress_warnings(warnings):
    groups={};result=[]
    for warning in dict.fromkeys(warnings):
        match=re.fullmatch(r'(.*?)\s*(\d{4}Q[1-4]): (.+)',warning)
        if match:
            key=(match[1],match[3]);groups.setdefault(key,[]).append(match[2])
        else:result.append(warning)
    result.extend(prefix+' '+', '.join(periods)+': '+detail for (prefix,detail),periods in groups.items())
    return result


def annual_summary(repo,data,profile,as_of):
    from stock_reports.analysis.annuals import annual_value,load_annual_review
    years=list(range(as_of.year-5,as_of.year))
    raw=repo.annual(data.symbol)
    review=load_annual_review(repo.settings,data.symbol)
    def converted(key,year):
        value,_=annual_value(raw,key,year,review)
        return value*review.money_multiplier if value is not None and review and year in review.years else None
    keys=['interest_income_net' if profile=='banking' else 'revenue','pretax_profit','net_profit','assets','equity']
    rows=[];sources=[]
    for key in keys:
        vals=[]
        for year in years:
            number,matches=annual_value(raw,key,year,review)
            multiplier=review.money_multiplier if review and year in review.years else Decimal(1)
            vals.append(format_value(number*multiplier/Decimal(10**9)) if number is not None else MISSING)
            for r in matches:
                if r.get('verified_source'):
                    sources.append(SourceReference.model_validate(r['verified_source']))
                    continue
                sources.append(SourceReference(source_name='CafeF BCTC năm' if r.get('statement_type') else 'CafeF dữ liệu năm nhập từ workbook',url=r['source_url'],
                    retrieved_at=r['imported_at'],locator=f"{r['sheet_name']}, dòng {r['source_row']}, {year}: {r['metric']}; SHA-256 {r['workbook_sha256']}"))
        p=data.periods[0];value=data.value(key,p)
        if ALIASES[key][0]=='BSheet' and p in data.invalid_balance_periods:value=None
        vals.append(format_value(value/Decimal(10**9)) if value is not None else MISSING)
        if data.fact(key,p):sources.append(data.fact(key,p).source)
        rows.append((LABELS[key],*vals))
    for key,label in [('equity','ROE năm (%)'),('assets','ROA năm (%)')]:
        vals=[]
        for year in years:
            before=converted(key,year-1);after=converted(key,year);profit=converted('net_profit',year)
            if review:
                opening=[f for f in review.opening_balances if f.period==str(year) and f.key==key]
                if len(opening)>1:raise ValueError('Duplicate verified opening balance')
                if opening:
                    before=opening[0].value_vnd
                    sources.append(opening[0].source)
            average=(before+after)/2 if before is not None and after is not None else None
            vals.append(format_value(profit/average*100) if profit is not None and average and average>0 else MISSING)
        rows.append((label,*vals,MISSING))
    if profile=='banking':
        facts=load_supplement(repo.settings,data.symbol,repo.cutoff)
        for label in ('NIM năm (%)','Nợ xấu cuối năm (%)'):
            selected=[f for f in facts if f.category=='operations' and f.label==label]
            vals=[]
            for year in years:
                entries=[f for f in selected if f.period==str(year)]
                vals.append(entries[0].value if len(entries)==1 else MISSING)
                sources.extend(f.source for f in entries)
            rows.append((label,*vals,'Không áp dụng: cột quý'))
    else:
        vals=[]
        for year in years:
            revenue,_=annual_value(raw,'revenue',year,review);gross,items=annual_value(raw,'gross_profit',year,review)
            vals.append(format_value(gross/revenue*100) if gross is not None and revenue and revenue>0 else MISSING)
            for r in items:
                sources.append(SourceReference.model_validate(r['verified_source']) if r.get('verified_source') else
                    SourceReference(source_name='CafeF BCTC năm',url=r['source_url'],retrieved_at=r['imported_at'],locator=f'{year}: {r["metric"]}'))
        rows.append(('Biên lợi nhuận gộp năm (%)',*vals,MISSING))
    if review:sources.extend(review.sources)
    annual_note=('Đơn vị VND và phạm vi '+('hợp nhất' if review.scope=='consolidated' else 'riêng lẻ')+
        ' đã đối chiếu cho các năm '+', '.join(map(str,review.years))+'. '+review.review_note) if review else \
        'Đơn vị và hợp nhất/riêng của số năm cần đối chiếu BCTC gốc.'
    return block('Bảng 1: KQKD và cân đối chính - 5 năm và kỳ mới nhất',
        ('Chỉ tiêu',*[str(y) for y in years],f'{p[0]}Q{p[1]}'),rows,sources=refs(sources),
        note='Cột năm: BCTC năm tải trực tiếp (ưu tiên) hoặc workbook lịch sử / 10^9. '+annual_note+' Không lấy quý 4 thay số năm. '
             'Cột quý dùng dữ liệu CafeF; chưa coi KQKD là quý riêng khi thiếu review. Hai kỳ không so sánh trực tiếp. '
             'ROE/ROA năm = LNST / bình quân vốn/tài sản đầu-cuối năm; chỉ tính khi hai năm cùng phạm vi, đơn vị đã đối chiếu. TTM xem bảng riêng.')


def projection_rows(scenarios,as_of):
    years=list(range(as_of.year-1,as_of.year+3));groups=[]
    if scenarios:
        base=next(c for c in scenarios.cases if c.name=='base')
        groups=[m.projections for m in base.components] if base.components else [base.projections]
    rows=[];sources=[]
    for field,label,scale in [('revenue_vnd','Doanh thu (tỷ VND)',10**9),
        ('net_profit_vnd','LNST (tỷ VND)',10**9),('eps_vnd','EPS (VND/cp)',1),
        ('bvps_vnd','BVPS (VND/cp)',1),('roe','ROE (%)',Decimal('.01'))]:
        vals=[];numbers=[]
        for year in years:
            points=[p for group in groups for p in group if p.year==year and getattr(p,field) is not None]
            distinct={getattr(p,field) for p in points}
            number=next(iter(distinct)) if len(distinct)==1 else None
            vals.append(format_value(number/Decimal(scale)) if number is not None else MISSING)
            numbers.append(number);sources.extend(p.source for p in points if p.source)
        rows.append((label,*vals))
        if field!='roe':rows.append(('Tăng trưởng '+label.split(' (')[0]+' (%)',MISSING,*[
            format_value((numbers[i]/numbers[i-1]-1)*100) if numbers[i] is not None and numbers[i-1] is not None and numbers[i-1]>0 else MISSING
            for i in range(1,len(years))]))
    return years,rows,refs(sources)


def peer_valuation(repo,candidates,symbol,scenarios,as_of):
    from stock_reports.analysis.valuation import evaluate_scenarios
    rows=[];sources=[];ratios=[];valid=0
    for i,(company,data,profile) in enumerate(candidates,1):
        ticker=company['symbol']
        if ticker==symbol:continue
        bars=repo.bars(ticker);review=data.review
        values=evaluate_scenarios(data,profile,bars[-1]['close'] if bars else None,None)
        market={m['label']:m['value'] for m in values['metrics']}
        price=values['current'];shares=review.shares_outstanding if review else None
        pb=market.get('P/B hiện tại');profit=None;eps=None
        cfg=repo.settings.root/'config/valuation'/f'{ticker}.json'
        forecast=load_scenarios(cfg) if cfg.exists() else None
        if forecast:
            base=next(c for c in forecast.cases if c.name=='base')
            projections=[p for method in base.components for p in method.projections] if base.components else list(base.projections)
            points=[p for p in projections if p.year==as_of.year+1]
            for field in ('net_profit_vnd','eps_vnd'):
                nums={getattr(p,field) for p in points if getattr(p,field) is not None}
                if len(nums)==1:
                    if field=='net_profit_vnd':profit=next(iter(nums))
                    else:eps=next(iter(nums))
            sources.extend(p.source for p in points if p.source)
        pe=price/eps if price is not None and eps is not None and eps>0 else None
        cap=price*shares/Decimal(10**9) if price is not None and shares else None
        rows.append((str(i),ticker,format_value(price,0),format_value(cap),
            format_value(profit/Decimal(10**9)) if profit is not None else MISSING,format_value(pe),format_value(pb)))
        if pe is not None and pb is not None:valid+=1;ratios.append((pe,pb))
        if review:sources.append(review.source)
        if bars:sources.append(repo.price_source(ticker,bars))
    if not rows:rows=[(MISSING,)*7]
    def median(values):
        values=sorted(values);n=len(values)
        return (values[n//2] if n%2 else (values[n//2-1]+values[n//2])/2) if n>=3 else None
    rows.append(('-', 'Trung vị nhóm', MISSING,MISSING,MISSING,
        format_value(median([r[0] for r in ratios])),format_value(median([r[1] for r in ratios]))))
    market={m['label']:m['value'] for m in scenarios['metrics']}
    rows.append(('-',symbol+' (đối chiếu)',format_value(scenarios['current'],0),MISSING,MISSING,MISSING,
                 format_value(market.get('P/B hiện tại'))))
    return block('7.6. Định giá so sánh - nhóm không gồm doanh nghiệp đang định giá',
        ('STT','Mã','Giá VND/cp','Vốn hóa tỷ VND',f'LNST {as_of.year+1}F tỷ VND',f'P/E {as_of.year+1}F','P/B'),rows,
        sources=refs(sources),note=f'Chọn tối đa 5 mã cùng nhóm GICS và cùng mô hình, cùng kỳ BCTC. '
        f'Có {valid} mã đủ cả P/E dự phóng và P/B đã kiểm chứng; dưới 3 không tính trung vị. '
        'Không lấy EPS TTM thay EPS dự phóng; không áp premium/discount khi chưa có căn cứ định lượng.')


def valuation_blocks(value,profile,scenarios,review,repo,candidates,symbol,as_of):
    vs=refs([review.source] if review else [],[s for c in scenarios.cases for s in [c.source,*[m.source for m in c.components]] if s] if scenarios else [])
    standard='justified_pb' if profile=='banking' else 'pb' if profile in ('securities','other_financial') else 'nav' if profile=='real_estate' else 'fcff'
    blocks=[block('7.2. Phương pháp theo mô hình kinh doanh',('Mô hình','Phương pháp chính','Đối chiếu','Báo cáo này'),[
        ('Sản xuất, bán lẻ, hạ tầng','FCFF / FCFE','P/E, EV/EBITDA','Áp dụng' if profile not in ('banking','securities','other_financial','real_estate') else 'Không áp dụng'),
        ('Ngân hàng','P/B hợp lý theo ROE','P/E','Áp dụng' if profile=='banking' else 'Không áp dụng'),
        ('Bất động sản','NAV','P/B','Áp dụng' if profile=='real_estate' else 'Không áp dụng'),
        ('Chứng khoán / tài chính khác','P/B có căn cứ mô hình riêng','P/E nếu EPS phù hợp','Áp dụng' if profile in ('securities','other_financial') else 'Không áp dụng')],
        note='Lựa chọn phương pháp là khung phân tích, không phải đầu vào định giá. Không dùng DCF sản xuất cho ngân hàng.')]
    methods=value['methods']
    method_rows=[(METHOD_NAMES[m['method']],format_value(m['target'],0),format_value(m['weight']*100)+'%') for m in methods] or \
        [(METHOD_NAMES[standard],MISSING,MISSING)]
    method_rows.append(('Giá mục tiêu phát hành (làm tròn)',format_value(value['target'],0),
        format_value(sum((m['weight'] for m in methods),Decimal(0))*100)+'%' if methods else MISSING))
    blocks.append(block('7.3. Tổng hợp phương pháp',('Phương pháp','Giá hàm ý VND/cp','Trọng số'),
        method_rows,sources=vs,
        note='Không mặc định 50/50. Giá mục tiêu phát hành chỉ có khi toàn bộ điều kiện kiểm chứng đạt; giá hàm ý chưa phát hành không phải khuyến nghị.'))
    base=next(c for c in scenarios.cases if c.name=='base') if scenarios else None
    inputs=list(base.components) if base and base.components else [base] if base else []
    assumption_rows=[]
    fields=[('risk_free_rate','Lãi suất phi rủi ro',100),('market_risk_premium','Phần bù rủi ro thị trường',100),
        ('beta','Beta',1),('ke','Chi phí vốn chủ sở hữu Ke',100),('wacc','WACC',100),
        ('terminal_growth','Tăng trưởng dài hạn g',100),('sustainable_roe','ROE bền vững',100)]
    if inputs:
        fields.extend([('multiple','Bội số mục tiêu',1),('growth','Tăng trưởng EPS / VCSH nhập rõ',100),
            ('forecast_bvps_vnd','BVPS dự phóng VND/cp',1),('cash_vnd','Tiền và đầu tư tài chính tỷ VND',Decimal('0.000000001')),
            ('debt_vnd','Nợ vay tỷ VND',Decimal('0.000000001')),('forecast_shares','Cổ phiếu dự phóng triệu cp',Decimal('0.000001'))])
    for field,label,factor in fields:
        if not inputs:assumption_rows.append((label,MISSING,MISSING));continue
        for item in inputs:
            try:number=cost_of_equity(item) if field=='ke' else getattr(item,field)
            except ValueError:number=item.ke  # Keep inconsistent supplied inputs visible, not publishable.
            prefix=METHOD_NAMES[item.method]+': ' if hasattr(item,'method') else ''
            basis=(item.source.source_name if item.source else 'Giả định của người soạn')+': '+item.rationale
            assumption_rows.append((prefix+label,format_value(number*factor)+('%' if factor==100 else '') if number is not None else MISSING,
                basis if number is not None else MISSING))
    assumption_rows.append(('Thời gian dự phóng',
        ', '.join('/'.join(str(p.year) for p in item.projections) for item in inputs if item.projections) or MISSING,
        'Các năm được nhập rõ; không tạo chuỗi dự phóng mặc định'))
    blocks.append(block('7.4. Giả định và căn cứ',('Giả định','Giá trị','Nguồn / lý do'),assumption_rows,sources=vs,
        note='Tỷ lệ cấu hình dùng số thập phân (ví dụ 0,10 = 10%); thiếu nguồn ghi rõ giả định của người soạn.'))
    if methods:
        for m in methods:
            method=m['method'];rows=[('Giá hàm ý (VND/cp)',format_value(m['target'],0))]
            if method in ('fcff','fcfe'):
                rows=[('PV dòng tiền trong kỳ (tỷ VND)',format_value(m['pv']/Decimal(10**9))),
                    ('PV giá trị cuối kỳ (tỷ VND)',format_value(m['terminal_pv']/Decimal(10**9))),
                    ('Tiền và đầu tư tài chính (tỷ VND)',format_value(m['cash']/Decimal(10**9)) if m['cash'] is not None else 'Không áp dụng cho FCFE'),
                    ('Nợ vay (tỷ VND)',format_value(m['debt']/Decimal(10**9)) if m['debt'] is not None else 'Không áp dụng cho FCFE'),
                    ('Giá trị VCSH (tỷ VND)',format_value(m['equity']/Decimal(10**9))),
                    ('Số cổ phiếu (triệu cp)',format_value(m['shares']/Decimal(10**6))),*rows]
            elif method=='justified_pb':
                rows=[('ROE bền vững',format_value(m['roe']*100)+'%'),('Ke',format_value(m['ke']*100)+'%'),
                    ('g',format_value(m['g']*100)+'%'),('P/B hợp lý',format_value(m['multiple'])),
                    ('BVPS dự phóng VND/cp',format_value(m['basis'],0)),
                    ('ROE thị trường hàm ý',format_value(m.get('implied_roe')*100)+'%' if m.get('implied_roe') is not None else MISSING),*rows]
            elif method=='nav':rows=[('VCSH NAV (tỷ VND)',format_value(m['equity']/Decimal(10**9))),
                ('Nghĩa vụ nợ (tỷ VND)',format_value(m['liabilities']/Decimal(10**9))),
                ('Số cổ phiếu (triệu cp)',format_value(m['shares']/Decimal(10**6))),*rows]
            else:rows=[('Bội số mục tiêu',format_value(m['multiple'])),('EPS/BVPS dự phóng VND/cp',format_value(m['basis'],0)),*rows]
            blocks.append(block('7.5. Chi tiết tính '+METHOD_NAMES[method],('Hạng mục','Giá trị'),rows,sources=vs,
                note='FCFF: TV = FCFF cuối kỳ × (1 + g) / (WACC - g); FCFE dùng Ke. P/B hợp lý = (ROE - g) / (Ke - g). NAV = tổng tài sản theo phần sở hữu - nghĩa vụ nợ.'))
            if method in ('fcff','fcfe'):
                projection=m['projection']
                rows=[]
                for item in projection:
                    flow=getattr(item,method+'_vnd')
                    rows.append((str(item.year),format_value(item.discount_years),format_value(flow/Decimal(10**9)),
                        format_value(flow/(1+m['discount_rate'])**item.discount_years/Decimal(10**9)),
                        (item.source.source_name if item.source else 'Giả định của người soạn')+': '+item.rationale))
                blocks.append(block('7.5. Dòng tiền và chiết khấu '+METHOD_NAMES[method],
                    ('Năm','Kỳ chiết khấu năm','Dòng tiền tỷ VND','PV tỷ VND','Căn cứ'),rows,
                    sources=refs(vs,[p.source for p in projection if p.source]),
                    note='Thời điểm từng dòng tiền do người soạn nhập; không tự mặc định chiết khấu cuối năm.'))
            elif method=='nav':
                blocks.append(block('7.5. Danh mục tài sản NAV',('Tài sản','Giá trị tỷ VND','Sở hữu %','Phần sở hữu tỷ VND','Căn cứ'),[
                    (a.name,format_value(a.value_vnd/Decimal(10**9)),format_value(a.ownership*100),
                     format_value(a.value_vnd*a.ownership/Decimal(10**9)),
                     (a.source.source_name if a.source else 'Giả định của người soạn')+': '+a.rationale) for a in m['assets']],
                    sources=refs(vs,[a.source for a in m['assets'] if a.source]),note='Không cộng lặp tài sản hoặc tự gán tỷ lệ sở hữu.'))
    else:
        labels=['ROE bền vững','Ke','g','P/B hợp lý','BVPS dự phóng VND/cp','Giá hàm ý VND/cp'] if profile=='banking' else \
            ['Danh mục tài sản / giá trị dự án','Nghĩa vụ nợ','Số cổ phiếu','Giá NAV VND/cp'] if profile=='real_estate' else \
            ['Dòng tiền dự phóng từng năm','Suất chiết khấu / g','Tiền và nợ vay','Số cổ phiếu','Giá hàm ý VND/cp']
        blocks.append(block('7.5. Chi tiết tính - '+METHOD_NAMES[standard],('Đầu vào','Giá trị'),[(label,MISSING) for label in labels],
            note='P/B hợp lý = (ROE - g) / (Ke - g), cần Ke > g. TV = FCFF cuối kỳ × (1 + g) / (WACC - g), cần WACC > g. '+value['reason']))
    blocks.append(peer_valuation(repo,candidates,symbol,value,as_of))
    if value['sensitivity']:
        grid=scenarios.sensitivity
        blocks.append(block('7.7. Độ nhạy '+grid.row_variable.upper()+' × '+grid.column_variable.upper(),
            (grid.row_variable.upper()+' / '+grid.column_variable.upper(),*[format_value(v*100)+'%' for v in grid.column_values]),
            [(format_value(row['row']*100)+'%',*[format_value(v,0) for v in row['values']]) for row in value['sensitivity']],
            note='VND/cp; ô không đạt điều kiện chiết khấu ghi thiếu. '+grid.rationale,sources=vs))
    else:blocks.append(block('7.7. Độ nhạy - ROE × Ke hoặc WACC × g',('Nội dung','Trạng thái'),
        [('Ba mức cho mỗi trục',MISSING),('Giá hàm ý VND/cp',MISSING)],note='Không tự đặt trục ±1% hoặc giả định khi chưa có căn cứ.'))
    names={'bear':'Bi quan','base':'Cơ sở','bull':'Lạc quan'}
    blocks.append(block('7.8. Ba kịch bản',('Kịch bản','Giả định chính','Giá VND/cp','So với hiện tại','Xác suất'),
        [(names[r['name']],r['rationale'],format_value(r['target'],0),format_value(r['upside'])+'%',
          format_value(r['probability']*100)+'%' if r['probability'] is not None else MISSING) for r in value['rows']] or
        [(label,MISSING,MISSING,MISSING,MISSING) for label in names.values()],sources=vs,
        note='Giữ tên kịch bản do người soạn nhập; nếu sai thứ tự hoặc thiếu kịch bản dưới giá hiện tại thì chặn khuyến nghị, không sửa giả định để tạo chiều giảm.'))
    blocks.append(block('7.9. Ngưỡng khuyến nghị',('Tiềm năng kịch bản cơ sở','Phân loại khi đủ điều kiện'),[
        ('≥ +15%','KHẢ QUAN'),('> -10% và < +15%','TRUNG LẬP'),('≤ -10%','KÉM KHẢ QUAN')],
        note='Các ngưỡng theo khuôn mẫu; không đặt khuyến nghị trước khi tính và kiểm chứng.'))
    checks=value['checks'] or [dict(label=label,passed=False) for label in
        ('Đơn vị, số cổ phiếu, hợp nhất/riêng','Giả định có nguồn/lý do','Thuyết minh','Ba kịch bản và chiều giảm','Phương pháp và kiểm tra đảo ngược')]
    blocks.append(block('7.10. Kiểm tra trước phát hành',('Điều kiện','Kết quả'),
        [(c['label'],'Đạt' if c['passed'] else 'Chưa đạt / '+MISSING) for c in checks]+[
        ('Nhóm so sánh không gồm chính doanh nghiệp','Đạt'),('Premium/discount có căn cứ','Không áp dụng: chưa dùng premium/discount')],
        note='Chỉ phân loại sau khi các kiểm tra bắt buộc đạt; bảng tiêu chí không phải khuyến nghị cho cổ phiếu này.'))
    return blocks


def build_company_document(settings,repo,company,data,profile,candidates,bars,valuation,scenarios,risk_notes):
    from stock_reports.analysis.research import macro_section,industry_section,financial_section,technical_section
    symbol=data.symbol;as_of=repo.as_of;review=data.review;p=data.periods[0];industry=company['industry']
    facts=load_supplement(settings,symbol,repo.cutoff)
    company_source=SourceReference(source_name='DNSE hồ sơ doanh nghiệp',url=company['source_url'],retrieved_at=company['retrieved_at'])
    price_source=repo.price_source(symbol,bars) if bars else None
    market={m['label']:m['value'] for m in valuation['metrics']}
    shares=review.shares_outstanding if review else None
    unit=review.price_multiplier if review else None
    high=low=None
    if bars and unit is not None and len(bars)>=200:
        dates=[datetime.fromtimestamp(r['ts'],VIETNAM).date() for r in bars]
        window=[r for r,d in zip(bars,dates) if (as_of-d).days<=364]
        if (as_of-min(dates)).days>=350 and window:
            high=max(Decimal(str(r['high'])) for r in window)*unit
            low=min(Decimal(str(r['low'])) for r in window)*unit
    volume=(sum(Decimal(str(r['volume'])) for r in bars[-30:])/30 if len(bars)>=30 and
        all(r['volume'] is not None for r in bars[-30:]) else None)
    day=datetime.fromtimestamp(bars[-1]['ts'],VIETNAM).strftime('%d/%m/%Y') if bars else MISSING
    sources=refs([company_source],[price_source] if price_source else [],
                 [review.source,*review.verification_sources] if review else [])
    price=valuation['current'];target=valuation['target'];upside=valuation['upside']
    cover=block('KẾT LUẬN TRƯỚC',('Chỉ tiêu','Kết luận'),[
        ('Khuyến nghị',valuation['assessment']),('Giá hiện tại VND/cp, ngày',format_value(price,0)+' | '+day),
        ('Giá mục tiêu 12 tháng VND/cp',format_value(target,0)),('Tăng / (giảm)',format_value(upside)+'%' if upside is not None else MISSING)],
        sources=sources,note='Giá mục tiêu chỉ công bố khi đủ điều kiện; giá hàm ý chưa kiểm chứng xem mục VII.')
    trade=block('Thông tin giao dịch đến '+day,('Chỉ tiêu','Giá trị'),[
        ('Giá cao / thấp 52 tuần VND/cp',format_value(high,0)+' / '+format_value(low,0)),
        ('Số cổ phiếu lưu hành triệu cp',format_value(shares/Decimal(10**6)) if shares else MISSING),
        ('KLGD bình quân 30 phiên cp',format_value(volume,0)),('% sở hữu nước ngoài',MISSING),
        ('Vốn hóa tỷ VND',format_value(price*shares/Decimal(10**9)) if price is not None and shares else MISSING),
        ('P/E TTM / P/B hiện tại lần',format_value(market.get('P/E hiện tại'))+' / '+format_value(market.get('P/B hiện tại'))),
        ('EPS TTM / BVPS hiện tại VND/cp',format_value(market.get('EPS TTM'),0)+' / '+format_value(market.get('BVPS hiện tại'),0)),
        ('Giá đóng cửa gốc, đơn vị nguồn',format_value(bars[-1]['close']) if bars else MISSING)],sources=sources,
        note='P/B và BVPS là số cuối kỳ, không phải TTM. 30 phiên không phải 30 ngày lịch. Không lấy hạn mức còn lại suy ra sở hữu nước ngoài. Giá nguồn chưa mặc định ×1.000.')
    all_risks=list(dict.fromkeys([*PROFILES[profile]['risks'],*risk_notes,*data.warnings]))
    if not review or not review.notes_reviewed:all_risks.append('Chưa rà soát toàn bộ thuyết minh BCTC gốc; chưa phát hành khuyến nghị.')
    metrics=financial_metrics(data,profile)
    thesis=[note(f'{company["company_name"] or symbol} ({company["exchange"]}: {symbol}) thuộc nhóm {industry["name"]}.',[company_source])]
    measured=next((m for m in metrics if m['value'] is not None and m['sources']),None)
    if measured:thesis.append(note(measured['label']+': '+format_value(measured['value'])+' '+measured['unit']+'. '+
        ('Đơn vị và kỳ theo hồ sơ đối chiếu BCTC gốc.' if review else 'Chỉ tiêu sơ bộ cần kiểm chứng đơn vị/phạm vi.'),measured['sources']))
    thesis.append(note(valuation['reason']))
    conclusion=section(SectionKind.RECOMMENDATION,'KẾT LUẬN TRƯỚC',thesis,[cover,trade])
    company_blocks=[block('Tổng quan doanh nghiệp',('Mục','Nội dung'),[
        ('Tên / sàn / mã',(company['company_name'] or symbol)+' / '+company['exchange']+' / '+symbol),
        ('Địa chỉ',next((f.value for f in facts if f.category=='overview' and 'địa chỉ' in f.label.lower()),MISSING)),
        ('Nguồn doanh thu / chi phí chính',PROFILES[profile]['business']),('Rủi ro chính',PROFILES[profile]['risks'][0])],
        sources=refs([company_source],[f.source for f in facts if f.category=='overview']),
        note='Chuỗi doanh thu/chi phí là khung mô hình cần đối chiếu công bố, không phải cơ cấu doanh thu thực đo.'),
        supplement_table(facts,'history','1. Thông tin chung và lịch sử hình thành'),
        supplement_table(facts,'shareholders','2. Cơ cấu cổ đông và quyền điều hành'),
        supplement_table(facts,'subsidiaries','3. Công ty con và liên kết'),
        supplement_table(facts,'segments','4. Cơ cấu doanh thu theo sản phẩm / thị trường')]
    overview_rows=[(f.label,f.value) for f in facts if f.category=='overview' and 'địa chỉ' not in f.label.lower()]
    if overview_rows:
        company_blocks[0]=company_blocks[0].model_copy(update={'rows':(*company_blocks[0].rows,*overview_rows)})
    for category,title,dimension in [('shareholders','Cơ cấu cổ đông theo tỷ trọng công bố',None),
        ('segments','Cơ cấu doanh thu theo sản phẩm','product'),('segments','Cơ cấu doanh thu theo thị trường','market')]:
        chart=composition_chart(facts,category,title,dimension)
        if chart:company_blocks.append(chart)
    company_section=section(SectionKind.COMPANY,'I. TỔNG QUAN DOANH NGHIỆP',[
        note('Chỉ vẽ cơ cấu cổ đông/doanh thu khi có tỷ lệ hoặc giá trị công bố cùng kỳ; không vẽ biểu đồ giả từ ô thiếu.')],company_blocks)
    industry_analysis=industry_section(repo,industry,profile,candidates=candidates)
    sector=section(SectionKind.INDUSTRY,'II. CẬP NHẬT NGÀNH',industry_analysis.findings,[*industry_analysis.blocks,
        block('Quy mô, giá đầu vào / đầu ra và vị thế',('Nội dung','Kết quả'),[
            ('Quy mô và tăng trưởng ngành',MISSING),('Giá đầu vào / đầu ra tháng-quý',MISSING),('Thị phần / xếp hạng doanh nghiệp',MISSING)],
            note='Snapshot biến động giá ngành không thay thế quy mô ngành hay thị phần doanh nghiệp.')])
    macro=macro_section(repo,profile)
    macro_rows=[];macro_refs=[]
    for code in dict.fromkeys(r['metric'] for r in repo.macro()):
        r=sorted([r for r in repo.macro() if r['metric']==code],key=lambda r:r['period'])[-1]
        macro_rows.append((r['label'],r['period'],format_value(r['value'])+' '+r['unit']))
        macro_refs.append(SourceReference.model_validate(r['source']))
    macro_news=[f for f in macro.findings if 'Ngày đăng:' in f.text]
    macro_findings=[f for f in macro.findings[len(macro_rows):] if f not in macro_news]
    macro=section(SectionKind.MACRO,'Vĩ mô liên quan',macro_findings,[block('Vĩ mô liên quan - kỳ quan sát',
        ('Chỉ tiêu','Kỳ','Giá trị'),macro_rows or [(MISSING,)*3],sources=refs(macro_refs),
        note='WDI là số năm; chưa có chuỗi lãi suất, tỷ giá, tín dụng tháng đã kiểm chứng. Không trộn bản Agriseco của báo cáo vĩ mô riêng vào báo cáo doanh nghiệp.')])
    operating_blocks=[supplement_table(facts,'operations','Chỉ tiêu vận hành công bố')]
    needed=(['Tăng trưởng tín dụng cùng kỳ','NIM','CASA','Thu nhập ngoài lãi','Chi phí tín dụng / nợ xấu'] if profile=='banking' else
        ['Dư nợ margin và tỷ lệ an toàn','Lãi đã thực hiện / chưa thực hiện','Chi phí vốn'] if profile=='securities' else
        ['Công suất / hiệu suất','Sản lượng / giá bán','Chi phí đơn vị / chính sách bán hàng'])
    available=[f.label.casefold() for f in facts if f.category=='operations']
    missing=[name for name in needed if not any(name.casefold() in label for label in available)]
    if missing:operating_blocks.append(block('Chỉ tiêu đặc thù cần bổ sung',('Chỉ tiêu','Giá trị'),
        [(name,MISSING) for name in missing],note='Không thay chỉ tiêu chưa công bố bằng tỷ lệ khác tên hoặc suy diễn từ mã ngành.'))
    series_key='loans_gross' if profile=='banking' else 'revenue'
    observed=list(reversed(data.periods))
    if any(data.fact(series_key,period) for period in observed):
        operating_blocks.append(ReportBlock(kind='chart',title=LABELS[series_key]+' theo các kỳ nguồn công bố',
            labels=tuple(f'{y}Q{q}' for y,q in observed),
            values=tuple(float(data.value(series_key,period)/Decimal(10**9)) if data.value(series_key,period) is not None else None for period in observed),
            sources=refs([data.fact(series_key,period).source for period in observed if data.fact(series_key,period)]),
            note='Giá trị nguồn / 10^9; đơn vị, scope và quý/lũy kế chưa kiểm chứng nếu thiếu review. Không lấy thay chỉ tiêu tín dụng quản lý.'))
    business=section(SectionKind.BUSINESS,'III. PHÂN TÍCH HOẠT ĐỘNG KINH DOANH',[
        note('Khung chuỗi giá trị: '+PROFILES[profile]['business']),
        *[note('Trụ cột kiểm chứng '+str(i)+': '+q) for i,q in enumerate(PROFILES[profile]['questions'],1)]],
        operating_blocks)
    fin=financial_section(data,profile)
    summary=annual_summary(repo,data,profile,as_of)
    financial=section(SectionKind.FINANCIAL,'IV. PHÂN TÍCH TÌNH HÌNH TÀI CHÍNH',[
        note('Cấu trúc vốn và thanh khoản: đối chiếu nợ vay, tiền mặt; ngân hàng kiểm tra tiền gửi và CAR, không chấm D/E theo mô hình sản xuất.'),
        note('Dòng tiền và cổ tức: '+MISSING+' cho lịch sử cổ tức/tỷ lệ chi trả có nguồn.'),
        *[f for f in fin.findings if not f.is_assumption][:4]],
        [summary,*[b for b in fin.blocks if not b.title.startswith('BCTC:')]])
    years,forecast_rows,forecast_refs=projection_rows(scenarios,as_of)
    # The first forecast-table column is an actual year, not a projection.
    # Fill from annual statements without inventing future assumptions.
    from stock_reports.analysis.annuals import annual_value,load_annual_review
    annual_review=load_annual_review(settings,symbol)
    actual_rows=repo.annual(symbol)
    actual_keys={'Doanh thu (tỷ VND)':'revenue','LNST (tỷ VND)':'net_profit'}
    enriched=[];actual_sources=[]
    for row in forecast_rows:
        label,*values=row
        if label in actual_keys:
            actual,matches=annual_value(actual_rows,actual_keys[label],years[0],annual_review)
            if actual is not None:
                values[0]=format_value(actual*(annual_review.money_multiplier if annual_review else 1)/Decimal(10**9))
                for r in matches:
                    actual_sources.append(SourceReference.model_validate(r['verified_source']) if r.get('verified_source') else
                        SourceReference(source_name='CafeF BCTC năm',url=r['source_url'],retrieved_at=r['imported_at'],locator=f'{years[0]}: {r["metric"]}'))
        if label.startswith('EPS'):
            eps=[f for f in facts if f.label=='EPS năm (VND/cp)' and f.period==str(years[0])]
            if len(eps)==1:values[0]=eps[0].value;actual_sources.append(eps[0].source)
        enriched.append((label,*values))
    forecast_rows=enriched;forecast_refs=refs(forecast_refs,actual_sources)
    assumption_facts=[f for f in facts if f.category=='forecast_assumptions']
    assumption_labels=['Tăng trưởng tín dụng','NIM','Chi phí tín dụng','Tăng vốn'] if profile=='banking' else \
        ['Tăng trưởng sản lượng','Giá bán','Biên lợi nhuận','CAPEX']
    assumption_rows=[]
    for label in dict.fromkeys([*assumption_labels,*[f.label for f in assumption_facts]]):
        matches=[f for f in assumption_facts if f.label==label]
        vals=[]
        for index,year in enumerate(years):
            entries=[f for f in matches if f.period in (str(year),str(year)+'F' if index else str(year))]
            unique={f.value for f in entries}
            vals.append(next(iter(unique)) if len(unique)==1 else MISSING)
        assumption_rows.append((label,*vals,'; '.join(dict.fromkeys(f.source.source_name for f in matches)) or MISSING))
    prospects=section(SectionKind.PROSPECTS,'V. TRIỂN VỌNG VÀ DỰ PHÓNG',[
        note('Dự phóng phải do người soạn nhập cùng nguồn hoặc lý do. Không kéo dài tốc độ lịch sử, không coi kịch bản 12 tháng là năm tài chính kế tiếp.')],
        [block('Bảng 2: Giả định dự phóng vận hành',('Biến',str(years[0]),*[str(y)+'F' for y in years[1:]],'Căn cứ'),
            assumption_rows,sources=refs([f.source for f in assumption_facts]),
            note='Giả định định giá chi tiết ở mục 7.4; không thay tăng trưởng VCSH bằng tăng trưởng tín dụng.'),
         block('Bảng 3: Kết quả dự phóng và tăng trưởng',('Chỉ tiêu',str(years[0]),*[str(y)+'F' for y in years[1:]]),
            forecast_rows,sources=forecast_refs,note='Chỉ hiện các năm/giá trị được nhập. Các cấu phần có dự phóng mâu thuẫn giữ thiếu. Thiếu nguồn ghi giả định của người soạn.')])
    risks=section(SectionKind.RISKS,'VI. RỦI RO ĐẦU TƯ',[note('Mức độ rủi ro không tự phân loại khi thiếu ngưỡng và bằng chứng.'),
        *[note(f.label+': '+f.value,[f.source]) for f in facts if f.category=='risks']],
        [block('Rủi ro, cơ chế và biến theo dõi',('Rủi ro','Cơ chế tác động','Biến theo dõi','Mức độ'),[
            ('Chi phí vốn / thanh khoản',PROFILES[profile]['channels'][0], 'Lãi suất, chi phí vốn, thanh khoản',MISSING),
            ('Cầu / chất lượng tài sản',PROFILES[profile]['channels'][-1],'Nợ xấu, thu tiền, sản lượng theo mô hình',MISSING),
            ('Chất lượng dữ liệu','Sai đơn vị hoặc kỳ làm sai chỉ tiêu và định giá','Scope, quý/YTD, cổ phiếu, điều chỉnh BCTC',MISSING)],
            note='Khung theo dõi rủi ro, không phải đánh giá định lượng mới.'),
         block('Lưu ý dữ liệu',('Cảnh báo',),[(r,) for r in compress_warnings(all_risks)])])
    val=section(SectionKind.VALUATION,'VII. ĐỊNH GIÁ VÀ KHUYẾN NGHỊ',[
        note('7.1. Kết luận: '+valuation['assessment']+'. Giá mục tiêu 12 tháng: '+format_value(target,0)+' VND/cp; tiềm năng: '+
             (format_value(upside)+'%' if upside is not None else MISSING)+'. '+valuation['reason'])],
        valuation_blocks(valuation,profile,scenarios,review,repo,candidates,symbol,as_of))
    appendix=section(SectionKind.APPENDIX,'VIII. PHỤ LỤC',[
        note('BCTC chi tiết theo quý, trạng thái kiểm chứng và tài liệu nguồn được lưu cùng snapshot báo cáo. Người soạn và người phê duyệt: chưa được cung cấp.'),
        *macro_news],
        [b for b in fin.blocks if b.title.startswith('BCTC:')])
    template=settings.root/'config/report_content/company-template.md'
    digest=sha256(template.read_bytes()).hexdigest() if template.exists() else None
    return ReportDocument(kind='stock',title=(company['company_name'] or symbol)+f' ({company["exchange"]}: {symbol}) - BÁO CÁO PHÂN TÍCH CỔ PHIẾU',
        as_of=as_of,symbol=symbol,company_name=company['company_name'] or symbol,industry_id=industry['slug'],industry_name=industry['name'],
        financial_period=f'{p[0]}Q{p[1]}',assessment=valuation['assessment'],data_quality=tuple(dict.fromkeys(all_risks)),
        template_version=TEMPLATE_VERSION,template_sha256=digest,cover_blocks=(cover,trade),
        sections=(conclusion,company_section,sector,macro,business,financial,prospects,risks,val,appendix,technical_section(repo,symbol)))

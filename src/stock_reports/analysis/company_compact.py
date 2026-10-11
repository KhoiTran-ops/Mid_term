"""Evidence-first company edition: no empty template tables or synthetic forecasts."""
from datetime import datetime
from decimal import Decimal
import json

from stock_reports.analysis.company_template import annual_summary, block, note, refs, section, load_supplement, format_value, compress_warnings, valuation_blocks
from stock_reports.analysis.contracts import ReportBlock, SectionKind
from stock_reports.analysis.financials import ALIASES, LABELS, financial_metrics
from stock_reports.analysis.profiles import PROFILES
from stock_reports.analysis.repository import VIETNAM
from stock_reports.domain.research import SourceReference
from stock_reports.analysis.market_fundamentals import load_market_snapshot, market_quote, provider_metrics
from stock_reports.analysis.annuals import annual_income_anomalies, load_annual_review
from stock_reports.reports.documents import ReportDocument

MISSING = 'Chưa đủ dữ liệu'
VERSION = 'company-compact-3.3'


def profile_financial_keys(profile):
    common=['revenue','pretax_profit','net_profit','assets','equity']
    if profile=='banking':return ['interest_income_net',*common,'loans_gross','deposits','operating_cost']
    if profile=='securities':return [*common,'brokerage','loan_income','investment_income','fvtpl','loans']
    if profile=='other_financial':return common
    return ['revenue','gross_profit','pretax_profit','net_profit','assets','equity','short_debt','long_debt','inventory','cfo']


def valuation_method_text(profile):
    if profile=='banking':return 'Ngân hàng: P/B hợp lý theo ROE bền vững, Ke và g; P/E chỉ đối chiếu. Không dùng DCF sản xuất.'
    if profile in ('securities','other_financial'):return 'Doanh nghiệp tài chính: P/B theo mô hình riêng; P/E chỉ đối chiếu khi EPS phù hợp. Không dùng FCFF sản xuất.'
    if profile=='real_estate':return 'Bất động sản: NAV theo dự án và nghĩa vụ nợ; P/B chỉ đối chiếu. Cần tỷ lệ sở hữu, pháp lý và tiến độ.'
    return 'Phi tài chính: FCFF/FCFE; P/E, P/B là đối chiếu khi đủ dữ liệu. Không tự đặt giả định dự phóng.'


def has_data(value):
    return value not in ('', MISSING, '-', '—', 'Không áp dụng: cột quý')


def prune_table(table):
    """Drop only entirely empty data rows/columns, never numeric zero."""
    rows = [r for r in table.rows if any(has_data(v) for v in r[1:])]
    if not rows:
        return None
    indices = [0] + [i for i in range(1, len(table.headers)) if any(has_data(r[i]) for r in rows)]
    return table.model_copy(update={'headers': tuple(table.headers[i] for i in indices),
                                   'rows': tuple(tuple(r[i] for i in indices) for r in rows)})


def build_compact_company_document(settings,repo,company,data,profile,candidates,bars,valuation,scenarios,risk_notes):
    symbol=data.symbol;period=data.periods[0];review=data.review
    annual_issues=annual_income_anomalies(repo.annual(symbol),load_annual_review(settings,symbol))
    snapshot=load_market_snapshot(settings,symbol,repo.as_of)
    quote=market_quote(snapshot,repo.cutoff)
    provider=provider_metrics(snapshot)
    provider_refs=[SourceReference.model_validate(s) for s in snapshot['sources']] if snapshot else []
    unit='tỷ đồng' if review else 'giá trị nguồn / 10^9'
    facts=load_supplement(settings,symbol,repo.cutoff)
    source=SourceReference(source_name='DNSE hồ sơ doanh nghiệp',url=company['source_url'],retrieved_at=company['retrieved_at'])
    financial_refs=refs([data.fact(k,p).source for k in ('revenue','net_profit','assets','equity') for p in data.periods if data.fact(k,p)])
    price_ref=repo.price_source(symbol,bars) if bars else None
    number=lambda v,n=2:format_value(v,n)
    pct=lambda v:number(v)+'%' if v is not None else MISSING
    def measured(key,p):
        if ALIASES[key][0]=='BSheet' and p in data.invalid_balance_periods:return None
        return data.value(key,p)
    def flow(key,p):
        return data.quarter_value(key,p) if review else data.value(key,p)
    revenue=flow('revenue',period);profit=flow('net_profit',period)
    comparable=(period[0]-1,period[1])
    def growth(key):
        a=flow(key,period);b=flow(key,comparable)
        return (a/b-1)*100 if a is not None and b is not None and b>0 and review else None
    def basis_refs(keys,periods):
        return refs([data.fact(k,p).source for k in keys for p in periods if data.fact(k,p)])
    trade_rows=[]
    day=datetime.fromtimestamp(bars[-1]['ts'],VIETNAM).strftime('%d/%m/%Y') if bars else ''
    if quote:day=quote['timestamp'].astimezone(VIETNAM).strftime('%d/%m/%Y')
    if valuation['current'] is not None:
        trade_rows.append(('Giá thị trường (VND/cp)' if quote else 'Giá đóng cửa (VND/cp)',number(valuation['current'],0)))
    elif bars:
        trade_rows.append(('Giá đóng cửa gốc '+price_ref.source_name,number(bars[-1]['close'])+' (đơn vị nguồn)'))
    if bars and len(bars)>=30:
        trade_rows.append(('KLGD bình quân 30 phiên (cp)',number(sum(Decimal(str(r['volume'])) for r in bars[-30:])/30,0)))
    for n in (20,60):
        if len(bars)>n and bars[-n-1]['close']>0:
            trade_rows.append((f'Biến động {n} phiên',pct((Decimal(str(bars[-1]['close']))/Decimal(str(bars[-n-1]['close']))-1)*100)))
    if review and review.shares_outstanding:
        trade_rows.append(('Cổ phiếu lưu hành (triệu cp)',number(review.shares_outstanding/Decimal(10**6))))
    for m in valuation['metrics']:
        if m['value'] is not None and m['label']!='Giá tham chiếu chuẩn hóa':trade_rows.append((m['label']+' ('+m['unit']+')',number(m['value'])))
    if valuation['current'] is not None and review and review.shares_outstanding:
        trade_rows.append(('Vốn hóa (tỷ VND)',number(valuation['current']*review.shares_outstanding/Decimal(10**9))))
    cover_rows=[('Khuyến nghị',valuation['assessment'])]
    if valuation['target'] is not None:
        cover_rows.extend([('Giá mục tiêu (VND/cp)',number(valuation['target'],0)),('Tiềm năng',pct(valuation['upside']))])
    cover=block('KẾT LUẬN',('Nội dung','Giá trị'),cover_rows)
    trade=block('Giao dịch đến '+day,('Chỉ tiêu','Giá trị'),trade_rows,sources=refs([price_ref] if price_ref else [],
        [quote['source']] if quote else [],provider_refs,
        [review.source] if review else [],[s for s in review.verification_sources if 'cổ tức' in s.source_name] if review else []))
    thesis=[]
    for key,label in [('revenue','Doanh thu thuần'),('net_profit','LNST')]:
        value=flow(key,period);change=growth(key)
        if value is not None:
            thesis.append(note(f'{label} {period[0]}Q{period[1]} đạt {number(value/Decimal(10**9))} {unit}'+
                (f', tăng {pct(change)} cùng kỳ.' if change is not None else '.'),basis_refs((key,),(period,comparable))))
    if bars and len(bars)>=200:
        sma=sum(Decimal(str(r['close'])) for r in bars[-200:])/200
        thesis.append(note('Giá đóng cửa so với SMA200: '+pct((Decimal(str(bars[-1]['close']))/sma-1)*100)+
            '; tín hiệu mô tả, không phải khuyến nghị.',[price_ref]))
    if not thesis:thesis=[note('Báo cáo dữ kiện hiện có; các điều kiện định giá được trình bày riêng.')]
    conclusion=section(SectionKind.RECOMMENDATION,'Kết quả kinh doanh và điều kiện đầu tư',thesis,[cover,trade])

    # Keep factual profile, not full empty scaffolding or partial-share pies.
    profile_rows=[('Tên / sàn / mã',(company['company_name'] or symbol)+' / '+company['exchange']+' / '+symbol,'Danh mục')]
    metadata=json.loads(company.get('raw_json') or '{}')
    for key,label in [('listedDate','Ngày niêm yết'),('gicsSubIndustry','Phân ngành chi tiết')]:
        if key=='listedDate' and any(f.category=='history' and 'niêm yết' in f.label.lower() for f in facts):continue
        if key=='gicsSubIndustry' and metadata.get(key)==company['industry']['name']:continue
        if metadata.get(key):profile_rows.append((label,str(metadata[key]),'Danh mục DNSE'))
    profile_refs=[source]
    for category,limit in [('overview',3),('history',2),('shareholders',2),('subsidiaries',3),('segments',2)]:
        for f in [f for f in facts if f.category==category][:limit]:
            profile_rows.append((f.label,f.value,f.period or 'Theo công bố'));profile_refs.append(f.source)
    overview=section(SectionKind.COMPANY,'I. TỔNG QUAN DOANH NGHIỆP',[
        note('Các thông tin dưới đây giữ nguyên kỳ công bố; không xem tỷ lệ cổ đông cuối năm là tỷ lệ hiện tại.')],
        [block('Hồ sơ và cơ cấu công bố',('Nội dung','Giá trị / mô tả','Kỳ'),profile_rows,sources=refs(profile_refs))])
    operating=[f for f in facts if f.category=='operations']
    business_blocks=[]
    if operating:business_blocks=[block('Chỉ tiêu hoạt động theo mô hình doanh nghiệp',('Chỉ tiêu','Giá trị','Kỳ'),
        [(f.label,f.value,f.period or 'Theo công bố') for f in operating[:7]],sources=refs([f.source for f in operating[:7]]))]
    business=section(SectionKind.BUSINESS,'III. HOẠT ĐỘNG KINH DOANH',[
        note('Chuỗi giá trị: '+PROFILES[profile]['business']+' Đây là khung phân tích, không phải cơ cấu doanh thu đo lường.')],business_blocks)

    industry=company['industry'];sector_ref=repo.industry_source(industry)
    industry_snapshot=next((r for r in repo.snapshots() if r['sector_id']==industry['sector_id']),None)
    sector_blocks=[]
    if industry_snapshot:
        raw=json.loads(industry_snapshot['raw_json']);values=dict(zip(raw.get('priceVolatilityKey',[]),raw.get('priceVolatilityValue',[])))
        labels=[k for k in ('1d','7d','1m','3m','6m','1y','3y','5y') if isinstance(values.get(k),(float,int))]
        sr=SourceReference(source_name='DNSE biến động nhóm ngành',url='https://banggia.dnse.com.vn/v2/nganh/danh-muc-nganh/'+industry['slug'],retrieved_at=industry_snapshot['retrieved_at'])
        if labels:
            sector_blocks.append(ReportBlock(kind='chart',chart_type='bar',title='Biến động giá nhóm '+industry['name'],labels=tuple(labels),values=tuple(values[k] for k in labels),sources=(sr,),note='Giá trị gốc DNSE; chưa xác nhận đơn vị và phương pháp chỉ số. Nhóm GICS rộng không thay thế chỉ số phân ngành chi tiết.'))
            sector_blocks.append(block('Diễn biến nhóm GICS',('Kỳ',*labels),[('Giá trị gốc',*[number(values[k]) for k in labels])],sources=(sr,)))
    layout_path=settings.root/'config/company_report_layouts'/f'{symbol}.json'
    layout=json.loads(layout_path.read_text(encoding='utf-8')) if layout_path.exists() else {}
    observed=[repo.company(t) for t in layout.get('peer_symbols',[]) if t!=symbol]
    if observed:
        sector_blocks.append(block('Nhóm quan sát - không phải mẫu định giá',('Mã','Doanh nghiệp'),
            [(c['symbol'],c['company_name']) for c in observed],sources=(sector_ref,),
            note='Danh mục quan sát, chưa có bộ BCTC cùng kỳ đủ kiểm chứng để tính trung vị bội số.'))
    elif candidates:
        sector_blocks.append(block('Nhóm quan sát - không phải trung vị định giá',('Mã','Doanh nghiệp','Kỳ'),
            [(c['symbol'],c['company_name'],f'{d.periods[0][0]}Q{d.periods[0][1]}') for c,d,_ in candidates],sources=(sector_ref,),
            note='Không dùng bội số thiếu kiểm chứng hoặc khác mô hình để tính trung vị.'))
    sector=section(SectionKind.INDUSTRY,'II. NGÀNH VÀ BỐI CẢNH',[
        note('Phân ngành DNSE cấp 2 là nhóm rộng. Chỉ dùng nhóm quan sát được chọn rõ theo hoạt động; không tự chọn theo thứ tự bảng chữ cái.',[sector_ref])],sector_blocks)
    macro_rows=[];macro_refs=[]
    for code in ('NY.GDP.MKTP.KD.ZG','FP.CPI.TOTL.ZG'):
        series=sorted([r for r in repo.macro() if r['metric']==code],key=lambda r:r['period'])
        if series:
            r=series[-1];macro_rows.append((r['label'],r['period'],number(r['value'])+' '+r['unit']));macro_refs.append(SourceReference.model_validate(r['source']))
    current=[r for r in repo.macro_context() if r['metric'] in ('GDP_YOY','CPI_AVERAGE_YOY','IIP_YOY')]
    for r in current:
        macro_rows.append((r['label'],r['period_label'],number(r['value'])+r['unit']));macro_refs.append(SourceReference.model_validate(r['source']))
    macro=section(SectionKind.MACRO,'Bối cảnh cầu và chi phí',[
        note('Số năm và số 9 tháng giữ riêng kỳ, không chuyển thành dự phóng '+symbol+'. '+PROFILES[profile]['channels'][0])],
        [block('Vĩ mô theo đúng kỳ công bố',('Chỉ tiêu','Kỳ','Giá trị'),macro_rows,sources=refs(macro_refs))] if macro_rows else [])

    summary=prune_table(annual_summary(repo,data,profile,repo.as_of))
    if summary:summary=summary.model_copy(update={'headers':(*summary.headers[:-1],summary.headers[-1]+' (QUÝ)'),
        'title':'KQKD và cân đối năm / quý ('+unit+', ROE/ROA: %)',
        'note':'Cột cuối là QUÝ, không phải năm. ROE/ROA năm dùng LNST / bình quân đầu-cuối năm; không thay bằng số công bố dùng vốn cuối kỳ.'})
    metrics=[m for m in financial_metrics(data,profile) if m['value'] is not None]
    if review and not review.cash_flow_quarters_comparable:
        cumulative_profit=sum((data.quarter_value('net_profit',(period[0],q)) for q in range(1,period[1]+1)),Decimal(0)) if all(data.quarter_value('net_profit',(period[0],q)) is not None for q in range(1,period[1]+1)) else None
        cfo=data.value('cfo',period)
        if cfo is not None and cumulative_profit and cumulative_profit>0:
            metrics.append(dict(label='CFO / LNST lũy kế',value=cfo/cumulative_profit,unit='lần',
                formula='CFO lũy kế / LNST cùng kỳ lũy kế; không trừ hai bản khác lần điều chỉnh',
                sources=basis_refs(('cfo','net_profit'),[(period[0],q) for q in range(1,period[1]+1)])))
    metric_table=block('Các chỉ tiêu tài chính',('Chỉ tiêu','Giá trị','Cơ sở'),
        [(m['label'],number(m['value'])+('' if m['unit']=='%' else ' ')+m['unit'],m['formula']) for m in metrics],
        sources=refs([s for m in metrics for s in m['sources']]))
    financial=section(SectionKind.FINANCIAL,'IV. TÌNH HÌNH TÀI CHÍNH',[
        note('Số năm giữ riêng với số quý; trạng thái kiểm toán/soát xét chỉ xác nhận theo văn bản gốc. '+
            ('Số quý đã có hồ sơ đối chiếu đơn vị và phạm vi.' if review else 'Giá trị nguồn được trình bày sơ bộ; không gắn nhãn đã kiểm chứng.'),financial_refs)],
        [b for b in (summary,metric_table if metrics else None) if b])
    appendix_blocks=[]
    for offset in (4,0):
        periods=list(reversed(data.periods[offset:offset+4]))
        if not periods:continue
        keys=profile_financial_keys(profile)
        rows=[];row_refs=[]
        for key in keys:
            vals=[measured(key,p) for p in periods]
            if all(v is None for v in vals):continue
            rows.append((LABELS[key],*[number(v/Decimal(10**9)) if v is not None else MISSING for v in vals]))
            row_refs.extend(data.fact(key,p).source for p in periods if data.fact(key,p))
        if not rows:continue
        appendix_blocks.append(block('Cửa sổ BCTC: '+', '.join(f'{y}Q{q}' for y,q in periods)+' ('+unit+')',
            ('Chỉ tiêu',*[f'{y}Q{q}' for y,q in periods]),rows,sources=refs(row_refs),
            note='KQKD: '+('quý riêng' if review and review.income_basis=='quarter' else 'theo nguồn')+'; cân đối: cuối kỳ; CFO: lũy kế từ đầu năm nếu đã đối chiếu.'))
    periods=list(reversed(data.periods));chart_refs=basis_refs(('revenue','net_profit'),periods)
    if any(flow('revenue',p) is not None for p in periods):
        appendix_blocks.insert(0,ReportBlock(kind='chart',chart_type='bar',title=f'Doanh thu/thu nhập và LNST trong {len(periods)} kỳ quan sát',
            labels=tuple(f'{y}Q{q}' for y,q in periods),values=tuple(float(flow('revenue',p)/Decimal(10**12)) if flow('revenue',p) is not None else None for p in periods),
            series=(('LNST',tuple(float(flow('net_profit',p)/Decimal(10**12)) if flow('net_profit',p) is not None else None for p in periods)),),
            sources=chart_refs,note=('Nghìn tỷ đồng; quý riêng.' if review and review.income_basis=='quarter' else 'Giá trị nguồn / 10^12; chưa xác nhận quý riêng/lũy kế.')+' Thu nhập: xanh dương; LNST: xanh lá. Không lấy giá trị năm thay quý IV.'))
    appendix=section(SectionKind.APPENDIX,'VIII. DỮ LIỆU QUÝ VÀ PHƯƠNG PHÁP',[
        note(('Kỳ mới nhất '+f'{period[0]}Q{period[1]}'+': '+review.period_disclosures.get(f'{period[0]}Q{period[1]}','')+
            ' Các kỳ còn lại giữ trạng thái công bố theo hồ sơ từng kỳ; không mặc định quý IV đã kiểm toán.'
            ) if review and review.period_disclosures else 'Các bảng giữ kỳ tài chính thực tế.',financial_refs)],appendix_blocks)

    technical_blocks=[];technical_findings=[]
    if bars:
        closes=[Decimal(str(r['close'])) for r in bars];multiplier=review.price_multiplier if review and review.price_multiplier else Decimal(1)
        series=[];sma_rows=[]
        for n in (20,50,200):
            smas=tuple(float(sum(closes[i-n+1:i+1])/n*multiplier) if i>=n-1 else None for i in range(len(closes)))
            series.append((f'SMA{n}',smas))
            if len(closes)>=n:
                average=sum(closes[-n:])/n;sma_rows.append((f'SMA{n}',number(average*multiplier),pct((closes[-1]/average-1)*100)))
        technical_blocks=[ReportBlock(kind='chart',title='Giá đóng cửa cùng SMA20, SMA50 và SMA200',
            labels=tuple(datetime.fromtimestamp(r['ts'],VIETNAM).strftime('%d/%m/%y') for r in bars),
            values=tuple(float(v*multiplier) for v in closes),series=tuple(series),sources=(price_ref,),
            note=('VND/cp.' if review and review.price_multiplier is not None else 'Đơn vị giá gốc '+price_ref.source_name+'; không dùng chuỗi này suy ra VND/cp.')+' Không phải tổng lợi suất; chưa kiểm chứng điều chỉnh cổ tức/chia tách.'),
            block('Đối chiếu xu hướng',('Mốc','SMA','Giá so với SMA'),sma_rows,sources=(price_ref,))]
        technical_findings=[note('Đường SMA mô tả vị trí giá; không suy ra quyết định mua/bán từ phân tích kỹ thuật.')]
    technical=section(SectionKind.TECHNICAL,'GIÁ VÀ GIAO DỊCH',technical_findings,technical_blocks)

    blockers=[]
    if annual_issues:blockers.append(('BCTC năm - số nguồn bất thường',', '.join(f'{y}: {LABELS[k]}' for y,k in annual_issues)+'; cần đối chiếu văn bản gốc, không tự đổi đơn vị.'))
    if data.invalid_balance_periods:blockers.append(('Dữ liệu cân đối','Các kỳ không khớp: '+', '.join(f'{y}Q{q}' for y,q in sorted(data.invalid_balance_periods))))
    if valuation['current'] is None:blockers.append(('Giá thị trường','Cần giá VND/cp có thời điểm và nhãn đơn vị nguồn.'))
    if not review or not review.shares_outstanding:blockers.append(('Cổ phiếu','Cần số cổ phiếu lưu hành sau các hành động doanh nghiệp.'))
    if not review or not review.notes_reviewed:blockers.append(('Thuyết minh','Cần hoàn tất đối chiếu chính sách kế toán, giao dịch và nghĩa vụ; chỉ tiêu nguồn không thay thế rà soát thuyết minh.'))
    if not scenarios:
        financial_model=profile in ('banking','securities','other_financial')
        blockers.extend([('Dự phóng theo mô hình',PROFILES[profile]['questions'][0]+' Kế hoạch doanh nghiệp không phải dự phóng của chuyên viên.'),
            ('Chi phí vốn / giả định định giá','Ke và g, ROE/BVPS dự phóng có căn cứ.' if financial_model else 'Dòng tiền/NAV, chi phí vốn và g có căn cứ theo phương pháp.'),
            ('So sánh và kịch bản','Cần nhóm cùng mô hình, độ nhạy và ba kịch bản có chiều giảm; không tự đặt bội số mục tiêu.')])
    else:
        blockers.extend((c['label'],'Chưa đạt kiểm tra phát hành') for c in valuation['checks'] if not c['passed'])
    pending=block('Dữ liệu / điều kiện còn thiếu',('Nhóm','Cần hoàn thiện'),blockers or [('Kiểm tra phát hành','Các điều kiện bắt buộc đã đạt')])
    known=[]
    if valuation['metrics']:
        known.append(block('Số liệu định giá tính được',('Chỉ tiêu','Giá trị','Cơ sở'),
            [(m['label'],number(m['value'])+' '+m['unit'],m['formula']) for m in valuation['metrics']],
            sources=refs(financial_refs,provider_refs,[review.source] if review else [])))
    if provider:
        visible=[m for m in provider if not m['label'].startswith(('EPS pha loãng','Cổ phiếu niêm yết'))]
        known.append(block('Chỉ tiêu định giá do nguồn tổng hợp',('Chỉ tiêu','Giá trị'),
            [(m['label'],number(m['value'],0 if m['unit']=='cp' else 2)+' '+m['unit']) for m in visible],sources=provider_refs))
    extra=[]
    if snapshot:
        extra.append(note((snapshot.get('fundamental_period') or 'Chỉ tiêu nguồn chưa nêu kỳ')+'. Ảnh chụp khi tải; không có ngày công bố riêng cho từng bội số. Không dùng bội số nguồn làm bội số mục tiêu.',provider_refs))
        shares=next((m['value'] for m in provider if m['label']=='Cổ phiếu lưu hành theo nguồn'),None)
        if review and review.shares_outstanding and shares is not None and shares!=review.shares_outstanding:
            extra.append(note('Cổ phiếu nguồn '+number(shares,0)+' khác hồ sơ doanh nghiệp '+number(review.shares_outstanding,0)+'. Giữ hai cơ sở riêng; cần đối chiếu hành động vốn, không tự ghi đè.',provider_refs))
    detailed=[b for b in (prune_table(b) for b in valuation_blocks(valuation,profile,scenarios,review,repo,candidates,symbol,repo.as_of)) if b] if scenarios else []
    valuation_section=section(SectionKind.VALUATION,'VII. ĐỊNH GIÁ VÀ KHUYẾN NGHỊ',[
        note(valuation['assessment']+'. '+valuation['reason']),
        note(valuation_method_text(profile)),*extra],
        [*known,*detailed,pending])
    plans=[f for f in facts if f.category=='forecast_assumptions']
    prospects=section(SectionKind.PROSPECTS,'V. TRIỂN VỌNG',[
        note('Chỉ trình bày kế hoạch đã công bố; không tự kéo dài tăng trưởng lịch sử hoặc dùng giả định của doanh nghiệp khác.')],
        [block('Kế hoạch doanh nghiệp (không phải dự phóng)',('Nội dung','Giá trị','Kỳ'),[(f.label,f.value,f.period or '') for f in plans],sources=refs([f.source for f in plans]))] if plans else [])
    risk_facts=[f for f in facts if f.category=='risks']
    risks=section(SectionKind.RISKS,'VI. RỦI RO',[
        note(f.label+': '+f.value,[f.source]) for f in risk_facts[:3]] or [note(PROFILES[profile]['risks'][0])])
    warnings=compress_warnings([*data.warnings,*[w for w in risk_notes if not w.startswith('Tin tức')]])
    warnings.extend(f'BCTC năm {y}: {LABELS[k]} nguồn vượt 1.000 lần doanh thu cùng kỳ; tạm loại số bất thường, không tự chia đơn vị.' for y,k in annual_issues)
    warnings=['Nguồn có độ trễ và có thể điều chỉnh; ngày chốt không phải ngày phát sinh của tất cả chỉ tiêu.' if 'backtest' in w else w for w in warnings]
    if (not review or not review.notes_reviewed) and not any('thuyết minh' in w for w in warnings):
        warnings.append('Chưa hoàn tất đối chiếu toàn bộ thuyết minh; chưa phát hành khuyến nghị.')
    warnings.append('Dấu gạch trong bảng: chưa đủ dữ liệu hoặc không áp dụng, không phải số 0. Các khoảng trống được gom tại mục VII.')
    return ReportDocument(kind='stock',title=(company['company_name'] or symbol)+f' ({company["exchange"]}: {symbol}) - BÁO CÁO DOANH NGHIỆP',
        as_of=repo.as_of,symbol=symbol,company_name=company['company_name'],industry_id=industry['slug'],industry_name=industry['name'],
        financial_period=f'{period[0]}Q{period[1]}',assessment=valuation['assessment'],data_quality=tuple(dict.fromkeys(warnings)),
        template_version=VERSION,cover_blocks=(cover,trade),
        sections=(conclusion,overview,sector,macro,business,financial,prospects,risks,valuation_section,appendix,technical))

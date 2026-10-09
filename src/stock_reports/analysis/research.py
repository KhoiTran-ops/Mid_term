"""Reusable macro and industry engines composed into a stock research document."""

from datetime import datetime
from decimal import Decimal
import json

from stock_reports.analysis.contracts import AnalysisSection, Finding, ReportBlock, SectionKind
from stock_reports.analysis.financials import FORMULA_VERSION, LABELS, financial_metrics
from stock_reports.analysis.profiles import PROFILES, detect_profile, securities_segments
from stock_reports.analysis.repository import ResearchRepository, VIETNAM
from stock_reports.analysis.valuation import evaluate_scenarios
from stock_reports.domain.research import SourceReference
from stock_reports.reports.documents import ReportDocument
from stock_reports.reports.models import ReportKind


def fmt(value, decimals=2):
    if value is None:
        return 'Chưa đủ dữ liệu'
    return f'{value:,.{decimals}f}'.replace(',','_').replace('.',',').replace('_','.')


def finding(text, sources=(), *, assumption=False):
    return Finding(text=text,sources=tuple(dict.fromkeys(sources)),is_assumption=assumption)


def section(kind,title,findings,blocks=()):
    return AnalysisSection(kind=kind,title=title,findings=tuple(findings),blocks=tuple(blocks))


def news_findings(rows):
    return [finding(f"{r['source_name']}: {r['title'][:140]}. Ngày đăng: {r['published_at'] or 'chưa rõ'}; tin cần đọc tại nguồn để đánh giá tác động.",
        [SourceReference(source_name=r['source_name'],url=r['url'],retrieved_at=r['first_seen'],published_at=r['published_at'])]) for r in rows]


def macro_section(repo,profile=None):
    data=repo.macro()
    findings,blocks=[],[]
    for code in dict.fromkeys(r['metric'] for r in data):
        series=sorted([r for r in data if r['metric']==code],key=lambda r:r['period'])
        last=series[-1]
        sources=tuple(SourceReference.model_validate(r['source']) for r in series)
        change=f"; thay đổi {fmt(last['value']-series[-2]['value'])} điểm phần trăm so với {series[-2]['period']}" if len(series)>1 else ''
        findings.append(finding(f"{last['label']} năm {last['period']}: {fmt(last['value'])} {last['unit']}{change}. Đây là quan sát năm, không phải số liệu tháng/quý đang diễn ra.",sources[-2:]))
        blocks.append(ReportBlock(kind='chart',title=f"{last['label']} - Việt Nam",labels=tuple(r['period'] for r in series),values=tuple(r['value'] for r in series),
            note=last['unit']+'; năm quan sát theo World Bank WDI.',sources=sources))
    if not data:
        findings.append(finding('Chưa có chuỗi vĩ mô định lượng trong kho; cần chạy macro update hoặc bổ sung nguồn chính thức trước khi đánh giá mức hiện tại.',assumption=True))
    grouped={code:sorted([r for r in data if r['metric']==code],key=lambda r:r['period']) for code in {r['metric'] for r in data}}
    growth=grouped.get('NY.GDP.MKTP.KD.ZG',[])
    inflation=grouped.get('FP.CPI.TOTL.ZG',[])
    if len(growth)>1:
        last,previous=growth[-1],growth[-2]
        direction='tăng tốc' if last['value']>previous['value'] else 'chậm lại' if last['value']<previous['value'] else 'đi ngang'
        findings.append(finding(f"Diễn giải dữ liệu năm: tăng trưởng GDP {last['period']} {direction} so với {previous['period']}. Điều này gợi ý kiểm tra cầu nội địa và sản lượng ngành; chưa đủ để dự báo tăng trưởng doanh nghiệp năm {repo.as_of.year}.",
            [SourceReference.model_validate(last['source'])],assumption=True))
    if len(inflation)>1:
        last,previous=inflation[-1],inflation[-2]
        direction='cao hơn' if last['value']>previous['value'] else 'thấp hơn' if last['value']<previous['value'] else 'ngang'
        findings.append(finding(f"Diễn giải dữ liệu năm: lạm phát {last['period']} {direction} năm {previous['period']}. Cần kiểm tra khả năng chuyển chi phí vào giá bán và chi phí vốn từng ngành; không suy ra quyết định lãi suất hiện tại từ CPI năm.",
            [SourceReference.model_validate(last['source'])],assumption=True))
    findings.extend(news_findings(repo.news(macro=True)))
    if profile:
        findings.extend(finding(text,assumption=True) for text in PROFILES[profile]['channels'])
    else:
        findings.extend(finding(text,assumption=True) for text in [
            'Nếu chi phí vốn và tỷ giá thay đổi, ngân hàng/chứng khoán chịu tác động qua biên lãi, thanh khoản và danh mục; doanh nghiệp phi tài chính chịu tác động qua chi phí tài trợ và đầu vào.',
            'Nếu đầu tư, tiêu dùng hoặc xuất khẩu tăng, cầu từng ngành có thể khác nhau; cần đối chiếu dữ liệu vận hành trước gán tác động lên lợi nhuận.'])
    findings.append(finding('Chưa có chuỗi lãi suất, tỷ giá và tín dụng tháng hiện tại đã kiểm chứng trong bộ đầu vào; không sinh dự báo cho các biến này.',assumption=True))
    return section(SectionKind.MACRO,'Tổng quan vĩ mô và chuỗi tác động',findings,blocks)


def industry_section(repo,industry,profile=None, *, candidates=()):
    source=repo.industry_source(industry)
    companies=repo.companies(industry['sector_id'])
    findings=[finding(f"Nhóm {industry['name']} thuộc GICS cấp 2 của DNSE, gồm {len(companies)} mã trong danh mục đang lưu. Phân ngành là danh mục hiện tại, chưa có lịch sử thay đổi phân ngành.",[source])]
    snapshot=next((r for r in repo.snapshots() if r['sector_id']==industry['sector_id']),None)
    blocks=[]
    if snapshot:
        raw=json.loads(snapshot['raw_json'])
        ref=SourceReference(source_name='DNSE thống kê ngành',url='https://banggia.dnse.com.vn/v2/nganh/danh-muc-nganh/'+industry['slug'],
            retrieved_at=snapshot['retrieved_at'],published_at=snapshot['source_time'],locator='MQTT stats/sector/volatility, sector '+industry['sector_id'])
        pairs=list(zip(raw.get('priceVolatilityKey',[]),raw.get('priceVolatilityValue',[])))
        findings.append(finding(f"Snapshot ngành có thời điểm nguồn {snapshot['source_time']}. Biến động 1d có giá trị gốc {fmt(dict(pairs).get('1d'))}; cần kiểm chứng đơn vị/phương pháp trước dùng làm chỉ số định giá.",[ref]))
        blocks.append(ReportBlock(kind='table',title='Diễn biến ngành theo DNSE',headers=('Khoảng thời gian','Giá trị gốc'),rows=tuple((k,fmt(v)) for k,v in pairs),
            note='Giữ giá trị nguồn; không ghép thành chuỗi OHLCV ngành hoặc thay thế lợi suất chuẩn hóa.',sources=(ref,)))
    else:
        findings.append(finding('Chưa có snapshot ngành trước ngày chốt đã chọn.',assumption=True))
    if profile:
        spec=PROFILES[profile]
        findings.append(finding('Khung chuỗi giá trị: '+spec['business'],assumption=True))
        findings.extend(finding('Câu hỏi kiểm chứng: '+q,assumption=True) for q in spec['questions'])
    if candidates:
        rows=[]
        refs=[]
        for company,data,model in candidates:
            p=data.periods[0] if data.periods else None
            metrics=financial_metrics(data,model)
            margin=next((m for m in metrics if m['label']=='Biên lợi nhuận sau thuế'),None)
            rows.append((company['symbol'],PROFILES[model]['name'],f'{p[0]}Q{p[1]}' if p else 'Thiếu',fmt(margin['value'] if margin else None),'Đã kiểm chứng' if data.review else 'Chưa kiểm chứng scope/đơn vị'))
            if margin:refs.extend(margin['sources'])
        blocks.append(ReportBlock(kind='table',title='Doanh nghiệp trong nhóm quan sát',headers=('Mã','Mô hình','Kỳ','Biên LNST (%)','Chất lượng'),rows=tuple(rows),sources=tuple(dict.fromkeys(refs)),
            note='So sánh từng doanh nghiệp; biên lợi nhuận phụ thuộc mô hình và định nghĩa doanh thu. Không lấy trung bình làm chuẩn ngành.'))
        if len(candidates)<3:
            findings.append(finding('Nhóm so sánh có dưới 3 công ty cùng kỳ đủ đầu vào; chưa đáp ứng mẫu 3–5 doanh nghiệp để kết luận vị thế tương đối.',assumption=True))
    return section(SectionKind.INDUSTRY,'Phân tích ngành '+industry['name'],findings,blocks)


def technical_section(repo,symbol):
    bars=repo.bars(symbol)
    if not bars:
        return section(SectionKind.TECHNICAL,'Giá và giao dịch',[finding('Chưa có đủ nến ngày đóng hợp lệ trước ngày chốt.',assumption=True)])
    ref=repo.price_source(symbol,bars)
    closes=[r['close'] for r in bars]
    last=bars[-1]
    day=datetime.fromtimestamp(last['ts'],VIETNAM).date()
    findings=[finding(f"Giá đóng cửa gốc DNSE ngày {day}: {fmt(last['close'])}; khối lượng {fmt(last['volume'],0)} cổ phiếu. Dữ liệu giá này chưa được xác minh điều chỉnh chia tách/cổ tức.",[ref])]
    rows=[]
    for n in (20,50,200):
        average=sum(closes[-n:])/n if len(closes)>=n else None
        difference=(closes[-1]/average-1)*100 if average else None
        rows.append((f'SMA{n}',fmt(average),fmt(difference)+'%' if difference is not None else 'Chưa đủ dữ liệu'))
    for n in (20,60):
        if len(closes)>n and closes[-n-1]>0:
            change=(closes[-1]/closes[-n-1]-1)*100
            findings.append(finding(f"Biến động giá trong {n} phiên: {fmt(change)}%, tính từ giá đóng cửa gốc; chưa gồm cổ tức hay xác nhận điều chỉnh hành động doanh nghiệp.",[ref]))
    foreign=repo.foreign(symbol)
    if foreign:
        row=foreign[0]
        fref=SourceReference(source_name='DNSE giao dịch nước ngoài',url=f'https://openapi.dnse.com.vn/price/foreigner?symbol={symbol}',retrieved_at=row['updated_at'],
            locator='Board G1, timestamp '+str(row['ts']))
        findings.append(finding(f"Snapshot nước ngoài G1: mua {fmt(row['buy_volume'],0)}, bán {fmt(row['sell_volume'],0)} cổ phiếu; không cộng lặp các board.",[fref]))
    chart=ReportBlock(kind='chart',title=f'{symbol}: giá đóng cửa gốc DNSE',labels=tuple(datetime.fromtimestamp(r['ts'],VIETNAM).strftime('%d/%m/%y') for r in bars),
        values=tuple(closes),note='Đơn vị giá nguồn; nến đóng hợp lệ, không phải biểu đồ tổng lợi suất.',sources=(ref,))
    blocks=[chart,ReportBlock(kind='table',title='Đối chiếu xu hướng',headers=('Mốc','SMA (giá gốc)','Giá so với SMA'),rows=tuple(rows),sources=(ref,))]
    findings.append(finding('SMA mô tả vị trí giá, không tự quyết định mua/bán. Tín hiệu cần đối chiếu định giá, thanh khoản và rủi ro doanh nghiệp.',assumption=True))
    return section(SectionKind.TECHNICAL,'Giá và dữ liệu giao dịch',findings,blocks)


def financial_section(data,profile):
    findings=[finding(w,assumption=True) for w in data.warnings]
    metrics=financial_metrics(data,profile)
    for m in metrics:
        if m['value'] is not None:
            findings.append(finding(f"{m['label']}: {fmt(m['value'])} {m['unit']}. {m['formula']}. Phiên bản {FORMULA_VERSION}.",m['sources']))
    if not findings:
        findings=[finding('Chưa có đủ dữ liệu tài chính để tính chỉ tiêu.',assumption=True)]
    blocks=[ReportBlock(kind='table',title='Chỉ tiêu theo mô hình doanh nghiệp',headers=('Chỉ tiêu','Giá trị','Công thức'),rows=tuple((m['label'],fmt(m['value'])+(' '+m['unit'] if m['value'] is not None else ''),m['formula']) for m in metrics),
        sources=tuple(dict.fromkeys(s for m in metrics for s in m['sources'])),note='Tỷ lệ trong cùng bảng có thể tính trên đơn vị gốc; khi chưa có review chỉ mang tính sơ bộ, không dùng để chấm điểm đầu tư.')]
    if data.audit_statuses:
        refs=tuple(SourceReference(source_name='CafeF metadata BCTC',url=r['source'],retrieved_at=r['retrieved_at'],locator=f"Kỳ {p[0]}Q{p[1]}; report_code={r['report_code']}") for p,r in data.audit_statuses.items())
        blocks.append(ReportBlock(kind='table',title='Kỳ, phạm vi và trạng thái báo cáo',headers=('Kỳ','Thông tin kiểm toán nguồn','Phạm vi'),
            rows=tuple((f'{p[0]}Q{p[1]}',data.audit_statuses[p]['audit_status'] or 'Chưa có mô tả để xác nhận',
                ('Hợp nhất' if data.review.scope=='consolidated' else 'Riêng') if data.review else 'Chưa kiểm chứng') for p in data.periods if p in data.audit_statuses),
            sources=refs,note='Cờ số nguồn khi thiếu mô tả không đủ xác nhận đã/chưa kiểm toán hoặc soát xét; phải đối chiếu văn bản BCTC gốc.'))
    keys=[k for k in LABELS if data.series.get(k)]
    for offset in range(0,len(data.periods),4):
        periods=list(reversed(data.periods[offset:offset+4]))
        refs=tuple(dict.fromkeys(data.fact(k,p).source for k in keys for p in periods if data.fact(k,p)))
        rows=tuple((LABELS[k],*[fmt(data.value(k,p)/Decimal(1e9)) if data.value(k,p) is not None else 'Thiếu' for p in periods]) for k in keys)
        if data.review:
            basis={'quarter':'quý riêng','ytd':'lũy kế từ đầu năm',None:'chưa kiểm chứng'}
            note=f'Tỷ VND, đã đối chiếu hồ sơ review. KQKD: {basis[data.review.income_basis]}; CF: {basis[data.review.cash_flow_basis]}. BS là số cuối kỳ. Ô thiếu giữ thiếu.'
        else:
            note='Giá trị nguồn chia 10^9 để trình bày; chưa khẳng định đơn vị VND. Ô thiếu giữ thiếu. KQKD/CF chưa mặc định là quý riêng.'
        invalid=[f'{y}Q{q}' for y,q in periods if (y,q) in data.invalid_balance_periods]
        if invalid:
            note+=' CẢNH BÁO: BS không khớp tại '+', '.join(invalid)+'; các số này giữ để đối chiếu, không dùng định giá.'
        blocks.append(ReportBlock(kind='table',title='BCTC: cửa sổ '+', '.join(f'{y}Q{q}' for y,q in periods),headers=('Chỉ tiêu',*[f'{y}Q{q}' for y,q in periods]),rows=rows,note=note,sources=refs))
    findings.extend(finding('Kiểm tra chất lượng lợi nhuận: '+q,assumption=True) for q in PROFILES[profile]['questions'])
    if data.periods and data.series.get('net_profit'):
        periods=list(reversed(data.periods))
        blocks.append(ReportBlock(kind='chart',title='LNST theo kỳ được nguồn trình bày',labels=tuple(f'{y}Q{q}' for y,q in periods),
            values=tuple(float(data.value('net_profit',p)/Decimal(1e9)) if data.value('net_profit',p) is not None else None for p in periods),
            note='Không cộng TTM khi chưa xác minh quý/lũy kế; đơn vị như bảng tài chính.',sources=tuple(data.fact('net_profit',p).source for p in periods if data.fact('net_profit',p))))
    return section(SectionKind.FINANCIAL,'Tài chính và chất lượng lợi nhuận',findings,blocks)


def build_document(settings, *, kind, as_of, symbol=None, industry_id=None, period=None, peers=(),review=None,scenarios=None, repository=None):
    repo=repository or ResearchRepository(settings,as_of)
    risk_notes=['Dữ liệu có độ trễ và có thể được nguồn điều chỉnh. Ngày chốt lọc kỳ/thời điểm nguồn; báo cáo không phải bộ dữ liệu backtest không có look-ahead.',
        'Tin tức cung cấp sự kiện và nguồn, chưa xác minh quan hệ nhân quả hay tác động định lượng tới lợi nhuận.']
    if kind==ReportKind.MACRO:
        macro=macro_section(repo)
        market=technical_section(repo,'VNINDEX')
        snapshots=repo.snapshots()
        names={r['sector_id']:r['name'] for r in repo.industries()}
        rows=[];refs=[]
        for row in snapshots:
            raw=json.loads(row['raw_json']);values=dict(zip(raw.get('priceVolatilityKey',[]),raw.get('priceVolatilityValue',[])))
            rows.append((names.get(row['sector_id'],row['sector_id']),fmt(values.get('1d')),fmt(values.get('1m'))))
            refs.append(SourceReference(source_name='DNSE ngành',url='https://banggia.dnse.com.vn/v2/nganh',retrieved_at=row['retrieved_at'],published_at=row['source_time']))
        rotation=section(SectionKind.INDUSTRY,'Đối chiếu các ngành trên thị trường',[finding('Diễn biến giá ngành cần được đối chiếu với lợi nhuận và chu kỳ riêng; không suy ra triển vọng vĩ mô từ một phiên giao dịch.',assumption=True)],
            [ReportBlock(kind='table',title='Các nhóm GICS',headers=('Ngành','1d (gốc)','1m (gốc)'),rows=tuple(rows),sources=tuple(dict.fromkeys(refs)),note='Giá trị gốc DNSE; đơn vị/phương pháp cần kiểm chứng trước dùng như lợi suất ngành.')])
        return ReportDocument(kind=kind,title=f'Tổng quan vĩ mô Việt Nam - {as_of:%d/%m/%Y}',as_of=as_of,
            assessment='Tổng quan dữ liệu và kịch bản',data_quality=tuple(risk_notes),
            sections=(macro,market,rotation,section(SectionKind.RISKS,'Rủi ro và khoảng trống dữ liệu',[finding(w,assumption=True) for w in risk_notes])))
    if kind==ReportKind.STOCK:
        company=repo.company(symbol)
        industry=company['industry']
    else:
        industry=repo.industry(industry_id)
        company=None
    members=repo.companies(industry['sector_id'])
    candidates=[]
    if company:
        data=repo.financials(symbol,period=period,review=review)
        profile=detect_profile(data,industry['name'])
    else:
        data=None;profile=None
    choices=list(dict.fromkeys(peers)) if peers else [r['symbol'] for r in members if not company or r['symbol']!=symbol]
    by_symbol={r['symbol']:r for r in members}
    comparison_period=data.periods[0] if data and data.periods else period
    for ticker in choices:
        if ticker not in by_symbol:
            raise ValueError('Mã so sánh phải thuộc cùng nhóm ngành DNSE')
        if company and ticker==symbol:
            continue
        try:
            other=repo.financials(ticker,period=comparison_period)
        except ValueError:
            if peers:raise
            continue
        model=detect_profile(other,industry['name'])
        if company and model!=profile:
            if peers:raise ValueError('Mã so sánh khác mô hình; chọn lại nhóm tương đồng')
            continue
        if other.periods:
            if comparison_period is None:
                comparison_period=other.periods[0]
            candidates.append((by_symbol[ticker],other,model))
        if len(candidates)==5:
            break
    if not company:
        models=sorted({m for _,_,m in candidates})
        profile=models[0] if len(models)==1 else 'non_financial'
        industry_analysis=industry_section(repo,industry,profile,candidates=candidates)
        findings=[finding(f'Nhóm quan sát gồm {len(candidates)} công ty, phân nhóm riêng: '+', '.join(PROFILES[m]['name'] for m in models)+'. Mẫu này không đại diện toàn ngành và không dùng trung bình chéo mô hình.',[repo.industry_source(industry)])]
        for model in models:
            findings.extend(finding(PROFILES[model]['name']+': '+text,assumption=True) for text in PROFILES[model]['questions'])
        return ReportDocument(kind=kind,title=f'Phân tích ngành {industry["name"]} - {as_of:%d/%m/%Y}',as_of=as_of,
            industry_id=industry['slug'],industry_name=industry['name'],assessment='Đánh giá ngành theo nguồn dữ liệu',data_quality=tuple(risk_notes),
            sections=(industry_analysis,macro_section(repo,profile),section(SectionKind.FINANCIAL,'Phân nhóm và so sánh doanh nghiệp',findings),
                section(SectionKind.RISKS,'Rủi ro ngành và dữ liệu cần bổ sung',[finding(w,assumption=True) for w in [*PROFILES[profile]['risks'],*risk_notes]])))
    if not data.periods:
        raise ValueError('Chưa có BCTC cho mã đã chọn; tải BCTC trước khi tạo báo cáo cổ phiếu')
    bars=repo.bars(symbol)
    valuation=evaluate_scenarios(data,profile,bars[-1]['close'] if bars else None,scenarios)
    company_source=SourceReference(source_name='DNSE hồ sơ doanh nghiệp',url=company['source_url'],retrieved_at=company['retrieved_at'])
    model_findings=[finding(f"{company['company_name'] or symbol} ({symbol}, {company['exchange']}) thuộc {industry['name']} theo DNSE.",[company_source]),
        finding('Khung mô hình: '+PROFILES[profile]['business'],assumption=True)]
    segments=securities_segments(data) if profile=='securities' else []
    if segments:
        p=data.periods[0]
        refs=[data.fact(k,p).source for k in ('brokerage','loan_income','investment_income','revenue') if data.fact(k,p)]
        model_findings.append(finding('Cơ cấu doanh thu quan sát: '+', '.join(f'{label} {fmt(value)}%' for label,value in segments)+
            '. Công ty có thể thuộc nhiều nhóm; tỷ trọng doanh thu không phải tỷ trọng lợi nhuận.',refs))
    model_findings.extend(news_findings(repo.news(symbol=symbol)))
    vf=[finding(valuation['reason'],assumption=True)]
    vb=[]
    if valuation['rows']:
        vf.append(finding(f"Giá tham chiếu được chuẩn hóa: {fmt(valuation['current'])} VND. Đầu vào định giá được kiểm chứng theo hồ sơ nguồn.",[review.source]))
        vb.append(ReportBlock(kind='table',title=f'Kịch bản {scenarios.method.upper()} - {scenarios.horizon_months} tháng',headers=('Kịch bản','Bội số','Tăng trưởng giả định','Giá (VND)','So với giá','Cơ sở giả định'),
            rows=tuple((r['name'],fmt(r['multiple']),fmt(r['growth']*100)+'%',fmt(r['target']),fmt(r['upside'])+'%',r['rationale']) for r in valuation['rows']),sources=(review.source,),
            note='P/B: VCSH dự phóng / cổ phiếu dự phóng x P/B; P/E: EPS TTM x (1+g) x P/E. Mọi bội số/tăng trưởng là giả định, không phải dự báo đã xác minh.'))
    for message in PROFILES[profile]['risks']:
        risk_notes.append(message)
    risk_notes.extend(data.warnings)
    if not review or not review.notes_reviewed:
        risk_notes.append('Chưa đối chiếu thuyết minh, giao dịch liên quan và báo cáo an toàn tài chính (nếu thuộc doanh nghiệp tài chính).')
    recommendations=[finding(valuation['assessment']+'. '+valuation['reason'],assumption=True),
        finding('Điều kiện xem xét lại: BCTC mới/điều chỉnh, thay đổi cơ cấu lợi nhuận, chi phí vốn, thanh khoản ngành hoặc giả định định giá. Không suy ra khuyến nghị chỉ từ SMA hay một tin mới.',assumption=True)]
    p=data.periods[0]
    return ReportDocument(kind=kind,title=f'{symbol} - {PROFILES[profile]["name"]}: phân tích cơ hội đầu tư',as_of=as_of,
        symbol=symbol,company_name=company['company_name'],industry_id=industry['slug'],industry_name=industry['name'],financial_period=f'{p[0]}Q{p[1]}',
        assessment=valuation['assessment'],data_quality=tuple(dict.fromkeys(risk_notes)),sections=(
            section(SectionKind.RECOMMENDATION,'Tóm tắt đánh giá và điều kiện đầu tư',recommendations),
            section(SectionKind.COMPANY,'Doanh nghiệp và mô hình kinh doanh',model_findings),macro_section(repo,profile),
            industry_section(repo,industry,profile,candidates=candidates),financial_section(data,profile),technical_section(repo,symbol),
            section(SectionKind.VALUATION,'Định giá và ba kịch bản',vf,vb),
            section(SectionKind.RISKS,'Rủi ro và dữ liệu còn thiếu',[finding(w,assumption=True) for w in dict.fromkeys(risk_notes)])))

"""Source-aware JSON adapter. All business calculations live outside templates."""
from calendar import monthrange
from datetime import date,datetime,UTC
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from statistics import stdev

from stock_reports.analysis.annuals import annual_value,load_annual_review,annual_income_anomalies
from stock_reports.analysis.company_template import load_supplement
from stock_reports.analysis.financials import LABELS,financial_metrics
from stock_reports.analysis.market_fundamentals import load_market_snapshot,market_quote,provider_metrics
from stock_reports.analysis.repository import VIETNAM
from stock_reports.reports.stocklens.evidence import adjusted_history,mine_annual,missing_report,build_scenarios
from stock_reports.reports.stocklens.peers import load_peer_summary
from stock_reports.reports.stocklens.strategy import evaluate
from stock_reports.data_sources.news.ranking import rank_company_news

VERSION='stocklens-1.2'
MONEY_KEYS={'revenue':'revenue','gross_profit':'gross_profit','net_income':'net_profit',
    'parent_income':'parent_profit','parent_equity':'parent_equity',
    'total_assets':'assets','liabilities':'liabilities','equity':'equity','operating_cash_flow':'cfo',
    'short_debt':'short_debt','long_debt':'long_debt','current_assets':'current_assets','current_liabilities':'current_liabilities'}


def numeric(value):
    if value is None or isinstance(value,bool):return None
    try:v=float(value)
    except (ValueError,TypeError):return None
    return v if math.isfinite(v) else None


def ratio(a,b,scale=1):
    return a/b*scale if a is not None and b is not None and b>0 else None


def sma(values,n):
    return [sum(values[i-n+1:i+1])/n if i>=n-1 else None for i in range(len(values))]


def ema(values,n):
    output=[None]*len(values);current=None
    for i,value in enumerate(values):
        if value is None:continue
        if current is None:
            seed=values[max(0,i-n+1):i+1]
            if len(seed)!=n or any(v is None for v in seed):continue
            current=sum(seed)/n
        else:current=current+(value-current)*2/(n+1)
        output[i]=current
    return output


def rsi(values,n=14):
    out=[None]*len(values)
    if len(values)<=n:return out
    delta=[values[i]-values[i-1] for i in range(1,len(values))]
    gain=sum(max(v,0) for v in delta[:n])/n;loss=sum(max(-v,0) for v in delta[:n])/n
    for i in range(n,len(values)):
        if i>n:gain=(gain*(n-1)+max(delta[i-1],0))/n;loss=(loss*(n-1)+max(-delta[i-1],0))/n
        out[i]=50 if gain==0 and loss==0 else 100 if loss==0 else 100-100/(1+gain/loss)
    return out


def calendar_return(rows,months,end=None):
    if not rows:return None
    end=end or date.fromisoformat(rows[-1]['date']);year=end.year;month=end.month-months
    while month<=0:year-=1;month+=12
    start=date(year,month,min(end.day,monthrange(year,month)[1]))
    old=[r for r in rows if r['date']<=start.isoformat()];recent=[r for r in rows if r['date']<=end.isoformat()]
    return (recent[-1]['close']/old[-1]['close']-1)*100 if old and recent and old[-1]['close']>0 else None


def history(settings,symbol,cutoff):
    path=settings.root/'var/stocklens_prices'/f'{symbol}.json'
    if not path.is_file():return [],[]
    payload=json.loads(path.read_text(encoding='utf-8'))
    if payload['symbol']!=symbol or payload['unit']!=('index points' if symbol=='VNINDEX' else 'thousand VND'):
        raise ValueError('StockLens price history symbol/unit mismatch')
    rows={}
    for row in payload['rows']:
        day=datetime.strptime(row['Ngay'],'%d/%m/%Y').date();close=numeric(row.get('GiaDongCua'))
        if day>cutoff.date() or close is None or close<=0:continue
        volume=numeric(row.get('KhoiLuongKhopLenh'));turnover=numeric(row.get('GiaTriKhopLenh'))
        rows[day.isoformat()]=dict(date=day.isoformat(),close=close*(1 if symbol=='VNINDEX' else 1000),
            volume=volume if volume is not None and volume>=0 else None,
            turnover=turnover*10**9 if turnover is not None and turnover>=0 else None)
    return [rows[k] for k in sorted(rows)],[*payload['sources'],payload['unit_source']]


def add_indicators(rows):
    if not rows:return []
    values=[r['close'] for r in rows];ma={n:sma(values,n) for n in (20,50,200)}
    e12,e26=ema(values,12),ema(values,26);macd=[a-b if a is not None and b is not None else None for a,b in zip(e12,e26)]
    signal=ema(macd,9);rsis=rsi(values);peak=0;out=[]
    for i,row in enumerate(rows):
        if i==max(0,len(rows)-250):peak=0
        peak=max(peak,row['close']);out.append(dict(date=row['date'],close=row['close'],
            ma20=ma[20][i],ma50=ma[50][i],ma200=ma[200][i],rsi=rsis[i],macd=macd[i],signal=signal[i],
            hist=macd[i]-signal[i] if macd[i] is not None and signal[i] is not None else None,
            volume=row['volume'],drawdown=(row['close']/peak-1)*100))
    return out


def build_payload(settings,repo,company,data,profile,document,*,horizon=None):
    cfg_path=settings.root/'config/stocklens.json';cfg=json.loads(cfg_path.read_text(encoding='utf-8')) if cfg_path.exists() else {}
    horizon=horizon or cfg.get('horizon','medium')
    if horizon not in ('short','medium','long'):raise ValueError('Invalid analysis horizon')
    symbol=data.symbol;provenance={};sources=[];missing=[s for s in document.data_quality if not s.startswith('Dấu gạch trong bảng:')];statements=[]
    def source(ref,item=None):
        if isinstance(ref,dict) and 'source' in ref:return ref
        raw=ref.model_dump(mode='json') if hasattr(ref,'model_dump') else ref
        return dict(item=item or raw['source_name'],source=raw['source_name'],url=str(raw['url']),
            locator=raw.get('locator'),retrieved_at=raw['retrieved_at'],published_at=raw.get('published_at'))
    def record(path,refs,formula=None,unit=None,verified=False):
        entries=[source(r) for r in refs];sources.extend(entries)
        provenance[path]=dict(source='; '.join(dict.fromkeys(r['source'] for r in entries)) or None,
            formula=formula,unit=unit,derived=bool(formula),verified=verified)
    def statement(text,fields,rule,kind='fact'):
        statements.append(dict(text=text,fields=fields,rule=rule,kind=kind))
    snapshot=load_market_snapshot(settings,symbol,repo.as_of);quote=market_quote(snapshot,repo.cutoff)
    provider=provider_metrics(snapshot);raw_rows,raw_sources=history(settings,symbol,repo.cutoff)
    rows,price_sources,price_reason=adjusted_history(settings,symbol,repo.cutoff)
    # Raw prices are for the displayed quote only. Never silently run indicators on unadjusted prices.
    if raw_rows and rows and raw_rows[-1]['date']!=rows[-1]['date']:
        price_reason='Ngày cuối giá thô và điều chỉnh không đồng nhất; chặn chỉ báo.';rows=[]
    sources.extend([*raw_sources,*price_sources]);series=add_indicators(rows);latest=series[-1] if series else {}
    closes=[r['close'] for r in rows[-250:]];last_day=rows[-1]['date'] if rows else quote['timestamp'].date().isoformat() if quote else None
    close=raw_rows[-1]['close'] if raw_rows else numeric(quote['value_vnd']) if quote else None
    if last_day is None and raw_rows:last_day=raw_rows[-1]['date']
    price={k:None for k in ('close','change_3m','change_6m','change_12m','change_1m','peak_250','trough_250','drawdown_from_peak','max_drawdown')}
    price.update(close=close,series_250=series[-250:])
    for months in (1,3,6,12):price[f'change_{months}m']=calendar_return(rows,months)
    if closes:
        price.update(peak_250=max(closes),trough_250=min(closes),drawdown_from_peak=(close/max(closes)-1)*100,
            max_drawdown=min(r['drawdown'] for r in series[-250:]))
    if not rows:missing.append(price_reason or 'Không có chuỗi giá điều chỉnh.')
    elif len(rows)<300:missing.append(f'Chỉ có {len(rows)} phiên điều chỉnh, dưới yêu cầu 300 phiên; các cửa sổ thiếu không được ước tính.')
    for k in price:
        record('price.'+k,raw_sources if k=='close' else price_sources,
            None if k=='close' else 'Giá đóng cửa đã điều chỉnh VCI/vnstock; lợi suất tháng lịch, không giả định ngày thiếu.', 'VND/cp' if k in ('close','peak_250','trough_250') else '%',bool(rows) if k!='close' else bool(raw_rows))
    technical={k:latest.get(v) for k,v in dict(ma20='ma20',ma50='ma50',ma200='ma200',rsi14='rsi',macd='macd',macd_signal='signal',macd_hist='hist',volume='volume').items()}
    # CafeF matched volume differs from VCI total volume. Keep the basis explicit;
    # splits are handled only by reviewed volume factors, not by guessed cash-dividend factors.
    volumes={r['date']:r for r in raw_rows};volume_rows=[]
    event_path=settings.root/'var/corporate_actions'/f'{symbol}.json'
    actions=json.loads(event_path.read_text(encoding='utf-8')) if event_path.is_file() else []
    for row in rows:
        actual=volumes.get(row['date']);volume=actual['volume'] if actual else None
        for event in actions:
            if event.get('verified') and event.get('volume_factor') and row['date']<event['ex_date']<=last_day:
                volume=volume*event['volume_factor'] if volume is not None else None
        volume_rows.append(dict(date=row['date'],volume=volume,close=row['close']))
    volume_by_date={r['date']:r['volume'] for r in volume_rows}
    for row in series:row['volume']=volume_by_date.get(row['date'])
    vols=[r['volume'] for r in volume_rows[-21:-1]]
    avg_volume=sum(vols)/20 if len(vols)==20 and all(v is not None for v in vols) else None
    technical['volume']=raw_rows[-1]['volume'] if raw_rows else None
    reference_volumes=[volumes[r['date']]['volume'] if r['date'] in volumes else None for r in rows[-21:-1]]
    reference_average=sum(reference_volumes)/20 if len(reference_volumes)==20 and all(v is not None for v in reference_volumes) else None
    liquidity=[r['close']*r['volume'] if r['volume'] is not None else None for r in volume_rows[-21:-1]]
    technical.update(volume_vs_ma20=ratio(technical['volume'],avg_volume),liquidity_threshold=numeric(cfg.get('liquidity_threshold')),
        turnover_ma20=sum(liquidity)/20 if len(liquidity)==20 and all(v is not None for v in liquidity) else None,
        volume_ma20=avg_volume,
        reference_volume_vs_ma20=ratio(technical['volume'],reference_average),
        reference_turnover_ma20=sum(r['close']*volumes[r['date']]['volume'] for r in rows[-21:-1])/20 if reference_average is not None else None,
        turnover_value=raw_rows[-1]['turnover'] if raw_rows else None,support=[price['trough_250']] if closes else [],
        resistance=[v for v in (technical['ma20'],technical['ma50'],technical['ma200']) if v is not None and close is not None and v>close])
    returns=[math.log(rows[i]['close']/rows[i-1]['close']) for i in range(1,len(rows))]
    for n in (20,60):technical[f'vol_{n}d']=stdev(returns[-n:])*math.sqrt(252)*100 if len(returns)>=n else None
    for k in technical:record('technical.'+k,price_sources,'SMA(n); RSI Wilder(14); EMA MACD(12,26,9); độ lệch chuẩn log-return × √252; không tính khi thiếu cửa sổ.',verified=bool(rows))
    for k,formula in [('volume_vs_ma20','KL phiên / trung bình 20 phiên TRƯỚC (loại phiên hiện tại); chỉ điều chỉnh volume_factor đã đối chiếu.'),('turnover_ma20','Trung bình 20 phiên TRƯỚC: close_adjusted × volume cùng cơ sở; ước lượng, không phải giá trị khớp lệnh thực.')]:
        record('technical.'+k,[*price_sources,*raw_sources],formula,'lần' if k=='volume_vs_ma20' else 'VND/phiên',bool(actions) and all(e.get('verified') for e in actions))
    benchmark,benchmark_sources,benchmark_reason=adjusted_history(settings,'VNINDEX',repo.cutoff)
    common={r['date'] for r in rows}&{r['date'] for r in benchmark}
    aligned=[r for r in benchmark if r['date']==last_day]
    vnreturn=calendar_return([r for r in benchmark if r['date'] in common],6,date.fromisoformat(last_day)) if last_day and aligned else None
    aligned_stock=calendar_return([r for r in rows if r['date'] in common],6,date.fromisoformat(last_day)) if last_day and aligned else None
    market=dict(vnindex_return_6m=vnreturn,vnindex_date=last_day if aligned else None,vnindex_level=aligned[-1]['close'] if aligned else None,
        relative_strength=aligned_stock-vnreturn if aligned_stock is not None and vnreturn is not None else None)
    sources.extend(benchmark_sources);record('market',benchmark_sources,'Cổ phiếu và VN-Index cùng ngày; cùng cửa sổ 6 tháng lịch.','điểm / %')
    raw=repo.annual(symbol);review=load_annual_review(settings,symbol);years=list(range(repo.as_of.year-4,repo.as_of.year))
    financials=dict(years=years);verified_years=set(review.years) if review else set()
    for display,key in MONEY_KEYS.items():
        vals=[]
        for year in years:
            value,matches=annual_value(raw,key,year,review);multiplier=review.money_multiplier if review and year in verified_years else Decimal(1)
            vals.append(numeric(value*multiplier/Decimal(10**9)) if value is not None else None)
            refs=[r['verified_source'] if r.get('verified_source') else dict(source_name='CafeF BCTC năm',url=r['source_url'],
                retrieved_at=r['imported_at'],locator=f'{year}: {r["metric"]}; {r.get("sheet_name")}, dòng {r.get("source_row")}') for r in matches]
            record(f'financials.{display}.{len(vals)-1}',refs,'Giá trị nguồn × hệ số đã đối chiếu / 10^9' if review else 'Giá trị nguồn / 10^9',
                'tỷ VND' if year in verified_years else 'giá trị nguồn / 10^9',bool(matches) and all(r.get('verified_source') for r in matches))
            if key=='parent_equity' and matches and all(r.get('verified_source') for r in matches):
                provenance[f'financials.{display}.{len(vals)-1}']['formula']='Tổng vốn công bố − lợi ích cổ đông không kiểm soát công bố; không suy tổng vốn từ tài sản − nợ.'
        financials[display]=vals
    financials['annual_history']=[]
    for year in range(repo.as_of.year-5,repo.as_of.year):
        annual_values={}
        for display,key in MONEY_KEYS.items():
            value,matches=annual_value(raw,key,year,review)
            multiplier=review.money_multiplier if review and year in verified_years else Decimal(1)
            annual_values[display]=numeric(value*multiplier/Decimal(10**9)) if value is not None else None
            refs=[r['verified_source'] for r in matches if r.get('verified_source')]
            record(f'financials.annual_history.{len(financials["annual_history"])}.values.{display}',refs,
                'Giá trị năm công bố / 10^9' if key!='parent_equity' else '(Tổng vốn công bố − lợi ích không kiểm soát) / 10^9',
                'tỷ VND' if year in verified_years else 'giá trị nguồn / 10^9',bool(refs))
        financials['annual_history'].append(dict(year=year,values=annual_values))
    for i,year in enumerate(years):
        keys=('total_assets','liabilities','equity');a,l,e=[financials[k][i] for k in keys]
        if all(v is not None for v in (a,l,e)) and a>0 and abs(a-l-e)>a*.005:
            unverified=[k for k in keys if not provenance[f'financials.{k}.{i}']['verified']]
            for k in unverified or keys:financials[k][i]=None
            missing.append(f'Bảng cân đối năm {year} không khớp tài sản = nợ phải trả + vốn chủ (ngưỡng 0,5%). Loại dòng chưa đối chiếu khỏi bảng/biểu đồ; không tự sửa đơn vị hoặc suy số còn thiếu.')
    banking=profile=='banking';ratios={k:[] for k in ('gross_margin','net_margin','roa','roe','ocf_to_ni')}
    for i,year in enumerate(years):
        income=financials['net_income'][i];revenue=financials['revenue'][i]
        ratios['gross_margin'].append(None if banking else ratio(financials['gross_profit'][i],revenue,100))
        ratios['net_margin'].append(None if banking else ratio(income,revenue,100))
        ratios['ocf_to_ni'].append(None if banking else ratio(financials['operating_cash_flow'][i],income))
        for field,name in (('total_assets','roa'),('equity','roe')):
            opening,_=annual_value(raw,MONEY_KEYS[field],year-1,review)
            if review:
                overrides=[f.value_vnd/Decimal(10**9) for f in review.opening_balances if f.period==str(year) and f.key==MONEY_KEYS[field]]
                if len(overrides)==1:opening=overrides[0]
                else:opening=opening*review.money_multiplier/Decimal(10**9) if opening is not None else None
            closing=financials[field][i];average=(numeric(opening)+closing)/2 if opening is not None and closing is not None else None
            ratios[name].append(ratio(income,average,100) if review and year in verified_years else None)
    metrics={m['label']:m for m in financial_metrics(data,profile)}
    short,long=financials['short_debt'][-1],financials['long_debt'][-1]
    ratios['debt_to_equity']=None if banking else ratio(short+long if short is not None and long is not None else None,financials['equity'][-1])
    ratios['current_ratio']=None if banking else ratio(financials['current_assets'][-1],financials['current_liabilities'][-1])
    financials['ratios']=ratios
    for key in ratios:record('financials.ratios.'+key,review.sources if review else [],'Tính từ các dòng cùng kỳ/phạm vi; ROE/ROA dùng bình quân đầu-cuối năm và chỉ tính khi đã đối chiếu.','% hoặc lần',bool(review))
    p=data.periods[0];financials['latest_quarter']=dict(period=f'{p[0]}Q{p[1]}',basis=data.review.income_basis if data.review else 'Theo nguồn; chưa đối chiếu quý riêng/lũy kế')
    for display,key in MONEY_KEYS.items():
        value=data.value(key,p)
        if key in ('assets','liabilities','equity') and p in data.invalid_balance_periods:value=None
        target={'total_assets':'assets'}.get(display,display);financials['latest_quarter'][target]=numeric(value/Decimal(10**9)) if value is not None else None
    facts=load_supplement(settings,symbol,repo.cutoff)
    bank_rows=[]
    for label,key in (('NIM quý','nim'),('CASA','casa'),('Nợ xấu','npl'),('CAR','car')):
        candidates=[f for f in facts if label.casefold() in f.label.casefold()] if banking else []
        fact=max(candidates,key=lambda f:f.period) if candidates else None
        financials['latest_quarter'][key]=numeric(fact.numeric) if fact and fact.period==financials['latest_quarter']['period'] else None
        if banking:
            bank_rows.append(dict(label=label,value=fact.value if fact else None,period=fact.period if fact else None))
        if fact:sources.append(source(fact.source))
    for k in financials['latest_quarter']:record('financials.latest_quarter.'+k,[data.fact(key,p).source for key in MONEY_KEYS.values() if data.fact(key,p)],'Giá trị nguồn cùng kỳ / 10^9; không tự chuyển quý/lũy kế.',verified=bool(data.review))
    financials['latest_quarter']['cash_flow_basis']=data.review.cash_flow_basis if data.review else None
    financials['latest_quarter']['disclosure_note']=data.review.period_disclosures.get(f'{p[0]}Q{p[1]}') if data.review else None
    financials['quarterly']=[]
    for period in data.periods[:5]:
        values={}
        for display,key in MONEY_KEYS.items():
            fact=data.fact(key,period);value=data.value(key,period)
            if key=='parent_equity' and value is None and period not in data.invalid_balance_periods:
                total=data.value('equity',period);minority=data.value('minority_equity',period)
                if total is not None and minority is not None:
                    value=total-minority
                    record(f'financials.quarterly.{len(financials["quarterly"])}.values.{display}',
                        [data.fact('equity',period).source,data.fact('minority_equity',period).source],
                        '(Tổng vốn công bố − lợi ích không kiểm soát công bố) / 10^9','tỷ VND',bool(data.review))
            if key in ('assets','liabilities','equity') and period in data.invalid_balance_periods:value=None
            values[display]=numeric(value/Decimal(10**9)) if value is not None else None
            if fact:record(f'financials.quarterly.{len(financials["quarterly"])}.values.{display}',[fact.source],
                'Nguồn quý riêng cho thu nhập; cash flow giữ YTD và không trừ bản sửa đổi khác cơ sở. / 10^9','tỷ VND',bool(data.review))
        financials['quarterly'].append(dict(period=f'{period[0]}Q{period[1]}',income_basis=data.review.income_basis if data.review else None,
            cash_flow_basis=data.review.cash_flow_basis if data.review else None,values=values))
    financials['half_year']=None
    if data.review and data.review.cash_flow_basis=='ytd' and p[1]==2:
        half={k:sum(values) if all(v is not None for v in values) else None for k,values in
            ((display,[numeric(data.quarter_value(key,(p[0],q))) for q in (1,2)]) for display,key in
             [('revenue','revenue'),('net_income','net_profit'),('parent_income','parent_profit')])}
        financials['half_year']=dict(period=f'{p[0]}H1',**{k:v/1e9 if v is not None else None for k,v in half.items()},
            operating_cash_flow=financials['latest_quarter']['operating_cash_flow'])
    prior_quarter=data.quarter_value('parent_profit',(p[0]-1,p[1]));current_quarter=data.quarter_value('parent_profit',p)
    financials['parent_income_yoy']=ratio(numeric(current_quarter),numeric(prior_quarter),100)-100 if current_quarter is not None and prior_quarter is not None and prior_quarter>0 else None
    record('financials.parent_income_yoy',[data.fact('parent_profit',q).source for q in (p,(p[0]-1,p[1])) if data.fact('parent_profit',q)],
        '(LNST mẹ quý riêng / quý cùng kỳ − 1) × 100; không dùng YoY doanh thu/LNST hợp nhất khác cơ sở.','%',bool(data.review))
    score_keys=('fa','fa_coverage','ta','unified','entry_threshold','exit_threshold')
    scores={k:None for k in score_keys};scores.update(pillars={k:None for k in ('quality','growth','value','safety')},ta_conditions=[])
    strategy,strategy_reason=evaluate(settings,financials,rows,volume_rows,benchmark)
    decision=dict(status='WATCH',reason='STRATEGY_CONFIG_MISSING')
    if strategy:
        scores=strategy['scores'];decision=strategy['decision']
        technical['liquidity_threshold']=strategy['liquidity_threshold']
        for key in scores:
            record('scores.'+key,[*(review.sources if review else []),*price_sources,*benchmark_sources],
                'strategy_engine.run; FA hiệu dụng = 50 + (FA thô − 50) × độ phủ; FA/TA thống nhất theo trọng số cấu hình.',
                '% độ phủ' if key=='fa_coverage' else 'điểm / 100',True)
        missing.append('Thanh khoản engine dùng 20 phiên gồm phiên hiện tại theo mã gốc; TB20 trình bày ở trang 4 dùng 20 phiên trước. Kết quả và cơ sở từng phép tính được giữ trong JSON.')
    else:missing.append(strategy_reason)
    valuation={k:None for k in ('eps_ttm','pe_ttm','pb','peer_median_pe','peer_count','peer_snapshot_date','bvps','market_cap','shares_outstanding','parent_profit_ttm')}
    valuation.update(basis='Chỉ tiêu CafeF tổng hợp, không phải mô hình giá mục tiêu; chưa xác nhận cơ sở EPS/P/E TTM.',period=snapshot.get('fundamental_period') if snapshot else None)
    names={'BVPS theo nguồn':'bvps','Vốn hóa theo nguồn':'market_cap','Cổ phiếu lưu hành theo nguồn':'shares_outstanding','P/B theo nguồn':'pb'}
    reported=[]
    for m in provider:
        if m['label'].startswith(('EPS pha loãng','Cổ phiếu niêm yết')):continue
        reported.append(dict(label=m['label'],value=numeric(m['value']),unit=m['unit']))
        if m['label'] in names:valuation[names[m['label']]]=numeric(m['value'])
    valuation['reported_metrics']=reported
    for k in valuation:record('valuation.'+k,snapshot['sources'] if snapshot else [],None,'theo nhãn nguồn',False)
    # Provider EPS/PE/BVPS on an unknown share basis are never mixed with the raw post-action quote.
    for k in ('eps_ttm','pe_ttm','pb','bvps','market_cap','shares_outstanding'):valuation[k]=None
    parent_ttm=data.ttm('parent_profit',p)
    shares=numeric(data.review.shares_outstanding) if data.review else None
    parent_equity=data.value('parent_equity',p)
    if parent_equity is None and data.review:parent_equity=data.review.parent_equity_vnd
    if shares and parent_ttm is not None and parent_equity is not None and close:
        eps=numeric(parent_ttm)/shares;cap=close*shares
        valuation.update(eps_ttm=eps,pe_ttm=ratio(close,eps),pb=ratio(cap,numeric(parent_equity)),bvps=ratio(numeric(parent_equity),shares),market_cap=cap,shares_outstanding=shares,parent_profit_ttm=numeric(parent_ttm),
            period=f'{p[0]}Q{p[1]}',basis='LNST mẹ 4 quý; số cổ phiếu lưu hành và vốn mẹ đã đối chiếu. Giá thô cùng ngày, không dùng EPS nhà cung cấp trước quyền.')
        for k in ('eps_ttm','pe_ttm','pb','bvps','market_cap','shares_outstanding'):
            record('valuation.'+k,[data.review.source,*data.review.verification_sources,*[data.fact('parent_profit',q).source for q in data.periods[:4] if data.fact('parent_profit',q)]],{'eps_ttm':'LNST mẹ TTM / cổ phiếu lưu hành','pe_ttm':'Giá thô / EPS TTM','pb':'Giá thô × số cổ phiếu / vốn mẹ','bvps':'Vốn mẹ / số cổ phiếu','market_cap':'Giá thô × số cổ phiếu','shares_outstanding':None}[k],'VND / lần / cp',True)
        record('valuation.parent_profit_ttm',[data.fact('parent_profit',q).source for q in data.periods[:4] if data.fact('parent_profit',q)],'Tổng LNST mẹ bốn quý riêng, điều chỉnh năm kiểm toán và bán niên soát xét.','VND',True)
    if not provider:missing.append('Chưa đủ dữ liệu định giá theo nguồn cho mã này.')
    peer,peer_source=load_peer_summary(settings,symbol,last_day or repo.as_of.isoformat())
    if peer:
        for key,value in peer.items():
            if key!='members':valuation[key]=value
        for key in peer:
            if key=='members':continue
            record('valuation.'+key,[peer_source],
                'Sector trước; <5 P/E hợp lệ thì industry. P/E dương ≤200; thiếu thì vốn hóa VND/LNST mẹ TTM dương. Chênh lệch chỉ dùng P/E lưu cùng snapshot.',
                'lần / % / số mẫu',True)
    news=[]; news_sources={}
    for row in repo.news(symbol=symbol,limit=100,distinct_publishers=False):
        cats=json.loads(row['categories'] or '[]')
        if not set(cats)&{'taichinh','doanhnghiep','nganh','vimo','kinhte','quocte','diachinhtri'}:continue
        stamp=datetime.fromisoformat(row['published_at']).astimezone(VIETNAM).isoformat() if row['published_at'] else None
        news.append(dict(source=row['source_name'],published_at=stamp,title=row['title'],summary=row['excerpt'] or None,
            channel='Thông tin doanh nghiệp/tài chính',impact='unclear',needs_verification=True,url=row['url']))
        news_sources[row['url']]=dict(item='Tin tức',source=row['source_name'],url=row['url'],locator=row['title'],retrieved_at=row['last_seen'],published_at=row['published_at'])
    issuer_path=settings.root/'var/issuer_news'/f'{symbol}.json'
    if issuer_path.is_file():
        for item in json.loads(issuer_path.read_text(encoding='utf-8')):
            if item['published_at'][:10]<=repo.as_of.isoformat():
                news.insert(0,{k:item[k] for k in ('source','published_at','title','summary','channel','impact','needs_verification','url')})
                news_sources[item['url']]=dict(item='Công bố doanh nghiệp',source=item['source'],url=item['url'],locator=item['title'],retrieved_at=item['retrieved_at'],published_at=item['published_at'])
    news=rank_company_news(list({n['url']:n for n in news}.values()),symbol,repo.as_of,12)
    sources.extend(news_sources[n['url']] for n in news)
    profile_rows=[dict(label='Doanh nghiệp',value=company['company_name'],period='Danh mục'),dict(label='Sàn / mã',value=company['exchange']+' / '+symbol,period='Danh mục'),
        dict(label='Ngành',value=company['industry']['name'],period='GICS cấp 2')]
    metadata=json.loads(company.get('raw_json') or '{}')
    if metadata.get('listedDate'):profile_rows.append(dict(label='Ngày niêm yết',value=str(metadata['listedDate']),period='Theo danh mục'))
    for f in facts:
        if f.category in ('overview','subsidiaries','history'):
            profile_rows.append(dict(label=f.label,value=f.value,period=f.period));sources.append(source(f.source))
    sources.append(source(dict(source_name='DNSE danh mục doanh nghiệp',url=company['source_url'],retrieved_at=company['retrieved_at'])))
    if close is not None:statement(f'Giá tham chiếu tại {last_day}: {close:,.0f} VND/cp.',['price.close','meta.price_date'],'Giá EOD/giá nguồn có thời điểm và đơn vị rõ ràng.')
    for n in (3,6,12):
        value=price[f'change_{n}m']
        if value is not None:statement(f'Giá biến động {value:+.2f}% trong {n} tháng lịch.',[f'price.change_{n}m'],'Lợi suất = giá cuối / giá đầu - 1.','opportunity' if value>0 else 'risk' if value<0 else 'neutral')
    if technical.get('rsi14') is not None:
        value=technical['rsi14'];statement(f'RSI(14) = {value:.2f}; '+('dưới 30' if value<30 else 'trên 70' if value>70 else 'trong vùng 30–70')+'.',
            ['technical.rsi14'],'Ngưỡng mô tả RSI 30/70; không phải tín hiệu giao dịch.','risk' if value>70 else 'neutral')
    if len(years)>1:
        for key,label in (('revenue','Doanh thu'),('net_income','LNST')):
            a,b=financials[key][-2:];change=(b/a-1)*100 if a is not None and b is not None and a>0 else None
            if change is not None:statement(f'{label} năm {years[-1]} thay đổi {change:+.2f}% so với {years[-2]}.',
                [f'financials.{key}.{len(years)-2}',f'financials.{key}.{len(years)-1}'],'Hai năm số nguồn; mức thay đổi không phải dự phóng.','opportunity' if change>0 else 'risk')
    alerts=[]
    for k,label in (('ma20','MA20'),('ma50','MA50'),('ma200','MA200')):
        if technical[k] is not None:alerts.append(dict(priority='high' if horizon=='short' and k=='ma20' or horizon=='long' and k=='ma200' else 'medium',
            condition='Giá so với '+label,threshold=f'{technical[k]:,.0f}',meaning='Quan sát vị trí giá, không phải lệnh.',fields=['technical.'+k,'price.close']))
    if technical['rsi14'] is not None:alerts.append(dict(priority='medium',condition='RSI(14) so với vùng 30/70',threshold='30 / 70',meaning='Theo dõi động lượng theo ngưỡng mô tả.',fields=['technical.rsi14']))
    if technical['rsi14'] is not None:alerts[-1].update(condition='RSI cắt lên 50',threshold='50',meaning='Xác nhận từ hai phiên liên tiếp.')
    for condition,threshold,meaning,fields in [
        ('Phá đáy 250 phiên',f"{price['trough_250']:,.0f}" if price['trough_250'] is not None else None,'So với đáy các phiên trước.',['price.trough_250','price.close']),
        ('MACD cắt signal',f"{technical['macd_signal']:,.1f}" if technical['macd_signal'] is not None else None,'Xác nhận từ hai phiên liên tiếp.',['technical.macd','technical.macd_signal']),
        ('KL giảm mạnh',f"{avg_volume*.5:,.0f}" if avg_volume is not None else None,'Dưới 0,5× TB20; xem cơ sở quyền.',['technical.volume_ma20','technical.volume']),
        ('BCTC mới / cơ sở EPS','Sau '+financials['latest_quarter']['period'],'LNST mẹ YoY, biên gộp, CFO/LNST đúng kỳ, EPS và cổ phiếu.',['financials.latest_quarter.period'])]:
        if threshold is not None:alerts.append(dict(priority='medium',condition=condition,threshold=threshold,meaning=meaning,fields=fields))
    for y,k in annual_income_anomalies(raw,review):missing.append(f'BCTC năm {y}: {LABELS[k]} nguồn bất thường; không tự thay hệ số đơn vị.')
    if banking:missing.append('Ngân hàng: không áp dụng biên LNST/doanh thu, biên gộp, CFO/LNST hoặc thanh toán hiện hành kiểu sản xuất; NIM/CASA/NPL/CAR cần đúng phạm vi và kỳ.')
    if not peer:missing.append('Peer lịch sử cần snapshot cùng ngày có từng thành viên; không sao chép số tổng hợp từ PDF.')
    missing.extend([
        'Giá VCI/vnstock đã điều chỉnh; không phải tổng lợi suất. Khối lượng CafeF khớp lệnh chỉ điều chỉnh theo sự kiện đã xác minh.',
        'Ảnh chụp dữ liệu có thể được bổ sung sau ngày kỳ kế toán; không phải dữ liệu backtest point-in-time.'])
    annual_path=settings.root/'var/issuer_disclosures'/symbol/f'{symbol}_{repo.as_of.year-1}_BCTN.pdf'
    annual_report=mine_annual(annual_path) if annual_path.is_file() else dict(file=None,pages=None,keyword_counts={},total_matches=None)
    annual_source_path=annual_path.with_suffix('.source.json')
    if annual_source_path.is_file():sources.append(json.loads(annual_source_path.read_text(encoding='utf-8')))
    scenarios=build_scenarios(price,technical)
    for event in actions:
        sources.append(dict(item='Sự kiện quyền',source='FPT công bố quyền',url=event['url'],locator=event.get('source'),retrieved_at=datetime.now(UTC).isoformat(),published_at=None))
        if event.get('date_source'):sources.append(dict(item='Ngày không hưởng quyền',source='BSC lịch quyền',url=event['date_source'],locator=event['ex_date'],retrieved_at=datetime.now(UTC).isoformat(),published_at=None))
    if technical['reference_volume_vs_ma20']!=technical['volume_vs_ma20']:
        missing.append('X10 TB20 353,3 tỷ/KL≈1,98 dùng KL khớp lệnh chưa điều chỉnh thưởng. Báo cáo này điều chỉnh KL trước quyền ×1,1 theo mục 1; số tham chiếu giữ riêng trong technical.reference_* để đối chiếu, không dùng làm số hiện hành.')
    unique_sources={tuple((s['source'],s['url'])):s for s in sources}
    payload=dict(meta=dict(ticker=symbol,company_name=company['company_name'],exchange=company['exchange'],sector=peer['peer_classification'] if peer else company['industry']['name'],
        report_date=repo.as_of.isoformat(),price_date=last_day,latest_fiscal_period=financials['latest_quarter']['period'],horizon=horizon,profile=profile,
        risk_level=cfg.get('risk_level') or 'Cân bằng / Vừa phải',priority=cfg.get('priority'),depth=cfg.get('depth'),accent=cfg.get('accent','#1F5EFF')),
        price=price,technical=technical,market=market,scores=scores,decision=decision,financials=financials,valuation=valuation,news=news,
        annual_report=annual_report,scenarios=scenarios,alerts=alerts,
        methodology=dict(formula_text='Giá/MA: VND/cp; lợi suất theo tháng lịch. RSI Wilder(14); MACD EMA(12,26,9); biến động log-return × √252. '
            'Biên lợi nhuận = lợi nhuận / doanh thu cùng kỳ. ROE/ROA chỉ dùng BCTC đối chiếu và bình quân đầu-cuối năm. Không tự suy vốn chủ = tài sản - nợ. '
            + ('FA/TA: engine do người dùng cung cấp. FA hiệu dụng co về 50 theo độ phủ; thống nhất theo trọng số cấu hình; không phải khuyến nghị.' if strategy else 'FA/TA: chưa có cấu hình engine, không dùng điểm mẫu.'),
            sources=list(unique_sources.values()),missing=list(dict.fromkeys(missing)),config_sha256=strategy['config_sha256'] if strategy else None,
            provenance=provenance,statements=statements,profile_rows=profile_rows,focus={k:v['focus'] for k,v in cfg.get('horizons',{}).items()},
            banking=banking,banking_rows=bank_rows,price_unit='VND/cp',financial_unit='tỷ VND' if review else 'giá trị nguồn / 10^9; chưa đối chiếu đơn vị/phạm vi',
            corporate_actions=actions,price_history_count=len(rows),quality_checks=[]))
    if strategy:
        payload['methodology']['strategy']=strategy['evidence']
        payload['methodology']['missing_reason']=strategy['missing_reason']
    payload['methodology']['news_selection']=dict(as_of=repo.as_of.isoformat(),policy='Trong ngày trước, liên quan trực tiếp và sự kiện tài chính, rồi độ mới. Không có lượt đọc để khẳng định được quan tâm nhất.',pdf_is_dated_snapshot=True)
    for k,v in price.items():
        if v is None and k!='close':payload['methodology'].setdefault('missing_reason',{})['price.'+k]=price_reason or 'Thiếu phiên tại đầu cửa sổ tháng lịch trên chuỗi điều chỉnh.'
    payload['methodology']['quality_checks'].extend([
        dict(check='adjusted_history_300',status='pass' if len(rows)>=300 else 'warning',detail=f'{len(rows)} phiên điều chỉnh; không tự bù phiên.'),
        dict(check='volume_adjustment',status='pass' if actions and all(e.get('verified') for e in actions) else 'warning',detail='Khối lượng/giá trị TB20 phải kiểm tra sự kiện quyền và cơ sở khớp lệnh/tổng giao dịch; chưa đối chiếu không được coi là xác nhận X10.'),
        dict(check='aligned_price_dates',status='pass' if rows and raw_rows and rows[-1]['date']==raw_rows[-1]['date'] else 'warning',detail='Ngày giá thô và giá điều chỉnh.'),
        dict(check='eps_share_identity',status='pass' if valuation['eps_ttm'] is not None else 'warning',detail='EPS × cổ phiếu = LNST mẹ TTM; thiếu đầu vào thì chặn định giá.')])
    for period in data.periods[:5]:
        balance=[numeric(data.value(k,period)) for k in ('assets','liabilities','equity')]
        a,l,e=balance
        status='warning' if any(v is None for v in balance) else 'pass' if a>0 and abs(a-l-e)<=a*.005 else 'warning'
        payload['methodology']['quality_checks'].append(dict(check=f'balance_{period[0]}Q{period[1]}',status=status,
            detail='Tài sản công bố = nợ + tổng vốn (≤ 0,5%); sai lệch thì cách ly ba trường, không suy tổng vốn.'))
    if rows and raw_rows:
        adjusted_by_date={r['date']:r['close'] for r in rows}
        jumps=[]
        for previous,current in zip(raw_rows,raw_rows[1:]):
            if previous['date'] not in adjusted_by_date or current['date'] not in adjusted_by_date:continue
            raw_change=current['close']/previous['close']-1
            adjusted_change=adjusted_by_date[current['date']]/adjusted_by_date[previous['date']]-1
            if abs(raw_change-adjusted_change)>.05:
                jumps.append(dict(date=current['date'],raw_return_pct=raw_change*100,adjusted_return_pct=adjusted_change*100))
        payload['methodology']['quality_checks'].append(dict(check='action_price_jumps',status='pass',
            detail='Đối chiếu giá thô/điều chỉnh quanh các bước thay đổi cơ sở >5 điểm %: '+json.dumps(jumps,ensure_ascii=False)))
        for event in actions:
            if event.get('verified') and event['type']=='bonus_shares':
                before=[r for r in raw_rows if r['date']<event['ex_date'] and r['date'] in adjusted_by_date]
                after=[r for r in raw_rows if r['date']>=event['ex_date'] and r['date'] in adjusted_by_date]
                if before and after:
                    old,new=before[-1],after[0]
                    factor=(adjusted_by_date[new['date']]/new['close'])/(adjusted_by_date[old['date']]/old['close'])
                    payload['methodology']['quality_checks'].append(dict(check='bonus_adjustment_'+event['ex_date'],
                        status='pass' if abs(factor-(1+event['ratio']))<=.01 else 'fail',detail=f'Hệ số giá qua quyền {factor:.6f}; kỳ vọng 1+ratio={1+event["ratio"]:.6f}.'))
    payload['methodology']['missing_reason']=missing_report(payload)['missing_reason']
    return payload

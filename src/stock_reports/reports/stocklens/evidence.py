"""Auditable source enrichments; no ticker-specific scoring or sample numbers."""
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path
import re

KEYWORDS=('quản trị','môi trường','chuyển đổi số','phát triển bền vững','rủi ro','bảo mật','trí tuệ nhân tạo')


def mine_annual(path):
    import pymupdf
    path=Path(path)
    with pymupdf.open(path) as pdf:
        pages=[p.get_text() for p in pdf]
    original='\n'.join(pages)
    normalized=re.sub(r'\s+',' ',original).casefold()
    counts={k:len(re.findall(re.escape(k),normalized)) for k in KEYWORDS}
    tokens=len(original.split()); total=sum(counts.values()); excerpts=[]
    for i,page in enumerate(pages,1):
        clean=re.sub(r'\s+',' ',page).strip()
        match=re.search(r'quản trị|chuyển đổi số',clean,re.I)
        if match:
            excerpts.append(dict(page=i,text=clean[match.start():].split('.')[0][:65]))
        if len(excerpts)==2:break
    return dict(file=path.name,pages=len(pages),text_pages=sum(bool(t.strip()) for t in pages),
        keyword_counts=counts,total_matches=total,distinct_keywords=sum(v>0 for v in counts.values()),
        tokens=tokens,density_per_10000=total/tokens*10000 if tokens else None,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),excerpts=excerpts)


def adjusted_history(settings,symbol,cutoff):
    path=settings.root/'var/stocklens_adjusted_prices'/f'{symbol}.json'
    if not path.is_file():return [],[], 'Không có bản lưu giá điều chỉnh VCI/vnstock; không tự back-adjust sự kiện chưa xác minh.'
    payload=json.loads(path.read_text(encoding='utf-8'))
    expected='index points' if symbol=='VNINDEX' else 'thousand VND'
    if payload.get('symbol')!=symbol or payload.get('unit')!=expected or payload.get('adjusted') is not True:
        return [],[], 'Bản lưu giá điều chỉnh không xác nhận mã, đơn vị hoặc cơ sở điều chỉnh.'
    rows=[]
    for r in payload['rows']:
        day=r['time'][:10]
        if day<=cutoff.date().isoformat():
            close=float(r['close'])*(1 if symbol=='VNINDEX' else 1000)
            if close<=0:raise ValueError('Invalid adjusted close')
            rows.append(dict(date=day,close=close,volume=r.get('volume'),turnover=None))
    rows.sort(key=lambda r:r['date'])
    if len({r['date'] for r in rows})!=len(rows):raise ValueError('Duplicate adjusted date')
    return rows,[payload['source']],None


def null_paths(value,path=''):
    if value is None:yield path
    elif isinstance(value,dict):
        for key,item in value.items():
            if key=='methodology':continue
            yield from null_paths(item,f'{path}.{key}' if path else key)
    elif isinstance(value,list):
        for i,item in enumerate(value):yield from null_paths(item,f'{path}.{i}')


def missing_report(payload):
    """One reason per null, including arrays; never replace missing with zero."""
    explicit=payload['methodology'].get('missing_reason',{})
    cells={}
    for path in null_paths(payload):
        if path in explicit:reason=explicit[path]
        elif path.startswith('scores.'):
            reason='Engine chưa có đủ chỉ tiêu FA hoặc cửa sổ giá/khối lượng/VNINDEX cùng cơ sở cho ô này; None không được thay bằng 0.' if payload['methodology'].get('strategy') else 'Chưa có cấu hình strategy_engine do người dùng cung cấp; không chấm theo điểm mẫu.'
        elif path.startswith('valuation.peer'):
            reason='Không có snapshot cùng ngày gồm từng thành viên, P/E và phân loại sector/industry; PDF tổng hợp không thay thế dữ liệu gốc.'
        elif path.startswith('annual_report.'):
            reason='Chưa có BCTN gốc trong bản lưu công bố doanh nghiệp.'
        elif path.startswith('scenarios.'):
            reason='Thiếu giá điều chỉnh hoặc MA/RSI/MACD đủ lịch sử để lập điều kiện.'
        elif payload['methodology']['banking'] and any(k in path for k in ('gross_margin','net_margin','ocf_to_ni','current_ratio')):
            reason='Không áp dụng chỉ tiêu sản xuất cho ngân hàng.'
        elif path.endswith(('.nim','.npl','.car','.casa')) and not payload['methodology']['banking']:
            reason='Không áp dụng chỉ tiêu ngân hàng cho doanh nghiệp này.'
        else:
            reason='Nguồn đã lưu và hồ sơ đối chiếu chưa cung cấp số liệu cùng kỳ/cơ sở; không suy số hoặc dùng số mẫu.'
        cells[path]=reason
    return dict(ticker=payload['meta']['ticker'],report_date=payload['meta']['report_date'],
        price_date=payload['meta']['price_date'],missing_count=len(cells),missing_reason=cells,
        quality_checks=payload['methodology'].get('quality_checks',[]))


def export_missing(payload,destination):
    path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(missing_report(payload),ensure_ascii=False,indent=2),encoding='utf-8')
    return path


def build_scenarios(price,technical):
    keys=('ma20','ma50','rsi14','macd','macd_signal')
    if price['trough_250'] is None or any(technical[k] is None for k in keys):
        return dict(bull=None,base=None,bear=None)
    ma20,ma50=technical['ma20'],technical['ma50'];low=price['trough_250']
    fields=['price.close','price.trough_250',*[f'technical.{k}' for k in keys]]
    evidence=f"Giá {price['close']:,.0f}; RSI {technical['rsi14']:.1f}; histogram {technical['macd']-technical['macd_signal']:+.1f}."
    monitor='KL > 1,5× TB20 trước; BCTC mới: LNST mẹ YoY, biên gộp, OCF/LNST đúng kỳ.'
    return {
        'bull':dict(trigger=f'Vượt MA20 {ma20:,.0f}, MA50 {ma50:,.0f}; RSI > 50; MACD cắt lên signal.',evidence=evidence,invalidation='Rơi lại dưới MA20 hoặc MACD cắt xuống signal.',monitor=monitor,fields=fields),
        'base':dict(trigger=f'Trên đáy 250 phiên {low:,.0f}, chưa vượt MA20/MA50 đồng thời.',evidence=evidence,invalidation='Đạt điều kiện tích cực hoặc phá đáy 250 phiên.',monitor=monitor,fields=fields),
        'bear':dict(trigger=f'Phá đáy {low:,.0f}; hoặc dưới MA20/MA50 và động lượng suy yếu.',evidence=evidence,invalidation='Lấy lại MA20/MA50, RSI > 50, MACD cắt lên signal.',monitor=monitor,fields=fields)}

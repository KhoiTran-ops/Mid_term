"""Dated provider fundamentals remain visible without becoming analyst forecasts."""
from datetime import datetime, UTC
from decimal import Decimal, InvalidOperation
import json
import re
from zoneinfo import ZoneInfo
from stock_reports.domain.research import SourceReference


def provider_number(value):
    if value is None or isinstance(value, bool): return None
    text = str(value).strip()
    if not re.fullmatch(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', text): return None
    try: number = Decimal(text.replace(',', ''))
    except InvalidOperation: return None
    return number if number.is_finite() else None


def provider_metrics(snapshot):
    """CafeF's code Beta is labelled P/B, NOT a CAPM beta."""
    if not snapshot: return []
    names = {'EPScoBan': ('EPS cơ bản theo nguồn', 'VND/cp', 1000),
        'EPSphaLoang': ('EPS pha loãng theo nguồn', 'VND/cp', 1000),
        'P/E': ('P/E theo nguồn', 'lần', 1),
        'GiaTriSoSach': ('BVPS theo nguồn', 'VND/cp', 1000),
        'VonHoaThiTruong': ('Vốn hóa theo nguồn', 'tỷ VND', 1),
        'KlcpNY': ('Cổ phiếu niêm yết theo nguồn', 'cp', 1),
        'KlcpLuuHanh': ('Cổ phiếu lưu hành theo nguồn', 'cp', 1)}
    rows = []
    for item in snapshot.get('indicators', []):
        code = item.get('Code'); text = re.sub(r'<[^>]+>', '', item.get('Text') or '').strip()
        spec = ('P/B theo nguồn', 'lần', 1) if text == 'P/B' else names.get(code)
        value = provider_number(item.get('Value'))
        if spec is None or value is None: continue
        label, unit, scale = spec
        if scale == 1000 and 'nghìn đồng' not in text: continue
        if unit=='tỷ VND' and 'tỷ đồng' not in text:continue
        if unit=='cp' and (value<0 or value!=value.to_integral_value()):continue
        rows.append(dict(label=label, value=value*scale, unit=unit,
            formula='Chỉ tiêu do CafeF tổng hợp; không phải dự phóng/khuyến nghị độc lập'))
    return rows


def load_market_snapshot(settings, symbol, as_of):
    path = settings.root/'var/market_fundamentals'/f'{symbol}.json'
    if not path.is_file(): return None
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    if snapshot['symbol'] != symbol: raise ValueError('Market snapshot symbol mismatch')
    retrieved = datetime.fromisoformat(snapshot['retrieved_at'])
    if retrieved > datetime.now(UTC) or retrieved.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).date() > as_of:
        return None  # An undated live fundamental must never be backdated.
    for source in snapshot['sources']: SourceReference.model_validate(source)
    return snapshot


def market_quote(snapshot, cutoff):
    if not snapshot or not snapshot.get('quote'): return None
    quote = snapshot['quote']
    published = datetime.fromisoformat(quote['timestamp'])
    value = provider_number(quote['price_vnd'])
    if published > cutoff or value is None or value <= 0: return None
    return dict(value_vnd=value, timestamp=published, source=SourceReference.model_validate(quote['source']))

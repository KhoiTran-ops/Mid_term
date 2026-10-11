"""Adapter for the supplied engine; never substitute sample scores or missing values."""
from datetime import date
import hashlib
import importlib.util
import json
from pathlib import Path

ENGINE_PATH = Path(__file__).resolve().parents[4] / 'strategy_engine.py'


def load_engine():
    spec = importlib.util.spec_from_file_location('stocklens_supplied_strategy', ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fa_inputs(financials):
    """Same latest full annual scope; percentage points for rates, multiples for ratios."""
    f = financials; r = f['ratios']
    latest = lambda values: values[-1] if values else None
    inputs = {'net_income': latest(f['net_income']), 'equity': latest(f['equity'])}
    for key in ('roe', 'roa', 'net_margin', 'ocf_to_ni'):
        inputs[key] = latest(r[key])
    for key in ('debt_to_equity', 'current_ratio'):
        inputs[key] = r[key]
    ni = f['net_income']; rev = f['revenue']; years = f['years']
    inputs['ni_yoy'] = (ni[-1] / ni[-2] - 1) * 100 if len(ni) >= 2 and len(years) >= 2 and years[-1] - years[-2] == 1 and ni[-1] is not None and ni[-2] is not None and ni[-2] > 0 else None
    inputs['rev_cagr_3y'] = ((rev[-1] / rev[-4]) ** (1 / 3) - 1) * 100 if len(rev) >= 4 and len(years) >= 4 and years[-1] - years[-4] == 3 and rev[-1] is not None and rev[-4] is not None and rev[-1] > 0 and rev[-4] > 0 else None
    return inputs


def evaluate(settings, financials, rows, volume_rows, benchmark):
    path = settings.root / 'strategy_config.json'
    if not path.is_file():
        return None, 'Chưa có strategy_config.json của engine do người dùng cung cấp.'
    cfg = json.loads(path.read_text(encoding='utf-8'))
    engine = load_engine(); inputs = fa_inputs(financials)
    recorded = settings.root / 'strategy_config.sha256'
    if recorded.is_file() and recorded.read_text(encoding='utf-8').strip() != engine.config_hash(cfg):
        raise ValueError('Strategy config changed without an updated strategy_config.sha256')
    dates = [date.fromisoformat(r['date']) for r in rows]
    close = [r['close'] for r in rows]
    volume = [r['volume'] for r in volume_rows]
    if len(volume) != len(close) or any(a['date'] != b['date'] for a, b in zip(rows, volume_rows)):
        raise ValueError('Strategy adjusted close/volume dates mismatch')
    if benchmark and rows and benchmark[-1]['date'] != rows[-1]['date']:
        benchmark = []  # Do not mix a stale market regime with today's stock data.
    idx_dates = [date.fromisoformat(r['date']) for r in benchmark]
    idx_close = [r['close'] for r in benchmark]
    if close:
        result = engine.run(inputs, dates, close, volume, idx_dates, idx_close, cfg)
    else:
        result = {'fa': engine.compute_fa(inputs, cfg), 'ta': None,
                  'decision': {'unified': None, 'status': 'WATCH', 'reason': 'MISSING_PRICE_HISTORY',
                               'entry': cfg['entry'], 'exit': cfg['exit'], 'config_sha256': engine.config_hash(cfg)}}
    fa, ta, decision = result['fa'], result['ta'], result['decision']
    rules = {'momentum': 'Lợi suất tháng lịch ' + '/'.join(map(str, cfg['ta']['momentum']['months'])) + ' tháng đều > 0',
             'relative_strength': f"Lợi suất cổ phiếu trừ VNINDEX cùng ngày trong {cfg['ta']['relative_strength']['months']} tháng > 0",
             'trend': 'Giá điều chỉnh > MA50 > MA200',
             'breakout': f"Giá > đỉnh đóng cửa {cfg['ta']['breakout']['lookback']} phiên trước",
             'volume': f"KL điều chỉnh / TB{cfg['ta']['volume']['lookback']} phiên trước ≥ {cfg['ta']['volume']['min_ratio']}"}
    scores = dict(fa=fa['fa'], fa_raw=fa['fa_raw'], fa_coverage=fa['coverage'] * 100,
                  ta=ta['ta'] if ta else None, unified=decision['unified'],
                  entry_threshold=decision['entry'], exit_threshold=decision['exit'],
                  pillars={k: fa['pillars'].get(k, {}).get('score') for k in cfg['fa']['pillars']},
                  ta_conditions=[dict(name=k, rule=rules[k], **c) for k, c in ta['conditions'].items()] if ta else [])
    missing = {}
    if scores['fa_raw'] is None: missing['scores.fa_raw'] = 'Không có chỉ tiêu FA phù hợp trong các trụ cột đang bật.'
    for k, pillar in cfg['fa']['pillars'].items():
        if scores['pillars'][k] is None:
            missing['scores.pillars.' + k] = ('Trụ cột bị tắt trong cấu hình gốc; không điền điểm 0.' if not pillar['enabled'] else 'Thiếu các chỉ tiêu FA cùng kỳ/cơ sở cho trụ cột này hoặc doanh nghiệp bị loại theo engine.')
    for i, condition in enumerate(scores['ta_conditions']):
        if condition['passed'] is None:
            for field in ('passed', 'value'):
                missing[f'scores.ta_conditions.{i}.{field}'] = 'Thiếu chuỗi điều chỉnh/cửa sổ hoặc VNINDEX cùng ngày; engine trả None, không tự bù dữ liệu.'
    if ta is None:
        for k in ('ta', 'unified'): missing['scores.' + k] = 'Không có chuỗi giá điều chỉnh để gọi run; không chấm TA/điểm tổng hợp bằng giá thô.'
    evidence = dict(version=cfg['version'], config_sha256=decision['config_sha256'],
                    engine_sha256=hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest(),
                    financial_year=financials['years'][-1] if financials['years'] else None,
                    inputs_fa=inputs, fa_rate_unit='percentage points', fa_ratio_unit='multiple',
                    price_count=len(close), price_date=rows[-1]['date'] if rows else None,
                    index_date=benchmark[-1]['date'] if benchmark else None,
                    volume_basis='CafeF matched volume × verified corporate-action factor; adjusted closes VCI',
                    liquidity_basis='Engine: last 20 sessions including current; report technical.turnover_ma20: prior 20 excluding current',
                    result=result)
    return dict(scores=scores, decision={k: decision[k] for k in ('status', 'reason')},
                config_sha256=decision['config_sha256'], evidence=evidence, missing_reason=missing,
                liquidity_threshold=cfg['min_liquidity_bn_vnd'] * 1e9), None

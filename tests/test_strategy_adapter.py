"""Supplied engine, immutable config and honest missing-data integration."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from stock_reports.reports.stocklens.strategy import evaluate, fa_inputs, load_engine

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / 'strategy_config.json').read_text(encoding='utf-8'))


def annuals():
    return dict(years=[2022, 2023, 2024, 2025], revenue=[44009.53, 52617.90, 62848.79, 70112.83],
                net_income=[6491.34, 7788.05, 9427.42, 11232.34], equity=[None, None, None, 43748.04],
                ratios=dict(roe=[None, None, None, 28.3], roa=[None, None, None, 14.0],
                            net_margin=[None, None, None, 16.0], ocf_to_ni=[None, None, None, .90],
                            debt_to_equity=.48, current_ratio=1.40))


def prices():
    days = [date(2025, 1, 1) + timedelta(days=i) for i in range(600)]
    days = [d for d in days if d.weekday() < 5]
    rows = [dict(date=d.isoformat(), close=100000 * .9985 ** i, volume=5e6) for i, d in enumerate(days)]
    rows[-1]['volume'] = 1e7
    idx = [dict(date=d.isoformat(), close=1700, volume=None) for d in days]
    return rows, idx


def test_original_supplied_test_runs_in_ci():
    result = subprocess.run([sys.executable, '-X', 'utf8', 'test_engine.py'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.rstrip().endswith('OK')


def test_config_hash_is_recorded_and_original():
    engine = load_engine()
    expected = (ROOT / 'strategy_config.sha256').read_text().strip()
    assert engine.config_hash(CFG) == expected == '013a149bbbec22f0e0aa4395e19d59a0d4ba094df29f31003c6baab4188f55af'
    changed = deepcopy(CFG); changed['entry'] += 1
    assert engine.config_hash(changed) != expected


def test_runtime_blocks_unrecorded_config_change(tmp_path):
    changed = deepcopy(CFG); changed['entry'] = 61
    (tmp_path / 'strategy_config.json').write_text(json.dumps(changed), encoding='utf-8')
    (tmp_path / 'strategy_config.sha256').write_text(load_engine().config_hash(CFG), encoding='utf-8')
    with pytest.raises(ValueError, match='without an updated'):
        evaluate(SimpleNamespace(root=tmp_path), annuals(), [], [], [])


def test_inputs_are_full_annual_scope_percentages_and_ratio_multiples():
    f = annuals(); inputs = fa_inputs(f)
    assert set(inputs) == {'net_income', 'equity', 'roe', 'roa', 'net_margin', 'ocf_to_ni', 'ni_yoy', 'rev_cagr_3y', 'debt_to_equity', 'current_ratio'}
    assert inputs['roe'] == 28.3 and inputs['ocf_to_ni'] == .90
    assert inputs['ni_yoy'] == pytest.approx(19.1454349)
    assert inputs['rev_cagr_3y'] == pytest.approx(((70112.83 / 44009.53) ** (1 / 3) - 1) * 100)
    f['revenue'][0] = None; f['net_income'][-1] = None
    inputs = fa_inputs(f)
    assert inputs['net_income'] is None and inputs['ni_yoy'] is None and inputs['rev_cagr_3y'] is None


def test_missing_metrics_remain_none_and_reduce_available_pillars():
    engine = load_engine(); inputs = fa_inputs(annuals())
    for key in ('net_income', 'equity', 'roe', 'roa', 'net_margin', 'ocf_to_ni'): inputs[key] = None
    result = engine.compute_fa(inputs, CFG)
    assert not result['excluded'] and result['pillars']['quality']['score'] is None
    assert result['coverage'] == pytest.approx(.4)
    inputs['net_income'] = 0
    assert engine.compute_fa(inputs, CFG)['excluded']


def test_run_mapping_adjusted_prices_volumes_and_decision():
    rows, idx = prices()
    result, reason = evaluate(SimpleNamespace(root=ROOT), annuals(), rows, rows, idx)
    engine = load_engine()
    raw = engine.run(fa_inputs(annuals()), [date.fromisoformat(r['date']) for r in rows],
                     [r['close'] for r in rows], [r['volume'] for r in rows],
                     [date.fromisoformat(r['date']) for r in idx], [r['close'] for r in idx], CFG)
    assert reason is None
    assert result['scores']['fa'] == raw['fa']['fa']
    assert result['scores']['fa_raw'] == raw['fa']['fa_raw']
    assert result['scores']['fa_coverage'] == pytest.approx(80)
    assert result['scores']['ta'] == 5 and result['scores']['unified'] == 18.1
    assert result['decision'] == dict(status='WATCH', reason='SCORE_BELOW_ENTRY')
    assert result['scores']['pillars']['value'] is None
    assert result['config_sha256'] == raw['decision']['config_sha256']
    assert len(result['scores']['ta_conditions']) == 5
    assert result['evidence']['result'] == raw


def test_missing_volume_is_not_zero_or_imputed():
    rows, idx = prices(); rows[-2]['volume'] = None
    result, _ = evaluate(SimpleNamespace(root=ROOT), annuals(), rows, rows, idx)
    condition = next(c for c in result['scores']['ta_conditions'] if c['name'] == 'volume')
    assert condition['value'] is None and condition['passed'] is None
    assert result['evidence']['result']['ta']['liquidity_tb20_bn'] is None
    assert result['decision']['reason'] == 'ILLIQUID'


def test_no_raw_fallback_if_adjusted_history_is_absent():
    result, _ = evaluate(SimpleNamespace(root=ROOT), annuals(), [], [], [])
    assert result['scores']['fa'] is not None
    assert result['scores']['ta'] is None and result['scores']['unified'] is None
    assert result['decision']['reason'] == 'MISSING_PRICE_HISTORY'


def test_reject_mismatched_volume_and_stale_index():
    rows, idx = prices()
    with pytest.raises(ValueError, match='dates mismatch'):
        evaluate(SimpleNamespace(root=ROOT), annuals(), rows, rows[:-1], idx)
    result, _ = evaluate(SimpleNamespace(root=ROOT), annuals(), rows, rows, idx[:-1])
    assert result['evidence']['index_date'] is None
    assert next(c for c in result['scores']['ta_conditions'] if c['name'] == 'relative_strength')['passed'] is None

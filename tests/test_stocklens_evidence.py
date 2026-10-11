import json
from datetime import datetime,UTC
from pathlib import Path
from types import SimpleNamespace
import pytest
from stock_reports.reports.stocklens.evidence import adjusted_history,null_paths,missing_report,build_scenarios
from stock_reports.reports.stocklens.charts import line_chart
from stock_reports.reports.stocklens.peers import peer_summary


def test_adjusted_loader_rejects_unverified_basis_and_future(tmp_path):
    folder=tmp_path/'var/stocklens_adjusted_prices';folder.mkdir(parents=True)
    payload=dict(symbol='FPT',unit='thousand VND',adjusted=True,source=dict(source='VCI'),rows=[dict(time='2026-10-09',close=57.9,volume=1),dict(time='2026-10-12',close=60,volume=1)])
    path=folder/'FPT.json';path.write_text(json.dumps(payload),encoding='utf-8')
    settings=SimpleNamespace(root=tmp_path);rows,_,reason=adjusted_history(settings,'FPT',datetime(2026,10,11,tzinfo=UTC))
    assert len(rows)==1 and rows[0]['close']==57900 and reason is None
    payload['adjusted']=False;path.write_text(json.dumps(payload),encoding='utf-8')
    rows,_,reason=adjusted_history(settings,'FPT',datetime(2026,10,11,tzinfo=UTC))
    assert not rows and reason


def test_every_null_gets_its_own_reason():
    data=dict(meta=dict(ticker='TEST',report_date='2026-10-11',price_date=None),scores=dict(fa=None),
        financials=dict(revenue=[1,None,0]),valuation=dict(peer_count=None),methodology=dict(banking=False))
    report=missing_report(data)
    assert set(report['missing_reason'])==set(null_paths(data))
    assert 'financials.revenue.1' in report['missing_reason'] and 'financials.revenue.2' not in report['missing_reason']
    assert 'engine' in report['missing_reason']['scores.fa'] and 'snapshot' in report['missing_reason']['valuation.peer_count']


def test_four_year_margin_chart_has_percent_ticks_and_all_years():
    chart=str(line_chart([2022,2023,2024,2025],[('gross',[39,38,37,36]),('net',[14,15,16,16])],percent_axis=True))
    for year in range(2022,2026):assert f'>{year}</text>' in chart
    assert '15%' in chart and '40%' in chart and '12.3</text>' not in chart


def test_peer_snapshot_filters_and_never_mixes_dates():
    day='2026-10-02'
    rows=[dict(symbol='FPT',sector='IT',industry='software',pe=11.88,snapshot_date=day)]
    rows.extend(dict(symbol=f'T{i}',sector='IT',industry='software',pe=pe,snapshot_date=day) for i,pe in enumerate([10,12,14,16,201,-1]))
    rows.append(dict(symbol='CAP',sector='IT',industry='software',pe=None,market_cap_vnd=200,parent_profit_ttm_vnd=20,snapshot_date=day))
    result=peer_summary(dict(snapshot_date=day,members=rows),'FPT')
    assert result['peer_group_level']=='sector' and result['peer_count']==6
    assert result['peer_median_pe']==pytest.approx(11.94) and result['peer_archived_pe']==11.88
    rows[1]['snapshot_date']='2026-10-09'
    with pytest.raises(ValueError,match='dates mismatch'):peer_summary(dict(snapshot_date=day,members=rows),'FPT')


def test_peer_sector_under_five_uses_industry():
    day='2026-10-02'
    rows=[dict(symbol='FPT',sector='IT',industry='software',pe=12,snapshot_date=day),dict(symbol='OTHER',sector='different',industry='software',pe=8,snapshot_date=day)]
    result=peer_summary(dict(snapshot_date=day,members=rows),'FPT')
    assert result['peer_group_level']=='industry' and result['peer_count']==2 and result['peer_median_pe']==10


def test_scenarios_do_not_have_probabilities_or_targets():
    price=dict(close=57900,trough_250=57500)
    tech=dict(ma20=63756,ma50=64108,rsi14=23.7,macd=-1501,macd_signal=-764)
    result=build_scenarios(price,tech)
    for scenario in result.values():
        assert set(scenario)=={'trigger','evidence','invalidation','monitor','fields'}
        assert all(scenario[k] for k in ('trigger','evidence','invalidation','monitor'))
    tech['ma50']=None
    assert all(s is None for s in build_scenarios(price,tech).values())


def test_annual_miner_normalizes_phrase_linebreaks(tmp_path,monkeypatch):
    import pymupdf
    import stock_reports.reports.stocklens.evidence as module
    monkeypatch.setattr(module,'KEYWORDS',('risk management','digital transformation'))
    path=tmp_path/'annual.pdf';pdf=pymupdf.open();page=pdf.new_page();page.insert_text((40,40),'risk\nmanagement risk management\ndigital transformation');pdf.save(path);pdf.close()
    result=module.mine_annual(path)
    assert result['keyword_counts']=={'risk management':2,'digital transformation':1}
    assert result['total_matches']==3 and result['distinct_keywords']==2 and result['text_pages']==1


def test_requested_fpt_acceptance_is_honest_if_archive_available():
    path=Path(__file__).resolve().parents[1]/'output/pdf/FPT-stocklens-2026-10-11.json'
    if not path.is_file():pytest.skip('Actual source-backed FPT archive is not installed; no fabricated fixture.')
    import importlib.util
    spec=importlib.util.spec_from_file_location('accept_stocklens',path.parents[2]/'tasks/accept_stocklens.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.acceptance(json.loads(path.read_text(encoding='utf-8')))
    assert result['price_date']=='2026-10-09'
    assert not result['counts']['fail']
    assert result['counts']['unavailable']>0 and result['all_targets_met'] is False
    assert result['counts']['different_basis']==2

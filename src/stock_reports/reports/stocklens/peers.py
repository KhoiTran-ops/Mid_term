"""Historical member-level valuation; no present-day substitution for missing snapshots."""
import json,math
from statistics import median


def positive(value):
    if isinstance(value,bool):return None
    try:value=float(value)
    except (TypeError,ValueError):return None
    return value if math.isfinite(value) and value>0 else None


def peer_summary(snapshot,symbol):
    day=snapshot['snapshot_date'];rows=snapshot['members']
    if any(r.get('snapshot_date')!=day for r in rows):raise ValueError('Peer member dates mismatch')
    if len({r['symbol'] for r in rows})!=len(rows):raise ValueError('Duplicate peer members')
    target=next((r for r in rows if r['symbol']==symbol),None)
    if not target:raise ValueError('Target absent from peer snapshot')
    def pe(row):
        value=positive(row.get('pe'))
        if value is None:
            cap,profit=positive(row.get('market_cap_vnd')),positive(row.get('parent_profit_ttm_vnd'))
            value=cap/profit if cap and profit else None
        return value if value is not None and value<=200 else None
    selected=[];level=None
    for key in ('sector','industry'):
        group=target.get(key)
        selected=[(r,pe(r)) for r in rows if group and r.get(key)==group and pe(r) is not None]
        level=key
        if len(selected)>=5 or key=='industry':break
    midpoint=median(v for _,v in selected) if selected else None;archived=pe(target)
    return dict(peer_median_pe=midpoint,peer_count=len(selected),peer_snapshot_date=day,
        peer_archived_pe=archived,peer_premium_pct=(archived/midpoint-1)*100 if archived and midpoint else None,
        peer_classification=target.get(level),peer_group_level=level,members=[r['symbol'] for r,_ in selected])


def load_peer_summary(settings,symbol,cutoff):
    folder=settings.root/'var/peer_snapshots'
    if not folder.exists():return None,None
    for path in sorted(folder.glob('*.json'),reverse=True):
        snapshot=json.loads(path.read_text(encoding='utf-8'))
        if snapshot['snapshot_date']>cutoff:continue
        if not any(r['symbol']==symbol for r in snapshot['members']):continue
        # A failed dated snapshot is rejected, not silently replaced with current quotes.
        return peer_summary(snapshot,symbol),snapshot['source']
    return None,None

"""StockLens strategy engine (tự xây). Thuần Python, không phụ thuộc thư viện ngoài."""
import json, hashlib, calendar, datetime as dt

def config_hash(cfg):
    s = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(s.encode()).hexdigest()

def lin(x, lo, hi):
    """Ánh xạ tuyến tính lo->0, hi->100 (hi<lo = càng thấp càng tốt), kẹp [0,100]."""
    if x is None: return None
    return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))

def months_back(d, n):
    y = d.year + (d.month - 1 - n) // 12; m = (d.month - 1 - n) % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

def aligned_return(dates, closes, months):
    """Lợi suất theo tháng lịch: dùng ngày giao dịch gần nhất không muộn hơn mốc."""
    if len(dates) < 2: return None
    target = months_back(dates[-1], months)
    idx = [i for i, d in enumerate(dates) if d <= target]
    if not idx or closes[idx[-1]] <= 0: return None
    return closes[-1] / closes[idx[-1]] - 1

def sma(v, n): return sum(v[-n:]) / n if len(v) >= n else None

def compute_ta(dates, close, volume, idx_dates, idx_close, cfg):
    t = cfg["ta"]; cond = {}
    # Momentum
    rets = {m: aligned_return(dates, close, m) for m in t["momentum"]["months"]}
    ok = all(r is not None for r in rets.values()) and all(r > 0 for r in rets.values())
    cond["momentum"] = {"value": rets, "passed": ok if all(r is not None for r in rets.values()) else None}
    # Relative strength (cùng ngày với VN-Index)
    m = t["relative_strength"]["months"]; common = sorted(set(dates) & set(idx_dates))
    rs = None
    if len(common) > 1:
        sd = dict(zip(dates, close)); idd = dict(zip(idx_dates, idx_close))
        a = aligned_return(common, [sd[d] for d in common], m); b = aligned_return(common, [idd[d] for d in common], m)
        rs = None if a is None or b is None else a - b
    cond["relative_strength"] = {"value": rs, "passed": None if rs is None else rs > 0}
    # Trend
    ma50, ma200 = sma(close, 50), sma(close, 200)
    tr = None if ma50 is None or ma200 is None else close[-1] > ma50 > ma200
    cond["trend"] = {"value": [close[-1], ma50, ma200], "passed": tr}
    # Breakout: giá > đỉnh đóng cửa 20 phiên TRƯỚC
    lb = t["breakout"]["lookback"]
    hi = max(close[-lb - 1:-1]) if len(close) > lb else None
    cond["breakout"] = {"value": [close[-1], hi], "passed": None if hi is None else close[-1] > hi}
    # Volume: KL / TB20 phiên trước
    lv = t["volume"]["lookback"]
    prior_vol = volume[-lv - 1:-1]
    avg = sum(prior_vol) / lv if len(volume) > lv and all(v is not None for v in prior_vol) else None
    ratio = None if not avg or volume[-1] is None else volume[-1] / avg
    cond["volume"] = {"value": ratio, "passed": None if ratio is None else ratio >= t["volume"]["min_ratio"]}
    pts = sum(t[k]["points"] for k, c in cond.items() if c["passed"])
    for k, c in cond.items(): c["points"] = t[k]["points"] if c["passed"] else 0
    # Thanh khoản TB20 (tỷ VND) và chế độ thị trường
    tb20 = sum(c * v for c, v in zip(close[-20:], volume[-20:])) / 20 / 1e9 if len(close) >= 20 and len(volume) >= 20 and all(v is not None for v in volume[-20:]) else None
    w = cfg["market_regime"]["index_ma_window"]; im = sma(idx_close, w)
    bull = None if im is None else idx_close[-1] > im
    return {"ta": float(pts), "conditions": cond, "liquidity_tb20_bn": tb20, "market_bull": bull}

def compute_fa(inputs, cfg):
    f = cfg["fa"]
    # Missing exclusion inputs are unknown, not zero. Preserve supplied scoring formulas.
    ni, eq = inputs.get("net_income"), inputs.get("equity")
    if (ni is not None and ni <= f["exclude_if"]["net_income_le"]) or (eq is not None and eq <= f["exclude_if"]["equity_le"]):
        return {"fa": 0.0, "fa_raw": None, "coverage": 0.0, "excluded": True, "pillars": {}}
    pill, wsum, wall = {}, 0.0, 0.0; acc = 0.0
    for name, p in f["pillars"].items():
        wall += p["weight"]; sc = cov = None
        if p["enabled"] and p["metrics"]:
            av = [(m["w"], lin(inputs.get(m["key"]), m["lo"], m["hi"])) for m in p["metrics"]]
            av = [(w, s) for w, s in av if s is not None]
            if av:
                tw = sum(w for w, _ in av); sc = sum(w * s for w, s in av) / tw
                cov = tw / sum(m["w"] for m in p["metrics"])
        pill[name] = {"score": sc, "weight": p["weight"], "coverage": cov or 0.0}
        if sc is not None: acc += p["weight"] * sc; wsum += p["weight"]
    fa_raw = acc / wsum if wsum else None
    coverage = wsum / wall if wall else 0.0
    fa_eff = 0.0 if fa_raw is None else 50 + (fa_raw - 50) * coverage
    return {"fa": fa_eff, "fa_raw": fa_raw, "coverage": coverage, "excluded": False, "pillars": pill}

def decide(fa, ta, cfg):
    w = cfg["weights"]; unified = fa["fa"] * w["fa"] + ta["ta"] * w["ta"]
    liquid = ta["liquidity_tb20_bn"] is not None and ta["liquidity_tb20_bn"] >= cfg["min_liquidity_bn_vnd"]
    if fa["excluded"]: status, reason = "EXCLUDED", "FA_EXCLUDED"
    elif not liquid: status, reason = "WATCH", "ILLIQUID"
    elif unified < cfg["entry"]: status, reason = "WATCH", "SCORE_BELOW_ENTRY"
    elif not ta["market_bull"]: status, reason = "WATCH", "MARKET_DEFENSIVE"
    else: status, reason = "PASS_SCREEN", "ALL_CONDITIONS_MET"
    return {"unified": round(unified, 1), "status": status, "reason": reason, "liquid": liquid,
            "entry": cfg["entry"], "exit": cfg["exit"], "config_sha256": config_hash(cfg)}

def run(inputs_fa, dates, close, volume, idx_dates, idx_close, cfg):
    fa = compute_fa(inputs_fa, cfg); ta = compute_ta(dates, close, volume, idx_dates, idx_close, cfg)
    return {"fa": fa, "ta": ta, "decision": decide(fa, ta, cfg)}

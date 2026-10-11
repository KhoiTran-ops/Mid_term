import json, datetime as dt, random
from strategy_engine import *
cfg = json.load(open("strategy_config.json"))
# 1) FA với số FPT năm 2025 (bản X10: FA 75.9, độ phủ 80%)
fpt = dict(net_income=11232.3, equity=43748.0, roe=28.3, roa=14.0, net_margin=16.0, ocf_to_ni=0.90,
           ni_yoy=19.1, rev_cagr_3y=16.8, debt_to_equity=0.48, current_ratio=1.40)
fa = compute_fa(fpt, cfg); print("FA raw %.1f | hiệu dụng %.1f | độ phủ %.0f%%" % (fa["fa_raw"], fa["fa"], fa["coverage"]*100))
print({k: round(v["score"],1) for k,v in fa["pillars"].items() if v["score"] is not None})
assert abs(fa["fa_raw"] - 75.9) < 1.5 and abs(fa["coverage"] - 0.8) < 1e-9
# 2) Điểm thống nhất khi TA = 5 (X10: 18.1)
print("unified với TA=5:", round(fa["fa"]*0.2 + 5*0.8, 1))
# 3) Chuỗi giả lập giảm giá + khối lượng đột biến: chỉ Volume đạt -> TA = 5
random.seed(1); d0 = dt.date(2025, 9, 1); dates, close, vol = [], [], []
p = 100000.0
for i in range(300):
    d = d0 + dt.timedelta(days=i)
    if d.weekday() >= 5: continue
    p *= 0.9985; dates.append(d); close.append(p); vol.append(5e6)
vol[-1] = 1.0e7
idx_dates, idx_close = dates[:], [1700 + i*0.0 for i in range(len(dates))]
r = run(fpt, dates, close, vol, idx_dates, idx_close, cfg)
print("TA:", r["ta"]["ta"], {k: v["passed"] for k, v in r["ta"]["conditions"].items()})
print(r["decision"])
assert r["ta"]["ta"] == 5.0 and r["decision"]["status"] == "WATCH"
print("OK")

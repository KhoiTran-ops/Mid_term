# Engine chấm điểm do người dùng cung cấp

## Tích hợp 11/10/2026

Ba file gốc được đặt tại gốc dự án: `strategy_engine.py`, `strategy_config.json`, `test_engine.py`. Không cần engine X10. Adapter tại `src/stock_reports/reports/stocklens/strategy.py` gọi đúng `run(inputs_fa, dates, close, volume, idx_dates, idx_close, cfg)` khi có chuỗi giá điều chỉnh. CLI và web dùng cùng adapter cho mọi mã.

- Cấu hình giữ nguyên từng byte so với file Downloads. SHA-256 file: `041da649facd5d07057abaa4f23dae62ccfda44cf4d6ed116e8fb4d55a6479d8`.
- Hash chuẩn hóa do `config_hash`/`run` trả về: `013a149bbbec22f0e0aa4395e19d59a0d4ba094df29f31003c6baab4188f55af`. Giá trị này nằm trong `strategy_config.sha256` và `methodology.config_sha256`; khác hash toàn file vì engine chuẩn hóa JSON.
- Engine gốc SHA-256: `b3de239bbca1347317a7657f63b9a72f67178eef30e0f01ba04bdc79cd24c591`. Chỉ thêm guard cho `net_income`/`equity=None` và cửa sổ volume có `None`, tránh lỗi phép so sánh/cộng. Giữ nguyên ánh xạ, trọng số, độ phủ, điều kiện và ngưỡng. Engine sau guard SHA-256: `7c3343cb1a04a24256d5872af52b114735bfdbd29c571322e35baaac0716fecf`; JSON ghi lại hash thực tế mỗi lần xuất.

## Đầu vào và đầu ra

FA lấy cùng năm tài chính đầy đủ mới nhất, không trộn bán niên 2026 với năm 2025. `net_income` là LNST hợp nhất năm, `equity` là tổng vốn chủ năm (tỷ VND, dấu không đổi); ROE/ROA dùng bình quân đầu-cuối năm; biên ròng dùng LNST/doanh thu; YoY LNST và CAGR doanh thu 3 năm lấy đúng các năm tương ứng. ROE, ROA, biên ròng, YoY và CAGR là điểm phần trăm. CFO/LNST, nợ vay/vốn chủ, thanh toán hiện hành là số lần theo cấu hình gốc, không nhân 100. Dữ liệu thiếu/không áp dụng vẫn là `None` (đặc biệt chỉ tiêu sản xuất ở ngân hàng).

Giá đóng cửa đầu vào là VCI đã điều chỉnh, không điều chỉnh hai lần. Volume CafeF khớp lệnh nhân hệ số quyền đã xác minh, cùng ngày với giá. Không thay volume thiếu bằng 0. RS do engine tự căn ngày chung VNINDEX; benchmark chốt khác ngày thì không dùng làm chế độ thị trường hiện tại. Khi không có giá điều chỉnh, chỉ chấm phần FA bằng `compute_fa`, để TA/điểm thống nhất null và trả trạng thái theo dõi do thiếu giá.

`scores.fa` là **FA hiệu dụng**, không phải FA thô. `scores.fa_raw` lưu FA thô; `fa_coverage` chuyển độ phủ từ 0–1 sang %. `pillars` lưu điểm từng trụ cột; `ta_conditions` lưu đủ 5 điều kiện, giá trị, passed và points. `methodology.strategy.result` lưu nguyên kết quả engine, gồm độ phủ từng trụ cột, liquidity và market regime. Độ phủ toàn cục của engine theo trọng số các trụ cột có dữ liệu, không tự sửa thành độ phủ từng chỉ tiêu; phần độ phủ chỉ tiêu riêng nằm trong từng pillar.

FPT từ số BCTC thực: FA thô **75,9134**; hiệu dụng **70,7307**; độ phủ **80%**; TA **5**; thống nhất **18,1**; vào **60**, ra **35**; `WATCH / SCORE_BELOW_ENTRY`. Value vẫn null vì bị tắt trong cấu hình, không phải lỗi tải dữ liệu. Không biến kết quả bộ lọc thành khuyến nghị mua/bán hay giá mục tiêu.

Thanh khoản của engine gốc là 20 phiên **gồm phiên hiện tại**; `technical.turnover_ma20` trên báo cáo là 20 phiên **trước** theo yêu cầu dữ liệu trước đó. Không đổi công thức engine để hai số trùng nhau; ghi rõ hai cơ sở trong JSON và phần giới hạn.

## Test và thay đổi cấu hình

`python test_engine.py` chạy test nguyên bản. `python -m pytest -q` chạy hồi quy toàn dự án. CI `.github/workflows/strategy-engine.yml` chạy test gốc, kiểm tra hash cấu hình và bộ test adapter; không cần API key.

Khi thay cấu hình có chủ đích, phải ghi lại hash mới trong `strategy_config.sha256`, cập nhật test hash và ghi lịch sử thay đổi tại đây. CI và runtime đều chặn khi hash file không khớp hash đã ghi. Không tự hiệu chỉnh cấu hình để khớp điểm PDF tham chiếu.

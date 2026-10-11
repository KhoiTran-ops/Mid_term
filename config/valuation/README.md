# Cấu hình định giá theo khuôn mẫu doanh nghiệp

Tệp thực cho một mã: `config/valuation/<MÃ>.json`. Không có giả định mẫu tự áp dụng.
Phải có hồ sơ `var/financial_reviews/<MÃ>.json` xác nhận tiền tệ, hệ số đơn vị,
scope, cơ sở quý/YTD, số cổ phiếu và tài liệu nguồn. Thiếu kiểm chứng chặn giá mục tiêu.

## Cấu trúc

- `method`: `justified_pb` (ngân hàng), `pb`/`pe` (bội số nhập rõ), `fcff`, `fcfe`,
  `nav`, hoặc `blended`.
- `horizon_months`: nhập rõ. Chỉ thời hạn 12 tháng mới đáp ứng mục tiêu 12 tháng trên bìa.
- `cases`: đúng ba trường hợp `bear`, `base`, `bull`; mỗi trường hợp có `rationale`
  giải thích ít nhất 8 ký tự và `source` nếu có. Không có source thì PDF ghi
  “Giả định của người soạn”, không coi là dữ kiện đã được xác minh.
- `probability`: tùy chọn, cần `probability_rationale`; nếu dùng phải đủ ba và tổng bằng 1.
- `sensitivity`: tùy chọn, gồm `row_variable`, `row_values`, `column_variable`,
  `column_values`, `rationale`. Ba giá trị mỗi trục phải được nhập rõ, tăng dần.
  Hỗ trợ `roe × ke` cho P/B hợp lý hoặc `wacc × g` cho FCFF.

## Đầu vào từng phương pháp

| Phương pháp | Trường cần cung cấp |
| --- | --- |
| P/B | `multiple`, `growth`; VCSH công ty mẹ và cổ phiếu trong review |
| P/E | `multiple`, `growth`; EPS TTM dương trong review; không nhận `forecast_shares` riêng |
| P/B hợp lý | `sustainable_roe`, `ke`, `terminal_growth`, `forecast_bvps_vnd`; Ke > g, ROE > g |
| FCFF | `wacc`, `terminal_growth`, `cash_vnd`, `debt_vnd`, `projections`; cổ phiếu trong review hoặc số dự phóng nhập rõ |
| FCFE | `ke`, `terminal_growth`, `projections`; không cộng tiền/trừ nợ lần nữa |
| NAV | `nav_assets`, `nav_liabilities_vnd`; cổ phiếu |
| Tổng hợp | Mỗi case có `components`, mỗi thành phần có `method`, `weight`, `rationale` và đầu vào tương ứng; tổng weight đúng 1 |

Tỷ lệ dùng số thập phân: 0,10 biểu thị 10%. Giá trị tiền có hậu tố `_vnd` dùng VND;
số cổ phiếu dùng cp, không phải triệu cp. Các số 0 có ý nghĩa phải được nhập rõ,
không được suy ra từ trường thiếu. `forecast_shares` là giả định pha loãng, không thay
thế kiểm chứng cổ phiếu lưu hành hiện tại để phát hành khuyến nghị.

`projections` gồm năm liên tiếp tăng dần, mỗi năm có `year`, `rationale`, `source`
nếu có, và các chỉ tiêu cần dùng: `fcff_vnd`, `fcfe_vnd`, `revenue_vnd`,
`net_profit_vnd`, `eps_vnd`, `bvps_vnd`, `roe`. DCF cần `discount_years` dương,
tăng dần cho từng dòng tiền, tính từ ngày định giá; không tự mặc định cuối năm.
Thời điểm giá trị cuối kỳ bằng thời điểm dòng tiền cuối. Suất chiết khấu phải lớn hơn g.

NAV: mỗi tài sản gồm `name`, `value_vnd`, `ownership` (0 < tỷ lệ ≤ 1),
`rationale`, `source` nếu có. Không được lặp tên tài sản để tránh cộng hai lần.

Có thể nhập `risk_free_rate`, `market_risk_premium`, `beta` để tính Ke theo CAPM.
Nếu nhập cả Ke trực tiếp và ba thành phần CAPM thì phải khớp nhau.

## Kiểm tra phát hành

Kịch bản phải giữ đúng thứ tự giá trị bi quan ≤ cơ sở ≤ lạc quan và có một kịch bản
dưới giá hiện tại. Không sửa giả định để tạo chiều giảm giả. Ngân hàng dùng bội số
P/B nhập tay vẫn được xem là giá hàm ý, chưa đủ kiểm tra ROE/đảo ngược để phát hành.
Thuyết minh chưa đối chiếu, thời hạn khác 12 tháng hoặc cổ phiếu chưa kiểm chứng
đều chặn khuyến nghị/giá mục tiêu trên bìa.

Ngưỡng của khuôn mẫu: cơ sở ≥ +15% là KHẢ QUAN, ≤ -10% là KÉM KHẢ QUAN,
giữa hai ngưỡng là TRUNG LẬP. Không đặt phân loại trước khi tính giá và kiểm chứng.

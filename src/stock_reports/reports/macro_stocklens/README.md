# StockLens Macro — JSON → HTML → Chromium PDF

Module độc lập với StockLens cổ phiếu: không gọi FA/TA, định giá, khuyến nghị mua/bán.
Tám partial nằm trong `pages/`, có thể đổi thứ tự / ẩn qua tham số. CSS 794×1123 px
tương đương A4 dọc; font Be Vietnam Pro và IBM Plex Mono dùng chung bộ tài sản đã có,
nhúng WOFF2 base64, chặn toàn bộ request mạng khi in.

## Chạy

Từ thư mục dự án, dùng Python trong môi trường đã có:

```powershell
& C:/Users/ADMIN/.venv/Scripts/python.exe run.py render-macro --period 2026-9T --out output/pdf/macro-9T-2026.pdf --qa-dir tmp/macro-qa
```

JSON riêng: thêm `--input path/to/period.json`. Schema: `schema.json`.
Kỳ hợp lệ: `2026-9T`, `2026-Q3`, `2026-09`, `2025`. Thay kỳ qua JSON, không sửa HTML.
Fetcher NSO hiện cấu hình các công bố **9 tháng 2022–2026**; tháng/quý/năm khác
phải cung cấp JSON / công bố chính thức tương ứng. Không lấy WDI năm thay cho tháng/quý.

Tùy chọn: `--draft` (đánh dấu mọi trang, cho phép xem lỗi), `--hide-empty-pages`,
`--pages 04_trade 01_overview`, `--accent '#1F5EFF'`, `--refresh`.
`project_limit` của API Python mặc định 10, tối đa 15; dòng không in giữ nguyên JSON
và thông báo “xem thêm trong JSON”. Không tự cắt tên dự án / nội dung dài.

Web “Tạo báo cáo → Tổng quan vĩ mô” dùng module này khi
`config/macro_stocklens.json.enabled=true`. Trường `macro_period` độc lập `period`
(quý BCTC cổ phiếu). Để trống: kỳ công bố gần nhất tại `as_of`.
API tải JSON và audit: `/api/reports/{id}/macro-data`, `/macro-quality`.

## Dữ liệu, quyền sử dụng và giả định

- Nguồn sơ cấp NSO: công bố kinh tế xã hội 9 tháng từng năm; URL, ngày công bố,
  thời điểm tải lưu ở `meta.sources` và `provenance` từng trường / chuỗi.
  Snapshot HTML bất biến: `var/macro/releases`; JSON nháp theo kỳ: `var/macro/periods`.
- PMI headline tháng 9/2026 và tháng trước: công bố công khai của **Cimigo**, đơn vị
  trực tiếp khảo sát PMI cho S&P Global. Chỉ lấy hai giá trị, không sao chép bài phân
  tích hay tải / tái xuất bộ chuỗi lịch sử có bản quyền. Parser kiểm tra tháng/năm,
  không dùng URL “latest” đã đổi kỳ để ghi đè kỳ cũ.
- Cache 12 giờ; retry tối đa 3 lần với timeout, lưu URL thực và raw hash. Khi nguồn
  lỗi, dùng snapshot đúng kỳ đã có; không đổi về số minh họa. Refresh theo công bố
  khi tạo báo cáo hoặc `--refresh`, **không phải luồng thống kê thời gian thực**.
- `licensed_json_sources` là cầu nối nguồn MPI/MOF/NHNN/Fiinpro đã được cấp quyền;
  mặc định chưa cấu hình, không giả vờ có dữ liệu. Mỗi nguồn khai báo `id`, `name`,
  `period`, HTTPS `url` không chứa khóa/query, `published`, `authorized: true`.
  Response `{ "period_code": "2026-9T", "fields": {"public_investment.ytd_disbursed": ...}, "units": {...} }`.
  Chỉ bật sau khi có quyền sử dụng. Không tự dùng khóa DNSE cho dữ liệu không thuộc DNSE.
- Số tiền thương mại/FDI là **tỷ USD**. Ngân sách/đầu tư công là **nghìn tỷ VND**.
  Bán lẻ JSON `value_bn_vnd` lưu **tỷ VND**, phần trình bày đổi sang nghìn tỷ VND
  bằng /1000; đơn vị ghi rõ. Giá trị thật 0 được giữ; null không thay bằng 0.
- Cán cân là số có dấu: XK − NK; trong nước + FDI = tổng. Nhập siêu âm, xuất siêu
  dương. Ngân sách thu − chi; số dư không được gọi là bội chi dự toán.
- Công thức backend có `derived[path].formula/inputs`, đánh dấu †. Không suy dự toán
  bằng cách đảo % thực hiện; không suy tỷ giá giao ngay từ chỉ số giá USD.
- Chuỗi lịch sử là **vintage công bố từng năm**, không coi là chuỗi đã hiệu chỉnh
  lại đồng nhất. GDP/bán lẻ/thương mại có thể khác số hồi tố trong thiết kế. Cờ
  ngoại lai là yêu cầu đối chiếu, không chứng minh dữ liệu sai và không tự sửa số.
  FDI đăng ký 2022/2023 chốt 20/9, các công bố sau chốt 30/9; `registered_as_of`
  được giữ ở từng dòng lịch sử. Không coi thời điểm chốt các vintage là giống nhau.
- IIP 9T/2025 = 9,1% được đối chiếu riêng nguồn năm 2025. Tín dụng dùng 10,89% tại
  28/9/2026 (NSO), không ép bằng 11,59% tại 30/9 trong thiết kế.
- Dự toán năm, giải ngân đầu tư công, tỷ giá giao ngay, danh sách dự án/quốc gia FDI,
  chuỗi tháng còn thiếu nguồn được xác nhận: ghi “Chưa có” và lý do. Không lấy từ
  mẫu Agriseco. Hộp note/conclusion chỉ nhận nội dung biên tập / nguồn được cấp phép;
  mặc định ẩn, không tự tạo đánh giá chung hoặc triển vọng.

## Cổng chất lượng và kiểm thử

`quality_report.json` gồm flags, missing/reasons, derived, source_differences.
Sai đơn vị, cán cân (0,02 tỷ USD), thu chi so dự toán (>1%), GDP đóng góp >100%,
chênh nguồn >0,2 điểm %, sai kỳ / ngày, giá trị không có nguồn: chặn bản chính thức.
Chênh làm tròn 0,05–0,2 điểm %: cảnh báo. Ngoại lai: nằm cùng phía ngoài hai lân cận
và lệch >40% ít nhất một lân cận, chưa có explanation → cảnh báo (bắt được 179,5).
Không tự chọn trung bình của hai nguồn xung đột.

Có thể cấu hình màu ngữ nghĩa trong JSON: `polarity` ánh xạ tên trường / đường dẫn
chuỗi sang `higher_good`, `higher_bad`, `neutral`; ví dụ `{"cpi.ytd_avg_yoy":"higher_bad"}`.

Mọi bảng/biểu đồ cùng tham chiếu một JSON canonical. SVG tự tính trục kể cả âm,
GDP <3% đỏ; CPI cao là đỏ, không dùng dấu số để áp dụng chung cho mọi chỉ tiêu.
Phát hiện tràn trang trước in, ghi kỳ/trang/partial/phần tử rồi hủy, không cắt chữ.
PDF catalog giữ bất biến, fingerprint chống tạo lại bản giống nhau; đổi dữ liệu/
template sinh phiên bản mới. Các bản macro Markdown cũ vẫn giữ nguyên.

```powershell
& C:/Users/ADMIN/.venv/Scripts/python.exe -m pytest -q tests/test_macro_stocklens.py
```

JSON ví dụ **dữ liệu thật** và PDF 8 trang: `output/pdf/macro-9T-2026.{json,pdf,html}`.
Audit đi kèm: `macro-9T-2026.quality_report.json`; ảnh QA: `tmp/macro-qa/page-*.png`.
Không dùng các fixture kiểm thử làm đầu vào sản xuất.

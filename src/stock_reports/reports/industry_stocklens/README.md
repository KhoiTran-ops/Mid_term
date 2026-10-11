# StockLens Industry

Module độc lập `JSON ngành → Jinja2 HTML/CSS → Chromium PDF`. Không gọi điểm FA/TA,
strategy_engine hoặc bộ dữ liệu vĩ mô để lấp chỗ thiếu của ngành.

## Chạy

```powershell
& C:/Users/ADMIN/.venv/Scripts/python.exe run.py render-industry --industry plastics --period 2025-12 --out output/pdf/industry-plastics-2025-12.pdf --qa-dir tmp/industry-qa
& C:/Users/ADMIN/.venv/Scripts/python.exe run.py render-industry --industry ngan-hang --period 2026-10 --out output/pdf/industry-banking-2026-10.pdf
& C:/Users/ADMIN/.venv/Scripts/python.exe run.py render-industry --industry my-sector --period 2026-Q3 --input my-industry.json --out output/pdf/my-industry.pdf
```

Lệnh đầu dùng JSON ví dụ `config/industry/periods/plastics/2025-12.json` đã đánh dấu
`meta.example=true`. CLI ghi rõ minh họa; loader web từ chối dùng ví dụ cho báo cáo thật.
Không tự gán `plastics` cho DNSE `nguyen-vat-lieu`: hai phạm vi này không đồng nhất.

Kỳ hỗ trợ: `YYYY-MM`, `YYYY-Q1…Q4`, `YYYY-9T`, `YYYY`. Kỳ báo cáo ngành không phải
kỳ BCTC. Mỗi bảng ghi đúng kỳ riêng, ví dụ báo cáo 10/2026 chứa BCTC năm 2025.

Mỗi lần xuất có PDF, JSON chuẩn hóa, HTML nhúng font và `<tên>.quality_report.json`.
CLI còn ghi `quality_report.json` (bản xuất gần nhất) cạnh PDF. Dùng audit cùng tên
khi cần giữ nhiều ngành/kỳ. `--pages` nhận các tên partial trong `render.PAGES`, cho
phép chọn và đổi thứ tự; `--keep-empty-pages` giữ các khối tĩnh chưa có dữ liệu.
`--accent '#RRGGBB'` đổi màu nhận diện, không đổi màu tín hiệu good/bad/warn.

## Cấu trúc / giao diện

- `schema.json`: JSON Schema, số hữu hạn/nullable, chuỗi, kỳ, phân biệt A/E/F.
- `data.py`: cấu trúc rỗng và chuẩn hóa; không suy dữ liệu hay tính dự phóng.
- `quality.py`: cơ cấu ±0,5%, CAGR ±0,3 đpt, YoY, đơn vị, kỳ, mã/sàn, ngày,
  nguồn dự phóng, quan điểm, giá mục tiêu và nhất quán số diễn giải (assertions).
- `charts.py`: SVG/CSS offline, trục lấy từ chuỗi thật, số âm đỏ, F nhạt/họa tiết,
  share bar chỉ vẽ nếu hợp lệ; không tự thêm phần Khác.
- `tokens.css`, `components.css`, `components.html`, `pages/*.html`: 16 partial
  A4 794×1123, Be Vietnam Pro + IBM Plex Mono nhúng WOFF2, nguồn ở từng khối.
- `render.py`: lập kế hoạch trang, bảng tối đa 19 mã/trang (ít hơn nếu có lý do dài),
  thêm trang cùng loại khi danh sách dài; hồ sơ 1–2 doanh nghiệp/trang. Đo tràn cả
  chiều ngang/dọc bằng Chromium trước khi commit; lỗi giữ PDF cũ và ghi audit.
- `pipeline/industry_periods.py`: adapter dữ liệu thật và snapshot nguồn theo SHA-256.

Trang thiếu nhóm số liệu tự ẩn, số `n / N` tự đánh lại. Nội dung quá dài mà không
thể chia theo cấu trúc sẽ **bị chặn**, không cắt chữ âm thầm hoặc giảm font vô hạn.
Không tự tạo văn bản phân tích. `summary.thesis`, các notes/drivers/business_points
được cung cấp trong JSON bởi biên tập viên có quyền sử dụng. Nội dung HTML được escape.

## Dữ liệu, nguồn và giả định

1. Ví dụ nhựa: số từ file HTML và bảng nghiệm thu người dùng cung cấp, không coi
   là dữ liệu ngành hiện tại. Danh mục 19 mã và nhóm doanh thu theo mẫu, không theo
   GICS DNSE. Các đoạn mô tả dài của bên thứ ba **không được sao chép nguyên văn**.
   `license_status=unknown`: bắt buộc watermark “chưa xác nhận bản quyền”.
   Ngày 12/12/2025 là ngày giao dịch trong mẫu, không giả định đó là ngày xuất bản.
   Ngày nguồn tham chiếu chỉ có độ chính xác tháng `2025-12`; ngày xuất bản chính
   xác để null. Metadata ngày chốt minh họa giữ 12/12/2025 theo bảng giao dịch.
2. Giữ các sai lệch gốc để phát hiện: chi phí VN tổng 101%, thị phần ống nhựa
   tổng 99,2%, LNST BMP sai nhãn nghìn tấn, ≈75% gán cho PE, upside BMP không
   khớp giá và mục tiêu, giá BMP vượt cao 52 tuần trong cùng hồ sơ. Không tự
   sửa số/thay nguồn. Audit liệt kê lỗi, trang bị ảnh hưởng ghi “cần kiểm tra”.
3. Phần “Kỹ thuật, khác” xuất khẩu 12% và phần còn lại AAA 8% có † và công thức.
   CAGR dự phóng 11,7→16,4 theo 5 năm đến 2029F; không kéo sang 2030 khi chưa có số.
4. DPC cùng kỳ lỗ: không tính YoY; ghi N/A với lý do. Số 0 hợp lệ vẫn là 0;
   thiếu là null + lý do, không dùng 0 làm dữ liệu thay thế.
5. Báo cáo thật: danh mục/snapshot DNSE, BCTC năm CafeF đã lưu với hồ sơ đối chiếu
   đơn vị `var/annual_reviews`, ảnh thị trường CafeF có ngày. BCTC chưa có hồ sơ
   đối chiếu không được gán đơn vị tỷ VND. %YoY tính tại adapter, ghi †.
   LNST là hợp nhất, không thay bằng LNST công ty mẹ. Vốn hóa chỉ dùng khi ảnh
   chỉ tiêu và giá đồng bộ ngày; không lấy ảnh hiện tại cho kỳ quá khứ.
6. Nhóm GICS cấp 2 là tập doanh nghiệp niêm yết, **không phải quy mô kinh tế toàn
   ngành**; bảng và hero ghi rõ phạm vi. Không tổng tài sản/doanh thu mẫu thiếu
   thành số tổng ngành. Năm hoàn chỉnh mặc định là năm trước ngày chốt kỳ.
7. NSO/Bộ Công Thương/Hải quan/ITC/EIA và các dịch vụ trả phí chưa có feed chuyên
   ngành được xác nhận ở dự án. Không giả vờ đã tải được dữ liệu Bloomberg/OPIS.
   Có thể cấu hình từng JSON bridge trong `config/industry_stocklens.json.json_sources`
   với `id`, `industry_id`, `period`, `url` HTTPS, `license_status=own|licensed`.
   Fetcher lưu JSON thô, URL, thời điểm, SHA-256; schema kiểm tra trước khi render.
   Không tải nội dung không có quyền rồi gán nhãn licensed.
8. Snapshot thô bất biến theo hash tại `var/industry/raw`; bản nháp kỳ tại
   `var/industry/periods/<ngành>/<kỳ>.json` được cập nhật. PDF web trong catalog
   bất biến; fingerprint gồm JSON và hash template/font, cùng dữ liệu dùng lại
   báo cáo cũ, khác dữ liệu tạo phiên bản mới. `--out` của CLI là đường xuất do
   người dùng chọn và có thể thay thế khi xuất lại, không phải kho phiên bản web.

## Web / kiểm thử

`config/industry_stocklens.json.enabled=true` bật cho mọi ngành có trong DNSE.
API tạo báo cáo dùng `kind=industry`, `industry_id`, `industry_period`, `as_of`.
Tải JSON/audit: `/api/reports/{id}/industry-data`, `/industry-quality`.
Không đổi báo cáo cũ; xuất mới chọn module này trước pipeline ngành legacy.

```powershell
& C:/Users/ADMIN/.venv/Scripts/python.exe -m pytest tests/test_industry_stocklens.py -q
& C:/Users/ADMIN/.venv/Scripts/python.exe -m pytest -q
```

CI `industry-report.yml` cài Chromium và chạy cả test mới lẫn regression ngành/web.
Test gồm thiếu nhóm/hồ sơ, đổi kỳ, chuỗi ngắn, số âm, tên dài, 43 mã, cơ cấu sai,
đơn vị sai, kỳ sai, nguồn thiếu, watermark, 16 trang, overflow fail-closed.

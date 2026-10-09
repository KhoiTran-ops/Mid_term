# Xác minh ngày 09/10/2026

## Phân tích, PDF và giao diện Stitch

- Toàn bộ **71 tests passed**, chạy `run.py test` ngoài sandbox với dữ liệu tạm trong
  `var/pytest-run`. Kết quả này thay thế giới hạn 58/63 của đợt trước.
- Kiểm chứng công thức chuyển YTD/TTM, khoảng trống quý, bình quân ROE, thiếu/0 mẫu số,
  profile tài chính, cổng đơn vị/thuyết minh, P/B pha loãng, ba kịch bản duy nhất,
  dữ liệu không hữu hạn/ngày tương lai, reuse báo cáo, nguồn và font PDF nhúng.
- Kiểm thử snapshot giữ giá trị đã đọc khi collector cập nhật database; không đọc lại
  đầu vào khác cho JSON sau khi đã tính báo cáo.
- API kiểm tra Host/Origin, mã/nhóm thiếu, không lộ tệp riêng hoặc raw inputs.
- Dữ liệu vĩ mô thật: 44 quan sát thuộc GDP/CPI/thương mại/FDI theo năm từ World Bank,
  lượt lấy không có lỗi. Năm quan sát được ghi rõ trong PDF.
- PDF thực: cổ phiếu SSI/chứng khoán, HPG/sản xuất, VCB/ngân hàng, ngành dịch vụ tài chính
  và tổng quan vĩ mô. Chưa có hồ sơ review/giả định thật nên không xuất giá mục tiêu giả.
- Render mọi trang qua Poppler, xem contact sheet và trang chi tiết để kiểm tra bố cục,
  bảng/biểu đồ, đánh số trang, nguồn và chữ tiếng Việt. Ảnh tại `var/pdf-check`.
- Browser Edge/Playwright: tab ba loại, lọc, xem/tải PDF, tạo vĩ mô từ giao diện, đóng dialog
  bằng Escape, tin Việt Nam/quốc tế/nguồn, font Noto Sans và responsive 320/390/768/1440px;
  không lỗi page và không tràn ngang. Ảnh tại `var/browser-check`.
- `pip check`, compile Python và `git diff --check`; lock thư viện được cập nhật.
- Web tại http://127.0.0.1:8001, collector tin/ngành tiếp tục chạy. Cổng 8000 của ứng dụng
  khác được giữ nguyên. Đã bắt đầu thêm lượt cập nhật giá/giao dịch HOSE cuối phiên.



## Đợt bổ sung dữ liệu/ngành/tin

- Thu thập giá DNSE thật: 1.522 cổ phiếu + VNINDEX, 45.589 nến ghi/cập nhật,
  không có lỗi trong manifest. Yêu cầu dữ liệu đến 14:16:42 +07; lượt chạy xong 14:56:26.
  Đây là số bản ghi xử lý, không phải 45.589 bản ghi mới hoàn toàn.
- BCTC HOSE: lượt đầu xử lý 406 mã, ghi 648 facts, 92 block bị từ chối/không có dữ liệu.
  Đã xác minh một số anchor trả 404 vẫn có số liệu trong bảng kỳ kế tiếp; sửa fallback,
  đếm kỳ duy nhất khi phân trang và cửa sổ 4 quý theo lịch. Lượt bổ sung hoàn tất 15:12:41, ghi/cập nhật 4.322 facts và 168 block bị từ chối;
  không khẳng định toàn bộ mã đã đủ 8 quý/cả ba báo cáo. Xem manifest và coverage mới nhất.
- DNSE ngành thật: 22 nhóm GICS cấp 2, 1.522 mã có hồ sơ/phân ngành,
  snapshot đọc được qua MQTT công khai. Watch chạy nền, giữ thời gian nguồn và dữ liệu gốc.
- Tin thật: lượt sau khi sửa parser/race thành công 19/19 nguồn; khoảng 1.600 tin đã lưu,
  bộ cập nhật web vẫn chạy. Ba liên kết menu VnEconomy nhận nhầm đã được lưu dấu vết
  sửa tại `var/jobs/news-menu-correction.json` rồi loại khỏi danh sách.
- 63 tests được thu thập. **58 kiểm thử đồng bộ qua** bằng pytest trong sandbox;
  5 kiểm thử asyncio/TestClient chưa hoàn tất trong sandbox. Không xóa hoặc skip test
  trong code/config. Lệnh đầy đủ cho người dùng vẫn là `run.ps1 test`.
- Lệnh chạy kiểm thử ngoài sandbox bị auto-review từ chối thực thi vì hết hạn mức
  của ứng dụng; chưa có kết quả toàn bộ 63 tests cho đợt này. Lượt trước đó đã qua 50 tests.
- Kiểm thử browser qua Edge/Playwright trên web thật cổng 8001: bộ lọc Việt Nam/quốc tế,
  nguồn BBC, mã HPG/từ khóa không dấu, ô tin trên trang chủ, refresh giữ input đang sửa.
  Mobile 390px không tràn ngang; không có lỗi console/page. Các assertion và ảnh đã xong;
  bước in kết quả tiếng Việt cuối script gặp lỗi encoding stdout Windows.
- Lỗi Jinja gọi nhầm `dict.items` đã được sửa dùng truy cập key. Hai nguồn gặp lỗi
  trong lượt tin đầu (race CNBC và cấu trúc Cục Thống kê) đã sửa, có test hồi quy.
- Kiểm thử hồi quy cho gap/404 BCTC, menu VnEconomy, dữ liệu protobuf thiếu field,
  chống trùng tin khi 8 thread cùng ghi, HTTP cache/backoff và phạm vi sàn.
- `pip check`, compile Python và `git diff --check` qua. Cập nhật requirements lock.

Ảnh kiểm tra tại `var/browser-check/news-desktop.png`, `news-mobile.png`,
`library-news.png`. Log tiến trình/lượt tải ở `var/jobs`, manifests ở `var/runs`.
Web mới tại `http://127.0.0.1:8001/news`; không dừng chương trình đang chiếm cổng 8000.

## Đợt tái cấu trúc nền tảng trước đó

- Chạy `run.ps1 test`: **50 passed**, gồm toàn bộ 34 kiểm thử cũ.
- Chạy `run.ps1 doctor` từ thư mục cha: nhận đúng gốc
  `F:\Mid_term_finance1\Mid_term`, database hiện có và `downloads_started=false`.
- Các lệnh help cho `data` và `import-legacy` chạy từ thư mục khác, không gọi API.
- Kiểm thử catalog: ba loại báo cáo, bộ lọc, phân trang, chữ ký PDF,
  metadata sai, rollback khi ghi database thất bại.
- Kiểm thử web: trạng thái trống, API/bộ lọc, escape HTML, khoảng ngày sai,
  chặn tệp riêng và đường dẫn PDF vượt kho.
- Kiểm thử publication: dùng renderer do bên gọi cung cấp, không đăng ký PDF
  dở dang khi renderer lỗi.
- Chạy web thật qua `run.ps1 web --port 8765`; kiểm tra Edge qua Playwright.
  Bộ lọc mã/ngành dùng catalog fixture ở server tạm riêng, không thêm báo cáo
  vào catalog thật. Kiểm tra desktop và mobile rộng 390px, không tràn ngang,
  không ghi nhận lỗi/warning trình duyệt. Server kiểm tra đã dừng.
- `pip check`: không có phụ thuộc xung đột. `git diff --check`: không có lỗi whitespace.
- Không gọi DNSE/CafeF trong đợt tái cấu trúc. File `var/market_data.db`
  vẫn có kích thước **1.010.827.264 byte**, thời điểm sửa **09/10/2026 13:23:21**.
  Đây là kiểm tra metadata tệp; không phải phép so sánh hash toàn database.

Chưa kiểm thử dữ liệu nguồn trực tiếp, nội dung báo cáo đầu tư hay renderer PDF
vì các tác vụ đó nằm ngoài phạm vi nền tảng lần này. Catalog thật hiện trống.

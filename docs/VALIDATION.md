# Xác minh nền tảng ngày 09/10/2026

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

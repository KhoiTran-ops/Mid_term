# Kế hoạch nền tảng

1. Chụp baseline mã hiện có; chuyển provider/storage/domain vào một package.
   Kiểm chứng bằng toàn bộ kiểm thử cũ, không gọi API thật.
2. Thêm cấu hình theo gốc dự án và hợp đồng dữ liệu cho các module tiếp theo.
3. Thêm kho PDF/metadata riêng, lọc theo loại/mã/ngành, phân trang và bảo vệ đường dẫn.
4. Thêm web đọc kho báo cáo, giao diện tra cứu cơ bản và kiểm thử HTTP/browser.
5. Thống nhất entrypoint và script tự chuẩn bị môi trường; viết hướng dẫn chạy.
6. Review cấu trúc, kiểm thử trọn bộ, chạy thực tế từ một thư mục shell khác.

Không tải dữ liệu DNSE/CafeF ở bất kỳ bước kiểm thử nào của lần này.

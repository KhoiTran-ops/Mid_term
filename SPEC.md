# Nền tảng hệ thống phân tích cơ hội đầu tư cổ phiếu

## Mục tiêu và phạm vi

Theo yêu cầu người dùng, hệ thống cuối cùng thu thập giá/giao dịch/chỉ số thị
trường, báo cáo tài chính và chỉ số tài chính, thông tin và tin doanh nghiệp,
dữ liệu vĩ mô và ngành. Đầu ra gồm PDF khuyến nghị từng cổ phiếu (có phần vĩ
mô/ngành), PDF vĩ mô độc lập và PDF ngành độc lập. Web tra cứu theo loại, mã
cổ phiếu/doanh nghiệp, ngành và ngày báo cáo.

Lần triển khai này xây nền tảng và ranh giới module; không tạo khuyến nghị giả,
không triển khai mô hình định giá hoặc PDF trước khi dữ liệu/phương pháp sẵn sàng.

## Kiến trúc và công nghệ

Python 3.12+, FastAPI/Uvicorn, Jinja2, SQLite. Mã tại `src/stock_reports`.
Giữ nguyên `var/market_data.db`, `.env`, raw archive và các dữ liệu đã tải.
Kho metadata báo cáo dùng `var/reports.db`, tệp PDF dùng `outputs/reports`;
web không được đọc `.env`, raw archive hoặc tùy ý đường dẫn từ request.

## Lệnh chung

`powershell -ExecutionPolicy Bypass -File .\run.ps1` khởi chạy web mặc định.
Các chế độ `doctor`, `data`, `reports`, `test` đều qua script này.
`run.py` là entrypoint Python duy nhất bên dưới. Không tự tải khi mở web.
Mọi đường dẫn tương đối được giải theo gốc dự án, không theo thư mục shell.

## Hợp đồng

- Dữ liệu có nguồn, kỳ/thời điểm, đơn vị và trạng thái chất lượng.
- Kết quả phân tích tách dữ kiện, giả định, luận điểm, rủi ro và bằng chứng.
- Báo cáo gồm `stock`, `industry`, `macro`; báo cáo cổ phiếu cần mã và ngành,
  báo cáo ngành cần ngành, báo cáo vĩ mô không gắn một mã cổ phiếu.
- PDF chỉ xuất bản sau khi tệp tồn tại, có định dạng PDF, metadata hợp lệ.
- API danh sách có bộ lọc và phân trang; web chỉ có thao tác đọc trong giai đoạn này.
- Module chưa triển khai có hợp đồng/đặc tả và task rõ ràng, không có dữ liệu mẫu
  giả hoặc hàm trả khuyến nghị mặc định.

## Phong cách và kiểm thử

Tên Python snake_case, lớp PascalCase; type hints tại ranh giới module.
Ví dụ: `catalog.list_reports(kind=ReportKind.STOCK, symbol="HPG", page=1)`.
Giữ toàn bộ 34 kiểm thử hiện có; thêm kiểm thử cho đường dẫn khi di chuyển,
loại báo cáo, bộ lọc, phân trang, tệp thiếu/đường dẫn vượt kho, API và script.
Test dùng dữ liệu tạm, không tải API thật và không ghi vào dữ liệu đã lưu.

## Tiêu chí nghiệm thu

1. Bộ lấy dữ liệu DNSE/CafeF giữ hành vi và vượt qua kiểm thử cũ sau khi di chuyển.
2. Một script mặc định mở web; chế độ kiểm tra/cập nhật/xuất dữ liệu có hướng dẫn.
3. Web hiển thị trạng thái rỗng đúng và tra cứu được PDF đã đăng ký theo loại/mã/ngành.
4. Không sửa nội dung database thị trường, không khởi động lại tải dữ liệu.
5. Có sơ đồ kiến trúc, hợp đồng và thứ tự triển khai các tính năng tiếp theo.

## Ranh giới

Luôn: kiểm thử sau mỗi lát cắt, ghi rõ chức năng đã có và chưa có, bảo toàn dữ liệu.
Không: đẩy GitHub/triển khai công khai, khởi động tải ngầm, bịa ngành hoặc khuyến nghị.
Nguồn tin/vĩ mô/ngành và phương pháp phân tích sẽ chọn ở bước thực hiện tương ứng.

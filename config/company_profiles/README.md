# Bổ sung thông tin doanh nghiệp có nguồn

Tệp: `<MÃ>.json`; gồm `symbol` và mảng `facts`. Không tạo dữ liệu mẫu cho một mã thật.
Mỗi fact cần:

- `category`: `overview`, `history`, `shareholders`, `subsidiaries`, `segments`,
  `operations`, `risks` hoặc `forecast_assumptions`.
- `label`, `value`: tên chỉ tiêu và nội dung công bố. Thiếu đầu vào không nhập số 0.
- `period`: kỳ quan sát hoặc kỳ dự phóng, thí dụ năm dưới dạng chuỗi hoặc có hậu tố F.
- `source`: `source_name`, `url`, `retrieved_at`, `locator`; `published_at` nếu có.
  Nguồn cục bộ dùng `url: null` và phải có locator. Nguồn xuất bản sau ngày chốt bị loại.
- `numeric`, `unit`: tùy chọn khi có số kiểm chứng.
- `dimension`: `product` / `market` cho cơ cấu doanh thu theo sản phẩm / thị trường.

Biểu đồ tròn chỉ xuất khi có ít nhất hai thành phần, cùng kỳ, mỗi thành phần
có numeric và unit `%`, tổng bằng 100% (dung sai 0,01 điểm phần trăm). Không tự tạo
“cổ đông khác” hoặc phần doanh thu còn lại. Hai biểu đồ doanh thu đủ điều kiện
được xếp cạnh nhau; chưa đủ dữ liệu chỉ giữ bảng thiếu.

Giả định vận hành ở bảng V lấy `forecast_assumptions`: label khớp tên biến,
period khớp năm hoặc năm F. Các giá trị mâu thuẫn cùng biến/kỳ giữ thiếu,
không tùy ý chọn một nguồn. Đây không phải kênh nhập lệnh hay prompt cho hệ thống.

# Đối chiếu bản dàn trang báo cáo ngành ngân hàng

## Phạm vi

- Dữ liệu và tin tức: chỉ từ `industry-ngan-hang-2026-10-09.pdf` (5 trang).
- Mẫu trình bày: `FPTSBao_cao_nganh_nhua_202512_b7ba2f82.pdf`; không sử dụng dữ liệu ngành nhựa, ảnh, tên thương hiệu hoặc logo.
- Bản mới: PDF A4 dọc, 9 trang, lề 2 cm, Arial, thân bài 10,5 pt; nhận diện navy trung tính.
- Bốn biểu đồ vĩ mô được chia hai trang, mỗi trang hai biểu đồ theo lựa chọn của người dùng.

## Các chỗ đã gộp / lược / chuyển vị trí

| Nội dung gốc | Xử lý trong bản mới | Nơi kiểm tra |
|---|---|---|
| Tóm tắt và mục I lặp danh mục DNSE 28 mã, thời điểm snapshot | Giữ nội dung, rút thành ba thông điệp bìa và tiêu điểm; thông tin đầy đủ ở B | Trang 1, 2, 6 |
| Bảng DNSE 5 kỳ ở trang 1, lặp trong bảng 8 kỳ trang 2 | Gộp thành một biểu đồ cột đủ tám kỳ, nhãn giữ chính xác giá trị gốc | Trang 6 |
| Cảnh báo đơn vị/phương pháp DNSE và không ghép OHLCV | Gộp vào khung Lưu ý dữ liệu, không gắn ký hiệu % khi chưa kiểm chứng | Trang 8 |
| Cảnh báo mẫu dưới 3 doanh nghiệp, không đại diện ngành, không trung bình chéo mô hình | Gộp trong cùng khung; giữ yêu cầu mẫu 3-5, không bỏ ý | Trang 8 |
| Chất lượng ACB/VCB: chưa kiểm chứng scope/đơn vị | Chuyển khỏi cột bảng sang khung Lưu ý dữ liệu; cả hai ô biên LNST vẫn thiếu | Trang 7, 8 |
| Bốn đoạn vĩ mô lặp “quan sát năm, không phải tháng/quý” | Gộp số liệu 2025 và thay đổi so với 2024 thành bảng; cảnh báo tần suất tập trung ở khung | Trang 4, 8 |
| Bốn đồ thị World Bank | Tái sử dụng phần đồ thị gốc ở độ phân giải cao, không số hóa hoặc ước tính các điểm 2015-2025; thay tiêu đề và thêm nguồn/đơn vị | Trang 4, 5 |
| Năm đoạn tin tức | Chuyển thành bảng đủ nguồn, tiêu đề, ngày và mức liên quan; giữ nguyên cả tin Guardian, không tự loại tin hay bổ sung tin mới | Trang 5 |
| Ngày tin VnEconomy “chưa rõ” | Chuẩn hóa ô thiếu thành “Chưa đủ dữ liệu”; các ngày còn lại giữ múi giờ UTC | Trang 5 |
| Chưa có đánh giá mức liên quan của từng tin trong đầu vào | Điền “Chưa rõ” cho cả năm tin, không suy diễn cao/thấp và không đánh giá tác động định lượng | Trang 5 |
| Các câu hỏi NIM, nợ xấu, nhóm 2, dự phòng, CAR lặp trang 2 và 5 | Gộp thành ba khung câu hỏi, giữ nguyên ý nghĩa | Trang 7 |
| Hai giả định tác động lãi suất / tăng trưởng ở trang 3 | Chuyển vào khung giả định truyền dẫn, giữ dạng điều kiện, không đổi thành kết luận | Trang 6 |
| Cảnh báo độ trễ, điều chỉnh, look-ahead và nhân quả tin tức lặp trang 1/5 | Chỉ giữ đầy đủ một lần trong khung Lưu ý dữ liệu | Trang 8 |
| Chưa có chuỗi lãi suất, tỷ giá, tín dụng tháng đã kiểm chứng | Chuyển vào khung Lưu ý dữ liệu, giữ nguyên không sinh dự báo | Trang 8 |
| Phụ lục nhắc công thức / JSON snapshot nhưng không có nội dung công thức hoặc tệp JSON đính kèm | Giữ ghi chú phương pháp financials-1.0, nói rõ không tái tạo phần không được cung cấp | Trang 9 |
| Danh mục nguồn [1]-[13] và miễn trừ | Giữ đủ 13 mục, thời điểm thu thập, định vị và liên kết gốc; giữ tuyên bố miễn trừ | Trang 9 |
| “Đánh giá ngành theo nguồn dữ liệu”, nhãn phân tích tự động và các nhãn “Khung phân tích / giả định” lặp | Lược nhãn hệ thống và thay bằng đề mục có ý nghĩa; các giả định vẫn được đánh dấu rõ | Toàn bản |

Không bỏ số liệu định lượng nào trong bản gốc. Không thêm số liệu, dự báo, đánh giá tác động hoặc khuyến nghị đầu tư. Mục khuyến nghị của cả hai kỳ chỉ ghi “Chưa đủ cơ sở khuyến nghị”.

## Kiểm tra bản xuất

- Đã render và kiểm tra trực quan cả 9 trang: chữ tiếng Việt, bảng, nhãn biểu đồ, nguồn, mục lục và chuyển phần.
- Đã kiểm tra đầy đủ các quan sát định lượng gốc, 13 URL nguồn duy nhất và đầu/chân trang của mọi trang.
- Hai dòng khuyến nghị chỉ dùng “Chưa đủ cơ sở khuyến nghị”; không có tên/logo thương hiệu mẫu hay nhãn đánh giá bị cấm.
- Ô biên LNST của cả ACB và VCB tiếp tục ghi “Chưa đủ dữ liệu”; không thay thiếu bằng 0.

## Năm dữ liệu còn thiếu để nâng mức phân tích

Đây là danh sách đầu vào cần bổ sung theo yêu cầu, không phải khẳng định rằng chỉ cần đủ chúng là có thể khuyến nghị:

1. NIM: thu nhập lãi chuẩn hóa 12 tháng và tài sản sinh lãi bình quân.
2. Nợ xấu, nợ nhóm 2 và bao phủ dự phòng theo cùng định nghĩa.
3. CAR với thuyết minh và cơ sở tính nhất quán.
4. P/B ngành với đơn vị, phương pháp và đầu vào đã kiểm chứng (chưa có trong PDF gốc).
5. Thêm doanh nghiệp so sánh cùng kỳ, cùng định nghĩa để đạt mẫu 3-5 doanh nghiệp đủ đầu vào.

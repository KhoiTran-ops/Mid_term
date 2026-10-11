# Thiết kế lại từ bản nội dung Markdown

## Phạm vi

Nguồn nội dung duy nhất: `C:\Users\ADMIN\Downloads\Báo cáo ngành Ngân hàng – 10 2026.md`.

Bản PDF mới giữ nhận diện trung tính, navy, Arial, A4 dọc và lề 2 cm. Không thay thế bản PDF đã giao trước. Không cập nhật website hoặc lấy dữ liệu trực tuyến.

## Cách tổ chức lại

- Giữ năm tiêu điểm, thêm bìa và mục lục; khuyến nghị ngắn/trung hạn và dài hạn đều là “Chưa đủ cơ sở khuyến nghị”.
- Vĩ mô: giữ đủ bốn số năm 2025, thay đổi so với 2024, giả định truyền dẫn và năm tin tức; giữ phân loại trong nước/quốc tế theo Markdown.
- Ngành: chuyển bảng tám kỳ DNSE thành biểu đồ cột có nhãn số chính xác, không tự gắn ký hiệu %. Giữ bảng so sánh bảy nhóm GICS và vị trí 13/22, 5/22.
- Doanh nghiệp: giữ đủ bảng tài chính quý 2/2026, giá, khối lượng, 11 chỉ báo tính sơ bộ và năm nhận xét gốc. Tách số liệu gốc và chỉ báo sơ bộ thành hai trang.
- Không tính lại tăng trưởng, ROE hoặc bất kỳ chỉ báo nào. Ký hiệu xấp xỉ và cảnh báo “không phải NIM” được giữ.
- Các ô công thức tăng trưởng trống được dẫn đến công thức có sẵn trong phụ lục, không tự tạo công thức mới. Các ô trống khác và ngày đăng chưa rõ được ghi “Chưa đủ dữ liệu”.
- Gom các giới hạn chất lượng thành khung “Lưu ý dữ liệu”: đơn vị VND chưa xác nhận; hợp nhất/riêng, quý/lũy kế; mẫu 2/28; DNSE chưa kiểm chứng; dữ liệu vĩ mô năm; độ trễ; tin tức và dòng tiền chưa đầy đủ.
- Giữ bảng dữ liệu cần bổ sung, các rủi ro và điều kiện xem xét lại đánh giá ngành.
- Đánh lại số bảng trong PDF theo thứ tự trình bày, gán nguồn [1]-[9] theo chín nhà cung cấp được nêu trong Markdown. File Markdown này không có danh mục 13 URL như bản PDF cũ; không gán các URL cũ vào số liệu mới để tránh tạo cảm giác đã xác minh nguồn.
- Không dựng chuỗi đường vĩ mô 2015-2025 vì bản Markdown chỉ có số năm 2025; không ước tính hoặc lấy điểm từ bên ngoài.

## Những điểm cần kiểm chứng, không bị sửa thành kết luận mới

- Dòng tiêu điểm ACB nêu LNST Q2/2026 giảm 12,1% so với cùng kỳ; nhận xét ACB dùng cụm “LNST đi ngang so với nửa đầu 2025”. Giữ hai phạm vi thời gian như nguồn, không đồng nhất chúng. Chỉ báo nửa đầu năm trong bảng là LNTT, không tự đổi thành LNST.
- Chi phí hoạt động VCB được nêu +40,2% trong bảng và “40%” trong nhận xét: giữ nguyên mức chi tiết của từng chỗ.
- Tỷ số thu nhập lãi thuần / tài sản bình quân gần 2,9-3,0% không phải NIM.
- P/B, EPS và các đầu vào định giá chưa đủ; không tạo giá mục tiêu hoặc khuyến nghị.
- Markdown không cung cấp URL hoặc BCTC gốc để xác minh các số mới. Danh mục nguồn PDF chỉ ghi tên, phạm vi và thời điểm đã có trong bản nội dung.

## Năm nhóm dữ liệu ưu tiên bổ sung

1. NIM và tài sản sinh lãi bình quân.
2. Nợ xấu, nhóm 2, bao phủ dự phòng.
3. CAR và dư nợ cho vay có ánh xạ duy nhất.
4. Đơn vị/phạm vi BCTC cùng số cổ phiếu, VCSH công ty mẹ, EPS cho định giá.
5. Thêm ngân hàng cùng kỳ để đạt nhóm 3-5 doanh nghiệp đủ đầu vào.

## Kiểm tra bản xuất

- Đã render và kiểm tra trực quan toàn bộ 10 trang: không phát hiện chữ/bảng bị cắt, chồng nội dung hoặc lỗi ký tự tiếng Việt.
- Đã đối chiếu mọi giá trị thập phân và số tài chính viết bằng dấu phân nhóm trong Markdown: không có giá trị bị bỏ hoặc thay đổi.
- Giữ đầy đủ 11 chỉ báo sơ bộ, năm nhận xét doanh nghiệp, bảy dòng dữ liệu cần bổ sung, chín nhà cung cấp và công thức/miễn trừ.
- Kiểm tra đầu/chân trang, ngày chốt, số trang, mục lục; không có tên/logo mẫu hoặc nhãn khuyến nghị bị cấm.
- Khối lượng được giữ theo bảng trong Markdown, không tự khẳng định nhà cung cấp riêng khi tài liệu chưa định vị nguồn cho trường này.

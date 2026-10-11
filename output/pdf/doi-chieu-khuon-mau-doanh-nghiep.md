# Đối chiếu báo cáo doanh nghiệp theo khuôn mẫu

## Đã áp dụng

- Bìa kết luận trước: khuyến nghị, giá hiện tại/ngày, giá mục tiêu 12 tháng, tiềm năng;
  luận điểm, rủi ro và bảng thông tin giao dịch.
- Đủ mục I–VIII: tổng quan, ngành, kinh doanh, tài chính, dự phóng, rủi ro,
  định giá/khuyến nghị, phụ lục. Mục VII có đủ 7.1–7.10.
- Bảng 5 năm tách khỏi kỳ quý mới nhất; BCTC chi tiết 8 kỳ giữ trong phụ lục.
  Không dùng quý 4 thay số cả năm, không dùng EPS TTM thay EPS dự phóng năm tới.
- P/B, BVPS dùng giá trị vốn cuối kỳ; EPS/P/E TTM ghi đúng kỳ. Bình quân giao dịch
  ghi 30 phiên, không giả nhận là 30 ngày lịch. Giá 52 tuần chỉ hiện nếu cửa sổ đủ dài
  và đơn vị giá được xác nhận; không suy ra sở hữu nước ngoài từ hạn mức giao dịch.
- Cơ cấu cổ đông và hai cơ cấu doanh thu có biểu đồ khi có dữ liệu cùng kỳ đầy đủ;
  thiếu dữ liệu không vẽ biểu đồ giả. Dữ liệu bổ sung có nguồn đọc từ `config/company_profiles`.
- Các cảnh báo ánh xạ lặp cùng chỉ tiêu được gộp theo danh sách quý, vẫn giữ nguyên
  mọi kỳ bị ảnh hưởng; cảnh báo đầy đủ cũng lưu trong hồ sơ JSON.
- Nguồn đánh số ở cuối, dẫn vào bảng/biểu đồ và câu có số; không tạo URL giả.

## Phần định giá đã mở rộng

- P/B hợp lý theo ROE cho ngân hàng, có kiểm tra ROE thị trường hàm ý và kiểm tra đảo ngược.
- FCFF, FCFE và NAV; không mặc định tiền/nợ bằng 0, không cộng tiền/trừ nợ lần nữa ở FCFE.
- Tổng hợp nhiều phương pháp chỉ khi trọng số được nhập rõ và cộng đủ 100%.
- Độ nhạy chỉ tính từ trục người soạn cung cấp. Ba kịch bản giữ đúng tên và kiểm tra thứ tự,
  chiều giảm, thời hạn và thuyết minh; không sửa số để đạt khuyến nghị mong muốn.
- Không tự gán tăng trưởng, suất chiết khấu, thời điểm chiết khấu hoặc xác suất.
- Ngưỡng theo khuôn mẫu: ≥ +15% / ≤ -10%; không còn ngưỡng giảm -15% của bản trước.

## Các phần chưa thể điền trong bản VCB

Kho có BCTC quý, dữ liệu giao dịch và nhóm so sánh. Chưa có hồ sơ review xác nhận
đơn vị/scope/thuyết minh, số cổ phiếu và bộ giả định định giá được phê duyệt cho VCB.
Vì vậy giá mục tiêu và khuyến nghị mua/bán vẫn bị chặn. Bản này không tuyên bố thiếu
BCTC; số quý có sẵn vẫn được trình bày như dữ liệu nguồn chưa kiểm chứng.

Cổ đông, công ty con, thị phần, NIM/CASA/CAR, cổ tức và dự phóng còn thiếu nguồn
phù hợp thì ghi “Chưa đủ dữ liệu”; không lấy thông tin dự đoán từ tên ngành.
Nhóm so sánh thực tế loại VCB khỏi tập trung vị; dưới 3 mã có bội số cùng kỳ được
kiểm chứng không tính trung vị.

## Phạm vi

Bộ tạo dùng khuôn mới cho mọi báo cáo cổ phiếu qua CLI và web, không chỉ riêng VCB.
Bản PDF VCB ngày 09/10/2026 là bản minh họa từ dữ liệu thực hiện có. Báo cáo ngành và
bản vĩ mô theo Markdown được giữ bố cục riêng. Bản Markdown gốc trong Downloads
không bị sửa. Không thêm giả định định giá vào cấu hình sản xuất của bất kỳ mã nào.

# Phân tích và xuất PDF - 09/10/2026

Ba đầu ra bắt buộc: cổ phiếu, ngành, vĩ mô. Báo cáo cổ phiếu tái sử dụng bộ phân tích
vĩ mô/ngành và bổ sung doanh nghiệp, tài chính, kỹ thuật, định giá, khuyến nghị/rủi ro.
Mẫu SSI dùng làm tham chiếu bố cục, không làm nguồn số liệu hiện tại hay nhận định mặc định.
Web áp dụng bố cục/design Stitch, dùng chung catalog/API/bộ lọc; không thêm các chức năng
đăng nhập/tổ chức phát hành giả. Font Noto Sans có tiếng Việt được lưu cục bộ và nhúng vào PDF.

| Module | Nghiệm thu |
|---|---|
| financials | Đọc 8 kỳ, ánh xạ chỉ tiêu có kiểm tra trùng; thiếu giữ None; review đơn vị/scope/basis có nguồn; YTD chuyển quý theo cùng năm; TTM đủ 4 quý liên tiếp; bình quân đầu/cuối khi cần |
| analysis | Profile ngân hàng/chứng khoán/BĐS/sản xuất và nhóm khác; mô hình chứng khoán từ cơ cấu doanh thu; không dùng D/E hoặc CFO để chấm doanh nghiệp tài chính như sản xuất |
| macro | Chuỗi World Bank có năm quan sát rõ, tin vĩ mô chính thức đã lưu, diễn giải có nguồn và chuỗi tác động theo ngành; không tạo dự báo GDP/CPI hiện tại từ tin |
| industry | Snapshot GICS DNSE + doanh nghiệp cùng nhóm; so sánh từng mã cùng kỳ, không gọi trung bình nhóm khác mô hình là chuẩn ngành |
| valuation | Kịch bản P/B hoặc P/E từ giả định nhập rõ; cần đầu vào VND và mẫu số đã kiểm chứng; dữ liệu thiếu không sinh giá mục tiêu/mua-bán giả |
| reports | PDF thực cho cả 3 loại, bảng/biểu đồ/công thức/nguồn/chất lượng; JSON snapshot cho tái kiểm tra; dùng ReportPublisher và catalog hiện có |
| web | Card/grid, tabs cổ phiếu/ngành/vĩ mô, bộ lọc và tin hiện có, preview PDF và một luồng tạo báo cáo dùng cùng service CLI; responsive, không có nút giả |

CLI và web dùng chung service tạo báo cáo; đọc dữ liệu đã lưu, không tải lại toàn thị trường
mỗi lần tạo PDF. Tin mới không sửa số liệu kế toán. BCTC gốc và thuyết minh vẫn là nguồn
đối chiếu riêng, không đổi nhãn PDF phân tích thành báo cáo tài chính chính thức.

Thứ tự: contracts/formulas/tests -> macro/ngành/cổ phiếu -> renderer -> publication/CLI
-> Stitch UI/preview/generation -> PDF render + browser + toàn bộ tests -> hướng dẫn.

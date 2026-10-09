# Tiến độ và tính năng tiếp theo

- [x] F01: Tái cấu trúc provider/storage/domain và giữ kiểm thử cũ.
- [x] F02: Cấu hình di chuyển được, hợp đồng dữ liệu/phân tích/PDF.
- [x] F03: Kho báo cáo và bộ lọc loại/mã/ngành/ngày, kiểm thử bảo vệ PDF.
- [x] F04: Web cơ bản và script chạy chung, kiểm thử từ thư mục khác.
- [x] F05: Hướng dẫn, review và xác minh không khởi động tải dữ liệu.

Sau nền tảng:

- [x] N01: Tiếp tục tải HOSE, bộ chọn sàn và tiến độ/manifest mỗi lượt.
- [x] N02: Phân trang BCTC theo kỳ duy nhất, xử lý cửa sổ quý có khoảng trống và anchor 404.
- [x] N03: Chuyển RSS/Atom/listing từ market-pulse; kho, cache, backoff, chống trùng và lịch nền.
- [x] N04: Ô tin mới và trang tin có bộ lọc Việt Nam/quốc tế riêng.
- [x] N05: Danh mục GICS cấp 2, ánh xạ mã và snapshot ngành DNSE có phản hồi gốc.

- [ ] D01: Xác minh đơn vị và cơ sở quý/lũy kế; xử lý chất lượng dữ liệu tài chính.
- [ ] D02: Mở rộng hồ sơ doanh nghiệp; ánh xạ GICS đã có từ DNSE, cần nối với đầu vào phân tích.
- [ ] D03: Kiểm chứng liên kết tin với mã/ngành; thu thập/ngày đăng/chống trùng đã có.
- [ ] D04: Dữ liệu vĩ mô/nguồn tin chính thức, ngày công bố và phiên bản điều chỉnh.
- [ ] D05: Chuẩn hóa đơn vị snapshot ngành, nhóm so sánh; catalog và dữ liệu gốc DNSE đã có.
- [ ] D06: Chỉ số tài chính ROE/ROA/EPS/P/E/P/B sau khi hoàn thành D01.
- [x] A01 (v1, dữ liệu năm): Phân tích vĩ mô độc lập có bằng chứng và tác động tới thị trường.
- [x] A02 (v1, snapshot/peer): Phân tích ngành độc lập có bằng chứng và động lực/rủi ro.
- [x] A03 (v1, có cổng chất lượng): Phân tích kỹ thuật, tài chính và tin doanh nghiệp.
- [x] A04 (v1, P/B/P/E từ giả định nhập): Dự phóng/định giá/kịch bản; quy tắc khuyến nghị và điều kiện thay đổi.
- [x] R01: PDF vĩ mô và ngành; render và kiểm tra bố cục.
- [x] R02: PDF cổ phiếu kết hợp phân tích doanh nghiệp/vĩ mô/ngành/định giá.
- [x] P01 (v1): Pipeline từ dữ liệu tới phân tích/PDF/xuất bản; lưu lỗi và truy nguồn.
- [x] W01 (v1): Thư viện Stitch, chi tiết/preview PDF, chất lượng và hàng đợi tạo; giữ bản cũ theo ID/thời điểm.
- [ ] W02: Gom lịch sử phiên bản theo doanh nghiệp/ngày thay vì các card riêng.

Mỗi task D/A/R/P/W cần tiêu chí nghiệm thu và kiểm thử riêng trước khi triển khai.


Đã có framework kiểm chứng D01/D06, nhưng **chưa xác minh đầy đủ dữ liệu thật mọi mã**.
D04 hiện có bốn chuỗi World Bank theo năm; cần bổ sung lãi suất/tỷ giá/tín dụng tháng.
D05 có so sánh cùng kỳ/profile; đơn vị snapshot DNSE còn cần đối chiếu.
A04 không bao gồm DCF/NAV hay dự phóng chuyên sâu khi thiếu thuyết minh.
R/P/W đã có đầu ra thực; xem docs/VALIDATION.md và docs/RESEARCH_METHODS.md.

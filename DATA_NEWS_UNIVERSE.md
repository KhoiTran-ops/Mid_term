# Báo cáo doanh nghiệp và tin tức toàn danh mục

## Cơ chế cập nhật

- Engine FA/TA và mẫu StockLens dùng chung cho mọi mã, không có nhánh chỉ dành cho FPT. Đầu vào thiếu vẫn là `None`.
- Nhận diện tin dùng toàn bộ danh mục doanh nghiệp trong `market_data.db`, cộng các bí danh đã đối chiếu. Các mã trùng từ thông thường cần ngữ cảnh chứng khoán.
- CafeF RSS thăm dò mỗi phút; VnEconomy RSS mỗi hai phút; các RSS còn lại thường ba phút. Nguồn công bố/nghiên cứu có lịch riêng. Khi nguồn lỗi, hệ thống backoff và hiển thị trạng thái; không bảo đảm độ trễ tức thời.
- Danh sách tin và tin doanh nghiệp trên trang báo cáo làm mới mỗi 30 giây khi trang đang hiển thị.
- Tin nổi bật ưu tiên ngày đăng tại Việt Nam, tiêu đề trực tiếp về mã, sự kiện kinh doanh/tài chính rồi thời gian đăng. Không có dữ liệu lượt đọc, nên không phải bảng xếp hạng mức độ phổ biến thực tế.
- Không lấy tin của doanh nghiệp khác để lấp khoảng trống. Nếu hôm nay không có tin, hiển thị rõ tin liên quan gần nhất.
- Báo cáo cổ phiếu đã có trong thư viện được kiểm tra thay đổi mỗi phút, giãn mỗi lần tạo ít nhất năm phút/mã. Mã mới được tạo khi người dùng yêu cầu. Không tự tạo hàng nghìn PDF không được yêu cầu.
- PDF là bản chốt dữ liệu theo ngày. Khi dữ liệu thay đổi, tạo phiên bản mới; bản đang đọc vẫn được giữ và trang báo cáo dẫn tới bản mới. Nội dung không đổi dùng lại báo cáo đã có.
- Trang tin trong PDF ưu tiên hai tin; tiêu đề/trích đoạn dài được rút gọn có thông báo. JSON giữ đầy đủ tin đã chọn và liên kết. Các kênh của cùng nhà xuất bản gộp trong bảng nguồn, không bỏ liên kết hay cảnh báo.

## Tải và kiểm kê BCTC

- Tải năm 2021–2025 và tối đa 24 quý đã công bố, giữ mọi dòng thành phần nguồn trả về cùng nguồn, thời điểm và bản lưu phản hồi.
- Dữ liệu đã tải được tái sử dụng; kỳ trống được thử tiếp. Một mã lỗi không làm dừng toàn danh mục. JSON tiến độ ghi nguyên tử và thử lại khi Windows khóa tạm thời.
- Theo dõi tại `/api/data-status` và `outputs/FINANCIAL_COMPLETE_PROGRESS.json`.
- `tasks/audit_financial_coverage.py` kiểm kê hiện diện ba bảng. `tasks/audit_company_components.py` kiểm tra từng chỉ tiêu năm/quý theo mô hình doanh nghiệp, ghi `outputs/COMPANY_COMPONENT_AUDIT.json`.
- `tasks/finalize_financial_refresh.py --run var/runs/financial-complete-20261010T132550 --audit-only` đang chờ lượt tải này hoàn tất để chạy lại cả hai bản kiểm kê. Báo cáo trong thư viện do web đang chạy tự cập nhật theo dữ liệu đã ghi thành công.
- Có dòng số liệu không đồng nghĩa đã đủ thuyết minh hay đối chiếu tài liệu gốc. Không tự xác nhận đơn vị, phạm vi hợp nhất, cổ phiếu lưu hành, kỳ quý/lũy kế, hoặc khuyến nghị đầu tư khi thiếu căn cứ.
- Nguồn có thể không cung cấp một số kỳ, nhất là trước ngày niêm yết hoặc chưa công bố. Không tạo số liệu để làm đầy báo cáo.

## Vận hành và khôi phục

- Nguồn RSS chính thức: https://cafef.vn/index.rss và https://vneconomy.vn/rss.html. Chỉ lưu tiêu đề/trích đoạn nguồn cung cấp, ghi nguồn và liên kết gốc.
- Tin cũ được phân loại lại theo chính sách tài chính và danh mục mở rộng. Bản sao trước đợt này: `var/news-before-universe-20261011T090017.sqlite3`; dùng SQLite backup để khôi phục khi đã dừng collector, không ghi đè DB đang chạy.
- Trạng thái nguồn: `/api/news/sources`. Trạng thái cập nhật PDF: `/api/report-refresh-status`.
- Tiến trình tải BCTC giữ khóa CafeF chung và giới hạn một yêu cầu/giây. Không chạy song song collector tài chính khác.

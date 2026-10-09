# Các module của hệ thống báo cáo đầu tư

| Module | Trách nhiệm | Phụ thuộc |
|---|---|---|
| core | Cấu hình, đường dẫn, thời gian, lỗi ứng dụng | — |
| domain | Hợp đồng dữ liệu thị trường, doanh nghiệp, tin tức, vĩ mô, ngành và bằng chứng | — |
| data-sources | DNSE, CafeF, ngành DNSE và RSS/Atom/listing chuyển từ market-pulse | domain, storage |
| storage | Thị trường, tin, ngành; kho metadata và tệp báo cáo riêng | domain |
| analysis | Phân tích kỹ thuật/tài chính theo profile, kịch bản định giá, vĩ mô và ngành | domain |
| reports | Ba loại báo cáo, nội dung có bằng chứng và renderer PDF A4 | domain, analysis |
| pipeline | Điều phối thu thập và công bố báo cáo; điểm nối các tính năng tiếp theo | core, data-sources, storage, reports |
| web | Danh sách báo cáo, xem/tải PDF; trang tin và bộ lọc Việt Nam/quốc tế | storage, reports, pipeline |

Thứ tự: core/domain → bảo toàn DNSE/CafeF/storage → kho báo cáo → web/điểm chạy
→ nguồn tin và dữ liệu bổ sung → phân tích vĩ mô/ngành/doanh nghiệp → định giá
→ tạo PDF → pipeline hoàn chỉnh.

Phạm vi hiện tại: nền tảng đã tái cấu trúc; cập nhật BCTC HOSE 8 quý và giá DNSE,
thu thập ngành và tin, kho báo cáo và web chạy qua một script.
Đã nối pipeline phân tích/PDF cho ba loại và hàng đợi tạo trên web. Định giá chỉ hoạt động
khi có hồ sơ đơn vị/scope/cổ phiếu và giả định kịch bản; chưa giả lập đầu vào thiếu.

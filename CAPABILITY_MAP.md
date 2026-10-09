# Các module của hệ thống báo cáo đầu tư

| Module | Trách nhiệm | Phụ thuộc |
|---|---|---|
| core | Cấu hình, đường dẫn, thời gian, lỗi ứng dụng | — |
| domain | Hợp đồng dữ liệu thị trường, doanh nghiệp, tin tức, vĩ mô, ngành và bằng chứng | — |
| data-sources | Bộ kết nối DNSE, CafeF; hợp đồng cho nguồn doanh nghiệp/tin tức/vĩ mô/ngành | domain, storage |
| storage | Lưu dữ liệu hiện có; kho metadata và tệp báo cáo riêng | domain |
| analysis | Hợp đồng phân tích kỹ thuật, tài chính, định giá, doanh nghiệp, vĩ mô và ngành | domain |
| reports | Ba loại báo cáo, nội dung có bằng chứng và hợp đồng xuất PDF | domain, analysis |
| pipeline | Điều phối thu thập và công bố báo cáo; điểm nối các tính năng tiếp theo | core, data-sources, storage, reports |
| web | Danh sách báo cáo, bộ lọc, xem/tải PDF | storage, reports |

Thứ tự: core/domain → bảo toàn DNSE/CafeF/storage → kho báo cáo → web/điểm chạy
→ nguồn tin và dữ liệu bổ sung → phân tích vĩ mô/ngành/doanh nghiệp → định giá
→ tạo PDF → pipeline hoàn chỉnh.

Phạm vi hiện tại: tái cấu trúc, giữ kiểm thử bộ lấy dữ liệu, hợp đồng mở rộng,
kho báo cáo và web cơ bản chạy được qua một script. Việc tải DNSE/CafeF vẫn tạm dừng.

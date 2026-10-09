# Thu thập dữ liệu và thư viện tin tức

Yêu cầu ngày 09/10/2026: tiếp tục cập nhật dữ liệu, ưu tiên BCTC HOSE 8 quý,
bổ sung chỉ số ngành DNSE và chuyển bộ tin market-pulse vào dự án Python.
Người dùng sẽ cung cấp thiết kế PDF sau.

| Phần | Phạm vi và nghiệm thu |
|---|---|
| Collection | Chọn sàn HOSE/HNX/UPCOM, không làm mất danh mục sàn khác; cập nhật tiếp từ dữ liệu cũ, có manifest và tiến độ |
| Chỉ số ngành | Danh mục GICS cấp 2, ánh xạ doanh nghiệp và snapshot thống kê ngành DNSE; giữ nguồn/giá trị gốc, không tạo OHLCV lịch sử giả |
| Tin tức | RSS/Atom và listing từ market-pulse, chống trùng URL, ngày công bố riêng ngày tải, nguồn và trạng thái cập nhật, cache/backoff |
| Web tin | Khu vực tin riêng, bộ lọc Việt Nam/quốc tế, từ khóa/nguồn/mã, phân trang; không lẫn bộ lọc PDF |
| Runtime | Vẫn dùng run.ps1; thu thập tin định kỳ khi chạy web, có chế độ tắt để kiểm thử; lệnh cập nhật dữ liệu riêng và hướng dẫn |

RSS là cập nhật định kỳ theo nguồn, không phải WebSocket trực tiếp.
Chỉ lưu tiêu đề, đoạn trích do nguồn cung cấp và liên kết; không sao chép toàn bài.
Phân loại doanh nghiệp/ngành bằng từ khóa là gợi ý, cần kiểm chứng trước phân tích.
Nguồn vĩ mô định lượng World Bank/FRED trong market-pulse không thuộc phần chuyển tin lần này.
Kiểm thử dùng fixture; lượt thu thập thực có logs/manifest riêng, không dùng số thử làm dữ liệu thật.

Thứ tự: chọn sàn + kiểm thử → chạy cập nhật → adapter chỉ số → adapter/kho tin → lịch tin → web/API → kiểm thử browser + tài liệu.

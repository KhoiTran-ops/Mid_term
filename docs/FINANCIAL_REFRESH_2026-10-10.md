# Cập nhật BCTC - 10/10/2026

## Phạm vi và trạng thái

- Tác vụ hữu hạn: 1.522 mã, BCTC năm 2021-2025 và tối đa 24 quý đã công bố.
- Chạy tiếp từ `var/runs/financial-complete-20261010T132550`; không khởi chạy nhiều bộ tải CafeF đồng thời.
- Đây là công việc đang thực hiện, chưa phải xác nhận mọi doanh nghiệp đủ mọi thành phần/thuyết minh.
- Snapshot 16:08 (+07): 548 mã có số liệu quý; 146 mã có số liệu ba nhóm trong cửa sổ tám quý; 6 mã có ba nhóm năm cho đủ 2021-2025. Các giá trị này không phải tiến độ cuối cùng.
- Một số đường dẫn CafeF năm cũ trả 404, bao gồm FPT 2021. Thử cột so sánh từ cửa sổ chồng lấn không đồng nghĩa đã lấy được số liệu; giữ các năm còn thiếu trong audit.

## Đã thay đổi

1. Tải bảng mở rộng `showtype=1`; bảng năm dùng `quarter=0`, không lấy quý 4 thay cho năm.
2. Lưu thành phần BCTC năm vào `annual_statement_facts`, giữ nguyên workbook lịch sử riêng.
3. Parser giữ null, số 0 có thật, dấu âm ngoặc; không tự nhân theo nhãn đơn vị trên giao diện.
4. Trang trống không xóa số đã tải; cột trống được thử ở cửa sổ/kỳ khác.
5. Ánh xạ CFO không nhầm với dòng trước biến động vốn lưu động; bảng trực tiếp/gián tiếp không cộng với nhau.
6. BCTC gốc đã nhập có ưu tiên trước nguồn thứ cấp và được bảo vệ khi tải lại.
7. Đối chiếu VCB: bảng dòng tiền trực tiếp 2025Q1-Q3, tổng tài sản 2023, LNST cổ đông ngân hàng 2025, nợ phải trả 2026Q2. Số CafeF ban đầu vẫn có trong dữ liệu/snapshot để truy vết.
8. Bổ sung ROE/ROA năm và TTM sau đối chiếu đơn vị/kỳ; riêng ROE/ROA 2024 dùng số đầu năm trình bày lại trong BCTC 2024.
9. Bổ sung NIM, CASA, CAR, nợ xấu, chi phí tín dụng, nhân sự, mạng lưới và danh sách công ty con/liên doanh/liên kết VCB từ công bố gốc. Giữ khác biệt phạm vi CAR và ngoại lệ hợp nhất của ngân hàng chuyển giao bắt buộc.
10. Các phản hồi tải mới được lưu theo URL + nội dung SHA-256, không ghi đè phiên bản cũ ở cùng URL. Những receipt tạo trước sửa đổi này vẫn có thể chỉ tới phiên bản đã bị tải lại; không coi chúng là bằng chứng nguyên vẹn của mọi phản hồi trước đó.
11. Web hiển thị tiến độ tải và cảnh báo tiến độ lâu không cập nhật. Tác vụ hậu xử lý đợi đợt tải kết thúc, lập audit mới và tái tạo các báo cáo doanh nghiệp đã có trong thư viện; nếu bộ tải báo lỗi thì hậu xử lý báo lỗi, không tuyên bố hoàn tất.

## Kiểm thử

- `python -m pytest -q`: 112 passed.
- VCB: PDF 20 trang đã render và kiểm tra hình ảnh.
- Tạo lại cùng dữ liệu: `reused=true`, giữ ID `b7c9613f-8681-400c-a7b6-285054c2d418`.
- Localhost: health, trang báo cáo và tải PDF trả HTTP 200.

## Các điểm không được tự điền

Thuyết minh chưa rà soát hết; cơ cấu cổ đông/thu nhập theo phân khúc, cổ tức, cổ phiếu lưu hành, đơn vị giá, EPS TTM và đầu vào định giá còn cần bằng chứng tương ứng. Giả định 2026-2028, Ke/g/ROE bền vững và giá mục tiêu không phải dữ liệu BCTC lịch sử; không sinh mặc định để loại bỏ ô thiếu.

## Theo dõi

- `outputs/FINANCIAL_COMPLETE_PROGRESS.json`: đợt tải đang chạy.
- `outputs/FINANCIAL_COVERAGE_AUDIT.json`: snapshot từng mã, năm và nhóm báo cáo thiếu.
- `outputs/FINANCIAL_REFRESH_REVIEW.md`: mô tả xử lý và năm nhóm dữ liệu còn cần làm.
- `outputs/REPORT_REFRESH_PROGRESS.json`: hậu xử lý/tái tạo báo cáo.

Nếu cần tiếp tục sau khi máy/tác vụ dừng, dùng môi trường Python chung đang có:

```powershell
& C:\Users\ADMIN\.venv\Scripts\python.exe -X utf8 tasks/refresh_financial_complete.py --resume var/runs/financial-complete-20261010T132550 --retry-failed
```

Giữ khóa trong `.env`, không đưa key/secret vào lệnh, tài liệu hay chat.

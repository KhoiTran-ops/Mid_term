# Phạm vi tách dữ liệu — 09/10/2026

- Nguồn: `F:\Telegram_chatbot\Telegram_Trading_Bot`.
- Đích: `F:\Mid_term_finance1`; giữ nguyên dự án nguồn và thư mục `Mid_term` sẵn có.
- Tách DNSE REST OHLCV, VNINDEX, giao dịch nước ngoài và bộ nhận OHLCV realtime.
- Tách CafeF: danh mục, thông tin kỳ báo cáo, bảng cân đối kế toán, kết quả
  kinh doanh, lưu chuyển tiền tệ trực tiếp/gián tiếp, tối đa 8 quý gần nhất mỗi mã.
- Tách SQLite và các kiểm thử liên quan. Loại phần Telegram, thông báo, chiến
  lược và các thông tin cá nhân khỏi cơ sở dữ liệu đích.
- Nhập lịch sử DNSE có sẵn; chỉ nhập số liệu tài chính thuộc 8 kỳ mới nhất của
  từng mã. Cập nhật dữ liệu qua API đến thời điểm chạy, theo giờ Việt Nam.
- Chạy lặp lại không tạo bản ghi trùng; lỗi một mã không làm mất dữ liệu mã khác.
- Dữ liệu thiếu để NULL; không điền 0, không suy diễn quý chưa công bố.
- Tách thời điểm tải, thời điểm giao dịch và kỳ tài chính trong báo cáo kiểm tra.
- Lưu dữ liệu gốc mới tải và nguồn; ghi rõ lịch sử nhập từ dự án cũ chưa có
  bản HTML/JSON gốc đi kèm. Không nhân/chia đơn vị tiền từ nhãn giao diện CafeF.
- Cung cấp lệnh cập nhật, kiểm tra độ phủ và xuất CSV cho đồ án tiếp theo.
- Chưa xây phân tích đầu tư, tin tức vĩ mô hoặc báo cáo PDF trong lần tách này.

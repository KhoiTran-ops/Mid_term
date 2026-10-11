# Bản sao dự án đã loại thông tin đăng nhập

`Mid_term-refactor-report-platform-sanitized.rar` là bản sao đã kiểm tra của
archive `Mid_term-refactor-report-platform.rar` do người dùng cung cấp ngày
11/10/2026. Archive gốc không bị sửa đổi.

## Phạm vi

- Giữ nội dung dự án, báo cáo đã xuất và dữ liệu có trong archive gốc.
- Loại `.env` và các biến thể riêng tư; giữ `.env.example` nếu không chứa khóa.
- Loại lịch sử `.git` cùng các thư mục thông tin đăng nhập `.aws`, `.ssh`,
  `.codex`, `.agents` và các file `credentials`, `id_rsa`, `id_ed25519`.
- Quét nội dung file để loại các bản sao chứa khóa trong `.env` gốc, khóa riêng,
  GitHub token, AWS access key hoặc token xác thực nhận diện được.
- File có dấu hiệu nhạy cảm bị loại khỏi **bản sao**, không sửa dữ liệu bên trong
  và không xóa file từ archive gốc.
- Dữ liệu là snapshot tại lúc tạo archive gốc, không phải dữ liệu thời gian thực.

Các mã băm SHA-256, kích thước và số file kiểm tra nằm trong `sanitization.json`.
Việc quét không thay thế kiểm tra bảo mật thủ công; không đưa khóa thật vào archive.

## Tải và sử dụng

File RAR được lưu bằng [Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage).
Nếu bản clone chỉ có file pointer, cài Git LFS rồi chạy `git lfs pull` ở nhánh này.
Giải nén RAR vào thư mục riêng; tạo `.env` từ `.env.example` và cấu hình khóa trên
máy của bạn. Không commit `.env` lên GitHub.

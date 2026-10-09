# Hệ thống báo cáo phân tích cơ hội đầu tư cổ phiếu

Dự án hiện ở **`F:\Mid_term_finance1\Mid_term`**. Đây là nền tảng để phát triển
hệ thống báo cáo cổ phiếu, báo cáo vĩ mô và báo cáo ngành, sau đó công bố PDF
trên một web có bộ lọc.

Đã hoàn thành tái cấu trúc bộ thu thập DNSE/CafeF, kho báo cáo PDF, web thư viện,
cấu hình và script chạy chung. **Chưa có bộ phân tích, định giá, khuyến nghị hay
bộ tạo PDF tự động.** Các module này đã có hợp đồng dữ liệu để triển khai tiếp.
Thư viện thực hiện chưa có báo cáo PDF; giao diện hiển thị trạng thái trống.
Dữ liệu đã tải được giữ nguyên; việc tải tiếp vẫn tạm dừng. Mở web không tải dữ liệu.

## Chạy web bằng một script

Mở PowerShell tại thư mục dự án:

```powershell
cd F:\Mid_term_finance1\Mid_term
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Mở **http://127.0.0.1:8000**. Nhấn `Ctrl+C` tại cửa sổ chạy để dừng.
Web có bộ lọc loại báo cáo, mã cổ phiếu, ngành, ngày dữ liệu và tìm kiếm tên doanh nghiệp/tiêu đề;
mỗi PDF đã đăng ký có nút xem và tải xuống. Danh sách ngành/mã lấy từ báo cáo đã đăng ký.

Script tự tạo môi trường `.venv` và cài thư viện khi cần. Lần cài đầu cần Internet
và Python 3.12 trở lên. Trên máy hiện tại môi trường đã được chuẩn bị.
Không cần cài Node.js. Script xác định đường dẫn theo vị trí của chính nó,
nên cũng có thể gọi bằng đường dẫn đầy đủ từ thư mục khác.

Đổi cổng hoặc chỉ chuẩn bị môi trường:

```powershell
.\run.ps1 web --port 8080
.\run.ps1 setup
```

## Các lệnh dùng chung

```powershell
# Kiểm tra cấu hình và các thành phần, không gọi API dữ liệu
.\run.ps1 doctor

# Kiểm thử với dữ liệu tạm, không cần khóa API
.\run.ps1 test

# Xem độ phủ dữ liệu đã lưu; xuất dữ liệu phục vụ phân tích
.\run.ps1 data status
.\run.ps1 data export --symbols HPG FPT VCB

# Xem các PDF đã đăng ký và trợ giúp nhập dữ liệu cũ
.\run.ps1 reports list
.\run.ps1 data --help
.\run.ps1 import-legacy --help
```

Nếu PowerShell chặn chạy script, dùng cùng tiền tố
`powershell -ExecutionPolicy Bypass -File .\run.ps1` rồi thêm lệnh, ví dụ `doctor`.
`run.py` là phần Python của cùng điểm vào, được `run.ps1` gọi bằng môi trường dự án.

## Khi muốn tiếp tục cập nhật dữ liệu

Các lệnh dưới đây **chủ động gọi nguồn dữ liệu**; chỉ chạy khi muốn kết thúc tạm dừng:

```powershell
.\run.ps1 data update --symbols HPG FPT VCB --foreign
.\run.ps1 data market --timeframes 1D
.\run.ps1 data financials --quarters 8
.\run.ps1 data financials --symbols HPG --refresh-financials
```

`update` cập nhật danh mục trước rồi chạy hai nguồn đồng thời. Khi chạy riêng,
chạy `market` trước `financials` để nhận mã mới. Không chạy hai lượt cập nhật
cùng nguồn đồng thời. `--database` là tùy chọn chung của nhóm `data`, đặt trước
`market`, `financials`, `status` hoặc `export`.

Thông tin DNSE giữ tại `.env`. Không chia sẻ tệp này. Cơ sở dữ liệu, phản hồi gốc,
cấu hình bí mật và PDF đầu ra được loại khỏi Git. `.env.example` chỉ chứa mẫu cấu hình.

## Đưa PDF có sẵn vào thư viện

Ví dụ cú pháp sau cần một PDF thực tại đường dẫn `--pdf`; dự án không tạo sẵn báo cáo ví dụ này:

```powershell
.\run.ps1 reports add --pdf "outputs/bao_cao_hpg.pdf" --kind stock --title "Phân tích HPG" --as-of 2026-10-09 --symbol HPG --company-name "Hòa Phát" --industry-id steel --industry-name "Thép"
```

- `stock`: bắt buộc mã cổ phiếu và mã ngành.
- `industry`: bắt buộc mã ngành, không nhận mã cổ phiếu.
- `macro`: không nhận mã cổ phiếu hay mã ngành.

`--as-of` là ngày chốt dữ liệu của báo cáo. Kho sao chép PDF vào
`outputs/reports/<UUID>.pdf`, ghi dấu SHA-256 và metadata vào `var/reports.db`.
Việc đăng ký kiểm tra chữ ký đầu tệp PDF; chưa kiểm định nội dung phân tích
hay toàn bộ cấu trúc tệp PDF. Chỉ đăng ký tài liệu đã kiểm tra.

## Cấu trúc mới

```text
Mid_term/
  run.ps1, run.py              # Một điểm vào cho web, dữ liệu, kho PDF và kiểm thử
  src/stock_reports/
    core/                     # Cấu hình và lỗi dùng chung
    domain/                   # Kiểu dữ liệu thị trường, doanh nghiệp, tin, nguồn
    data_sources/             # DNSE, CafeF, lưu phản hồi gốc; hợp đồng nguồn mới
    storage/                  # SQLite thị trường, kiểm kê dữ liệu, kho báo cáo
    analysis/                 # Hợp đồng đầu vào/kết quả phân tích có bằng chứng
    reports/                  # Metadata, cấu trúc báo cáo và giao diện render PDF
    pipeline/                 # Thu thập, nhập lịch sử và công bố PDF
    web/                      # Web, API đọc báo cáo, giao diện và CSS
  tests/                      # Kiểm thử cũ và kiểm thử nền tảng mới
  docs/                       # Kiến trúc và đối chiếu đường dẫn cũ/mới
  tasks/                      # Tiến độ và thứ tự phát triển tiếp
  var/market_data.db          # Dữ liệu đã có, được giữ nguyên
  var/reports.db              # Kho metadata PDF riêng
  var/runs/                  # Manifest và phản hồi gốc của các lượt tải
  outputs/reports/            # PDF đã đăng ký
```

Mã cũ trong `common/`, `data/`, `scripts/` và `collect_data.py` đã chuyển vào package
`stock_reports`. Các import và kiểm thử đi kèm đã được cập nhật.
Xem [kiến trúc](docs/ARCHITECTURE.md), [đối chiếu module](docs/RESTRUCTURE.md),
[đặc tả](SPEC.md) và [công việc tiếp theo](tasks/todo.md).

## Trình tự phát triển tiếp

1. Xác minh đơn vị, quý/lũy kế và chất lượng BCTC; tính chỉ số tài chính, bổ sung hồ sơ và ngành doanh nghiệp.
2. Bổ sung nguồn tin doanh nghiệp, vĩ mô và ngành có ngày công bố và liên kết nguồn.
3. Triển khai các bộ phân tích vĩ mô, ngành, kỹ thuật, tài chính và tin doanh nghiệp.
4. Xây dựng dự phóng, định giá, kịch bản và quy tắc khuyến nghị dựa trên bằng chứng.
5. Render PDF, kiểm tra bố cục, nối pipeline tạo báo cáo và công bố lên web.

Hiện `AnalysisEngine`, các nguồn dữ liệu bổ sung và `PdfRenderer` là giao diện
cho module thực sẽ viết sau. Hợp đồng báo cáo cổ phiếu yêu cầu các phần vĩ mô,
ngành, doanh nghiệp, kỹ thuật, tài chính, định giá, khuyến nghị và rủi ro; một tập chỉ báo
kỹ thuật riêng không đáp ứng hợp đồng này. Nhận định thực tế phải có nguồn;
giả định phải được đánh dấu riêng.

## Ý nghĩa dữ liệu và giới hạn

- DNSE giữ OHLCV, thời gian nguồn và trạng thái nến; bộ thu thập hỗ trợ danh mục,
  VNINDEX và dữ liệu nước ngoài. Nến ngày đang diễn ra có thể chưa được REST công bố.
  `requested_until` là mốc yêu cầu; xem inventory để biết thời điểm dữ liệu thực.
- Nến phút cập nhật ngày hiện tại, chưa tự lấp ngày phút còn thiếu trong lịch sử.
  `--foreign` lấy snapshot ngày hiện tại và giữ lịch sử đã có.
- CafeF giữ tối đa 8 kỳ quý gần nhất đã công bố của từng doanh nghiệp.
  Metadata kỳ báo cáo không bảo đảm mọi bảng đủ chỉ tiêu. Kiểm tra
  `outputs/coverage.csv` và `outputs/DATA_STATUS.md` trước khi phân tích.
- `BSheet` là cân đối kế toán, `IncSta` là kết quả kinh doanh;
  không cộng `CashFlow` và `CashFlowDirect` với nhau.
- Giá trị thiếu giữ `NULL`; dữ liệu bất thường giữ để đối chiếu nguồn.
  Giá ngoài khoảng thấp/cao cần được xác minh trước khi dùng.
- CafeF giữ chuỗi gốc và số đã đọc. Nhãn hiển thị “tỷ đồng” không đủ để suy ra
  đơn vị trong HTML; EPS có đơn vị riêng, lưu chuyển tiền tệ có thể lũy kế năm.
  Chuẩn hóa các điểm này là bước tiếp theo trước khi định giá.
- Cập nhật nhanh không phát hiện mọi điều chỉnh kỳ cũ. `--refresh-financials`
  tải lại cửa sổ 8 quý cho mã cần đối chiếu.
- Dữ liệu nhập cũ có nguồn/thời điểm tải nhưng không có phản hồi gốc đi kèm.
  Lượt tải mới lưu bản gốc và receipts dưới `var/runs`.
- Manifest trích xuất và lượt tải cũ có thể chứa đường dẫn cũ vì là dấu vết lịch sử;
  đường dẫn chạy hiện tại được giải theo thư mục dự án mới.

Web hiện phục vụ cục bộ tại `127.0.0.1`, chỉ đọc báo cáo, chưa có đăng nhập,
upload, lịch chạy tự động hay triển khai công khai.
`requirements.txt` là thư viện chạy; `requirements-dev.txt` bổ sung kiểm thử;
`requirements-lock.txt` ghi phiên bản môi trường đã kiểm tra, gồm cả thư viện phát triển.

Nguồn đặc tả DNSE: [OHLC history](https://developers.dnse.com.vn/docs/dnse/get-ohlc-history/).
Mã nguồn tách theo giấy phép MIT đi kèm trong `LICENSE`.

# Bộ dữ liệu cho đồ án phân tích cơ hội đầu tư cổ phiếu

Đã tách từ `F:\Telegram_chatbot\Telegram_Trading_Bot` sang
`F:\Mid_term_finance1`. Dự án chạy độc lập, không cần Telegram. Giữ nguyên
thư mục `Mid_term` đã có trong máy. Chưa xây dựng phần phân tích, định giá hoặc PDF.

## Thành phần

| Vị trí | Nội dung |
|---|---|
| `data/dnse_market.py` | DNSE REST: danh mục, OHLCV, VNINDEX, giao dịch nước ngoài; bộ nhận nến phút realtime |
| `data/cafef/client.py` | Kết nối dữ liệu công khai CafeF, giới hạn tốc độ và thử lại |
| `data/cafef/parsers.py` | Đọc kỳ báo cáo, trạng thái kiểm toán và chỉ tiêu tài chính |
| `data/cafef/sync.py` | Đồng bộ tối đa 8 quý gần nhất từng mã; dùng lại lịch sử khi cập nhật |
| `data/db/market_store.py` | Lưu SQLite, không chứa thông tin chat Telegram |
| `collect_data.py` | Cập nhật, kiểm tra và xuất dữ liệu |
| `scripts/import_legacy.py` | Nhập lịch sử từ cơ sở dữ liệu cũ theo chế độ chỉ đọc |
| `var/market_data.db` | Cơ sở dữ liệu đã chuyển và cập nhật |
| `var/legacy_import.json` | Số lượng dữ liệu và nguồn nhập |
| `var/runs/*/manifest.json` | Kết quả của từng lượt cập nhật |
| `var/runs/*/raw/receipts.jsonl` | Nguồn, thời điểm tải và dấu kiểm tra phản hồi gốc |
| `outputs/coverage.csv` | Tình trạng dữ liệu của từng mã |
| `outputs/DATA_STATUS.md` | Tổng hợp độ phủ và giới hạn dữ liệu |
| `docs/extraction_manifest.json` | Các tệp nguồn và dấu kiểm tra khi tách mã |

## Chạy trên máy hiện tại

Mở PowerShell trong `F:\Mid_term_finance1`. Đã có môi trường Python riêng
`.venv` và cấu hình DNSE trong `.env`; chỉ chuyển hai khóa DNSE từ dự án cũ.
Không chia sẻ `.env`. Cơ sở dữ liệu, phản hồi tải về và cấu hình được loại khỏi Git.

```powershell
# Kiểm tra độ phủ và thời điểm dữ liệu thực tế
.\.venv\Scripts\python.exe collect_data.py status

# Cập nhật giá ngày, nến phút hôm nay và báo cáo tài chính toàn danh mục
.\.venv\Scripts\python.exe collect_data.py update

# Chỉ cập nhật một số mã; thêm dữ liệu nước ngoài hôm nay
.\.venv\Scripts\python.exe collect_data.py update --symbols HPG FPT VCB --foreign

# Chỉ giá ngày (nhanh hơn); lịch sử DNSE đã lưu được giữ lại
.\.venv\Scripts\python.exe collect_data.py market --timeframes 1D

# Kiểm tra báo cáo mới, bổ sung phần chưa tải, tối đa 8 quý mỗi mã
.\.venv\Scripts\python.exe collect_data.py financials --quarters 8

# Tải lại toàn bộ 8 quý để kiểm tra số liệu điều chỉnh của một mã
.\.venv\Scripts\python.exe collect_data.py financials --symbols HPG --refresh-financials

# Xuất dữ liệu phục vụ phân tích; giữ nguyên cột nguồn và thời điểm tải
.\.venv\Scripts\python.exe collect_data.py export --symbols HPG FPT VCB

# Kiểm thử
.\.venv\Scripts\python.exe -m pytest tests -q
```

Lệnh `market` và `financials` có thể chạy riêng, mỗi nguồn có giới hạn tốc độ.
`update` chạy hai nguồn đồng thời. Đầu ra khác 0 và thông tin trong manifest
cho biết có lỗi hoặc phần dữ liệu nguồn không cung cấp; xem `issues` và `failures`.
Lệnh `update` tải danh mục DNSE mới trước khi đồng bộ cả hai nguồn. Khi chạy
riêng, chạy `market` trước `financials` để bao gồm mã mới niêm yết.
Không chạy hai lệnh cập nhật cùng một nguồn đồng thời.

## Cài lại môi trường

Dùng Python 3.12 trở lên. Trên máy này có Python tại `F:\Data\.python\python.exe`.

```powershell
& 'F:\Data\.python\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements.txt` chứa thư viện chạy; `requirements-dev.txt` bổ sung kiểm thử.

## Ý nghĩa dữ liệu và giới hạn

- DNSE: lưu giá mở/cao/thấp/đóng, khối lượng, thời gian nguồn và trạng thái
  hoàn tất nến. Nến ngày đang diễn ra có thể chưa được REST công bố. Mốc tải
  `requested_until` là thời điểm bắt đầu lượt cập nhật; thời điểm dữ liệu thực
  tế xem ở bảng kiểm tra. Nến phút được cập nhật cho ngày hiện tại, không tự
  lấp các ngày phút còn thiếu giữa dữ liệu cũ và hôm nay.
- Lịch sử nước ngoài có sẵn được giữ nguyên. `--foreign` tải snapshot trong
  ngày hiện tại; không tự tải lại toàn bộ lịch sử hai năm.
- CafeF: `BSheet` là cân đối kế toán, `IncSta` là kết quả kinh doanh,
  `CashFlow`/`CashFlowDirect` là hai phương pháp lưu chuyển tiền tệ.
  Không cộng hai phương pháp này với nhau.
- Cửa sổ 8 quý là 8 kỳ gần nhất **đã công bố của từng doanh nghiệp**. Có mã
  thiếu báo cáo hoặc chỉ có số liệu cũ. Metadata kỳ báo cáo không bảo đảm
  cả ba bảng có đầy đủ chỉ tiêu. Xem `coverage.csv` trước khi phân tích.
- Giá trị thiếu giữ `NULL`; dữ liệu bất thường được giữ lại để kiểm chứng.
  Bảng kiểm tra thống kê OHLCV có giá ngoài khoảng thấp/cao. Không dùng
  trực tiếp các dòng này để suy luận trước khi đối chiếu nguồn.
- Số liệu CafeF giữ cả chuỗi gốc và số đã đọc. Nhãn giao diện “tỷ đồng” có
  thể chỉ phản ánh cách JavaScript hiển thị, trong khi HTML chứa số ở đơn vị
  đồng; EPS lại có đơn vị riêng. Cần xác minh từng loại chỉ tiêu trước khi
  chuẩn hóa, dự phóng hay định giá. Lưu chuyển tiền tệ có thể là lũy kế năm.
- Chế độ cập nhật nhanh kiểm tra kỳ báo cáo mới và dùng lại số liệu cũ đã
  tải, không phát hiện mọi điều chỉnh của kỳ cũ. Dùng `--refresh-financials`
  cho mã sẽ được phân tích trong báo cáo đầu tư.
- Lịch sử nhập từ cơ sở dữ liệu cũ giữ nguồn và ngày tải ban đầu nhưng
  không có phản hồi HTML/JSON gốc đi kèm. Lượt tải mới có bản gốc tại `var/runs`.
- Chưa có tin tức, dữ liệu vĩ mô, mô hình định giá hay khuyến nghị đầu tư.

Nguồn đặc tả DNSE: https://developers.dnse.com.vn/docs/dnse/get-ohlc-history/

Mã nguồn tách theo giấy phép MIT đi kèm trong `LICENSE`.

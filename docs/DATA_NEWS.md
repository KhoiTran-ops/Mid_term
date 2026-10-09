# Nguồn dữ liệu, ngành và tin tức

Phần bổ sung ngày 09/10/2026. Thiết kế PDF và logic khuyến nghị chưa nằm trong đợt này.

## Chuyển bộ tin market-pulse

Đọc mã tại `F:\Mid_term_finance1\market-pulse`, giữ dự án nguồn nguyên trạng.
Chuyển logic sang Python để tiếp tục dùng một điểm vào `run.ps1`, không cần Node.js.

| Mã gốc | Module trong Mid_term |
|---|---|
| `src/adapters.js` | `data_sources/news/adapters.py`: RSS/Atom, HTML listing, HTTP cache |
| `src/normalize.js` | `data_sources/news/normalize.py`: URL, ngày, loại HTML, gợi ý thực thể |
| `src/collector.js` | `pipeline/news.py`: lịch nguồn, giới hạn đồng thời, backoff |
| `src/store.js` | `storage/news.py`: tin, nguồn, phiên bản sửa và audit lượt tải |
| `src/runtime.js` | `pipeline/news_runtime.py`: vòng lặp nền và quản lý dừng |
| `config/sources.json`, `entities.json` | `config/news_sources.json`, `news_entities.json` |

19 nguồn RSS/listing: VnExpress, VietNamNet, VnEconomy, BBC, Guardian, CNBC,
Fed, ECB, Cục Thống kê và Vietcap. Không chuyển các adapter World Bank/FRED
định lượng hay Guardian API cần khóa trong phần tin này.

Các thay đổi cần thiết khi tích hợp:

- RSS/Atom được đọc bằng XML parser; không cho DOCTYPE/ENTITY.
- Chỉ giữ tiêu đề/đoạn trích/liên kết. HTML được loại trước lưu, template vẫn escape.
- URL chuẩn hóa bỏ fragment và tham số tracking; chống trùng bằng URL.
  Các nguồn cùng có một bài được lưu vào `article_sources`; ghi tin trong transaction
  để hai feed đồng thời không gây lỗi trùng khóa.
- Nếu nội dung đổi, giữ bản trước trong `revisions`. Không chống trùng theo suy đoán
  ngữ nghĩa giữa hai bài có URL khác nhau.
- `published_at` khác `first_seen`/`last_seen`; thiếu ngày hoặc thiếu múi giờ giữ `NULL`.
  Listing Cục Thống kê đọc ngày phát hành của đúng báo cáo, không lấy lịch công bố tiếp theo.
  VnEconomy chỉ đọc liên kết trong `article`, bỏ liên kết menu chuyên mục.
- Khu vực theo cấu hình kênh: `VN` là Việt Nam, `Global`/`US`/`EU` là quốc tế.
  Bộ lọc này không bảo đảm mọi bài trong một feed đều chỉ đề cập đúng khu vực đó.
- Tags mã/ngành từ tiêu đề/đoạn trích và từ khóa chỉ là gợi ý. Phân loại ngành tin
  không tự chuyển thành mã GICS DNSE. Phải kiểm chứng trước phân tích/khuyến nghị.
- HTTP có timeout, giới hạn 6 MB và 4 nguồn đồng thời. Lỗi được lưu theo loại hoặc mã HTTP,
  thử lại với backoff; không lưu thông báo chứa khóa/URL riêng. ETag/Last-Modified hỗ trợ 304.
- Khóa hệ điều hành `var/news-collector.lock` ngăn web và `news watch/update` cùng thu thập.
  Khóa được nhả khi tiến trình kết thúc. Nguồn đang lỗi vẫn hiện tin đã lưu.

Web đọc SQLite cục bộ, không gọi publisher trong từng request. `/news` tự làm mới
phần kết quả mỗi 60 giây, giữ bộ lọc đang nhập. Lịch nguồn 10–360 phút trong config;
không hứa cập nhật tức thời hơn nguồn RSS. Đặt `NEWS_AUTO_UPDATE=false` để chạy offline.

## Ngành DNSE

Nguồn được đối chiếu với [trang ngành của bảng giá DNSE](https://banggia.dnse.com.vn/v2/nganh/danh-muc-nganh/ngan-hang):

1. [Catalog GICS cấp 2](https://api.dnse.com.vn/market-api/sectors?classificationType=gics&level=2): 22 nhóm.
2. [Danh mục ticker](https://api.dnse.com.vn/market-api/tickers?_start=0&_end=10000&floor=):
   tên/sàn và `gicsIndustryGroupId`, lưu các mã `STOCK`, `isListed=true` trên HOSE/HNX/UPCOM.
3. Luồng MQTT 5 qua WebSocket `wss://datafeed-krx.dnse.com.vn/wss`, topic công khai
   `stats/sector/volatility`, protobuf envelope loại 730.

Đã đối chiếu schema với dữ liệu mà frontend DNSE công khai sử dụng, đọc thực tế được
22 nhóm. Client chỉ đọc một snapshot retained và ngắt kết nối, không dùng kênh tài khoản.
`industries watch` lặp lại mỗi phút; catalog làm mới mỗi 24 giờ ở lần khởi động mới của mã này.
Giao thức theo [MQTT 5 của OASIS](https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html)
và [Python protobuf](https://protobuf.dev/reference/python/python-generated/).

Các trường gốc gồm `priceVolatilityKey`/`priceVolatilityValue` cho các khoảng như
1d/7d/1m/3m/6m/1y/3y/5y, `matchPrice`, `volume`, `marketCap`, `totalStocks`,
`priceChangeToday`, `grossTradeValue` và thời gian nguồn. Không tự đổi đơn vị các trường
vốn hóa/giá trị giao dịch. Field không có trong payload không được tự điền giá trị.

`var/industries.db` có bảng sectors, companies, snapshots. Catalog có khóa
`(classification, level, sector_id)`; companies dùng phân nhóm GICS cấp 2.
Không ghép ID với phân ngành Vietstock: cùng slug/ID có thể có ý nghĩa khác giữa hai hệ.
Snapshot giữ chất lượng `raw`, thời gian nguồn và thời gian tải riêng; cùng nguồn/thời gian
được chống trùng. Nếu thị trường chưa cập nhật, một lượt tải mới có thể không thêm snapshot.

Đây là thống kê ngành tổng hợp, chưa phải bộ nến lịch sử của chỉ số ngành chính thức.
REST OHLC được thử với VNFIN nhưng nguồn trả lỗi không hỗ trợ; không tạo dữ liệu giả.
Lịch sử snapshot chỉ có từ ngày bắt đầu collector. Cần chốt đơn vị/phương pháp tính
trước khi dùng để so sánh hay đưa vào báo cáo đầu tư.

Phản hồi JSON/MQTT và manifest mỗi lượt lưu trong `var/runs/industries-*`.
Phản hồi tin lưu trong `var/runs/news-*`; lịch/kết quả từng lượt tin nằm trong `var/news.db`.

## BCTC và giá

Lọc HOSE theo catalog DNSE đầy đủ; không xóa danh mục các sàn khác. BCTC lấy tối đa
8 kỳ công bố gần nhất. Metadata có kỳ không đồng nghĩa cả ba báo cáo đều có số liệu.
CafeF có thể có cửa sổ báo cáo với ô trống hoặc một anchor trả 404; thử kỳ kế tiếp
để lấy phần thực sự có, phần còn thiếu tiếp tục được ghi nhận. Không nội suy số liệu.

Giá 1D và 1m, cùng snapshot nước ngoài, dùng bộ DNSE cũ đã tái cấu trúc.
Mốc `requested_until` là thời điểm bắt đầu lượt chạy. Xem `outputs/coverage.csv`
và `outputs/data_inventory.json` để biết thời điểm dữ liệu thực cho từng mã.
Lượt tải hữu hạn lưu tiến độ `dnse-progress.json`/`cafef-progress.json` cạnh manifest.
Thông tin tiến trình chạy nền của đợt này ở `var/jobs`; không đưa dữ liệu/log hay khóa vào Git.

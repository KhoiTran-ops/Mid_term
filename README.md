# Hệ thống báo cáo phân tích cơ hội đầu tư cổ phiếu


## Chạy web bằng một script

Mở PowerShell tại thư mục dự án:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Mở **http://127.0.0.1:8000**. Nhấn `Ctrl+C` tại cửa sổ chạy để dừng.
Web có bộ lọc loại báo cáo, mã cổ phiếu, ngành, ngày dữ liệu và tìm kiếm tên doanh nghiệp/tiêu đề;
mỗi PDF có trang chi tiết, xem trước và tải xuống. Nút **Tạo báo cáo** chọn từng loại
hoặc bộ ba cổ phiếu + ngành + vĩ mô; dùng cùng bộ phân tích với lệnh bên dưới. Danh sách ngành/mã lấy từ báo cáo đã đăng ký.
Trang chủ có ô tin mới và đường dẫn đến `/news`. Trang tin có bộ lọc riêng:
Việt Nam/quốc tế, nguồn tin, mã doanh nghiệp và từ khóa; hỗ trợ tìm không dấu.
Mở web tự chạy bộ cập nhật tin theo lịch nguồn. Giá/BCTC được cập nhật bằng lệnh riêng.

Script tự tạo môi trường `.venv` và cài thư viện khi cần. Lần cài đầu cần Internet
và Python 3.12 trở lên. Trên máy hiện tại môi trường đã được chuẩn bị.
Không cần cài Node.js. Script xác định đường dẫn theo vị trí của chính nó,
nên cũng có thể gọi bằng đường dẫn đầy đủ từ thư mục khác.

Đổi cổng hoặc chỉ chuẩn bị môi trường:

```powershell
.\run.ps1 web --port 8080
.\run.ps1 setup
```

Nếu cổng 8000 đang được dùng, chọn cổng khác. Trong đợt triển khai này, web mới
được mở ở **http://127.0.0.1:8001** và tin tại **http://127.0.0.1:8001/news**.

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

## Cập nhật dữ liệu

Tất cả tác vụ dùng cùng `run.ps1`. Mỗi lệnh dưới đây chủ động gọi nguồn dữ liệu:

```powershell
.\run.ps1 data update --symbols HPG FPT VCB --foreign
.\run.ps1 data market --timeframes 1D
.\run.ps1 data market --timeframes 1D 1m --foreign
.\run.ps1 data financials --exchanges HOSE --quarters 8
.\run.ps1 data financials --symbols HPG --refresh-financials
.\run.ps1 data daily
.\run.ps1 data daily --date 2026-10-09
.\run.ps1 data import-annual --xlsx var/imports/cafef-indicators-2010-2024.xlsx

# Danh mục ngành và một snapshot thống kê ngành từ bảng giá DNSE
.\run.ps1 industries update
.\run.ps1 industries update --catalog-only
.\run.ps1 industries status

# Giữ thu thập snapshot mỗi phút; Ctrl+C để dừng
.\run.ps1 industries watch --interval 60

# Cập nhật các nguồn tin đến hạn; --force để kiểm tra toàn bộ nguồn ngay
.\run.ps1 news update --force
.\run.ps1 news status
.\run.ps1 news watch
```

`update` cập nhật danh mục trước rồi chạy hai nguồn đồng thời. `data financials`
tự dùng danh mục doanh nghiệp/ngành DNSE công khai và không cần khóa DNSE.
`data market` và `data update` cần đủ `DNSE_API_KEY`/`DNSE_API_SECRET` trong `.env`.
Khi chưa có secret, `data daily` vẫn tải EOD công khai CafeF cho ngày hiện tại
theo múi giờ Việt Nam; có thể truyền `--date YYYY-MM-DD` để bù một ngày cụ thể.
Không chạy hai lượt cập nhật cùng nguồn đồng thời. `--database` là tùy chọn chung của nhóm `data`, đặt trước
`market`, `financials`, `status` hoặc `export`.

`industries update --catalog-only` tải toàn bộ doanh nghiệp niêm yết và GICS cấp 2,
đồng thời đồng bộ danh mục cho CafeF nhưng bỏ qua snapshot MQTT. File năm 2010–2024
từ dự án Crawl-CafeF-Data được nhập vào `annual_financial_facts`; chương trình chuẩn hóa
header lệch giữa sheet, bỏ dòng trùng và ghi xung đột vào `data_anomalies`. Chuỗi năm này
không bị trộn vào `financial_facts` theo quý.

`--exchanges HOSE` chỉ giới hạn mã được tải, vẫn giữ danh mục đầy đủ của các sàn.
8 quý là 8 kỳ **đã công bố gần nhất của từng công ty**, có thể khác nhau giữa các mã;
không giả định tất cả đã có BCTC quý 3/2026. Bộ thu thập đếm kỳ duy nhất khi phân trang,
đọc cửa sổ 4 quý theo lịch và thử bảng kỳ kế tiếp nếu một anchor trả HTTP 404.
Các lỗi/thiếu dữ liệu còn lại được ghi vào manifest. Dữ liệu đã có được tái sử dụng;
`--refresh-financials` tải lại để kiểm tra điều chỉnh.

`data market` là một lượt hữu hạn, lấy đến thời điểm bắt đầu lượt chạy.
Chạy lại để lấy phiên mới hơn. `industries watch` và bộ tin khi mở web tiếp tục theo lịch.
Không chạy hai lượt giá/BCTC cùng nguồn đồng thời. Bộ tin và bộ ngành có khóa chống chạy trùng.

Muốn chỉ đọc tin đã lưu, đặt `NEWS_AUTO_UPDATE=false` trong `.env` trước khi mở web.
Nguồn và lịch tin ở `config/news_sources.json`; danh sách gợi ý mã/ngành ở
`config/news_entities.json`. RSS cập nhật theo lịch 10–360 phút tùy nguồn;
trang tin làm mới danh sách mỗi phút. Đây là polling, không phải tin đẩy ngay tức thời.

Sao chép `.env.example` thành `.env` rồi điền hai biến DNSE nếu cần dữ liệu giá.
Không dán khóa vào chat và không commit `.env`. Cơ sở dữ liệu, phản hồi gốc,
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
    analysis/                 # Ánh xạ BCTC, profile, vĩ mô/ngành/kỹ thuật và định giá
    reports/                  # Metadata, cấu trúc báo cáo và renderer A4 có font nhúng
    pipeline/                 # Thu thập, nhập lịch sử và công bố PDF
    web/                      # Thư viện Stitch, tin, preview và hàng đợi tạo báo cáo
  tests/                      # Kiểm thử cũ và kiểm thử nền tảng mới
  docs/                       # Kiến trúc và đối chiếu đường dẫn cũ/mới
  tasks/                      # Tiến độ và thứ tự phát triển tiếp
  var/market_data.db          # Dữ liệu đã có, được giữ nguyên
  var/reports.db              # Kho metadata PDF riêng
  var/news.db                 # Tin, nguồn, lịch, chống trùng và lịch sử sửa
  var/industries.db           # GICS, ánh xạ doanh nghiệp, snapshot ngành
  var/runs/                  # Manifest và phản hồi gốc của các lượt tải
  var/jobs/                  # Log và thông tin những tiến trình chạy nền của đợt tải này
  config/                    # Nguồn tin và từ khóa nhận diện
  outputs/reports/            # PDF đã đăng ký
```

Mã cũ trong `common/`, `data/`, `scripts/` và `collect_data.py` đã chuyển vào package
`stock_reports`. Các import và kiểm thử đi kèm đã được cập nhật.
Xem [kiến trúc](docs/ARCHITECTURE.md), [đối chiếu module](docs/RESTRUCTURE.md),
[đặc tả](SPEC.md) và [công việc tiếp theo](tasks/todo.md).

## Tạo báo cáo từ dữ liệu đã lưu

```powershell
# Một lượt tạo cả cổ phiếu, ngành của doanh nghiệp và tổng quan vĩ mô
.\run.ps1 reports generate --kind all --symbol SSI

# Từng đầu ra độc lập
.\run.ps1 reports generate --kind stock --symbol HPG
.\run.ps1 reports generate --kind industry --industry-id dich-vu-tai-chinh
.\run.ps1 reports generate --kind macro

# Chọn kỳ cuối và doanh nghiệp so sánh cùng nhóm/mô hình
.\run.ps1 reports generate --kind stock --symbol SSI --period 2026Q2 --peers HCM VCI VND

# Bổ sung chuỗi vĩ mô năm từ World Bank cho Việt Nam và 7 nền kinh tế so sánh
.\run.ps1 macro update
.\run.ps1 macro status
```

Báo cáo vĩ mô hiện chỉ dùng chuỗi Việt Nam; dữ liệu Hoa Kỳ, Trung Quốc, Nhật Bản,
Hàn Quốc, Singapore, Thái Lan và Indonesia được giữ trong kho để đối chiếu.

PDF được đăng ký tự động trong kho hiện có; mở web để xem. Không tải lại toàn thị trường
khi tạo báo cáo. Tác vụ web chạy trong hàng đợi có giới hạn; đóng hộp tạo không hủy tác vụ.
Dữ liệu/nội dung/format giống nhau tái sử dụng PDF đã có. Khi dữ liệu hay giả định thay đổi,
bản mới được lưu với ID và thời điểm xuất riêng; bản cũ vẫn đọc được.

**BCTC gốc** là PDF doanh nghiệp công bố, dùng kiểm chứng số liệu/thuyết minh.
**PDF phân tích** trong thư viện là đầu ra của chương trình. Dữ liệu CafeF không tự trở thành
BCTC chính thức; chương trình chưa tự tìm và tải BCTC gốc cho mọi doanh nghiệp.

Mỗi báo cáo có bản đối chiếu ở `outputs/analysis/<ID>.json`: đầu vào tài chính/giá/
ngành/vĩ mô, nguồn, định vị dòng, hồ sơ kiểm chứng, giả định, fingerprint và SHA-256 PDF.
Dữ liệu đầu vào đầy đủ chỉ đọc từ máy; web chỉ trả nội dung báo cáo và số trang.

### Kiểm chứng tài chính và nhập giả định định giá

Xem [phương pháp và schema đầu vào](docs/RESEARCH_METHODS.md). Khi đã đối chiếu tài liệu gốc,
lưu hồ sơ theo mã tại `var/financial_reviews/SSI.json`; lưu ba kịch bản tại
`config/valuation/SSI.json`. Bộ tạo tự đọc hai tệp này. Có thể chỉ định tệp riêng:

```powershell
.\run.ps1 reports generate --kind stock --symbol SSI --review "var/financial_reviews/SSI.json" --scenarios "config/valuation/SSI.json"
```

Không có sẵn hồ sơ đã xác minh cho SSI hay giả định bội số mặc định. Không nhập số cổ phiếu
bằng cách chia vốn điều lệ cho mệnh giá. Hồ sơ phải nêu nguồn và bao phủ mọi quý đang dùng;
TTM cần đủ bốn quý liên tiếp. Doanh nghiệp tài chính dùng profile riêng, không được chấm
D/E hoặc CFO theo mô hình sản xuất. P/B cần VCSH thuộc cổ đông công ty mẹ và cổ phiếu;
P/E cần EPS TTM đã kiểm chứng. Thuyết minh chưa đối chiếu thì đánh giá vẫn là theo dõi.

Dữ liệu vĩ mô hiện là GDP/CPI/thương mại/FDI **theo năm**, có năm quan sát và nguồn.
Báo cáo có diễn giải biến động và chuỗi tác động theo ngành; chưa có chuỗi lãi suất,
tỷ giá, tín dụng tháng hiện tại đủ kiểm chứng. Snapshot ngành giữ đơn vị nguồn chưa xác nhận.
DCF, NAV, NIM/NPL và an toàn vốn cần thêm đầu vào riêng, chưa được suy diễn từ dữ liệu thiếu.

## Ý nghĩa dữ liệu và giới hạn

- DNSE giữ OHLCV, thời gian nguồn và trạng thái nến; bộ thu thập hỗ trợ danh mục,
  VNINDEX và dữ liệu nước ngoài. Nến ngày đang diễn ra có thể chưa được REST công bố.
  `requested_until` là mốc yêu cầu; xem inventory để biết thời điểm dữ liệu thực.
- Nến phút cập nhật ngày hiện tại; cuối tuần lấy thứ Sáu gần nhất. Chưa tự lấp
  mọi ngày phút còn thiếu trong lịch sử, và chưa tự nhận diện ngày nghỉ lễ.
  `--foreign` lấy hết các trang snapshot của phiên này và giữ lịch sử đã có.
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
- DNSE ngành: đã thu thập 22 nhóm GICS cấp 2 và ánh xạ mã qua `gicsIndustryGroupId`.
  Snapshot gồm biến động theo các khoảng thời gian, khối lượng, vốn hóa và giá trị giao dịch
  do nguồn cung cấp. Giữ đơn vị/giá trị gốc với chất lượng `raw`; cần kiểm chứng đơn vị
  trước tính toán. Đây là thống kê ngành trên bảng giá DNSE, chưa phải chuỗi OHLCV
  lịch sử của chỉ số ngành. Lịch sử snapshot bắt đầu từ lúc bộ thu thập được chạy.
- Tin lưu tiêu đề, đoạn trích và URL gốc. “Việt Nam/quốc tế” phân theo phạm vi kênh nguồn,
  không theo ngôn ngữ: kênh Thế giới của VnExpress nằm trong Quốc tế.
  Ngày đăng thiếu giữ trống; ngày ghi nhận được lưu riêng. Gợi ý mã/ngành theo từ khóa
  chưa phải liên kết đã kiểm chứng để đưa trực tiếp vào khuyến nghị đầu tư.
- Dữ liệu nhập cũ có nguồn/thời điểm tải nhưng không có phản hồi gốc đi kèm.
  Lượt tải mới lưu bản gốc và receipts dưới `var/runs`.
- Manifest trích xuất và lượt tải cũ có thể chứa đường dẫn cũ vì là dấu vết lịch sử;
  đường dẫn chạy hiện tại được giải theo thư mục dự án mới.

Web hiện phục vụ cục bộ tại `127.0.0.1`, đọc báo cáo/tin và cập nhật tin nền,
chưa có đăng nhập, upload, lịch tạo báo cáo hay triển khai công khai.
`requirements.txt` là thư viện chạy; `requirements-dev.txt` bổ sung kiểm thử;
`requirements-lock.txt` ghi phiên bản môi trường đã kiểm tra, gồm cả thư viện phát triển.

Nguồn đặc tả DNSE: [OHLC history](https://developers.dnse.com.vn/docs/dnse/get-ohlc-history/).
Mã nguồn tách theo giấy phép MIT đi kèm trong `LICENSE`.

Chi tiết phần chuyển tin và nguồn ngành: [DATA_NEWS.md](docs/DATA_NEWS.md).
Kết quả kiểm tra: [VALIDATION.md](docs/VALIDATION.md).

## Tải lại toàn bộ dữ liệu và kiểm tra DNSE

Các tác vụ hữu hạn dưới `tasks/` dùng cùng `.env`, không in khóa ra nhật ký:

```powershell
python tasks/probe_dnse_capabilities.py
python tasks/refresh_all_data.py
python tasks/refresh_market_all.py
# Tiếp tục lượt BCTC đã bị gián đoạn (dùng đúng thư mục manifest):
python tasks/refresh_all_data.py --resume var/runs/full-refresh-YYYYMMDDTHHMMSS
```

Lượt BCTC sao lưu SQLite trước khi tải lại 8 quý đã công bố, ưu tiên 28 mã ngân hàng.
Lượt DNSE ưu tiên ngân hàng, tải lịch sử nến ngày/VNINDEX, nến phút và nước ngoài
của phiên gần nhất. Hai nguồn có thể chạy đồng thời; mỗi nguồn có khóa collector.
Tiến độ ở `outputs/FULL_REFRESH_PROGRESS.json` và `outputs/MARKET_REFRESH_PROGRESS.json`;
manifest và phản hồi gốc ở `var/runs/`. Cả hai lượt tạo lại báo cáo ngành ngân hàng
sau khi hoàn tất nhóm ưu tiên; dữ liệu thay đổi tạo phiên bản mới, không xóa bản cũ.

`outputs/coverage.csv` phản ánh độ phủ thực tế, không chỉ số request thành công.
Không coi ô trống là 0; không coi metadata 8 quý là đã đủ cả ba bảng BCTC.
Trong lúc lượt BCTC chạy, tạo báo cáo dùng dữ liệu đã ghi thành công; mã chưa tải
sẽ có thông báo chờ, không khởi động thêm collector CafeF cạnh tranh.

## Báo cáo vĩ mô theo bản nội dung được duyệt

Ngày chốt `2026-10-09` có bản tham chiếu tại
`config/report_content/macro-2026-10-09.md`, được dàn thành PDF riêng 8 trang.
Chọn Vĩ mô và đúng ngày này trên web, hoặc chạy:

```powershell
python tasks/design_macro_from_markdown.py
```

PDF xuất thêm tại `output/pdf/bao-cao-vi-mo-viet-nam-10-2026-ban-markdown.pdf`;
bản đối chiếu thay đổi ở `output/pdf/doi-chieu-ban-markdown-vi-mo.md`.
Đầu vào và SHA-256 của Markdown được lưu trong hồ sơ phân tích. Agriseco và
tin tức được ghi là dẫn lại từ tài liệu người dùng, chưa kiểm chứng độc lập;
không tạo URL nguồn giả và không trộn dữ liệu live vào bản có ngày chốt này.
Ngày khác vẫn dùng bộ tạo vĩ mô từ kho dữ liệu, không tái sử dụng snapshot cũ.

## Khuôn báo cáo doanh nghiệp có định giá

Các báo cáo cổ phiếu qua web/CLI dùng `config/report_content/company-template.md`:
bìa kết luận trước, đủ mục I–VIII và 7.1–7.10. Xuất bản kiểm tra cho một mã:

```powershell
python tasks/design_company_report.py --symbol VCB --as-of 2026-10-09
```

Giá mục tiêu/khuyến nghị chỉ xuất sau kiểm chứng; không có giả định mặc định.
Hỗ trợ FCFF, FCFE, NAV, P/B theo ROE, P/E/P/B kịch bản và tổng hợp có trọng số nhập rõ.
Đầu vào, đơn vị, công thức và kiểm tra phát hành: [hướng dẫn định giá](config/valuation/README.md).
Thông tin cổ đông, cơ cấu doanh thu và chỉ tiêu công bố:
[hồ sơ doanh nghiệp có nguồn](config/company_profiles/README.md).
Ô thiếu không điền 0; nguồn và dấu SHA-256 của khuôn được lưu trong hồ sơ phân tích.

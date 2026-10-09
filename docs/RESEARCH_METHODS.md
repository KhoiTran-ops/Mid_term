# Phương pháp phân tích và kiểm chứng đầu vào

Phiên bản 09/10/2026; công thức `financials-1.0`, định dạng `research-a4-1.1`.
Quy tắc người dùng và mẫu SSI là đầu vào thiết kế. Không chép số liệu, giá mục tiêu
hoặc khuyến nghị của mẫu vào báo cáo mới. Chưa tự tải PDF BCTC gốc/thuyết minh cho mọi mã.

## Ba đầu ra và luồng chung

`reports generate --kind all --symbol SSI` dựng ba tài liệu: cổ phiếu SSI,
ngành của SSI theo DNSE và tổng quan vĩ mô Việt Nam. `stock`, `industry`, `macro`
dựng từng loại riêng. Bộ `macro_section`/`industry_section` được tái sử dụng trong
báo cáo cổ phiếu; web gọi cùng `generate_reports`, publisher và catalog với CLI.

PDF cổ phiếu có tóm tắt đánh giá, mô hình doanh nghiệp/tin liên quan, vĩ mô,
ngành, tài chính/chất lượng lợi nhuận, giá/giao dịch, định giá/kịch bản và rủi ro.
Ngành có nhóm doanh nghiệp cùng kỳ, phân nhóm mô hình, vĩ mô và rủi ro riêng.
Vĩ mô có chuỗi định lượng năm, diễn giải thay đổi, tin có nguồn, VNINDEX và
đối chiếu các ngành. Mỗi bảng/biểu đồ có nguồn; nhận định có giả định được đánh dấu.

Các nguồn được đọc lần đầu rồi giữ trong một lượt tạo để collector tiếp tục chạy
mà không làm thay đổi đầu vào đã dùng. Đây không phải giao dịch đồng thời giữa
mọi kho nguồn. JSON lưu đúng các facts tài chính đã đọc, cùng giá/quan sát được dùng.

## Tài chính

- Chọn tối đa tám kỳ đã công bố gần nhất; metadata báo cáo không bảo đảm đủ mọi bảng.
- Ánh xạ tên chỉ tiêu theo bảng và danh sách alias. Hai dòng cùng chỉ tiêu nhưng
  khác giá trị bị giữ thiếu và cảnh báo. Không cộng CashFlow và CashFlowDirect.
- Không dùng 0 thay thiếu. Phân số có mẫu số không dương trả thiếu.
- Tỷ lệ cùng bảng trên đơn vị gốc chỉ là quan sát sơ bộ khi chưa kiểm chứng scope/đơn vị.
- Quý riêng từ YTD: Q1 giữ nguyên; Qn = YTD Qn − YTD Q(n−1) trong cùng năm.
  Thiếu quý trước thì kết quả thiếu; không trừ Q1 cho Q4 năm trước.
- TTM chỉ tính khi có bốn quý liên tiếp, đã kiểm chứng quý/lũy kế.
- ROE/ROA = LNST TTM / trung bình số dư cuối kỳ hiện tại và cuối kỳ cùng quý năm trước.
  Đây là bình quân hai điểm, không phải bình quân mọi ngày/quý.
- CFO/LNST quý riêng chỉ áp dụng doanh nghiệp phi tài chính và sau chuyển YTD.

Profile gồm ngân hàng, chứng khoán, BĐS, sản xuất/vật liệu, tài chính khác và phi tài chính khác.
Chứng khoán trình bày tỷ trọng môi giới, lãi cho vay/phải thu, FVTPL theo số liệu thực tế;
không ép công ty vào một nhóm duy nhất và không đồng nhất lãi FVTPL với đánh giá lại.
Ngân hàng/chứng khoán/tài chính khác không nhận chỉ tiêu vay/VCSH hoặc CFO theo
cách chấm điểm doanh nghiệp sản xuất. NIM/NPL/CAR, margin thực và an toàn tài chính
cần thuyết minh hoặc báo cáo quản lý bổ sung; không được thay bằng tỷ lệ gần giống.

Peer cổ phiếu thuộc cùng GICS, cùng profile và đúng kỳ được chọn; ưu tiên HOSE.
Tối đa năm mã, có cảnh báo nếu dưới ba. Peer tự chọn theo danh mục chỉ là nhóm quan sát;
không tự khẳng định tương đồng về quy mô hay lấy trung bình nhóm làm chuẩn định giá.
Ngành có thể có nhiều mô hình; từng mô hình được trình bày riêng.

## Hồ sơ kiểm chứng

Lưu `var/financial_reviews/<SYMBOL>.json` hoặc truyền `--review`.
Không tạo tệp xác nhận mặc định từ dữ liệu CafeF. Các trường:

| Trường | Yêu cầu |
|---|---|
| symbol | Khớp mã đang phân tích |
| periods | Danh sách `YYYYQn`, bao phủ mọi kỳ được dùng |
| scope | `consolidated` hoặc `standalone`, đã đối chiếu BCTC |
| currency | `VND` |
| money_multiplier | Hệ số dương đổi số gốc thành VND; ví dụ nguồn triệu đồng thì 1000000 |
| income_basis | `quarter` hoặc `ytd`, sau kiểm chứng |
| cash_flow_basis | `quarter`, `ytd` hoặc null khi chưa xác định |
| source | source_name, URL BCTC gốc, retrieved_at có múi giờ, locator (trang/dòng) |
| notes_reviewed | Chỉ true khi đã đọc thuyết minh/tài liệu bổ sung cần thiết |
| price_multiplier | Hệ số dương đổi giá DNSE thành VND, có bằng chứng |
| shares_outstanding | Số cổ phiếu phù hợp ngày định giá; không suy ra từ vốn điều lệ |
| parent_equity_vnd | VCSH thuộc cổ đông công ty mẹ, VND; không gồm lợi ích thiểu số |
| eps_ttm_vnd | EPS TTM VND đã kiểm chứng/điều chỉnh pha loãng khi cần |

Các trường định giá có thể null khi chưa đủ tài liệu; báo cáo vẫn xuất được và ghi rõ thiếu.
Phải bổ sung định vị trang cho từng chỉ tiêu đặc thù từ thuyết minh khi đưa vào tính toán.

## Ba kịch bản định giá

Lưu `config/valuation/<SYMBOL>.json` hoặc truyền `--scenarios`.
Schema gồm `method` (`pb` hoặc `pe`), `horizon_months` (1–60) và đúng ba `cases`.
Mỗi case có `name` duy nhất (`bear`, `base`, `bull`), `multiple` dương,
`growth` > −1 (tỷ lệ, không phải phần trăm), `rationale` giải thích lựa chọn;
`forecast_shares` dương là tùy chọn cho P/B khi cần xét pha loãng.

- P/B = VCSH công ty mẹ × (1 + growth) / cổ phiếu dự phóng × multiple.
- P/E = EPS TTM đã kiểm chứng × (1 + growth) × multiple.
- Giá so sánh = close DNSE × price_multiplier. Upside = (giá kịch bản / giá so sánh − 1) × 100.
- Profile tài chính chỉ hỗ trợ P/B ở phiên bản này. P/E không nhận forecast_shares
  riêng, phải dùng EPS đã xét pha loãng. EPS không dương thì không dùng P/E.
- Thiếu hồ sơ/đơn vị/cổ phiếu/EPS hoặc kịch bản thì không tạo giá mục tiêu.
- Chưa đối chiếu thuyết minh thì chỉ đánh giá theo dõi. Sau kiểm chứng:
  upside cơ sở ≥15% là tích cực, ≤−15% là thận trọng, còn lại trung lập.
  Ngưỡng này là quy tắc phiên bản 1 do phần mềm đặt, không phải chuẩn cơ quan quản lý,
  không gán xác suất và không phải khuyến nghị vô điều kiện.

Bội số và tăng trưởng luôn là giả định nhập có giải thích; không tự lấy bội số nước ngoài
áp cho Việt Nam. DCF/NAV chưa triển khai vì cần dự phóng và chiết khấu/dữ liệu dự án riêng.

## Vĩ mô, ngành, giao dịch và tin

World Bank WDI: tăng trưởng GDP thực, CPI, thương mại/GDP, FDI ròng vào/GDP;
11 năm trước năm hiện tại, giữ năm quan sát, URL API và ngày nguồn cập nhật.
Đây là chuỗi năm có thể được điều chỉnh, không phải GDP/CPI tháng hiện tại.
Diễn giải tăng/giảm dựa trên quan sát năm, chuỗi tác động ngành được ghi là giả định.
Lãi suất/tỷ giá/tín dụng tháng hiện tại còn thiếu, không tự dự báo từ tiêu đề tin.

Ngành DNSE là GICS cấp 2, snapshot MQTT giữ giá trị gốc và thời gian nguồn.
Đơn vị/phương pháp chỉ số ngành chưa được xác nhận; không ghép snapshot thành OHLCV.
Giá cổ phiếu/VNINDEX dùng nến ngày đóng hợp lệ; SMA và biến động giá dùng close gốc,
chưa xác nhận điều chỉnh chia tách/cổ tức nên không gọi là tổng lợi suất.
Giao dịch nước ngoài chỉ lấy board G1, không cộng lặp các board.

Tin chọn có giới hạn theo nguồn, giữ tiêu đề/ngày/link để đọc bản gốc; không tự gán
tác động nhân quả hay thay số liệu kế toán từ tin. Liên kết mã/ngành bằng từ khóa vẫn
cần kiểm chứng. Ngày chốt lọc kỳ/thời điểm nguồn; dữ liệu điều chỉnh và phân ngành hiện tại
khiến bộ này chưa phù hợp backtest tránh hoàn toàn look-ahead.

## Nguồn phương pháp và công cụ

- [World Bank Indicator API Queries](https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries): cấu trúc API/chuỗi năm.
- [Damodaran: Valuing Financial Service Firms](https://people.stern.nyu.edu/adamodar/pdfiles/eqnotes/finsvc.pdf): đặc thù nợ, vốn và định giá doanh nghiệp tài chính.
- [ReportLab User Guide](https://docs.reportlab.com/reportlab/userguide/): layout, bảng, biểu đồ và font TrueType nhúng.
- [Noto Fonts](https://github.com/notofonts/noto-fonts): font tiếng Việt lưu tại web/static/fonts, giấy phép OFL đi cùng.

Các nguồn phương pháp không cung cấp giá mục tiêu hoặc bội số được xác nhận cho từng mã.

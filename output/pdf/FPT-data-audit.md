# Đối chiếu pipeline FPT – giá chốt 09/10/2026

Đây là bản sửa dữ liệu, giữ giao diện 10 trang. Không sao chép điểm hoặc snapshot tổng hợp từ PDF vào trường dữ liệu hiện hành.

## Đã sửa

- Giá hiển thị: CafeF EOD thô 57.900 VND/cp. Chỉ báo: 530 phiên giá điều chỉnh VCI qua vnstock 4.0.9; không điều chỉnh lần hai. MA50/200, RSI, MACD và lợi suất 3/6/12 tháng khớp trong sai số 2%.
- TB20 dùng 20 phiên trước, không chứa phiên hiện tại; giá trị phiên thực và TB20 ước lượng có nhãn riêng. Volume khớp lệnh CafeF trước thưởng ×1,1; volume tổng VCI không bị trộn vào mẫu khớp lệnh.
- Các nguồn gốc FPT đã tải: BCTN 2021/2022/2023/2025, BCTC Q1/Q2 và H1 soát xét 2026, nghị quyết thay đổi cổ phiếu 07/10/2026, thông báo thưởng và hai kết quả phát hành ESOP.
- 65 dữ kiện năm đã trích theo mã dòng/cột từ lớp văn bản gốc. Bảng PDF 2022–2025; JSON lưu thêm 2021 và bảng 5 kỳ quý. 31 dữ kiện quý/đối chiếu được lưu riêng có trang, URL, SHA-256 và lý do.
- Sửa tài sản 2026Q1/Q2: nguồn CafeF ánh xạ nhầm dòng tài sản dài hạn khác thành tổng tài sản. Dùng tổng tài sản công bố; tổng vốn gồm lợi ích không kiểm soát. Vốn mẹ = tổng vốn công bố − lợi ích không kiểm soát công bố (†), không suy tổng vốn = tài sản − nợ.
- Thu nhập Q4/2025 = năm kiểm toán − Q1/Q2/Q3; thu nhập Q2/2026 = H1 soát xét − Q1 công bố. Dòng tiền giữ YTD; không trừ các bản chỉnh sửa khác cơ sở. FPT Telecom đổi cơ sở hợp nhất từ 01/01/2026: không so YoY doanh thu/LNST hợp nhất thô.
- EPS TTM = LNST mẹ bốn quý / 1.885.727.648 cổ phiếu đã kiểm chứng tại nghị quyết 07/10. P/B dùng vốn mẹ H1 soát xét. Chỉ tiêu provider khác cơ sở vẫn giữ trong JSON nhưng không dùng để tính và không thay thế số đã đối chiếu trong PDF.
- Annual Miner: chuẩn hóa khoảng trắng/ngắt dòng trước đếm cụm từ. SHA-256 PDF 2025: `6dfe3ae09e6663c78021e24cefe0d745504c50e2892809915b3306d4fa9ec58c`. 233 trang/231 có chữ; 117.171 token; 1.141 lượt/7 từ khóa; mật độ 97,38. Hai trích đoạn có trang, không suy cảm xúc từ tần suất.
- Tin Toyota và ZEBOX lấy trực tiếp từ FPT, giữ ngày và +07. Giờ xuất bản không được nguồn xác nhận: 00:00 là chuẩn hóa ngày, không phải thời điểm chính xác. Tác động tài chính chưa xác minh định lượng.
- Sinh ba kịch bản có điều kiện và tám cảnh báo, không xác suất/giá mục tiêu. Mỗi ô null có missing_reason, kể cả ô không áp dụng.
- Biểu đồ biên lợi nhuận có bốn nhãn năm và trục % theo bước 5 điểm; biểu đồ nguồn vốn đủ các năm có cả nợ và vốn.

## Khác cơ sở cần lưu ý

Tham chiếu X10 TB20 ≈353,3 tỷ và KL/TB20 ≈1,98 được tái tạo bằng khối lượng khớp lệnh **chưa điều chỉnh** thưởng. Khi thực hiện yêu cầu điều chỉnh volume trước ngày 21/09 ×1,1, số hiện hành là TB20 ≈367,96 tỷ và KL/TB20 ≈1,90. JSON giữ `technical.reference_turnover_ma20` / `reference_volume_vs_ma20` để kiểm tra, không dùng chúng làm số điều chỉnh. Bảng nghiệm thu ghi `different_basis`, không ghi đạt giả.

Hai đợt 24/06 là ESOP có giá phát hành 10.000 VND và khóa chuyển nhượng 3/10 năm, không phải chia tách/ thưởng. Không chia giá máy móc cho 1+0,00499+0,00135 hoặc nhân volume như một split. Giá lịch sử dùng nguồn điều chỉnh VCI.

## Chưa hoàn tất – không điền số mẫu

1. Đã thay yêu cầu X10 bằng engine tự xây do người dùng cung cấp ngày 11/10/2026. Cấu hình giữ nguyên; hash engine trả về `013a149bbbec22f0e0aa4395e19d59a0d4ba094df29f31003c6baab4188f55af`. FA/coverage/TA/điểm thống nhất đã có kết quả thật; trụ cột value còn null vì cấu hình tắt, không phải lỗi tải.
2. Chưa có dữ liệu từng thành viên của snapshot peer 23 mẫu ngày 02/10/2026. Không lấy trung vị 10,82 trong PDF làm kết quả tính; không trộn P/E hiện tại với P/E snapshot. Phân loại DNSE GICS vẫn giữ nhãn nguồn, không đổi thành ICB sector chỉ để giống PDF.
3. Không xác nhận đã rà toàn bộ thuyết minh tài chính. OCR chỉ phục vụ đọc; dữ kiện đưa vào review đã đối chiếu trực quan/mã dòng. Hồ sơ năm cần trích lại nếu file công bố thay đổi.

## Nguồn và giả định

- Giá điều chỉnh: https://trading.vietcap.com.vn qua Quote.history; tài liệu đơn vị và adjusted: https://www.vnstocks.com/docs/vnstock-data/du-lieu-giao-dich.
- Đơn vị CafeF: nghìn VND, volume cổ phiếu, giá trị tỷ VND được kiểm tra trên trang đơn vị trước refresh. Giá trị close_adjusted × volume là **ước lượng**, không thay thế giá trị giao dịch thực.
- Công bố gốc: https://fpt.com/vi/nha-dau-tu/bao-cao-thuong-nien và https://fpt.com/vi/nha-dau-tu/thong-tin-cong-bo. Mỗi chỉ tiêu có URL, trang/mã dòng và SHA trong hồ sơ review/JSON provenance.
- Quyền: thông báo FPT ngày 09/09 có 10:1 và ngày đăng ký cuối cùng 22/09; ngày GDKHQ 21/09 đối chiếu https://www.bsc.com.vn/lich-su-kien/FPT_20260922_STOCK_DIV/.
- Peer/engine thiếu thì giữ null. Dữ liệu tải hiện tại không phải snapshot backtest point-in-time; không giả định thông tin đã biết tại các ngày lịch sử.

## Chạy lại

Python dùng môi trường chung `C:\Users\ADMIN\.venv`. vnstock 4.0.9/vnai 2.6.3 cài từ kho chính thức; phụ thuộc công khai lấy từ PyPI. Không bật đồng bộ agent/skill hoặc ghi API key. Cài đặt phụ thuộc vnstock đã chuyển pandas về 2.3.3 và numpy về 2.2.6; bộ kiểm thử dự án được chạy lại.

`tasks/refresh_stocklens_adjusted.py`, `refresh_stocklens_prices.py`, `review_fpt_annuals.py`, `review_fpt_quarters.py`, `preview_stocklens.py`, `accept_stocklens.py`, `qa_stocklens.py` cung cấp các bước làm mới, đối chiếu và nghiệm thu. Sinh web tự kiểm tra cache giá điều chỉnh; thiếu thì chạy VCI → KBS khi `auto_price_refresh=true`. Thất bại giữ bản lưu và lý do, không log header/secret.

`FPT-acceptance.json` hiện chứa 29 trường nghiệm thu (thêm FA thô và phân biệt FA hiệu dụng): 24 đạt, 2 khác cơ sở, 3 chưa có snapshot peer gốc; **all_targets_met=false**. `missing_report.json` liệt kê từng ô còn thiếu/không áp dụng và cổng kiểm tra. API: `/api/reports/{id}/missing-report`.

## Kiểm tra cuối ngày 11/10/2026

- Bộ kiểm thử trước engine: **145 passed**; sau tích hợp engine và kiểm tra hash: **154 passed**. Bản PDF của FPT, HPG, VCB, ACB, ACG và SSI đều đủ 10 trang; kiểm tra dựng ảnh sau mỗi lần cập nhật.
- CafeF giá thô FPT: 493 phiên; VNINDEX: 495 phiên. Trình tải dùng cửa sổ năm với cả ngày bắt đầu/kết thúc và phân trang, không để kết quả 225 phiên ghi đè lịch sử đầy đủ.
- Localhost cổng 8000: trang chủ và API JSON/PDF/missing-report trả thành công. Dữ liệu năm gồm 2021–2025; JSON có 5 kỳ quý. Các ô null được giải thích riêng, bao gồm chỉ tiêu không áp dụng và trụ cột value tắt.
- Kiểm tra thực tế tạo lại cùng dữ liệu: `reused=true`, giữ ID `a7efa11a-c32e-4bac-85f5-6caefa541dbe`. Nguồn tin mới làm thay đổi đầu vào nên tạo phiên bản mới, không phải bản trùng của cùng snapshot. Không xóa các phiên bản cũ của người dùng.
- Đã giải quyết đầu vào engine; còn thiếu dữ liệu thành viên peer gốc. Không biến ô thiếu thành số 0 hoặc sao chép điểm trong PDF.

## Bổ sung chấm điểm FA/TA

- Gọi engine tự xây với 10 đầu vào FA từ BCTC năm 2025 và chuỗi giá/volume đã điều chỉnh. FA thô 75,9134; hiệu dụng 70,7307; độ phủ 80%; TA 5; thống nhất 18,1; vào 60/ra 35; `WATCH / SCORE_BELOW_ENTRY`.
- JSON giữ cả inputs, kết quả engine nguyên bản, điểm từng trụ cột, 5 điều kiện TA, decision, hash cấu hình và hash engine. Cấu hình byte-for-byte khớp file người dùng; chỉ thêm guard None ở engine, có mô tả/mã băm tại `STRATEGY_ENGINE.md`.
- CI chạy `test_engine.py` nguyên bản và các test adapter. Runtime/CI chặn thay cấu hình khi chưa cập nhật hash đã ghi. Không tự hiệu chỉnh trọng số/ngưỡng.
- TB20 kiểm tra thanh khoản của engine gồm phiên hiện tại theo mã gốc; TB20 trang 4 loại phiên hiện tại theo yêu cầu báo cáo. Hai cơ sở được ghi rõ, không sửa engine để ép trùng số.

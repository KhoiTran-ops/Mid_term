# Đối chiếu cấu trúc trước và sau

Gốc chạy hiện tại: `F:\Mid_term_finance1\Mid_term`.
Thay đổi cấu trúc không tải thêm dữ liệu và không chuyển sang database thị trường khác.

| Module trước | Module sau, dưới `src/stock_reports/` |
|---|---|
| `common/types.py` | `domain/market.py` |
| `data/providers.py` | `core/errors.py` |
| `data/dnse_market.py` | `data_sources/dnse/market.py` |
| `data/cafef/client.py` | `data_sources/cafef/client.py` |
| `data/cafef/parsers.py` | `data_sources/cafef/parsers.py` |
| `data/cafef/sync.py` | `data_sources/cafef/sync.py` |
| `data/archive.py` | `data_sources/archive.py` |
| `data/db/market_store.py` | `storage/market.py` |
| `data/inventory.py` | `storage/inventory.py` |
| `data/refresh.py` | `pipeline/market_refresh.py` |
| `scripts/import_legacy.py` | `pipeline/import_legacy.py` |
| `collect_data.py` | `pipeline/collection.py`, gọi qua `run.ps1 data ...` |

Import và đường dẫn monkeypatch của kiểm thử đã cập nhật theo package mới.
Không giữ hai bản implementation provider. Các thư mục cũ có thể còn cache Python
từ môi trường trước, không phải module nguồn đang được dùng.

Các module mới cho domain nghiên cứu, hợp đồng nguồn/phân tích/render, catalog,
publication và web được liệt kê trong `CAPABILITY_MAP.md`.

`docs/extraction_manifest.json` và manifest dưới `var/runs` là hồ sơ trích xuất/lượt tải
trước tái cấu trúc. Các đường dẫn cũ trong đó là lịch sử, được giữ nguyên.
`.env`, `var/market_data.db`, dữ liệu gốc và outputs có sẵn được giữ.
`var/reports.db` và `outputs/reports/` là kho riêng cho chức năng thư viện mới.

Không có khuyến nghị giả, số liệu giả hoặc PDF mẫu trong thư viện thực.
Fixture kiểm thử được tạo trong thư mục tạm và tách khỏi database thị trường.

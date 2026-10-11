# StockLens - company-report export

Default stock-report output is a source-backed, ten-page HTML/CSS/Chromium PDF. Industry and macro renderers are unchanged.

```powershell
& C:/Users/ADMIN/.venv/Scripts/python.exe run.py render --ticker FPT --out FPT.pdf
& C:/Users/ADMIN/.venv/Scripts/python.exe run.py render --ticker HPG --horizon long --out HPG.pdf
& C:/Users/ADMIN/.venv/Scripts/python.exe run.py render --ticker FPT --input outputs/stocklens/FPT.json --out FPT.pdf
```

The command creates PDF, JSON and self-contained HTML sidecars. For repository examples use `output/pdf/FPT-stocklens-2026-10-11.json`; this is the exact JSON of the final published PDF. The website offers PDF and JSON downloads.

## Files

- `schema.json`: strict typed JSON contract, explicit nulls, evidence paths and source metadata.
- `data.py`: source adapter and backend financial/technical calculations.
- `charts.py`: pure server-side SVG geometry, preserving gaps.
- `tokens.css`, `components.css`, `components.html`: reusable visual system.
- `base.html`, `pages/01_*.html` through `pages/10_*.html`: independent page partials.
- `assets/fonts.css`, `assets/fonts/`: fonts extracted from the supplied reference and embedded offline.
- `render.py`: validation, formatting, HTML, overflow checks, ten-page PDF assertion.
- `config/stocklens.json`: brand accent, default horizon and presentation-focus matrix.
- `tests/test_stocklens.py`: missing valuation, banks, fewer years, zeros, large/small numbers, long names, evidence, balance identity and overflow.

Use `render_html(payload, pages=(...))` for selected/reordered HTML partials. The published PDF intentionally always uses the ten default pages. Template calculations are restricted to layout and formatting; finance/indicator calculations occur in the adapter.

Install `requirements.txt`. A bundled Playwright Chromium is preferred; installed Microsoft Edge is used as a local Chromium fallback. Fonts and SVG are embedded; external requests are blocked during rendering. Install Chromium with `python -m playwright install chromium` if neither engine exists.

An overflow error reports ticker/page and prevents publication, instead of clipping text. Timestamps use Asia/Ho_Chi_Minh. Cache keys include template assets, configuration and source-backed data, so repeated identical requests reuse the same report.

## Explicit assumptions and boundaries

1. The reference supplies design only, never its FPT scores, prices, forecasts or keyword counts.
2. The default financial window is the last four completed years (2022-2025 for an October 2026 report). Earlier years remain in the database. Missing items remain null and genuine zero stays zero.
3. Raw CafeF prices supply the displayed quote. Indicators use archived adjusted VCI/vnstock prices with at least 300 sessions preferred; the last 250 are displayed. No padding or guessed back-adjustment. `auto_price_refresh` enables VCI → KBS fallback in report jobs; the optional SDK is installed from `https://vnstocks.com/api/simple` with public dependencies from PyPI. Never enable vnstock agent-file synchronization for this module.
4. Monthly performance uses calendar months and observed dates, not 21-session months. VN-Index RS uses common start/end trading dates. Provider adjusted prices are not total returns. CafeF matched volumes are adjusted only with reviewed split/bonus volume factors; ESOP is not a split. Raw-volume X10 comparison fields are separate from adjusted current fields.
5. Annual and quarter/YTD values remain separate. Unknown units/bases remain visible in limitations. Unbalanced annual statements are not silently reconciled, and equity is never inferred as assets minus liabilities.
6. TTM valuation requires parent profit, verified shares and parent equity. Verified valuation replaces provider figures in the PDF; differently based provider figures stay labeled separately in JSON. Peer medians require dated member-level snapshots; current multiples cannot reproduce an absent historical snapshot.
7. Banking excludes manufacturing margins, CFO/net-income and liquidity ratios. NIM/CASA/NPL/CAR retain their original reporting period and scope, including half-year versus quarter distinctions.
8. FA/TA/unified scores require the original X10 engine/config; no rewriting or copying PDF results. Conditional scenarios use actual adjusted thresholds, without probabilities/targets. Annual mining is recomputed from an actual issuer PDF, with hash/pages/token denominator and normalized phrase linebreaks. Risk preference defaults to balanced/moderate, independently of scoring.
9. Profile rows (8), news (2 when annual evidence is present, otherwise 4) and alerts (8) have explicit limits and omission notices. Issuer announcements take display priority; JSON keeps all selected financial news. Every null has a path-specific missing_reason. `render_pdf` exports a `.missing_report.json` sidecar; CLI also writes `missing_report.json` and web provides `/api/reports/{id}/missing-report`.
10. As-of accounting periods do not guarantee point-in-time backtest availability. Data-quality review is not a completeness certification of all issuer notes.

`tasks/accept_stocklens.py` generates the requested FPT acceptance table and reports unavailable/different-basis results explicitly. It never treats missing X10 or peer inputs as passed. Detailed sources, assumptions and remaining blockers: `output/pdf/FPT-data-audit.md`.

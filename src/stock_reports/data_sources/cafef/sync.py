"""CafeF audited financial statements and one-day EOD fallback."""

from dataclasses import dataclass
from datetime import date, datetime, time as clock_time, timedelta, timezone
import logging
import math
from typing import Callable, Iterable, Protocol

from stock_reports.data_sources.cafef.client import CafeFClient, CafeFError, DataPage, EXCHANGES
from stock_reports.data_sources.cafef.parsers import parse_financial_periods, parse_financial_statement
from stock_reports.storage.market import MarketStore


logger = logging.getLogger(__name__)
STATEMENT_TYPES = ("BSheet", "IncSta", "CashFlow", "CashFlowDirect")


class SyncClient(Protocol):
    def get_price_page(self, **kwargs: object) -> DataPage: ...


@dataclass(frozen=True)
class Instrument:
    symbol: str
    exchange: str
    company_name: str


@dataclass(frozen=True)
class SyncResult:
    dataset: str
    saved: int
    rejected: int
    requests: int
    issues: tuple[dict[str, object], ...] = ()


def catalog_instruments(rows: Iterable[dict[str, object]]) -> list[Instrument]:
    exchange_aliases = {"hose": "HOSE", "hastc": "HNX", "upcom": "UPCOM"}
    instruments: list[Instrument] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        redirect = str(row.get("RedirectUrl", "")).lower()
        parts = [part for part in redirect.split("/") if part]
        exchange = exchange_aliases.get(parts[1], "") if len(parts) > 1 and parts[0] == "du-lieu" else ""
        symbol = str(row.get("Symbol", "")).strip().upper()
        if exchange not in EXCHANGES or not symbol or (symbol, exchange) in seen:
            continue
        seen.add((symbol, exchange))
        instruments.append(Instrument(symbol, exchange, str(row.get("Title", "")).strip()))
    return instruments


def next_daily_run(now: datetime, *, hour: int = 15, minute: int = 0) -> datetime:
    target = datetime.combine(now.date(), clock_time(hour, minute), tzinfo=now.tzinfo)
    return target if target > now else target + timedelta(days=1)


class CafeFSynchronizer:
    def __init__(self, *, client: SyncClient, store: MarketStore,
                 page_size: int = 20) -> None:
        self.client = client
        self.store = store
        self.page_size = page_size

    def sync_market_dataset(self, *, dataset: str, exchange: str,
                            start: date, end: date, resume: bool = True) -> SyncResult:
        if dataset != "prices":
            raise ValueError("CafeF market fallback only supports EOD prices")
        key = f"cafef:{dataset}:{exchange}:{start.isoformat()}:{end.isoformat()}"
        page = int(self.store.get_checkpoint(key) or 0) + 1 if resume else 1
        saved = rejected = requests = 0
        while True:
            response = self.client.get_price_page(
                exchange=exchange, start=start, end=end,
                page=page, page_size=self.page_size,
            )
            requests += 1
            added, bad = self.store.upsert_eod_rows(
                exchange, response.rows, source="cafef"
            )
            saved += added
            rejected += bad
            self.store.set_checkpoint(key, str(page))
            logger.debug("CafeF page synchronized", extra={
                "event": "cafef_page_synchronized", "provider": "cafef",
                "operation": dataset,
            })
            total_pages = math.ceil(response.total_count / self.page_size)
            if page >= total_pages or not response.rows:
                break
            page += 1
        return SyncResult(dataset, saved, rejected, requests)

    def sync_daily(self, day: date) -> list[SyncResult]:
        results: list[SyncResult] = []
        for exchange in sorted(EXCHANGES):
            results.append(self.sync_market_dataset(
                dataset="prices", exchange=exchange, start=day, end=day,
                resume=False,
            ))
        self.store.reconcile_exchange_scopes()
        return results


def sync_catalog(client: CafeFClient, store: MarketStore) -> int:
    instruments = catalog_instruments(client.get_company_catalog())
    count = store.upsert_instruments(instruments, source="cafef")
    store.reconcile_exchange_scopes()
    return count


def sync_financial_history(client: CafeFClient, store: MarketStore, *,
                           max_quarters: int = 8,
                           symbols: Iterable[str] | None = None,
                           incremental: bool = False,
                           on_progress: Callable[[str, int, int], None] | None = None) -> SyncResult:
    if max_quarters < 1:
        raise ValueError("max_quarters must be positive")
    saved = rejected = requests = 0
    issues = []
    selected = list(symbols) if symbols is not None else [s for s, _ in store.list_instruments()]
    for index, symbol in enumerate(selected, 1):
        cached = store.financial_periods_for(symbol, max_quarters) if incremental else []
        cached_keys = {(int(p['fiscal_year']), int(p['fiscal_quarter'])) for p in cached}
        periods: list[dict[str, object]] = []
        page = 1
        while True:
            try:
                block, total = parse_financial_periods(
                    client.get_financial_summary(symbol, page=page)
                )
            except (CafeFError, ValueError) as error:
                rejected += 1
                issues.append(dict(symbol=symbol, dataset='summary', page=page,
                                   error_type=type(error).__name__))
                break
            requests += 1
            unique = {(int(p['fiscal_year']), int(p['fiscal_quarter'])): p for p in periods}
            unique.update({(int(p['fiscal_year']), int(p['fiscal_quarter'])): p for p in block})
            periods = list(unique.values())
            block_keys = {(int(p['fiscal_year']), int(p['fiscal_quarter'])) for p in block}
            if incremental and block and len(cached_keys) >= max_quarters and block_keys <= cached_keys:
                # Reuse the older, already downloaded periods, but preserve fresh audit metadata.
                fresh = {(int(p['fiscal_year']), int(p['fiscal_quarter'])): p for p in periods}
                periods = [*fresh.values(), *[p for p in cached
                    if (int(p['fiscal_year']), int(p['fiscal_quarter'])) not in fresh]]
                break
            if len(periods) >= max_quarters or page * 4 >= total or not block:
                break
            page += 1
        periods = sorted(
            periods,
            key=lambda period: (
                int(period["fiscal_year"]), int(period["fiscal_quarter"])
            ),
            reverse=True,
        )[:max_quarters]
        store.upsert_financial_periods(
            periods, source="https://apiweb.cafef.vn/api/v1/BCTC/GetReportSummary"
        )
        available_periods = {
            (int(period["fiscal_year"]), int(period["fiscal_quarter"]))
            for period in periods
        }
        for statement_type in STATEMENT_TYPES:
            existing = store.financial_statement_periods(symbol, statement_type) if incremental else set()
            pending = available_periods - existing
            attempted = set()
            while pending:
                primary = max(pending)
                number = primary[0] * 4 + primary[1] - 1
                # HTML windows contain four calendar quarters, including gaps in publication.
                primary_window = {p for p in pending if 0 <= number - (p[0]*4+p[1]-1) < 4}
                fallback_year, fallback_zero_quarter = divmod(number + 1, 4)
                fallback = (fallback_year, fallback_zero_quarter + 1)
                anchors = [primary]
                html = None
                for anchor_year, anchor_quarter in anchors:
                    anchor = (anchor_year, anchor_quarter)
                    if anchor in attempted:
                        continue
                    attempted.add(anchor)
                    try:
                        html = client.get_financial_html(symbol, statement_type, anchor_year, anchor_quarter)
                        break
                    except (CafeFError, ValueError) as error:
                        rejected += 1
                        issues.append(dict(symbol=symbol, statement_type=statement_type,
                            anchor=f'{anchor_year}Q{anchor_quarter}', error_type=type(error).__name__,
                            status_code=getattr(error, 'status_code', None)))
                        # An unavailable anchor can still appear in the next quarter's table.
                        if anchor == primary and getattr(error, 'status_code', None) == 404 and fallback <= max(available_periods):
                            anchors.append(fallback)
                if html is None:
                    pending.difference_update(primary_window)
                    continue
                requests += 1
                number = anchor_year * 4 + anchor_quarter - 1
                block_periods = {p for p in available_periods if 0 <= number - (p[0]*4+p[1]-1) < 4}
                pending.difference_update(block_periods)
                facts = parse_financial_statement(html)
                source = (
                    "https://cafef.vn/du-lieu/BaoCaoTaiChinh_V2.aspx"
                    f"?quarter={anchor_quarter}&symbol={symbol}"
                    f"&type={statement_type}&year={anchor_year}"
                )
                filtered = []
                for fact in facts:
                    values = {
                        period: value for period, value in fact["values"].items()
                        if period in block_periods
                    }
                    if values:
                        filtered.append({**fact, "values": values})
                if filtered:
                    saved += store.replace_financial_facts(
                        symbol, statement_type, filtered, source=source
                    )
                else:
                    rejected += 1
                    issues.append(dict(symbol=symbol, statement_type=statement_type,
                        anchor=f'{anchor_year}Q{anchor_quarter}', error_type='NoStatementData'))
                logger.debug("CafeF financial block synchronized", extra={
                    "event": "cafef_financial_synchronized", "provider": "cafef",
                    "operation": statement_type,
                })
        if incremental and periods:
            store.trim_financial_history(symbol, max_quarters)
        if on_progress:
            on_progress(symbol, index, len(selected))
    return SyncResult("financials", saved, rejected, requests, tuple(issues))


def build_default_sync(database_path: str, *, requests_per_second: float = 0.5
                       ) -> tuple[CafeFClient, MarketStore, CafeFSynchronizer]:
    from pathlib import Path
    from stock_reports.data_sources.cafef.client import RateLimitedTransport
    client = CafeFClient(transport=RateLimitedTransport(
        requests_per_second=requests_per_second
    ))
    store = MarketStore(Path(database_path))
    store.initialize()
    return client, store, CafeFSynchronizer(client=client, store=store)


def ho_chi_minh_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh"))

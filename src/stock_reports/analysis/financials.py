"""Source-aware mapping and conservative, versioned financial calculations."""

from contextlib import closing
from dataclasses import dataclass, field
from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from stock_reports.data_sources.news.normalize import fold
from stock_reports.domain.research import SourceReference


FORMULA_VERSION = 'financials-1.0'
ALIASES = {
    'assets': ('BSheet', [r'^tong cong tai san$', r'^tong tai san co$']),
    'equity': ('BSheet', [r'^von chu so huu$']),
    'liabilities': ('BSheet', [r'^no phai tra$', r'^tong no phai tra$']),
    'current_assets': ('BSheet', [r'^tai san ngan han$']),
    'current_liabilities': ('BSheet', [r'^no ngan han$']),
    'inventory': ('BSheet', [r'^hang ton kho$']),
    'receivables': ('BSheet', [r'^cac khoan phai thu ngan han$']),
    'loans': ('BSheet', [r'^cac khoan cho vay$', r'^cho vay khach hang$']),
    'deposits': ('BSheet', [r'^tien gui cua khach hang$']),
    'fvtpl': ('BSheet', [r'^cac tai san tai chinh ghi nhan thong qua lai lo']),
    'short_debt': ('BSheet', [r'^vay va no thue tai chinh ngan han$', r'^vay va no ngan han$']),
    'long_debt': ('BSheet', [r'^vay va no thue tai chinh dai han$', r'^vay va no dai han$']),
    'revenue': ('IncSta', [r'^doanh thu thuan ve ban hang va cung cap dich vu', r'^cong doanh thu hoat dong$', r'^tong thu nhap hoat dong$']),
    'gross_profit': ('IncSta', [r'^loi nhuan gop ve ban hang va cung cap dich vu']),
    'net_profit': ('IncSta', [r'^loi nhuan ke toan sau thue tndn$', r'^loi nhuan sau thue thu nhap doanh nghiep', r'^loi nhuan sau thue$']),
    'parent_profit': ('IncSta', [r'^loi nhuan sau thue cua co dong cong ty me', r'^loi nhuan sau thue cua chu so huu']),
    'brokerage': ('IncSta', [r'^doanh thu moi gioi chung khoan$']),
    'loan_income': ('IncSta', [r'^lai tu cac khoan cho vay va phai thu$']),
    'investment_income': ('IncSta', [r'^lai tu cac tai san tai chinh ghi nhan thong qua lai lo']),
    'unrealized_profit': ('IncSta', [r'^loi nhuan chua thuc hien$']),
    'pretax_profit': ('IncSta', [r'^tong loi nhuan ke toan truoc thue$', r'^tong loi nhuan truoc thue']),
    'interest_income_net': ('IncSta', [r'^thu nhap lai thuan$']),
    'operating_cost': ('IncSta', [r'^chi phi hoat dong$']),
    'cfo': ('CashFlow', [r'^luu chuyen tien thuan tu hoat dong kinh doanh']),
}
LABELS = {
    'assets':'Tổng tài sản', 'equity':'Vốn chủ sở hữu', 'liabilities':'Nợ phải trả',
    'current_assets':'Tài sản ngắn hạn', 'current_liabilities':'Nợ ngắn hạn',
    'inventory':'Hàng tồn kho', 'receivables':'Phải thu ngắn hạn', 'loans':'Các khoản cho vay',
    'deposits':'Tiền gửi khách hàng', 'fvtpl':'Tài sản FVTPL', 'short_debt':'Vay ngắn hạn',
    'long_debt':'Vay dài hạn', 'revenue':'Doanh thu/thu nhập hoạt động', 'gross_profit':'Lợi nhuận gộp',
    'net_profit':'Lợi nhuận sau thuế', 'parent_profit':'LNST cổ đông công ty mẹ',
    'brokerage':'Doanh thu môi giới', 'loan_income':'Lãi cho vay và phải thu',
    'investment_income':'Lãi FVTPL', 'unrealized_profit':'Lợi nhuận chưa thực hiện',
    'pretax_profit':'Lợi nhuận trước thuế', 'interest_income_net':'Thu nhập lãi thuần',
    'operating_cost':'Chi phí hoạt động', 'cfo':'Dòng tiền hoạt động kinh doanh',
}


class FinancialReview(BaseModel):
    """Explicit, sourced analyst verification; never inferred from a UI unit label."""
    model_config = ConfigDict(extra='forbid')
    symbol: str
    periods: tuple[str, ...] = Field(min_length=1)
    scope: Literal['consolidated', 'standalone']
    currency: Literal['VND']
    money_multiplier: Decimal = Field(gt=0, allow_inf_nan=False)
    income_basis: Literal['quarter', 'ytd']
    cash_flow_basis: Literal['quarter', 'ytd'] | None = None
    source: SourceReference
    notes_reviewed: bool = False
    price_multiplier: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    shares_outstanding: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    parent_equity_vnd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    eps_ttm_vnd: Decimal | None = Field(default=None, allow_inf_nan=False)


def quarter_number(period):
    return period[0] * 4 + period[1] - 1


def quarter_from_number(number):
    year, quarter = divmod(number, 4)
    return year, quarter + 1


def parse_period(value: str):
    match = re.fullmatch(r'(\d{4})Q([1-4])', value.upper())
    if not match:
        raise ValueError('Kỳ phải có dạng 2026Q2')
    return int(match[1]), int(match[2])


def normalized_name(value):
    value = re.sub(r'^(?:[A-Z]+|\d+(?:\.\d+)*)[.)]\s*', '', value.strip())
    return fold(re.sub(r'\s+', ' ', value)).strip()


@dataclass(frozen=True)
class Fact:
    value: Decimal | None
    source: SourceReference
    name: str


@dataclass
class FinancialData:
    symbol: str
    periods: list[tuple[int, int]]
    series: dict[str, dict[tuple[int, int], Fact]]
    review: FinancialReview | None
    warnings: list[str]
    audit_statuses: dict = field(default_factory=dict)
    raw_rows: tuple[dict, ...] = ()
    invalid_balance_periods: set = field(default_factory=set)

    def fact(self, key, period):
        return self.series.get(key, {}).get(period)

    def value(self, key, period):
        fact = self.fact(key, period)
        return fact.value if fact else None

    def quarter_value(self, key, period):
        statement = ALIASES[key][0]
        basis = (self.review.cash_flow_basis if statement == 'CashFlow' else self.review.income_basis) if self.review else None
        value = self.value(key, period)
        if value is None or basis is None:
            return None
        if basis == 'quarter' or period[1] == 1:
            return value
        previous = self.value(key, (period[0], period[1]-1))
        return value - previous if previous is not None else None

    def ttm(self, key, period):
        values = [self.quarter_value(key, quarter_from_number(quarter_number(period)-i)) for i in range(4)]
        return sum(values, Decimal(0)) if all(v is not None for v in values) else None


def load_financials(database: Path, symbol: str, *, period=None, review=None):
    if review and review.symbol.upper() != symbol.upper():
        raise ValueError('Hồ sơ kiểm chứng không khớp mã cổ phiếu')
    with closing(sqlite3.connect(database, timeout=30)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        rows = [dict(r) for r in db.execute('SELECT * FROM financial_facts WHERE symbol=? ORDER BY fiscal_year,fiscal_quarter,row_order', (symbol,))]
        published = [tuple(r) for r in db.execute('SELECT fiscal_year,fiscal_quarter FROM financial_periods WHERE symbol=? ORDER BY fiscal_year DESC,fiscal_quarter DESC',(symbol,))]
        audit_rows = [dict(r) for r in db.execute('SELECT * FROM financial_periods WHERE symbol=?',(symbol,))]
    periods = sorted(set(published or [(r['fiscal_year'],r['fiscal_quarter']) for r in rows]), reverse=True)
    if period:
        if period not in periods:
            raise ValueError('Không có kỳ tài chính đã chọn trong dữ liệu lưu')
        periods = [p for p in periods if p <= period]
    periods = periods[:8]
    if review and not set(periods) <= {parse_period(p) for p in review.periods}:
        raise ValueError('Hồ sơ kiểm chứng phải bao phủ tất cả kỳ tài chính được sử dụng')
    series, warnings = {}, []
    for key, (statement, patterns) in ALIASES.items():
        series[key] = {}
        for p in periods:
            candidates = [r for r in rows if (r['fiscal_year'],r['fiscal_quarter']) == p and
                r['statement_type'] in ([statement,'CashFlowDirect'] if statement=='CashFlow' else [statement])]
            for pattern in patterns:
                matches = [r for r in candidates if re.search(pattern, normalized_name(r['item_name'])) and r['value_numeric'] is not None]
                if not matches:
                    continue
                # Never add direct and indirect cash flows or choose conflicting duplicate rows.
                if len({Decimal(str(r['value_numeric'])) for r in matches}) != 1:
                    warnings.append(f'{LABELS[key]} {p[0]}Q{p[1]}: ánh xạ không duy nhất, chưa sử dụng.')
                    break
                row = matches[0]
                source = SourceReference(source_name='CafeF', url=row['source'], retrieved_at=row['retrieved_at'],
                    locator=f"{row['statement_type']} {p[0]}Q{p[1]}, dòng {row['row_order']}: {row['item_name']}")
                multiplier = review.money_multiplier if review else Decimal(1)
                series[key][p] = Fact(Decimal(str(row['value_numeric'])) * multiplier, source, row['item_name'])
                break
    if not review:
        warnings.extend(['Đơn vị tiền tệ, hợp nhất/riêng và cơ sở quý/lũy kế CafeF chưa được kiểm chứng với BCTC gốc.',
            'Chỉ trình bày dữ liệu gốc và tỷ lệ trong cùng bảng; ROE/ROA TTM, định giá và khuyến nghị mua/bán bị chặn.'])
    if len(periods) < 8:
        warnings.append(f'Chỉ có {len(periods)}/8 kỳ đã công bố trong cửa sổ dữ liệu.')
    audit_statuses = {(r['fiscal_year'],r['fiscal_quarter']):r for r in audit_rows
                     if (r['fiscal_year'],r['fiscal_quarter']) in periods}
    data=FinancialData(symbol, periods, series, review, warnings, audit_statuses,
        tuple(r for r in rows if (r['fiscal_year'],r['fiscal_quarter']) in periods))
    validate_balance(data)
    return data


def validate_balance(data):
    """Reject cross-row ratios when the mapped balance sheet is contradictory."""
    for p in data.periods:
        assets,equity,liabilities=(data.value(k,p) for k in ('assets','equity','liabilities'))
        invalid=assets is not None and equity is not None and assets>0 and equity>assets*Decimal('1.005')
        if assets is not None and liabilities is not None and equity is not None and assets>0:
            invalid=invalid or abs(assets-liabilities-equity)>assets*Decimal('0.005')
        if invalid:
            data.invalid_balance_periods.add(p)
            message=f'{p[0]}Q{p[1]}: bảng cân đối ánh xạ không khớp tài sản = nợ + vốn (dung sai 0,5%); chặn tỷ lệ dùng BS và định giá, cần đối chiếu nguồn gốc.'
            if message not in data.warnings:data.warnings.append(message)


def ratio(numerator, denominator, *, percent=False):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator * (100 if percent else 1)


def financial_metrics(data, profile):
    if not data.periods:
        return []
    p = data.periods[0]
    v = lambda key: data.value(key,p)
    metrics = []

    def add(label, value, unit, formula, keys):
        balance_keys={k for k,(statement,_) in ALIASES.items() if statement=='BSheet'}
        if p in data.invalid_balance_periods and balance_keys.intersection(keys):
            value=None
        sources = tuple(dict.fromkeys(data.fact(k,p).source for k in keys if data.fact(k,p)))
        metrics.append(dict(label=label, value=value, unit=unit, formula=formula, sources=sources))

    add('Biên lợi nhuận sau thuế', ratio(v('net_profit'),v('revenue'),percent=True), '%', 'LNST / doanh thu cùng kỳ x 100', ['net_profit','revenue'])
    if profile == 'banking':
        add('Cho vay / tiền gửi theo BCTC',ratio(v('loans'),v('deposits'),percent=True),'%',
            'Cho vay khách hàng / tiền gửi khách hàng; không phải LDR theo quy định', ['loans','deposits'])
        add('Chi phí / thu nhập hoạt động',ratio(v('operating_cost'),v('revenue'),percent=True),'%',
            'Chi phí hoạt động / tổng thu nhập hoạt động', ['operating_cost','revenue'])
    elif profile == 'securities':
        add('Cho vay / vốn chủ sở hữu',ratio(v('loans'),v('equity')), 'lần',
            'Các khoản cho vay / VCSH; không đồng nhất toàn bộ cho vay với margin', ['loans','equity'])
        add('FVTPL / vốn chủ sở hữu',ratio(v('fvtpl'),v('equity')), 'lần', 'Tài sản FVTPL / VCSH', ['fvtpl','equity'])
        for key in ['brokerage','loan_income','investment_income']:
            add(f'Tỷ trọng {LABELS[key].lower()}',ratio(v(key),v('revenue'),percent=True),'%',
                f'{LABELS[key]} / tổng doanh thu hoạt động', [key,'revenue'])
        add('LN chưa thực hiện / LNTT',ratio(v('unrealized_profit'),v('pretax_profit'),percent=True),'%',
            'Lợi nhuận chưa thực hiện / LNTT cùng kỳ', ['unrealized_profit','pretax_profit'])
    elif profile != 'other_financial':
        add('Hệ số thanh toán hiện hành',ratio(v('current_assets'),v('current_liabilities')),'lần',
            'Tài sản ngắn hạn / nợ ngắn hạn', ['current_assets','current_liabilities'])
        debt = v('short_debt') + v('long_debt') if v('short_debt') is not None and v('long_debt') is not None else None
        add('Vay tài chính / vốn chủ sở hữu',ratio(debt,v('equity')),'lần',
            '(Vay ngắn hạn + vay dài hạn) / VCSH; không dùng tổng nợ phải trả', ['short_debt','long_debt','equity'])
        add('Biên lợi nhuận gộp',ratio(v('gross_profit'),v('revenue'),percent=True),'%',
            'LN gộp / doanh thu thuần', ['gross_profit','revenue'])
        if profile == 'real_estate':
            add('Tồn kho / tổng tài sản',ratio(v('inventory'),v('assets'),percent=True),'%',
                'Hàng tồn kho / tổng tài sản; cần thuyết minh dự án', ['inventory','assets'])
    beginning = quarter_from_number(quarter_number(p)-4)
    for key, label in [('equity','ROE TTM'),('assets','ROA TTM')]:
        start, end = data.value(key,beginning), v(key)
        average = (start+end)/2 if start is not None and end is not None else None
        profit = data.ttm('net_profit',p)
        add(label,ratio(profit,average,percent=True),'%', 'LNST 4 quý liên tiếp / bình quân đầu-cuối 12 tháng', ['net_profit',key])
        if data.review:
            metrics[-1]['sources'] = tuple(dict.fromkeys([data.review.source, *[f.source for k in ['net_profit',key] for f in data.series[k].values()]]))
    if data.review and profile not in ('banking','securities','other_financial'):
        add('CFO / LNST cùng quý',ratio(data.quarter_value('cfo',p),data.quarter_value('net_profit',p)),'lần',
            'CFO quý riêng / LNST quý riêng sau chuyển YTD', ['cfo','net_profit'])
    return metrics


def load_review(path):
    return FinancialReview.model_validate_json(Path(path).read_text(encoding='utf-8-sig')) if path else None

"""Explicit scenarios; no target price without verified share and currency inputs."""

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Scenario(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Literal['bear','base','bull']
    multiple: Decimal = Field(gt=0, allow_inf_nan=False)
    growth: Decimal = Field(default=0, gt=-1, allow_inf_nan=False)
    forecast_shares: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    rationale: str = Field(min_length=8)


class Scenarios(BaseModel):
    model_config = ConfigDict(extra='forbid')
    method: Literal['pb','pe']
    horizon_months: int = Field(ge=1, le=60)
    cases: tuple[Scenario, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def check_cases(self):
        if {c.name for c in self.cases} != {'bear','base','bull'}:
            raise ValueError('Cần ba kịch bản bear/base/bull duy nhất')
        return self


def load_scenarios(path):
    return Scenarios.model_validate_json(Path(path).read_text(encoding='utf-8-sig')) if path else None


def evaluate_scenarios(data, profile, close, scenarios):
    review = data.review
    if data.periods and data.periods[0] in data.invalid_balance_periods:
        return dict(rows=[],assessment='Chưa đủ cơ sở khuyến nghị',reason='Bảng cân đối ánh xạ không khớp; cần đối chiếu dữ liệu nguồn trước định giá.')
    if not scenarios:
        return dict(rows=[],assessment='Chưa đủ cơ sở khuyến nghị',reason='Chưa có giả định định giá được nhập cho ba kịch bản.')
    if not review or not review.price_multiplier or close is None:
        return dict(rows=[],assessment='Chưa đủ cơ sở khuyến nghị',reason='Cần kiểm chứng đơn vị tài chính, kỳ/scope và đơn vị giá DNSE.')
    financial = profile in ('banking','securities','other_financial')
    if financial and scenarios.method != 'pb':
        raise ValueError('Profile tài chính dùng kịch bản P/B trong phiên bản này')
    if scenarios.method == 'pb' and (not review.parent_equity_vnd or not review.shares_outstanding):
        return dict(rows=[],assessment='Chưa đủ cơ sở khuyến nghị',reason='P/B cần VCSH thuộc cổ đông công ty mẹ (VND) và số cổ phiếu có nguồn.')
    if scenarios.method == 'pe' and (review.eps_ttm_vnd is None or review.eps_ttm_vnd <= 0):
        return dict(rows=[],assessment='Chưa đủ cơ sở khuyến nghị',reason='P/E cần EPS TTM dương đã kiểm chứng, phù hợp chu kỳ/mô hình.')
    current = Decimal(str(close)) * review.price_multiplier
    if current <= 0:
        raise ValueError('Giá tham chiếu phải dương')
    rows = []
    for case in sorted(scenarios.cases,key=lambda c: ['bear','base','bull'].index(c.name)):
        if scenarios.method == 'pb':
            shares = case.forecast_shares or review.shares_outstanding
            base = review.parent_equity_vnd * (1+case.growth) / shares
        else:
            if case.forecast_shares:
                raise ValueError('P/E cần EPS đã điều chỉnh pha loãng; không nhận forecast_shares riêng')
            base = review.eps_ttm_vnd * (1+case.growth)
        target = base * case.multiple
        upside = (target/current-1)*100
        rows.append(dict(name=case.name,target=target,upside=upside,rationale=case.rationale,
            multiple=case.multiple,growth=case.growth))
    base = next(r for r in rows if r['name']=='base')
    if not review.notes_reviewed:
        assessment='Theo dõi - cần kiểm chứng thuyết minh'
    elif base['upside'] >= 15:
        assessment='Tích cực theo kịch bản cơ sở'
    elif base['upside'] <= -15:
        assessment='Thận trọng theo kịch bản cơ sở'
    else:
        assessment='Trung lập theo kịch bản cơ sở'
    return dict(rows=rows,assessment=assessment,current=current,
        reason='Phân loại v1: tăng/giảm giá kịch bản cơ sở >=15% / <=-15%; đây là quy tắc theo giả định, chưa gán xác suất hay bảo đảm lợi nhuận.')

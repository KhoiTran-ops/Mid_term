"""Explicit valuation; never invent flows, weights, rates or probabilities."""

from decimal import Decimal
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from stock_reports.domain.research import SourceReference

VALUATION_VERSION = 'valuation-2.3'
Method = Literal['pb','pe','justified_pb','fcff','fcfe','nav']


class ValuationModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Projection(ValuationModel):
    year: int = Field(ge=1900,le=2100)
    discount_years: Decimal | None = Field(default=None,gt=0,allow_inf_nan=False)
    fcff_vnd: Decimal | None = Field(default=None,allow_inf_nan=False)
    fcfe_vnd: Decimal | None = Field(default=None,allow_inf_nan=False)
    revenue_vnd: Decimal | None = Field(default=None,allow_inf_nan=False)
    net_profit_vnd: Decimal | None = Field(default=None,allow_inf_nan=False)
    eps_vnd: Decimal | None = Field(default=None,allow_inf_nan=False)
    bvps_vnd: Decimal | None = Field(default=None,gt=0,allow_inf_nan=False)
    roe: Decimal | None = Field(default=None,allow_inf_nan=False)
    source: SourceReference | None = None
    rationale: str = Field(min_length=8)


class NavAsset(ValuationModel):
    name: str = Field(min_length=1)
    value_vnd: Decimal = Field(allow_inf_nan=False)
    ownership: Decimal = Field(gt=0,le=1,allow_inf_nan=False)
    source: SourceReference | None = None
    rationale: str = Field(min_length=8)


class MethodInputs(ValuationModel):
    multiple: Decimal | None = Field(default=None,gt=0,allow_inf_nan=False)
    growth: Decimal | None = Field(default=None,gt=-1,allow_inf_nan=False)
    forecast_shares: Decimal | None = Field(default=None,gt=0,allow_inf_nan=False)
    risk_free_rate: Decimal | None = Field(default=None,ge=0,allow_inf_nan=False)
    market_risk_premium: Decimal | None = Field(default=None,ge=0,allow_inf_nan=False)
    beta: Decimal | None = Field(default=None,ge=0,allow_inf_nan=False)
    ke: Decimal | None = Field(default=None,gt=0,allow_inf_nan=False)
    wacc: Decimal | None = Field(default=None,gt=0,allow_inf_nan=False)
    terminal_growth: Decimal | None = Field(default=None,gt=-1,allow_inf_nan=False)
    sustainable_roe: Decimal | None = Field(default=None,allow_inf_nan=False)
    forecast_bvps_vnd: Decimal | None = Field(default=None,gt=0,allow_inf_nan=False)
    cash_vnd: Decimal | None = Field(default=None,ge=0,allow_inf_nan=False)
    debt_vnd: Decimal | None = Field(default=None,ge=0,allow_inf_nan=False)
    nav_liabilities_vnd: Decimal | None = Field(default=None,ge=0,allow_inf_nan=False)
    projections: tuple[Projection,...] = ()
    nav_assets: tuple[NavAsset,...] = ()
    source: SourceReference | None = None
    rationale: str = Field(min_length=8)

    @model_validator(mode='after')
    def chronological_projection(self):
        years=[p.year for p in self.projections]
        if years and (years!=sorted(set(years)) or any(b-a!=1 for a,b in zip(years,years[1:]))):
            raise ValueError('Dự phóng cần các năm liên tiếp, tăng dần, không trùng')
        times=[p.discount_years for p in self.projections]
        if times and all(t is not None for t in times) and times!=sorted(set(times)):
            raise ValueError('Thời điểm chiết khấu cần tăng dần, không trùng')
        if len({a.name for a in self.nav_assets})!=len(self.nav_assets):
            raise ValueError('Danh mục NAV không được lặp tên tài sản/dự án')
        return self


class WeightedMethod(MethodInputs):
    method: Method
    weight: Decimal = Field(gt=0,le=1,allow_inf_nan=False)


class Scenario(MethodInputs):
    name: Literal['bear','base','bull']
    probability: Decimal | None = Field(default=None,ge=0,le=1,allow_inf_nan=False)
    probability_rationale: str | None = None
    components: tuple[WeightedMethod,...] = ()

    @model_validator(mode='after')
    def explicit_weights_and_probability(self):
        if self.components:
            if len({m.method for m in self.components})!=len(self.components):
                raise ValueError('Không lặp phương pháp trong bảng trọng số')
            if sum((m.weight for m in self.components),Decimal(0))!=1:
                raise ValueError('Trọng số phương pháp phải cộng đúng 100%')
        if self.probability is not None and not self.probability_rationale:
            raise ValueError('Xác suất cần căn cứ riêng; không tự gán')
        return self


class Sensitivity(ValuationModel):
    row_variable: Literal['roe','wacc']
    row_values: tuple[Decimal,Decimal,Decimal]
    column_variable: Literal['ke','g']
    column_values: tuple[Decimal,Decimal,Decimal]
    rationale: str = Field(min_length=8)

    @model_validator(mode='after')
    def valid_axes(self):
        if (self.row_variable,self.column_variable) not in (('roe','ke'),('wacc','g')):
            raise ValueError('Độ nhạy dùng ROE × Ke hoặc WACC × g')
        for axis in (self.row_values,self.column_values):
            if any(not v.is_finite() for v in axis) or list(axis)!=sorted(set(axis)):
                raise ValueError('Trục độ nhạy cần ba giá trị hữu hạn tăng dần')
        return self


class Scenarios(ValuationModel):
    method: Literal['pb','pe','justified_pb','fcff','fcfe','nav','blended']
    horizon_months: int = Field(ge=1,le=60)
    cases: tuple[Scenario,...] = Field(min_length=3,max_length=3)
    sensitivity: Sensitivity | None = None

    @model_validator(mode='after')
    def check_cases(self):
        if {c.name for c in self.cases}!={'bear','base','bull'}:
            raise ValueError('Cần ba kịch bản bear/base/bull duy nhất')
        if any(bool(c.components)!=(self.method=='blended') for c in self.cases):
            raise ValueError('Blended cần thành phần và trọng số cho từng kịch bản')
        probabilities=[c.probability for c in self.cases]
        if any(v is not None for v in probabilities) and (
            any(v is None for v in probabilities) or sum(probabilities)!=1):
            raise ValueError('Xác suất cần đủ ba kịch bản và cộng đúng 100%')
        return self


def load_scenarios(path):
    return Scenarios.model_validate_json(Path(path).read_text(encoding='utf-8-sig')) if path else None


def cost_of_equity(case):
    calculated=(case.risk_free_rate+case.beta*case.market_risk_premium
        if all(v is not None for v in (case.risk_free_rate,case.beta,case.market_risk_premium)) else None)
    if case.ke is not None and calculated is not None and abs(case.ke-calculated)>Decimal('0.000001'):
        raise ValueError('Ke nhập không khớp công thức CAPM từ giả định đã cung cấp')
    return case.ke if case.ke is not None else calculated


def calculate_method(method,case,review):
    """Verified VND; rates in decimal fractions. Zero must be explicitly supplied."""
    shares=case.forecast_shares if case.forecast_shares is not None else review.shares_outstanding
    detail=dict(method=method,weight=getattr(case,'weight',Decimal(1)),rationale=case.rationale,
        source=case.source,projection=case.projections)
    ke=cost_of_equity(case)
    if method in ('pb','pe'):
        if case.multiple is None or case.growth is None:
            raise ValueError('P/B hoặc P/E cần bội số và tăng trưởng được nhập rõ, không mặc định 0')
        if method=='pb':
            if review.parent_equity_vnd is None or review.parent_equity_vnd<=0 or shares is None:
                raise ValueError('P/B cần VCSH thuộc cổ đông công ty mẹ (VND) và số cổ phiếu có nguồn')
            basis=review.parent_equity_vnd*(1+case.growth)/shares
        else:
            if review.eps_ttm_vnd is None or review.eps_ttm_vnd<=0:
                raise ValueError('P/E cần EPS TTM dương đã kiểm chứng')
            if case.forecast_shares is not None:
                raise ValueError('P/E cần EPS đã điều chỉnh pha loãng; không nhận forecast_shares riêng')
            basis=review.eps_ttm_vnd*(1+case.growth)
        target=basis*case.multiple
        detail.update(basis=basis,multiple=case.multiple,growth=case.growth)
    elif method=='justified_pb':
        roe,g,bvps=case.sustainable_roe,case.terminal_growth,case.forecast_bvps_vnd
        if any(v is None for v in (roe,g,bvps,ke)):
            raise ValueError('P/B hợp lý cần ROE bền vững, Ke, g và BVPS dự phóng có căn cứ')
        if ke<=g or roe<=g:
            raise ValueError('P/B hợp lý cần Ke > g và ROE > g để có giá trị dương')
        multiple=(roe-g)/(ke-g);target=bvps*multiple
        detail.update(basis=bvps,multiple=multiple,roe=roe,ke=ke,g=g)
    elif method in ('fcff','fcfe'):
        rate=case.wacc if method=='fcff' else ke
        g=case.terminal_growth
        flows=[getattr(p,method+'_vnd') for p in case.projections]
        times=[p.discount_years for p in case.projections]
        if rate is None or g is None or not flows or any(v is None for v in flows) or shares is None:
            raise ValueError('DCF cần đủ dòng tiền từng năm, suất chiết khấu, g và số cổ phiếu')
        if any(t is None for t in times):
            raise ValueError('DCF cần thời điểm chiết khấu từng dòng tiền, không tự đặt cuối năm')
        if rate<=g:raise ValueError('DCF cần suất chiết khấu lớn hơn g')
        if flows[-1]<=0:raise ValueError('Dòng tiền năm cuối phải dương để dùng tăng trưởng vĩnh viễn')
        pv=sum((v/(1+rate)**t for v,t in zip(flows,times)),Decimal(0))
        terminal=flows[-1]*(1+g)/(rate-g)
        terminal_pv=terminal/(1+rate)**times[-1]
        equity=pv+terminal_pv
        if method=='fcff':
            if case.cash_vnd is None or case.debt_vnd is None:
                raise ValueError('FCFF cần nhập rõ tiền/đầu tư tài chính và nợ vay, kể cả khi bằng 0')
            equity+=case.cash_vnd-case.debt_vnd
        target=equity/shares
        detail.update(pv=pv,terminal=terminal,terminal_pv=terminal_pv,equity=equity,
            shares=shares,discount_rate=rate,g=g,cash=case.cash_vnd,debt=case.debt_vnd)
    else:
        if not case.nav_assets or case.nav_liabilities_vnd is None or shares is None:
            raise ValueError('NAV cần danh mục tài sản, tỷ lệ sở hữu, nghĩa vụ nợ và số cổ phiếu')
        equity=sum((a.value_vnd*a.ownership for a in case.nav_assets),Decimal(0))-case.nav_liabilities_vnd
        target=equity/shares
        detail.update(equity=equity,shares=shares,liabilities=case.nav_liabilities_vnd,assets=case.nav_assets)
    if target<=0:raise ValueError('Giá trị vốn chủ sở hữu/giá hàm ý không dương; không phát hành giá mục tiêu')
    detail['target']=target
    return detail


def evaluate_scenarios(data,profile,close,scenarios, *, quote=None):
    review=data.review;current=None;metrics=[]
    financial=profile in ('banking','securities','other_financial')
    balance_invalid=bool(data.periods and data.periods[0] in data.invalid_balance_periods)
    book_value=None
    if review and review.parent_equity_vnd is not None and review.parent_equity_vnd>0 and review.shares_outstanding and not balance_invalid:
        book_value=review.parent_equity_vnd/review.shares_outstanding
        metrics.append(dict(label='BVPS hiện tại',value=book_value,unit='VND/cp',formula='VCSH công ty mẹ / số cổ phiếu'))
    if review and not balance_invalid and review.eps_ttm_vnd is not None and review.eps_ttm_vnd>0:
        metrics.append(dict(label='EPS TTM',value=review.eps_ttm_vnd,unit='VND/cp',formula='EPS TTM trong hồ sơ kiểm chứng'))
    if quote or review and review.price_multiplier is not None and close is not None:
        current=quote['value_vnd'] if quote else Decimal(str(close))*review.price_multiplier
        if not current.is_finite() or current<=0:raise ValueError('Giá tham chiếu phải dương và hữu hạn')
        metrics.append(dict(label='Giá tham chiếu chuẩn hóa',value=current,unit='VND',
            formula='Giá CafeF có thời điểm nguồn và nhãn đơn vị nghìn VND × 1000' if quote else 'Giá đóng cửa × hệ số đơn vị giá đã kiểm chứng'))
        if book_value is not None:
            metrics.append(dict(label='P/B hiện tại',value=current/book_value,unit='lần',formula='Giá chuẩn hóa / BVPS'))
        if review and not balance_invalid and review.eps_ttm_vnd is not None and review.eps_ttm_vnd>0:
            metrics.append(dict(label='P/E hiện tại',value=current/review.eps_ttm_vnd,unit='lần',formula='Giá chuẩn hóa / EPS TTM'))

    def blocked(reason):
        return dict(rows=[],metrics=metrics,current=current,assessment='Chưa đủ cơ sở khuyến nghị',
            reason=reason,methods=[],sensitivity=[],checks=[],target=None,upside=None,version=VALUATION_VERSION)
    if balance_invalid:return blocked('Bảng cân đối ánh xạ không khớp; cần đối chiếu nguồn trước định giá.')
    if not scenarios:return blocked('Chưa có giả định cho ba kịch bản; không sinh giá mục tiêu hay dự phóng mặc định.')
    if not review or current is None:
        return blocked('Cần kiểm chứng đơn vị tài chính, kỳ/scope, số cổ phiếu và đơn vị giá.')
    methods={m.method for c in scenarios.cases for m in c.components} if scenarios.method=='blended' else {scenarios.method}
    if financial and not methods<= {'pb','justified_pb'}:
        raise ValueError('Profile tài chính dùng P/B; P/E chỉ là đối chiếu, không dùng FCFF/FCFE của sản xuất')
    rows=[]
    try:
        for case in sorted(scenarios.cases,key=lambda c:['bear','base','bull'].index(c.name)):
            details=[calculate_method(m.method,m,review) for m in case.components] if scenarios.method=='blended' else [calculate_method(scenarios.method,case,review)]
            target=sum((d['target']*d['weight'] for d in details),Decimal(0))
            rows.append(dict(name=case.name,target=target,upside=(target/current-1)*100,
                rationale=case.rationale,multiple=case.multiple,growth=case.growth,details=details,
                probability=case.probability,probability_rationale=case.probability_rationale,source=case.source))
    except ValueError as error:return blocked(str(error))
    base=rows[1];ordered=rows[0]['target']<=base['target']<=rows[2]['target']
    downside=rows[0]['target']<current
    reverse=[];current_pb=next((m['value'] for m in metrics if m['label']=='P/B hiện tại'),None)
    for detail in base['details']:
        if detail['method']=='justified_pb' and current_pb is not None:
            detail['implied_roe']=detail['g']+current_pb*(detail['ke']-detail['g'])
            detail['target_implied_roe']=detail['g']+detail['multiple']*(detail['ke']-detail['g'])
            reverse.append(abs(detail['target_implied_roe']-detail['roe'])<Decimal('0.000001'))
    coherent=profile!='banking' or ('pb' not in methods and bool(reverse) and all(reverse))
    checks=[dict(label='Đơn vị tiền, cổ phiếu và phạm vi BCTC',passed=bool(review.shares_outstanding)),
        dict(label='Thuyết minh đã đối chiếu',passed=review.notes_reviewed),
        dict(label='Thời hạn mục tiêu 12 tháng',passed=scenarios.horizon_months==12),
        dict(label='Bi quan ≤ cơ sở ≤ lạc quan',passed=ordered),
        dict(label='Có kịch bản dưới giá hiện tại',passed=downside),
        dict(label='P/B ngân hàng khớp ROE và kiểm tra đảo ngược',passed=coherent)]
    publishable=all(c['passed'] for c in checks)
    if publishable:
        assessment='KHẢ QUAN' if base['upside']>=15 else 'KÉM KHẢ QUAN' if base['upside']<=-10 else 'TRUNG LẬP'
        reason='Ngưỡng: ≥ +15% Khả quan; ≤ -10% Kém khả quan; giữa hai ngưỡng Trung lập. Không gán xác suất nếu thiếu căn cứ.'
    else:
        assessment='Chưa đủ cơ sở khuyến nghị'
        reason='Chưa đạt kiểm tra phát hành: '+'; '.join(c['label'] for c in checks if not c['passed'])+'.'
    sensitivity=[]
    if scenarios.sensitivity:
        grid=scenarios.sensitivity
        matching=next((d for d in base['details'] if d['method']==('justified_pb' if grid.row_variable=='roe' else 'fcff')),None)
        if matching:
            original=next(m for m in scenarios.cases if m.name=='base')
            if original.components:original=next(m for m in original.components if m.method==matching['method'])
            for r in grid.row_values:
                values=[]
                for col in grid.column_values:
                    patch=({'sustainable_roe':r,'ke':col,'risk_free_rate':None,'market_risk_premium':None,'beta':None}
                        if grid.row_variable=='roe' else {'wacc':r,'terminal_growth':col})
                    try:values.append(calculate_method(matching['method'],original.model_copy(update=patch),review)['target'])
                    except ValueError:values.append(None)
                sensitivity.append(dict(row=r,values=values))
    return dict(rows=rows,metrics=metrics,current=current,assessment=assessment,reason=reason,
        methods=base['details'],sensitivity=sensitivity,checks=checks,
        target=base['target'] if publishable else None,upside=base['upside'] if publishable else None,version=VALUATION_VERSION)

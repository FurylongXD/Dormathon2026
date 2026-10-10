from dataclasses import dataclass, asdict, replace
from datetime import date
from math import isfinite


class AssessmentError(ValueError):
    """An input cannot be assessed safely; never substitute missing values with zero."""


@dataclass(frozen=True)
class Applicant:
    demo_id: str
    age: int
    citizenship: str
    gross_income: float
    net_income: float
    existing_loan_payment: float
    loan_balance: float
    card_payment: float
    card_balance: float
    card_limit: float
    card_annual_rate: float
    living_expenses: float
    cash_savings: float
    income_variability: float
    variable_income_fraction: float
    months_in_job: int
    contract_months_remaining: int
    epf_balance: float
    epf_regular_months: int
    arrears_max_months: int
    late_payments_12m: int
    housing_loans_count: int
    mock_reported_ctos_score: int
    legal_flags: int
    loan_settlement_fee: float
    document_verified: bool = False

    def validate(self):
        if not self.demo_id.startswith("DEMO") or not self.demo_id[4:].isdigit():
            raise AssessmentError("Only anonymous DEMO identifiers are accepted.")
        if self.citizenship not in {"MY", "OTHER"} or not 18 <= self.age <= 75:
            raise AssessmentError("Unsupported age or citizenship value.")
        for key, value in asdict(self).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if not isfinite(value) or value < 0:
                    raise AssessmentError(f"Invalid {key}: must be finite and non-negative.")
        if self.net_income <= 0 or self.gross_income < self.net_income or self.card_limit <= 0:
            raise AssessmentError("Invalid income or credit limit.")
        if not 300 <= self.mock_reported_ctos_score <= 850:
            raise AssessmentError("Mock CTOS field must be between 300 and 850.")
        if self.variable_income_fraction > 1 or self.income_variability > 2:
            raise AssessmentError("Income ratios are out of range.")
        if (self.legal_flags not in {0, 1} or self.epf_regular_months > 12 or self.late_payments_12m > 12
                or self.arrears_max_months > 12 or self.card_annual_rate > .5):
            raise AssessmentError("Credit history or card-rate field is outside the supported schema.")
        return self


@dataclass(frozen=True)
class Quote:
    offer_id: str
    bank_code: str
    product: str
    asset_price: float
    requested_principal: float
    down_payment: float
    annual_rate: float  # Decimal: 0.05 means 5% p.a.; NOT the number 5.
    rate_method: str  # flat, reducing_nominal, reducing_effective
    months: int
    fees: float  # Paid upfront; financed insurance/legal fees are not supported.
    variable_rate: bool
    vehicle_age: int
    quote_date: str
    purpose: str = "purchase"
    rate_source: str = "uploaded_mock_quotation"

    def validate(self):
        if self.product not in {"car", "home", "personal"}:
            raise AssessmentError("Supported products: car, home, personal.")
        if self.rate_method not in {"flat", "reducing_nominal", "reducing_effective"}:
            raise AssessmentError("Rate basis must be specified explicitly.")
        for key in ("asset_price", "requested_principal", "down_payment", "annual_rate", "fees"):
            value = getattr(self, key)
            if not isfinite(value) or value < 0:
                raise AssessmentError(f"Invalid quote field: {key}.")
        if not 1 <= self.months <= 420 or not 0 <= self.annual_rate <= 0.5:
            raise AssessmentError("Invalid tenor/rate; provide annual rate as a decimal.")
        if self.requested_principal <= self.fees or self.asset_price <= 0 or self.vehicle_age < 0:
            raise AssessmentError("Invalid loan value, fee or vehicle age.")
        if self.product != "personal" and abs(self.asset_price - self.down_payment - self.requested_principal) > 1:
            raise AssessmentError("Asset price must equal principal plus down payment (no financed fees).")
        if self.product == "personal" and self.down_payment != 0:
            raise AssessmentError("Personal loans have no asset down payment.")
        if self.product == "personal" and abs(self.asset_price - self.requested_principal) > .01:
            raise AssessmentError("Personal-loan amount and comparison amount must agree.")
        date.fromisoformat(self.quote_date)
        return self


def changed(obj, **kwargs):
    """Construct immutable counterfactuals without mutating an applicant's documents."""
    return replace(obj, **kwargs)


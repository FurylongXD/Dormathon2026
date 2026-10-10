"""Cash-flow calculations. These are deterministic estimates, not ML predictions."""
from .schema import Quote, Applicant


def monthly_rate(q: Quote) -> float:
    if q.rate_method == "reducing_effective":
        return (1 + q.annual_rate) ** (1 / 12) - 1
    return q.annual_rate / 12


def instalment(q: Quote, principal=None, annual_rate=None) -> float:
    from dataclasses import replace
    q = replace(q, annual_rate=annual_rate) if annual_rate is not None else q
    p = q.requested_principal if principal is None else principal
    if q.rate_method == "flat":
        return p * (1 + q.annual_rate * q.months / 12) / q.months
    r = monthly_rate(q)
    return p / q.months if r == 0 else p * r / (1 - (1 + r) ** (-q.months))


def effective_rate(q: Quote) -> float:
    """Annual compounded IRR with upfront fees and end-of-month repayments."""
    proceeds = q.requested_principal - q.fees
    payment = instalment(q)
    lo, hi = 0.0, 10.0
    for _ in range(100):
        r = (lo + hi) / 2
        pv = payment * (1 - (1 + r) ** (-q.months)) / r if r else payment * q.months
        if pv > proceeds:
            lo = r
        else:
            hi = r
    return (1 + (lo + hi) / 2) ** 12 - 1


def calculations(a: Applicant, q: Quote, cap_principal: float, dsr_assumption=0.60) -> dict:
    payment = instalment(q)
    debt = a.existing_loan_payment + a.card_payment
    capacity = max(0.0, min(dsr_assumption * a.net_income - debt,
                            a.net_income - debt - a.living_expenses))
    affordable_principal = capacity / instalment(q, principal=1.0)
    ceiling = max(0.0, min(cap_principal, affordable_principal))
    out = {
        "monthly_instalment_rm": payment,
        "existing_monthly_debt_rm": debt,
        "calculated_dsr": (debt + payment) / a.net_income,
        "net_disposable_income_rm": a.net_income - debt - payment,
        "surplus_after_living_expenses_rm": a.net_income - debt - payment - a.living_expenses,
        "credit_card_utilization_ratio": a.card_balance / a.card_limit,
        "ltv_ratio": q.requested_principal / q.asset_price if q.product != "personal" else None,
        "annual_effective_cashflow_rate": effective_rate(q),
        "total_instalments_rm": payment * q.months,
        "total_financing_cost_rm": payment * q.months - q.requested_principal + q.fees,
        "total_cash_outlay_rm": payment * q.months + q.fees + q.down_payment,
        "product_or_planning_principal_ceiling_rm": cap_principal,
        "affordability_principal_ceiling_rm": affordable_principal,
        "illustrative_financing_ceiling_rm": ceiling,
        "minimum_asset_cash_rm": max(0.0, q.asset_price - ceiling) if q.product != "personal" else 0.0,
        "available_upfront_cash_rm": a.cash_savings,
        "upfront_cash_needed_rm": q.down_payment + q.fees,
        "upfront_cash_gap_rm": max(0.0, q.down_payment + q.fees - a.cash_savings),
        "cash_after_deposit_and_fees_rm": a.cash_savings - q.down_payment - q.fees,
        "requested_bank_financing_rm": q.requested_principal,
        "quoted_asset_price_rm": q.asset_price if q.product != "personal" else None,
        "quoted_down_payment_rm": q.down_payment,
        "dsr_threshold_assumption": dsr_assumption,
        "planning_assumptions": "60% net-income DSR and observed living expenses; no extra contingency margin included. Not a bank-specific rule.",
        "ceiling_is_not_bank_approved_amount": True,
    }
    if q.variable_rate:
        stress_payment = instalment(q, annual_rate=q.annual_rate + 0.02)
        out["rate_stress_plus_2pp"] = {"monthly_instalment_rm": stress_payment,
                                      "dsr": (debt + stress_payment) / a.net_income,
                                      "assumption": "Illustrative +2 percentage point rate stress; not a BNM limit."}
    return out


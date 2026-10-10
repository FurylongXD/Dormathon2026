from .finance import instalment

FEATURES = ["age", "net_income", "gross_income", "calculated_dsr", "ltv_ratio",
            "surplus_ratio", "credit_utilization", "income_variability", "variable_income_fraction",
            "months_in_job", "contract_months_remaining", "epf_regular_months", "epf_to_income",
            "arrears_max_months", "late_payments_12m", "mock_ctos_score", "legal_flags",
            "cash_buffer_months_after_deposit", "tenure_years", "rate", "is_car", "is_home", "is_personal"]


def engineer(a, q):
    a.validate()
    q.validate()
    payment = instalment(q)
    debt = a.existing_loan_payment + a.card_payment
    return dict(zip(FEATURES, [
        a.age, a.net_income, a.gross_income, (debt + payment) / a.net_income,
        q.requested_principal / q.asset_price if q.product != "personal" else 0,
        (a.net_income - debt - payment - a.living_expenses) / a.net_income,
        a.card_balance / a.card_limit, a.income_variability, a.variable_income_fraction,
        a.months_in_job, min(a.contract_months_remaining, 120), a.epf_regular_months,
        min(a.epf_balance / a.net_income, 100), a.arrears_max_months, a.late_payments_12m,
        a.mock_reported_ctos_score, a.legal_flags,
        max(-12, min(36, (a.cash_savings - q.down_payment - q.fees) / max(1, a.living_expenses + debt + payment))),
        q.months / 12, q.annual_rate, int(q.product == "car"), int(q.product == "home"), int(q.product == "personal")
    ]))

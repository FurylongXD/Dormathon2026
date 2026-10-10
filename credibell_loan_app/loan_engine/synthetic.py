"""Transparent simulator: labels are sampled, never presented as Malaysian bank outcomes."""
import numpy as np
from .schema import Applicant, Quote
from .features import engineer


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -35, 35)))


def sample_profile(rng, index, product=None):
    product = product or rng.choice(["car", "home", "personal"])
    gross = round(float(np.clip(rng.lognormal(8.65, .55), 1500, 30000)), 2)
    net = round(gross * float(rng.uniform(.72, .89)), 2)
    limit = float(rng.choice([3000, 5000, 10000, 20000, 35000]))
    balance = round(limit * float(rng.uniform(0, 1.15)), 2)
    card_payment = round(max(50, balance * .05), 2) if balance else 0
    # 5% minimum-payment assumption applies ONLY to generated mock statements.
    loan_payment = round(net * float(rng.uniform(0, .42)), 2)
    loan_balance = round(loan_payment * float(rng.integers(12, 85)) * .85, 2)
    months_in_job = int(rng.integers(1, 181))
    a = Applicant(
        demo_id=f"DEMO{index:05d}", age=int(rng.integers(18, 71)), citizenship="MY",
        gross_income=gross, net_income=net, existing_loan_payment=loan_payment,
        loan_balance=loan_balance, card_payment=card_payment, card_balance=balance,
        card_limit=limit, card_annual_rate=.18,
        living_expenses=round(net * float(rng.uniform(.20, .55)), 2),
        cash_savings=round(net * float(rng.uniform(.2, 30)), 2),
        income_variability=float(rng.uniform(0, .55)),
        variable_income_fraction=float(rng.uniform(0, .8)), months_in_job=months_in_job,
        contract_months_remaining=int(rng.choice([6, 12, 24, 999])),
        epf_balance=round(gross * float(rng.uniform(0, 48)), 2),
        epf_regular_months=int(rng.integers(0, 13)),
        arrears_max_months=int(rng.choice([0, 1, 2, 3], p=[.76, .13, .07, .04])),
        late_payments_12m=int(rng.choice([0, 1, 2, 4, 6], p=[.61, .17, .12, .07, .03])),
        housing_loans_count=int(rng.choice([0, 1, 2], p=[.72, .22, .06])),
        mock_reported_ctos_score=int(rng.integers(350, 841)),
        legal_flags=int(rng.random() < .04), loan_settlement_fee=50,
    )
    if product == "car":
        asset = round(float(rng.uniform(25000, 180000)), 2)
        ltv = float(rng.uniform(.45, .95))
        principal = round(asset * ltv, 2)
        bank, rate, months = "PUBLIC_BANK_CAR", float(rng.uniform(.035, .09)), int(rng.choice([36, 60, 84, 108]))
    elif product == "home":
        asset = round(float(rng.uniform(180000, 950000)), 2)
        principal = round(asset * float(rng.uniform(.50, .95)), 2)
        bank, rate, months = "CIMB_HOME", float(rng.uniform(.025, .065)), int(rng.choice([120, 180, 240, 300, 360, 420]))
    else:
        principal = round(float(rng.uniform(5000, 100000)), 2)
        asset = principal
        bank, rate, months = "MAYBANK_PERSONAL", float(rng.uniform(.045, .12)), int(rng.choice([24, 36, 48, 60, 72]))
    q = Quote("SIMULATED", bank, product, asset, principal,
              round(asset - principal, 2) if product != "personal" else 0,
              rate, "reducing_nominal", months, 0, product == "home", 0, "2026-10-10")
    return a, q


def generate_training_data(n=16000, seed=20261010):
    rng = np.random.default_rng(seed)
    rows, approval, arrears, health = [], [], [], []
    for i in range(n):
        a, q = sample_profile(rng, i)
        f = engineer(a, q)
        # Deliberately disclosed synthetic mechanics. No bank identities or secret rules.
        risk_logit = (-3.6 + 3.2 * (f["calculated_dsr"] - .45)
                      + 1.3 * f["credit_utilization"] + .85 * a.arrears_max_months
                      + .12 * a.late_payments_12m + 1.5 * a.income_variability
                      + .65 * int(a.months_in_job < 6) + .65 * a.legal_flags
                      + 1.25 * max(0, -f["surplus_ratio"])
                      + (650 - a.mock_reported_ctos_score) / 260
                      - .04 * min(12, max(0, f["cash_buffer_months_after_deposit"])))
        pd = float(sigmoid(risk_logit))
        approved_probability = float(sigmoid(2.5 - 4.2 * (f["calculated_dsr"] - .4)
                            - 1.1 * f["credit_utilization"] - .95 * a.arrears_max_months
                            - 1.5 * a.income_variability - .6 * int(a.months_in_job < 6)
                            + (a.mock_reported_ctos_score - 650) / 180
                            + 1.1 * f["surplus_ratio"] - .9 * a.legal_flags
                            - 2.0 * max(0, f["ltv_ratio"] - .85)))
        next_arrears = int(rng.random() < pd)
        score = np.clip(100 * (1 - pd) - 18 * next_arrears
                        - 8 * f["credit_utilization"] + rng.normal(0, 4), 0, 100)
        rows.append(f)
        approval.append(int(rng.random() < approved_probability))
        arrears.append(next_arrears)
        health.append(float(score))
    return rows, np.array(approval), np.array(arrears), np.array(health)


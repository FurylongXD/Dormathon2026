"""Recommendations are based on rerun counterfactuals; no invented SHAP % changes."""
from dataclasses import replace
from .schema import AssessmentError


def categorize(a, financials):
    issues = []
    def add(category, severity, reason):
        issues.append({"category": category, "severity": severity, "reason": reason})
    if financials["calculated_dsr"] > .6:
        add("High debt-service ratio", "high", "DSR exceeds the disclosed 60% demo affordability assumption; the bank's own limit is unknown.")
    if financials["surplus_after_living_expenses_rm"] < 0:
        add("Insufficient disposable income", "high", "Income does not cover recorded living expenses, current commitments and the new instalment.")
    if a.card_balance / a.card_limit > .5:
        add("High revolving-credit utilization", "medium", "More than 50% of the mock card limit is used; 50% is a demo categorization rule.")
    if a.income_variability > .15 or a.variable_income_fraction > .3:
        add("Irregular income", "medium", "Three-month income varies or a substantial share is variable; accepted-income rules differ by bank.")
    if a.months_in_job < 6:
        add("Recent job change", "medium", "Under six months in the role; six months is a demo heuristic, not a universal bank requirement.")
    if a.arrears_max_months > 0 or a.late_payments_12m > 0:
        add("Repayment history concerns", "high", "Mock credit records contain arrears or late payments.")
    if a.legal_flags:
        add("Legal-record review", "high", "A mock legal-record flag requires human review and confirmation; it is not an automatic rejection.")
    if financials["upfront_cash_gap_rm"] > 0:
        add("Deposit shortfall", "high", "Available cash is below the quotation's down payment plus upfront fees.")
    if a.contract_months_remaining < 12:
        add("Employment continuity", "medium", "The mock contract expires within twelve months; renewal prospects are not known.")
    return sorted(issues, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["severity"]])


class RecommendationEngine:
    def __init__(self, assessor):
        self.assessor = assessor

    def alternatives(self, a, q, baseline, as_of):
        candidates = []
        # Keep an explicit cash reserve; EPF retirement savings are NOT spendable cash.
        reserve = 3 * a.living_expenses
        spare = max(0, a.cash_savings - q.down_payment - q.fees - reserve)
        if a.card_balance > 0 and spare >= 100:
            repay = min(a.card_balance, spare, a.card_balance * .5)
            ratio = (a.card_balance - repay) / a.card_balance
            a2 = replace(a, card_balance=a.card_balance - repay, card_payment=a.card_payment * ratio,
                         cash_savings=a.cash_savings - repay)
            candidates.append(("Repay part of the card balance", a2, q, repay,
                "Assumes the next statement minimum due falls proportionally; actual minimum-payment rules and bureau update timing must be confirmed."))
        settle = a.loan_balance + a.loan_settlement_fee
        if a.loan_balance > 0 and spare >= settle:
            candidates.append(("Settle the existing loan", replace(a, loan_balance=0, existing_loan_payment=0,
                              cash_savings=a.cash_savings - settle), q, settle,
                "Assumes the mock outstanding balance plus stated settlement fee is the settlement amount; get an actual settlement quotation. Historical arrears stay unchanged."))
        if q.product != "personal":
            extra = min(spare, .1 * q.asset_price, .5 * q.requested_principal)
            if extra >= 100:
                # Savings are measured before paying the purchase deposit. q2 now
                # contains the larger deposit, so subtracting extra here would count it twice.
                candidates.append(("Increase the down payment", a,
                    replace(q, requested_principal=q.requested_principal - extra, down_payment=q.down_payment + extra), extra,
                    "Requires a revised bank quotation; assumes the same rate and tenor. Cash reserve is retained."))
            cheaper_price = q.asset_price * .85
            if cheaper_price > q.down_payment:
                candidates.append(("Choose an asset costing 15% less", a,
                    replace(q, asset_price=cheaper_price, requested_principal=cheaper_price - q.down_payment), 0,
                    "Illustrative cheaper purchase with the same cash deposit; needs a new asset and bank quotation. Rate and tenor held constant."))
        else:
            candidates.append(("Borrow 20% less", a, replace(q, asset_price=q.asset_price * .8,
                              requested_principal=q.requested_principal * .8), 0,
                              "Requires a new quote; published amount/rate tiers may change. Current rate is held constant for comparison."))
        maximum = baseline["policy"]["max_months"]
        if q.months < maximum:
            candidates.append(("Consider a longer repayment term", a, replace(q, months=min(maximum, q.months + 24)), 0,
                              "Lower instalments can raise total financing cost. Approval is not assured and a revised quote is needed."))
        if a.months_in_job < 7:
            candidates.append(("Reassess after more than six months in the current job", replace(a, months_in_job=7), q, 0,
                              "Conditional simulation: income, debt, cash and credit history remain unchanged. It is not a forecast of future employment or score."))
        output = []
        base_p = baseline["approval_chance"]["generic_synthetic_probability"]
        base_health = baseline["internal_credit_health_score"]["value"]
        for title, a2, q2, cash_cost, assumption in candidates:
            try:
                new = self.assessor(a2, q2, as_of, explain=False)
            except AssessmentError:
                continue
            if (not new["policy"]["assessment_checks_pass"] or new["coverage_warnings"]
                    or new["financials"]["upfront_cash_gap_rm"] > 0):
                continue
            p2 = new["approval_chance"]["generic_synthetic_probability"]
            pd2 = new["credit_risk"]["probability_90day_arrears_next_12m"]
            output.append({"action_id": f"SCENARIO{len(output) + 1}", "action": title, "cash_cost_rm": cash_cost, "assumption": assumption,
                           "requires_new_documents_or_quote": True,
                           "scenario_approval_probability": p2,
                           "approval_change_percentage_points": (p2 - base_p) * 100 if base_p is not None else None,
                           "internal_score_change": new["internal_credit_health_score"]["value"] - base_health if base_health is not None else None,
                           "official_ctos_score_change": None,
                           "scenario_risk_probability": pd2, "scenario_risk_rating": new["credit_risk"]["rating"],
                           "monthly_instalment_rm": new["financials"]["monthly_instalment_rm"],
                           "dsr": new["financials"]["calculated_dsr"],
                           "financing_cost_change_rm": new["financials"]["total_financing_cost_rm"] - baseline["financials"]["total_financing_cost_rm"],
                           "cash_after_deposit_and_fees_rm": a2.cash_savings - q2.down_payment - q2.fees,
                           "emergency_reserve_assumption_rm": reserve})
        output.sort(key=lambda item: (-(item["approval_change_percentage_points"] or 0), item["cash_cost_rm"]))
        return output

    @staticmethod
    def narrative(assessment):
        probability = assessment["approval_chance"]["generic_synthetic_probability"]
        parts = ["This is an assessment of synthetic documents, using a model trained on simulated outcomes."]
        if probability is not None:
            parts.append(f"The generic simulation approval estimate for the requested loan is {probability:.1%}; real-bank odds have not been validated.")
        if not assessment["policy"]["published_rules_pass"]:
            parts.append("The quotation fails these published checks: " + "; ".join(assessment["policy"]["failures"]) + ".")
        if assessment["risk_issues"]:
            parts.append("Review first: " + "; ".join(item["category"] for item in assessment["risk_issues"][:3]) + ".")
        best = next((s for s in assessment.get("alternative_scenarios", [])
                     if s["approval_change_percentage_points"] is not None and s["approval_change_percentage_points"] > 0), None)
        if best:
            parts.append(f"The largest tested improvement is '{best['action']}': {best['approval_change_percentage_points']:.1f} percentage points in the simulation, requiring RM{best['cash_cost_rm']:,.2f} cash. {best['assumption']}")
        parts.append("Pay commitments on time and verify any errors in the source credit report. The system cannot predict a change in an official CTOS score.")
        return " ".join(parts)


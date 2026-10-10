import json
from datetime import date
from pathlib import Path
from .schema import AssessmentError

ROOT = Path(__file__).resolve().parent.parent


class PolicyEngine:
    def __init__(self, path=None):
        self.data = json.loads(Path(path or ROOT / "config/bank_policies.json").read_text(encoding="utf-8"))

    def check(self, a, q, as_of):
        today = date.fromisoformat(as_of)
        if not date.fromisoformat(self.data["verified_on"]) <= today <= date.fromisoformat(self.data["valid_until"]):
            raise AssessmentError("Policy snapshot expired or predates its review. Reverify sources and update the dated policy file.")
        q.validate()
        if date.fromisoformat(q.quote_date) > today or (today - date.fromisoformat(q.quote_date)).days > 30:
            raise AssessmentError("Quotation must be no more than 30 days old and not in the future.")
        p = self.data["products"].get(q.bank_code)
        if p is None or p["product"] != q.product:
            raise AssessmentError(f"Unsupported bank/product: {q.bank_code}. Add verified product rules first.")
        failures, assumptions, unknowns = [], [], ["Internal bank DSR limit, score cutoffs and income acceptance rules are not public here."]
        max_months = p.get("max_months", 108)
        margin = p.get("margin", 1.0)
        if q.bank_code == "PUBLIC_BANK_CAR":
            band = next((b for b in p["age_bands"] if q.vehicle_age <= b[0]), None)
            if band is None:
                assumptions.append("Passenger vehicle age exceeds supported published bands (12 years); bank review required.")
                margin, max_months = 0.0, 0
            else:
                _, margin, max_months = band
        if p.get("used_vehicle_age_policy_unknown") and q.vehicle_age > 0:
            unknowns.append("Maybank used-car age-specific terms require a bank-confirmed quotation.")
        if ((p.get('guarantor_below_age') and a.age<p['guarantor_below_age'])
                or (p.get('guarantor_above_age') and a.age>p['guarantor_above_age'])
                or (p.get('noncitizen_guarantor') and a.citizenship!='MY')):
            assumptions.append('This product requires a guarantor for this applicant category; guarantor details are not available.')
        if q.product == "home":
            max_months = min(max_months, 420, max(0, (p["max_age_at_maturity"] - a.age) * 12))
            unknowns.append("Property valuation, financed fees, required additional income documents and actual asset-only margin need bank confirmation.")
            unknowns.append(p.get("margin_interpretation", ""))
            if a.housing_loans_count >= 2:
                margin = min(margin, 0.70)
        if q.product == "personal":
            max_months = min(max_months, 120)
            if "max_age_at_maturity" in p:
                max_months = min(max_months, max(0, (p["max_age_at_maturity"] - a.age) * 12))
            if today >= date(2027, 1, 1) and q.rate_method == "flat":
                failures.append("New personal-financing flat-rate calculation conflicts with BNM's 2027 effective requirements.")
        if q.bank_code == "MAYBANK_CAR" and today >= date.fromisoformat(p["reducing_balance_from"]) and q.rate_method == "flat":
            failures.append("Maybank car quotes dated after its RBM switch must use reducing balance.")
        if q.product == "home" and q.rate_method == "flat":
            failures.append("This home-financing calculator supports reducing balance quotations only.")
        for key, value, text in [("min_age", a.age, "Age below published minimum"),
                                 ("min_gross_income", a.gross_income, "Gross income below published minimum"),
                                 ("min_principal", q.requested_principal, "Amount below published minimum"),
                                 ("min_months", q.months, "Tenure below published minimum")]:
            if key in p and value < p[key]:
                failures.append(text)
        if a.age > p.get("max_age", 100):
            failures.append("Age exceeds published entry maximum")
        if "citizenship" in p and a.citizenship != p["citizenship"]:
            failures.append("Citizenship does not match published eligibility")
        cap = p.get("max_principal", q.asset_price * margin)
        if q.requested_principal > cap + 0.01:
            failures.append("Requested principal exceeds published/conservative financing ceiling")
        if q.months > max_months:
            failures.append("Requested tenure exceeds published age/product maximum")
        if q.purpose != "purchase":
            raise AssessmentError("Refinancing and property-secured personal use need separate policy rules.")
        if q.variable_rate and q.rate_method == "flat":
            raise AssessmentError("Variable flat-rate quote unsupported; clarify rate basis first.")
        if "min_job_months_exclusive" in p and a.months_in_job <= p["min_job_months_exclusive"]:
            failures.append("Employment history does not exceed the published minimum of six consecutive months")
        # A conservative planning ceiling is never reported as a published bank rule.
        cap_message = "Requested principal exceeds published/conservative financing ceiling"
        if (p.get("margin_is_demo_assumption") and a.housing_loans_count < 2
                and cap_message in failures):
            failures.remove(cap_message)
            assumptions.append("Requested principal exceeds the 90% asset-only demo planning ceiling; confirm the bank's actual margin.")
        return {"published_rules_pass": not failures, "assessment_checks_pass": not failures and not assumptions,
                "failures": failures, "assumption_failures": assumptions, "unknowns": unknowns,
                "bank": p["bank"], "product": q.product, "principal_ceiling_rm": cap,
                "margin_of_finance": margin if q.product != "personal" else None,
                "principal_ceiling_basis": "demo planning assumption" if p.get("margin_is_demo_assumption") and a.housing_loans_count < 2 else "published product/regulatory ceiling",
                "max_months": max_months, "source": p["source"],
                "regulatory_sources": self.data["bnm_sources"],
                "verified_on": self.data["verified_on"],
                "scope": "Partial published policy check; not a lending decision or bank endorsement."}


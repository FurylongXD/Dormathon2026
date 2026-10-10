from pathlib import Path
from .policies import PolicyEngine
from .finance import calculations
from .features import engineer
from .predictors import ModelBundle, RiskRatingModel
from .shap_engine import ShapEngine
from .recommendations import RecommendationEngine, categorize
from .schema import AssessmentError


class LoanAssessmentEngine:
    def __init__(self, model_dir, policy_path=None):
        self.models = ModelBundle(model_dir)
        self.policies = PolicyEngine(policy_path)
        self.shap = ShapEngine(self.models)
        self.recommendations = RecommendationEngine(self.assess_offer)

    def assess_offer(self, applicant, quotation, as_of, explain=True):
        applicant.validate()
        policy = self.policies.check(applicant, quotation, as_of)
        f = engineer(applicant, quotation)
        warnings = self.models.coverage_warnings(f)
        estimates = self.models.predict(f) if not warnings else {"approval": None, "risk": None, "health": None}
        fin = calculations(applicant, quotation, policy["principal_ceiling_rm"])
        risk = RiskRatingModel().assess(estimates["risk"]) if estimates["risk"] is not None else {
            "rating": None, "probability_90day_arrears_next_12m": None, "reason": "Outside synthetic model coverage"}
        # Failing a published eligibility test is not mathematically a zero credit-risk probability.
        out = {
            "offer_id": quotation.offer_id, "bank_code": quotation.bank_code, "bank": policy["bank"],
            "product": quotation.product, "policy": policy, "financials": fin, "coverage_warnings": warnings,
            "approval_chance": {
                "generic_synthetic_probability": estimates["approval"],
                "bank_specific_probability": None,
                "eligible_demo_probability": estimates["approval"] if policy["assessment_checks_pass"] and fin["upfront_cash_gap_rm"] == 0 else None,
                "qualification": "Generic calibrated simulation; no bank-specific approval outcome data. Eligibility and cash constraints are checked separately."
            },
            "credit_risk": risk,
            "internal_credit_health_score": {"value": estimates["health"], "scale": "0-100",
                                             "label": "Expected synthetic 12-month internal credit-health score; not an official bureau score."},
            "reported_mock_ctos_score": applicant.mock_reported_ctos_score,
            "risk_issues": categorize(applicant, fin),
            "shap": self.shap.explain(f) if explain and not warnings else {},
        }
        return out

    def assess(self, applicant, quotes, as_of, document_audit=None):
        if not applicant.document_verified or not document_audit:
            raise AssessmentError("Public assessment requires a complete OCR-verified mock submission and document provenance.")
        if not quotes:
            raise AssessmentError("At least one bank quotation is needed.")
        first = quotes[0]
        if any((q.product, q.asset_price, q.requested_principal, q.down_payment) !=
               (first.product, first.asset_price, first.requested_principal, first.down_payment) for q in quotes):
            raise AssessmentError("Bank ranking requires quotations for the same purchase and principal.")
        offers = [self.assess_offer(applicant, q, as_of) for q in quotes]
        for q, offer in zip(quotes, offers):
            offer["alternative_scenarios"] = self.recommendations.alternatives(applicant, q, offer, as_of)
            offer["recommendation"] = self.recommendations.narrative(offer)
        def comparable(o):
            return (o["policy"]["assessment_checks_pass"] and not o["coverage_warnings"]
                    and o["financials"]["upfront_cash_gap_rm"] == 0)
        candidates = [o for o in offers if comparable(o)]
        # Nominal rates with different flat/reducing bases are never sorted directly.
        cost_rank = sorted(candidates, key=lambda o: o["financials"]["total_financing_cost_rm"])
        rate_rank = sorted(candidates, key=lambda o: o["financials"]["annual_effective_cashflow_rate"])
        balance_rank = sorted(candidates, key=lambda o: (-o["approval_chance"]["generic_synthetic_probability"],
                                                        o["financials"]["total_financing_cost_rm"]))
        return {
            "mode": "synthetic_mock_documents_only", "as_of": as_of, "demo_id": applicant.demo_id,
            "model_scope": "Simulation prototype; not a bank decision, licensed credit report, or validated real-world approval service.",
            "offers": offers,
            "bank_options": {"lowest_total_financing_cost": [o["offer_id"] for o in cost_rank],
                             "lowest_effective_cashflow_rate": [o["offer_id"] for o in rate_rank],
                             "approval_then_cost": [o["offer_id"] for o in balance_rank],
                             "scope": "Only uploaded mock offers and the supported published product checks; not all banks or live rates.",
                             "different_tenors": len({q.months for q in quotes}) > 1,
                             "excluded_offers": [o["offer_id"] for o in offers if not comparable(o)]},
            "document_audit": document_audit,
            "privacy": {"local_ocr": True, "real_documents_accepted": False, "bank_connections": False,
                        "llm_used_by_default": False, "human_review_required_for_real_deployment": True},
        }


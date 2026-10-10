"""Meaningful financial, reconciliation, attribution and external-service checks.

No internet calls or paid LLM calls are made by these tests. Run the separate
verify_ocr.py for real local OCR against all thirty provided document images.
"""
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import unittest

from loan_engine.demo_documents import fixture_fields
from loan_engine.documents import DocumentSubmission, parse_fields, DocumentKind
from loan_engine.engine import LoanAssessmentEngine
from loan_engine.features import engineer
from loan_engine.finance import instalment, effective_rate, calculations
from loan_engine.policies import PolicyEngine
from loan_engine.predictors import RiskRatingModel
from loan_engine.schema import AssessmentError

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-10-10"


def submission_from_fields(fields):
    submission = DocumentSubmission(ROOT / "sample_documents/car/manifest.json")
    for kind, values in fields.items():
        lines = [(f"{k}: {v}", .999) for k, v in values.items()]
        submission.documents[kind] = parse_fields(kind, lines, "test-only-digest")
    return submission


def fixture(product="car"):
    return submission_from_fields(fixture_fields(product)).compile(AS_OF)


class FinancialTests(unittest.TestCase):
    def setUp(self):
        self.a, self.quotes, _ = fixture()
        self.q = self.quotes[0]

    def test_public_bank_ninety_percent_and_ten_percent_cash(self):
        result = PolicyEngine().check(self.a, self.q, AS_OF)
        f = calculations(self.a, self.q, result["principal_ceiling_rm"])
        self.assertEqual(result["principal_ceiling_rm"], 90000)
        self.assertEqual(f["minimum_asset_cash_rm"], 10000)
        self.assertTrue(f["ceiling_is_not_bank_approved_amount"])

    def test_annuity_matches_present_value(self):
        payment = instalment(self.q)
        r = self.q.annual_rate / 12
        pv = sum(payment / (1 + r) ** i for i in range(1, self.q.months + 1))
        self.assertAlmostEqual(pv, self.q.requested_principal, places=6)

    def test_zero_interest_and_fee_cashflows(self):
        q = replace(self.q, annual_rate=0, fees=0)
        self.assertAlmostEqual(instalment(q), q.requested_principal / q.months)
        self.assertAlmostEqual(effective_rate(q), 0, places=9)
        self.assertGreater(effective_rate(replace(q, fees=500)), 0)

    def test_flat_rate_is_not_compared_as_nominal_rate(self):
        q = replace(self.q, annual_rate=.03, rate_method="flat", fees=0)
        self.assertAlmostEqual(instalment(q), 90000 * (1 + .03 * 7) / 84)
        self.assertGreater(effective_rate(q), q.annual_rate)
        self.assertGreater(effective_rate(replace(q, fees=300)), effective_rate(q))

    def test_variable_rate_stress_increases_payment_and_dsr(self):
        a, quotes, _ = fixture("home")
        f = calculations(a, quotes[0], 270000)
        self.assertGreater(f["rate_stress_plus_2pp"]["dsr"], f["calculated_dsr"])

    def test_purchase_price_reconciles_to_deposit_plus_principal(self):
        with self.assertRaises(AssessmentError):
            replace(self.q, requested_principal=85000).validate()

    def test_nan_and_percentage_wrong_units_are_rejected(self):
        for rate in (math.nan, math.inf, 5.3):
            with self.assertRaises(AssessmentError):
                replace(self.q, annual_rate=rate).validate()

    def test_third_outstanding_housing_facility_seventy_percent(self):
        a, quotes, _ = fixture("home")
        p = PolicyEngine().check(replace(a, housing_loans_count=2), quotes[0], AS_OF)
        self.assertEqual(p["principal_ceiling_rm"], 210000)
        self.assertFalse(p["published_rules_pass"])

    def test_home_planning_assumption_is_not_published_bank_rule(self):
        a, quotes, _ = fixture("home")
        q = replace(quotes[0], requested_principal=279000, down_payment=21000)
        p = PolicyEngine().check(a, q, AS_OF)
        self.assertTrue(p["published_rules_pass"])
        self.assertFalse(p["assessment_checks_pass"])
        self.assertTrue(p["assumption_failures"])

    def test_old_vehicle_margin_and_tenure(self):
        p = PolicyEngine().check(self.a, replace(self.q, vehicle_age=11), AS_OF)
        self.assertEqual(p["principal_ceiling_rm"], 75000)
        self.assertEqual(p["max_months"], 36)
        self.assertFalse(p["published_rules_pass"])

    def test_maybank_reducing_balance_switch(self):
        q = replace(self.quotes[1], rate_method="flat")
        self.assertFalse(PolicyEngine().check(self.a, q, AS_OF)["published_rules_pass"])

    def test_personal_employment_and_age_at_maturity(self):
        a, qs, _ = fixture("personal")
        p = PolicyEngine().check(a, qs[1], AS_OF)
        self.assertFalse(p["published_rules_pass"])  # only four months in current role
        p = PolicyEngine().check(replace(a, months_in_job=7, age=58), qs[1], AS_OF)
        self.assertEqual(p["max_months"], 24)
        self.assertFalse(p["published_rules_pass"])

    def test_personal_2027_effective_date_with_reverified_snapshot(self):
        a, qs, _ = fixture("personal")
        policies = PolicyEngine()
        policies.data["verified_on"], policies.data["valid_until"] = "2027-01-01", "2027-01-31"
        p = policies.check(a, replace(qs[0], quote_date="2027-01-01"), "2027-01-01")
        self.assertTrue(any("2027" in error for error in p["failures"]))
        self.assertTrue(PolicyEngine().check(a, qs[0], AS_OF)["published_rules_pass"])

    def test_stale_policies_and_quotations_stop_assessment(self):
        for today in ("2026-10-01", "2026-12-01"):
            with self.assertRaises(AssessmentError):
                PolicyEngine().check(self.a, self.q, today)
        with self.assertRaises(AssessmentError):
            PolicyEngine().check(self.a, replace(self.q, quote_date="2026-08-01"), AS_OF)


class DocumentTests(unittest.TestCase):
    def test_no_manual_financial_entry_required_and_no_debt_double_count(self):
        a, qs, _ = fixture()
        f = calculations(a, qs[0], 90000)
        self.assertEqual(f["existing_monthly_debt_rm"], 1700)  # 1350 + 350, not counted again from CCRIS
        self.assertTrue(a.document_verified)

    def test_missing_image_stops_submission(self):
        docs = fixture_fields()
        del docs["ctos_statement"]
        with self.assertRaises(AssessmentError):
            submission_from_fields(docs).compile(AS_OF)

    def test_identity_mismatch_stops_submission(self):
        docs = fixture_fields()
        docs["bank_statement"]["demo_id"] = "DEMO99999"
        with self.assertRaises(AssessmentError):
            submission_from_fields(docs).compile(AS_OF)

    def test_salary_credit_epf_and_debt_mismatches_stop(self):
        for kind, field in (("bank_statement", "income_credit_1"), ("epf_statement", "employee_contribution_1"),
                            ("credit_card_statement", "balance"), ("existing_loan_statement", "monthly_payment")):
            docs = fixture_fields()
            docs[kind][field] += 100
            with self.subTest(kind=kind), self.assertRaises(AssessmentError):
                submission_from_fields(docs).compile(AS_OF)

    def test_duplicate_income_months_and_stale_income_stop(self):
        docs = fixture_fields()
        for kind in ("payslip", "bank_statement", "epf_statement"):
            docs[kind]["month_2"] = docs[kind]["month_1"]
        with self.assertRaises(AssessmentError):
            submission_from_fields(docs).compile(AS_OF)

    def test_unknown_or_wrong_slot_image_rejected_before_ocr(self):
        class ExplodingOCR:
            def recognize(self, content):
                raise AssertionError("OCR must not run on unknown/wrong-slot bytes")
        sub = DocumentSubmission(ROOT / "sample_documents/car/manifest.json", ExplodingOCR())
        with self.assertRaises(AssessmentError):
            sub.add_document("profile", "private.png", b"arbitrary unknown input")
        payslip = ROOT / "sample_documents/car/payslip.png"
        with self.assertRaises(AssessmentError):
            sub.add_document("profile", payslip.name, payslip.read_bytes())

    def test_low_confidence_ambiguous_and_missing_fields_stop(self):
        lines = [(f"{k}: {v}", .999) for k, v in fixture_fields()["profile"].items()]
        with self.assertRaises(AssessmentError):
            parse_fields("profile", lines + [("age: 33", .999)], "digest")
        with self.assertRaises(AssessmentError):
            parse_fields("profile", [(t, .5) for t, _ in lines], "digest")
        with self.assertRaises(AssessmentError):
            parse_fields("profile", lines[:-1], "digest")


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = LoanAssessmentEngine(ROOT / "artifacts")
        cls.a, cls.quotes, cls.audit = fixture()
        cls.result = cls.engine.assess(cls.a, cls.quotes, AS_OF, cls.audit)

    def test_separate_risk_approval_and_internal_score_outputs(self):
        o = self.result["offers"][0]
        p = o["approval_chance"]["generic_synthetic_probability"]
        risk = o["credit_risk"]["probability_90day_arrears_next_12m"]
        self.assertTrue(0 < p < 1 and 0 < risk < 1)
        self.assertNotAlmostEqual(p, 1 - risk)
        self.assertIsNone(o["approval_chance"]["bank_specific_probability"])
        self.assertTrue(0 <= o["internal_credit_health_score"]["value"] <= 100)

    def test_shap_reconstructs_calibrated_probabilities_and_score(self):
        for q in self.quotes:
            f = engineer(self.a, q)
            pred = self.engine.models.predict(f)
            shap = self.engine.shap.explain(f)
            for target in ("approval", "risk", "health"):
                self.assertAlmostEqual(shap[target]["reconstructed_prediction"], pred[target], places=4)
                self.assertAlmostEqual(sum(v["contribution"] for v in shap[target]["features"]),
                                       shap[target]["sum_contributions"], places=6)

    def test_letter_grade_boundaries(self):
        for p, grade in ((0, "A"), (.03, "B"), (.08, "C"), (.15, "D"), (.30, "E"), (.50, "F"), (1, "F")):
            self.assertEqual(RiskRatingModel.grade(p), grade)

    def test_outside_training_coverage_suppresses_probability(self):
        a = replace(self.a, net_income=100000, gross_income=120000)
        result = self.engine.assess_offer(a, self.quotes[0], AS_OF)
        self.assertTrue(result["coverage_warnings"])
        self.assertIsNone(result["approval_chance"]["generic_synthetic_probability"])

    def test_unverified_documents_cannot_use_public_assessment(self):
        with self.assertRaises(AssessmentError):
            self.engine.assess(replace(self.a, document_verified=False), self.quotes, AS_OF, self.audit)

    def test_down_payment_scenario_deducts_cash_once(self):
        o = self.result["offers"][0]
        scenario = next(s for s in o["alternative_scenarios"] if s["action"] == "Increase the down payment")
        self.assertAlmostEqual(scenario["cash_after_deposit_and_fees_rm"],
            self.a.cash_savings - self.quotes[0].down_payment - self.quotes[0].fees - scenario["cash_cost_rm"])
        self.assertGreaterEqual(scenario["cash_after_deposit_and_fees_rm"], scenario["emergency_reserve_assumption_rm"] - .01)

    def test_card_payment_action_reruns_model_and_does_not_erase_arrears(self):
        scenario = next(s for s in self.result["offers"][0]["alternative_scenarios"] if s["action"] == "Repay part of the card balance")
        repay = scenario["cash_cost_rm"]
        a2 = replace(self.a, card_balance=self.a.card_balance - repay,
                     card_payment=self.a.card_payment * (1 - repay / self.a.card_balance), cash_savings=self.a.cash_savings - repay)
        expected = self.engine.assess_offer(a2, self.quotes[0], AS_OF, explain=False)
        self.assertAlmostEqual(scenario["scenario_approval_probability"], expected["approval_chance"]["generic_synthetic_probability"])
        self.assertEqual(a2.arrears_max_months, self.a.arrears_max_months)
        self.assertIsNone(scenario["official_ctos_score_change"])

    def test_offer_ranking_uses_effective_cashflow_rate(self):
        ranked = self.result["bank_options"]["lowest_effective_cashflow_rate"]
        eligible = {o["offer_id"]: o for o in self.result["offers"]}
        rates = [eligible[k]["financials"]["annual_effective_cashflow_rate"] for k in ranked]
        self.assertEqual(rates, sorted(rates))




if __name__ == "__main__":
    unittest.main()

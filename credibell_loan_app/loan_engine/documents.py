"""Ten independent upload slots; strictly local OCR of registered mock PNG/JPEG files.

The manifest is trusted local configuration produced by make-demo. SHA-256 registration
is a mock-only acceptance control, NOT document authentication or a production PII filter.
Unknown bytes are rejected BEFORE OCR. Arbitrary real statements are intentionally unsupported.
"""
from enum import Enum
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from io import BytesIO
import importlib.util
import json
import re
from pathlib import Path
import numpy as np
from PIL import Image
from .schema import Applicant, Quote, AssessmentError


class DocumentKind(str, Enum):
    PROFILE = "profile"
    PAYSLIP = "payslip"
    BANK_STATEMENT = "bank_statement"
    EPF = "epf_statement"
    CCRIS = "ccris_statement"
    CTOS = "ctos_statement"
    CREDIT_CARD = "credit_card_statement"
    EXISTING_LOAN = "existing_loan_statement"
    EMPLOYMENT = "employment_contract"
    QUOTATION = "loan_quotation"


COMMON = {"demo_marker": str, "demo_id": str, "document_type": str, "issued_date": str}
PERIODS = {f"month_{i}": str for i in range(1, 4)}
FIELDS = {
    "profile": {"age": int, "citizenship": str},
    "payslip": {**PERIODS, **{f"{key}_{i}": float for key in ("gross", "net", "epf", "tax", "other_deductions") for i in range(1, 4)}},
    "bank_statement": {**PERIODS, **{f"{key}_{i}": float for key in ("income_credit", "living_expenses") for i in range(1, 4)}, "cash_savings": float},
    "epf_statement": {**PERIODS, **{f"employee_contribution_{i}": float for i in range(1, 4)}, "balance": float, "regular_months": int},
    "ccris_statement": {"card_account": str, "loan_account": str, "card_payment": float, "loan_payment": float,
                        "card_balance": float, "card_limit": float, "loan_balance": float,
                        "arrears_max_months": int, "late_payments_12m": int, "housing_loans_count": int},
    "ctos_statement": {"mock_reported_score": int, "legal_flags": int},
    "credit_card_statement": {"account": str, "balance": float, "limit": float, "minimum_due": float, "annual_rate": float},
    "existing_loan_statement": {"account": str, "balance": float, "monthly_payment": float, "early_settlement_fee": float},
    "employment_contract": {"months_in_job": int, "contract_months_remaining": int, "variable_income_fraction": float},
    "loan_quotation": {"product": str, "asset_price": float, "requested_principal": float, "down_payment": float,
                       "vehicle_age": int, "offer_count": int,
                       **{f"{key}_{i}": kind for i in (1, 2) for key, kind in
                          {"bank_code": str, "annual_rate": float, "rate_method": str, "months": int,
                           "fees": float, "variable_rate": int}.items()}},
}


def canonical(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass
class ParsedDocument:
    kind: str
    fields: dict
    field_confidences: dict
    source_sha256: str
    recognition_min_confidence: float
    field_evidence: dict = field(default_factory=dict)
    page_count: int = 1


class LocalOCR:
    def __init__(self):
        from rapidocr import RapidOCR
        models = Path(importlib.util.find_spec("rapidocr").origin).parent / "models"
        names = {"Det": "PP-OCRv6_det_small.onnx", "Rec": "PP-OCRv6_rec_small.onnx", "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx"}
        missing = [str(models / name) for name in names.values() if not (models / name).exists()]
        if missing:
            raise AssessmentError("Offline OCR assets missing. Install pinned rapidocr==3.10.0 with its bundled models. " + str(missing))
        params = {f"{stage}.model_path": str(models / filename) for stage, filename in names.items()}
        params.update({"EngineConfig.onnxruntime.intra_op_num_threads": 2,
                       "EngineConfig.onnxruntime.inter_op_num_threads": 2, "Global.log_level": "warning"})
        self.engine = RapidOCR(params=params)

    def recognize(self, content):
        with Image.open(BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG"} or getattr(image, "n_frames", 1) != 1:
                raise AssessmentError("Only single-frame PNG/JPEG mock images are supported.")
            if image.width * image.height > 12_000_000:
                raise AssessmentError("Image exceeds the 12-megapixel limit.")
            output = self.engine(np.asarray(image.convert("RGB")))
        if output.txts is None:
            raise AssessmentError("OCR found no text.")
        return [(str(text), float(score)) for text, score in zip(output.txts, output.scores)]


def parse_fields(kind, recognized, digest, min_confidence=.90):
    types = {**COMMON, **FIELDS[kind]}
    keys = {canonical(key): key for key in types}
    values, confidences = {}, {}
    # Each generated form contains one labelled value per line, so there is no
    # inference from unrelated transaction amounts or free text.
    for text, confidence in recognized:
        match = re.match(r"^\s*([^:：]+)[:：]\s*(.*?)\s*$", text)
        if not match:
            continue
        key = keys.get(canonical(match.group(1)))
        if key is None:
            continue
        if key in values:
            raise AssessmentError(f"Duplicate/ambiguous OCR field {kind}.{key}.")
        if confidence < min_confidence:
            raise AssessmentError(f"Low OCR confidence for {kind}.{key}: {confidence:.3f}; assessment stopped.")
        raw = match.group(2).strip()
        convert = types[key]
        if convert in (float, int):
            raw = raw.replace(",", "").replace(" ", "")
            if not re.fullmatch(r"\d+(?:\.\d+)?", raw):
                raise AssessmentError(f"Unrecognized numeric value for {kind}.{key}: {raw!r}")
            value = float(raw)
            if not np.isfinite(value) or value < 0 or (convert is int and not value.is_integer()):
                raise AssessmentError(f"Invalid value for {kind}.{key}.")
            values[key] = convert(value)
        else:
            values[key] = raw.replace(" ", "")
        confidences[key] = confidence
    required = set(types)
    if kind == "loan_quotation" and values.get("offer_count") == 1:
        required -= {key for key in FIELDS[kind] if key.endswith("_2")}
    if missing := required - values.keys():
        raise AssessmentError(f"Missing OCR fields in {kind}: {sorted(missing)}. Use complete, clear registered mock images.")
    if values["demo_marker"] != "SYNTHETICONLY" or values["document_type"] != kind:
        raise AssessmentError("Synthetic marker or document upload slot does not match.")
    date.fromisoformat(values["issued_date"])
    return ParsedDocument(kind, values, confidences, digest, min(confidences.values()))


class DocumentSubmission:
    """Map future UI file uploaders to add_document(DocumentKind, filename, bytes).

    Every slot is independent. No manual financial input, UI framework or bank API.
    """
    def __init__(self, manifest_path, ocr=None):
        self.manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if self.manifest.get("synthetic_only") is not True:
            raise AssessmentError("A trusted synthetic-only manifest is required.")
        self.ocr = ocr
        self.documents = {}

    def add_document(self, kind, filename, content):
        kind = DocumentKind(kind).value
        if len(content) > 12_000_000:
            raise AssessmentError("Upload exceeds 12 MB.")
        if Path(filename).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise AssessmentError("Upload a registered PNG/JPEG mock image.")
        digest = sha256(content).hexdigest()
        registration = self.manifest["files"].get(digest)
        if not registration or registration["kind"] != kind:
            raise AssessmentError("Unregistered or wrong-slot image rejected before OCR. Real documents are not accepted.")
        if self.ocr is None:
            self.ocr = LocalOCR()
        doc = parse_fields(kind, self.ocr.recognize(content), digest)
        if doc.fields["demo_id"] != registration["demo_id"]:
            raise AssessmentError("OCR applicant identifier disagrees with trusted mock registration.")
        self.documents[kind] = doc
        return doc

    def compile(self, as_of):
        missing = set(k.value for k in DocumentKind) - self.documents.keys()
        if missing:
            raise AssessmentError(f"Missing document slots: {sorted(missing)}")
        docs = {k: d.fields for k, d in self.documents.items()}
        identities = {d["demo_id"] for d in docs.values()}
        if len(identities) != 1:
            raise AssessmentError("Documents belong to different mock applicants.")
        today = date.fromisoformat(as_of)
        for kind, d in docs.items():
            age_days = (today - date.fromisoformat(d["issued_date"])).days
            limit = 365 if kind in {"profile", "employment_contract", "epf_statement"} else 60
            if age_days < 0 or age_days > limit:
                raise AssessmentError(f"{kind} date outside demo recency rule ({limit} days); this is not a bank-specific limit.")
        p, b, e, c, t, card, loan, contract, profile, quote = [docs[k] for k in
            ("payslip", "bank_statement", "epf_statement", "ccris_statement", "ctos_statement", "credit_card_statement",
             "existing_loan_statement", "employment_contract", "profile", "loan_quotation")]
        def same(x, y, field):
            if isinstance(x, (float, int)) and isinstance(y, (float, int)):
                agrees = abs(x - y) <= 1.0
            else:
                agrees = x == y
            if not agrees:
                raise AssessmentError(f"Cross-document mismatch: {field}; no prediction produced.")
        for i in range(1, 4):
            same(p[f"month_{i}"], b[f"month_{i}"], "salary/bank month")
            same(p[f"month_{i}"], e[f"month_{i}"], "salary/EPF month")
            same(p[f"net_{i}"], b[f"income_credit_{i}"], "salary paid versus bank income credit")
            same(p[f"epf_{i}"], e[f"employee_contribution_{i}"], "payslip/EPF employee contribution")
            same(p[f"gross_{i}"] - p[f"epf_{i}"] - p[f"tax_{i}"] - p[f"other_deductions_{i}"], p[f"net_{i}"], "net salary arithmetic")
        months = [date.fromisoformat(p[f"month_{i}"]) for i in range(1, 4)]
        if len({(d.year, d.month) for d in months}) != 3 or months != sorted(months):
            raise AssessmentError("Three distinct chronological salary months are required.")
        if any((y.year * 12 + y.month) - (x.year * 12 + x.month) != 1 for x, y in zip(months, months[1:])):
            raise AssessmentError("Salary months must be consecutive.")
        if not 0 <= (today - months[-1]).days <= 60:
            raise AssessmentError("Most recent income month must be within 60 days.")
        # Match account keys before using payments: credit reports repeat debts.
        for x, y, key in [(c["card_account"], card["account"], "card account"),
                          (c["loan_account"], loan["account"], "loan account"),
                          (c["card_balance"], card["balance"], "card balance"),
                          (c["card_limit"], card["limit"], "card limit"),
                          (c["card_payment"], card["minimum_due"], "card payment"),
                          (c["loan_payment"], loan["monthly_payment"], "loan payment"),
                          (c["loan_balance"], loan["balance"], "loan balance")]:
            same(x, y, key)
        net_values = np.array([p[f"net_{i}"] for i in range(1, 4)])
        a = Applicant(
            demo_id=next(iter(identities)), age=profile["age"], citizenship=profile["citizenship"],
            gross_income=float(np.mean([p[f"gross_{i}"] for i in range(1, 4)])), net_income=float(net_values.mean()),
            existing_loan_payment=loan["monthly_payment"], loan_balance=loan["balance"],
            card_payment=card["minimum_due"], card_balance=card["balance"], card_limit=card["limit"],
            card_annual_rate=card["annual_rate"], living_expenses=float(np.mean([b[f"living_expenses_{i}"] for i in range(1, 4)])),
            cash_savings=b["cash_savings"], income_variability=float(net_values.std() / net_values.mean()),
            variable_income_fraction=contract["variable_income_fraction"], months_in_job=contract["months_in_job"],
            contract_months_remaining=contract["contract_months_remaining"], epf_balance=e["balance"], epf_regular_months=e["regular_months"],
            arrears_max_months=c["arrears_max_months"], late_payments_12m=c["late_payments_12m"], housing_loans_count=c["housing_loans_count"],
            mock_reported_ctos_score=t["mock_reported_score"], legal_flags=t["legal_flags"], loan_settlement_fee=loan["early_settlement_fee"],
            document_verified=True,
        ).validate()
        if quote["offer_count"] not in {1, 2}:
            raise AssessmentError("Mock quotation supports one or two explicit bank offers.")
        offers = []
        for i in range(1, quote["offer_count"] + 1):
            if quote[f"variable_rate_{i}"] not in {0, 1}:
                raise AssessmentError("Variable rate indicator must be 0 or 1.")
            offers.append(Quote(
                f"OFFER{i}", quote[f"bank_code_{i}"], quote["product"], quote["asset_price"], quote["requested_principal"],
                quote["down_payment"], quote[f"annual_rate_{i}"], quote[f"rate_method_{i}"], quote[f"months_{i}"],
                quote[f"fees_{i}"], bool(quote[f"variable_rate_{i}"]), quote["vehicle_age"], quote["issued_date"]
            ).validate())
        audit = {k: {"source_sha256": d.source_sha256, "fields": d.fields,
                     "field_confidences": d.field_confidences, "recognition_min_confidence": d.recognition_min_confidence}
                 for k, d in self.documents.items()}
        return a, offers, audit


"""Create anonymous, labelled mock images and a trusted byte-registration manifest.

Forms are intentionally a controlled template, not replicas of bank/CTOS/CCRIS documents.
expected_fields.json is a TEST oracle; the OCR runtime never reads it.
"""
from datetime import date
from hashlib import sha256
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
from .documents import FIELDS


def fixture_fields(product="car", demo_id="DEMO00001", as_of="2026-10-10"):
    issued = date.fromisoformat(as_of)
    months = []
    for offset in (3, 2, 1):
        index = issued.year * 12 + issued.month - 1 - offset
        year, month = divmod(index, 12)
        months.append(f"{year:04d}-{month + 1:02d}-15")
    periods = {f"month_{i}": value for i, value in enumerate(months, 1)}
    net, gross = [6400, 6500, 6600], [7900, 8000, 8100]
    epf = [round(x * .11, 2) for x in gross]
    tax = [round(g - n - e - 100, 2) for g, n, e in zip(gross, net, epf)]
    docs = {
        "profile": {"age": 32, "citizenship": "MY"},
        "payslip": {**periods, **{f"{key}_{i}": values[i - 1] for key, values in
                    {"gross": gross, "net": net, "epf": epf, "tax": tax, "other_deductions": [100, 100, 100]}.items() for i in range(1, 4)}},
        "bank_statement": {**periods, **{f"income_credit_{i}": v for i, v in enumerate(net, 1)},
                           **{f"living_expenses_{i}": 2100 for i in range(1, 4)}, "cash_savings": 30000},
        "epf_statement": {**periods, **{f"employee_contribution_{i}": v for i, v in enumerate(epf, 1)}, "balance": 92000, "regular_months": 12},
        "ccris_statement": {"card_account": "CCDEMO1", "loan_account": "LNDEMO1", "card_payment": 350, "loan_payment": 1350,
                            "card_balance": 7000, "card_limit": 10000, "loan_balance": 22000,
                            "arrears_max_months": 1, "late_payments_12m": 2, "housing_loans_count": 0},
        "ctos_statement": {"mock_reported_score": 625, "legal_flags": 0},
        "credit_card_statement": {"account": "CCDEMO1", "balance": 7000, "limit": 10000, "minimum_due": 350, "annual_rate": .18},
        "existing_loan_statement": {"account": "LNDEMO1", "balance": 22000, "monthly_payment": 1350, "early_settlement_fee": 50},
        "employment_contract": {"months_in_job": 4, "contract_months_remaining": 999, "variable_income_fraction": .35},
    }
    docs["ccris_statement"]["card_account"] = docs["credit_card_statement"]["account"] = "CC" + demo_id
    docs["ccris_statement"]["loan_account"] = docs["existing_loan_statement"]["account"] = "LN" + demo_id
    choices = {
        "car": (100000, 90000, 10000, [("PUBLIC_BANK_CAR", .053, "reducing_nominal", 84, 100, 0),
                                      ("MAYBANK_CAR", .058, "reducing_effective", 84, 200, 0)]),
        "home": (300000, 270000, 30000, [("CIMB_HOME", .041, "reducing_nominal", 360, 1000, 1),
                                      ("MAYBANK_HOME", .039, "reducing_nominal", 360, 1500, 1)]),
        "personal": (30000, 30000, 0, [("MAYBANK_PERSONAL", .07, "flat", 60, 0, 0),
                                    ("CIMB_PERSONAL", .0788, "flat", 60, 150, 0)]),
    }
    asset, principal, deposit, offers = choices[product]
    if product == "home":
        docs["bank_statement"]["cash_savings"] = 80000
    quotation = {"product": product, "asset_price": asset, "requested_principal": principal,
                 "down_payment": deposit, "vehicle_age": 0, "offer_count": len(offers)}
    for i, row in enumerate(offers, 1):
        quotation.update({f"{key}_{i}": value for key, value in zip(
            ("bank_code", "annual_rate", "rate_method", "months", "fees", "variable_rate"), row)})
    docs["loan_quotation"] = quotation
    return {kind: {"demo_marker": "SYNTHETICONLY", "demo_id": demo_id, "document_type": kind,
                   "issued_date": as_of, **fields} for kind, fields in docs.items()}


def font(size):
    candidates = [Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def make_demo(output_dir, product="car", demo_id="DEMO00001", as_of="2026-10-10"):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    expected = fixture_fields(product, demo_id, as_of)
    manifest = {"synthetic_only": True, "generator": "loan_models_v2", "files": {}}
    for kind, fields in expected.items():
        lines = [f"{key}: {value:.4f}" if isinstance(value, float) else f"{key}: {value}" for key, value in fields.items()]
        width, height = 1440, 220 + 62 * len(lines)
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width, 100), fill="#143744")
        draw.text((45, 25), "MOCK FINANCIAL DOCUMENT", fill="white", font=font(39))
        draw.text((45, 119), "Anonymous demo data / Not an official bank or bureau record", fill="#43505b", font=font(26))
        for i, line in enumerate(lines):
            draw.text((45, 185 + 62 * i), line, fill="black", font=font(34))
        path = out / f"{kind}.png"
        image.save(path, optimize=True)
        digest = sha256(path.read_bytes()).hexdigest()
        manifest["files"][digest] = {"kind": kind, "demo_id": demo_id}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "expected_fields.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")
    return manifest


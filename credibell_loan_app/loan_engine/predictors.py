import json
from pathlib import Path
import numpy as np
import xgboost as xgb
from .features import FEATURES
from .synthetic import sigmoid
from .schema import AssessmentError


class ModelBundle:
    def __init__(self, model_dir):
        self.model_dir = Path(model_dir)
        self.metadata = json.loads((self.model_dir / "metadata.json").read_text(encoding="utf-8"))
        if self.metadata["feature_names"] != FEATURES or not self.metadata["not_real_bank_validation"]:
            raise AssessmentError("Incompatible model bundle or missing synthetic-data label.")
        self.boosters = {}
        for name, filename in self.metadata["models"].items():
            booster = xgb.Booster(params={"nthread": 2})
            booster.load_model(bytearray((self.model_dir / filename).read_bytes()))
            self.boosters[name] = booster

    def matrix(self, features):
        if set(features) != set(FEATURES):
            raise AssessmentError("Feature schema mismatch.")
        return xgb.DMatrix(np.array([[features[k] for k in FEATURES]], dtype=np.float32), feature_names=FEATURES)

    def coverage_warnings(self, features):
        return [f"{k} is outside the synthetic training range"
                for k in FEATURES if features[k] < self.metadata["feature_ranges"][k][0] - .0001
                or features[k] > self.metadata["feature_ranges"][k][1] + .0001]

    def predict(self, features):
        matrix = self.matrix(features)
        out = {}
        for name, model in self.boosters.items():
            margin = float(model.predict(matrix, output_margin=True)[0])
            if name == "health":
                out[name] = float(np.clip(margin, 0, 100))
            else:
                c = self.metadata["calibration"][name]
                out[name] = float(sigmoid(c["slope"] * margin + c["intercept"]))
        return out


class RiskRatingModel:
    """Separate grade component using the independently trained 12-month arrears model.

    Custom demonstration boundaries; they are not a CTOS or bank rating scale.
    Approval and delinquency are separate targets, not complements.
    """
    BANDS = [(0.03, "A"), (0.08, "B"), (0.15, "C"), (0.30, "D"), (0.50, "E"), (1.01, "F")]

    @classmethod
    def grade(cls, probability):
        if not 0 <= probability <= 1:
            raise AssessmentError("Risk probability is out of range.")
        return next(grade for ceiling, grade in cls.BANDS if probability < ceiling)

    def assess(self, probability):
        return {"rating": self.grade(probability), "probability_90day_arrears_next_12m": probability,
                "scale": "Custom A-F demonstration scale; A lowest risk, F highest risk.",
                "bands": [{"upper_exclusive": min(1, x), "rating": g} for x, g in self.BANDS]}


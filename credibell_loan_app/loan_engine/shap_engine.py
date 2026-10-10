"""Exact TreeSHAP via XGBoost; no approximate feature importance or extra SHAP dependency.

Binary explanations add in CALIBRATED LOG-ODDS, never percentage-point deltas.
Grade explanations inherit the risk model; grade cutoffs are deterministic.
"""
import numpy as np
from .features import FEATURES
from .synthetic import sigmoid


class ShapEngine:
    def __init__(self, models):
        self.models = models

    def explain(self, features):
        matrix = self.models.matrix(features)
        result = {}
        for name, booster in self.models.boosters.items():
            contributions = booster.predict(matrix, pred_contribs=True, approx_contribs=False)[0].astype(float)
            base = float(contributions[-1])
            effects = contributions[:-1]
            if name != "health":
                c = self.models.metadata["calibration"][name]
                effects = effects * c["slope"]
                base = base * c["slope"] + c["intercept"]
                units, link = "calibrated_log_odds", "sigmoid"
                reconstructed = float(sigmoid(base + effects.sum()))
            else:
                units, link = "internal_score_points_before_0_100_clip", "clip_0_100"
                reconstructed = float(np.clip(base + effects.sum(), 0, 100))
            pairs = [{"feature": k, "value": float(features[k]), "contribution": float(v)} for k, v in zip(FEATURES, effects)]
            pairs.sort(key=lambda item: abs(item["contribution"]), reverse=True)
            result[name] = {"method": "Exact TreeSHAP with tree-path-dependent background",
                            "units": units, "base_value": base, "link": link,
                            "sum_contributions": float(effects.sum()), "reconstructed_prediction": reconstructed,
                            "features": pairs, "causal_interpretation": False}
        result["risk_rating"] = {"derived_from": "risk", "explanation": "A-F follows risk probability thresholds; refer to risk SHAP effects."}
        return result

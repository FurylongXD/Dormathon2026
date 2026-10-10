import csv
import json
from pathlib import Path
import numpy as np
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss, mean_absolute_error
from sklearn.model_selection import train_test_split
from .features import FEATURES
from .synthetic import generate_training_data, sigmoid

MODEL_FILES = {"approval": "approval.json", "risk": "credit_risk.json", "health": "credit_health.json"}


def binary_metrics(y, p):
    approved = p >= .5
    bins = []
    for lo in np.arange(0, 1, .1):
        mask = (p >= lo) & (p < lo + .1)
        if mask.any():
            bins.append({"bin_lower": round(float(lo), 1), "count": int(mask.sum()),
                         "mean_prediction": float(p[mask].mean()), "observed_fraction": float(y[mask].mean())})
    return {"roc_auc": float(roc_auc_score(y, p)), "brier_score": float(brier_score_loss(y, p)),
            "log_loss": float(log_loss(y, p)), "threshold": .5,
            "false_negative_rate": float((~approved[y == 1]).mean()),
            "false_positive_rate": float(approved[y == 0].mean()), "calibration_bins": bins}


def train_models(out_dir, n=16000, seed=20261010, export_data=None):
    if n < 2000:
        raise ValueError("At least 2,000 synthetic records are required for disjoint validation sets.")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, approval, arrears, health = generate_training_data(n, seed)
    X = np.array([[r[k] for k in FEATURES] for r in rows], dtype=np.float32)
    idx = np.arange(n)
    train_idx, rest = train_test_split(idx, test_size=.4, random_state=seed, stratify=approval)
    early_idx, rest = train_test_split(rest, test_size=.625, random_state=seed + 1, stratify=approval[rest])
    cal_idx, test_idx = train_test_split(rest, test_size=.6, random_state=seed + 2, stratify=approval[rest])
    def matrix(indices, labels=None):
        return xgb.DMatrix(X[indices], label=labels[indices] if labels is not None else None, feature_names=FEATURES)
    metadata = {
        "schema_version": 1, "feature_names": FEATURES, "data_source": "fully_synthetic_simulator_v2",
        "not_real_bank_validation": True, "seed": seed, "n": n,
        "splits": {"train": len(train_idx), "early_stopping": len(early_idx),
                   "calibration": len(cal_idx), "untouched_test": len(test_idx)},
        "target_definitions": {
            "approval": "Synthetic generic underwriting approval of the requested quotation; not bank-specific odds.",
            "risk": "Synthetic occurrence of at least one 90+ day arrears event within the next 12 months, for ALL simulated profiles including rejected ones.",
            "health": "Expected synthetic 12-month internal credit-health score (0-100); not CTOS, CCRIS, FICO or a bureau score."
        },
        "feature_ranges": {k: [float(X[:, j].min()), float(X[:, j].max())] for j, k in enumerate(FEATURES)},
        "calibration": {}, "models": MODEL_FILES,
    }
    metrics = {"scope": "Held-out synthetic records only; no claim of real Malaysian bank accuracy.", "models": {}}
    for name, y in [("approval", approval), ("risk", arrears), ("health", health)]:
        binary = name != "health"
        params = {"objective": "binary:logistic" if binary else "reg:squarederror",
                  "eval_metric": "logloss" if binary else "mae", "tree_method": "hist",
                  "max_depth": 3, "eta": .045, "min_child_weight": 20,
                  "subsample": .85, "colsample_bytree": .9, "lambda": 8,
                  "nthread": 2, "seed": seed}
        booster = xgb.train(params, matrix(train_idx, y), num_boost_round=500,
                            evals=[(matrix(early_idx, y), "early")], early_stopping_rounds=40, verbose_eval=False)
        booster = booster[:booster.best_iteration + 1]
        if binary:
            margin = booster.predict(matrix(cal_idx), output_margin=True)
            calibrator = LogisticRegression(C=1e6, solver="lbfgs").fit(margin.reshape(-1, 1), y[cal_idx])
            slope, intercept = float(calibrator.coef_[0, 0]), float(calibrator.intercept_[0])
            if slope <= 0:
                raise ValueError("Calibration reverses risk ordering; investigate simulator/model.")
            metadata["calibration"][name] = {"slope": slope, "intercept": intercept}
            pred = sigmoid(slope * booster.predict(matrix(test_idx), output_margin=True) + intercept)
            metrics["models"][name] = binary_metrics(y[test_idx], pred)
        else:
            pred = np.clip(booster.predict(matrix(test_idx)), 0, 100)
            metrics["models"][name] = {"mae_internal_score_points": float(mean_absolute_error(y[test_idx], pred))}
        booster.save_model(out_dir / MODEL_FILES[name])
    for filename, value in [("metadata.json", metadata), ("metrics.json", metrics)]:
        (out_dir / filename).write_text(json.dumps(value, indent=2), encoding="utf-8")
    if export_data:
        path = Path(export_data)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.writer(fp)
            writer.writerow(["demo_id", *FEATURES, "synthetic_approval", "synthetic_90day_arrears_12m", "synthetic_health_12m"])
            for i, row in enumerate(rows):
                writer.writerow([f"DEMO{i:05d}", *[row[k] for k in FEATURES], int(approval[i]), int(arrears[i]), float(health[i])])
    return metrics


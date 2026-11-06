"""Train Ridge model with a PROPER evaluation (hold-out + cross-validation).

Run:  uv run python -m app.train
"""
import json

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.model import (
    ARTIFACT_PATH, CATEGORICAL, DATA_PATH, FEATURES, METRICS_PATH, NUMERIC, TARGET,
)

RANDOM_STATE = 42
TEST_SIZE = 0.2
CV_FOLDS = 5


def build_pipeline() -> Pipeline:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    pre = ColumnTransformer([
        ("num", numeric, NUMERIC),
        ("cat", categorical, CATEGORICAL),
    ])
    return Pipeline([("pre", pre), ("model", Ridge(alpha=1.0))])


def scores(pipe: Pipeline, X, y) -> dict:
    pred = pipe.predict(X)
    return {"r2": float(r2_score(y, pred)), "mae": float(mean_absolute_error(y, pred))}


def main() -> None:
    df = pd.read_csv(DATA_PATH)
    df = df[FEATURES + [TARGET]].dropna(subset=[TARGET])
    X, y = df[FEATURES], df[TARGET]
    print(f"[train] rows={len(df)}")

    # 1) BASELINE (what the old code did): fit on ALL data, score on the SAME data
    baseline = scores(build_pipeline().fit(X, y), X, y)

    # 2) HOLD-OUT: fit on 80 %, score on the unseen 20 %
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    pipe = build_pipeline().fit(X_tr, y_tr)
    train_m, test_m = scores(pipe, X_tr, y_tr), scores(pipe, X_te, y_te)

    # 3) 5-FOLD CV: a more stable estimate (the pipeline is refit inside every fold,
    #    so imputers/scaler never see the validation fold -> no leakage)
    cv = cross_validate(
        build_pipeline(), X, y, cv=CV_FOLDS,
        scoring=("r2", "neg_mean_absolute_error"),
    )
    cv_m = {
        "r2_mean": float(cv["test_r2"].mean()), "r2_std": float(cv["test_r2"].std()),
        "mae_mean": float(-cv["test_neg_mean_absolute_error"].mean()),
        "mae_std": float(cv["test_neg_mean_absolute_error"].std()),
    }

    print(f"[train] in-sample  (old, full data) : R2={baseline['r2']:.4f}  MAE={baseline['mae']:,.0f} USD")
    print(f"[train] hold-out TRAIN ({1-TEST_SIZE:.0%})        : R2={train_m['r2']:.4f}  MAE={train_m['mae']:,.0f} USD")
    print(f"[train] hold-out TEST  ({TEST_SIZE:.0%}, unseen) : R2={test_m['r2']:.4f}  MAE={test_m['mae']:,.0f} USD")
    print(f"[train] {CV_FOLDS}-fold CV                    : R2={cv_m['r2_mean']:.4f}+-{cv_m['r2_std']:.4f}  "
          f"MAE={cv_m['mae_mean']:,.0f}+-{cv_m['mae_std']:,.0f} USD")

    gap_r2 = train_m["r2"] - test_m["r2"]
    gap_mae = test_m["mae"] / train_m["mae"] - 1
    print(f"[train] generalization gap: dR2={gap_r2:+.4f}, MAE on test is {gap_mae:+.1%} vs train")
    if gap_r2 > 0.10:
        print("[train] VERDICT: noticeable overfitting")
    else:
        print("[train] VERDICT: no significant overfitting (gap small); "
              "remaining error is bias/limited features, not memorisation")

    # Final artifact: metrics above come from the hold-out/CV procedure; the
    # production model is then refit on ALL available data (standard practice).
    final = build_pipeline().fit(X, y)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, ARTIFACT_PATH)
    METRICS_PATH.write_text(json.dumps({
        "baseline_in_sample": baseline, "holdout_train": train_m,
        "holdout_test": test_m, "cv": cv_m,
    }, indent=2))
    print(f"[train] artifact persisted: {ARTIFACT_PATH}")


if __name__ == "__main__":
    main()

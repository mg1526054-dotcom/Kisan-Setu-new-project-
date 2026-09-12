"""
Trains:
  1. A seasonal-naive baseline (same-week-last-year average) — always reported
     alongside the real model so we can prove the ML model earns its keep.
  2. Two XGBoost quantile-regression models (10th and 90th percentile) that
     together form the predicted price RANGE, plus a median model for the
     point estimate used in charts.

Validation is a walk-forward, time-ordered split — never a random shuffle —
to avoid leaking future prices into training.
"""
import sys
import os
import json
import joblib
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ml.features import load_price_weather_frame, build_features, FEATURE_COLS, TARGET_COL

MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "artifacts"))
os.makedirs(MODEL_DIR, exist_ok=True)


def seasonal_naive_baseline(df: pd.DataFrame) -> pd.Series:
    """Predicts this week's price as the mean of the same ISO week in prior years,
    per crop+market — a classic, hard-to-beat agricultural forecasting baseline."""
    df = df.copy()
    df["year"] = df["date"].dt.year
    lookup = df.groupby(["crop_id", "market_id", "week_of_year"])[TARGET_COL].mean()
    keys = list(zip(df["crop_id"], df["market_id"], df["week_of_year"]))
    values = [lookup.get(k, np.nan) for k in keys]
    return pd.Series(values, index=df.index)


def mape(y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    mask = y_true != 0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def walk_forward_split(df: pd.DataFrame, holdout_frac=0.2):
    df = df.sort_values("date")
    cutoff_idx = int(len(df) * (1 - holdout_frac))
    cutoff_date = df.iloc[cutoff_idx]["date"]
    train = df[df["date"] < cutoff_date]
    test = df[df["date"] >= cutoff_date]
    return train, test


def train_quantile_model(X_train, y_train, quantile: float) -> XGBRegressor:
    model = XGBRegressor(
        objective="reg:quantileerror",
        quantile_alpha=quantile,
        n_estimators=250,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
    )
    model.fit(X_train, y_train)
    return model


def run():
    print("Loading data from database...")
    raw = load_price_weather_frame()
    df = build_features(raw)
    print(f"Feature frame: {df.shape[0]} rows, {df.shape[1]} columns")

    train_df, test_df = walk_forward_split(df, holdout_frac=0.2)
    X_train, y_train = train_df[FEATURE_COLS], train_df[TARGET_COL]
    X_test, y_test = test_df[FEATURE_COLS], test_df[TARGET_COL]

    print(f"Train rows: {len(train_df)}  Test rows: {len(test_df)}")

    # --- Baseline ---
    baseline_pred = seasonal_naive_baseline(df).loc[test_df.index]
    baseline_pred = baseline_pred.fillna(y_train.mean())
    baseline_mae = float(np.mean(np.abs(y_test.values - baseline_pred.values)))
    baseline_mape = mape(y_test.values, baseline_pred.values)

    # --- Median (point-estimate) model ---
    median_model = train_quantile_model(X_train, y_train, quantile=0.5)
    median_pred = median_model.predict(X_test)
    model_mae = float(np.mean(np.abs(y_test.values - median_pred)))
    model_rmse = float(np.sqrt(np.mean((y_test.values - median_pred) ** 2)))
    model_mape = mape(y_test.values, median_pred)

    # --- Range models (10th / 90th percentile -> the predicted price range) ---
    low_model = train_quantile_model(X_train, y_train, quantile=0.10)
    high_model = train_quantile_model(X_train, y_train, quantile=0.90)

    # Coverage check: how often does the actual price fall inside our predicted range?
    low_pred = low_model.predict(X_test)
    high_pred = high_model.predict(X_test)
    coverage = float(np.mean((y_test.values >= low_pred) & (y_test.values <= high_pred)))

    metrics = {
        "baseline_mae": round(baseline_mae, 2),
        "baseline_mape_pct": round(baseline_mape, 2),
        "model_mae": round(model_mae, 2),
        "model_rmse": round(model_rmse, 2),
        "model_mape_pct": round(model_mape, 2),
        "range_coverage_pct": round(coverage * 100, 1),
        "n_train": len(train_df),
        "n_test": len(test_df),
    }
    print(json.dumps(metrics, indent=2))

    joblib.dump(median_model, os.path.join(MODEL_DIR, "median_model.joblib"))
    joblib.dump(low_model, os.path.join(MODEL_DIR, "low_model.joblib"))
    joblib.dump(high_model, os.path.join(MODEL_DIR, "high_model.joblib"))
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    with open(os.path.join(MODEL_DIR, "feature_cols.json"), "w") as f:
        json.dump(FEATURE_COLS, f)

    print(f"\nModels saved to {MODEL_DIR}")
    print(f"Model beats baseline by "
          f"{round((1 - model_mae / baseline_mae) * 100, 1)}% lower MAE."
          if baseline_mae > 0 else "")


if __name__ == "__main__":
    run()

import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ml.features import load_price_weather_frame, build_features, FEATURE_COLS
from ml.explain import top_drivers, confidence_from_range, risk_level_from_confidence

MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ml", "artifacts"))

_median_model = None
_low_model = None
_high_model = None
_metrics = None


def _load_models():
    global _median_model, _low_model, _high_model, _metrics
    if _median_model is None:
        _median_model = joblib.load(os.path.join(MODEL_DIR, "median_model.joblib"))
        _low_model = joblib.load(os.path.join(MODEL_DIR, "low_model.joblib"))
        _high_model = joblib.load(os.path.join(MODEL_DIR, "high_model.joblib"))
        with open(os.path.join(MODEL_DIR, "metrics.json")) as f:
            _metrics = json.load(f)
    return _median_model, _low_model, _high_model, _metrics


def latest_feature_row(crop_id: int, market_id: int, target_date: date) -> pd.DataFrame:
    """Builds a single feature row representing 'the latest known state' for
    this crop/market, projected forward to target_date's week-of-year /
    month so the model conditions its prediction on the right season."""
    raw = load_price_weather_frame(crop_id=crop_id, market_id=market_id)
    if raw.empty:
        raise ValueError("No historical data for this crop/market combination.")
    feats = build_features(raw)
    if feats.empty:
        raise ValueError("Not enough history to build features for this crop/market.")

    last_row = feats.iloc[[-1]].copy()
    last_row["week_of_year"] = target_date.isocalendar().week
    last_row["month"] = target_date.month
    return last_row, feats


def historical_volatility(feats: pd.DataFrame) -> float:
    return float(feats["modal_price"].tail(26).std() or 0.0)


def generate_advisory(predicted_min, predicted_max, historical_recent_mean, risk_level) -> str:
    mid = (predicted_min + predicted_max) / 2
    if mid > historical_recent_mean * 1.05:
        return "Prices are trending above the recent average — consider waiting to sell if storage allows."
    if mid < historical_recent_mean * 0.95:
        return "Prices are trending below the recent average — selling soon may avoid further softening."
    return "Prices look broadly stable near the recent average — timing is flexible."


def compute_forecast(crop_id: int, market_id: int, target_date: date = None):
    if target_date is None:
        target_date = date.today() + timedelta(days=7)

    median_model, low_model, high_model, metrics = _load_models()
    last_row, feats_history = latest_feature_row(crop_id, market_id, target_date)

    X = last_row[FEATURE_COLS]
    median_pred = float(median_model.predict(X)[0])
    low_pred = float(low_model.predict(X)[0])
    high_pred = float(high_model.predict(X)[0])

    if high_pred < low_pred:
        low_pred, high_pred = high_pred, low_pred
    low_pred = min(low_pred, median_pred - 1)
    high_pred = max(high_pred, median_pred + 1)

    vol = historical_volatility(feats_history)
    confidence = confidence_from_range(low_pred, high_pred, vol)
    risk = risk_level_from_confidence(confidence)

    drivers = top_drivers(median_model, last_row, FEATURE_COLS, top_n=3)
    recent_mean = float(feats_history["modal_price"].tail(8).mean())
    advisory = generate_advisory(low_pred, high_pred, recent_mean, risk)

    return {
        "target_date": target_date,
        "predicted_min": round(low_pred, 2),
        "predicted_max": round(high_pred, 2),
        "predicted_median": round(median_pred, 2),
        "confidence": confidence,
        "risk_level": risk,
        "drivers": drivers,
        "advisory": advisory,
        "model_metrics": metrics,
    }

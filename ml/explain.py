"""
Explainability layer: turns a trained XGBoost model's per-prediction feature
contributions into short, farmer-readable sentences.

Uses XGBoost's built-in `pred_contribs` (SHAP-equivalent additive
contributions) so we get a true per-prediction explanation, not just global
feature importance.
"""
import numpy as np
import pandas as pd
from xgboost import DMatrix

FRIENDLY_NAMES = {
    "week_of_year": "seasonal timing",
    "month": "seasonal timing",
    "lag_1": "last week's price",
    "lag_2": "price two weeks ago",
    "lag_4": "price a month ago",
    "roll_mean_4": "the recent 4-week average price",
    "roll_std_4": "recent price volatility",
    "momentum": "the recent price trend",
    "rainfall_mm": "current rainfall",
    "rainfall_deviation": "rainfall compared to the seasonal average",
    "temp_min_c": "night-time temperature",
    "temp_max_c": "day-time temperature",
    "arrivals_lag_1": "last week's market arrivals",
    "arrival_trend": "the change in market arrivals",
}


def top_drivers(model, X_row: pd.DataFrame, feature_cols, top_n=3):
    """Returns a list of {feature, contribution, direction, sentence} for the
    top_n most influential features behind a single prediction."""
    booster = model.get_booster()
    dmat = DMatrix(X_row[feature_cols], feature_names=feature_cols)
    contribs = booster.predict(dmat, pred_contribs=True)[0]  # last value = bias term
    feature_contribs = list(zip(feature_cols, contribs[:-1]))
    feature_contribs.sort(key=lambda x: abs(x[1]), reverse=True)

    drivers = []
    for feat, contrib in feature_contribs[:top_n]:
        direction = "upward" if contrib > 0 else "downward"
        friendly = FRIENDLY_NAMES.get(feat, feat)
        sentence = f"{friendly.capitalize()} is pushing the price {direction} " \
                   f"(impact: {'+' if contrib > 0 else ''}₹{contrib:.0f}/quintal)."
        drivers.append({
            "feature": feat,
            "friendly_name": friendly,
            "contribution": round(float(contrib), 2),
            "direction": direction,
            "sentence": sentence,
        })
    return drivers


def confidence_from_range(low: float, high: float, historical_volatility: float) -> float:
    """Confidence is higher when the predicted range is narrow *relative to
    the predicted price itself* — a ₹200 range means very different things
    for a ₹1,000 crop vs a ₹6,000 crop, so we normalise by the midpoint
    rather than comparing raw rupee widths."""
    mid = max((low + high) / 2, 1.0)
    relative_width = (high - low) / mid  # e.g. 0.15 = range is 15% of the price

    if relative_width <= 0.10:
        confidence = 0.90
    elif relative_width <= 0.20:
        confidence = 0.78
    elif relative_width <= 0.35:
        confidence = 0.62
    elif relative_width <= 0.50:
        confidence = 0.48
    else:
        confidence = 0.35
    return round(float(confidence), 2)


def risk_level_from_confidence(confidence: float) -> str:
    if confidence >= 0.75:
        return "Low"
    if confidence >= 0.55:
        return "Medium"
    return "High"

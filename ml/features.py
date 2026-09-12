"""
Feature engineering for KisanSetu's price forecasting model.

Reads price + weather history straight from the database (not flat files),
so retraining always reflects the latest ingested data.
"""
import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.database import SessionLocal, PriceRecord, WeatherRecord, Crop, Market


def load_price_weather_frame(crop_id: int = None, market_id: int = None) -> pd.DataFrame:
    """Pulls price + weather history from the DB into a single dataframe,
    optionally filtered to one crop/market (used at inference time)."""
    db = SessionLocal()
    try:
        q = db.query(
            PriceRecord.date, PriceRecord.crop_id, PriceRecord.market_id,
            PriceRecord.min_price, PriceRecord.max_price, PriceRecord.modal_price,
            PriceRecord.arrivals_qty,
        )
        if crop_id is not None:
            q = q.filter(PriceRecord.crop_id == crop_id)
        if market_id is not None:
            q = q.filter(PriceRecord.market_id == market_id)
        prices = pd.DataFrame(q.all(), columns=[
            "date", "crop_id", "market_id", "min_price", "max_price",
            "modal_price", "arrivals_qty",
        ])

        wq = db.query(WeatherRecord.date, WeatherRecord.market_id,
                       WeatherRecord.rainfall_mm, WeatherRecord.temp_min_c,
                       WeatherRecord.temp_max_c)
        if market_id is not None:
            wq = wq.filter(WeatherRecord.market_id == market_id)
        weather = pd.DataFrame(wq.all(), columns=[
            "date", "market_id", "rainfall_mm", "temp_min_c", "temp_max_c",
        ])
    finally:
        db.close()

    prices["date"] = pd.to_datetime(prices["date"])
    weather["date"] = pd.to_datetime(weather["date"])
    df = pd.merge_asof(
        prices.sort_values("date"),
        weather.sort_values("date"),
        on="date", by="market_id", direction="nearest",
    )
    return df.sort_values(["crop_id", "market_id", "date"]).reset_index(drop=True)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Adds lag prices, seasonality, rainfall deviation, arrival trend and
    market-momentum features. Operates per crop+market group to avoid
    leaking one market's history into another's lags."""
    df = df.copy()
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["month"] = df["date"].dt.month

    group_cols = ["crop_id", "market_id"]
    df = df.sort_values(group_cols + ["date"])

    g = df.groupby(group_cols)["modal_price"]
    df["lag_1"] = g.shift(1)
    df["lag_2"] = g.shift(2)
    df["lag_4"] = g.shift(4)
    df["roll_mean_4"] = g.transform(lambda s: s.shift(1).rolling(4, min_periods=1).mean())
    df["roll_std_4"] = g.transform(lambda s: s.shift(1).rolling(4, min_periods=1).std())
    df["momentum"] = df["lag_1"] - df["lag_2"]

    rain_avg = df.groupby(["market_id", "week_of_year"])["rainfall_mm"].transform("mean")
    df["rainfall_deviation"] = df["rainfall_mm"] - rain_avg

    ga = df.groupby(group_cols)["arrivals_qty"]
    df["arrival_trend"] = ga.shift(1) - ga.shift(2)
    df["arrivals_lag_1"] = ga.shift(1)

    df = df.dropna(subset=["lag_1", "lag_2", "lag_4", "roll_mean_4"]).reset_index(drop=True)
    return df


FEATURE_COLS = [
    "week_of_year", "month", "lag_1", "lag_2", "lag_4", "roll_mean_4",
    "roll_std_4", "momentum", "rainfall_mm", "rainfall_deviation",
    "temp_min_c", "temp_max_c", "arrivals_lag_1", "arrival_trend",
]
TARGET_COL = "modal_price"

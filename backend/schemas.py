from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class CropOut(BaseModel):
    id: int
    name: str
    class Config:
        from_attributes = True


class MarketOut(BaseModel):
    id: int
    name: str
    district: str
    state: str
    class Config:
        from_attributes = True


class HistoryPoint(BaseModel):
    date: date
    modal_price: float
    min_price: float
    max_price: float
    arrivals_qty: float


class ForecastRequest(BaseModel):
    crop_id: int
    market_id: int
    target_date: Optional[date] = None  # defaults to "today + 7 days" if omitted


class DriverOut(BaseModel):
    feature: str
    friendly_name: str
    contribution: float
    direction: str
    sentence: str


class ForecastResponse(BaseModel):
    crop: str
    market: str
    target_date: date
    predicted_min: float
    predicted_max: float
    predicted_median: float
    confidence: float
    risk_level: str
    drivers: List[DriverOut]
    advisory: str
    model_metrics: dict
    disclaimer: str = "Illustrative forecast from a demo model trained on synthetic data — validate against live AGMARKNET/e-NAM data before real-world use."

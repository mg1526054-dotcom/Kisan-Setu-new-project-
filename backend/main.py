import os
import sys
import json
from datetime import date
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.database import get_db, init_db, SessionLocal, Crop, Market, PriceRecord, ForecastLog
from backend.schemas import CropOut, MarketOut, HistoryPoint, ForecastRequest, ForecastResponse
from backend.services.forecast import compute_forecast

app = FastAPI(title="KisanSetu API", version="1.0.0",
              description="AI-based crop price forecasting & market intelligence for SIH26132.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ml", "artifacts"))
REQUIRED_MODEL_FILES = ["median_model.joblib", "low_model.joblib", "high_model.joblib", "metrics.json"]


def _database_is_empty() -> bool:
    db = SessionLocal()
    try:
        return db.query(Crop).count() == 0
    finally:
        db.close()


def _models_are_missing() -> bool:
    return not all(os.path.exists(os.path.join(MODEL_DIR, f)) for f in REQUIRED_MODEL_FILES)


@app.on_event("startup")
def on_startup():
    """Self-healing startup: many free hosting tiers (e.g. Render's free plan)
    wipe the filesystem between deploys/restarts, so we can't rely solely on
    a one-time build-step to seed the database or train the model. Instead,
    every time the app boots, it checks whether the data/model are present
    and (re)builds them if not. This makes the app resilient regardless of
    the platform's build-command configuration."""
    init_db()

    if _database_is_empty():
        print("[startup] Database is empty — seeding synthetic mandi/weather data...")
        from data.seed import run as seed_run
        seed_run()
        print("[startup] Seeding complete.")

    if _models_are_missing():
        print("[startup] Trained model artifacts missing — training now (first boot may take ~30-60s)...")
        from ml.train import run as train_run
        train_run()
        print("[startup] Training complete.")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/crops", response_model=List[CropOut])
def get_crops(db: Session = Depends(get_db)):
    return db.query(Crop).order_by(Crop.name).all()


@app.get("/api/markets", response_model=List[MarketOut])
def get_markets(crop: Optional[str] = Query(None, description="Crop name to filter markets that have data for it"),
                 db: Session = Depends(get_db)):
    q = db.query(Market)
    if crop:
        crop_obj = db.query(Crop).filter(Crop.name == crop).first()
        if not crop_obj:
            raise HTTPException(status_code=404, detail=f"Unknown crop: {crop}")
        market_ids = {p.market_id for p in db.query(PriceRecord.market_id)
                      .filter(PriceRecord.crop_id == crop_obj.id).distinct()}
        q = q.filter(Market.id.in_(market_ids))
    return q.order_by(Market.name).all()


@app.get("/api/history", response_model=List[HistoryPoint])
def get_history(crop_id: int, market_id: int,
                 from_date: Optional[date] = None, to_date: Optional[date] = None,
                 db: Session = Depends(get_db)):
    q = db.query(PriceRecord).filter(
        PriceRecord.crop_id == crop_id, PriceRecord.market_id == market_id
    )
    if from_date:
        q = q.filter(PriceRecord.date >= from_date)
    if to_date:
        q = q.filter(PriceRecord.date <= to_date)
    rows = q.order_by(PriceRecord.date).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No history found for this crop/market combination.")
    return [
        HistoryPoint(date=r.date, modal_price=r.modal_price, min_price=r.min_price,
                     max_price=r.max_price, arrivals_qty=r.arrivals_qty)
        for r in rows
    ]


@app.post("/api/forecast", response_model=ForecastResponse)
def post_forecast(req: ForecastRequest, db: Session = Depends(get_db)):
    crop_obj = db.query(Crop).filter(Crop.id == req.crop_id).first()
    market_obj = db.query(Market).filter(Market.id == req.market_id).first()
    if not crop_obj or not market_obj:
        raise HTTPException(status_code=404, detail="Unknown crop_id or market_id.")

    try:
        result = compute_forecast(req.crop_id, req.market_id, req.target_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    resolved_target_date = result["target_date"]

    log = ForecastLog(
        crop_id=req.crop_id, market_id=req.market_id,
        target_date=resolved_target_date,
        predicted_min=result["predicted_min"], predicted_max=result["predicted_max"],
        confidence=result["confidence"], risk_level=result["risk_level"],
        drivers_json=json.dumps(result["drivers"]),
    )
    db.add(log)
    db.commit()

    return ForecastResponse(
        crop=crop_obj.name, market=market_obj.name,
        target_date=resolved_target_date,
        predicted_min=result["predicted_min"], predicted_max=result["predicted_max"],
        predicted_median=result["predicted_median"], confidence=result["confidence"],
        risk_level=result["risk_level"], drivers=result["drivers"],
        advisory=result["advisory"], model_metrics=result["model_metrics"],
    )


# --- Serve the simple frontend ---
app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "templates", "index.html"))

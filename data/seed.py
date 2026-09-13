"""
Seeds the KisanSetu database with realistic *synthetic* mandi price, arrivals,
and weather data for 5 crops across 5 Maharashtra markets, spanning 3 years
of weekly observations.

WHY SYNTHETIC DATA: live scraping of AGMARKNET/e-NAM requires network access
and API keys not available in every environment. This generator produces
data with realistic seasonality, trend, and noise so the full pipeline
(features -> model -> API -> UI) can be built, tested, and demoed end to end.
Swap this script for a real AGMARKNET/e-NAM ingestion job when live data
access is available — the downstream schema does not need to change.
"""
import sys
import os
import math
import random
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.database import Base, engine, SessionLocal, Crop, Market, PriceRecord, WeatherRecord

random.seed(42)

MARKETS = [
    {"name": "Pune APMC", "district": "Pune", "lat": 18.5204, "lon": 73.8567},
    {"name": "Nashik Mandi", "district": "Nashik", "lat": 19.9975, "lon": 73.7898},
    {"name": "Nagpur Market", "district": "Nagpur", "lat": 21.1458, "lon": 79.0882},
    {"name": "Solapur Mandi", "district": "Solapur", "lat": 17.6599, "lon": 75.9064},
    {"name": "Aurangabad APMC", "district": "Chhatrapati Sambhajinagar", "lat": 19.8762, "lon": 75.3433},
    {"name": "Mumbai APMC (Vashi)", "district": "Thane", "lat": 19.0760, "lon": 72.9981},
    {"name": "Kolhapur APMC", "district": "Kolhapur", "lat": 16.7050, "lon": 74.2433},
    {"name": "Amravati Mandi", "district": "Amravati", "lat": 20.9374, "lon": 77.7796},
    {"name": "Latur APMC", "district": "Latur", "lat": 18.4088, "lon": 76.5604},
    {"name": "Jalgaon APMC", "district": "Jalgaon", "lat": 21.0077, "lon": 75.5626},
    {"name": "Ahmednagar Mandi", "district": "Ahmednagar", "lat": 19.0948, "lon": 74.7480},
    {"name": "Nanded APMC", "district": "Nanded", "lat": 19.1383, "lon": 77.3210},
    {"name": "Akola APMC", "district": "Akola", "lat": 20.7002, "lon": 77.0082},
    {"name": "Satara Mandi", "district": "Satara", "lat": 17.6805, "lon": 74.0183},
    {"name": "Sangli APMC", "district": "Sangli", "lat": 16.8524, "lon": 74.5815},
]

# base_price: typical modal price (Rs/quintal); vol: relative volatility;
# season_peak_week: ISO week where seasonal price tends to peak (pre-harvest scarcity)
CROPS = [
    {"name": "Potato", "base_price": 1200, "vol": 0.18, "season_peak_week": 30},
    {"name": "Onion", "base_price": 1500, "vol": 0.30, "season_peak_week": 40},
    {"name": "Tomato", "base_price": 1400, "vol": 0.35, "season_peak_week": 15},
    {"name": "Soybean", "base_price": 4200, "vol": 0.12, "season_peak_week": 45},
    {"name": "Cotton", "base_price": 6800, "vol": 0.10, "season_peak_week": 48},
    {"name": "Wheat", "base_price": 2200, "vol": 0.08, "season_peak_week": 20},
    {"name": "Rice (Paddy)", "base_price": 2100, "vol": 0.09, "season_peak_week": 42},
    {"name": "Maize", "base_price": 1850, "vol": 0.14, "season_peak_week": 38},
    {"name": "Sugarcane", "base_price": 315, "vol": 0.05, "season_peak_week": 50},
    {"name": "Tur (Arhar)", "base_price": 7200, "vol": 0.15, "season_peak_week": 10},
    {"name": "Gram (Chana)", "base_price": 5300, "vol": 0.11, "season_peak_week": 18},
    {"name": "Groundnut", "base_price": 6100, "vol": 0.13, "season_peak_week": 44},
    {"name": "Mustard", "base_price": 5450, "vol": 0.12, "season_peak_week": 14},
    {"name": "Turmeric", "base_price": 13500, "vol": 0.22, "season_peak_week": 22},
    {"name": "Garlic", "base_price": 9500, "vol": 0.32, "season_peak_week": 28},
    {"name": "Ginger", "base_price": 7800, "vol": 0.28, "season_peak_week": 35},
    {"name": "Green Chili", "base_price": 3200, "vol": 0.30, "season_peak_week": 25},
]

START_DATE = date(2023, 1, 1)
END_DATE = date(2026, 1, 1)


def seasonal_factor(day_of_year, peak_week):
    """Smooth seasonal multiplier peaking around `peak_week`."""
    peak_day = peak_week * 7
    diff = abs(day_of_year - peak_day)
    diff = min(diff, 365 - diff)
    return 1.0 + 0.25 * math.cos(diff / 365 * 2 * math.pi)


def rainfall_for(day_of_year, market_seed):
    """Rough monsoon-shaped rainfall curve (heavier Jun-Sep) + noise."""
    month = date(2024, 1, 1).replace(day=1)
    doy = day_of_year
    monsoon_center = 200  # ~mid-July
    monsoon = max(0, 40 * math.exp(-((doy - monsoon_center) ** 2) / (2 * 55 ** 2)))
    noise = random.uniform(0, 8) if random.random() > 0.6 else 0
    return round(max(0, monsoon + noise + market_seed), 1)


def temp_for(day_of_year):
    base = 27 + 6 * math.cos((day_of_year - 30) / 365 * 2 * math.pi)
    tmin = base - random.uniform(4, 7)
    tmax = base + random.uniform(4, 7)
    return round(tmin, 1), round(tmax, 1)


def run():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    market_objs = {}
    for m in MARKETS:
        obj = Market(name=m["name"], district=m["district"], state="Maharashtra",
                     latitude=m["lat"], longitude=m["lon"])
        db.add(obj)
        market_objs[m["name"]] = obj
    db.commit()

    crop_objs = {}
    for c in CROPS:
        obj = Crop(name=c["name"])
        db.add(obj)
        crop_objs[c["name"]] = obj
    db.commit()

    price_rows, weather_rows = [], []

    for m_idx, m in enumerate(MARKETS):
        market_obj = market_objs[m["name"]]
        market_seed = m_idx * 1.3  # small deterministic offset per market
        d = START_DATE
        while d <= END_DATE:
            doy = d.timetuple().tm_yday
            rain = rainfall_for(doy, market_seed)
            tmin, tmax = temp_for(doy)
            weather_rows.append(WeatherRecord(
                date=d, market=market_obj, rainfall_mm=rain,
                temp_min_c=tmin, temp_max_c=tmax,
            ))
            d += timedelta(days=7)  # weekly weather record

    for c in CROPS:
        crop_obj = crop_objs[c["name"]]
        for m_idx, m in enumerate(MARKETS):
            market_obj = market_objs[m["name"]]
            trend_drift = random.uniform(-0.03, 0.05)  # slow multi-year drift per crop/market
            d = START_DATE
            week_index = 0
            while d <= END_DATE:
                doy = d.timetuple().tm_yday
                season = seasonal_factor(doy, c["season_peak_week"])
                trend = 1 + trend_drift * (week_index / 52)
                noise = random.gauss(0, c["vol"] * 0.4)
                modal = max(200, c["base_price"] * season * trend * (1 + noise))
                spread = modal * random.uniform(0.05, 0.12)
                min_p = round(modal - spread, 2)
                max_p = round(modal + spread, 2)

                base_arrival = 4000 + 2000 * (1 / season)  # more arrivals -> softer price
                arrivals = max(200, round(base_arrival * random.uniform(0.7, 1.3), 1))

                price_rows.append(PriceRecord(
                    date=d, crop=crop_obj, market=market_obj,
                    min_price=min_p, max_price=max_p, modal_price=round(modal, 2),
                    arrivals_qty=arrivals,
                ))
                d += timedelta(days=7)
                week_index += 1

    db.add_all(weather_rows)
    db.add_all(price_rows)
    db.commit()
    print(f"Seeded {len(MARKETS)} markets, {len(CROPS)} crops, "
          f"{len(price_rows)} price records, {len(weather_rows)} weather records.")
    db.close()


if __name__ == "__main__":
    run()

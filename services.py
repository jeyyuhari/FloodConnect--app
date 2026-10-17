"""
services.py - free, key-less external data sources. Every function fails safe:
on any network / parsing problem it returns None (callers show a friendly fallback).
  * Open-Meteo Geocoding   - place name -> coordinates
  * Open-Meteo Forecast    - 3 day rainfall / wind forecast
  * USGS Earthquake feed   - earthquakes in the last 24 hours (M2.5+)
"""
import requests
from core import haversine

TIMEOUT = 8
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"


def geocode(name, count=5):
    try:
        r = requests.get(GEOCODE_URL, params={"name": name, "count": count, "language": "en", "format": "json"}, timeout=TIMEOUT)
        r.raise_for_status()
        out = []
        for x in r.json().get("results", []) or []:
            out.append({
                "label": ", ".join([p for p in [x.get("name"), x.get("admin1"), x.get("country")] if p]),
                "lat": float(x["latitude"]), "lon": float(x["longitude"]),
                "country": x.get("country"),
            })
        return out
    except Exception:
        return None


def forecast(lat, lon, days=3):
    """Returns {'dates': [...], 'rain_mm': [...], 'wind_kmh': [...]} or None."""
    try:
        r = requests.get(FORECAST_URL, params={
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": days,
            "daily": "precipitation_sum,wind_speed_10m_max"}, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()["daily"]
        return {"dates": d["time"], "rain_mm": d["precipitation_sum"], "wind_kmh": d["wind_speed_10m_max"]}
    except Exception:
        return None


def recent_quakes():
    """List of {'mag','place','lat','lon','time'} for the last 24h, or None."""
    try:
        r = requests.get(USGS_URL, timeout=TIMEOUT)
        r.raise_for_status()
        out = []
        for f in r.json().get("features", []):
            lon, lat = f["geometry"]["coordinates"][:2]
            p = f["properties"]
            out.append({"mag": p.get("mag"), "place": p.get("place"), "lat": lat, "lon": lon, "time": p.get("time")})
        return out
    except Exception:
        return None


def quakes_near(quakes, lat, lon, radius_km=300):
    """Quakes within radius, nearest first, with distance."""
    if not quakes:
        return []
    res = []
    for q in quakes:
        if q["mag"] is None:
            continue
        d = haversine(lat, lon, q["lat"], q["lon"])
        if d <= radius_km:
            res.append({**q, "distance_km": d})
    return sorted(res, key=lambda x: x["distance_km"])

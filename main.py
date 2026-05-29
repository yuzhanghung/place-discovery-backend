"""
Place Discovery & Favorites — FastAPI backend.

Run locally:
    pip install -r requirements.txt
    cp .env.example .env   # fill in values
    uvicorn main:app --reload --port 8000

Required environment variables:
    GEOAPIFY_API_KEY        Geoapify Places API key
    SUPABASE_URL            https://<project-ref>.supabase.co
    SUPABASE_SERVICE_KEY    Supabase service-role key (server-only)
    FRONTEND_ORIGIN         e.g. http://localhost:5173 or your Lovable URL
"""

import os
from typing import Optional, Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ---------- Config ----------
GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")

if not (GEOAPIFY_API_KEY and SUPABASE_URL and SUPABASE_SERVICE_KEY):
    print("⚠️  Missing env vars. Set GEOAPIFY_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY.")

supabase: Client = create_client(SUPABASE_URL or "https://placeholder.supabase.co",
                                  SUPABASE_SERVICE_KEY or "placeholder")

# Geoapify category mapping
CATEGORY_MAP = {
    "restaurants": "catering.restaurant",
    "cafes": "catering.cafe",
    "hotels": "accommodation.hotel",
    "parks": "leisure.park",
    "museums": "entertainment.museum",
    "libraries": "education.library",
    "gyms": "sport.fitness",
    "supermarkets": "commercial.supermarket",
    "hospitals": "healthcare.hospital",
    "attractions": "tourism.attraction",
    "schools": "education.school",
    "gas stations": "service.vehicle.fuel",
}
Category = Literal[
    "restaurants", "cafes", "hotels", "parks", "museums", "libraries",
    "gyms", "supermarkets", "hospitals", "attractions", "schools", "gas stations",
]

app = FastAPI(title="Place Discovery API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Schemas ----------
class Place(BaseModel):
    place_id: str
    name: str
    address: str
    category: str
    latitude: float
    longitude: float


class FavoriteIn(BaseModel):
    place_id: str
    name: str
    address: str
    category: str
    latitude: float
    longitude: float
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None


class FavoritePatch(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None


class WebhookPayload(BaseModel):
    event_type: Optional[str] = None
    data: dict = {}


# ---------- Sync helpers (simple DB ops) ----------
def save_favorite_to_supabase(fav: FavoriteIn) -> dict:
    """Synchronous: insert a favorite row."""
    res = supabase.table("favorites").insert(fav.model_dump()).execute()
    return res.data[0] if res.data else {}


def log_search_history(query: str, category: str) -> None:
    """Synchronous: log a search query."""
    supabase.table("search_history").insert(
        {"search_query": query, "category": category}
    ).execute()


# ---------- Async helpers ----------
async def fetch_places_from_api(location: str, category: Category, limit: int = 20) -> list[Place]:
    """Async: call Geoapify Places API."""
    geoapify_cat = CATEGORY_MAP[category]

    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Geocode the location string -> lat/lon
        geo = await client.get(
            "https://api.geoapify.com/v1/geocode/search",
            params={"text": location, "limit": 1, "apiKey": GEOAPIFY_API_KEY},
        )
        geo.raise_for_status()
        features = geo.json().get("features", [])
        if not features:
            raise HTTPException(status_code=404, detail=f"Location not found: {location}")
        lon, lat = features[0]["geometry"]["coordinates"]

        # 2. Search places nearby
        resp = await client.get(
            "https://api.geoapify.com/v2/places",
            params={
                "categories": geoapify_cat,
                "filter": f"circle:{lon},{lat},5000",
                "bias": f"proximity:{lon},{lat}",
                "limit": limit,
                "apiKey": GEOAPIFY_API_KEY,
            },
        )
        resp.raise_for_status()
        results = []
        for f in resp.json().get("features", []):
            p = f.get("properties", {})
            results.append(Place(
                place_id=p.get("place_id") or f.get("id") or "",
                name=p.get("name") or p.get("address_line1") or "Unnamed",
                address=p.get("formatted") or "",
                category=category,
                latitude=p.get("lat", lat),
                longitude=p.get("lon", lon),
            ))
        return results


async def sync_places_to_supabase(places: list[Place]) -> int:
    """Async: upsert places into the place_cache table."""
    if not places:
        return 0
    rows = [
        {
            "place_id": p.place_id,
            "name": p.name,
            "address": p.address,
            "category": p.category,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "raw_data": p.model_dump(),
        }
        for p in places if p.place_id
    ]
    if not rows:
        return 0
    supabase.table("place_cache").upsert(rows, on_conflict="place_id").execute()
    return len(rows)


async def handle_webhook_event(event_type: str, payload: dict) -> dict:
    """Async: persist a webhook event."""
    res = supabase.table("webhook_events").insert(
        {"event_type": event_type, "payload": payload}
    ).execute()
    return res.data[0] if res.data else {}


# ---------- Routes ----------
@app.get("/")
def root():
    return {"service": "Place Discovery API", "status": "ok"}


@app.get("/places/search", response_model=list[Place])
async def places_search(
    location: str = Query(..., min_length=2, max_length=120),
    category: Category = Query(...),
    limit: int = Query(20, ge=1, le=50),
):
    places = await fetch_places_from_api(location, category, limit)
    log_search_history(location, category)
    return places


@app.post("/favorites")
def create_favorite(fav: FavoriteIn):
    return save_favorite_to_supabase(fav)


@app.get("/favorites")
def list_favorites(category: Optional[Category] = None):
    q = supabase.table("favorites").select("*").order("created_at", desc=True)
    if category:
        q = q.eq("category", category)
    return q.execute().data


@app.patch("/favorites/{favorite_id}")
def update_favorite(favorite_id: UUID, patch: FavoritePatch):
    data = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = supabase.table("favorites").update(data).eq("id", str(favorite_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return res.data[0]


@app.delete("/favorites/{favorite_id}")
def delete_favorite(favorite_id: UUID):
    supabase.table("favorites").delete().eq("id", str(favorite_id)).execute()
    return {"deleted": True}


@app.post("/sync/places")
async def sync_places(location: str, category: Category):
    places = await fetch_places_from_api(location, category)
    count = await sync_places_to_supabase(places)
    # fire-and-forget our own sync-complete webhook log
    await handle_webhook_event("sync-complete", {"location": location, "category": category, "count": count})
    return {"synced": count}


@app.get("/webhook-events")
def list_webhook_events(limit: int = 50):
    return (
        supabase.table("webhook_events")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )


@app.get("/search-history")
def list_search_history(limit: int = 20):
    return (
        supabase.table("search_history")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )


@app.post("/webhooks/place-updated")
async def webhook_place_updated(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    await handle_webhook_event("place-updated", payload)
    return {"success": True}


@app.post("/webhooks/sync-complete")
async def webhook_sync_complete(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    await handle_webhook_event("sync-complete", payload)
    return {"success": True}

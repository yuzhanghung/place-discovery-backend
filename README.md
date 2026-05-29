# Place Discovery & Favorites — Backend

FastAPI + Supabase + Geoapify Places.

## 1. Set up Supabase
1. Create a new project at https://supabase.com.
2. Open **SQL Editor** and run `schema.sql`.
3. Copy your **Project URL** and the **service_role** key (Settings → API).

## 2. Get a Geoapify key
Free tier at https://myprojects.geoapify.com — create an API key for "Places API".

## 3. Run the backend
```bash
cd place-discovery-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your real values
uvicorn main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive Swagger.

## 4. Connect the Lovable frontend
In the Lovable project, set the env var:
```
VITE_BACKEND_URL=http://localhost:8000
```
(or your deployed FastAPI URL — Render, Fly.io, Railway, etc.)

Make sure `FRONTEND_ORIGIN` in `.env` matches your frontend URL so CORS works.

## Endpoints
- `GET /` health check
- `GET /places/search?location=Paris&category=cafes`
- `POST /favorites`
- `GET /favorites?category=cafes`
- `PATCH /favorites/{id}` — body `{ "rating": 5, "notes": "..." }`
- `DELETE /favorites/{id}`
- `POST /sync/places?location=Paris&category=cafes`
- `GET /search-history`
- `GET /webhook-events`
- `POST /webhooks/place-updated`
- `POST /webhooks/sync-complete`

## Architecture notes
- **Sync** functions: `save_favorite_to_supabase`, `log_search_history` — fast DB writes using the sync supabase-py client.
- **Async** functions: `fetch_places_from_api`, `sync_places_to_supabase`, `handle_webhook_event` — anything that may be slow (Geoapify HTTP, batched writes, event handling).
- The **service-role** key is server-only; the frontend never sees it.
- Geoapify key is read from env on the server only.

## Deploy
- **Render / Railway / Fly.io**: deploy `main.py` with `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- Set the four env vars in the host dashboard.

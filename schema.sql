-- Supabase schema for Place Discovery & Favorites
-- Run in the Supabase SQL editor.

create table if not exists public.favorites (
  id uuid primary key default gen_random_uuid(),
  place_id text not null,
  name text not null,
  address text,
  category text not null,
  latitude numeric,
  longitude numeric,
  rating integer check (rating between 1 and 5),
  notes text,
  created_at timestamptz default now()
);

create table if not exists public.search_history (
  id uuid primary key default gen_random_uuid(),
  search_query text not null,
  category text,
  created_at timestamptz default now()
);

create table if not exists public.webhook_events (
  id uuid primary key default gen_random_uuid(),
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz default now()
);

create table if not exists public.place_cache (
  id uuid primary key default gen_random_uuid(),
  place_id text unique not null,
  name text,
  address text,
  category text,
  latitude numeric,
  longitude numeric,
  raw_data jsonb,
  synced_at timestamptz default now()
);

-- The FastAPI backend uses the service role key, so RLS is bypassed.
-- Still enable RLS so the tables are not accidentally exposed via the
-- public anon key if you ever turn the Data API on.
alter table public.favorites enable row level security;
alter table public.search_history enable row level security;
alter table public.webhook_events enable row level security;
alter table public.place_cache enable row level security;

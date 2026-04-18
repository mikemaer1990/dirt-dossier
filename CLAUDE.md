# dirt-dossier

A personal mountain biking dashboard that ingests Strava ride data and matches it against OpenStreetMap trail geometry. Solo-use, local-first, built to eventually scale to a hosted deployment.

## For Claude Code

This file is the authoritative spec for this project. Before taking any action, read this file in full and stay aligned with its scope and constraints. If a user request would contradict this spec, ask for confirmation before proceeding.

## Goals

1. Answer questions Strava cannot answer, specifically per-trail performance over time, bike component wear tracking, and cross-source analytics (ride data + weather + trail metadata).
2. Auto-generate monthly and yearly writeups using the Anthropic API, grounded in the user's actual ride history.
3. Teach the user spatial databases (PostGIS), Python/FastAPI backend work, and end-to-end data pipeline design.
4. Produce a finished, portfolio-worthy project with a clean repo, real data, and a working dashboard.

## Non-goals (out of scope for Phase 1)

- Multi-user support, authentication, or sharing
- Multi-region support (Nanaimo only for now)
- Replacing Strava's core features (segment leaderboards, live tracking, social)
- Public deployment (local PC only during Phase 1)
- Strava webhooks (manual sync only during Phase 1)
- Mobile app
- Real-time live tracking
- Social features

Do not build any of the above without explicit instruction. When in doubt, ask.

## User preferences

- **No em dashes anywhere in code comments, documentation, or generated output.**
- Only list skills and technologies the user can genuinely defend without AI assistance. If the user asks for help with something outside their comfort zone, explain rather than silently implementing complex patterns.
- The user writes casually in chat but expects polished output in repo files.
- Prefer local-first, privacy-respecting solutions.
- The user prefers plain text with standard markdown formatting in documentation, not heavy structured tool output.

## Tech stack (locked in)

### Backend (ingest and API)
- Python 3.12
- FastAPI for the HTTP API (Phase 2+, not strictly needed in Phase 1)
- SQLAlchemy 2.0 (async) for ORM
- GeoAlchemy2 for PostGIS integration
- shapely for Python-side geometry work
- httpx for Strava API calls
- osmium-tool (`osmium`) as a CLI dependency for filtering OSM PBF extracts. Install via apt: `sudo apt install osmium-tool`. Python binding `osmium` (pyosmium) for in-script parsing.
- uv for dependency management (faster than pip)

### Frontend (dashboard)
- Next.js 15 with App Router
- TypeScript (strict mode)
- Tailwind CSS
- Drizzle ORM for the database client
- React Server Components by default, client components only where needed
- Leaflet or MapLibre for map rendering (both are free, no API key required for basic use)

### Database
- Postgres 16
- PostGIS 3.4 extension
- Use the official `postgis/postgis:16-3.4` Docker image

### Infrastructure
- Docker Compose for orchestration
- Single compose file at the repo root
- Services: `db` (Postgres+PostGIS) only in Phase 1. The API runs as a Python process from the user's terminal, not containerized yet, for fast iteration.

### External APIs and data sources
- Strava API v3 (OAuth 2.0, athlete capacity 1 / "Single Player Mode")
- **OpenStreetMap via Geofabrik regional extracts** for trail geometry. Download `british-columbia-latest.osm.pbf` from https://download.geofabrik.de/north-america/canada/british-columbia.html. Filter locally with `osmium` to the Nanaimo bounding box and mountain-bike-relevant tags. No API dependency, no rate limits, no auth. Refresh quarterly.
- Trailforks is NOT a data source for this project. Their free tier does not permit KML export (Pro required, ~$50 CAD/year) and their API is not granted to personal projects. We considered it and deliberately chose OSM instead. Do not add Trailforks as a source without explicit instruction.
- Open-Meteo historical weather API (Phase 2, no key required)
- Anthropic API (Phase 2, for monthly writeups)

## Development environment

The user is on Windows using WSL2 with Ubuntu. All commands in this project assume they run inside WSL, not PowerShell or CMD. The project folder lives inside the WSL filesystem (not `/mnt/c/...`) for file system performance.

If the user has not set up WSL2 yet, the first task is to walk them through it. See `docs/wsl-setup.md` (to be created).

## Repo structure

```
dirt-dossier/
├── CLAUDE.md                    # This file
├── README.md                    # Setup and usage for humans
├── .env.example                 # Environment variable template
├── .gitignore
├── docker-compose.yml           # Postgres + PostGIS service
├── docs/
│   ├── wsl-setup.md             # WSL2 installation guide
│   ├── strava-oauth.md          # How to register Strava app and auth flow
│   ├── osm-import.md            # How to download BC extract and filter Nanaimo trails
│   └── schema.md                # Database schema documentation
├── api/                         # Python backend
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/
│   │   └── dirt_dossier/
│   │       ├── __init__.py
│   │       ├── config.py        # Settings, env vars
│   │       ├── db.py            # SQLAlchemy engine, session
│   │       ├── models.py        # ORM models
│   │       ├── strava.py        # Strava API client
│   │       └── matching.py      # Trail matching logic
│   └── scripts/
│       ├── import_trails.py     # One-time OSM PBF import
│       ├── bootstrap_strava.py  # One-time history backfill
│       ├── sync_recent.py       # Ongoing manual sync
│       ├── match_all.py         # Re-run trail matching for all rides
│       ├── seed_bikes.py        # User fills in bike data
│       └── seed_components.py   # User fills in component data
├── web/                         # Next.js frontend
│   ├── package.json
│   ├── next.config.ts
│   ├── drizzle.config.ts
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx         # Dashboard home
│   │   │   ├── trails/
│   │   │   │   └── [id]/page.tsx
│   │   │   ├── rides/
│   │   │   │   └── [id]/page.tsx
│   │   │   └── garage/
│   │   │       └── page.tsx
│   │   ├── db/
│   │   │   └── schema.ts        # Drizzle schema
│   │   └── lib/
│   └── drizzle/                 # Generated migrations
└── data/
    ├── osm/                     # Downloaded OSM extracts (gitignored)
    └── backups/                 # pg_dump output (gitignored)
```

## Database schema

All tables use SRID 4326 (WGS84 lat/lng) for geometry columns. Store as `GEOMETRY` type, cast to `geography` only for accurate distance/length calculations.

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

-- Trails from OpenStreetMap (via Geofabrik BC extract), one-time import, refreshed quarterly
CREATE TABLE trails (
    id SERIAL PRIMARY KEY,
    osm_way_id BIGINT UNIQUE,  -- OSM way ID, null if manually added
    name TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT 'nanaimo',
    difficulty TEXT,  -- derived from mtb:scale tag where present; null otherwise
    direction TEXT,   -- up, down, both (from oneway tag where present)
    length_m INTEGER,
    descent_m INTEGER,
    ascent_m INTEGER,
    source TEXT NOT NULL DEFAULT 'osm',  -- 'osm', 'manual', or future sources
    raw_tags JSONB,  -- full OSM tag set for reference
    geometry GEOMETRY(LINESTRING, 4326) NOT NULL,
    last_refreshed_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_trails_geometry ON trails USING GIST(geometry);

-- Bikes, seeded manually by user
CREATE TABLE bikes (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    model TEXT,
    year INTEGER,
    strava_gear_id TEXT UNIQUE,
    purchase_date DATE,
    purchase_cost_cad NUMERIC(10, 2),
    notes TEXT
);

-- Components on bikes, for maintenance tracking
CREATE TABLE components (
    id SERIAL PRIMARY KEY,
    bike_id INTEGER REFERENCES bikes(id),
    type TEXT NOT NULL,  -- chain, brake_pad_front, brake_pad_rear, tire_front, tire_rear, fork_service, shock_service, etc
    brand TEXT,
    model TEXT,
    installed_at DATE NOT NULL,
    installed_cost_cad NUMERIC(10, 2),
    replacement_threshold_km NUMERIC,
    replacement_threshold_hours NUMERIC,
    replacement_threshold_days INTEGER,
    current_status TEXT DEFAULT 'active',  -- active, replaced, retired
    notes TEXT
);

-- Maintenance actions log
CREATE TABLE maintenance_log (
    id SERIAL PRIMARY KEY,
    bike_id INTEGER REFERENCES bikes(id),
    component_id INTEGER REFERENCES components(id),
    action TEXT NOT NULL,  -- installed, replaced, serviced, cleaned, inspected
    action_date DATE NOT NULL,
    cost_cad NUMERIC(10, 2),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Activities from Strava
CREATE TABLE activities (
    id SERIAL PRIMARY KEY,
    strava_id BIGINT UNIQUE NOT NULL,
    name TEXT,
    activity_type TEXT NOT NULL,  -- Ride, MountainBikeRide, etc
    start_time TIMESTAMPTZ NOT NULL,
    duration_s INTEGER NOT NULL,
    moving_time_s INTEGER,
    distance_m NUMERIC NOT NULL,
    elevation_gain_m NUMERIC,
    avg_speed_mps NUMERIC,
    max_speed_mps NUMERIC,
    avg_heartrate NUMERIC,
    max_heartrate NUMERIC,
    bike_id INTEGER REFERENCES bikes(id),
    strava_gear_id TEXT,
    weather JSONB,  -- filled by Phase 2 enrichment
    geometry GEOMETRY(LINESTRING, 4326),
    raw_summary JSONB,  -- full Strava response for reference
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_activities_geometry ON activities USING GIST(geometry);
CREATE INDEX idx_activities_start_time ON activities(start_time DESC);

-- Trail matches per activity, computed at ingest time
CREATE TABLE activity_trails (
    id SERIAL PRIMARY KEY,
    activity_id INTEGER REFERENCES activities(id) ON DELETE CASCADE,
    trail_id INTEGER REFERENCES trails(id),
    overlap_m NUMERIC NOT NULL,
    overlap_pct NUMERIC NOT NULL,
    elapsed_s INTEGER,  -- time on trail, computed from stream walk
    avg_speed_mps NUMERIC,
    direction TEXT,  -- up, down (inferred from elevation delta)
    matched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (activity_id, trail_id)
);
CREATE INDEX idx_activity_trails_activity ON activity_trails(activity_id);
CREATE INDEX idx_activity_trails_trail ON activity_trails(trail_id);

-- Strava auth tokens, one row
CREATE TABLE strava_auth (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- single row enforcement
    athlete_id BIGINT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Phase 1 milestones

Build in this order. Do not skip ahead. Each week has a "done when" criterion that must be met before moving on.

### Week 1: Foundation

**Done when:**
- WSL2 is installed and the user can run `docker compose up -d` successfully
- Postgres+PostGIS container is running and reachable at `localhost:5432`
- Python `api/` project is set up with `uv`, all dependencies install cleanly
- Initial database migration runs and creates all tables
- A trivial script (`scripts/healthcheck.py`) connects to the DB and prints `PostGIS version: 3.4.x`

Do not proceed until the user confirms the healthcheck runs.

### Week 2: Data ingest

**Done when:**
- A new Alembic migration renames `trails.trailforks_id` to `trails.osm_way_id` (BIGINT), adds `trails.source` column (TEXT, default 'osm'), and adds `trails.raw_tags` column (JSONB). The ORM model and any script stubs are updated to match.
- User has downloaded the BC extract from Geofabrik (see `docs/osm-import.md`) and placed it at `data/osm/british-columbia-latest.osm.pbf`
- `scripts/import_trails.py` uses `osmium` to filter the BC extract to a Nanaimo bounding box and MTB-relevant tags, parses the result, and populates the `trails` table with geometries, names, OSM way IDs, difficulty (from `mtb:scale` where present), and raw tags
- User has registered a Strava app and added credentials to `.env` (see `docs/strava-oauth.md`)
- OAuth flow completes, tokens are stored in `strava_auth` table
- `scripts/bootstrap_strava.py` successfully backfills the user's entire Strava history into `activities` (respecting rate limits with sleep-and-retry)
- User can query both tables with counts that make intuitive sense

### Week 3: Trail matching

**Done when:**
- `api/src/dirt_dossier/matching.py` implements the PostGIS trail matching query
- `scripts/match_all.py` runs matching for every activity and populates `activity_trails`
- User manually verifies three recent rides: pick rides where they remember which trails they rode, run a query showing matches, confirm the results are correct
- Buffer size and overlap threshold are tuned based on verification (default 20m buffer, 50m minimum overlap, will likely need adjustment)

### Week 4: Dashboard v1

**Done when:**
- Next.js app is set up in `web/`, Drizzle connects to the same Postgres DB
- `/` dashboard page shows: most recent ride with basic stats, total distance this month, total rides this year, count of unique trails ridden
- `/rides/[id]` page shows: ride summary, a map with the route (Leaflet or MapLibre with OpenStreetMap tiles), list of trails matched
- `/trails/[id]` page shows: trail name, your history of rides on this trail, best/worst/avg time per direction
- User runs `npm run dev` and can browse their own data in a browser

Phase 1 complete. Pause and celebrate.

## Phase 2 and beyond (not yet in scope)

These are planned but should not be built until Phase 1 is fully complete and stable.

- Weather enrichment via Open-Meteo (store in `activities.weather` JSONB)
- Bike and component management UI (currently seed scripts only)
- Maintenance reminder logic (flag components over threshold)
- Garage page showing bike mileage, component wear, upcoming service
- Monthly writeup generator using Anthropic API
- Year-in-review generator
- Strava webhook receiver (requires deployment)
- Pi migration
- Authentication for public deployment

## Strava API rules

Respect these at all times:

- Single Player Mode: 200 requests per 15 min, 2000 per day overall
- Non-upload limit: 100 requests per 15 min, 1000 per day
- On 429 response, read the rate limit headers and sleep until the next window
- Never fetch the same data twice unnecessarily; cache raw JSON in `activities.raw_summary`
- Only fetch activity types `Ride` and `MountainBikeRide` for v1
- Store the refresh token; access tokens expire every 6 hours and must be refreshed

## Trail matching specifics

The core query (run once per activity after ingest):

```sql
INSERT INTO activity_trails (activity_id, trail_id, overlap_m, overlap_pct)
SELECT
    :activity_id,
    t.id,
    ST_Length(
        ST_Intersection(
            ST_Buffer(t.geometry::geography, 20)::geometry,
            a.geometry
        )::geography
    ) AS overlap_m,
    ST_Length(
        ST_Intersection(
            ST_Buffer(t.geometry::geography, 20)::geometry,
            a.geometry
        )::geography
    ) / NULLIF(ST_Length(t.geometry::geography), 0) AS overlap_pct
FROM trails t, activities a
WHERE a.id = :activity_id
  AND ST_Intersects(
      ST_Buffer(t.geometry::geography, 25)::geometry,
      a.geometry
  )
  AND ST_Length(
      ST_Intersection(
          ST_Buffer(t.geometry::geography, 20)::geometry,
          a.geometry
      )::geography
  ) > 50
ON CONFLICT (activity_id, trail_id) DO UPDATE
SET overlap_m = EXCLUDED.overlap_m,
    overlap_pct = EXCLUDED.overlap_pct,
    matched_at = NOW();
```

Tuning parameters (keep in a constants file):
- `TRAIL_BUFFER_M = 20` (matching radius around trail line)
- `INTERSECT_BUFFER_M = 25` (slightly wider for the initial spatial index filter)
- `MIN_OVERLAP_M = 50` (ignore matches shorter than this)

After the main match, compute `elapsed_s`, `avg_speed_mps`, and `direction` in Python by walking the activity's GPS stream and finding points inside the trail buffer.

## Environment variables

`.env.example`:

```
# Database
DATABASE_URL=postgresql://dirt:dirt@localhost:5432/dirt_dossier
POSTGRES_USER=dirt
POSTGRES_PASSWORD=dirt
POSTGRES_DB=dirt_dossier

# Strava (from https://www.strava.com/settings/api)
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_REDIRECT_URI=http://localhost:8000/auth/callback

# Anthropic (Phase 2 only)
ANTHROPIC_API_KEY=

# Misc
LOG_LEVEL=INFO
```

## Testing approach

Phase 1 uses manual verification, not automated tests. The trail matching correctness check is: pick 3-5 recent rides where the user remembers exactly which trails they rode, run a query showing what the system matched, confirm alignment. Add automated tests only if a specific regression justifies them.

## Style and conventions

- Python: use type hints throughout, `ruff` for linting and formatting with default settings
- TypeScript: strict mode, no `any`, use Drizzle's inferred types everywhere
- SQL: uppercase keywords, snake_case table and column names
- Commits: small and focused, conventional commit prefixes (feat, fix, chore, docs)
- Imports: absolute paths where tooling supports it

## When to ask the user vs proceed

**Proceed without asking:**
- Refactoring that doesn't change behavior
- Adding type hints or docstrings
- Fixing obvious bugs
- Installing a dependency already implied by the spec
- Writing migration files that match the schema above

**Ask first:**
- Adding a new dependency not in this spec
- Changing the database schema
- Adding a new page or route in the frontend
- Any change that would touch the out-of-scope list
- Choosing between two reasonable implementation approaches if both have tradeoffs

## Reference: what the user is NOT doing

To prevent scope creep, these are things the user has explicitly decided against for Phase 1:

- No authentication, no multi-user, no sharing
- No Pi deployment yet (local PC only)
- No Strava webhooks (manual sync is fine)
- No replicating Strava's UI; link out to Strava for polished ride maps
- No segment tracking (trails only, via OpenStreetMap data)
- No admin CRUD UI (seed scripts for manual data)
- No tests beyond manual verification
- No public-facing deployment

If a future user request implies doing any of these, surface the conflict and confirm before acting.

# dirt-dossier

Personal mountain biking dashboard. Ingests Strava ride data, matches rides against Trailforks trail geometry, tracks bike component wear, and generates ride analytics Strava can't produce.

Built for one user (me), one region (Nanaimo, BC), runs locally.

## What it does

- **Per-trail performance tracking.** See your history, PRs, and trends on any specific NMBC trail, not just Strava segments.
- **Bike maintenance tracking.** Track mileage on individual components (chain, pads, tires, fork, shock) and get flagged when you hit replacement intervals.
- **Monthly and yearly writeups.** Auto-generated narrative summaries of your riding, grounded in your actual data.
- **Cross-source analytics.** Combines Strava ride data with historical weather, trail difficulty, and bike component state to answer questions Strava can't.

## Tech stack

- Postgres 16 + PostGIS 3.4 (spatial database, Dockerized)
- Python 3.12 + FastAPI + SQLAlchemy 2.0 + GeoAlchemy2 (backend)
- Next.js 15 App Router + TypeScript + Tailwind + Drizzle ORM (dashboard)
- Docker Compose (local orchestration)

## Prerequisites

- Windows with WSL2 installed (see `docs/wsl-setup.md` if you need help)
- Docker installed inside WSL2 (or Docker Desktop with WSL2 backend)
- Node.js 20+ and `npm` (inside WSL)
- Python 3.12 and `uv` (inside WSL)
- A Strava account
- An Anthropic API key (Phase 2+ only)

## Setup

All commands run inside WSL2 (Ubuntu), not PowerShell.

### 1. Clone and enter the repo

```bash
git clone <your-repo-url> dirt-dossier
cd dirt-dossier
```

### 2. Create your `.env`

```bash
cp .env.example .env
```

Fill in Strava credentials (see `docs/strava-oauth.md`).

### 3. Start the database

```bash
docker compose up -d
```

This runs Postgres + PostGIS on `localhost:5432`. Data persists in a named Docker volume across restarts.

Verify it's running:

```bash
docker compose ps
docker compose logs db
```

### 4. Set up the Python backend

```bash
cd api
uv sync
```

Run the health check to confirm DB connectivity:

```bash
uv run python scripts/healthcheck.py
```

Expected output includes `PostGIS version: 3.4.x`.

### 5. Run database migrations

```bash
uv run alembic upgrade head
```

### 6. Authenticate with Strava

```bash
uv run python scripts/strava_auth.py
```

Follow the prompts. This opens a browser, you approve, and tokens are stored in the DB.

### 7. Import Trailforks data

Download the Nanaimo region KML first (see `docs/trailforks-export.md`), save it to `data/trailforks/nanaimo.kml`.

```bash
uv run python scripts/import_trails.py data/trailforks/nanaimo.kml
```

### 8. Bootstrap your Strava history

```bash
uv run python scripts/bootstrap_strava.py
```

This will take a while if you have a lot of history. It respects Strava's rate limits (2000 requests/day) and will sleep when needed.

### 9. Run trail matching

```bash
uv run python scripts/match_all.py
```

### 10. Seed your bikes and components

Edit `scripts/seed_bikes.py` and `scripts/seed_components.py` with real values (your bikes, when components were installed, replacement thresholds).

```bash
uv run python scripts/seed_bikes.py
uv run python scripts/seed_components.py
```

### 11. Start the dashboard

```bash
cd ../web
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

## Daily use

### Pull new rides

After a ride, run:

```bash
cd api
uv run python scripts/sync_recent.py
```

This fetches any activities since your last sync, writes them to the DB, and runs trail matching.

### Log a maintenance action

For Phase 1, edit `scripts/log_maintenance.py` and run it. Admin UI comes in Phase 2.

### Backup

```bash
./scripts/backup.sh
```

Creates a `pg_dump` in `data/backups/` with today's date. Worth running weekly.

## Repo layout

- `api/` - Python backend (scripts, future FastAPI)
- `web/` - Next.js dashboard
- `docker-compose.yml` - Postgres + PostGIS service
- `docs/` - Setup guides and reference docs
- `data/` - KML downloads and DB backups (gitignored)

See `CLAUDE.md` for the authoritative project spec.

## Phase status

- [ ] Phase 1: Foundation, ingest, matching, dashboard v1
- [ ] Phase 2: Weather enrichment, maintenance module, writeup generator
- [ ] Phase 3: Pi deployment, webhooks, remote access

## Why not just use Strava?

Strava is great at what it does. This app fills the gaps:

- Strava has segments, not trails. Segments are user-created and don't map cleanly to NMBC's trail network. This app matches rides against actual Trailforks trail geometry.
- Strava tracks total bike mileage, not component-level wear.
- Strava's Year in Sport is a template. This app generates writeups specific to you, your trails, and your patterns.
- Strava doesn't correlate rides with weather, trail difficulty, or your component state. This app does.

You keep using Strava for what it's good at (ride logging, segments, social). This app adds what Strava won't do.

## License

Personal project, no license. If you want to fork it for your own use, reach out.

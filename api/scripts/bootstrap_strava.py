"""Backfill all Strava activities into the activities table.

Loads tokens from strava_auth, auto-refreshes if expired, then paginates
through /athlete/activities and fetches GPS streams for each ride.

Usage:
    uv run python scripts/bootstrap_strava.py

Rate limiting:
- Sleeps 1-2 seconds between calls by default.
- On 429, reads X-Ratelimit-Usage / X-Ratelimit-Limit and sleeps until the
  next 15-minute window (or until midnight UTC if the daily limit is hit).
"""

import json
import logging
import math
import os
import random
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import httpx
import psycopg2
import psycopg2.extras

from dirt_dossier.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_URL = "https://www.strava.com/api/v3"
ACTIVITY_TYPES = {"Ride", "MountainBikeRide"}
STREAM_KEYS = "latlng,altitude,time,heartrate,distance"
PAGE_SIZE = 100
PROGRESS_EVERY = 25


def seconds_until_next_15min_window() -> int:
    now = datetime.now(tz=timezone.utc)
    minutes = now.minute
    secs = now.second
    next_boundary = (math.floor(minutes / 15) + 1) * 15
    if next_boundary >= 60:
        wait_s = (60 - minutes) * 60 - secs
    else:
        wait_s = (next_boundary - minutes) * 60 - secs
    return max(wait_s + 5, 10)


def seconds_until_midnight_utc() -> int:
    now = datetime.now(tz=timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    midnight = midnight + timedelta(days=1)
    return int((midnight - now).total_seconds()) + 10


def parse_rate_limit_headers(resp: httpx.Response) -> tuple[int, int, int, int]:
    """Return (15min_used, 15min_limit, daily_used, daily_limit)."""
    usage = resp.headers.get("X-Ratelimit-Usage", "0,0")
    limit = resp.headers.get("X-Ratelimit-Limit", "100,1000")
    u15, udaily = (int(x) for x in usage.split(","))
    l15, ldaily = (int(x) for x in limit.split(","))
    return u15, l15, udaily, ldaily


def handle_rate_limit(resp: httpx.Response) -> None:
    u15, l15, udaily, ldaily = parse_rate_limit_headers(resp)
    if udaily >= ldaily:
        wait = seconds_until_midnight_utc()
        log.warning(
            "Daily rate limit hit (%d/%d). Sleeping %ds until midnight UTC.", udaily, ldaily, wait
        )
    else:
        wait = seconds_until_next_15min_window()
        log.warning(
            "15-min rate limit hit (%d/%d). Sleeping %ds until next window.", u15, l15, wait
        )
    time.sleep(wait)


def get_with_retry(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    while True:
        resp = client.get(url, **kwargs)
        if resp.status_code == 429:
            handle_rate_limit(resp)
            continue
        resp.raise_for_status()
        return resp


def load_tokens(conn: psycopg2.extensions.connection) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM strava_auth WHERE id = 1")
        row = cur.fetchone()
    if not row:
        log.error("No tokens in strava_auth. Run scripts/strava_auth.py first.")
        sys.exit(1)
    return dict(row)


def refresh_token_if_needed(
    conn: psycopg2.extensions.connection, tokens: dict, settings
) -> dict:
    expires_at: datetime = tokens["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    if expires_at > now:
        return tokens

    log.info("Access token expired. Refreshing ...")
    resp = httpx.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": settings.strava_client_id,
            "client_secret": settings.strava_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    new_expires = datetime.fromtimestamp(data["expires_at"], tz=timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE strava_auth SET
                access_token  = %s,
                refresh_token = %s,
                expires_at    = %s,
                updated_at    = NOW()
            WHERE id = 1
            """,
            (data["access_token"], data["refresh_token"], new_expires),
        )
    conn.commit()

    tokens = dict(tokens)
    tokens["access_token"] = data["access_token"]
    tokens["refresh_token"] = data["refresh_token"]
    tokens["expires_at"] = new_expires
    log.info("Token refreshed. New expiry: %s", new_expires.isoformat())
    return tokens


def fetch_all_activities(client: httpx.Client) -> list[dict]:
    activities = []
    page = 1
    log.info("Fetching activity list ...")
    while True:
        resp = get_with_retry(
            client,
            f"{BASE_URL}/athlete/activities",
            params={"per_page": PAGE_SIZE, "page": page},
        )
        page_data = resp.json()
        if not page_data:
            break
        activities.extend(page_data)
        log.info("  Fetched page %d (%d activities so far)", page, len(activities))
        page += 1
        time.sleep(random.uniform(1.0, 2.0))
    return activities


def fetch_streams(client: httpx.Client, activity_id: int) -> dict | None:
    resp = get_with_retry(
        client,
        f"{BASE_URL}/activities/{activity_id}/streams",
        params={"keys": STREAM_KEYS, "key_by_type": "true"},
    )
    return resp.json()


def build_linestring_wkt(latlng: list[list[float]]) -> str | None:
    if not latlng or len(latlng) < 2:
        return None
    coords = ", ".join(f"{lng} {lat}" for lat, lng in latlng)
    return f"SRID=4326;LINESTRING({coords})"


def upsert_activity(
    conn: psycopg2.extensions.connection, summary: dict, streams: dict | None, bike_lookup: dict
) -> None:
    latlng_stream = (streams or {}).get("latlng", {}).get("data") if streams else None
    geometry_wkt = build_linestring_wkt(latlng_stream) if latlng_stream else None

    gear_id = summary.get("gear_id")
    bike_id = bike_lookup.get(gear_id) if gear_id else None

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO activities (
                strava_id, name, activity_type, start_time, duration_s, moving_time_s,
                distance_m, elevation_gain_m, avg_speed_mps, max_speed_mps,
                avg_heartrate, max_heartrate, bike_id, strava_gear_id,
                geometry, raw_summary
            ) VALUES (
                %(strava_id)s, %(name)s, %(activity_type)s, %(start_time)s,
                %(duration_s)s, %(moving_time_s)s, %(distance_m)s, %(elevation_gain_m)s,
                %(avg_speed_mps)s, %(max_speed_mps)s, %(avg_heartrate)s, %(max_heartrate)s,
                %(bike_id)s, %(strava_gear_id)s,
                %(geometry)s::geometry,
                %(raw_summary)s::jsonb
            )
            ON CONFLICT (strava_id) DO UPDATE SET
                name             = EXCLUDED.name,
                geometry         = COALESCE(EXCLUDED.geometry, activities.geometry),
                raw_summary      = EXCLUDED.raw_summary,
                ingested_at      = NOW()
            """,
            {
                "strava_id": summary["id"],
                "name": summary.get("name"),
                "activity_type": summary.get("type", summary.get("sport_type", "")),
                "start_time": summary["start_date"],
                "duration_s": summary["elapsed_time"],
                "moving_time_s": summary.get("moving_time"),
                "distance_m": summary.get("distance", 0),
                "elevation_gain_m": summary.get("total_elevation_gain"),
                "avg_speed_mps": summary.get("average_speed"),
                "max_speed_mps": summary.get("max_speed"),
                "avg_heartrate": summary.get("average_heartrate"),
                "max_heartrate": summary.get("max_heartrate"),
                "bike_id": bike_id,
                "strava_gear_id": gear_id,
                "geometry": geometry_wkt,
                "raw_summary": json.dumps(summary),
            },
        )
    conn.commit()


def load_bike_lookup(conn: psycopg2.extensions.connection) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT id, strava_gear_id FROM bikes WHERE strava_gear_id IS NOT NULL")
        return {row[1]: row[0] for row in cur.fetchall()}


def main() -> None:
    settings = get_settings()

    with psycopg2.connect(settings.database_url) as conn:
        tokens = load_tokens(conn)
        tokens = refresh_token_if_needed(conn, tokens, settings)

        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        with httpx.Client(headers=headers, timeout=60) as client:
            all_activities = fetch_all_activities(client)

        rides = [
            a for a in all_activities
            if a.get("type") in ACTIVITY_TYPES or a.get("sport_type") in ACTIVITY_TYPES
        ]
        log.info("Found %d total activities, %d are rides.", len(all_activities), len(rides))

        bike_lookup = load_bike_lookup(conn)

        imported = 0
        skipped = 0

        with httpx.Client(headers=headers, timeout=60) as client:
            for i, summary in enumerate(rides, 1):
                activity_id = summary["id"]

                streams = None
                try:
                    streams = fetch_streams(client, activity_id)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        log.debug("No streams for activity %d (private/deleted?)", activity_id)
                    else:
                        log.warning("Stream fetch failed for %d: %s", activity_id, exc)
                    skipped += 1

                upsert_activity(conn, summary, streams, bike_lookup)
                imported += 1

                if i % PROGRESS_EVERY == 0:
                    log.info("Progress: %d / %d", i, len(rides))

                time.sleep(random.uniform(1.0, 2.0))

    log.info("Bootstrap complete. %d activities imported, %d had no streams.", imported, skipped)


if __name__ == "__main__":
    main()

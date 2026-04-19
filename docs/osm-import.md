# OSM Trail Import

This document explains how to download the BC OpenStreetMap extract and import mountain bike trails into the database.

## Prerequisites

- `osmium-tool` installed: `sudo apt install osmium-tool`
- Database running: `docker compose up -d`
- `pyosmium` installed: included in `api/pyproject.toml`, install with `uv sync` from `api/`

## Step 1: Download the BC extract

Download the British Columbia PBF extract from Geofabrik:

```
https://download.geofabrik.de/north-america/canada/british-columbia.html
```

Click the `.osm.pbf` download link. Save the file to:

```
data/osm/british-columbia-latest.osm.pbf
```

The file is roughly 500 MB. Download time depends on your connection. You only need to repeat this quarterly when you want fresh OSM data.

If you have `wget` or `curl` available:

```bash
mkdir -p data/osm
wget -O data/osm/british-columbia-latest.osm.pbf \
  https://download.geofabrik.de/north-america/canada/british-columbia-latest.osm.pbf
```

## Step 2: Run the import script

From the repo root:

```bash
cd api
uv run python scripts/import_trails.py
```

The script will:

1. Use `osmium extract` to clip the BC extract to the Nanaimo bounding box.
2. Use `osmium tags-filter` to keep only MTB-relevant ways.
3. Parse the filtered data with pyosmium.
4. UPSERT each way into the `trails` table, skipping ways with no name and no `mtb:scale` tag.
5. Print a summary of ways seen, imported, and skipped.

## Bounding box

The default Nanaimo bounding box is:

| Edge  | Coordinate |
|-------|-----------|
| West  | -124.10   |
| South | 49.08     |
| East  | -123.85   |
| North | 49.28     |

You can override this with CLI arguments:

```bash
uv run python scripts/import_trails.py --bbox-west -124.15 --bbox-south 49.05 --bbox-east -123.80 --bbox-north 49.32
```

## Re-importing after an OSM refresh

The script uses `ON CONFLICT (osm_way_id) DO UPDATE`, so re-running it is safe. Download a new extract, drop the old file, and run the script again. Existing `activity_trails` rows are unaffected because they reference `trails.id`, not `osm_way_id`.

## Tag filtering

The script keeps any OSM way that has at least one of:

- `highway=path`
- `highway=cycleway`
- `highway=track`
- `route=mtb`
- Any `mtb:scale` tag (any value)

Ways that pass the tag filter but have neither a `name` tag nor an `mtb:scale` tag are skipped to reduce noise from unnamed generic paths.

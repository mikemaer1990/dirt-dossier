"""Import MTB trails from an OpenStreetMap PBF extract into the trails table.

Usage:
    uv run python scripts/import_trails.py [--bbox-west W] [--bbox-south S] \
        [--bbox-east E] [--bbox-north N] [--pbf PATH]

The script:
1. Filters the BC PBF extract to the Nanaimo bbox with osmium.
2. Filters to MTB-relevant tags with osmium tags-filter.
3. Parses the result with pyosmium and UPSERTs into trails.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import osmium
import osmium.geom
import psycopg2
import psycopg2.extras

from dirt_dossier.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_PBF = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "osm", "british-columbia-latest.osm.pbf"
)

MTB_TAG_FILTERS = [
    "w/highway=path",
    "w/highway=cycleway",
    "w/highway=track",
    "w/route=mtb",
    "w/mtb:scale",
]


def filter_pbf(input_pbf: str, bbox: tuple[float, float, float, float]) -> str:
    """Run osmium extract + tags-filter, return path to filtered temp file."""
    west, south, east, north = bbox
    bbox_str = f"{west},{south},{east},{north}"

    extract_file = tempfile.NamedTemporaryFile(suffix=".osm.pbf", delete=False)
    extract_file.close()

    filtered_file = tempfile.NamedTemporaryFile(suffix=".osm.pbf", delete=False)
    filtered_file.close()

    log.info("Extracting bbox %s from %s ...", bbox_str, input_pbf)
    subprocess.run(
        ["osmium", "extract", "--bbox", bbox_str, input_pbf,
         "-o", extract_file.name, "--overwrite"],
        check=True,
    )

    log.info("Filtering MTB-relevant tags ...")
    subprocess.run(
        ["osmium", "tags-filter", extract_file.name, *MTB_TAG_FILTERS,
         "-o", filtered_file.name, "--overwrite"],
        check=True,
    )

    os.unlink(extract_file.name)
    return filtered_file.name


class TrailHandler(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self._fab = osmium.geom.WKBFactory()
        self.ways: list[dict] = []
        self.seen = 0
        self.skipped = 0

    def way(self, w: osmium.osm.Way) -> None:
        self.seen += 1

        tags = {tag.k: tag.v for tag in w.tags}
        name = tags.get("name")
        mtb_scale = tags.get("mtb:scale")

        if not name and not mtb_scale:
            self.skipped += 1
            return

        try:
            wkb_hex = self._fab.create_linestring(
                w, osmium.geom.use_nodes.UNIQUE, osmium.geom.direction.FORWARD
            )
        except Exception:
            self.skipped += 1
            return

        difficulty = mtb_scale

        self.ways.append(
            {
                "osm_way_id": w.id,
                "name": name or f"OSM Way {w.id}",
                "difficulty": difficulty,
                "raw_tags": json.dumps(tags),
                "wkb_hex": wkb_hex,
            }
        )


def upsert_trails(conn: psycopg2.extensions.connection, ways: list[dict]) -> int:
    sql = """
        INSERT INTO trails (osm_way_id, name, region, difficulty, source, raw_tags, geometry)
        VALUES (
            %(osm_way_id)s,
            %(name)s,
            'nanaimo',
            %(difficulty)s,
            'osm',
            %(raw_tags)s::jsonb,
            ST_GeomFromWKB(%(wkb)s::bytea, 4326)
        )
        ON CONFLICT (osm_way_id) DO UPDATE SET
            name        = EXCLUDED.name,
            difficulty  = EXCLUDED.difficulty,
            source      = EXCLUDED.source,
            raw_tags    = EXCLUDED.raw_tags,
            geometry    = EXCLUDED.geometry,
            last_refreshed_at = NOW()
    """
    imported = 0
    with conn.cursor() as cur:
        for way in ways:
            cur.execute(
                sql,
                {
                    "osm_way_id": way["osm_way_id"],
                    "name": way["name"],
                    "difficulty": way["difficulty"],
                    "raw_tags": way["raw_tags"],
                    "wkb": psycopg2.Binary(bytes.fromhex(way["wkb_hex"])),
                },
            )
            imported += 1
    conn.commit()
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import OSM MTB trails into the database.")
    parser.add_argument("--pbf", default=DEFAULT_PBF, help="Path to BC OSM PBF extract")
    parser.add_argument("--bbox-west", type=float, default=-124.10)
    parser.add_argument("--bbox-south", type=float, default=49.08)
    parser.add_argument("--bbox-east", type=float, default=-123.85)
    parser.add_argument("--bbox-north", type=float, default=49.28)
    args = parser.parse_args()

    pbf_path = os.path.abspath(args.pbf)
    if not os.path.exists(pbf_path):
        log.error("PBF file not found: %s", pbf_path)
        log.error("Download it from https://download.geofabrik.de/north-america/canada/british-columbia.html")
        sys.exit(1)

    bbox = (args.bbox_west, args.bbox_south, args.bbox_east, args.bbox_north)
    filtered_pbf = filter_pbf(pbf_path, bbox)

    try:
        log.info("Parsing filtered PBF ...")
        handler = TrailHandler()
        handler.apply_file(filtered_pbf, locations=True)
    finally:
        os.unlink(filtered_pbf)

    log.info(
        "Ways seen: %d, to import: %d, skipped: %d",
        handler.seen, len(handler.ways), handler.skipped,
    )

    if not handler.ways:
        log.warning("No ways to import. Check your bbox and that the PBF has MTB data.")
        return

    settings = get_settings()
    with psycopg2.connect(settings.database_url) as conn:
        imported = upsert_trails(conn, handler.ways)

    log.info("Import complete. %d trails upserted.", imported)


if __name__ == "__main__":
    main()

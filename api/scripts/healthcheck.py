"""Verifies that the database is reachable and PostGIS is installed."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import psycopg2
from dirt_dossier.config import get_settings


def main() -> None:
    url = get_settings().database_url
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT PostGIS_Lib_Version();")
    version = cur.fetchone()[0]
    print(f"PostGIS version: {version}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

"""Complete the Strava OAuth flow and store tokens in the database.

Run once after adding STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET to .env.
Starts a local HTTP server on port 8000, opens the Strava auth page, waits for
the callback, exchanges the code for tokens, and writes them to strava_auth.

Usage:
    uv run python scripts/strava_auth.py
"""

import http.server
import logging
import os
import sys
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from threading import Event

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import httpx
import psycopg2

from dirt_dossier.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
SCOPES = "read,activity:read_all"

_code_received = Event()
_auth_code: str | None = None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "error" in params:
            error = params["error"][0]
            self._respond(f"Authorization denied: {error}. You can close this tab.")
            log.error("Strava returned an error: %s", error)
            _code_received.set()
            return

        if "code" not in params:
            self._respond("Unexpected callback. No code in query string.")
            return

        _auth_code = params["code"][0]
        self._respond(
            "Authorization successful! You can close this tab and return to the terminal."
        )
        _code_received.set()

    def _respond(self, message: str) -> None:
        body = message.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # suppress default access log noise
        pass


def build_auth_url(client_id: str, redirect_uri: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPES,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(client_id: str, client_secret: str, code: str) -> dict:
    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def store_tokens(conn: psycopg2.extensions.connection, data: dict) -> int:
    expires_at = datetime.fromtimestamp(data["expires_at"], tz=timezone.utc)
    athlete_id = data["athlete"]["id"]

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO strava_auth
                (id, athlete_id, access_token, refresh_token, expires_at, updated_at)
            VALUES (1, %s, %s, %s, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                athlete_id    = EXCLUDED.athlete_id,
                access_token  = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at    = EXCLUDED.expires_at,
                updated_at    = NOW()
            """,
            (athlete_id, data["access_token"], data["refresh_token"], expires_at),
        )
    conn.commit()
    return athlete_id


def main() -> None:
    settings = get_settings()

    if not settings.strava_client_id or not settings.strava_client_secret:
        log.error("STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    auth_url = build_auth_url(settings.strava_client_id, settings.strava_redirect_uri)
    callback_port = 8000

    server = http.server.HTTPServer(("localhost", callback_port), CallbackHandler)

    log.info("Opening browser for Strava authorization...")
    log.info("If the browser does not open, visit:\n  %s", auth_url)
    webbrowser.open(auth_url)

    log.info("Waiting for callback on %s ...", settings.strava_redirect_uri)
    while not _code_received.is_set():
        server.handle_request()

    server.server_close()

    if _auth_code is None:
        log.error("No authorization code received. Aborting.")
        sys.exit(1)

    log.info("Exchanging authorization code for tokens ...")
    token_data = exchange_code(settings.strava_client_id, settings.strava_client_secret, _auth_code)

    with psycopg2.connect(settings.database_url) as conn:
        athlete_id = store_tokens(conn, token_data)

    log.info("Authorization successful. Tokens stored for athlete %d.", athlete_id)


if __name__ == "__main__":
    main()

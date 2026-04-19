# Strava OAuth Setup

This document explains how to register a Strava API application and authorize it to access your ride data.

## Step 1: Create a Strava API application

1. Go to https://www.strava.com/settings/api while logged in to your Strava account.
2. Fill in the application form:
   - **Application Name**: anything, e.g. `dirt-dossier`
   - **Category**: choose `Data Importer` or `Other`
   - **Club**: leave blank
   - **Website**: `http://localhost`
   - **Authorization Callback Domain**: `localhost`
3. Click **Create** and note the **Client ID** and **Client Secret** shown on the next page.

## Step 2: Add credentials to .env

Open `.env` at the repo root (copy from `.env.example` if it does not exist yet):

```
STRAVA_CLIENT_ID=your_client_id_here
STRAVA_CLIENT_SECRET=your_client_secret_here
STRAVA_REDIRECT_URI=http://localhost:8000/auth/callback
```

Replace `your_client_id_here` and `your_client_secret_here` with the values from the Strava API settings page.

## Step 3: Run the auth script

From the `api/` directory:

```bash
uv run python scripts/strava_auth.py
```

The script will:

1. Print an authorization URL.
2. Open it in your browser automatically (or paste it manually if that fails).
3. Start a local HTTP server on port 8000.
4. Wait for Strava to redirect back with an authorization code.
5. Exchange the code for access and refresh tokens.
6. Store the tokens in the `strava_auth` table.

You should see output like:

```
Opening browser for Strava authorization...
Waiting for callback on http://localhost:8000/auth/callback ...
Authorization successful. Tokens stored for athlete 12345678.
```

## Scopes requested

The script requests `read,activity:read_all`. This is the minimum needed to read your full activity history including private activities.

## Token refresh

Access tokens expire every 6 hours. `bootstrap_strava.py` and `sync_recent.py` automatically refresh the token using the stored refresh token before making API calls. You only need to run `strava_auth.py` once.

## Rate limits (Single Player Mode)

Strava's API limits for a personal app:

| Window    | Limit |
|-----------|-------|
| 15 minutes | 100 requests |
| Daily      | 1000 requests |

The bootstrap script handles 429 responses by reading the rate limit headers and sleeping until the next window opens.

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import httpx
from urllib.parse import urlencode
import os
import secrets

app = FastAPI()

# Add session middleware for state param
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(16))

CLIENT_ID = "e0f64b5f67a7407f917d0ea041ca7c26"       # Replace with your Spotify Client ID
CLIENT_SECRET = "fecb6807c15043818006662537f8b221"  # Replace with your Spotify Client Secret
REDIRECT_URI = "http://127.0.0.1:8000/callback"  # Must match your Spotify app Redirect URI

SCOPE = "user-read-private user-read-email user-read-playback-state user-modify-playback-state user-read-currently-playing user-top-read user-follow-read"

TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTH_URL = "https://accounts.spotify.com/authorize"

# In-memory storage of tokens for demo purposes
# In production, store tokens securely per user (DB, cache)
tokens = {}

@app.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session['state'] = state

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "show_dialog": "true"
    }

    url = AUTH_URL + "?" + urlencode(params)

    return RedirectResponse(url=url)

@app.get("/callback")
async def callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error:
        return JSONResponse({"error": error})

    saved_state = request.session.get('state')
    if state is None or state != saved_state:
        raise HTTPException(status_code=400, detail="State mismatch or missing")

    if code is None:
        raise HTTPException(status_code=400, detail="Missing code parameter")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
        response = await client.post(TOKEN_URL, data=data, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Token exchange failed: {response.text}")

        token_data = response.json()
        # Save tokens in memory (demo)
        tokens['access_token'] = token_data['access_token']
        tokens['refresh_token'] = token_data['refresh_token']
        tokens['expires_in'] = token_data['expires_in']

    return JSONResponse({
        "message": "Authentication successful! Tokens stored.",
        "access_token": tokens['access_token'],
        "refresh_token": tokens['refresh_token'],
        "expires_in": tokens['expires_in']
    })

@app.get("/tokens")
async def get_tokens():
    if not tokens:
        return {"message": "No tokens stored yet. Login first."}
    return tokens

@app.get("/spotify")
async def spotify_info():
    if not tokens.get('access_token'):
        raise HTTPException(status_code=401, detail="Not authenticated with Spotify. Login first.")

    headers = {
        "Authorization": f"Bearer {tokens['access_token']}"
    }

    async with httpx.AsyncClient() as client:
        # Get top 10 tracks
        top_tracks_resp = await client.get("https://api.spotify.com/v1/me/top/tracks?limit=10", headers=headers)
        top_tracks_resp.raise_for_status()
        top_tracks = top_tracks_resp.json()

        # Get currently playing track
        now_playing_resp = await client.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)
        # Note: 204 status code means no song playing
        if now_playing_resp.status_code == 204:
            now_playing = None
        else:
            now_playing_resp.raise_for_status()
            now_playing = now_playing_resp.json()

        # Get followed artists
        followed_resp = await client.get("https://api.spotify.com/v1/me/following?type=artist&limit=50", headers=headers)
        followed_resp.raise_for_status()
        followed = followed_resp.json()

    return {
        "top_tracks": top_tracks,
        "currently_playing": now_playing,
        "followed_artists": followed
    }
from fastapi import Query

@app.put("/spotify/play")
async def play_track(uri: str = Query(..., description="Spotify track URI to play")):
    if not tokens.get('access_token'):
        raise HTTPException(status_code=401, detail="Not authenticated with Spotify. Login first.")

    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Content-Type": "application/json"
    }
    data = {
        "uris": [uri]
    }

    async with httpx.AsyncClient() as client:
        resp = await client.put("https://api.spotify.com/v1/me/player/play", json=data, headers=headers)
        if resp.status_code not in (204, 202):
            raise HTTPException(status_code=resp.status_code, detail=f"Failed to start playback: {resp.text}")

    return {"message": f"Started playing track {uri}"}


@app.put("/spotify/pause")
async def pause_playback():
    if not tokens.get('access_token'):
        raise HTTPException(status_code=401, detail="Not authenticated with Spotify. Login first.")

    headers = {
        "Authorization": f"Bearer {tokens['access_token']}"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.put("https://api.spotify.com/v1/me/player/pause", headers=headers)
        if resp.status_code not in (204, 202):
            raise HTTPException(status_code=resp.status_code, detail=f"Failed to pause playback: {resp.text}")

    return {"message": "Playback paused"}

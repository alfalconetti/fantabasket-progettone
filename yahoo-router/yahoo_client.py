"""
Client Yahoo Fantasy API — OAuth2 (flusso oob), refresh automatico, parsing JSON Yahoo.
Usato sia da main.py (FastAPI) sia da cli.py (bootstrap OAuth e debug).
"""
import asyncio
import base64
import json
import logging
import os
import time
import urllib.parse

import httpx

logger = logging.getLogger(__name__)

AUTH_URL     = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL    = "https://api.login.yahoo.com/oauth2/get_token"
API_BASE     = "https://fantasysports.yahooapis.com/fantasy/v2"
REDIRECT_URI = "oob"

TOKEN_PATH   = os.environ.get("YAHOO_TOKEN_PATH", "/data/yahoo_token.json")
GAME_KEY_TTL = 12 * 3600  # il game_key cambia a ogni stagione NBA


class NotAuthorized(Exception):
    """Nessun token salvato: va eseguito `python3 cli.py auth`."""


# ── secrets / config ────────────────────────────────────────────────────────

def read_secret(env_var: str) -> str:
    path = os.environ.get(env_var)
    if path and os.path.exists(path):
        return open(path).read().strip()
    return os.environ.get(env_var.replace("_FILE", ""), "")


def league_ids() -> list[str]:
    raw = os.environ.get("YAHOO_LEAGUE_IDS", "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _basic_auth() -> str:
    cid = read_secret("YAHOO_CLIENT_ID_FILE")
    sec = read_secret("YAHOO_CLIENT_SECRET_FILE")
    return "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode()


# ── token storage ───────────────────────────────────────────────────────────

def load_token() -> dict | None:
    if not os.path.exists(TOKEN_PATH):
        return None
    with open(TOKEN_PATH) as f:
        return json.load(f)


def _save_token(tok: dict) -> None:
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
    tmp = TOKEN_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(tok, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, TOKEN_PATH)


# ── OAuth2 ──────────────────────────────────────────────────────────────────

def auth_url() -> str:
    params = {
        "client_id":     read_secret("YAHOO_CLIENT_ID_FILE"),
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "language":      "en-us",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


async def _token_request(data: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            TOKEN_URL,
            data={"redirect_uri": REDIRECT_URI, **data},
            headers={"Authorization": _basic_auth(),
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        return r.json()


async def exchange_code(code: str) -> None:
    tok = await _token_request({"grant_type": "authorization_code", "code": code})
    _save_token(tok)


_lock = asyncio.Lock()


async def get_access_token(force_refresh: bool = False) -> str:
    async with _lock:
        tok = load_token()
        if not tok:
            raise NotAuthorized()
        if not force_refresh and tok.get("expires_at", 0) - 60 > time.time():
            return tok["access_token"]

        new = await _token_request({"grant_type": "refresh_token",
                                    "refresh_token": tok["refresh_token"]})
        new.setdefault("refresh_token", tok["refresh_token"])
        _save_token(new)
        logger.info("Yahoo access token rinnovato")
        return new["access_token"]


# ── chiamate API ────────────────────────────────────────────────────────────

async def api_get(path: str) -> dict:
    """GET su /fantasy/v2/{path}; ritorna il contenuto di fantasy_content."""
    for tentativo in (0, 1):
        token = await get_access_token(force_refresh=(tentativo == 1))
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(f"{API_BASE}/{path}",
                            params={"format": "json"},
                            headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 401 and tentativo == 0:
            continue  # token revocato/scaduto in anticipo: forza refresh e riprova
        r.raise_for_status()
        return r.json()["fantasy_content"]
    raise RuntimeError("unreachable")


def _merge(items) -> dict:
    """Yahoo restituisce gli oggetti come liste di dict a chiave singola
    (con liste vuote in mezzo): li appiattisce in un unico dict."""
    out = {}
    for it in items:
        if isinstance(it, dict):
            out.update(it)
        elif isinstance(it, list):
            out.update(_merge(it))
    return out


_game_cache: dict = {}


async def get_game() -> dict:
    if _game_cache and time.time() - _game_cache["ts"] < GAME_KEY_TTL:
        return _game_cache["game"]
    fc = await api_get("game/nba")
    g = _merge(fc["game"])
    game = {"game_key": g["game_key"], "season": g.get("season")}
    _game_cache.update(game=game, ts=time.time())
    return game


async def get_league_teams(league_id: str) -> dict:
    game = await get_game()
    league_key = f"{game['game_key']}.l.{league_id}"
    fc = await api_get(f"league/{league_key}/teams")
    meta, body = fc["league"][0], fc["league"][1]

    teams = []
    for k, v in body["teams"].items():
        if k == "count":
            continue
        t = _merge(v["team"][0])
        managers = t.get("managers") or []
        mgr = managers[0].get("manager", {}) if managers else {}
        teams.append({
            "team_key":         t.get("team_key"),
            "team_id":          t.get("team_id"),
            "name":             t.get("name"),
            "manager":          mgr.get("nickname"),
            "is_commissioner":  mgr.get("is_commissioner") == "1",
        })
    teams.sort(key=lambda x: int(x["team_id"]))

    return {
        "league_id":  league_id,
        "league_key": league_key,
        "name":       meta.get("name"),
        "season":     meta.get("season"),
        "teams":      teams,
    }

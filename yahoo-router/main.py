"""
Yahoo Router — microservizio FastAPI che incapsula OAuth2 e le chiamate
alle Yahoo Fantasy API. Il bot-main lo interroga via HTTP sulla rete interna.
"""
import logging

import httpx
from fastapi import FastAPI, Header, HTTPException

import yahoo_client as yc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fantabasket Yahoo Router")


def _check_auth(authorization: str):
    if authorization != f"Bearer {yc.read_secret('ROUTER_TOKEN_FILE')}":
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _call(coro):
    try:
        return await coro
    except yc.NotAuthorized:
        raise HTTPException(status_code=503,
                            detail="Yahoo non autorizzato: eseguire `python3 cli.py auth`")
    except httpx.HTTPStatusError as e:
        logger.error("Yahoo API %s: %s", e.response.status_code, e.response.text[:500])
        raise HTTPException(status_code=502, detail=f"Yahoo error {e.response.status_code}")
    except httpx.HTTPError as e:
        logger.error("Yahoo request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Yahoo error: {e}")


@app.get("/yahoo/game")
async def game(authorization: str = Header(...)):
    _check_auth(authorization)
    return await _call(yc.get_game())


@app.get("/yahoo/teams")
async def teams(authorization: str = Header(...)):
    _check_auth(authorization)
    return [await _call(yc.get_league_teams(lid)) for lid in yc.league_ids()]


@app.get("/health")
async def health():
    return {"ok": True, "authorized": yc.load_token() is not None}

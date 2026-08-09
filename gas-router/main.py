"""
GAS Router — microservizio FastAPI che riceve chiamate dal bot
e le inoltra alla Web App Google Apps Script.
"""
import os
import logging
import httpx
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fantabasket GAS Router")


def _read_secret(env_var: str) -> str:
    path = os.environ.get(env_var)
    if path and os.path.exists(path):
        return open(path).read().strip()
    return os.environ.get(env_var.replace("_FILE", ""), "")


# Config — caricata all'avvio
GAS_ROSTER_URL = _read_secret("GAS_ROSTER_URL_FILE")
GAS_TOKEN      = _read_secret("GAS_TOKEN_FILE")
ROUTER_TOKEN   = _read_secret("ROUTER_TOKEN_FILE")


class GASPayload(BaseModel):
    action: str
    teams: Optional[list[Any]] = None


@app.post("/gas/roster")
async def roster(payload: GASPayload, authorization: str = Header(...)):
    _check_auth(authorization)
    gas_payload = {
        "token": GAS_TOKEN,
        "action": payload.action,
        "teams": payload.teams or [],
    }
    return await _forward(GAS_ROSTER_URL, gas_payload)


def _check_auth(authorization: str):
    if authorization != f"Bearer {ROUTER_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _forward(url: str, payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.error("GAS request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"GAS error: {str(e)}")


@app.get("/health")
async def health():
    return {"ok": True}

"""
FastAPI backend for the Kensho Transcript Dashboard.
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from kensho_client import KenshoClient

app = FastAPI(title="Kensho Transcript Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*", "X-Kensho-Refresh-Token"],
)

# Env-var token is the fallback; UI-supplied token takes precedence.
ENV_REFRESH_TOKEN = os.environ.get("KENSHO_REFRESH_TOKEN", "")

# Cache clients by refresh token so we don't re-authenticate on every request.
_client_cache: dict[str, KenshoClient] = {}


def _get_client(refresh_token: str) -> KenshoClient:
    if refresh_token not in _client_cache:
        _client_cache[refresh_token] = KenshoClient(refresh_token=refresh_token)
    return _client_cache[refresh_token]


def _resolve_token(header_token: Optional[str]) -> str:
    token = header_token or ENV_REFRESH_TOKEN
    if not token:
        raise HTTPException(
            status_code=401,
            detail="No Kensho refresh token provided. Set it in the dashboard settings or via KENSHO_REFRESH_TOKEN env var.",
        )
    return token


# ------------------------------------------------------------------
# API routes
# ------------------------------------------------------------------


@app.get("/api/transcripts")
def list_transcripts(
    ticker: str = Query(..., description="Stock ticker, e.g. KKR"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    include_conferences: bool = Query(True, description="Include conference call transcripts"),
    x_kensho_refresh_token: Optional[str] = Header(None),
):
    token = _resolve_token(x_kensho_refresh_token)
    try:
        events = _get_client(token).get_all_transcripts_for_ticker(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            include_conferences=include_conferences,
        )
        return {"ticker": ticker.upper(), "count": len(events), "events": events}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/transcript/{key_dev_id}")
def get_transcript(
    key_dev_id: int,
    x_kensho_refresh_token: Optional[str] = Header(None),
):
    token = _resolve_token(x_kensho_refresh_token)
    try:
        text = _get_client(token).get_transcript(key_dev_id)
        if text is None:
            raise HTTPException(status_code=404, detail="Transcript not available for this event")
        return {"key_dev_id": key_dev_id, "transcript": text}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/resolve/{ticker}")
def resolve_ticker(
    ticker: str,
    x_kensho_refresh_token: Optional[str] = Header(None),
):
    token = _resolve_token(x_kensho_refresh_token)
    try:
        return _get_client(token).resolve_ticker(ticker)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# Serve frontend
# ------------------------------------------------------------------

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "static")

app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))

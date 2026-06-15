"""
FastAPI backend for the Kensho Transcript Dashboard.
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from kensho_client import KenshoClient

app = FastAPI(title="Kensho Transcript Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REFRESH_TOKEN = os.environ.get("KENSHO_REFRESH_TOKEN", "")

if not REFRESH_TOKEN:
    print("WARNING: KENSHO_REFRESH_TOKEN env var not set. API calls will fail.")

client = KenshoClient(refresh_token=REFRESH_TOKEN)


# ------------------------------------------------------------------
# API routes
# ------------------------------------------------------------------


@app.get("/api/transcripts")
def list_transcripts(
    ticker: str = Query(..., description="Stock ticker, e.g. KKR"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    include_conferences: bool = Query(True, description="Include conference call transcripts"),
):
    """Return metadata for all available transcripts for a ticker."""
    try:
        events = client.get_all_transcripts_for_ticker(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            include_conferences=include_conferences,
        )
        return {"ticker": ticker.upper(), "count": len(events), "events": events}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/transcript/{key_dev_id}")
def get_transcript(key_dev_id: int):
    """Return full transcript text for a given key_dev_id."""
    try:
        text = client.get_transcript(key_dev_id)
        if text is None:
            raise HTTPException(status_code=404, detail="Transcript not available")
        return {"key_dev_id": key_dev_id, "transcript": text}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/resolve/{ticker}")
def resolve_ticker(ticker: str):
    """Resolve a ticker to S&P Global IDs."""
    try:
        return client.resolve_ticker(ticker)
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

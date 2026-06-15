"""
Kensho LLM-Ready API client.
Base URL: https://kfinance.kensho.com/api/v1/
Auth:     Bearer token via OAuth2 refresh token or RSA keypair
"""

import time
from datetime import datetime, timedelta
from typing import Optional
import httpx

API_HOST = "https://kfinance.kensho.com"
API_VERSION = "1"
URL_BASE = f"{API_HOST}/api/v{API_VERSION}/"

# S&P Global key development categories that can carry transcripts.
# The most relevant one for conference/investor day calls is category 6.
TRANSCRIPT_CATEGORIES = [
    "RESULTS_ANNOUNCEMENTS_OR_CORPORATE_COMMUNICATIONS",
]


class KenshoClient:
    def __init__(self, refresh_token: str):
        self.refresh_token = refresh_token
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._http = httpx.Client(timeout=60.0)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _ensure_token(self) -> None:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return
        resp = self._http.get(
            f"{API_HOST}/oauth2/refresh",
            params={"refresh_token": self.refresh_token},
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        # Tokens typically last 1 hour; refresh after 55 min
        self._token_expires_at = time.time() + 55 * 60

    def _headers(self) -> dict:
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # ID resolution
    # ------------------------------------------------------------------

    def resolve_ticker(self, ticker: str, exchange_code: Optional[str] = None) -> dict:
        """Return {company_id, security_id, trading_item_id} for a ticker."""
        url = f"{URL_BASE}id/{ticker}"
        if exchange_code:
            url += f"/exchange_code/{exchange_code}"
        resp = self._http.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Earnings transcripts
    # ------------------------------------------------------------------

    def get_earnings(self, company_id: int) -> list[dict]:
        """
        Return list of earnings events for a company.
        Each item: {name, key_dev_id, datetime}
        """
        resp = self._http.get(
            f"{URL_BASE}earnings/{company_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        earnings = data.get("earnings", [])
        for e in earnings:
            e["transcript_type"] = "Earnings Call"
        return earnings

    # ------------------------------------------------------------------
    # Key developments (conference calls, investor days, etc.)
    # ------------------------------------------------------------------

    def get_key_devs(
        self,
        company_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        key_dev_category: Optional[str] = None,
    ) -> dict:
        """
        POST /key_devs/
        Returns key development events grouped by category.
        company_id: resolved S&P Global CIQ company integer ID
        start_date / end_date: ISO date strings "YYYY-MM-DD" (null = all history / present)
        key_dev_category: e.g. "RESULTS_ANNOUNCEMENTS_OR_CORPORATE_COMMUNICATIONS"
        """
        payload: dict = {"company_id": company_id}
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date
        if key_dev_category:
            payload["key_dev_category"] = key_dev_category

        resp = self._http.post(
            f"{URL_BASE}key_devs/",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_conference_key_devs(
        self,
        company_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch key developments across transcript-bearing categories and
        return a flat list with transcript_type populated.
        """
        events: list[dict] = []
        for category in TRANSCRIPT_CATEGORIES:
            try:
                data = self.get_key_devs(
                    company_id=company_id,
                    start_date=start_date,
                    end_date=end_date,
                    key_dev_category=category,
                )
                results: dict = data.get("results", {})
                for cat_name, items in results.items():
                    for item in items:
                        item["transcript_type"] = cat_name.replace("_", " ").title()
                        events.append(item)
            except httpx.HTTPStatusError:
                pass
        return events

    # ------------------------------------------------------------------
    # Transcript fetch
    # ------------------------------------------------------------------

    def get_transcript(self, key_dev_id: int) -> Optional[str]:
        """
        GET /transcript/{key_dev_id}
        Returns formatted transcript text or None if not available.
        """
        resp = self._http.get(
            f"{URL_BASE}transcript/{key_dev_id}",
            headers=self._headers(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        components = data.get("transcript", [])
        lines = []
        for part in components:
            speaker = part.get("person_name", "")
            text = part.get("text", "")
            if speaker:
                lines.append(f"**{speaker}**: {text}")
            else:
                lines.append(text)
        return "\n\n".join(lines) if lines else None

    # ------------------------------------------------------------------
    # Convenience: all transcripts for a ticker
    # ------------------------------------------------------------------

    def get_all_transcripts_for_ticker(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        include_conferences: bool = True,
    ) -> list[dict]:
        """
        High-level method: resolves ticker, fetches earnings + (optionally)
        conference transcripts, returns sorted list of transcript metadata.
        Does NOT fetch transcript bodies — call get_transcript(key_dev_id) per item.
        """
        ids = self.resolve_ticker(ticker)
        company_id: int = ids["company_id"]

        # 1. Earnings
        earnings = self.get_earnings(company_id)
        for e in earnings:
            e.setdefault("source", "Earnings")

        # 2. Conference / other key developments
        conf_events: list[dict] = []
        if include_conferences:
            conf_events = self.get_conference_key_devs(
                company_id=company_id,
                start_date=start_date,
                end_date=end_date,
            )
            for e in conf_events:
                e.setdefault("source", "Conference")

        # Merge and deduplicate by key_dev_id
        seen: set[int] = set()
        merged: list[dict] = []
        for event in earnings + conf_events:
            kid = event.get("key_dev_id")
            if kid and kid not in seen:
                seen.add(kid)
                merged.append(event)

        # Sort newest first
        def sort_key(e: dict) -> str:
            return e.get("most_important_date_utc") or e.get("announced_date_utc") or e.get("datetime") or ""

        merged.sort(key=sort_key, reverse=True)
        return merged

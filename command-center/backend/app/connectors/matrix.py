"""11matrix connector (read-only, spec §3.2): GA, ads, Search Console per project/store.

Normalised shape per property:
  {matrix_id, name, period: {from, to}, sessions, sessions_prev, revenue, revenue_prev,
   ad_spend, ad_spend_prev, clicks, clicks_prev, impressions, impressions_prev}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from ..config import settings

FIXTURE = Path(__file__).with_name("fixtures") / "matrix.json"


class MatrixMock:
    def __init__(self) -> None:
        self._data = json.loads(FIXTURE.read_text())

    async def metrics(self, days: int = 7) -> list[dict[str, Any]]:
        return self._data["properties"]

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "backend": "mock", "properties": len(self._data["properties"])}


class MatrixHTTP:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def metrics(self, days: int = 7) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=60, headers=self.headers) as c:
            r = await c.get(f"{self.url}/api/metrics", params={"days": days})
            r.raise_for_status()
            return r.json()

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10, headers=self.headers) as c:
                (await c.get(f"{self.url}/api/health")).raise_for_status()
            return {"ok": True, "backend": "http", "url": self.url}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "backend": "http", "url": self.url, "error": str(exc)}


def client() -> MatrixMock | MatrixHTTP:
    if settings.matrix_backend == "http" and settings.matrix_url:
        return MatrixHTTP(settings.matrix_url, settings.matrix_token)
    return MatrixMock()

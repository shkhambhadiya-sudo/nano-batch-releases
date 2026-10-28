"""11deeds connector (read-only in v1, spec §3.1).

Two backends:
- mock: reads `fixtures/deeds.json` so the system runs end-to-end without the VPS.
- http: calls the 11deeds MCP/HTTP endpoint. The exact routes are placeholders
  until the real server exists; keep the normalised shape below stable so agents
  never depend on 11deeds' raw format.

Normalised shapes:
  user:    {deeds_user_id, name, role, skills[], teams[], last_completed_at}
  project: {deeds_project_id, name, team}
  task:    {deeds_task_id, deeds_project_id, deeds_user_id, title, description, status,
            priority, due_date, last_activity_at, time_consumed_min, comments[]}
  comment: {deeds_task_id, deeds_user_id, text, at}
  attendance: {deeds_user_id, date, check_in, check_out, break_min}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from ..config import settings

FIXTURE = Path(__file__).with_name("fixtures") / "deeds.json"
STATUS_MAP = {"open": "todo", "todo": "todo", "in_progress": "in-progress", "in-progress": "in-progress",
              "blocked": "blocked", "done": "done", "completed": "done", "closed": "done", "dropped": "dropped"}


class DeedsMock:
    def __init__(self) -> None:
        self._data = json.loads(FIXTURE.read_text())

    async def users(self) -> list[dict[str, Any]]:
        return [_norm_user(u) for u in self._data["users"]]

    async def projects(self) -> list[dict[str, Any]]:
        return [_norm_project(p) for p in self._data["projects"]]

    async def tasks(self, since: str | None = None) -> list[dict[str, Any]]:
        rows = self._data["tasks"]
        if since:
            rows = [t for t in rows if (t.get("last_activity_at") or "") >= since]
        return [_norm_task(t) for t in rows]

    async def attendance(self, since: str | None = None) -> list[dict[str, Any]]:
        rows = self._data.get("attendance", [])
        return [a for a in rows if not since or a["date"] >= since[:10]]

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "backend": "mock", "users": len(self._data["users"]), "tasks": len(self._data["tasks"])}


class DeedsHTTP:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def _get(self, path: str, **params: Any) -> Any:
        async with httpx.AsyncClient(timeout=60, headers=self.headers) as c:
            r = await c.get(f"{self.url}{path}", params={k: v for k, v in params.items() if v})
            r.raise_for_status()
            return r.json()

    async def users(self) -> list[dict[str, Any]]:
        return [_norm_user(u) for u in await self._get("/api/users")]

    async def projects(self) -> list[dict[str, Any]]:
        return [_norm_project(p) for p in await self._get("/api/projects")]

    async def tasks(self, since: str | None = None) -> list[dict[str, Any]]:
        return [_norm_task(t) for t in await self._get("/api/tasks", updated_since=since)]

    async def attendance(self, since: str | None = None) -> list[dict[str, Any]]:
        return await self._get("/api/attendance", since=since)

    async def health(self) -> dict[str, Any]:
        try:
            await self._get("/api/health")
            return {"ok": True, "backend": "http", "url": self.url}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "backend": "http", "url": self.url, "error": str(exc)}


def _norm_user(u: dict[str, Any]) -> dict[str, Any]:
    return {"deeds_user_id": str(u.get("id") or u["deeds_user_id"]), "name": u["name"], "role": u.get("role", ""),
            "skills": u.get("skills", []), "teams": u.get("teams", []), "last_completed_at": u.get("last_completed_at")}


def _norm_project(p: dict[str, Any]) -> dict[str, Any]:
    return {"deeds_project_id": str(p.get("id") or p["deeds_project_id"]), "name": p["name"], "team": p.get("team", "")}


def _norm_task(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "deeds_task_id": str(t.get("id") or t["deeds_task_id"]),
        "deeds_project_id": str(t.get("project_id") or t.get("deeds_project_id") or "") or None,
        "deeds_user_id": str(t.get("assignee_id") or t.get("deeds_user_id") or "") or None,
        "title": t["title"], "description": t.get("description", ""),
        "status": STATUS_MAP.get(str(t.get("status", "todo")).lower(), "todo"),
        "priority": str(t.get("priority", "medium")).lower(),
        "due_date": t.get("due_date"), "last_activity_at": t.get("last_activity_at") or t.get("updated_at"),
        "time_consumed_min": int(t.get("time_consumed_min", 0) or 0),
        "comments": t.get("comments", []),
    }


def client() -> DeedsMock | DeedsHTTP:
    if settings.deeds_backend == "http" and settings.deeds_url:
        return DeedsHTTP(settings.deeds_url, settings.deeds_token)
    return DeedsMock()

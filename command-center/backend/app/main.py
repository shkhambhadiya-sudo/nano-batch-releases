"""FastAPI app: the owner's API + static PWA + the scheduler process. One service,
started by launchd on the Mac (spec §8, §10)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, log, memory
from .agents import analyst, cos, doctor, orchestrator, validator
from .config import settings
from .connectors import deeds, matrix
from .llm.gateway import gateway
from .scheduler import Job, Scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

JOBS = [
    Job("orchestrator", orchestrator.run, times=settings.orchestrator_times),
    Job("validator", validator.run, times=settings.validator_times),
    Job("analyst", analyst.run, times=settings.analyst_times),
    Job("cos", cos.run, times=settings.brief_times),
    Job("doctor", doctor.run, interval_hours=settings.doctor_interval_hours),
]
scheduler = Scheduler(JOBS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if settings.scheduler_enabled:
        await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(title="Command Center", lifespan=lifespan)
api = FastAPI()


# ---- models ------------------------------------------------------------------

class Text(BaseModel):
    text: str


class Convert(BaseModel):
    project_id: str | None = None
    owner_id: str | None = None
    due_date: str | None = None


class Decision(BaseModel):
    approved: bool


class FlagDecision(BaseModel):
    decision: str  # accepted | dismissed | discussed
    note: str = ""


class Level(BaseModel):
    level: int


class LinkIn(BaseModel):
    from_task: str
    to_task: str
    type: str


# ---- overview ----------------------------------------------------------------

@api.get("/overview")
def overview() -> dict[str, Any]:
    return {
        "counts": memory.summary_counts(),
        "projects": memory.project_overview(),
        "goals": memory.list_("goals", limit=100),
        "brief": memory.latest_report("daily-brief"),
        "accuracy": memory.suggestion_accuracy(),
    }


# ---- capture / ideas ---------------------------------------------------------

@api.post("/capture")
async def capture(body: Text) -> dict[str, Any]:
    return await cos.capture(body.text.strip())


@api.post("/ideas/{idea_id}/answer")
async def idea_answer(idea_id: str, body: Text) -> dict[str, Any]:
    try:
        return await cos.answer(idea_id, body.text.strip())
    except KeyError:
        raise HTTPException(404)


@api.post("/ideas/{idea_id}/convert")
def idea_convert(idea_id: str, body: Convert) -> dict[str, Any]:
    try:
        return cos.convert(idea_id, project_id=body.project_id, owner_id=body.owner_id, due_date=body.due_date)
    except KeyError:
        raise HTTPException(404)


@api.get("/ideas")
def ideas(status: str | None = None) -> list[dict]:
    return memory.list_("ideas", "status=?", (status,)) if status else memory.list_("ideas")


@api.patch("/ideas/{idea_id}")
def idea_patch(idea_id: str, body: dict[str, Any]) -> dict | None:
    return memory.patch("ideas", idea_id, {k: v for k, v in body.items() if k in ("kind", "project_id", "status")})


# ---- generic CRUD for goals / projects / tasks / people / blockers -----------

CRUD = {"goals": "goal", "projects": "proj", "tasks": "task", "people": "person", "blockers": "blk", "milestones": "ms"}
# Generic /{table} routes live on their own router that is included LAST, so the
# specific routes above and below (/views/..., /system/..., /suggestions) win.
crud = APIRouter()


@crud.get("/{table}")
def list_table(table: str, limit: int = 500) -> list[dict]:
    if table not in CRUD:
        raise HTTPException(404)
    order = "name" if table in ("projects", "people") else "created_at DESC"
    return memory.list_(table, order=order, limit=limit)


@crud.post("/{table}")
def create_row(table: str, body: dict[str, Any]) -> dict:
    if table not in CRUD:
        raise HTTPException(404)
    goal_ids = body.pop("goal_ids", None)
    if table == "blockers":
        body.setdefault("since", db.now_iso())
    if table == "tasks":
        body.setdefault("last_activity_at", db.now_iso())
    row = memory.create(table, CRUD[table], body)
    if table == "projects" and goal_ids is not None:
        memory.set_project_goals(row["id"], goal_ids)
    log.log_action("owner", f"created {table[:-1]}", output_ref=[row["id"]])
    return row


@crud.get("/{table}/{id_}")
def get_row(table: str, id_: str) -> dict:
    if table not in CRUD:
        raise HTTPException(404)
    row = memory.get(table, id_)
    if not row:
        raise HTTPException(404)
    if table == "projects":
        row["goals"] = memory.project_goals(id_)
        row["tasks"] = memory.list_("tasks", "project_id=?", (id_,), limit=1000)
    if table == "tasks":
        row["links"] = memory.links(id_)
    if table == "goals":
        row["projects"] = memory.goal_projects(id_)
    return row


@crud.patch("/{table}/{id_}")
def patch_row(table: str, id_: str, body: dict[str, Any]) -> dict | None:
    if table not in CRUD:
        raise HTTPException(404)
    goal_ids = body.pop("goal_ids", None)
    if table == "tasks" and body:
        body["last_activity_at"] = db.now_iso()
    row = memory.patch(table, id_, body) if body else memory.get(table, id_)
    if table == "projects" and goal_ids is not None:
        memory.set_project_goals(id_, goal_ids)
    log.log_action("owner", f"updated {table[:-1]}", inputs_ref=[id_], notes=",".join(body))
    return row


@crud.delete("/{table}/{id_}")
def delete_row(table: str, id_: str) -> dict:
    if table not in CRUD:
        raise HTTPException(404)
    memory.delete(table, id_)
    log.log_action("owner", f"deleted {table[:-1]}", inputs_ref=[id_])
    return {"ok": True}


@api.post("/links")
def add_link(body: LinkIn) -> dict:
    memory.add_link(body.from_task, body.to_task, body.type, set_by="owner")
    return {"ok": True}


@api.get("/links")
def all_links() -> list[dict]:
    return memory.links()


# ---- derived views -----------------------------------------------------------

@api.get("/views/people-load")
def people_load() -> list[dict]:
    return memory.people_load()


@api.get("/views/blockers")
def blockers() -> list[dict]:
    return memory.open_blockers()


@api.get("/views/stale")
def stale() -> list[dict]:
    return memory.stale_tasks()


@api.get("/views/overdue")
def overdue() -> list[dict]:
    return memory.overdue_tasks()


@api.get("/views/map")
def map_view() -> dict[str, Any]:
    return {"goals": memory.list_("goals", limit=200), "projects": memory.project_overview(),
            "project_goals": [{"project_id": p["id"], "goal_ids": [g["id"] for g in memory.project_goals(p["id"])]} for p in memory.list_("projects", limit=100)],
            "milestones": memory.list_("milestones", limit=1000), "tasks": memory.list_("tasks", limit=5000), "links": memory.links()}


# ---- approvals ---------------------------------------------------------------

@api.get("/suggestions")
def suggestions(status: str = "pending") -> list[dict]:
    rows = memory.list_("suggestions", "status=?", (status,), order="created_at DESC", limit=500)
    tasks = {t["id"]: t for t in memory.list_("tasks", limit=5000)}
    people = {p["id"]: p["name"] for p in memory.list_("people", limit=1000)}
    for s in rows:
        pl = s["payload"]
        s["task"] = tasks.get(pl.get("task_id") or pl.get("from_task"))
        s["task_to"] = tasks.get(pl.get("to_task"))
        s["person_name"] = people.get(pl.get("person_id"))
    return rows


@api.post("/suggestions/{id_}/decide")
def decide(id_: str, body: Decision) -> dict | None:
    s = memory.get("suggestions", id_)
    if not s:
        raise HTTPException(404)
    row = memory.decide_suggestion(id_, body.approved)
    if body.approved:
        _apply_suggestion(s)
    log.log_action("owner", f"{'approved' if body.approved else 'rejected'} suggestion", inputs_ref=[id_])
    return row


def _apply_suggestion(s: dict) -> None:
    """Approved suggestions whose effect lives inside Command Center are applied
    here. Anything that would touch 11deeds (reminders, assignments) is only
    recorded until the agent's permission level allows write access (spec §6)."""
    pl = s["payload"]
    if s["type"] == "link":
        memory.add_link(pl["from_task"], pl["to_task"], pl["link_type"], set_by="owner")
    elif s["type"] in ("assign", "reassign") and pl.get("task_id") and pl.get("person_id"):
        memory.patch("tasks", pl["task_id"], {"owner_id": pl["person_id"]})
    elif s["type"] == "priority" and pl.get("task_id") and pl.get("priority"):
        memory.patch("tasks", pl["task_id"], {"priority": pl["priority"]})
    elif s["type"] == "deadline" and pl.get("task_id") and pl.get("new_due"):
        memory.patch("tasks", pl["task_id"], {"due_date": pl["new_due"]})


@api.get("/flags")
def flags(open_only: bool = True) -> list[dict]:
    rows = memory.list_("flags", "decision IS NULL" if open_only else "1=1", limit=500)
    people = {p["id"]: p for p in memory.list_("people", limit=1000)}
    tasks = {t["id"]: t["title"] for t in memory.list_("tasks", limit=5000)}
    for f in rows:
        f["person"] = people.get(f["person_id"])
        f["task_titles"] = [tasks.get(t, t) for t in f["task_ids"]]
    return rows


@api.post("/flags/{id_}/decide")
def decide_flag(id_: str, body: FlagDecision) -> dict | None:
    log.log_action("owner", f"flag {body.decision}", inputs_ref=[id_], notes=body.note)
    return memory.decide_flag(id_, body.decision, body.note)


@api.get("/permissions")
def permissions() -> list[dict]:
    return memory.suggestion_accuracy()


@api.post("/permissions/{agent}")
def set_permission(agent: str, body: Level) -> dict:
    memory.set_permission_level(agent, body.level)
    log.log_action("owner", f"set {agent} permission level {body.level}")
    return {"agent": agent, "level": memory.permission_level(agent)}


# ---- reports / system ---------------------------------------------------------

@api.get("/reports")
def reports(type_: str | None = None, limit: int = 20) -> list[dict]:
    return memory.list_("reports", "type=?", (type_,), limit=limit) if type_ else memory.list_("reports", limit=limit)


@api.get("/system/health")
async def health() -> dict[str, Any]:
    return {
        "llm": await gateway.health(), "deeds": await deeds.client().health(), "matrix": await matrix.client().health(),
        "runs": memory.list_("agent_runs", order="started_at DESC", limit=40),
        "doctor": memory.latest_report("doctor"),
        "schedule": {"orchestrator": settings.orchestrator_times, "validator": settings.validator_times,
                     "analyst": settings.analyst_times, "brief": settings.brief_times, "doctor_every_h": settings.doctor_interval_hours},
    }


@api.get("/system/log")
def activity_log(limit: int = 200, agent: str | None = None) -> list[dict]:
    return log.recent(limit=limit, agent=agent)


@api.get("/system/log/sanitized")
def activity_log_sanitized(since: str | None = None) -> list[dict]:
    return log.sanitized_export(since=since)


@api.post("/system/run/{agent}")
async def run_agent(agent: str) -> dict:
    if agent not in {j.agent for j in JOBS}:
        raise HTTPException(404)
    run_id = await scheduler.trigger(agent)
    return {"run": memory.get("agent_runs", run_id)}


api.include_router(crud)
app.mount("/api", api)

# ---- PWA ----------------------------------------------------------------------
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    def root() -> dict:
        return {"ok": True, "note": "frontend not built; run `npm run build` in frontend/", "api": "/api/overview"}

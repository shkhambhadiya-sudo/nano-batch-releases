"""Core behaviour tests: memory views, scheduler catch-up, COS interview, agents end-to-end on mock data."""
from __future__ import annotations

import dataclasses
import importlib
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

os.environ["CC_LLM_BACKEND"] = "mock"
os.environ["CC_SCHEDULER"] = "0"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path, monkeypatch):
    from app import config, db
    # settings is a frozen dataclass; swap the module-level instance for a test copy.
    test_settings = dataclasses.replace(config.settings, db_path=tmp_path / "t.db")
    for mod in ("app.config", "app.db", "app.memory", "app.agents.validator", "app.agents.doctor"):
        monkeypatch.setattr(importlib.import_module(mod), "settings", test_settings)
    db.init_db(tmp_path / "t.db")
    yield


def test_memory_crud_and_views():
    from app import memory
    g = memory.create("goals", "goal", {"title": "Revenue"})
    p = memory.create("projects", "proj", {"name": "Aurora"})
    memory.set_project_goals(p["id"], [g["id"]])
    person = memory.create("people", "person", {"name": "A", "skills": ["seo"], "teams": ["Growth"]})
    t = memory.create("tasks", "task", {"title": "X", "project_id": p["id"], "owner_id": person["id"],
                                        "due_date": "2020-01-01", "last_activity_at": "2020-01-01T00:00:00+00:00"})
    assert memory.project_goals(p["id"])[0]["id"] == g["id"]
    assert memory.get("people", person["id"])["skills"] == ["seo"]
    assert [x["id"] for x in memory.overdue_tasks()] == [t["id"]]
    assert [x["id"] for x in memory.stale_tasks()] == [t["id"]]
    assert memory.idle_people() == []
    memory.patch("tasks", t["id"], {"status": "done"})
    assert memory.idle_people()[0]["id"] == person["id"]
    c = memory.summary_counts()
    assert c["projects"] == 1 and c["open_tasks"] == 0 and c["idle_people"] == 1


def test_suggestion_accuracy_and_permissions():
    from app import memory
    s1 = memory.suggest("orchestrator", "reminder", {"task_id": "x"}, "r")
    s2 = memory.suggest("orchestrator", "reminder", {"task_id": "y"}, "r")
    memory.decide_suggestion(s1["id"], True)
    memory.decide_suggestion(s2["id"], False)
    acc = memory.suggestion_accuracy()[0]
    assert acc["accuracy"] == 50 and acc["level"] == 0
    memory.set_permission_level("orchestrator", 9)
    assert memory.permission_level("orchestrator") == 3


def test_activity_log_sanitized():
    from app import log
    log.log_action("cos", "did thing", notes="contains employee name", error=None)
    with pytest.raises(ValueError):
        with log.activity("cos", "fails"):
            raise ValueError("boom")
    rows = log.recent()
    assert rows[0]["result"] == "error" and "boom" in rows[0]["error"]
    san = log.sanitized_export()
    assert all("notes" not in r for r in san)


def test_scheduler_is_due_runs_once_after_gap():
    from app import db
    from app.scheduler import Job, is_due

    async def noop(run_id, since):
        pass

    job = Job("orchestrator", noop, times=("09:00", "18:00"))
    assert is_due(job)  # never ran
    now = datetime.now().astimezone()
    # last ok run 30 hours ago -> several slots missed, is_due is True exactly once (one run covers all)
    with db.connect() as conn:
        db.insert(conn, "agent_runs", {"id": "r1", "agent": "orchestrator", "started_at": (now - timedelta(hours=30)).isoformat(),
                                       "finished_at": (now - timedelta(hours=30)).isoformat(), "status": "ok", "covered_until": (now - timedelta(hours=30)).isoformat()})
    assert is_due(job)
    with db.connect() as conn:
        db.insert(conn, "agent_runs", {"id": "r2", "agent": "orchestrator", "started_at": now.isoformat(),
                                       "finished_at": now.isoformat(), "status": "ok", "covered_until": now.isoformat()})
    assert not is_due(job)
    interval = Job("doctor", noop, interval_hours=6)
    assert is_due(interval)


async def test_run_job_records_error_and_mark_interrupted():
    from app import db, memory
    from app.scheduler import Job, mark_interrupted, run_job

    async def bad(run_id, since):
        raise RuntimeError("nope")

    rid = await run_job(Job("validator", bad, times=("08:00",)))
    assert memory.get("agent_runs", rid)["status"] == "error"
    with db.connect() as conn:
        db.insert(conn, "agent_runs", {"id": "stuck", "agent": "cos", "started_at": db.now_iso(), "status": "running"})
    assert mark_interrupted() == 1
    assert memory.get("agent_runs", "stuck")["status"] == "error"


async def test_cos_interview_and_convert():
    from app import memory
    from app.agents import cos
    memory.create("projects", "proj", {"name": "Aurora Skincare"})
    idea = await cos.capture("Launch a referral program for Aurora skincare")
    assert idea["kind"] == "task" and idea["pending_question"] and idea["project_id"]
    idea = await cos.answer(idea["id"], "100 signups")
    if idea["pending_question"]:
        idea = await cos.answer(idea["id"], "Nov 5")
    assert idea["status"] == "refined"
    out = cos.convert(idea["id"], due_date="2026-11-05")
    assert out["created"]["title"].startswith("Launch a referral")
    assert memory.get("ideas", idea["id"])["status"] == "converted"
    b = await cos.capture("Blocked: waiting on API keys")
    assert b["kind"] == "blocker"


async def test_agents_end_to_end_on_mock_data():
    from app import memory
    from app.agents import analyst, cos, doctor, orchestrator, validator
    from app.scheduler import Job, run_job
    memory.create("goals", "goal", {"title": "Grow", "deadline": "2026-12-31"})
    for name, fn in [("orchestrator", orchestrator.run), ("validator", validator.run), ("analyst", analyst.run),
                     ("doctor", doctor.run), ("cos", cos.run)]:
        rid = await run_job(Job(name, fn, times=("00:00",)))
        assert memory.get("agent_runs", rid)["status"] == "ok", name
    c = memory.summary_counts()
    assert c["projects"] == 18 and c["people"] == 40 and c["open_tasks"] > 0
    assert c["pending_suggestions"] > 0 and c["open_blockers"] > 0
    assert memory.latest_report("daily-brief") and memory.latest_report("doctor")
    # Second orchestrator run must not duplicate pending suggestions for the same task.
    before = c["pending_suggestions"]
    await run_job(Job("orchestrator", orchestrator.run, times=("00:00",)))
    assert memory.summary_counts()["pending_suggestions"] == before


def test_api_smoke():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/overview").status_code == 200
        r = c.post("/api/goals", json={"title": "G"}); assert r.status_code == 200
        gid = r.json()["id"]
        r = c.post("/api/projects", json={"name": "P", "goal_ids": [gid]}); pid = r.json()["id"]
        assert c.get(f"/api/projects/{pid}").json()["goals"][0]["id"] == gid
        r = c.post("/api/capture", json={"text": "Fix checkout bug on P store by friday"})
        assert r.json()["kind"] == "task"
        assert c.get("/api/system/health").json()["llm"]["ok"]
        assert c.post("/api/system/run/orchestrator").json()["run"]["status"] == "ok"
        assert len(c.get("/api/suggestions").json()) > 0
        assert c.post("/api/system/run/nope").status_code == 404
